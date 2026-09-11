# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = [
#     "yfinance>=0.2.50",
#     "pandas>=2.2",
#     "numpy>=1.26",
# ]
# ///
"""Panic-reversal backtest v2: knife taxonomy + exit-policy comparison.

See HYPOTHESIS.md for rules, registered predictions, and known biases.

Run:  uv run --python 3.12 backtest.py
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

START = "2005-01-01"
COST_PER_SIDE = 0.0010  # 10 bps

# --- v1 entry rules (unchanged) ---
DRAWDOWN_SETUP = -0.35
FAST_RETURN = -0.15
ARMED_DAYS = 60
DRAWDOWN_AT_ENTRY = -0.25
RSI_PERIOD = 14
RSI_TRIGGER = 30.0
RECOVERY_FRACTION = 0.90
TIME_STOP_DAYS = 180
COOLDOWN_DAYS = 20

# --- v2 taxonomy thresholds (stated, not tuned) ---
SHOCK_DAY_RET = -0.12   # one-day close-to-close drop => informational shock
SHOCK_GAP = -0.08       # overnight gap down => informational shock
SYSTEMIC_DD = -0.12     # SPY >=12% off its 252d high => systemic panic
VIX_PANIC = 30.0
TRAIL_FRACTION = 0.80   # trailing policy: stop 20% below post-entry peak

POLICIES = ("resistance", "trailing", "hold180")

CACHE = Path(__file__).parent / "prices.pkl"

# Approximate current S&P 100. KNOWN SURVIVORSHIP BIAS — see HYPOTHESIS.md.
UNIVERSE = [
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "AVGO", "BRK-B",
    "JPM", "V", "UNH", "XOM", "LLY", "MA", "HD", "PG", "COST", "JNJ", "ORCL",
    "ABBV", "BAC", "CRM", "CVX", "MRK", "KO", "AMD", "PEP", "NFLX", "ADBE",
    "WMT", "DIS", "TMO", "CSCO", "ACN", "QCOM", "INTU", "IBM", "TXN", "AMGN",
    "CMCSA", "GE", "ISRG", "NOW", "CAT", "PFE", "SPGI", "UBER", "GS", "AXP",
    "MS", "RTX", "HON", "UNP", "BLK", "T", "BKNG", "LOW", "ELV", "VZ", "COP",
    "SCHW", "LMT", "SBUX", "PLTR", "C", "BA", "MDT", "DE", "ADP", "GILD",
    "MMC", "ETN", "AMT", "PGR", "SYK", "BMY", "MU", "INTC", "TJX", "CB", "SO",
    "NEE", "DHR", "LIN", "ABT", "MCD", "NKE", "PM", "UPS", "MO", "WFC", "EMR",
    "FDX", "GM", "TGT", "CVS", "DUK", "COF", "MDLZ", "PYPL",
]


def wilder_rsi(close: pd.Series, period: int = RSI_PERIOD) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    return (100.0 - 100.0 / (1.0 + rs)).fillna(50.0)


def download_universe(tickers: list[str]) -> dict[str, pd.DataFrame]:
    if CACHE.exists():
        return pd.read_pickle(CACHE)
    raw = yf.download(
        tickers, start=START, auto_adjust=True, group_by="ticker",
        threads=True, progress=False,
    )
    frames: dict[str, pd.DataFrame] = {}
    for t in tickers:
        try:
            df = raw[t].dropna(subset=["Close"])
        except KeyError:
            continue
        if len(df) < 300:
            continue
        frames[t] = df
    pd.to_pickle(frames, CACHE)
    return frames


def exit_trade(
    df: pd.DataFrame, entry_idx: int, pre_high: float, crash_low: float, policy: str,
) -> tuple[int, float, str]:
    """Return (exit_exec_idx, exit_px, reason). Decision on close, fill next open."""
    close, open_ = df["Close"], df["Open"]
    n = len(df)
    target = RECOVERY_FRACTION * pre_high
    peak = float(close.iloc[entry_idx])

    exit_idx: int | None = None
    reason = "eod_data"
    for j in range(entry_idx + 1, n):
        c = float(close.iloc[j])
        if policy == "resistance":
            if c >= target:
                exit_idx, reason = j, "recovery"
                break
            if c < crash_low:
                exit_idx, reason = j, "thesis_break"
                break
            if j - entry_idx >= TIME_STOP_DAYS:
                exit_idx, reason = j, "time_stop"
                break
        elif policy == "trailing":
            peak = max(peak, c)
            if c < max(crash_low, TRAIL_FRACTION * peak):
                exit_idx, reason = j, "trail_stop"
                break
            if j - entry_idx >= TIME_STOP_DAYS:
                exit_idx, reason = j, "time_stop"
                break
        else:  # hold180
            if j - entry_idx >= TIME_STOP_DAYS:
                exit_idx, reason = j, "hold180"
                break

    if exit_idx is None:
        return n - 1, float(close.iloc[n - 1]), reason
    if exit_idx + 1 < n:
        return exit_idx + 1, float(open_.iloc[exit_idx + 1]), reason
    return exit_idx, float(close.iloc[exit_idx]), reason


def net_return(entry_px: float, exit_px: float) -> float:
    return (exit_px * (1 - COST_PER_SIDE)) / (entry_px * (1 + COST_PER_SIDE)) - 1.0


def find_trades(
    ticker: str, df: pd.DataFrame,
    spy_close: pd.Series, spy_dd: pd.Series, vix_close: pd.Series,
) -> list[dict]:
    close, low, open_ = df["Close"], df["Low"], df["Open"]
    roll_high = close.rolling(252, min_periods=252).max()
    drawdown = close / roll_high - 1.0
    ret_fast = close.pct_change(15)
    rsi = wilder_rsi(close)

    setup = (drawdown <= DRAWDOWN_SETUP) & (ret_fast <= FAST_RETURN)
    armed = setup.rolling(ARMED_DAYS, min_periods=1).max().astype(bool)
    rsi_cross_up = (rsi >= RSI_TRIGGER) & (rsi.shift(1) < RSI_TRIGGER)
    entry_signal = armed & rsi_cross_up & (drawdown <= DRAWDOWN_AT_ENTRY)

    crash_low = low.rolling(ARMED_DAYS, min_periods=1).min()
    ret1 = close.pct_change()
    gap = open_ / close.shift(1) - 1.0
    worst_day = ret1.rolling(ARMED_DAYS, min_periods=1).min()
    worst_gap = gap.rolling(ARMED_DAYS, min_periods=1).min()

    trades: list[dict] = []
    i, n = 252, len(df)
    while i < n - 1:
        if not entry_signal.iloc[i]:
            i += 1
            continue

        entry_idx = i + 1
        entry_px = float(open_.iloc[entry_idx])
        d_in = df.index[entry_idx]
        pre_high = float(roll_high.iloc[i])
        stop = float(crash_low.iloc[i])

        is_shock = bool(
            worst_day.iloc[i] <= SHOCK_DAY_RET or worst_gap.iloc[i] <= SHOCK_GAP
        )
        spy_dd_now = float(spy_dd.asof(d_in))
        is_systemic = spy_dd_now <= SYSTEMIC_DD
        vix_now = float(vix_close.asof(d_in))

        row: dict = {
            "ticker": ticker, "entry_date": d_in, "entry_px": entry_px,
            "shock": is_shock, "systemic": is_systemic,
            "spy_dd": spy_dd_now, "vix": vix_now,
        }
        primary_exec = entry_idx
        for policy in POLICIES:
            exec_idx, exit_px, reason = exit_trade(df, entry_idx, pre_high, stop, policy)
            d_out = df.index[exec_idx]
            nr = net_return(entry_px, exit_px)
            spy_ret = float(spy_close.asof(d_out)) / float(spy_close.asof(d_in)) - 1.0
            row[f"{policy}_reason"] = reason
            row[f"{policy}_days"] = exec_idx - entry_idx
            row[f"{policy}_net"] = nr
            row[f"{policy}_excess"] = nr - spy_ret
            if policy == "resistance":
                primary_exec = exec_idx  # v1 policy defines cooldown / no-overlap
        trades.append(row)
        i = primary_exec + COOLDOWN_DAYS
    return trades


def stats_block(tdf: pd.DataFrame, policy: str) -> dict:
    net, exc = tdf[f"{policy}_net"], tdf[f"{policy}_excess"]
    return {
        "n": len(tdf),
        "win": (net > 0).mean(),
        "mean_net": net.mean(),
        "median_net": net.median(),
        "mean_excess": exc.mean(),
        "median_excess": exc.median(),
        "avg_days": tdf[f"{policy}_days"].mean(),
    }


def fmt_table(rows: dict[str, dict]) -> str:
    df = pd.DataFrame(rows).T
    df["n"] = df["n"].astype(int)
    for c in ("win", "mean_net", "median_net", "mean_excess", "median_excess"):
        df[c] = df[c].map(lambda x: f"{x:+.1%}")
    df["avg_days"] = df["avg_days"].map(lambda x: f"{x:.0f}")
    return df.to_string()


def main() -> None:
    print(f"loading {len(UNIVERSE)} tickers + SPY + VIX since {START} ...")
    frames = download_universe(UNIVERSE + ["SPY", "^VIX"])
    spy = frames.pop("SPY")["Close"]
    vix = frames.pop("^VIX")["Close"]
    spy_dd = spy / spy.rolling(252, min_periods=252).max() - 1.0
    print(f"got usable data for {len(frames)} tickers")

    rows: list[dict] = []
    for ticker, df in frames.items():
        rows.extend(find_trades(ticker, df, spy, spy_dd, vix))
    tdf = pd.DataFrame(rows).sort_values("entry_date").reset_index(drop=True)

    out = Path(__file__).parent / "trades.csv"
    tdf.to_csv(out, index=False)
    print(f"{len(tdf)} trades -> {out}\n")

    print("=" * 66)
    print("PANIC REVERSAL v2 — net of 10 bps/side, survivorship-biased universe")
    print("=" * 66)

    print("\n--- exit policy comparison (identical entries) ---")
    print(fmt_table({p: stats_block(tdf, p) for p in POLICIES}))

    bucket = np.select(
        [
            tdf.systemic & ~tdf.shock, tdf.systemic & tdf.shock,
            ~tdf.systemic & ~tdf.shock, ~tdf.systemic & tdf.shock,
        ],
        ["systemic-grind", "systemic-shock", "idio-grind", "idio-shock"],
        default="other",
    )
    tdf["bucket"] = bucket
    order = ["systemic-grind", "systemic-shock", "idio-grind", "idio-shock"]

    for policy in ("hold180", "resistance"):
        label = "pure knife quality" if policy == "hold180" else "deployed v1 rules"
        print(f"\n--- knife taxonomy under `{policy}` ({label}) ---")
        print(fmt_table({
            b: stats_block(tdf[tdf.bucket == b], policy)
            for b in order if (tdf.bucket == b).any()
        }))

    print(f"\n--- VIX at entry (>= {VIX_PANIC:.0f} vs below), `resistance` policy ---")
    print(fmt_table({
        f"VIX >= {VIX_PANIC:.0f}": stats_block(tdf[tdf.vix >= VIX_PANIC], "resistance"),
        f"VIX <  {VIX_PANIC:.0f}": stats_block(tdf[tdf.vix < VIX_PANIC], "resistance"),
    }))


if __name__ == "__main__":
    main()
