"""Point-in-time quarterly fundamentals rebuilt from the raw SEC XBRL facts.

    import pit_quarters as pq
    panel, src, annual = pq.quarterly_panel("MMM")

WHY THIS EXISTS SEPARATELY FROM cache_long/pit_fundamentals.csv
That CSV is not usable for anything that needs a period value. sec_pit.py groups
every XBRL fact by (filed, fp, fy) and keeps the FIRST value it meets per metric;
a fact array is ordered by period end ascending and a filing restates its
comparatives, so "first" is the OLDEST period in the document. The result is a
panel whose flow items are stale by a year on 10-Q rows and two years on 10-K
rows, and whose Q2 and Q3 rows are six- and nine-month cumulatives rather than
quarters. Verified against MMM: the 10-K filed 2011-02-16 reports FY2010 net
income of 4.085e9, and the panel row for that filing carries 3.460e9, which is
FY2008.

sec_raw/*.json carries start, end, filed and form on each individual fact, so the
correct series can be rebuilt from it. This module does that and nothing else, so
any feature block that needs real quarterly fundamentals can share one
reconstruction rather than each inventing its own.

WHAT IT GUARANTEES
  * one row per fiscal quarter end per symbol, with the value AND the date the
    market first learned it, taken from the EARLIEST filing that disclosed the
    period, which is also the original rather than the restated number
  * quarters come either directly from a quarter-length fact or by differencing
    any two year-to-date cumulatives a quarter apart (Q4 = FY - 9M), which is the
    only way to get a quarterly cash flow figure at all
  * thousandfold XBRL tagging errors in revenue and share counts repaired, and
    impossible values rejected, using only facts dated before the one judged
  * nothing anywhere keyed on a period END date as if it were a knowledge date

  * of several candidates for one quarter end, the one that became public
    FIRST wins, so nothing is delayed by a restatement that happened to report
    the same period more tidily later

It reads only sec_raw/ and writes nothing. feat_growth.py audits it by rebuilding
features from date-truncated facts; that audit is what produced the last three
corrections in here, and its comments name them.
"""
from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "sec_raw")

# ---- period classification. A fiscal quarter is 13 weeks, but 52/53-week
# retail calendars and month-end conventions push the span around, so the
# quarter window is deliberately loose on both sides and the annual window
# brackets 52 and 53 weeks plus a few days of drift.
Q_DAYS_MIN, Q_DAYS_MAX = 80, 100
A_DAYS_MIN, A_DAYS_MAX = 345, 385

# four consecutive quarter ends span three quarter gaps, ~273 days. Anything
# outside this means a quarter is missing from the series and the four values
# are not a trailing year.
TTM_SPAN_MIN, TTM_SPAN_MAX = 250, 300

# units-error cleaning, see XBRL UNITS ERRORS above. 20x because no real quarter
# or share count moves that far in one step while every split stays well inside
# it. DECIMAL_TOL is in log10: an offset must land within a factor of five of an
# exact thousandfold, and since the gap between "fine" and "thousandfold wrong"
# is three decades, that slack absorbs seasonality without ever being confused
# for a scale error.
SCALE_TOL = 20.0
SCALE_WINDOW_Q = 9
DECIMAL_STEP = 3.0
DECIMAL_TOL = 0.7

# share counts are sometimes instants dated on the balance-sheet date and
# sometimes cover-page or weighted-average figures dated elsewhere, so the
# series is taken as-of each quarter end with at most one quarter of slack.
SHARES_ASOF_TOL_DAYS = 100

FLOW_METRICS = ("revenue", "net_income", "cfo")
FORMS = ("10-K", "10-Q")

# --------------------------------------------------------------------------
# building the panel
# --------------------------------------------------------------------------
def _facts(units: dict) -> list[dict]:
    """The fact list for the one unit a metric was saved under."""
    if not units:
        return []
    for k in ("USD", "shares"):
        if k in units:
            return units[k]
    return next(iter(units.values()), [])


def _first_disclosure(rows: list[tuple], keys: int) -> pd.DataFrame:
    """Collapse repeated disclosures of the same period to the earliest filing.

    The earliest filing is both the date the market learned the number and the
    ORIGINAL value. A later restatement is not what anyone could have traded
    on, so it is discarded rather than preferred.
    """
    cols = ["start", "end", "val", "filed"] if keys == 2 else ["end", "val", "filed"]
    df = pd.DataFrame(rows, columns=cols)
    if df.empty:
        return df
    # pinned to nanoseconds here rather than wherever a join later objects:
    # pandas parses these strings at microsecond resolution and merge_asof
    # refuses to join across the two units
    for c in (["start", "end", "filed"] if keys == 2 else ["end", "filed"]):
        df[c] = pd.to_datetime(df[c], errors="coerce").astype("datetime64[ns]")
    df = df.dropna(subset=["end", "filed", "val"])
    on = ["start", "end"] if keys == 2 else ["end"]
    df = df.sort_values(["filed"]).drop_duplicates(subset=on, keep="first")
    return df


