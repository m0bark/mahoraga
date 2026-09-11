"""Point-in-time profitability and balance-sheet features, one row per grid cell.

    python feat_qual.py            # build, report coverage, write the CSV
    python feat_qual.py --dry      # build and report, write nothing

WHAT THIS BLOCK IS
Fourteen fundamental-only features on the (date, symbol) grid in
cache_long/grid.csv. Fundamentals only -- no price input of any kind, so this
block carries no market-cap or valuation ratios. Every value on a row dated d
comes from an SEC filing whose FILED date is <= d.

THE FEATURES, with units stated because they are not uniform
  roa              %      TTM net income / total assets
  roe              %      TTM net income / common equity
  roic             %      TTM operating income / (equity + long-term debt)
  gross_margin     %      TTM gross profit / TTM revenue
  op_margin        %      TTM operating income / TTM revenue
  net_margin       %      TTM net income / TTM revenue
  current_ratio    x      current assets / current liabilities
  debt_equity      x      TOTAL liabilities / equity  (not just debt)
  lt_debt_equity   x      long-term debt / equity
  asset_turnover   x      TTM revenue / total assets
  accruals         %      (TTM net income - TTM cash from operations) / assets
  cash_to_assets   %      cash and equivalents / total assets
  fscore_pct       %      Piotroski score as a share of AVAILABLE legs
  fscore_legs      count  how many of the nine legs were computable (0-9)

Balance-sheet denominators are ENDING balances, not two-point averages. An
average assets figure needs the year-ago balance sheet as well, which doubles
the number of inputs that have to be present and therefore cuts coverage, for a
second-order change in a cross-sectional ranking. Stated here so nobody assumes
otherwise.

EVERY RATIO IS BUILT FROM ONE PERIOD
Each input arrives on its own filing date and is carried forward independently,
so a company that tags gross profit only in its 10-K has a stale gross profit
sitting beside a current revenue for three quarters of the year. Dividing those
does not give a noisier margin, it gives a different quantity, and it is how a
gross margin above 100% appears in a dataset where no single filing reports one.
So a feature is NaN unless all of its inputs carry the same period end. It costs
real coverage -- 22% of the rows where gross profit and revenue are both present,
18% for roic -- and the PERIOD ALIGNMENT table prints the bill feature by
feature. Without the rule gross_margin topped out at 109% and op_margin at 118%;
with it they top out at 91% and 80%.

WHY THE SOURCE IS sec_raw/ AND NOT cache_long/pit_fundamentals.csv
pit_fundamentals.csv keys one row per (filed, fp, fy) and, for each metric,
keeps the FIRST fact it meets in the SEC companyfacts array. Those arrays are
ordered by period end ascending, and a filing restates its comparatives, so the
first fact is the OLDEST comparative in the document rather than the period the
filing is about. Checked against Apple's 10-K filed 2025-10-31:

    facts in that filing   FY2023  $96.995bn
                           FY2024  $93.736bn
                           FY2025 $112.010bn   <- what the filing reported
    panel value            FY2023  $96.995bn   <- two years stale
    panel _end             2024-09-28          <- matches neither

The same shift hits every income-statement and cash-flow column, and the panel
carries no period START, so the length of a flow period cannot be recovered from
it either. A TTM built on that column would be wrong by two fiscal years, not by
a rounding error. sec_raw/*.json is the data sec_pit.py already downloaded and it
keeps `start`, `end`, `val`, `form` and `filed` on every fact, which is
everything needed to do this correctly. Nothing here is a new download and
nothing outside this module is written.

HOW TTM IS BUILT, since the instruction to "sum four quarters" needs care
XBRL flow facts are cumulative within the fiscal year: a Q3 10-Q reports the nine
months to date and the 10-K reports the full year. They are not four independent
quarters. So:
  1. single quarters come from two places -- facts whose own duration is a
     quarter, and differences between two cumulative facts that SHARE a start
     date. The second source is the only way a fourth quarter exists at all,
     because no filing reports Q4 on its own;
  2. a TTM is four consecutive quarters whose combined span is 350-380 days,
     which rejects a window with a quarter missing because its span then comes
     out near 455 days;
  3. a fact whose own duration is already annual is taken as a TTM directly.
     This is what lets an annual-only stretch of history still produce a value;
  4. an FY row is treated as a FULL YEAR, never as Q4. The annual fact minus the
     same filing's nine-month fact is Q4; the annual fact itself is the year.
Where a period is reported more than once (an amendment, a restatement) the
EARLIEST disclosure wins, matching sec_pit.py: a later correction is not what
could have been traded on at the time.

Only periodic-report forms are used: 10-K, 10-KT, 10-Q and their amendments. 8-K
earnings releases often beat the 10-Q by a few weeks and are deliberately left
out, because including them would make this block's information timing differ
from pit_fscore.csv, which is built from 10-K and 10-Q only. That costs a few
weeks of timeliness and buys consistency across the matrix.

NO LOOKAHEAD, concretely
A fact enters a row dated d only if its filed date is <= d, and among those the
one with the latest period end wins. Values carry forward between filings, as
they must, but a value is dropped once its period end is more than
MAX_STALE_DAYS behind d, so a company that stopped filing does not keep
contributing a frozen number for years. The target column fwd63 is read only to
copy the grid's row order and is never an input. report_lookahead() asserts both
directions of the rule on the finished panel rather than claiming them here, and
it earned its keep: eleven facts in this dataset carry a period end AFTER their
own filing date (Roper's 10-Q filed 2009-11-02 reports a balance sheet dated
2009-12-31), which is impossible and is discarded at load. Twenty-one further
facts report a negative total asset, cash, long-term debt or current balance,
which is also impossible, and they too are dropped rather than allowed to produce
a negative lt_debt_equity.

THE TAILS ARE REAL AND ARE NOT CLIPPED
debt_equity reaches 132,900x and roe reaches 48,276%. Both are genuine: ICE's
newly formed holding company filed a 2013 10-Q showing ten dollars of equity
against $1.3m of liabilities, and Wynn's parent-only equity fell to about $1.3m
after its special dividends. A ratio with a sliver of equity underneath it is
unbounded by construction. Nothing here is winsorised, because where to clip is a
modelling choice and belongs to whatever consumes this matrix, not to the feature
definition. The EXTREME ROWS table names the (symbol, date) behind every min and
max so a reader can check rather than guess.

THE REVENUE COLUMN IS PARTLY MIS-TAGGED AND THAT IS NOT FIXABLE FROM DISK
sec_pit.py's fetch stores, for each metric, ONLY the first XBRL tag it finds
present, and its revenue list starts with "Revenues". Many companies carry a
sparse "Revenues" tag for an incidental disclosure while reporting the real top
line under RevenueFromContractWithCustomer*, so "Revenues" wins and shadows it.
Apple is the clearest case: its stored revenue is eleven facts from one 2018 10-K
covering calendar 2016-2017, so Apple has no usable revenue history here and its
three margin features and asset_turnover are NaN on every row. Only one tag per
metric survives in sec_raw/*.json, so the good tag cannot be recovered without
re-downloading companyfacts, which is outside this block's scope. The same
single-tag rule explains the staleness voids on debt_lt and cash: a company that
switches from LongTermDebt to LongTermDebtNoncurrent keeps only whichever tag
sec_pit.py asked for first, so its series simply stops. Revenue is the worst case
because the shadowing tag is also the most common one.
Where the mis-tagging is PROVABLE it is voided rather than shipped, on two tests.
The hard identity: gross profit is revenue minus cost of sales and operating
income is gross profit minus operating expense, so neither can exceed revenue in
the same period, and one breach proves the tag wrong. The typicality test: a
company can out-earn a year of its own sales once, on a disposal gain, but not
habitually, so a symbol whose MEDIAN trailing-year net income exceeds its median
trailing-year revenue is not reporting a top line either. The second test is what
separates Fifth Third and Regions, at 4x and 20x in every period, from CME and
Public Storage, which cross above revenue three or four times in sixty periods on
real gains and are left alone. A wrong top line is wrong on every date, not only
where a test trips, so the symbol's whole revenue series goes. Ten symbols are
voided; they are named in the report.

WHY debt_equity IS THINNER THAN IT HAS TO BE
Total liabilities is an optional tag and only 342 of the 465 symbols use it,
which caps debt_equity and lt_debt_equity near 59% of rows. Assets minus
StockholdersEquity would lift that to roughly 92%, but StockholdersEquity
excludes noncontrolling interest while Assets does not, so the difference is
liabilities PLUS minority interest, and the ratio would be quietly overstated for
exactly the conglomerates and utilities where leverage matters most. The gap is
left open and reported instead of closed with an identity that does not hold.

WHAT COULD NOT BE BUILT
  Quick Ratio   needs inventory, or at least receivables, to strip the illiquid
                part out of current assets. This dataset has AssetsCurrent and
                LiabilitiesCurrent and nothing between them. A "quick ratio"
                equal to the current ratio, or to current assets minus some
                guessed inventory fraction, would rank companies by a number
                that is not the quantity named. Left out.
  Payout Ratio  needs dividends paid or declared. No dividend field was
                downloaded, so there is nothing to divide by earnings. Left out
                rather than proxied.
Both are screener columns this block simply does not have. They are absent, not
approximated.

KNOWN THIN SPOTS, reported by the coverage table rather than hidden
gross_profit is tagged by only 236 of 465 symbols and revenue is damaged as
described above, so gross_margin, op_margin, net_margin and asset_turnover cover
far fewer rows than roa does. debt_lt is likewise thin, which caps roic and
lt_debt_equity. A missing debt_lt is NOT read as zero debt: a company with no
long-term-debt tag may simply not use the tag, and treating that as a debt-free
balance sheet would flatter it.
Negative or zero equity makes roe, roic, debt_equity and lt_debt_equity
meaningless rather than merely extreme -- the sign flips and the magnitude
explodes -- so those four are NaN when the denominator is not strictly positive,
and the frequency is printed.
"""
from __future__ import annotations

