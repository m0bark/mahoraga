# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = [
#     "pandas>=2.2",
#     "numpy>=1.26",
#     "scikit-learn>=1.4",
#     "scipy>=1.11",
# ]
# ///
"""Neural net pattern-finder with a RANDOM HOLDOUT YEAR (user spec).

Feed a wide feature buffet to an MLP; hold out one randomly chosen year
(never seen in training, 4-week embargo on both sides); test cold on it.
Baseline = plain 1-week-reversal rank, for reference.

Run:  uv run --python 3.12 nn_holdout.py
"""

from __future__ import annotations

import random
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.neural_network import MLPRegressor
from sklearn.preprocessing import StandardScaler

HERE = Path(__file__).parent
PRICES_500 = HERE.parent / "panic_reversal" / "prices500.pkl"
PRICES_IDX = HERE.parent / "panic_reversal" / "prices.pkl"

COST_PER_WEEK = 0.002
EMBARGO_WEEKS = 4
HOLDOUT_SEED = 2026          # deterministic "random" year, printed below


def wilder_rsi(close: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    ag = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    al = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    return (100 - 100 / (1 + ag / al.replace(0.0, np.nan))).fillna(50.0)


def build_panel() -> tuple[pd.DataFrame, list[str]]:
    frames = pd.read_pickle(PRICES_500)
    closes_d = pd.DataFrame({t: df["Close"] for t, df in frames.items()})
    opens_d = pd.DataFrame({t: df["Open"] for t, df in frames.items()})
    volumes_d = pd.DataFrame({t: df["Volume"] for t, df in frames.items()})
    idx = pd.read_pickle(PRICES_IDX)
    spy_d = idx["SPY"]["Close"]
    vix_d = idx["^VIX"]["Close"]

    p = closes_d.resample("W-FRI").last()
    v = volumes_d.resample("W-FRI").sum()
    r = p.pct_change()
    ret1d = closes_d.pct_change()
    gap1d = opens_d / closes_d.shift(1) - 1.0
    spy_w = spy_d.resample("W-FRI").last()
    spy_r = spy_w.pct_change()

    stock: dict[str, pd.DataFrame] = {
        "rev_1w": r,
        "rev_2w": p.pct_change(2),
        "rev_3w": p.pct_change(3),
        "mom_4w": p.pct_change(4),
        "mom_8w": p.pct_change(8),
        "mom_12w": p.pct_change(12),
        "mom_26w": p.pct_change(26),
        "mom_52w": p.shift(4) / p.shift(52) - 1.0,
        "vol_4w": r.rolling(4).std(),
        "vol_12w": r.rolling(12).std(),
        "vol_26w": r.rolling(26).std(),
        "skew_12w": r.rolling(12).skew(),
        "dd_52w": p / p.rolling(52).max() - 1.0,
        "up_from_low": p / p.rolling(52).min() - 1.0,
        "rsi": wilder_rsi(closes_d).resample("W-FRI").last(),
        "vol_ratio_1_12": v / v.rolling(12).mean(),
        "vol_ratio_4_26": v.rolling(4).mean() / v.rolling(26).mean(),
        "size": (closes_d * volumes_d).rolling(20).mean().resample("W-FRI").last(),
        "worst_day_8w": ret1d.rolling(40).min().resample("W-FRI").last(),
        "worst_gap_8w": gap1d.rolling(40).min().resample("W-FRI").last(),
        "corr_spy_26w": r.rolling(26).corr(spy_r),
    }
    stock = {k: df.rank(axis=1, pct=True) for k, df in stock.items()}

    market = pd.DataFrame({
        "spy_1w": spy_r,
        "spy_4w": spy_w.pct_change(4),
        "spy_dd": spy_w / spy_w.rolling(52).max() - 1.0,
        "vix": vix_d.resample("W-FRI").last(),
        "vix_chg_4w": vix_d.resample("W-FRI").last().pct_change(4),
    })

    fwd = r.shift(-1)
    y_raw = fwd.sub(fwd.mean(axis=1), axis=0)
    y = y_raw.rank(axis=1, pct=True)

    cols = [df.stack().rename(k) for k, df in stock.items()]
    long = pd.concat(cols + [y.stack().rename("y"), y_raw.stack().rename("y_raw")], axis=1)
    long.index.names = ["week", "ticker"]
    long = long.join(market, on="week")
    long["month"] = long.index.get_level_values("week").month
    long = long.dropna()
    counts = long.groupby("week").size()
    long = long[long.index.get_level_values("week").isin(counts[counts >= 60].index)]
    xcols = list(stock) + list(market.columns) + ["month"]
    return long.sort_index(), xcols


def evaluate(df: pd.DataFrame, pred_col: str, name: str) -> None:
    ics, weekly_excess = [], []
    for _, g in df.groupby("week"):
        ics.append(spearmanr(g[pred_col], g["y_raw"]).statistic)
        top = g.nlargest(max(5, len(g) // 10), pred_col)
        weekly_excess.append(top["y_raw"].mean())
    ics, ex = pd.Series(ics), pd.Series(weekly_excess)
    net = ex - COST_PER_WEEK
    print(f"\n{name}  ({len(ex)} weeks)")
    print(f"  IC {ics.mean():+.3f} (t={ics.mean() / ics.std() * np.sqrt(len(ics)):+.2f})   "
          f"decile gross {ex.mean() * 52:+.1%}/yr   net {net.mean() * 52:+.1%}/yr   "
          f"win weeks {(ex > 0).mean():.0%}   worst week {ex.min():+.1%}")


def main() -> None:
    panel, xcols = build_panel()
    weeks = panel.index.get_level_values("week")
    years = sorted(set(weeks.year))[1:-1]          # full years only
    holdout = random.Random(HOLDOUT_SEED).choice(years)
    print(f"panel: {len(panel):,} rows, {weeks.nunique()} weeks, {len(xcols)} features")
    print(f"HOLDOUT YEAR (random, seed={HOLDOUT_SEED}): {holdout}")

    test_mask = weeks.year == holdout
    t0, t1 = weeks[test_mask].min(), weeks[test_mask].max()
    embargo = (weeks >= t0 - pd.Timedelta(weeks=EMBARGO_WEEKS)) & (
        weeks <= t1 + pd.Timedelta(weeks=EMBARGO_WEEKS)
    )
    train = panel[~embargo]
    test = panel[test_mask].copy()
    print(f"train {len(train):,} rows (embargo ±{EMBARGO_WEEKS}w) -> test {len(test):,} rows")
    print("note: training includes years AFTER the holdout (your spec — a "
          "time-asymmetric test; walk-forward is the stricter companion check)")

    scaler = StandardScaler().fit(train[xcols])
    nn = MLPRegressor(
        hidden_layer_sizes=(128, 64, 32), batch_size=1024,
        learning_rate_init=1e-3, max_iter=300,
        early_stopping=True, validation_fraction=0.1, n_iter_no_change=10,
        random_state=0,
    )
    nn.fit(scaler.transform(train[xcols]), train["y"])
    print(f"NN trained: {nn.n_iter_} epochs, val score {nn.best_validation_score_:+.4f}")

    test["nn"] = nn.predict(scaler.transform(test[xcols]))
    test["base"] = 1.0 - test["rev_1w"]

    print(f"\n=== cold test on {holdout} (never seen in training) ===")
    evaluate(test, "nn", "neural_net (27 features)")
    evaluate(test, "base", "baseline (plain 1w reversal)")


if __name__ == "__main__":
    main()
