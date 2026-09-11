"""Backtest the dashboard's PRICE-ONLY signals against a same-universe control.

    python research/sheet/backtest.py

WHAT IS AND IS NOT TESTED, AND WHY

Testable (computable from the price panel at every past date):
    momentum score, zone_status, RSI, 200-SMA side, distance to support

NOT testable, and not faked here:
    RATE          yfinance gives only CURRENT fundamentals. There is no
                  point-in-time P/E, ROE or margin history. Scoring 2023
                  dates with 2026 fundamentals is look-ahead bias and would
                  manufacture a beautiful result that does not exist.
    UNUSUAL       no historical option chains are available at all.

THE CONTROL IS THE WHOLE EXPERIMENT

The universe is TODAY'S S&P 500. Every name in it survived to today, and
several were added BECAUSE they went up. Backtesting any signal on that list
produces inflated returns no matter what the signal is -- this project has
measured that bias at roughly 20-26 percentage points.

So a raw return number is worthless. Every signal is scored against RANDOM
picks drawn from THE SAME BIASED UNIVERSE on THE SAME DATES with THE SAME
basket size. Both legs carry identical survivorship bias, so the difference
between them does not. That difference is the only number that means
anything, and it is the column called EDGE.

Inference is a date-block bootstrap: whole rebalance dates are resampled
together, because 500 stocks on one date are not 500 independent
observations -- they mostly move with the market.
"""
from __future__ import annotations

import io
import os
import sys
import warnings

_OUT = io.TextIOWrapper(open(sys.stdout.fileno(), "wb", closefd=False),
                        encoding="utf-8", errors="replace")


def say(*a) -> None:
    print(*a, file=_OUT)
    _OUT.flush()


warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
_s = importlib.util.spec_from_file_location("cp", os.path.join(HERE, "compute.py"))
cp = importlib.util.module_from_spec(_s)
_s.loader.exec_module(cp)

HORIZONS = [21, 63]
N_RANDOM = 400           # random baskets per date
N_BOOT = 2000            # date-block bootstrap draws
WARMUP = 252             # bars needed before a signal may be computed


def month_ends(idx: pd.DatetimeIndex) -> list[pd.Timestamp]:
    s = pd.Series(idx, index=idx)
    return [d for d in s.groupby([idx.year, idx.month]).last().tolist()]


def trailing_support(h: np.ndarray, l: np.ndarray, spot: float, k: int = 5):
    """Nearest clustered swing low below spot, using ONLY the window given."""
    lows = []
    for i in range(k, len(l) - k):
        w = l[i - k:i + k + 1]
        if l[i] == w.min() and (w == l[i]).sum() == 1:
            lows.append((i, float(l[i])))
    cl = cp.cluster(lows, len(l))
    cand = [c for c in cl if c["price"] < spot * 0.995]
    if not cand:
        return np.nan
    strong = [c for c in cand if c["touches"] >= 2]
    return max((strong or cand), key=lambda c: c["price"])["price"]


