"""Fear meter v2 -- is this drawdown fear, or is the business breaking?

    python research/tool/fear_meter.py META NXPI ENPH

WHAT IT IS: a summary of business STATE, not a forecast. Every line is a
fact about the company or its peers. It does not predict returns -- five
sealed runs in this project say nothing in this family does. It answers the
one question a screen cannot: "is the thing that fell still working?"

v1 was a single quarter of revenue. That misses three ways a business
breaks and one way a price falls while the business is fine:

  1. TRAJECTORY, not level. Revenue can grow while decelerating hard.
  2. QUALITY of earnings. OCF diverging from NI, margins rolling over,
     shares being issued -- deterioration shows here first.
  3. BALANCE SHEET stress. Leverage and liquidity kill companies that
     still post growth.
  4. PEER CONTEXT. A name down 40% while its sector is down 35% is a
     sector event. Down 40% while peers are flat is company-specific.
     This is the single biggest miss in v1.

And the honest output nobody else prints: UNEXPLAINED. If the business
checks out and peers are fine, the meter says so and tells you to go read
the news -- because the cause is real and it is not in the numbers yet.
That is the META case: every fundamental green, and the stock fell on a
capex guidance change no financial-statement screen can see.

Survivorship note: companies that actually broke often delist, so any
sample skews toward survivors. That biases a meter like this toward
calling FEAR. Treat a FEAR verdict as "no red flag found", not "safe".
"""
from __future__ import annotations

import io
import math
import sys
import warnings

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import yfinance as yf

PEERS = {
    "semis": "NVDA AMD AVGO TSM MU INTC QCOM TXN ADI MRVL LRCX AMAT KLAC NXPI ON MCHP "
             "SWKS QRVO TER ENTG MPWR ASML AMKR COHR".split(),
    "software": "MSFT GOOGL META ADBE CRM NOW ORCL PANW ZS NET DDOG TEAM WDAY HUBS INTU "
                "ADSK SNPS CDNS FTNT OKTA TWLO TTD SHOP".split(),
    "clean": "FSLR ENPH SEDG RUN CSIQ JKS PLUG NEE BE GEV".split(),
    "ev": "TSLA GM F LI XPEV APTV ALB MP RIVN LCID".split(),
    "infra": "VRT ETN PWR NVT MOD CEG VST ISRG DXCM".split(),
}
SECTOR_OF = {t: s for s, v in PEERS.items() for t in v}


def sector_drawdown(sector: str) -> float | None:
    """Median 52w drawdown across the peer group -- the market context."""
    names = PEERS.get(sector, [])
    if len(names) < 4:
        return None
    try:
        c = yf.download(names, period="2y", auto_adjust=True,
                        progress=False, threads=True)["Close"]
        dd = []
        for t in names:
            if t not in c:
                continue
            s = c[t].dropna()
            if len(s) > 252:
                dd.append(s.iloc[-1] / s.iloc[-252:].max() - 1)
        return float(np.median(dd)) if len(dd) >= 4 else None
    except Exception:
        return None


def series(tk: yf.Ticker, stmt: str, row: str) -> list[float] | None:
    try:
        df = getattr(tk, stmt)
        s = df.loc[row].dropna().sort_index()
        return [float(x) for x in s.values] if len(s) >= 2 else None
    except Exception:
        return None


def trend(v: list[float] | None) -> tuple[str, float | None]:
    """Direction of the last few periods, and the latest period-on-period change."""
    if not v or len(v) < 2:
        return "?", None
    chg = (v[-1] / v[-2] - 1) if v[-2] else None
    if len(v) >= 4 and all(x > 0 for x in v[-4:]):
        first = v[-3] / v[-4] - 1 if v[-4] else 0
        last = v[-1] / v[-2] - 1 if v[-2] else 0
        if last > first + 0.02:
            return "accelerating", chg
        if last < first - 0.02:
            return "decelerating", chg
    return "steady", chg


