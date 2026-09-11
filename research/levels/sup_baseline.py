"""Baseline for the support test: same +5%/-2% barriers from a RANDOM day."""
import sys, io, warnings
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8"); warnings.filterwarnings("ignore")
import numpy as np, pandas as pd, yfinance as yf
TICKERS = ("AAPL MSFT JNJ XOM JPM PG KO PEP WMT CVX MRK PFE T VZ INTC CSCO ORCL IBM MCD NKE "
           "HD LOW CAT DE MMM GE BA HON UPS UNH ABT LLY BMY AMGN GILD TXN QCOM ADBE CRM AMD "
           "MU AMAT COST TGT SBUX DIS CMCSA F GM DAL LUV GS MS BAC C WFC AXP USB PNC SCHW").split()
px = yf.download(TICKERS, start="2006-01-01", end="2026-08-27", auto_adjust=True, progress=False)
out = []
for t in TICKERS:
    try: c = px["Close"][t].dropna()
    except KeyError: continue
    cv = c.values
    if len(cv) < 500: continue
    rng = np.random.default_rng(abs(hash(t)) % 2**31)
    for i in rng.choice(np.arange(65, len(cv)-16), size=min(400, len(cv)//4), replace=False):
        L = cv[i]; fut = cv[i+1:i+16]
        u = np.where(fut > L*1.05)[0]; d = np.where(fut < L*0.98)[0]
        u = u[0] if len(u) else 10**6; d = d[0] if len(d) else 10**6
        if u == d: continue
        out.append(u < d)
out = np.array(out)
print(f"RANDOM DAY, same +5%/-2% barriers:  n={len(out)}  'bounced' {out.mean()*100:.1f}%")
