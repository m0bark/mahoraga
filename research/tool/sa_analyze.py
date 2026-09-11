"""Click-to-run: open StockAnalysis for a ticker, you copy, it analyzes.

    python research/tool/sa_analyze.py NVDA

Flow:
  1. opens stockanalysis.com/stocks/NVDA/financials/ in your browser
  2. you select the table and hit Ctrl+C  (normal use of your own account)
  3. press Enter here -- it reads the clipboard, parses, and analyzes
  4. saves to research/tool/library/NVDA.json so the data accumulates

WHY YOU DO THE COPYING: StockAnalysis has no API and does not permit
programmatic redistribution of the data it licenses. A bot that harvests
pages breaks that and risks your account. You reading your own subscription
in your own browser is just browsing. This script never logs in, never
touches your password, and never fetches a page itself.

Analysis run on the pasted numbers:
  * Piotroski-style legs (the documented +7.5%/yr separator WITHIN a
    price-selected group -- Piotroski 2000)
  * revenue / margin / FCF trend  -> the FEAR vs BROKEN call
  * leverage and liquidity
  * price context pulled free from yfinance (drawdown, 200d, 5y position)
Every leg prints its inputs so you can audit it rather than trust it.
"""
from __future__ import annotations

import io
import json
import os
import re
import subprocess
import sys
import webbrowser

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

LIB = "research/tool/library"
PAGES = {
    "financials": "https://stockanalysis.com/stocks/{t}/financials/",
    "ratios": "https://stockanalysis.com/stocks/{t}/financials/ratios/",
    "balance": "https://stockanalysis.com/stocks/{t}/financials/balance-sheet/",
    "cashflow": "https://stockanalysis.com/stocks/{t}/financials/cash-flow-statement/",
}
MULT = {"K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12}


# ----------------------------------------------------------------- clipboard
def read_clipboard() -> str:
    try:
        import tkinter
        r = tkinter.Tk()
        r.withdraw()
        s = r.clipboard_get()
        r.destroy()
        if s.strip():
            return s
    except Exception:
        pass
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", "Get-Clipboard"],
                             capture_output=True, timeout=20)
        return out.stdout.decode("utf-8", "replace")
    except Exception:
        return ""


# -------------------------------------------------------------------- parsing
def to_num(s: str):
    s = str(s).strip().replace(",", "").replace("$", "")
    if s in ("", "-", "--", "n/a", "N/A", "Upgrade"):
        return None
    neg = s.startswith("(") and s.endswith(")")
    if neg:
        s = s[1:-1]
    pctv = s.endswith("%")
    if pctv:
        s = s[:-1]
    m = 1.0
    if s and s[-1].upper() in MULT:
        m = MULT[s[-1].upper()]
        s = s[:-1]
    try:
        v = float(s) * m
    except ValueError:
        return None
    if neg:
        v = -v
    return v / 100 if pctv else v


def parse_table(text: str) -> dict[str, list]:
    """StockAnalysis tables copy as tab- or multi-space-separated rows:
    a header of fiscal years, then 'Metric  v1  v2  ...'."""
    rows: dict[str, list] = {}
    years: list[str] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        cells = re.split(r"\t|\s{2,}", line.strip())
        cells = [c.strip() for c in cells if c.strip()]
        if len(cells) < 2:
            continue
        head = cells[0]
        vals = cells[1:]
        if not years and sum(bool(re.fullmatch(r"(FY\s*)?(19|20)\d{2}", v)) for v in vals) >= 2:
            years = vals
            continue
        nums = [to_num(v) for v in vals]
        if sum(v is not None for v in nums) >= 2:
            rows.setdefault(head, nums)
    rows["__years__"] = years
    return rows


def find(rows: dict, *names):
    """Fetch a row by fuzzy label match; returns list oldest->newest."""
    keys = list(rows.keys())
    for want in names:
        w = want.lower()
        for k in keys:
            if k.lower() == w:
                return _oriented(rows[k], rows.get("__years__"))
    for want in names:
        w = want.lower()
        for k in keys:
            if w in k.lower():
                return _oriented(rows[k], rows.get("__years__"))
    return None


