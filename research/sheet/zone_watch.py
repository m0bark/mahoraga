"""Fires the moment any stock touches its buy zone. Live prices, not the cache.

    python research/sheet/zone_watch.py --once      # one live check
    python research/sheet/zone_watch.py --loop 2    # every 2 minutes, forever
    python research/sheet/zone_watch.py --list      # what is closest right now

WHY THIS IS SEPARATE FROM alerts.py
alerts.py reads summary.csv, which is only as fresh as the last hourly build.
A stock can enter its zone, bounce, and leave again inside that hour and the
alert would never fire -- or worse, fire an hour late at a price you can no
longer get. This pulls LIVE quotes and compares them to a zone entry price
that was computed at the last build and does not move intraday.

WHY IT DOES NOT QUOTE ALL 500
Quoting the whole index every two minutes is ~360,000 requests a day and gets
you rate-limited by lunchtime. Only names within WATCH_BAND percent of their
zone entry can plausibly touch it in one interval, so only those are quoted --
typically 60-150 names, one batched request, about two seconds.

FIRING RULE
A symbol fires ONCE per crossing. It re-arms only after the price climbs back
above the entry price by RE_ARM percent, so a stock oscillating on the line
does not send forty messages. State lives in zone_state.json.
"""
from __future__ import annotations

import importlib.util
import io
import json
import os
import sys
import time
import warnings
from datetime import datetime, time as dtime

_OUT = io.TextIOWrapper(open(sys.stdout.fileno(), "wb", closefd=False),
                        encoding="utf-8", errors="replace")


def say(*a) -> None:
    print(*a, file=_OUT)
    _OUT.flush()


warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import yfinance as yf

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
STATE = os.path.join(HERE, "zone_state.json")
WATCH_BAND = 6.0      # quote anything within this % above its entry price
RE_ARM = 2.0          # must rise this % back above entry before it can fire again
MIN_RATE = None       # set a number to ignore low-quality names entirely


def _mod(name, path):
    sp = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


al = _mod("al", os.path.join(HERE, "alerts.py"))


def market_open() -> bool:
    """US cash session in local time is unknown, so this is deliberately loose:
    weekdays only, and a wide window. Better to check a few extra times than to
    miss an open because of a timezone assumption."""
    n = datetime.now()
    if n.weekday() >= 5:
        return False
    return dtime(13, 0) <= n.time() <= dtime(23, 59) or \
        dtime(0, 0) <= n.time() <= dtime(1, 30)


def load_state() -> dict:
    try:
        return json.load(open(STATE, encoding="utf-8"))
    except Exception:
        return {}


def save_state(d: dict) -> None:
    json.dump(d, open(STATE, "w", encoding="utf-8"), indent=1)


def candidates() -> pd.DataFrame:
    p = os.path.join(CACHE, "summary.csv")
    if not os.path.exists(p):
        return pd.DataFrame()
    d = pd.read_csv(p)
    need = {"symbol", "price", "zone_entry_price", "zone_status"}
    if not need <= set(d.columns):
        say("summary.csv has no zone_entry_price -- run build_workbook.py")
        return pd.DataFrame()
    d = d.dropna(subset=["zone_entry_price"])
    d = d[d["zone_entry_price"] > 0]
    if MIN_RATE is not None and "RATE" in d:
        d = d[pd.to_numeric(d["RATE"], errors="coerce") >= MIN_RATE]
    # a bottom-quartile name is flagged CHEAP FOR A REASON and has no
    # perfect_buy; do not wake anyone up for those
    if "buy_note" in d:
        d = d[~d["buy_note"].astype(str).str.startswith("CHEAP")]
    d["gap_pct"] = (d["price"] / d["zone_entry_price"] - 1) * 100
    return d[d["gap_pct"] <= WATCH_BAND].copy()


def live(symbols: list[str]) -> dict[str, float]:
    if not symbols:
        return {}
    try:
        q = yf.download(symbols, period="1d", interval="1m", progress=False,
                        threads=True, auto_adjust=False)["Close"]
        if isinstance(q, pd.Series):
            q = q.to_frame(symbols[0])
        return {c: float(q[c].dropna().iloc[-1]) for c in q.columns
                if q[c].notna().any()}
    except Exception as e:
        say(f"quote failed: {type(e).__name__}: {e}")
        return {}


