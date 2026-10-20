#!/usr/bin/env python3
"""Check Yahoo Finance symbols before putting them in MARKETS in /etc/default/athan.

fetch-markets.py drops a symbol it cannot fetch and carries on, so a typo or a delisted
index never raises an error -- the tile just silently disappears. This resolves each
symbol through the same client the real fetcher uses (same host rotation and user-agent
rotation), so a pass here means a pass there.

  ./test-symbols.py                       # check the MARKETS line already in the conf
  ./test-symbols.py "S&P 500|^GSPC;Gold|GC=F"
"""
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("fetchmkt", os.path.join(HERE, "fetch-markets.py"))
fm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fm)          # safe: fetch-markets.py only runs main() under __main__


def parse(spec_str):
    out = []
    for part in spec_str.split(";"):
        if "|" in part:
            label, sym = part.split("|", 1)
            out.append((label.strip(), sym.strip()))
    return out


def main():
    if len(sys.argv) > 1:
        pairs = parse(sys.argv[1])
    else:
        conf = fm.read_conf(fm.CONF)
        pairs = parse(conf.get("MARKETS", ""))
    if not pairs:
        print("No symbols to check.")
        return 1

    client = fm.Client(fm.load_state().get("combo", 0))
    ok = bad = 0
    for label, sym in pairs:
        try:
            q = fm.fetch(client, label, sym)
            if not q:
                raise ValueError("no data returned")
            print(f"  OK    {label:20s} {sym:10s} {q['price']:>14,.2f}")
            ok += 1
        except Exception as e:
            print(f"  FAIL  {label:20s} {sym:10s} {type(e).__name__}: {str(e)[:50]}")
            bad += 1

    n = ok
    cols = max(1, n) if n <= 4 else -(-n // 2)
    print(f"\n{ok} usable, {bad} unusable.")
    if bad:
        print("Unusable symbols are dropped silently by fetch-markets.py -- remove them "
              "from MARKETS so the tile count is what you expect.")
    if ok:
        print(f"{ok} tiles will lay out as {cols} column(s) x {-(-ok // cols)} row(s)"
              + ("" if ok % cols == 0 else f"  (note: {cols - ok % cols} empty cell(s) in the last row)"))
    if ok > 8:
        print("Only the first 8 are shown on the slide.")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
