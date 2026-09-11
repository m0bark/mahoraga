"""Data layer for the S&P 500 dashboard.

    python research/sheet/fetch.py --prices        # fast: bulk OHLCV (~30s)
    python research/sheet/fetch.py --fundamentals  # slow: one call per name (~12m)
    python research/sheet/fetch.py --options       # slow: option chains (~25m)
    python research/sheet/fetch.py --all

WHY THE JOBS ARE SPLIT
Prices come back for all 503 names in one batched request. Fundamentals need
one request PER TICKER, and option chains need one per ticker per expiry.
Refreshing the slow ones hourly would mean ~12,000 requests a day to restate
numbers that change four times a year. So the hourly path touches only
prices; everything else is cached daily and read from disk.

Every cache file carries the UTC timestamp it was written, and the workbook
prints it, so a stale number is visible rather than silently believed.
"""
from __future__ import annotations

import io
import json
import os
import sys
import time
import warnings
from concurrent.futures import ThreadPoolExecutor

_OUT = io.TextIOWrapper(open(sys.stdout.fileno(), "wb", closefd=False),
                        encoding="utf-8", errors="replace")


def say(*a) -> None:
    print(*a, file=_OUT)
    _OUT.flush()


warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import yfinance as yf

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
SP500 = os.path.join(HERE, "sp500.csv")
# macro factor proxies. TLT = long bonds, GLD = gold, USO = oil,
# UUP = dollar index, ^VIX = volatility. SPY is the market leg.
FACTORS = {"SPY": "SPY", "TLT": "TLT", "GLD": "GLD", "OIL": "USO",
           "DXY": "UUP", "VIX": "^VIX"}
HIST_START = "2023-01-01"          # 2y+ of history for betas and pivots


def universe() -> pd.DataFrame:
    return pd.read_csv(SP500)


