# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = [
#     "yfinance>=0.2.50",
#     "pandas>=2.2",
#     "numpy>=1.26",
# ]
# ///
"""Live screener for the Broken-Shit Formula (see FORMULA.md).

Downloads the last 2 years and reports, for today:
  BUY SIGNAL — full setup + RSI recross within the last 3 sessions
  FALLING    — setup armed but RSI < 30: knife still falling, wait
  ARMED      — setup fired in last 60d, still >=25% down, waiting for RSI dip/cross
  WATCH      — >=25% below 252d high but no fast-panic leg (grinders)

Run:  uv run --python 3.12 screen.py
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import yfinance as yf

RSI_PERIOD = 14
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

BUCKET_STATS = {
    "systemic-shock": "hist: 79% win, +50% mean over 180d (best)",
    "systemic-grind": "hist: 67% win, +19% mean",
    "idio-shock": "hist: 60% win, +23% mean (survivorship-inflated — half interest)",
    "idio-grind": "hist: 55% win, +15% mean (weakest — usually skip)",
}


def wilder_rsi(close: pd.Series, period: int = RSI_PERIOD) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    return (100.0 - 100.0 / (1.0 + rs)).fillna(50.0)


def get_universe() -> list[str]:
    """S&P 500 from Wikipedia; falls back to the hardcoded S&P 100 list."""
    from io import StringIO
    from urllib.request import Request, urlopen

    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    try:
        req = Request(url, headers={"User-Agent": "Mozilla/5.0 (research script)"})
        with urlopen(req, timeout=30) as resp:
            html = resp.read().decode("utf-8")
        syms = pd.read_html(StringIO(html))[0]["Symbol"].astype(str)
        return sorted(set(syms.str.replace(".", "-", regex=False)))
    except Exception as exc:  # network/layout change — degrade gracefully
        print(f"(S&P 500 list unavailable: {exc}; using built-in 100-name list)")
        return UNIVERSE


def main() -> None:
    universe = get_universe()
    frames: dict[str, pd.DataFrame] = {}
    for k in range(0, len(universe), 100):
        chunk = universe[k : k + 100]
        raw = yf.download(chunk, period="2y", auto_adjust=True,
                          group_by="ticker", threads=True, progress=False)
        for t in chunk:
            try:
                df = raw[t].dropna(subset=["Close"])
            except KeyError:
                continue
            if len(df) >= 300:
                frames[t] = df

    idx = yf.download(["SPY", "^VIX"], period="2y", auto_adjust=True,
                      group_by="ticker", threads=True, progress=False)
    spy = idx["SPY"].dropna(subset=["Close"])["Close"]
    vix_now = float(idx["^VIX"].dropna(subset=["Close"])["Close"].iloc[-1])
    spy_dd = float(spy.iloc[-1] / spy.rolling(252, min_periods=200).max().iloc[-1] - 1)
    systemic = spy_dd <= -0.12

    print(f"as of {spy.index[-1].date()}")
    print(f"market regime: SPY {spy_dd:+.1%} vs 252d high, VIX {vix_now:.1f} -> "
          f"{'SYSTEMIC PANIC (best knife weather)' if systemic else 'calm/idiosyncratic regime'}")

    rows: list[dict] = []
    for t, df in frames.items():
        close, open_ = df["Close"], df["Open"]
        roll_high = close.rolling(252, min_periods=200).max()
        dd = close / roll_high - 1.0
        ret15 = close.pct_change(15)
        rsi = wilder_rsi(close)

        setup = (dd <= -0.35) & (ret15 <= -0.15)
        armed = bool(setup.tail(60).any())
        ret1 = close.pct_change()
        gap = open_ / close.shift(1) - 1.0
        shock = bool(ret1.tail(60).min() <= -0.12 or gap.tail(60).min() <= -0.08)
        cross = (rsi >= 30) & (rsi.shift(1) < 30)
        cross_recent = bool(cross.tail(3).any())

        dd_now = float(dd.iloc[-1])
        rsi_now = float(rsi.iloc[-1])

        if armed:
            if rsi_now < 30:
                status = "FALLING"
            elif cross_recent and dd_now <= -0.25:
                status = "BUY SIGNAL"
            elif dd_now <= -0.25:
                status = "ARMED"
            else:
                continue  # recovered past the entry zone
        elif dd_now <= -0.25:
            status = "WATCH"
        else:
            continue

        bucket = f"{'systemic' if systemic else 'idio'}-{'shock' if shock else 'grind'}"
        rows.append({
            "status": status, "ticker": t, "dd": dd_now,
            "ret15": float(ret15.iloc[-1]), "rsi": rsi_now, "bucket": bucket,
        })

    if not rows:
        print("\nnothing broken enough today. The formula's answer is: no trade.")
        return

    out = pd.DataFrame(rows)
    order = ["BUY SIGNAL", "FALLING", "ARMED", "WATCH"]
    for status in order:
        grp = out[out.status == status].sort_values("dd")
        if grp.empty:
            continue
        print(f"\n--- {status} ({len(grp)}) ---")
        for _, r in grp.iterrows():
            print(f"  {r.ticker:6s} dd {r.dd:+.1%}  15d {r.ret15:+.1%}  "
                  f"RSI {r.rsi:5.1f}  {r.bucket}  [{BUCKET_STATS[r.bucket]}]")

    print("\nreminders: BUY SIGNAL = enter next open, wide trailing stop (20% off"
          "\npost-entry peak, floored at the crash low), hold months not weeks."
          "\nFALLING = do NOT buy yet. See FORMULA.md steps 3-5.")


if __name__ == "__main__":
    main()