import glob
import io
import json
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
RAW = os.path.join(HERE, "sec_raw")
GRID = os.path.join(LONG, "grid.csv")
FSCORE = os.path.join(LONG, "pit_fscore.csv")
OUT = os.path.join(LONG, "feat_qual.csv")

# Flow items are durations and need a TTM; stock items are instants and are used
# as reported on the balance-sheet date.
FLOW_METRICS = ("revenue", "net_income", "op_income", "cfo", "gross_profit")
STOCK_METRICS = ("assets", "liabilities", "equity", "cash", "debt_lt",
                 "current_assets", "current_liabilities")

# Periodic reports only. An amendment is kept because it was genuinely public on
# its own filed date; an 8-K earnings release is excluded so that this block's
# information timing matches pit_fscore.csv.
PERIODIC_FORMS = frozenset({"10-K", "10-K/A", "10-KT", "10-KT/A",
                            "10-Q", "10-Q/A"})

# Duration windows in days. A fiscal quarter is 13 or 14 weeks (91 or 98 days)
# for 52/53-week filers and 89-92 days for calendar filers; a fiscal year is 364,
# 365 or 371. The windows are tight on purpose: 4-month and 8-month transition
# periods are real in this data and must be discarded, not quietly counted as a
# quarter.
QUARTER_MIN_DAYS, QUARTER_MAX_DAYS = 80, 100
ANNUAL_MIN_DAYS, ANNUAL_MAX_DAYS = 350, 380

