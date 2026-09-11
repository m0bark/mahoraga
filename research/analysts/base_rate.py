"""What fraction of stocks rise over 12 months anyway?

This is the number an analyst's "success rate" must be compared against.
A 70% hit rate is only impressive if the base rate is materially below 70%.

Survivorship note: this ticker list is today's survivors, so the measured
base rate is an OVER-estimate of reality. That cuts in the analyst's favour
here -- the true bar is lower. It is stated, not hidden.
"""
from __future__ import annotations
import io, sys, warnings
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd, yfinance as yf

U = ("AAPL MSFT GOOGL AMZN META NVDA AMD AVGO TSM MU INTC QCOM TXN ADI MRVL LRCX AMAT KLAC "
     "NXPI ON MCHP SWKS TER MPWR ANET ADBE CRM NOW ORCL PANW ZS NET DDOG TEAM WDAY INTU ADSK "
     "SNPS CDNS FTNT SHOP FSLR ENPH RUN PLUG NEE BE TSLA GM F ALB MP VRT ETN PWR NVT MOD CEG "
     "VST ISRG DXCM JNJ XOM JPM PG KO PEP WMT CVX MRK PFE T VZ CSCO IBM MCD NKE HD LOW CAT DE "
     "MMM GE BA HON UPS UNH ABT LLY BMY AMGN GILD COST TGT SBUX DIS CMCSA DAL LUV GS MS BAC C "
     "WFC AXP USB PNC SCHW").split()

px = yf.download(U + ["SPY"], start="2005-01-01", end="2026-09-04",
                 auto_adjust=True, progress=False, threads=True)["Close"]
spy = px["SPY"].dropna()
names = [t for t in U if t in px]
H = 252

rows = []
for t in names:
    c = px[t].dropna()
    if len(c) < 600:
        continue
    cv, idx = c.values, c.index
    fwd = np.full(len(cv), np.nan)
    fwd[:-H] = cv[H:] / cv[:-H] - 1
    for i in range(0, len(cv) - H, 21):          # monthly sampling
        s0, s1 = spy.asof(idx[i]), spy.asof(idx[i + H])
        rows.append({"t": t, "date": idx[i], "ret": fwd[i],
                     "mkt": s1 / s0 - 1})
d = pd.DataFrame(rows).dropna()
d["beat_mkt"] = d.ret > d.mkt

print(f"{len(d):,} stock-year observations, {len(names)} names, "
      f"{d.date.min().date()}..{d.date.max().date()}\n")
print("=== THE BAR AN ANALYST MUST CLEAR ===")
print(f"  stocks with POSITIVE 12-month return:      {(d.ret > 0).mean()*100:.1f}%")
print(f"  stocks that BEAT the market over 12 months:{d.beat_mkt.mean()*100:.1f}%")
print(f"  median 12-month return:                    {d.ret.median()*100:+.1f}%")
print(f"  mean 12-month return:                      {d.ret.mean()*100:+.1f}%")

print("\n=== by market regime (SPY's own 12m return) ===")
for lo, hi, lab in [(-9, 0, "market DOWN"), (0, 0.15, "market +0-15%"),
                    (0.15, 9, "market +15% or more")]:
    s = d[(d.mkt > lo) & (d.mkt <= hi)]
    if len(s) > 100:
        print(f"  {lab:<22} n={len(s):6,}  positive {(s.ret>0).mean()*100:5.1f}%"
              f"   beat mkt {s.beat_mkt.mean()*100:5.1f}%")

print("\n=== the skew Bessembinder describes ===")
print(f"  mean {d.ret.mean()*100:+.1f}% vs median {d.ret.median()*100:+.1f}% "
      f"-> mean is dragged up by a right tail")
print(f"  share of observations above +100%: {(d.ret > 1.0).mean()*100:.2f}%")
print(f"  share above +50%:                  {(d.ret > 0.5).mean()*100:.2f}%")
