"""COPY DESK -- live tracker for analyst buy/sell actions across the market.

    python research/analysts/copy_desk.py                     # scan top 800, show what's new
    python research/analysts/copy_desk.py --n 2500             # scan wider
    python research/analysts/copy_desk.py --buys               # only Upgrades/Initiates to Buy
    python research/analysts/copy_desk.py --days 3             # only actions dated in last 3 days
    python research/analysts/copy_desk.py --analyst "Quinn Bolton"
    python research/analysts/copy_desk.py --firm Needham
    python research/analysts/copy_desk.py --live 30            # rescan every 30 minutes
    python research/analysts/copy_desk.py --recent             # read tape only, no network

WHAT IT DOES
Scans stockanalysis.com's per-stock ratings pages (NOT the analyst pages --
those are paywalled and mask the ticker after row 9), parses every rating
action, and diffs against the local tape. Anything not already recorded is
printed newest-first as an actionable line, and appended to the tape.

    SYMBOL  ACTION      RATING  TARGET   UPSIDE   ANALYST            FIRM        DATE

Parallel: 4 concurrent fetches behind a shared rate limiter, so a 2,500-name
scan takes about 12 minutes instead of 50. The limiter is global; raising
WORKERS without raising MIN_INTERVAL will not go faster, by design.

WHAT THE OPERATOR SHOULD KNOW (measured on this tape, 11,570 events, 2026-09-07)
Entering on the public publication date underperformed entering the same
stock on a nearby day by -0.67% to -1.55% over the following month
(Bonferroni p ~ 0.0005, placebo on random dates: -0.01%). Upgrades alone
showed no stable effect either way. The tool reports what the analysts did;
it does not claim the copy is profitable. See
research/cards/2026-09-07-analyst-date-selection.md.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

_OUT = io.TextIOWrapper(open(sys.stdout.fileno(), "wb", closefd=False),
                        encoding="utf-8", errors="replace")


def say(*a) -> None:
    print(*a, file=_OUT)
    _OUT.flush()


sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import importlib.util

_spec = importlib.util.spec_from_file_location(
    "sw", os.path.join(os.path.dirname(os.path.abspath(__file__)), "sweep_ratings.py"))
sw = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sw)

WORKERS = 4
MIN_INTERVAL = 0.30          # seconds between requests, GLOBAL across workers
NEW_CSV = "research/analysts/new_actions.csv"
BUY_WORDS = ("Buy", "Strong Buy", "Outperform", "Overweight", "Positive")
_lock = threading.Lock()
_last = [0.0]


def throttled_get(url: str) -> str | None:
    with _lock:
        wait = MIN_INTERVAL - (time.time() - _last[0])
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.time()
    return sw.get(url)


def scan(syms: list[str], today: str) -> list[dict]:
    got: list[dict] = []
    done = [0]

    def one(s: str):
        page = throttled_get(f"https://stockanalysis.com/stocks/{s.lower()}/ratings/")
        rows = sw.parse(s, page, today) if page else []
        with _lock:
            done[0] += 1
            if done[0] % 100 == 0:
                say(f"  scanned {done[0]}/{len(syms)}")
        return rows

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for r in ex.map(one, syms):
            got += r
    return got


def parse_date(s: str):
    try:
        return dt.datetime.strptime(s, "%b %d, %Y")
    except Exception:
        return None


def show(rows: list[dict], title: str, days: int | None, buys: bool) -> list[dict]:
    now = dt.datetime.now()
    out = []
    for r in rows:
        d = parse_date(r.get("date", ""))
        if d is None:
            continue
        if days is not None and (now - d).days > days:
            continue
        if buys and not (r["action"] in ("Upgrade", "Upgrades", "Initiates")
                         and any(b in r["rating"] for b in BUY_WORDS)):
            continue
        r = dict(r)
        r["_d"] = d
        out.append(r)
    out.sort(key=lambda x: x["_d"], reverse=True)

    say("")
    say(f"=== {title}: {len(out)} ===")
    if not out:
        say("  (nothing)")
        return out
    say(f"{'SYMBOL':<8}{'ACTION':<12}{'RATING':<14}{'TARGET':>9}{'UPSIDE':>9}  "
        f"{'ANALYST':<24}{'FIRM':<24}DATE")
    say("-" * 118)
    for r in out[:80]:
        tgt = f"${r['target']}" if r.get("target") else "-"
        ups = f"{r['upside_pct']}%" if r.get("upside_pct") else "-"
        star = "*" if r["action"] in ("Upgrade", "Upgrades") else " "
        say(f"{star}{r['symbol']:<7}{r['action']:<12}{r['rating'][:13]:<14}"
            f"{tgt:>9}{ups:>9}  {r['analyst'][:23]:<24}{r['firm'][:23]:<24}"
            f"{r['_d']:%b %d}")
    if len(out) > 80:
        say(f"  ... {len(out) - 80} more (full list in {NEW_CSV})")
    return out


def write_new(rows: list[dict]) -> None:
    if not rows:
        return
    cols = [c for c in sw.FIELDS]
    with open(NEW_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    say(f"\nwrote {NEW_CSV}")


def run_once(n: int, days: int | None, buys: bool,
             analyst: str | None, firm: str | None,
             watch: str | None = None) -> None:
    if watch:
        # a focused list beats a wide sweep: Green (JFQA 2006) measures roughly
        # a 2-hour profitable window after public release, so latency matters
        # more than coverage. 150 names ~ 45s; 2,500 names ~ 12 min.
        if os.path.exists(watch):
            syms = [x.strip().upper() for x in open(watch) if x.strip()]
        else:
            syms = [x.strip().upper() for x in watch.split(",") if x.strip()]
    else:
        src = sw.UNIVERSE_RANKED if os.path.exists(sw.UNIVERSE_RANKED) else sw.UNIVERSE_ALL
        syms = [s.strip() for s in open(src) if s.strip()][:n]
    today = time.strftime("%Y-%m-%d")
    tape, seen = sw.load_tape()
    say(f"scanning {len(syms)} stocks with {WORKERS} workers "
        f"({MIN_INTERVAL:.2f}s between requests) | tape has {len(tape)} events")
    t0 = time.time()
    got = scan(syms, today)
    say(f"scan done in {(time.time()-t0)/60:.1f} min: {len(got)} rows parsed")

    fresh = [r for r in got if sw.key(r) not in seen]
    if fresh:
        sw.flush(fresh)
    say(f"{len(fresh)} NOT previously in the tape")

    pool = fresh
    if analyst:
        pool = [r for r in got if analyst.lower() in r["analyst"].lower()]
        show(pool, f"ALL actions by analyst matching '{analyst}'", days, buys)
    elif firm:
        pool = [r for r in got if firm.lower() in r["firm"].lower()]
        show(pool, f"ALL actions by firm matching '{firm}'", days, buys)
    else:
        shown = show(fresh, "NEW since last scan", days, buys)
        pool = shown
    write_new(pool)


def recent(days: int, buys: bool, analyst: str | None, firm: str | None) -> None:
    """Tape only. No network."""
    tape, _ = sw.load_tape()
    rows = tape
    if analyst:
        rows = [r for r in rows if analyst.lower() in r["analyst"].lower()]
    if firm:
        rows = [r for r in rows if firm.lower() in r["firm"].lower()]
    lab = f"last {days}d from local tape ({len(tape)} events)"
    write_new(show(rows, lab, days, buys))


def main() -> None:
    a = sys.argv[1:]

    def opt(flag, cast=str, default=None):
        return cast(a[a.index(flag) + 1]) if flag in a else default

    days = opt("--days", int, None)
    buys = "--buys" in a
    analyst = opt("--analyst")
    firm = opt("--firm")
    n = opt("--n", int, 800)
    watch = opt("--symbols")   # comma list or a file of tickers, one per line

    if "--recent" in a:
        recent(days if days is not None else 7, buys, analyst, firm)
        return

    every = opt("--live", int, None)
    if every:
        say(f"LIVE MODE: rescanning every {every} min. Ctrl+C to stop.")
        while True:
            say(f"\n{'='*70}\n{time.strftime('%Y-%m-%d %H:%M')}  scan starting")
            try:
                run_once(n, days, buys, analyst, firm, watch)
            except Exception as e:
                say(f"scan failed: {type(e).__name__}: {e}")
            say(f"sleeping {every} min")
            time.sleep(every * 60)
    else:
        run_once(n, days, buys, analyst, firm, watch)


if __name__ == "__main__":
    main()
