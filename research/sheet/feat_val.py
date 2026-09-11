"""Point-in-time valuation multiples, one row per (date, symbol) in the grid.

    python research/sheet/feat_val.py            # build, report, write the CSV

WHAT THIS BLOCK IS
Eleven valuation features. Each needs two things joined at the decision date:
the price on that date, and the most recent SEC filing whose `filed` date is on
or before it. Nothing here reads a price after the date or a filing the market
had not seen.

  market_cap      close on the date * most recently filed share count
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

ACCOUNTING CHOICES, all of them deliberate

1. NEGATIVE DENOMINATORS ARE NaN, NOT LARGE. A company losing money has no
   P/E. Keeping the negative value would place the worst names at the cheap end
   of the ranking and invert the whole factor, so every multiple whose
   denominator is <= 0 is set to NaN: pe, ps, pb, p_cash, p_fcf, ev_sales,
   ev_opinc. The report counts how often each one fires, because it is common.
   The two YIELDS are the deliberate exception. Their denominator is market
   cap, which is always positive here, so a negative earnings or FCF yield is
   both meaningful and monotone through zero and is KEPT. earnings_yield
   therefore equals 100/pe wherever pe exists and carries a negative value
   where pe is NaN. That asymmetry is the point, not an oversight.

2. EV/EBITDA CANNOT BE BUILT. There is no depreciation or amortisation field in
   pit_fundamentals.csv, so EBITDA is not recoverable. Operating income is the
   closest available denominator and the feature is named ev_opinc so that
   nobody later reads it as EBITDA. It is systematically SMALLER than EBITDA,
   so ev_opinc is systematically HIGHER than EV/EBITDA, by more for capital
   intensive names. It is not a substitute, it is a different ratio.

3. HOW TTM IS BUILT. Income-statement and cash-flow fields in this panel are
   CUMULATIVE YEAR-TO-DATE, not single quarters. Measured on the data:
   median Q2/Q1 = 2.03, Q3/Q1 = 3.09, FY/Q1 = 3.81 for net income, and the same
   1:2:3:4 pattern for revenue, cfo, capex, op_income and gross profit, while
   balance-sheet fields are identical across all four filings of a label
   (ratio exactly 1.00). So a single quarter is a DIFFERENCE of two YTD values.
   The FY row does not duplicate a year already covered by the quarters: it
   closes out the year whose Q1-Q3 carry the PREVIOUS label. Revenue
   FY(label+1)/Q3(label) has median 1.3468 with an interquartile range of
   1.324-1.371, which is 4/3 to within noise, while FY(label)/Q3(label) is
   1.266 with a range of 1.184-1.342, a year-over-year growth mismatch. So the
   chronological sequence of cumulative periods is
       Q1(label Y), Q2(label Y), Q3(label Y), FY(label Y+1)
   and the rule used here is: slot = 4*seq_year + qidx - 1, with qidx 1/2/3 for
   Q1/Q2/Q3 and seq_year = fy, and qidx 4 with seq_year = fy-1 for an FY row
   (fy for the 32 rare fp="Q4" rows, which land on the same slot as the FY row
   that follows them and are de-duplicated against it).
   Then: quarter = YTD(qidx) - YTD(qidx-1) inside a seq_year, with qidx 1 taken
   as-is, and TTM = the sum of four CONSECUTIVE slots. A gap in the slot
   sequence gives NaN rather than a three-quarter "TTM". Each TTM carries the
   LATEST `filed` date of every filing it consumed, so a TTM only becomes
   visible on the date its last ingredient became public.

4. BALANCE-SHEET ITEMS are stocks, not flows, so they are taken from the latest
   filing that reported them rather than summed. Each one is carried forward
   independently and expires after MAX_FILING_STALENESS_DAYS, so a five year
   old cash figure never silently stands in for a current one.

5. WHICH FILING WINS A TIE. 182 (symbol, fy, fp) labels appear more than once,
   because a later filing restates a period. The EARLIEST filed row is kept:
   the original disclosure is what could have been traded on.

6. SHARE COUNTS ARE BOUNDED BY A MARKET-CAP BAND. The `shares` field comes from
   whichever of three XBRL tags a company used and a minority are plainly
   mis-tagged: PCG reports 4.1e14 shares, CB 3.4e14, BRK-B 1.5e12 and elsewhere
   1.6e6 (its A-share count, against a B-share price), ED 2.2e7 against a real
   3.3e8, while MCD, SYK and GRMN have rows under a million. A hard share-count
   cap cannot be used because NVDA's 2.46e10 is genuine. Instead market_cap
   outside [MIN_MARKET_CAP, MAX_MARKET_CAP] is NaN. The report counts the
   rejections. BRK-B never gets a usable share count in this panel and so has no
   valuation features at all.

WHAT I COULD NOT BUILD, AND THE TWO DEFECTS THAT MATTER MORE THAN THE FEATURES

  * EV/EBITDA, for the reason in point 2.

  * A TRUE market cap, because px_close.csv is TOTAL-RETURN ADJUSTED and the
    share counts are as-reported. Checked against known closes: 2024-12-31
    shows AAPL 248.62 against an actual 250.42, KO 59.68 against 62.26, XOM
    101.72 against 107.59, NVDA 134.09 against 134.29 -- each discounted by
    about one year of its own dividend yield, and NVDA 2015-12-31 at 0.80
    against an actual ~33 is the 40:1 of its two later splits. So
    close * shares is the true market cap divided by the cumulative
    split-and-dividend factor from that date to the end of the file. Worse,
    that factor is FUTURE information: it is built from splits and dividends
    that had not happened yet on the date. The distortion is a smooth per
    symbol drift for dividend payers, converging to 1.0 at the end of the
    sample, and a discrete multi-fold error for any date before a split. It
    cannot be removed with the files available, because recovering a raw price
    needs a dividend and split history this project does not have, and because
    the conversion is needed in the one direction that only the future supplies:
    putting an end-anchored adjusted price and an as-reported share count into
    the same units requires the splits BETWEEN the date and the end of the file.
    The clearest single instance: px_close shows KLAC at 62.25 on 2024-12-31
    against an actual close of 629.70, a 10x error caused by a split that
    happened AFTER 2024 and therefore could not have been known.

    THE DIRECTION OF THIS LEAK IS THE PROBLEM. A stock that splits later has its
    market cap understated by the split factor, and stocks split after they go
    up. So pre-split rows carry an artificially cheap multiple and those names
    subsequently outperformed. Left unexamined this manufactures a value factor
    out of corporate actions. Nobody should run a value backtest on this block
    until the price input is a raw or split-only-adjusted series, or a dividend
    and split history exists to rebuild one. The report quantifies how much of
    the matrix sits before a detected split. Pure return features are unaffected
    -- the factor cancels in a ratio of two adjusted prices -- so this is a
    defect of valuation features specifically.

  * Current fundamentals. Every value in pit_fundamentals.csv is a COMPARATIVE
    column lifted from the filing, not the filing's own period. sec_pit.py
    keyed facts on (filed, fp, fy) and kept the first value seen per metric,
    and the SEC returns a metric's facts in ascending end-date order, so the
    first value is the EARLIEST period that filing disclosed. AAPL's 10-Q filed
    2013-01-24 yields net income 13.064e9, which is Apple's Q1 FY2012, not the
    Q1 FY2013 that filing reported. Median filed-minus-_end is 300 days. The
    information-age table in the report adds it up: the filing itself is a median
    183 days old on the decision date, and the value inside it is another year
    older, so a TTM here describes a twelve-month period ending about 18 months
    before the date it is used on. That is stale enough that no
    earnings-revision signal survives in it, but it is NOT lookahead: every
    number was public on `filed`. Fixing it means
    re-deriving the panel from sec_raw/ with the period end carried per fact,
    which is a change to sec_pit.py and out of scope for this block.

  * `_end` is not usable as the period date. It is overwritten by each metric in
    turn and ends up holding a balance-sheet comparative, which is why the
    sequence above is built from (fy, fp) and not from _end.
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
GRID = os.path.join(LONG, "grid.csv")
FUND = os.path.join(LONG, "pit_fundamentals.csv")
PX = os.path.join(LONG, "px_close.csv")
OUT = os.path.join(LONG, "feat_val.csv")

TTM_QUARTERS = 4                 # a trailing year is four consecutive slots
QUARTERS_PER_YEAR = 4            # slot arithmetic
PCT = 100.0                      # yields are reported in percent
DAYS_PER_YEAR = 365              # reporting only, for the information-age sum

# An S&P 500 constituent is not a sub-$1bn company and not a $10tn one, so a
# market cap outside this band is a mis-tagged share count or a price wrecked by
# a later split, not a business. The floor is set at a billion rather than lower
# because every symbol it rejects is verifiably a large cap: BRK-B (the share
# tag returns 1.6m A shares against a B-share price), ED (22m against a real
# 330m), CMG, NVDA, ORLY, LRCX (prices divided by a 15:1 to 50:1 later split).
MIN_MARKET_CAP = 1e9
MAX_MARKET_CAP = 1e13

# a balance-sheet item older than this is not allowed to stand in for a current
# one. Two years, because the panel's values are already about a year stale and
# a third year of carry would be fiction.
MAX_FILING_STALENESS_DAYS = 730

# DIAGNOSTIC ONLY, never used in a feature value: a share count jumping by more
# than SPLIT_JUMP between consecutive filings is the signature of a stock split.
# The upper bound excludes the mis-tagged rows (BRK-B jumps by 1e6) from the
# size estimate; the largest genuine split in this universe is CMG's 50:1.
SPLIT_JUMP = 1.4
MAX_SPLIT_JUMP = 60.0

# cumulative YTD fields, summed into a trailing twelve months
FLOW = ["revenue", "net_income", "cfo", "capex", "op_income"]
# point-in-time stocks, taken from the latest filing that reported them
STOCK = ["equity", "cash", "debt_lt", "shares"]

QIDX = {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4, "FY": 4}

FEATURES = ["market_cap", "pe", "ps", "pb", "p_cash", "p_fcf", "ev",
            "ev_sales", "ev_opinc", "earnings_yield", "fcf_yield"]


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
    # fwd63 is the target. It is dropped here so that no later line can read it.
    return g[["date", "symbol"]].copy()


def load_prices(dates: pd.DatetimeIndex, symbols: list[str]) -> pd.DataFrame:
    """Long (date, symbol, px) restricted to the grid's own dates.

    Restricting to the grid dates is what makes lookahead impossible: the frame
    handed onward contains no row dated after any decision date it is used for.
    """
    px = pd.read_csv(PX, index_col=0, parse_dates=True)
    keep = [c for c in symbols if c in px.columns]
    px = px.loc[px.index.isin(dates), keep]
    px = px.where(px > 0)           # a zero or negative close is bad data
    out = px.stack().rename("px").reset_index()
    out.columns = ["date", "symbol", "px"]
    out["date"] = _ns(out["date"])
    return out


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
    q["known"] = np.maximum(q["filed"].to_numpy("datetime64[ns]"),
                            prev_filed.where(adjacent)
                            .to_numpy("datetime64[ns]"))
    q.loc[first, "known"] = q.loc[first, "filed"]
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
        val = roll.stack().rename(col)
        known = kmax.stack().rename("known")
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
    tolerance is the staleness expiry; without it a 2011 figure would be
    carried to 2026 and counted as coverage.
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
# the features
# --------------------------------------------------------------------------
def safe_div(num: pd.Series, den: pd.Series) -> pd.Series:
    """A multiple is undefined, not large, when its denominator is <= 0."""
    return num / den.where(den > 0)


def compute(d: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    cap = d["px"] * d["shares"]
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
    # the yields divide by market cap, which is positive by construction, so a
    # negative yield is meaningful and is kept. See docstring point 1.
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

    This is the number that decides whether these features are worth anything.
    It has two additive parts: the panel's comparative-column lag (see the
    docstring), and the wait for the FY filing that completes a four-quarter
    chain, which for a TTM can be most of a year on its own.
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
    say("  the cap at 730 is MAX_FILING_STALENESS_DAYS doing its job")
    flows = age[FLOW].stack().median()
    say("  ADD ~365 DAYS TO THE FLOW ROWS. The age above is")
    say("  filing-to-date, and the value inside a filing is the same")
    say("  quarter ONE YEAR earlier, so a TTM here describes a year")
    say(f"  ending ~{flows + DAYS_PER_YEAR:.0f} days before the decision date.")
    say(f"  Only {flows:.0f} days of that is reporting delay. These are slow")
    say("  features and no earnings-revision signal survives in them.")


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
        sc = 1e-9 if c in ("market_cap", "ev") else 1.0
        flag = "  <-- THIN" if cov < 50 else ""
        say(f"  {c:<15}{cov:>7.1f}%" + "".join(
            f"{v * sc:>12,.2f}" for v in
            [q.iloc[0], q.iloc[1], q.iloc[2], q.iloc[3], q.iloc[4],
             s.mean()]) + flag)
    say("  " + "-" * 95)
    say("  market_cap and ev are printed in $bn; everything else is as stored")


def report_splits(f: pd.DataFrame, out: pd.DataFrame) -> None:
    """How much of the matrix sits before a split, i.e. how much of it the
    adjusted-price defect hits hardest. Diagnostic only -- this looks forward
    and is never used in a feature value."""
    s = f.loc[f["shares"].notna(), ["symbol", "filed", "shares"]]
    s = s.sort_values(["symbol", "filed"])
    r = s["shares"] / s.groupby("symbol")["shares"].shift(1)
    plausible = (r > SPLIT_JUMP) & (r <= MAX_SPLIT_JUMP)
    jump = s.assign(r=r).loc[plausible, ["symbol", "filed", "r"]]
    # a mis-tagged share count also produces a jump, so this is an upper bound
    last = jump.groupby("symbol")["filed"].max()
    hit = out["date"] < out["symbol"].map(last)
    factor = jump.groupby("symbol")["r"].prod()
    say("\nADJUSTED-PRICE EXPOSURE (diagnostic only -- this looks forward and")
    say("never touches a feature value)")
    say(f"  share-count jumps over {SPLIT_JUMP}x: {len(jump)} events on "
        f"{jump['symbol'].nunique()} symbols")
    say(f"  grid rows dated before a symbol's last such jump: "
        f"{hit.sum():,} = {hit.mean() * PCT:.1f}%")
    say(f"  implied understatement on those rows: median {factor.median():.1f}x,"
        f" worst {factor.max():.0f}x")
    say("  the remaining rows are understated by their own cumulative dividend")
    say("  adjustment instead, which is smaller but never zero")


def verify(out: pd.DataFrame, grid: pd.DataFrame) -> None:
    say("\nCONTRACT CHECK against the grid")
    assert len(out) == len(grid), f"{len(out)} rows vs grid {len(grid)}"
    key = out["date"].astype(str) + "|" + out["symbol"]
    gkey = grid["date"].astype(str) + "|" + grid["symbol"]
    assert key.tolist() == gkey.tolist(), "(date, symbol) order does not match"
    assert not out.duplicated(["date", "symbol"]).any(), "duplicate pair"
    inf = np.isinf(out[FEATURES].to_numpy(dtype=float)).sum()
    assert inf == 0, f"{inf} infinite values -- a guarded divide leaked"
    cols = ["date", "symbol"] + FEATURES
    assert out.columns.tolist() == cols, "column drift"
    say(f"  rows {len(out):,} == grid {len(grid):,}")
    say(f"  (date, symbol) identical and in the same order: yes")
    say(f"  dates {out['date'].nunique()}  symbols {out['symbol'].nunique()}")


def main() -> None:
    say("BUILDING feat_val -- point-in-time valuation multiples")
    grid = load_grid()
    f = load_filings()

    q = decumulate(f)
    say(f"  de-cumulated quarters available: "
        f"{q[FLOW].notna().any(axis=1).sum():,} of {len(q):,} slots")
    neg = int((q["revenue"] < 0).sum())
    say(f"  de-cumulated quarters with NEGATIVE revenue (a broken YTD "
        f"sequence, left as-is): {neg}")

    panels = build_ttm(q)
    panels.update(build_stock(f))
    d, age = as_of(grid, panels)

    px = load_prices(pd.DatetimeIndex(grid["date"].unique()),
                     sorted(grid["symbol"].unique()))
    d = d.merge(px, on=["date", "symbol"], how="left")
    report_inputs(d)
    report_age(age)

    out, counts = compute(d)
    say("\nDENOMINATOR REJECTIONS -- why a multiple is NaN")
    say(f"  {'reason':<42}{'rows':>9}{'of grid':>10}")
    say("  " + "-" * 61)
    for k, v in counts.items():
        say(f"  {k:<42}{v:>9,}{v / len(out) * PCT:>9.1f}%")

    nothing = out[FEATURES].isna().all(axis=1)
    say(f"\n  rows with NO valuation feature at all: {nothing.sum():,} = "
        f"{nothing.mean() * PCT:.1f}%")

    report_features(out)
    report_splits(f, out)

    # the grid order is the contract, so restore it before the check and write
    out = out.set_index(["date", "symbol"]).loc[
        pd.MultiIndex.from_frame(grid[["date", "symbol"]])].reset_index()
    verify(out, grid)
    out.to_csv(OUT, index=False)
    say(f"\nwrote {OUT}  ({len(out):,} rows, {len(FEATURES)} features)")


if __name__ == "__main__":
    main()
