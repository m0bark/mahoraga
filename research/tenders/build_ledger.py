"""Stage 1 of the pre-registered go-live gate: build the 36-month
reverse-split cash-out event universe from SEC EDGAR.

Gate (from forced_flows/SURVEY-2026-08-28.md, pre-registered):
  >=8 investable events, >=85% completion, >=$150 avg net at post-vote entry.

This stage answers the first number only: how many real deals existed.
Stage 2 reads each filing for cash-out price / threshold / dates.
"""
from __future__ import annotations
import json, urllib.parse, urllib.request, time, sys, io, csv
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

UA = {"User-Agent": "personal-research-tool contact-via-edgar"}
START, END = "2023-09-01", "2026-08-30"


def fts(q, forms, frm=0):
    p = urllib.parse.urlencode({"q": q, "forms": forms, "dateRange": "custom",
                                "startdt": START, "enddt": END, "from": frm})
    req = urllib.request.Request("https://efts.sec.gov/LATEST/search-index?" + p, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as f:
        return json.load(f)


def collect(q, forms):
    out, frm = [], 0
    while True:
        d = fts(q, forms, frm)
        hits = d.get("hits", {}).get("hits", [])
        out += hits
        total = d.get("hits", {}).get("total", {}).get("value", 0)
        frm += len(hits)
        if frm >= total or not hits:
            break
        time.sleep(0.3)
    return out


hits = collect('"reverse stock split"', "SC 13E3")
print(f"SC 13E3 filings mentioning a reverse stock split, {START}..{END}: {len(hits)}")

deals = defaultdict(lambda: {"filings": [], "names": "", "cik": ""})
for h in hits:
    s = h["_source"]
    cik = str(s.get("ciks", ["?"])[0])
    d = deals[cik]
    d["cik"], d["names"] = cik, "; ".join(s.get("display_names", ["?"]))
    d["filings"].append((s["file_date"], s.get("root_forms", ["?"])[0], s.get("adsh", "")))

print(f"distinct issuers: {len(deals)}\n")
rows = []
for cik, d in sorted(deals.items(), key=lambda kv: min(f[0] for f in kv[1]["filings"])):
    dates = sorted(f[0] for f in d["filings"])
    nm = d["names"]
    tick = nm.split("(")[1].split(")")[0] if "(" in nm else ""
    rows.append({"cik": cik, "name": nm.split("  (")[0], "ticker": tick,
                 "first_filing": dates[0], "last_filing": dates[-1],
                 "n_filings": len(dates)})
    print(f"{dates[0]}  {len(dates):2d} filings  {tick:<12s} {nm.split('  (')[0][:52]}")

with open("research/tenders/ledger_stage1.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    w.writeheader(); w.writerows(rows)
print(f"\nwrote research/tenders/ledger_stage1.csv ({len(rows)} issuers)")
