"""A real point-in-time Piotroski F-Score from SEC filings, trend legs included.

    python research/sheet/pit_quality.py              # build and report coverage
    python research/sheet/pit_quality.py --save       # write the panel to cache

WHY THIS EXISTS
Card research/cards/2026-08-31-nearhigh-fscore.md logged this line:

    F-Score-lite leg coverage: ['500/500','500/500','500/500','0/500',
                               '0/500','500/500','500/500']

Legs 4 and 5 populated ZERO times out of 500. Those were the two improvement
legs, because the vendor's `.three_years` fields never resolved. Piotroski's
score is mostly about improvement, so every fundamental screen this project has
tested was a degraded static quality score with the trend legs missing, and the
FAIL it recorded refutes that degraded screen rather than the actual claim.

The SEC XBRL companyfacts data already pulled by sec_pit.py carries what the
vendor did not: net income, cash flow from operations, total assets, long-term
debt, share count, gross profit, revenue and current assets/liabilities, each
tagged with the date the filing was FILED. That last field is the whole reason
this is point-in-time: a score dated by the filing date cannot know anything
the market did not know.

THE NINE LEGS, as Piotroski defined them
  profitability
    1  ROA positive                      net income / assets > 0
    2  CFO positive                      cash from operations > 0
    3  ROA improving                     this year's ROA > last year's
    4  earnings backed by cash           CFO/assets > net income/assets
  leverage and liquidity
    5  long-term debt falling            debt/assets below last year's
    6  current ratio improving           CA/CL above last year's
    7  no dilution                       share count not above last year's
  operating efficiency
    8  gross margin improving            GP/revenue above last year's
    9  asset turnover improving          revenue/assets above last year's

Legs 3, 5, 6, 7, 8 and 9 all compare against the SAME FISCAL QUARTER one year
earlier rather than the previous filing, because a retailer's Q4 against its Q3
measures Christmas, not improvement.

HONESTY ABOUT COVERAGE
Three fields are thin in this dataset: gross_profit 37.6%, revenue 56.1%,
debt_lt 58.6%. So legs 5, 8 and 9 will often be unavailable. Rather than
quietly averaging whatever survived, every record carries legs_available, the
score is expressed as a PERCENTAGE of available legs, and a minimum coverage
is enforced. Per-leg coverage is printed, because the one thing the earlier
card proves is that a score which hides its own gaps will be believed.
"""
from __future__ import annotations

import io
import os
import sys

_OUT = io.TextIOWrapper(open(sys.stdout.fileno(), "wb", closefd=False),
                        encoding="utf-8", errors="replace")


def say(*a) -> None:
    print(*a, file=_OUT)
    _OUT.flush()


import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
LONG = os.path.join(HERE, "cache_long")
SRC = os.path.join(LONG, "pit_fundamentals.csv")
OUT = os.path.join(LONG, "pit_fscore.csv")

MIN_LEGS = 6          # below this the score is not comparable across names

LEG_NAMES = [
    "roa_pos", "cfo_pos", "roa_up", "cash_backed",
    "debt_down", "curr_up", "no_dilution",
    "margin_up", "turnover_up",
]


