"""RETRACTED 2026-09-06 -- this script produced a sign-flipped result.

DO NOT USE. Superseded by revision_study.py. Kept only as the record of
the error, because the error is the useful part.

WHAT WENT WRONG
The random-entry control drew from the entire 15-month downloaded history
(line 88, start="2025-06-01" -> ~254 eligible entry dates) while the
scorable events occupied two narrow calendar bands: 8 ross-seymore semis
in 2026-04-30..2026-06-04, and 2 events in Aug/Sep 2025. So

    edge = excess - ctrl_mean
         = (date selection) + (event-period regime - full-period regime)

and the second term was 8x the first with the OPPOSITE sign. For those 8
names the full-window control is +13.06% while the same statistic confined
to the event band is -12.75% -- a 25.8pp gap. The printed headline

    ALL events   h=63   n=10   excess -14.45%   random +4.04%   edge -18.49%   t=-2.67

therefore measured "semis, Apr-Jun 2026" and not the analyst. Calendar-
matched, the same events come out +3.3pp AHEAD of a band-matched dart.

A SECOND, INDEPENDENT DEFECT
The paired t treated 10 events as independent when 8 came from one analyst
in one sector with 83% mean window overlap. Block-shift randomization puts
the honest |t| at 1.09, not 2.67 -- a design effect of 5.7, n_eff = 1.8.

Neither the negative result nor its significance survives. The correct
reading of this dataset is that it was uninformative in both directions.

Also confirmed by audit and fixed in revision_study.py: `fwd(...) or np.nan`
turned a real 0.0 return into NaN; rng.integers(0, len-h-1) never sampled
the last legal date; searchsorted clamped pre-history events to index 0 and
fabricated returns; 12 tests were attempted and 8 printed with no
multiplicity control; two printed rows were byte-identical and read as
replication; two crypto names were benchmarked to XLK.

Original docstring follows.

Event study on DATED analyst actions from events.csv.

    python research/analysts/event_study.py

WHAT IS BEING TESTED
For each dated rating action, the stock's return from the event date
forward, MINUS the sector ETF's return over the identical window. Sector,
not SPY, because these analysts are sector specialists and sector beta is
what made the leaderboard look skilful in the first place.

THE CONTROL THAT DECIDES IT
A raw positive excess return proves nothing on its own -- these are mostly
semis and financials in a window where those ran. So every event is paired
with RANDOM-ENTRY draws: the same stock, the same holding length, but
entered on random dates inside the same overall window. If the analyst's
chosen date does not beat a dart thrown at his own coverage list over the
same period, the date carried no information and there is nothing to copy.

KNOWN LIMITS, stated up front so the number is read correctly:
  * The page shows the LATEST action per (analyst, stock), not a full
    history. This is a snapshot of standing positions with their last-update
    date -- not a clean event tape.
  * The free tier exposes 7 analysts and ~9 rows each: 44 events. With
    n=44 the standard error on a mean excess return is large; this can
    refute a big effect, it cannot establish a small one.
  * Window is Apr-Sep 2026 only. One regime.
"""
from __future__ import annotations

import csv
import io
import sys
import warnings

_OUT = io.TextIOWrapper(open(sys.stdout.fileno(), "wb", closefd=False),
                        encoding="utf-8", errors="replace")


def say(*a) -> None:
    print(*a, file=_OUT)
    _OUT.flush()


warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import yfinance as yf

EVENTS = "research/analysts/events.csv"
HORIZONS = [21, 63]          # ~1 month, ~3 months of trading days
N_RANDOM = 200               # random-entry draws per event
ANALYST_SECTOR = {
    "ross-seymore": "XLK", "srini-pajjuri": "XLK", "shrenik-kothari": "XLK",
    "bill-papanastasiou": "XLK", "sanjay-sakhrani": "XLF",
    "paul-newsome": "XLF", "phil-hardie": "XLF",
}


