#!/usr/bin/env bash
# One-time migration: switch /etc/default/athan to US news video + English-only scripture
# + US financial ticker. Idempotent -- safe to run twice.
#
# Each key is REPLACED in place if it already exists and APPENDED if it does not, so the
# file keeps its structure and no key ends up defined twice. A timestamped backup is taken
# first. This file is mode 600 because it holds the CalDAV password; the backup is too.
set -euo pipefail
CONF=/etc/default/athan
[ -f "$CONF" ] || { echo "Missing $CONF"; exit 1; }
[ "$(id -u)" -eq 0 ] || { echo "Run with sudo: sudo $0"; exit 1; }

BACKUP="${CONF}.bak.$(date +%Y%m%d-%H%M%S)"
cp -a "$CONF" "$BACKUP"
chmod 600 "$BACKUP"
echo "Backup: $BACKUP"

set_key(){
  local key="$1" val="$2"
  if grep -qE "^[[:space:]]*${key}=" "$CONF"; then
    # Replace the whole line. The value is written via an env var so that slashes,
    # ampersands and pipes in URLs cannot be mangled by sed's replacement parsing.
    NEWLINE="${key}=${val}" perl -pi -e 's/^\s*\Q'"${key}"'\E=.*$/$ENV{NEWLINE}/' "$CONF"
    echo "  set     ${key}"
  else
    printf '%s=%s\n' "$key" "$val" >> "$CONF"
    echo "  added   ${key}"
  fi
}

# ---- Ayah / Hadith: English only, larger text -------------------------------
set_key TRANSLATION_LANGS '"en"'
set_key TEXT_SCALE_MAX    '1.6'
set_key AYAH_SECONDS      '24'

# ---- News video: US channels, two minutes per pass ---------------------------
# Replace the IDs below with the output of yt-channel-id.sh before relying on them.
set_key NEWS_VIDEO            'true'
set_key NEWS_VIDEO_TITLE      '"US News Live"'
set_key NEWS_VIDEO_SECONDS    '120'
set_key NEWS_VIDEO_CHANNELS   '"NBC News NOW|UCeY0bbntWzzVIaj2z3QigXg;NBC News|UChDKyKQ59fYz3JO2fl0Z6sg;ABC News|UCBi2mrWuNuyYy4gbM6fU18Q;CBS News|UC-SJ6nODDmufqBzPBwCvYvQ"'

# ---- Market tiles: no crypto, no Russell 2000 -------------------------------
# Six tiles lay out as 3x2 with no empty cells. Check any symbol you add first with
# test-symbols.py -- a bad symbol is simply dropped from the slide without an error.
set_key MARKETS_SLIDE 'true'
set_key MARKETS       '"S&P 500|^GSPC;Dow Jones|^DJI;Nasdaq|^IXIC;10-Yr Treasury|^TNX;Crude Oil|CL=F;Gold|GC=F"'

# ---- Ticker: US financial instead of NYC local ------------------------------
set_key US_NEWS_TICKER 'true'
set_key US_NEWS_LABEL  '"US MARKETS"'
set_key US_NEWS_FEEDS  '"MarketWatch|https://feeds.content.dowjones.io/public/rss/mw_topstories;Yahoo Finance|https://finance.yahoo.com/news/rssindex;CNBC|https://www.cnbc.com/id/10000664/device/rss/rss.html"'

chmod 600 "$CONF"
echo
echo "Done. Now:"
echo "  /opt/athan/apply-config.sh        # render config.js"
echo "  /opt/athan/fetch-news.py          # pull the new feeds now instead of waiting 15 min"
echo "  /opt/athan/fetch-markets.py --force   # redraw the market tiles now"
echo "  grep -n 'US_NEWS_FEEDS\|TRANSLATION_LANGS\|NEWS_VIDEO_SECONDS' $CONF"
