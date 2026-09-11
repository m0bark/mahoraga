"""Does waiting for a POSITIVE REACTION on the dip beat buying the dip cold?

Arms, all inside a >=15% drawdown state:
  A raw_dip      buy the moment the name enters the dip state
  B react_sma    buy the first close back above the 20d SMA after >=10d below
  C react_low    buy the first close >=10% above the trailing 20d low
  D no_dip       buy quality names NOT in a dip  (the QC winner, 12.09%/yr)
  R random       random days, same universe -- the survivorship control

If confirmation works, B and C beat A by enough to matter, and at least one
beats D. Otherwise the reaction is just a later, higher entry.
"""
from __future__ import annotations
import sys, io, warnings
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd, yfinance as yf

U = ("AAPL MSFT GOOGL AMZN META NVDA AMD AVGO TSM MU INTC QCOM TXN ADI MRVL LRCX AMAT KLAC "
     "NXPI ON MCHP SWKS QRVO TER ENTG MPWR ANET COHR LITE ONTO ACLS AMKR AEIS ADBE CRM NOW "
     "ORCL PANW ZS NET DDOG TEAM WDAY HUBS INTU ADSK SNPS CDNS FTNT OKTA TWLO TTD SHOP FSLR "
     "ENPH SEDG RUN CSIQ JKS PLUG NEE BE TSLA GM F LI XPEV APTV ALB MP VRT ETN PWR NVT MOD "
     "CEG VST ISRG DXCM JNJ XOM JPM PG KO PEP WMT CVX MRK PFE T VZ CSCO IBM MCD NKE HD LOW "
     "CAT DE MMM GE BA HON UPS UNH ABT LLY BMY AMGN GILD COST TGT SBUX DIS CMCSA DAL LUV GS "
     "MS BAC C WFC AXP USB PNC SCHW").split()
DIP, HZ = -0.15, (60, 120, 250)

px = yf.download(U + ["SPY"], start="2010-01-01", end="2026-08-28",
                 auto_adjust=True, progress=False, threads=True)["Close"]
spy = px["SPY"].dropna()
rows = []
rng = np.random.default_rng(11)

def add(arm, t, i, cv, dates):
    r = {"arm": arm, "t": t, "date": dates[i]}
    for h in HZ:
        if i + h >= len(cv):
            return None
        s0 = spy.asof(dates[i]); s1 = spy.asof(dates[i + h])
        r[f"x{h}"] = (cv[i + h] / cv[i] - 1) - (s1 / s0 - 1)
    return r

for t in U:
    if t not in px:
        continue
    c = px[t].dropna()
    if len(c) < 800:
        continue
    cv, dates = c.values, c.index
    dd = (c / c.rolling(252).max() - 1).values
    sma20 = c.rolling(20).mean().values
    low20 = c.rolling(20).min().values
    in_dip = dd <= DIP
    below = c.values < sma20
    below_run = pd.Series(below).rolling(10).min().values      # 10 straight days below
    last = {k: -999 for k in "ABCD"}
    for i in range(260, len(cv) - max(HZ)):
        if in_dip[i]:
            if not in_dip[i - 1] and i - last["A"] >= 60:
                last["A"] = i; rows.append(add("A raw_dip", t, i, cv, dates))
            if (below_run[i - 1] == 1 and cv[i] > sma20[i] and i - last["B"] >= 60):
                last["B"] = i; rows.append(add("B react_sma", t, i, cv, dates))
            if (cv[i] >= low20[i] * 1.10 and cv[i - 1] < low20[i - 1] * 1.10
                    and i - last["C"] >= 60):
                last["C"] = i; rows.append(add("C react_low", t, i, cv, dates))
        elif dd[i] > -0.05 and i - last["D"] >= 60:
            last["D"] = i; rows.append(add("D no_dip", t, i, cv, dates))
    pool = np.arange(260, len(cv) - max(HZ))
    for i in rng.choice(pool, size=min(60, len(pool)), replace=False):
        rows.append(add("R random", t, i, cv, dates))

d = pd.DataFrame([r for r in rows if r])
print(f"{len(d)} entries, {len(U)} names, 2011-2026. Excess return vs SPY.\n")
print(f"{'arm':<14}{'n':>7}{'60d':>9}{'120d':>9}{'250d':>9}{'win% 250d':>11}")
for a in sorted(d.arm.unique()):
    s = d[d.arm == a]
    print(f"{a:<14}{len(s):7d}{s.x60.mean()*100:8.2f}%{s.x120.mean()*100:8.2f}%"
          f"{s.x250.mean()*100:8.2f}%{(s.x250>0).mean()*100:10.0f}%")

print("\n--- does confirmation beat buying the dip cold? ---")
A = d[d.arm == "A raw_dip"]
for arm in ("B react_sma", "C react_low"):
    B = d[d.arm == arm]
    for h in (60, 250):
        diff = B[f"x{h}"].mean() - A[f"x{h}"].mean()
        se = np.sqrt(B[f"x{h}"].var()/len(B) + A[f"x{h}"].var()/len(A))
        print(f"  {arm} - raw_dip @{h}d: {diff*100:+6.2f}%  SE {se*100:4.2f}%  t={diff/se:+5.2f}")
