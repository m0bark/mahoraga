# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = [
#     "pandas>=2.2",
#     "numpy>=1.26",
# ]
# ///
"""Bar check: monthly broken-decile tilt vs turnover-matched random deciles.

Candidate: each month-end, hold the ~10% of the universe deepest below its
252d high, equal weight. Baselines: (a) EW universe, (b) 20 random-decile
portfolios (same size, same monthly rebalance) — the dumb twin with
identical structure and turnover. The candidate passes only if it beats
the random twins decisively, not just the EW average.

Tier: SCOUTING.  Run:  uv run --python 3.12 tilt_vs_random.py
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
PRICES_500 = HERE.parent / "panic_reversal" / "prices500.pkl"

N_RANDOM = 20


def main() -> None:
    frames: dict[str, pd.DataFrame] = pd.read_pickle(PRICES_500)
    closes = pd.DataFrame({t: df["Close"] for t, df in frames.items()})
    dd = closes / closes.rolling(252, min_periods=252).max() - 1.0

    m = closes.resample("ME").last()
    dd_m = dd.resample("ME").last()
    fwd = m.shift(-1) / m - 1.0
    valid = dd_m.notna().sum(axis=1) >= 200
    q = dd_m.rank(axis=1, pct=True)  # lowest pct = deepest drawdown

    broken = fwd.where(q <= 0.10).mean(axis=1)[valid]
    ew = fwd.mean(axis=1)[valid]
    cand = (broken - ew).dropna()
    t_cand = cand.mean() / cand.std(ddof=1) * np.sqrt(len(cand))
    print(f"months: {len(cand)}")
    print(f"candidate (broken decile): excess vs EW {cand.mean() * 12:+.1%}/yr  (t={t_cand:+.2f})")
    print(f"  worst month {cand.min():+.1%}   months positive {(cand > 0).mean():.0%}")

    rng = np.random.default_rng(7)
    rand_means = []
    notna = dd_m.notna()
    for k in range(N_RANDOM):
        # random decile: same count of names each month, uniformly drawn
        picks = dd_m.copy() * np.nan
        r = pd.DataFrame(rng.random(dd_m.shape), index=dd_m.index, columns=dd_m.columns)
        r = r.where(notna)
        rq = r.rank(axis=1, pct=True)
        port = fwd.where(rq <= 0.10).mean(axis=1)[valid]
        ex = (port - ew).dropna()
        rand_means.append(ex.mean() * 12)
    rand_means = np.array(rand_means)
    beat = (cand.mean() * 12 > rand_means).mean()
    print(f"\nrandom-decile twins (n={N_RANDOM}): excess vs EW "
          f"mean {rand_means.mean():+.1%}/yr, min {rand_means.min():+.1%}, max {rand_means.max():+.1%}")
    print(f"candidate beats {beat:.0%} of random twins")
    print(f"\nBAR: excess>0 t>=2.5 [{'PASS' if t_cand >= 2.5 else 'FAIL'}], "
          f"n>=200 [{'PASS' if len(cand) >= 200 else 'FAIL'}], "
          f"beats random twins [{'PASS' if beat >= 0.95 else 'FAIL'}], "
          f"costs ~1-2%/yr at ~30-50%/mo one-way decile turnover vs "
          f"{cand.mean() * 12:.1%}/yr gross [{'PASS' if cand.mean() * 12 > 0.04 else 'FAIL'}]")


if __name__ == "__main__":
    main()
