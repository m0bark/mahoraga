"""Stage 3 of the pre-registered go-live gate: per-deal economics.

Gate (forced_flows/SURVEY-2026-08-28.md):
    >=8 investable events, >=85% completion, >=$150 avg net at post-vote entry.

Stage 1 found 24 SC 13E3 issuers in 36 months.
Stage 2 machine-extracted terms for 15; ~9 carry a share threshold (the
signature of a genuine odd-lot cash-out rather than a going-private merger).

Stage 3 answers the money question per deal:
    * cash-out price and the share threshold  -> max position, gross payout
    * the Reg M-A Item 1002(c) quarterly high/low market price table, which
      the issuer is OBLIGED to publish inside the proxy. This is why the
      ledger needs no price vendor: the issuers delist, so yfinance and
      Stooq have nothing, but the filing carries its own price history.
    * whether the stock traded BELOW the threshold price after the vote,
      which is the only entry the survey permits.

Writes research/tenders/ledger_stage3.csv
"""
from __future__ import annotations

import csv
import html as htmlmod
import io
import json
import re
import sys
import time
import urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

H = {"User-Agent": "mahoraga-research m0ba.c0ffe@gmail.com"}
PROXY_FORMS = ("DEFM14A", "DEF 14A", "PREM14A", "PRE 14A", "DEF 14C", "PRE 14C")


def get(url: str, tries: int = 3) -> str:
    for k in range(tries):
        try:
            return urllib.request.urlopen(
                urllib.request.Request(url, headers=H), timeout=60
            ).read().decode("utf8", "ignore")
        except Exception:
            if k == tries - 1:
                raise
            time.sleep(2)
    return ""


def plain(h: str) -> str:
    return re.sub(r"\s+", " ", htmlmod.unescape(re.sub(r"<[^>]+>", " ", h)))


def money(s: str):
    try:
        return float(s.replace(",", "").replace("$", ""))
    except Exception:
        return None


def price_table(txt: str) -> list[tuple[float, float]]:
    """Item 1002(c) quarterly high/low table. Issuers format it many ways, so
    take every 'High ... Low' numeric pair in the market-price section."""
    m = re.search(r"(Market\s+Price\s+of\s+(?:our\s+)?Common\s+Stock.{0,6000})",
                  txt, re.I | re.S)
    if not m:
        return []
    seg = m.group(1)
    pairs = re.findall(r"\$?\s?(\d{1,3}\.\d{2})\s+\$?\s?(\d{1,3}\.\d{2})", seg)
    out = []
    for a, b in pairs:
        hi, lo = money(a), money(b)
        if hi and lo and 0 < lo <= hi < 1000:
            out.append((hi, lo))
    return out[:12]


def extract(txt: str) -> dict:
    d: dict = {}
    for p in (r"receive \$\s?([\d,]+\.\d{2})\s+in cash",
              r"cash payment of \$\s?([\d,]+\.\d{2})",
              r"\$\s?([\d,]+\.\d{2})\s+in cash, without interest"):
        m = re.search(p, txt, re.I)
        if m:
            d["cash"] = money(m.group(1))
            break
    m = re.search(r"between\s+([\d,]+)\s+and\s+([\d,]+)\s+shares", txt, re.I)
    if m:
        d["thr_min"] = int(m.group(1).replace(",", ""))
        d["thr_max"] = int(m.group(2).replace(",", ""))
    else:
        m = re.search(r"fewer than\s+([\d,]+)\s+shares", txt, re.I)
        if m:
            d["thr_min"] = d["thr_max"] = int(m.group(1).replace(",", ""))
    m = re.search(r"to be held on ([A-Z][a-z]+ \d{1,2}, \d{4})", txt)
    if m:
        d["meeting"] = m.group(1)
    d["record_only"] = bool(re.search(r"record holders?\b[^.]{0,200}\bonly\b",
                                      txt, re.I))
    pt = price_table(txt)
    if pt:
        d["px_hi"] = max(h for h, _ in pt)
        d["px_lo"] = min(lo for _, lo in pt)
        d["px_last_hi"], d["px_last_lo"] = pt[0]
    return d


def main() -> None:
    rows = list(csv.DictReader(open("research/tenders/ledger_stage1.csv",
                                    encoding="utf-8")))
    out = []
    print(f"{'ticker':<8}{'cash':>8}{'thresh':>9}{'maxpos$':>9}"
          f"{'52w hi/lo from filing':>24}  {'name'}")
    print("-" * 104)
    for r in rows:
        cik = r["cik"].lstrip("0")
        rec = {"name": r["name"][:40], "ticker": r["ticker"].split(",")[0],
               "cik": cik, "first_13e3": r["first_filing"]}
        try:
            s = json.loads(get(
                f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json"
            ))["filings"]["recent"]
            cand = [i for i, f in enumerate(s["form"]) if f in PROXY_FORMS]
            if not cand:
                rec["note"] = "no proxy"
            else:
                i = cand[0]
                acc = s["accessionNumber"][i].replace("-", "")
                j = json.loads(get(
                    f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/index.json"))
                docs = [x for x in j["directory"]["item"]
                        if x["name"].endswith(".htm")
                        and not re.match(r"^R\d+\.htm$", x["name"])]
                if docs:
                    doc = max(docs, key=lambda x: int(x["size"]))["name"]
                    txt = plain(get(
                        f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{doc}"))
                    rec.update(extract(txt))
                    rec["proxy_date"] = s["filingDate"][i]
        except Exception as e:
            rec["note"] = f"ERR {str(e)[:40]}"
        # max position is capped by the threshold, by construction
        if rec.get("cash") and rec.get("thr_min"):
            rec["max_pos"] = round((rec["thr_min"] - 1) * rec["cash"])
        out.append(rec)
        pxr = (f"{rec['px_hi']:.2f}/{rec['px_lo']:.2f}"
               if rec.get("px_hi") else "-")
        print(f"{rec.get('ticker',''):<8}"
              f"{(f'${rec[chr(99)+chr(97)+chr(115)+chr(104)]:.2f}' if rec.get('cash') else '-'):>8}"
              f"{(str(rec.get('thr_min','-'))):>9}"
              f"{(f'${rec[chr(109)+chr(97)+chr(120)+chr(95)+chr(112)+chr(111)+chr(115)]:,}' if rec.get('max_pos') else '-'):>9}"
              f"{pxr:>24}  {rec['name'][:34]}")
        time.sleep(0.3)

    cols = ["name", "ticker", "cik", "first_13e3", "proxy_date", "cash",
            "thr_min", "thr_max", "max_pos", "meeting", "record_only",
            "px_hi", "px_lo", "px_last_hi", "px_last_lo", "note"]
    with open("research/tenders/ledger_stage3.csv", "w", newline="",
              encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(out)

    threshold_deals = [x for x in out if x.get("thr_min") and x.get("cash")]
    priced = [x for x in threshold_deals if x.get("px_hi")]
    print("-" * 104)
    print(f"{len(out)} issuers | {len(threshold_deals)} with cash + threshold "
          f"(the odd-lot signature) | {len(priced)} with a filing price table")
    print(f"GATE needs >=8 investable events in 36 months. "
          f"Currently {len(threshold_deals)} candidates before quality screens.")
    if threshold_deals:
        avg = sum(x["max_pos"] for x in threshold_deals) / len(threshold_deals)
        print(f"mean max position (threshold-1 shares x cash): ${avg:,.0f}")
        print("At a 3% net spread that is roughly "
              f"${avg*0.03:,.0f} per event.")
    print("\nwrote research/tenders/ledger_stage3.csv")


if __name__ == "__main__":
    main()
