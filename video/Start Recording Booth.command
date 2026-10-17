#!/bin/zsh
# Double-click to start the recording booth. Keep this window open while recording.
cd "$(dirname "$0")"
pkill -f "narration/serve.mjs" 2>/dev/null
(sleep 2 && open -a "Google Chrome" "http://localhost:4400/narration/booth.html" 2>/dev/null || open "http://localhost:4400/narration/booth.html") &
node narration/serve.mjs
