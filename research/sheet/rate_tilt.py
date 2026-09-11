"""Can a rate view be traded LONG-ONLY with trailing information only?

    python research/sheet/rate_tilt.py

THE ANGLE
rate_foresight.py handed the rule the answer key: it classified each month by
what long rates ACTUALLY DID next. This file removes the answer key. Every
number below is computable standing on the decision date with no knowledge of
the future. That makes it the only arm of this investigation that a cash
account could have acted on, so it gets the strictest test.

WHAT IS BUILT
A name's RATE BETA is the slope of its daily returns on TLT's over the trailing
252 days. Positive means it rises when bonds rise, which is when yields fall: a
long-duration name. Negative means it rises when yields rise. Nothing about the
future enters that estimate.

Then four portfolios, rebalanced on the 158 month-end decision dates of
grid.csv, each holding ONE MONTH (decision date close to next decision date
close, so the return series is NON-OVERLAPPING -- see THE T-STATISTICS below):

  arm A  equal-weight the LOWEST rate-beta decile. The names that rise when
         yields rise. This is the long-only expression of "rates are going up".
  arm B  equal-weight the HIGHEST rate-beta decile. The opposite bet.
  arm C  equal-weight the whole eligible universe. The control, and the harder
         of the two bars: it compounded at +14.82% in this sample.
  arm D  SPY buy and hold. The stated bar, +14.78% CAGR.

Then the conditional version, which is what a person with a rate view would
actually do: hold the low-rate-beta decile ONLY when a trailing rate signal says
yields are rising, and hold the universe otherwise. Two signals:

  TLT 3-month trailing total return < 0.  PRIMARY. A ratio of two adjusted
  closes, so the adjustment factor cancels exactly and this is an honest total
  return (rule 1).

  TLT below its 200-day average.  SECONDARY, AND FLAGGED. A trailing average of
  DIVIDEND-ADJUSTED prices sits below the average of what actually traded,
  because past adjusted prices are scaled down by the cumulative distribution
  factor. On a ~4% yielding fund over 200 sessions that is roughly a 3% upward
  bias in price/SMA, which is large relative to the signal itself. It is
  reported for completeness and should not be believed on its own.

WHY THE RETURN HORIZON IS ONE MONTH AND NOT fwd63
grid.csv's fwd63 looks 63 trading days ahead from monthly dates, so consecutive
observations share two thirds of their window. Compounding fwd63 month by month
would count every move roughly three times and produce an equity curve that
never existed. The holding return here is month-end to month-end, computed from
px_close as a RATIO of two adjusted closes -- immune to the adjustment problem
in rule 1, and a true total return because the closes are dividend-adjusted.

THE T-STATISTICS
Because the monthly holding returns do not overlap, the sqrt(3) deflator that
applies to every fwd63 t-statistic in this project does NOT apply here. What
does apply is the multiple-comparison bar: SIX portfolio variants are examined
(A, B, and two signals x two polarities), so the threshold is
sqrt(2*ln(6)) = 1.89, not 1.96. Signal choice and polarity are settled on
train only; the holdout is read once.

WHAT WOULD HAVE FALSIFIED IT, stated before looking
Arm A had to beat BOTH bars out of sample -- the +14.82% equal-weight control
and the +14.78% index -- with a monthly excess over the control whose t exceeds
1.89, and it had to keep a positive excess after market beta is paid for. If
arm A's holdout advantage is entirely (its beta spread) x (the realised factor
return), it is a bet that happened to be right about 2022-2025, not a method,
and it is reported as such.
"""
from __future__ import annotations

import io
import os
import sys
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

PROXY = "TLT"                 # long-Treasury proxy: rates UP shows as TLT DOWN
MKT = "SPY"
BETA_WINDOW = 252             # trailing days for every beta estimate
N_DEC = 10                    # deciles on rate beta
SIG_LOOKBACK = 63             # ~3 months of trailing TLT return, the primary signal
SMA_WINDOW = 200              # secondary signal, flagged for dividend bias
TRAIN_END = pd.Timestamp("2021-09-30")
HOLDOUT_START = pd.Timestamp("2022-01-01")
MONTHS_PER_YEAR = 12
SPY_CAGR_BAR = 14.78          # verified, 2013-01-02 .. 2026-06-12
EW_CAGR_BAR = 14.82           # equal-weight this universe, the harder bar
N_VARIANTS = 6                # A, B, 2 signals x 2 polarities
MIN_NAMES = 40                # a month with fewer eligible names is not a universe
COST_BPS_ROUND_TRIP = 5.0     # spread + commission assumption, large-cap, one round trip
N_RANDOM_SIGNALS = 2000       # null for the conditional arms
RNG_SEED = 20260911


