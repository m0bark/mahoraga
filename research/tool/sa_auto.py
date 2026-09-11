"""Fully automatic: give it tickers, it fetches StockAnalysis and analyzes.

    python research/tool/sa_auto.py NVDA META NXPI
    python research/tool/sa_auto.py --file research/tool/sa_tickers.txt

No clipboard, no clicking, no login, no password. It fetches the public
pages, parses the server-rendered tables, scores the fundamentals, and
saves each name to research/tool/library/<TICKER>.json.

Terms: StockAnalysis's Terms of Use contain no prohibition on automated
access. The one restriction is on republishing their content in full --
this keeps everything local and republishes nothing. It also rate-limits
itself (default 1.5s between requests) because hammering someone's server
is rude regardless of what the terms permit.

Pro depth: logged-out pages carry recent years. If you want the 10-40 year
history your Pro plan unlocks, export the cookie once:
    set SA_COOKIE=<the cookie string from your logged-in browser>
and it will be sent with the requests. Optional; everything works without.
"""
from __future__ import annotations

import gzip
import html as htmlmod
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

LIB = "research/tool/library"
DELAY = 1.5
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
PAGES = {
    "income": "https://stockanalysis.com/stocks/{t}/financials/",
    "balance": "https://stockanalysis.com/stocks/{t}/financials/balance-sheet/",
    "cashflow": "https://stockanalysis.com/stocks/{t}/financials/cash-flow-statement/",
    "ratios": "https://stockanalysis.com/stocks/{t}/financials/ratios/",
}
MULT = {"K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12}


# -------------------------------------------------------------------- fetch
def fetch(url: str) -> str | None:
    h = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"}
    ck = os.environ.get("SA_COOKIE")
    if ck:
        h["Cookie"] = ck
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers=h)
            raw = urllib.request.urlopen(req, timeout=30).read()
            if raw[:2] == b"\x1f\x8b":
                raw = gzip.decompress(raw)
            return raw.decode("utf-8", "ignore")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            time.sleep(2 * (attempt + 1))
        except Exception:
            time.sleep(2 * (attempt + 1))
    return None


# -------------------------------------------------------------------- parse
def strip_tags(s: str) -> str:
    return re.sub(r"\s+", " ", htmlmod.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def to_num(s: str):
    s = str(s).strip().replace(",", "").replace("$", "")
    if s in ("", "-", "--", "n/a", "N/A", "Upgrade"):
        return None
    neg = s.startswith("(") and s.endswith(")")
    if neg:
        s = s[1:-1]
    if s.startswith("-"):
        neg, s = True, s[1:]
    ispct = s.endswith("%")
    if ispct:
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
    return v / 100 if ispct else v


def parse_tables(html: str) -> dict:
    """Pull every <table>; keep rows whose label maps to a metric.
    Returns {label: [oldest..newest]} plus __years__."""
    rows: dict[str, list] = {}
    years: list[str] = []
    for tbl in re.findall(r"<table.*?</table>", html, re.S | re.I):
        trs = re.findall(r"<tr.*?</tr>", tbl, re.S | re.I)
        local_years: list[str] = []
        body: list[tuple[str, list]] = []
        for tr in trs:
            cells = [strip_tags(c) for c in
                     re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S | re.I)]
            cells = [c for c in cells if c != ""]
            if len(cells) < 2:
                continue
            yrs = [c for c in cells if re.fullmatch(r"(FY\s*)?(19|20)\d{2}", c)]
            if len(yrs) >= 2 and not local_years:
                local_years = yrs
                continue
            label, vals = cells[0], cells[1:]
            nums = [to_num(v) for v in vals]
            if sum(x is not None for x in nums) >= 2:
                body.append((label, nums))
        if not body:
            continue
        if local_years and not years:
            years = local_years
        newest_first = True
        if local_years:
            y = [int(re.sub(r"\D", "", x)) for x in local_years]
            newest_first = y[0] >= y[-1]
        for label, nums in body:
            if label not in rows:
                rows[label] = list(reversed(nums)) if newest_first else nums
    rows["__years__"] = years
    return rows


def find(rows: dict, *names):
    keys = [k for k in rows if k != "__years__"]
    for want in names:
        for k in keys:
            if k.lower() == want.lower():
                return rows[k]
    for want in names:
        for k in keys:
            if want.lower() in k.lower():
                return rows[k]
    return None


# ----------------------------------------------------------------- analysis
def fmt(v):
    if v is None:
        return "-"
    a = abs(v)
    for s, m in (("T", 1e12), ("B", 1e9), ("M", 1e6), ("K", 1e3)):
        if a >= m:
            return f"{v/m:.2f}{s}"
    return f"{v:,.2f}"


