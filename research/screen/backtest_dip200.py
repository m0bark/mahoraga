"""Backtest the quality-dip setup: name >=15% off its 52w high, sitting near
its 200-day SMA. Buy, hold, measure.

TWO CONTROLS, because without them this number is worthless:
  1. SPY over the identical window (the bar everything must beat).
  2. RANDOM entries in the SAME universe on the SAME dates. This is the one
     that matters: the ticker list is today's survivors, so it drifts upward
     no matter what. Both arms inherit that bias, so signal-minus-random is
     the honest excess.

NOT TESTED HERE: the quality overlay. yfinance only serves CURRENT
fundamentals, so filtering 2016 entries on 2026 financials is lookahead of
the worst kind. Price mechanics only. Stated, not hidden.
"""
from __future__ import annotations
import sys, io, warnings, math
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd, yfinance as yf

SECTORS = {
 "semis": "NVDA AMD AVGO TSM MU INTC QCOM TXN ADI MRVL LRCX AMAT KLAC ASML NXPI ON MCHP "
          "SWKS QRVO TER ENTG MPWR ANET COHR LITE ONTO ACLS AMKR AEIS",
 "software": "MSFT GOOGL META ADBE CRM NOW ORCL PANW ZS NET DDOG TEAM WDAY HUBS INTU ADSK "
             "SNPS CDNS FTNT OKTA TWLO TTD SHOP",
 "clean": "FSLR ENPH SEDG RUN CSIQ JKS PLUG NEE BE",
 "EV": "TSLA GM F LI XPEV APTV ALB MP",
 "infra": "VRT ETN PWR NVT MOD CEG VST ISRG DXCM",
}
TICKERS = sorted({t for v in SECTORS.values() for t in v.split()})
HOLDS = (20, 60, 120, 250)
DD_MIN, LO200, HI200 = -0.15, -0.15, 0.05

raw = yf.download(TICKERS + ["SPY"], start="2012-01-01", end="2026-08-28",
                  auto_adjust=True, progress=False, threads=True)["Close"]
spy = raw["SPY"].dropna()
spy_dd = spy / spy.rolling(252).max() - 1

sig, rnd = [], []
rng = np.random.default_rng(7)
for t in TICKERS:
    if t not in raw:
        continue
    c = raw[t].dropna()
    if len(c) < 600:
        continue
    hi = c.rolling(252).max()
    sma = c.rolling(200).mean()
    dd = c / hi - 1
    d200 = c / sma - 1
    ok = (dd <= DD_MIN) & (d200 >= LO200) & (d200 <= HI200)
    idx = np.where(ok.values)[0]

    cv = c.values
    dates = c.index
    last = -999
    ent = []
    for i in idx:
        if i - last < 60 or i + max(HOLDS) >= len(cv):   # 1 entry per name per quarter
            continue
        last = i
        ent.append(i)
        row = {"t": t, "date": dates[i],
               "spy_dd": spy_dd.asof(dates[i]), "arm": "signal"}
        for h in HOLDS:
            row[f"r{h}"] = cv[i + h] / cv[i] - 1
            s0, s1 = spy.asof(dates[i]), spy.asof(dates[i + h] if i + h < len(dates) else dates[-1])
            row[f"x{h}"] = row[f"r{h}"] - (s1 / s0 - 1)
        sig.append(row)
    # random control: same count of entries, same name, random dates
    if ent:
        pool = np.arange(260, len(cv) - max(HOLDS) - 1)
        for i in rng.choice(pool, size=min(len(ent) * 3, len(pool)), replace=False):
            row = {"t": t, "date": dates[i], "arm": "random",
                   "spy_dd": spy_dd.asof(dates[i])}
            for h in HOLDS:
                row[f"r{h}"] = cv[i + h] / cv[i] - 1
                s0, s1 = spy.asof(dates[i]), spy.asof(dates[i + h])
                row[f"x{h}"] = row[f"r{h}"] - (s1 / s0 - 1)
            rnd.append(row)

S, R = pd.DataFrame(sig), pd.DataFrame(rnd)
print(f"universe {len(TICKERS)} names | signal entries {len(S)} | random control {len(R)}")
print(f"period {S.date.min().date()} .. {S.date.max().date()}\n")

print(f"{'hold':<7}{'SIGNAL ret':>12}{'RANDOM ret':>12}{'sig vs SPY':>12}"
      f"{'rnd vs SPY':>12}{'EDGE (sig-rnd)':>16}{'win%':>7}")
for h in HOLDS:
    a, b = S[f"r{h}"].mean(), R[f"r{h}"].mean()
    xa, xb = S[f"x{h}"].mean(), R[f"x{h}"].mean()
    print(f"{h:<7}{a*100:11.2f}%{b*100:11.2f}%{xa*100:11.2f}%{xb*100:11.2f}%"
          f"{(xa-xb)*100:15.2f}%{(S[f'r{h}']>0).mean()*100:6.0f}%")

print("\n--- does it work better in a market panic? (your Rule 2) ---")
print(f"{'SPY drawdown at entry':<26}{'n':>6}{'60d excess vs SPY':>20}{'250d excess':>14}")
for lo, hi, lab in [(-99, -0.12, "SPY <= -12% (panic)"), (-0.12, -0.05, "SPY -5% to -12%"),
                    (-0.05, 1, "SPY > -5% (calm)")]:
    s = S[(S.spy_dd > lo) & (S.spy_dd <= hi)]
    if len(s) > 20:
        print(f"{lab:<26}{len(s):6d}{s.x60.mean()*100:19.2f}%{s.x250.mean()*100:13.2f}%")
S.to_csv("research/screen/backtest_entries.csv", index=False)
R.to_csv("research/screen/backtest_random.csv", index=False)
