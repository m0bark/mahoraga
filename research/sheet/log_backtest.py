"""Backtest each of the three ledgers, with the control that matters.

    python research/sheet/log_backtest.py             # all three
    python research/sheet/log_backtest.py --only buyzone

WHAT THIS DOES DIFFERENTLY FROM A NORMAL BACKTEST
Every signal is scored against RANDOM baskets of the same size, drawn from the
same point-in-time universe on the same dates. The universe is names that were
already top-350 by dollar volume THREE YEARS EARLIER, so nothing can be picked
because of what it later became. A raw return number on a survivor list is
meaningless; the difference from random is not.

THE THREE, AND WHAT CAN HONESTLY BE SAID ABOUT EACH

  buyzone   FULLY TESTABLE. Price-only: support, 200-day average, spot minus
            1.5 ATR. Rebuildable at every past date.

  analyst   NOT testable from this data, and pretending otherwise would be a
            lie. Historical rating DATES exist on the tape, but only the last
            8 per stock, so the sample is whatever happens to still be on the
            page -- recency-selected, not a history. What HAS been measured on
            11,570 dated events: entering on the public rating date under-
            performed a nearby day in the same stock by 0.67-1.55% over the
            next month, p~0.0005, placebo on random dates -0.01%.
            The closest testable proxy is run here and labelled as a proxy.

  bigmoney  NOT testable at all. Nobody publishes free historical option
            chains, so there is no past. The nearest price-only proxy is a
            VOLUME SURGE -- unusual activity leaves a footprint in share
            volume too -- and that is what is measured, clearly labelled. The
            real answer for bigmoney can only come from the forward ledger.

Nothing here is tuned. These are the rules exactly as logs.py fires them.
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
_c = importlib.util.spec_from_file_location("cp", os.path.join(HERE, "compute.py"))
cp = importlib.util.module_from_spec(_c)
_c.loader.exec_module(cp)

HOLD = 63
N_RANDOM = 300
N_BOOT = 2000
MIN_PICKS = 5


def trailing_support(low: np.ndarray, spot: float, k: int = 5):
    lows = []
    for i in range(k, len(low) - k):
        w = low[i - k:i + k + 1]
        if low[i] == w.min() and (w == low[i]).sum() == 1:
            lows.append((i, float(low[i])))
    cl = [c for c in cp.cluster(lows, len(low)) if c["price"] < spot * 0.995]
    if not cl:
        return np.nan
    strong = [c for c in cl if c["touches"] >= 2]
    return max((strong or cl), key=lambda c: c["price"])["price"]


def panel(P, close, high, low, vol, syms, dates, elig):
    """Every rule's condition, evaluated as of each rebalance date."""
    C, L, V = P["close"], low[syms], vol[syms]
    rows = []
    for d in dates:
        el = elig.get(d)
        if not el:
            continue
        i = C.index.get_loc(d)
        win = slice(max(0, i - 504), i + 1)
        sub = C.iloc[win]
        spot = sub.iloc[-1]
        sma200 = sub.tail(200).mean()
        tr = (sub.tail(15).max() - sub.tail(15).min())
        v = V.iloc[win]
        vsurge = v.tail(5).mean() / v.tail(60).mean()
        for s in el:
            p = spot.get(s, np.nan)
            if not np.isfinite(p):
                continue
            ll = L[s].iloc[win].to_numpy()
            ll = ll[np.isfinite(ll)]
            if len(ll) < 80:
                continue
            sup = trailing_support(ll, float(p))
            atrv = float(tr.get(s, np.nan)) / 14 if np.isfinite(tr.get(s, np.nan)) else np.nan
            anchors = [x for x in (sup, float(sma200.get(s, np.nan)),
                                   float(p) - 1.5 * atrv if np.isfinite(atrv) else np.nan)
                       if np.isfinite(x) and x < p]
            zone_hi = np.median(anchors) if anchors else np.nan
            rows.append({"date": d, "symbol": s, "price": float(p),
                         "in_zone": bool(anchors) and p <= zone_hi * 1.03,
                         "n_anchors": len(anchors),
                         "vol_surge": float(vsurge.get(s, np.nan))})
    return pd.DataFrame(rows)


