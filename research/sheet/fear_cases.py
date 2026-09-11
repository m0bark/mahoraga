"""Every -40% capitulation, named and dated. See the trades, not the average.

    python research/sheet/fear_cases.py                 # the record
    python research/sheet/fear_cases.py --symbol MU     # one name's history
    python research/sheet/fear_cases.py --year 2022
    python research/sheet/fear_cases.py --worst         # the ones that kept falling

WHY THIS EXISTS
"+4.82% over random, p=0.000" is a number you have to take on trust. This is
the same measurement written out one trade at a time: the name, the date, how
far it had already fallen, and exactly what the next three months did. If the
edge is real it should be visible here as a list of outcomes you could have
lived through -- including the ones that kept going down, which are the whole
reason the average is not larger.

Nothing here is selected after the fact. Every observation the study used is
printed, and the losers are printed as loudly as the winners.
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

HOLD = 63
DEEP = -40.0
CACHE = os.path.join(HERE, "cache_long", "fear_cases.csv")


def build():
    P, fwd, dates, elig = op.prep(hold=HOLD)
    C = P["close"]
    rows = []
    for d in dates:
        el = elig.get(d)
        if not el:
            continue
        i = C.index.get_loc(d)
        win = C.iloc[max(0, i - 252):i + 1]
        r = fwd.loc[d]
        pool = r[[s for s in el if s in r.index]].dropna()
        base = float(pool.mean()) if len(pool) > 50 else np.nan
        for s in el:
            c = win[s].dropna()
            if len(c) < 200:
                continue
            hi, spot = float(c.max()), float(c.iloc[-1])
            if hi <= 0:
                continue
            dd = (spot / hi - 1) * 100
            f = r.get(s, np.nan)
            if not np.isfinite(f) or dd > DEEP:
                continue
            # worst point during the hold: what you would actually have felt
            fut = C[s].iloc[i:i + HOLD + 1].dropna()
            trough = (float(fut.min()) / spot - 1) * 100 if len(fut) else np.nan
            rows.append({"date": d.strftime("%Y-%m-%d"), "symbol": s,
                         "price": round(spot, 2), "from_high": round(dd, 1),
                         "fwd_63d": round(f * 100, 1),
                         "worst_during": round(trough, 1),
                         "market_that_period": round(base * 100, 1)
                         if np.isfinite(base) else np.nan})
    x = pd.DataFrame(rows)
    x["vs_market"] = (x["fwd_63d"] - x["market_that_period"]).round(1)
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    x.to_csv(CACHE, index=False)
    return x


def load():
    if os.path.exists(CACHE):
        return pd.read_csv(CACHE)
    say("building the case file (one pass, then cached) ...")
    return build()


def summary(x):
    say(f"{len(x):,} capitulation events (-40% or worse), "
        f"{x['date'].min()} .. {x['date'].max()}")
    say(f"across {x['symbol'].nunique()} different companies\n")
    w = (x.fwd_63d > 0).mean() * 100
    b = (x.vs_market > 0).mean() * 100
    say(f"{'made money over 63 days':<34}{w:>6.1f}%")
    say(f"{'beat the market over 63 days':<34}{b:>6.1f}%")
    say(f"{'average return':<34}{x.fwd_63d.mean():>+6.1f}%")
    say(f"{'average vs market':<34}{x.vs_market.mean():>+6.1f}%")
    say(f"{'median return':<34}{x.fwd_63d.median():>+6.1f}%")
    say(f"{'worst single outcome':<34}{x.fwd_63d.min():>+6.1f}%")
    say(f"{'best single outcome':<34}{x.fwd_63d.max():>+6.1f}%")
    say("")
    say("WHAT YOU HAD TO SIT THROUGH:")
    say(f"{'  average further fall before recovery':<40}"
        f"{x.worst_during.mean():>+6.1f}%")
    say(f"{'  fell another 10%+ at some point':<40}"
        f"{(x.worst_during <= -10).mean()*100:>6.1f}%")
    say(f"{'  fell another 20%+ at some point':<40}"
        f"{(x.worst_during <= -20).mean()*100:>6.1f}%")
    say("  That is the cost of this trade, and it is not in the average.")


def show(x, title, n=25):
    say(f"\n{title}")
    say(f"{'date':<12}{'sym':<7}{'price':>9}{'from high':>11}"
        f"{'next 63d':>10}{'vs mkt':>9}{'worst dip':>11}")
    say("-" * 69)
    for r in x.head(n).itertuples():
        say(f"{r.date:<12}{r.symbol:<7}{r.price:>9.2f}{r.from_high:>10.1f}%"
            f"{r.fwd_63d:>+9.1f}%{r.vs_market:>+8.1f}%{r.worst_during:>+10.1f}%")


def main():
    a = sys.argv[1:]
    x = load()
    if "--symbol" in a:
        s = a[a.index("--symbol") + 1].upper()
        g = x[x.symbol == s]
        if g.empty:
            say(f"{s} never fell 40% in this sample")
            return
        say(f"{s}: {len(g)} capitulation events")
        show(g.sort_values("date"), f"every time {s} was down 40%+", 50)
        say(f"\naverage next 63 days: {g.fwd_63d.mean():+.1f}%  "
            f"({(g.fwd_63d > 0).mean()*100:.0f}% positive)")
        return
    if "--year" in a:
        y = a[a.index("--year") + 1]
        g = x[x.date.str.startswith(y)]
        summary(g)
        show(g.sort_values("from_high"), f"deepest falls of {y}")
        return
    if "--worst" in a:
        summary(x)
        show(x.sort_values("fwd_63d"),
             "THE 25 WORST OUTCOMES -- what buying the fear cost when it failed")
        return
    summary(x)
    show(x.sort_values("from_high"), "THE 25 DEEPEST FALLS IN THE SAMPLE")
    show(x.sort_values("fwd_63d", ascending=False),
         "THE 25 BEST OUTCOMES")
    show(x.sort_values("fwd_63d"),
         "THE 25 WORST OUTCOMES -- these are why the average is only +4.8%")
    say("\nrun with --worst, --year 2022, or --symbol MU to dig in")


if __name__ == "__main__":
    main()
