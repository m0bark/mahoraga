"""The single filter that survived, attacked from four directions.

    python research/sheet/verify_turnover.py

Of 48 point-in-time screener filters swept over 50,825 rows, exactly one
survived beta-neutralisation with a consistent sign across a sealed holdout:

    asset_turnover = trailing-twelve-month revenue / total assets
    train   +1.52% per quarter, t +4.49
    holdout +1.84% per quarter, t +3.26
    monotonicity +0.71 across the ten deciles

One survivor out of 48 is roughly what pure chance produces, so the burden of
proof is entirely on it. Four attacks, any one of which should kill it:

  1. IS IT A SECTOR BET? Asset turnover is the most sector-determined ratio on
     the list. A grocer turns its assets over several times a year and a
     utility a fraction of once, and neither fact is about the stock. If the
     effect disappears once deciles are cut WITHIN sector, it was a bet on
     retail over utilities and has nothing to do with selection.

  2. IS IT STABLE YEAR BY YEAR? A spread carried by two or three years is a
     regime, not an edge.

  3. DOES IT SURVIVE FRESH DATA ONLY? The fundamentals panel carries a known
     comparative-column defect: balance-sheet fields can be far older than the
     filing date suggests. If the effect only exists on stale rows, it is an
     artefact of the defect rather than a property of the companies.

  4. IS IT JUST SIZE OR VALUE IN DISGUISE? Turnover correlates with both. The
     spread is recomputed after neutralising each of beta, market cap and
     price-to-book together.

Anything that only survives attack 1 is reported as failed, because a sector
tilt is not what was asked for.
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
FEATURE = "asset_turnover"
N_DEC = 10


def load() -> pd.DataFrame:
    g = pd.read_csv(os.path.join(LONG, "grid.csv"), parse_dates=["date"])
    for n in ("qual", "tech", "val2"):
        p = os.path.join(LONG, f"feat_{n}.csv")
        if os.path.exists(p):
            b = pd.read_csv(p, parse_dates=["date"])
            cols = [c for c in b.columns if c not in ("date", "symbol")]
            g = g.merge(b[["date", "symbol"] + cols], on=["date", "symbol"],
                        how="left")
    u = pd.read_csv(os.path.join(HERE, "sp500.csv"))
    g = g.merge(u[["symbol", "sector"]].drop_duplicates("symbol"),
                on="symbol", how="left")
    g["y"] = g["fwd63"] - g.groupby("date")["fwd63"].transform("mean")
    return g.dropna(subset=["y", FEATURE])


def spread(d: pd.DataFrame, col: str = FEATURE, y: str = "y",
           within: list | None = None) -> tuple:
    """Top minus bottom decile, cut within month and optionally within sector."""
    keys = ["date"] + (within or [])
    s = d.dropna(subset=[col, y]).copy()
    if s.empty:
        return np.nan, np.nan, 0

    def cut(x: pd.Series) -> pd.Series:
        if x.notna().sum() < N_DEC * 2:
            return pd.Series(np.nan, index=x.index)
        return pd.qcut(x.rank(method="first"), N_DEC, labels=False,
                       duplicates="drop")

    s["dec"] = s.groupby(keys)[col].transform(cut)
    s = s.dropna(subset=["dec"])
    if s.empty:
        return np.nan, np.nan, 0
    hi = s.loc[s.dec == s.dec.max(), y]
    lo = s.loc[s.dec == 0, y]
    if len(hi) < 2 or len(lo) < 2:
        return np.nan, np.nan, len(s)
    se = np.sqrt(hi.var(ddof=1) / len(hi) + lo.var(ddof=1) / len(lo))
    t = (hi.mean() - lo.mean()) / se if se > 0 else np.nan
    return hi.mean() - lo.mean(), t, len(s)


def neutralise(d: pd.DataFrame, cols: list) -> pd.DataFrame:
    """Within each month regress y on the given columns and keep the residual.
    Rows missing any control are dropped rather than mean-filled, because
    filling a control with its mean quietly un-neutralises those rows."""
    out = []
    for dt, g in d.groupby("date"):
        k = g.dropna(subset=cols + ["y"])
        if len(k) < 30:
            continue
        X = np.column_stack([np.ones(len(k))]
                            + [k[c].to_numpy(dtype=float) for c in cols])
        yy = k["y"].to_numpy(dtype=float)
        ok = np.isfinite(X).all(axis=1) & np.isfinite(yy)
        if ok.sum() < 30:
            continue
        beta, *_ = np.linalg.lstsq(X[ok], yy[ok], rcond=None)
        k = k.loc[k.index[ok]].copy()
        k["y"] = yy[ok] - X[ok] @ beta
        out.append(k)
    return pd.concat(out) if out else d.iloc[0:0]


def main() -> None:
    d = load()
    tr = d[d.date <= "2021-09-30"]
    ho = d[d.date > "2021-12-31"]
    say(f"{len(d):,} rows with {FEATURE} | train {len(tr):,} holdout {len(ho):,}")
    say(f"coverage {d[FEATURE].notna().mean() * 100:.1f}% of the grid")

    say("")
    say("=" * 76)
    say("  BASELINE, reproducing the sweep")
    say("=" * 76)
    for lab, part in (("train", tr), ("holdout", ho)):
        a, t, n = spread(part)
        say(f"  {lab:<10}{a:>+8.2f}%  t {t:>+6.2f}  n {n:,}")

    say("")
    say("=" * 76)
    say("  ATTACK 1 -- DECILES CUT WITHIN SECTOR")
    say("=" * 76)
    say("  If this collapses, the filter was buying retailers and selling")
    say("  utilities, which is a sector tilt and not a stock screen.")
    for lab, part in (("train", tr), ("holdout", ho)):
        a, t, n = spread(part, within=["sector"])
        say(f"  {lab:<10}{a:>+8.2f}%  t {t:>+6.2f}  n {n:,}")
    say("")
    say("  for reference, the same cut on the RAW (not demeaned) sector means:")
    sec = (d.groupby("sector")[FEATURE].median().sort_values(ascending=False))
    for k, v in sec.items():
        say(f"    {str(k)[:28]:<30}{v:>7.2f}")

    say("")
    say("=" * 76)
    say("  ATTACK 2 -- YEAR BY YEAR")
    say("=" * 76)
    say(f"  {'year':<8}{'spread':>10}{'t':>8}{'n':>9}")
    d2 = d.copy()
    d2["yr"] = d2.date.dt.year
    pos = neg = 0
    for y, g in d2.groupby("yr"):
        a, t, n = spread(g)
        if not np.isfinite(a):
            continue
        pos += a > 0
        neg += a <= 0
        say(f"  {int(y):<8}{a:>+9.2f}%{t:>+8.2f}{n:>9,}")
    say(f"  positive in {pos} of {pos + neg} years")

    say("")
    say("=" * 76)
    say("  ATTACK 3 -- FRESH FILINGS ONLY")
    say("=" * 76)
    say("  The fundamentals panel has a comparative-column defect that makes")
    say("  some balance-sheet data far older than its filing date implies.")
    say("  fscore_legs is a proxy for how completely a row was measured.")
    if "fscore_legs" in d:
        for mn in (6, 7, 8):
            k = d[d.fscore_legs >= mn]
            a, t, n = spread(k)
            say(f"  legs >= {mn}   {a:>+8.2f}%  t {t:>+6.2f}  n {n:,}")
    else:
        say("  fscore_legs absent; cannot run this attack")

    say("")
    say("=" * 76)
    say("  ATTACK 4 -- NEUTRALISE BETA, SIZE AND BOOK TOGETHER")
    say("=" * 76)
    ctrl = [c for c in ("beta252", "market_cap", "pb") if c in d.columns]
    say(f"  controls: {', '.join(ctrl)}")
    if ctrl:
        nd = neutralise(d, ctrl)
        for lab, part in (("train", nd[nd.date <= "2021-09-30"]),
                          ("holdout", nd[nd.date > "2021-12-31"])):
            a, t, n = spread(part)
            say(f"  {lab:<10}{a:>+8.2f}%  t {t:>+6.2f}  n {n:,}")
        say("")
        say("  market_cap here is from feat_val2 (unadjusted prices). It still")
        say("  carries a stale share count for buyback-heavy names, so treat it")
        say("  as a rough size control rather than an exact one.")

    say("")
    say("=" * 76)
    say("  VERDICT")
    say("=" * 76)
    say("  Read attack 1 first. A filter that only works across sectors and not")
    say("  within them is a sector allocation decision wearing a screen's")
    say("  clothes, and it would be implemented by buying a sector ETF rather")
    say("  than by picking stocks.")


if __name__ == "__main__":
    main()
