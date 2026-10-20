#!/usr/bin/env bash
# Resolve YouTube handles (@ABCNews) or channel URLs to the UC... channel IDs that the
# dashboard needs, and print a ready-to-paste NEWS_VIDEO_CHANNELS line.
#
# Why this exists: the video slide addresses a channel by its UC... ID, not its handle.
# Handles change and IDs are easy to mistype, and a wrong ID fails silently (the slide
# just skips). Run this on a machine with internet access and paste the output.
#
#   bash yt-channel-id.sh @ABCNews @NBCNews @CBSNews
#
set -uo pipefail
[ $# -gt 0 ] || { echo "usage: $0 @handle [@handle ...]"; exit 1; }
UA='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36'

line=""
fail=0
for h in "$@"; do
  case "$h" in
    http*) url="$h" ;;
    @*)    url="https://www.youtube.com/${h}" ;;
    *)     url="https://www.youtube.com/@${h}" ;;
  esac
  page=$(curl -sSL --compressed -m 25 -A "$UA" "$url" 2>/dev/null)
  id=$(printf '%s' "$page" | grep -oE '"(channelId|externalId)":"UC[A-Za-z0-9_-]{22}"' | head -1 | grep -oE 'UC[A-Za-z0-9_-]{22}')
  name=$(printf '%s' "$page" | grep -oE '<meta property="og:title" content="[^"]*"' | head -1 | sed 's/.*content="//; s/"$//')
  [ -z "$name" ] && name="${h#@}"
  if [ -n "$id" ]; then
    printf '  %-26s %s\n' "$name" "$id"
    line="${line}${name}|${id};"
  else
    printf '  %-26s COULD NOT RESOLVE (%s)\n' "${h}" "$url"
    fail=1
  fi
done

if [ -n "$line" ]; then
  echo
  echo "Paste into /etc/default/athan:"
  echo
  echo "NEWS_VIDEO_CHANNELS=\"${line%;}\""
  echo
  echo "Then: sudo /opt/athan/apply-config.sh"
fi
exit $fail
