"""Does a good company make the trigger work? Measured, not argued.

    python research/sheet/trigger_quality.py

THE REQUEST THIS ANSWERS
"Combine the trigger with good fundamentals, because if we buy a bad company
at a bad price of course it will fall."

That is the right instinct and it is exactly what this project has twice
measured going the other way. Both of those measurements have a problem, which
is why this test exists rather than a restatement of them:

  card 2026-08-30  claimed buying dips in quality names cost -5.19%/yr
  card 2026-08-31  measured the opposite, deep-dip quintile +12.02%/yr
                   against the near-high quintile's +8.17%
  and card 2026-08-31 also logged that legs 4 and 5 of its quality score
                   populated ZERO times out of 500 -- both improvement legs

So the two results contradict each other, and the screen that produced them was
a degraded static score missing the trend legs. pit_quality.py rebuilt the score
from SEC filings with all nine legs populating. This is the first honest look.

WHAT IS BEING CUT
The 27,515 filled trigger trades from trigger_diagnose.py, split by the F-Score
that was PUBLICLY KNOWN on the day the trigger was armed. The alignment is on
the SEC filing date, so a score used on 2015-04-30 comes from a filing actually
filed on or before 2015-04-30.

THREE OUTCOMES ARE REPORTED, because the choice of exit changes the answer:
  pct          the trigger as tested: stop at support, target at resistance
  pct_worst    the same, but the stop fills at the low of the bar that
               triggered it, which is the pessimistic end of the fill bracket
  nostop_pct   no stop at all, exit at the target or after 126 days

THE BAR THIS HAS TO CLEAR
Five quintiles means five chances to find something. A top-minus-bottom spread
is only interesting if it is monotonic across the middle as well, and if the
t-statistic clears the multiple-testing bar rather than the usual 1.96. With
five buckets that bar is sqrt(2*ln(5)) = 1.79 for a one-off look, and this file
reports the spread's own t so the comparison is visible rather than implied.
"""
from __future__ import annotations

import io
import os
import sys

_OUT = io.TextIOWrapper(open(sys.stdout.fileno(), "wb", closefd=False),
                        encoding="utf-8", errors="replace")


def say(*a) -> None:
    print(*a, file=_OUT)
    _OUT.flush()


import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
LONG = os.path.join(HERE, "cache_long")

N_BUCKETS = 5
SLOTS = 10
POS_PCT = 0.09
START_CASH = 100_000.0
MT_BAR = float(np.sqrt(2 * np.log(N_BUCKETS)))   # 1.79 for five looks


def load() -> pd.DataFrame:
    t = pd.read_csv(os.path.join(LONG, "trigger_trades.csv"),
                    parse_dates=["date"])
    q = pd.read_csv(os.path.join(LONG, "pit_fscore.csv"), parse_dates=["filed"])
    say(f"{len(t):,} trigger trades | {len(q):,} filing-dated quality records")

    # PIT JOIN. One merge_asof per symbol on the filing date, backward, so the
    # score attached to a trade is the latest one FILED on or before the day the
    # trigger was armed. Doing this as a single global merge_asof would let one
    # symbol's filing leak onto another symbol's trade.
    out = []
    qi = {s: g.sort_values("filed") for s, g in q.groupby("symbol")}
    for s, g in t.groupby("sym"):
        qg = qi.get(s)
        g = g.sort_values("date")
        if qg is None:
            g["fscore_pct"] = np.nan
            g["fscore_legs"] = np.nan
            out.append(g)
            continue
        m = pd.merge_asof(
            g, qg[["filed", "fscore_pct", "legs_available"]],
            left_on="date", right_on="filed", direction="backward")
        m = m.rename(columns={"legs_available": "fscore_legs"})
        m["stale_days"] = (m["date"] - m["filed"]).dt.days
        out.append(m)
    j = pd.concat(out, ignore_index=True)
    have = j["fscore_pct"].notna()
    say(f"quality known for {have.sum():,} of {len(j):,} trades "
        f"({have.mean() * 100:.1f}%)")
    if "stale_days" in j:
        say(f"median filing age at the trigger: "
            f"{j.loc[have, 'stale_days'].median():.0f} days")
        say("  that staleness is the mechanism to keep in mind. The filing is")
        say("  two months old and the price is current, so a healthy filing")
        say("  beside a falling price can mean the market knows something the")
        say("  filing does not yet contain.")
    return j[have].copy()


