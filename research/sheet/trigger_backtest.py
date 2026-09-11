"""Backtest the ACTUAL mechanic: arm a limit at the 3:1 price and wait.

    python research/sheet/trigger_backtest.py
    python research/sheet/trigger_backtest.py --ratio 2   # test 2:1 instead

WHY THIS IS NOT THE EARLIER R:R TEST
The earlier study bucketed stocks by whatever R:R they happened to have at a
month end. That measures the population, not the strategy. What you would
actually do is different in three ways that all cost money:

  1. YOU WAIT. The limit sits at support + range/4 and may never trade there.
     A trigger that never fills is capital doing nothing, and it is usually
     the strongest names that never come back to your price.
  2. YOU CAN BE WRONG ABOUT THE FILL. A limit fills AT the limit, not at the
     bar's low. Assuming otherwise is free money.
  3. THE TRADE HAS AN EXIT. Support hit first = loss. Resistance hit first =
     win. Whichever comes first is what you actually got, so the walk is done
     bar by bar rather than by comparing end prices.

WHAT IS COMPARED
  TRIGGER   arm the limit, wait up to EXPIRY_DAYS, take the fill if it comes
  MARKET    buy the same name the same day at the close, no waiting
  RANDOM    same stock, entry date shuffled within the year

The number that decides it is expectancy in R -- units of the risk you took.
+0.30R means every trade is worth 0.30x whatever you put at risk, and it is
comparable across stocks and position sizes in a way percentages are not.

FILL RATE IS THE HIDDEN VARIABLE. If only 40% of triggers fill, the strategy
has to earn its keep on 40% of the opportunities while the other 60% sat in
cash, and that is reported explicitly rather than buried.
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
_c = importlib.util.spec_from_file_location("cp", os.path.join(HERE, "compute.py"))
cp = importlib.util.module_from_spec(_c)
_c.loader.exec_module(cp)

EXPIRY_DAYS = 21          # how long the limit stays good
HOLD_DAYS = 126           # how long to wait for target or stop after filling
RATIO = 3.0


def levels(high, low, spot, k=5):
    lows, highs = [], []
    for i in range(k, len(low) - k):
        w = low[i - k:i + k + 1]
        if low[i] == w.min() and (w == low[i]).sum() == 1:
            lows.append((i, float(low[i])))
        w = high[i - k:i + k + 1]
        if high[i] == w.max() and (w == high[i]).sum() == 1:
            highs.append((i, float(high[i])))
    sup = [c for c in cp.cluster(lows, len(low)) if c["price"] < spot * 0.995]
    res = [c for c in cp.cluster(highs, len(high)) if c["price"] > spot * 1.005]
    s = max(sup, key=lambda c: c["price"]) if sup else None
    r = min(res, key=lambda c: c["price"]) if res else None
    return s, r


def walk(H, L, start, stop_px, target_px, limit=HOLD_DAYS):
    """Bar by bar: which level is touched FIRST. Same-bar ties go to the stop,
    because assuming the good outcome on an ambiguous bar is how backtests
    lie."""
    fh = H[start:start + limit]
    fl = L[start:start + limit]
    for j in range(min(len(fh), limit)):
        lo_hit = np.isfinite(fl[j]) and fl[j] <= stop_px
        hi_hit = np.isfinite(fh[j]) and fh[j] >= target_px
        if lo_hit:
            return "loss", j
        if hi_hit:
            return "win", j
    return "open", limit


def main() -> None:
    ratio = float(sys.argv[sys.argv.index("--ratio") + 1]) \
        if "--ratio" in sys.argv else RATIO
    P, fwd, dates, elig = op.prep(hold=63)
    C = P["close"]
    H = pd.read_csv(os.path.join(op.LONG, "px_high.csv"), index_col=0,
                    parse_dates=True).sort_index()
    L = pd.read_csv(os.path.join(op.LONG, "px_low.csv"), index_col=0,
                    parse_dates=True).sort_index()
    say(f"testing a {ratio:.0f}:1 trigger, limit good for {EXPIRY_DAYS} days, "
        f"then {HOLD_DAYS} days to resolve\n")

    rng = np.random.default_rng(8)
    trig, mkt, rnd = [], [], []
    armed = filled = 0

    for d in dates:
        el = elig.get(d)
        if not el:
            continue
        i = C.index.get_loc(d)
        if i + EXPIRY_DAYS + HOLD_DAYS >= len(C):
            continue
        win = slice(max(0, i - 504), i + 1)
        for s in el:
            if s not in C.columns or s not in H.columns:
                continue
            c = C[s].iloc[win].to_numpy()
            hh = H[s].iloc[win].to_numpy()
            ll = L[s].iloc[win].to_numpy()
            m = np.isfinite(c) & np.isfinite(hh) & np.isfinite(ll)
            if m.sum() < 120:
                continue
            spot = float(c[m][-1])
            if spot <= 0:
                continue
            sup, res = levels(hh[m], ll[m], spot)
            if sup is None or res is None:
                continue
            S, R = sup["price"], res["price"]
            if R <= S:
                continue
            trigger = S + (R - S) / (ratio + 1)
            if trigger >= spot:            # already at or below the trigger
                continue
            armed += 1

            fullH = H[s].to_numpy()
            fullL = L[s].to_numpy()
            # ---- does the limit fill inside its life?
            fill_at = None
            for j in range(1, EXPIRY_DAYS + 1):
                k = i + j
                if k >= len(fullL):
                    break
                if np.isfinite(fullL[k]) and fullL[k] <= trigger:
                    fill_at = k
                    break
            if fill_at is not None:
                filled += 1
                out, _ = walk(fullH, fullL, fill_at + 1, S, R)
                r_mult = (ratio if out == "win" else -1.0 if out == "loss"
                          else (float(C[s].iloc[min(fill_at + HOLD_DAYS,
                                                    len(C) - 1)]) - trigger)
                          / max(trigger - S, 1e-9))
                trig.append({"date": d, "sym": s, "out": out, "r": r_mult})

            # ---- the comparison: buy at market today, same stop and target
            out_m, _ = walk(fullH, fullL, i + 1, S, R)
            rm = (( R - spot) / (spot - S) if out_m == "win"
                  else -1.0 if out_m == "loss"
                  else (float(C[s].iloc[min(i + HOLD_DAYS, len(C) - 1)]) - spot)
                  / max(spot - S, 1e-9))
            mkt.append({"date": d, "sym": s, "out": out_m, "r": rm})

            # ---- random entry, same stock, shuffled date
            j2 = i + int(rng.integers(-120, 121))
            if 520 < j2 < len(C) - HOLD_DAYS - 1:
                sp2 = float(C[s].iloc[j2])
                if sp2 > 0:
                    st2 = sp2 * (1 - (spot - S) / spot)
                    tg2 = sp2 * (1 + (R - spot) / spot)
                    out_r, _ = walk(fullH, fullL, j2 + 1, st2, tg2)
                    rr2 = ((tg2 - sp2) / (sp2 - st2) if out_r == "win"
                           else -1.0 if out_r == "loss" else 0.0)
                    rnd.append({"out": out_r, "r": rr2})

    t = pd.DataFrame(trig)
    m_ = pd.DataFrame(mkt)
    r_ = pd.DataFrame(rnd)
    if t.empty:
        say("no fills")
        return

    say(f"{'':<22}{'n':>8}{'win%':>8}{'loss%':>8}{'open%':>8}{'expectancy':>13}")
    say("-" * 68)
    for lab, df in (("TRIGGER (limit)", t), ("MARKET (buy now)", m_),
                    ("RANDOM (shuffled)", r_)):
        if df.empty:
            continue
        w = (df.out == "win").mean() * 100
        l = (df.out == "loss").mean() * 100
        op_ = (df.out == "open").mean() * 100
        say(f"{lab:<22}{len(df):>8,}{w:>7.1f}%{l:>7.1f}%{op_:>7.1f}%"
            f"{df.r.mean():>+12.3f}R")
    say("-" * 68)
    say(f"\nFILL RATE: {filled:,} of {armed:,} triggers filled "
        f"({filled/max(armed,1)*100:.1f}%)")
    say(f"  {armed - filled:,} never traded at your price -- that capital did")
    say("  nothing, and those are disproportionately the names that ran away.")

    if not t.empty and not m_.empty:
        say(f"\nTRIGGER minus MARKET: {t.r.mean() - m_.r.mean():+.3f}R per trade")
        say(f"TRIGGER minus RANDOM: {t.r.mean() - r_.r.mean():+.3f}R per trade"
            if not r_.empty else "")
        # is waiting worth it once you account for the ones that never fill?
        blended = t.r.mean() * (filled / max(armed, 1))
        say(f"\nBLENDED, counting unfilled triggers as 0R: {blended:+.3f}R")
        say(f"versus just buying at market every time:    {m_.r.mean():+.3f}R")
        say("\nThat blended figure is the honest comparison. Waiting only wins")
        say("if the better entries more than pay for the trades you never got.")

    say("\nBY YEAR (trigger only)")
    t["yr"] = pd.to_datetime(t.date).dt.year
    say(f"   {'year':<7}{'n':>7}{'win%':>8}{'expectancy':>13}")
    for y, g in t.groupby("yr"):
        if len(g) < 20:
            continue
        say(f"   {int(y):<7}{len(g):>7}{(g.out=='win').mean()*100:>7.1f}%"
            f"{g.r.mean():>+12.3f}R")


if __name__ == "__main__":
    main()
