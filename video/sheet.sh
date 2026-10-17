#!/bin/zsh
# Contact sheet for reviewing stills in one look: sheet.sh out.jpg a.jpg b.jpg c.jpg ...
# Two stills per row at half size, so type and alignment stay readable. PER_ROW=4 gives four per row at quarter size.
OUT=$1; shift
PER_ROW=${PER_ROW:-2}
WORK=$(mktemp -d)
ROWS=(); i=0
while (( $# > 0 )); do
  i=$((i+1)); ROW=()
  for k in {1..$PER_ROW}; do (( $# > 0 )) && { ROW+=("$1"); shift; }; done
  magick "${ROW[@]}" -resize $((1920 / PER_ROW))x$((1080 / PER_ROW)) +append $WORK/row-$i.jpg
  ROWS+=($WORK/row-$i.jpg)
done
magick "${ROWS[@]}" -background black -append "$OUT"
rm -rf $WORK
echo "$OUT"