def _clean_scale(d: pd.DataFrame, by_span: bool) -> tuple[pd.DataFrame, int, int]:
    """Repair thousandfold tagging errors and reject what is still impossible.

      offset within a factor of five of an exact thousandfold  ->  repair
      otherwise more than SCALE_TOL from the reference         ->  reject
      anything else                                            ->  accept

    One sequential pass, each fact judged against the running median of the facts
    ALREADY ACCEPTED before it. The reference is the accepted median rather than
    the raw one because otherwise a rejected value poisons the reference for
    everything after it.

    The pass runs in FILED order, not period-end order. That distinction is the
    whole point: a 10-K restates two years of comparatives, so a fact with an old
    period end can carry a brand new filing date, and walking in end order would
    let a 2016 filing sit in the reference used to judge a 2014 one. Filed order
    guarantees the reference contains only what was public at the time.

    When by_span is true facts are judged inside their own period-length class,
    because a twelve-month figure is four times a three-month one by design.
    """
    if d.empty:
        return d, 0, 0
    d = d.sort_values(["filed", "end"]).copy()
    if by_span:
        # 1 = quarter, 2 = half, 3 = nine months, 4 = full year
        grp = ((d["end"] - d["start"]).dt.days / 91.0).round().clip(1, 4)
    else:
        grp = pd.Series(1, index=d.index)

    vals = d["val"].to_numpy(dtype=float, copy=True)
    keep = np.ones(len(d), dtype=bool)
    fixed = 0
    accepted: dict[float, list[float]] = {}
    for i, (v, g) in enumerate(zip(vals, grp.to_numpy())):
        hist = accepted.setdefault(float(g), [])
        if not np.isfinite(v) or v <= 0:
            keep[i] = False
            continue
        if not hist:                       # nothing to compare against yet
            hist.append(v)
            continue
        ref = float(np.median(hist[-SCALE_WINDOW_Q:]))
        offset = np.log10(v / ref)
        k = round(offset / DECIMAL_STEP)
        if k != 0 and abs(offset - k * DECIMAL_STEP) < DECIMAL_TOL:
            v = v * 10.0 ** (-DECIMAL_STEP * k)
            vals[i] = v
            fixed += 1
        elif max(v / ref, ref / v) > SCALE_TOL:
            keep[i] = False
            continue
        hist.append(v)

    d["val"] = vals
    return d.loc[keep], int((~keep).sum()), fixed


def _quarters(d: pd.DataFrame) -> pd.DataFrame:
    """Discrete fiscal quarters out of a symbol's duration facts, direct where the
    filing gave one and differenced out of year-to-date cumulatives where it did
    not. See HOW THE QUARTERS ARE RECONSTRUCTED above.

    A derived quarter's knowledge date is the LATER of the two cumulatives,
    because you cannot difference a figure you have not seen yet.
    """
    if d.empty:
        return d
    span = (d["end"] - d["start"]).dt.days
    direct = d[(span >= Q_DAYS_MIN) & (span <= Q_DAYS_MAX)].copy()
    direct["src"] = "direct"

    out = [direct]
    # Group on the fiscal-year start: every year-to-date figure in one fiscal year
    # shares it, so any two ends inside a group differ by exactly the periods
    # between them. ALL pairs a quarter apart are emitted, not just consecutive
    # ones. Consecutive-only was fragile in a way that mattered: a later 10-K can
    # restate a comparative and insert an end BETWEEN two ends already present,
    # which broke the pair they used to form and made a quarter that was
    # available in real time disappear from the series. All pairs cannot lose a
    # candidate that way -- a late filing only ever adds one -- and since each
    # candidate carries the later of its two filing dates, the dedup below still
    # picks whichever became public first.
    for _, g in d.sort_values(["start", "end"]).groupby("start", sort=False):
        if len(g) < 2:
            continue
        e = g["end"].to_numpy("datetime64[ns]")
        v = g["val"].to_numpy(dtype=float)
        f = g["filed"].to_numpy("datetime64[ns]")
        gap = (e[None, :] - e[:, None]) / np.timedelta64(1, "D")
        i, j = np.nonzero((gap >= Q_DAYS_MIN) & (gap <= Q_DAYS_MAX))
        if not len(i):
            continue
        out.append(pd.DataFrame({
            "start": e[i], "end": e[j], "val": v[j] - v[i],
            "filed": np.maximum(f[i], f[j]), "src": "derived",
        }))

    q = pd.concat(out, ignore_index=True).dropna(subset=["val", "filed"])
    # EARLIEST disclosure wins, with a direct fact breaking a same-day tie.
    # Preferring direct outright looked tidier and was wrong: when a 10-Q gave
    # only cumulatives and the next 10-K supplied the discrete quarter, it made
    # the quarter look unknown until the 10-K, which delayed the whole TTM by a
    # filing cycle and quietly swapped in the 10-K's restated figure. An audit
    # rebuilding features from facts truncated at each row's own date caught it:
    # the truncated rebuild had values where the full one did not.
    # concat of the direct and derived frames can land on a different
    # datetime resolution; pin it so the asof joins downstream agree
    q["end"] = pd.to_datetime(q["end"]).astype("datetime64[ns]")
    q["filed"] = pd.to_datetime(q["filed"]).astype("datetime64[ns]")
    q["_rank"] = (q["src"] == "derived").astype(int)
    q = q.sort_values(["end", "filed", "_rank"]).drop_duplicates("end", keep="first")
    return q.drop(columns="_rank")


