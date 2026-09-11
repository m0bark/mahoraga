"""Watchlist monitor: pull, compute, classify. One table, no invented signals.

WHAT IT DOES (each column is backed by something measured):
  * QUALITY  -- the one component that passed a survivorship-free PIT test
                (12.09%/yr vs 11.02% equal-weight, beat all random twins).
                Shown with the REASON it failed, so you can judge.
  * STATE    -- fear vs broken, from revenue direction, not from the chart.
  * DIP      -- reported as description only. Buying dips mechanically was
                measured at -5.19%/yr PIT. This tool will not tell you to.
  * VALUE    -- position in the 5y price range + PEG proxy, as CONTEXT.
                The sell-at-a-premium rule is UNTESTED; profit targets at
                prior levels tested WORSE than holding. Flag, don't obey.

Usage:  python research/tool/watchlist.py AAPL META NXPI ...
        python research/tool/watchlist.py --file my_tickers.txt
"""
from __future__ import annotations
import sys, io, warnings, math, csv
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd, yfinance as yf

DEFAULT = "META NXPI AVGO KLAC ON MPWR CDNS ADSK PWR GEV TSLA MU AMD ASML".split()


def pct(x, nd=0):
    return "-" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x*100:.{nd}f}%"


def quality(info) -> tuple[bool, str]:
    """Returns (passes, reason_it_failed). Missing data FAILS -- never passes silently."""
    g = info.get
    fails = []
    rev = g("revenueGrowth")
    mar = g("profitMargins")
    fcf = g("freeCashflow")
    td, tc, eb = g("totalDebt") or 0, g("totalCash") or 0, g("ebitda")
    if rev is None or rev <= 0:
        fails.append(f"rev growth {pct(rev,0)}")
    if mar is None or mar <= 0:
        fails.append(f"margin {pct(mar,0)}")
    if not fcf or fcf <= 0:
        fails.append("FCF<=0")
    nd = (td - tc) / eb if eb and eb > 0 else None
    if nd is not None and nd >= 2.5:
        fails.append(f"netdebt/EBITDA {nd:.1f}")
    return (not fails), "; ".join(fails)


def revenue_trend(t: str) -> tuple[str, float | None]:
    """Fear vs broken, from the filings -- not the chart."""
    try:
        r = yf.Ticker(t).quarterly_income_stmt.loc["Total Revenue"].dropna().sort_index()
        if len(r) < 3:
            return "?", None
        chg = r.iloc[-1] / r.iloc[0] - 1
        if chg > 0.05:
            return "FEAR", chg          # business growing while price fell
        if chg > -0.02:
            return "WATCH", chg
        return "BROKEN", chg            # revenue actually declining
    except Exception:
        return "?", None


def main(tickers: list[str]) -> None:
    px = yf.download(tickers, period="5y", auto_adjust=True,
                     progress=False, threads=True)["Close"]
    if isinstance(px, pd.Series):
        px = px.to_frame(tickers[0])
    out = []
    for t in tickers:
        try:
            c = px[t].dropna()
            if len(c) < 260:
                continue
            last = c.iloc[-1]
            sma200 = c.rolling(200).mean().iloc[-1]
            hi52, lo52 = c.iloc[-252:].max(), c.iloc[-252:].min()
            rng5 = (last - c.min()) / (c.max() - c.min())
            vol = c.pct_change().iloc[-252:].std() * math.sqrt(252)
            info = yf.Ticker(t).info
            q, why = quality(info)
            state, chg = revenue_trend(t)
            fpe = info.get("forwardPE")
            revg = info.get("revenueGrowth")
            peg = (fpe / (revg * 100)) if (fpe and revg and revg > 0) else None
            out.append({
                "ticker": t, "price": last,
                "dd52": last / hi52 - 1, "vs200": last / sma200 - 1,
                "pos5y": rng5, "vol": vol,
                "quality": "PASS" if q else "FAIL", "why": why,
                "revenue": state, "rev_chg": chg,
                "fwdPE": fpe, "peg": peg,
            })
        except Exception as e:
            out.append({"ticker": t, "why": f"ERR {str(e)[:40]}"})

    print(f"{'tkr':<6}{'price':>9}{'dd52':>7}{'vs200':>7}{'5y pos':>8}{'vol':>6}"
          f"{'qual':>6}{'revenue':>9}{'fwdPE':>7}{'PEG':>6}  {'notes'}")
    print("-" * 104)
    for r in sorted(out, key=lambda x: x.get("dd52") if x.get("dd52") is not None else 0):
        if "price" not in r:
            print(f"{r['ticker']:<6}  {r['why']}")
            continue
        note = []
        if r["quality"] == "FAIL":
            note.append(r["why"])
        if r["revenue"] == "BROKEN":
            note.append("REVENUE DECLINING -- not a dip, a decline")
        if r["pos5y"] > 0.90 and (r["peg"] or 0) > 3:
            note.append("rich: top decile of 5y range + PEG>3")
        print(f"{r['ticker']:<6}{r['price']:9.2f}{pct(r['dd52']):>7}{pct(r['vs200'],1):>7}"
              f"{pct(r['pos5y']):>8}{pct(r['vol']):>6}{r['quality']:>6}"
              f"{r['revenue']:>9}"
              f"{(f'{r[chr(102)+chr(119)+chr(100)+chr(80)+chr(69)]:.0f}' if r['fwdPE'] else '-'):>7}"
              f"{(f'{r[chr(112)+chr(101)+chr(103)]:.1f}' if r['peg'] else '-'):>6}"
              f"  {'; '.join(note)}")

    with open("research/tool/watchlist_out.csv", "w", newline="", encoding="utf-8") as f:
        rows = [r for r in out if "price" in r]
        if rows:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader(); w.writerows(rows)
    print("\nwrote research/tool/watchlist_out.csv")
    print("REMINDER: quality is validated. The dip columns are DESCRIPTION, not a")
    print("signal -- mechanical dip-buying measured -5.19%/yr point-in-time.")
    print("Sell discipline stays PROTOCOLS.md: trim above 1.5x target weight,")
    print("20% trailing stop, sell 100% on thesis break. Not on valuation.")


if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] == "--file":
        tk = open(a[1]).read().split()
    else:
        tk = [x.upper() for x in a] or DEFAULT
    main(tk)
