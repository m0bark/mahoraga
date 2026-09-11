"""Unadjusted daily closes for the S&P 500, the price a market cap needs.

    python research/sheet/fetch_raw_px.py            # download, verify, write

Re-running is cheap and safe: the existing CSV is read first and only symbols
that are missing or all-NaN are fetched again, so a rate-limited run is repaired
by running it a second time rather than re-downloading 500 good columns.

WHY THIS FILE EXISTS
cache_long/px_close.csv is TOTAL-RETURN adjusted: every past close is divided
by the cumulative split AND dividend factor running from that date to the end
of the file. That is the right series for a return, where the factor cancels in
a ratio of two prices, and the wrong series for a market cap, where the price
is multiplied by an as-reported share count. feat_val.py did exactly that and
understated NVDA's 2013 market cap by 61x, AAPL's by 33x, T's by 2.9x -- an
error equal to each name's own future corporate actions, so largest for the
names that went up most. That is lookahead dressed as a cheap valuation.

WHAT "UNADJUSTED" MEANS HERE, AND WHY auto_adjust=False IS NOT ENOUGH
Yahoo's chart API serves two close series and NEITHER is the traded price:

  Adj Close  split- and dividend-adjusted       (auto_adjust=True)
  Close      split-adjusted, dividends intact   (auto_adjust=False)

Measured: AAPL 2013-04-30 comes back as 15.8136 under auto_adjust=False. The
price that actually printed was 442.78, and 15.8136 * 7 * 4 = 442.78 exactly --
the 7:1 of June 2014 and the 4:1 of August 2020, and EXACTLY, which also proves
no dividend has been taken out of it. So Close must still be multiplied back up
by the splits that happened AFTER each date:

    raw_close[t] = close[t] * prod(ratio of every split dated strictly > t)

The splits arrive in the same request (actions=True), so the factor is built
from the same response rather than a second source that could disagree with it.
A split dated on t has already happened in t's own price, hence the strict >.
Splits before the download window cannot affect a price inside it, and splits
after today do not exist yet, so the in-window action history is sufficient --
this is not a case of needing future information, it is recovering a number the
market printed.

SPINOFFS RIDE IN THE SPLIT COLUMN, AND THAT IS WANTED HERE
Yahoo records a large spinoff as a split. T carries a 1.324 "split" on
2022-04-11, which is the Warner Bros Discovery separation, not a share
division: T's 2013-04-30 Close is served as 28.2931 and the price that printed
was 37.46 = 28.2931 * 1.324. Multiplying it back is still correct for this
file's purpose, because the goal is the price that traded against the share
count of the day, and on that day the shares included the spun-off business.
Such ratios are not round numbers, so they are listed separately in the report
rather than hidden among the 2:1s -- they are the rows where "unadjusted" is a
judgement rather than arithmetic.

WHAT IS WRITTEN
cache_long/px_raw_close.csv, the same shape as px_close.csv: index "Date",
one column per symbol, values the as-traded close in the currency of the day.

WHAT I COULD NOT BUILD
  * History for names that left the index. sp500.csv is CURRENT membership, so
    a name delisted before today is absent from it and from this file. The grid
    was built from the same list, so nothing downstream asks for a symbol this
    file does not try to fetch.
  * History for names that joined too recently to have any. FDXF (FedEx
    Freight, added 2026-06-01) has no price series at all and is reported as a
    failure rather than quietly dropped. It is not in the grid.
  * Currency redenominations and ticker changes. Yahoo serves one continuous
    series per CURRENT ticker; a pre-change price under an old ticker is not
    recoverable here.
  * A share-count series. This file is prices only. The share count still comes
    from SEC filings, which is where the remaining market-cap error lives.
"""
from __future__ import annotations

import io
import os
import sys
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
import yfinance as yf

HERE = os.path.dirname(os.path.abspath(__file__))
LONG = os.path.join(HERE, "cache_long")
SP500 = os.path.join(HERE, "sp500.csv")
OUT = os.path.join(LONG, "px_raw_close.csv")
# the split events themselves, long form. feat_val2.py needs them for a reason
# this file does not: an SEC share count filed BEFORE a split is a pre-split
# count, and pairing it with a post-split unadjusted price understates the market
# cap by the split ratio. Writing them here keeps one source of truth for
# corporate actions instead of two that can disagree.
SPLITS = os.path.join(LONG, "splits.csv")