def buckets(j: pd.DataFrame) -> pd.DataFrame:
    """Quintiles cut WITHIN each month, not across the whole history. A global
    cut would load the top bucket with whatever years happened to have strong
    balance sheets and turn a quality test into a calendar test."""
    j = j.copy()
    j["q"] = (j.groupby("date")["fscore_pct"]
              .transform(lambda s: pd.qcut(s.rank(method="first"), N_BUCKETS,
                                           labels=False, duplicates="drop")
                         if s.notna().sum() >= N_BUCKETS else np.nan))
    return j.dropna(subset=["q"])


def spread_t(hi: pd.Series, lo: pd.Series) -> float:
    """Welch t on the top-minus-bottom difference in mean percent return."""
    if len(hi) < 2 or len(lo) < 2:
        return float("nan")
    se = np.sqrt(hi.var(ddof=1) / len(hi) + lo.var(ddof=1) / len(lo))
    return float((hi.mean() - lo.mean()) / se) if se > 0 else float("nan")


def simulate(t: pd.DataFrame, exit_col: str) -> float:
    """Same slot-limited cash-account simulation as trigger_diagnose.py, so the
    numbers are comparable to the -35.6% QC run rather than to a per-trade
    average."""
    need = {"entry_i", "exit_i", "entry_px", exit_col}
    if not need.issubset(t.columns) or t.empty:
        return float("nan")
    df = t.dropna(subset=list(need)).sort_values("entry_i")
    if df.empty:
        return float("nan")
    by_entry: dict = {}
    for rec in df.itertuples():
        by_entry.setdefault(int(rec.entry_i), []).append(rec)
    exits: dict = {}
    cash = START_CASH
    book: dict = {}
    nxt = 0
    for i in range(int(df.entry_i.min()), int(df.exit_i.max()) + 1):
        for key in exits.pop(i, []):
            sh, _cb, xp = book.pop(key)
            cash += sh * xp
        for rec in by_entry.get(i, []):
            if len(book) >= SLOTS:
                continue
            equity = cash + sum(sh * cb for sh, cb, _ in book.values())
            want = equity * POS_PCT
            if want > cash or rec.entry_px <= 0:
                continue
            nxt += 1
            book[nxt] = (want / rec.entry_px, rec.entry_px,
                         float(getattr(rec, exit_col)))
            cash -= want
            exits.setdefault(int(rec.exit_i), []).append(nxt)
    cash += sum(sh * xp for sh, _cb, xp in book.values())
    return cash