TTM_QUARTERS = 4

# Quantities that cannot be negative under any accounting. A negative one is a
# sign error in the filing's XBRL, and it produced a negative long-term debt and
# therefore a negative lt_debt_equity before this guard existed. Equity is
# deliberately absent: it legitimately goes negative and is handled by over().
NON_NEGATIVE_METRICS = ("assets", "liabilities", "cash", "debt_lt",
                        "current_assets", "current_liabilities")

# A symbol whose TYPICAL trailing-year net income exceeds its typical trailing-
# year revenue is not reporting a top line. One period above is a real one-off
# gain; a median above is a mis-tagged revenue. The minimum period count keeps a
# short history from being condemned on two noisy observations.
MISTAG_MEDIAN_RATIO = 1.0
MISTAG_MIN_PERIODS = 4

# A value whose period ended this long before the decision date is dropped. An
# annual-only filer is legitimately 14 months stale just before its next 10-K
# (fiscal year ends December, filed March, nothing new until the following
# March), so the cap has to clear that; past it the company stopped filing.
MAX_STALE_DAYS = 550

PCT = 100.0

# One datetime resolution for every frame here. read_csv and a cast from int64
# disagree on it, and merge_asof refuses to join across resolutions.
DT = "datetime64[ns]"

# Thresholds used only by the report, so the wording and the numbers agree.
THIN_COVERAGE_PCT = 50.0
GOOD_SYMBOL_COVERAGE = 0.90
WEAK_SYMBOL_COVERAGE = 0.50

# name, unit, what it is. Drives the coverage table so the report and the
# docstring cannot drift apart.
FEATURES: tuple[tuple[str, str, str], ...] = (
    ("roa", "%", "TTM net income / assets"),
    ("roe", "%", "TTM net income / equity"),
    ("roic", "%", "TTM op income / (equity + LT debt)"),
    ("gross_margin", "%", "TTM gross profit / TTM revenue"),
    ("op_margin", "%", "TTM op income / TTM revenue"),
    ("net_margin", "%", "TTM net income / TTM revenue"),
    ("current_ratio", "x", "current assets / current liabilities"),
    ("debt_equity", "x", "total liabilities / equity"),
    ("lt_debt_equity", "x", "long-term debt / equity"),
    ("asset_turnover", "x", "TTM revenue / assets"),
    ("accruals", "%", "(TTM NI - TTM CFO) / assets"),
    ("cash_to_assets", "%", "cash / assets"),
    ("fscore_pct", "%", "Piotroski, share of available legs"),
    ("fscore_legs", "n", "legs computable, 0-9"),
)
FEATURE_NAMES = tuple(n for n, _, _ in FEATURES)

# Which inputs each feature divides, in one place, so the period-alignment rule
# and the feature arithmetic cannot disagree about what a feature is made of.
FEATURE_INPUTS: dict[str, tuple[str, ...]] = {
    "roa": ("net_income", "assets"),
    "roe": ("net_income", "equity"),
    "roic": ("op_income", "equity", "debt_lt"),
    "gross_margin": ("gross_profit", "revenue"),
    "op_margin": ("op_income", "revenue"),
    "net_margin": ("net_income", "revenue"),
    "current_ratio": ("current_assets", "current_liabilities"),
    "debt_equity": ("liabilities", "equity"),
    "lt_debt_equity": ("debt_lt", "equity"),
    "asset_turnover": ("revenue", "assets"),
    "accruals": ("net_income", "cfo", "assets"),
    "cash_to_assets": ("cash", "assets"),
}

QUANTILES = (0.01, 0.10, 0.50, 0.90, 0.99)


# --------------------------------------------------------------------------
# stage 1: raw facts
# --------------------------------------------------------------------------
def load_facts(symbols: frozenset[str]
               ) -> tuple[pd.DataFrame, list[str], int, int]:
    """Every periodic-report fact for the metrics this block needs.

    Returns the fact frame, the symbols whose file could not be read, the count
    of facts discarded for ending after their own filing date, and the count
    discarded for an impossible negative value. A read failure is reported,
    never swallowed: the symbol's features end up NaN and the coverage table
    shows the hole.
    """
    wanted = set(FLOW_METRICS) | set(STOCK_METRICS)
    rows: list[tuple] = []
    failed: list[str] = []
    for path in sorted(glob.glob(os.path.join(RAW, "*.json"))):
        sym = os.path.basename(path)[:-len(".json")]
        if sym not in symbols:
            continue
        try:
            with open(path, "r", encoding="utf-8") as fh:
                doc = json.load(fh)
        except (OSError, ValueError) as exc:
            failed.append(f"{sym} ({type(exc).__name__})")
            continue
        for metric, units in doc.get("facts", {}).items():
            if metric not in wanted:
                continue
            # every metric here is a USD amount; anything else is a tagging
            # surprise and is skipped rather than silently mixed in
            if "USD" not in units:
                continue
            for fact in units["USD"]:
                if fact.get("form") not in PERIODIC_FORMS:
                    continue
                rows.append((sym, metric, fact.get("start"), fact.get("end"),
                             fact.get("val"), fact.get("filed")))

    f = pd.DataFrame(rows, columns=["symbol", "metric", "start", "end",
                                    "val", "filed"])
    for col in ("start", "end", "filed"):
        f[col] = pd.to_datetime(f[col], errors="coerce").astype(DT)
    f["val"] = pd.to_numeric(f["val"], errors="coerce")
    f = f.dropna(subset=["end", "filed", "val"])

    # A handful of filings mis-tag their own period end into the future -- ROP's
    # 10-Q filed 2009-11-02 carries a balance sheet dated 2009-12-31. No company
    # can report a period that has not happened, so these are tagging errors in
    # the filing, and left in they would both count as lookahead and shadow the
    # genuinely newer facts under the latest-period-end rule.
    future = f["end"] > f["filed"]
    n_future = int(future.sum())
    f = f[~future]

    # sign errors: a balance sheet cannot hold negative cash or negative debt
    bad_sign = f["metric"].isin(NON_NEGATIVE_METRICS) & (f["val"] < 0)
    n_sign = int(bad_sign.sum())
    f = f[~bad_sign]
    return f, failed, n_future, n_sign


