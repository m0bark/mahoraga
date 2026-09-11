"""Why did a +0.212R strategy lose 35.6% of the account on QuantConnect?

    python research/sheet/trigger_diagnose.py

THE QUESTION
The local study reported the 3:1 trigger at +0.212R per trade against +0.065R
for buying at market, positive in all 14 years. Run on QC with working bracket
exits over the same window it finished at $64,397 from $100,000 while SPY
roughly tripled. Both cannot be right, so one of them is measuring something
other than what it claims.

R IS A RATIO, NOT MONEY. That is the suspicion being tested here. One R is the
distance from the entry down to support, and that distance is a DIFFERENT
fraction of the price on every single trade. A trade risking 4% of the price
and a trade risking 35% of the price both count as -1.00R when they lose.
Average them and the result has no dollar meaning at all. If the losing trades
systematically risk more of the price than the winning trades gain, then R
expectancy is positive while the account bleeds, and nothing in the earlier
test would have caught it.

WHAT IS MEASURED
  1. mean R                  reproduces the original number as a control
  2. mean PERCENT return     the same trades in units that buy groceries
  3. risk width by outcome   is a loser's 1R wider than a winner's?
  4. bars held by outcome    a close stop resolves fast, a far target does not
  5. return per bar          capital is finite, so time in a trade is a cost
  6. a PORTFOLIO SIMULATION  10 slots, 9% each, cash account, no borrowing,
                             which is what QC actually ran
  7. stop fills at the bar LOW instead of exactly at support, to bracket how
     much of any damage is slippage rather than the signal itself

The percent and portfolio figures are the honest ones. If they are negative
while R is positive, the earlier conclusion was a unit error and the QC result
is simply correct.
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

EXPIRY_DAYS = 21
HOLD_DAYS = 126
RATIO = 3.0
SLOTS = 10
POS_PCT = 0.09
START_CASH = 100_000.0


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
    """Which level is touched first. Returns the outcome, the bar offset, and
    the bar's low on a stop hit so the fill can be bracketed between support
    (what the original test assumed) and the low (the worst it could be)."""
    fh = H[start:start + limit]
    fl = L[start:start + limit]
    for j in range(min(len(fh), limit)):
        if np.isfinite(fl[j]) and fl[j] <= stop_px:
            return "loss", j, float(fl[j])
        if np.isfinite(fh[j]) and fh[j] >= target_px:
            return "win", j, target_px
    return "open", min(len(fh), limit), np.nan


def main() -> None:
    P, fwd, dates, elig = op.prep(hold=63)
    C = P["close"]
    H = pd.read_csv(os.path.join(op.LONG, "px_high.csv"), index_col=0,
                    parse_dates=True).sort_index()
    L = pd.read_csv(os.path.join(op.LONG, "px_low.csv"), index_col=0,
                    parse_dates=True).sort_index()

    rows, mrows = [], []
    armed = 0

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
            S, Rt = sup["price"], res["price"]
            if Rt <= S:
                continue
            T = S + (Rt - S) / (RATIO + 1)
            if T >= spot:
                continue
            armed += 1

            fullH = H[s].to_numpy()
            fullL = L[s].to_numpy()
            fullC = C[s].to_numpy()

            fill_at = None
            for j in range(1, EXPIRY_DAYS + 1):
                k = i + j
                if k >= len(fullL):
                    break
                if np.isfinite(fullL[k]) and fullL[k] <= T:
                    fill_at = k
                    break

            if fill_at is not None:
                out, j, lowpx = walk(fullH, fullL, fill_at + 1, S, Rt)
                exit_i = fill_at + 1 + j
                # THE SAME ENTRY WITH NO STOP AT ALL. If the entry has real
                # forecasting content it should survive without a 1.5%-away
                # stop protecting it; if the result collapses without the stop
                # then the stop was the strategy, and a stop that close is a
                # bet on fill quality rather than on the company.
                o2, j2, _ = walk(fullH, fullL, fill_at + 1, -1e9, Rt)
                if o2 == "win":
                    px2 = Rt
                    exit2_i = fill_at + 1 + j2
                else:
                    exit2_i = min(fill_at + HOLD_DAYS, len(fullC) - 1)
                    px2 = float(fullC[exit2_i])
                if out == "win":
                    exit_px = exit_worst = Rt
                    r_mult = RATIO
                elif out == "loss":
                    exit_px, exit_worst = S, min(S, lowpx)
                    r_mult = -1.0
                else:
                    k2 = min(fill_at + HOLD_DAYS, len(fullC) - 1)
                    exit_px = exit_worst = float(fullC[k2])
                    exit_i = k2
                    r_mult = (exit_px - T) / max(T - S, 1e-9)
                rows.append({
                    "date": d, "sym": s, "out": out, "r": r_mult,
                    "entry_i": fill_at, "exit_i": exit_i,
                    "entry_px": T, "exit_px": exit_px, "exit_worst": exit_worst,
                    "risk_pct": (T - S) / T * 100,
                    "reward_pct": (Rt - T) / T * 100,
                    "bars": max(exit_i - fill_at, 1),
                    "nostop_pct": (px2 / T - 1) * 100,
                    "nostop_exit_i": exit2_i,
                    "nostop_px": px2,
                    "nostop_bars": max(exit2_i - fill_at, 1),
                    # RETRACTED COMPARISON, kept so the mistake stays visible.
                    # This shares an EXIT price with the trigger arm while
                    # entering higher, so the trigger beats it by arithmetic on
                    # every single trade and the difference came back with
                    # t = +100.88. A t of 100 is not a strong result, it is
                    # proof that the quantity is deterministic. Do not use it.
                    "buyhold_same_exit_pct": (float(fullC[exit2_i]) / spot - 1)
                    * 100,
                    # THE HONEST VERSION: a FIXED 63-day horizon measured from
                    # the fill, so neither arm inherits the other's exit.
                    "fix63_pct": (float(fullC[min(fill_at + 63,
                                                  len(fullC) - 1)]) / T - 1)
                    * 100,
                })

            out_m, jm, lowm = walk(fullH, fullL, i + 1, S, Rt)
            if out_m == "win":
                ex_m = Rt
            elif out_m == "loss":
                ex_m = S
            else:
                ex_m = float(fullC[min(i + HOLD_DAYS, len(fullC) - 1)])
            mrows.append({"out": out_m, "entry_px": spot, "exit_px": ex_m,
                          "risk_pct": (spot - S) / spot * 100,
                          "bars": max(jm + 1, 1),
                          "filled": fill_at is not None,
                          # buy at the close on the decision date and hold 63
                          # days. Recorded for EVERY armed candidate, including
                          # the 27.8% whose limit never filled, because those
                          # are the names that ran away and leaving them out is
                          # what made the first comparison meaningless.
                          "bh63_pct": (float(fullC[min(i + 63,
                                                       len(fullC) - 1)]) / spot
                                       - 1) * 100,
                          "r": (RATIO if out_m == "win" else
                                -1.0 if out_m == "loss" else
                                (ex_m - spot) / max(spot - S, 1e-9))})

    t = pd.DataFrame(rows)
    m_ = pd.DataFrame(mrows)
    if t.empty:
        say("no fills")
        return

    t["pct"] = (t.exit_px / t.entry_px - 1) * 100
    t["pct_worst"] = (t.exit_worst / t.entry_px - 1) * 100
    m_["pct"] = (m_.exit_px / m_.entry_px - 1) * 100

    say("")
    say("=" * 72)
    say("  1-2. THE SAME TRADES IN TWO DIFFERENT UNITS")
    say("=" * 72)
    say(f"{'':<24}{'n':>8}{'mean R':>11}{'mean %':>11}{'median %':>11}")
    say("-" * 72)
    say(f"{'TRIGGER (limit)':<24}{len(t):>8,}{t.r.mean():>+10.3f}R"
        f"{t.pct.mean():>+10.2f}%{t.pct.median():>+10.2f}%")
    say(f"{'MARKET (buy now)':<24}{len(m_):>8,}{m_.r.mean():>+10.3f}R"
        f"{m_.pct.mean():>+10.2f}%{m_.pct.median():>+10.2f}%")
    say(f"{'TRIGGER, stop at low':<24}{len(t):>8,}{'':>11}"
        f"{t.pct_worst.mean():>+10.2f}%{t.pct_worst.median():>+10.2f}%")
    say(f"{'TRIGGER, NO STOP':<24}{len(t):>8,}{'':>11}"
        f"{t.nostop_pct.mean():>+10.2f}%{t.nostop_pct.median():>+10.2f}%")
    say("")
    say(f"  win rate   trigger {(t.out == 'win').mean() * 100:.1f}%   "
        f"market {(m_.out == 'win').mean() * 100:.1f}%")
    say("")
    say("  If mean R is positive and mean % is negative, R was the wrong unit.")

    say("")
    say("=" * 72)
    say("  3. HOW WIDE IS 1R, BY OUTCOME")
    say("=" * 72)
    say(f"{'outcome':<12}{'n':>8}{'share':>9}{'risk width':>13}{'mean %':>11}")
    say("-" * 72)
    for o in ("win", "loss", "open"):
        g = t[t.out == o]
        if g.empty:
            continue
        say(f"{o:<12}{len(g):>8,}{len(g)/len(t)*100:>8.1f}%"
            f"{g.risk_pct.mean():>12.2f}%{g.pct.mean():>+10.2f}%")
    say("")
    say("  1R on a loser against 1R on a winner is the whole question. If the")
    say("  loser risks more of the price, every -1.00R costs more than every")
    say("  +3.00R earns and the ratio is lying about the money.")

    say("")
    say("=" * 72)
    say("  4-5. TIME IS A COST")
    say("=" * 72)
    say(f"{'outcome':<12}{'n':>8}{'mean bars':>12}{'%/bar':>12}{'ann. %':>11}")
    say("-" * 72)
    for o in ("win", "loss", "open"):
        g = t[t.out == o]
        if g.empty:
            continue
        per = (g.pct / g.bars).mean()
        say(f"{o:<12}{len(g):>8,}{g.bars.mean():>11.1f}{per:>+11.3f}%"
            f"{per*252:>+10.1f}%")
    allper = (t.pct / t.bars).mean()
    say("-" * 72)
    say(f"{'ALL':<12}{len(t):>8,}{t.bars.mean():>11.1f}{allper:>+11.3f}%"
        f"{allper*252:>+10.1f}%")

    say("")
    say("=" * 72)
    say("  6. PORTFOLIO SIMULATION -- what QC actually ran")
    say("=" * 72)
    say(f"  {SLOTS} slots, {POS_PCT*100:.0f}% of equity each, cash account, "
        f"no borrowing")
    for label, col in (("stop exactly at support", "exit_px"),
                       ("stop fills at the bar low", "exit_worst")):
        eq = simulate(t, col)
        say(f"  {label:<28} final ${eq:>12,.0f}   "
            f"{(eq / START_CASH - 1) * 100:>+7.1f}%")
    say(f"  {'SPY over the same window':<28} {'':>13}  {spy_return(C):>+7.1f}%")

    say("")
    say("=" * 72)
    say("  7. IS WAITING FOR THE TRIGGER WORTH ANYTHING AT ALL?")
    say("=" * 72)
    say("  Fixed 63-day horizon for both arms, so neither inherits the other's")
    say("  exit price. The buy-now arm is measured on ALL armed candidates,")
    say("  including the ones whose limit never filled, because those are the")
    say("  names that ran away and excluding them is what broke the first")
    say("  version of this comparison.")
    fr = len(t) / max(armed, 1)
    trig63 = t["fix63_pct"]
    blended = trig63.mean() * fr          # unfilled triggers earn cash, 0%
    bh_all = m_["bh63_pct"]
    bh_filled = m_.loc[m_.filled, "bh63_pct"]
    say("")
    say(f"  {'trigger, filled only':<44}{trig63.mean():>+9.2f}%"
        f"{trig63.median():>+10.2f}%")
    say(f"  {'trigger, blended (unfilled = 0%)':<44}{blended:>+9.2f}%")
    say(f"  {'buy now, only names that later filled':<44}"
        f"{bh_filled.mean():>+9.2f}%{bh_filled.median():>+10.2f}%")
    say(f"  {'buy now, EVERY armed candidate':<44}{bh_all.mean():>+9.2f}%"
        f"{bh_all.median():>+10.2f}%")
    say("")
    say(f"  fill rate {fr * 100:.1f}%   so {100 - fr * 100:.1f}% of the time the "
        f"limit earns nothing")
    say(f"  holding period when no stop is used: {t.nostop_bars.mean():.0f} "
        f"trading days mean, {t.nostop_bars.median():.0f} median")
    say("")
    edge = blended - bh_all.mean()
    se = np.sqrt(trig63.var(ddof=1) / len(trig63)
                 + bh_all.var(ddof=1) / len(bh_all))
    say(f"  STRATEGY minus CONTROL: {edge:+.2f}%  "
        f"(rough t {edge / se if se > 0 else float('nan'):+.2f})")
    if edge > 0:
        say("  Waiting survives the honest control.")
    else:
        say("  Waiting LOSES to simply buying. The gap between the two buy-now")
        say("  rows is the whole illusion: the limit only fills on names that")
        say("  fell, so comparing against that subset flatters it. Measured")
        say("  against every candidate it was armed on, the limit is behind.")

    say("")
    say("=" * 72)
    say("  BY YEAR, in percent rather than R")
    say("=" * 72)
    t["yr"] = pd.to_datetime(t.date).dt.year
    say(f"   {'year':<7}{'n':>7}{'win%':>8}{'mean R':>10}{'mean %':>10}")
    for y, g in t.groupby("yr"):
        if len(g) < 20:
            continue
        say(f"   {int(y):<7}{len(g):>7}{(g.out == 'win').mean() * 100:>7.1f}%"
            f"{g.r.mean():>+9.3f}R{g.pct.mean():>+9.2f}%")

    say("")
    say(f"FILL RATE: {len(t):,} of {armed:,} armed "
        f"({len(t) / max(armed, 1) * 100:.1f}%)")

    # the ledger is expensive to regenerate (the pivot scan is the slow part),
    # so anything that wants to re-cut these same trades by another variable
    # reads the CSV instead of recomputing them and risking a different universe
    if "--dump" in sys.argv:
        p = os.path.join(op.LONG, "trigger_trades.csv")
        t.to_csv(p, index=False)
        say(f"\nwrote {len(t):,} trades to {p}")


def simulate(t: pd.DataFrame, exit_col: str) -> float:
    """10 slots, fixed fraction of equity, no borrowing, entries in bar order.
    Deliberately generous: no commission, no slippage on entry, and a slot is
    freed the same bar its trade resolves."""
    df = t.sort_values("entry_i")
    by_entry: dict = {}
    for rec in df.itertuples():
        by_entry.setdefault(int(rec.entry_i), []).append(rec)
    exits: dict = {}
    cash = START_CASH
    book: dict = {}
    nxt = 0
    for i in range(int(df.entry_i.min()), int(df.exit_i.max()) + 1):
        for key in exits.pop(i, []):
            sh, _cb, xp = book.pop(key)
            cash += sh * xp
        for rec in by_entry.get(i, []):
            if len(book) >= SLOTS:
                continue
            equity = cash + sum(sh * cb for sh, cb, _ in book.values())
            want = equity * POS_PCT
            if want > cash or rec.entry_px <= 0:
                continue
            sh = want / rec.entry_px
            nxt += 1
            key = nxt
            book[key] = (sh, rec.entry_px, float(getattr(rec, exit_col)))
            cash -= sh * rec.entry_px
            exits.setdefault(int(rec.exit_i), []).append(key)
    cash += sum(sh * xp for sh, _cb, xp in book.values())
    return cash


def spy_return(C: pd.DataFrame) -> float:
    if "SPY" not in C.columns:
        return float("nan")
    s = C["SPY"].dropna()
    s = s[s.index >= "2013-01-01"]
    if s.empty:
        return float("nan")
    return (s.iloc[-1] / s.iloc[0] - 1) * 100


if __name__ == "__main__":
    main()