def table(j: pd.DataFrame, col: str, label: str) -> None:
    say("")
    say("=" * 74)
    say(f"  {label}")
    say("=" * 74)
    say(f"  {'quality':<14}{'n':>8}{'win%':>8}{'mean':>10}{'median':>10}"
        f"{'portfolio':>14}")
    say("  " + "-" * 70)
    names = ["Q1 worst", "Q2", "Q3", "Q4", "Q5 best"]
    for b in range(N_BUCKETS):
        g = j[j.q == b]
        if g.empty:
            continue
        wr = (g.out == "win").mean() * 100 if "out" in g else float("nan")
        # the ledger stores an exit PRICE and exit BAR only for the stopped
        # variants. The no-stop variant has a return but no exit index, so its
        # portfolio cannot be simulated from this file and is shown as n/a
        # rather than silently reusing the stopped exits.
        xcol = {"pct": "exit_px", "pct_worst": "exit_worst"}.get(col)
        eq = simulate(g, xcol) if xcol else float("nan")
        eqs = f"${eq:,.0f}" if np.isfinite(eq) else "n/a"
        say(f"  {names[b]:<14}{len(g):>8,}{wr:>7.1f}%{g[col].mean():>+9.2f}%"
            f"{g[col].median():>+9.2f}%{eqs:>14}")
    say("  " + "-" * 70)
    hi = j.loc[j.q == N_BUCKETS - 1, col].dropna()
    lo = j.loc[j.q == 0, col].dropna()
    if len(hi) and len(lo):
        d = hi.mean() - lo.mean()
        tt = spread_t(hi, lo)
        verdict = ("clears" if abs(tt) > MT_BAR else "does NOT clear")
        say(f"  best minus worst: {d:+.2f}%   t = {tt:+.2f}   "
            f"{verdict} the {MT_BAR:.2f} bar")
        mono = [j.loc[j.q == b, col].mean() for b in range(N_BUCKETS)]
        inc = all(mono[i] <= mono[i + 1] for i in range(len(mono) - 1))
        dec = all(mono[i] >= mono[i + 1] for i in range(len(mono) - 1))
        say(f"  monotonic: {'yes, rising' if inc else 'yes, falling' if dec else 'NO'}"
            f"   ({' '.join(f'{m:+.2f}' for m in mono)})")
        if not inc and not dec:
            say("  A non-monotonic spread is the signature of noise. The top and")
            say("  bottom of five buckets will always differ by something.")


def main() -> None:
    j = load()
    if j.empty:
        say("no overlap between the trade ledger and the quality panel")
        return
    j = buckets(j)
    say(f"\nbucketed {len(j):,} trades into {N_BUCKETS} within-month quintiles")

    table(j, "pct", "TRIGGER AS TESTED -- stop at support, target at resistance")
    table(j, "pct_worst", "SAME TRADES, pessimistic stop fill (at the bar low)")
    table(j, "nostop_pct", "NO STOP -- target or 126 days, the version that made money")

    # the comparison that actually decides the user's question
    say("")
    say("=" * 74)
    say("  DOES QUALITY HELP AT ALL? top two quintiles vs bottom two")
    say("=" * 74)
    say(f"  {'exit rule':<34}{'good':>11}{'bad':>11}{'good-bad':>12}{'t':>8}")
    say("  " + "-" * 70)
    for col, lab in (("pct", "stop at support"),
                     ("pct_worst", "stop at the bar low"),
                     ("nostop_pct", "no stop, 126-day cap")):
        good = j.loc[j.q >= N_BUCKETS - 2, col].dropna()
        bad = j.loc[j.q <= 1, col].dropna()
        if not len(good) or not len(bad):
            continue
        say(f"  {lab:<34}{good.mean():>+10.2f}%{bad.mean():>+10.2f}%"
            f"{good.mean() - bad.mean():>+11.2f}%{spread_t(good, bad):>+8.2f}")
    say("")
    say(f"  A spread needs |t| > {MT_BAR:.2f} to survive having looked five ways,")
    say("  and it needs the middle buckets to line up. One without the other is")
    say("  a coincidence with a good story attached.")

    say("")
    say("=" * 74)
    say("  AND THE REVERSE QUESTION: is the trigger helping quality, or hurting it?")
    say("=" * 74)
    say("  Quality alone, with no trigger and no stop, is the comparison that")
    say("  card 2026-08-30 found beat everything at 12.09%/yr. If the best")
    say("  quality quintile inside the trigger set cannot beat the trigger's")
    say("  own average by a clear margin, then fundamentals are not rescuing")
    say("  this mechanic and the honest move is to drop the mechanic, not to")
    say("  add another filter to it.")
    base = j["nostop_pct"].mean()
    best = j.loc[j.q == N_BUCKETS - 1, "nostop_pct"].mean()
    say(f"\n  all trigger trades, no stop:        {base:+.2f}%")
    say(f"  best-quality quintile, no stop:     {best:+.2f}%")
    say(f"  quality adds:                       {best - base:+.2f}%")


if __name__ == "__main__":
    main()
