"""Odd-lot / Dutch-auction self-tender scanner (forced-flows family).

Supersedes tender_scan.py. Differences that matter:
  * dedupes to DISTINCT OFFERS. EDGAR full-text search returns one hit per
    DOCUMENT, so a single Schedule TO yields 5-15 hits; the old script counted
    those as separate events.
  * paginates. FTS page size is 100 and `from` is capped at 9,900.
  * screens out the ~85% of SC TO-I flow that is non-traded BDC / interval-fund
    quarterly repurchase offers, by requiring the CIK to carry a ticker in
    https://www.sec.gov/files/company_tickers.json
  * separates a GENUINE odd-lot preference (the proration-ordering clause) from
    a passing mention of the words "odd lot".
  * extracts the Expiration Date and computes lead time / days remaining.

Verified empirically 2026-09-06:
  - endpoint  https://efts.sec.gov/LATEST/search-index?q=...&forms=...
  - the User-Agent header is MANDATORY (403 without one). SEC webmaster FAQ
    format: "Sample Company Name AdminContact@<domain>". Max rate 10 req/sec.
  - FTS coverage starts 2001-01-01. Indexing lag ~0-1 business days.
  - SC 13E4 is a DEAD form (0 filings after 2001; folded into SC TO-I by
    Regulation M-A).
  - SC TO-T essentially never carries an odd-lot preference (9 filings in 7yr).

Run: .venv/Scripts/python.exe research/tenders/odd_lot_scan.py [days_back]
"""
from __future__ import annotations

import html as htmlmod
import io
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

UA = {"User-Agent": "mahoraga-research m0ba.c0ffe@gmail.com"}
FTS = "https://efts.sec.gov/LATEST/search-index?"
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
RATE_SLEEP = 0.12  # stay under the documented 10 req/sec cap

# The proration-ORDERING clause. A document that merely contains "odd lot"
# does not qualify: roughly half of the "odd lot" SC TO-I hits are passing
# mentions or fund NAV repurchase offers.
PREFERENCE = re.compile(
    r"(without\s+subjecting\s+them\s+to\s+the\s+proration"
    r"|not\s+subject\s+to\s+(?:the\s+)?proration"
    r"|without\s+proration"
    r"|odd\s*lots?\s+(?:priority|preference)"
    r"|purchase\s+all\s+odd\s*lots?"
    r"|first,?\s+(?:we|the\s+(?:company|fund|issuer|trust))\s+will\s+purchase\s+all)",
    re.I,
)
THRESHOLD = re.compile(
    r"(?:fewer|less)\s+than\s+(\d{2,4}(?:,\d{3})?)\s+(?:shares|units)", re.I)
DUTCH = re.compile(r"dutch\s+auction|purchase\s+price\s+range|price\s+range\s+of\s+not", re.I)
FUND = re.compile(
    r"repurchase\s+offer|interval\s+fund|net\s+asset\s+value\s+per\s+share"
    r"|Investment\s+Company\s+Act\s+of\s+1940", re.I)
EXPIRY = re.compile(
    r"(?:11:59\s*[Pp]\.?[Mm]|12:00\s*[Mm]idnight|5:00\s*[Pp]\.?[Mm]"
    r"|one\s+minute\s+after\s+11:59)"
    r"[^.]{0,90}?on\s+(?:[A-Z][a-z]+day,?\s+)?"
    r"(January|February|March|April|May|June|July|August|September|October"
    r"|November|December)\s+(\d{1,2}),?\s+(20\d\d)")
MONTHS = {m: i + 1 for i, m in enumerate(
    "january february march april may june july august september october "
    "november december".split())}


def _get(url: str, tries: int = 3) -> str:
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=90) as r:
                return r.read().decode("utf8", "ignore")
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 503) and k < tries - 1:
                time.sleep(2 + 2 * k)
                continue
            return ""
        except Exception:
            if k == tries - 1:
                return ""
            time.sleep(1.5 + k)
    return ""


def fts_page(q: str, forms: str, start: str, end: str, frm: int = 0) -> dict:
    params = {"q": q, "forms": forms, "startdt": start, "enddt": end}
    if frm:
        params["from"] = frm
    body = _get(FTS + urllib.parse.urlencode(params))
    return json.loads(body) if body else {}


def fts_all(q: str, forms: str, start: str, end: str) -> list[dict]:
    out: list[dict] = []
    frm = 0
    while True:
        d = fts_page(q, forms, start, end, frm)
        if not d:
            break
        hits = d["hits"]["hits"]
        total = d["hits"]["total"]["value"]
        out += hits
        frm += len(hits)
        if not hits or frm >= total or frm >= 9900:
            break
        time.sleep(RATE_SLEEP)
    return out


