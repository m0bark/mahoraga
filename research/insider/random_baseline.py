# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = [
#     "pandas>=2.2",
#     "numpy>=1.26",
# ]
# ///
"""Control for the cluster-buy study: same-symbol RANDOM-DATE twins.

For every covered cluster-buy event, draw 3 random dates on the SAME symbol
(seeded, anywhere in its price history except the final horizon). If the
cluster excess merely reflects which SYMBOLS insiders trade (size/beta
tilts, survivorship), the random twins show it; if the excess is about
WHEN insiders cluster, the twins stay near zero.

Run:  uv run --python 3.12 random_baseline.py
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
PRICES_500 = HERE.parent / "panic_reversal" / "prices500.pkl"
HORIZONS = (21, 63, 126)


def main() -> None:
    buys = pd.read_csv(HERE / "cluster_buys.csv", parse_dates=["date"])
    frames = pd.read_pickle(PRICES_500)
    closes = pd.DataFrame({s: df["Close"] for s, df in frames.items()})
    ew = closes.mean(axis=1)
    idx = closes.index
    covered = buys[buys.symbol.isin(closes.columns)]
    rng = np.random.default_rng(42)

    for hz in HORIZONS:
        real, rand = [], []
        for _, e in covered.iterrows():
            col = closes[e.symbol]
            valid = col.dropna()
            if len(valid) < hz + 300:
                continue
            pos = idx.searchsorted(e.date) + 1
            if pos + hz < len(idx):
                px = col.iloc[pos: pos + hz + 1]
                if not px.isna().any() and px.iloc[0] > 0:
                    real.append((px.iloc[-1] / px.iloc[0] - 1.0)
                                - (ew.iloc[pos + hz] / ew.iloc[pos] - 1.0))
            lo = idx.searchsorted(valid.index[252])
            hi = idx.searchsorted(valid.index[-1]) - hz - 1
            if hi <= lo:
                continue
            for rpos in rng.integers(lo, hi, size=3):
                px = col.iloc[rpos: rpos + hz + 1]
                if not px.isna().any() and px.iloc[0] > 0:
                    rand.append((px.iloc[-1] / px.iloc[0] - 1.0)
                                - (ew.iloc[rpos + hz] / ew.iloc[rpos] - 1.0))
        r, q = pd.Series(real), pd.Series(rand)
        t_gap = (r.mean() - q.mean()) / np.sqrt(
            r.var(ddof=1) / len(r) + q.var(ddof=1) / len(q))
        print(f"{hz:3d}d: cluster excess {r.mean():+.2%} (n={len(r)})  vs  "
              f"same-symbol random {q.mean():+.2%} (n={len(q)})  "
              f"gap={r.mean() - q.mean():+.2%} (t={t_gap:+.2f})")


if __name__ == "__main__":
    main()