def has_facts(sym: str) -> bool:
    """Whether raw XBRL facts were ever fetched for this symbol. Separate from
    quarterly_panel so a caller can tell "never fetched" from "fetched but no
    usable quarters" in its coverage report."""
    return os.path.exists(os.path.join(RAW, f"{sym}.json"))


def quarterly_panel(sym: str) -> tuple[pd.DataFrame, dict, dict]:
    """One row per fiscal quarter end: the metric values and, for each, the date
    that value became public. Also returns the symbol's directly reported ANNUAL
    figures, which are never used as features and exist only for the TTM tie-out.
    Empty frame when the symbol has no quarters."""
    path = os.path.join(RAW, f"{sym}.json")
    if not os.path.exists(path):
        return pd.DataFrame(), {}, {}
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        doc = json.load(fh)
    facts = doc.get("facts", {})

    parts: dict[str, pd.DataFrame] = {}
    annual: dict[str, pd.Series] = {}
    src: dict[str, int] = {}
    for m in FLOW_METRICS:
        rows = []
        for x in _facts(facts.get(m)):
            if x.get("form") not in FORMS or not x.get("start") or not x.get("end"):
                continue
            rows.append((x["start"], x["end"], x.get("val"), x.get("filed")))
        d = _first_disclosure(rows, keys=2)
        # the scale filter runs on the CUMULATIVE facts, before differencing,
        # so a mis-scaled nine-month figure cannot contaminate the Q4 derived
        # from it; the quarter is simply unavailable, which is the truth
        if m == "revenue":
            d, nbad, nfix = _clean_scale(d, by_span=True)
            src["revenue:scale_rejected"] = nbad
            src["revenue:scale_repaired"] = nfix
        if d.empty:
            continue
        # the annual facts are not features; they are kept only so the TTM sums
        # can be checked against a figure the filer stated directly
        span = (d["end"] - d["start"]).dt.days
        ann = d[(span >= A_DAYS_MIN) & (span <= A_DAYS_MAX)]
        annual[m] = ann.set_index("end")["val"].groupby(level=0).last()
        d = _quarters(d)
        if d.empty:
            continue
        for k, v in d["src"].value_counts().items():
            src[f"{m}:{k}"] = int(v)
        parts[m] = d.set_index("end")[["val", "filed"]].rename(
            columns={"val": m, "filed": f"{m}_filed"})

    # no metric requires any other: a bank whose net income is never tagged as a
    # plain duration fact (TFC) still has usable cash-flow and share-count
    # growth, and dropping the symbol entirely would hide that
    if not parts:
        return pd.DataFrame(), src, annual
    panel = None
    for m in FLOW_METRICS:
        if m in parts:
            panel = parts[m] if panel is None else panel.join(parts[m], how="outer")
    panel = panel.sort_index()

    shares, (nbad, nfix) = _shares_asof(facts.get("shares"), panel.index)
    src["shares:scale_rejected"] = nbad
    src["shares:scale_repaired"] = nfix
    panel = panel.join(shares, how="left")
    # a metric absent for this symbol still needs its pair of columns, and an
    # all-missing join leaves object dtype, which numpy will not read as dates
    blank = pd.Series(np.nan, index=panel.index)
    for c in ("revenue", "net_income", "cfo", "shares"):
        panel[c] = pd.to_numeric(
            panel[c] if c in panel.columns else blank, errors="coerce")
        fc = f"{c}_filed"
        panel[fc] = pd.to_datetime(
            panel[fc] if fc in panel.columns else blank,
            errors="coerce").astype("datetime64[ns]")
    return panel, src, annual


