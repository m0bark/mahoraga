"""Analyst copy-tracker: snapshot ratings, detect CHANGES, build a ledger.

    python research/analysts/tracker.py            # snapshot + diff vs last run
    python research/analysts/tracker.py --report   # show the ledger so far
    python research/analysts/tracker.py --rebuild  # rebuild ledger from snapshots

WHY THIS SHAPE, AND NOT "BUY WHAT THE TOP ANALYSTS RATE BUY"

Three measured facts decide the design:

1. The LEVEL of consensus does not predict returns. The CHANGE does.
   Chen-Zimmermann open-source data 1993-2024: consensus-change earns
   +0.54%/mo (t=7.0) full sample, +0.32%/mo (t=4.5) after May 2001, with
   +0.30%/mo alpha (t=3.36) after momentum controls. The LEVEL signal is
   dead post-decimalization. So a static "who rates it Buy" list is the
   half that does not work -- which is exactly what the website shows you.

2. Agreement is mostly a size artifact. On stockanalysis.com's own
   top-stocks page: corr(number of agreeing top analysts, log market cap)
   = +0.569, and corr(agreement, implied upside) = -0.354. More agreement,
   bigger company, LESS expected upside.

3. Drift is front-loaded -- roughly 30 days for upgrades (Womack 1996).
   A 12-month hold, which is how the site scores, dilutes it.

So this tool does not screen. It WATCHES, and it records the one thing
that carries information: the moment a rating changes. You cannot backtest
this from public pages -- historical rating dates are not published -- so
the only honest path is to start recording now and measure forward.

PAYWALL HAZARD (found the hard way, 2026-09-06)
The free tier renders only ~9 real tickers per analyst; every later row
has its symbol replaced by the literal string XXXX. Those rows are
unusable -- no symbol means no forward return can ever be attached to
them -- and they are not unique, so keying a diff on symbol collapses all
of them into ONE entry and refires the rest as NEW on every run. The first
run of this tool produced 125 phantom "changes" in a single day that way.
Masked rows are now dropped at the parse boundary and the count is
printed; the diff additionally refuses to run on any analyst whose symbol
keys are not unique, rather than silently producing garbage.

PRE-REGISTERED GATE, written before any data exists, so it cannot be moved:
  after >= 40 recorded upgrade events with >= 60 trading days elapsed,
  require mean excess return vs the stock's SECTOR ETF > 0 with t > 2.
  Below that, no money. A sector benchmark, not SPY, because the analysts
  are sector specialists and sector beta is what fooled the leaderboard.

Pro depth: set SA_COOKIE from your logged-in browser to render more than
the 7 analysts and ~9 symbols the public page exposes server-side.
"""
from __future__ import annotations

import csv
import gzip
import html as htmlmod
import io
import json
import os
import re
import sys
import time
import urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

SNAP_DIR = "research/analysts/snapshots"
LEDGER = "research/analysts/ledger.csv"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
DELAY = 1.5
# the site's paywall placeholder for a gated ticker
MASKED = re.compile(r"^X{3,}$")
# sector ETF used as the benchmark for each analyst's coverage
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


def cells_of(tbl: str):
    for tr in re.findall(r"<tr.*?</tr>", tbl, re.S | re.I):
        c = [re.sub(r"\s+", " ", htmlmod.unescape(re.sub(r"<[^>]+>", " ", x))).strip()
             for x in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S | re.I)]
        c = [x for x in c if x]
        if len(c) >= 5:
            yield c


def leaderboard() -> list[dict]:
    """Slugs come from the page's own hrefs, never from munging the display
    name -- the name cell has the star score and firm glued onto it."""
    h = get("https://stockanalysis.com/analysts/")
    if not h:
        return []
    slugs = []
    for s in re.findall(r'href="/analysts/([a-z0-9-]+)/"', h):
        if s not in ("top-stocks", "most-followed") and s not in slugs:
            slugs.append(s)
    tbl = re.findall(r"<table.*?</table>", h, re.S | re.I)
    out = []
    for c in cells_of(tbl[0] if tbl else ""):
        try:
            rank = int(c[0])
        except ValueError:
            continue
        firm = c[2]
        name = re.sub(r"\(\d\.\d+\)", "", c[1]).replace(firm, "").strip()
        want = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
        slug = want if want in slugs else next(
            (s for s in slugs if s.startswith(want.split("-")[0])
             and want.split("-")[-1] in s), want)
        out.append({"rank": rank, "name": name, "slug": slug, "firm": firm,
                    "sector": c[3], "success": c[4], "avg_return": c[5],
                    "ratings": c[6]})
    return out


