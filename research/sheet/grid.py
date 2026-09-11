"""Dump the point-in-time universe grid once, so every feature block aligns.

    python research/sheet/grid.py

WHY THIS IS A SEPARATE FILE
optimize.prep() is the slow, load-bearing step: it rebuilds the eligible
universe for every month end using liquidity as of three years earlier and
index membership as of the date itself. It takes minutes. More importantly, if
two feature blocks each call it independently there is no guarantee they agree
on the universe, and a feature matrix assembled from two different universes is
worse than no feature matrix at all.

So it runs once, here, and everything downstream reads this CSV.

THE CONTRACT every feature block must honour
  rows     exactly the (date, symbol) pairs in this file, no additions
  date     a month-end trading day, the decision date
  symbol   eligible on that date under the PIT rules in optimize.prep()
  fwd63    forward 63-trading-day total return in percent, the TARGET
           (NaN where the window runs past the end of the data)

A feature may only use information dated STRICTLY BEFORE OR ON `date`. Any
feature computed from a price after `date`, or from a filing whose `filed` date
is after `date`, is lookahead and invalidates the whole matrix.
"""
from __future__ import annotations

import importlib.util
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
_o = importlib.util.spec_from_file_location("op", os.path.join(HERE, "optimize.py"))
op = importlib.util.module_from_spec(_o)
_o.loader.exec_module(op)

OUT = os.path.join(op.LONG, "grid.csv")
HOLD = 63


def main() -> None:
    P, fwd, dates, elig = op.prep(hold=HOLD)
    C = P["close"]
    rows = []
    for d in dates:
        for s in elig[d]:
            rows.append((d, s))
    g = pd.DataFrame(rows, columns=["date", "symbol"])
    fl = fwd.stack().rename("fwd63").reset_index()
    fl.columns = ["date", "symbol", "fwd63"]
    g = g.merge(fl, on=["date", "symbol"], how="left")
    g["fwd63"] = g["fwd63"] * 100
    g.to_csv(OUT, index=False)
    say(f"\nwrote {len(g):,} rows to {OUT}")
    say(f"  {g.date.nunique()} dates, {g.symbol.nunique()} symbols")
    say(f"  {g.date.min():%Y-%m-%d} .. {g.date.max():%Y-%m-%d}")
    say(f"  target fwd63 present on {g.fwd63.notna().mean() * 100:.1f}% of rows")
    say(f"  mean fwd63 {g.fwd63.mean():+.2f}%  median {g.fwd63.median():+.2f}%")
    say(f"\n  TRAIN <= {op.TRAIN_END}: "
        f"{(g.date <= op.TRAIN_END).sum():,} rows")
    say(f"  HOLDOUT >  {op.TRAIN_END}: "
        f"{(g.date > op.TRAIN_END).sum():,} rows")


if __name__ == "__main__":
    main()
