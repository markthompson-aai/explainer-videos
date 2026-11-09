---
name: learn
description: Teach the user a topic as a narrated slide video (diagrams on screen, a voice explaining, captions) plus an audio-only version, built with the explainer-videos pipeline. Use when the user says /learn <topic>, "teach me X", "make an explainer video on X", or wants to learn something as video or audio.
---

Teach the user the topic in `$ARGUMENTS` by writing a script and building it with the explainer-videos pipeline at `${CLAUDE_PLUGIN_ROOT}`. People learn best from a diagram and a voice explaining it, so slides carry diagrams and a few words, and the narration carries the explanation.

## First run: check the tools

Run `${CLAUDE_PLUGIN_ROOT}/check.sh`. It reports whether `uv`, `ffmpeg`, Chrome and an AssemblyAI API key are available. If something is missing, tell the user exactly what to install (on a Mac: `brew install uv ffmpeg`, `brew install --cask google-chrome`) and where to put the key (`ASSEMBLYAI_API_KEY` in the environment, or in `~/.config/explainer-videos/.env`; free key at https://www.assemblyai.com/dashboard). Stop until they have it.

## Inputs

- **Topic**: `$ARGUMENTS`. If it names a file, URL or note, read that and teach from it. Otherwise research it from primary sources (official docs, papers, the project's own code) before writing anything.
- **Depth**: default 5 to 7 slides and 5 to 7 minutes of narration (roughly 5,000 to 7,000 characters). `short` means 3 to 4 slides, `deep` means 10 to 12.
- **Form**: `audio` means audio only (`--audio-only`, no slides). Otherwise make the video; an `.m4a` comes with it anyway.
- **Where**: `./explainer-videos/topics/<slug>/script.md` in the current working directory, slug lowercase with hyphens. If that folder exists, ask whether to rebuild or extend it.

## Writing the script

Read `${CLAUDE_PLUGIN_ROOT}/README.md` (script format, slide helpers) and `${CLAUDE_PLUGIN_ROOT}/topics/streaming-stt/script.md` (a worked example) before writing.

1. Decide what the user should be able to explain to someone else by the end, then work backwards. One idea per slide, in a teacher's order: what it is, how it works (the diagram slide), where it goes wrong or the trade-offs, how it shows up in practice, recap.
2. Every slide gets a ```slide block using the helpers in `slide.html` (`.flow`, `.cols`, `.bars`, `.timeline`, `.steps`, inline SVG). Prefer a diagram to bullets. On-screen text is labels; the narration says the rest. The first section is the title slide: a ```slide block containing only `@layout title`.
3. Narration is spoken English for a text-to-speech voice: short sentences, numbers and units written as words where the reading matters, paragraph breaks as pauses, no markdown, no code. Explain every term the first time it appears.
4. End the file with a `## Sources` section listing what you taught from. It is kept but never voiced.

## Building

1. `uv run ${CLAUDE_PLUGIN_ROOT}/build.py --file explainer-videos/topics/<slug>/script.md --dry-run` to check the character count.
2. `... --slides` and look at every PNG in `explainer-videos/topics/<slug>/out/slides/` yourself. Fix overlaps, overflow and anything that reads badly before voicing. Show the user the PNG paths and the character count, and wait for their OK unless `$ARGUMENTS` contains `go`.
3. `uv run ${CLAUDE_PLUGIN_ROOT}/build.py --file explainer-videos/topics/<slug>/script.md` (add `--audio-only` for audio). Spot-check two frames of the finished video for captions (`ffmpeg -ss 60 -i <mp4> -frames:v 1 -update 1 frame.png`).

## Reply

Lead with the `open` command for the `.mp4` and the `.m4a` path, then the length, slide count and characters billed, then the three things the video should leave them able to explain. Offer the obvious next topic in one line if there is one.

$ARGUMENTS
