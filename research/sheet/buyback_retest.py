"""Retest the buyback screen with splits removed. One rejection I called unfairly.

    python research/sheet/buyback_retest.py

WHY
The 55-filter sweep rejected shares_change_1y: train -0.95% (t -2.95), holdout
+1.54% (t +2.54), a sign flip, verdict "train only". An audit then found the
feature conflates stock splits with dilution. A 20-for-1 split is reported as
+1,859% "dilution", so the entire right tail of the distribution is splits
rather than share issuance, and the top decile of a "dilution" sort is
substantially a list of companies that split because they had gone up.

That is a contaminated feature, and a rejection based on it is not a fair test.
feat_growth.py documented the limitation and deliberately did not import
cache_long/splits.csv to avoid making two feature blocks rebuild in a fixed
order, which is a reasonable engineering call. It still leaves the screen
untested, so the correction happens here instead.

THE CORRECTION
A split multiplies the share count without changing ownership. For each row,
the cumulative split ratio over the trailing year is divided out:

    corrected = (1 + raw/100) / cumulative_ratio - 1

Negative is a buyback, positive is genuine dilution. Net buyback yield is a
documented factor in the literature, so unlike most of what this project has
tested there is a prior reason to look.

THE BAR IS THE SAME AS IT WAS FOR EVERYTHING ELSE
Top decile minus bottom decile of forward 63-day return, demeaned within the
month, train to 2021-09 with a three-month embargo, holdout from 2022-01. And
then the same thing on a beta-neutralised target, because a dilution sort will
correlate with size and volatility and the raw number would mostly be beta.
A filter has to clear both or it has not cleared anything.
"""
from __future__ import annotations

import io
import os
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

HERE = os.path.dirname(os.path.abspath(__file__))
LONG = os.path.join(HERE, "cache_long")
N_DEC = 10
TRAIN_END = pd.Timestamp("2021-09-30")
HOLDOUT_START = pd.Timestamp("2022-01-01")
SPLIT_FLAG = 1.15        # a ratio this far from 1 is a split, not a reclassification


def load() -> pd.DataFrame:
    g = pd.read_csv(os.path.join(LONG, "grid.csv"), parse_dates=["date"])
    gr = pd.read_csv(os.path.join(LONG, "feat_growth.csv"), parse_dates=["date"])
    ft = pd.read_csv(os.path.join(LONG, "feat_tech.csv"), parse_dates=["date"])
    d = (g.merge(gr[["date", "symbol", "shares_change_1y"]],
                 on=["date", "symbol"], how="left")
         .merge(ft[["date", "symbol", "beta252"]], on=["date", "symbol"],
                how="left"))
    sp = pd.read_csv(os.path.join(LONG, "splits.csv"), parse_dates=["date"])
    sp = sp[sp.ratio >= SPLIT_FLAG]
    say(f"{len(d):,} grid rows | {len(sp)} splits of ratio >= {SPLIT_FLAG} "
        f"over {sp.symbol.nunique()} symbols")

    # cumulative split ratio in the trailing year of each row. Small loop over
    # the 174 affected symbols rather than a cross join of 50,825 x 253.
    d["cum_split"] = 1.0
    by_sym = {s: g2.sort_values("date") for s, g2 in sp.groupby("symbol")}
    for s, rows in d.groupby("symbol"):
        ev = by_sym.get(s)
        if ev is None:
            continue
        for idx, dt in zip(rows.index, rows["date"]):
            w = ev[(ev.date > dt - pd.DateOffset(years=1)) & (ev.date <= dt)]
            if len(w):
                d.loc[idx, "cum_split"] = float(w.ratio.prod())

    raw = pd.to_numeric(d["shares_change_1y"], errors="coerce")
    d["raw"] = raw
    d["corrected"] = ((1 + raw / 100.0) / d["cum_split"] - 1) * 100.0
    d["y"] = d.fwd63 - d.groupby("date")["fwd63"].transform("mean")
    touched = (d.cum_split > 1).sum()
    say(f"rows inside a split window: {touched:,} "
        f"({touched / len(d) * 100:.2f}%)")
    return d.dropna(subset=["corrected", "y"])


def neutralise(d: pd.DataFrame) -> pd.DataFrame:
    """Regress the target on market beta within each month and keep the
    residual, so what is measured is selection rather than leverage."""
    out = []
    for _, g in d.groupby("date"):
        k = g.dropna(subset=["beta252", "y"])
        if len(k) < 30:
            continue
        x = k["beta252"].to_numpy(float)
        yy = k["y"].to_numpy(float)
        b1, b0 = np.polyfit(x, yy, 1)
        k = k.copy()
        k["y"] = yy - (b0 + b1 * x)
        out.append(k)
    return pd.concat(out) if out else d.iloc[0:0]


def spread(df: pd.DataFrame, col: str) -> tuple:
    s = df.dropna(subset=[col, "y"]).copy()
    if len(s) < 500:
        return (np.nan,) * 4
    s["dec"] = s.groupby("date")[col].transform(
        lambda x: pd.qcut(x.rank(method="first"), N_DEC, labels=False,
                          duplicates="drop")
        if x.notna().sum() >= N_DEC else np.nan)
    s = s.dropna(subset=["dec"])
    hi = s.loc[s.dec == s.dec.max(), "y"]
    lo = s.loc[s.dec == 0, "y"]
    if len(hi) < 2 or len(lo) < 2:
        return (np.nan,) * 4
    se = np.sqrt(hi.var(ddof=1) / len(hi) + lo.var(ddof=1) / len(lo))
    t = (hi.mean() - lo.mean()) / se if se > 0 else np.nan
    means = s.groupby("dec")["y"].mean()
    mono = means.corr(pd.Series(means.index, index=means.index),
                      method="spearman")
    return hi.mean() - lo.mean(), t, mono, len(s)


def report(d: pd.DataFrame, label: str) -> None:
    tr = d[d.date <= TRAIN_END]
    ho = d[d.date >= HOLDOUT_START]
    say("")
    say("=" * 76)
    say(f"  {label}")
    say("=" * 76)
    say(f"  {'feature':<14}{'period':<10}{'hi-lo':>10}{'t':>8}{'mono':>8}{'n':>9}")
    say("  " + "-" * 72)
    for col, nm in (("raw", "as shipped"), ("corrected", "de-split")):
        for per, part in (("train", tr), ("holdout", ho)):
            a, t, m, n = spread(part, col)
            if not np.isfinite(a):
                continue
            say(f"  {nm:<14}{per:<10}{a:>+9.2f}%{t:>+8.2f}{m:>+8.2f}{n:>9,}")
        say("  " + "-" * 72)


def main() -> None:
    d = load()
    say("")
    say("  DILUTION, top and bottom decile means, to show what changed")
    for col in ("raw", "corrected"):
        s = d[col].dropna()
        say(f"    {col:<10} p1 {s.quantile(.01):>+9.1f}%  median "
            f"{s.median():>+6.2f}%  p99 {s.quantile(.99):>+9.1f}%  "
            f"max {s.max():>+10.1f}%")
    report(d, "RAW TARGET -- demeaned within month")
    report(neutralise(d), "BETA-NEUTRAL TARGET -- the honest test")
    say("")
    say("  Negative hi-lo means the DILUTED names underperformed, i.e. the")
    say("  buyback side won, which is the direction the literature expects.")
    say("  It has to hold in train AND holdout AND survive beta, the same bar")
    say("  every other filter in this project was held to.")


if __name__ == "__main__":
    main()
