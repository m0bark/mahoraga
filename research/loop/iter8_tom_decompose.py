# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = [
#     "pandas>=2.2",
#     "numpy>=1.26",
# ]
# ///
"""Iter8: turn-of-month decomposition on SPY — survivorship-free lane.

The sweep found TOM (last 4 + first 3 trading days) at t=2.0. Decompose:
per-day-position means, half-sample stability, and the risk-efficiency
framing (TOM-only exposure vs buy-and-hold).

Run:  uv run --python 3.12 iter8_tom_decompose.py
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
PRICES_IDX = HERE.parent / "panic_reversal" / "prices.pkl"


def t_stat(x: pd.Series) -> float:
    return float(x.mean() / x.std(ddof=1) * np.sqrt(len(x)))


def main() -> None:
    spy = pd.read_pickle(PRICES_IDX)["SPY"]["Close"]
    r = spy.pct_change().dropna()
    month = r.index.to_period("M")
    day_num = r.groupby(month).cumcount() + 1
    total = r.groupby(month).transform("size")
    day_rev = total - day_num  # 0 = last trading day

    pos = pd.Series("mid", index=r.index)
    for k in (3, 2, 1, 0):
        pos[day_rev == k] = f"-{k + 1}"      # -1 = last day, -4 = 4th-last
    for k in (1, 2, 3):
        pos[day_num == k] = f"+{k}"          # +1 = first day of month

    print(f"ITER8 — TOM decomposition on SPY ({len(r)} days, "
          f"unconditional {r.mean() * 252:+.1%}/yr ann)\n")
    print("per-position mean daily return (annualized x252) and t:")
    order = ["-4", "-3", "-2", "-1", "+1", "+2", "+3", "mid"]
    for p in order:
        g = r[pos == p]
        print(f"  {p:3s}  n={len(g):4d}  ann={g.mean() * 252:+7.1%}  t={t_stat(g):+.2f}")

    in_win = pos != "mid"
    for label, mask in [("2005-2015", r.index.year <= 2015),
                        ("2016-2026", r.index.year >= 2016)]:
        a, b = r[in_win & mask], r[~in_win & mask]
        diff_t = (a.mean() - b.mean()) / np.sqrt(
            a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b))
        print(f"\n{label}: TOM {a.mean() * 252:+.1%}/yr vs mid "
              f"{b.mean() * 252:+.1%}/yr  (diff t={diff_t:+.2f})")

    tom_only = r.where(in_win, 0.0)
    for name, x in [("buy-and-hold", r), ("TOM-only (33% exposure)", tom_only)]:
        eq = (1 + x).cumprod()
        cagr = eq.iloc[-1] ** (252 / len(x)) - 1
        dd = (eq / eq.cummax() - 1).min()
        vol = x.std() * np.sqrt(252)
        print(f"\n{name}: CAGR {cagr:+.1%}  vol {vol:.1%}  maxDD {dd:+.1%}  "
              f"CAGR/vol {cagr / vol:+.2f}")


if __name__ == "__main__":
    main()
