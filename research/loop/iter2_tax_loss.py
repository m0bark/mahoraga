# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = [
#     "pandas>=2.2",
#     "numpy>=1.26",
# ]
# ///
"""Iter2: turn-of-year tax-loss bounce (forced-flows family).

Mechanism: taxable holders MUST realize losses by Dec 31; that selling is
price-insensitive and lifts in January. Prediction: year-to-November loser
decile UNDERperforms in December (pressure) and OUTperforms in January
(pressure lifts), concentrated in early January.

Honest stats note: the unit of inference is the YEAR (cross-sectional
correlation within a January is huge), so the t that matters is over ~20
year-observations. Loser-conditioning also inherits survivorship bias
(haircut applies). Run:  uv run --python 3.12 iter2_tax_loss.py
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
PRICES_500 = HERE.parent / "panic_reversal" / "prices500.pkl"


def t_over_years(x: pd.Series) -> float:
    return float(x.mean() / x.std(ddof=1) * np.sqrt(len(x)))


def main() -> None:
    frames: dict[str, pd.DataFrame] = pd.read_pickle(PRICES_500)
    closes = pd.DataFrame({t: df["Close"] for t, df in frames.items()})
    m = closes.resample("ME").last()

    rows = []
    for y in range(2006, 2026):
        try:
            p_dec_prev = m[m.index == m[m.index.year == y - 1][m[m.index.year == y - 1].index.month == 12].index[0]].iloc[0]
            p_nov = m[(m.index.year == y) & (m.index.month == 11)].iloc[0]
            p_dec = m[(m.index.year == y) & (m.index.month == 12)].iloc[0]
            p_jan = m[(m.index.year == y + 1) & (m.index.month == 1)].iloc[0]
        except IndexError:
            continue
        perf = (p_nov / p_dec_prev - 1.0).dropna()
        ok = perf.index.intersection(p_dec.dropna().index).intersection(p_jan.dropna().index)
        if len(ok) < 150:
            continue
        perf = perf[ok]
        losers = perf.nsmallest(max(10, len(ok) // 10)).index
        dec_ret = (p_dec / p_nov - 1.0)[ok]
        jan_ret = (p_jan / p_dec - 1.0)[ok]
        rows.append({
            "year": y, "n": len(ok),
            "dec_losers": dec_ret[losers].mean(), "dec_ew": dec_ret.mean(),
            "jan_losers": jan_ret[losers].mean(), "jan_ew": jan_ret.mean(),
        })

    r = pd.DataFrame(rows).set_index("year")
    r["dec_excess"] = r.dec_losers - r.dec_ew
    r["jan_excess"] = r.jan_losers - r.jan_ew
    print("ITER2 — turn-of-year tax-loss bounce (loser decile vs EW universe)")
    print("SCOUTING tier; loser-conditioning inherits survivorship bias.\n")
    print(r[["dec_excess", "jan_excess"]].to_string(
        float_format=lambda x: f"{x:+.1%}"))
    print(f"\nDecember (predicted NEGATIVE): mean {r.dec_excess.mean():+.2%}, "
          f"t={t_over_years(r.dec_excess):+.2f}, years<0: {(r.dec_excess < 0).mean():.0%}")
    print(f"January  (predicted POSITIVE): mean {r.jan_excess.mean():+.2%}, "
          f"t={t_over_years(r.jan_excess):+.2f}, years>0: {(r.jan_excess > 0).mean():.0%}")
    print(f"combined Dec-short/Jan-long spread: mean "
          f"{(r.jan_excess - r.dec_excess).mean():+.2%}/yr-event, "
          f"t={t_over_years(r.jan_excess - r.dec_excess):+.2f}  (n={len(r)} years)")

    # early-January concentration: first 10 trading days vs rest of January
    daily = closes
    early_rows = []
    for y in range(2007, 2027):
        jan_days = daily[(daily.index.year == y) & (daily.index.month == 1)]
        prev_dec = daily[(daily.index.year == y - 1) & (daily.index.month == 12)]
        if len(jan_days) < 15 or len(prev_dec) < 10:
            continue
        p0 = prev_dec.iloc[-1]
        p10 = jan_days.iloc[9]
        pend = jan_days.iloc[-1]
        # losers ranked by Jan..Nov of prior year
        try:
            p_nov = m[(m.index.year == y - 1) & (m.index.month == 11)].iloc[0]
            p_dec_prev2 = m[(m.index.year == y - 2) & (m.index.month == 12)].iloc[0]
        except IndexError:
            continue
        perf = (p_nov / p_dec_prev2 - 1.0).dropna()
        ok = perf.index.intersection(p0.dropna().index).intersection(pend.dropna().index).intersection(p10.dropna().index)
        if len(ok) < 150:
            continue
        losers = perf[ok].nsmallest(max(10, len(ok) // 10)).index
        early = (p10 / p0 - 1.0)[ok]
        late = (pend / p10 - 1.0)[ok]
        early_rows.append({
            "year": y,
            "early_excess": early[losers].mean() - early.mean(),
            "late_excess": late[losers].mean() - late.mean(),
        })
    er = pd.DataFrame(early_rows).set_index("year")
    print(f"\nJanuary concentration: first 10 trading days excess "
          f"{er.early_excess.mean():+.2%} (t={t_over_years(er.early_excess):+.2f})  "
          f"vs rest of Jan {er.late_excess.mean():+.2%} "
          f"(t={t_over_years(er.late_excess):+.2f})  (n={len(er)} years)")


if __name__ == "__main__":
    main()