def _oriented(vals, years):
    """StockAnalysis shows newest-first; flip so index -1 is the latest."""
    if years and len(years) >= 2:
        y = [int(re.sub(r"\D", "", x) or 0) for x in years]
        if len(y) >= 2 and y[0] > y[-1]:
            return list(reversed(vals))
    return list(reversed(vals))


# ------------------------------------------------------------------- analysis
def analyze(t: str, rows: dict) -> dict:
    rev = find(rows, "Revenue", "Total Revenue")
    ni = find(rows, "Net Income")
    fcf = find(rows, "Free Cash Flow")
    ocf = find(rows, "Operating Cash Flow", "Cash from Operations")
    gm = find(rows, "Gross Margin")
    assets = find(rows, "Total Assets")
    de = find(rows, "Debt / Equity", "Debt/Equity", "Total Debt")
    cr = find(rows, "Current Ratio")
    sh = find(rows, "Shares Outstanding", "Shares Change")

    def last(x):
        if not x:
            return None
        v = [i for i in x if i is not None]
        return v[-1] if v else None

    def prev(x):
        if not x:
            return None
        v = [i for i in x if i is not None]
        return v[-2] if len(v) >= 2 else None

    def roa(i):
        if rev and ni and assets:
            try:
                if ni[i] is not None and assets[i]:
                    return ni[i] / assets[i]
            except Exception:
                return None
        return None

    legs = []

    def leg(name, cond, detail):
        legs.append({"leg": name, "pass": cond, "detail": detail})

    ni_l, ni_p = last(ni), prev(ni)
    ocf_l = last(ocf)
    roa_l = roa(-1) if (ni and assets) else None
    roa_p = roa(-2) if (ni and assets and len(ni) > 1) else None
    gm_l, gm_p = last(gm), prev(gm)
    cr_l = last(cr)
    sh_l, sh_p = last(sh), prev(sh)
    rev_l, rev_p = last(rev), prev(rev)
    fcf_l = last(fcf)

    leg("profitable", (ni_l or 0) > 0, f"net income {fmt(ni_l)}")
    leg("operating cash flow > 0", (ocf_l or 0) > 0, f"OCF {fmt(ocf_l)}")
    leg("FCF > 0", (fcf_l or 0) > 0, f"FCF {fmt(fcf_l)}")
    if roa_l is not None and roa_p is not None:
        leg("ROA improving", roa_l > roa_p, f"{roa_l:.1%} vs {roa_p:.1%}")
    if ocf_l is not None and ni_l is not None:
        leg("accruals ok (OCF > NI)", ocf_l > ni_l,
            f"OCF {fmt(ocf_l)} vs NI {fmt(ni_l)}")
    if gm_l is not None and gm_p is not None:
        leg("gross margin improving", gm_l > gm_p, f"{pctf(gm_l)} vs {pctf(gm_p)}")
    if cr_l is not None:
        leg("current ratio > 1", cr_l > 1, f"{cr_l:.2f}")
    if sh_l is not None and sh_p is not None:
        leg("no dilution", sh_l <= sh_p * 1.01, f"{fmt(sh_p)} -> {fmt(sh_l)}")
    if rev_l is not None and rev_p is not None:
        leg("revenue growing", rev_l > rev_p, f"{fmt(rev_p)} -> {fmt(rev_l)}")

    scored = [x for x in legs if x["pass"] is not None]
    score = sum(1 for x in scored if x["pass"])

    state = "?"
    if rev and len([x for x in rev if x is not None]) >= 2:
        v = [x for x in rev if x is not None]
        chg = v[-1] / v[-2] - 1 if v[-2] else None
        if chg is not None:
            state = "FEAR (growing)" if chg > 0.05 else (
                "WATCH" if chg > -0.02 else "BROKEN (revenue declining)")

    cagr = None
    if rev:
        v = [x for x in rev if x is not None and x > 0]
        if len(v) >= 3:
            cagr = (v[-1] / v[0]) ** (1 / (len(v) - 1)) - 1

    return {"ticker": t, "score": score, "of": len(scored), "legs": legs,
            "state": state, "rev_cagr": cagr, "years": rows.get("__years__", []),
            "rows_seen": [k for k in rows if k != "__years__"]}


