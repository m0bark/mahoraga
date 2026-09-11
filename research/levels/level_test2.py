"""Part 2 -- (a) does SUPPORT bounce? (b) does it matter WHY price is there?

(b) is the mechanism question: a level reached by quiet drift vs a level
reached on a news-sized gap. If levels are informationless but *reasons*
are not, the conditioner should be the reason, not the line.
"""
import sys, io, warnings
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd, yfinance as yf

TICKERS = ("AAPL MSFT JNJ XOM JPM PG KO PEP WMT CVX MRK PFE T VZ INTC CSCO ORCL "
           "IBM MCD NKE HD LOW CAT DE MMM GE BA HON UPS UNH ABT LLY BMY AMGN GILD "
           "TXN QCOM ADBE CRM AMD MU AMAT COST TGT SBUX DIS CMCSA F GM DAL LUV "
           "GS MS BAC C WFC AXP USB PNC SCHW").split()
LB, NEAR, HZ = 60, 0.005, 15

px = yf.download(TICKERS, start="2006-01-01", end="2026-08-27",
                 auto_adjust=True, progress=False, threads=True)

sup, res = [], []
for t in TICKERS:
    try:
        h, l, c, v = px["High"][t], px["Low"][t], px["Close"][t], px["Volume"][t]
    except KeyError:
        continue
    df = pd.DataFrame({"h": h, "l": l, "c": c, "v": v}).dropna()
    if len(df) < 500:
        continue
    cv = df.c.values
    ret = df.c.pct_change().abs()
    # "news-sized move" = |1-day move| in top 2% of that stock's history, within 3 days before the touch
    big = (ret > ret.quantile(0.98)).rolling(3).max().shift(1).values

    # ---- SUPPORT: touch a 60-day low from above ----
    lvl = df.l.rolling(LB).min().shift(1)
    above = (df.c > lvl * (1 + NEAR)).rolling(5).min().shift(1) == 1
    at = (df.c <= lvl * (1 + NEAR)) & (df.c >= lvl * (1 - NEAR)) & above
    lv = lvl.values
    last = -99
    for i in np.where(at.values)[0]:
        if i - last < HZ or i + HZ >= len(cv) or np.isnan(lv[i]): continue
        last = i; L = lv[i]; fut = cv[i+1:i+1+HZ]
        u = np.where(fut > L*1.05)[0]; d = np.where(fut < L*0.98)[0]
        u = u[0] if len(u) else 10**6; d = d[0] if len(d) else 10**6
        if u == d: continue
        sup.append({"bounced": u < d, "resolved": min(u,d) < 10**6,
                    "news": bool(big[i] == 1), "fwd10": cv[i+10]/cv[i]-1})

    # ---- RESISTANCE, split by news vs drift ----
    lvl2 = df.h.rolling(LB).max().shift(1)
    below = (df.c < lvl2*(1-NEAR)).rolling(5).min().shift(1) == 1
    at2 = (df.c >= lvl2*(1-NEAR)) & (df.c <= lvl2*(1+NEAR)) & below
    l2 = lvl2.values
    last = -99
    for i in np.where(at2.values)[0]:
        if i - last < HZ or i + HZ >= len(cv) or np.isnan(l2[i]): continue
        last = i; L = l2[i]; fut = cv[i+1:i+1+HZ]
        u = np.where(fut > L*1.02)[0]; d = np.where(fut < L*0.95)[0]
        u = u[0] if len(u) else 10**6; d = d[0] if len(d) else 10**6
        if u == d: continue
        res.append({"broke": u < d, "resolved": min(u,d) < 10**6,
                    "news": bool(big[i] == 1), "fwd10": cv[i+10]/cv[i]-1})

S, R = pd.DataFrame(sup), pd.DataFrame(res)
print("=== SUPPORT: at a 60-day LOW (bounce +5% vs break -2%, 15d) ===")
r0 = S[S.resolved]
print(f"  all touches           n={len(r0):5d}   bounced {r0.bounced.mean()*100:5.1f}%   fwd10 {S.fwd10.mean()*100:+5.2f}%")
for flag, lab in [(False, "reached by quiet drift"), (True, "reached on news-sized move")]:
    s = S[S.news == flag]; sr = s[s.resolved]
    print(f"  {lab:22s}n={len(sr):5d}   bounced {sr.bounced.mean()*100:5.1f}%   fwd10 {s.fwd10.mean()*100:+5.2f}%")
print()
print("=== RESISTANCE: at a 60-day HIGH, split by how it got there ===")
for flag, lab in [(False, "reached by quiet drift"), (True, "reached on news-sized move")]:
    s = R[R.news == flag]; sr = s[s.resolved]
    print(f"  {lab:22s}n={len(sr):5d}   broke   {sr.broke.mean()*100:5.1f}%   fwd10 {s.fwd10.mean()*100:+5.2f}%")