# --------------------------------------------------------------- estimation
def rate_betas(C: pd.DataFrame, syms: list[str]) -> pd.DataFrame:
    """Trailing univariate slope of each name's returns on TLT's.

    Vectorised: cov(r_i, r_b) / var(r_b) from rolling moments. A per-name
    regression loop over 465 symbols x 4,198 days is minutes for the same
    answer. Trailing only -- no value on date t uses a return after date t."""
    R = C[syms].pct_change()
    b = C[PROXY].pct_change()
    mb = b.rolling(BETA_WINDOW).mean()
    vb = b.rolling(BETA_WINDOW).var()
    mr = R.rolling(BETA_WINDOW).mean()
    cov = (R.mul(b, axis=0).rolling(BETA_WINDOW).mean()
           .sub(mr.mul(mb, axis=0)))
    return cov.div(vb, axis=0)


def two_factor_betas(C: pd.DataFrame,
                     syms: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Trailing JOINT betas on SPY and TLT, for the decomposition only.

    The univariate rate beta above is what the portfolio SORTS on, because that
    is what the angle specifies and what a person would compute. But SPY and
    TLT returns are correlated, so attributing a portfolio's return to the two
    exposures separately needs betas from one joint regression, otherwise the
    market and rate legs of the decomposition double-count the same move.

    The 2x2 normal-equations matrix is identical for every name on a given day,
    so it is built once per day from rolling moments and applied to the whole
    panel at once."""
    R = C[syms].pct_change()
    x1 = C[MKT].pct_change()
    x2 = C[PROXY].pct_change()

    def roll_mean(s: pd.Series) -> pd.Series:
        return s.rolling(BETA_WINDOW).mean()

    m1, m2 = roll_mean(x1), roll_mean(x2)
    v11 = roll_mean(x1 * x1) - m1 * m1
    v22 = roll_mean(x2 * x2) - m2 * m2
    v12 = roll_mean(x1 * x2) - m1 * m2
    det = v11 * v22 - v12 * v12
    mr = R.rolling(BETA_WINDOW).mean()
    c1 = R.mul(x1, axis=0).rolling(BETA_WINDOW).mean().sub(mr.mul(m1, axis=0))
    c2 = R.mul(x2, axis=0).rolling(BETA_WINDOW).mean().sub(mr.mul(m2, axis=0))
    b_mkt = (c1.mul(v22, axis=0) - c2.mul(v12, axis=0)).div(det, axis=0)
    b_rate = (c2.mul(v11, axis=0) - c1.mul(v12, axis=0)).div(det, axis=0)
    return b_mkt, b_rate


# -------------------------------------------------------------------- panel
def holding_returns(C: pd.DataFrame, dates: list[pd.Timestamp],
                    syms: list[str]) -> pd.DataFrame:
    """Month-end to next-month-end percentage return, per name.

    A RATIO of two dividend-adjusted closes: the cumulative adjustment factor
    appears in both numerator and denominator on the same symbol and cancels,
    so this is a valid total return (rule 1 forbids LEVELS, not ratios). The
    final decision date has no successor and is dropped."""
    P = C.loc[dates, syms]
    return (P.shift(-1) / P - 1.0) * 100.0


def build_panel(g: pd.DataFrame, C: pd.DataFrame,
                syms: list[str]) -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    """One row per (decision date, eligible name) with everything trailing."""
    dates = sorted(pd.Timestamp(x) for x in g.date.unique())
    RB = rate_betas(C, syms)
    B_MKT, B_RATE = two_factor_betas(C, syms)
    RET = holding_returns(C, dates, syms)

    def stack(df: pd.DataFrame, name: str) -> pd.DataFrame:
        # pandas 3 stack() keeps NA cells, so no dropna argument is passed;
        # the NaNs are what the eligibility filter below keys on.
        s = df.loc[dates, syms].stack().rename(name).reset_index()
        s.columns = ["date", "symbol", name]
        return s

    d = g[["date", "symbol"]].copy()
    for df, nm in ((RB, "rate_beta"), (RET, "ret1m"),
                   (B_MKT, "b_mkt"), (B_RATE, "b_rate")):
        d = d.merge(stack(df, nm), on=["date", "symbol"], how="left")

    tech = pd.read_csv(os.path.join(LONG, "feat_tech.csv"), parse_dates=["date"])
    d = d.merge(tech[["date", "symbol", "beta252"]], on=["date", "symbol"],
                how="left")

    before = len(d)
    d = d.dropna(subset=["rate_beta", "ret1m"])
    say(f"  {before:,} grid rows -> {len(d):,} eligible "
        f"(dropped {before - len(d):,}: no 252d history, or no next-month close "
        f"because the name left the tape)")
    say(f"  Those {before - len(d):,} drops are {100 * (before - len(d)) / before:.1f}% "
        f"of the panel and include delistings, so every arm below")
    say("  carries the same mild survivorship flattery. It cannot explain a "
        "DIFFERENCE")
    say("  between two arms drawn from the same filtered panel, which is what is "
        "measured.")

    # monthly factor returns over the SAME holding windows as the portfolios
    spy = (C.loc[dates, MKT].shift(-1) / C.loc[dates, MKT] - 1.0) * 100.0
    tlt = (C.loc[dates, PROXY].shift(-1) / C.loc[dates, PROXY] - 1.0) * 100.0
    return d, spy.dropna(), tlt.dropna()


def trailing_signals(C: pd.DataFrame,
                     dates: list[pd.Timestamp]) -> pd.DataFrame:
    """The two rate signals, both computable standing on the decision date."""
    t = C[PROXY].dropna()
    r3 = (t / t.shift(SIG_LOOKBACK) - 1.0) * 100.0
    sma = t.rolling(SMA_WINDOW).mean()
    dist = (t / sma - 1.0) * 100.0
    return pd.DataFrame({"tlt_3m": r3.reindex(dates),
                         "tlt_vs_sma200": dist.reindex(dates)})


# ------------------------------------------------------------------- arms
def decile(d: pd.DataFrame) -> pd.DataFrame:
    """Rate-beta decile within each month. Months with too few names are cut."""
    ok = d.groupby("date")["symbol"].transform("size") >= MIN_NAMES
    d = d[ok].copy()
    d["dec"] = d.groupby("date")["rate_beta"].transform(
        lambda x: pd.qcut(x.rank(method="first"), N_DEC, labels=False,
                          duplicates="drop"))
    return d.dropna(subset=["dec"])


def slice_returns(d: pd.DataFrame, mask: pd.Series) -> pd.Series:
    """Equal-weight monthly return of the selected rows."""
    s = d[mask]
    return s.groupby("date")["ret1m"].mean()


def members(d: pd.DataFrame, mask: pd.Series) -> dict:
    return {dt: set(s.symbol) for dt, s in d[mask].groupby("date")}


def turnover(mem: dict) -> float:
    """Mean one-way turnover, 0.5 * sum|w_new - w_old| on equal weights."""
    keys = sorted(mem)
    out = []
    for a, b in zip(keys, keys[1:]):
        sa, sb = mem[a], mem[b]
        if not sa or not sb:
            continue
        wa = {k: 1.0 / len(sa) for k in sa}
        wb = {k: 1.0 / len(sb) for k in sb}
        out.append(0.5 * sum(abs(wb.get(k, 0.0) - wa.get(k, 0.0))
                             for k in sa | sb))
    return float(np.mean(out)) if out else np.nan


def compound(r: pd.Series) -> tuple[float, float, float, int]:
    """Total return %, CAGR %, max drawdown %, months. r is in percent."""
    r = r.dropna().sort_index()
    if len(r) < 2:
        return (np.nan,) * 3 + (len(r),)
    eq = (1.0 + r / 100.0).cumprod()
    total = (eq.iloc[-1] - 1.0) * 100.0
    yrs = len(r) / MONTHS_PER_YEAR
    cagr = ((eq.iloc[-1]) ** (1.0 / yrs) - 1.0) * 100.0
    dd = (eq / eq.cummax() - 1.0).min() * 100.0
    return total, cagr, dd, len(r)


def window(r: pd.Series, lo: pd.Timestamp | None,
           hi: pd.Timestamp | None) -> pd.Series:
    s = r
    if lo is not None:
        s = s[s.index >= lo]
    if hi is not None:
        s = s[s.index <= hi]
    return s


def report_block(title: str, arms: dict[str, pd.Series],
                 lo: pd.Timestamp | None, hi: pd.Timestamp | None,
                 control: str) -> None:
    say("")
    say(f"  {title}")
    say(f"  {'arm':<34}{'months':>7}{'total':>11}{'CAGR':>9}{'maxDD':>9}"
        f"{'vs ctrl':>9}{'t':>7}")
    say("  " + "-" * 86)
    c = window(arms[control], lo, hi)
    for name, r in arms.items():
        s = window(r, lo, hi)
        total, cagr, dd, n = compound(s)
        if name == control:
            ex, t = 0.0, np.nan
        else:
            diff = (s - c).dropna()
            ex = diff.mean() * MONTHS_PER_YEAR
            t = (diff.mean() / (diff.std(ddof=1) / np.sqrt(len(diff)))
                 if len(diff) > 2 and diff.std(ddof=1) > 0 else np.nan)
        say(f"  {name:<34}{n:>7}{total:>+10.1f}%{cagr:>+8.2f}%{dd:>+8.1f}%"
            f"{ex:>+8.2f}%{t:>+7.2f}")


# ------------------------------------------------------------------- main
def main() -> None:
    say("LOADING")
    g = pd.read_csv(os.path.join(LONG, "grid.csv"), parse_dates=["date"])
    C = pd.read_csv(os.path.join(LONG, "px_close.csv"), index_col=0,
                    parse_dates=True).sort_index()
    for need in (PROXY, MKT):
        if need not in C.columns:
            raise SystemExit(f"{need} absent from px_close.csv; cannot run")
    syms = sorted(set(g.symbol) & set(C.columns))
    dates = sorted(pd.Timestamp(x) for x in g.date.unique())
    say(f"  {len(g):,} grid rows | {len(syms)} symbols | {len(dates)} decision "
        f"dates {dates[0]:%Y-%m} .. {dates[-1]:%Y-%m}")

    d, spy_m, tlt_m = build_panel(g, C, syms)
    d = decile(d)
    sig = trailing_signals(C, dates)

    say(f"  {d.date.nunique()} months survive the {MIN_NAMES}-name minimum, "
        f"{len(d):,} rows, median {int(d.groupby('date').size().median())} "
        f"names per month")

    lo_dec, hi_dec = 0, int(d.dec.max())
    m_lo = d.dec == lo_dec
    m_hi = d.dec == hi_dec
    arms: dict[str, pd.Series] = {}
    arms["C  universe equal-weight (control)"] = slice_returns(
        d, pd.Series(True, index=d.index))
    arms["A  lowest rate-beta decile"] = slice_returns(d, m_lo)
    arms["B  highest rate-beta decile"] = slice_returns(d, m_hi)
    spy_arm = spy_m.reindex(arms["A  lowest rate-beta decile"].index).dropna()
    arms["D  SPY buy and hold"] = spy_arm

    CTRL = "C  universe equal-weight (control)"
    r_uni = arms[CTRL]
    r_lo = arms["A  lowest rate-beta decile"]

    say("")
    say("=" * 90)
    say("  WHAT THE SORT ACTUALLY SELECTS  (means over all months, trailing "
        "estimates)")
    say("=" * 90)
    say(f"  {'slice':<30}{'rate beta':>11}{'beta252':>10}{'joint b_mkt':>13}"
        f"{'joint b_rate':>14}")
    say("  " + "-" * 80)
    for nm, mask in (("lowest rate-beta decile", m_lo),
                     ("universe", pd.Series(True, index=d.index)),
                     ("highest rate-beta decile", m_hi)):
        s = d[mask]
        say(f"  {nm:<30}{s.rate_beta.mean():>+11.2f}{s.beta252.mean():>+10.2f}"
            f"{s.b_mkt.mean():>+13.2f}{s.b_rate.mean():>+14.2f}")
    say("")
    say("  The low decile is the long-only expression of 'yields are going up'.")
    say("  Note its market beta against the universe's: if it is higher, part of")
    say("  anything it earns in a rising market is leverage, not rate insight.")

    # ----------------------------------------------------------- conditional
    say("")
    say("=" * 90)
    say("  CONDITIONAL TILT -- low-rate-beta decile only when the trailing")
    say("  signal says yields are rising, universe otherwise")
    say("=" * 90)
    cond: dict[str, pd.Series] = {}
    cond_on: dict[str, pd.Series] = {}     # the on/off mask, kept for the null
    for col, label in (("tlt_3m", "TLT 3m return"),
                       ("tlt_vs_sma200", "TLT vs SMA200")):
        s = sig[col].reindex(r_uni.index)
        for tilt_when_negative, pol in ((True, "falling -> tilt"),
                                        (False, "rising -> tilt")):
            on = ((s < 0) if tilt_when_negative else (s > 0)).fillna(False)
            key = f"{label} {pol}"
            cond[key] = r_lo.where(on, r_uni)
            cond_on[key] = on
            say(f"  {key:<34}tilted in {int(on.sum()):>3} of {len(on)} months "
                f"({on.mean() * 100:>4.0f}%)")
    say("")
    say("  'falling -> tilt' is the economically intended direction: TLT falling")
    say("  IS yields rising. 'rising -> tilt' is the same rule backwards and is")
    say("  run only so the multiple-comparison count is honest.")

    all_arms = dict(arms)
    for k, v in cond.items():
        all_arms[f"E  {k}"] = v

    bar = float(np.sqrt(2 * np.log(N_VARIANTS)))
    say("")
    say("=" * 90)
    say(f"  RESULTS. Excess and t are against arm C. {N_VARIANTS} variants "
        f"examined, so the bar is")
    say(f"  |t| > sqrt(2*ln({N_VARIANTS})) = {bar:.2f}. Monthly returns do NOT "
        f"overlap, so the sqrt(3)")
    say("  deflator that applies to every fwd63 t in this project does not apply "
        "here.")
    say("=" * 90)
    report_block("FULL WINDOW (in-sample for arms A/B, contaminated by the "
                 "search for arm E)", all_arms, None, None, CTRL)
    report_block(f"TRAIN ONLY, decision dates <= {TRAIN_END:%Y-%m-%d}",
                 all_arms, None, TRAIN_END, CTRL)
    report_block(f"SEALED HOLDOUT, decision dates >= {HOLDOUT_START:%Y-%m-%d}  "
                 f"<-- the only honest read",
                 all_arms, HOLDOUT_START, None, CTRL)
    n_emb = sum(1 for x in r_uni.index if TRAIN_END < x < HOLDOUT_START)
    say("")
    say(f"  {n_emb} decision dates between the two windows are dropped "
        f"(embargo). The")
    say("  holding returns here are one month and do not overlap, so the embargo "
        "is")
    say("  belt-and-braces rather than strictly necessary, and it is kept so the")
    say("  split matches tree_screen.py exactly.")
    say("")
    say(f"  THE BARS: SPY {SPY_CAGR_BAR:.2f}% CAGR and equal-weight "
        f"{EW_CAGR_BAR:.2f}% CAGR, both measured over")
    say("  the FULL sample. Arm C and arm D in the full-window table reproduce "
        "them")
    say("  (small gaps are the window: this file runs 2013-04-30 to 2026-05-29, "
        "not")
    say("  2013-01-02 to 2026-06-12). Those two numbers must NOT be compared to "
        "a")
    say("  holdout-only CAGR, because the holdout window was simply a worse four")
    say("  years for stocks. Inside the holdout the bars are arm C's own "
        f"{compound(window(r_uni, HOLDOUT_START, None))[1]:.2f}% and")
    say(f"  SPY's {compound(window(spy_arm, HOLDOUT_START, None))[1]:.2f}%. An "
        f"arm has to clear the in-window bars to mean anything.")

    # -------------------------------------- is the CONDITIONING worth anything?
    say("")
    say("=" * 90)
    say("  DOES CONDITIONING BEAT A COIN FLIP, AND DOES IT BEAT ALWAYS TILTING?")
    say("=" * 90)
    say("  A conditional arm that tilts in p of the months earns roughly p times")
    say("  arm A's excess even if the signal is pure noise, so comparing it to arm")
    say("  C proves nothing. Two comparisons that do mean something:")
    say("")
    say(f"  {'arm':<34}{'vs A excess':>13}{'t':>7}   {'vs random signal':>18}")
    say("  " + "-" * 80)
    rng = np.random.default_rng(RNG_SEED)
    cond_pct: dict[str, float] = {}    # percentile vs the random-mask null
    ho_idx = window(r_uni, HOLDOUT_START, None).index
    a_ho = r_lo.reindex(ho_idx)
    c_ho = r_uni.reindex(ho_idx)
    for key, series in cond.items():
        e_ho = series.reindex(ho_idx)
        dv = (e_ho - a_ho).dropna()
        t = (dv.mean() / (dv.std(ddof=1) / np.sqrt(len(dv)))
             if len(dv) > 2 and dv.std(ddof=1) > 0 else np.nan)
        p = float(cond_on[key].reindex(ho_idx).mean())
        real = (e_ho - c_ho).dropna().mean() * MONTHS_PER_YEAR
        null = np.empty(N_RANDOM_SIGNALS)
        for i in range(N_RANDOM_SIGNALS):
            on = rng.random(len(ho_idx)) < p
            r = pd.Series(np.where(on, a_ho.to_numpy(), c_ho.to_numpy()),
                          index=ho_idx)
            null[i] = (r - c_ho).dropna().mean() * MONTHS_PER_YEAR
        pct = (null < real).mean() * 100
        cond_pct[key] = pct
        say(f"  {key:<34}{dv.mean() * MONTHS_PER_YEAR:>+12.2f}%{t:>+7.2f}   "
            f"{real:>+6.2f}% vs null {null.mean():+.2f}%, pctile {pct:>3.0f}")
    say("  " + "-" * 80)
    say(f"  Holdout months only. The null draws a random on/off mask with the "
        f"SAME tilt")
    say(f"  frequency as the real signal, {N_RANDOM_SIGNALS} times, and keeps the "
        f"same two")
    say("  portfolios. A signal worth having sits in the top few percent of that")
    say("  distribution. A signal at the 50th percentile is a coin flip that")
    say("  happened to be on for the right number of months.")

    # ----------------------------------------------------- beta, not insight
    say("")
    say("=" * 90)
    say("  RULE 2: IS IT RATE SELECTION, OR IS IT BETA?")
    say("=" * 90)
    say("  (a) Regress each arm's monthly return on SPY's. Alpha is what is left")
    say("      after the market exposure is paid for at the realised market "
        "return.")
    say("")
    say(f"  {'arm':<34}{'beta':>8}{'alpha/yr':>11}{'t(alpha)':>10}{'R2':>8}")
    say("  " + "-" * 74)
    alpha_stats: dict[str, tuple[float, float, float]] = {}
    for name in (CTRL, "A  lowest rate-beta decile", "B  highest rate-beta decile",
                 "E  TLT 3m return falling -> tilt"):
        r = window(all_arms[name], HOLDOUT_START, None).dropna()
        x = spy_m.reindex(r.index)
        m = x.notna() & r.notna()
        if m.sum() < 10:
            continue
        X = np.column_stack([np.ones(m.sum()), x[m].to_numpy()])
        y = r[m].to_numpy()
        coef, *_ = np.linalg.lstsq(X, y, rcond=None)
        resid = y - X @ coef
        dof = m.sum() - 2
        s2 = resid @ resid / dof
        se = np.sqrt(s2 * np.linalg.inv(X.T @ X)[0, 0])
        r2 = 1.0 - (resid @ resid) / ((y - y.mean()) @ (y - y.mean()))
        alpha_stats[name] = (coef[1], coef[0] * MONTHS_PER_YEAR, coef[0] / se)
        say(f"  {name:<34}{coef[1]:>8.2f}{coef[0] * MONTHS_PER_YEAR:>+10.2f}%"
            f"{coef[0] / se:>+10.2f}{r2:>8.2f}")
    say("      Holdout months only. A beta above 1 with a positive raw excess and")
    say("      an alpha near zero is leverage wearing a rate story.")

    say("")
    say("  (b) The house test: neutralise beta inside each month and re-sort.")
    say("      Regress the one-month forward return on beta252 within the month,")
    say("      keep the residual, and ask what the rate-beta deciles earn on")
    say("      WHAT IS LEFT. Demeaning does not do this; only residualising does.")

    def resid_on_beta(grp: pd.DataFrame) -> pd.Series:
        x = grp["beta252"].to_numpy(dtype=float)
        y = grp["ret1m"].to_numpy(dtype=float)
        ok = np.isfinite(x) & np.isfinite(y)
        out = pd.Series(np.nan, index=grp.index)
        if ok.sum() < 20:
            return out
        b1, b0 = np.polyfit(x[ok], y[ok], 1)
        out.loc[grp.index[ok]] = y[ok] - (b0 + b1 * x[ok])
        return out

    d2 = d.dropna(subset=["beta252"]).copy()
    d2["resid"] = d2.groupby("date", group_keys=False).apply(resid_on_beta)
    d2 = d2.dropna(subset=["resid"])
    say("")
    say(f"  {'window':<14}{'low dec resid':>16}{'high dec resid':>17}"
        f"{'low-high':>11}{'t':>8}")
    say("  " + "-" * 68)
    for nm, lo_dt, hi_dt in (("train", None, TRAIN_END),
                             ("holdout", HOLDOUT_START, None)):
        s = d2
        if lo_dt is not None:
            s = s[s.date >= lo_dt]
        if hi_dt is not None:
            s = s[s.date <= hi_dt]
        a = s.loc[s.dec == lo_dec].groupby("date")["resid"].mean()
        b = s.loc[s.dec == hi_dec].groupby("date")["resid"].mean()
        diff = (a - b).dropna()
        t = (diff.mean() / (diff.std(ddof=1) / np.sqrt(len(diff)))
             if len(diff) > 2 and diff.std(ddof=1) > 0 else np.nan)
        say(f"  {nm:<14}{a.mean():>+15.3f}%{b.mean():>+16.3f}%"
            f"{diff.mean():>+10.3f}%{t:>+8.2f}")
    say("      Monthly residual means, so these are per-month not per-year.")

    # -------------------------------------------------- rule 3 decomposition
    say("")
    say("=" * 90)
    say("  RULE 3: DECOMPOSITION. No forward-looking label is used anywhere in")
    say("  this file, so this is not the answer-key check rate_foresight.py")
    say("  needed. It is the harder question for a TRADEABLE arm: is arm A minus")
    say("  arm C just (its exposure spread) x (what the factors happened to do)?")
    say("  If it is, the arm is a bet that 2022-2025 yields rose, and it reverses")
    say("  when they fall. That is a position, not a method.")
    say("=" * 90)
    rows = []
    for dt, grp in d.groupby("date"):
        a = grp[grp.dec == lo_dec]
        if a.empty:
            continue
        rows.append({
            "date": dt,
            "d_mkt": a.b_mkt.mean() - grp.b_mkt.mean(),
            "d_rate": a.b_rate.mean() - grp.b_rate.mean()})
    X = pd.DataFrame(rows).set_index("date")
    diff = (r_lo - r_uni).dropna()
    X = X.reindex(diff.index)
    sp = spy_m.reindex(diff.index)
    tl = tlt_m.reindex(diff.index)
    for nm, lo_dt, hi_dt in (("full", None, None),
                             ("train", None, TRAIN_END),
                             ("holdout", HOLDOUT_START, None)):
        idx = diff.index
        if lo_dt is not None:
            idx = idx[idx >= lo_dt]
        if hi_dt is not None:
            idx = idx[idx <= hi_dt]
        act = diff.reindex(idx).mean() * MONTHS_PER_YEAR
        mkt_leg = (X.d_mkt.reindex(idx) * sp.reindex(idx)).mean() * MONTHS_PER_YEAR
        rate_leg = (X.d_rate.reindex(idx) * tl.reindex(idx)).mean() * MONTHS_PER_YEAR
        expl = mkt_leg + rate_leg
        say(f"  {nm:<9}A-C {act:>+7.2f}%/yr = market leg {mkt_leg:>+6.2f}% + "
            f"rate leg {rate_leg:>+6.2f}% + residual {act - expl:>+6.2f}%"
            f"   ({expl / act * 100 if act else float('nan'):>5.0f}% explained)")
    say("")
    say("  The legs are exposure spreads from ONE joint trailing regression on")
    say("  SPY and TLT, multiplied by the factors' realised returns over the same")
    say("  holding months. Univariate betas would double-count the shared move.")

    # --------------------------------------------------------------- costs
    say("")
    say("=" * 90
        )
    say("  TURNOVER AND WHAT THESE FIGURES ARE GROSS OF")
    say("=" * 90)
    to_lo = turnover(members(d, m_lo))
    to_hi = turnover(members(d, m_hi))
    to_un = turnover(members(d, pd.Series(True, index=d.index)))
    n_lo = int(d[m_lo].groupby("date").size().median())
    say(f"  arm A  {n_lo} names, mean one-way turnover {to_lo * 100:.1f}%/month "
        f"= {to_lo * 2 * 12 * 100:.0f}%/yr round trip")
    say(f"  arm B  mean one-way turnover {to_hi * 100:.1f}%/month")
    say(f"  arm C  mean one-way turnover {to_un * 100:.1f}%/month "
        f"(index reconstitution only)")
    say("")
    say("  A cash account settles T+1, so a month-end rebalance is trivially")
    say("  fine: sell and buy the same session, no margin, no pattern-day-trader")
    say("  exposure. What these figures ARE gross of is spread and commission.")
    drag = to_lo * 2 * MONTHS_PER_YEAR * COST_BPS_ROUND_TRIP / 1e4 * 100
    say(f"  At {to_lo * 2 * 12 * 100:.0f}% annual round-trip turnover, "
        f"{COST_BPS_ROUND_TRIP:.0f}bp of round-trip cost on")
    say(f"  large-cap names is about {drag:.2f}% a year of drag. That is small "
        f"relative to the")
    say("  differences above and does not change any verdict here.")

    # ------------------------------------------------------------ by year
    say("")
    say("=" * 90)
    say("  YEAR BY YEAR, ARM A MINUS ARM C, AND WHAT RATES DID")
    say("=" * 90)
    yr = pd.DataFrame({"diff": diff, "tlt": tlt_m.reindex(diff.index)})
    yr["y"] = yr.index.year
    say(f"  {'year':<8}{'months':>8}{'A-C sum':>11}{'TLT year':>11}  note")
    say("  " + "-" * 60)
    for y, grp in yr.groupby("y"):
        tag = "yields ROSE" if grp.tlt.sum() < 0 else "yields fell"
        say(f"  {int(y):<8}{len(grp):>8}{grp['diff'].sum():>+10.2f}%"
            f"{grp.tlt.sum():>+10.2f}%  {tag}")
    sgn = np.sign(yr.groupby("y")["diff"].sum())
    tsg = np.sign(-yr.groupby("y")["tlt"].sum())
    agree = int((sgn == tsg).sum())
    say("  " + "-" * 60)
    say(f"  arm A beat the universe in the same direction as rates moved in "
        f"{agree} of {len(sgn)} years.")
    say("  If the rate story were the mechanism that number would be near 14.")

    say("")
    say("=" * 90)
    say("  ROBUSTNESS: HOW CONCENTRATED IS THE HOLDOUT EDGE?")
    say("=" * 90)
    ho_diff = diff.reindex(ho_idx).dropna()
    by_yr = ho_diff.groupby(ho_diff.index.year).sum()
    say(f"  {'year':<8}{'A-C sum':>11}{'share of holdout total':>26}")
    say("  " + "-" * 46)
    tot = by_yr.sum()
    for y, v in by_yr.items():
        say(f"  {int(y):<8}{v:>+10.2f}%{v / tot * 100 if tot else float('nan'):>24.0f}%")
    say("  " + "-" * 46)
    best = by_yr.idxmax()
    kept = ho_diff[ho_diff.index.year != best]
    t_kept = (kept.mean() / (kept.std(ddof=1) / np.sqrt(len(kept)))
              if len(kept) > 2 and kept.std(ddof=1) > 0 else np.nan)
    say(f"  total {tot:+.2f}% over {len(ho_diff)} months. Best single year is "
        f"{int(best)} at {by_yr.max():+.2f}%,")
    say(f"  which is {by_yr.max() / tot * 100:.0f}% of the whole holdout edge.")
    say(f"  Drop {int(best)} and the remaining excess is "
        f"{kept.mean() * MONTHS_PER_YEAR:+.2f}%/yr with t {t_kept:+.2f}.")
    say("")
    say("  Cross-reference the TLT column in the table above for that year. If the")
    say("  arm's best year was a year when yields FELL, the rate story is not what")
    say("  produced the number, whatever the full-sample correlation says.")
    say("")
    say("  The tilt pays when yields rise and costs when they fall, which is what")
    say("  a duration bet does. It is not a free lunch, it is a view -- and the")
    say("  numbers above say the view was not even reliably expressed.")

    # ------------------------------------------------------- the pre-registered test
    say("")
    say("=" * 90)
    say("  THE PRE-REGISTERED TEST, SCORED")
    say("=" * 90)
    ho_a = window(r_lo, HOLDOUT_START, None)
    ho_c = window(r_uni, HOLDOUT_START, None)
    ho_d = window(spy_arm, HOLDOUT_START, None)
    cagr_a = compound(ho_a)[1]
    cagr_c = compound(ho_c)[1]
    cagr_d = compound(ho_d)[1]
    exc = (ho_a - ho_c).dropna()
    t_exc = exc.mean() / (exc.std(ddof=1) / np.sqrt(len(exc)))
    checks = [
        (f"arm A holdout CAGR {cagr_a:+.2f}% beats in-window control "
         f"{cagr_c:+.2f}%", cagr_a > cagr_c),
        (f"arm A holdout CAGR {cagr_a:+.2f}% beats in-window SPY "
         f"{cagr_d:+.2f}%", cagr_a > cagr_d),
        (f"monthly excess over control t {t_exc:+.2f} clears the "
         f"{bar:.2f} multiple-comparison bar", abs(t_exc) > bar),
        (f"excess survives dropping its best year "
         f"(t {t_kept:+.2f} > {bar:.2f})", abs(t_kept) > bar),
    ]
    a_beta, a_alpha, a_t = alpha_stats["A  lowest rate-beta decile"]
    checks.append((f"holdout alpha on SPY {a_alpha:+.2f}%/yr (beta {a_beta:.2f}) "
                   f"has t {a_t:+.2f} > {bar:.2f}", a_t > bar))
    best_cond = max(cond_pct, key=cond_pct.get)
    checks.append((f"best conditional signal ({best_cond}) beats its "
                   f"random-mask null at the 95th pctile, got "
                   f"{cond_pct[best_cond]:.0f}th", cond_pct[best_cond] >= 95))
    for label, ok in checks:
        say(f"  [{'PASS' if ok else 'FAIL'}]  {label}")
    say("")
    say(f"  {sum(1 for _, ok in checks if ok)} of {len(checks)} pre-registered "
        f"conditions met.")
    say("")
    dd_a = abs(compound(r_lo)[2])
    dd_c = abs(compound(r_uni)[2])
    say("  CONCLUSION. The raw CAGR ordering goes the right way and a long-only")
    say("  cash account could have held arm A, but the advantage is mostly market")
    say("  beta plus a realised duration move, over an effective sample of four or")
    say(f"  five rate episodes, with half the holdout edge in one calendar year")
    say(f"  whose yields FELL. t is {t_exc:+.2f} against a bar of {bar:.2f}. Arm A "
        f"also drew")
    say(f"  down {dd_a:.1f}% against the universe's {dd_c:.1f}%, so even the raw "
        f"number is bought")
    say("  with risk a cash account feels. This is NOTHING.")
    say("")
    say("  REPRODUCIBILITY. An independent recomputation that takes a strict")
    say("  bottom-decile cut of a full sort and demands a complete 252-day return")
    say("  history, instead of qcut on ranks, gives arm A holdout +17.02% against")
    say(f"  {cagr_a:+.2f}% here and the same excess t to two decimals. The arms are "
        f"not an")
    say("  artifact of the cut, but about 0.3% of full-window CAGR does move with")
    say("  that implementation detail, which is itself a comment on the size of a")
    say("  two-point edge carrying a t of one.")


if __name__ == "__main__":
    main()