def ratings_of(slug: str) -> tuple[list[dict], int]:
    """Returns (usable rows, number of paywall-masked rows dropped).

    A masked row carries no ticker, so no forward return can ever be
    attached to it. Dropping it here is the only honest option; carrying
    it forward poisons the diff (see PAYWALL HAZARD in the module docstring).
    """
    h = get(f"https://stockanalysis.com/analysts/{slug}/")
    if not h:
        return [], 0
    tbl = re.findall(r"<table.*?</table>", h, re.S | re.I)
    if not tbl:
        return [], 0
    out: list[dict] = []
    masked = 0
    for c in cells_of(tbl[0]):
        joined = " ".join(c)
        sym = c[0].replace("TSX: ", "TSX:").split()[0] if c else ""
        m = re.search(r"(Downgraded|Upgraded|Maintained|Initiated|Reiterated):\s*(\w+)",
                      joined)
        if not m or not sym:
            continue
        if MASKED.match(sym):
            masked += 1
            continue
        pt = re.findall(r"\$([\d,]+\.?\d*)", joined)
        out.append({"symbol": sym, "action": m.group(1), "rating": m.group(2),
                    "target": pt[-1].replace(",", "") if pt else None})
    return out, masked


def snapshot(today: str) -> dict:
    board = leaderboard()
    print(f"leaderboard: {len(board)} analysts"
          + ("" if os.environ.get("SA_COOKIE") else
             "  (set SA_COOKIE for more than the public 7)"))
    snap = {"date": today, "analysts": {}}
    total_masked = 0
    for a in board:
        rows, masked = ratings_of(a["slug"])
        total_masked += masked
        time.sleep(DELAY)
        snap["analysts"][a["slug"]] = {"meta": a, "ratings": rows}
        note = f"   [{masked} paywalled, dropped]" if masked else ""
        print(f"  {a['name'][:28]:<30}{a['sector'][:12]:<14}"
              f"{len(rows):>3} usable{note}")
    usable = sum(len(v["ratings"]) for v in snap["analysts"].values())
    seen = usable + total_masked
    print(f"\n{usable} usable rows; {total_masked} dropped as paywalled "
          f"({total_masked / max(seen, 1):.0%} of the table)")
    if total_masked and not os.environ.get("SA_COOKIE"):
        print("  -> set SA_COOKIE from a logged-in browser to unmask these")
    return snap


def latest_prior(today: str) -> dict | None:
    if not os.path.isdir(SNAP_DIR):
        return None
    files = sorted(f for f in os.listdir(SNAP_DIR)
                   if f.endswith(".json") and f[:-5] < today)
    if not files:
        return None
    return json.load(open(os.path.join(SNAP_DIR, files[-1]), encoding="utf-8"))


def diff(prev: dict, cur: dict) -> list[dict]:
    """Only CHANGES are events. A standing Buy is not an event.

    Refuses to diff an analyst whose symbols are not unique. A collapsed
    dict key does not fail loudly -- it silently refires every duplicate as
    NEW on every run, forever, which is how 125 phantom events got into the
    first ledger.
    """
    events = []
    for slug, cd in cur["analysts"].items():
        now = cd["ratings"]
        was = prev["analysts"].get(slug, {}).get("ratings", []) if prev else []
        before = {r["symbol"]: r for r in was}
        if len(before) != len(was) or len({r["symbol"] for r in now}) != len(now):
            print(f"  !! {slug}: duplicate symbols, skipped "
                  f"(would produce phantom events)")
            continue
        for r in now:
            b = before.get(r["symbol"])
            kind = None
            if b is None:
                kind = "NEW"
            elif b["rating"] != r["rating"]:
                kind = f"CHANGED {b['rating']}->{r['rating']}"
            elif b.get("target") != r.get("target"):
                kind = f"TARGET {b.get('target')}->{r.get('target')}"
            if kind:
                events.append({
                    "date": cur["date"], "analyst": slug,
                    "sector": cd["meta"]["sector"],
                    "benchmark": SECTOR_ETF.get(cd["meta"]["sector"].split()[0], "SPY"),
                    "symbol": r["symbol"], "action": r["action"],
                    "rating": r["rating"], "target": r.get("target"),
                    "event": kind,
                })
    return events


