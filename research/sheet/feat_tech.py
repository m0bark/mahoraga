"""Technical / price-derived feature block for the point-in-time feature matrix.

    python research/sheet/feat_tech.py            # build, report, write the CSV
    python research/sheet/feat_tech.py --dry      # build and report, write nothing

WHAT THIS BLOCK IS
One row per (date, symbol) in cache_long/grid.csv, in the grid's own order, no
rows added and none dropped. Every column is derived from px_close / px_high /
px_low / px_volume only. No fundamentals, no index membership, no target.

NO LOOKAHEAD
Each feature is a rolling or expanding statistic evaluated AT the grid date, so
the value on row (d, s) is a function of rows <= d of the price panel and
nothing else. The panel is never shifted backwards, the grid date is never
advanced, and fwd63 is not read. The one place this needs stating explicitly is
`change_1d`: it is the return from the prior close INTO the close of d, which is
known at the close of d, not the day after.

THE FEATURES
  dist_sma20/50/200   close divided by the n-day simple moving average of the
                      close, minus one, in percent. Positive = above the average.
  sma50_over_200      1.0 when the 50d SMA is strictly above the 200d SMA, 0.0
                      when it is not, NaN when either average is unavailable.
                      Never 0.0 as a stand-in for "unknown".
  rsi14               Wilder's RSI. Wilder's smoothing is the recursive average
                      prev * (n-1)/n + today/n, seeded with the first complete
                      14-day simple average of gains and of losses -- not an
                      ewm() seeded on the first observation, which is the usual
                      shortcut and is wrong for the first few months of a
                      newly listed name.
  atr14_pct           Wilder ATR over 14 days as a percent of the close. True
                      range is max(high-low, |high-prev close|, |low-prev
                      close|), so it includes overnight gaps.
  vol20/60/252        annualised realised volatility: sample standard deviation
                      of daily simple returns over the window, times sqrt(252),
                      in percent.
  beta252             252-day OLS beta of daily simple returns against SPY,
                      computed as cov(r_i, r_spy) / var(r_spy) from rolling
                      moments. SPY IS present as a column of px_close.csv, so
                      the equal-weight-universe fallback the brief allows is not
                      needed and is not implemented.
  pos_20d/50d/52w     where the close sits in the high/low range of the window,
                      0 = at the low, 100 = at the high. The range uses the
                      INTRADAY extremes (rolling max of px_high, rolling min of
                      px_low), which is what a screener's "52-week high" means.
  pos_alltime         the same measure over all history available on that date.
                      "All time" is bounded by this dataset, which starts
                      2010-01-04; for a name that listed before then it is a
                      since-2010 position, not a true all-time one.
  dd_52w              percent below the 52-week intraday high. <= 0 by
                      construction.
  off_low_60          percent above the 60-day intraday low. >= 0 by
                      construction.
  perf_1w/1m/3m/6m/1y trailing simple returns in percent over 5 / 21 / 63 / 126
                      / 252 TRADING days. Trading days, not calendar months, so
                      the windows line up with the rest of the block.
  change_1d           one-day percent change of the close.
  rel_volume          mean volume over 20 days divided by mean volume over 60
                      days. > 1 means volume is picking up.
  avg_volume_20       mean daily volume over 20 days, in shares.
  dollar_vol_60       mean of close * volume over 60 days, in dollars.
  price               the close on the grid date.

WHAT COULD NOT BE BUILT
  Gap and Change-from-Open. Both need the opening price, and cache_long has no
  open-price file -- only close, high, low and volume. Substituting the previous
  close for the open would make Gap identically zero and Change-from-Open a
  duplicate of change_1d, so neither is emitted. If px_open.csv ever lands they
  are two lines of code.

THE ONE LOOKAHEAD CHANNEL I COULD NOT CLOSE -- READ THIS BEFORE USING price,
avg_volume_20 OR dollar_vol_60
  px_close.csv and px_volume.csv are ADJUSTED series. Verified, not assumed:
  NVDA's close on 2013-04-30 reads 0.3192 against a volume of 276,712,000,
  which is the 2013 price divided by the 40x of splits that happened in 2021
  and 2024 and the share count multiplied by the same 40x. T's close on that
  date reads 11.22 where the market saw about 36.70, the gap being the
  dividends T paid between then and the end of the file.

  The adjustment factor on date d is therefore a function of corporate actions
  AFTER d. Three features are quoted in those units and so leak:
    price           a total-return-adjusted level, not the price a screener saw
                    on d. A low value is partly a statement that the name later
                    split, which is information from after d.
    avg_volume_20   share counts restated into post-split terms, same leak.
    dollar_vol_60   close * volume cancels the SPLIT factor exactly -- NVDA's
                    2013 figure comes out at the true 88m -- but NOT the
                    cumulative DIVIDEND factor, which only the close carries.
                    T's 2013 dollar volume lands near 359m against a true
                    1.17bn, understated by the dividends still to be paid.
  Fixing this needs unadjusted prices or a split/dividend table, and
  cache_long has neither, so the features are emitted as the brief asks for
  and the contamination is named here, flagged in the coverage table and
  warned about at run time. Do not build a point-in-time "price > $5" or
  "dollar volume > $20m" filter on these three columns.

  Every OTHER feature in the block is immune, because a ratio or a return
  divides the adjustment factor out. Returns computed on adjusted closes are
  TOTAL returns, dividends reinvested, which is the same convention the grid's
  own fwd63 target uses, so the two sides agree.

ACCOUNTING / DATA CHOICES WORTH EXPLAINING
  Two rows of the price files, 2026-05-25 and 2026-09-07, carry a price for one
  symbol out of 509 and NaN for the other 508. Those are Memorial Day and Labor
  Day: US market holidays that leaked into the index as near-empty rows. They
  are dropped before anything is computed, because leaving them in would put a
  NaN inside every rolling window for the following n days and so blank out
  features on the 2026-05-29 grid date and after. A named threshold does the
  dropping rather than a hardcoded date list. Neither date is a grid date.
  After the drop the panel has exactly one interior missing cell left (FISV),
  so gaps are not a material concern.

  Every rolling window uses min_periods equal to the full window. A 200-day
  average computed from 40 days is not a 200-day average, and quietly emitting
  one would put a garbage value on the first grid dates of every late listing.
  The cost is that a name needs a full year of history before beta252, vol252,
  pos_52w and perf_1y populate, which the coverage table makes visible.

  In the Wilder recursion a missing input day does not poison the series
  forever: that day emits NaN and the smoothed average carries forward
  unchanged, resuming on the next good day.
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
OUT = os.path.join(LONG, "feat_tech.csv")

PRICE_FILES = {
    "close": "px_close.csv",
    "high": "px_high.csv",
    "low": "px_low.csv",
    "volume": "px_volume.csv",
}

# --- windows, all in TRADING days
SMA_FAST, SMA_MID, SMA_SLOW = 20, 50, 200
RSI_N = 14
ATR_N = 14
VOL_WINDOWS = (20, 60, 252)
BETA_N = 252
POS_WINDOWS = {"pos_20d": 20, "pos_50d": 50, "pos_52w": 252}
DD_N = 252
OFF_LOW_N = 60
PERF_WINDOWS = {"perf_1w": 5, "perf_1m": 21, "perf_3m": 63,
                "perf_6m": 126, "perf_1y": 252}
VOL_FAST, VOL_SLOW = 20, 60
DOLLAR_VOL_N = 60

TRADING_DAYS_YEAR = 252
PCT = 100.0
MARKET_SYMBOL = "SPY"

# A genuine trading day has prices for most of the panel. Anything below this
# is a holiday row that leaked in, not a day on which the market was thin.
MIN_CROSS_SECTION = 0.5
# pos_alltime needs some history to mean anything, but demanding a full year
# would make it identical to pos_52w.
MIN_ALLTIME_DAYS = 20
# Float-noise tolerance for the bounds assertions. A close that IS the window
# low lands on -1e-15 rather than exactly 0, which is not a formula error.
EPS = 1e-6

FEATURE_ORDER = [
    "dist_sma20", "dist_sma50", "dist_sma200", "sma50_over_200",
    "rsi14", "atr14_pct",
    "vol20", "vol60", "vol252", "beta252",
    "pos_20d", "pos_50d", "pos_52w", "pos_alltime",
    "dd_52w", "off_low_60",
    "perf_1w", "perf_1m", "perf_3m", "perf_6m", "perf_1y",
    "change_1d", "rel_volume", "avg_volume_20", "dollar_vol_60", "price",
]

# Quoted in units that depend on corporate actions AFTER the grid date, because
# the source price files are adjusted. See the docstring. Flagged everywhere
# they are reported so the leak cannot be forgotten.
ADJ_CONTAMINATED = frozenset({"price", "avg_volume_20", "dollar_vol_60"})

# Features whose natural unit is not a percent, so the report should not pretend
# otherwise when it prints quantiles.
RAW_UNIT = {"sma50_over_200", "rsi14", "beta252", "rel_volume",
            "avg_volume_20", "dollar_vol_60", "price"}


# ----------------------------------------------------------------- loading

def load_prices() -> dict[str, pd.DataFrame]:
    """The four price frames, date index, symbol columns, holiday rows removed.

    All four are filtered by the SAME row mask, taken from the close frame, so
    that high/low/volume stay aligned with close element for element. Any later
    feature can then assume a shared index and column order."""
    frames: dict[str, pd.DataFrame] = {}
    for name, fn in PRICE_FILES.items():
        df = pd.read_csv(os.path.join(LONG, fn), index_col=0, parse_dates=True)
        df = df.sort_index()
        frames[name] = df.astype("float64")

    close = frames["close"]
    keep = close.isna().mean(axis=1) < (1.0 - MIN_CROSS_SECTION)
    dropped = close.index[~keep]
    if len(dropped):
        say("dropped non-trading rows (price for < "
            f"{MIN_CROSS_SECTION:.0%} of the panel): "
            + ", ".join(d.strftime("%Y-%m-%d") for d in dropped))

    ref_cols = close.columns
    for name, df in frames.items():
        if not df.columns.equals(ref_cols):
            # reindexing rather than raising: a column the close frame does not
            # have is useless here, and a missing one must become NaN, not a
            # silent misalignment of positions.
            frames[name] = df.reindex(columns=ref_cols)
        frames[name] = frames[name].loc[keep.index[keep]]
    return frames


def load_grid() -> pd.DataFrame:
    g = pd.read_csv(GRID, parse_dates=["date"])
    # fwd63 is the target. It is read off the frame here only to drop it, so no
    # later line can accidentally reference it.
    return g[["date", "symbol"]].copy()


# ------------------------------------------------------- panel -> grid rows

class Taker:
    """Pulls the grid's (date, symbol) cells out of a full wide panel.

    One integer-position lookup computed once, then every feature is a single
    fancy-index into its panel. This is the reason the whole block runs in
    seconds instead of recomputing rolling windows per row."""

    def __init__(self, grid: pd.DataFrame, ref: pd.DataFrame) -> None:
        self.index = ref.index
        self.columns = ref.columns
        self.rows = self.index.get_indexer(pd.DatetimeIndex(grid["date"]))
        self.cols = self.columns.get_indexer(grid["symbol"].to_numpy())
        missing_d = sorted(set(grid.loc[self.rows < 0, "date"]))
        missing_s = sorted(set(grid.loc[self.cols < 0, "symbol"]))
        if missing_d:
            say(f"WARNING grid dates absent from the price index: {missing_d}")
        if missing_s:
            say(f"WARNING grid symbols absent from the price panel: {missing_s}")

    def __call__(self, panel: pd.DataFrame) -> np.ndarray:
        if not panel.index.equals(self.index):
            raise ValueError("panel index does not match the price index")
        if not panel.columns.equals(self.columns):
            raise ValueError("panel columns do not match the price columns")
        a = panel.to_numpy()
        out = np.full(len(self.rows), np.nan)
        ok = (self.rows >= 0) & (self.cols >= 0)
        out[ok] = a[self.rows[ok], self.cols[ok]]
        return out


# ------------------------------------------------------------- primitives

def roll_mean(df: pd.DataFrame, n: int) -> pd.DataFrame:
    return df.rolling(n, min_periods=n).mean()


def roll_max(df: pd.DataFrame, n: int) -> pd.DataFrame:
    return df.rolling(n, min_periods=n).max()


def roll_min(df: pd.DataFrame, n: int) -> pd.DataFrame:
    return df.rolling(n, min_periods=n).min()


def wilder_rma(df: pd.DataFrame, n: int) -> pd.DataFrame:
    """Wilder's recursive moving average, seeded with the first full n-day SMA.

    Vectorised across symbols: the loop is over ~4,200 dates, each step a single
    numpy row operation over ~500 columns. Per-column because the seed lands at
    a different row for every listing date."""
    x = df.to_numpy(dtype="float64")
    seed = roll_mean(df, n).to_numpy()
    n_rows, n_cols = x.shape

    seeded = ~np.isnan(seed)
    has_seed = seeded.any(axis=0)
    # argmax on a boolean row-stack gives the first True; guard the all-False
    # columns with an unreachable position so they stay NaN throughout.
    seed_pos = np.where(has_seed, np.argmax(seeded, axis=0), n_rows + 1)

    out = np.full((n_rows, n_cols), np.nan)
    prev = np.full(n_cols, np.nan)
    for t in range(n_rows):
        xt = x[t]
        is_seed = seed_pos == t
        prev = np.where(is_seed, seed[t], prev)
        # A missing day must not destroy the series: skip the update, emit NaN
        # for the day, resume from the same `prev` tomorrow.
        step = (t > seed_pos) & ~np.isnan(xt)
        prev = np.where(step, (prev * (n - 1) + np.nan_to_num(xt)) / n, prev)
        out[t] = np.where(np.isnan(xt) & ~is_seed, np.nan, prev)
    return pd.DataFrame(out, index=df.index, columns=df.columns)


def true_range(high: pd.DataFrame, low: pd.DataFrame,
               close: pd.DataFrame) -> pd.DataFrame:
    """Wilder's true range: the day's own range widened by any overnight gap."""
    prev_close = close.shift(1)
    a = high - low
    b = (high - prev_close).abs()
    c = (low - prev_close).abs()
    return a.combine(b, np.maximum).combine(c, np.maximum)


def range_position(close: pd.DataFrame, hi: pd.DataFrame,
                   lo: pd.DataFrame) -> pd.DataFrame:
    """0 at the window low, 100 at the window high.

    A window whose high equals its low has no range to sit in -- one flat price
    for the whole window -- so it is NaN rather than an arbitrary 0, 50 or 100."""
    span = (hi - lo).where(lambda s: s > 0)
    return (close - lo) / span * PCT


def rolling_beta(rets: pd.DataFrame, market: pd.Series, n: int) -> pd.DataFrame:
    """cov(r_i, r_m) / var(r_m) from rolling first and second moments.

    Population vs sample normalisation cancels in the ratio, so the plain
    rolling mean is enough and is far cheaper than a per-column covariance."""
    m = market.rolling(n, min_periods=n)
    mean_m = m.mean()
    var_m = m.mean().pow(2).rsub(market.pow(2).rolling(n, min_periods=n).mean())
    mean_i = rets.rolling(n, min_periods=n).mean()
    mean_im = rets.mul(market, axis=0).rolling(n, min_periods=n).mean()
    cov = mean_im.sub(mean_i.mul(mean_m, axis=0))
    return cov.div(var_m.where(var_m > 0), axis=0)


# ------------------------------------------------------------------ build

def build() -> pd.DataFrame:
    grid = load_grid()
    px = load_prices()
    close, high, low, volume = (px["close"], px["high"], px["low"],
                                px["volume"])
    say(f"price panel {close.shape[0]:,} trading days x {close.shape[1]} "
        f"symbols, {close.index.min():%Y-%m-%d} .. {close.index.max():%Y-%m-%d}")

    take = Taker(grid, close)
    f: dict[str, np.ndarray] = {}

    # --- moving averages
    sma = {n: roll_mean(close, n) for n in (SMA_FAST, SMA_MID, SMA_SLOW)}
    for n, key in ((SMA_FAST, "dist_sma20"), (SMA_MID, "dist_sma50"),
                   (SMA_SLOW, "dist_sma200")):
        f[key] = take((close / sma[n] - 1.0) * PCT)

    cross_known = sma[SMA_MID].notna() & sma[SMA_SLOW].notna()
    cross = (sma[SMA_MID] > sma[SMA_SLOW]).astype("float64").where(cross_known)
    f["sma50_over_200"] = take(cross)

    # --- Wilder RSI. Gains and losses are smoothed separately, as Wilder
    # defined it; RS = avg gain / avg loss.
    delta = close.diff()
    gain = delta.clip(lower=0.0).where(delta.notna())
    loss = (-delta).clip(lower=0.0).where(delta.notna())
    avg_gain = wilder_rma(gain, RSI_N)
    avg_loss = wilder_rma(loss, RSI_N)
    # An all-up window gives avg_loss == 0. RSI is 100 there, not a divide by
    # zero, so handle it explicitly instead of letting inf propagate.
    rs = avg_gain / avg_loss.where(avg_loss > 0)
    rsi = PCT - PCT / (1.0 + rs)
    rsi = rsi.where(avg_loss > 0, other=pd.DataFrame(
        np.where(avg_gain.to_numpy() > 0, PCT, np.nan),
        index=rsi.index, columns=rsi.columns))
    f["rsi14"] = take(rsi.where(avg_gain.notna() & avg_loss.notna()))

    # --- ATR as a share of price, so it is comparable across price levels
    atr = wilder_rma(true_range(high, low, close), ATR_N)
    f["atr14_pct"] = take(atr / close * PCT)

    # --- realised volatility and beta, both on daily simple returns
    rets = close.pct_change(fill_method=None)
    for n in VOL_WINDOWS:
        sd = rets.rolling(n, min_periods=n).std(ddof=1)
        f[f"vol{n}"] = take(sd * np.sqrt(TRADING_DAYS_YEAR) * PCT)

    if MARKET_SYMBOL in rets.columns:
        f["beta252"] = take(rolling_beta(rets, rets[MARKET_SYMBOL], BETA_N))
    else:
        # Documented fallback. Not expected: SPY is in px_close.csv.
        say(f"WARNING {MARKET_SYMBOL} absent; beta uses the equal-weight "
            "universe return as the market")
        f["beta252"] = take(rolling_beta(rets, rets.mean(axis=1), BETA_N))

    # --- position in the high/low range, intraday extremes
    for key, n in POS_WINDOWS.items():
        f[key] = take(range_position(close, roll_max(high, n), roll_min(low, n)))

    all_hi = high.expanding(min_periods=MIN_ALLTIME_DAYS).max()
    all_lo = low.expanding(min_periods=MIN_ALLTIME_DAYS).min()
    f["pos_alltime"] = take(range_position(close, all_hi, all_lo))

    f["dd_52w"] = take((close / roll_max(high, DD_N) - 1.0) * PCT)
    f["off_low_60"] = take((close / roll_min(low, OFF_LOW_N) - 1.0) * PCT)

    # --- trailing performance
    for key, n in PERF_WINDOWS.items():
        f[key] = take((close / close.shift(n) - 1.0) * PCT)
    f["change_1d"] = take(rets * PCT)

    # --- volume and liquidity
    v_fast = roll_mean(volume, VOL_FAST)
    v_slow = roll_mean(volume, VOL_SLOW)
    f["rel_volume"] = take(v_fast / v_slow.where(v_slow > 0))
    f["avg_volume_20"] = take(v_fast)
    f["dollar_vol_60"] = take(roll_mean(close * volume, DOLLAR_VOL_N))
    f["price"] = take(close)

    missing = [c for c in FEATURE_ORDER if c not in f]
    extra = [c for c in f if c not in FEATURE_ORDER]
    if missing or extra:
        raise ValueError(f"feature set mismatch: missing={missing} extra={extra}")

    say("WARNING the source price files are split- and dividend-adjusted, so "
        + ", ".join(sorted(ADJ_CONTAMINATED))
        + " are quoted in units set by corporate actions AFTER the grid date. "
          "They are not point-in-time levels. Ratios and returns are unaffected.")

    out = grid.copy()
    for c in FEATURE_ORDER:
        out[c] = f[c]
    return out


# ----------------------------------------------------------------- reports

def report_coverage(out: pd.DataFrame) -> None:
    """Per-feature coverage, the check pit_quality.py exists to enforce.

    A feature that populates on 12% of rows is not a feature, and a model fed
    one will report a conclusion about a column that was almost always
    missing."""
    n = len(out)
    say("\nPER-FEATURE COVERAGE over "
        f"{n:,} grid rows")
    say(f"  {'feature':<18}{'populated':>12}{'median':>16}")
    say("  " + "-" * 46)
    for c in FEATURE_ORDER:
        s = out[c]
        cov = s.notna().mean() * PCT
        med = s.median(skipna=True)
        unit = "" if c in RAW_UNIT else "%"
        flag = ""
        if cov < 90:
            flag = "  <-- THIN"
        elif c in ADJ_CONTAMINATED:
            flag = "  <-- ADJUSTED UNITS, see docstring"
        say(f"  {c:<18}{cov:>11.1f}%{med:>15,.3f}{unit}{flag}")
    say("  " + "-" * 46)
    worst = min((out[c].notna().mean() for c in FEATURE_ORDER))
    say(f"  lowest coverage of any feature: {worst * PCT:.1f}%")
    full = out[FEATURE_ORDER].notna().all(axis=1).mean() * PCT
    say(f"  rows with every feature present: {full:.1f}%")


def report_distribution(out: pd.DataFrame) -> None:
    qs = [0.01, 0.25, 0.5, 0.75, 0.99]
    say("\nDISTRIBUTION -- an absurd value should be visible here")
    head = "".join(f"{f'p{int(q * 100)}':>14}" for q in qs)
    say(f"  {'feature':<18}{'mean':>14}{head}")
    say("  " + "-" * (18 + 14 * (len(qs) + 1)))
    for c in FEATURE_ORDER:
        s = out[c]
        row = f"{s.mean(skipna=True):>14,.3f}"
        row += "".join(f"{v:>14,.3f}" for v in s.quantile(qs))
        say(f"  {c:<18}{row}")


def check_against_grid(out: pd.DataFrame) -> None:
    """The grid is the contract: same rows, same order, nothing added or lost."""
    g = pd.read_csv(GRID, parse_dates=["date"])
    if len(out) != len(g):
        raise AssertionError(f"row count {len(out):,} != grid {len(g):,}")
    if not out["date"].equals(g["date"]):
        raise AssertionError("date column does not match the grid row for row")
    if not out["symbol"].equals(g["symbol"]):
        raise AssertionError("symbol column does not match the grid row for row")
    pairs_out = set(zip(out["date"], out["symbol"]))
    pairs_g = set(zip(g["date"], g["symbol"]))
    if pairs_out != pairs_g:
        raise AssertionError("(date, symbol) pair sets differ from the grid")
    if out.duplicated(subset=["date", "symbol"]).any():
        raise AssertionError("duplicate (date, symbol) rows")
    if "fwd63" in out.columns:
        raise AssertionError("the target leaked into the feature block")
    say(f"\nGRID CHECK ok: {len(out):,} rows, {out.date.nunique()} dates, "
        f"{out.symbol.nunique()} symbols, order and pairs identical")


def check_sanity(out: pd.DataFrame) -> None:
    """Bounds that hold by construction. A breach means a formula is wrong."""
    def violations(mask: pd.Series) -> int:
        return int(mask.fillna(False).sum())

    def outside_pct_range(s: pd.Series) -> pd.Series:
        return (s < -EPS) | (s > PCT + EPS)

    problems: list[str] = []
    checks = {
        "rsi14 outside [0, 100]": outside_pct_range(out.rsi14),
        "pos_20d outside [0, 100]": outside_pct_range(out.pos_20d),
        "pos_50d outside [0, 100]": outside_pct_range(out.pos_50d),
        "pos_52w outside [0, 100]": outside_pct_range(out.pos_52w),
        "pos_alltime outside [0, 100]": outside_pct_range(out.pos_alltime),
        "dd_52w positive": out.dd_52w > EPS,
        "off_low_60 negative": out.off_low_60 < -EPS,
        "atr14_pct negative": out.atr14_pct < 0,
        "vol20 negative": out.vol20 < 0,
        "price non-positive": out.price <= 0,
        "rel_volume non-positive": out.rel_volume <= 0,
        "sma50_over_200 not 0/1": ~out.sma50_over_200.isin([0.0, 1.0])
                                  & out.sma50_over_200.notna(),
    }
    for label, mask in checks.items():
        k = violations(mask)
        if k:
            problems.append(f"{label}: {k:,} rows")
    if problems:
        raise AssertionError("sanity checks failed -- " + "; ".join(problems))
    say("SANITY ok: bounded features inside their bounds, signs as expected")


def main() -> None:
    out = build()
    check_against_grid(out)
    check_sanity(out)
    report_coverage(out)
    report_distribution(out)
    if "--dry" in sys.argv:
        say("\n--dry: nothing written")
        return
    out.to_csv(OUT, index=False, date_format="%Y-%m-%d")
    say(f"\nwrote {len(out):,} rows x {len(FEATURE_ORDER)} features to {OUT}")


if __name__ == "__main__":
    main()
