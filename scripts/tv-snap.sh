#!/usr/bin/env bash
# Screenshots the REAL TV screen every INTERVAL seconds for MINUTES minutes and joins them
# into one contact sheet (~/tv-snaps/sheet.jpg) so you can see the actual slide rotation.
# Run over SSH as the kiosk user:   bash ~/athan-tv/scripts/tv-snap.sh
set -eu
INTERVAL=${INTERVAL:-20}
MINUTES=${MINUTES:-6}
OUT=${OUT:-$HOME/tv-snaps}
export DISPLAY=${DISPLAY:-:0}
export XAUTHORITY=${XAUTHORITY:-$HOME/.Xauthority}

if ! command -v import >/dev/null || ! command -v montage >/dev/null; then
  echo "Installing imagemagick (one time)…"; sudo apt-get install -y -qq imagemagick >/dev/null
fi
rm -rf "$OUT"; mkdir -p "$OUT"
n=$(( MINUTES * 60 / INTERVAL ))
echo "Taking $n screenshots, one every ${INTERVAL}s (about $MINUTES min). Leave the TV alone…"
for i in $(seq -w 1 "$n"); do
  t=$(date +%H:%M:%S)
  if import -window root -resize 640x360 "$OUT/$i.png" 2>/dev/null; then
    echo "  $i  $t  ok"; printf '%s' "$t" > "$OUT/$i.txt"
  else
    echo "  $i  $t  FAILED (is the kiosk running on $DISPLAY?)"
  fi
  [ "$i" -lt "$n" ] && sleep "$INTERVAL"
done
args=()
for f in "$OUT"/*.png; do args+=(-label "$(cat "${f%.png}.txt")" "$f"); done
montage "${args[@]}" -tile 4x -geometry +4+4 -pointsize 14 "$OUT/sheet.jpg"
echo "Done: $OUT/sheet.jpg"
