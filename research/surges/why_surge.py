"""Reverse-engineer surges: find them first, THEN ask what caused them.

Instead of testing a hypothesis, mine the outcome and classify. The payoff
question is not 'what causes surges' -- it is 'what fraction of surges were
detectable BEFORE they happened'. If nearly all are news-day gaps with no
pre-signature, surges are unforecastable from price and that is a finding.

Surge = forward 20-day return >= +25%.
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
SURGE, HZ = 0.25, 20

px = yf.download(U + ["SPY"], start="2010-01-01", end="2026-08-28",
                 auto_adjust=True, progress=False, threads=True)
C, O, V = px["Close"], px["Open"], px["Volume"]
spy = C["SPY"].dropna()

rows = []
for t in U:
    if t not in C:
        continue
    c, o, v = C[t].dropna(), O[t], V[t]
    if len(c) < 800:
        continue
    cv, dates = c.values, c.index
    fwd = np.full(len(cv), np.nan)
    fwd[:-HZ] = cv[HZ:] / cv[:-HZ] - 1
    volavg = v.reindex(dates).rolling(60).mean().values
    vv = v.reindex(dates).values
    ov = o.reindex(dates).values
    last = -999
    for i in np.where(fwd >= SURGE)[0]:
        if i - last < HZ or i < 260:
            continue
        last = i
        win_c = cv[i:i + HZ + 1]
        # biggest single day inside the surge window, and was it a gap?
        day_r = win_c[1:] / win_c[:-1] - 1
        k = int(np.argmax(day_r))
        big_day, big_ret = i + 1 + k, float(day_r[k])
        gap = (ov[big_day] / cv[big_day - 1] - 1) if big_day < len(cv) else np.nan
        s0, s1 = spy.asof(dates[i]), spy.asof(dates[min(i + HZ, len(dates) - 1)])
        rows.append({
            "t": t, "date": dates[i], "fwd20": fwd[i],
            "prior60": cv[i] / cv[i - 60] - 1,
            "dd_at_start": cv[i] / max(cv[max(0, i - 252):i + 1]) - 1,
            "spy20": s1 / s0 - 1,
            "big_day_ret": big_ret,
            "big_day_gap": gap,
            "gap_share": (gap / big_ret) if big_ret > 0 else np.nan,
            "share_from_1day": big_ret / fwd[i],
            "vol_before": float(np.nanmean(vv[i-5:i]) / volavg[i]) if volavg[i] else np.nan,
            "ret_5d_before": cv[i] / cv[i - 5] - 1,
        })

d = pd.DataFrame(rows)
print(f"{len(d)} surges (>= +{SURGE:.0%} in {HZ}d), {len(d.t.unique())} names, "
      f"{d.date.min().date()}..{d.date.max().date()}\n")

print("=== HOW CONCENTRATED IS THE MOVE? ===")
print(f"  median share of the {HZ}d surge from its single biggest day: "
      f"{d.share_from_1day.median()*100:.0f}%")
print(f"  surges where ONE day is >=50% of the move: "
      f"{(d.share_from_1day>=0.5).mean()*100:.0f}%")
print(f"  that biggest day was an OPEN GAP (>=3%): "
      f"{(d.big_day_gap>=0.03).mean()*100:.0f}%")
print(f"  median gap as share of the big day's return: {d.gap_share.median()*100:.0f}%")

print("\n=== WAS IT THE MARKET, OR THE NAME? ===")
print(f"  median SPY return over the same 20d: {d.spy20.median()*100:+.1f}%")
print(f"  surges where SPY also rose >5% (market-wide): {(d.spy20>0.05).mean()*100:.0f}%")

print("\n=== WHAT DID THE STOCK LOOK LIKE BEFORE? ===")
print(f"  median prior-60d return: {d.prior60.median()*100:+.1f}%")
print(f"  median drawdown from 52w high at start: {d.dd_at_start.median()*100:+.1f}%")
for lo, hi, lab in [(-9, -0.30, "deep dip (< -30%)"), (-0.30, -0.15, "-15..-30%"),
                    (-0.15, -0.05, "-5..-15%"), (-0.05, 1, "near highs (> -5%)")]:
    s = d[(d.dd_at_start > lo) & (d.dd_at_start <= hi)]
    print(f"    {lab:<22}{len(s):5d}  {len(s)/len(d)*100:4.0f}% of surges")

print("\n=== ANY PRE-SIGNATURE? (the only part that would be tradeable) ===")
print(f"  median volume in the 5d BEFORE, vs 60d avg: {d.vol_before.median():.2f}x")
print(f"  surges with elevated pre-volume (>1.5x): {(d.vol_before>1.5).mean()*100:.0f}%")
print(f"  median return in the 5d BEFORE the surge: {d.ret_5d_before.median()*100:+.2f}%")
d.to_csv("research/surges/surges.csv", index=False)