# --------------------------------------------------------------------------
# stage 2: single quarters, then TTM
# --------------------------------------------------------------------------
def single_quarters(flows: pd.DataFrame) -> pd.DataFrame:
    """One row per (symbol, metric, quarter) holding that quarter alone.

    Two sources. Facts whose own duration is a quarter, and the difference
    between two cumulative facts sharing a start date -- the second is the only
    way a fourth quarter exists, because no filing reports Q4 on its own.
    """
    f = flows.dropna(subset=["start"]).copy()
    # the same period reported twice (amendment, restatement) collapses to its
    # first disclosure, consistent with sec_pit.py's original-filing rule
    f = (f.sort_values(["symbol", "metric", "start", "end", "filed"])
          .drop_duplicates(["symbol", "metric", "start", "end"], keep="first"))
    f["days"] = (f["end"] - f["start"]).dt.days

    direct = (f[f["days"].between(QUARTER_MIN_DAYS, QUARTER_MAX_DAYS)]
              [["symbol", "metric", "start", "end", "val", "filed"]]
              .rename(columns={"filed": "known"}))

    # cumulative differences: within one (symbol, metric, start) the facts are
    # nested year-to-date windows, so consecutive ends bracket a single period
    grp = f.groupby(["symbol", "metric", "start"], sort=False)
    f["prev_end"] = grp["end"].shift(1)
    f["prev_val"] = grp["val"].shift(1)
    f["prev_filed"] = grp["filed"].shift(1)
    d = f.dropna(subset=["prev_end"]).copy()
    d["gap_days"] = (d["end"] - d["prev_end"]).dt.days
    d = d[d["gap_days"].between(QUARTER_MIN_DAYS, QUARTER_MAX_DAYS)]
    derived = pd.DataFrame({
        "symbol": d["symbol"],
        "metric": d["metric"],
        "start": d["prev_end"],
        "end": d["end"],
        "val": d["val"] - d["prev_val"],
        # an increment is not public until BOTH of its legs are public
        "known": d[["filed", "prev_filed"]].max(axis=1),
    })

    q = pd.concat([direct, derived], ignore_index=True)
    # one value per quarter end, earliest disclosure wins
    q = (q.sort_values(["symbol", "metric", "end", "known"])
          .drop_duplicates(["symbol", "metric", "end"], keep="first"))
    return q.reset_index(drop=True)


def ttm(flows: pd.DataFrame, quarters: pd.DataFrame) -> pd.DataFrame:
    """Trailing-twelve-month flows: four consecutive quarters, or an annual fact
    taken whole."""
    q = quarters.sort_values(["symbol", "metric", "end"]).reset_index(drop=True)
    grp = q.groupby(["symbol", "metric"], sort=False)
    # rolling max over an int64 view, because rolling() will not reduce datetimes
    q["known_i"] = q["known"].astype("int64")
    q["sum4"] = grp["val"].transform(lambda s: s.rolling(TTM_QUARTERS).sum())
    q["n4"] = grp["val"].transform(lambda s: s.rolling(TTM_QUARTERS).count())
    q["known4"] = grp["known_i"].transform(
        lambda s: s.rolling(TTM_QUARTERS).max())
    q["start4"] = grp["start"].shift(TTM_QUARTERS - 1)
    q["span"] = (q["end"] - q["start4"]).dt.days
    ok = (q["n4"] == TTM_QUARTERS) & q["span"].between(ANNUAL_MIN_DAYS,
                                                      ANNUAL_MAX_DAYS)
    rolled = pd.DataFrame({
        "symbol": q.loc[ok, "symbol"],
        "metric": q.loc[ok, "metric"],
        "pend": q.loc[ok, "end"],
        "val": q.loc[ok, "sum4"],
        # the TTM is public only once its last-filed constituent quarter is
        "known": pd.to_datetime(q.loc[ok, "known4"].astype("int64")).astype(DT),
    })

    # an annual fact already covers twelve months. A 10-K's three annual
    # comparatives all arrive on one filed date and are separated downstream by
    # the latest-period-end rule, so all three are kept here.
    a = flows.dropna(subset=["start"]).copy()
    a["days"] = (a["end"] - a["start"]).dt.days
    a = a[a["days"].between(ANNUAL_MIN_DAYS, ANNUAL_MAX_DAYS)]
    annual = pd.DataFrame({
        "symbol": a["symbol"], "metric": a["metric"], "pend": a["end"],
        "val": a["val"], "known": a["filed"],
    })

    t = pd.concat([rolled, annual], ignore_index=True)
    t = (t.sort_values(["symbol", "metric", "pend", "known"])
          .drop_duplicates(["symbol", "metric", "pend"], keep="first"))
    return t.reset_index(drop=True)


def instants(stocks: pd.DataFrame) -> pd.DataFrame:
    """Balance-sheet items as reported, keyed by balance-sheet date."""
    s = pd.DataFrame({
        "symbol": stocks["symbol"], "metric": stocks["metric"],
        "pend": stocks["end"], "val": stocks["val"], "known": stocks["filed"],
    })
    s = (s.sort_values(["symbol", "metric", "pend", "known"])
          .drop_duplicates(["symbol", "metric", "pend"], keep="first"))
    return s.reset_index(drop=True)