def stamp(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["fetched_utc"] = pd.Timestamp.utcnow().strftime("%Y-%m-%d %H:%M")
    return df


def fetch_prices() -> None:
    """Bulk OHLCV for every name plus the macro factors. One batched request."""
    u = universe()
    syms = sorted(u.symbol) + list(FACTORS.values())
    say(f"prices: {len(syms)} tickers from {HIST_START}")
    frames = {}
    CH = 150
    for i in range(0, len(syms), CH):
        batch = syms[i:i + CH]
        for attempt in range(3):
            try:
                d = yf.download(batch, start=HIST_START, auto_adjust=True,
                                progress=False, threads=True, group_by="column")
                if not d.empty:
                    for field in ("Close", "Volume", "High", "Low", "Open"):
                        if field in d:
                            f = d[field]
                            if isinstance(f, pd.Series):
                                f = f.to_frame(batch[0])
                            frames.setdefault(field, []).append(f)
                    break
            except Exception as e:
                say(f"  batch {i} attempt {attempt + 1}: {type(e).__name__}")
                time.sleep(4 * (attempt + 1))
        say(f"  {min(i + CH, len(syms))}/{len(syms)}")

    os.makedirs(CACHE, exist_ok=True)
    for field, parts in frames.items():
        px = pd.concat(parts, axis=1)
        px = px.loc[:, ~px.columns.duplicated()].dropna(how="all")
        px.to_csv(os.path.join(CACHE, f"px_{field.lower()}.csv"))
        say(f"  wrote px_{field.lower()}.csv  {px.shape[0]}d x {px.shape[1]} cols")

    close = pd.read_csv(os.path.join(CACHE, "px_close.csv"), index_col=0)
    got = int(close.notna().any().sum())
    say(f"resolved {got}/{len(syms)} tickers")
    with open(os.path.join(CACHE, "prices_stamp.txt"), "w") as f:
        f.write(pd.Timestamp.utcnow().strftime("%Y-%m-%d %H:%M UTC"))


_INFO_KEYS = [
    "shortName", "sector", "industry", "marketCap", "enterpriseValue",
    "trailingPE", "forwardPE", "pegRatio", "priceToSalesTrailing12Months",
    "priceToBook", "enterpriseToEbitda", "enterpriseToRevenue",
    "grossMargins", "operatingMargins", "profitMargins", "ebitdaMargins",
    "returnOnEquity", "returnOnAssets", "debtToEquity", "currentRatio",
    "quickRatio", "totalDebt", "totalCash", "totalRevenue", "ebitda",
    "freeCashflow", "operatingCashflow", "revenueGrowth", "earningsGrowth",
    "earningsQuarterlyGrowth", "dividendYield", "payoutRatio", "beta",
    "trailingEps", "forwardEps", "bookValue", "sharesOutstanding",
    "heldPercentInstitutions", "shortPercentOfFloat", "recommendationMean",
    "numberOfAnalystOpinions", "targetMeanPrice", "targetHighPrice",
    "targetLowPrice", "fiftyTwoWeekHigh", "fiftyTwoWeekLow",
]


def _one_info(sym: str, tries: int = 4) -> dict:
    """One yfinance .info pull, resilient to Yahoo rate-limiting.

    When Yahoo throttles a machine, yf.Ticker(sym).info returns an EMPTY dict
    rather than raising. Accepting that blank is what silently empties
    shortName/sector/RATE/perfect_buy, the analyst consensus and the whole
    Fundamentals sheet on a fresh PC. So an empty payload is treated as a
    throttle and retried with backoff, and only the last attempt gives up.
    """
    row = {"symbol": sym}
    for attempt in range(tries):
        try:
            t = yf.Ticker(sym)
            info = t.info or {}
            throttled = not info.get("marketCap") and not info.get("shortName")
            if throttled and attempt < tries - 1:
                time.sleep(1.5 * (attempt + 1))      # 1.5s, 3s, 4.5s backoff
                continue
            for k in _INFO_KEYS:
                row[k] = info.get(k)
            try:
                cal = t.calendar
                ed = None
                if isinstance(cal, dict):
                    ed = cal.get("Earnings Date")
                    if isinstance(ed, (list, tuple)) and ed:
                        ed = ed[0]
                elif hasattr(cal, "loc") and "Earnings Date" in getattr(cal, "index", []):
                    ed = cal.loc["Earnings Date"][0]
                row["next_earnings"] = str(ed)[:10] if ed is not None else None
            except Exception:
                row["next_earnings"] = None
            if throttled:
                row["error"] = "empty_info_after_retries"
            return row
        except Exception as e:
            row["error"] = type(e).__name__
            if attempt < tries - 1:
                time.sleep(1.5 * (attempt + 1))
    return row


def fetch_fundamentals() -> None:
    u = universe()
    syms = list(u.symbol)
    say(f"fundamentals: {len(syms)} tickers, one request each")
    rows, done = [], [0]
    lock = __import__("threading").Lock()

    def work(s):
        r = _one_info(s)
        with lock:
            done[0] += 1
            if done[0] % 50 == 0:
                say(f"  {done[0]}/{len(syms)}")
        return r

    # 3 threads, not 6: Yahoo throttles a fresh machine hitting .info hard, and
    # a throttle here silently blanks the whole Fundamentals sheet. Slower and
    # complete beats fast and empty.
    with ThreadPoolExecutor(max_workers=3) as ex:
        for r in ex.map(work, syms):
            rows.append(r)

    df = pd.DataFrame(rows).merge(u, on="symbol", how="left",
                                  suffixes=("_yf", ""))
    os.makedirs(CACHE, exist_ok=True)
    stamp(df).to_csv(os.path.join(CACHE, "fundamentals.csv"), index=False)
    bad = df["marketCap"].isna().sum() if "marketCap" in df else len(df)
    say(f"wrote fundamentals.csv: {len(df)} rows, {bad} missing marketCap")
    # A large blank fraction means Yahoo throttled this machine, not that the
    # companies have no data. Say so loudly so it is not mistaken for a clean run.
    if len(df) and bad > len(df) * 0.25:
        say(f"  WARNING: {bad}/{len(df)} rows have no marketCap - Yahoo likely "
            f"rate-limited this machine. Wait 10-15 min and re-run "
            f"'fetch.py --fundamentals', then 'build_workbook.py'.")


def _one_options(sym: str) -> dict:
    """Aggregate near-dated option activity into a 'big money' footprint.

    NOTE: this is used as a SIGNAL ONLY. The account these sheets serve is
    long-spot cash and does not trade options. Reading the option tape to
    infer where size is positioning is not itself an options trade.
    """
    out = {"symbol": sym, "call_notional": 0.0, "put_notional": 0.0,
           "call_vol": 0, "put_vol": 0, "call_oi": 0, "put_oi": 0,
           "max_strike_notional": 0.0, "max_strike": None, "n_expiries": 0}
    try:
        t = yf.Ticker(sym)
        # t.options comes back empty both for names with no listed options AND
        # for a rate-limited machine. Retry a couple of times so a throttle is
        # not mistaken for "no options" and left blank on the Big Money tab.
        exps = list(t.options or [])
        for _retry in range(2):
            if exps:
                break
            time.sleep(1.2 * (_retry + 1))
            exps = list(yf.Ticker(sym).options or [])
        exps = exps[:3]                          # nearest 3 expiries
        out["n_expiries"] = len(exps)
        for e in exps:
            try:
                ch = t.option_chain(e)
            except Exception:
                continue
            for side, frame in (("call", ch.calls), ("put", ch.puts)):
                if frame is None or frame.empty:
                    continue
                f = frame.fillna(0)
                # notional = contract price x volume x 100 shares per contract
                notional = (f["lastPrice"] * f["volume"] * 100)
                out[f"{side}_notional"] += float(notional.sum())
                out[f"{side}_vol"] += int(f["volume"].sum())
                out[f"{side}_oi"] += int(f["openInterest"].sum())
                if len(notional):
                    i = int(notional.idxmax())
                    if float(notional.loc[i]) > out["max_strike_notional"]:
                        out["max_strike_notional"] = float(notional.loc[i])
                        out["max_strike"] = f"{side} {f.loc[i, 'strike']} {e}"
    except Exception as e:
        out["error"] = type(e).__name__
    return out


def fetch_options() -> None:
    u = universe()
    syms = list(u.symbol)
    say(f"options: {len(syms)} tickers x up to 3 expiries")
    rows, done = [], [0]
    lock = __import__("threading").Lock()

    def work(s):
        r = _one_options(s)
        with lock:
            done[0] += 1
            if done[0] % 50 == 0:
                say(f"  {done[0]}/{len(syms)}")
        return r

    # 3 threads to stay under Yahoo's throttle, same reasoning as fundamentals.
    with ThreadPoolExecutor(max_workers=3) as ex:
        for r in ex.map(work, syms):
            rows.append(r)
    df = pd.DataFrame(rows)
    os.makedirs(CACHE, exist_ok=True)
    stamp(df).to_csv(os.path.join(CACHE, "options.csv"), index=False)
    live = (df["call_notional"] + df["put_notional"] > 0).sum()
    say(f"wrote options.csv: {len(df)} rows, {live} with live volume")


def main() -> None:
    a = sys.argv[1:]
    if not a or "--all" in a:
        fetch_prices(); fetch_fundamentals(); fetch_options(); return
    if "--prices" in a:
        fetch_prices()
    if "--fundamentals" in a:
        fetch_fundamentals()
    if "--options" in a:
        fetch_options()


if __name__ == "__main__":
    main()
