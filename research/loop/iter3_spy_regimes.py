# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = [
#     "pandas>=2.2",
#     "numpy>=1.26",
# ]
# ///
"""Iter3: SPY/VIX regime map + fear-peaked dip entries — SURVIVORSHIP-FREE.

SPY is a real, investable series: no constituent bias. Two parts:

A) Regime map: weekly forward SPY return conditional on VIX level
   (fixed ex-ante buckets <17 / 17-25 / >25) x SPY drawdown state
   (0..-5% / -5..-15% / <-15%). n ~ 1000 weeks.

B) Event study: "fear peaked" dip entries — SPY >=15% below its 252d high
   AND VIX >= 20% below its own 10-day max (panic subsiding). Forward
   60/120d vs unconditional non-overlapping baselines.

Run:  uv run --python 3.12 iter3_spy_regimes.py
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
PRICES_IDX = HERE.parent / "panic_reversal" / "prices.pkl"

VIX_LOW, VIX_HIGH = 17.0, 25.0


def welch(a: pd.Series, b: pd.Series) -> float:
    a, b = a.dropna(), b.dropna()
    return float((a.mean() - b.mean())
                 / np.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b)))


def main() -> None:
    idx = pd.read_pickle(PRICES_IDX)
    spy = idx["SPY"]["Close"]
    vix = idx["^VIX"]["Close"]

    # ---- A) weekly regime map ----
    w = spy.resample("W-FRI").last().dropna()
    vw = vix.resample("W-FRI").last().reindex(w.index).ffill()
    dd = w / w.rolling(52, min_periods=52).max() - 1.0
    fwd = w.pct_change().shift(-1)

    df = pd.DataFrame({"fwd": fwd, "dd": dd, "vix": vw}).dropna()
    df["vix_b"] = pd.cut(df.vix, [0, VIX_LOW, VIX_HIGH, 999],
                         labels=["vix<17", "vix17-25", "vix>25"])
    df["dd_b"] = pd.cut(df.dd, [-1, -0.15, -0.05, 0.01],
                        labels=["dd<-15%", "dd-5..-15%", "dd0..-5%"])
    uncond = df.fwd.mean()
    print(f"ITER3-A — weekly forward SPY return by regime "
          f"({len(df)} weeks, unconditional {uncond * 52:+.1%}/yr)\n")
    grid = df.groupby(["dd_b", "vix_b"], observed=True).agg(
        n=("fwd", "size"), ann=("fwd", lambda s: s.mean() * 52),
        t_vs_uncond=("fwd", lambda s: welch(s, df.fwd)),
    )
    print(grid.to_string(float_format=lambda x: f"{x:+.2f}" if abs(x) < 30 else f"{x:.0f}"))

    # ---- B) fear-peaked dip entries (daily, non-overlapping) ----
    dd_d = spy / spy.rolling(252, min_periods=252).max() - 1.0
    vix_a = vix.reindex(spy.index).ffill()
    fear_peaked = vix_a <= 0.80 * vix_a.rolling(10).max()
    cond = (dd_d <= -0.15) & fear_peaked

    print("\nITER3-B — SPY >=15% off high AND VIX >=20% below its 10d max")
    for hz in (60, 120):
        events, i, n = [], 252, len(spy)
        arr = cond.to_numpy()
        while i < n - hz:
            if arr[i]:
                events.append(float(spy.iloc[i + hz] / spy.iloc[i] - 1.0))
                i += hz
            else:
                i += 1
        ev = pd.Series(events)
        base = spy.iloc[::hz].pct_change().dropna()
        print(f"  {hz:3d}d: events={len(ev):3d}  mean={ev.mean():+.1%}  "
              f"median={ev.median():+.1%}  win={float((ev > 0).mean()):.0%}  "
              f"worst={ev.min():+.1%}  vs uncond {base.mean():+.1%}  "
              f"t={welch(ev, base):+.2f}")


if __name__ == "__main__":
    main()