def build() -> pd.DataFrame:
    f = pd.read_csv(SRC)
    f["filed"] = pd.to_datetime(f["filed"], errors="coerce")
    f["_end"] = pd.to_datetime(f["_end"], errors="coerce")
    f = f.dropna(subset=["filed", "symbol"])

    num = ["assets", "liabilities", "equity", "cash", "debt_lt", "op_income",
           "cfo", "capex", "current_assets", "current_liabilities",
           "net_income", "shares", "gross_profit", "revenue"]
    for c in num:
        f[c] = pd.to_numeric(f.get(c), errors="coerce")

    # ---- the ratios each leg is built from
    A = f["assets"].where(f["assets"] > 0)
    f["roa"] = f["net_income"] / A
    f["cfoa"] = f["cfo"] / A
    f["lev"] = f["debt_lt"] / A
    f["curr"] = f["current_assets"] / f["current_liabilities"].where(
        f["current_liabilities"] > 0)
    f["margin"] = f["gross_profit"] / f["revenue"].where(f["revenue"] > 0)
    f["turn"] = f["revenue"] / A

    # ---- YEAR-OVER-YEAR, same fiscal quarter. A merge on (symbol, fp, fy-1)
    # rather than a shift, because filings arrive out of order and a shift
    # would silently compare Q3 against Q2.
    f["fy"] = pd.to_numeric(f["fy"], errors="coerce")
    f = f.dropna(subset=["fy"])
    f["fy"] = f["fy"].astype(int)
    prior_cols = ["roa", "lev", "curr", "shares", "margin", "turn"]
    prior = f[["symbol", "fp", "fy", "filed"] + prior_cols].copy()
    prior["fy"] = prior["fy"] + 1
    prior = prior.rename(columns={c: f"{c}_p" for c in prior_cols})
    # A symbol can file the same (fp, fy) more than once, because restatements
    # reuse the label. keep="last" takes the most recent version, which is the
    # RESTATEMENT -- and a restatement can be filed after the row that consumes
    # it, which is lookahead. keep="first" takes the figure as it was
    # originally reported, which is the only version that was knowable at the
    # time. Small effect here (2 rows of 20,791, found by an audit of this
    # file), but the direction of the error is the dangerous kind.
    prior = (prior.sort_values("filed")
             .drop_duplicates(subset=["symbol", "fp", "fy"], keep="first")
             .drop(columns=["filed"]))
    f = f.merge(prior, on=["symbol", "fp", "fy"], how="left")

    # ---- the nine legs. NaN where the inputs are missing, never 0.
    def leg(cond, *needs):
        ok = np.ones(len(f), dtype=bool)
        for n in needs:
            ok &= f[n].notna().to_numpy()
        return pd.Series(np.where(ok, cond.astype(float), np.nan), index=f.index)

    L = {}
    L["roa_pos"] = leg(f["roa"] > 0, "roa")
    L["cfo_pos"] = leg(f["cfo"] > 0, "cfo")
    L["roa_up"] = leg(f["roa"] > f["roa_p"], "roa", "roa_p")
    L["cash_backed"] = leg(f["cfoa"] > f["roa"], "cfoa", "roa")
    L["debt_down"] = leg(f["lev"] < f["lev_p"], "lev", "lev_p")
    L["curr_up"] = leg(f["curr"] > f["curr_p"], "curr", "curr_p")
    L["no_dilution"] = leg(f["shares"] <= f["shares_p"], "shares", "shares_p")
    L["margin_up"] = leg(f["margin"] > f["margin_p"], "margin", "margin_p")
    L["turnover_up"] = leg(f["turn"] > f["turn_p"], "turn", "turn_p")

    legs = pd.DataFrame(L)
    f["legs_available"] = legs.notna().sum(axis=1)
    f["legs_passed"] = legs.sum(axis=1, skipna=True)
    f["fscore_pct"] = np.where(
        f["legs_available"] >= MIN_LEGS,
        f["legs_passed"] / f["legs_available"] * 100, np.nan)

    say("PER-LEG COVERAGE -- the check the earlier card proved was necessary")
    say(f"  {'leg':<16}{'populated':>12}{'pass rate':>12}")
    say("  " + "-" * 40)
    for n in LEG_NAMES:
        cov = legs[n].notna().mean() * 100
        pr = legs[n].mean(skipna=True) * 100
        flag = "  <-- THIN" if cov < 50 else ""
        say(f"  {n:<16}{cov:>11.1f}%{pr:>11.1f}%{flag}")
    say("  " + "-" * 40)
    say(f"  records with >= {MIN_LEGS} legs: "
        f"{(f['legs_available'] >= MIN_LEGS).mean() * 100:.1f}% of "
        f"{len(f):,}")
    say(f"  median legs available: {f['legs_available'].median():.0f} of 9")

    keep = ["symbol", "filed", "_end", "fy", "fp", "fscore_pct",
            "legs_available", "legs_passed"]
    out = pd.concat([f[keep], legs], axis=1)
    out = out.dropna(subset=["fscore_pct"])
    out = out.sort_values(["symbol", "filed"])
    say(f"\n  usable records: {len(out):,} over {out.symbol.nunique()} symbols")
    say(f"  filed {out.filed.min():%Y-%m-%d} .. {out.filed.max():%Y-%m-%d}")
    return out


def as_of(panel: pd.DataFrame, dates: pd.DatetimeIndex) -> pd.DataFrame:
    """Wide frame, date x symbol, carrying the latest fscore_pct KNOWN on each
    date. merge_asof per symbol on the FILED date, so nothing reaches back to a
    filing the market had not seen."""
    out = {}
    grid = pd.DataFrame(index=pd.DatetimeIndex(dates).sort_values())
    for sym, g in panel.groupby("symbol"):
        g = g.sort_values("filed")[["filed", "fscore_pct"]].dropna()
        if g.empty:
            continue
        s = pd.merge_asof(grid.reset_index().rename(columns={"index": "d"}),
                          g.rename(columns={"filed": "d"}),
                          on="d", direction="backward")
        out[sym] = s.set_index("d")["fscore_pct"]
    return pd.DataFrame(out)


def main() -> None:
    panel = build()
    if "--save" in sys.argv:
        panel.to_csv(OUT, index=False)
        say(f"\nwrote {OUT}")
    say("\nDISTRIBUTION of fscore_pct")
    q = panel["fscore_pct"].quantile([0.1, 0.25, 0.5, 0.75, 0.9])
    for k, v in q.items():
        say(f"  p{int(k * 100):<3} {v:>6.1f}")


if __name__ == "__main__":
    main()
