"""Point-in-time growth rates for the feature matrix, one row per grid row.

    python feat_growth.py            # build, report coverage, write the CSV
    python feat_growth.py --no-save  # build and report only

WHAT THIS BLOCK IS
Nine fundamental growth features. Every one is computed only from SEC filings
whose FILED date is on or before the grid date, so no row can see a number the
market had not been given.

  rev_growth_yoy     revenue in a fiscal quarter vs the SAME fiscal quarter one
                     year earlier, percent. Same-quarter, never sequential: a
                     retailer's Q4 against its Q3 measures Christmas.
  rev_growth_ttm     trailing four quarters of revenue vs the prior four
  rev_growth_3y      3-year CAGR of TTM revenue, percent per year
  eps_growth_yoy     quarterly EPS vs the same quarter a year earlier
  eps_growth_ttm     TTM EPS vs the prior TTM
  eps_growth_3y      3-year CAGR of TTM EPS
  cfo_growth_ttm     TTM cash from operations vs the prior TTM
  shares_change_1y   share count vs a year earlier; negative is a buyback,
                     positive is dilution
  ni_growth_ttm      TTM net income vs the prior TTM

Periods are matched to their counterparts by END DATE, one year back within 45
days and three years back within 75, not by the (fy, fp) labels: those labels
describe the REPORT in XBRL, not the period, and end dates survive 52/53-week
retail calendars. A 3-year CAGR is annualised on the ACTUAL elapsed years, so a
match that lands at 2.9 years is not reported as if it were 3.

THE NEGATIVE-BASE RULE
A growth rate off a base <= 0 is not a number, it is a sign artefact: revenue
moving from -40m to -10m is not +75% growth. When the prior-period base is <= 0
the feature is NaN, never a large positive. For the two 3-year CAGRs the current
end must be > 0 as well, because a fractional power of a negative ratio is not
real. The coverage table counts the rows this costs; it is 5-6% of the grid for
the earnings features and essentially nothing for revenue.

HOW THE QUARTERS ARE RECONSTRUCTED, AND THE FY PROBLEM
Income-statement and cash-flow facts are PERIOD values and a filing reports them
in whatever window it pleases, so a TTM cannot be assumed. Each quarter here
comes from one of two places:

  direct   a fact whose own start..end span is 80-100 days
  derived  two year-to-date facts sharing a fiscal-year start and ending a
           quarter apart, differenced: Q2 = H1 - Q1, Q4 = FY - 9M. ALL such
           pairs, not just adjacent ones, because a later filing can restate a
           comparative and insert an end between two that already pair up.

The second is not optional. A cash flow statement is year-to-date by construction
and a discrete quarterly CFO fact barely exists: 73% of CFO quarters here are
differenced, and without that step cfo_growth_ttm populated 0.0% of the grid. It
also settles the FY-is-not-Q4 problem -- an fp=FY figure is the twelve-month
cumulative it says it is, and Q4 is recovered by subtracting the nine-month
figure rather than being mistaken for a quarter. A TTM is then four quarters
summed, and only where all four are present AND their ends span 250-300 days, so
a gap cannot be passed off as a year. The check on all of it is printed: four
summed quarters against the ANNUAL figure the filer stated for the same end date
agree within 1% on 97.2% of revenue, 98.3% of net income and 99.8% of CFO.

EPS IS DERIVED, NOT REPORTED
Reported EPS is not in this dataset (see below), so quarterly EPS is net income
over the share count as of that quarter end, and TTM EPS is four quarterly EPS
figures summed rather than TTM net income over one share count, which is how a
trailing EPS is normally built. It is basic-style and will differ from reported
diluted EPS, more so with heavy option or convertible overhang. Four fifths of
these companies tag shares as an instant and the rest as a period weighted
average, but a symbol uses one tag throughout, so a within-symbol growth rate
stays apples to apples.

XBRL UNITS ERRORS
They are real and they are violent. LUV tagged its 2011 Q2 revenue as 4,136 for
$4.136bn, KO has a share count of 4,255 against a true 4.3bn, SYK tagged shares
in millions for fifteen straight quarters, ICE reported a share count of 1. Left
alone these produced growth rates of 1e8 and 1e10 percent. Every offset is an
exact power of a thousand, which is the signature of a decimal error and of
nothing else, so the value is repaired by that power where it is, and rejected
where it is merely impossible. This runs on revenue and the share count only --
net income and cash flow legitimately collapse towards zero, and a real fall
from $300m to $0.3m is itself a thousandfold offset, so the same repair would
fabricate an earnings collapse. Their tails are therefore raw, and the printed
distributions show them: the largest ni_growth_ttm of +103,000% is HPE coming off
a near-zero trailing year, a real number rather than a units error. Separately, a
value stops being carried forward 450 days after the newest filing it rests on,
so a late filer cannot leave a 2015 growth rate sitting on a 2020 row; that cap
is the 450 in the lag audit's maximum column.

THE TWO AUDITS THIS RUNS ON ITSELF, AND WHAT THE SECOND ONE FOUND
The lag audit prints, for every populated cell, how old the newest filing behind
it was, and asserts that minimum is not negative. Over all 50,825 rows and nine
features the minimum is 0 days and the median is about 50, which is a reporting
lag, so no row can see a filing dated after it.

That is necessary and it is not sufficient, because a value can be free of
future data and still not be the value the same code would have produced on the
day. So the second audit resamples 250 rows, truncates each symbol's facts to
filings dated on or before that row, rebuilds all nine features and compares. It
found three real bugs that the lag audit was blind to:

  * a preference for a directly reported quarter over a differenced one, which
    made a quarter look unknown until a later 10-K supplied it directly and so
    delayed an entire TTM by a filing cycle
  * period matching done over the UNION of every metric's fiscal calendar, so a
    company ending a cash-flow quarter on 2013-06-28 and a revenue quarter on
    2013-06-30 could have one metric's year-ago slot land on the other's row
  * the asof tie broken by an unstable sort. A 10-K makes a year of comparatives
    public at once, so several periods share one asof date, and which of them
    landed on the grid was arbitrary -- sometimes a quarter three periods stale

All three are fixed. What the audit still reports, and what this docstring will
not pretend away, is that about 5% of populated cells hold a STALER reading than
a same-day rebuild would give, median gap 0.8% of the value and p90 32%. The
cause is that a period's first disclosure can arrive later than an alternative a
real-time build would have reached for, which pushes this build back to an older
quarter. Staleness is conservative: it cannot leak the future, and the audit
asserts zero cells are populated here that a same-day rebuild leaves empty.

WHY THIS READS sec_raw/ AND NOT cache_long/pit_fundamentals.csv
pit_fundamentals.csv cannot support these features, and the reason is a bug in
how it was flattened rather than thin coverage. sec_pit.py groups every XBRL
fact by (filed, fp, fy) and keeps the FIRST value it meets per metric. A fact
array is ordered by period end ascending and a filing restates its
comparatives, so "first" is the OLDEST period in the document, not the period
being reported. Verified against MMM:

  the 10-K filed 2011-02-16 reports FY2010 net income of 4.085e9;
  the panel row for that filing carries 3.460e9, which is MMM's FY2008.
  the 10-K filed 2026-02-03 (FY2025) carries -6.995e9, which is FY2023.
  the 10-Q filed 2010-05-05 (Q1 2010, 930m) carries 518m, which is Q1 2009.

So every flow item in that file is stale by a year on 10-Q rows and two years on
10-K rows, and its Q2 and Q3 rows are six- and nine-month cumulatives, so the
period LENGTH changes with fp. Same-period comparisons inside it stay internally
consistent, which is why pit_fscore.py still produces plausible numbers, but no
TTM can be summed from it: the FY row is two years behind the Q rows, so FY minus
Q3 is not Q4. Four of the nine features here would have been unbuildable and the
other five would have measured 2015 growth on a 2017 date.

sec_raw/*.json is the untouched upstream of that file and carries start, end,
filed and form on every individual fact. For each (metric, start, end) period
this module keeps the EARLIEST filing that disclosed it, which is both the day
the market learned it and the original rather than the restated value.

WHAT I COULD NOT BUILD, AND WHY
  * Every forward-looking growth filter the screener offers is unbuildable in
    this project, because all of it is ANALYST ESTIMATE data and there is none
    here, in any file. Unbuildable, and not to be claimed as tested later:
    forward EPS estimates, forward revenue estimates, forward EPS or revenue
    growth, PEG (it needs forward growth), analyst recommendation or rating
    consensus, analyst count, estimate revisions and revision breadth, and
    earnings surprise. Surprise in particular is not recoverable from filings at
    all: it needs the consensus that stood before the print.
  * Reported EPS. sec_pit.py never requested EarningsPerShareBasic or Diluted,
    so sec_raw does not contain it. Hence the derived EPS above.
  * Full revenue history. The fetch step saved only the FIRST revenue tag it
    found per company out of four candidates and discarded the rest, so a
    company that moved from SalesRevenueNet to Revenues in 2018 has no revenue
    before 2018 here. MMM is one: its revenue facts start in 2016. This is the
    whole reason the revenue features sit near 50-60% coverage while the net
    income and cash flow features reach 80%. Fixing it needs a re-fetch from
    data.sec.gov, which is out of scope for a feature block.
  * Splits cannot be separated from dilution in shares_change_1y. A raw share
    count cannot tell a 20-for-1 split from a 20x issuance, so the tails beyond
    roughly +-100% are splits and share-class retagging rather than dilution;
    GOOGL's +1,859% is the July 2022 split. The body of the distribution is
    genuine buyback and dilution. A sibling block has since written
    cache_long/splits.csv (date, symbol, ratio), which would fix this properly;
    it is deliberately not used here, because this block is specified as
    fundamentals-only and importing another block's output would make the two
    rebuild in a fixed order.
  * Organic and constant-currency growth, segment growth and backlog growth are
    not in XBRL company facts in any usable form.
  * Only 10-K and 10-Q facts are used. An earnings 8-K often makes a number
    public two to four weeks earlier, so these features are LATE rather than
    early. Late is conservative and cannot manufacture lookahead.
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

# the corrected point-in-time quarterly series lives in its own module so any
# other feature block can share one reconstruction instead of inventing another
import pit_quarters as pq
from pit_quarters import (FLOW_METRICS, has_facts, quarterly_panel, tie_out,
                          ttm_sum)

HERE = os.path.dirname(os.path.abspath(__file__))
LONG = os.path.join(HERE, "cache_long")
GRID = os.path.join(LONG, "grid.csv")
OUT = os.path.join(LONG, "feat_growth.csv")

# matching a period to its counterpart one and three years earlier by END DATE
# rather than by (fy, fp) labels. End dates survive fiscal-calendar drift and
# the fy/fp labels in company facts refer to the REPORT, not the period.
YEAR_DAYS, YOY_TOL_DAYS = 365, 45
THREE_YEAR_DAYS, CAGR_TOL_DAYS = 1095, 75
DAYS_PER_YEAR = 365.25

# a growth rate whose newest input filing is older than this has gone stale;
# carrying it forward indefinitely would let a late filer's 2015 growth rate
# sit on a 2020 row. One year plus a generous late-filing allowance.
MAX_STALE_DAYS = 450

# the real-time rebuild audit re-derives every feature for this many randomly
# chosen rows from facts truncated at each row's own date. 250 rows is ~2,250
# feature cells, enough to catch a systematic leak, and costs about half a minute.
AUDIT_ROWS = 250
AUDIT_SEED = 11

FEATURES = [
    "rev_growth_yoy", "rev_growth_ttm", "rev_growth_3y",
    "eps_growth_yoy", "eps_growth_ttm", "eps_growth_3y",
    "cfo_growth_ttm", "shares_change_1y", "ni_growth_ttm",
]
VOID = "__void_"          # prefix for the non-positive-base diagnostic columns
ASOF = "__asof_"          # prefix for the filing date the lag audit checks


# --------------------------------------------------------------------------
# stage 2: growth rates off that panel
# --------------------------------------------------------------------------
def _match_lag(ends: np.ndarray, lag_days: int, tol_days: int) -> np.ndarray:
    """For each period end, the index of the period ending ~lag_days earlier.

    -1 where no period falls inside the tolerance, which is what short history
    or a changed fiscal year end looks like.
    """
    n = len(ends)
    if n == 0:
        return np.zeros(0, dtype=int)
    target = ends - np.timedelta64(lag_days, "D")
    pos = np.searchsorted(ends, target)
    out = np.full(n, -1, dtype=int)
    for i in range(n):
        best, bestd = -1, None
        for j in (pos[i] - 1, pos[i]):
            if 0 <= j < n:
                dd = abs((ends[j] - target[i]) / np.timedelta64(1, "D"))
                if bestd is None or dd < bestd:
                    best, bestd = j, dd
        # a period is never its own prior-year counterpart
        if best >= 0 and bestd is not None and bestd <= tol_days and best != i:
            out[i] = best
    return out


def _take(arr: np.ndarray, idx: np.ndarray, fill):
    """arr[idx] with -1 meaning "no match", which becomes fill."""
    out = np.full(len(idx), fill, dtype=arr.dtype)
    ok = idx >= 0
    out[ok] = arr[idx[ok]]
    return out


def _growth(cur: np.ndarray, base: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Percent change, NaN off a base <= 0, plus the flag for exactly that."""
    cur = np.asarray(cur, dtype=float)
    base = np.asarray(base, dtype=float)
    both = np.isfinite(cur) & np.isfinite(base)
    usable = both & (base > 0)
    voided = both & ~usable
    out = np.full(len(cur), np.nan)
    np.divide(cur, base, out=out, where=usable)
    out = np.where(usable, (out - 1.0) * 100.0, np.nan)
    return out, voided


