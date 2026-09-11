"""Does a chart 'level' predict anything?

Event: price approaches a prior 60-day high (resistance) from below.
Question: does it BREAK or REJECT -- and are those odds different from
a random day in the same stock? If not, the level carries zero information.

Honest caveats: current-member ticker list (survivorship-biased upward),
yfinance adjusted closes, no costs. This measures conditional probability,
not a tradeable strategy.
"""
import sys, io, warnings
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd, yfinance as yf

TICKERS = ("AAPL MSFT JNJ XOM JPM PG KO PEP WMT CVX MRK PFE T VZ INTC CSCO ORCL "
           "IBM MCD NKE HD LOW CAT DE MMM GE BA HON UPS UNH ABT LLY BMY AMGN GILD "
           "TXN QCOM ADBE CRM AMD MU AMAT COST TGT SBUX DIS CMCSA F GM DAL LUV "
           "GS MS BAC C WFC AXP USB PNC SCHW").split()

LOOKBACK = 60      # days defining the level
NEAR     = 0.005   # "at the level" = within 0.5%
HORIZON  = 15      # trading days to resolve
BREAK_UP = 0.02    # +2% above level = broke
REJECT   = 0.05    # -5% below level = rejected

px = yf.download(TICKERS, start="2006-01-01", end="2026-08-27",
                 auto_adjust=True, progress=False, threads=True)

rows = []
for t in TICKERS:
    try:
        h, c, v = px["High"][t], px["Close"][t], px["Volume"][t]
    except KeyError:
        continue
    df = pd.DataFrame({"h": h, "c": c, "v": v}).dropna()
    if len(df) < 500:
        continue
    lvl = df.h.rolling(LOOKBACK).max().shift(1)
    volr = df.v / df.v.rolling(LOOKBACK).mean()
    below = (df.c < lvl * (1 - NEAR)).rolling(5).min().shift(1) == 1   # was clearly below
    at = (df.c >= lvl * (1 - NEAR)) & (df.c <= lvl * (1 + NEAR)) & below

    cv, lv, vv = df.c.values, lvl.values, volr.values
    idx = np.where(at.values)[0]
    last = -99
    for i in idx:
        if i - last < HORIZON or i + HORIZON >= len(cv) or np.isnan(lv[i]):
            continue
        last = i
        L = lv[i]
        fut = cv[i+1:i+1+HORIZON]
        up = np.where(fut > L * (1 + BREAK_UP))[0]
        dn = np.where(fut < L * (1 - REJECT))[0]
        u = up[0] if len(up) else 10**6
        d = dn[0] if len(dn) else 10**6
        if u == d:
            continue
        rows.append({"t": t, "i": i, "broke": u < d, "resolved": min(u, d) < 10**6,
                     "volr": vv[i], "fwd10": cv[i+10]/cv[i] - 1})

    # BASELINE: same test from a random day, level = that day's close
    rng = np.random.default_rng(abs(hash(t)) % 2**31)
    cand = rng.choice(np.arange(LOOKBACK + 5, len(cv) - HORIZON - 1),
                      size=min(400, len(cv) // 4), replace=False)
    for i in cand:
        L = cv[i]
        fut = cv[i+1:i+1+HORIZON]
        up = np.where(fut > L * (1 + BREAK_UP))[0]
        dn = np.where(fut < L * (1 - REJECT))[0]
        u = up[0] if len(up) else 10**6
        d = dn[0] if len(dn) else 10**6
        if u == d:
            continue
        rows.append({"t": t, "i": i, "broke": u < d, "resolved": min(u, d) < 10**6,
                     "volr": np.nan, "fwd10": cv[i+10]/cv[i] - 1, "baseline": True})

r = pd.DataFrame(rows)
if "baseline" not in r.columns:
    r["baseline"] = False
r["baseline"] = r["baseline"].fillna(False).astype(bool)
ev, bl = r[~r.baseline], r[r.baseline]

def rate(d, label):
    res = d[d.resolved]
    print(f"{label:34s} n={len(res):6d}  broke {res.broke.mean()*100:5.1f}%   "
          f"fwd10 mean {d.fwd10.mean()*100:+5.2f}%  median {d.fwd10.median()*100:+5.2f}%")

print(f"=== AT A 60-DAY HIGH ({LOOKBACK}d level, +{BREAK_UP:.0%} break vs -{REJECT:.0%} reject, {HORIZON}d) ===")
rate(ev, "AT THE LEVEL")
rate(bl, "RANDOM DAY (baseline)")
print()
print("--- conditioned on volume at the level ---")
q = ev.dropna(subset=["volr"])
for lo, hi, lab in [(0, .8, "volume < 0.8x avg"), (.8, 1.2, "0.8-1.2x"),
                    (1.2, 2.0, "1.2-2.0x"), (2.0, 99, "volume > 2x avg")]:
    s = q[(q.volr >= lo) & (q.volr < hi)]
    if len(s) > 30:
        rate(s, "  " + lab)
