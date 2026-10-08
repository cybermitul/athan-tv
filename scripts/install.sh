#!/usr/bin/env bash
# athan-tv installer for a fresh Debian 13 (Trixie) minimal install. Idempotent: safe to re-run.
#
#   KIOSK_USER=mitul ./scripts/install.sh
#
# Optional environment variables:
#   KIOSK_USER      user that auto-logs in and runs the display (required unless run via sudo)
#   LATITUDE / LONGITUDE   written to /etc/default/athan on first install
#   DISABLE_IOMMU=yes      add intel_iommu=off to GRUB (fixes silent HDMI audio on some
#                          Haswell/4th-gen Intel boxes -- see docs/TROUBLESHOOTING.md)
set -euo pipefail
export PATH="/usr/local/sbin:/usr/sbin:/sbin:$PATH"   # works even after plain `su`

[ "$(id -u)" -eq 0 ] || { echo "Run as root (su -)"; exit 1; }
KIOSK_USER="${KIOSK_USER:-${SUDO_USER:-}}"
[ -n "$KIOSK_USER" ] || { echo "Set KIOSK_USER, e.g.  KIOSK_USER=mitul $0"; exit 1; }
id "$KIOSK_USER" >/dev/null 2>&1 || { echo "User $KIOSK_USER does not exist"; exit 1; }
KIOSK_HOME=$(getent passwd "$KIOSK_USER" | cut -d: -f6)

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ATHAN=/opt/athan
step(){ echo; echo "==> $*"; }

step "1/8 Installing packages"
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
  xserver-xorg openbox lightdm chromium unclutter \
  mpg123 ffmpeg alsa-utils \
  curl jq at cron file ca-certificates python3 python3-caldav \
  fonts-noto-core fonts-hosny-amiri fonts-noto-color-emoji >/dev/null

step "2/8 Installing Docker (if missing)"
if ! command -v docker >/dev/null; then
  curl -fsSL https://get.docker.com | sh
fi
systemctl enable --now docker >/dev/null

step "3/8 Copying files to $ATHAN"
install -d "$ATHAN/web/bg"
install -m 644 "$REPO/web/index.html" "$ATHAN/web/index.html"
install -m 644 "$REPO/docker-compose.yml" "$ATHAN/docker-compose.yml"
install -m 644 "$REPO/config/nginx-default.conf" "$ATHAN/nginx.conf"
for s in schedule-athan.sh play-adhan.sh apply-config.sh fetch-media.sh fetch-news.py fetch-weather.py fetch-family.py; do
  install -m 755 "$REPO/scripts/$s" "$ATHAN/$s"
done
install -m 644 "$REPO/config/logrotate-athan" /etc/logrotate.d/athan
if [ ! -f /etc/default/athan ]; then
  install -m 644 "$REPO/athan.conf.example" /etc/default/athan
  [ -n "${LATITUDE:-}" ]  && sed -i "s/^LATITUDE=.*/LATITUDE=${LATITUDE}/"   /etc/default/athan
  [ -n "${LONGITUDE:-}" ] && sed -i "s/^LONGITUDE=.*/LONGITUDE=${LONGITUDE}/" /etc/default/athan
  echo "  Created /etc/default/athan -- review your location settings there."
else
  echo "  Keeping existing /etc/default/athan"
fi
chmod 600 /etc/default/athan    # may hold the CalDAV password
"$ATHAN/apply-config.sh"

step "4/8 Downloading backgrounds and adhan"
"$ATHAN/fetch-media.sh"

step "5/8 Starting web container on :8080"
docker rm -f athan-display >/dev/null 2>&1 || true   # replaces a container created by an older manual `docker run`
docker compose -f "$ATHAN/docker-compose.yml" up -d

step "6/8 Configuring kiosk autologin for $KIOSK_USER"
install -d /etc/lightdm/lightdm.conf.d
sed "s/KIOSK_USER/$KIOSK_USER/" "$REPO/config/50-autologin.conf" > /etc/lightdm/lightdm.conf.d/50-autologin.conf
install -d -o "$KIOSK_USER" -g "$KIOSK_USER" "$KIOSK_HOME/.config" "$KIOSK_HOME/.config/openbox"
install -m 644 -o "$KIOSK_USER" -g "$KIOSK_USER" "$REPO/config/openbox-autostart" "$KIOSK_HOME/.config/openbox/autostart"
usermod -aG audio,video "$KIOSK_USER"

step "7/8 Scheduling adhan, news, weather and family data (root crontab)"
systemctl enable --now atd cron >/dev/null
( crontab -l 2>/dev/null | grep -vE 'schedule-athan.sh|fetch-news.py|fetch-weather.py|fetch-family.py' || true
  echo "5 0 * * * $ATHAN/schedule-athan.sh"
  echo "@reboot sleep 60 && $ATHAN/schedule-athan.sh"
  echo "*/15 * * * * $ATHAN/fetch-news.py >/dev/null 2>&1"
  echo "@reboot sleep 90 && $ATHAN/fetch-news.py >/dev/null 2>&1"
  echo "*/10 * * * * $ATHAN/fetch-weather.py >/dev/null 2>&1"
  echo "@reboot sleep 75 && $ATHAN/fetch-weather.py >/dev/null 2>&1"
  echo "*/5 * * * * $ATHAN/fetch-family.py >/dev/null 2>&1"
  echo "@reboot sleep 80 && $ATHAN/fetch-family.py >/dev/null 2>&1"
) | crontab -
"$ATHAN/fetch-news.py" || echo "  (news feeds unreachable right now -- cron retries every 15 min)"
"$ATHAN/fetch-weather.py" || echo "  (weather unreachable right now -- cron retries every 10 min)"
"$ATHAN/fetch-family.py" || echo "  (family calendar not reachable yet -- see docs/FAMILY.md)"
"$ATHAN/schedule-athan.sh" || echo "  (could not fetch times now -- cron will retry)"
atq || true

step "8/8 Boot options"
if [ "${DISABLE_IOMMU:-no}" = "yes" ]; then
  if ! grep -q 'intel_iommu=off' /etc/default/grub; then
    sed -i 's/^GRUB_CMDLINE_LINUX_DEFAULT="\(.*\)"/GRUB_CMDLINE_LINUX_DEFAULT="\1 intel_iommu=off"/' /etc/default/grub
    update-grub
    echo "  intel_iommu=off added -- takes effect after reboot"
  else
    echo "  intel_iommu=off already set"
  fi
else
  echo "  Skipped (set DISABLE_IOMMU=yes if HDMI audio fails with 'Input/output error')"
fi

cat <<MSG

Done. Next:
  1. Check /etc/default/athan (location, ALSA_DEVICE), then:  $ATHAN/apply-config.sh
  2. Test audio:   $ATHAN/play-adhan.sh test
  3. Reboot:       reboot
MSG
