#!/usr/bin/env bash
# Fetch today's prayer times and queue one `at` job per prayer that plays the adhan.
# Run by root's crontab at 00:05 daily and at boot. Safe to re-run: it replaces
# any adhan jobs it queued earlier instead of doubling them up.
set -uo pipefail

CONF=/etc/default/athan
# shellcheck source=/dev/null
[ -f "$CONF" ] && . "$CONF"
LATITUDE="${LATITUDE:-40.7128}"
LONGITUDE="${LONGITUDE:--74.0060}"
METHOD="${METHOD:-2}"
SCHOOL="${SCHOOL:-0}"
TUNE="${TUNE:-}"

PLAYER=/opt/athan/play-adhan.sh
LOG=/var/log/athan-schedule.log
log(){ echo "$(date '+%F %T') $*" >> "$LOG"; }

DATE=$(date +%d-%m-%Y)
URL="https://api.aladhan.com/v1/timings/${DATE}?latitude=${LATITUDE}&longitude=${LONGITUDE}&method=${METHOD}&school=${SCHOOL}"
[ -n "$TUNE" ] && URL="${URL}&tune=${TUNE}"

# Retry for up to ~10 minutes -- at boot or after an outage the network may not be up yet
JSON=""
for attempt in $(seq 1 10); do
  if JSON=$(curl -fsS --max-time 20 "$URL") && echo "$JSON" | jq -e '.code == 200' >/dev/null 2>&1; then
    break
  fi
  JSON=""
  log "fetch attempt $attempt failed, retrying in 60s"
  sleep 60
done
if [ -z "$JSON" ]; then
  log "ERROR: could not fetch prayer times for $DATE -- no adhan queued today"
  exit 1
fi

# Remove adhan jobs from an earlier run (this version's player, or older versions that
# called mpg123 on adhan.mp3 directly) so re-runs never double up
for j in $(atq | awk '{print $1}'); do
  if at -c "$j" 2>/dev/null | grep -qE "$PLAYER|/opt/athan/adhan\.mp3"; then atrm "$j"; fi
done

log "scheduling for $DATE"
NOW=$(date +%H:%M)
for PRAYER in Fajr Dhuhr Asr Maghrib Isha; do
  TIME=$(echo "$JSON" | jq -r ".data.timings.${PRAYER}" | cut -c1-5)   # "05:32 (EDT)" -> "05:32"
  if [[ ! "$TIME" > "$NOW" ]]; then
    log "  $PRAYER ($TIME) already passed, skipping"
    continue
  fi
  if echo "$PLAYER $PRAYER" | at "$TIME" today >/dev/null 2>&1; then
    log "  queued $PRAYER at $TIME"
  else
    log "  ERROR: could not queue $PRAYER at $TIME"
  fi
done
