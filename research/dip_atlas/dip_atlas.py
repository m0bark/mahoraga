# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = [
#     "pandas>=2.2",
#     "numpy>=1.26",
# ]
# ///
"""Dip Atlas v1 — empirical anatomy of every >=20% dip, 500 large caps, 2005-2026.

GATHER: extract every episode where a stock fell >=20% below its 252d high.
PROCESS: formation speed/shape, catalyst class, trough conditions, bottom
signals, false-bottom rates, recovery times, support behavior.

Tier: Prometheus SCOUTING — survivorship-biased universe (current
constituents), descriptive statistics only, NO trading verdict. Anything
tradeable found here becomes a hypothesis card for a QC Sentinel test.

Run:  uv run --python 3.12 dip_atlas.py
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
PRICES_500 = HERE.parent / "panic_reversal" / "prices500.pkl"
PRICES_IDX = HERE.parent / "panic_reversal" / "prices.pkl"

DIP_THRESHOLD = -0.20        # an episode = drawdown crossing this
RECOVERY_LEVEL = -0.05       # episode ends when drawdown recovers to here
SHOCK_DAY = -0.12
SHOCK_GAP = -0.08
SYSTEMIC_DD = -0.12
CAPITULATION_RET = -0.07
CAPITULATION_VOLX = 3.0


def wilder_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    ag = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    al = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    return (100 - 100 / (1 + ag / al.replace(0.0, np.nan))).fillna(50.0)


def episodes_for(ticker: str, df: pd.DataFrame, spy_dd: pd.Series,
                 spy_rsi: pd.Series, vix: pd.Series) -> list[dict]:
    close, low, open_, vol = df["Close"], df["Low"], df["Open"], df["Volume"]
    n = len(df)
    if n < 400:
        return []
    roll_high = close.rolling(252, min_periods=252).max()
    dd = (close / roll_high - 1.0).to_numpy()
    ret1 = close.pct_change().to_numpy()
    gap1 = (open_ / close.shift(1) - 1.0).to_numpy()
    vol60 = vol.rolling(60, min_periods=20).mean().to_numpy()
    rsi = wilder_rsi(close).to_numpy()
    logc = np.log(close.to_numpy())
    lows = low.to_numpy()
    closes = close.to_numpy()
    idx = df.index

    out: list[dict] = []
    i = 252
    while i < n:
        if not (dd[i] <= DIP_THRESHOLD and dd[i - 1] > DIP_THRESHOLD):
            i += 1
            continue
        # peak = last day at (or within 1% of) the rolling high before the cross
        peak = i
        for j in range(i, 252 - 1, -1):
            if dd[j] >= -0.01:
                peak = j
                break
        # episode end = recovery to -5% or end of data (censored)
        end = n - 1
        censored = True
        for j in range(i, n):
            if dd[j] >= RECOVERY_LEVEL:
                end = j
                censored = False
                break
        trough = peak + int(np.argmin(closes[peak:end + 1]))
        trough_dd = closes[trough] / roll_high.iloc[i] - 1.0
        min_dd_episode = float(np.min(dd[i:end + 1]))

        seg_ret = ret1[peak + 1:trough + 1]
        seg_gap = gap1[peak + 1:trough + 1]
        shock = bool(len(seg_ret) and (np.nanmin(seg_ret) <= SHOCK_DAY
                                       or np.nanmin(seg_gap) <= SHOCK_GAP))
        total_decline = logc[trough] - logc[peak]
        worst5 = float(np.sum(np.sort(np.log1p(seg_ret[~np.isnan(seg_ret)]))[:5])) \
            if len(seg_ret) >= 5 else np.nan
        crash_concentration = worst5 / total_decline if total_decline < -1e-9 else np.nan

        d_tr = idx[trough]
        systemic = bool(float(spy_dd.asof(d_tr)) <= SYSTEMIC_DD)
        vix_tr = float(vix.asof(d_tr)) if not np.isnan(vix.asof(d_tr)) else np.nan

        # capitulation day within 5d of trough: big down day on huge volume
        lo5, hi5 = max(trough - 5, 0), min(trough + 5, n - 1)
        cap = False
        for j in range(lo5, hi5 + 1):
            if (not np.isnan(ret1[j]) and ret1[j] <= CAPITULATION_RET
                    and vol60[j] > 0 and vol.iloc[j] >= CAPITULATION_VOLX * vol60[j]):
                cap = True
                break

        # signal S1: first RSI recross above 30 after the cross day
        s1 = None
        was_below = False
        for j in range(i, min(end, trough + 60) + 1):
            if rsi[j] < 30:
                was_below = True
            elif was_below and rsi[j] >= 30:
                s1 = j
                break
        # S3: same but only while SPY itself is not oversold
        s3 = None
        was_below = False
        for j in range(i, min(end, trough + 60) + 1):
            if rsi[j] < 30:
                was_below = True
            elif was_below and rsi[j] >= 30 and float(spy_rsi.asof(idx[j])) >= 30:
                s3 = j
                break

        def false_bottom(sig: int | None) -> bool | None:
            if sig is None:
                return None
            low_at_sig = float(np.min(lows[peak:sig + 1]))
            later_low = float(np.min(lows[sig:end + 1])) if sig < end else low_at_sig
            return later_low < 0.95 * low_at_sig

        # retest: after first touching the trough low, does price come back
        # within 5% of it between 10 and 120 days later?
        retest = False
        for j in range(trough + 10, min(trough + 120, end) + 1):
            if lows[j] <= closes[trough] * 1.05:
                retest = True
                break

        # recovery half-life: days from trough to retracing half the dip
        half_level = closes[trough] * np.exp(-0.5 * total_decline)
        half_days = None
        for j in range(trough, end + 1):
            if closes[j] >= half_level:
                half_days = j - trough
                break

        # support: prior 2y low before the peak — did the trough hold above it?
        pre = lows[max(peak - 504, 0):peak]
        support_held = bool(len(pre) and closes[trough] >= np.min(pre))

        out.append({
            "ticker": ticker,
            "peak_date": idx[peak], "trough_date": d_tr,
            "min_dd": min_dd_episode, "trough_dd": float(trough_dd),
            "days_peak_trough": trough - peak,
            "crash_concentration": crash_concentration,
            "shock": shock, "systemic": systemic,
            "vix_trough": vix_tr, "rsi_trough": float(rsi[trough]),
            "capitulation": cap, "retest": retest,
            "censored": censored,
            "days_to_half": half_days,
            "days_to_recovery": (end - trough) if not censored else None,
            "s1_offset": (s1 - trough) if s1 is not None else None,
            "s1_false_bottom": false_bottom(s1),
            "s3_offset": (s3 - trough) if s3 is not None else None,
            "s3_false_bottom": false_bottom(s3),
            "support_held": support_held,
        })
        i = end + 20
    return out


def pct(x) -> str:
    return f"{x:.0%}"


def main() -> None:
    frames: dict[str, pd.DataFrame] = pd.read_pickle(PRICES_500)
    idx_frames = pd.read_pickle(PRICES_IDX)
    spy = idx_frames["SPY"]["Close"]
    vix = idx_frames["^VIX"]["Close"]
    spy_dd = spy / spy.rolling(252, min_periods=252).max() - 1.0
    spy_rsi = wilder_rsi(spy)

    eps: list[dict] = []
    for t, df in frames.items():
        eps.extend(episodes_for(t, df, spy_dd, spy_rsi, vix))
    e = pd.DataFrame(eps)
    e.to_csv(HERE / "episodes.csv", index=False)
    print(f"DIP ATLAS v1 — {len(e)} episodes (>=20% below 252d high), "
          f"{e.ticker.nunique()} tickers, {e.peak_date.min().year}-{e.peak_date.max().year}")
    print("tier: SCOUTING — survivorship-biased universe, descriptive only\n")

    print("=== WHERE DIPS STOP, part 1: is there a floor? (conditional continuation) ===")
    for a, b in [(0.20, 0.30), (0.30, 0.40), (0.40, 0.50), (0.50, 0.60)]:
        base = e[e.min_dd <= -a]
        cont = base[base.min_dd <= -b]
        print(f"  P(reaches -{b:.0%} | reached -{a:.0%}) = {len(cont) / len(base):.0%}  (n={len(base)})")

    print("\n=== HOW DIPS FORM: class anatomy ===")
    e["klass"] = np.select(
        [e.systemic & e.shock, e.systemic & ~e.shock, ~e.systemic & e.shock],
        ["systemic-shock", "systemic-grind", "idio-shock"], default="idio-grind")
    g = e.groupby("klass").agg(
        n=("min_dd", "size"), median_depth=("min_dd", "median"),
        median_days_to_trough=("days_peak_trough", "median"),
        crash_conc=("crash_concentration", "median"),
        capitulation_rate=("capitulation", "mean"),
    )
    print(g.to_string(float_format=lambda x: f"{x:+.0%}" if abs(x) < 5 else f"{x:.0f}"))
    print(f"\n  crash concentration = share of the whole decline that happened in its 5 worst days")
    print(f"  overall median: {e.crash_concentration.median():.0%} of the damage in 5 days")

    print("\n=== WHERE DIPS STOP, part 2: conditions at the trough ===")
    print(f"  capitulation day (>=7% drop on >=3x volume) within 5d of the low: {pct(e.capitulation.mean())}")
    print(f"    ... in systemic dips: {pct(e[e.systemic].capitulation.mean())}   idio dips: {pct(e[~e.systemic].capitulation.mean())}")
    print(f"  median RSI at the exact low: {e.rsi_trough.median():.0f}")
    print(f"  median VIX at the low: systemic {e[e.systemic].vix_trough.median():.0f} vs idio {e[~e.systemic].vix_trough.median():.0f}")
    print(f"  trough retested (price back within 5% of low, 10-120d later): {pct(e.retest.mean())}")
    print(f"  trough held above the prior 2-year low ('support'): {pct(e.support_held.mean())}")

    print("\n=== BOTTOM SIGNALS: timing vs the actual low ===")
    for name, off, fb in [("S1 RSI-recross", "s1_offset", "s1_false_bottom"),
                          ("S3 RSI-recross + market not oversold", "s3_offset", "s3_false_bottom")]:
        s = e[e[off].notna()]
        offs = s[off].astype(float)
        fbr = s[fb].astype(bool)
        print(f"  {name}: fires in {len(s)}/{len(e)} episodes")
        print(f"    median offset from the low: {offs.median():+.0f} trading days "
              f"(negative = fired BEFORE the low = knife still falling)")
        print(f"    within +/-10d of the low: {pct((offs.abs() <= 10).mean())}   "
              f"fired before the low: {pct((offs < 0).mean())}")
        print(f"    FALSE BOTTOM rate (price later broke >=5% below the signal-day low): {pct(fbr.mean())}")

    print("\n=== RECOVERY ===")
    rec = e[~e.censored]
    print(f"  recovered to within 5% of old high inside the sample: {pct((~e.censored).mean())} "
          f"(survivorship-inflated — dead companies are absent)")
    print(f"  median days low -> half the dip retraced: {rec.days_to_half.median():.0f}")
    print(f"  median days low -> full recovery: {rec.days_to_recovery.median():.0f}")
    for k, gk in e.groupby("klass"):
        r = gk[~gk.censored]
        if len(r):
            print(f"    {k}: {pct((~gk.censored).mean())} recovered, median {r.days_to_recovery.median():.0f}d to full")


if __name__ == "__main__":
    main()
