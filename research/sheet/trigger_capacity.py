"""Was the trigger under-deployed, or just not an edge? Sweep capacity locally.

    python research/sheet/trigger_capacity.py --build    # cache the candidates
    python research/sheet/trigger_capacity.py            # run the sweep

THE QUESTION
On QuantConnect the no-stop trigger with a fundamental gate returned +147.9%
over 13.45 years, about 7.0% a year, against roughly 9% for the index. The
per-trade economics replicated well: +1.59% on QC against +1.97% measured
locally, which is the haircut survivorship bias predicts. But it only armed
645 orders in 13.45 years, four a month, because MAX_LIVE_ORDERS was 4. So
capital sat idle and the question is whether the shortfall is deployment or
whether there was never an edge.

WHY THIS RUNS LOCALLY AND NOT ON QUANTCONNECT
Fifteen configurations is fifteen backtests, and the project has already been
told once by QC's own overfitting detector that it found 57 parameters. The
standing rule here is to sweep locally, with a control, and spend a single
backtest on the one configuration that survives. Local data omits delisted
companies so every figure below is the optimistic bound, which is exactly what
a screening pass should be.

THE CONTROL IS THE POINT
At every capacity level the same candidate list is also traded by BUYING AT THE
CLOSE on the decision date instead of resting a limit below the market. Same
names, same caps, same targets, same 126-day timeout, same sizing. If the limit
is worth anything it has to beat that arm, and the interesting number is not
whether the trigger improves with capacity but whether its ADVANTAGE over
buying survives being scaled up.

It probably will not. Raising the cap means arming the limits that sit further
below the market, and those are the adverse-selection trades: measured earlier,
a name that falls to your limit goes on to return half what the average
candidate returned. That is the hypothesis this file is built to kill.

WHAT IS REPORTED
The whole grid, not the best cell. A grid where one cell looks good and its
neighbours do not is noise with a coordinate.
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

CAND = os.path.join(op.LONG, "trigger_candidates.csv")

RATIO = 3.0
EXPIRY_DAYS = 21
HOLD_DAYS = 126
START_CASH = 100_000.0
CASH_USE = 0.95
LIVE_GRID = (4, 8, 12, 20, 30)
POS_GRID = (10, 20, 30)


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


def first_at_or_above(arr, lo, hi, level) -> int | None:
    for j in range(lo, min(hi, len(arr))):
        if np.isfinite(arr[j]) and arr[j] >= level:
            return j
    return None


def first_at_or_below(arr, lo, hi, level) -> int | None:
    for j in range(lo, min(hi, len(arr))):
        if np.isfinite(arr[j]) and arr[j] <= level:
            return j
    return None


def build() -> pd.DataFrame:
    """One expensive pass producing every armed candidate and the forward facts
    a simulation needs, so the sweep itself is pure bookkeeping."""
    P, fwd, dates, elig = op.prep(hold=63)
    C = P["close"]
    H = pd.read_csv(os.path.join(op.LONG, "px_high.csv"), index_col=0,
                    parse_dates=True).sort_index()
    L = pd.read_csv(os.path.join(op.LONG, "px_low.csv"), index_col=0,
                    parse_dates=True).sort_index()
    rows = []
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
            T = S + (R - S) / (RATIO + 1)
            if T >= spot:
                continue

            fh, fl, fc = (H[s].to_numpy(), L[s].to_numpy(), C[s].to_numpy())
            fill = first_at_or_below(fl, i + 1, i + 1 + EXPIRY_DAYS, T)
            rec = {
                "bar": i, "sym": s, "spot": spot, "trig": T, "targ": R,
                # how far the limit sits below the market. The QC algorithm
                # arms the NEAREST ones first, so the sweep must rank the same
                # way or it is testing a different strategy.
                "dist": (spot - T) / spot * 100,
                "fill_bar": -1 if fill is None else fill,
            }
            for tag, start, entry in (("t", fill, T), ("m", i, spot)):
                if start is None:
                    rec[f"{tag}_exit_bar"] = -1
                    rec[f"{tag}_exit_px"] = np.nan
                    continue
                tb = first_at_or_above(fh, start + 1, start + 1 + HOLD_DAYS, R)
                if tb is not None:
                    rec[f"{tag}_exit_bar"] = tb
                    rec[f"{tag}_exit_px"] = R
                else:
                    k = min(start + HOLD_DAYS, len(fc) - 1)
                    rec[f"{tag}_exit_bar"] = k
                    rec[f"{tag}_exit_px"] = float(fc[k])
            rows.append(rec)
    cand = pd.DataFrame(rows)
    cand.to_csv(CAND, index=False)
    say(f"\nwrote {len(cand):,} armed candidates to {CAND}")
    say(f"  fill rate if everything were armed: "
        f"{(cand.fill_bar >= 0).mean() * 100:.1f}%")
    say(f"  median distance below market: {cand.dist.median():.2f}%")
    return cand


def simulate(cand: pd.DataFrame, max_live: int, max_pos: int,
             arm: str = "trigger") -> dict:
    """Mirror of the QC algorithm: monthly arming, nearest limits first, a
    separate cap on live orders and on positions, sized off settled cash, exit
    at the target or after HOLD_DAYS with no stop.

    arm="market" replaces the resting limit with an immediate buy at the close,
    which is the control. Everything else is held identical."""
    by_bar: dict = {}
    for rec in cand.itertuples():
        by_bar.setdefault(int(rec.bar), []).append(rec)
    decision_bars = sorted(by_bar)
    last = int(max(cand.t_exit_bar.max(), cand.m_exit_bar.max()))

    cash = START_CASH
    live: dict = {}        # order id -> dict
    pos: dict = {}         # order id -> dict
    fills_at: dict = {}    # bar -> [order id]
    exits_at: dict = {}    # bar -> [order id]
    nxt = 0
    rets, deployed_bars, equity_curve = [], 0, []

    for b in range(decision_bars[0], last + 1):
        # ---- exits first so the cash is available to arm with
        for oid in exits_at.pop(b, []):
            p = pos.pop(oid, None)
            if p is None:
                continue
            cash += p["sh"] * p["exit_px"]
            rets.append((p["exit_px"] / p["entry"] - 1) * 100)
        # ---- fills
        for oid in fills_at.pop(b, []):
            o = live.pop(oid, None)
            if o is None:
                continue
            pos[oid] = o
            exits_at.setdefault(int(o["exit_bar"]), []).append(oid)
        # ---- expiry of unfilled limits
        for oid in [k for k, v in live.items() if b - v["armed"] >= EXPIRY_DAYS]:
            o = live.pop(oid)
            cash += o["reserved"]

        if b in by_bar:
            room = min(max_pos - len(pos), max_live - len(live))
            if room > 0:
                picks = sorted(by_bar[b], key=lambda r: r.dist)
                slot = cash * CASH_USE / room
                taken = 0
                for rec in picks:
                    if taken >= room:
                        break
                    entry = rec.trig if arm == "trigger" else rec.spot
                    fb = int(rec.fill_bar) if arm == "trigger" else int(rec.bar)
                    eb = int(rec.t_exit_bar if arm == "trigger"
                             else rec.m_exit_bar)
                    ep = (rec.t_exit_px if arm == "trigger" else rec.m_exit_px)
                    if entry <= 0 or slot > cash or not np.isfinite(ep):
                        continue
                    if arm == "trigger" and fb < 0:
                        # armed, never filled. It still RESERVES cash in a cash
                        # account for as long as it rests, which is the cost
                        # the earlier per-trade study ignored entirely.
                        nxt += 1
                        live[nxt] = {"armed": b, "reserved": slot,
                                     "sh": 0.0, "entry": entry,
                                     "exit_bar": -1, "exit_px": np.nan}
                        cash -= slot
                        taken += 1
                        continue
                    if eb <= fb:
                        continue
                    nxt += 1
                    sh = slot / entry
                    o = {"armed": b, "reserved": slot, "sh": sh,
                         "entry": entry, "exit_bar": eb, "exit_px": ep}
                    cash -= slot
                    # A fill dated on or before the current bar has to be
                    # booked NOW. Fills for bar b were already processed at the
                    # top of this iteration, so scheduling one into fills_at[b]
                    # would leave it pending forever -- which silently gave the
                    # market arm zero trades, i.e. a control that could not
                    # lose. The market arm buys at the close of the decision
                    # bar, so it lands here every time.
                    if fb <= b:
                        pos[nxt] = o
                        exits_at.setdefault(eb, []).append(nxt)
                    else:
                        live[nxt] = o
                        fills_at.setdefault(fb, []).append(nxt)
                    taken += 1

        invested = sum(p["sh"] * p["entry"] for p in pos.values())
        if pos:
            deployed_bars += 1
        equity_curve.append(cash + invested
                            + sum(o["reserved"] for o in live.values()))

    final = cash + sum(p["sh"] * p["exit_px"] for p in pos.values()) \
        + sum(o["reserved"] for o in live.values())
    eq = pd.Series(equity_curve)
    peak = eq.cummax()
    dd = ((eq - peak) / peak).min() * 100
    years = len(eq) / 252.0
    return {
        "final": final,
        "cagr": ((final / START_CASH) ** (1 / years) - 1) * 100 if years else 0,
        "n": len(rets),
        "mean": float(np.mean(rets)) if rets else np.nan,
        "deployed": deployed_bars / max(len(eq), 1) * 100,
        "dd": dd,
        "years": years,
    }


def benchmark() -> float:
    """Equal-weight the eligible universe, rebalanced monthly. The thing any of
    this has to beat, and it needs no skill at all."""
    P, fwd, dates, elig = op.prep(hold=63)
    C = P["close"]
    eq, prev = 1.0, None
    for d in dates:
        if prev is not None:
            a, b = C.index.get_loc(prev), C.index.get_loc(d)
            names = [s for s in elig[prev] if s in C.columns]
            r = (C[names].iloc[b] / C[names].iloc[a] - 1).dropna()
            if len(r):
                eq *= (1 + r.mean())
        prev = d
    yrs = (C.index.get_loc(dates[-1]) - C.index.get_loc(dates[0])) / 252.0
    return (eq ** (1 / yrs) - 1) * 100


def main() -> None:
    if "--build" in sys.argv or not os.path.exists(CAND):
        cand = build()
    else:
        cand = pd.read_csv(CAND)
        say(f"{len(cand):,} cached candidates")
    say(f"  fill rate over ALL candidates: "
        f"{(cand.fill_bar >= 0).mean() * 100:.1f}%")

    bm = benchmark()
    say(f"\nBENCHMARK, equal-weight eligible universe, monthly: {bm:+.2f}%/yr")
    say("Everything below must beat that, not zero.\n")

    say("=" * 88)
    say("  CAPACITY SWEEP -- trigger against buying at market, same caps")
    say("=" * 88)
    say(f"  {'live':>5}{'pos':>5}  {'TRIGGER cagr':>14}{'n':>7}{'/trade':>9}"
        f"{'dep%':>7}  {'MARKET cagr':>13}{'n':>7}  {'edge':>8}")
    say("  " + "-" * 84)
    best = None
    grid = []
    for mp in POS_GRID:
        for ml in LIVE_GRID:
            if ml > mp:
                continue
            t = simulate(cand, ml, mp, "trigger")
            m = simulate(cand, ml, mp, "market")
            edge = t["cagr"] - m["cagr"]
            grid.append({"live": ml, "pos": mp, "t": t["cagr"],
                         "m": m["cagr"], "edge": edge, "n": t["n"]})
            say(f"  {ml:>5}{mp:>5}  {t['cagr']:>+13.2f}%{t['n']:>7}"
                f"{t['mean']:>+8.2f}%{t['deployed']:>6.0f}%"
                f"  {m['cagr']:>+12.2f}%{m['n']:>7}  {edge:>+7.2f}%")
            if best is None or t["cagr"] > best["t"]:
                best = grid[-1]
        say("  " + "-" * 84)

    g = pd.DataFrame(grid)
    say("")
    say("=" * 88)
    say("  READING THE GRID")
    say("=" * 88)
    say(f"  best TRIGGER cell: live {best['live']}, pos {best['pos']}, "
        f"{best['t']:+.2f}%/yr")
    say(f"  the MARKET arm in that same cell:            {best['m']:+.2f}%/yr")
    say(f"  benchmark, no skill required:                {bm:+.2f}%/yr")
    say("")
    say(f"  cells where the trigger beats buying:  {(g.edge > 0).sum()} of {len(g)}")
    say(f"  cells where the trigger beats the benchmark: "
        f"{(g.t > bm).sum()} of {len(g)}")
    say(f"  mean edge over buying across the grid: {g.edge.mean():+.2f}%/yr")
    say("")
    say("  DOES THE EDGE SURVIVE SCALE? edge by live-order cap, averaged over")
    say("  the position caps. If this falls as the cap rises, the extra orders")
    say("  are the adverse-selection ones and capacity is not the fix.")
    for ml, sub in g.groupby("live"):
        say(f"    live {ml:>3}   edge {sub.edge.mean():>+7.2f}%/yr   "
            f"trigger {sub.t.mean():>+7.2f}%   trades {int(sub.n.mean()):>5}")
    say("")
    if (g.edge > 0).sum() <= len(g) / 2:
        say("  The limit does not reliably beat simply buying the same names.")
        say("  Capacity was not the problem. There is no edge to deploy.")
    elif (g.t > bm).sum() == 0:
        say("  The limit beats buying the same names but NOTHING in the grid")
        say("  beats the equal-weight benchmark. The selection is the problem,")
        say("  not the entry: a better entry into a worse basket.")
    else:
        say("  Some cells clear both bars. Before believing it, check that the")
        say("  neighbours of the best cell also clear them -- one good cell in")
        say(f"  a grid of {len(g)} is what noise looks like.")


if __name__ == "__main__":
    main()