def check(send: bool = True) -> int:
    c = candidates()
    if c.empty:
        say("no candidates near a zone")
        return 0
    syms = list(c["symbol"])
    say(f"{len(syms)} names within {WATCH_BAND:.0f}% of their zone entry "
        f"-- quoting live")
    px = live(syms)
    if not px:
        return 0
    st = load_state()
    # FIRST RUN SEEDING. Without this the very first check pushes a message for
    # every name that already happens to be sitting in its zone -- 19 of them
    # on the first live test. You want to be told about CROSSINGS, not about
    # the current state of the world, so the opening run records what is
    # already touching and sends nothing.
    seeding = not os.path.exists(STATE)
    if seeding:
        say("  first run: recording what is already in the zone, sending nothing")
    fired = 0
    MAX_PER_CYCLE = 8
    for _, r in c.iterrows():
        s = r["symbol"]
        if s not in px:
            continue
        p, entry = px[s], float(r["zone_entry_price"])
        was = st.get(s, {}).get("fired", False)
        if p <= entry and not was:
            gap = (p / entry - 1) * 100
            msg = (f"<b>ZONE TOUCH — {s}</b>\n"
                   f"live ${p:,.2f}  (zone entry ${entry:,.2f}, {gap:+.2f}%)\n"
                   f"buy zone ${r.get('buy_zone_low', float('nan')):,.2f}"
                   f" - ${r.get('buy_zone_high', float('nan')):,.2f}\n"
                   f"rate {r.get('RATE', float('nan')):.0f}/100"
                   f"   halal {r.get('halal_auto', '?')}"
                   f"   RSI {r.get('rsi14', float('nan')):.0f}\n"
                   f"support ${r.get('support', float('nan')):,.2f}"
                   f"   200d {r.get('vs_200sma', '?')}\n"
                   f"\nPROBATION: the buy-zone rule backtests NEGATIVE "
                   f"(-0.23%/qtr vs random, ahead on 46% of dates). "
                   f"This is a heads-up, not a recommendation.")
            say(f"  TOUCH  {s}  ${p:,.2f} <= ${entry:,.2f}"
                + ("  (seeded, not sent)" if seeding else ""))
            if send and not seeding:
                if fired < MAX_PER_CYCLE:
                    al.send(msg)
                elif fired == MAX_PER_CYCLE:
                    al.send("<b>...and more</b>" + "\n"
                            f"More than {MAX_PER_CYCLE} names touched their "
                            f"zone this cycle. Open the desk UI or run "
                            f"zone_watch.py --list.")
            st[s] = {"fired": True, "at": datetime.now().isoformat(timespec="minutes"),
                     "price": p}
            fired += 1
        elif was and p > entry * (1 + RE_ARM / 100):
            st[s] = {"fired": False}
            say(f"  re-arm {s} (back {((p/entry-1)*100):+.1f}% above entry)")
    save_state(st)
    if not fired:
        near = c.nsmallest(3, "gap_pct")
        say("  nothing touched. closest: " + ", ".join(
            f"{r.symbol} {r.gap_pct:+.2f}%" for r in near.itertuples()))
    return fired


def listing() -> None:
    c = candidates()
    if c.empty:
        say("nothing near a zone")
        return
    c = c.sort_values("gap_pct")
    say(f"{'sym':<7}{'price':>10}{'entry':>10}{'gap':>8}{'$ away':>9}"
        f"{'rate':>6}  status")
    say("-" * 62)
    for r in c.head(25).itertuples():
        say(f"{r.symbol:<7}{r.price:>10.2f}{r.zone_entry_price:>10.2f}"
            f"{r.gap_pct:>7.2f}%{r.price - r.zone_entry_price:>9.2f}"
            f"{getattr(r, 'RATE', float('nan')):>6.0f}  {r.zone_status}")
    say("-" * 62)
    say(f"{len(c)} names within {WATCH_BAND:.0f}% of entry")


if __name__ == "__main__":
    a = sys.argv[1:]
    if "--list" in a:
        listing()
    elif "--loop" in a:
        every = float(a[a.index("--loop") + 1])
        say(f"watching every {every} min. Ctrl+C to stop.")
        while True:
            try:
                if market_open():
                    check()
                else:
                    say(f"{datetime.now():%H:%M} market closed, idling")
            except Exception as e:
                say(f"check failed: {type(e).__name__}: {e}")
            time.sleep(every * 60)
    else:
        check(send="--dry" not in a)
