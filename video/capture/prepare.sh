#!/bin/zsh
# Derives what the stage plays from the raw captures: the search row of each typing frame, so the stage
# can lay one keystroke at a time over the home page without decoding a dozen full screenshots.
# capture/prepare.sh   (run after capture/capture.mjs; stage/footage/ is derived and not committed)
set -e
cd "$(dirname "$0")/.."
mkdir -p stage/footage/typing
find stage/footage/typing -name "*.jpg" -delete
# The search row in CSS pixels is x 150-830, y 630-720 at a 1440 px viewport; the captures are at 2x.
for frame in capture/raw/home-[0-9][0-9].jpg; do
  magick "$frame" -crop 1360x180+300+1260 +repage -quality 92 "stage/footage/typing/$(basename "$frame")"
done
echo "stage/footage/typing: $(ls stage/footage/typing | wc -l | tr -d ' ') frames"

# Screen recordings for the ASI:One and Creao beats, once they exist, as 30 fps frames.
# "asiOneIn" and "creaoIn" in stage/status.json set the second of the recording to start from.
for name in asi-one creao-run; do
  source=$(ls capture/raw/$name.mp4 capture/raw/$name.mov 2>/dev/null | head -1)
  [[ -n "$source" ]] || continue
  key=$([[ $name == asi-one ]] && echo asiOneIn || echo creaoIn)
  start=$(node -e "console.log(require('./stage/status.json')['$key'] ?? 0)")
  mkdir -p stage/footage/$name
  find stage/footage/$name -name "*.jpg" -delete
  ffmpeg -v error -ss $start -i $source -t 40 -vf "fps=30,scale=1500:-2" -q:v 3 stage/footage/$name/%05d.jpg
  echo "stage/footage/$name: $(ls stage/footage/$name | wc -l | tr -d ' ') frames from $source at ${start} s"
done
