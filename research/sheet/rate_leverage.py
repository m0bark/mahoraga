"""Does the BALANCE SHEET predict the rate hit, where price beta only restated it?

    python rate_leverage.py

THE ANGLE
rate_foresight.py handed the test a perfect rate forecast and found a -9.35%
decile spread on rate beta with t -21.61 and perfect monotonicity, and then the
decomposition killed it: 78% of that spread was (rate-beta spread) x (the TLT
move that defined the regime) plus (market-beta spread) x (the SPY move). A
price beta measured against TLT, multiplied by TLT's realised return, cannot be
anything else. It is the answer key read back out.

This file asks the same question with inputs that are NOT mechanically linked to
TLT's move. Leverage and liquidity come from SEC filings. A firm's debt-to-
equity on 2015-07-31 does not know what long rates did over the next quarter, so
if debt-to-equity sorts returns inside a rates-up window, that is an economic
statement about who gets hurt by a higher discount rate, not an arithmetic
identity. Equity duration is proxied by pe and pb: a high multiple puts more of
the value in distant cash flows, which is what a discount rate hits hardest.

THE SEVEN FEATURES, pre-registered before looking
  debt_equity       x   total liabilities / equity           feat_qual
  lt_debt_equity    x   long-term debt / equity              feat_qual
  current_ratio     x   current assets / current liabilities feat_qual
  cash_to_assets    %   cash / total assets                  feat_qual
  opinc_to_ltdebt   x   TTM operating income / LT debt        derived, see below
  pe                x   price / TTM earnings                 feat_val2
  pb                x   price / book                         feat_val2

WHY THE COVERAGE RATIO IS DERIVED BY ALGEBRA AND NOT BUILT FROM THE RAW FILINGS
The brief suggested op_income over debt_lt out of pit_fundamentals.csv. That
file is a flat one-row-per-filing table with an instant date (_end) and a filed
date and NO duration start, so there is no way to tell a quarterly op_income
from an annual one inside it. Measured: the median ratio of an FY row's
op_income to the same symbol's median quarterly op_income is 2.00, not 4.00, so
the FY rows are NOT clean annual figures and a rolling four-row sum would be
wrong by an unknown factor that varies by symbol. Rather than hand-build a bad
TTM, the ratio is recovered exactly from two columns feat_qual.py already built
with its careful duration-checked TTM:

    roic           = TTM op income / (equity + LT debt) x 100
    lt_debt_equity = LT debt / equity
  =>  TTM op income / LT debt = (roic / 100) x (1 + 1 / lt_debt_equity)

Restricted to lt_debt_equity > 0.01, which is the only region where the identity
is meaningful: negative equity flips the sign of the denominator and near-zero
LT debt sends a true coverage ratio to infinity. That restriction costs coverage
and the cost is reported. The two inputs can carry different filing dates
because feat_qual advances each input independently, so this is an approximation
at the margin; it is a cross-sectional RANK input, which is what the deciles
use, so a small dating mismatch moves a name a decile at most.

WHAT IS MEASURED, in this order
  1. Unconditional top-minus-bottom decile spreads, train and sealed holdout,
     on the month-demeaned target AND on the beta-neutralised target. This is
     where feat_qual's current_ratio claimed +1.98% train / +2.33% holdout on
     the raw target; rule 2 says that number means nothing until beta is paid
     for, and it had never been separately checked.
  2. The same spreads split by regime, where the regime is TLT's ACTUAL next
     63 days. That is deliberate lookahead, exactly as in rate_foresight.py,
     and it is the ceiling on what a correct FOMC call could buy.
  3. RULE 3. Each regime spread is decomposed into
        (market-beta spread) x (realised SPY 63d) + (rate-beta spread) x
        (realised TLT 63d) + residual
     using betas from a BIVARIATE trailing 252-day regression on SPY and TLT
     jointly, so the two exposures do not double-count their own correlation.
     The residual is the only part that is a statement about the balance sheet.
  4. Long-only actionability: the top decile's raw forward return annualised,
     against the 14.82% equal-weight benchmark this universe set.

WHAT WOULD HAVE FALSIFIED THE ANGLE, written down first
A leverage feature whose regime spread is mostly explained by the two betas is
the same restatement rate_foresight.py already found, in fundamental clothing.
A feature with a large residual that flips sign between train and holdout is
noise. The angle only survives if some feature shows a residual spread that is
(a) the same sign in train and holdout, (b) |t| over the multiplicity bar after
the sqrt(3) overlap haircut, and (c) present in the UNCONDITIONAL test too,
because a long-only cash account has no way to know the regime in advance.

THE SAMPLE IS THE BINDING CONSTRAINT. 158 monthly dates with 63-day forward
labels is about 52 independent observations, spread over four or five rate
episodes. Everything below is reported against that, not against 50,825 rows.
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

# ---------------------------------------------------------------- constants
MKT = "SPY"                  # market factor
RATE = "TLT"                 # long-Treasury factor; TLT DOWN == yields UP
BETA_WINDOW = 252            # trailing days for the bivariate factor betas
FWD_DAYS = 63                # forward horizon of grid.csv's fwd63
N_DEC = 10
TRAIN_END = pd.Timestamp("2021-09-30")
HOLDOUT_START = pd.Timestamp("2022-01-01")
OVERLAP_HAIRCUT = 1.7        # sqrt(3), 63-day labels on monthly dates
MIN_LTDE = 0.01              # below this the coverage identity is meaningless
MIN_NAMES_MONTH = 40         # a month needs this many names to cut deciles
TRADING_DAYS = 252
EW_BENCHMARK_CAGR = 14.82    # equal-weight universe, the bar from rule 4
SPY_BENCHMARK_CAGR = 14.78

FEATURES = ("debt_equity", "lt_debt_equity", "current_ratio", "cash_to_assets",
            "opinc_to_ltdebt", "pe", "pb")
# Sign convention note for reading the tables: "high decile" is the HIGH value
# of the feature, so high debt_equity = most levered, high current_ratio = most
# liquid, high pe/pb = longest equity duration.


# --------------------------------------------------------------------- data
def load_panel() -> pd.DataFrame:
    """grid plus the seven features plus beta252, all row-aligned by assertion.

    The feature CSVs are documented as row-aligned to grid.csv in the same
    order. That is asserted rather than trusted, because a silent misalignment
    would shuffle labels against features and produce pure noise that looks
    like a result."""
    g = pd.read_csv(os.path.join(LONG, "grid.csv"), parse_dates=["date"])
    q = pd.read_csv(os.path.join(LONG, "feat_qual.csv"), parse_dates=["date"])
    v = pd.read_csv(os.path.join(LONG, "feat_val2.csv"), parse_dates=["date"])
    t = pd.read_csv(os.path.join(LONG, "feat_tech.csv"), parse_dates=["date"])
    for name, b in (("qual", q), ("val2", v), ("tech", t)):
        if not (b.date.values == g.date.values).all() or \
           not (b.symbol.values == g.symbol.values).all():
            raise SystemExit(f"feat_{name}.csv is NOT row-aligned to grid.csv")
    d = g.copy()
    for c in ("debt_equity", "lt_debt_equity", "current_ratio",
              "cash_to_assets", "roic"):
        d[c] = q[c].to_numpy()
    for c in ("pe", "pb"):
        d[c] = v[c].to_numpy()
    d["beta252"] = t["beta252"].to_numpy()

    # the derived coverage ratio, see the module docstring for the algebra
    lde = d["lt_debt_equity"]
    ok = lde > MIN_LTDE
    d["opinc_to_ltdebt"] = np.where(
        ok, (d["roic"] / 100.0) * (1.0 + 1.0 / lde.where(ok)), np.nan)
    return d


def factor_betas(C: pd.DataFrame, syms: list[str]) -> tuple[pd.DataFrame,
                                                            pd.DataFrame]:
    """Trailing 252-day BIVARIATE betas on SPY and TLT jointly.

    A univariate slope on TLT, which is what rate_foresight.py used, absorbs
    part of the market because SPY and TLT are correlated. For a decomposition
    that attributes a return to two factors without double counting, the
    exposures must come from the joint regression. The 2x2 normal equations are
    solved in closed form; the factor moment matrix is the same for every name
    on a given day, so only the two cross-moments per name are panel-sized."""
    R = C[syms].pct_change()
    s = C[MKT].pct_change()
    b = C[RATE].pct_change()

    def rm(x: pd.Series) -> pd.Series:
        return x.rolling(BETA_WINDOW).mean()

    ms, mb = rm(s), rm(b)
    vss = rm(s * s) - ms * ms
    vbb = rm(b * b) - mb * mb
    vsb = rm(s * b) - ms * mb
    det = vss * vbb - vsb * vsb

    mr = R.rolling(BETA_WINDOW).mean()
    cis = R.mul(s, axis=0).rolling(BETA_WINDOW).mean().sub(mr.mul(ms, axis=0))
    cib = R.mul(b, axis=0).rolling(BETA_WINDOW).mean().sub(mr.mul(mb, axis=0))
    # guard a singular factor matrix rather than emitting silent infinities
    det = det.where(det.abs() > 1e-18)
    b_mkt = cis.mul(vbb, axis=0).sub(cib.mul(vsb, axis=0)).div(det, axis=0)
    b_rate = cib.mul(vss, axis=0).sub(cis.mul(vsb, axis=0)).div(det, axis=0)
    return b_mkt, b_rate


def forward_move(px: pd.Series, dates: np.ndarray) -> dict:
    """Realised percent move of one series over the next FWD_DAYS, per date.

    This is the deliberate lookahead. It defines the regime label and it is
    also the factor realisation used in the rule-3 decomposition, which is the
    whole point: the decomposition asks how much of the spread is exposure
    multiplied by a number nobody knew at the decision date."""
    out = {}
    for dt in dates:
        ts = pd.Timestamp(dt)
        if ts not in px.index:
            continue
        i = px.index.get_loc(ts)
        j = min(i + FWD_DAYS, len(px) - 1)
        out[ts] = (px.iloc[j] / px.iloc[i] - 1.0) * 100.0
    return out


def attach_market_data(d: pd.DataFrame) -> pd.DataFrame:
    C = pd.read_csv(os.path.join(LONG, "px_close.csv"), index_col=0,
                    parse_dates=True).sort_index()
    for need in (MKT, RATE):
        if need not in C.columns:
            raise SystemExit(f"{need} absent from px_close.csv; cannot run")
    syms = sorted(set(d.symbol) & set(C.columns))
    b_mkt, b_rate = factor_betas(C, syms)

    def melt(frame: pd.DataFrame, name: str) -> pd.DataFrame:
        m = frame.stack().rename(name).reset_index()
        m.columns = ["date", "symbol", name]
        return m

    d = d.merge(melt(b_mkt, "b_mkt"), on=["date", "symbol"], how="left")
    d = d.merge(melt(b_rate, "b_rate"), on=["date", "symbol"], how="left")

    dates = d.date.unique()
    d["spy_fwd"] = d.date.map(forward_move(C[MKT].dropna(), dates))
    d["tlt_fwd"] = d.date.map(forward_move(C[RATE].dropna(), dates))
    d = d.dropna(subset=["spy_fwd", "tlt_fwd"])
    d["regime"] = np.where(d.tlt_fwd < 0, "rates UP", "rates DOWN")
    return d


def add_targets(d: pd.DataFrame) -> pd.DataFrame:
    """y_dm: forward return minus the month's universe mean. Selection only.

    y_bn: rule 2. Within each month, regress y_dm on beta252 and keep the
    residual. Demeaning removes the market's LEVEL, not exposure to it; this
    removes the part of the cross-section that is paid for carrying beta."""
    d = d.dropna(subset=["fwd63"]).copy()
    d["y_dm"] = d.fwd63 - d.groupby("date")["fwd63"].transform("mean")

    def resid(g: pd.DataFrame) -> pd.Series:
        x = g["beta252"].to_numpy(dtype=float)
        y = g["y_dm"].to_numpy(dtype=float)
        m = np.isfinite(x) & np.isfinite(y)
        out = pd.Series(np.nan, index=g.index)
        if m.sum() < MIN_NAMES_MONTH:
            return out
        slope, icpt = np.polyfit(x[m], y[m], 1)
        out.loc[g.index[m]] = y[m] - (icpt + slope * x[m])
        return out

    d["y_bn"] = d.groupby("date", group_keys=False).apply(resid)
    return d


# ------------------------------------------------------------ measurements
def deciles(s: pd.Series) -> pd.Series:
    """Decile labels within a single month, ties broken by position.

    method="first" rather than the default average: a fundamental ratio has
    repeated values (carried-forward filings), and average ranks let one tie
    block straddle a decile edge and empty a slice."""
    if s.notna().sum() < N_DEC:
        return pd.Series(np.nan, index=s.index)
    return pd.qcut(s.rank(method="first"), N_DEC, labels=False,
                   duplicates="drop")


def pooled_spread(df: pd.DataFrame, col: str, y: str) -> tuple:
    """House-pattern decile spread: pooled rows, cross-sectional t, monotonicity."""
    s = df[[col, y, "date"]].dropna()
    if len(s) < 500 or s[col].nunique() < N_DEC:
        return np.nan, np.nan, 0, np.nan
    s = s.copy()
    s["dec"] = s.groupby("date")[col].transform(deciles)
    s = s.dropna(subset=["dec"])
    if s.empty:
        return np.nan, np.nan, 0, np.nan
    top = s.dec.max()
    hi = s.loc[s.dec == top, y]
    lo = s.loc[s.dec == 0, y]
    if len(hi) < 2 or len(lo) < 2:
        return np.nan, np.nan, len(s), np.nan
    se = np.sqrt(hi.var(ddof=1) / len(hi) + lo.var(ddof=1) / len(lo))
    t = (hi.mean() - lo.mean()) / se if se > 0 else np.nan
    means = s.groupby("dec")[y].mean()
    mono = means.corr(pd.Series(means.index, index=means.index),
                      method="spearman")
    return hi.mean() - lo.mean(), t, len(s), mono


def monthly_legs(d: pd.DataFrame, col: str, y: str) -> pd.DataFrame:
    """One row per month: the long-short spread and its factor exposures.

    The unit of observation here is the MONTH, not the row, because a month's
    names share a market and a rate move. Everything in the decomposition is
    aggregated from this frame."""
    need = [col, y, "b_mkt", "b_rate", "spy_fwd", "tlt_fwd", "fwd63"]
    rows = []
    for dt, g in d.groupby("date"):
        x = g[need].dropna()
        if len(x) < MIN_NAMES_MONTH or x[col].nunique() < N_DEC:
            continue
        q = deciles(x[col])
        hi, lo = x[q == q.max()], x[q == 0]
        if len(hi) < 2 or len(lo) < 2:
            continue
        rows.append({
            "date": dt,
            "spread": hi[y].mean() - lo[y].mean(),
            "d_b_mkt": hi.b_mkt.mean() - lo.b_mkt.mean(),
            "d_b_rate": hi.b_rate.mean() - lo.b_rate.mean(),
            # the LONG-ONLY version of the same exposures: top decile against
            # the measurable universe that month, not against the bottom decile
            "u_b_mkt": hi.b_mkt.mean() - x.b_mkt.mean(),
            "u_b_rate": hi.b_rate.mean() - x.b_rate.mean(),
            "spy_fwd": x.spy_fwd.iloc[0],
            "tlt_fwd": x.tlt_fwd.iloc[0],
            "hi_raw": hi.fwd63.mean(),
            "uni_raw": x.fwd63.mean(),     # equal weight over the MEASURABLE names
            "all_raw": g.fwd63.mean(),     # equal weight over the whole month
            "n": len(x),
        })
    m = pd.DataFrame(rows)
    if m.empty:
        return m
    m["explained"] = m.d_b_mkt * m.spy_fwd + m.d_b_rate * m.tlt_fwd
    m["residual"] = m.spread - m.explained
    m["excess"] = m.hi_raw - m.uni_raw
    m["u_explained"] = m.u_b_mkt * m.spy_fwd + m.u_b_rate * m.tlt_fwd
    m["u_residual"] = m.excess - m.u_explained
    return m


def series_t(x: pd.Series) -> float:
    """t of a monthly series mean. Reported before the overlap haircut."""
    x = x.dropna()
    if len(x) < 3 or x.std(ddof=1) == 0:
        return np.nan
    return float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x))))


def annualise(pct_63d: float) -> float:
    """A 63-day percent return expressed as a CAGR, for the 14.82% comparison."""
    if not np.isfinite(pct_63d) or pct_63d <= -100.0:
        return np.nan
    return ((1.0 + pct_63d / 100.0) ** (TRADING_DAYS / FWD_DAYS) - 1.0) * 100.0


def bar(k: int) -> float:
    """Multiplicity bar from rule 5: sqrt(2 ln K) for K variants searched."""
    return float(np.sqrt(2.0 * np.log(max(k, 2))))


# ----------------------------------------------------------------- reports
def report_setup(d: pd.DataFrame) -> None:
    say("=" * 86)
    say("  SETUP")
    say("=" * 86)
    say(f"  {len(d):,} rows | {d.symbol.nunique()} symbols | "
        f"{d.date.nunique()} months | {d.date.min():%Y-%m} .. {d.date.max():%Y-%m}")
    n_up = d[d.regime == "rates UP"].date.nunique()
    say(f"  regime by ACTUAL next {FWD_DAYS}d of {RATE}: "
        f"{n_up} months rates UP, {d.date.nunique() - n_up} rates DOWN")
    say(f"  effective independent observations ~ {d.date.nunique() // 3} "
        f"({FWD_DAYS}-day labels on monthly dates)")
    say("")
    say(f"  {'feature':<18}{'coverage':>10}{'months usable':>15}"
        f"{'p5':>10}{'median':>10}{'p95':>10}")
    say("  " + "-" * 73)
    for c in FEATURES:
        s = d[c]
        per = d.dropna(subset=[c]).groupby("date")[c].count()
        usable = int((per >= MIN_NAMES_MONTH).sum())
        say(f"  {c:<18}{s.notna().mean():>9.1%}{usable:>15}"
            f"{s.quantile(0.05):>+10.2f}{s.median():>+10.2f}"
            f"{s.quantile(0.95):>+10.2f}")
    say("")
    say("  opinc_to_ltdebt is thin by construction: it needs roic AND a")
    say("  positive lt_debt_equity on the same row. Cost of that restriction is")
    say("  the coverage figure above, not a silent subset.")


def report_unconditional(tr: pd.DataFrame, ho: pd.DataFrame) -> pd.DataFrame:
    say("")
    say("=" * 86)
    say("  1. UNCONDITIONAL DECILE SPREADS -- no rate view at all")
    say("=" * 86)
    b = bar(len(FEATURES))
    say(f"  Seven pre-registered features, so the bar is |t| > sqrt(2 ln 7) = "
        f"{b:.2f}.")
    say(f"  Divide every t by {OVERLAP_HAIRCUT} first for the overlapping-label")
    say("  inflation. y_dm = demeaned within month. y_bn = rule 2, beta252")
    say("  regressed out within month.")
    say("")
    say(f"  {'feature':<18}{'tr y_dm':>9}{'t':>7}{'ho y_dm':>9}{'t':>7}"
        f"{'tr y_bn':>9}{'t':>7}{'ho y_bn':>9}{'t':>7}{'mono':>7}")
    say("  " + "-" * 82)
    rows = []
    for c in FEATURES:
        a_tr, ta_tr, _, mono = pooled_spread(tr, c, "y_dm")
        a_ho, ta_ho, _, _ = pooled_spread(ho, c, "y_dm")
        b_tr, tb_tr, _, _ = pooled_spread(tr, c, "y_bn")
        b_ho, tb_ho, _, _ = pooled_spread(ho, c, "y_bn")
        rows.append({"feature": c, "dm_tr": a_tr, "dm_ho": a_ho,
                     "bn_tr": b_tr, "bn_ho": b_ho, "bn_t_ho": tb_ho,
                     "bn_t_tr": tb_tr})
        say(f"  {c:<18}{a_tr:>+8.2f}%{ta_tr:>+7.2f}{a_ho:>+8.2f}%{ta_ho:>+7.2f}"
            f"{b_tr:>+8.2f}%{tb_tr:>+7.2f}{b_ho:>+8.2f}%{tb_ho:>+7.2f}"
            f"{mono:>+7.2f}")
    s = pd.DataFrame(rows)
    say("  " + "-" * 82)
    survive = s[(np.sign(s.bn_tr) == np.sign(s.bn_ho))
                & (s.bn_t_tr.abs() > b * OVERLAP_HAIRCUT)
                & (s.bn_t_ho.abs() > 1.96 * OVERLAP_HAIRCUT)]
    say(f"  {len(survive)} of {len(FEATURES)} survive BETA-NEUTRAL with a "
        f"consistent sign and t past the haircut bar.")
    return s


def report_regimes(d: pd.DataFrame) -> dict:
    say("")
    say("=" * 86)
    say("  2. THE SAME SPREADS SPLIT BY THE ACTUAL RATE MOVE (lookahead, on purpose)")
    say("=" * 86)
    say("  This is the ceiling on a correct FOMC call, not a tradable number.")
    say("  A long-only cash account does not know the regime on the decision")
    say("  date, so read this as diagnosis and section 1 as the trade.")
    say("")
    k = len(FEATURES) * 2
    say(f"  Seven features in two regimes is K={k} variants, bar |t| > "
        f"{bar(k):.2f} before the {OVERLAP_HAIRCUT}x overlap haircut.")
    legs = {}
    for y, label in (("y_dm", "month-demeaned"), ("y_bn", "beta-neutral")):
        say("")
        say(f"  TARGET: {label}")
        say(f"  {'feature':<18}{'regime':<12}{'months':>8}{'spread':>10}"
            f"{'t(monthly)':>12}{'t/1.7':>8}")
        say("  " + "-" * 70)
        for c in FEATURES:
            for r in ("rates UP", "rates DOWN"):
                m = monthly_legs(d[d.regime == r], c, y)
                if m.empty:
                    continue
                legs[(c, r, y)] = m
                t = series_t(m.spread)
                say(f"  {c:<18}{r:<12}{len(m):>8}{m.spread.mean():>+9.2f}%"
                    f"{t:>+12.2f}{t / OVERLAP_HAIRCUT:>+8.2f}")
    return legs


def report_decomposition(legs: dict) -> pd.DataFrame:
    say("")
    say("=" * 86)
    say("  3. RULE 3 -- HOW MUCH IS JUST EXPOSURE TIMES THE REALISED FACTOR MOVE?")
    say("=" * 86)
    say("  spread = d(market beta) x SPY_63d + d(rate beta) x TLT_63d + residual")
    say("  Betas are from the BIVARIATE trailing-252d regression on SPY and TLT")
    say("  together. d(.) is the top-decile mean minus the bottom-decile mean.")
    say("  The residual is the only part that is a claim about the balance sheet.")
    say("")
    say(f"  {'feature':<18}{'regime':<12}{'d bmkt':>8}{'d brate':>9}"
        f"{'spread':>9}{'expl':>8}{'resid':>8}{'%expl':>8}{'t resid':>9}")
    say("  " + "-" * 81)
    rows = []
    for (c, r, y), m in legs.items():
        if y != "y_dm":
            continue
        act, ex, re_ = m.spread.mean(), m.explained.mean(), m.residual.mean()
        frac = 100.0 * ex / act if abs(act) > 1e-9 else np.nan
        tr_ = series_t(m.residual)
        rows.append({"feature": c, "regime": r, "spread": act, "expl": ex,
                     "resid": re_, "pct_expl": frac, "t_resid": tr_})
        say(f"  {c:<18}{r:<12}{m.d_b_mkt.mean():>+8.2f}"
            f"{m.d_b_rate.mean():>+9.2f}{act:>+8.2f}%{ex:>+7.2f}%"
            f"{re_:>+7.2f}%{frac:>+7.0f}%{tr_:>+9.2f}")
    say("  " + "-" * 81)
    say("  A %expl near 100 means the spread IS the two betas handed an answer")
    say("  key, which is what rate_foresight.py found for price rate beta.")
    say("  A %expl near 0 with a small spread means there was nothing to")
    say("  explain in the first place -- check the spread column before")
    say("  celebrating a clean residual.")
    return pd.DataFrame(rows)


def report_split_residuals(d: pd.DataFrame) -> None:
    """Does the regime residual keep its sign across the sealed split?

    Section 3 pools all 158 months, which is a fit-and-judge-on-the-same-data
    measurement. A residual that is one sign before 2021-10 and the other sign
    after is an artefact of two or three rate episodes, not a channel."""
    say("")
    say("=" * 86)
    say("  3b. THE REGIME RESIDUALS ACROSS THE SEALED SPLIT")
    say("=" * 86)
    say("  Same decomposition, computed separately on train months and holdout")
    say("  months. A sign flip here ends the story for that cell.")
    say("")
    say(f"  {'feature':<18}{'regime':<12}{'tr mo':>6}{'tr resid':>10}{'t':>7}"
        f"{'ho mo':>7}{'ho resid':>10}{'t':>7}  sign")
    say("  " + "-" * 80)
    for c in FEATURES:
        for r in ("rates UP", "rates DOWN"):
            sub = d[d.regime == r]
            m_tr = monthly_legs(sub[sub.date <= TRAIN_END], c, "y_dm")
            m_ho = monthly_legs(sub[sub.date >= HOLDOUT_START], c, "y_dm")
            if m_tr.empty or m_ho.empty:
                continue
            a, b = m_tr.residual.mean(), m_ho.residual.mean()
            agree = "same" if np.sign(a) == np.sign(b) else "FLIPS"
            say(f"  {c:<18}{r:<12}{len(m_tr):>6}{a:>+9.2f}%"
                f"{series_t(m_tr.residual):>+7.2f}{len(m_ho):>7}{b:>+9.2f}%"
                f"{series_t(m_ho.residual):>+7.2f}  {agree}")


def report_longonly(ho: pd.DataFrame) -> pd.DataFrame:
    say("")
    say("=" * 86)
    say("  4. COULD A LONG-ONLY CASH ACCOUNT ACT? TOP DECILE, RAW RETURNS")
    say("=" * 86)
    say(f"  Holdout only, {HOLDOUT_START:%Y-%m} onward. Raw forward 63-day")
    say("  return of the top decile, annualised the same way for the universe")
    say("  so the comparison is arithmetic-identical. The bar is the equal-")
    say(f"  weight universe at {EW_BENCHMARK_CAGR:.2f}% and SPY at "
        f"{SPY_BENCHMARK_CAGR:.2f}% CAGR.")
    say("  'univ' is equal weight over the names where the feature EXISTS that")
    say("  month, which is the only portfolio the screen competes against;")
    say("  'all' is equal weight over the whole month for reference.")
    say("")
    say(f"  {'feature':<18}{'months':>7}{'top 63d':>9}{'univ 63d':>10}"
        f"{'all 63d':>9}{'top CAGR':>10}{'univ CAGR':>11}{'vs 14.82':>10}")
    say("  " + "-" * 82)
    rows = []
    legs = {}
    for c in FEATURES:
        m = monthly_legs(ho, c, "y_dm")
        if m.empty:
            continue
        legs[c] = m
        top, uni, alld = m.hi_raw.mean(), m.uni_raw.mean(), m.all_raw.mean()
        ct, cu = annualise(top), annualise(uni)
        rows.append({"feature": c, "top_cagr": ct, "univ_cagr": cu,
                     "excess": m.excess.mean(),
                     "u_resid": m.u_residual.mean(),
                     "t_excess": series_t(m.excess),
                     "t_u_resid": series_t(m.u_residual)})
        say(f"  {c:<18}{len(m):>7}{top:>+8.2f}%{uni:>+9.2f}%{alld:>+8.2f}%"
            f"{ct:>+9.2f}%{cu:>+10.2f}%{ct - EW_BENCHMARK_CAGR:>+9.2f}%")
    say("")
    say("  AND THE SAME EXCESS, WITH THE TWO BETAS PAID FOR (rule 3, long-only)")
    say("  excess = top decile minus the measurable universe. explained =")
    say("  (top-minus-universe market beta) x SPY_63d + (ditto rate beta) x")
    say("  TLT_63d. A long-only screen that only beats equal weight because it")
    say("  holds more beta in a rising market is a leverage choice, not a screen.")
    say("")
    say(f"  {'feature':<18}{'d bmkt':>8}{'d brate':>9}{'excess':>9}{'t':>7}"
        f"{'expl':>8}{'resid':>8}{'t':>7}{'resid CAGR':>12}")
    say("  " + "-" * 78)
    s = pd.DataFrame(rows)
    for c in FEATURES:
        if c not in legs:
            continue
        m = legs[c]
        ex, exp, re_ = m.excess.mean(), m.u_explained.mean(), m.u_residual.mean()
        # what the top decile would have compounded at if it had carried the
        # universe's betas instead of its own
        cagr = annualise(m.uni_raw.mean() + re_)
        say(f"  {c:<18}{m.u_b_mkt.mean():>+8.2f}{m.u_b_rate.mean():>+9.2f}"
            f"{ex:>+8.2f}%{series_t(m.excess):>+7.2f}{exp:>+7.2f}%"
            f"{re_:>+7.2f}%{series_t(m.u_residual):>+7.2f}{cagr:>+11.2f}%")
    say("  " + "-" * 78)
    return s


def report_verdict(uncond: pd.DataFrame, dec: pd.DataFrame,
                   lo: pd.DataFrame) -> None:
    say("")
    say("=" * 86)
    say("  VERDICT")
    say("=" * 86)
    b = bar(len(FEATURES)) * OVERLAP_HAIRCUT
    kept = uncond[(np.sign(uncond.bn_tr) == np.sign(uncond.bn_ho))
                  & (uncond.bn_t_tr.abs() > b)
                  & (uncond.bn_t_ho.abs() > 1.96 * OVERLAP_HAIRCUT)]
    say(f"  Unconditional, beta-neutral, both halves, past the haircut bar: "
        f"{len(kept)} of {len(FEATURES)}.")
    if len(kept):
        for r in kept.itertuples():
            say(f"    {r.feature}: train {r.bn_tr:+.2f}% / holdout "
                f"{r.bn_ho:+.2f}%")
    big = dec[dec.spread.abs() > 1.0]
    if len(big):
        say("")
        say("  Regime spreads over 1% in magnitude, and what is left of them")
        say("  after the two betas are paid their realised factor returns:")
        for r in big.sort_values("spread", key=abs, ascending=False).itertuples():
            say(f"    {r.feature:<17}{r.regime:<12}{r.spread:>+7.2f}% -> "
                f"residual {r.resid:>+6.2f}% (t {r.t_resid:+.2f}, "
                f"{r.pct_expl:+.0f}% explained by beta)")
    say("")
    say("  LONG-ONLY, holdout, top decile against the measurable universe:")
    for r in lo.sort_values("excess", ascending=False).itertuples():
        say(f"    {r.feature:<17}top CAGR {r.top_cagr:>+6.2f}% vs univ "
            f"{r.univ_cagr:>+6.2f}%  excess {r.excess:+.2f}% (t "
            f"{r.t_excess:+.2f}) of which residual {r.u_resid:+.2f}% "
            f"(t {r.t_u_resid:+.2f})")
    say("")
    say("  A residual that clears the bar ONLY inside a regime is not a trade")
    say("  for a cash account: the regime label is the next quarter's TLT")
    say("  return. It would only matter as evidence that an FOMC call has an")
    say("  economic transmission channel worth forecasting.")


def main() -> None:
    say("LOADING")
    d = load_panel()
    d = attach_market_data(d)
    d = add_targets(d)
    report_setup(d)

    tr = d[d.date <= TRAIN_END]
    ho = d[d.date >= HOLDOUT_START]
    dropped = d[(d.date > TRAIN_END) & (d.date < HOLDOUT_START)]
    say("")
    say(f"  train   {len(tr):>7,} rows  {tr.date.min():%Y-%m} .. "
        f"{tr.date.max():%Y-%m}  ({tr.date.nunique()} months)")
    say(f"  embargo {len(dropped):>7,} rows dropped "
        f"({dropped.date.nunique()} months of overlapping labels)")
    say(f"  holdout {len(ho):>7,} rows  {ho.date.min():%Y-%m} .. "
        f"{ho.date.max():%Y-%m}  ({ho.date.nunique()} months)")

    uncond = report_unconditional(tr, ho)
    legs = report_regimes(d)
    dec = report_decomposition(legs)
    report_split_residuals(d)
    lo = report_longonly(ho)
    report_verdict(uncond, dec, lo)


if __name__ == "__main__":
    main()