def void_mistagged_revenue(flow_ttm: pd.DataFrame
                           ) -> tuple[pd.DataFrame, list[str]]:
    """Drop the revenue series of a symbol whose revenue is provably not it.

    Two tests, both about what is possible rather than about what looks odd.

    The hard identity. Gross profit is revenue minus cost of sales and operating
    income is gross profit minus operating expense, so neither can exceed revenue
    in the same period. One breach is proof of a wrong tag.

    The typicality test. A company can earn more in a year than it bills, once,
    on a disposal gain. It cannot do so habitually. So a symbol whose MEDIAN
    trailing-year net income exceeds its median trailing-year revenue is not
    reporting a top line either. This separates Fifth Third and Regions, whose
    ratio sits at 4x and 20x in every period, from CME and Public Storage,
    which cross above revenue in three or four periods out of sixty and are left
    alone.

    A wrong top line is wrong on every date, not only where a test trips, so the
    symbol's whole revenue series goes. Shipping it would make net_margin
    wrong by a multiple while still looking like a plausible percentage.
    """
    w = flow_ttm.pivot_table(index=["symbol", "pend"], columns="metric",
                             values="val", aggfunc="last")
    if "revenue" not in w.columns:
        return flow_ttm, []

    breach = pd.Series(False, index=w.index)
    for item in ("gross_profit", "op_income"):
        if item in w.columns:
            breach |= (w[item].notna() & w["revenue"].notna()
                       & (w[item] > w["revenue"]))
    hit = set(w.index.get_level_values("symbol")[breach.to_numpy()])

    if "net_income" in w.columns:
        r = (w["net_income"] / w["revenue"].where(w["revenue"] > 0)).dropna()
        by_sym = r.groupby(level="symbol")
        typical = by_sym.median()
        enough = by_sym.size() >= MISTAG_MIN_PERIODS
        hit |= set(typical.index[enough & (typical > MISTAG_MEDIAN_RATIO)])

    flagged = sorted(hit)
    keep = ~((flow_ttm["metric"] == "revenue")
             & flow_ttm["symbol"].isin(flagged))
    return flow_ttm[keep].reset_index(drop=True), flagged


# --------------------------------------------------------------------------
# stage 3: what was known on each filing date
# --------------------------------------------------------------------------
def known_series(events: pd.DataFrame) -> pd.DataFrame:
    """Collapse the event stream to one row per (symbol, known date) carrying the
    freshest value of every metric.

    A filing restates old periods alongside the new one, so "freshest" means the
    largest period end seen so far, not the last row in the file.
    """
    e = events.sort_values(["symbol", "metric", "known", "pend"])
    run = e.groupby(["symbol", "metric"], sort=False)["pend"].cummax()
    e = e[e["pend"] >= run]
    e = e.drop_duplicates(["symbol", "metric", "known"], keep="last")

    val = e.pivot_table(index=["symbol", "known"], columns="metric",
                        values="val", aggfunc="last")
    end = e.pivot_table(index=["symbol", "known"], columns="metric",
                        values="pend", aggfunc="last")
    end.columns = [f"{c}__end" for c in end.columns]
    w = val.join(end).sort_index().reset_index()
    # metrics appear on different filing dates, so carry each one forward
    cols = [c for c in w.columns if c not in ("symbol", "known")]
    w[cols] = w.groupby("symbol", sort=False)[cols].ffill()
    return w


def as_of(grid: pd.DataFrame, known: pd.DataFrame) -> pd.DataFrame:
    """Attach to every grid row the last filing state at or before its date."""
    g = grid.sort_values("date").reset_index(drop=True)
    k = known.sort_values("known").reset_index(drop=True)
    return pd.merge_asof(g, k, left_on="date", right_on="known", by="symbol",
                         direction="backward")


def drop_stale(m: pd.DataFrame,
               metrics: tuple[str, ...]) -> tuple[pd.DataFrame, dict[str, int]]:
    """NaN out any metric whose period ended more than MAX_STALE_DAYS before the
    decision date, so a company that stopped filing stops contributing."""
    dropped: dict[str, int] = {}
    for metric in metrics:
        end_col = f"{metric}__end"
        if metric not in m.columns or end_col not in m.columns:
            # the metric never appeared for any symbol; NaN, and the coverage
            # table will show 0.0%
            m[metric] = np.nan
            m[end_col] = pd.NaT
            dropped[metric] = 0
            continue
        age = (m["date"] - m[end_col]).dt.days
        stale = age.gt(MAX_STALE_DAYS) & m[metric].notna()
        dropped[metric] = int(stale.sum())
        m.loc[stale, metric] = np.nan
        m.loc[stale, end_col] = pd.NaT
    return m, dropped


# --------------------------------------------------------------------------
# stage 4: the features
# --------------------------------------------------------------------------
def over(num: pd.Series, den: pd.Series, scale: float = 1.0) -> pd.Series:
    """num / den, with the denominator required to be strictly positive.

    Every denominator in this block is a quantity that is only interpretable
    when positive -- assets, equity, revenue, current liabilities, invested
    capital. A zero or negative one does not make the ratio large, it makes it
    meaningless, so the result is NaN.
    """
    return num / den.where(den > 0) * scale


def same_period(m: pd.DataFrame, metrics: tuple[str, ...]) -> pd.Series:
    """True where every named input is present AND they all describe the same
    accounting period.

    Each metric arrives on its own filing date and is carried forward
    independently, so a company that stopped tagging gross profit would otherwise
    have last year's gross profit divided into this year's revenue. That is how a
    gross margin above 100% appears in a dataset where no single filing reports
    one. Mixing two periods is not a thinner version of the ratio, it is a
    different quantity, so the row is NaN instead.
    """
    ok = pd.Series(True, index=m.index)
    for metric in metrics:
        ok &= m[metric].notna()
    first = m[f"{metrics[0]}__end"]
    for metric in metrics[1:]:
        ok &= first.eq(m[f"{metric}__end"])
    return ok


