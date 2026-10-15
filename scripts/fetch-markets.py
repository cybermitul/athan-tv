#!/usr/bin/env python3
"""Fetch market prices into /opt/athan/web/markets.json (root cron, every 5 minutes).

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
import urllib.parse
import urllib.request

CONF = os.environ.get("ATHAN_CONF", "/etc/default/athan")
OUT = os.environ.get("MARKETS_OUT", "/opt/athan/web/markets.json")
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
DEFAULT = ("S&P 500|^GSPC;Dow Jones|^DJI;Nasdaq|^IXIC;Russell 2000|^RUT;"
           "10-Yr Treasury|^TNX;Crude Oil|CL=F;Gold|GC=F;Bitcoin|BTC-USD")
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


def get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def downsample(vals, n):
    if len(vals) <= n:
        return vals
    step = (len(vals) - 1) / (n - 1)
    return [vals[round(i * step)] for i in range(n)]


def fetch(label, symbol):
    url = ("https://query1.finance.yahoo.com/v8/finance/chart/" + urllib.parse.quote(symbol, safe="")
           + "?range=1d&interval=5m&includePrePost=false")
    res = get_json(url)["chart"]["result"][0]
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
    conf = read_conf(CONF)
    spec = conf.get("MARKETS") or DEFAULT
    pairs = [p.split("|", 1) for p in spec.split(";") if "|" in p]
    try:
        with open(OUT, encoding="utf-8") as f:
            previous = {q["symbol"]: q for q in json.load(f).get("quotes", [])}
    except (FileNotFoundError, ValueError, KeyError):
        previous = {}

    quotes, ok = [], 0
    for label, symbol in pairs:
        label, symbol = label.strip(), symbol.strip()
        try:
            q = fetch(label, symbol)
            ok += 1
            print(f"{label:<16} {q['price']:>12,.2f}  {q['pct']:+6.2f}%  {'open' if q['open'] else 'closed'}")
        except Exception as e:                       # one bad symbol must not stop the others
            print(f"{label}: FAILED ({e})", file=sys.stderr)
            q = previous.get(symbol)
            if q is None:
                continue
            q = dict(q, stale=True)
        quotes.append(q)
        time.sleep(0.3)                              # be gentle with the endpoint

    if ok == 0:
        print("All symbols failed; keeping previous markets.json", file=sys.stderr)
        return 1
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
