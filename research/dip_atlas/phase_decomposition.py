# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = [
#     "pandas>=2.2",
#     "numpy>=1.26",
# ]
# ///
"""Iter7: where in a dip's lifecycle do the returns live?

For every >=20% dip episode, enter at the FIRST day of each point-in-time
phase and hold 120 trading days (no stop — isolating phase, not exit rules):

  freefall  new episode low within the last 5 days (includes the -20% cross)
  basing    episode low unbroken 6-20 days
  stall     low unbroken >20 days, price still < 10% above the low
  recovery  low unbroken >20 days AND price >= 10% above the low
  resolved  the day the episode ends (drawdown back to -5%)

Tier: SCOUTING (survivorship-biased cache; recovery-phase numbers are the
MOST inflated by survivorship — dead companies never reach recovery).
Run:  uv run --python 3.12 phase_decomposition.py
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
PRICES_500 = HERE.parent / "panic_reversal" / "prices500.pkl"
PRICES_IDX = HERE.parent / "panic_reversal" / "prices.pkl"

COST_PER_SIDE = 0.0010
HORIZON = 120
PHASE_ORDER = ["freefall", "basing", "stall", "recovery", "resolved"]


def episodes(dd: np.ndarray, n: int) -> list[tuple[int, int, bool]]:
    out, i = [], 252
    while i < n:
        if dd[i] <= -0.20 and dd[i - 1] > -0.20:
            end, censored = n - 1, True
            for j in range(i, n):
                if dd[j] >= -0.05:
                    end, censored = j, False
                    break
            out.append((i, end, censored))
            i = end + 20
        else:
            i += 1
    return out


def main() -> None:
    frames: dict[str, pd.DataFrame] = pd.read_pickle(PRICES_500)
    spy = pd.read_pickle(PRICES_IDX)["SPY"]["Close"]
    events: list[dict] = []

    for t, df in frames.items():
        n = len(df)
        if n < 400:
            continue
        closes = df["Close"].to_numpy()
        lows = df["Low"].to_numpy()
        opens = df["Open"].to_numpy()
        roll_high = df["Close"].rolling(252, min_periods=252).max().to_numpy()
        dd = closes / roll_high - 1.0
        idx = df.index

        for a, b, censored in episodes(dd, n):
            L, t_L = float(lows[a]), a
            seen: set[str] = set()
            day_list: list[tuple[int, str]] = []
            for j in range(a, b + 1):
                if lows[j] < L:
                    L, t_L = float(lows[j]), j
                held = j - t_L
                if held <= 5:
                    ph = "freefall"
                elif held <= 20:
                    ph = "basing"
                elif closes[j] >= 1.10 * L:
                    ph = "recovery"
                else:
                    ph = "stall"
                if ph not in seen:
                    seen.add(ph)
                    day_list.append((j, ph))
            if not censored:
                day_list.append((b, "resolved"))

            for j, ph in day_list:
                e0 = j + 1
                if e0 >= n - 1:
                    continue
                entry = float(opens[e0])
                x1 = min(e0 + HORIZON, n - 1)
                exit_px = float(closes[x1])
                net = (exit_px * (1 - COST_PER_SIDE)) / (entry * (1 + COST_PER_SIDE)) - 1.0
                spy_ret = float(spy.asof(idx[x1])) / float(spy.asof(idx[e0])) - 1.0
                events.append({
                    "ticker": t, "phase": ph, "date": idx[e0],
                    "days_into_episode": j - a,
                    "net": net, "excess": net - spy_ret,
                })

    e = pd.DataFrame(events)
    e.to_csv(HERE / "phase_events.csv", index=False)
    print("ITER7 — forward 120d returns by dip phase (first day of each phase,")
    print("plain hold, net 10bps/side). SCOUTING tier: survivorship-biased,")
    print("recovery/resolved numbers inflated most; clustering inflates t.\n")
    for ph in PHASE_ORDER:
        g = e[e.phase == ph]
        if g.empty:
            continue
        ex = g.excess
        tstat = ex.mean() / ex.std(ddof=1) * np.sqrt(len(ex))
        yrs = g.assign(y=g.date.dt.year).groupby("y").excess.mean()
        print(f"{ph:9s} n={len(g):4d}  entered day {g.days_into_episode.median():3.0f} of episode  "
              f"mean net={g.net.mean():+6.1%}  median={g.net.median():+6.1%}  "
              f"excess={ex.mean():+6.1%} (t={tstat:+5.1f})  years+={(yrs > 0).mean():.0%}")


if __name__ == "__main__":
    main()