def listed_ciks() -> dict[int, str]:
    body = _get(TICKERS_URL)
    if not body:
        return {}
    return {int(v["cik_str"]): v["ticker"] for v in json.loads(body).values()}


def plain(h: str) -> str:
    return re.sub(r"\s+", " ", htmlmod.unescape(re.sub(r"<[^>]+>", " ", h)))


def best_doc_per_accession(hits: list[dict]) -> dict[str, dict]:
    """FTS hits are per-document. Keep the Offer to Purchase
    (EX-99.(a)(1)(A)) when present, else any (a)(1) exhibit, else the cover."""
    best: dict[str, tuple[int, dict]] = {}
    for h in hits:
        ft = (h["_source"].get("file_type") or "").upper().replace(" ", "")
        rank = 0 if "A)(1)(A" in ft else (1 if "A)(1)" in ft else 2)
        acc = h["_source"]["adsh"]
        if acc not in best or rank < best[acc][0]:
            best[acc] = (rank, h)
    return {k: v[1] for k, v in best.items()}


def parse_expiry(txt: str) -> date | None:
    m = EXPIRY.search(txt)
    if not m:
        return None
    try:
        return date(int(m.group(3)), MONTHS[m.group(1).lower()], int(m.group(2)))
    except Exception:
        return None


def scan(days_back: int = 90) -> list[dict]:
    start = (date.today() - timedelta(days=days_back)).isoformat()
    end = date.today().isoformat()
    tickers = listed_ciks()
    hits = fts_all('"odd lot"', "SC TO-I", start, end)
    rows = []
    for acc, h in best_doc_per_accession(hits).items():
        src = h["_source"]
        cik = int(src["ciks"][0])
        if src.get("form") != "SC TO-I":   # skip amendments
            continue
        if cik not in tickers:             # skip non-traded funds
            continue
        url = (f"https://www.sec.gov/Archives/edgar/data/{cik}/"
               f"{acc.replace('-', '')}/{h['_id'].split(':', 1)[1]}")
        txt = plain(_get(url))
        time.sleep(RATE_SLEEP)
        if len(txt) < 2500:
            continue
        exp = parse_expiry(txt)
        filed = date.fromisoformat(src["file_date"])
        th = THRESHOLD.search(txt)
        rows.append({
            "filed": src["file_date"],
            "ticker": tickers[cik],
            "name": src["display_names"][0].split("  (")[0],
            "preference": bool(PREFERENCE.search(txt)),
            "threshold": th.group(1) if th else "",
            "dutch": bool(DUTCH.search(txt)),
            "fund": bool(FUND.search(txt)),
            "expires": exp.isoformat() if exp else "",
            "lead_days": (exp - filed).days if exp else None,
            "days_left": (exp - date.today()).days if exp else None,
            "url": url,
        })
    return sorted(rows, key=lambda r: r["filed"], reverse=True)


def main() -> None:
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 90
    rows = scan(days)
    live = [r for r in rows
            if r["preference"] and (r["days_left"] is None or r["days_left"] >= 0)]
    print(f"listed-issuer SC TO-I mentioning odd lots, last {days}d: {len(rows)}")
    print(f"  ...with a genuine odd-lot PREFERENCE clause: "
          f"{sum(r['preference'] for r in rows)}\n")
    for r in rows:
        flag = "PREF" if r["preference"] else "----"
        kind = "DA" if r["dutch"] else "FX"
        fnd = " [fund]" if r["fund"] else ""
        left = f"{r['days_left']:+d}d" if r["days_left"] is not None else "  ?"
        print(f"{r['filed']}  {flag} {kind} <{r['threshold'] or '?':>5}sh  "
              f"exp {r['expires'] or '?':<10} {left:>5}  "
              f"{r['ticker']:<6} {r['name'][:38]}{fnd}")
        print(f"    {r['url']}")
    print(f"\n{len(live)} live offer(s) carrying an odd-lot preference. "
          f"READ EACH FILING before acting: confirm (1) the priority clause is "
          f"in the final terms, (2) the threshold (usually 100 shares), "
          f"(3) tender price or range vs market, (4) that ALL your shares must "
          f"be tendered to qualify, (5) street-name vs record-holder handling, "
          f"(6) the offer conditions and any minimum.")


if __name__ == "__main__":
    main()