def load() -> pd.DataFrame:
    df = pd.DataFrame(list(csv.DictReader(open(EVENTS, encoding="utf-8"))))
    df["edate"] = pd.to_datetime(df["date"], format="%b %d, %Y", errors="coerce")
    for c in ("target_old", "target_new"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["bench"] = df["analyst"].map(ANALYST_SECTOR).fillna("SPY")
    df = df.dropna(subset=["edate"])
    df["revision"] = np.where(
        df.target_old.notna() & (df.target_new > df.target_old), "RAISED",
        np.where(df.target_old.notna() & (df.target_new < df.target_old),
                 "CUT", "none"))
    return df


def fwd(px: pd.Series, i: int, h: int) -> float | None:
    if i < 0 or i + h >= len(px):
        return None
    a, b = px.iloc[i], px.iloc[i + h]
    return None if not (np.isfinite(a) and np.isfinite(b) and a > 0) else b / a - 1


def main() -> None:
    if "--force" not in sys.argv:
        say(__doc__.split("Original docstring follows.")[0])
        say("Refusing to run. Use revision_study.py. (--force to override.)")
        return
    df = load()
    syms = sorted(set(df.symbol))
    benches = sorted(set(df.bench))
    say(f"{len(df)} dated events | {len(syms)} symbols | "
        f"{df.edate.min():%Y-%m-%d} .. {df.edate.max():%Y-%m-%d}")

    px = yf.download(syms + benches, start="2025-06-01", end="2026-09-06",
                     auto_adjust=True, progress=False, threads=True)["Close"]
    px = px.dropna(how="all")
    say(f"price history: {len(px)} trading days, "
        f"{px.notna().any().sum()}/{len(syms) + len(benches)} tickers resolved\n")

    rng = np.random.default_rng(7)
    rows = []
    for _, e in df.iterrows():
        if e.symbol not in px or e.bench not in px:
            continue
        s, b = px[e.symbol].dropna(), px[e.bench].dropna()
        common = s.index.intersection(b.index)
        s, b = s.loc[common], b.loc[common]
        i = common.searchsorted(e.edate)          # first trading day on/after event
        for h in HORIZONS:
            rs, rb = fwd(s, i, h), fwd(b, i, h)
            if rs is None or rb is None:
                continue
            # same stock, same holding length, random entry dates
            hi = len(common) - h - 1
            if hi <= 1:
                continue
            draws = rng.integers(0, hi, N_RANDOM)
            ctrl = np.array([(fwd(s, int(j), h) or np.nan)
                             - (fwd(b, int(j), h) or np.nan) for j in draws])
            rows.append({"symbol": e.symbol, "analyst": e.analyst,
                         "action": e.action, "revision": e.revision, "h": h,
                         "excess": rs - rb,
                         "ctrl_mean": float(np.nanmean(ctrl))})
    r = pd.DataFrame(rows)
    if r.empty:
        say("no scorable events -- all too recent for the horizon")
        return

    say(f"{'group':<26}{'h':>4}{'n':>5}{'excess':>10}{'random':>10}"
        f"{'edge':>9}{'t':>7}")
    say("-" * 71)

    def line(lbl, d):
        for h in HORIZONS:
            g = d[d.h == h]
            if len(g) < 3:
                continue
            diff = g.excess - g.ctrl_mean
            t = diff.mean() / (diff.std(ddof=1) / np.sqrt(len(g))) if len(g) > 1 else 0
            say(f"{lbl:<26}{h:>4}{len(g):>5}{g.excess.mean() * 100:>9.2f}%"
                f"{g.ctrl_mean.mean() * 100:>9.2f}%{diff.mean() * 100:>8.2f}%{t:>7.2f}")

    line("ALL events", r)
    for rv in ("RAISED", "CUT"):
        line(f"target {rv}", r[r.revision == rv])
    for ac in sorted(set(r.action)):
        line(f"action {ac}", r[r.action == ac])
    say("-" * 71)
    say("excess = stock minus its SECTOR ETF over the window")
    say("random = same stock, same holding length, random entry in the window")
    say("edge   = excess - random. THIS is the analyst's date selection.")
    say("t      = paired t on (excess - random) across events")
    say("\nWith n this small, |t| < 2 means the data cannot distinguish the")
    say("analyst's timing from a dart thrown at his own coverage list.")
    r.to_csv("research/analysts/event_study_out.csv", index=False)
    say("\nwrote research/analysts/event_study_out.csv")


if __name__ == "__main__":
    main()
