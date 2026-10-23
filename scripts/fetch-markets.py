#!/usr/bin/env python3
"""Fetch market prices into /opt/athan/web/markets.json (root cron, every 10 minutes).

Source: Yahoo Finance's public chart endpoint (no API key; delayed ~15 min for most
exchanges). It is unofficial, so every failure is handled: a symbol that fails keeps its
previous value, and if every symbol fails the previous markets.json is kept as is.

Symbols come from MARKETS in /etc/default/athan, formatted "Label|SYMBOL;Label|SYMBOL".
"""
import json
import os
import re
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

CONF = os.environ.get("ATHAN_CONF", "/etc/default/athan")
OUT = os.environ.get("MARKETS_OUT", "/opt/athan/web/markets.json")
STATE = os.environ.get("MARKETS_STATE", "/var/lib/athan/markets-state.json")
# Yahoo answers 429 to some browser user-agents (reported for Linux/macOS Chrome, Safari,
# Firefox) while plain "Mozilla/5.0" and Windows Chrome/Edge get 200. Since it is the UA
# being refused, not a real rate limit, we try each UA on both API hosts, keep whichever
# one works, and start with it next run.
HOSTS = ("query1.finance.yahoo.com", "query2.finance.yahoo.com")
UAS = (
    "Mozilla/5.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/145.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/145.0.0.0 Safari/537.36 Edg/145.0.0.0",
)
COOLDOWN = 30 * 60          # after a run where everything was refused, back off this long
DEFAULT = ("WTI Crude|CL=F;Brent Crude|BZ=F;S&P 500|^GSPC;Dow Jones|^DJI;Nasdaq|^IXIC;"
           "10-Yr Treasury|^TNX;Gold|GC=F")
SPARK_POINTS = 60


def read_conf(path):
    conf = {}
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                m = re.match(r'^\s*([A-Z_]+)=(.*)$', line)
                if m:
                    val = m.group(2).strip()
                    q = re.match(r'^(["\'])(.*?)\1', val)
                    conf[m.group(1)] = q.group(2) if q else val.split(" #", 1)[0].strip()
    except (FileNotFoundError, PermissionError):
        pass
    return conf


def load_state():
    try:
        with open(STATE, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return {}


def save_state(state):
    try:
        os.makedirs(os.path.dirname(STATE), exist_ok=True)
        with open(STATE, "w", encoding="utf-8") as f:
            json.dump(state, f)
    except OSError:
        pass


class Blocked(Exception):
    """Every UA/host combination was refused -- no point trying more symbols this run."""


class Client:
    """Plain anonymous requests (no cookie/crumb: the chart endpoint doesn't need them,
    and authenticated chart calls are throttled harder). Rotates UA/host on 429/403."""

    def __init__(self, start=0):
        self.combos = [(h, u) for u in UAS for h in HOSTS]
        self.i = start % len(self.combos)

    def get_json(self, path):
        last = None
        for _ in range(len(self.combos)):
            host, ua = self.combos[self.i]
            req = urllib.request.Request("https://" + host + path, headers={
                "User-Agent": ua, "Accept": "application/json,text/plain,*/*",
                "Accept-Language": "en-US,en;q=0.9"})
            try:
                with urllib.request.urlopen(req, timeout=20) as r:
                    return json.load(r)
            except urllib.error.HTTPError as e:
                last = e
                if e.code not in (429, 403, 401):
                    raise                    # 404 etc: a real per-symbol problem
                self.i = (self.i + 1) % len(self.combos)
                time.sleep(1)
        raise Blocked(f"HTTP {last.code} on every user-agent/host")


def downsample(vals, n):
    if len(vals) <= n:
        return vals
    step = (len(vals) - 1) / (n - 1)
    return [vals[round(i * step)] for i in range(n)]


def fetch(client, label, symbol):
    path = ("/v8/finance/chart/" + urllib.parse.quote(symbol, safe="")
            + "?range=1d&interval=5m&includePrePost=false")
    res = client.get_json(path)["chart"]["result"][0]
    meta = res["meta"]
    price = meta.get("regularMarketPrice")
    prev = meta.get("chartPreviousClose") or meta.get("previousClose")
    if price is None or not prev:
        raise ValueError("no price in response")
    closes = []
    try:
        closes = [round(c, 4) for c in res["indicators"]["quote"][0]["close"] if c is not None]
    except (KeyError, IndexError, TypeError):
        pass
    reg = (meta.get("currentTradingPeriod") or {}).get("regular") or {}
    now = time.time()
    is_open = bool(reg) and reg.get("start", 0) <= now < reg.get("end", 0)
    if symbol.endswith("-USD"):                        # crypto trades 24/7
        is_open = True
    return {
        "label": label, "symbol": symbol,
        "price": price, "prev": prev,
        "change": price - prev, "pct": (price - prev) / prev * 100,
        "currency": meta.get("currency") or "",
        "time": meta.get("regularMarketTime"),
        "open": is_open,
        "spark": downsample(closes, SPARK_POINTS),
    }


def main():
    force = "--force" in sys.argv
    state = load_state()
    wait = state.get("blocked_until", 0) - time.time()
    if wait > 0 and not force:
        print(f"Backing off after HTTP 429; next try in {int(wait // 60) + 1} min (use --force to try now)")
        return 0
    client = Client(state.get("combo", 0))
    conf = read_conf(CONF)
    spec = conf.get("MARKETS") or DEFAULT
    pairs = [p.split("|", 1) for p in spec.split(";") if "|" in p]
    try:
        with open(OUT, encoding="utf-8") as f:
            previous = {q["symbol"]: q for q in json.load(f).get("quotes", [])}
    except (FileNotFoundError, ValueError, KeyError):
        previous = {}

    quotes, ok, blocked = [], 0, False
    for label, symbol in pairs:
        label, symbol = label.strip(), symbol.strip()
        q = None
        if not blocked:
            try:
                q = fetch(client, label, symbol)
                ok += 1
                print(f"{label:<16} {q['price']:>12,.2f}  {q['pct']:+6.2f}%  {'open' if q['open'] else 'closed'}")
            except Blocked as e:                     # Yahoo refuses us outright: stop asking
                print(f"{label}: FAILED ({e}); skipping the rest this run", file=sys.stderr)
                blocked = True
            except Exception as e:                   # one bad symbol must not stop the others
                print(f"{label}: FAILED ({e})", file=sys.stderr)
            time.sleep(0.3)                          # be gentle with the endpoint
        if q is None:                                # keep the last good value, marked stale
            if symbol not in previous:
                continue
            q = dict(previous[symbol], stale=True)
        quotes.append(q)

    if ok == 0:
        state["blocked_until"] = int(time.time()) + COOLDOWN
        save_state(state)
        print("All symbols failed; keeping previous markets.json and backing off 30 min", file=sys.stderr)
        return 1
    host, ua = client.combos[client.i]
    save_state({"combo": client.i})
    print(f"(via {host}, UA \"{ua[:40]}\")")
    us = next((q for q in quotes if q["symbol"] in ("^GSPC", "^DJI", "^IXIC")), None)
    data = {"updated": int(time.time()), "us_open": bool(us and us["open"]), "quotes": quotes}
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(OUT), prefix=".markets-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.chmod(tmp, 0o644)
    os.replace(tmp, OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