def assess(t: str) -> dict:
    tk = yf.Ticker(t)
    px = tk.history(period="2y")["Close"].dropna()
    if len(px) < 260:
        return {"ticker": t, "error": "not enough price history"}
    last = px.iloc[-1]
    dd = last / px.iloc[-252:].max() - 1

    rev = series(tk, "quarterly_income_stmt", "Total Revenue")
    ni = series(tk, "quarterly_income_stmt", "Net Income")
    gp = series(tk, "quarterly_income_stmt", "Gross Profit")
    ocf = series(tk, "quarterly_cashflow", "Operating Cash Flow")
    capex = series(tk, "quarterly_cashflow", "Capital Expenditure")
    sh = series(tk, "quarterly_balance_sheet", "Ordinary Shares Number")

    info = {}
    try:
        info = tk.info
    except Exception:
        pass

    flags: list[tuple[str, str, str]] = []   # (severity, name, detail)
    notes: list[str] = []                    # context, never scored

    rev_dir, rev_chg = trend(rev)
    if rev_chg is not None:
        if rev_chg < -0.05:
            flags.append(("RED", "revenue declining", f"{rev_chg:+.1%} QoQ"))
        elif rev_dir == "decelerating":
            flags.append(("AMBER", "growth decelerating", f"{rev_chg:+.1%} QoQ, slowing"))

    # CALIBRATED 2026-08-31: margin compression is the strongest flag in the
    # set -- >2% drop fires on 10% of names with 3.58x lift. The old 0.5%
    # AMBER was below the noise floor; tightened to 1% (1.75x lift).
    if gp and rev and len(gp) >= 2 and len(rev) >= 2:
        m1 = gp[-1] / rev[-1] if rev[-1] else None
        m0 = gp[-2] / rev[-2] if rev[-2] else None
        if m1 is not None and m0 is not None:
            if m1 < m0 - 0.02:
                flags.append(("RED", "gross margin compressing", f"{m0:.1%} -> {m1:.1%}"))
            elif m1 < m0 - 0.01:
                flags.append(("AMBER", "gross margin slipping", f"{m0:.1%} -> {m1:.1%}"))

    # REMOVED 2026-08-31 by calibration:
    #   "operating cash flow negative"  lift 0.77x -- fires as often on
    #       healthy names (8%) as sick ones (6%). Growth companies burn cash.
    #   "earnings not converting to cash" (OCF < 60% of NI)  lift 0.00x --
    #       fired on 16% of HEALTHY names and 0% of deteriorating ones. It
    #       was backwards. Kept only as a printed note, never as a flag.
    if ocf and ni and len(ni) >= 2 and ni[-1] and ni[-1] > 0 and ocf:
        conv = ocf[-1] / ni[-1]
        if conv < 0.6:
            notes.append(f"OCF/NI conversion {conv:.0%} "
                         f"(no discriminating power -- context only)")

    if sh and len(sh) >= 2 and sh[-2]:
        d = sh[-1] / sh[-2] - 1
        if d > 0.03:
            flags.append(("RED", "material dilution", f"share count {d:+.1%} QoQ"))
        elif d > 0.01:
            flags.append(("AMBER", "issuing shares", f"share count {d:+.1%} QoQ"))

    # CALIBRATED: debt/equity > 2.0 had lift 1.28x (nothing); > 1.0 has
    # 1.53x, so the threshold moved down and the severity down to AMBER.
    # "current ratio < 1" REMOVED -- lift 0.42x, i.e. it fired MORE often on
    # healthy names (23%) than deteriorating ones (10%). Backwards.
    de = info.get("debtToEquity")
    if de is not None and de > 100:
        flags.append(("AMBER", "leverage above 1x equity", f"debt/equity {de/100:.2f}"))

    # RECLASSIFIED 2026-08-31. Calibration: capex step-up does NOT indicate
    # deterioration -- lift 0.29x-0.95x up to 1.6x, and 26% of HEALTHY names
    # fire at 1.4x. Capex step-ups are mostly growth companies investing.
    # But it is often WHY a good business's stock fell (the META case), so it
    # is kept as CONTEXT and deliberately does not count toward a verdict.
    if capex and len(capex) >= 4:
        base = float(np.mean([abs(x) for x in capex[-4:-1]]))
        now = abs(capex[-1])
        if base and now > base * 1.4:
            notes.append(f"capex {now/1e6:,.0f}M vs {base/1e6:,.0f}M avg "
                         f"({now/base:.1f}x) -- capital allocation shifted; "
                         f"not a deterioration signal, a place to look")

    sec = SECTOR_OF.get(t)
    sec_dd = sector_drawdown(sec) if sec else None
    rel = None
    if sec_dd is not None:
        rel = dd - sec_dd

    reds = [f for f in flags if f[0] == "RED"]
    ambers = [f for f in flags if f[0] == "AMBER"]

    # rel = own drawdown minus peer median. rel ~ 0 => moved WITH the sector.
    # rel << 0 => fell much harder than peers = idiosyncratic, the class
    # PROTOCOLS calls the worst-recovering one. Flag it, never wave it through.
    sector_wide = (rel is not None and abs(rel) <= 0.10
                   and sec_dd is not None and sec_dd < -0.10)
    lone = rel is not None and rel < -0.10
    if lone:
        flags.append(("AMBER", "falling alone",
                      f"{dd:+.0%} vs {sec} peers {sec_dd:+.0%} "
                      f"({rel:+.0%} worse) -- company-specific"))
        ambers = [f for f in flags if f[0] == "AMBER"]

    if reds:
        verdict = "BROKEN"
        why = "fundamentals deteriorating"
    elif lone and not sector_wide:
        verdict = "IDIOSYNCRATIC"
        why = (f"fell {abs(rel):.0%} harder than {sec} peers with no red flag "
               f"in the numbers -- find the reason before buying")
    elif len(ambers) >= 2:
        verdict = "WATCH"
        why = "multiple soft signals"
    elif sector_wide:
        verdict = "FEAR (sector-wide)"
        why = f"moved with the sector ({sec} median {sec_dd:+.0%})"
    elif not flags and dd < -0.15:
        verdict = "UNEXPLAINED"
        why = "business checks out, peers do not explain it -- go read the news"
    elif ambers:
        verdict = "WATCH"
        why = ambers[0][1]
    else:
        verdict = "FEAR"
        why = "no red flag in the financials"

    return {"ticker": t, "price": last, "dd": dd, "sector": sec,
            "sector_dd": sec_dd, "rel": rel, "verdict": verdict, "why": why,
            "flags": flags, "notes": notes, "rev_dir": rev_dir,
            "rev_chg": rev_chg}


