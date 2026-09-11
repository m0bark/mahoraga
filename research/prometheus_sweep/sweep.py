# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = [
#     "yfinance>=0.2.50",
#     "pandas>=2.2",
#     "numpy>=1.26",
# ]
# ///
"""Prometheus sweep: test a battery of documented market anomalies on one dataset.

Universe: ~100 current US large caps + SPY + VIX, daily, 2005-2026 (cached by
research/panic_reversal/backtest.py). Survivorship-biased — cross-sectional
results are indicative, not proof.

Run:  uv run --python 3.12 sweep.py
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

CACHE = Path(__file__).parent.parent / "panic_reversal" / "prices.pkl"
COST_PER_SIDE = 0.0010


def one_sample_t(x: pd.Series) -> float:
    x = x.dropna()
    return float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x))))


def welch_t(a: pd.Series, b: pd.Series) -> float:
    a, b = a.dropna(), b.dropna()
    return float(
        (a.mean() - b.mean())
        / np.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b))
    )


def verdict(t: float, tradeable_note: str = "") -> str:
    if abs(t) >= 2.5:
        v = "SURVIVES (statistically)"
    elif abs(t) >= 1.5:
        v = "MARGINAL"
    else:
        v = "DEAD in this sample"
    return f"{v}{'  — ' + tradeable_note if tradeable_note else ''}"


def block(title: str, anchor: str) -> None:
    print("\n" + "=" * 70)
    print(f"{title}   [{anchor}]")
    print("=" * 70)


def turn_of_month(spy: pd.Series) -> None:
    block("1. Turn-of-month effect (SPY)", "Lakonishok & Smidt 1988")
    r = spy.pct_change().dropna()
    month = r.index.to_period("M")
    day_num = r.groupby(month).cumcount() + 1
    total = r.groupby(month).transform("size")
    day_rev = total - day_num  # 0 = last day of month
    in_win = (day_num <= 3) | (day_rev <= 3)
    r_in, r_out = r[in_win], r[~in_win]
    t = welch_t(r_in, r_out)
    print(f"window = last 4 + first 3 trading days ({in_win.mean():.0%} of days)")
    print(f"mean daily: in-window {r_in.mean():+.4%}  vs out {r_out.mean():+.4%}")
    print(f"annualized if only invested in-window: {r_in.mean() * 252 * in_win.mean():+.1%}"
          f"  (buy-hold whole month: {r.mean() * 252:+.1%})")
    print(f"t(diff) = {t:+.2f}   -> {verdict(t)}")


def overnight_vs_intraday(spy_o: pd.Series, spy_c: pd.Series,
                          opens: pd.DataFrame, closes: pd.DataFrame) -> None:
    block("2. Overnight vs intraday drift", "Cooper, Cliff & Gulen 2008")
    on = (spy_o / spy_c.shift(1) - 1).dropna()
    intra = (spy_c / spy_o - 1).dropna()
    print(f"SPY  overnight ann. {on.mean() * 252:+.1%} (t={one_sample_t(on):+.2f})   "
          f"intraday ann. {intra.mean() * 252:+.1%} (t={one_sample_t(intra):+.2f})")
    on_p = (opens / closes.shift(1) - 1).mean(axis=1).dropna()
    in_p = (closes / opens - 1).mean(axis=1).dropna()
    print(f"EW universe overnight ann. {on_p.mean() * 252:+.1%} (t={one_sample_t(on_p):+.2f})   "
          f"intraday ann. {in_p.mean() * 252:+.1%} (t={one_sample_t(in_p):+.2f})")
    t = welch_t(on, intra)
    print(f"t(SPY overnight vs intraday) = {t:+.2f}   -> "
          f"{verdict(t, 'daily round trip: costs ~25bps/day dwarf the edge — diagnostic, not tradeable')}")


def vix_spike_reversion(spy: pd.Series, vix: pd.Series) -> None:
    block("3. VIX-spike mean reversion (buy SPY on panic)", "vol risk premium lit.")
    sma = vix.rolling(60).mean()
    spike = (vix >= 1.5 * sma).reindex(spy.index).fillna(False)
    hold = 10
    events, i = [], 0
    idx = spy.index
    while i < len(idx) - hold:
        if spike.iloc[i]:
            events.append(float(spy.iloc[i + hold] / spy.iloc[i] - 1))
            i += hold  # non-overlapping
        else:
            i += 1
    ev = pd.Series(events)
    base = spy.iloc[::hold].pct_change().dropna()  # unconditional non-overlapping 10d
    t = welch_t(ev, base)
    print(f"events (VIX >= 1.5x its 60d avg): {len(ev)}, non-overlapping {hold}d holds")
    print(f"mean 10d SPY after spike: {ev.mean():+.2%}  vs unconditional {base.mean():+.2%}")
    print(f"win rate after spike: {(ev > 0).mean():.0%}   worst event: {ev.min():+.1%}")
    print(f"t(diff) = {t:+.2f}   -> {verdict(t)}")


def sma200_timing(spy: pd.Series) -> None:
    block("4. 200-day SMA trend filter on SPY", "Faber 2007")
    r = spy.pct_change()
    sig = (spy > spy.rolling(200).mean()).shift(1).fillna(False)
    strat = (r * sig).dropna()
    bh = r.dropna()

    def stats(x: pd.Series) -> tuple[float, float, float]:
        eq = (1 + x).cumprod()
        cagr = float(eq.iloc[-1] ** (252 / len(x)) - 1)
        dd = float((eq / eq.cummax() - 1).min())
        vol = float(x.std() * np.sqrt(252))
        return cagr, dd, vol

    c1, d1, v1 = stats(strat)
    c0, d0, v0 = stats(bh)
    print(f"timing: CAGR {c1:+.1%}  maxDD {d1:+.1%}  vol {v1:.1%}  "
          f"(in market {sig.mean():.0%} of days, cash yield assumed 0)")
    print(f"buyhold: CAGR {c0:+.1%}  maxDD {d0:+.1%}  vol {v0:.1%}")
    print("-> not a return edge; it's a drawdown/regime tool. "
          "Judge by maxDD & vol, not CAGR.")


def momentum_12_1(closes: pd.DataFrame) -> None:
    block("5. Cross-sectional momentum 12-1 (monthly)", "Jegadeesh & Titman 1993")
    m = closes.resample("ME").last()
    mom = m.shift(1) / m.shift(12) - 1
    fwd = m.shift(-1) / m - 1
    valid = mom.notna().sum(axis=1) >= 40
    q = mom.rank(axis=1, pct=True)
    top = fwd.where(q >= 0.8).mean(axis=1)[valid]
    bot = fwd.where(q <= 0.2).mean(axis=1)[valid]
    ew = fwd.mean(axis=1)[valid]
    spread = (top - bot).dropna()
    excess = (top - ew).dropna()
    print(f"months: {len(spread)}   long top quintile / short bottom quintile")
    print(f"L/S spread: {spread.mean() * 12:+.1%}/yr  (t={one_sample_t(spread):+.2f})")
    print(f"long-only top-quintile excess vs EW universe: {excess.mean() * 12:+.1%}/yr "
          f"(t={one_sample_t(excess):+.2f})")
    print(f"worst spread month: {spread.min():+.1%} (momentum crashes are real)")
    print(f"-> {verdict(one_sample_t(spread), 'survivorship likely UNDERSTATES the short leg here')}")


def weekly_reversal(closes: pd.DataFrame) -> None:
    block("6. Short-term reversal: buy the week's losers", "Lehmann 1990")
    w = closes.resample("W-FRI").last()
    wr = w.pct_change()
    fwd = wr.shift(-1)
    q = wr.rank(axis=1, pct=True)
    losers = fwd.where(q <= 0.10).mean(axis=1)
    ew = fwd.mean(axis=1)
    edge = (losers - ew).dropna()
    gross_wk = float(edge.mean())
    net_wk = gross_wk - 2 * COST_PER_SIDE  # full weekly turnover of the sleeve
    t = one_sample_t(edge)
    print(f"weeks: {len(edge)}   bottom-decile 1-week losers vs EW universe, next week")
    print(f"gross edge: {gross_wk:+.3%}/wk = {gross_wk * 52:+.1%}/yr  (t={t:+.2f})")
    print(f"net of 20bps/wk turnover cost: {net_wk:+.3%}/wk = {net_wk * 52:+.1%}/yr")
    print(f"-> {verdict(t, 'verdict must be read on the NET number')}")


def high_52wk_momentum(closes: pd.DataFrame) -> None:
    block("7. 52-week-high proximity (monthly)", "George & Hwang 2004")
    prox = closes / closes.rolling(252, min_periods=252).max()
    m = closes.resample("ME").last()
    p = prox.resample("ME").last()
    fwd = m.shift(-1) / m - 1
    valid = p.notna().sum(axis=1) >= 40
    q = p.rank(axis=1, pct=True)
    near = fwd.where(q >= 0.8).mean(axis=1)[valid]
    far = fwd.where(q <= 0.2).mean(axis=1)[valid]
    spread = (near - far).dropna()
    t = one_sample_t(spread)
    print(f"months: {len(spread)}   near-high quintile minus far-from-high quintile")
    print(f"spread: {spread.mean() * 12:+.1%}/yr  (t={t:+.2f})")
    print("note: 'far from high' IS the falling-knife bucket — a negative spread "
          "here would mean knives outperform; positive means strength persists")
    print(f"-> {verdict(t)}")


def main() -> None:
    frames: dict[str, pd.DataFrame] = pd.read_pickle(CACHE)
    spy_df = frames.pop("SPY")
    vix = frames.pop("^VIX")["Close"]
    spy_c, spy_o = spy_df["Close"], spy_df["Open"]
    closes = pd.DataFrame({t: df["Close"] for t, df in frames.items()})
    opens = pd.DataFrame({t: df["Open"] for t, df in frames.items()})
    print(f"dataset: {closes.shape[1]} tickers, {closes.index[0].date()} .. "
          f"{closes.index[-1].date()}  (survivorship-biased large caps)")

    turn_of_month(spy_c)
    overnight_vs_intraday(spy_o, spy_c, opens, closes)
    vix_spike_reversion(spy_c, vix)
    sma200_timing(spy_c)
    momentum_12_1(closes)
    weekly_reversal(closes)
    high_52wk_momentum(closes)

    print("\n" + "=" * 70)
    print("Caveats: single market, current-constituent bias, no borrow costs on")
    print("short legs, t-stats uncorrected for testing 7 hypotheses at once")
    print("(Bonferroni-adjusted bar for 7 tests: |t| >~ 2.7).")
    print("=" * 70)


if __name__ == "__main__":
    main()
