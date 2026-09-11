"""The base-rate check that decides whether 'surges come from dips' means
anything at all.

P(dip | surge) is what reverse-engineering gives you.
P(surge | dip) is what you would actually trade.
They are only related through P(dip) -- the fraction of ALL stock-days that
are in a drawdown. If stocks are usually in a drawdown, then surges coming
from drawdowns is exactly what chance predicts, and carries no information.
"""
import sys, io, warnings
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd, yfinance as yf

d = pd.read_csv("research/surges/surges.csv", parse_dates=["date"])
U = sorted(d.t.unique())
C = yf.download(U, start="2010-01-01", end="2026-08-28",
                auto_adjust=True, progress=False, threads=True)["Close"]

buckets = [(-9, -0.30, "deep dip (< -30%)"), (-0.30, -0.15, "-15..-30%"),
           (-0.15, -0.05, "-5..-15%"), (-0.05, 1, "near highs (> -5%)")]
alldd, surge_flag = [], []
for t in U:
    c = C[t].dropna()
    if len(c) < 800:
        continue
    dd = (c / c.rolling(252).max() - 1).iloc[260:]
    alldd.append(dd.values)
allv = np.concatenate(alldd)
allv = allv[~np.isnan(allv)]

print(f"base rate over {len(allv):,} stock-days, same universe & period\n")
print(f"{'drawdown state':<24}{'% of ALL days':>15}{'% of SURGES':>14}{'lift':>9}")
for lo, hi, lab in buckets:
    base = ((allv > lo) & (allv <= hi)).mean()
    surg = ((d.dd_at_start > lo) & (d.dd_at_start <= hi)).mean()
    print(f"{lab:<24}{base*100:14.1f}%{surg*100:13.1f}%{surg/base:8.2f}x")

# the forward-direction number, computed directly
print("\nforward direction -- P(surge in next 20d | state today):")
tot_days, tot_surge = {}, {}
for t in U:
    c = C[t].dropna()
    if len(c) < 800:
        continue
    cv = c.values
    dd = (c / c.rolling(252).max() - 1).values
    fwd = np.full(len(cv), np.nan); fwd[:-20] = cv[20:] / cv[:-20] - 1
    for lo, hi, lab in buckets:
        m = (dd > lo) & (dd <= hi) & ~np.isnan(fwd)
        tot_days[lab] = tot_days.get(lab, 0) + int(m.sum())
        tot_surge[lab] = tot_surge.get(lab, 0) + int((m & (fwd >= 0.25)).sum())
for _, _, lab in buckets:
    n, s = tot_days[lab], tot_surge[lab]
    print(f"  {lab:<24}{s/n*100:6.2f}%   ({s:,} of {n:,} days)")