# the grid starts 2013-04-30 but feature blocks need years of prior history for
# trailing windows, and pit_fundamentals reaches back further
START = "2009-12-01"

BATCH = 50                  # tickers per request on the first pass
REPAIR_BATCH = 10           # smaller on repair passes: a rate limit rejects a
                            # whole request, so a small request loses less
REPAIR_PASSES = 4
MAX_ATTEMPTS = 3
SLEEP_BETWEEN = 1.5         # seconds between requests
SLEEP_REPAIR = 6.0          # between requests on a repair pass
SLEEP_BACKOFF = 5.0         # multiplied by the attempt number after a failure

NO_SPLIT = 1.0              # the identity ratio for a day with no split
PCT = 100.0
HALF = 0.5

# A genuine share division is a round ratio. Anything else in the split column
# is a spinoff or a restructuring, which is reported separately -- see the
# docstring. The tolerance is on the distance to the nearest half-integer.
ROUND_RATIO_TOL = 0.01

# As-traded closes, each independently known and NOT derived from this
# pipeline. These are the regression test: a split-adjusted series fails every
# one of them by its own cumulative split factor, so it cannot pass by luck.
# Deliberately all names with a real split in the window, because a name that
# never split has nothing to get wrong -- those are covered by NO_ACTION_EXACT.
KNOWN_CLOSES: dict[tuple[str, str], float] = {
    ("NVDA", "2013-04-30"): 13.77,     # 40x: the 2021 4:1 and 2024 10:1
    ("AAPL", "2013-04-30"): 442.78,    # 28x: the 2014 7:1 and 2020 4:1
    ("AMZN", "2013-04-30"): 253.81,    # 20x: the 2022 20:1
    ("KLAC", "2024-12-31"): 629.70,    # 10x, the case feat_val.py logged
    ("NFLX", "2013-04-30"): 216.93,    # 70x: the 2015 7:1 and 2025 10:1
}
KNOWN_TOLERANCE = 0.02              # 2%: third-party closes, not the tape

# Names with no corporate action in the window. For these Yahoo's Close IS the
# traded price, so the correction must be exactly the identity. This catches a
# factor accidentally applied to the wrong column or shifted by a row. Two
# names that look like they belong and do not: IBM carries the 2021 Kyndryl
# spinoff as a 1.046 split, and WMT split 3:1 in February 2024.
NO_ACTION_EXACT = ["MSFT", "JNJ", "XOM", "PG", "MCD", "HD"]


def universe() -> list[str]:
    return sorted(pd.read_csv(SP500)["symbol"].dropna().unique().tolist())


def load_existing() -> pd.DataFrame:
    """Whatever a previous run managed to write, so a repair run is cheap."""
    if not os.path.exists(OUT):
        return pd.DataFrame()
    df = pd.read_csv(OUT, index_col=0, parse_dates=True)
    df.index = pd.to_datetime(df.index)
    usable = [c for c in df.columns if df[c].notna().sum() > 0]
    return df[usable]


def _fields(raw: pd.DataFrame, batch: list[str]) -> tuple[pd.DataFrame,
                                                          pd.DataFrame]:
    """Pull Close and Stock Splits out of one download response.

    yfinance collapses the ticker level when a batch has one name, so a Series
    is widened back into a one-column frame rather than special-cased later.
    """
    got = []
    for field in ("Close", "Stock Splits"):
        f = raw[field] if field in raw else pd.DataFrame(index=raw.index)
        if isinstance(f, pd.Series):
            f = f.to_frame(batch[0])
        got.append(f)
    return got[0], got[1]