def build_signals(close: pd.DataFrame, high: pd.DataFrame, low: pd.DataFrame,
                  syms: list[str], dates: list[pd.Timestamp]) -> pd.DataFrame:
    """One row per (date, symbol) with every signal computed AS OF that date."""
    rows = []
    C = close[syms]
    for d in dates:
        if d not in C.index:
            continue
        i = C.index.get_loc(d)
        if i < WARMUP:
            continue
        win = slice(max(0, i - 504), i + 1)          # <= 2y trailing, inclusive
        sub = C.iloc[win]
        spot = sub.iloc[-1]
        sma200 = sub.tail(200).mean()
        sma50 = sub.tail(50).mean()
        # momentum, all from data at or before d
        m3 = sub.iloc[-1] / sub.iloc[-64] - 1 if len(sub) > 64 else np.nan
        m6 = sub.iloc[-1] / sub.iloc[-127] - 1 if len(sub) > 127 else np.nan
        m121 = (sub.iloc[-22] / sub.iloc[-253] - 1) if len(sub) > 253 else np.nan
        d1 = sub.pct_change()
        rsi_v = {}
        for s in syms:
            c = sub[s].dropna()
            rsi_v[s] = cp.rsi(c) if len(c) > 30 else np.nan
        atr_v, sup_v = {}, {}
        for s in syms:
            hh = high[s].iloc[win].to_numpy() if s in high else None
            ll = low[s].iloc[win].to_numpy() if s in low else None
            cc = sub[s]
            if hh is None or ll is None or cc.isna().all():
                atr_v[s], sup_v[s] = np.nan, np.nan
                continue
            ok = ~np.isnan(ll)
            atr_v[s] = cp.atr(pd.Series(hh), pd.Series(ll), cc) if ok.sum() > 20 else np.nan
            sup_v[s] = (trailing_support(hh[ok], ll[ok], float(cc.iloc[-1]))
                        if ok.sum() > 60 and np.isfinite(cc.iloc[-1]) else np.nan)
        for s in syms:
            p = spot.get(s, np.nan)
            if not np.isfinite(p):
                continue
            rows.append({
                "date": d, "symbol": s, "price": float(p),
                "mom3": float(m3.get(s, np.nan)), "mom6": float(m6.get(s, np.nan)),
                "mom121": float(m121.get(s, np.nan)),
                "sma200": float(sma200.get(s, np.nan)),
                "sma50": float(sma50.get(s, np.nan)),
                "rsi": rsi_v.get(s, np.nan), "atr": atr_v.get(s, np.nan),
                "support": sup_v.get(s, np.nan),
            })
    sig = pd.DataFrame(rows)
    sig["above200"] = sig["price"] > sig["sma200"]
    sig["pct_to_support"] = (sig["support"] / sig["price"] - 1) * 100
    # momentum score = cross-sectional rank on that date only
    for c in ("mom3", "mom6", "mom121"):
        sig[f"r_{c}"] = sig.groupby("date")[c].rank(pct=True)
    sig["mom_score"] = sig[["r_mom3", "r_mom6", "r_mom121"]].mean(axis=1) * 100
    # price-only buy zone: support / 200-SMA / spot-1.5ATR (NO valuation anchor,
    # which would need point-in-time fundamentals that do not exist)
    A = ["support", "sma200"]
    sig["anchor_vol"] = sig["price"] - 1.5 * sig["atr"]
    anchors = sig[A + ["anchor_vol"]]
    below = anchors.where(anchors.lt(sig["price"], axis=0))
    sig["n_anchors"] = below.notna().sum(axis=1)
    sig["zone_high"] = below.median(axis=1)
    sig["in_zone"] = sig["price"] <= sig["zone_high"] * 1.03
    return sig


def fwd_returns(close: pd.DataFrame, sig: pd.DataFrame, h: int) -> pd.Series:
    idx = close.index
    out = np.full(len(sig), np.nan)
    pos = {d: idx.get_loc(d) for d in sig["date"].unique() if d in idx}
    for j, (d, s, p) in enumerate(zip(sig["date"], sig["symbol"], sig["price"])):
        i = pos.get(d)
        if i is None or i + h >= len(idx) or s not in close:
            continue
        b = close[s].iloc[i + h]
        if np.isfinite(b) and p > 0:
            out[j] = b / p - 1
    return pd.Series(out, index=sig.index)


def score(sig: pd.DataFrame, mask: pd.Series, ret: pd.Series, rng,
          basket: int = 25):
    """Signal basket vs random baskets of the same size, same dates."""
    per_date = []
    for d, g in sig.groupby("date"):
        r = ret.loc[g.index]
        ok = r.notna()
        if ok.sum() < 60:
            continue
        m = mask.loc[g.index] & ok
        if m.sum() < 5:
            continue
        pool = r[ok].to_numpy()
        sel = float(r[m].mean())
        n = min(int(m.sum()), basket)
        draws = rng.integers(0, len(pool), (N_RANDOM, n))
        ctrl = float(pool[draws].mean(axis=1).mean())
        per_date.append((d, sel, ctrl, int(m.sum())))
    if len(per_date) < 8:
        return None
    df = pd.DataFrame(per_date, columns=["date", "sel", "ctrl", "n"])
    df["edge"] = df["sel"] - df["ctrl"]
    # date-block bootstrap: resample whole dates, not individual stocks
    boot = np.array([df["edge"].sample(len(df), replace=True,
                                       random_state=int(rng.integers(1 << 31))).mean()
                     for _ in range(N_BOOT)])
    p = float((np.sign(boot) != np.sign(df["edge"].mean())).mean() * 2)
    return {"dates": len(df), "avg_picks": df["n"].mean(),
            "signal_pct": df["sel"].mean() * 100,
            "random_pct": df["ctrl"].mean() * 100,
            "edge_pct": df["edge"].mean() * 100,
            "win_rate": float((df["edge"] > 0).mean() * 100),
            "p": min(p, 1.0)}


