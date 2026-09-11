"""The benchmark that cannot be argued with: what did the ACTUAL STOCKS these
analysts cover do, over the exact window TipRanks scores (Jan 2009 on)?

Not a generic universe. Not the S&P. Their own coverage list, pulled from
their own pages, measured over 12-month windows the same way TipRanks does.
"""
from __future__ import annotations
import io, json, os, sys, warnings, glob
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd, yfinance as yf

snap_files = sorted(glob.glob("research/analysts/snapshots/*.json"))
snap = json.load(open(snap_files[-1], encoding="utf-8"))
print(f"snapshot {snap['date']}\n")

by_analyst = {}
for slug, d in snap["analysts"].items():
    syms = []
    for r in d["ratings"]:
        s = r["symbol"]
        if s.startswith("TSX:"):
            syms.append(s.replace("TSX:", "") + ".TO")
        elif s.isalpha() or "." in s:
            syms.append(s)
    by_analyst[slug] = {"sector": d["meta"]["sector"],
                        "succ": d["meta"]["success"],
                        "avgret": d["meta"]["avg_return"],
                        "syms": sorted(set(syms))}

allsyms = sorted({s for v in by_analyst.values() for s in v["syms"]})
print(f"{len(allsyms)} distinct tickers across 7 analysts' current coverage")
px = yf.download(allsyms, start="2008-06-01", end="2026-09-05",
                 auto_adjust=True, progress=False, threads=True)["Close"]
px = px[px.index >= "2009-01-01"]
H = 252


def stats(syms):
    pos, rets = [], []
    for s in syms:
        if s not in px:
            continue
        c = px[s].dropna()
        if len(c) < H + 60:
            continue
        cv = c.values
        f = cv[H:] / cv[:-H] - 1
        # monthly sampling to reduce overlap
        f = f[::21]
        pos.extend(f > 0)
        rets.extend(f)
    if len(pos) < 50:
        return None
    return (float(np.mean(pos)), float(np.mean(rets)),
            float(np.median(rets)), len(pos))


print(f"\n{'analyst':<22}{'sector':<12}{'their':>8}{'COVERAGE':>10}{'gap':>7}"
      f"{'avgret':>9}{'cov mean':>10}{'gap':>8}")
print("-" * 88)
for slug, v in by_analyst.items():
    st = stats(v["syms"])
    if not st:
        print(f"{slug[:21]:<22}{v['sector'][:11]:<12}  (too few price series)")
        continue
    base, mean, med, n = st
    succ = float(v["succ"].replace("%", ""))
    ar = float(v["avgret"].replace("%", ""))
    print(f"{slug[:21]:<22}{v['sector'][:11]:<12}{succ:>7.1f}%{base*100:>9.1f}%"
          f"{succ-base*100:>+7.1f}{ar:>8.1f}%{mean*100:>9.1f}%{ar-mean*100:>+8.1f}")

st = stats(allsyms)
print("-" * 88)
if st:
    base, mean, med, n = st
    print(f"ALL COVERED NAMES POOLED  ({n:,} stock-month observations, 2009-2026)")
    print(f"  share of 12-month windows POSITIVE : {base*100:.1f}%")
    print(f"  mean 12-month return               : {mean*100:+.1f}%")
    print(f"  median 12-month return             : {med*100:+.1f}%")
    print(f"\n  => an analyst covering these names scores {base*100:.1f}% by")
    print(f"     holding every one of them and doing nothing.")
