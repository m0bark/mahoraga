"""Point-in-time fundamentals from SEC XBRL. Free. No subscription.

    python research/sheet/sec_pit.py --ciks       # map tickers -> CIK
    python research/sheet/sec_pit.py --fetch      # pull companyfacts (~10 min)
    python research/sheet/sec_pit.py --panel      # build the PIT panel
    python research/sheet/sec_pit.py --all

WHY THIS MATTERS MORE THAN ANYTHING ELSE HERE
The RATE score has never been backtested, and the reason given was always the
same: yfinance reports only TODAY's P/E and margins, so scoring 2015 with 2026
accounts is look-ahead. Paid vendors sell point-in-time fundamentals; the SEC
gives them away.

data.sec.gov/api/xbrl/companyfacts/CIK##########.json returns every value a
company has ever reported, and crucially each carries a **filed** date -- the
day that number actually became public. Filter on filed <= d and you have
exactly what an investor could have known on date d, with no hindsight at all.

WHAT THIS FIXES
  * RATE becomes backtestable for the first time in this project
  * restatements are handled correctly: the ORIGINAL filing is used, not the
    later corrected one, because the original is what you would have traded on
  * reporting lag is real, not assumed -- a quarter ending 2026-07-26 was not
    public until 2026-08-26, a month later, and using the period-end date
    would hand you a month of free foresight

RATE LIMIT
SEC asks for a real User-Agent with contact details and caps you near 10
requests/second. This runs single-threaded with a small delay and identifies
itself properly. Do not raise the rate; they will block the IP.
"""
from __future__ import annotations

import gzip
import io
import json
import os
import sys
import time
import urllib.request
import warnings

_OUT = io.TextIOWrapper(open(sys.stdout.fileno(), "wb", closefd=False),
                        encoding="utf-8", errors="replace")


def say(*a) -> None:
    print(*a, file=_OUT)
    _OUT.flush()


warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "sec_raw")
CIKS = os.path.join(HERE, "sec_ciks.csv")
PANEL = os.path.join(HERE, "cache_long", "pit_fundamentals.csv")
UA = "mahoraga-research m0ba.c0ffe@gmail.com"
DELAY = 0.12                      # ~8 req/s, inside the SEC's stated limit

# the concepts the RATE score needs, with fallbacks -- XBRL tagging is not
# uniform, so each metric lists every tag companies actually use for it
WANT = {
    "revenue": ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax",
                "RevenueFromContractWithCustomerIncludingAssessedTax",
                "SalesRevenueNet"],
    "net_income": ["NetIncomeLoss", "ProfitLoss"],
    "assets": ["Assets"],
    "liabilities": ["Liabilities"],
    "equity": ["StockholdersEquity",
               "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"],
    "cash": ["CashAndCashEquivalentsAtCarryingValue"],
    "debt_lt": ["LongTermDebtNoncurrent", "LongTermDebt"],
    "op_income": ["OperatingIncomeLoss"],
    "gross_profit": ["GrossProfit"],
    "cfo": ["NetCashProvidedByUsedInOperatingActivities"],
    "capex": ["PaymentsToAcquirePropertyPlantAndEquipment"],
    "shares": ["CommonStockSharesOutstanding", "WeightedAverageNumberOfSharesOutstandingBasic",
               "dei:EntityCommonStockSharesOutstanding"],
    "current_assets": ["AssetsCurrent"],
    "current_liabilities": ["LiabilitiesCurrent"],
}


def get(url: str, tries: int = 3):
    h = {"User-Agent": UA, "Accept-Encoding": "gzip, deflate"}
    for k in range(tries):
        try:
            r = urllib.request.urlopen(urllib.request.Request(url, headers=h),
                                       timeout=45)
            raw = r.read()
            if raw[:2] == b"\x1f\x8b":
                raw = gzip.decompress(raw)
            return raw
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            time.sleep(2 * (k + 1))
        except Exception:
            time.sleep(2 * (k + 1))
    return None


