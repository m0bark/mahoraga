"""THE test: is a top analyst's average return skill, or their sector?

TipRanks scores a rating as the stock's RAW 12-month price move, no
benchmark. So an analyst's "average return" is mostly a statement about
what their coverage universe did. Financials analysts and energy analysts
are not playing the same game.

TipRanks rankings incorporate ratings since Jan 2009, so that is the window.
"""
from __future__ import annotations
import io, sys, warnings
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd, yfinance as yf

SECTOR_ETF = {"Financials": "XLF", "Energy": "XLE", "Technology": "XLK",
              "Healthcare": "XLV", "Industrials": "XLI"}
ANALYSTS = [
    ("Phil Hardie",        "Financials", 77.2, 15.4,  920),
    ("Paul Newsome",       "Financials", 74.3, 14.9, 1156),
    ("Travis Wood",        "Energy",     73.3, 33.8,  345),
    ("Sanjay Sakhrani",    "Financials", 72.9, 16.4,  810),
    ("Manav Gupta",        "Energy",     72.5, 25.2,  602),
    ("Shrenik Kothari",    "Technology", 71.9, 25.4,  587),
    ("Bill Papanastasiou", "Technology", 71.9, 82.8,  119),
]

etfs = sorted(set(SECTOR_ETF[a[1]] for a in ANALYSTS))
px = yf.download(etfs + ["SPY"], start="2008-06-01", end="2026-09-05",
                 auto_adjust=True, progress=False, threads=True)["Close"]
px = px[px.index >= "2009-01-01"]
H = 252

stats = {}
for e in etfs + ["SPY"]:
    c = px[e].dropna()
    cv = c.values
    fwd = cv[H:] / cv[:-H] - 1
    stats[e] = {"pos": float((fwd > 0).mean()), "mean": float(fwd.mean()),
                "med": float(np.median(fwd))}

print("SECTOR ETF, rolling 12-month windows since Jan 2009 "
      "(the TipRanks ranking window)\n")
print(f"{'etf':<6}{'% of 12m windows positive':>28}{'mean 12m':>11}{'median':>9}")
for e in etfs + ["SPY"]:
    s = stats[e]
    print(f"{e:<6}{s['pos']*100:>27.1f}%{s['mean']*100:>10.1f}%{s['med']*100:>8.1f}%")

print("\n" + "=" * 92)
print("ANALYST vs THEIR OWN SECTOR — the only comparison that means anything")
print("=" * 92)
print(f"{'analyst':<20}{'sector':<12}{'succ%':>7}{'sector%':>9}{'edge':>7}"
      f"{'avgret%':>9}{'sector':>8}{'edge':>8}{'n':>6}")
print("-" * 92)
for name, sec, succ, avgret, n in ANALYSTS:
    e = SECTOR_ETF[sec]
    sp, sm = stats[e]["pos"] * 100, stats[e]["mean"] * 100
    se = np.sqrt((sp / 100) * (1 - sp / 100) / n) * 100
    z = (succ - sp) / se
    print(f"{name[:19]:<20}{sec[:11]:<12}{succ:>7.1f}{sp:>9.1f}{succ-sp:>+7.1f}"
          f"{avgret:>9.1f}{sm:>8.1f}{avgret-sm:>+8.1f}{n:>6}")
    print(f"{'':<20}{'':12}{'':7}{'':9}{f'({z:+.1f} SD)':>7}")

print("-" * 92)
print("succ%  = analyst hit rate | sector% = share of 12m windows the sector ETF rose")
print("avgret%= analyst average return | sector = sector ETF mean 12m return")
print("\nThe ETF is a FLOOR, not a fair benchmark: single stocks are more volatile")
print("than their sector ETF, so a stock-picker should beat the ETF's mean return")
print("on dispersion alone, without any skill.")