def download(symbols: list[str]) -> tuple[pd.DataFrame, pd.DataFrame,
                                          list[str]]:
    """Split-adjusted closes and split events, plus the symbols that failed.

    Three layers of retry, because the only observed failure mode is a rate
    limit that rejects an entire request: attempts inside a batch, then the
    batch broken into single symbols, then whole repair passes with smaller
    requests and longer gaps. Whatever still fails is RETURNED, never
    swallowed, so the caller can report it and the column stays absent.
    """
    closes: list[pd.DataFrame] = []
    splits: list[pd.DataFrame] = []

    def attempt(batch: list[str], pause: float) -> bool:
        for n in range(MAX_ATTEMPTS):
            try:
                raw = yf.download(batch, start=START, auto_adjust=False,
                                  actions=True, progress=False, threads=True,
                                  group_by="column")
            except Exception as e:                    # noqa: BLE001
                say(f"    {batch[0]}..{batch[-1]} try {n + 1}: "
                    f"{type(e).__name__}: {e}")
                time.sleep(SLEEP_BACKOFF * (n + 1))
                continue
            if raw.empty or "Close" not in raw:
                time.sleep(SLEEP_BACKOFF * (n + 1))
                continue
            c, s = _fields(raw, batch)
            # a request can return a frame whose columns are all empty; those
            # symbols have not actually been fetched
            keep = [x for x in c.columns if c[x].notna().sum() > 0]
            if not keep:
                time.sleep(SLEEP_BACKOFF * (n + 1))
                continue
            closes.append(c[keep])
            splits.append(s.reindex(columns=keep))
            time.sleep(pause)
            return len(keep) == len(batch)
        return False

    def done() -> set[str]:
        return {c for f in closes for c in f.columns}

    todo = list(symbols)
    size, pause = BATCH, SLEEP_BETWEEN
    for p in range(REPAIR_PASSES + 1):
        if not todo:
            break
        if p:
            say(f"  repair pass {p}: {len(todo)} symbols still missing")
            size, pause = REPAIR_BATCH, SLEEP_REPAIR
        for i in range(0, len(todo), size):
            batch = todo[i:i + size]
            if not attempt(batch, pause) and len(batch) > 1:
                for sym in batch:                     # isolate the bad ticker
                    attempt([sym], pause)
            say(f"  pass {p}: {min(i + size, len(todo))}/{len(todo)}")
        todo = [s for s in todo if s not in done()]

    close = pd.concat(closes, axis=1) if closes else pd.DataFrame()
    split = pd.concat(splits, axis=1) if splits else pd.DataFrame()
    close = close.loc[:, ~close.columns.duplicated()].sort_index()
    split = split.loc[:, ~split.columns.duplicated()].sort_index()
    return close, split, sorted(todo)


def split_factor(split: pd.DataFrame, index: pd.DatetimeIndex) -> pd.DataFrame:
    """factor[t, sym] = product of every split ratio dated strictly after t.

    Built by reverse-cumulative-producting the ratio column and shifting one
    row forward, which drops t's own split -- the price on an ex-date already
    reflects that split.
    """
    s = split.reindex(index).fillna(0.0)
    s = s.where(s > 0, NO_SPLIT)              # 0 and NaN both mean "no split"
    rev = s.iloc[::-1].cumprod().iloc[::-1]   # prod over u >= t
    return rev.shift(-1).fillna(NO_SPLIT)     # prod over u >  t


def _is_round(r: pd.Series) -> pd.Series:
    """True where the ratio is a whole or half share division (2, 3, 1.5, 7)."""
    return ((r * 2).round() - r * 2).abs() < ROUND_RATIO_TOL


def report_splits(split: pd.DataFrame, factor: pd.DataFrame) -> None:
    """Which names the correction moves, how much, and which of those moves is
    a real share division rather than a spinoff wearing a split's clothes."""
    first = factor.iloc[0].sort_values(ascending=False)
    moved = first[first > NO_SPLIT + ROUND_RATIO_TOL]
    say(f"\nSPLIT CORRECTION -- factor at the start of the file "
        f"({factor.index[0]:%Y-%m-%d})")
    say(f"  symbols with at least one event since then: {len(moved)} of "
        f"{len(first)}")
    say(f"  {'symbol':<10}{'factor':>10}")
    say("  " + "-" * 20)
    for sym, v in moved.head(12).items():
        say(f"  {sym:<10}{v:>9.1f}x")
    if len(moved) > 12:
        say(f"  ... {len(moved) - 12} more, smallest {moved.min():.2f}x")

    ev = split.where(split > 0).stack(future_stack=True).dropna()
    ev = ev.rename("ratio").reset_index()
    ev.columns = ["date", "symbol", "ratio"]
    # A real split is a round or half-integer ratio, and a real REVERSE split is
    # the reciprocal of one (C's 1:10 arrives as 0.1, DUK's 1:3 as 0.3333), so
    # both directions are tested. What survives is a spinoff.
    odd = ev[~(_is_round(ev["ratio"]) | _is_round(1.0 / ev["ratio"]))]
    say(f"\n  NON-ROUND RATIOS ({len(odd)} of {len(ev)} events) -- spinoffs and")
    say("  restructurings, multiplied back for the reason in the docstring")
    for _, r in odd.sort_values("date").iterrows():
        say(f"    {r['symbol']:<8}{r['date']:%Y-%m-%d}  {r['ratio']:.4f}")


