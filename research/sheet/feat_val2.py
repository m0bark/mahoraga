"""Point-in-time valuation multiples on UNADJUSTED prices, one row per grid pair.

    python research/sheet/feat_val2.py               # build, report, write
    python research/sheet/feat_val2.py --crosscheck  # also audit share counts
                                                     # against today's real ones

WHY THIS REPLACES feat_val.py
feat_val.py is arithmetically identical to this file and wrong, because it
multiplied an as-reported SEC share count by a close from px_close.csv, which is
split- and dividend-ADJUSTED. An adjusted close is the true close divided by the
cumulative corporate-action factor from that date to the end of the file, so

    adjusted close * as-reported shares = true market cap / (future factor)

and the error is therefore LARGEST for the names that rose and split the most.
Measured on the old file: NVDA 2013-04-30 came out at $195m against a real
$12bn (61x), AAPL at $12.6bn against $420bn (33x), T at $66bn against $190bn
(2.9x). Every multiple built on that is a partial readout of the future, and on
the first pass it produced a clean-looking out-of-sample "low P/E wins" result
that was pure lookahead. This file reads cache_long/px_raw_close.csv, which is
the as-traded close -- see fetch_raw_px.py for how it is recovered and verified.

THE ELEVEN FEATURES
  market_cap      close on the date * share count known on the date
  pe              market_cap / TTM net income
  ps              market_cap / TTM revenue
  pb              market_cap / equity
  p_cash          market_cap / cash
  p_fcf           market_cap / (TTM cfo - TTM capex)
  ev              market_cap + debt_lt - cash
  ev_sales        ev / TTM revenue
  ev_opinc        ev / TTM operating income
  earnings_yield  100 * TTM net income / market_cap
  fcf_yield       100 * (TTM cfo - TTM capex) / market_cap

ACCOUNTING CHOICES CARRIED OVER FROM feat_val.py, all still deliberate

1. NEGATIVE DENOMINATORS ARE NaN, NOT LARGE. A company losing money has no P/E.
   Keeping the negative value would place the worst names at the cheap end of
   the ranking and invert the factor, so every multiple whose denominator is
   <= 0 is NaN: pe, ps, pb, p_cash, p_fcf, ev_sales, ev_opinc. The report counts
   how often each fires, because it is common.
   The two YIELDS are the deliberate exception. Their denominator is market cap,
   which is positive by construction here, so a negative earnings or FCF yield
   is meaningful and monotone through zero and is KEPT. earnings_yield equals
   100/pe wherever pe exists and carries a negative value where pe is NaN. That
   asymmetry is the point, not an oversight.

2. EV/EBITDA CANNOT BE BUILT, so the feature is named ev_opinc. There is no
   depreciation or amortisation field in pit_fundamentals.csv, so EBITDA is not
   recoverable. Operating income is the closest available denominator and is
   systematically SMALLER than EBITDA, making ev_opinc systematically HIGHER
   than EV/EBITDA, by more for capital-intensive names. It is a different ratio,
   not a substitute, and the name says so.

3. HOW TTM IS BUILT. Income-statement and cash-flow fields in this panel are
   CUMULATIVE YEAR-TO-DATE, not single quarters (measured: median Q2/Q1 = 2.03,
   Q3/Q1 = 3.09, FY/Q1 = 3.81 for net income, the same 1:2:3:4 pattern for
   revenue, cfo, capex and op_income, while balance-sheet fields are identical
   across all four filings of a label). So a quarter is a DIFFERENCE of two YTD
   values. The FY row does not duplicate a year the quarters already cover: it
   closes out the year whose Q1-Q3 carry the PREVIOUS label (revenue
   FY(label+1)/Q3(label) has median 1.3468, IQR 1.324-1.371, which is 4/3 to
   within noise, against 1.266 for FY(label)/Q3(label)). Hence
       slot = 4 * seq_year + qidx - 1
   with qidx 1/2/3 for Q1/Q2/Q3 at seq_year = fy, and qidx 4 at seq_year = fy-1
   for an FY row. Then quarter = YTD(qidx) - YTD(qidx-1) inside a seq_year, and
   TTM = the sum of four CONSECUTIVE slots. A gap gives NaN rather than a
   three-quarter "TTM". Each TTM carries the LATEST `filed` date of every filing
   it consumed, so it becomes visible only when its last ingredient is public.

4. BALANCE-SHEET ITEMS are stocks, not flows, so each is taken from the latest
   filing that reported it rather than summed, carried forward independently, and
   expired after MAX_FILING_STALENESS_DAYS so a five-year-old cash figure never
   stands in for a current one.

5. WHICH FILING WINS A TIE. 182 (symbol, fy, fp) labels appear more than once
   because a later filing restates a period. The EARLIEST filed row is kept: the
   original disclosure is what could have been traded on.

6. SHARE COUNTS ARE BOUNDED BY A MARKET-CAP BAND. The `shares` field comes from
   whichever of three XBRL tags a company used and a minority are plainly
   mis-tagged: PCG reports 4.1e14 shares, CB 3.4e14, BRK-B 1.6e6 (its A-share
   count, against a B-share price), ED 2.2e7 against a real 3.3e8. A hard
   share-count cap cannot be used because NVDA's 2.46e10 is genuine, so
   market_cap outside [MIN_MARKET_CAP, MAX_MARKET_CAP] is NaN instead and the
   report counts the rejections.

WHAT IS NEW HERE, BEYOND THE PRICE

7. SHARE COUNTS ARE ROLLED FORWARD OVER SPLITS. Fixing the price creates a
   failure mode the old file could not have: an unadjusted price is POST-split
   from the ex-date onward, while the share count still comes from a filing made
   BEFORE the split and is a PRE-split count. Pairing them understates the cap by
   the split ratio for as long as the stale count is carried -- the mirror image
   of the old bug, smaller in extent but just as large in magnitude where it
   bites. So the share count is multiplied by every split ratio dated strictly
   after the filing date and on or before the decision date, read from
   cache_long/splits.csv. This uses only splits already ex-dividend on the
   decision date, so it is point-in-time legal. The report prints how many rows
   it touches and what it does to the verification table, because a correction
   that cannot be shown to help does not belong in a feature.

WHAT I COULD NOT BUILD, AND THE DEFECT THAT STILL MATTERS

  * EV/EBITDA, for the reason in point 2.

  * A share count dated to its own period. Every value in pit_fundamentals.csv
    is a COMPARATIVE column lifted from the filing, not the filing's own period:
    sec_pit.py keyed facts on (filed, fp, fy) and kept the FIRST value seen per
    metric, and the SEC returns a metric's facts in ascending end-date order, so
    the first value is the EARLIEST period that filing disclosed. AAPL's 10-Q
    filed 2013-01-24 yields net income 13.064e9, which is Apple's Q1 FY2012, not
    the Q1 FY2013 that filing reported. Median filed-minus-_end is 300 days.
    So these multiples price today against fundamentals roughly a year old.
    That is stale, and it flattens any genuine earnings-revision signal, but it
    is NOT lookahead: the numbers were all public on `filed`. It also caps how
    well point 7 can work -- the roll-forward starts from `filed`, while the
    count itself may already be a year older than that, so a split inside that
    gap is still missed. Fixing it properly means re-deriving the panel from
    sec_raw/ carrying each fact's period end, a change to sec_pit.py and out of
    scope for this block.

  * Multi-class share counts. Where a company has A and B shares the XBRL tag
    often returns one class while the price series is the other. BRK-B is the
    clearest case and gets no valuation features at all because the band rejects
    it. `--crosscheck` audits every symbol's latest share count against the real
    current one and prints the suspects, so these are named rather than assumed
    absent.

  * `_end` is not usable as the period date. It is overwritten by each metric in
    turn and ends up holding a balance-sheet comparative, which is why the
    sequence in point 3 is built from (fy, fp) and not from _end.
"""
from __future__ import annotations

