# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = [
#     "pandas>=2.2",
#     "numpy>=1.26",
#     "scikit-learn>=1.4",
#     "lightgbm>=4.3",
#     "scipy>=1.11",
# ]
# ///
"""Cross-sectional ML ranker: predict which stocks beat the market next week.

Feeds a feature buffet (momentum/reversal/vol/drawdown/RSI/volume/regime) to
two models — LightGBM (trees) and an MLP (neural net) — under walk-forward
validation, against a dumb baseline (plain 1-week reversal rank).

Pre-registered bar: a model earns attention ONLY if its out-of-sample IC and
net decile excess beat the baseline. Data = current constituents (upper
bound); anything that survives here graduates to QuantConnect.

Run:  uv run --python 3.12 train.py
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor
from scipy.stats import spearmanr
from sklearn.neural_network import MLPRegressor
from sklearn.preprocessing import StandardScaler

HERE = Path(__file__).parent
PRICES_500 = HERE.parent / "panic_reversal" / "prices500.pkl"
PRICES_IDX = HERE.parent / "panic_reversal" / "prices.pkl"

COST_PER_WEEK = 0.002       # ~full weekly turnover of the sleeve, 10bps/side
FOLD_STARTS = [2012, 2015, 2018, 2021, 2024]   # 3y test windows, expanding train
EMBARGO_WEEKS = 2

STOCK_FEATURES = [
    "rev_1w", "rev_2w", "mom_4w", "mom_12w", "mom_26w", "mom_52w",
    "vol_12w", "dd_52w", "rsi", "vol_ratio",
]
MARKET_FEATURES = ["spy_1w", "spy_dd", "vix"]


def wilder_rsi(close: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    ag = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    al = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    return (100 - 100 / (1 + ag / al.replace(0.0, np.nan))).fillna(50.0)


def build_panel() -> pd.DataFrame:
    frames = pd.read_pickle(PRICES_500)
    closes_d = pd.DataFrame({t: df["Close"] for t, df in frames.items()})
    volumes_d = pd.DataFrame({t: df["Volume"] for t, df in frames.items()})
    idx = pd.read_pickle(PRICES_IDX)
    spy_d = idx["SPY"]["Close"]
    vix_d = idx["^VIX"]["Close"]

    p = closes_d.resample("W-FRI").last()
    v = volumes_d.resample("W-FRI").sum()
    r = p.pct_change()

    feats: dict[str, pd.DataFrame] = {
        "rev_1w": r,
        "rev_2w": p.pct_change(2),
        "mom_4w": p.pct_change(4),
        "mom_12w": p.pct_change(12),
        "mom_26w": p.pct_change(26),
        "mom_52w": p.shift(4) / p.shift(52) - 1.0,   # 12-1 style, skip last month
        "vol_12w": r.rolling(12).std(),
        "dd_52w": p / p.rolling(52).max() - 1.0,
        "rsi": wilder_rsi(closes_d).resample("W-FRI").last(),
        "vol_ratio": v / v.rolling(12).mean(),
    }
    # rank-normalize stock features per week: cross-sectional percentiles
    feats = {k: df.rank(axis=1, pct=True) for k, df in feats.items()}

    spy_w = spy_d.resample("W-FRI").last()
    market = pd.DataFrame({
        "spy_1w": spy_w.pct_change(),
        "spy_dd": spy_w / spy_w.rolling(52).max() - 1.0,
        "vix": vix_d.resample("W-FRI").last(),
    })

    fwd = r.shift(-1)
    target_raw = fwd.sub(fwd.mean(axis=1), axis=0)          # next-week excess
    target_rank = target_raw.rank(axis=1, pct=True)

    rows = []
    for k, df in feats.items():
        rows.append(df.stack().rename(k))
    long = pd.concat(
        rows + [target_rank.stack().rename("y"), target_raw.stack().rename("y_raw")],
        axis=1,
    )
    long.index.names = ["week", "ticker"]
    long = long.join(market, on="week").dropna()
    counts = long.groupby("week").size()
    long = long[long.index.get_level_values("week").isin(counts[counts >= 60].index)]
    return long.sort_index()


def evaluate(pred: pd.Series, panel: pd.DataFrame, name: str) -> dict:
    df = panel.loc[pred.index].assign(pred=pred)
    ics, weekly_excess = [], []
    for _, g in df.groupby("week"):
        if len(g) < 60:
            continue
        ics.append(spearmanr(g["pred"], g["y_raw"]).statistic)
        top = g.nlargest(max(5, len(g) // 10), "pred")
        weekly_excess.append(top["y_raw"].mean())
    ics = pd.Series(ics)
    ex = pd.Series(weekly_excess)
    net = ex - COST_PER_WEEK
    return {
        "model": name,
        "weeks": len(ex),
        "IC": ics.mean(),
        "IC_t": ics.mean() / ics.std() * np.sqrt(len(ics)),
        "gross_ann": ex.mean() * 52,
        "net_ann": net.mean() * 52,
        "net_t": net.mean() / net.std() * np.sqrt(len(net)),
        "worst_wk": ex.min(),
    }


def main() -> None:
    panel = build_panel()
    weeks = panel.index.get_level_values("week")
    print(f"panel: {len(panel):,} rows, {weeks.nunique()} weeks, "
          f"{panel.index.get_level_values('ticker').nunique()} tickers")

    xcols = STOCK_FEATURES + MARKET_FEATURES
    preds: dict[str, list[pd.Series]] = {"lightgbm": [], "neural_net": [], "baseline": []}

    for i, y0 in enumerate(FOLD_STARTS):
        y1 = FOLD_STARTS[i + 1] if i + 1 < len(FOLD_STARTS) else 2027
        test_mask = (weeks.year >= y0) & (weeks.year < y1)
        cutoff = weeks[test_mask].min() - pd.Timedelta(weeks=EMBARGO_WEEKS)
        train = panel[weeks < cutoff]
        test = panel[test_mask]
        print(f"fold {y0}-{y1 - 1}: train {len(train):,} rows -> test {len(test):,}")

        gbm = LGBMRegressor(
            n_estimators=300, learning_rate=0.05, num_leaves=31,
            min_child_samples=200, subsample=0.8, colsample_bytree=0.8,
            n_jobs=-1, verbose=-1,
        )
        gbm.fit(train[xcols], train["y"])
        preds["lightgbm"].append(pd.Series(gbm.predict(test[xcols]), index=test.index))

        mlp_train = train.tail(200_000)   # recency-capped for tractability
        scaler = StandardScaler().fit(mlp_train[xcols])
        mlp = MLPRegressor(
            hidden_layer_sizes=(24, 12), batch_size=512, max_iter=30,
            early_stopping=True, n_iter_no_change=3, random_state=0,
        )
        mlp.fit(scaler.transform(mlp_train[xcols]), mlp_train["y"])
        preds["neural_net"].append(
            pd.Series(mlp.predict(scaler.transform(test[xcols])), index=test.index)
        )
        preds["baseline"].append(1.0 - test["rev_1w"])   # buy the week's losers

    results = [evaluate(pd.concat(p), panel, name) for name, p in preds.items()]
    out = pd.DataFrame(results).set_index("model")
    fmt = out.copy()
    for c in ("IC", "gross_ann", "net_ann", "worst_wk"):
        fmt[c] = out[c].map(lambda x: f"{x:+.2%}" if c != "IC" else f"{x:+.3f}")
    for c in ("IC_t", "net_t"):
        fmt[c] = out[c].map(lambda x: f"{x:+.2f}")
    print("\n=== walk-forward, out-of-sample 2012-2026, top-decile long sleeve ===")
    print(fmt.to_string())
    print("\nbar: a model matters only if it beats `baseline` on IC AND net_ann.")
    print("caveats: current-constituent universe (upper bound); costs modeled")
    print(f"flat at {COST_PER_WEEK:.1%}/wk; survivors graduate to QuantConnect.")


if __name__ == "__main__":
    main()
