"""Odd-lot tender offer scanner (forced-flows family — structural, not
statistical). Searches SEC EDGAR full-text search for recent tender-offer
filings mentioning odd-lot provisions and lists them newest-first.

Each hit still requires READING THE FILING: confirm (1) an explicit
odd-lot priority clause, (2) tender price / range vs current market price,
(3) expiration date, (4) financing/minimum conditions. The edge only
exists when odd lots are accepted without proration AND market < tender
price by more than two commissions.

Run: .venv/Scripts/python.exe research/tenders/tender_scan.py [days_back]
"""
from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request
from datetime import date, timedelta

FTS_URL = "https://efts.sec.gov/LATEST/search-index?{}"
UA = {"User-Agent": "personal-research-tool contact-via-edgar"}
FORMS = ["SC TO-I", "SC TO-I/A", "SC TO-T", "SC 13E3"]
PHRASE = '"odd lot"'


def search(days_back: int) -> list[dict]:
    start = (date.today() - timedelta(days=days_back)).isoformat()
    params = urllib.parse.urlencode({
        "q": PHRASE,
        "forms": ",".join(FORMS),
        "dateRange": "custom",
        "startdt": start,
        "enddt": date.today().isoformat(),
    })
    req = urllib.request.Request(FTS_URL.format(params), headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        payload = json.load(r)
    return payload.get("hits", {}).get("hits", [])


def main() -> None:
    days_back = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    hits = search(days_back)
    if not hits:
        print(f"no tender filings mentioning {PHRASE} in the last "
              f"{days_back} days")
        return
    seen: set[str] = set()
    print(f"tender filings mentioning {PHRASE}, last {days_back} days "
          f"(newest first, deduped by company):\n")
    for h in sorted(hits, key=lambda x: x["_source"]["file_date"],
                    reverse=True):
        src = h["_source"]
        names = "; ".join(src.get("display_names", ["?"]))
        if names in seen:
            continue
        seen.add(names)
        adsh = src.get("adsh", "")
        acc = adsh.replace("-", "")
        cik = str(src.get("ciks", ["?"])[0]).lstrip("0")
        url = (f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc}"
               if cik != "?" else "(no link)")
        print(f"{src['file_date']}  {src.get('root_forms', ['?'])[0]:<9} "
              f"{names}")
        print(f"    {url}")
    print(f"\n{len(seen)} distinct companies. Read each filing before "
          f"acting; only explicit no-proration odd-lot clauses count.")


if __name__ == "__main__":
    main()
