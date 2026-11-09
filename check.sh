#!/usr/bin/env bash
# Reports whether the explainer-videos pipeline can run on this machine.
ok=1
have() { command -v "$1" >/dev/null 2>&1; }
have uv     && echo "uv:      ok ($(uv --version 2>/dev/null))"     || { echo "uv:      MISSING  (brew install uv, or https://docs.astral.sh/uv/)"; ok=0; }
have ffmpeg && echo "ffmpeg:  ok ($(ffmpeg -version 2>/dev/null | head -1 | cut -d' ' -f3))" || { echo "ffmpeg:  MISSING  (brew install ffmpeg)"; ok=0; }
chrome=""
for c in "$CHROME" "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" "/Applications/Chromium.app/Contents/MacOS/Chromium" \
         "$(command -v google-chrome 2>/dev/null)" "$(command -v google-chrome-stable 2>/dev/null)" "$(command -v chromium 2>/dev/null)" "$(command -v chromium-browser 2>/dev/null)"; do
  [ -n "$c" ] && [ -x "$c" ] && chrome="$c" && break
done
[ -n "$chrome" ] && echo "chrome:  ok ($chrome)" || { echo "chrome:  MISSING  (brew install --cask google-chrome, or set CHROME=/path/to/chrome)"; ok=0; }
here="$(cd "$(dirname "$0")" && pwd)"
if [ -n "$ASSEMBLYAI_API_KEY" ]; then echo "api key: ok (environment)"
elif grep -qs '^ASSEMBLYAI_API_KEY=' "$here/.env"; then echo "api key: ok ($here/.env)"
elif grep -qs '^ASSEMBLYAI_API_KEY=' "$HOME/.config/explainer-videos/.env"; then echo "api key: ok (~/.config/explainer-videos/.env)"
else echo "api key: MISSING  (export ASSEMBLYAI_API_KEY=..., or put ASSEMBLYAI_API_KEY=... in ~/.config/explainer-videos/.env; free key at https://www.assemblyai.com/dashboard)"; ok=0; fi
[ "$ok" = 1 ] && echo "All set." || { echo "Fix the MISSING lines above, then run again."; exit 1; }
