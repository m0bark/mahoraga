"""Reverse-split cash-out scanner (forced-flows family — structural).
Searches SEC EDGAR full-text search for Rule 13e-3 going-private filings
mentioning reverse stock splits: companies cashing out all holders below
the split threshold at a board-fixed price.

Each hit still requires READING THE FILING before acting:
(1) cash-out price vs market, (2) threshold and RATIO RANGE — always buy
below the range MINIMUM, (3) street-name treatment: some deals (e.g.
Cyanotech) pay RECORD holders only — broker-held shares get nothing
without a DRS transfer, (4) vote/expected effective date, (5) abandonment
language — boards can pull the split even after approval, (6) sector
screen. Safest entry is AFTER the ratio-fixing vote, below the threshold.

Run: .venv/Scripts/python.exe research/tenders/reverse_split_scan.py [days_back]
"""
from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request
from datetime import date, timedelta

FTS_URL = "https://efts.sec.gov/LATEST/search-index?{}"
UA = {"User-Agent": "personal-research-tool contact-via-edgar"}
QUERIES = [
    ('"reverse stock split"', ["SC 13E3"]),
    ('"reverse stock split" "cash in lieu"', ["PRE 14A", "DEF 14A"]),
]


def search(phrase: str, forms: list[str], days_back: int) -> list[dict]:
    start = (date.today() - timedelta(days=days_back)).isoformat()
    params = urllib.parse.urlencode({
        "q": phrase,
        "forms": ",".join(forms),
        "dateRange": "custom",
        "startdt": start,
        "enddt": date.today().isoformat(),
    })
    req = urllib.request.Request(FTS_URL.format(params), headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        payload = json.load(r)
    return payload.get("hits", {}).get("hits", [])


def main() -> None:
    days_back = int(sys.argv[1]) if len(sys.argv) > 1 else 90
    rows: dict[str, dict] = {}
    for phrase, forms in QUERIES:
        for h in search(phrase, forms, days_back):
            src = h["_source"]
            names = "; ".join(src.get("display_names", ["?"]))
            key = names.lower()
            row = rows.setdefault(key, {
                "names": names, "first": src["file_date"],
                "forms": set(), "cik": str(src.get("ciks", ["?"])[0]),
                "adsh": src.get("adsh", ""),
            })
            row["forms"].add(src.get("root_forms", ["?"])[0])
            if src["file_date"] < row["first"]:
                row["first"] = src["file_date"]

    if not rows:
        print(f"no reverse-split going-private filings in the last "
              f"{days_back} days")
        return
    print(f"reverse-split cash-out candidates, last {days_back} days "
          f"(13E-3 = strongest signal):\n")
    for row in sorted(rows.values(), key=lambda r: r["first"], reverse=True):
        cik = row["cik"].lstrip("0")
        acc = row["adsh"].replace("-", "")
        forms = ",".join(sorted(row["forms"]))
        print(f"{row['first']}  [{forms:<16}] {row['names']}")
        print(f"    https://www.sec.gov/Archives/edgar/data/{cik}/{acc}")
    print(f"\n{len(rows)} distinct companies. 13E-3 filers are true "
          f"going-private deals; 14A-only hits need reading to confirm a "
          f"cash-out (many are routine splits with fractional-share cash). "
          f"NEVER buy at/above the ratio-range minimum threshold.")


if __name__ == "__main__":
    main()
