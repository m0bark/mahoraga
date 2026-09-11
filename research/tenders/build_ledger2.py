"""Stage 2 of the pre-registered go-live gate: extract deal TERMS for every
SC 13E3 reverse-split issuer, straight from the filings.

Why this works where price vendors don't: these issuers go private and
delist, so yfinance/Stooq return nothing for most of them. But Reg M-A
Item 1002(c) FORCES the issuer to disclose the cash-out price, the share
threshold, and recent market prices inside the proxy itself. The ledger is
therefore point-in-time and survivorship-free by construction -- exactly
the property every other lane in this project failed to get for free.

Reads: research/tenders/ledger_stage1.csv
Writes: research/tenders/ledger_stage2.csv
"""
from __future__ import annotations
import csv, html, io, json, re, sys, time, urllib.request
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

H = {"User-Agent": "mahoraga-research m0ba.c0ffe@gmail.com"}
PROXY_FORMS = ("DEFM14A", "DEF 14A", "PREM14A", "PRE 14A", "DEF 14C", "PRE 14C")


def get(url: str, tries: int = 3) -> str:
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers=H)
            return urllib.request.urlopen(req, timeout=60).read().decode("utf8", "ignore")
        except Exception:
            if k == tries - 1:
                raise
            time.sleep(1.5)
    return ""


def plain(h: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", h)))


def biggest_doc(cik: str, acc: str) -> str | None:
    j = json.loads(get(f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/index.json"))
    items = [x for x in j["directory"]["item"]
             if x["name"].endswith(".htm") and not re.match(r"^R\d+\.htm$", x["name"])]
    if not items:
        return None
    return max(items, key=lambda x: int(x["size"]))["name"]


def extract(txt: str) -> dict:
    out = {}
    # cash-out price per pre-split share
    pats = [r"receive \$\s?([\d,]+\.\d{2})\s+in cash",
            r"cash payment of \$\s?([\d,]+\.\d{2})",
            r"\$\s?([\d,]+\.\d{2})\s+in cash, without interest"]
    for p in pats:
        m = re.search(p, txt, re.I)
        if m:
            out["cash_price"] = m.group(1).replace(",", "")
            break
    # threshold ("Minimum Number") -- the ratio range
    m = re.search(r"between\s+([\d,]+)\s+and\s+([\d,]+)\s+shares", txt, re.I)
    if m:
        out["thresh_min"], out["thresh_max"] = m.group(1).replace(",", ""), m.group(2).replace(",", "")
    else:
        m = re.search(r"fewer than\s+([\d,]+)\s+shares", txt, re.I)
        if m:
            out["thresh_min"] = out["thresh_max"] = m.group(1).replace(",", "")
    # split ratio range
    m = re.search(r"1-for-([\d,]+)\s+and not greater than 1-for-([\d,]+)", txt, re.I)
    if m:
        out["ratio"] = f"1:{m.group(1)}-1:{m.group(2)}"
    # meeting date
    m = re.search(r"Special Meeting[^.]{0,120}?to be held on ([A-Z][a-z]+ \d{1,2}, \d{4})", txt)
    if m:
        out["meeting"] = m.group(1)
    # street-name / record-holder trap
    out["record_only"] = bool(re.search(r"record holders?\b[^.]{0,200}\bonly\b", txt, re.I))
    out["has_fairness"] = bool(re.search(r"fairness opinion", txt, re.I))
    return out


rows = list(csv.DictReader(open("research/tenders/ledger_stage1.csv", encoding="utf-8")))
res = []
for r in rows:
    cik = r["cik"].lstrip("0")
    rec = {"name": r["name"][:38], "ticker": r["ticker"].split(",")[0],
           "first_13e3": r["first_filing"]}
    try:
        s = json.loads(get(f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json"))["filings"]["recent"]
        cand = [i for i, f in enumerate(s["form"]) if f in PROXY_FORMS
                and s["filingDate"][i] >= r["first_filing"]]
        if not cand:
            rec["note"] = "no proxy after 13E3"
        else:
            i = cand[-1]
            acc = s["accessionNumber"][i].replace("-", "")
            doc = biggest_doc(cik, acc)
            txt = plain(get(f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{doc}"))
            rec["proxy_form"], rec["proxy_date"] = s["form"][i], s["filingDate"][i]
            rec.update(extract(txt))
    except Exception as e:
        rec["note"] = f"ERR {str(e)[:40]}"
    res.append(rec)
    print(f"{rec.get('ticker',''):<8}{rec['name'][:30]:<32}"
          f"${rec.get('cash_price','-'):>8}  thresh {rec.get('thresh_min','-'):>6}-{rec.get('thresh_max','-'):<6}"
          f" {rec.get('meeting','-'):<20} {rec.get('note','')}")
    time.sleep(0.25)

cols = ["name", "ticker", "first_13e3", "proxy_form", "proxy_date", "cash_price",
        "thresh_min", "thresh_max", "ratio", "meeting", "record_only", "has_fairness", "note"]
with open("research/tenders/ledger_stage2.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
    w.writeheader(); w.writerows(res)
got = sum(1 for x in res if x.get("cash_price"))
print(f"\n{got}/{len(res)} issuers with a machine-extracted cash-out price")
print("wrote research/tenders/ledger_stage2.csv")
