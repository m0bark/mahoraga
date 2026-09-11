"""Pull DATED analyst rating events off stockanalysis.com analyst pages.

    python research/analysts/pull_events.py

WHY THIS REPLACES THE DIFF-FORWARD PLAN

tracker.py was built on the belief that historical rating dates are not
published, so the only honest path was to snapshot daily and diff. That
belief was wrong. The analyst table has seven columns:

    Stock | Action | Price Target | Current | Upside | Ratings | Updated
                                                                ^^^^^^^
and the Updated cell carries the actual date of the rating action
("Jun 29, 2026"). Every visible row is therefore already a dated event and
can be scored against history immediately -- no waiting.

Two parsing bugs this file fixes, both found by noticing that two different
analysts had identical "targets" on five different stocks:

  1. The old code took the LAST dollar figure in the row, which is the
     CURRENT price column, not the target. So every "target" it recorded
     was really the share price -- meaning the TARGET-changed branch of the
     diff would fire every single day as prices moved, forever.
  2. The Price Target cell is often "$430 -> $515", i.e. it states the old
     and new target explicitly. That arrow is the single most informative
     thing on the page and the old parser threw it away.

Paywall: the free tier masks tickers past ~row 9 (literal "XXXX") and shows
only 7 analysts. Masked rows are dropped and counted. Set SA_COOKIE from a
logged-in browser to unmask.
"""
from __future__ import annotations

import csv
import gzip
import html as htmlmod
import io
import os
import re
import sys
import time
import urllib.request

_OUT = io.TextIOWrapper(open(sys.stdout.fileno(), "wb", closefd=False),
                        encoding="utf-8", errors="replace")


def say(*a) -> None:
    print(*a, file=_OUT)
    _OUT.flush()


UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
DELAY = 1.5
MASKED = re.compile(r"^X{3,}$")
OUT_CSV = "research/analysts/events.csv"
SECTOR_ETF = {"Financials": "XLF", "Energy": "XLE", "Technology": "XLK",
              "Healthcare": "XLV", "Industrials": "XLI", "Consumer": "XLY",
              "Materials": "XLB", "Utilities": "XLU", "Real Estate": "XLRE"}


def get(url: str) -> str | None:
    h = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"}
    ck = os.environ.get("SA_COOKIE")
    if ck:
        h["Cookie"] = ck
    for k in range(3):
        try:
            raw = urllib.request.urlopen(
                urllib.request.Request(url, headers=h), timeout=30).read()
            if raw[:2] == b"\x1f\x8b":
                raw = gzip.decompress(raw)
            return raw.decode("utf-8", "ignore")
        except Exception:
            time.sleep(2 * (k + 1))
    return None


def txt(x: str) -> str:
    return re.sub(r"\s+", " ", htmlmod.unescape(re.sub(r"<[^>]+>", " ", x))).strip()


def money(s: str) -> float | None:
    m = re.search(r"([\d,]+\.?\d*)", s or "")
    return float(m.group(1).replace(",", "")) if m else None


def parse_target(cell: str) -> tuple[float | None, float | None]:
    """'$430 -> $515' -> (430, 515);  '$125' -> (None, 125).

    The arrow renders as a unicode right-arrow; split on any non-numeric,
    non-$ run rather than hardcoding the glyph.
    """
    nums = [float(x.replace(",", "")) for x in re.findall(r"\$([\d,]+\.?\d*)", cell)]
    if len(nums) >= 2:
        return nums[0], nums[-1]
    if len(nums) == 1:
        return None, nums[0]
    return None, None


def rows_of(slug: str) -> tuple[list[dict], int]:
    h = get(f"https://stockanalysis.com/analysts/{slug}/")
    if not h:
        return [], 0
    tbl = re.findall(r"<table.*?</table>", h, re.S | re.I)
    if not tbl:
        return [], 0
    out: list[dict] = []
    masked = 0
    for tr in re.findall(r"<tr.*?</tr>", tbl[0], re.S | re.I):
        c = [txt(x) for x in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S | re.I)]
        c = [x for x in c if x]
        # Stock, Action, Price Target, Current, Upside, Ratings, Updated
        if len(c) < 7:
            continue
        m = re.match(r"(Downgraded|Upgraded|Maintained|Initiated|Reiterated):\s*(.+)",
                     c[1])
        if not m:
            continue
        sym = c[0].split()[0]
        if MASKED.match(sym):
            masked += 1
            continue
        if not re.match(r"^[A-Z][A-Z.\-]{0,6}$", sym):
            continue
        t_old, t_new = parse_target(c[2])
        out.append({
            "analyst": slug, "symbol": sym,
            "action": m.group(1), "rating": m.group(2).strip(),
            "target_old": t_old, "target_new": t_new,
            "price_at_pull": money(c[3]),
            "upside_pct": money(c[4].replace("+", "").replace("%", "")),
            "n_ratings_on_stock": money(c[5]),
            "date": c[6],
        })
    return out, masked


def main() -> None:
    h = get("https://stockanalysis.com/analysts/")
    if not h:
        say("leaderboard fetch failed")
        return
    slugs, meta = [], {}
    for s in re.findall(r'href="/analysts/([a-z0-9-]+)/"', h):
        if s not in ("top-stocks", "most-followed") and s not in slugs:
            slugs.append(s)
    tbl = re.findall(r"<table.*?</table>", h, re.S | re.I)
    for tr in re.findall(r"<tr.*?</tr>", tbl[0] if tbl else "", re.S | re.I):
        c = [x for x in (txt(y) for y in
                         re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S | re.I)) if x]
        if len(c) >= 6 and c[0].isdigit():
            meta[c[3]] = c[3]                       # sector column
    say(f"{len(slugs)} analyst pages"
        + ("" if os.environ.get("SA_COOKIE") else "   (public tier: 7 max)"))

    allrows, tot_masked = [], 0
    for s in slugs:
        r, mk = rows_of(s)
        tot_masked += mk
        allrows += r
        say(f"  {s:<24}{len(r):>3} dated events   [{mk} paywalled]")
        time.sleep(DELAY)

    if not allrows:
        say("no rows parsed -- layout may have changed")
        return
    keys = list(allrows[0].keys())
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(allrows)

    dated = [r for r in allrows if r["date"]]
    raised = [r for r in allrows if r["target_old"] and r["target_new"]
              and r["target_new"] > r["target_old"]]
    cut = [r for r in allrows if r["target_old"] and r["target_new"]
           and r["target_new"] < r["target_old"]]
    say(f"\n{len(allrows)} usable dated events; {tot_masked} paywalled and dropped")
    say(f"  with an explicit target change: {len(raised) + len(cut)}"
        f"  ({len(raised)} raised, {len(cut)} cut)")
    acts: dict[str, int] = {}
    for r in allrows:
        acts[r["action"]] = acts.get(r["action"], 0) + 1
    say(f"  actions: {acts}")
    # sort as DATES, not strings -- lexicographic order on "Mon D, YYYY"
    # puts Apr before Aug before Sep and reported a range that was simply wrong
    import datetime as _dt
    ds = sorted(_dt.datetime.strptime(r["date"], "%b %d, %Y") for r in dated)
    say(f"  date range: {ds[0]:%b %d, %Y}  ..  {ds[-1]:%b %d, %Y}" if ds else "  no dates")
    say(f"\nwrote {OUT_CSV}")


if __name__ == "__main__":
    main()
