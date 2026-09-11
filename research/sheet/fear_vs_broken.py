"""Is the stock down on FEAR, or is it down because the business broke?

    python research/sheet/fear_vs_broken.py

THE HYPOTHESIS, in the operator's words
"Micron was $700 in July because of China. People didn't sell because Micron
is bad, they sold out of fear. I want the price so good the math shuts down."

That is a real and separable claim. A stock 30% off its high is in one of two
completely different situations:

    FEAR    price collapsed, the LAST FILED numbers are still growing
    BROKEN  price collapsed, and so did revenue and earnings

From a chart the two are identical. From the filings they are not. Every
earlier attempt in this project to test it failed for one reason: yfinance
reports only TODAY's fundamentals, so asking "were earnings growing in 2018?"
meant using 2026 data and inventing the answer.

The SEC XBRL feed fixes that. Each value carries the date it was FILED, so
`filed <= d` is exactly what a person could have read on the day. That is
what makes this testable at last.

WHAT IS MEASURED
At each month end, every eligible name is bucketed by
    drawdown from its 252-day high        (how much fear)
  x trailing revenue and earnings growth  (as last FILED, not as known now)
and scored on forward 63-day return against random baskets from the same
point-in-time universe.

IF THE THESIS IS RIGHT, deep-drawdown names with intact fundamentals beat
both random AND deep-drawdown names with collapsing fundamentals. If both
buckets do the same, the fundamentals are not separating anything and
"buy the fear" is just buying drawdown, which this project already measured
as an anti-signal.
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
_o = importlib.util.spec_from_file_location("op", os.path.join(HERE, "optimize.py"))
op = importlib.util.module_from_spec(_o)
_o.loader.exec_module(op)

PIT = os.path.join(HERE, "cache_long", "pit_fundamentals.csv")
HOLD = 63
N_RANDOM = 300
N_BOOT = 2000


def trailing(pit: pd.DataFrame):
    """Per symbol, an ordered list of (filed, revenue, net income) so growth
    can be computed against what was public FOUR FILINGS AGO -- roughly a
    year, without assuming a fiscal calendar."""
    out = {}
    for sym, g in pit.sort_values("filed").groupby("symbol"):
        rec = []
        for r in g.itertuples():
            rev = getattr(r, "revenue", np.nan)
            ni = getattr(r, "net_income", np.nan)
            rec.append((r.filed, rev, ni))
        out[sym] = rec
    return out


def growth_as_of(rec, d):
    """Revenue and earnings growth using only filings public on date d."""
    vis = [x for x in rec if x[0] <= d]
    if len(vis) < 5:
        return np.nan, np.nan
    now, then = vis[-1], vis[-5]        # 4 filings back ~ one year
    rg = ((now[1] / then[1] - 1) if np.isfinite(now[1]) and np.isfinite(then[1])
          and then[1] > 0 else np.nan)
    eg = ((now[2] / abs(then[2]) - 1) if np.isfinite(now[2]) and np.isfinite(then[2])
          and then[2] != 0 else np.nan)
    return rg, eg


def main() -> None:
    if not os.path.exists(PIT):
        say("no PIT panel -- run sec_pit.py first")
        return
    pit = pd.read_csv(PIT)
    pit["filed"] = pd.to_datetime(pit["filed"], errors="coerce")
    pit = pit.dropna(subset=["filed"])
    rec = trailing(pit)

    P, fwd, dates, elig = op.prep(hold=HOLD)
    C = P["close"]
    say(f"{len(dates)} dates | PIT panel {len(pit):,} filings\n")

    rows = []
    for d in dates:
        el = elig.get(d)
        if not el:
            continue
        i = C.index.get_loc(d)
        win = C.iloc[max(0, i - 252):i + 1]
        r = fwd.loc[d]
        for s in el:
            if s not in C.columns or s not in rec:
                continue
            c = win[s].dropna()
            if len(c) < 200:
                continue
            spot = float(c.iloc[-1])
            hi = float(c.max())
            if hi <= 0:
                continue
            dd = spot / hi - 1.0
            rg, eg = growth_as_of(rec[s], d)
            f = r.get(s, np.nan)
            if not np.isfinite(f):
                continue
            rows.append({"date": d, "symbol": s, "dd": dd * 100,
                         "rev_g": rg, "earn_g": eg, "fwd": f})
    x = pd.DataFrame(rows)
    x = x.dropna(subset=["rev_g"])
    say(f"{len(x):,} observations with a filed growth figure\n")

    rng = np.random.default_rng(23)

    def ctrl_for(sub):
        """Random baskets of the same size from the same dates."""
        per = []
        for d, g in sub.groupby("date"):
            pool = x[x.date == d]["fwd"].to_numpy()
            if len(pool) < 60 or len(g) < 5:
                continue
            n = min(len(g), 40)
            c = float(pool[rng.integers(0, len(pool), (N_RANDOM, n))].mean(axis=1).mean())
            per.append((float(g["fwd"].mean()), c))
        if len(per) < 20:
            return None
        a = pd.DataFrame(per, columns=["sel", "ctrl"])
        e = (a["sel"] - a["ctrl"]).to_numpy()
        b = e[rng.integers(0, len(e), (N_BOOT, len(e)))].mean(axis=1)
        p = min(float((np.sign(b) != np.sign(e.mean())).mean() * 2), 1.0)
        return len(a), a["sel"].mean() * 100, a["ctrl"].mean() * 100, e.mean() * 100, p

    say("1. DRAWDOWN ALONE (no fundamentals) -- the baseline to beat")
    say(f"   {'drawdown':<16}{'dates':>6}{'ret':>9}{'random':>9}{'EDGE':>8}{'p':>7}")
    say("   " + "-" * 56)
    bands = [(-100, -40, "worse than -40%"), (-40, -25, "-25 to -40%"),
             (-25, -15, "-15 to -25%"), (-15, -5, "-5 to -15%"),
             (-5, 1, "near highs")]
    for lo, hi, lab in bands:
        r = ctrl_for(x[(x.dd > lo) & (x.dd <= hi)])
        if r:
            say(f"   {lab:<16}{r[0]:>6}{r[1]:>8.2f}%{r[2]:>8.2f}%{r[3]:>+7.2f}%{r[4]:>7.3f}")

    say("\n2. FEAR vs BROKEN -- same drawdown, split by what was FILED")
    say(f"   {'bucket':<34}{'dates':>6}{'ret':>9}{'random':>9}{'EDGE':>8}{'p':>7}")
    say("   " + "-" * 74)
    deep = x[x.dd <= -20]
    for glo, ghi, glab in [(0.05, 99, "revenue GROWING >5%"),
                           (-0.05, 0.05, "revenue flat"),
                           (-99, -0.05, "revenue SHRINKING >5%")]:
        sub = deep[(deep.rev_g > glo) & (deep.rev_g <= ghi)]
        r = ctrl_for(sub)
        if r:
            say(f"   {'down 20%+, ' + glab:<34}{r[0]:>6}{r[1]:>8.2f}%"
                f"{r[2]:>8.2f}%{r[3]:>+7.2f}%{r[4]:>7.3f}")

    say("\n3. THE STRICT VERSION -- deep drawdown, revenue AND earnings growing")
    for ddlim, lab in [(-20, "down 20%+"), (-30, "down 30%+"), (-40, "down 40%+")]:
        sub = x[(x.dd <= ddlim) & (x.rev_g > 0.05) & (x.earn_g > 0)]
        r = ctrl_for(sub)
        if r:
            say(f"   {lab + ', both growing':<34}{r[0]:>6}{r[1]:>8.2f}%"
                f"{r[2]:>8.2f}%{r[3]:>+7.2f}%{r[4]:>7.3f}")
        else:
            n = len(x[(x.dd <= ddlim) & (x.rev_g > 0.05) & (x.earn_g > 0)])
            say(f"   {lab + ', both growing':<34}  too few dates (n={n})")

    say("\n   " + "-" * 74)
    say("   EDGE is versus random baskets from the same point-in-time universe")
    say("   on the same dates. Growth figures are AS FILED, so nothing here")
    say("   uses a number that was not public on the day.")
    say("   9 buckets tested -> Bonferroni bar p < 0.0056.")


if __name__ == "__main__":
    main()
