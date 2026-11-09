#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx>=0.27"]
# ///
"""Build a narrated slide video from a Markdown script.

  uv run build.py streaming-stt             topics/streaming-stt/script.md -> topics/streaming-stt/out/streaming-stt.mp4
  uv run build.py streaming-stt --slides    render the slide PNGs only (no API calls), to check the visuals
  uv run build.py streaming-stt --dry-run   print what the voice will read; nothing is rendered or billed
  uv run build.py --file path/to/script.md  a script outside topics/
  uv run build.py streaming-stt --no-captions   leave the captions as a .srt next to the video, not burned in

Pipeline, per section of the script:
  slide HTML -> headless Chrome screenshot (1920x1080 PNG)
  narration  -> AssemblyAI TTS (/v1/speech/events: audio + the time of each word)
then one ffmpeg pass: slides timed to the audio, captions from the word timings.

Needs ASSEMBLYAI_API_KEY in the environment, in .env next to this script, next to
the script being built, or in ~/.config/explainer-videos/.env. Audio and video land
in <topic>/out/ (gitignored) and are cached: edit one section and only that section
is re-voiced or re-drawn. The script format is described in README.md.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import wave
from dataclasses import dataclass, field
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
TOPICS = HERE / "topics"
TEMPLATE = HERE / "slide.html"
CHROME_CANDIDATES = [
    os.environ.get("CHROME", ""),
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    *(shutil.which(n) or "" for n in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome")),
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
]
CHROME = next((c for c in CHROME_CANDIDATES if c and Path(c).exists()), "")
TTS_URL = "https://tts.us.assemblyai.com/v1/speech/events"
SAMPLE_RATE = 24_000
DEFAULT_VOICE = "aai-anna"  # same voice as the voice-buddy project
LEAD_MS = 600      # silence before the first word
GAP_MS = 900       # silence between sections (slide change breathes)
TAIL_MS = 1500     # hold the last slide
MAX_CHARS = 4500   # per TTS request (API limit is 5,000)
CAPTION_CHARS = 46 # longest caption line before we break


# ---------- script ----------

@dataclass
class Section:
    title: str
    slide_html: str | None
    layout: str
    narration: str
    pcm: bytes = b""
    words: list[dict] = field(default_factory=list)
    png: Path | None = None

    @property
    def duration_ms(self) -> int:
        return int(len(self.pcm) / 2 / SAMPLE_RATE * 1000)


def read_frontmatter(text: str) -> tuple[dict, str]:
    m = re.match(r"---\n(.*?)\n---\n?", text, re.S)
    if not m:
        return {}, text
    meta = {}
    for line in m.group(1).splitlines():
        key, sep, value = line.partition(":")
        if sep:
            meta[key.strip()] = value.strip().strip("\"'")
    return meta, text[m.end():]


def speakable(md: str) -> str:
    """Narration as the voice should read it. Paragraph breaks stay (the model pauses there)."""
    t = re.sub(r"<!--.*?-->", "", md, flags=re.S)
    t = re.sub(r"\[\[[^\]|]*\|([^\]]*)\]\]", r"\1", t)
    t = re.sub(r"\[\[([^\]]*)\]\]", lambda m: m.group(1).split("/")[-1], t)
    t = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", t)
    t = re.sub(r"^\s*[-*>]+\s*", "", t, flags=re.M)
    t = re.sub(r"[*_`]", "", t)
    paragraphs = [re.sub(r"\s+", " ", p).strip() for p in re.split(r"\n\s*\n", t)]
    return "\n".join(p for p in paragraphs if p)


def parse_script(path: Path) -> tuple[dict, list[Section]]:
    meta, body = read_frontmatter(path.read_text())
    body = re.sub(r"^# .*\n", "", body, count=1, flags=re.M)  # optional top-level title line
    sections = []
    for chunk in re.split(r"^## +", body, flags=re.M)[1:]:
        title, _, rest = chunk.partition("\n")
        if title.strip().lower() in ("sources", "notes"):
            continue  # reference material at the end of the script, not a slide
        slide_html, layout = None, "default"
        if m := re.search(r"```slide\n(.*?)\n?```", rest, re.S):
            slide_html = m.group(1)
            rest = rest[:m.start()] + rest[m.end():]
            if lm := re.match(r"\s*@layout +(\w+)\s*\n?", slide_html):
                layout = lm.group(1)
                slide_html = slide_html[lm.end():]
        narration = speakable(rest)
        if not narration:
            sys.exit(f"Section '{title.strip()}' has no narration")
        sections.append(Section(title.strip(), slide_html, layout, narration))
    if not sections:
        sys.exit(f"No '## ' sections in {path}")
    return meta, sections


# ---------- slides ----------

def slide_page(meta: dict, section: Section, index: int, total: int) -> str:
    html = TEMPLATE.read_text()
    body = section.slide_html or ""
    if section.layout == "title":
        body = (f'<div class="title-slide"><h1>{section.title}</h1>'
                f'<p class="subtitle">{meta.get("subtitle", "")}</p>{body}</div>')
        heading = ""
    else:
        heading = f"<h2>{section.title}</h2>"
    return (html.replace("{{topic}}", meta.get("title", ""))
                .replace("{{counter}}", f"{index} / {total}")
                .replace("{{layout}}", section.layout)
                .replace("{{heading}}", heading)
                .replace("{{body}}", body))


def render_slides(meta: dict, sections: list[Section], out: Path) -> None:
    if not CHROME:
        sys.exit("Google Chrome (or Chromium) not found. Install it, or set CHROME=/path/to/chrome")
    slides_dir = out / "slides"
    slides_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as profile:
        for i, s in enumerate(sections, 1):
            page = slide_page(meta, s, i, len(sections))
            digest = hashlib.sha1(page.encode()).hexdigest()[:12]
            html_path = slides_dir / f"{i:02d}.html"
            png = slides_dir / f"{i:02d}.png"
            stamp = slides_dir / f"{i:02d}.hash"
            s.png = png
            if png.exists() and stamp.exists() and stamp.read_text() == digest:
                continue
            html_path.write_text(page)
            print(f"  slide {i:02d}: {s.title}", flush=True)
            subprocess.run([
                CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
                "--force-device-scale-factor=1", f"--user-data-dir={profile}",
                "--window-size=1920,1080", "--virtual-time-budget=1500",
                f"--screenshot={png}", html_path.as_uri(),
            ], check=True, capture_output=True)
            stamp.write_text(digest)


# ---------- voice ----------

def api_key(near: Path | None = None) -> str:
    if key := os.environ.get("ASSEMBLYAI_API_KEY"):
        return key
    places = [HERE / ".env", Path.home() / ".config" / "explainer-videos" / ".env"]
    if near:
        places.insert(0, near / ".env")  # .env next to the script being built
    for env in places:
        if env.exists():
            for line in env.read_text().splitlines():
                if line.startswith("ASSEMBLYAI_API_KEY="):
                    return line.split("=", 1)[1].strip().strip("\"'")
    sys.exit("Set ASSEMBLYAI_API_KEY, or put ASSEMBLYAI_API_KEY=... in .env next to build.py "
             "or in ~/.config/explainer-videos/.env (free key: https://www.assemblyai.com/dashboard)")


def split_text(text: str, limit: int = MAX_CHARS) -> list[str]:
    if len(text) <= limit:
        return [text]
    out, current = [], ""
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        if current and len(current) + len(sentence) + 1 > limit:
            out.append(current.strip())
            current = ""
        current += sentence + " "
    return out + ([current.strip()] if current.strip() else [])


def tts(text: str, voice: str, key: str, client: httpx.Client) -> tuple[bytes, list[dict], int]:
    """One /v1/speech/events request: PCM16 audio, word timings (ms from start), billed characters."""
    audio, words, billed, ended, event = bytearray(), [], 0, False, None
    body = {"text": text, "voice_id": voice, "sample_rate": SAMPLE_RATE, "encoding": "pcm_s16le"}
    with client.stream("POST", TTS_URL, headers={"Authorization": key}, json=body) as r:
        if r.status_code != 200:
            r.read()
            sys.exit(f"TTS {r.status_code}: {r.text[:400]}")
        for line in r.iter_lines():
            if line.startswith(":"):
                continue
            if line.startswith("event: "):
                event = line[7:]
            elif line.startswith("data: "):
                data = json.loads(line[6:])
                if event == "Audio":
                    audio += base64.b64decode(data["audio"])
                elif event == "WordBoundaries":
                    words = data["words"]
                elif event == "Termination":
                    billed, ended = data.get("billed_characters", 0), True
                elif event == "Error":
                    sys.exit(f"TTS error {data.get('code')}: {data.get('message')} ({data.get('request_id')})")
    if not ended:
        raise RuntimeError("TTS stream was cut before Termination")
    return bytes(audio), words, billed


def voice_sections(sections: list[Section], voice: str, out: Path) -> int:
    audio_dir = out / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    key, total_billed = api_key(out.parent), 0
    with httpx.Client(timeout=httpx.Timeout(10.0, read=90.0)) as client:
        for i, s in enumerate(sections, 1):
            digest = hashlib.sha1(f"{voice}\n{s.narration}".encode()).hexdigest()[:12]
            pcm_path, meta_path = audio_dir / f"{i:02d}.pcm", audio_dir / f"{i:02d}.json"
            if pcm_path.exists() and meta_path.exists():
                cached = json.loads(meta_path.read_text())
                if cached.get("hash") == digest:
                    s.pcm, s.words = pcm_path.read_bytes(), cached["words"]
                    continue
            print(f"  voice {i:02d}: {s.title} ({len(s.narration)} chars)", flush=True)
            pcm, words = bytearray(), []
            for part in split_text(s.narration):
                for attempt in (1, 2):
                    try:
                        a, w, billed = tts(part, voice, key, client)
                        break
                    except (RuntimeError, httpx.HTTPError) as e:
                        if attempt == 2:
                            sys.exit(f"TTS failed twice on section {i}: {e}")
                        print(f"    retrying ({e})", flush=True)
                offset = int(len(pcm) / 2 / SAMPLE_RATE * 1000)
                words += [{**x, "start": x["start"] + offset, "end": x["end"] + offset} for x in w]
                pcm += a
                total_billed += billed
            s.pcm, s.words = bytes(pcm), words
            pcm_path.write_bytes(s.pcm)
            meta_path.write_text(json.dumps({"hash": digest, "words": words}))
    return total_billed


# ---------- assemble ----------

def silence(ms: int) -> bytes:
    return b"\x00\x00" * int(SAMPLE_RATE * ms / 1000)


def srt_time(ms: int) -> str:
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def captions(words: list[dict]) -> list[tuple[int, int, str]]:
    """Group timed words into short caption lines, breaking at sentence ends or length."""
    cues, line, start = [], [], None
    for w in words:
        text = re.sub(r"<[^>]+>", "", w["word"])
        if not text or w["end"] == w["start"] and not text.strip():
            continue
        if line and len(" ".join(line + [text])) > CAPTION_CHARS:
            cues.append((start, prev_end, " ".join(line)))
            line, start = [], None
        if start is None:
            start = w["start"]
        line.append(text)
        prev_end = w["end"]
        if re.search(r"[.!?:]$", text):  # a cue never runs across a sentence
            cues.append((start, prev_end, " ".join(line)))
            line, start = [], None
    if line:
        cues.append((start, prev_end, " ".join(line)))
    # let each cue linger briefly, but never into the next one
    out = []
    for i, (a, b, t) in enumerate(cues):
        nxt = cues[i + 1][0] if i + 1 < len(cues) else b + 10_000
        out.append((a, min(b + 400, nxt - 40), t))
    return out


def assemble(meta: dict, sections: list[Section], out: Path, slug: str, burn_captions: bool, video_too: bool = True) -> Path:
    pcm, cues, concat, t = bytearray(silence(LEAD_MS)), [], [], LEAD_MS
    for i, s in enumerate(sections):
        for a, b, text in captions(s.words):
            cues.append((a + t, b + t, text))
        pcm += s.pcm
        t += s.duration_ms
        hold = (GAP_MS if i < len(sections) - 1 else TAIL_MS)
        pcm += silence(hold)
        seconds = (s.duration_ms + hold + (LEAD_MS if i == 0 else 0)) / 1000
        if s.png:
            concat.append(f"file 'slides/{s.png.name}'\nduration {seconds:.3f}")
        t += hold
    if sections[-1].png:
        concat.append(f"file 'slides/{sections[-1].png.name}'")  # concat demuxer needs the last frame repeated

    wav = out / "narration.wav"
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(bytes(pcm))
    if concat:
        (out / "slides.txt").write_text("\n".join(concat) + "\n")
    srt = out / f"{slug}.srt"
    srt.write_text("".join(f"{n}\n{srt_time(a)} --> {srt_time(b)}\n{text}\n\n" for n, (a, b, text) in enumerate(cues, 1)))

    # libass sizes against a 384x288 canvas, so FontSize=13 is about 49px on 1080p
    style = ("FontName=Helvetica Neue,FontSize=13,Bold=0,PrimaryColour=&H00FFFFFF,"
             "BackColour=&H50141028,OutlineColour=&H50141028,BorderStyle=4,Outline=0,Shadow=0,"
             "MarginV=26,MarginL=40,MarginR=40,Alignment=2")
    vf = "fps=30,scale=1920:1080:flags=lanczos"  # fps first: concat gives one frame per slide, captions need frames to land on
    if burn_captions:
        vf += f",subtitles={srt.name}:force_style='{style}'"
    vf += ",format=yuv420p"
    audio = out / f"{slug}.m4a"  # audio-only version, for listening like an audiobook
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", wav.name, "-c:a", "aac", "-b:a", "96k",
                    "-metadata", f"title={meta.get('title', slug)}", "-movflags", "+faststart", audio.name],
                   cwd=out, check=True)
    if not video_too:
        return audio

    video = out / f"{slug}.mp4"
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", "slides.txt",
           "-i", wav.name, "-vf", vf, "-c:v", "libx264", "-preset", "medium", "-crf", "19",
           "-tune", "stillimage", "-c:a", "aac", "-b:a", "160k",
           "-movflags", "+faststart", "-shortest", video.name]
    print("  ffmpeg: stitching", flush=True)
    subprocess.run(cmd, cwd=out, check=True)
    return video


# ---------- main ----------

def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("topic", nargs="?", help="folder name under topics/")
    p.add_argument("--file", type=Path, help="script.md to build instead of a topic")
    p.add_argument("--voice", help=f"voice_id (default from the script, else {DEFAULT_VOICE})")
    p.add_argument("--slides", action="store_true", help="render slide PNGs only; no API calls")
    p.add_argument("--dry-run", action="store_true", help="print the narration and stop")
    p.add_argument("--no-captions", action="store_true", help="don't burn captions in (the .srt is still written)")
    p.add_argument("--audio-only", action="store_true", help="voice the script and write <slug>.m4a; no slides or video")
    args = p.parse_args()

    if args.file:
        script, slug = args.file.resolve(), args.file.resolve().parent.name
    elif args.topic:
        script, slug = TOPICS / args.topic / "script.md", args.topic
    else:
        p.error("give a topic (folder under topics/) or --file")
    if not script.exists():
        sys.exit(f"No script at {script}")
    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg not found on PATH")

    meta, sections = parse_script(script)
    voice = args.voice or meta.get("voice", DEFAULT_VOICE)
    out = script.parent / "out"

    if args.dry_run:
        for i, s in enumerate(sections, 1):
            print(f"## {i}. {s.title}  [{s.layout}, {'slide' if s.slide_html else 'title only'}]\n{s.narration}\n")
        chars = sum(len(s.narration) for s in sections)
        print(f"{len(sections)} sections, {chars} characters, roughly {chars / 15 / 60:.1f} minutes of speech")
        return

    if not args.audio_only:
        print(f"Rendering slides for '{meta.get('title', slug)}'", flush=True)
        render_slides(meta, sections, out)
        if args.slides:
            print(f"Slides in {out / 'slides'}")
            return

    print("Voicing", flush=True)
    billed = voice_sections(sections, voice, out)
    made = assemble(meta, sections, out, slug, burn_captions=not args.no_captions, video_too=not args.audio_only)
    total = sum(s.duration_ms for s in sections) / 1000
    print(f"Done: {made}  ({total // 60:.0f}:{total % 60:02.0f} of narration, {billed} characters billed this run)")
    if not args.audio_only:
        print(f"      {out / f'{slug}.m4a'}  (audio only)")


if __name__ == "__main__":
    main()
