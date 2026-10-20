#!/usr/bin/env python3
"""Check news feeds before putting them in /etc/default/athan.

A feed that 403s, has moved, or has gone stale makes the ticker quietly go empty --
fetch-news.py drops anything older than 48 hours. This reports, per feed, whether it
parses, how many headlines it yields, and how fresh the newest one is, using exactly
the same parser the real fetcher uses so a pass here means a pass there.

  ./test-feeds.py                       # test both feed groups from /etc/default/athan
  ./test-feeds.py "Name|URL;Name|URL"   # test a spec you are about to paste
"""
import importlib.util
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("fetchnews", os.path.join(HERE, "fetch-news.py"))
fn = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fn)          # safe: fetch-news.py only runs main() under __main__


def check(label, feedspec):
    print(f"\n=== {label} ===")
    feeds = fn.parse_feeds(feedspec)
    if not feeds:
        print("  (no feeds configured)")
        return True
    cutoff = time.time() - fn.MAX_AGE_HOURS * 3600
    all_ok = True
    for name, url in feeds:
        try:
            items = fn.fetch_feed(name, url)
        except Exception as e:
            print(f"  FAIL  {name:22s} {type(e).__name__}: {str(e)[:60]}")
            print(f"        {url}")
            all_ok = False
            continue
        dated = [i["ts"] for i in items if i["ts"]]
        fresh = [t for t in dated if t >= cutoff]
        newest = max(dated) if dated else None
        age = f"{(time.time() - newest) / 3600:.1f}h old" if newest else "no dates (always kept)"
        kept = len(fresh) if dated else len(items)
        flag = "OK  " if kept else "EMPTY"
        if not kept:
            all_ok = False
        print(f"  {flag}  {name:22s} {len(items):2d} headlines, {kept:2d} within "
              f"{fn.MAX_AGE_HOURS}h, newest {age}")
        if items:
            print(f"        > {items[0]['title'][:78]}")
    return all_ok


def main():
    if len(sys.argv) > 1:
        return 0 if check("given spec", sys.argv[1]) else 1
    conf = fn.read_conf(fn.CONF)
    ok = True
    for group, key in fn.CONF_KEYS.items():
        ok &= check(f"{key} ({group})", conf.get(key, fn.DEFAULT_FEEDS[group]))
    print("\nAll feeds usable." if ok else "\nSome feeds failed or are stale -- see above.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
