#!/usr/bin/env bash
# Play the adhan. Usage: play-adhan.sh [Fajr|Dhuhr|Asr|Maghrib|Isha|test]
CONF=/etc/default/athan
# shellcheck source=/dev/null
[ -f "$CONF" ] && . "$CONF"
ALSA_DEVICE="${ALSA_DEVICE:-hdmi:CARD=HDMI,DEV=0}"
AUDIO="${AUDIO:-/opt/athan/adhan.mp3}"
SCALE="${SCALE:-}"
PRAYER="${1:-test}"

if [ "$PRAYER" = "Fajr" ]; then
  [ -n "${FAJR_AUDIO:-}" ] && [ -f "$FAJR_AUDIO" ] && AUDIO="$FAJR_AUDIO"
  [ -n "${FAJR_SCALE:-}" ] && SCALE="$FAJR_SCALE"
fi

ARGS=(-q -o alsa -a "$ALSA_DEVICE")
[ -n "$SCALE" ] && ARGS+=(-f "$SCALE")

echo "$(date '+%F %T') playing $PRAYER: $AUDIO on $ALSA_DEVICE${SCALE:+ (scale $SCALE)}" >> /var/log/athan-schedule.log
exec mpg123 "${ARGS[@]}" "$AUDIO"
