"""Test the direction BEFORE building anything: near the 52-week high, or
deep in a drawdown?

THE BIAS ARGUMENT THAT MAKES THIS LOCAL TEST USABLE:
this universe is today's survivors, so failed deep-dip names are missing
while near-high names rarely delist. The bias therefore FAVOURS the dip
side -- and we can prove it: the same data says dip beats no-dip, while the
PIT QC run says the opposite.

So if near-high wins HERE, it wins against a bias pointing the other way.
A result that survives a headwind is credible; one that rides a tailwind
(the +10%-off-the-low rule, t=3.45) is not.

Ranks names monthly by nearness = price / 252-day high, forms quintiles.
"""
from __future__ import annotations
import sys, io, warnings
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd, yfinance as yf

U = ("AAPL MSFT GOOGL AMZN META NVDA AMD AVGO TSM MU INTC QCOM TXN ADI MRVL LRCX AMAT KLAC "
     "NXPI ON MCHP SWKS QRVO TER ENTG MPWR ANET COHR LITE ONTO ACLS AMKR AEIS ADBE CRM NOW "
     "ORCL PANW ZS NET DDOG TEAM WDAY HUBS INTU ADSK SNPS CDNS FTNT OKTA TWLO TTD SHOP FSLR "
     "ENPH SEDG RUN CSIQ JKS PLUG NEE BE TSLA GM F LI XPEV APTV ALB MP VRT ETN PWR NVT MOD "
     "CEG VST ISRG DXCM JNJ XOM JPM PG KO PEP WMT CVX MRK PFE T VZ CSCO IBM MCD NKE HD LOW "
     "CAT DE MMM GE BA HON UPS UNH ABT LLY BMY AMGN GILD COST TGT SBUX DIS CMCSA DAL LUV GS "
     "MS BAC C WFC AXP USB PNC SCHW").split()
HZ = (63, 126, 252)

px = yf.download(U + ["SPY"], start="2010-01-01", end="2026-08-28",
                 auto_adjust=True, progress=False, threads=True)["Close"]
spy = px["SPY"].dropna()
cols = [t for t in U if t in px]
P = px[cols]
NEAR = P / P.rolling(252).max()          # 1.00 = at the 52w high
month_ends = P.resample("ME").last().index

rows = []
rng = np.random.default_rng(3)
for dt in month_ends:
    if dt not in P.index:
        loc = P.index.searchsorted(dt)
        if loc >= len(P.index):
            continue
        dt = P.index[loc]
    i = P.index.get_loc(dt)
    if i < 260 or i + max(HZ) >= len(P.index):
        continue
    n = NEAR.iloc[i].dropna()
    if len(n) < 40:
        continue
    try:
        q = pd.qcut(n.rank(method="first"), 5,
                    labels=["Q5 deepest dip", "Q4", "Q3", "Q2", "Q1 nearest high"])
    except ValueError:
        continue
    for t, lab in q.items():
        r = {"date": dt, "t": t, "bucket": str(lab), "near": n[t]}
        ok = True
        for h in HZ:
            p0, p1 = P[t].iloc[i], P[t].iloc[i + h]
            if not np.isfinite(p0) or not np.isfinite(p1) or p0 <= 0:
                ok = False; break
            s0, s1 = spy.asof(P.index[i]), spy.asof(P.index[i + h])
            r[f"x{h}"] = (p1 / p0 - 1) - (s1 / s0 - 1)
        if ok:
            rows.append(r)

d = pd.DataFrame(rows)
print(f"{len(d):,} name-months, {d.date.min().date()}..{d.date.max().date()}\n")

print("STEP 1 -- can this dataset be trusted on this question?")
dip = d[d.bucket == "Q5 deepest dip"].x252.mean()
hi = d[d.bucket == "Q1 nearest high"].x252.mean()
print(f"  local says: deepest-dip 12m excess {dip*100:+.2f}%  vs nearest-high {hi*100:+.2f}%")
print("  known PIT answer (QC): dip 6.90%/yr LOSES to no-dip 12.09%/yr")
print(f"  => local bias direction favours {'DIPS' if dip > hi else 'NEAR-HIGH'}\n")

print("STEP 2 -- the ranking")
print(f"{'bucket':<18}{'n':>8}{'3m':>9}{'6m':>9}{'12m':>9}{'win 12m':>10}")
order = ["Q1 nearest high", "Q2", "Q3", "Q4", "Q5 deepest dip"]
for b in order:
    s = d[d.bucket == b]
    print(f"{b:<18}{len(s):8d}{s.x63.mean()*100:8.2f}%{s.x126.mean()*100:8.2f}%"
          f"{s.x252.mean()*100:8.2f}%{(s.x252>0).mean()*100:9.0f}%")

A, B = d[d.bucket == "Q1 nearest high"], d[d.bucket == "Q5 deepest dip"]
for h in HZ:
    diff = A[f"x{h}"].mean() - B[f"x{h}"].mean()
    se = np.sqrt(A[f"x{h}"].var()/len(A) + B[f"x{h}"].var()/len(B))
    print(f"\n  nearest-high - deepest-dip @{h//21}m: {diff*100:+6.2f}%  "
          f"SE {se*100:4.2f}%  t={diff/se:+5.2f}")