def main() -> None:
    u = pd.read_csv(os.path.join(HERE, "sp500.csv"))
    close = cp.load_px("close")
    high, low = cp.load_px("high"), cp.load_px("low")
    syms = [s for s in u.symbol if s in close.columns]
    dates = month_ends(close.index)
    say(f"universe {len(syms)} names | {len(close)} trading days "
        f"| {close.index[0]:%Y-%m-%d} .. {close.index[-1]:%Y-%m-%d}")

    say("computing signals as-of each month end (no look-ahead) ...")
    sig = build_signals(close, high, low, syms, dates)
    say(f"{len(sig):,} (date, symbol) observations over "
        f"{sig['date'].nunique()} rebalance dates\n")

    rng = np.random.default_rng(5)
    TESTS = [
        ("momentum top 10%", lambda s: s["mom_score"] >= 90),
        ("momentum top 20%", lambda s: s["mom_score"] >= 80),
        ("momentum bottom 10%", lambda s: s["mom_score"] <= 10),
        ("IN ZONE (price anchors)", lambda s: s["in_zone"]),
        ("IN ZONE + above 200sma", lambda s: s["in_zone"] & s["above200"]),
        ("above 200-SMA", lambda s: s["above200"]),
        ("below 200-SMA", lambda s: ~s["above200"]),
        ("RSI < 30", lambda s: s["rsi"] < 30),
        ("RSI > 70", lambda s: s["rsi"] > 70),
        ("within 2% of support", lambda s: s["pct_to_support"] > -2),
        ("mom top20 + above200", lambda s: (s["mom_score"] >= 80) & s["above200"]),
    ]
    for h in HORIZONS:
        ret = fwd_returns(close, sig, h)
        say(f"===== {h} trading days forward "
            f"({'~1 month' if h == 21 else '~3 months'}) =====")
        say(f"{'signal':<26}{'dates':>6}{'picks':>7}{'signal':>9}{'random':>9}"
            f"{'EDGE':>8}{'win%':>7}{'p':>7}")
        say("-" * 79)
        for name, fn in TESTS:
            r = score(sig, fn(sig), ret, rng)
            if r is None:
                say(f"{name:<26}   too few usable dates")
                continue
            say(f"{name:<26}{r['dates']:>6}{r['avg_picks']:>7.0f}"
                f"{r['signal_pct']:>8.2f}%{r['random_pct']:>8.2f}%"
                f"{r['edge_pct']:>7.2f}%{r['win_rate']:>6.0f}%{r['p']:>7.3f}")
        say("")
    say("EDGE = signal basket minus random baskets of the same size, drawn from")
    say("the SAME survivorship-biased universe on the SAME dates. Both legs")
    say("carry the bias, so EDGE does not. Only EDGE means anything; the raw")
    say("'signal' column is inflated and is shown only to prove that.")
    say("p = two-sided date-block bootstrap. 11 signals x 2 horizons = 22 tests,")
    say(f"so the Bonferroni bar is p < {0.05/22:.4f}.")
    say("")
    say("NOT TESTED: RATE (no point-in-time fundamentals exist in yfinance) and")
    say("UNUSUAL options (no historical option chains). Both would require")
    say("look-ahead to 'backtest' and are therefore left unmeasured, not faked.")


if __name__ == "__main__":
    main()