def analyze(t: str, rows: dict) -> dict:
    rev = find(rows, "Revenue", "Total Revenue")
    ni = find(rows, "Net Income")
    fcf = find(rows, "Free Cash Flow")
    ocf = find(rows, "Operating Cash Flow", "Cash from Operations")
    gm = find(rows, "Gross Margin")
    assets = find(rows, "Total Assets")
    cr = find(rows, "Current Ratio")
    sh = find(rows, "Shares Outstanding", "Shares Change")
    de = find(rows, "Debt / Equity", "Debt/Equity")

    def L(x, i=-1):
        if not x:
            return None
        v = [a for a in x if a is not None]
        return v[i] if len(v) >= abs(i) else None

    def roa(i):
        if ni and assets:
            n, a = L(ni, i), L(assets, i)
            if n is not None and a:
                return n / a
        return None

    legs = []

    def leg(name, cond, detail):
        legs.append({"leg": name, "pass": bool(cond), "detail": detail})

    ni_l, ocf_l, fcf_l = L(ni), L(ocf), L(fcf)
    ra, rp = roa(-1), roa(-2)
    gm_l, gm_p = L(gm), L(gm, -2)
    rev_l, rev_p = L(rev), L(rev, -2)
    sh_l, sh_p = L(sh), L(sh, -2)
    cr_l, de_l = L(cr), L(de)

    if ni_l is not None:
        leg("profitable", ni_l > 0, f"net income {fmt(ni_l)}")
    if ocf_l is not None:
        leg("operating cash flow > 0", ocf_l > 0, f"OCF {fmt(ocf_l)}")
    if fcf_l is not None:
        leg("FCF > 0", fcf_l > 0, f"FCF {fmt(fcf_l)}")
    if ra is not None and rp is not None:
        leg("ROA improving", ra > rp, f"{ra:.1%} vs {rp:.1%}")
    if ocf_l is not None and ni_l is not None:
        leg("accruals ok (OCF > NI)", ocf_l > ni_l, f"{fmt(ocf_l)} vs {fmt(ni_l)}")
    if gm_l is not None and gm_p is not None:
        leg("gross margin improving", gm_l > gm_p, f"{gm_l:.1%} vs {gm_p:.1%}")
    if cr_l is not None:
        leg("current ratio > 1", cr_l > 1, f"{cr_l:.2f}")
    if de_l is not None:
        leg("debt/equity < 1", de_l < 1, f"{de_l:.2f}")
    if sh_l is not None and sh_p is not None:
        leg("no dilution", sh_l <= sh_p * 1.01, f"{fmt(sh_p)} -> {fmt(sh_l)}")
    if rev_l is not None and rev_p is not None:
        leg("revenue growing", rev_l > rev_p, f"{fmt(rev_p)} -> {fmt(rev_l)}")

    score = sum(1 for x in legs if x["pass"])
    state = "?"
    if rev_l is not None and rev_p:
        chg = rev_l / rev_p - 1
        state = ("FEAR (growing)" if chg > 0.05 else
                 "WATCH" if chg > -0.02 else "BROKEN (revenue declining)")
    cagr = None
    if rev:
        v = [x for x in rev if x is not None and x > 0]
        if len(v) >= 3:
            cagr = (v[-1] / v[0]) ** (1 / (len(v) - 1)) - 1
    return {"ticker": t, "score": score, "of": len(legs), "legs": legs,
            "state": state, "rev_cagr": cagr, "years": rows.get("__years__", []),
            "n_items": len([k for k in rows if k != "__years__"])}


# --------------------------------------------------------------------- main
def run(t: str) -> dict | None:
    merged: dict = {}
    got = []
    for name, tmpl in PAGES.items():
        html = fetch(tmpl.format(t=t.lower()))
        time.sleep(DELAY)
        if not html:
            continue
        r = parse_tables(html)
        if len([k for k in r if k != "__years__"]) >= 2:
            got.append(name)
            for k, v in r.items():
                if k == "__years__":
                    merged.setdefault("__years__", v)
                else:
                    merged.setdefault(k, v)
    if not merged:
        print(f"{t:<7} no data")
        return None
    a = analyze(t, merged)
    a["pages"] = got
    # StockAnalysis reports currency figures in MILLIONS; fmt() is
    # unit-agnostic, so "192.88K" means 192,880 million = $192.88B.
    cg = "-" if a["rev_cagr"] is None else f"{a['rev_cagr']:+.1%}"
    pages = "+".join(got)
    print(f"{t:<7} score {a['score']}/{a['of']:<3} {a['state']:<26} "
          f"rev CAGR {cg:>7}  "
          f"[{a['n_items']} items, {len(a['years'])} yrs, {pages}]")
    os.makedirs(LIB, exist_ok=True)
    json.dump({"analysis": a, "raw": merged},
              open(os.path.join(LIB, f"{t}.json"), "w", encoding="utf-8"),
              indent=1, default=str)
    return a


def main() -> None:
    args = sys.argv[1:]
    if args and args[0] == "--file":
        tickers = open(args[1]).read().split()
    else:
        tickers = [a.upper() for a in args]
    if not tickers:
        print(__doc__)
        return
    detail = len(tickers) == 1
    print(f"fetching {len(tickers)} ticker(s), {DELAY}s apart\n")
    results = []
    for t in tickers:
        a = run(t)
        if a:
            results.append(a)
    if detail and results:
        a = results[0]
        print()
        for leg in a["legs"]:
            print(f"  [{'PASS' if leg['pass'] else 'fail'}] "
                  f"{leg['leg']:<26} {leg['detail']}")
    if len(results) > 1:
        print(f"\nranked by score:")
        for a in sorted(results, key=lambda x: -x["score"]):
            print(f"  {a['score']}/{a['of']}  {a['ticker']:<7}{a['state']}")
    print(f"\nsaved {len(results)} to {LIB}/")
    print("Currency figures are in MILLIONS as reported by StockAnalysis")
    print("(so '192.88K' means 192,880 million = $192.88B).")
    print("Score is a SEPARATOR, not a buy signal -- Piotroski's +7.5%/yr was")
    print("measured within a price-selected group, long-short. Not yet")
    print("validated here; that is what the pending QC run is for.")


if __name__ == "__main__":
    main()