def build_ciks() -> None:
    raw = get("https://www.sec.gov/files/company_tickers.json")
    if not raw:
        say("could not fetch the SEC ticker map")
        return
    m = json.loads(raw.decode())
    t2c = {}
    for v in m.values():
        t2c[str(v["ticker"]).upper()] = int(v["cik_str"])
    u = pd.read_csv(os.path.join(HERE, "sp500.csv"))
    u["cik"] = u["symbol"].str.upper().map(t2c)
    # BRK-B style tickers are BRK.B at the SEC
    miss = u["cik"].isna()
    u.loc[miss, "cik"] = (u.loc[miss, "symbol"].str.replace("-", ".", regex=False)
                          .str.upper().map(t2c))
    u[["symbol", "cik"]].to_csv(CIKS, index=False)
    say(f"mapped {int(u['cik'].notna().sum())}/{len(u)} tickers to a CIK")
    if u["cik"].isna().any():
        say(f"  unmapped: {list(u.loc[u['cik'].isna(), 'symbol'])[:12]}")


def fetch() -> None:
    if not os.path.exists(CIKS):
        build_ciks()
    c = pd.read_csv(CIKS).dropna(subset=["cik"])
    os.makedirs(RAW, exist_ok=True)
    todo = [(r.symbol, int(r.cik)) for r in c.itertuples()
            if not os.path.exists(os.path.join(RAW, f"{r.symbol}.json"))]
    say(f"{len(c)} companies, {len(todo)} still to fetch")
    for i, (sym, cik) in enumerate(todo, 1):
        raw = get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json")
        if raw:
            # store only what the panel needs; the full files are ~2-20 MB each
            try:
                d = json.loads(raw.decode("utf-8", "ignore"))
                keep = {"entityName": d.get("entityName"), "facts": {}}
                g = d.get("facts", {}).get("us-gaap", {})
                for metric, tags in WANT.items():
                    for t in tags:
                        if t in g:
                            keep["facts"][metric] = g[t]["units"]
                            break
                json.dump(keep, open(os.path.join(RAW, f"{sym}.json"), "w"))
            except Exception as e:
                say(f"  {sym}: parse failed ({type(e).__name__})")
        if i % 50 == 0:
            say(f"  {i}/{len(todo)}")
        time.sleep(DELAY)
    say(f"raw facts in {RAW}")


def panel() -> None:
    """One row per (symbol, filed date) with the numbers public on that day."""
    files = [f for f in os.listdir(RAW) if f.endswith(".json")] \
        if os.path.isdir(RAW) else []
    if not files:
        say("no raw facts -- run --fetch first")
        return
    rows = []
    for f in files:
        sym = f[:-5]
        try:
            d = json.load(open(os.path.join(RAW, f)))
        except Exception:
            continue
        recs = {}
        for metric, units in d.get("facts", {}).items():
            key = "USD" if "USD" in units else ("shares" if "shares" in units
                                                else next(iter(units), None))
            if key is None:
                continue
            for x in units[key]:
                if x.get("form") not in ("10-K", "10-Q") or "filed" not in x:
                    continue
                # ORIGINAL filing wins: a restatement filed later is not what
                # you could have acted on at the time
                k = (x["filed"], x.get("fp", ""), x.get("fy", ""))
                recs.setdefault(k, {})
                if metric not in recs[k]:
                    recs[k][metric] = x["val"]
                    recs[k]["_end"] = x.get("end")
        for (filed, fp, fy), vals in recs.items():
            vals.update({"symbol": sym, "filed": filed, "fp": fp, "fy": fy})
            rows.append(vals)
    p = pd.DataFrame(rows)
    if p.empty:
        say("nothing parsed")
        return
    p["filed"] = pd.to_datetime(p["filed"], errors="coerce")
    p = p.dropna(subset=["filed"]).sort_values(["symbol", "filed"])
    os.makedirs(os.path.dirname(PANEL), exist_ok=True)
    p.to_csv(PANEL, index=False)
    have = [c for c in WANT if c in p.columns]
    say(f"PIT panel: {len(p):,} filings, {p['symbol'].nunique()} companies")
    say(f"  {p['filed'].min():%Y-%m-%d} .. {p['filed'].max():%Y-%m-%d}")
    say(f"  metrics present: {have}")
    cov = {c: f"{p[c].notna().mean()*100:.0f}%" for c in have}
    say(f"  coverage: {cov}")
    say(f"\nwrote {PANEL}")
    say("\nThis is what an investor could actually have known on each date.")
    say("RATE can now be backtested without look-ahead for the first time.")


if __name__ == "__main__":
    a = sys.argv[1:]
    if "--ciks" in a:
        build_ciks()
    elif "--fetch" in a:
        fetch()
    elif "--panel" in a:
        panel()
    else:
        build_ciks(); fetch(); panel()