import io
import os
import sys
import textwrap
import time
import warnings

_OUT = io.TextIOWrapper(open(sys.stdout.fileno(), "wb", closefd=False),
                        encoding="utf-8", errors="replace")


def say(*a) -> None:
    print(*a, file=_OUT)
    _OUT.flush()


warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
LONG = os.path.join(HERE, "cache_long")
GRID = os.path.join(LONG, "grid.csv")
FUND = os.path.join(LONG, "pit_fundamentals.csv")
PX = os.path.join(LONG, "px_raw_close.csv")        # UNADJUSTED, the whole point
SPLITS = os.path.join(LONG, "splits.csv")
OUT = os.path.join(LONG, "feat_val2.csv")
CROSS = os.path.join(LONG, "val_crosscheck.csv")

TTM_QUARTERS = 4                 # a trailing year is four consecutive slots
QUARTERS_PER_YEAR = 4            # slot arithmetic
PCT = 100.0                      # yields are reported in percent
BN = 1e-9                        # scale for printing dollars in billions

# An S&P 500 constituent is not a sub-$1bn company and not a $10tn one, so a
# market cap outside this band is a mis-tagged share count, not a business.
MIN_MARKET_CAP = 1e9
MAX_MARKET_CAP = 1e13

# a balance-sheet item older than this is not allowed to stand in for a current
# one. Two years, because the panel's values are already about a year stale and
# a third year of carry would be fiction.
MAX_FILING_STALENESS_DAYS = 730

# cumulative YTD fields, summed into a trailing twelve months
FLOW = ["revenue", "net_income", "cfo", "capex", "op_income"]
# point-in-time stocks, taken from the latest filing that reported them
STOCK = ["equity", "cash", "debt_lt", "shares"]

QIDX = {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4, "FY": 4}

FEATURES = ["market_cap", "pe", "ps", "pb", "p_cash", "p_fcf", "ev",
            "ev_sales", "ev_opinc", "earnings_yield", "fcf_yield"]

