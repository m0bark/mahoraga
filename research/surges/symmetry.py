"""Deep dips surge 7x more often. Do they also CRASH more often?

If the up-tail and the down-tail both scale together, 'more surges' is just
volatility -- more lottery tickets, not better odds -- and the mean return
is what decides whether you get paid. That reconciles the surge study with
the sealed QC verdict (-5.19%/yr).
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

agg = {lab: {"n": 0, "up": 0, "dn": 0, "sum": 0.0, "sq": 0.0} for _, _, lab in buckets}
for t in U:
    c = C[t].dropna()
    if len(c) < 800:
        continue
    cv = c.values
    dd = (c / c.rolling(252).max() - 1).values
    fwd = np.full(len(cv), np.nan); fwd[:-20] = cv[20:] / cv[:-20] - 1
    for lo, hi, lab in buckets:
        m = (dd > lo) & (dd <= hi) & ~np.isnan(fwd)
        f = fwd[m]
        a = agg[lab]
        a["n"] += len(f); a["up"] += int((f >= 0.25).sum())
        a["dn"] += int((f <= -0.25).sum())
        a["sum"] += float(f.sum()); a["sq"] += float((f ** 2).sum())

print(f"{'state':<24}{'P(+25%)':>9}{'P(-25%)':>9}{'up/dn':>8}"
      f"{'mean 20d':>10}{'stdev':>8}")
for _, _, lab in buckets:
    a = agg[lab]
    n = a["n"]; mu = a["sum"] / n
    sd = np.sqrt(a["sq"] / n - mu ** 2)
    up, dn = a["up"] / n, a["dn"] / n
    print(f"{lab:<24}{up*100:8.2f}%{dn*100:8.2f}%{up/max(dn,1e-9):7.2f}x"
          f"{mu*100:9.2f}%{sd*100:7.1f}%")
print("\n(mean 20d = simple average forward 20-day return from that state)")