def _cagr(cur: np.ndarray, base: np.ndarray,
          years: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Annualised growth. Needs BOTH ends > 0: a fractional power of a negative
    ratio is not a real number, so a swing through zero has no CAGR."""
    cur = np.asarray(cur, dtype=float)
    base = np.asarray(base, dtype=float)
    both = np.isfinite(cur) & np.isfinite(base) & np.isfinite(years) & (years > 0)
    usable = both & (base > 0) & (cur > 0)
    voided = both & ~usable
    ratio = np.full(len(cur), np.nan)
    np.divide(cur, base, out=ratio, where=usable)
    out = np.where(usable, (np.power(ratio, 1.0 / np.where(years > 0, years, 1.0))
                            - 1.0) * 100.0, np.nan)
    return out, voided


EMPTY = pd.DataFrame({"asof": pd.Series(dtype="datetime64[ns]"),
                      "end": pd.Series(dtype="datetime64[ns]"),
                      "val": pd.Series(dtype=float),
                      "void": pd.Series(dtype=bool)})


def metric_block(panel: pd.DataFrame, m: str,
                 names: dict[str, str]) -> dict[str, pd.DataFrame]:
    """Growth features for one metric, measured on that metric's OWN quarters.

    The subsetting to rows where m is present is the point, and it was a real bug
    before: the panel index is the UNION of every metric's fiscal quarter ends,
    and a company can end a CFO quarter on 2013-06-28 and a revenue quarter on
    2013-06-30. Matching a prior year on the union then let one metric's
    year-ago slot land on a row belonging to another metric's calendar, which
    silently produced growth rates off mismatched periods. An audit that rebuilt
    features from date-truncated facts caught it, on CSX among others.

    names maps a shape to the output feature name, any subset of
      level_yoy  the raw value against the same quarter a year earlier
      ttm        trailing four quarters against the prior four
      cagr       3-year CAGR of the TTM
    """
    out = {n: EMPTY.copy() for n in names.values()}
    sub = panel[panel[m].notna()]
    if sub.empty:
        return out
    ends = sub.index.to_numpy(dtype="datetime64[ns]")
    val = sub[m].to_numpy(dtype=float)
    filed = sub[f"{m}_filed"].to_numpy(dtype="datetime64[ns]")
    nat = np.datetime64("NaT")
    yoy = _match_lag(ends, YEAR_DAYS, YOY_TOL_DAYS)

    def frame(v, z, filed_cur, idx) -> pd.DataFrame:
        # a feature is known only once EVERY period it used is public, and the
        # base period is normally but not always the earlier filing
        asof = np.maximum(filed_cur, _take(filed_cur, idx, nat))
        # `end` travels with the value because project() needs the fiscal period
        # to break asof ties, and several periods share one filing date
        return pd.DataFrame({"asof": asof, "end": ends, "val": v, "void": z})

    if "level_yoy" in names:
        v, z = _growth(val, _take(val, yoy, np.nan))
        out[names["level_yoy"]] = frame(v, z, filed, yoy)

    if "ttm" in names or "cagr" in names:
        ttm, ttm_filed = ttm_sum(val, filed, ends)
        if "ttm" in names:
            v, z = _growth(ttm, _take(ttm, yoy, np.nan))
            out[names["ttm"]] = frame(v, z, ttm_filed, yoy)
        if "cagr" in names:
            lag3 = _match_lag(ends, THREE_YEAR_DAYS, CAGR_TOL_DAYS)
            # annualise on the ACTUAL elapsed years: the matched period can sit
            # anywhere inside the tolerance, and calling 2.9 years three years
            # overstates the rate
            base_end = _take(ends, lag3, nat)
            years = (ends - base_end) / np.timedelta64(1, "D") / DAYS_PER_YEAR
            v, z = _cagr(ttm, _take(ttm, lag3, np.nan), years)
            out[names["cagr"]] = frame(v, z, ttm_filed, lag3)
    return out


def symbol_features(panel: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Per-feature frames of [asof, val, void], one row per fiscal quarter.

    Every feature carries its OWN asof date, the latest filed date among the
    periods it actually consumed, so a revenue feature is not held back waiting
    on a share count it never used.
    """
    # EPS is derived, so its knowledge date is the later of its two inputs and it
    # is treated as a metric in its own right from here on
    shares = panel["shares"].to_numpy(dtype=float)
    eps = np.divide(panel["net_income"].to_numpy(dtype=float), shares,
                    out=np.full(len(panel), np.nan),
                    where=np.isfinite(shares) & (shares > 0))
    panel = panel.assign(
        eps=eps,
        eps_filed=np.maximum(panel["net_income_filed"].to_numpy("datetime64[ns]"),
                             panel["shares_filed"].to_numpy("datetime64[ns]")))

    out: dict[str, pd.DataFrame] = {}
    out.update(metric_block(panel, "revenue", {"level_yoy": "rev_growth_yoy",
                                               "ttm": "rev_growth_ttm",
                                               "cagr": "rev_growth_3y"}))
    out.update(metric_block(panel, "eps", {"level_yoy": "eps_growth_yoy",
                                           "ttm": "eps_growth_ttm",
                                           "cagr": "eps_growth_3y"}))
    out.update(metric_block(panel, "net_income", {"ttm": "ni_growth_ttm"}))
    out.update(metric_block(panel, "cfo", {"ttm": "cfo_growth_ttm"}))
    out.update(metric_block(panel, "shares", {"level_yoy": "shares_change_1y"}))
    return out


def project(frames: dict[str, pd.DataFrame],
            dates: pd.DatetimeIndex) -> pd.DataFrame:
    """Carry each feature forward to the grid dates by its own asof date.

    merge_asof backward, so a row sees the most recent filing dated on or
    before it and never a later one. The staleness tolerance drops a value
    whose newest input filing is more than MAX_STALE_DAYS old.
    """
    # pandas parses the grid CSV at microsecond resolution while the fact dates
    # are nanosecond; merge_asof refuses to join across the two, so both sides
    # are pinned here rather than wherever the mismatch happens to surface.
    left = pd.DataFrame({"date": pd.DatetimeIndex(dates).sort_values()
                        .as_unit("ns")})
    res = left.copy()
    tol = pd.Timedelta(days=MAX_STALE_DAYS)
    for name, f in frames.items():
        f = f.assign(asof=f["asof"].astype("datetime64[ns]"))
        g = f.dropna(subset=["asof"])
        g = g[g["val"].notna() | g["void"]]
        # Several fiscal periods routinely share one asof date, because a 10-K
        # makes a whole year of comparatives public at once, and only the LATEST
        # of them belongs on the grid. Sorting on asof alone left that to the
        # sort's tie order, which is not stable, so the row that won was
        # arbitrary and the grid could carry a quarter three periods stale. The
        # period end is the tie-break, and it has to be.
        g = g.sort_values(["asof", "end"]).drop_duplicates("asof", keep="last")
        if g.empty:
            res[name] = np.nan
            res[VOID + name] = False
            res[ASOF + name] = pd.NaT
            continue
        g = g.assign(_asof=g["asof"])
        m = pd.merge_asof(left, g.rename(columns={"asof": "date",
                                                  "val": name,
                                                  "void": VOID + name}),
                          on="date", direction="backward", tolerance=tol)
        res[name] = m[name].to_numpy()
        res[VOID + name] = m[VOID + name].fillna(False).to_numpy()
        # kept for the lag audit: the newest filing this value depends on
        res[ASOF + name] = m["_asof"].to_numpy()
    return res.set_index("date")


# --------------------------------------------------------------------------
# stage 3: assemble onto the grid and report
# --------------------------------------------------------------------------
def build() -> tuple[pd.DataFrame, dict]:
    grid = pd.read_csv(GRID, parse_dates=["date"])
    say(f"grid: {len(grid):,} rows, {grid.date.nunique()} dates, "
        f"{grid.symbol.nunique()} symbols, "
        f"{grid.date.min():%Y-%m-%d} .. {grid.date.max():%Y-%m-%d}")

    by_sym = {s: g["date"] for s, g in grid.groupby("symbol", sort=True)}
    pieces, stats = [], {"no_json": [], "no_quarters": [], "quarters": [],
                         "src": {}, "tie": {}}
    for i, (sym, dates) in enumerate(by_sym.items(), 1):
        if not has_facts(sym):
            stats["no_json"].append(sym)
            continue
        panel, src, annual = quarterly_panel(sym)
        for k, v in src.items():
            stats["src"][k] = stats["src"].get(k, 0) + v
        if panel.empty:
            stats["no_quarters"].append(sym)
            continue
        stats["quarters"].append(len(panel))
        tie_out(panel, annual, stats["tie"])
        p = project(symbol_features(panel), pd.DatetimeIndex(dates.unique()))
        p = p.reset_index()
        p.insert(1, "symbol", sym)
        pieces.append(p)
        if i % 100 == 0:
            say(f"  {i}/{len(by_sym)} symbols")

    feat = pd.concat(pieces, ignore_index=True)
    if feat.duplicated(["date", "symbol"]).any():
        raise ValueError("feature frame has duplicate (date, symbol) keys; "
                         "a left merge on it would change the row count")

    out = grid[["date", "symbol"]].merge(feat, on=["date", "symbol"], how="left")
    for c in FEATURES:
        out[VOID + c] = out[VOID + c].fillna(False).astype(bool)
    stats["symbols_used"] = len(pieces)
    stats["n_symbols"] = len(by_sym)
    return out, stats


def report(out: pd.DataFrame, stats: dict) -> None:
    n = len(out)
    say("\nSYMBOL SOURCING")
    say(f"  symbols in grid              {stats['n_symbols']}")
    say(f"  with a quarterly panel       {stats['symbols_used']}")
    if stats["no_json"]:
        say(f"  no sec_raw file              {len(stats['no_json'])} "
            f"{stats['no_json'][:8]}")
    if stats["no_quarters"]:
        say(f"  no discrete quarterly facts  {len(stats['no_quarters'])} "
            f"{stats['no_quarters'][:8]}")
    q = pd.Series(stats["quarters"])
    say(f"  fiscal quarters per symbol   median {q.median():.0f}, "
        f"min {q.min()}, max {q.max()}")

    say("\nWHERE THE QUARTERLY FACTS CAME FROM (quarter-observations, all "
        "symbols)")
    say("  direct = the filing reported that quarter on its own")
    say("  derived = differenced out of two year-to-date figures a quarter apart")
    for m in FLOW_METRICS:
        dr = stats["src"].get(f"{m}:direct", 0)
        dv = stats["src"].get(f"{m}:derived", 0)
        tot = dr + dv
        pct = f"{dv / tot * 100:.0f}%" if tot else "n/a"
        say(f"  {m:<12}{dr:>9,} direct{dv:>10,} derived   ({pct} derived)")
    say("\nXBRL SCALE CLEANING, facts touched")
    say(f"  {'metric':<12}{'repaired':>12}{'rejected':>12}")
    for m in ("revenue", "shares"):
        say(f"  {m:<12}{stats['src'].get(m + ':scale_repaired', 0):>12,}"
            f"{stats['src'].get(m + ':scale_rejected', 0):>12,}")
    say("  net income and cash flow are deliberately NOT cleaned, so their tails")
    say("  in the distribution table below are raw -- see XBRL UNITS ERRORS above")

    say(f"\nPER-FEATURE COVERAGE over the full grid ({n:,} rows)")
    say(f"  {'feature':<18}{'coverage':>10}{'base<=0 rows':>14}{'of grid':>9}"
        f"{'median':>9}{'p10':>8}{'p90':>8}")
    say("  " + "-" * 76)
    for c in FEATURES:
        v = out[c]
        cov = v.notna().mean() * 100
        k = int(out[VOID + c].sum())
        flag = "  <-- THIN" if cov < 50 else ""
        say(f"  {c:<18}{cov:>9.1f}%{k:>14,}{k / n * 100:>8.2f}%"
            f"{v.median():>9.1f}{v.quantile(0.10):>8.1f}"
            f"{v.quantile(0.90):>8.1f}{flag}")
    say("  " + "-" * 76)
    say("  coverage = non-NaN share of grid rows. base<=0 = rows where the "
        "inputs")
    say("  WERE known but the prior-period base was <= 0 (for the 3y CAGRs, "
        "either")
    say("  end <= 0), so the feature was voided to NaN rather than reported as a")
    say("  large positive. At least one feature was voided on "
        f"{int(out[[VOID + c for c in FEATURES]].any(axis=1).sum()):,} rows.")

    say("\nFULL DISTRIBUTIONS, so an absurd value is visible")
    qs = [0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99]
    say(f"  {'feature':<18}{'mean':>9}" + "".join(f"{'p'+str(int(x*100)):>9}"
                                                  for x in qs) + f"{'max':>11}")
    say("  " + "-" * 98)
    for c in FEATURES:
        s = out[c].dropna()
        if s.empty:
            say(f"  {c:<18}  all NaN")
            continue
        vals = "".join(f"{s.quantile(x):>9.1f}" for x in qs)
        say(f"  {c:<18}{s.mean():>9.1f}{vals}{s.max():>11.1f}")

    say("\nCOVERAGE OVER TIME, share of rows with any growth feature")
    yr = out.assign(year=out.date.dt.year)
    any_f = yr[FEATURES].notna().any(axis=1)
    t = yr.assign(any_f=any_f).groupby("year")["any_f"].agg(["mean", "size"])
    for y, r in t.iterrows():
        say(f"  {y}  {r['mean'] * 100:>5.1f}%  of {int(r['size']):>5} rows")

    say("\nTTM CROSS-CHECK: four summed quarters against the ANNUAL figure the "
        "filer")
    say("reported for the same period end -- the test of the year-to-date "
        "differencing,")
    say("because a wrong derived quarter would stop the four from tying.")
    say(f"  {'metric':<12}{'comparisons':>13}{'within 1%':>11}{'within 5%':>11}")
    for m in FLOW_METRICS:
        c = stats["tie"].get(m)
        if not c or not c["n"]:
            say(f"  {m:<12}   no annual facts to compare against")
            continue
        say(f"  {m:<12}{c['n']:>13,}{c['p1'] / c['n'] * 100:>10.1f}%"
            f"{c['p5'] / c['n'] * 100:>10.1f}%")
    say("  a miss is normally a restatement between the quarterly and the annual")
    say("  filing; a LOW rate would mean the differencing is broken and the TTM")
    say("  features should not be used. Reminder: shares_change_1y cannot "
        "separate")
    say("  a split from an issuance, so its tails past +-100% are splits.")


def verify(out: pd.DataFrame) -> None:
    """The grid is the contract; prove the output honours it before shipping."""
    grid = pd.read_csv(GRID, parse_dates=["date"])
    assert len(out) == len(grid), f"row count {len(out)} != grid {len(grid)}"
    assert list(out.columns[:2]) == ["date", "symbol"], "key columns moved"
    same_date = (out["date"].to_numpy() == grid["date"].to_numpy()).all()
    same_sym = (out["symbol"].to_numpy() == grid["symbol"].to_numpy()).all()
    assert same_date and same_sym, "(date, symbol) order does not match the grid"
    assert not out.duplicated(["date", "symbol"]).any(), "duplicate keys"
    assert "fwd63" not in out.columns, "the target must not appear in a feature block"
    say(f"\nVERIFIED: {len(out):,} rows, (date, symbol) identical to the grid "
        "in the same order")


def audit_lag(out: pd.DataFrame) -> None:
    """The no-lookahead proof, in days rather than in prose: for every populated
    cell, how old was the newest filing it depends on? A negative number anywhere
    would mean a filing from the future reached a row, so the minimum is
    asserted, not merely printed.
    """
    say("\nPOINT-IN-TIME LAG AUDIT: days from the newest filing used to the "
        "grid date")
    say(f"  {'feature':<18}{'min':>7}{'p5':>7}{'p25':>7}{'median':>8}"
        f"{'p75':>7}{'p95':>7}{'max':>7}")
    say("  " + "-" * 68)
    worst = None
    for c in FEATURES:
        lag = (out["date"] - out[ASOF + c]).dt.days.dropna()
        if lag.empty:
            say(f"  {c:<18}  no populated cells")
            continue
        worst = lag.min() if worst is None else min(worst, lag.min())
        say(f"  {c:<18}{lag.min():>7.0f}{lag.quantile(.05):>7.0f}"
            f"{lag.quantile(.25):>7.0f}{lag.median():>8.0f}"
            f"{lag.quantile(.75):>7.0f}{lag.quantile(.95):>7.0f}"
            f"{lag.max():>7.0f}")
    say("  " + "-" * 68)
    assert worst is not None and worst >= 0, (
        f"LOOKAHEAD: a feature used a filing dated {worst} days AFTER its row")
    say(f"  minimum lag across every feature and row: {worst:.0f} days "
        "(>= 0, so no row sees a filing it could not have seen)")


def audit_realtime(out: pd.DataFrame, n_rows: int = AUDIT_ROWS) -> None:
    """Rebuild a sample of rows from facts TRUNCATED at the row's own date.

    The lag audit proves no filing dated after a row reached it. This proves the
    stronger thing: that the value on the row is what the same code would have
    produced on the day, knowing only what was filed by then. Any cell where the
    shipped value is populated but the truncated rebuild is EMPTY is lookahead,
    and that count is asserted to be zero.

    It found three real bugs that the lag audit could not see -- a preference for
    directly reported quarters that delayed a whole TTM by a filing cycle, period
    matching done across the union of every metric's fiscal calendar, and an asof
    tie broken by an unstable sort so that an arbitrary, sometimes three-quarters
    stale period won. All three are fixed. What remains is a few percent of cells
    whose value is a STALER reading than a same-day rebuild would give, because a
    period's first disclosure can arrive later than an alternative a real-time
    build would have reached for. Staleness is conservative and cannot leak the
    future, but it is real and it is reported rather than smoothed over.
    """
    original = pq._facts
    cutoff: list = [None]

    def truncated(units: dict) -> list[dict]:
        return [x for x in original(units)
                if x.get("filed") and pd.Timestamp(x["filed"]) <= cutoff[0]]

    pop = out[out[FEATURES].notna().any(axis=1)]
    sample = pop.sample(min(n_rows, len(pop)), random_state=AUDIT_SEED)
    cells = future = stale = 0
    gaps: list[float] = []
    pq._facts = truncated
    try:
        for r in sample.itertuples(index=False):
            cutoff[0] = pd.Timestamp(r.date)
            panel, _, _ = quarterly_panel(r.symbol)
            if panel.empty:
                continue
            live = project(symbol_features(panel),
                           pd.DatetimeIndex([pd.Timestamp(r.date)]))
            for c in FEATURES:
                shipped, rebuilt = getattr(r, c), live[c].iloc[0]
                cells += 1
                if pd.isna(shipped) and pd.isna(rebuilt):
                    continue
                if pd.isna(rebuilt) and not pd.isna(shipped):
                    future += 1
                elif pd.isna(shipped) or not np.isclose(shipped, rebuilt,
                                                        rtol=1e-9, atol=1e-9):
                    stale += 1
                    if not pd.isna(shipped) and not pd.isna(rebuilt):
                        gaps.append(abs(shipped - rebuilt)
                                    / max(abs(rebuilt), 1e-9))
    finally:
        pq._facts = original

    say("\nREAL-TIME REBUILD AUDIT, the check the lag audit cannot do")
    say(f"  rows resampled and rebuilt from date-truncated facts  {len(sample)}")
    say(f"  feature cells compared                               {cells:,}")
    say(f"  cells populated here but EMPTY in the rebuild         {future}"
        "   <-- lookahead")
    say(f"  cells differing, i.e. a staler reading than same-day  {stale}"
        f"  ({stale / max(cells, 1) * 100:.1f}%)")
    if gaps:
        g = np.array(gaps)
        say(f"    relative gap on those: median {np.median(g) * 100:.1f}%, "
            f"p90 {np.quantile(g, 0.9) * 100:.0f}%")
    assert future == 0, (f"LOOKAHEAD: {future} cells carry a value no same-day "
                        "rebuild could produce")
    say("  no cell depends on a filing dated after its row")


def main() -> None:
    out, stats = build()
    verify(out)
    audit_lag(out)
    if "--fast" not in sys.argv:
        audit_realtime(out)
    report(out, stats)
    if "--no-save" not in sys.argv:
        out[["date", "symbol"] + FEATURES].to_csv(OUT, index=False)
        say(f"\nwrote {OUT}")
    else:
        say("\n--no-save: nothing written")


if __name__ == "__main__":
    main()