def fmt(v):
    if v is None:
        return "-"
    a = abs(v)
    for s, m in (("T", 1e12), ("B", 1e9), ("M", 1e6), ("K", 1e3)):
        if a >= m:
            return f"{v/m:.2f}{s}"
    return f"{v:,.2f}"


def pctf(v):
    return "-" if v is None else (f"{v:.1%}" if abs(v) < 5 else f"{v:.1f}%")


def price_context(t: str) -> str:
    try:
        import warnings
        warnings.filterwarnings("ignore")
        import yfinance as yf
        c = yf.Ticker(t).history(period="5y")["Close"].dropna()
        if len(c) < 260:
            return "  price context: not enough history"
        last = c.iloc[-1]
        return ("  price {:.2f} | 52w drawdown {:+.0%} | vs 200d {:+.1%} | "
                "5y range pos {:.0%}").format(
            last, last / c.iloc[-252:].max() - 1,
            last / c.rolling(200).mean().iloc[-1] - 1,
            (last - c.min()) / (c.max() - c.min()))
    except Exception as e:
        return f"  price context unavailable ({str(e)[:40]})"


# ----------------------------------------------------------------------- main
def main() -> None:
    t = (sys.argv[1] if len(sys.argv) > 1 else input("ticker: ")).strip().upper()
    if not re.fullmatch(r"[A-Z.\-]{1,8}", t):
        print("bad ticker"); return
    page = sys.argv[2] if len(sys.argv) > 2 else "financials"
    url = PAGES.get(page, PAGES["financials"]).format(t=t)

    print(f"opening {url}")
    webbrowser.open(url)
    print("\n  1. select the financials table on the page")
    print("  2. Ctrl+C to copy")
    print("  3. come back here and press Enter")
    print("  (tip: also try  ... sa_analyze.py {} ratios|balance|cashflow)".format(t))
    input("\n[Enter when copied] ")

    text = read_clipboard()
    if not text.strip():
        print("clipboard empty -- copy the table and re-run"); return
    rows = parse_table(text)
    data = {k: v for k, v in rows.items() if k != "__years__"}
    if len(data) < 3:
        print(f"parsed only {len(data)} rows -- did the whole table get copied?")
        print("first 200 chars of clipboard:\n", text[:200])
        return

    a = analyze(t, rows)
    print("\n" + "=" * 66)
    print(f"{t}   fundamental score {a['score']}/{a['of']}   "
          f"revenue: {a['state']}")
    if a["rev_cagr"] is not None:
        print(f"  revenue CAGR over pasted period: {a['rev_cagr']:+.1%}/yr "
              f"({len(a['years'])} periods)")
    print(price_context(t))
    print("-" * 66)
    for leg in a["legs"]:
        mark = "PASS" if leg["pass"] else "fail"
        print(f"  [{mark}] {leg['leg']:<26} {leg['detail']}")
    print("-" * 66)
    print(f"  parsed {len(a['rows_seen'])} line items: "
          f"{', '.join(a['rows_seen'][:8])}"
          f"{' ...' if len(a['rows_seen']) > 8 else ''}")

    os.makedirs(LIB, exist_ok=True)
    path = os.path.join(LIB, f"{t}.json")
    blob = {"analysis": a, "raw": {k: v for k, v in rows.items()}}
    if os.path.exists(path):
        try:
            old = json.load(open(path, encoding="utf-8"))
            blob["raw"] = {**old.get("raw", {}), **blob["raw"]}
        except Exception:
            pass
    json.dump(blob, open(path, "w", encoding="utf-8"), indent=1, default=str)
    print(f"\nsaved {path}  (re-run with ratios/balance/cashflow to enrich it)")
    print("\nNOTE: the score is a SEPARATOR, not a buy signal. Piotroski's")
    print("+7.5%/yr was measured WITHIN a price-selected group, long-short,")
    print("cross-sectional. It has not been validated in this project yet --")
    print("that is what the pending QC run is for.")


if __name__ == "__main__":
    main()