def verify(raw: pd.DataFrame) -> int:
    """Two checks: known traded closes, and exactness where nothing happened.

    The split-adjusted comparison series is re-fetched here for the dozen
    verification symbols only, rather than reused from the download pass, so the
    check tests what is ACTUALLY IN THE FILE even when most columns were resumed
    from disk and never re-downloaded in this run.
    """
    syms = sorted({s for s, _ in KNOWN_CLOSES} | set(NO_ACTION_EXACT))
    ref = yf.download(syms, start=START, auto_adjust=False, actions=True,
                      progress=False, threads=True, group_by="column")
    adj, rsplit = _fields(ref, syms)
    adj.index = pd.to_datetime(adj.index).tz_localize(None)
    rsplit.index = adj.index
    factor = split_factor(rsplit.reindex(columns=adj.columns), adj.index)

    say("\nVERIFICATION against independently known as-traded closes")
    say(f"  {'symbol':<8}{'date':<13}{'stored':>12}{'known':>12}{'err':>8}"
        f"{'split-adj':>12}")
    say("  " + "-" * 65)
    bad = 0
    for (sym, date), known in KNOWN_CLOSES.items():
        ts = pd.Timestamp(date)
        if sym not in raw.columns or ts not in raw.index:
            say(f"  {sym:<8}{date:<13}{'NOT IN FILE':>12}")
            bad += 1
            continue
        got, old = raw.at[ts, sym], adj.at[ts, sym]
        err = abs(got / known - 1.0)
        bad += int(err > KNOWN_TOLERANCE)
        say(f"  {sym:<8}{date:<13}{got:>12,.2f}{known:>12,.2f}"
            f"{err * PCT:>7.1f}%{old:>12,.2f}"
            f"{'' if err <= KNOWN_TOLERANCE else '   <-- WRONG'}")
    say("  " + "-" * 65)
    say("  'split-adj' is the auto_adjust=False Close before the correction --")
    say("  what a naive fetch would have stored.")

    say("\n  EXACTNESS where no corporate action occurred (factor must be 1.0)")
    for sym in NO_ACTION_EXACT:
        if sym not in raw.columns:
            say(f"    {sym:<8}NOT IN FILE")
            bad += 1
            continue
        # the two frames come from different requests and so have different
        # row sets; compare only the dates and values both of them have
        a, b = raw[sym].align(adj[sym], join="inner")
        both = a.notna() & b.notna()
        # the final bar is the CURRENT session and moves between two requests
        # seconds apart, so comparing it measures the tape, not this code
        both &= both.index < both.index.max()
        f = factor[sym]
        same = bool(both.any()) and np.allclose(a[both], b[both])
        ok = bool(f.eq(NO_SPLIT).all()) and same
        bad += int(not ok)
        say(f"    {sym:<8}factor min {f.min():.4f} max {f.max():.4f}  "
            f"identical to Close on {int(both.sum()):,} days: {same}"
            f"{'' if ok else '   <-- WRONG'}")
    return bad


