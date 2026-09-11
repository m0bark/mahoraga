# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = [
#     "pandas>=2.2",
#     "numpy>=1.26",
# ]
# ///
"""Insider cluster-buy event study (forced-information family, shot #1).

Signal (point-in-time): a symbol has a CLUSTER BUY when, within a trailing
30-calendar-day window of FILING dates, >= 3 DISTINCT insiders filed
open-market purchases (code P) totaling >= $200k. Event date = filing date
when the condition first becomes true; 90-day cooldown per symbol.
Filing date, not transaction date — you can only trade what's public.

Study: forward 21/63/126-trading-day returns vs the EW universe, on the
cached 500-large-cap price panel. Coverage will be partial (insider buying
skews small-cap) — reported. Sale clusters computed as an inverse check.

Tier: SCOUTING (price panel is survivorship-biased; the signal data itself
is complete and point-in-time). Run after insider_download.py all:
  uv run --python 3.12 insider_clusters.py
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
COMPACT = HERE / "compact"
PRICES_500 = HERE.parent / "panic_reversal" / "prices500.pkl"

MIN_OWNERS = 3
MIN_VALUE = 200_000
WINDOW_DAYS = 30
COOLDOWN_DAYS = 90
HORIZONS = (21, 63, 126)


def load_transactions() -> pd.DataFrame:
    parts = []
    for f in sorted(COMPACT.glob("*.csv.gz")):
        parts.append(pd.read_csv(f, compression="gzip", dtype={"symbol": str}))
    t = pd.concat(parts, ignore_index=True)
    t["filing_date"] = pd.to_datetime(t["filing_date"], errors="coerce")
    t["symbol"] = t["symbol"].str.upper().str.strip()
    t = t.dropna(subset=["filing_date", "symbol", "owner_cik", "value"])
    t = t[t["value"] > 0]
    return t


def find_clusters(t: pd.DataFrame, code: str) -> pd.DataFrame:
    x = t[t.code == code].sort_values("filing_date")
    events = []
    for sym, g in x.groupby("symbol"):
        dates = g.filing_date.to_numpy()
        owners = g.owner_cik.to_numpy()
        values = g.value.to_numpy()
        last_event = np.datetime64("1900-01-01")
        for i in range(len(g)):
            d = dates[i]
            if (d - last_event) / np.timedelta64(1, "D") < COOLDOWN_DAYS:
                continue
            lo = d - np.timedelta64(WINDOW_DAYS, "D")
            mask = (dates >= lo) & (dates <= d)
            if len(set(owners[mask])) >= MIN_OWNERS and values[mask].sum() >= MIN_VALUE:
                events.append({"symbol": sym, "date": pd.Timestamp(d),
                               "n_owners": len(set(owners[mask])),
                               "value": float(values[mask].sum())})
                last_event = d
    return pd.DataFrame(events)


def study(events: pd.DataFrame, closes: pd.DataFrame, label: str) -> None:
    ew = closes.mean(axis=1)
    covered = events[events.symbol.isin(closes.columns)].copy()
    print(f"\n{label}: {len(events)} events total, "
          f"{len(covered)} on covered symbols "
          f"({len(covered) / max(len(events), 1):.0%} coverage)")
    idx = closes.index
    for hz in HORIZONS:
        rets, mkts = [], []
        for _, e in covered.iterrows():
            pos = idx.searchsorted(e.date) + 1  # trade next session
            if pos + hz >= len(idx):
                continue
            px = closes[e.symbol].iloc[pos: pos + hz + 1]
            if px.isna().any() or px.iloc[0] <= 0:
                continue
            rets.append(px.iloc[-1] / px.iloc[0] - 1.0)
            mkts.append(ew.iloc[pos + hz] / ew.iloc[pos] - 1.0)
        r, mkt = pd.Series(rets), pd.Series(mkts)
        ex = r - mkt
        if len(ex) < 20:
            print(f"  {hz:3d}d: n={len(ex)} — too few")
            continue
        t_ex = ex.mean() / ex.std(ddof=1) * np.sqrt(len(ex))
        print(f"  {hz:3d}d: n={len(ex):4d}  raw={r.mean():+.2%}  "
              f"excess vs EW={ex.mean():+.2%} (t={t_ex:+.2f})  "
              f"win={float((ex > 0).mean()):.0%}  median ex={ex.median():+.2%}")


def main() -> None:
    t = load_transactions()
    print(f"transactions loaded: {len(t):,} "
          f"({(t.code == 'P').sum():,} buys, {(t.code == 'S').sum():,} sales), "
          f"{t.filing_date.min().date()} .. {t.filing_date.max().date()}, "
          f"{t.symbol.nunique():,} symbols")

    frames = pd.read_pickle(PRICES_500)
    closes = pd.DataFrame({s: df["Close"] for s, df in frames.items()})

    buys = find_clusters(t, "P")
    buys.to_csv(HERE / "cluster_buys.csv", index=False)
    study(buys, closes, f"CLUSTER BUYS (>= {MIN_OWNERS} insiders, "
                        f">= ${MIN_VALUE / 1000:.0f}k, {WINDOW_DAYS}d window)")

    officer = t[(t.code == "P") & (t.is_officer | t.is_director)]
    study(find_clusters(officer.assign(code="P"), "P"), closes,
          "CLUSTER BUYS, officers/directors only")

    sells = find_clusters(t, "S")
    study(sells, closes, "CLUSTER SELLS (inverse check — expected weak)")

    print("\ncaveats: price panel = survivorship-biased current large caps; "
          "coverage skews the sample toward big names (where the insider "
          "effect is weakest in the literature). A pass here understates "
          "small-cap potential; a fail here does NOT kill the small-cap case.")


if __name__ == "__main__":
    main()