def score(df, mask, fwd, rng, label):
    per = []
    for d, g in df.groupby("date"):
        r = fwd.loc[g.index]
        ok = r.notna()
        if ok.sum() < 60:
            continue
        m = mask.loc[g.index] & ok
        if m.sum() < MIN_PICKS:
            continue
        pool = r[ok].to_numpy()
        n = min(int(m.sum()), 40)
        ctrl = float(pool[rng.integers(0, len(pool), (N_RANDOM, n))].mean(axis=1).mean())
        per.append((d, float(r[m].mean()), ctrl, int(m.sum())))
    if len(per) < 20:
        say(f"  {label}: only {len(per)} usable dates -- not enough to say anything")
        return None
    x = pd.DataFrame(per, columns=["date", "sel", "ctrl", "n"])
    e = (x["sel"] - x["ctrl"]).to_numpy()
    b = e[rng.integers(0, len(e), (N_BOOT, len(e)))].mean(axis=1)
    p = min(float((np.sign(b) != np.sign(e.mean())).mean() * 2), 1.0)
    say(f"  {label:<34}{len(x):>5} dates{x['n'].mean():>7.0f} picks"
        f"{x['sel'].mean()*100:>8.2f}%{x['ctrl'].mean()*100:>8.2f}%"
        f"{e.mean()*100:>8.2f}%{(e>0).mean()*100:>6.0f}%{p:>7.3f}")
    return e.mean() * 100, p


def main() -> None:
    only = sys.argv[sys.argv.index("--only") + 1] if "--only" in sys.argv else None
    P, fwd_df, dates, elig = op.prep(hold=HOLD)
    close = P["close"]
    low = pd.read_csv(os.path.join(op.LONG, "px_low.csv"), index_col=0,
                      parse_dates=True).sort_index()
    high = pd.read_csv(os.path.join(op.LONG, "px_high.csv"), index_col=0,
                       parse_dates=True).sort_index()
    vol = pd.read_csv(os.path.join(op.LONG, "px_volume.csv"), index_col=0,
                      parse_dates=True).sort_index()
    syms = list(close.columns.intersection(
        pd.read_csv(os.path.join(HERE, "sp500.csv")).symbol))
    say("building conditions at every rebalance date ...")
    df = panel(P, close, high, low, vol, syms, dates, elig)
    f = fwd_df.stack().rename("fwd").reset_index()
    f.columns = ["date", "symbol", "fwd"]
    df = df.merge(f, on=["date", "symbol"], how="left")
    fwd = df["fwd"]
    say(f"{len(df):,} rows over {df['date'].nunique()} dates "
        f"({df['date'].min():%Y-%m} .. {df['date'].max():%Y-%m})\n")

    rng = np.random.default_rng(42)
    say(f"  {'rule':<34}{'dates':>5}{'picks':>13}{'signal':>8}"
        f"{'random':>8}{'EDGE':>8}{'win':>6}{'p':>7}")
    say("  " + "-" * 90)

    if only in (None, "buyzone"):
        say("\nBUYZONE  (fully testable, price-only)")
        score(df, df["in_zone"].fillna(False), fwd, rng, "in zone")
        score(df, (df["in_zone"] & (df["n_anchors"] >= 2)).fillna(False), fwd,
              rng, "in zone, 2+ anchors below")

    if only in (None, "bigmoney"):
        say("\nBIGMONEY  (PROXY ONLY -- no historical option chains exist)")
        say("  proxy: share-volume surge, which unusual option activity leaves")
        for thr, lab in ((1.5, "volume > 1.5x its 60d avg"),
                         (2.0, "volume > 2.0x its 60d avg"),
                         (3.0, "volume > 3.0x its 60d avg")):
            score(df, (df["vol_surge"] > thr).fillna(False), fwd, rng, lab)

    if only in (None, "analyst"):
        say("\nANALYST  (NOT testable here -- stated, not faked)")
        say("  The tape holds only the last 8 ratings per stock, so its history")
        say("  is recency-selected rather than a record. What was measured on")
        say("  11,570 dated events with a same-stock nearby-day control:")
        say("      entry on the public rating date:  -0.67% to -1.55% / month")
        say("      placebo on random dates:          -0.01%")
        say("      Bonferroni-corrected p:            0.0005")
        say("  See research/cards/2026-09-07-analyst-date-selection.md")

    say("\n" + "  " + "-" * 90)
    say("  EDGE = signal minus random baskets, same size, same dates, same")
    say("  point-in-time universe. Only EDGE means anything; the raw 'signal'")
    say("  column is inflated by survivorship and is shown to prove it.")
    say("\n  WHAT THIS MEANS FOR THE LEDGERS")
    say("  A ledger whose rule backtests negative is not going to surprise you")
    say("  by being positive live. Keep it running anyway -- a rule you have")
    say("  measured and rejected is more useful than one you never tested,")
    say("  because it tells you what NOT to do with the next signal you see.")


if __name__ == "__main__":
    main()
