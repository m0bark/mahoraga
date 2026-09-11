"""24/7 analyst-rating catcher over the top N liquid US stocks.

    python research/sheet/tape_watch.py --once          # one pass, then exit
    python research/sheet/tape_watch.py --loop 30       # forever, every 30 min
    python research/sheet/tape_watch.py --follow "Quinn Bolton"
    python research/sheet/tape_watch.py --following     # show the follow list

WHAT IT DOES
Sweeps stockanalysis.com's per-stock ratings pages (NOT the analyst pages --
those are paywalled and blank the ticker after row 9), appends anything new to
the shared tape, and pushes a Telegram message for any rating action by an
analyst or firm on your FOLLOW LIST.

WHY IT SWEEPS IN SHARDS
The full universe is ~1,000 names at ~1 request per 0.3s across 4 workers, so
one complete pass is roughly 75 seconds of continuous requests. Running that
every 30 minutes all day is 48 full sweeps and ~48,000 requests, which is rude
and gets you blocked. Instead each pass covers ONE SHARD of the universe and
the shard rotates, so the whole list is covered every SHARDS passes while the
request rate stays low. Mega caps get their own always-on shard because they
are where actions land most often.

FOLLOW LIST  (research/sheet/following.csv)
    kind,value,note
    analyst,Quinn Bolton,semis guy
    firm,Needham,
Adding a row is enough -- the next pass picks it up, no restart. Any action by
a followed analyst or firm fires a Telegram push immediately.
"""
from __future__ import annotations

import csv
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


import importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
ANALYSTS = os.path.join(HERE, "..", "analysts")


def _load(name, path):
    sp = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


sw = _load("sw", os.path.join(ANALYSTS, "sweep_ratings.py"))
al = _load("al", os.path.join(HERE, "alerts.py"))

UNIVERSE_N = 1000
SHARDS = 8
WORKERS = 4
MIN_INTERVAL = 0.30
FOLLOW = os.path.join(HERE, "following.csv")
STATE = os.path.join(HERE, "tape_state.txt")
_lock = threading.Lock()
_last = [0.0]


def universe(n: int = UNIVERSE_N) -> list[str]:
    p = os.path.join(ANALYSTS, "universe_ranked.txt")
    if not os.path.exists(p):
        p = os.path.join(ANALYSTS, "universe_all.txt")
    return [s.strip() for s in open(p) if s.strip()][:n]


def follow_list() -> list[dict]:
    if not os.path.exists(FOLLOW):
        with open(FOLLOW, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["kind", "value", "note"])
            w.writeheader()
            w.writerow({"kind": "firm", "value": "Needham", "note": "example"})
        return follow_list()
    return [r for r in csv.DictReader(open(FOLLOW, encoding="utf-8"))
            if (r.get("value") or "").strip()]


def add_follow(value: str, kind: str = "analyst") -> None:
    rows = follow_list()
    if any((r["value"] or "").lower() == value.lower() for r in rows):
        say(f"already following {value}")
        return
    with open(FOLLOW, "a", newline="", encoding="utf-8") as f:
        csv.DictWriter(f, fieldnames=["kind", "value", "note"]).writerow(
            {"kind": kind, "value": value, "note": ""})
    say(f"now following {kind}: {value}")
    say("The next sweep picks this up automatically -- no restart needed.")


def shard_index() -> int:
    try:
        return int(open(STATE).read().strip()) % SHARDS
    except Exception:
        return 0


def bump_shard() -> None:
    open(STATE, "w").write(str((shard_index() + 1) % SHARDS))


def throttled(url: str):
    with _lock:
        wait = MIN_INTERVAL - (time.time() - _last[0])
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.time()
    return sw.get(url)


def sweep(syms: list[str]) -> list[dict]:
    today = time.strftime("%Y-%m-%d")
    got: list[dict] = []

    def one(s: str):
        page = throttled(f"https://stockanalysis.com/stocks/{s.lower()}/ratings/")
        return sw.parse(s, page, today) if page else []

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for rows in ex.map(one, syms):
            got += rows
    return got


def matches(row: dict, follows: list[dict]) -> str | None:
    a = (row.get("analyst") or "").lower()
    f = (row.get("firm") or "").lower()
    for w in follows:
        v = (w["value"] or "").strip().lower()
        k = (w.get("kind") or "analyst").strip().lower()
        if not v:
            continue
        if k == "analyst" and v in a:
            return f"analyst {w['value']}"
        if k == "firm" and v in f:
            return f"firm {w['value']}"
        if k == "symbol" and v == (row.get("symbol") or "").lower():
            return f"symbol {w['value']}"
    return None


def one_pass(full: bool = False) -> int:
    uni = universe()
    i = shard_index()
    if full:
        syms, label = uni, "FULL"
    else:
        # shard 0 is always the 120 most liquid names -- that is where rating
        # actions actually land, so they get checked every pass
        top = uni[:120]
        rest = uni[120:]
        syms = top + rest[i::SHARDS]
        label = f"shard {i + 1}/{SHARDS}"
    _, seen = sw.load_tape()
    t0 = time.time()
    got = sweep(syms)
    fresh = [r for r in got if sw.key(r) not in seen]
    if fresh:
        sw.flush(fresh)
    say(f"{label}: {len(syms)} stocks, {len(got)} rows, {len(fresh)} new "
        f"({time.time() - t0:.0f}s)")

    follows = follow_list()
    hits = [(r, m) for r in fresh if (m := matches(r, follows))]
    for r, why in hits[:20]:
        line = (f"{r['symbol']} {r['action']} -> {r['rating']}"
                + (f" PT ${r['target']}" if r.get("target") else "")
                + f"\n  {r['analyst']} / {r['firm']} ({r['date']})"
                + f"\n  matched: {why}")
        say(f"  FOLLOW HIT  {r['symbol']} {r['action']} {r['analyst']}")
        al.send(f"<b>FOLLOWED ANALYST</b>\n{line}")
    if not full:
        bump_shard()
    return len(fresh)


if __name__ == "__main__":
    a = sys.argv[1:]
    if "--follow" in a:
        i = a.index("--follow")
        kind = "firm" if "--firm" in a else "analyst"
        add_follow(a[i + 1], kind)
    elif "--following" in a:
        for r in follow_list():
            say(f"  {r.get('kind', 'analyst'):<9}{r['value']:<32}{r.get('note', '')}")
    elif "--loop" in a:
        every = int(a[a.index("--loop") + 1])
        say(f"looping every {every} min, {SHARDS} shards "
            f"(full universe covered every {SHARDS * every} min). Ctrl+C to stop.")
        while True:
            try:
                one_pass()
            except Exception as e:
                say(f"pass failed: {type(e).__name__}: {e}")
            time.sleep(every * 60)
    else:
        one_pass(full="--full" in a)
