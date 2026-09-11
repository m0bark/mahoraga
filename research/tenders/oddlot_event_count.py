"""Count US tender offers with an odd-lot preference, 36 months, from EDGAR FTS."""
import json, urllib.parse, urllib.request, time, sys, io
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
UA = {"User-Agent": "personal-research-tool contact-via-edgar"}
START, END = "2023-09-01", "2026-09-06"

def fts(q, forms, frm=0):
    p = urllib.parse.urlencode({"q": q, "forms": forms, "dateRange": "custom",
                                "startdt": START, "enddt": END, "from": frm})
    req = urllib.request.Request("https://efts.sec.gov/LATEST/search-index?" + p, headers=UA)
    with urllib.request.urlopen(req, timeout=45) as f:
        return json.load(f)

def collect(q, forms):
    out, frm = [], 0
    while True:
        d = fts(q, forms, frm)
        hits = d.get("hits", {}).get("hits", [])
        out += hits
        total = d.get("hits", {}).get("total", {}).get("value", 0)
        frm += len(hits)
        if frm >= total or not hits or frm >= 1000:
            break
        time.sleep(0.35)
    return out, total

for q, forms, label in [
    ('"odd lots"', "SC TO-I", "SC TO-I (issuer self-tender) w/ 'odd lots'"),
    ('"Odd Lot Priority"', "SC TO-I", "SC TO-I w/ 'Odd Lot Priority'"),
    ('"odd lots"', "SC TO-T", "SC TO-T (third-party) w/ 'odd lots'"),
    ('"odd lots"', "SC 14D9", "SC 14D9 w/ 'odd lots'"),
]:
    try:
        hits, total = collect(q, forms)
        issuers = defaultdict(list)
        for h in hits:
            s = h["_source"]
            cik = str(s.get("ciks", ["?"])[0])
            issuers[cik].append((s["file_date"], "; ".join(s.get("display_names", ["?"]))))
        print(f"\n### {label}: {total} filings, {len(issuers)} distinct issuers, {START}..{END}")
        rows = sorted(((min(d for d,_ in v), v[0][1], len(v)) for v in issuers.values()))
        for dt, nm, n in rows:
            print(f"  {dt}  n={n:2d}  {nm[:70]}")
    except Exception as e:
        print(f"{label}: ERROR {e}")
    time.sleep(0.5)