def build_features(m: pd.DataFrame) -> pd.DataFrame:
    ni, oi, rev, gp, cfo = (m["net_income"], m["op_income"], m["revenue"],
                            m["gross_profit"], m["cfo"])
    assets, equity, liab = m["assets"], m["equity"], m["liabilities"]
    dlt, ca, cl, cash = (m["debt_lt"], m["current_assets"],
                         m["current_liabilities"], m["cash"])

    out = pd.DataFrame(index=m.index)
    out["roa"] = over(ni, assets, PCT)
    out["roe"] = over(ni, equity, PCT)
    # invested capital is equity plus long-term debt, as specified. A missing
    # debt_lt is NOT read as zero: an untagged balance sheet is not a debt-free
    # one, so the row is NaN rather than flattered.
    out["roic"] = over(oi, equity + dlt, PCT)
    out["gross_margin"] = over(gp, rev, PCT)
    out["op_margin"] = over(oi, rev, PCT)
    out["net_margin"] = over(ni, rev, PCT)
    out["current_ratio"] = over(ca, cl)
    out["debt_equity"] = over(liab, equity)
    out["lt_debt_equity"] = over(dlt, equity)
    out["asset_turnover"] = over(rev, assets)
    out["accruals"] = over(ni - cfo, assets, PCT)
    out["cash_to_assets"] = over(cash, assets, PCT)
    # every ratio above is only a ratio when its parts describe one period
    for name, inputs in FEATURE_INPUTS.items():
        out[name] = out[name].where(same_period(m, inputs))
    return out


def join_fscore(body: pd.DataFrame) -> pd.DataFrame:
    """fscore_pct and legs_available as of the grid date, merge_asof backward on
    the FILED date, per symbol."""
    s = pd.read_csv(FSCORE)
    s["filed"] = pd.to_datetime(s["filed"], errors="coerce").astype(DT)
    s = s.dropna(subset=["filed", "symbol"])
    s = (s[["symbol", "filed", "fscore_pct", "legs_available"]]
         .sort_values(["symbol", "filed"])
         .drop_duplicates(["symbol", "filed"], keep="last")
         .sort_values("filed").reset_index(drop=True))

    g = body[["date", "symbol"]].sort_values("date").reset_index()
    j = pd.merge_asof(g, s, left_on="date", right_on="filed", by="symbol",
                      direction="backward")
    # the same staleness rule as the fundamentals, applied to the filed date
    # because pit_fscore.csv inherits its _end from the distorted panel
    stale = (j["date"] - j["filed"]).dt.days.gt(MAX_STALE_DAYS)
    j.loc[stale, ["fscore_pct", "legs_available"]] = np.nan
    j = j.set_index("index").sort_index()
    return pd.DataFrame({"fscore_pct": j["fscore_pct"],
                         "fscore_legs": j["legs_available"]})


# --------------------------------------------------------------------------
# reporting
# --------------------------------------------------------------------------
def report_inputs(m: pd.DataFrame, metrics: tuple[str, ...],
                  stale: dict[str, int]) -> None:
    say("INPUT COVERAGE on the grid -- why a feature is thin is always here")
    say(f"  {'field':<22}{'present':>9}{'age p50':>9}{'age p99':>9}"
        f"{'voided stale':>14}")
    say("  " + "-" * 63)
    for metric in sorted(metrics):
        cov = m[metric].notna().mean() * PCT
        age = (m["date"] - m[f"{metric}__end"]).dt.days
        flag = "  <-- THIN" if cov < THIN_COVERAGE_PCT else ""
        say(f"  {metric:<22}{cov:>8.1f}%{age.median():>8.0f}d"
            f"{age.quantile(0.99):>8.0f}d{stale[metric]:>14,}{flag}")
    say("  " + "-" * 63)
    say("  age is days from the period end to the decision date: reporting lag.")
    say(f"  'voided stale' counts values dropped for an age over"
        f" {MAX_STALE_DAYS}d, meaning the")
    say("  company stopped reporting that field. Those cells are NaN, not"
        " carried forward.")


def report_revenue(m: pd.DataFrame, voided: list[str]) -> None:
    """The revenue column is the weakest input here and the reason is a tag
    choice made upstream, not a gap in the filings. Spelled out so nobody reads
    a thin margin feature as a thin universe."""
    say("")
    say("REVENUE TAGGING -- the upstream defect behind the thin margins")
    per = m.groupby("symbol")["revenue"].apply(lambda s: s.notna().mean())
    n = len(per)
    good = int((per >= GOOD_SYMBOL_COVERAGE).sum())
    mid = int(((per >= WEAK_SYMBOL_COVERAGE)
               & (per < GOOD_SYMBOL_COVERAGE)).sum())
    weak = int(((per > 0) & (per < WEAK_SYMBOL_COVERAGE)).sum())
    none = int((per == 0).sum())
    say(f"  revenue present on >=90% of a symbol's rows: {good} of {n} symbols")
    say(f"                        50-90% of its rows: {mid}")
    say(f"                         1-50% of its rows: {weak}")
    say(f"                      never:                {none}")
    say("  cause: sec_pit.py keeps only the first matching XBRL tag, and"
        " \"Revenues\" shadows")
    say("  RevenueFromContractWithCustomer* wherever a company uses the former"
        " incidentally.")
    say("  Fixing it needs a re-fetch of companyfacts with the full tag list.")
    if voided:
        say("  revenue VOIDED as provably mis-tagged -- gross profit or"
            " operating income above")
        say("  revenue in one period, or median net income above median revenue"
            " across periods:")
        say(f"  {voided}")


