"""Does a high risk:reward setup actually pay? And do supports hold?

    python research/sheet/rr_backtest.py

TWO QUESTIONS, BOTH ANSWERABLE WITHOUT PREDICTING ANYTHING

 1. WHEN PRICE SITS AT SUPPORT, DOES IT BOUNCE OR BREAK?
    A base rate, not a forecast. Over the next 63 trading days, did price
    touch the resistance above (a WIN) before it broke the support below
    (a LOSS)? Whichever happened first is what a trader with that stop and
    that target would actually have got.

 2. DOES R:R PREDICT THE OUTCOME?
    R:R is arithmetic: a 3:1 setup breaks even at a 25% hit rate. That is
    true regardless of what markets do. What is NOT automatic is whether
    high-R:R setups keep their hit rate -- if a 3:1 setup only wins 15% of
    the time, the arithmetic works and the trade still loses money. So the
    test is: bucket by R:R, measure the ACTUAL hit rate, and compare it to
    the breakeven hit rate the arithmetic demands.

    R:R bucket    breakeven needs    actual        verdict
    3:1           25.0%              ?             pays if actual > breakeven

That comparison is the whole point. It cannot be argued with, and it does
not require the support level to have any predictive power at all.

Universe is point-in-time: in the index that day AND top-350 by dollar
volume three years earlier, so nothing is picked for what it later became.
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

HOLD = 63
NEAR_SUPPORT = 3.0        # "at support" means within this % of it


def levels(high, low, spot, k=5):
    """Nearest clustered swing low below and swing high above, from the
    window given -- no data after the decision date."""
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


def main() -> None:
    P, fwd, dates, elig = op.prep(hold=HOLD)
    C = P["close"]
    H = pd.read_csv(os.path.join(op.LONG, "px_high.csv"), index_col=0,
                    parse_dates=True).sort_index()
    L = pd.read_csv(os.path.join(op.LONG, "px_low.csv"), index_col=0,
                    parse_dates=True).sort_index()
    say(f"{len(dates)} rebalance dates, {C.index[0]:%Y-%m} .. {C.index[-1]:%Y-%m}\n")

    rows = []
    for d in dates:
        el = elig.get(d)
        if not el:
            continue
        i = C.index.get_loc(d)
        if i + HOLD >= len(C):
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
            if not np.isfinite(spot) or spot <= 0:
                continue
            sup, res = levels(hh[m], ll[m], spot)
            if sup is None or res is None:
                continue
            risk = (spot - sup["price"]) / spot * 100
            rew = (res["price"] - spot) / spot * 100
            if risk <= 0.2 or rew <= 0:
                continue
            # walk forward day by day: whichever level is touched FIRST is
            # the outcome. Checking only the final price would count a trade
            # that stopped out and recovered as a winner.
            fh = H[s].iloc[i + 1:i + 1 + HOLD].to_numpy()
            fl = L[s].iloc[i + 1:i + 1 + HOLD].to_numpy()
            outcome, bars = "neither", HOLD
            for j in range(min(len(fh), HOLD)):
                hit_lo = np.isfinite(fl[j]) and fl[j] <= sup["price"]
                hit_hi = np.isfinite(fh[j]) and fh[j] >= res["price"]
                if hit_lo and hit_hi:
                    outcome, bars = "loss", j        # same bar: assume the worse
                    break
                if hit_lo:
                    outcome, bars = "loss", j
                    break
                if hit_hi:
                    outcome, bars = "win", j
                    break
            end = float(C[s].iloc[i + HOLD])
            rows.append({"date": d, "symbol": s, "rr": rew / risk,
                         "risk": risk, "reward": rew, "outcome": outcome,
                         "bars": bars, "at_support": risk <= NEAR_SUPPORT,
                         "touches_ok": sup["touches"] >= 2 and res["touches"] >= 2,
                         "ret": end / spot - 1})
    x = pd.DataFrame(rows)
    # RANDOM-DATE CONTROL. Every bucket above shows a positive margin, but the
    # market rose over this window, so "touched resistance before support"
    # happens partly by drift alone. The control re-runs the IDENTICAL
    # measurement on the same stocks with the entry date shuffled inside the
    # same year, which keeps the regime and destroys only the setup. If the
    # real expectancy does not beat the shuffled one, R:R is measuring the
    # bull market, not the setup.
    if not x.empty:
        rng = np.random.default_rng(4)
        ctrl_rows = []
        idx_all = list(C.index)
        for d in dates:
            el = elig.get(d)
            if not el:
                continue
            i = C.index.get_loc(d)
            if i + HOLD >= len(C):
                continue
            for s in rng.choice(el, size=min(len(el), 60), replace=False):
                shift = int(rng.integers(-120, 121))
                j = i + shift
                if j < 520 or j + HOLD >= len(C):
                    continue
                w2 = slice(max(0, j - 504), j + 1)
                c = C[s].iloc[w2].to_numpy()
                hh = H[s].iloc[w2].to_numpy() if s in H.columns else None
                ll = L[s].iloc[w2].to_numpy() if s in L.columns else None
                if hh is None or ll is None:
                    continue
                m = np.isfinite(c) & np.isfinite(hh) & np.isfinite(ll)
                if m.sum() < 120:
                    continue
                spot = float(c[m][-1])
                if spot <= 0:
                    continue
                sup, res = levels(hh[m], ll[m], spot)
                if sup is None or res is None:
                    continue
                risk = (spot - sup["price"]) / spot * 100
                rew = (res["price"] - spot) / spot * 100
                if risk <= 0.2 or rew <= 0:
                    continue
                fh = H[s].iloc[j + 1:j + 1 + HOLD].to_numpy()
                fl = L[s].iloc[j + 1:j + 1 + HOLD].to_numpy()
                out = "neither"
                for k2 in range(min(len(fh), HOLD)):
                    lo_hit = np.isfinite(fl[k2]) and fl[k2] <= sup["price"]
                    hi_hit = np.isfinite(fh[k2]) and fh[k2] >= res["price"]
                    if lo_hit:
                        out = "loss"; break
                    if hi_hit:
                        out = "win"; break
                ctrl_rows.append({"rr": rew / risk, "outcome": out})
        globals()["_CTRL"] = pd.DataFrame(ctrl_rows)
    if x.empty:
        say("nothing scorable")
        return
    say(f"{len(x):,} setups scored over {x['date'].nunique()} dates\n")

    # ---- 1. at support: bounce or break?
    at = x[x.at_support]
    say("1. WHEN PRICE IS AT SUPPORT (within 3%), WHAT HAPPENS NEXT?")
    say(f"   n = {len(at):,}")
    for lab, sub in (("all", at), ("levels 2+ touches", at[at.touches_ok])):
        if len(sub) < 50:
            continue
        w = (sub.outcome == "win").mean() * 100
        l = (sub.outcome == "loss").mean() * 100
        n = (sub.outcome == "neither").mean() * 100
        say(f"   {lab:<20} bounced to resistance {w:>5.1f}%   "
            f"broke support {l:>5.1f}%   neither {n:>5.1f}%")
    say("   'broke support' means it traded through the level first, not that")
    say("   it ended lower -- the stop would have been hit.\n")

    # ---- 2. does R:R deliver?
    say("2. DOES R:R PAY? actual hit rate vs the breakeven it needs")
    say(f"   {'R:R bucket':<12}{'n':>7}{'breakeven':>11}{'actual':>9}"
        f"{'margin':>9}{'avg ret':>9}")
    say("   " + "-" * 58)
    bins = [(0, 1, "under 1:1"), (1, 2, "1-2:1"), (2, 3, "2-3:1"),
            (3, 5, "3-5:1"), (5, 99, "over 5:1")]
    for lo, hi, lab in bins:
        g = x[(x.rr >= lo) & (x.rr < hi)]
        g = g[g.outcome != "neither"]
        if len(g) < 100:
            continue
        mid = g["rr"].median()
        be = 100 / (1 + mid)
        act = (g.outcome == "win").mean() * 100
        say(f"   {lab:<12}{len(g):>7,}{be:>10.1f}%{act:>8.1f}%"
            f"{act - be:>+8.1f}%{g['ret'].mean()*100:>8.2f}%")
    say("   " + "-" * 58)
    say("   margin = actual minus breakeven. POSITIVE means the arithmetic")
    say("   holds up: that bucket wins often enough to pay for its own losses.")
    say("   NEGATIVE means the setup looks asymmetric and is not.\n")

    # ---- 3. expectancy in R multiples, the number that decides it
    say("3. EXPECTANCY PER TRADE, in units of the risk you took (R)")
    say(f"   {'R:R bucket':<12}{'n':>7}{'win%':>7}{'expectancy':>12}")
    say("   " + "-" * 40)
    for lo, hi, lab in bins:
        g = x[(x.rr >= lo) & (x.rr < hi)]
        g = g[g.outcome != "neither"]
        if len(g) < 100:
            continue
        wr = (g.outcome == "win").mean()
        exp = wr * g["rr"].median() - (1 - wr) * 1.0
        say(f"   {lab:<12}{len(g):>7,}{wr*100:>6.1f}%{exp:>+11.2f}R")
    say("   " + "-" * 40)
    c = globals().get("_CTRL", pd.DataFrame())
    if len(c) > 500:
        say("")
        say("4. THE CONTROL -- same stocks, entry date shuffled within the year")
        say(f"   {'R:R bucket':<12}{'real exp':>10}{'shuffled':>11}{'DIFF':>9}{'n ctrl':>9}")
        say("   " + "-" * 52)
        for lo, hi, lab in bins:
            g = x[(x.rr >= lo) & (x.rr < hi)]
            g = g[g.outcome != "neither"]
            cg = c[(c.rr >= lo) & (c.rr < hi)]
            cg = cg[cg.outcome != "neither"]
            if len(g) < 100 or len(cg) < 50:
                continue
            mid = g["rr"].median()
            e1 = (g.outcome == "win").mean() * mid - (1 - (g.outcome == "win").mean())
            wr2 = (cg.outcome == "win").mean()
            e2 = wr2 * cg["rr"].median() - (1 - wr2)
            say(f"   {lab:<12}{e1:>+9.2f}R{e2:>+10.2f}R{e1-e2:>+8.2f}R{len(cg):>9,}")
        say("   " + "-" * 52)
        say("   DIFF is the setup's contribution after the market's own drift")
        say("   is removed. Near zero means R:R was measuring the bull market.")
        say("")
    say("   +0.30R means every trade is worth 0.30x whatever you risked.")
    say("   Risk $250 at +0.30R and the average trade is worth $75.")
    say("   NEGATIVE expectancy means the setup loses money however you size it.")


if __name__ == "__main__":
    main()
