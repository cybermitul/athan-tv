#!/usr/bin/env bash
# Download freely licensed background photos and the adhan from Wikimedia Commons.
# Existing files are left alone, so your own photos/recordings are never overwritten.
# Credits and licenses: docs/CREDITS.md
set -euo pipefail
DEST=/opt/athan
UA="athan-tv/1.0 (home prayer-times display)"
BASE="https://commons.wikimedia.org/wiki/Special:FilePath"

BACKGROUNDS=(
  "Sultan_Omar_Ali_Saifuddin_Mosque_02.jpg"
  "Blue_Mosque_Courtyard_Dusk_Wikimedia_Commons.jpg"
  "Kherua_Mosque.jpg"
  "Sunsets_of_Umm_al-Fahm6.JPG"
  "Sri_Lanka_Colombo_Grand_Mosque_Landscape.jpg"
)

mkdir -p "$DEST/web/bg"
n=1
for f in "${BACKGROUNDS[@]}"; do
  out="$DEST/web/bg/$n.jpg"
  if [ -s "$out" ]; then
    echo "  bg/$n.jpg exists, skipping"
  elif curl -fsSL -A "$UA" -o "$out" "$BASE/$f?width=1920" && file -b --mime-type "$out" | grep -q '^image/'; then
    echo "  bg/$n.jpg <- $f"
  else
    echo "  WARN: could not download $f"; rm -f "$out"
  fi
  n=$((n+1))
done
chmod 644 "$DEST"/web/bg/*.jpg 2>/dev/null || true

if [ -s "$DEST/adhan.mp3" ]; then
  echo "  adhan.mp3 exists, skipping"
else
  tmp=$(mktemp --suffix=.ogg)
  curl -fsSL -A "$UA" -o "$tmp" "$BASE/Beautiful_adhan.ogg"
  # 48 kHz stereo matches HDMI's native rate
  ffmpeg -loglevel error -y -i "$tmp" -ar 48000 -ac 2 -b:a 192k "$DEST/adhan.mp3"
  rm -f "$tmp"
  echo "  adhan.mp3 <- Beautiful_adhan.ogg"
fi
