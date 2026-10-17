#!/bin/zsh
# Builds the video from what is in capture/raw/: facts, lines, guide voice, effects, music, picture, and
# out/knockout-demo.mp4, then checks it is exactly 180 s.
#
#   ./build.sh                 the full 1080p render with the guide voice, or the recorded narration if one exists
#   ./build.sh --draft         a faster 1080p30 draft into renders/draft.mp4 (nothing copied to out/)
#   ./build.sh --music=b       use the second music option (audio/music-b.wav); set it in project.json to keep it
#
# Run capture/capture-all.sh first whenever the app's state changed (a key was added, footage recorded).
set -e
cd "$(dirname "$0")"
draft=false
# The music option in project.json (audio/music-a.wav or music-b.wav) is the default; --music= overrides it.
variant=$(node -e 'console.log(require("./project.json").music?.file?.match(/music-(\w+)\.wav/)?.[1] ?? "a")')
for argument in "$@"; do
  case $argument in
    --draft) draft=true ;;
    --music=*) variant=${argument#--music=} ;;
  esac
done

./capture/prepare.sh
node capture/facts.mjs
node lib/cues.mjs
voice_log=$(node audio/guide-vo.mjs)
echo "$voice_log" | grep -E "warning|wrote" || true
if echo "$voice_log" | grep -q warning; then
  echo "A line runs into the next one; move its cue in stage/script.json before rendering." >&2
  exit 1
fi
node lib/narration-md.mjs
node render.mjs --sfx
node audio/render-sfx.mjs
node audio/render-score.mjs --variant=$variant

if [[ -f narration/narration.wav ]]; then
  voice=(--narration=narration/narration.wav)
  soundtrack=audio/soundtrack-narrated.wav
else
  voice=(--narration=audio/vo.wav --raw)
  soundtrack=audio/soundtrack-guide.wav
fi
node audio/soundtrack.mjs --music=audio/music-$variant.wav --drop=0 --align=0 $voice --out=$soundtrack
node audio/soundtrack.mjs --music=audio/music-$variant.wav --drop=0 --align=0 --out=audio/soundtrack.wav > /dev/null

if $draft; then
  node render.mjs --audio=$soundtrack --out=renders/draft.mp4
  output=renders/draft.mp4
else
  node render.mjs --final --audio=$soundtrack --out=renders/knockout-demo-voiced.mp4
  # The recording booth plays renders/knockout-demo.mp4: the same picture with music and effects only.
  ffmpeg -y -v error -i renders/knockout-demo-voiced.mp4 -i audio/soundtrack.wav -map 0:v -map 1:a -c:v copy -c:a aac -b:a 256k -shortest renders/knockout-demo.mp4
  mkdir -p out
  cp renders/knockout-demo-voiced.mp4 out/knockout-demo.mp4
  node lib/srt.mjs
  cp exports/knockout-demo-captions.srt out/knockout-demo-captions.srt
  output=out/knockout-demo.mp4
fi

length=$(ffprobe -v error -show_entries format=duration -of csv=p=0 $output)
echo "$output: $length s"
[[ "$length" == 180.0* ]] || { echo "The video must be exactly 180.0 s (Devpost 2-3 min, Fetch.ai 3-5 min)." >&2; exit 1; }