def report_alignment(m: pd.DataFrame) -> None:
    """How much coverage the same-period rule costs, feature by feature. Worth
    its own table: it is the difference between a ratio and two numbers from
    different years stacked on top of each other."""
    say("")
    say("PERIOD ALIGNMENT -- rows where all inputs were present but from"
        " DIFFERENT periods")
    say(f"  {'feature':<16}{'inputs present':>16}{'aligned':>10}{'lost':>8}"
        f"{'lost %':>9}")
    say("  " + "-" * 60)
    for name, inputs in FEATURE_INPUTS.items():
        present = pd.Series(True, index=m.index)
        for metric in inputs:
            present &= m[metric].notna()
        aligned = same_period(m, inputs)
        lost = int(present.sum() - aligned.sum())
        pct = lost / present.sum() * PCT if present.sum() else 0.0
        say(f"  {name:<16}{int(present.sum()):>16,}{int(aligned.sum()):>10,}"
            f"{lost:>8,}{pct:>8.1f}%")
    say("  " + "-" * 60)
    say("  A metric missing from the latest filing is carried forward, so its"
        " period end falls")
    say("  behind the others. Those rows are NaN rather than a ratio across two"
        " fiscal years.")


def report_equity(m: pd.DataFrame) -> None:
    say("")
    say("NEGATIVE OR ZERO EQUITY -- roe, roic, debt_equity, lt_debt_equity are"
        " NaN here")
    eq = m["equity"]
    have = eq.notna()
    bad = have & (eq <= 0)
    say(f"  equity reported on {have.mean() * PCT:.1f}% of rows")
    if have.sum():
        say(f"  of those, equity <= 0 on {int(bad.sum()):,} rows "
            f"({bad.sum() / have.sum() * PCT:.2f}%), "
            f"{m.loc[bad, 'symbol'].nunique()} distinct symbols")
    den = m["equity"] + m["debt_lt"]
    dhave = den.notna()
    dbad = dhave & (den <= 0)
    if dhave.sum():
        say(f"  equity + LT debt <= 0 on {int(dbad.sum()):,} of "
            f"{int(dhave.sum()):,} rows where both are reported")


def report_features(feat: pd.DataFrame) -> None:
    say("")
    say("PER-FEATURE COVERAGE AND DISTRIBUTION")
    head = (f"  {'feature':<16}{'unit':>5}{'cov':>7}{'mean':>9}{'min':>10}"
            + "".join(f"{'p' + str(int(q * 100)):>9}" for q in QUANTILES)
            + f"{'max':>11}")
    say(head)
    say("  " + "-" * (len(head) - 2))
    for name, unit, _ in FEATURES:
        s = feat[name]
        cov = s.notna().mean() * PCT
        qs = s.quantile(QUANTILES)
        flag = "  <-- THIN" if cov < THIN_COVERAGE_PCT else ""
        say(f"  {name:<16}{unit:>5}{cov:>6.1f}%{s.mean():>9.2f}{s.min():>10.1f}"
            + "".join(f"{qs[q]:>9.2f}" for q in QUANTILES)
            + f"{s.max():>11.1f}" + flag)
    say("  " + "-" * (len(head) - 2))
    blank = int(feat[list(FEATURE_NAMES)].isna().all(axis=1).sum())
    say(f"  cov is the share of all {len(feat):,} grid rows carrying a value."
        f" {blank:,} rows carry")
    say("  no feature at all -- a symbol the grid admits before its first"
        " usable filing.")
    say("  min and max are printed alongside p1/p99 so a single absurd row"
        " cannot hide inside")
    say("  a healthy-looking quantile. The ratio features are unbounded above by"
        " construction:")
    say("  a company with a sliver of positive equity gives a debt_equity in the"
        " hundreds, which")
    say("  is why their means sit far above their medians. Nothing is winsorised"
        " here -- that is")
    say("  a modelling choice and belongs downstream, not in the feature"
        " definition.")


def report_extremes(body: pd.DataFrame) -> None:
    """Name the row behind each feature's min and max.

    A tail printed as a bare number invites the reader to assume a bug. Printed
    with its symbol and date it can be checked, and in this dataset the worst of
    them check out: ICE's 132,900x debt_equity is the newly formed holding
    company's 2013 10-Q, which really did report ten dollars of equity against
    $1.3m of liabilities. Those rows are real, not corrupt, and they are left in
    because clipping them is a modelling decision.
    """
    say("")
    say("EXTREME ROWS -- which (symbol, date) produces each tail")
    say(f"  {'feature':<16}{'min':>12}  {'at':<18}{'max':>12}  {'at':<18}")
    say("  " + "-" * 78)
    for name, _, _ in FEATURES:
        s = body[name]
        if not s.notna().any():
            say(f"  {name:<16}{'no values':>12}")
            continue
        lo, hi = body.loc[s.idxmin()], body.loc[s.idxmax()]
        say(f"  {name:<16}{s.min():>12.1f}  "
            f"{lo['symbol'] + ' ' + format(lo['date'], '%Y-%m-%d'):<18}"
            f"{s.max():>12.1f}  "
            f"{hi['symbol'] + ' ' + format(hi['date'], '%Y-%m-%d'):<18}")
    say("  " + "-" * 78)


def report_lookahead(m: pd.DataFrame, metrics: tuple[str, ...]) -> None:
    """The one rule that matters, tested rather than asserted in prose."""
    future_filing = int((m["known"] > m["date"]).sum())
    future_period = 0
    for metric in metrics:
        end_col = f"{metric}__end"
        ahead = (m[end_col].notna() & m[metric].notna()
                 & (m[end_col] > m["date"]))
        future_period += int(ahead.sum())
    lag = (m["date"] - m["known"]).dt.days
    say("")
    say("NO-LOOKAHEAD AUDIT")
    say(f"  rows sourced from a filing dated after the row date:"
        f" {future_filing}")
    say(f"  values whose accounting period ends after the row date:"
        f" {future_period}")
    say(f"  days from the latest usable filing to the decision date:"
        f" p1 {lag.quantile(0.01):.0f}  p50 {lag.median():.0f}"
        f"  p99 {lag.quantile(0.99):.0f}")
    assert future_filing == 0, f"{future_filing} rows used a future filing"
    assert future_period == 0, f"{future_period} values end after the row date"