def main() -> None:
    tickers = [a.upper() for a in sys.argv[1:]]
    if not tickers:
        print(__doc__)
        return
    for t in tickers:
        a = assess(t)
        if "error" in a:
            print(f"{t}: {a['error']}")
            continue
        print("=" * 68)
        rel = ("n/a" if a["rel"] is None else
               f"{a['rel']:+.0%} vs {a['sector']} peers (median {a['sector_dd']:+.0%})")
        print(f"{t}  {a['price']:.2f}   drawdown {a['dd']:+.0%}   {rel}")
        print(f"  VERDICT: {a['verdict']}  --  {a['why']}")
        print(f"  revenue: {a['rev_dir']}"
              + (f", {a['rev_chg']:+.1%} QoQ" if a["rev_chg"] is not None else ""))
        if a["flags"]:
            for sev, name, detail in a["flags"]:
                print(f"    [{sev:<5}] {name:<32} {detail}")
        else:
            print("    no flags raised")
        for nt in a.get("notes", []):
            print(f"    [note ] {nt}")
    print("\nUNEXPLAINED is not a pass -- it means the cause is real and is not")
    print("in the statements yet (guidance, capital allocation, regulation).")
    print("FEAR means 'no red flag found', never 'safe'. Broken companies")
    print("delist, so any survivor-weighted sample under-counts them.")


if __name__ == "__main__":
    main()
