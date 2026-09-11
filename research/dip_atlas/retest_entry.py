# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = [
#     "pandas>=2.2",
#     "numpy>=1.26",
# ]
# ///
"""Iter1: retest-confirmation entry vs RSI-recross vs random timing, in-dip.

Point-in-time rules (no hindsight trough knowledge):
  Episode: drawdown <= -20% vs 252d high, until recovery to -5%.
  L = running min LOW within the episode so far, t_L its day.
  RETEST signal (first per episode), on day t:
    - t - t_L >= 10                (the low has held unbroken 10+ days)
    - max close since t_L >= 1.08L (a real bounce happened, not a flat drift)
    - low_t <= 1.05L and close_t >= 1.03L  (came back to the zone and held)
  S1 signal: first RSI(14) recross above 30 within the episode.
  RANDOM baseline: one uniform day per episode (seeded), >=5d after start.

All three: enter next open, stop on close < 0.95 x (episode min low at
signal), exit next open; else time-exit at 120 trading days. Net of 10bps
per side; excess vs SPY over the same window.

Tier: SCOUTING (survivorship-biased cache). Run:
  uv run --python 3.12 retest_entry.py
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
STOP_FRAC = 0.95
HOLD_DAYS = 10
BOUNCE = 1.08
RETEST_LOW = 1.05
RETEST_HOLD = 1.03


def wilder_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    ag = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    al = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    return (100 - 100 / (1 + ag / al.replace(0.0, np.nan))).fillna(50.0)


def episodes(dd: np.ndarray, n: int) -> list[tuple[int, int]]:
    out, i = [], 252
    while i < n:
        if dd[i] <= -0.20 and dd[i - 1] > -0.20:
            end = n - 1
            for j in range(i, n):
                if dd[j] >= -0.05:
                    end = j
                    break
            out.append((i, end))
            i = end + 20
        else:
            i += 1
    return out


def evaluate(i_sig: int, L: float, closes: np.ndarray, opens: np.ndarray,
             idx, spy: pd.Series, n: int, stop_mode: str = "low") -> dict | None:
    e0 = i_sig + 1
    if e0 >= n:
        return None
    entry = float(opens[e0])
    # "low": stop 5% under the episode low (v1 geometry — differs per entry
    # distance from the low). "entry": stop 15% under the entry price for
    # everyone — isolates timing skill from stop placement.
    stop_level = STOP_FRAC * L if stop_mode == "low" else 0.85 * entry
    exit_exec, stopped = None, False
    for j in range(e0 + 1, min(e0 + HORIZON, n - 1) + 1):
        if closes[j] < stop_level:
            exit_exec, stopped = min(j + 1, n - 1), True
            break
    if exit_exec is None:
        exit_exec = min(e0 + HORIZON, n - 1)
    exit_px = float(opens[exit_exec]) if stopped else float(closes[exit_exec])
    net = (exit_px * (1 - COST_PER_SIDE)) / (entry * (1 + COST_PER_SIDE)) - 1.0
    d0, d1 = idx[e0], idx[exit_exec]
    spy_ret = float(spy.asof(d1)) / float(spy.asof(d0)) - 1.0
    return {"date": d0, "net": net, "excess": net - spy_ret, "stopped": stopped}


def main() -> None:
    frames: dict[str, pd.DataFrame] = pd.read_pickle(PRICES_500)
    spy = pd.read_pickle(PRICES_IDX)["SPY"]["Close"]
    rows: dict[str, list[dict]] = {
        f"{s}|{m}": [] for s in ("retest", "rsi_recross", "random")
        for m in ("low", "entry")
    }

    for t, df in frames.items():
        n = len(df)
        if n < 400:
            continue
        closes = df["Close"].to_numpy()
        lows = df["Low"].to_numpy()
        opens = df["Open"].to_numpy()
        roll_high = df["Close"].rolling(252, min_periods=252).max().to_numpy()
        dd = closes / roll_high - 1.0
        rsi = wilder_rsi(df["Close"]).to_numpy()
        idx = df.index
        rng = np.random.default_rng(abs(hash(t)) % (2**32))

        for (a, b) in episodes(dd, n):
            L, t_L, max_c = float(lows[a]), a, float(closes[a])
            got_retest = got_s1 = False
            was_below = False
            for j in range(a, b + 1):
                if lows[j] < L:
                    L, t_L, max_c = float(lows[j]), j, float(closes[j])
                else:
                    max_c = max(max_c, float(closes[j]))
                if (not got_retest and j - t_L >= HOLD_DAYS
                        and max_c >= BOUNCE * L
                        and lows[j] <= RETEST_LOW * L
                        and closes[j] >= RETEST_HOLD * L):
                    for m in ("low", "entry"):
                        r = evaluate(j, L, closes, opens, idx, spy, n, m)
                        if r:
                            rows[f"retest|{m}"].append(r)
                    got_retest = True
                if rsi[j] < 30:
                    was_below = True
                elif was_below and rsi[j] >= 30 and not got_s1:
                    Lj = float(np.min(lows[a:j + 1]))
                    for m in ("low", "entry"):
                        r = evaluate(j, Lj, closes, opens, idx, spy, n, m)
                        if r:
                            rows[f"rsi_recross|{m}"].append(r)
                    got_s1 = True
            if b - a > 6:
                jr = int(rng.integers(a + 5, b + 1))
                Lr = float(np.min(lows[a:jr + 1]))
                for m in ("low", "entry"):
                    r = evaluate(jr, Lr, closes, opens, idx, spy, n, m)
                    if r:
                        rows[f"random|{m}"].append(r)

    print("ITER1 — retest-confirmation entry vs RSI-recross vs random, "
          "120d horizon, stop at 95% of the signal-day low, net of 10bps/side")
    print("tier: SCOUTING (survivorship-biased). t-stats overstated by "
          "crisis clustering.\n")
    for name, rs in rows.items():
        d = pd.DataFrame(rs)
        ex = d.excess
        t = ex.mean() / ex.std(ddof=1) * np.sqrt(len(ex))
        by_year = d.assign(y=d.date.dt.year).groupby("y").excess.mean()
        pos_years = (by_year > 0).mean()
        print(f"{name:12s} n={len(d):4d}  stopped={d.stopped.mean():.0%}  "
              f"mean net={d.net.mean():+.1%}  median={d.net.median():+.1%}  "
              f"mean excess={ex.mean():+.1%} (t={t:+.2f})  "
              f"years positive={pos_years:.0%}")
    pd.concat(
        [pd.DataFrame(v).assign(strategy=k) for k, v in rows.items()]
    ).to_csv(HERE / "retest_entries.csv", index=False)
    print(f"\nevents -> {HERE / 'retest_entries.csv'}")


if __name__ == "__main__":
    main()