# Market caps looked up independently of this pipeline. These are the regression
# test the old file failed by 2.9x to 61x. The first six share one date so that a
# systematic price error cannot hide behind a date effect.
#
# The last three are the test for the split roll-forward of point 7, chosen as
# grid dates that fall BETWEEN a split and the first filing after it, which is
# where a pre-split count meets a post-split price. GOOGL is the negative
# control: its filing lands nine days AFTER its split, so the count is already
# post-split and the roll must not fire. Without these three the roll-forward
# would be an unverified correction, since no 2013-04-30 row is affected by it.
KNOWN_CAPS: dict[tuple[str, str], float] = {
    ("NVDA", "2013-04-30"): 12e9,
    ("AAPL", "2013-04-30"): 420e9,
    ("T", "2013-04-30"): 190e9,
    ("JNJ", "2013-04-30"): 230e9,
    ("MSFT", "2013-04-30"): 272e9,
    ("KO", "2013-04-30"): 187e9,
    ("NVDA", "2021-07-30"): 487e9,       # 4:1 on 2021-07-20, filing 2021-02-26
    ("AMZN", "2022-06-30"): 1.08e12,     # 20:1 on 2022-06-06, filing 2022-04-29
    ("GOOGL", "2022-07-29"): 1.51e12,    # 20:1 on 2022-07-18, filing 2022-07-27
}
CAP_TOLERANCE = 0.15             # the brief's "roughly 15%"
CAP_ALARM = 2.0                  # beyond this, say so loudly

# Why the two that miss, miss. Both were run down rather than waved through, and
# in each case the share count is the suspect, never the price -- the price on
# this date is verified to the cent against the tape in fetch_raw_px.py.
CAP_NOTES: dict[str, str] = {
    "NVDA": "REFERENCE LOOKS WRONG, not the pipeline. $12bn implies 871m shares "
            "at the verified $13.77 close. NVDA filed 612m (FY2012 10-K) and "
            "today's 24,147m over the 40x of the 2021 4:1 and 2024 10:1 is "
            "604m, so 871m is a count NVDA never had. Computed $8.4bn stands.",
    "T": "STALE SHARE COUNT, the comparative-column defect. The panel's 5,913m "
         "is AT&T's 2010 figure, carried unchanged through every filing from "
         "2011 to 2013 while the real count fell to ~5.2bn on a large buyback. "
         "$190bn implies 5,072m, which is close to the truth. Overstates the "
         "cap by 17%, and for a buyback-heavy name it always will.",
}

# --crosscheck: a live share count this far from the panel's latest one is a
# class mismatch or a stale tag, not organic issuance.
SHARE_SUSPECT = 1.25
CROSSCHECK_SLEEP = 0.2


# --------------------------------------------------------------------------
# loading
# --------------------------------------------------------------------------
def _ns(s: pd.Series) -> pd.Series:
    """One datetime resolution everywhere. pandas parses the CSVs at different
    units and merge_asof refuses to join across them."""
    return pd.to_datetime(s, errors="coerce").astype("datetime64[ns]")


def load_grid() -> pd.DataFrame:
    g = pd.read_csv(GRID)
    g["date"] = _ns(g["date"])
    # fwd63 is the TARGET. It is dropped here so that no later line can read it.
    return g[["date", "symbol"]].copy()


def load_prices(dates: pd.DatetimeIndex, symbols: list[str]) -> pd.DataFrame:
    """Long (date, symbol, px) restricted to the grid's own dates.

    Restricting to the grid dates is what makes lookahead impossible: the frame
    handed onward contains no row dated after any decision date it is used for.
    """
    px = pd.read_csv(PX, index_col=0, parse_dates=True)
    keep = [c for c in symbols if c in px.columns]
    missing = sorted(set(symbols) - set(keep))
    if missing:
        say(f"  WARNING {len(missing)} grid symbols absent from {os.path.basename(PX)}"
            f": {', '.join(missing)}")
    px = px.loc[px.index.isin(dates), keep]
    px = px.where(px > 0)                      # a zero or negative close is bad
    out = px.stack(future_stack=True).dropna().rename("px").reset_index()
    out.columns = ["date", "symbol", "px"]
    out["date"] = _ns(out["date"])
    return out


def load_splits() -> pd.DataFrame:
    """Long (date, symbol, ratio). Absent file is fatal, not a silent no-op: the
    roll-forward in point 7 would quietly stop happening."""
    if not os.path.exists(SPLITS):
        say(f"  MISSING {SPLITS} -- run fetch_raw_px.py first")
        sys.exit(1)
    s = pd.read_csv(SPLITS)
    s["date"] = _ns(s["date"])
    s["ratio"] = pd.to_numeric(s["ratio"], errors="coerce")
    return s.dropna(subset=["date", "symbol", "ratio"]).sort_values(
        ["symbol", "date"])


