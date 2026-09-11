"""Quality-dip screen: great business, hot sector, beaten down to the 200-day,
sold off on fear rather than a broken thesis, medium volatility.

Filters are deliberately transparent -- every column is shown so the fear-vs-
broken call stays with the human. This is a CANDIDATE LIST, not a signal.
"""
from __future__ import annotations
import sys, io, warnings, math
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd, yfinance as yf

SECTORS = {
 "semis/AI-hw": "NVDA AMD AVGO TSM MU INTC QCOM TXN ADI MRVL LRCX AMAT KLAC ASML NXPI ON MCHP "
                "SWKS QRVO TER ENTG MPWR ALAB CRDO ARM SMCI ANET COHR LITE ONTO ACLS AMKR AEIS",
 "software/AI": "MSFT GOOGL META ADBE CRM NOW ORCL PANW CRWD ZS NET DDOG SNOW MDB TEAM WDAY "
                "HUBS INTU ADSK SNPS CDNS FTNT OKTA TWLO APP TTD SHOP",
 "solar/clean": "FSLR ENPH SEDG RUN NXT SHLS ARRY CSIQ JKS FLNC GEV NEE BE PLUG",
 "EV/mobility": "TSLA RIVN LCID GM F LI XPEV APTV ALB MP",
 "power/infra": "VRT ETN PWR NVT MOD CEG VST TLN ISRG DXCM",
}
TICKERS = sorted({t for v in SECTORS.values() for t in v.split()})
SEC_OF = {t: k for k, v in SECTORS.items() for t in v.split()}

px = yf.download(TICKERS, period="2y", auto_adjust=True, progress=False, threads=True)
close = px["Close"]

rows = []
for t in TICKERS:
    try:
        c = close[t].dropna()
        if len(c) < 260:
            continue
        last = c.iloc[-1]
        sma200 = c.rolling(200).mean().iloc[-1]
        hi52 = c.iloc[-252:].max()
        dd = last / hi52 - 1                      # drawdown from 52w high
        d200 = last / sma200 - 1                  # distance from the 200-day line
        vol = c.pct_change().iloc[-252:].std() * math.sqrt(252)
        mom20 = last / c.iloc[-21] - 1
        rows.append({"t": t, "sector": SEC_OF[t], "px": last, "dd52": dd,
                     "d200": d200, "vol": vol, "mom20": mom20})
    except Exception:
        continue

df = pd.DataFrame(rows)
# THE SETUP: beaten down, sitting on / just under / just over the 200-day line
cand = df[(df.dd52 <= -0.15) & (df.d200 >= -0.15) & (df.d200 <= 0.05)].copy()
print(f"{len(df)} names screened -> {len(cand)} at the 200-day after a >=15% drawdown\n")

# --- fundamentals pass: is the business actually fine? ---
out = []
for _, r in cand.iterrows():
    t = r.t
    try:
        info = yf.Ticker(t).info
    except Exception:
        info = {}
    g = lambda k: info.get(k)
    rev_g, mar = g("revenueGrowth"), g("profitMargins")
    td, tc = g("totalDebt") or 0, g("totalCash") or 0
    ebitda, fcf = g("ebitda"), g("freeCashflow")
    netdebt = (td - tc) / ebitda if ebitda and ebitda > 0 else None
    out.append({**r.to_dict(), "rev_g": rev_g, "margin": mar,
                "netdebt_ebitda": netdebt, "fcf_pos": (fcf or 0) > 0,
                "pe": g("forwardPE"), "mcap": (g("marketCap") or 0) / 1e9})

f = pd.DataFrame(out)
QUALITY = (f.rev_g.fillna(-1) > 0) & (f.margin.fillna(-1) > 0) & (f.fcf_pos) & \
          (f.netdebt_ebitda.fillna(99) < 2.5)
MEDVOL = (f.vol > 0.28) & (f.vol < 0.62)          # not AAPL-slow, not MU-fast

f["quality"] = QUALITY
f["medvol"] = MEDVOL
f = f.sort_values("dd52")

def show(d, title):
    if not len(d):
        print(f"--- {title}: none ---\n"); return
    print(f"--- {title} ({len(d)}) ---")
    print(f"{'tkr':<6}{'sector':<13}{'px':>8}{'dd52':>8}{'vs200':>8}{'vol':>7}"
          f"{'rev_g':>8}{'margin':>8}{'ND/EB':>7}{'fwdPE':>7}{'$B':>7}")
    for _, r in d.iterrows():
        nd = f"{r.netdebt_ebitda:.1f}" if r.netdebt_ebitda is not None and not pd.isna(r.netdebt_ebitda) else "net$"
        pe = f"{r.pe:.0f}" if r.pe and not pd.isna(r.pe) else "-"
        print(f"{r.t:<6}{r.sector:<13}{r.px:8.2f}{r.dd52*100:7.0f}%{r.d200*100:7.1f}%"
              f"{r.vol*100:6.0f}%{(r.rev_g or 0)*100:7.0f}%{(r.margin or 0)*100:7.0f}%"
              f"{nd:>7}{pe:>7}{r.mcap:7.0f}")
    print()

show(f[f.quality & f.medvol], "PASSES QUALITY + MEDIUM VOL")
show(f[f.quality & ~f.medvol], "quality, but vol outside 28-62%")
show(f[~f.quality], "at the 200-day but FAILS quality (the 'broken' pile)")
f.to_csv("research/screen/candidates.csv", index=False)