def _shares_asof(units: dict,
                 qends: pd.DatetimeIndex) -> tuple[pd.DataFrame, tuple[int, int]]:
    """Share count known as of each quarter end, joined backward with a quarter of
    slack because cover-page instants are dated after the balance-sheet date."""
    empty = pd.DataFrame(index=qends, columns=["shares", "shares_filed"])
    rows = []
    for x in _facts(units):
        if x.get("form") not in FORMS or not x.get("end"):
            continue
        rows.append((x["end"], x.get("val"), x.get("filed")))
    d = _first_disclosure(rows, keys=1)
    if d.empty:
        return empty, (0, 0)
    d = d.sort_values("end").drop_duplicates("end", keep="first")
    # stray share counts sit several orders of magnitude off (KO has 4,255
    # against a true 4.3bn, ICE has 1 and 0); a count cannot move like that
    d, nbad, nfix = _clean_scale(d.assign(start=d["end"]), by_span=False)
    if d.empty:
        return empty, (nbad, nfix)
    # the count dated CLOSEST BEFORE the quarter end, not the one that happened to
    # be published first. Tried the other way round and it was much worse: a ratio
    # needs both of its ends measured at the same offset from their quarter end,
    # and choosing by filing date lets one end sit at the quarter end and the
    # other a quarter before it, which turns a buyback into noise.
    d = d.sort_values("end")      # _clean_scale returns filed order; asof needs end
    left = pd.DataFrame({"end": pd.DatetimeIndex(qends).as_unit("ns")}
                        ).sort_values("end")
    out = pd.merge_asof(left, d.rename(columns={"val": "shares",
                                                "filed": "shares_filed"}),
                        on="end", direction="backward",
                        tolerance=pd.Timedelta(days=SHARES_ASOF_TOL_DAYS))
    return out.set_index("end")[["shares", "shares_filed"]], (nbad, nfix)


def ttm_sum(val: np.ndarray, filed: np.ndarray,
         ends: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Trailing four quarters, summed, and the date the fourth one became
    public. NaN unless all four quarters are present AND their end dates span a
    single year; a gap in the series means the four values are not a year."""
    n = len(val)
    tot = pd.Series(val).rolling(4, min_periods=4).sum().to_numpy()
    # max of the four filed dates, because a prior quarter can be disclosed
    # late. pandas cannot roll a max over datetime64, so this shifts the int64
    # view instead; NaT is int64 min there and so never wins a maximum, which
    # is harmless because a present value always carries a present filed date.
    fi = filed.astype("datetime64[ns]").view("int64")
    fmax_i = fi.copy()
    for k in (1, 2, 3):
        if n > k:
            fmax_i[k:] = np.maximum(fmax_i[k:], fi[:-k])
    fmax = fmax_i.view("datetime64[ns]")
    span = np.full(n, np.nan)
    if n >= 4:
        span[3:] = (ends[3:] - ends[:-3]) / np.timedelta64(1, "D")
    ok = np.isfinite(tot) & (span >= TTM_SPAN_MIN) & (span <= TTM_SPAN_MAX)
    return np.where(ok, tot, np.nan), np.where(ok, fmax, np.datetime64("NaT"))


def tie_out(panel: pd.DataFrame, annual: dict, acc: dict) -> None:
    """Accumulate how often four summed quarters equal the reported annual figure.

    The only independent check available on the differencing: the filer states a
    twelve-month number directly and four correct quarters must reproduce it.
    Compared only where the annual period ends on the TTM window's own end date.
    """
    ends = panel.index.to_numpy(dtype="datetime64[ns]")
    for m in FLOW_METRICS:
        a = annual.get(m)
        if a is None or a.empty or m not in panel.columns:
            continue
        ttm, _ = ttm_sum(panel[m].to_numpy(dtype=float),
                      panel[f"{m}_filed"].to_numpy("datetime64[ns]"), ends)
        ref = pd.Series(a.to_numpy(dtype=float),
                        index=pd.DatetimeIndex(a.index)).reindex(panel.index)
        r = ref.to_numpy(dtype=float)
        both = np.isfinite(ttm) & np.isfinite(r) & (np.abs(r) > 0)
        if not both.any():
            continue
        err = np.abs(ttm - r)[both] / np.abs(r)[both]
        c = acc.setdefault(m, {"n": 0, "p1": 0, "p5": 0})
        c["n"] += int(both.sum())
        c["p1"] += int((err <= 0.01).sum())
        c["p5"] += int((err <= 0.05).sum())