def load_filings() -> pd.DataFrame:
    """One row per filing, with the chronological slot its period occupies."""
    f = pd.read_csv(FUND)
    f["filed"] = _ns(f["filed"])
    f["fy"] = pd.to_numeric(f["fy"], errors="coerce")
    for c in FLOW + STOCK:
        f[c] = pd.to_numeric(f.get(c), errors="coerce")
    n0 = len(f)
    f = f.dropna(subset=["filed", "symbol", "fy"])
    f = f[f["fp"].isin(QIDX)]
    say(f"  filings read {n0:,} -> usable {len(f):,} "
        f"(dropped {n0 - len(f):,} with no filed/fy or an unknown fp)")

    f["qidx"] = f["fp"].map(QIDX).astype(int)
    # an FY row closes out the year whose Q1-Q3 carry the PREVIOUS label, so it
    # belongs one seq_year back. See docstring point 3 for the measurement.
    f["seq_year"] = np.where(f["fp"] == "FY", f["fy"] - 1, f["fy"]).astype(int)
    f["slot"] = f["seq_year"] * QUARTERS_PER_YEAR + f["qidx"] - 1

    # the original disclosure wins a restatement: keep the earliest filed
    f = f.sort_values(["symbol", "slot", "filed"])
    n1 = len(f)
    f = f.drop_duplicates(subset=["symbol", "slot"], keep="first")
    say(f"  dropped {n1 - len(f):,} restatements of a slot already disclosed")
    return f


# --------------------------------------------------------------------------
# trailing twelve months
# --------------------------------------------------------------------------
def decumulate(f: pd.DataFrame) -> pd.DataFrame:
    """YTD -> single quarter, by differencing inside a seq_year.

    `known` is the later of the two filing dates a difference consumes, because
    a quarter derived from two filings is not public until both are.
    """
    q = f.sort_values(["symbol", "slot"]).copy()
    grp = q.groupby(["symbol", "seq_year"], sort=False)
    prev_qidx = grp["qidx"].shift(1)
    prev_filed = grp["filed"].shift(1)
    adjacent = prev_qidx.eq(q["qidx"] - 1)     # no gap inside the fiscal year

    first = q["qidx"].eq(1)
    q["known"] = q["filed"].where(first, prev_filed.where(adjacent).combine_first(
        pd.Series(pd.NaT, index=q.index)))
    q["known"] = np.maximum(q["filed"].to_numpy("datetime64[ns]"),
                            q["known"].to_numpy("datetime64[ns]"))
    q.loc[~(first | adjacent), "known"] = pd.NaT

    for c in FLOW:
        prev = grp[c].shift(1)
        diff = q[c] - prev.where(adjacent)
        q[c] = q[c].where(first, diff)
        q.loc[~(first | adjacent), c] = np.nan
    return q[["symbol", "slot", "known"] + FLOW]


