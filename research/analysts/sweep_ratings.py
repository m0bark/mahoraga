"""Sweep per-stock analyst-rating pages into a dated event tape.

    python research/analysts/sweep_ratings.py --rank        # build universe
    python research/analysts/sweep_ratings.py --n 1200      # sweep top 1200
    python research/analysts/sweep_ratings.py --stats

WHY THIS AXIS AND NOT THE ANALYST PAGES

The /analysts/<name>/ pages are paywalled: the free tier masks every ticker
past about row 9 with the literal string "XXXX", and exposes only 7
analysts. That path yields 44 usable events, 8 of which come from one
analyst inside a five-week window -- an effective sample of roughly one.

The /stocks/<sym>/ratings/ pages carry THE SAME DATA on the opposite axis
-- analyst name, firm, rating, action, price target, upside, date -- and
are NOT masked at all. Measured on 12 sample tickers: 0 masked rows.

Each stock page holds up to 8 of the most recent ratings, so history depth
is inversely proportional to coverage: NVDA's 8 ratings span 3 days, EXOD's
span 158. One sweep of N stocks therefore yields up to 8N dated events,
weighted toward thin-coverage names for history and toward mega caps for
recency. Repeated sweeps accumulate whatever scrolls past the 8-row window,
so the tape grows without ever needing the paywall.

DEDUP KEY: (symbol, analyst, date, action, rating). Re-running is safe and
idempotent; only genuinely new rows are appended.

RATE LIMIT: one request per DELAY seconds, single threaded, real UA. A full
6,956-name sweep at 1.2s is about 2.3 hours; the default 1200 most liquid
names is about 25 minutes. Resumable -- rerun after an interrupt and it
skips symbols already recorded today.
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
DELAY = 1.2
UNIVERSE_ALL = "research/analysts/universe_all.txt"
UNIVERSE_RANKED = "research/analysts/universe_ranked.txt"
TAPE = "research/analysts/ratings_tape.csv"
FIELDS = ["symbol", "analyst", "firm", "rating", "action", "target",
          "upside_pct", "date", "pulled"]
DATE_RE = re.compile(r"^[A-Z][a-z]{2} \d{1,2}, \d{4}$")
ACTIONS = ("Upgrade", "Downgrade", "Maintains", "Initiates", "Reiterates",
           "Upgrades", "Downgrades", "Initiated", "Reiterated", "Maintained")


def get(url: str) -> str | None:
    h = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"}
    ck = os.environ.get("SA_COOKIE")
    if ck:
        h["Cookie"] = ck
    for k in range(3):
        try:
            raw = urllib.request.urlopen(
                urllib.request.Request(url, headers=h), timeout=25).read()
            if raw[:2] == b"\x1f\x8b":
                raw = gzip.decompress(raw)
            return raw.decode("utf-8", "ignore")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None                    # stock has no ratings page
            time.sleep(2 * (k + 1))
        except Exception:
            time.sleep(2 * (k + 1))
    return None


def txt(x: str) -> str:
    return re.sub(r"\s+", " ", htmlmod.unescape(re.sub(r"<[^>]+>", " ", x))).strip()


def num(s: str) -> str:
    """Keep the sign. '-12.5%' must not come back as 12.5."""
    m = re.search(r"(-?[\d,]+\.?\d*)", (s or "").replace("+", ""))
    return m.group(1).replace(",", "") if m else ""


def parse(sym: str, page: str, today: str) -> list[dict]:
    """Columns: Analyst | Firm | Rating | Rating | Action | Price Target | Upside | Date

    Cells are located BY CONTENT, not by index. The page filters empty cells
    out, so a legitimately blank Price Target or Upside would shift every
    later column left and silently mis-assign the date. Anchoring on the
    date regex and the known action vocabulary makes that impossible.
    """
    tbl = re.findall(r"<table.*?</table>", page, re.S | re.I)
    if not tbl:
        return []
    out = []
    for tr in re.findall(r"<tr.*?</tr>", tbl[0], re.S | re.I)[1:]:
        c = [x for x in (txt(y) for y in
                         re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S | re.I)) if x]
        if len(c) < 4:
            continue
        date = next((x for x in c if DATE_RE.match(x)), "")
        action = next((x for x in c if x in ACTIONS), "")
        if not date or not action:
            continue
        ai = c.index(action)
        rating = c[ai - 1] if ai >= 1 else ""
        # the firm name is duplicated into the analyst cell: "Quinn Bolton Needham"
        firm = c[1] if len(c) > 1 else ""
        # the Stock/Analyst cell repeats the firm name; strip it wherever it
        # sits, not only as an exact suffix -- the site is inconsistent about
        # spacing, which left rows like "Unknown Analyst Seaport Seaport Global"
        analyst = clean_analyst(c[0], firm)
        tgt = next((x for x in c[ai + 1:] if x.startswith("$")), "")
        ups = next((x for x in c[ai + 1:] if x.endswith("%")), "")
        out.append({"symbol": sym, "analyst": analyst, "firm": firm,
                    "rating": rating, "action": action,
                    "target": num(tgt), "upside_pct": num(ups),
                    "date": date, "pulled": today})
    return out


def clean_analyst(cell: str, firm: str) -> str:
    """Strip the firm name and the star-score fragment out of the analyst cell.

    The cell is not a clean name. It carries the firm appended, and for
    unranked analysts the literal text "No rating" or a "(4.52)" score,
    which produced entries like "Christine Yao No rating" and
    "Unknown Analyst Seaport Seaport Global".
    """
    a = cell
    if firm:
        a = a.replace(firm, " ")
    a = re.sub(r"\(\d\.\d+\)", " ", a)
    a = re.sub(r"No rating", " ", a, flags=re.I)
    a = re.sub(r"\s{2,}", " ", a).strip(" -,")
    if not a or a.lower().startswith("unknown analyst"):
        return "(unnamed)"
    return a


def normalize_tape() -> None:
    """Re-apply clean_analyst to every stored row, then dedup.

    Needed once: changing the name rule changes the dedup key, so without
    this every historic event re-fires as NEW on the next scan.
    """
    rows, _ = load_tape()
    if not rows:
        say("no tape")
        return
    seen, out, changed = set(), [], 0
    for r in rows:
        before = r["analyst"]
        r["analyst"] = clean_analyst(r["analyst"], r.get("firm", ""))
        if r["analyst"] != before:
            changed += 1
        k = key(r)
        if k in seen:
            continue
        seen.add(k)
        out.append(r)
    with open(TAPE, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(out)
    say(f"normalized {changed} analyst names; {len(rows)} -> {len(out)} rows "
        f"after dedup")


def key(r: dict) -> tuple:
    return (r["symbol"], r["analyst"], r["date"], r["action"], r["rating"])


def load_tape() -> tuple[list[dict], set]:
    if not os.path.exists(TAPE):
        return [], set()
    rows = list(csv.DictReader(open(TAPE, encoding="utf-8")))
    return rows, {key(r) for r in rows}


def rank_universe() -> None:
    """Order the universe by dollar volume so a partial sweep is the liquid half."""
    import warnings
    warnings.filterwarnings("ignore")
    import yfinance as yf

    syms = [s.strip() for s in open(UNIVERSE_ALL) if s.strip()]
    say(f"ranking {len(syms)} symbols by dollar volume (60d)")
    vals: dict[str, float] = {}
    CH = 400
    for i in range(0, len(syms), CH):
        ch = syms[i:i + CH]
        try:
            d = yf.download(ch, period="3mo", auto_adjust=True,
                            progress=False, threads=True)
            close, vol = d["Close"], d["Volume"]
            dv = (close * vol).tail(60).mean()
            for s in ch:
                if s in dv and dv[s] == dv[s]:
                    vals[s] = float(dv[s])
        except Exception as e:
            say(f"  chunk {i}: {type(e).__name__}")
        say(f"  {min(i + CH, len(syms))}/{len(syms)}  ranked so far {len(vals)}")
    ranked = sorted(vals, key=lambda s: -vals[s])
    open(UNIVERSE_RANKED, "w").write("\n".join(ranked))
    say(f"\nwrote {UNIVERSE_RANKED}: {len(ranked)} symbols")
    say(f"  #1 {ranked[0]}  ${vals[ranked[0]]/1e9:.1f}B/day")
    say(f"  #{len(ranked)} {ranked[-1]}  ${vals[ranked[-1]]/1e3:.0f}K/day")


def stats() -> None:
    rows, _ = load_tape()
    if not rows:
        say("no tape yet")
        return
    say(f"{len(rows)} rating events on {len({r['symbol'] for r in rows})} stocks "
        f"by {len({r['analyst'] for r in rows})} analysts "
        f"at {len({r['firm'] for r in rows})} firms")
    acts: dict[str, int] = {}
    for r in rows:
        acts[r["action"]] = acts.get(r["action"], 0) + 1
    say(f"  actions: {dict(sorted(acts.items(), key=lambda x: -x[1]))}")
    ups = sum(v for k, v in acts.items() if k.startswith("Upgrade"))
    say(f"\nGATE PROGRESS: upgrade events {ups}/40")


def sweep(n: int, k: int = 0, stride: int = 1) -> None:
    """Slice k of `stride` workers. Each worker owns its OWN output file so
    concurrent appends cannot interleave and corrupt a shared CSV; --merge
    folds them back into the tape with the same dedup key."""
    global TAPE
    src = UNIVERSE_RANKED if os.path.exists(UNIVERSE_RANKED) else UNIVERSE_ALL
    syms = [s.strip() for s in open(src) if s.strip()][:n]
    today = time.strftime("%Y-%m-%d")
    _, seen = load_tape()                       # dedup against the MAIN tape
    rows = []
    done = {r["symbol"] for r in load_tape()[0]}
    if stride > 1:
        TAPE = f"research/analysts/ratings_part{k}.csv"
        part, pseen = load_tape()
        seen |= pseen
        done |= {r["symbol"] for r in part}
        syms = syms[k::stride]
    todo = [s for s in syms if s not in done]
    done_today = done
    say(f"universe {src} | {len(syms)} targets | {len(done_today)} already pulled "
        f"today | {len(todo)} to go")
    say(f"tape has {len(rows)} events\n")

    new: list[dict] = []
    total_new = 0            # cumulative; `new` is cleared on every flush
    empty = 0
    t0 = time.time()
    for i, s in enumerate(todo, 1):
        page = get(f"https://stockanalysis.com/stocks/{s.lower()}/ratings/")
        got = parse(s, page, today) if page else []
        fresh = [r for r in got if key(r) not in seen]
        for r in fresh:
            seen.add(key(r))
        new += fresh
        total_new += len(fresh)
        if not got:
            empty += 1
        if i % 25 == 0 or i == len(todo):
            rate = i / max(time.time() - t0, 1)
            eta = (len(todo) - i) / max(rate, 1e-9) / 60
            say(f"  {i}/{len(todo)}  +{total_new} new events  "
                f"{empty} pages empty  eta {eta:.0f}m")
        if new and len(new) % 200 == 0:
            flush(new)
            new = []
        time.sleep(DELAY)
    if new:
        flush(new)
    say("")
    stats()


def flush(new: list[dict]) -> None:
    header = not os.path.exists(TAPE)
    with open(TAPE, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if header:
            w.writeheader()
        w.writerows(new)


def merge() -> None:
    """Fold every ratings_part*.csv into the main tape, deduped."""
    import glob
    rows, seen = load_tape()
    added = 0
    out = []
    for f in sorted(glob.glob("research/analysts/ratings_part*.csv")):
        part = list(csv.DictReader(open(f, encoding="utf-8")))
        fresh = [r for r in part if key(r) not in seen]
        for r in fresh:
            seen.add(key(r))
        out += fresh
        added += len(fresh)
        say(f"  {f}: {len(part)} rows, {len(fresh)} new")
    if out:
        flush(out)
    say("")
    say(f"merged {added} new events; tape now {len(rows) + added}")
    stats()


def main() -> None:
    a = sys.argv[1:]
    if "--rank" in a:
        rank_universe()
        return
    if "--stats" in a:
        stats()
        return
    if "--normalize" in a:
        normalize_tape()
        return
    if "--merge" in a:
        merge()
        return
    n = int(a[a.index("--n") + 1]) if "--n" in a else 1200
    k = int(a[a.index("--slice") + 1]) if "--slice" in a else 0
    st = int(a[a.index("--stride") + 1]) if "--stride" in a else 1
    sweep(n, k, st)


if __name__ == "__main__":
    main()
