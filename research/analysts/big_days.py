"""When a pick "goes 40% in one day" -- what actually produced that?

If an analyst's headline average return is driven by a handful of enormous
single days, the question is whether those days were foreseeable. The surge
study (research/surges/RESULTS.md) already measured that 54% of the biggest
days inside a surge OPEN as gaps -- priced before anyone can trade.

Here: for stock-years that doubled, how concentrated was the gain, and how
much of it arrived in gaps?
"""
from __future__ import annotations
import io, sys, warnings
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd, yfinance as yf

U = ("AAPL MSFT GOOGL AMZN META NVDA AMD AVGO MU INTC QCOM MRVL LRCX AMAT KLAC NXPI ON MCHP "
     "SWKS TER MPWR ANET ADBE CRM NOW ORCL PANW ZS NET DDOG TEAM WDAY INTU ADSK SNPS CDNS "
     "FTNT SHOP FSLR ENPH RUN PLUG NEE BE TSLA GM F ALB MP VRT ETN PWR NVT MOD CEG VST ISRG "
     "DXCM JNJ XOM JPM PG KO PEP WMT CVX MRK PFE T VZ CSCO IBM MCD NKE HD LOW CAT DE MMM GE "
     "BA HON UPS UNH ABT LLY BMY AMGN GILD COST TGT SBUX DIS CMCSA DAL LUV GS MS BAC C WFC "
     "AXP USB PNC SCHW").split()
H = 252

data = yf.download(U, start="2005-01-01", end="2026-09-04", auto_adjust=True,
                   progress=False, threads=True)
C, O = data["Close"], data["Open"]

rows = []
for t in U:
    if t not in C:
        continue
    c = C[t].dropna()
    o = O[t].reindex(c.index)
    if len(c) < 600:
        continue
    cv, ov = c.values, o.values
    for i in range(0, len(cv) - H, 63):
        w = cv[i:i + H + 1]
        tot = w[-1] / w[0] - 1
        dr = w[1:] / w[:-1] - 1
        k = int(np.argmax(dr))
        big = float(dr[k])
        gi = i + 1 + k
        gap = (ov[gi] / cv[gi - 1] - 1) if gi < len(cv) else np.nan
        # what the year returns if you remove its best 5 days
        srt = np.sort(dr)[::-1]
        ex5 = float(np.prod(1 + srt[5:]) - 1)
        rows.append({"t": t, "total": tot, "best_day": big, "gap": gap,
                     "ex_best5": ex5, "n_over20": int((dr > 0.20).sum())})
d = pd.DataFrame(rows).dropna(subset=["total"])

print(f"{len(d):,} overlapping stock-years\n")
dbl = d[d.total > 1.0]
print(f"=== stock-years that MORE THAN DOUBLED: {len(dbl):,} ({len(dbl)/len(d)*100:.1f}%) ===")
print(f"  median total return                  {dbl.total.median()*100:+.0f}%")
print(f"  median return EXCLUDING best 5 days   {dbl.ex_best5.median()*100:+.0f}%")
print(f"  share whose single best day was >20%  {(dbl.best_day>0.20).mean()*100:.0f}%")
print(f"  ...and that day OPENED with a >10% gap {(dbl[dbl.best_day>0.20].gap>0.10).mean()*100:.0f}%")
print(f"  median size of the best single day    {dbl.best_day.median()*100:+.1f}%")

print("\n=== all stock-years: how much rides on a few days ===")
print(f"  median total                          {d.total.median()*100:+.1f}%")
print(f"  median excluding best 5 days          {d.ex_best5.median()*100:+.1f}%")
print(f"  share with at least one +20% day      {(d.n_over20>0).mean()*100:.1f}%")

big = d[d.best_day > 0.20]
print(f"\n=== the '+40% in one day' events ({len(big):,} stock-years contain one) ===")
print(f"  median gap at the open on that day     {big.gap.median()*100:+.1f}%")
print(f"  share where the GAP was most of the move: "
      f"{(big.gap / big.best_day > 0.6).mean()*100:.0f}%")
print("\nA gap is priced before the opening bell. Holding the name beforehand")
print("captures it; deciding to buy after seeing it does not.")
