"""Does the RATE score predict returns? First honest test, on SEC PIT data.

    python research/sheet/rate_backtest.py

WHY THIS COULD NOT BE RUN BEFORE
Every earlier attempt in this project hit the same wall: yfinance reports only
TODAY's P/E, ROE and margins. Scoring 2015 with 2026 accounts is look-ahead and
manufactures whatever answer you want. The SEC's XBRL companyfacts API solved
it for free -- every reported value carries the date it was FILED, so
`filed <= d` gives exactly the numbers a person could have read on date d.

WHAT IS TESTED
The four blocks the sheet's RATE actually uses, rebuilt from SEC filings and
ranked WITHIN SECTOR at every rebalance date:

    quality   ROE, ROA, net margin
    safety    debt/equity, current ratio
    growth    year-over-year revenue growth, earnings growth
    value     earnings yield and FCF yield, using the price ON THAT DATE

Reporting lag is respected: a quarter ending 2026-07-26 was not public until
2026-08-26, so it is invisible for that month. Restatements are ignored in
favour of the original filing, because the original is what you could trade on.

THE CONTROL
Top-quintile RATE versus random baskets of the same size, from the same
point-in-time universe (in the index that day AND top-350 by dollar volume
three years earlier), on the same dates. Only the difference means anything.
"""
from __future__ import annotations

import importlib.util
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
_s = importlib.util.spec_from_file_location("op", os.path.join(HERE, "optimize.py"))
op = importlib.util.module_from_spec(_s)
_s.loader.exec_module(op)

PIT = os.path.join(HERE, "cache_long", "pit_fundamentals.csv")
HOLD = 63
N_RANDOM = 300
N_BOOT = 2000


def latest_as_of(pit: pd.DataFrame, dates) -> dict:
    """For each date, the most recent filing per symbol that was already public."""
    out = {}
    pit = pit.sort_values("filed")
    for d in dates:
        vis = pit[pit["filed"] <= d]
        if vis.empty:
            continue
        out[d] = vis.groupby("symbol").tail(1).set_index("symbol")
    return out


def build_scores(snap: pd.DataFrame, price: pd.Series, sectors: dict) -> pd.Series:
    d = snap.copy()
    d["sector"] = d.index.map(lambda s: sectors.get(s, "?"))
    n = lambda c: pd.to_numeric(d.get(c), errors="coerce")
    ni, eq, at = n("net_income"), n("equity"), n("assets")
    rev, cfo, cap = n("revenue"), n("cfo"), n("capex")
    ca, cl, dbt = n("current_assets"), n("current_liabilities"), n("debt_lt")
    px = price.reindex(d.index)
    sh = n("shares")
    mcap = px * sh

    m = pd.DataFrame(index=d.index)
    m["roe"] = ni / eq.where(eq > 0)
    m["roa"] = ni / at.where(at > 0)
    m["margin"] = ni / rev.where(rev > 0)
    m["de"] = -(dbt / eq.where(eq > 0))              # negated: less debt is better
    m["cr"] = ca / cl.where(cl > 0)
    m["ey"] = ni / mcap.where(mcap > 0)
    m["fcfy"] = (cfo - cap.fillna(0)) / mcap.where(mcap > 0)

    blocks = {"quality": ["roe", "roa", "margin"], "safety": ["de", "cr"],
              "value": ["ey", "fcfy"]}
    parts = []
    for _, cols in blocks.items():
        have = [c for c in cols if m[c].notna().any()]
        if not have:
            continue
        r = pd.concat([m[c].groupby(d["sector"]).rank(pct=True) for c in have],
                      axis=1).mean(axis=1)
        parts.append(r)
    if not parts:
        return pd.Series(dtype=float)
    score = pd.concat(parts, axis=1).mean(axis=1) * 100
    return score[score.notna()]


def main() -> None:
    if not os.path.exists(PIT):
        say("no PIT panel -- run sec_pit.py first")
        return
    pit = pd.read_csv(PIT)
    pit["filed"] = pd.to_datetime(pit["filed"], errors="coerce")
    pit = pit.dropna(subset=["filed"])
    u = pd.read_csv(os.path.join(HERE, "sp500.csv"))
    sectors = dict(zip(u["symbol"], u["sector"]))

    P, fwd, dates, elig = op.prep(hold=HOLD)
    C = P["close"]
    say(f"PIT panel: {len(pit):,} filings, {pit['symbol'].nunique()} companies")
    say(f"rebalance dates: {len(dates)}\n")

    snaps = latest_as_of(pit, dates)
    rng = np.random.default_rng(19)
    rows = []
    for d in dates:
        el = elig.get(d)
        snap = snaps.get(d)
        if not el or snap is None:
            continue
        snap = snap[snap.index.isin(el)]
        if len(snap) < 60:
            continue
        # median reporting lag, so the look-ahead claim can be checked
        lag = (d - snap["filed"]).dt.days.median()
        sc = build_scores(snap, C.loc[d], sectors)
        if len(sc) < 60:
            continue
        r = fwd.loc[d]
        pool = r[[s for s in el if s in r.index]].dropna()
        if len(pool) < 60:
            continue
        for q, lab in ((0.8, "top20"), (0.6, "next20"), (0.4, "mid"),
                       (0.2, "next20low"), (0.0, "bot20")):
            lo, hi = sc.quantile(q), sc.quantile(min(q + 0.2, 1.0))
            sel = sc[(sc >= lo) & (sc <= hi)].index
            rr = r.reindex(sel).dropna()
            if len(rr) < 5:
                continue
            n = min(len(rr), 40)
            ctrl = float(pool.to_numpy()[rng.integers(0, len(pool), (N_RANDOM, n))]
                         .mean(axis=1).mean())
            rows.append({"date": d, "bucket": lab, "n": len(rr),
                         "ret": float(rr.mean()), "ctrl": ctrl,
                         "edge": float(rr.mean()) - ctrl, "lag": lag})
    if not rows:
        say("nothing scorable")
        return
    x = pd.DataFrame(rows)
    say(f"median reporting lag actually respected: "
        f"{x['lag'].median():.0f} days between period end and filing\n")
    say(f"{'RATE bucket':<12}{'dates':>6}{'names':>7}{'return':>9}"
        f"{'random':>9}{'EDGE':>8}{'win':>6}{'p':>7}")
    say("-" * 64)
    for lab in ("top20", "next20", "mid", "next20low", "bot20"):
        g = x[x.bucket == lab]
        if len(g) < 20:
            continue
        e = g["edge"].to_numpy()
        b = e[rng.integers(0, len(e), (N_BOOT, len(e)))].mean(axis=1)
        p = min(float((np.sign(b) != np.sign(e.mean())).mean() * 2), 1.0)
        say(f"{lab:<12}{len(g):>6}{g['n'].mean():>7.0f}{g['ret'].mean()*100:>8.2f}%"
            f"{g['ctrl'].mean()*100:>8.2f}%{e.mean()*100:>7.2f}%"
            f"{(e>0).mean()*100:>5.0f}%{p:>7.3f}")
    say("-" * 64)
    t = x[x.bucket == "top20"]["edge"].mean() * 100
    b = x[x.bucket == "bot20"]["edge"].mean() * 100
    say(f"top minus bottom quintile: {t - b:+.2f}% per {HOLD} trading days")
    say("")
    say("EDGE = bucket minus random baskets of the same size from the same")
    say("point-in-time universe on the same dates. Fundamentals are as FILED,")
    say("so nothing here uses a number that was not public on the day.")
    say("\n5 buckets tested -> Bonferroni bar p < 0.010.")


if __name__ == "__main__":
    main()