def clean_snapshot(snap: dict) -> dict:
    """Strip masked rows from a snapshot saved before the paywall fix."""
    for v in snap.get("analysts", {}).values():
        v["ratings"] = [r for r in v["ratings"] if not MASKED.match(r["symbol"])]
    return snap


def write_events(events: list[dict], mode: str) -> None:
    header = mode == "w" or not os.path.exists(LEDGER)
    with open(LEDGER, mode, newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(events[0].keys()))
        if header:
            w.writeheader()
        w.writerows(events)


def rebuild() -> None:
    """Recompute the whole ledger from saved snapshots, masked rows removed.

    Needed once, because every event in the pre-fix ledger is a phantom.
    """
    files = sorted(f for f in os.listdir(SNAP_DIR) if f.endswith(".json"))
    snaps = [clean_snapshot(json.load(open(os.path.join(SNAP_DIR, f),
                                          encoding="utf-8"))) for f in files]
    print(f"rebuilding from {len(snaps)} snapshots")
    for s in snaps:
        n = sum(len(v["ratings"]) for v in s["analysts"].values())
        print(f"  {s['date']}: {n} usable rows")
    all_events = []
    for prev, cur in zip(snaps, snaps[1:]):
        ev = diff(prev, cur)
        print(f"  {prev['date']} -> {cur['date']}: {len(ev)} real events")
        all_events += ev
    if all_events:
        write_events(all_events, "w")
        print(f"\nwrote {len(all_events)} events to {LEDGER}")
    else:
        if os.path.exists(LEDGER):
            os.remove(LEDGER)
        print(f"\n0 real events across all snapshots -- removed {LEDGER}")
        print("The 125 events in the old ledger were the XXXX key collision,")
        print("not analyst activity.")


def report() -> None:
    if not os.path.exists(LEDGER):
        print("no ledger yet -- run without --report first")
        return
    rows = list(csv.DictReader(open(LEDGER, encoding="utf-8")))
    print(f"{len(rows)} recorded events")
    kinds: dict[str, int] = {}
    for r in rows:
        k = r["event"].split()[0]
        kinds[k] = kinds.get(k, 0) + 1
    print(" ", kinds)
    ups = [r for r in rows if r["action"] == "Upgraded"]
    print("\nGATE: need >=40 upgrade events with >=60 trading days elapsed,")
    print("      then mean excess vs SECTOR ETF > 0 with t > 2.")
    print(f"  upgrades recorded so far: {len(ups)}/40")


def main() -> None:
    if "--report" in sys.argv:
        report()
        return
    if "--rebuild" in sys.argv:
        rebuild()
        return

    today = time.strftime("%Y-%m-%d")
    os.makedirs(SNAP_DIR, exist_ok=True)
    cur = snapshot(today)
    if not cur["analysts"]:
        print("nothing fetched -- site layout may have changed")
        return
    json.dump(cur, open(os.path.join(SNAP_DIR, f"{today}.json"), "w",
                        encoding="utf-8"), indent=1)
    prev = latest_prior(today)
    if prev is None:
        print("\nfirst snapshot saved. No diff yet -- run again in a few days "
              "and changes become events.")
        return

    events = diff(clean_snapshot(prev), cur)
    print(f"\n{len(events)} changes since {prev['date']}")
    for e in events[:25]:
        print(f"  {e['symbol']:<10}{e['action']:<12}{e['rating']:<8}"
              f"{e['event']:<26}{e['analyst']}")
    if events:
        write_events(events, "a")
        print(f"\nappended to {LEDGER}")
    print("\nOnly CHANGES are recorded. A standing Buy rating is not an event --")
    print("the consensus LEVEL was measured dead post-decimalization; the")
    print("CHANGE is the half that carries information.")


if __name__ == "__main__":
    main()
