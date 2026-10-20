#!/usr/bin/env bash
# Set keys in /etc/default/athan non-interactively.
#
#   sudo /opt/athan/set-conf.sh MARKETS='S&P 500|^GSPC;Gold|GC=F' AYAH_SECONDS=30
#
# Why not just edit the file: it is mode 600 (it holds the CalDAV password), and editing
# it in an editor inside a pasted command block is how stray shell lines end up inside the
# config -- where apply-config.sh would SOURCE them. This replaces a key in place if it
# exists and appends it if it does not, so no key is ever defined twice, takes a
# timestamped mode-600 backup, and prints key names only, never values.
set -euo pipefail
CONF=/etc/default/athan
[ -f "$CONF" ] || { echo "Missing $CONF"; exit 1; }
[ "$(id -u)" -eq 0 ] || { echo "Run with sudo: sudo $0 KEY=VALUE ..."; exit 1; }
[ $# -gt 0 ] || { echo "usage: sudo $0 KEY=VALUE [KEY=VALUE ...]"; exit 1; }

# Validate everything BEFORE touching the file, so a typo cannot leave it half-edited.
for arg in "$@"; do
  case "$arg" in
    [A-Z_]*=*) ;;
    *) echo "Not a KEY=VALUE argument: ${arg%%=*}"; exit 1 ;;
  esac
done

BACKUP="${CONF}.bak.$(date +%Y%m%d-%H%M%S)"
cp -a "$CONF" "$BACKUP"; chmod 600 "$BACKUP"
echo "Backup: $BACKUP"

for arg in "$@"; do
  key="${arg%%=*}"; val="${arg#*=}"
  # Quote the value unless it is a bare number or true/false, so symbols like ^ | & and
  # spaces survive being sourced by apply-config.sh.
  case "$val" in
    [0-9]*|true|false|'"'*) q="$val" ;;
    *) q="\"$val\"" ;;
  esac
  if grep -qE "^[[:space:]]*${key}=" "$CONF"; then
    NEWLINE="${key}=${q}" perl -pi -e 's/^\s*\Q'"${key}"'\E=.*$/$ENV{NEWLINE}/' "$CONF"
    echo "  set     ${key}"
  else
    printf '%s=%s\n' "$key" "$q" >> "$CONF"
    echo "  added   ${key}"
  fi
done
chmod 600 "$CONF"

# A bad value here breaks every script that sources the file, so fail loudly now.
if ! bash -n "$CONF" 2>/dev/null; then
  echo "WARNING: $CONF is no longer valid shell. Restore with:  sudo cp -a $BACKUP $CONF"
  exit 1
fi
echo
echo "Valid. Now:  sudo /opt/athan/apply-config.sh"
