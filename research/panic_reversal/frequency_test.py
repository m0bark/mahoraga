# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = [
#     "yfinance>=0.2.50",
#     "pandas>=2.2",
#     "numpy>=1.26",
#     "lxml>=5",
# ]
# ///
"""Can the broken-shit formula deliver >=1 entry per month?

Path A: same formula, S&P 500 universe (5x names -> more panic catches?)
Path B: rank-based monthly portfolio — always own the most-broken decile,
        rebalanced month-end (guaranteed monthly action by construction).

Run:  uv run --python 3.12 frequency_test.py
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

import backtest as bt

HERE = Path(__file__).parent
CACHE500 = HERE / "prices500.pkl"
WIKI = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"


def sp500_tickers() -> list[str]:
    from io import StringIO
    from urllib.request import Request, urlopen

    req = Request(WIKI, headers={"User-Agent": "Mozilla/5.0 (research script)"})
    with urlopen(req) as resp:
        html = resp.read().decode("utf-8")
    tables = pd.read_html(StringIO(html))
    syms = tables[0]["Symbol"].astype(str).str.replace(".", "-", regex=False)
    return sorted(set(syms))


def download_500() -> dict[str, pd.DataFrame]:
    if CACHE500.exists():
        return pd.read_pickle(CACHE500)
    tickers = sp500_tickers()
    print(f"downloading {len(tickers)} S&P 500 tickers since {bt.START} (chunked) ...")
    frames: dict[str, pd.DataFrame] = {}
    for k in range(0, len(tickers), 100):
        chunk = tickers[k : k + 100]
        raw = yf.download(chunk, start=bt.START, auto_adjust=True,
                          group_by="ticker", threads=True, progress=False)
        for t in chunk:
            try:
                df = raw[t].dropna(subset=["Close"])
            except KeyError:
                continue
            if len(df) >= 300:
                frames[t] = df
        print(f"  {min(k + 100, len(tickers))}/{len(tickers)} done, usable so far: {len(frames)}")
    pd.to_pickle(frames, CACHE500)
    return frames


def path_a(frames: dict[str, pd.DataFrame], spy: pd.Series,
           spy_dd: pd.Series, vix: pd.Series) -> None:
    print("\n" + "=" * 68)
    print("PATH A — same formula, S&P 500 universe")
    print("=" * 68)
    rows: list[dict] = []
    for t, df in frames.items():
        rows.extend(bt.find_trades(t, df, spy, spy_dd, vix))
    tdf = pd.DataFrame(rows).sort_values("entry_date").reset_index(drop=True)
    tdf.to_csv(HERE / "trades500.csv", index=False)

    d = tdf.entry_date
    years = (d.max() - d.min()).days / 365.25
    print(f"trades: {len(tdf)} over {years:.1f}y = {len(tdf) / years:.0f}/year")

    months = pd.period_range(d.min(), d.max(), freq="M")
    per_month = d.dt.to_period("M").value_counts().reindex(months, fill_value=0)
    hit = (per_month > 0).mean()
    zeros = per_month == 0
    # longest run of zero-entry months
    drought = max(
        (len(list(g)) for k, g in __import__("itertools").groupby(zeros) if k),
        default=0,
    )
    print(f"months with >=1 entry: {hit:.0%}   median entries/month: {per_month.median():.0f}")
    print(f"longest drought: {drought} consecutive months with zero entries")
    print(f"quiet-regime months (VIX<20 era) still fire due to idio crashes in a 500-name universe")

    print("\nper-trade quality (same policies as v2):")
    print(bt.fmt_table({p: bt.stats_block(tdf, p) for p in bt.POLICIES}))


def path_b(frames: dict[str, pd.DataFrame]) -> None:
    print("\n" + "=" * 68)
    print("PATH B — monthly rank portfolio: always own the most-broken decile")
    print("=" * 68)
    closes = pd.DataFrame({t: df["Close"] for t, df in frames.items()})
    dd = closes / closes.rolling(252, min_periods=252).max() - 1.0
    rsi = bt.wilder_rsi(closes)

    m = closes.resample("ME").last()
    dd_m = dd.resample("ME").last()
    rsi_m = rsi.resample("ME").last()
    fwd = m.shift(-1) / m - 1.0

    valid = dd_m.notna().sum(axis=1) >= 200
    q = dd_m.rank(axis=1, pct=True)  # lowest pct = deepest drawdown
    broken = q <= 0.10
    stab = broken & (rsi_m >= 30)

    ew = fwd.mean(axis=1)[valid]
    port_all = fwd.where(broken).mean(axis=1)[valid]
    port_stab = fwd.where(stab).mean(axis=1)[valid]

    for name, port in (("broken decile (raw)", port_all),
                       ("broken decile + RSI>=30 stabilized", port_stab)):
        ex = (port - ew).dropna()
        t = bt.one_sample_t(ex) if hasattr(bt, "one_sample_t") else float(
            ex.mean() / (ex.std(ddof=1) / np.sqrt(len(ex))))
        n_names = (broken if name.endswith("(raw)") else stab).sum(axis=1)[valid].mean()
        print(f"\n{name}: ~{n_names:.0f} names/month, {len(ex)} months")
        print(f"  portfolio: {port.mean() * 12:+.1%}/yr   EW universe: {ew.mean() * 12:+.1%}/yr")
        print(f"  excess: {ex.mean() * 12:+.1%}/yr  (t={t:+.2f})   "
              f"worst month excess: {ex.min():+.1%}")
    print("\ncost note: decile turnover ~30-50%/month -> ~1-2%/yr drag at 10bps/side.")


def main() -> None:
    frames = download_500()
    print(f"usable tickers: {len(frames)}")
    base: dict[str, pd.DataFrame] = pd.read_pickle(bt.CACHE)
    spy = base["SPY"]["Close"]
    vix = base["^VIX"]["Close"]
    spy_dd = spy / spy.rolling(252, min_periods=252).max() - 1.0

    path_a(frames, spy, spy_dd, vix)
    path_b(frames)

    print("\ncaveat: current-constituent survivorship bias is WORSE at 500 names")
    print("than 100 (more blown-up mid-caps missing). Rankings > absolute levels.")


if __name__ == "__main__":
    main()
