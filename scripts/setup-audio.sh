#!/usr/bin/env bash
# Lets the adhan (mpg123, run as root) and the news video (Chromium, kiosk user) share
# the HDMI output. Without this, Chromium plays to ALSA's "default" device (often the
# silent analog jack), and whichever program opens HDMI first locks the other one out.
#
# Writes /etc/asound.conf with a "dmix" (software mixer) on the HDMI device named in
# ALSA_DEVICE, makes it the system default, and play-adhan.sh then plays through it too.
# Undo:  sudo rm /etc/asound.conf   (play-adhan.sh falls back to ALSA_DEVICE directly)
set -eu
CONF=/etc/default/athan
# shellcheck source=/dev/null
[ -f "$CONF" ] && . "$CONF"
DEV="${ALSA_DEVICE:-hdmi:CARD=HDMI,DEV=0}"
APLAY_L=${APLAY_L:-$(aplay -l 2>/dev/null || true)}
OUT=${ASOUND_OUT:-/etc/asound.conf}

if [ "${ALSA_SHARED:-yes}" = "no" ]; then
  echo "  ALSA_SHARED=no: leaving audio routing alone"; exit 0
fi
if [ -f "$OUT" ] && ! grep -q "athan-tv setup-audio" "$OUT"; then
  echo "  $OUT exists and was not written by athan-tv -- leaving it alone"; exit 0
fi

card=$(sed -nE 's/.*CARD=([^,]+).*/\1/p' <<<"$DEV")
case "$DEV" in
  hdmi:*)   # hdmi:CARD=X,DEV=n means the n-th HDMI output of card X
    n=$(sed -nE 's/.*DEV=([0-9]+).*/\1/p' <<<"$DEV"); n=${n:-0}
    dev=$(awk -v c="$card" '$1=="card" && $3==c && /device [0-9]+:/ {
            for (i=1;i<=NF;i++) if ($i=="device") { d=$(i+1); sub(":","",d); print d } }' <<<"$APLAY_L" \
          | sed -n "$((n + 1))p") ;;
  hw:*|plughw:*)
    if [ -n "$card" ]; then dev=$(sed -nE 's/.*DEV=([0-9]+).*/\1/p' <<<"$DEV")
    else card=$(sed -nE 's/^[a-z]+:([^,]+),.*/\1/p' <<<"$DEV"); dev=$(sed -nE 's/^[a-z]+:[^,]+,([0-9]+).*/\1/p' <<<"$DEV"); fi ;;
  *) echo "  ALSA_DEVICE=$DEV is not an hdmi:/hw: device -- leaving audio routing alone"; exit 0 ;;
esac
if [ -z "${card:-}" ] || [ -z "${dev:-}" ]; then
  echo "  Could not find the hardware behind ALSA_DEVICE=$DEV in 'aplay -l' -- audio routing unchanged"; exit 0
fi

cat > "$OUT" <<EOF
# Written by athan-tv setup-audio.sh -- edit ALSA_DEVICE in /etc/default/athan instead.
# A shared software mixer on HDMI ($DEV = hw:CARD=$card,DEV=$dev), so the adhan and the
# news video can both play. Remove this file to go back to direct output.
pcm.athanmix {
  type dmix
  ipc_key 5232
  ipc_key_add_uid false
  ipc_perm 0666
  slave { pcm "hw:CARD=$card,DEV=$dev"  format S16_LE  rate 48000  channels 2 }
}
pcm.athan { type plug  slave.pcm "athanmix" }
pcm.!default { type plug  slave.pcm "athanmix" }
ctl.!default { type hw  card "$card" }
EOF
echo "  Audio: HDMI hw:CARD=$card,DEV=$dev shared by adhan + Chromium ($OUT)"
if pgrep -x pipewire >/dev/null || pgrep -x pulseaudio >/dev/null; then
  echo "  Note: a sound server (PipeWire/PulseAudio) is running; Chromium may use it instead of ALSA."
fi