def fetch_splits(symbols: list[str]) -> pd.DataFrame:
    """Long (date, symbol, ratio) of every split event, for the whole universe.

    A separate pass rather than a by-product of the price download, because the
    resume path means most price columns are never re-fetched in a given run and
    the action history would then cover only the few symbols that were.
    """
    rows: list[pd.DataFrame] = []
    for i in range(0, len(symbols), BATCH):
        batch = symbols[i:i + BATCH]
        for n in range(MAX_ATTEMPTS):
            try:
                raw = yf.download(batch, start=START, auto_adjust=False,
                                  actions=True, progress=False, threads=True,
                                  group_by="column")
            except Exception as e:                    # noqa: BLE001
                say(f"    splits {batch[0]}..{batch[-1]} try {n + 1}: "
                    f"{type(e).__name__}")
                time.sleep(SLEEP_BACKOFF * (n + 1))
                continue
            if raw.empty or "Stock Splits" not in raw:
                time.sleep(SLEEP_BACKOFF * (n + 1))
                continue
            _, s = _fields(raw, batch)
            s.index = pd.to_datetime(s.index).tz_localize(None)
            ev = s.where(s > 0).stack(future_stack=True).dropna()
            if len(ev):
                ev = ev.rename("ratio").reset_index()
                ev.columns = ["date", "symbol", "ratio"]
                rows.append(ev)
            break
        time.sleep(SLEEP_BETWEEN)
        say(f"  splits {min(i + BATCH, len(symbols))}/{len(symbols)}")
    ev = (pd.concat(rows) if rows else
          pd.DataFrame(columns=["date", "symbol", "ratio"]))
    return ev.drop_duplicates(["date", "symbol"]).sort_values(["symbol", "date"])


def report_coverage(raw: pd.DataFrame, failed: list[str]) -> None:
    say("\nCOVERAGE")
    say(f"  shape {raw.shape[0]:,} days x {raw.shape[1]} symbols")
    say(f"  {raw.index.min():%Y-%m-%d} .. {raw.index.max():%Y-%m-%d}")
    nz = raw.notna().sum()
    say(f"  non-null closes: {int(nz.sum()):,}")
    say(f"  symbols with a full history: {int((nz == nz.max()).sum())}")
    thin = nz[nz < len(raw) * HALF]
    say(f"  symbols with under half the days (a later listing, mostly): "
        f"{len(thin)}")
    if len(thin):
        say("    " + ", ".join(f"{s}({n})" for s, n in
                               thin.sort_values().head(20).items()))
    say(f"  FAILED, no column written: "
        f"{', '.join(failed) if failed else 'none'}")


def main() -> None:
    syms = universe()
    have = load_existing()
    todo = [s for s in syms if s not in have.columns]
    say(f"UNADJUSTED CLOSES: {len(syms)} symbols from {START}")
    say(f"  already on disk and usable: {have.shape[1]}")
    say(f"  to download: {len(todo)}")

    close, split, failed = download(todo) if todo else (
        pd.DataFrame(), pd.DataFrame(), [])

    if not close.empty:
        close.index = pd.to_datetime(close.index).tz_localize(None)
        split = split.reindex(columns=close.columns)
        split.index = pd.to_datetime(split.index).tz_localize(None)
        factor = split_factor(split, close.index)
        fresh = (close * factor).where(close * factor > 0)
        report_splits(split, factor)
    else:
        say("\nnothing new to download")
        fresh = pd.DataFrame()

    raw = (pd.concat([have, fresh], axis=1) if not have.empty else fresh)
    if raw.empty:
        say("nothing to write")
        sys.exit(1)
    raw = raw.loc[:, ~raw.columns.duplicated()].sort_index()
    raw = raw.reindex(columns=sorted(raw.columns))
    raw.index.name = "Date"

    report_coverage(raw, failed)
    bad = verify(raw)
    raw.to_csv(OUT)
    say(f"\nwrote {OUT}  ({raw.shape[0]:,} days x {raw.shape[1]} symbols)")

    if not os.path.exists(SPLITS):
        say(f"\nSPLIT EVENTS for the whole universe -> {SPLITS}")
        ev = fetch_splits(syms)
        ev.to_csv(SPLITS, index=False)
        say(f"wrote {SPLITS}  ({len(ev)} events, "
            f"{ev['symbol'].nunique()} symbols)")
    else:
        say(f"\n{SPLITS} already present, left alone")
    if bad:
        say(f"\n{bad} VERIFICATION FAILURES -- do not build valuation on this")
        sys.exit(1)


if __name__ == "__main__":
    main()
