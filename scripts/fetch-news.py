#!/usr/bin/env python3
"""Fetch news headlines (Bengali, US financial, breaking news) from RSS/RDF/Atom feeds into /opt/athan/web/news.json.

Runs from root's crontab every 15 minutes. The web page reads news.json from the
same origin, which avoids the browser's cross-origin (CORS) block on news sites.
Only headlines and source names are stored -- no article text.

Feeds come from /etc/default/athan, each formatted "Name|URL;Name|URL":
  NEWS_FEEDS     Bengali ticker
  US_NEWS_FEEDS  US financial ticker
  TOP_NEWS_FEEDS Breaking News slide (each headline keeps its timestamp, for "12 min ago")
If every feed in a group fails, that group's previous headlines are kept.
"""
import html
import json
import os
import re
import sys
import tempfile
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

CONF = "/etc/default/athan"
OUT = os.environ.get("NEWS_OUT", "/opt/athan/web/news.json")
DEFAULT_FEEDS = {
    "bn": "BBC বাংলা|https://feeds.bbci.co.uk/bengali/rss.xml;DW বাংলা|https://rss.dw.com/rdf/rss-ben-all",
    # Two feeds already reach MAX_TOTAL. Yahoo Finance is deliberately absent: its RSS
    # endpoint 404s for some hosts regardless of User-Agent.
    "us": "MarketWatch|https://feeds.content.dowjones.io/public/rss/mw_topstories"
          ";CNBC|https://www.cnbc.com/id/10000664/device/rss/rss.html",
    "top": "NBC News|https://feeds.nbcnews.com/nbcnews/public/news"
           ";CBS News|https://www.cbsnews.com/latest/rss/main"
           ";ABC News|https://abcnews.go.com/abcnews/topstories",
}
CONF_KEYS = {"bn": "NEWS_FEEDS", "us": "US_NEWS_FEEDS", "top": "TOP_NEWS_FEEDS"}
# Yahoo Finance (and some others) answer 404/403 to a non-browser User-Agent, exactly as
# Yahoo's quote API does in fetch-markets.py. Be honest first, then fall back to browser
# agents rather than losing the feed. The first agent that works for a feed is used.
UAS = (
    "athan-tv/1.0 (home prayer-times display)",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/145.0.0.0 Safari/537.36",
    "Mozilla/5.0",
)
ACCEPT = "application/rss+xml,application/atom+xml,application/xml;q=0.9,*/*;q=0.8"
MAX_PER_FEED = 10
MAX_TOTAL = 20
MAX_AGE_HOURS = 48
ATOM = "{http://www.w3.org/2005/Atom}"
RSS1 = "{http://purl.org/rss/1.0/}"            # RSS 1.0 / RDF (used by DW)
DC = "{http://purl.org/dc/elements/1.1/}"


def read_conf(path):
    """Minimal parser for the shell-style KEY=value file shared with the bash scripts."""
    conf = {}
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                m = re.match(r'^\s*([A-Z_]+)=(.*)$', line)
                if not m:
                    continue
                val = m.group(2).strip()
                q = re.match(r'^(["\'])(.*?)\1', val)          # quoted value: take what's inside the quotes
                conf[m.group(1)] = q.group(2) if q else val.split(" #", 1)[0].strip()
    except FileNotFoundError:
        pass
    return conf


def clean(text):
    text = html.unescape(text or "")
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def parse_date(s):
    if not s:
        return None
    s = s.strip()
    try:
        d = parsedate_to_datetime(s)
    except (TypeError, ValueError):
        try:
            d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.timestamp()


def fetch_feed(name, url):
    last = None
    for ua in UAS:
        req = urllib.request.Request(url, headers={"User-Agent": ua, "Accept": ACCEPT})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                raw = r.read()
            break
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (401, 403, 404, 406, 429):     # looks like agent filtering: try the next
                continue
            raise
        except Exception as e:                          # network-level failure: no point retrying agents
            raise
    else:
        raise last
    root = ET.fromstring(raw)
    items = []
    for it in root.iter("item"):                       # RSS 2.0
        items.append((it.findtext("title"), it.findtext("pubDate") or it.findtext(DC + "date")))
    for it in root.iter(RSS1 + "item"):                # RSS 1.0 / RDF
        items.append((it.findtext(RSS1 + "title"), it.findtext(DC + "date")))
    for it in root.iter(ATOM + "entry"):               # Atom
        items.append((it.findtext(ATOM + "title"), it.findtext(ATOM + "updated") or it.findtext(ATOM + "published")))
    out = []
    for title, date in items[:MAX_PER_FEED]:
        t = clean(title)
        if t:
            out.append({"title": t, "source": name, "ts": parse_date(date)})
    return out


def collect(feeds):
    items, ok = [], 0
    for name, url in feeds:
        try:
            got = fetch_feed(name, url)
            items += got
            ok += 1
            print(f"{name}: {len(got)} headlines")
        except Exception as e:                          # one bad feed must not stop the others
            print(f"{name}: FAILED ({e})", file=sys.stderr)
    if ok == 0:
        return None
    cutoff = time.time() - MAX_AGE_HOURS * 3600
    items = [i for i in items if i["ts"] is None or i["ts"] >= cutoff]
    items.sort(key=lambda i: i["ts"] or 0, reverse=True)
    seen, unique = set(), []
    for i in items:
        if i["title"] not in seen:
            seen.add(i["title"])
            unique.append(i)                            # ts is kept: the Breaking News slide shows each headline's age
    return unique[:MAX_TOTAL]


def parse_feeds(spec):
    feeds = []
    for part in spec.split(";"):
        if "|" in part:
            name, url = part.split("|", 1)
            feeds.append((name.strip(), url.strip()))
    return feeds


def main():
    conf = read_conf(CONF)
    try:
        with open(OUT, encoding="utf-8") as f:
            previous = json.load(f)
    except (FileNotFoundError, ValueError):
        previous = {}

    data, any_ok = {"updated": int(time.time())}, False
    for group, key in CONF_KEYS.items():
        spec = conf.get(key, DEFAULT_FEEDS[group])
        got = collect(parse_feeds(spec)) if spec else []
        if got is None:
            print(f"[{group}] all feeds failed; keeping previous headlines", file=sys.stderr)
            got = previous.get(group, previous.get("items", []) if group == "bn" else [])
        else:
            any_ok = True
        data[group] = got
    data["items"] = data["bn"]                          # backward compatibility with older pages

    if not any_ok:
        print("All feeds failed; keeping previous news.json", file=sys.stderr)
        return 1
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(OUT), prefix=".news-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.chmod(tmp, 0o644)
    os.replace(tmp, OUT)                                # atomic: the page never reads a half-written file
    return 0


if __name__ == "__main__":
    sys.exit(main())