def verify(grid: pd.DataFrame, out: pd.DataFrame) -> None:
    """The grid is the contract, so check it rather than trust it."""
    assert len(out) == len(grid), f"row count {len(out)} != grid {len(grid)}"
    assert out["date"].equals(grid["date"]), "date column diverged from grid"
    assert out["symbol"].equals(grid["symbol"]), "symbol column diverged"
    assert not out.duplicated(["date", "symbol"]).any(), "duplicate grid cell"
    missing = set(FEATURE_NAMES) - set(out.columns)
    assert not missing, f"features missing from output: {missing}"
    say("")
    say(f"CONTRACT CHECK passed: {len(out):,} rows, {out['date'].nunique()}"
        f" dates, {out['symbol'].nunique()} symbols,")
    say("  (date, symbol) pairs and row order identical to grid.csv")


def spot_check(out: pd.DataFrame) -> None:
    """A handful of rows printed raw, because a coverage table can look healthy
    while the numbers are nonsense."""
    cols = ["date", "roa", "roe", "net_margin", "gross_margin",
            "current_ratio", "debt_equity", "fscore_pct"]
    fmt = {"date": lambda d: f"{d:%Y-%m-%d}"}

    say("")
    say("SPOT CHECK 1 -- KDP, a symbol with every input present")
    say(out[out["symbol"] == "KDP"].tail(4)[cols].to_string(index=False,
                                                           formatters=fmt))
    say("  Keurig Dr Pepper earns a mid-50s gross margin on roughly $15bn of"
        " sales and")
    say("  carries about as much total liability as equity, so a low-teens net"
        " margin and")
    say("  a debt/equity near 1.2x is the right neighbourhood.")

    say("")
    say("SPOT CHECK 2 -- AAPL, where the mis-tagged revenue bites")
    say(out[out["symbol"] == "AAPL"].tail(4)[cols].to_string(index=False,
                                                            formatters=fmt))
    say("  roa near 31% and roe above 100% are correct for Apple: TTM net income"
        " of about")
    say("  $118bn on $379bn of assets and $88bn of equity. Both margins are NaN"
        " because")
    say("  Apple's stored revenue tag holds eleven 2018 facts and nothing"
        " current, so the")
    say("  tag defect surfaces as an honest gap instead of a wrong percentage.")


# --------------------------------------------------------------------------
def main() -> None:
    grid = pd.read_csv(GRID, parse_dates=["date"])
    # fwd63 is the target. Read only to establish row order, never as input.
    grid = grid[["date", "symbol"]].copy()
    grid["date"] = grid["date"].astype(DT)
    symbols = frozenset(grid["symbol"].unique())
    say(f"grid: {len(grid):,} rows, {grid['date'].nunique()} dates, "
        f"{len(symbols)} symbols, "
        f"{grid['date'].min():%Y-%m-%d} .. {grid['date'].max():%Y-%m-%d}")

    facts, failed, n_future, n_sign = load_facts(symbols)
    say(f"facts: {len(facts):,} periodic-report facts over "
        f"{facts['symbol'].nunique()} of {len(symbols)} grid symbols")
    if failed:
        say(f"  UNREADABLE FILES ({len(failed)}): {failed}")
    say(f"  discarded, period end after their own filing date: {n_future}")
    say(f"  discarded, negative value for a quantity that cannot be negative:"
        f" {n_sign}")
    no_file = sorted(symbols - set(facts["symbol"].unique()))
    if no_file:
        say(f"  NO FACTS AT ALL ({len(no_file)}): {no_file}")

    flows = facts[facts["metric"].isin(FLOW_METRICS)]
    stocks = facts[facts["metric"].isin(STOCK_METRICS)]
    quarters = single_quarters(flows)
    say(f"  single quarters reconstructed: {len(quarters):,}")
    flow_ttm = ttm(flows, quarters)
    say(f"  TTM observations: {len(flow_ttm):,}")
    flow_ttm, voided = void_mistagged_revenue(flow_ttm)
    if voided:
        say(f"  revenue series voided as provably mis-tagged: {voided}")
    stock_obs = instants(stocks)
    say(f"  balance-sheet observations: {len(stock_obs):,}")

    known = known_series(pd.concat([flow_ttm, stock_obs], ignore_index=True))
    say(f"  filing states: {len(known):,} (symbol x filing date)")

    m = as_of(grid.reset_index(), known)
    all_metrics = FLOW_METRICS + STOCK_METRICS
    m, dropped = drop_stale(m, all_metrics)
    say(f"  values voided as stale (period end over {MAX_STALE_DAYS}d before"
        f" the decision date): {sum(dropped.values()):,}")

    # back to the grid's own row order before anything is reported or written
    body = pd.concat([m[["index", "date", "symbol"]], build_features(m)], axis=1)
    body = body.set_index("index").sort_index().reset_index(drop=True)
    body = pd.concat([body, join_fscore(body)], axis=1)

    say("")
    report_inputs(m, all_metrics, dropped)
    report_revenue(m, voided)
    report_alignment(m)
    report_equity(m)
    report_features(body)
    report_extremes(body)
    report_lookahead(m, all_metrics)
    verify(grid, body)
    spot_check(body)

    if "--dry" in sys.argv:
        say("\n--dry: nothing written")
        return
    body.to_csv(OUT, index=False)
    say(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