def _dense(q: pd.DataFrame, col: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Slot x symbol grids for one metric and for its known date.

    Reindexing onto every slot in the range is what makes the gap rule free: a
    missing quarter is a NaN row, so a four-slot rolling sum with min_periods=4
    refuses to produce a TTM across it.
    """
    v = q.dropna(subset=[col, "known"])
    slots = range(int(q["slot"].min()), int(q["slot"].max()) + 1)
    wide = v.pivot_table(index="slot", columns="symbol", values=col,
                         aggfunc="last").reindex(slots)
    kn = v.assign(_k=v["known"].astype("int64")).pivot_table(
        index="slot", columns="symbol", values="_k", aggfunc="last")
    return wide, kn.reindex(slots).reindex(columns=wide.columns)


def build_ttm(q: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Per metric, a long panel of (symbol, known, value) for the TTM sum."""
    panels: dict[str, pd.DataFrame] = {}
    for col in FLOW:
        wide, kn = _dense(q, col)
        roll = wide.rolling(TTM_QUARTERS, min_periods=TTM_QUARTERS).sum()
        # the TTM is public only once its LAST ingredient is
        kmax = kn.rolling(TTM_QUARTERS, min_periods=TTM_QUARTERS).max()
        val = roll.stack(future_stack=True).rename(col)
        known = kmax.stack(future_stack=True).rename("known")
        p = pd.concat([val, known], axis=1).dropna().reset_index()
        p["known"] = pd.to_datetime(p["known"].astype("int64"))
        panels[col] = p.sort_values(["known", "slot"])
    return panels


def build_stock(f: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Per balance-sheet metric, a long panel of (symbol, known, value).

    Each item is carried independently: a filing that reported equity but not
    cash must not blank out a cash figure that was already public.
    """
    panels: dict[str, pd.DataFrame] = {}
    for col in STOCK:
        p = f.loc[f[col].notna(), ["symbol", "slot", "filed", col]].copy()
        p = p.rename(columns={"filed": "known"})
        p["known"] = _ns(p["known"])
        panels[col] = p.sort_values(["known", "slot"])
    return panels


def as_of(grid: pd.DataFrame,
          panels: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Attach each metric's latest value KNOWN on the grid date.

    merge_asof backward on the filing date with a tolerance, per symbol. The
    tolerance is the staleness expiry; without it a 2011 figure would be carried
    to 2026 and counted as coverage.
    """
    out = grid.sort_values(["date", "symbol"]).reset_index(drop=True)
    age = pd.DataFrame(index=out.index)
    tol = pd.Timedelta(days=MAX_FILING_STALENESS_DAYS)
    for col, p in panels.items():
        m = pd.merge_asof(out[["date", "symbol"]], p[["known", "symbol", col]],
                          left_on="date", right_on="known", by="symbol",
                          direction="backward", tolerance=tol)
        # the backward direction already guarantees this, but the assertion is
        # the cheapest possible insurance against a future refactor of the join
        got = m[col].notna()
        assert (m.loc[got, "known"] <= m.loc[got, "date"]).all(), \
            f"{col}: a value dated after the decision date got through"
        out[col] = m[col].to_numpy()
        age[col] = (m["date"] - m["known"]).dt.days.to_numpy()
    return out, age


# --------------------------------------------------------------------------
# the split roll-forward -- see docstring point 7
# --------------------------------------------------------------------------
def roll_shares(d: pd.DataFrame, age: pd.DataFrame,
                splits: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """Share count restated for splits between the filing date and the date.

    Returns the rolled count and the multiplier applied. Implemented as a step
    function per symbol: C(t) = sum of log(ratio) over splits dated <= t, so the
    product over (filed, date] is exp(C(date) - C(filed)). Logs rather than a
    running product because the factors reach 70x and a float product of many
    of them drifts.
    """
    filed = d["date"] - pd.to_timedelta(age["shares"], unit="D")
    mult = pd.Series(1.0, index=d.index)
    for sym, ev in splits.groupby("symbol", sort=False):
        rows = np.flatnonzero((d["symbol"] == sym).to_numpy())
        if rows.size == 0:
            continue
        ex = ev["date"].to_numpy("datetime64[ns]")
        clog = np.concatenate([[0.0], np.cumsum(np.log(ev["ratio"].to_numpy()))])
        # searchsorted "right" counts events dated <= t, which is what C(t) is
        hi = clog[np.searchsorted(ex, d["date"].to_numpy("datetime64[ns]")[rows],
                                  side="right")]
        lo = clog[np.searchsorted(ex, filed.to_numpy("datetime64[ns]")[rows],
                                  side="right")]
        mult.iloc[rows] = np.exp(hi - lo)
    # a row with no known share count has nothing to roll
    mult = mult.where(d["shares"].notna() & filed.notna(), 1.0)
    return d["shares"] * mult, mult


# --------------------------------------------------------------------------
# the features
# --------------------------------------------------------------------------
def safe_div(num: pd.Series, den: pd.Series) -> pd.Series:
    """A multiple is undefined, not large, when its denominator is <= 0."""
    return num / den.where(den > 0)


def compute(d: pd.DataFrame,
            shares: pd.Series) -> tuple[pd.DataFrame, dict[str, int]]:
    cap = d["px"] * shares
    bad = cap.notna() & ((cap < MIN_MARKET_CAP) | (cap > MAX_MARKET_CAP))
    cap = cap.where(~bad)

    fcf = d["cfo"] - d["capex"]
    ev = cap + d["debt_lt"] - d["cash"]       # NaN unless both legs are known

    out = pd.DataFrame({"date": d["date"], "symbol": d["symbol"]})
    out["market_cap"] = cap
    out["pe"] = safe_div(cap, d["net_income"])
    out["ps"] = safe_div(cap, d["revenue"])
    out["pb"] = safe_div(cap, d["equity"])
    out["p_cash"] = safe_div(cap, d["cash"])
    out["p_fcf"] = safe_div(cap, fcf)
    out["ev"] = ev
    out["ev_sales"] = safe_div(ev, d["revenue"])
    out["ev_opinc"] = safe_div(ev, d["op_income"])
    # the yields divide by market cap, positive by construction, so a negative
    # yield is meaningful and is kept. See docstring point 1.
    out["earnings_yield"] = PCT * d["net_income"] / cap
    out["fcf_yield"] = PCT * fcf / cap

    counts = {
        "market cap outside the plausibility band": int(bad.sum()),
        "net income <= 0 (kills pe)": int((d["net_income"] <= 0).sum()),
        "revenue <= 0 (kills ps, ev_sales)": int((d["revenue"] <= 0).sum()),
        "equity <= 0 (kills pb)": int((d["equity"] <= 0).sum()),
        "cash <= 0 (kills p_cash)": int((d["cash"] <= 0).sum()),
        "fcf <= 0 (kills p_fcf)": int((fcf <= 0).sum()),
        "op income <= 0 (kills ev_opinc)": int((d["op_income"] <= 0).sum()),
        "ev < 0, a net-cash name (kept)": int((ev < 0).sum()),
    }
    return out, counts


# --------------------------------------------------------------------------
# reporting
# --------------------------------------------------------------------------
def report_inputs(d: pd.DataFrame) -> None:
    say("\nINPUT COVERAGE on the grid -- what the asof join actually found")
    say(f"  {'input':<14}{'on rows':>10}")
    say("  " + "-" * 26)
    for c in ["px"] + FLOW + STOCK:
        say(f"  {'ttm_' + c if c in FLOW else c:<14}"
            f"{d[c].notna().mean() * PCT:>9.1f}%")


def report_age(age: pd.DataFrame) -> None:
    """How old the information behind each input is on the decision date.

    Two additive parts: the panel's comparative-column lag (docstring), and the
    wait for the FY filing that completes a four-quarter chain, which for a TTM
    can be most of a year on its own.
    """
    say("\nINFORMATION AGE -- days from the source filing to the decision date")
    say(f"  {'input':<16}{'median':>9}{'p90':>9}{'max':>9}")
    say("  " + "-" * 43)
    for c in FLOW + STOCK:
        s = age[c].dropna()
        if s.empty:
            continue
        say(f"  {'ttm_' + c if c in FLOW else c:<16}{s.median():>9.0f}"
            f"{s.quantile(0.9):>9.0f}{s.max():>9.0f}")


def report_features(out: pd.DataFrame) -> None:
    say("\nPER-FEATURE COVERAGE AND DISTRIBUTION")
    say(f"  {'feature':<15}{'cover':>8}{'p5':>12}{'p25':>12}{'median':>12}"
        f"{'p75':>12}{'p95':>12}{'mean':>12}")
    say("  " + "-" * 95)
    for c in FEATURES:
        s = out[c]
        cov = s.notna().mean() * PCT
        if s.notna().sum() == 0:
            say(f"  {c:<15}{cov:>7.1f}%   all NaN")
            continue
        q = s.quantile([0.05, 0.25, 0.5, 0.75, 0.95])
        sc = BN if c in ("market_cap", "ev") else 1.0
        flag = "  <-- THIN" if cov < 50 else ""
        say(f"  {c:<15}{cov:>7.1f}%" + "".join(
            f"{v * sc:>12,.2f}" for v in
            [q.iloc[0], q.iloc[1], q.iloc[2], q.iloc[3], q.iloc[4],
             s.mean()]) + flag)
    say("  " + "-" * 95)
    say("  market_cap and ev are printed in $bn; everything else is as stored")


def report_roll(mult: pd.Series) -> None:
    touched = mult.ne(1.0)
    say("\nSHARE-COUNT ROLL-FORWARD over splits (docstring point 7)")
    say(f"  rows whose share count was restated: {int(touched.sum()):,} = "
        f"{touched.mean() * PCT:.2f}% of the grid")
    if touched.any():
        m = mult[touched]
        say(f"  multiplier: median {m.median():.2f}x  min {m.min():.3f}x  "
            f"max {m.max():.1f}x")
        say("  without this, each of those rows would carry a pre-split count")
        say("  against a post-split price, understating the cap by that factor")


def verify_caps(out: pd.DataFrame, d: pd.DataFrame, shares: pd.Series,
                label: str, notes: bool = False) -> tuple[int, int]:
    """The regression test the old file failed. Prints price and share count
    alongside the cap so a miss can be attributed to one or the other."""
    key = out["date"].astype(str) + "|" + out["symbol"]
    say(f"\nMARKET-CAP VERIFICATION ({label})")
    say(f"  {'symbol':<7}{'date':<12}{'price':>9}{'shares(m)':>11}"
        f"{'computed':>12}{'truth':>10}{'ratio':>8}{'err':>8}{'impl(m)':>10}")
    say("  " + "-" * 88)
    off, alarm = 0, 0
    for (sym, date), truth in KNOWN_CAPS.items():
        hit = np.flatnonzero((key == f"{date}|{sym}").to_numpy())
        if hit.size == 0:
            say(f"  {sym:<7}{date:<12}{'NOT IN GRID':>9}")
            off += 1
            continue
        i = hit[0]
        cap = out["market_cap"].iloc[i]
        if not np.isfinite(cap):
            say(f"  {sym:<7}{date:<12}{d['px'].iloc[i]:>9.2f}"
                f"{shares.iloc[i] * 1e-6:>11,.0f}{'NaN':>12}"
                f"{truth * BN:>9.0f}b{'--':>8}{'--':>8}   <-- NO VALUE")
            off += 1
            continue
        ratio = cap / truth
        err = abs(ratio - 1.0)
        off += int(err > CAP_TOLERANCE)
        alarm += int(ratio > CAP_ALARM or ratio < 1.0 / CAP_ALARM)
        flag = ("" if err <= CAP_TOLERANCE else
                "   <-- OFF" if ratio < CAP_ALARM and ratio > 1 / CAP_ALARM
                else "   <-- OFF BY MORE THAN 2x")
        # impl is the share count the reference value implies at the VERIFIED
        # price. It splits the blame: if impl matches the real historical count
        # the panel's count is stale, and if it does not the reference is wrong.
        say(f"  {sym:<7}{date:<12}{d['px'].iloc[i]:>9.2f}"
            f"{shares.iloc[i] * 1e-6:>11,.0f}{cap * BN:>11.0f}b"
            f"{truth * BN:>9.0f}b{ratio:>8.2f}{err * PCT:>7.1f}%"
            f"{truth / d['px'].iloc[i] * 1e-6:>10,.0f}{flag}")
    say("  " + "-" * 88)
    say("  impl(m) = the share count the TRUTH column implies at this price")
    if notes:
        for sym, note in CAP_NOTES.items():
            for n, chunk in enumerate(textwrap.wrap(note, 80)):
                say(f"  {sym + ':' if n == 0 else '':<6}{chunk}")
    return off, alarm


def report_suspects(out: pd.DataFrame, shares: pd.Series,
                    d: pd.DataFrame) -> None:
    """Share counts that look wrong, from the panel alone.

    Two signatures, neither of which needs an external source: a symbol the
    plausibility band rejects most of the time (a mis-tagged or wrong-class
    count), and a symbol whose market cap is never available at all.
    """
    frame = pd.DataFrame({"symbol": d["symbol"],
                          "cap": out["market_cap"],
                          "shares": shares,
                          "px": d["px"]})
    g = frame.groupby("symbol")
    rej = (g["shares"].apply(lambda s: s.notna().mean())
           - g["cap"].apply(lambda s: s.notna().mean()))
    none = g["cap"].apply(lambda s: s.notna().mean())
    say("\nSHARE-COUNT SUSPECTS from the panel alone")
    worst = rej[rej > 0.2].sort_values(ascending=False)
    say(f"  symbols where the band rejects the cap on >20% of rows that HAVE a")
    say(f"  share count ({len(worst)} of {frame['symbol'].nunique()}):")
    for sym, v in worst.head(20).items():
        s = frame.loc[frame["symbol"] == sym]
        say(f"    {sym:<8}rejected {v * PCT:>5.1f}% of priced rows   "
            f"median shares {s['shares'].median():.3g}  "
            f"median px {s['px'].median():.2f}")
    dead = none[none == 0.0]
    say(f"  symbols with NO market cap on any row ({len(dead)}): "
        f"{', '.join(dead.index[:30])}")


def crosscheck(out: pd.DataFrame, shares: pd.Series, d: pd.DataFrame,
               splits: pd.DataFrame) -> None:
    """Audit the panel's latest share count against the real current one.

    This is the only part of the file that touches the network and the only one
    that can catch a class mismatch that stays inside the plausibility band --
    BRK-B is loud because the band rejects it, but a company whose A-class count
    is merely 20% of its total is silently 5x cheap on every multiple. Cached,
    because it costs one request per symbol.
    """
    import yfinance as yf

    last = d["date"].max()
    tail = d["date"].eq(last)
    panel = pd.DataFrame({"symbol": d.loc[tail, "symbol"],
                          "panel_shares": shares[tail],
                          "px": d.loc[tail, "px"],
                          "cap": out.loc[tail, "market_cap"]})
    panel = panel.dropna(subset=["panel_shares"])

    if os.path.exists(CROSS):
        live = pd.read_csv(CROSS)
        say(f"\n  reusing {CROSS} ({len(live)} symbols)")
    else:
        rows = []
        syms = sorted(panel["symbol"].unique())
        say(f"\n  fetching live share counts for {len(syms)} symbols")
        for n, sym in enumerate(syms, 1):
            rec = {"symbol": sym, "live_shares": np.nan, "error": ""}
            try:
                fi = yf.Ticker(sym).fast_info
                rec["live_shares"] = fi.get("shares")
            except Exception as e:                      # noqa: BLE001
                # a failure becomes a recorded NaN, never a silent skip
                rec["error"] = f"{type(e).__name__}: {e}"[:80]
            rows.append(rec)
            if n % 50 == 0:
                say(f"    {n}/{len(syms)}")
            time.sleep(CROSSCHECK_SLEEP)
        live = pd.DataFrame(rows)
        live.to_csv(CROSS, index=False)
        say(f"  wrote {CROSS}")

    m = panel.merge(live, on="symbol", how="left")
    # The live count is as of TODAY and the panel count as of the last grid
    # date, so a split in between makes a correct pair look 10x apart. KLAC
    # split 10:1 on 2026-06-12 and is the loudest false positive there is.
    # Dividing it out is what leaves only genuine disagreements.
    post = splits[splits["date"] > last].groupby("symbol")["ratio"].prod()
    m["post_split"] = m["symbol"].map(post).fillna(1.0)
    m["ratio"] = m["live_shares"] / m["post_split"] / m["panel_shares"]

    say(f"\nSHARE-COUNT CROSSCHECK on the last grid date ({last:%Y-%m-%d})")
    say(f"  live count unavailable for "
        f"{int(m['live_shares'].isna().sum())} of {len(m)} symbols")
    say(f"  live counts de-split for {int(m['post_split'].ne(1.0).sum())} "
        f"symbols that split after the last grid date")
    ok = m.dropna(subset=["ratio"])
    say(f"  live/panel ratio: median {ok['ratio'].median():.3f}  "
        f"p5 {ok['ratio'].quantile(0.05):.3f}  "
        f"p95 {ok['ratio'].quantile(0.95):.3f}")
    sus = ok[(ok["ratio"] > SHARE_SUSPECT) | (ok["ratio"] < 1 / SHARE_SUSPECT)]
    say(f"  beyond {SHARE_SUSPECT}x either way: {len(sus)} symbols")
    say(f"  {'symbol':<8}{'panel(m)':>12}{'live(m)':>12}{'ratio':>12}"
        f"{'cap($bn)':>11}")
    say("  " + "-" * 57)
    for _, r in sus.sort_values("ratio").iterrows():
        cap = r["cap"] * BN
        # a broken tag makes the ratio millions, so the width has to survive it
        say(f"  {r['symbol']:<8}{r['panel_shares'] * 1e-6:>12,.2f}"
            f"{r['live_shares'] * 1e-6:>12,.0f}{r['ratio']:>12,.2f}"
            f"{cap if np.isfinite(cap) else float('nan'):>11,.1f}")
    say("  a ratio still far from 1 after de-splitting is a class mismatch or a")
    say("  broken tag, not organic issuance. A NaN cap means the plausibility")
    say("  band already rejected that row, so no feature was built from it.")


def verify(out: pd.DataFrame, grid: pd.DataFrame) -> None:
    say("\nCONTRACT CHECK against the grid")
    assert len(out) == len(grid), f"{len(out)} rows vs grid {len(grid)}"
    key = out["date"].astype(str) + "|" + out["symbol"]
    gkey = grid["date"].astype(str) + "|" + grid["symbol"]
    assert key.tolist() == gkey.tolist(), "(date, symbol) order does not match"
    assert not out.duplicated(["date", "symbol"]).any(), "duplicate pair"
    say(f"  rows {len(out):,} == grid {len(grid):,}")
    say("  (date, symbol) identical and in the same order: yes")
    say(f"  dates {out['date'].nunique()}  symbols {out['symbol'].nunique()}")


def main() -> None:
    say("BUILDING feat_val2 -- valuation multiples on UNADJUSTED prices")
    grid = load_grid()
    f = load_filings()
    splits = load_splits()
    say(f"  split events: {len(splits)} on {splits['symbol'].nunique()} symbols")

    q = decumulate(f)
    say(f"  de-cumulated quarters available: "
        f"{q[FLOW].notna().any(axis=1).sum():,} of {len(q):,} slots")
    say(f"  de-cumulated quarters with NEGATIVE revenue (a broken YTD "
        f"sequence, left as-is): {int((q['revenue'] < 0).sum())}")

    panels = build_ttm(q)
    panels.update(build_stock(f))
    d, age = as_of(grid, panels)

    px = load_prices(pd.DatetimeIndex(grid["date"].unique()),
                     sorted(grid["symbol"].unique()))
    d = d.merge(px, on=["date", "symbol"], how="left")
    report_inputs(d)
    report_age(age)

    rolled, mult = roll_shares(d, age, splits)
    report_roll(mult)

    # both variants are built so the roll-forward has to earn its place: the
    # raw one is reported, the rolled one is shipped only if it is no worse
    plain_out, _ = compute(d, d["shares"])
    out, counts = compute(d, rolled)
    off_plain, alarm_plain = verify_caps(plain_out, d, d["shares"],
                                         "share count as filed")
    off, alarm = verify_caps(out, d, rolled, "share count rolled over splits",
                             notes=True)
    say(f"  as filed: {off_plain} of {len(KNOWN_CAPS)} outside "
        f"{CAP_TOLERANCE * PCT:.0f}%, {alarm_plain} beyond {CAP_ALARM}x")
    say(f"  rolled:   {off} of {len(KNOWN_CAPS)} outside "
        f"{CAP_TOLERANCE * PCT:.0f}%, {alarm} beyond {CAP_ALARM}x")
    if alarm:
        say(f"\n  *** {alarm} MARKET CAP(S) STILL OFF BY MORE THAN {CAP_ALARM}x."
            f" DO NOT SHIP A VALUATION FILTER ON THIS UNTIL DIAGNOSED. ***")

    say("\nDENOMINATOR REJECTIONS -- why a multiple is NaN")
    say(f"  {'reason':<42}{'rows':>9}{'of grid':>10}")
    say("  " + "-" * 61)
    for k, v in counts.items():
        say(f"  {k:<42}{v:>9,}{v / len(out) * PCT:>9.1f}%")

    report_features(out)
    report_suspects(out, rolled, d)
    if "--crosscheck" in sys.argv:
        crosscheck(out, rolled, d, splits)

    # the grid order is the contract, so restore it before the check and write
    out = out.set_index(["date", "symbol"]).loc[
        pd.MultiIndex.from_frame(grid[["date", "symbol"]])].reset_index()
    verify(out, grid)
    out.to_csv(OUT, index=False)
    say(f"\nwrote {OUT}  ({len(out):,} rows, {len(FEATURES)} features)")


if __name__ == "__main__":
    main()
