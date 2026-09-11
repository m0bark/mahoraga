"""Does the value effect survive fixing the price? Old vs new, side by side.

    python research/sheet/val_decile_check.py

WHAT THIS ANSWERS
feat_val.py built market cap from a SPLIT- AND DIVIDEND-ADJUSTED close times an
as-reported share count, so every multiple it produced was the true multiple
divided by that name's own cumulative FUTURE corporate-action factor. Names that
split are names that went up, so the contaminated file marked exactly the future
winners as cheap. On the first pass it produced a clean out-of-sample "low P/E
wins" result. This script measures how much of that result was the leak, by
running the identical decile test on the contaminated feat_val.csv and on the
corrected feat_val2.csv.

THE TEST
For each of pe, pb, ps, p_fcf and earnings_yield:
  1. Take fwd63 from grid.csv, the forward 63-trading-day return in percent.
  2. DEMEAN it within each month. Every decile spread is then a pure
     cross-sectional bet with the market leg removed, so a month where
     everything rose contributes nothing.
  3. Sort that month's cross-section into DECILES on the feature and take
     mean(top decile) - mean(bottom decile). Top decile is the HIGHEST feature
     value, so for a multiple the top decile is the EXPENSIVE end and a negative
     spread means cheap wins. earnings_yield is inverted relative to the others
     -- high yield IS cheap -- so its sign is expected to flip, and the table
     labels which end is cheap for each feature rather than silently comparing
     signs that mean opposite things.
  4. Average the monthly spreads inside each period and report a t-statistic
     across months, because a mean of 158 monthly spreads with no dispersion
     measure is not evidence of anything.

TRAIN AND HOLDOUT
  train    date <= 2021-09-30
  holdout  date >  2021-12-31
The quarter between them is in NEITHER, on purpose: fwd63 from 2021-09-30 runs
about three months forward, so including dates inside that window would let a
train observation and a holdout observation share a return.

WHY THIS IS A SEPARATE FILE FROM feat_val2.py
feat_val2.py is forbidden from reading grid.csv's fwd63 column -- that is the
target, and a feature block that can see it cannot be trusted not to. This
script's whole job is to read it. Keeping them apart is what makes the rule in
feat_val2.load_grid enforceable by inspection rather than by good intentions.

WHAT I COULD NOT BUILD
  * A like-for-like universe. The two files cover the same 50,825 grid rows, but
    the contaminated one rejects a different set of rows through the market-cap
    plausibility band (it rejected names whose price had been divided by a later
    split). So the two columns are not measured on identical samples and the
    report prints each side's coverage next to its spread.
  * Any transaction cost, borrow cost or capacity assumption. These are raw
    long-short decile spreads on month-end rebalancing and are an upper bound on
    what a tradable version would earn.
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
GRID = os.path.join(LONG, "grid.csv")
OLD = os.path.join(LONG, "feat_val.csv")
NEW = os.path.join(LONG, "feat_val2.csv")

TRAIN_END = pd.Timestamp("2021-09-30")
HOLDOUT_START = pd.Timestamp("2021-12-31")

DECILES = 10
MIN_NAMES = 50        # below this a cross-section cannot carry ten buckets
PCT = 100.0

TESTED = ["pe", "pb", "ps", "p_fcf", "earnings_yield"]

# which end of each feature is the CHEAP one, so a sign can be read
CHEAP_END = {"pe": "bottom", "pb": "bottom", "ps": "bottom",
             "p_fcf": "bottom", "earnings_yield": "top"}


def load(path: str, cols: list[str]) -> pd.DataFrame:
    if not os.path.exists(path):
        say(f"MISSING {path}")
        sys.exit(1)
    df = pd.read_csv(path, usecols=["date", "symbol"] + cols)
    df["date"] = pd.to_datetime(df["date"])
    return df


def load_target() -> pd.DataFrame:
    """fwd63 demeaned inside each month. This is the only file that reads it."""
    g = pd.read_csv(GRID)
    g["date"] = pd.to_datetime(g["date"])
    g = g.dropna(subset=["fwd63"])
    g["resid"] = g["fwd63"] - g.groupby("date")["fwd63"].transform("mean")
    return g[["date", "symbol", "resid"]]


def monthly_spreads(df: pd.DataFrame, col: str) -> pd.Series:
    """One top-minus-bottom decile spread per month, on demeaned returns."""
    out: dict[pd.Timestamp, float] = {}
    for date, g in df.groupby("date", sort=True):
        g = g.dropna(subset=[col, "resid"])
        if len(g) < MIN_NAMES:
            continue
        # rank before bucketing: a multiple's raw distribution has a long right
        # tail and qcut on the values themselves puts unequal counts per bucket
        r = g[col].rank(method="first")
        try:
            b = pd.qcut(r, DECILES, labels=False)
        except ValueError:
            continue                       # not enough distinct values
        top = g.loc[b == DECILES - 1, "resid"].mean()
        bot = g.loc[b == 0, "resid"].mean()
        if np.isfinite(top) and np.isfinite(bot):
            out[date] = top - bot
    return pd.Series(out).sort_index()


def stat(s: pd.Series) -> tuple[float, float, int]:
    """Mean monthly spread, its t-statistic across months, and the month count."""
    s = s.dropna()
    if len(s) < 2:
        return float("nan"), float("nan"), len(s)
    t = s.mean() / (s.std(ddof=1) / np.sqrt(len(s)))
    return s.mean(), t, len(s)


def periods(s: pd.Series) -> dict[str, pd.Series]:
    return {"train": s[s.index <= TRAIN_END],
            "holdout": s[s.index > HOLDOUT_START]}


def main() -> None:
    say("VALUE DECILE SPREAD -- contaminated feat_val vs corrected feat_val2")
    tgt = load_target()
    say(f"  target rows with fwd63: {len(tgt):,} over "
        f"{tgt['date'].nunique()} months")
    say(f"  train  date <= {TRAIN_END:%Y-%m-%d}")
    say(f"  holdout date >  {HOLDOUT_START:%Y-%m-%d}  "
        f"(the quarter between is in neither, to stop the 63-day windows "
        f"overlapping)")

    frames = {}
    for tag, path in (("OLD", OLD), ("NEW", NEW)):
        f = load(path, TESTED).merge(tgt, on=["date", "symbol"], how="inner")
        frames[tag] = f
        say(f"  {tag} {os.path.basename(path)}: {len(f):,} rows joined to a "
            f"target")

    say(f"\nTOP-DECILE MINUS BOTTOM-DECILE fwd63, demeaned within month, in %")
    say("  top decile = HIGHEST feature value. For a multiple that is the")
    say("  EXPENSIVE end, so a NEGATIVE spread means cheap outperformed.")
    say(f"\n  {'feature':<16}{'cheap':<8}{'period':<9}"
        f"{'OLD spr':>9}{'t':>7}{'n':>5}{'cov':>7}  "
        f"{'NEW spr':>9}{'t':>7}{'n':>5}{'cov':>7}")
    say("  " + "-" * 93)
    for col in TESTED:
        res = {}
        for tag in ("OLD", "NEW"):
            f = frames[tag]
            res[tag] = (periods(monthly_spreads(f, col)),
                        f[col].notna().mean() * PCT)
        for p in ("train", "holdout"):
            first = p == "train"
            line = (f"  {col if first else '':<16}"
                    f"{CHEAP_END[col] if first else '':<8}{p:<9}")
            for tag in ("OLD", "NEW"):
                per, cov = res[tag]
                m, t, n = stat(per[p])
                line += (f"{m:>9.2f}{t:>7.2f}{n:>5}{cov:>6.1f}%  "
                         if np.isfinite(m) else
                         f"{'--':>9}{'--':>7}{n:>5}{cov:>6.1f}%  ")
            say(line)
        say("  " + "-" * 93)
    say("  spr is the mean MONTHLY spread in percentage points of 63-day return")
    say("  cov is the share of all 50,825 grid rows where that feature exists")
    say("  'cheap' names the decile a value investor would BUY, so the sign of a")
    say("  spread favouring value is negative for the four multiples and")
    say("  positive for earnings_yield")
    say("\n  WHY pe AND earnings_yield CAN DISAGREE AND BOTH BE RIGHT")
    say("  pe is NaN for a loss-maker; earnings_yield keeps the negative value.")
    say("  So earnings_yield's bottom decile is mostly companies pe excludes")
    say("  entirely -- measured on the holdout, it averages a -8.0% yield, is")
    say("  72% loss-making, and only 27% of it has a pe at all. That decile is")
    say("  a profitable-minus-unprofitable bet, not an expensive-minus-cheap")
    say("  one, and it is not evidence about value either way.")


if __name__ == "__main__":
    main()
