# Explainer Videos

Turn a Markdown script into a narrated slide video, with diagrams on screen, a voice explaining the detail, and captions timed to the voice. Built for learning: ask Claude to teach you a topic, get a ten-minute video and an audio-only version to listen to on a walk.

- **Slides** are HTML, rendered by headless Chrome. A small stylesheet gives you flow diagrams, cards, bars, timelines and numbered steps; inline SVG works too.
- **Narration** is [AssemblyAI text-to-speech](https://www.assemblyai.com/docs/speech-to-text/text-to-speech). The API returns the start and end time of every word, so captions need no second transcription pass.
- **ffmpeg** stitches it together: one still per section, timed to the audio, captions burned in, plus an `.m4a` of the narration alone.

Each section's audio and slide are cached by content, so editing one slide re-voices only that slide. A ten-minute video costs about ten thousand characters of TTS.

## Install

You need Python with [uv](https://docs.astral.sh/uv/), [ffmpeg](https://ffmpeg.org/) and Google Chrome (or Chromium). On a Mac:

```bash
brew install uv ffmpeg
brew install --cask google-chrome   # if you don't have it
git clone https://github.com/markthompson-aai/explainer-videos
cd explainer-videos
```

Put your AssemblyAI API key where the build can find it: in the environment as `ASSEMBLYAI_API_KEY`, in `.env` next to `build.py`, or in `~/.config/explainer-videos/.env`. A free key is at <https://www.assemblyai.com/dashboard>.

```bash
echo 'ASSEMBLYAI_API_KEY=your_key_here' > .env
```

## Build the example

```bash
uv run build.py streaming-stt --dry-run   # print what the voice will read, and the character count
uv run build.py streaming-stt --slides    # render the slide PNGs only, no API calls
uv run build.py streaming-stt             # voice it and build topics/streaming-stt/out/streaming-stt.mp4
```

Other flags: `--audio-only` voices the script and writes just the `.m4a`; `--no-captions` leaves captions in the `.srt` instead of burning them in; `--voice aai-<name>` picks a voice (default `aai-anna`, catalogue in the [dashboard](https://www.assemblyai.com/dashboard/text-to-speech/voices)); `--file path/to/script.md` builds a script outside `topics/`, with output in an `out/` folder next to it.

## Let Claude write the script

The fun part is not typing the script yourself. This repo is also a Claude Code plugin with a `learn` skill: say `/explainer-videos:learn how HTTP caching works` and Claude researches the topic, writes the script, renders the slides for you to check, then voices and builds it.

```
/plugin marketplace add markthompson-aai/explainer-videos
/plugin install explainer-videos@explainer-videos
```

Then, in any project, `/explainer-videos:learn <topic>` (plain `/learn` also works when nothing else claims that name). Add `short` or `deep` for length, `audio` for narration only, or `go` to skip the slide check. The skill checks for uv, ffmpeg, Chrome and the API key on first run and tells you what is missing. Scripts land in `explainer-videos/topics/<slug>/` in the current directory, so your videos live with whatever you were working on.

The same plugin works in the Claude Code tab of the Claude desktop app (run the marketplace add once in a terminal; the app shares the same settings).

## Script format

One Markdown file per topic. Frontmatter, then one `## ` section per slide. Inside a section, an optional ```` ```slide ```` block holds the slide's HTML; everything else is narration.

````markdown
---
title: How streaming speech-to-text works
subtitle: One line under the title on the opening slide
voice: aai-anna
---

## How streaming speech-to-text works
```slide
@layout title
```
Narration for the title slide.

## The pipeline, end to end
```slide
<div class="flow">
  <div class="box"><b>Microphone</b><small>16 kHz PCM</small></div><span class="arrow"></span>
  <div class="box accent"><b>Model</b><small>encoder and decoder</small></div>
</div>
<p class="note">One line of commentary under the diagram.</p>
```
Plain prose. A paragraph break becomes a short pause. Write numbers and units out
in words where the reading matters ("sixteen kilohertz", not "16 kHz").

## Sources
A `## Sources` or `## Notes` section at the end is kept in the file but never rendered or voiced.
````

Slide helpers in `slide.html`:

| Class | What it draws |
|---|---|
| `.flow` with `.box` (`.accent`, `.warm`) and `.arrow` | Left-to-right pipeline; `.flow.vertical` stacks it |
| `.cols`, `.cols-3`, `.cols-4` with `.card` (`.card.accent`) | Two to four cards |
| `.bars` with `.bar` and `style="--w:40%"` (`.warm`, `.teal`, `.muted`) | Horizontal bars with a label and a value |
| `.timeline` rows with `.t`, `.txt`, `.tag` (`.final` on a row) | Timestamped rows, a highlighted last row |
| `.steps` | Numbered list |
| `.big` | One large number with a caption |
| `.note`, `.kicker`, `<mark>` | Commentary line, small heading, highlight |

Edit `slide.html` to restyle everything at once: colours are CSS variables at the top.

## How it works

`build.py` is a single-file [uv script](https://docs.astral.sh/uv/guides/scripts/). It parses the script, renders each slide with `chrome --headless --screenshot` at 1920x1080, streams each section's narration from the TTS events endpoint (24 kHz PCM plus word timings), groups the words into caption cues that always end at a sentence boundary, writes a concat list and an `.srt`, and runs one ffmpeg command. Slides are cached by a hash of their HTML, audio by a hash of the voice and text.

## Licence

MIT. Voices and the TTS API are AssemblyAI's; you need your own key and pay for your own characters.
