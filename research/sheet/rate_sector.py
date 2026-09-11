"""Sector rotation in rates-up windows. Is a sector tilt anything but two betas?

    python research/sheet/rate_sector.py

THE ANGLE
A stock screener cannot be run in a cash account without a lot of work, but a
sector tilt can: you buy one ETF. So if a rate view is worth anything at all to
a long-only account, the cheapest possible expression is "rates are going up,
overweight sector X". This file measures whether that sentence has ever been
true in this sample, and then whether what is left of it after paying for the
two exposures you already hold is worth the trade.

THE DELIBERATE LOOKAHEAD, same as rate_foresight.py
Each month is classified rates-UP or rates-DOWN by what TLT ACTUALLY DID over
the following 63 trading days. Nobody knows that on the decision date. It is
granted on purpose: it is the best possible case for a rate view. If a sector
tilt cannot pay with the answer key face up, a tilt driven by a forecast that is
right 60% of the time cannot pay either.

WHAT IS MEASURED, in order
  1. Each sector's equal-weight forward 63-day return MINUS the universe mean
     that month, averaged separately over rates-UP and rates-DOWN months. The
     t-statistic is computed on the MONTHLY series, not pooled over stock-rows:
     forty names in one sector in one month share a sector and a market and are
     not forty observations.
  2. THE DECOMPOSITION THAT DECIDES IT. Each name's market beta and rate beta
     come from ONE joint trailing 252-day regression of its daily returns on
     SPY and TLT, so the two exposures are not double-counted the way two
     separate univariate betas would be. A sector's predicted relative return is
     (its market-beta spread) x (realised SPY move) + (its rate-beta spread) x
     (realised TLT move). Subtract that and report the residual. A sector whose
     rates-up edge is all prediction and no residual is not a rotation, it is
     the beta you already own multiplied by an answer key.
  3. A BETA-NEUTRALISED TARGET, per the house rule that demeaning within a month
     removes the market's level and not your exposure to it. Forward return is
     regressed cross-sectionally on beta252 (and separately on beta252 plus rate
     beta) within each month, and the sector table is rebuilt on the residual.
  4. EPISODE STABILITY. Three distinct hiking episodes live in this sample:
     the 2013 taper, the 2015-2018 hikes and the 2022-2023 hikes. Three episodes
     is THREE observations. The sign table is reported as three observations and
     no t-statistic is attached to it.
  5. THE SEALED SPLIT. Sectors are ranked by their rates-up figure on dates
     <= 2021-09-30 and that ranking is judged once on dates >= 2022-01-01, with
     the three months between dropped because fwd63 overlaps them.
  6. WHAT A CASH ACCOUNT COULD ACTUALLY DO. The regime label is lookahead, so a
     regime-conditional tilt is not implementable. The implementable version is
     an always-on sector tilt, so each sector's equal-weight monthly-rebalanced
     compounded return is computed from px_close over the holdout and compared
     with the 14.82% equal-weight universe bar.

WHAT WOULD HAVE FALSIFIED IT
A sector whose rates-up relative return (a) is large, (b) keeps most of its size
as a residual after both betas are paid for, (c) has the same sign in all three
episodes, and (d) holds its rank out of sample. Any of those missing and the
answer is no. State it as a failure in the same words it would have been stated
as a success.

KNOWN LIMITATIONS, stated before the numbers
  * sp500.csv carries CURRENT GICS sector labels, not point-in-time ones. Real
    Estate was carved out of Financials in 2016 and Communication Services was
    created in 2018, so pre-2018 rows labelled Communication Services were then
    classified elsewhere and XLC did not exist to buy. This is a classification
    anachronism, not a return lookahead, but it weakens the "buy the ETF" claim
    for those two sectors specifically.
  * Price LEVELS are never used. Only ratios of two closes and returns, which
    are immune to the adjustment factor. See CONTAMINATED in tree_screen.py.
  * Overlapping 63-day windows on monthly dates inflate t by about sqrt(3).
    Eleven sectors are tested, so the bar is sqrt(2*ln(11)) = 2.19 AFTER that
    division, which is a raw |t| of about 3.7.
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
SECTOR_FILE = os.path.join(HERE, "sp500.csv")

MKT = "SPY"                 # market factor
RATE = "TLT"                # long-Treasury factor; TLT down == yields up
BETA_WINDOW = 252           # trailing days for the joint two-factor regression
FWD_DAYS = 63               # matches grid.csv fwd63 exactly
MIN_NAMES = 8               # a sector-month with fewer names is not a sector
N_SECTORS = 11
OVERLAP_INFLATION = np.sqrt(3.0)   # 63-day windows on monthly dates
MULTI_TEST_BAR = float(np.sqrt(2 * np.log(N_SECTORS)))

# Sealed split, with the embargo the overlapping labels force.
SEARCH_END = pd.Timestamp("2021-09-30")
HOLDOUT_START = pd.Timestamp("2022-01-01")

# The bar from rule 4: equal-weight this universe compounded at +14.82%/yr and
# SPY at +14.78%. Not the ~9% long-run average.
EW_UNIVERSE_CAGR = 14.82
SPY_CAGR = 14.78

# Three distinct hiking episodes. These are the THREE observations in the
# stability section; they are not 72 independent months.
EPISODES: tuple[tuple[str, str, str], ...] = (
    ("2013 taper", "2013-05-01", "2013-12-31"),
    ("2015-2018 hikes", "2015-12-01", "2018-12-31"),
    ("2022-2023 hikes", "2022-01-01", "2023-10-31"),
)


# --------------------------------------------------------------------- data
def load_panel() -> tuple[pd.DataFrame, pd.DataFrame]:
    """grid.csv joined to sector labels and to beta252, plus the price panel."""
    g = pd.read_csv(os.path.join(LONG, "grid.csv"), parse_dates=["date"])
    C = pd.read_csv(os.path.join(LONG, "px_close.csv"), index_col=0,
                    parse_dates=True).sort_index()
    for need in (MKT, RATE):
        if need not in C.columns:
            raise SystemExit(f"{need} absent from px_close.csv; cannot run")

    sec = pd.read_csv(SECTOR_FILE)[["symbol", "sector"]]
    g = g.merge(sec, on="symbol", how="left")
    n_miss = int(g.sector.isna().sum())

    # beta252 is the house market beta and is needed for the rule-2 check.
    t = pd.read_csv(os.path.join(LONG, "feat_tech.csv"),
                    parse_dates=["date"])[["date", "symbol", "beta252"]]
    g = g.merge(t, on=["date", "symbol"], how="left")

    say(f"  grid {len(g):,} rows | {g.symbol.nunique()} symbols | "
        f"{g.date.nunique()} months {g.date.min():%Y-%m}..{g.date.max():%Y-%m}")
    say(f"  sectors {g.sector.nunique()} | unmapped symbols {n_miss} rows")
    g = g.dropna(subset=["sector"])
    return g, C


def two_factor_betas(C: pd.DataFrame, syms: list[str]
                     ) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Joint trailing regression of each name on SPY and TLT, daily returns.

    WHY JOINT AND NOT TWO UNIVARIATE SLOPES. SPY and TLT are correlated, so a
    univariate TLT beta partly restates market exposure and a univariate market
    beta partly restates rate exposure. Adding two univariate exposure terms in
    the decomposition would then double-count whatever the two factors share and
    could explain more than 100% of a sector's return. The 2x2 normal equations
    have a closed form, so this costs nothing:

        [Vss Vst][b_m]   [Cis]
        [Vst Vtt][b_r] = [Cit]

    Only ROLLING MOMENTS OF RETURNS appear. No price level is used anywhere, so
    the adjustment-factor contamination documented in tree_screen.py cannot
    enter here: the factor cancels in every pct_change.
    """
    # px_close.csv carries a few NON-TRADING rows with every price NaN
    # (2026-05-25 Memorial Day, 2026-09-07 Labor Day). pct_change turns one such
    # row into TWO NaN returns, and rolling(252) with the default min_periods
    # then returns NaN for the following 252 days. Left alone that silently
    # deleted the whole 2026-05-29 decision month from the panel -- 347 rows, one
    # of 158 months -- which is exactly the kind of quiet drop that makes two
    # runs of the same measurement disagree. A day the market proxy did not
    # trade is not a trading day, so it is removed before any return is taken.
    # The forward factor moves deliberately keep the ORIGINAL index so their
    # 63-row offsets stay on the same convention grid.py used to build fwd63.
    Cc = C[C[[MKT, RATE]].notna().all(axis=1)]
    R = Cc[syms].pct_change()
    rs = Cc[MKT].pct_change()
    rt = Cc[RATE].pct_change()
    W = BETA_WINDOW

    def cov_ss(a: pd.Series, b: pd.Series) -> pd.Series:
        return ((a * b).rolling(W).mean()
                - a.rolling(W).mean() * b.rolling(W).mean())

    def cov_panel(P: pd.DataFrame, b: pd.Series) -> pd.DataFrame:
        return (P.mul(b, axis=0).rolling(W).mean()
                .sub(P.rolling(W).mean().mul(b.rolling(W).mean(), axis=0)))

    v_ss, v_tt, v_st = cov_ss(rs, rs), cov_ss(rt, rt), cov_ss(rs, rt)
    c_is, c_it = cov_panel(R, rs), cov_panel(R, rt)
    det = v_ss * v_tt - v_st ** 2
    b_m = c_is.mul(v_tt, axis=0).sub(c_it.mul(v_st, axis=0)).div(det, axis=0)
    b_r = c_it.mul(v_ss, axis=0).sub(c_is.mul(v_st, axis=0)).div(det, axis=0)
    return b_m, b_r


def forward_factor_moves(C: pd.DataFrame, dates: np.ndarray
                         ) -> pd.DataFrame:
    """THE DELIBERATE LOOKAHEAD: what SPY and TLT actually did next, in percent.

    A ratio of two adjusted closes is a valid total return, so this is clean.
    """
    rows = []
    for dt in dates:
        ts = pd.Timestamp(dt)
        if ts not in C.index:
            continue
        i = C.index.get_loc(ts)
        j = min(i + FWD_DAYS, len(C.index) - 1)
        rows.append({
            "date": ts,
            "spy_fwd": (C[MKT].iloc[j] / C[MKT].iloc[i] - 1) * 100,
            "tlt_fwd": (C[RATE].iloc[j] / C[RATE].iloc[i] - 1) * 100,
        })
    f = pd.DataFrame(rows)
    # TLT falling means yields rising means a hawkish / hiking window.
    f["regime"] = np.where(f.tlt_fwd < 0, "rates UP", "rates DOWN")
    return f


# ------------------------------------------------------ the monthly sector panel
def sector_months(d: pd.DataFrame, target: str = "fwd63") -> pd.DataFrame:
    """One row per (date, sector): equal-weight target minus the universe mean.

    Equal-weight inside the sector and equal-weight for the universe mean, which
    is the benchmark rule 4 pins at +14.82%.
    """
    univ = d.groupby("date")[target].mean().rename("univ")
    sm = (d.groupby(["date", "sector"])
          .agg(ew=(target, "mean"), n=(target, "size"),
               b_mkt=("b_mkt", "mean"), b_rate=("b_rate", "mean"))
          .reset_index())
    ub = (d.groupby("date")[["b_mkt", "b_rate"]].mean()
          .rename(columns={"b_mkt": "ub_mkt", "b_rate": "ub_rate"}))
    sm = sm.merge(univ, on="date").merge(ub, on="date")
    sm = sm[sm.n >= MIN_NAMES].copy()
    sm["rel"] = sm.ew - sm.univ
    sm["d_mkt"] = sm.b_mkt - sm.ub_mkt      # market-beta spread vs the universe
    sm["d_rate"] = sm.b_rate - sm.ub_rate   # rate-beta spread vs the universe
    return sm


def t_monthly(x: pd.Series) -> float:
    """t on the MONTHLY series, raw. The caller divides by the overlap factor.

    Pooling stock-rows would treat forty names in one sector-month as forty
    independent draws. They share a sector and a market; they are one draw.
    """
    x = x.dropna()
    if len(x) < 3 or x.std(ddof=1) == 0:
        return np.nan
    return float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x))))


def regime_table(sm: pd.DataFrame, f: pd.DataFrame, title: str,
                 label: str = "rel") -> pd.DataFrame:
    """The headline table, sorted by the rates-UP figure."""
    m = sm.merge(f[["date", "regime"]], on="date")
    out = []
    for s, sub in m.groupby("sector"):
        up = sub.loc[sub.regime == "rates UP", label]
        dn = sub.loc[sub.regime == "rates DOWN", label]
        out.append({
            "sector": s, "n_up": len(up), "n_dn": len(dn),
            "up": up.mean(), "dn": dn.mean(),
            "t_up": t_monthly(up), "t_dn": t_monthly(dn),
            "all": sub[label].mean(), "t_all": t_monthly(sub[label]),
        })
    r = pd.DataFrame(out).sort_values("up", ascending=False)

    say("")
    say("=" * 94)
    say(f"  {title}")
    say("=" * 94)
    say(f"  {'sector':<24}{'n up':>6}{'rates UP':>11}{'t/1.7':>8}"
        f"{'n dn':>6}{'rates DOWN':>12}{'t/1.7':>8}{'all months':>12}{'t/1.7':>8}")
    say("  " + "-" * 90)
    for x in r.itertuples():
        say(f"  {x.sector:<24}{x.n_up:>6}{x.up:>+10.2f}%"
            f"{x.t_up / OVERLAP_INFLATION:>+8.2f}"
            f"{x.n_dn:>6}{x.dn:>+11.2f}%{x.t_dn / OVERLAP_INFLATION:>+8.2f}"
            f"{getattr(x, 'all'):>+11.2f}%{x.t_all / OVERLAP_INFLATION:>+8.2f}")
    say("  " + "-" * 90)
    pass_bar = [x.sector for x in r.itertuples()
                if np.isfinite(x.t_up)
                and abs(x.t_up / OVERLAP_INFLATION) > MULTI_TEST_BAR]
    say(f"  Bar for the rates-UP column with {N_SECTORS} sectors tested: "
        f"|t| > {MULTI_TEST_BAR:.2f} after dividing by {OVERLAP_INFLATION:.2f}.")
    say(f"  Clearing it: {', '.join(pass_bar) if pass_bar else 'none'}")
    return r


# --------------------------------------------- exposure x realised factor return
def decompose(sm: pd.DataFrame, f: pd.DataFrame) -> pd.DataFrame:
    """Rule 3. How much of each sector's rates-up edge is beta with the answer?

    predicted  = d_mkt * realised SPY move + d_rate * realised TLT move
    residual   = actual relative return - predicted

    Both exposures are point-in-time (trailing 252 days). Both factor moves are
    the realised FORWARD moves, i.e. the answer key. If predicted tracks actual,
    the sector "rotation" is the portfolio's standing factor loadings being
    handed next quarter's factor returns, which is a restatement of what the
    sector is, not a forecast of what it will do.
    """
    m = sm.merge(f[["date", "spy_fwd", "tlt_fwd", "regime"]], on="date")
    m["pred"] = m.d_mkt * m.spy_fwd + m.d_rate * m.tlt_fwd
    m["resid"] = m.rel - m.pred
    up = m[m.regime == "rates UP"]

    say("")
    say("=" * 94)
    say("  DECOMPOSITION IN RATES-UP MONTHS: exposure x realised factor return")
    say("=" * 94)
    say("  b_mkt and b_rate are sector averages from ONE joint trailing")
    say("  regression on SPY and TLT. The spreads are against the universe mean.")
    say("")
    say(f"  {'sector':<24}{'b_mkt':>7}{'b_rate':>8}{'actual':>10}"
        f"{'predicted':>11}{'residual':>10}{'t resid':>9}{'% expl':>8}")
    say("  " + "-" * 90)
    rows = []
    for s, sub in up.groupby("sector"):
        a, p, e = sub.rel.mean(), sub.pred.mean(), sub.resid.mean()
        expl = 100 * p / a if abs(a) > 1e-9 else np.nan
        rows.append({"sector": s, "b_mkt": sub.b_mkt.mean(),
                     "b_rate": sub.b_rate.mean(), "actual": a, "pred": p,
                     "resid": e, "t_resid": t_monthly(sub.resid),
                     "explained_pct": expl})
    r = pd.DataFrame(rows).sort_values("actual", ascending=False)
    for x in r.itertuples():
        say(f"  {x.sector:<24}{x.b_mkt:>7.2f}{x.b_rate:>8.2f}{x.actual:>+9.2f}%"
            f"{x.pred:>+10.2f}%{x.resid:>+9.2f}%"
            f"{x.t_resid / OVERLAP_INFLATION:>+9.2f}{x.explained_pct:>+7.0f}%")
    say("  " + "-" * 90)

    # A pooled read on whether predicted tracks actual at all.
    g = up[["rel", "pred"]].dropna()
    if len(g) > 20:
        b1, b0 = np.polyfit(g.pred, g.rel, 1)
        rr = float(np.corrcoef(g.pred, g.rel)[0, 1] ** 2)
        say(f"  Pooled over {len(g)} sector-months: actual = {b0:+.2f} + "
            f"{b1:+.2f} x predicted, R^2 {rr:.2f}")
        say("  A slope near 1 with a high R^2 means the sector tilt IS the two")
        say("  betas. A slope near 0 means the exposures explain nothing and the")
        say("  sector effect, whatever it is, is something else.")
    say("")
    say("  '% expl' above 100 with a same-sign residual means the exposures")
    say("  overshoot; below 0 means they point the wrong way entirely.")

    # A SECOND, MORE GENEROUS DECOMPOSITION.
    # The trailing 252-day betas can MISMEASURE a sector's true exposure: REIT
    # duration is not constant and a linear daily-frequency slope may understate
    # it at the 63-day horizon. That would leave a large residual for exactly the
    # highest-rate-beta sector and look like a finding when it is mismeasurement.
    # So refit: regress each sector's monthly relative return on the REALISED
    # SPY and TLT moves over all months, with full hindsight. Those exposures are
    # the best any linear two-factor story could possibly have been. Whatever
    # intercept survives in rates-UP months is what is genuinely not exposure.
    say("")
    say("  SAME TEST WITH EXPOSURES FITTED IN HINDSIGHT (generous to the null)")
    say("  rel ~ a + b_s*SPY_fwd + b_t*TLT_fwd over all months, then the mean")
    say("  residual in rates-UP months only. Best case for 'it is just exposure'.")
    say("")
    say(f"  {'sector':<24}{'b_s fit':>9}{'b_t fit':>9}{'R^2':>7}"
        f"{'actual UP':>11}{'resid UP':>10}{'t/1.7':>8}")
    say("  " + "-" * 90)
    hs = []
    for s, sub in m.groupby("sector"):
        z = sub[["rel", "spy_fwd", "tlt_fwd", "regime", "date"]].dropna()
        if len(z) < 40:
            continue
        A = np.column_stack([np.ones(len(z)), z.spy_fwd, z.tlt_fwd])
        coef, *_ = np.linalg.lstsq(A, z.rel.to_numpy(), rcond=None)
        fit = A @ coef
        res = z.rel.to_numpy() - fit
        ss = 1 - res.var() / z.rel.var() if z.rel.var() > 0 else np.nan
        mu = z.regime == "rates UP"
        hs.append({"sector": s, "b_s": coef[1], "b_t": coef[2], "r2": ss,
                   "actual_up": z.loc[mu, "rel"].mean(),
                   "resid_up": res[mu.to_numpy()].mean(),
                   "t_resid_up": t_monthly(pd.Series(res[mu.to_numpy()]))})
    h = pd.DataFrame(hs).sort_values("actual_up", ascending=False)
    for x in h.itertuples():
        say(f"  {x.sector:<24}{x.b_s:>+9.2f}{x.b_t:>+9.2f}{x.r2:>7.2f}"
            f"{x.actual_up:>+10.2f}%{x.resid_up:>+9.2f}%"
            f"{x.t_resid_up / OVERLAP_INFLATION:>+8.2f}")
    say("  " + "-" * 90)
    left = [x.sector for x in h.itertuples()
            if np.isfinite(x.t_resid_up)
            and abs(x.t_resid_up / OVERLAP_INFLATION) > MULTI_TEST_BAR]
    say(f"  Sectors with a rates-UP residual clearing |t| > {MULTI_TEST_BAR:.2f} "
        f"once exposures are")
    say(f"  fitted with hindsight: {', '.join(left) if left else 'none'}")
    r = r.merge(h[["sector", "b_s", "b_t", "r2", "resid_up", "t_resid_up"]],
                on="sector", how="left")
    return r


def beta_neutral_target(d: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """Rule 2. Regress fwd63 on the named exposures WITHIN each month, keep the
    residual. Demeaning removed the market's level; this removes the loading."""
    out = d.copy()

    def resid(gg: pd.DataFrame) -> pd.Series:
        X = gg[cols].to_numpy(dtype=float)
        y = gg["fwd63"].to_numpy(dtype=float)
        ok = np.isfinite(y) & np.isfinite(X).all(axis=1)
        r = pd.Series(np.nan, index=gg.index)
        if ok.sum() < 20:
            return r
        A = np.column_stack([np.ones(ok.sum()), X[ok]])
        coef, *_ = np.linalg.lstsq(A, y[ok], rcond=None)
        r.loc[gg.index[ok]] = y[ok] - A @ coef
        return r

    out["fwd63"] = out.groupby("date", group_keys=False).apply(resid)
    return out.dropna(subset=["fwd63"])


# ----------------------------------------------------------- episode stability
def episodes(sm: pd.DataFrame, f: pd.DataFrame, order: list[str]) -> pd.DataFrame:
    """Sign per sector in each hiking episode. THREE observations, no t-stat."""
    m = sm.merge(f[["date", "regime"]], on="date")
    up = m[m.regime == "rates UP"]
    say("")
    say("=" * 94)
    say("  EPISODE STABILITY -- rates-UP months inside each distinct episode")
    say("=" * 94)
    say("  THREE EPISODES IS THREE OBSERVATIONS. No t-statistic is reported")
    say("  here, because 72 overlapping monthly windows drawn from three")
    say("  macro regimes are not 72 independent trials of a sector rule.")
    say("")
    # A rates-UP month is any month TLT fell. That is NOT the same thing as a
    # month inside a Fed hiking episode, and an FOMC hike view is the latter.
    in_ep = pd.Series(False, index=up.index)
    for _, a, b in EPISODES:
        in_ep |= (up.date >= pd.Timestamp(a)) & (up.date <= pd.Timestamp(b))

    head = "".join(f"{n.split()[0]:>13}" for n, _, _ in EPISODES)
    say(f"  {'sector':<24}{head}{'all 3 eps':>12}{'outside':>11}{'agree':>8}")
    say("  " + "-" * 90)
    rows = []
    for s in order:
        sub = up[up.sector == s]
        msk = in_ep.reindex(sub.index).fillna(False)
        vals, ns = [], []
        for _, a, b in EPISODES:
            w = sub[(sub.date >= pd.Timestamp(a)) & (sub.date <= pd.Timestamp(b))]
            vals.append(w.rel.mean() if len(w) else np.nan)
            ns.append(len(w))
        pooled = sub.loc[msk, "rel"].mean()
        outside = sub.loc[~msk, "rel"].mean()
        fin = [v for v in vals if np.isfinite(v)]
        agree = (len(fin) > 0
                 and (all(v > 0 for v in fin) or all(v < 0 for v in fin)))
        cells = "".join(f"{v:>+12.2f}%" if np.isfinite(v) else f"{'n/a':>13}"
                        for v in vals)
        say(f"  {s:<24}{cells}{pooled:>+11.2f}%{outside:>+10.2f}%"
            f"{('YES' if agree else 'no'):>8}")
        rows.append({"sector": s, "e1": vals[0], "e2": vals[1], "e3": vals[2],
                     "n1": ns[0], "n2": ns[1], "n3": ns[2],
                     "pooled_ep": pooled, "outside_ep": outside, "agree": agree})
    r = pd.DataFrame(rows)
    say("  " + "-" * 90)
    say("  months per episode: " + ", ".join(
        f"{n.split()[0]} {int(r[f'n{i + 1}'].max())}"
        for i, (n, _, _) in enumerate(EPISODES)))
    n_in = up.loc[in_ep, "date"].nunique()
    say(f"  {n_in} of {up.date.nunique()} rates-UP months sit inside a named "
        f"hiking episode.")
    say("  TLT falls for many reasons that are not the Fed, so the 'all 3 eps'")
    say("  column is the one an FOMC hike view would actually have been trading;")
    say("  'outside' is the rest of the rates-UP label.")
    say(f"  {int(r.agree.sum())} of {len(r)} sectors keep one sign across all "
        f"three episodes.")
    say("  Eleven coins flipped three times each: about 2.75 of 11 agree by")
    say("  chance alone, so anything near that number is noise.")
    return r


# -------------------------------------------------------------- sealed holdout
def sealed(sm: pd.DataFrame, f: pd.DataFrame) -> pd.DataFrame:
    """Rank sectors on the search sample, judge the ranking once on the holdout."""
    m = sm.merge(f[["date", "regime"]], on="date")
    up = m[m.regime == "rates UP"]
    tr = up[up.date <= SEARCH_END]
    ho = up[up.date >= HOLDOUT_START]
    drop = up[(up.date > SEARCH_END) & (up.date < HOLDOUT_START)]

    say("")
    say("=" * 94)
    say("  SEALED SPLIT -- rank on the search sample, judge once on the holdout")
    say("=" * 94)
    say(f"  search  {tr.date.nunique():>3} rates-UP months  "
        f"{tr.date.min():%Y-%m}..{tr.date.max():%Y-%m}")
    say(f"  embargo {drop.date.nunique():>3} rates-UP months dropped "
        f"(fwd63 overlaps the holdout)")
    say(f"  holdout {ho.date.nunique():>3} rates-UP months  "
        f"{ho.date.min():%Y-%m}..{ho.date.max():%Y-%m}")
    a = tr.groupby("sector").rel.mean().rename("search")
    b = ho.groupby("sector").rel.mean().rename("holdout")
    nb = ho.groupby("sector").rel.apply(t_monthly).rename("t_ho")
    r = pd.concat([a, b, nb], axis=1).sort_values("search", ascending=False)
    r["rank_search"] = r.search.rank(ascending=False)
    r["rank_holdout"] = r.holdout.rank(ascending=False)
    say("")
    say(f"  {'sector':<24}{'search':>11}{'rank':>6}{'holdout':>11}{'rank':>6}"
        f"{'t/1.7 ho':>10}{'sign':>7}")
    say("  " + "-" * 90)
    for x in r.itertuples():
        same = np.sign(x.search) == np.sign(x.holdout)
        say(f"  {x.Index:<24}{x.search:>+10.2f}%{int(x.rank_search):>6}"
            f"{x.holdout:>+10.2f}%{int(x.rank_holdout):>6}"
            f"{x.t_ho / OVERLAP_INFLATION:>+10.2f}"
            f"{('same' if same else 'FLIP'):>7}")
    say("  " + "-" * 90)
    rho = r.rank_search.corr(r.rank_holdout, method="spearman")
    agree = int((np.sign(r.search) == np.sign(r.holdout)).sum())
    say(f"  rank correlation search vs holdout: {rho:+.2f} over {len(r)} sectors")
    say(f"  {agree} of {len(r)} sectors keep their sign out of sample "
        f"(5.5 expected by chance)")
    top = r.index[0]
    say(f"  The sector the search sample would have picked is {top} at "
        f"{r.search.iloc[0]:+.2f}%; out of sample it did "
        f"{r.holdout.iloc[0]:+.2f}%.")
    return r


# ---------------------------------------- is it a rate view or a standing loading?
def loadings_check(sm: pd.DataFrame, f: pd.DataFrame,
                   raw: pd.DataFrame) -> pd.DataFrame:
    """Three diagnostics the headline table demands before it can be believed.

    1. SYMMETRY. If a sector's rates-UP figure is the mirror image of its
       rates-DOWN figure, there is no regime-specific behaviour to discover: the
       sector has a standing loading and the regime label is just telling you the
       sign of the factor return that quarter. The unconditional figure is what a
       long-only account without a forecast actually earns, and for a pure
       two-sided exposure that is zero.

    2. IS THE RANKING THE RATE-BETA ORDERING? If ranking sectors by their
       rates-UP return reproduces ranking them by minus their rate beta, the
       out-of-sample rank persistence is a statement about sector betas being
       stable, which is true, known, and not a forecast.

    3. ONE-EPISODE CONCENTRATION. The rates-UP figure recomputed with the
       2022-2023 months removed. A sector whose whole number comes from one
       episode has one observation, not 72.
    """
    m = sm.merge(f[["date", "regime"]], on="date")
    up = m[m.regime == "rates UP"]
    _, e3a, e3b = EPISODES[-1]
    ex = up[~((up.date >= pd.Timestamp(e3a)) & (up.date <= pd.Timestamp(e3b)))]

    say("")
    say("=" * 94)
    say("  IS THIS A RATE VIEW, OR THE SECTORS' STANDING LOADINGS?")
    say("=" * 94)
    say(f"  {'sector':<24}{'rates UP':>10}{'rates DOWN':>12}"
        f"{'uncondition':>13}{'half-spread':>13}{'UP ex-2022':>12}")
    say("  " + "-" * 90)
    rows = []
    for x in raw.itertuples():
        half = (x.up - x.dn) / 2
        uncond = getattr(x, "all")
        e = ex.loc[ex.sector == x.sector, "rel"].mean()
        rows.append({"sector": x.sector, "up": x.up, "dn": x.dn,
                     "uncond": uncond, "half": half, "up_ex2022": e})
        say(f"  {x.sector:<24}{x.up:>+9.2f}%{x.dn:>+11.2f}%"
            f"{uncond:>+12.2f}%{half:>+12.2f}%{e:>+11.2f}%")
    r = pd.DataFrame(rows)
    say("  " + "-" * 90)

    rho_mirror = r.up.corr(r.dn, method="spearman")
    ratio = (r.uncond.abs().mean() / r.half.abs().mean()
             if r.half.abs().mean() > 0 else np.nan)
    say(f"  1. SYMMETRY  rank corr(rates-UP, rates-DOWN) = {rho_mirror:+.2f}. "
        f"Near -1 means the")
    say(f"     table is one exposure read twice. Mean |unconditional| is "
        f"{ratio:.2f}x the mean")
    say("     |half-spread|, and the unconditional column is all a long-only")
    say("     account without a rate forecast ever gets to keep.")

    lo = sm.groupby("sector")[["b_rate", "b_mkt"]].mean()
    j = r.set_index("sector").join(lo)
    rho_rate = j.up.corr(-j.b_rate, method="spearman")
    rho_mkt = j.up.corr(j.b_mkt, method="spearman")
    say(f"  2. LOADINGS  rank corr(rates-UP figure, MINUS rate beta) = "
        f"{rho_rate:+.2f}")
    say(f"               rank corr(rates-UP figure, market beta)     = "
        f"{rho_mkt:+.2f}")
    say("     Near +1 on either line means the sector ranking restates an")
    say("     exposure that was on the screen before the FOMC ever met.")

    flips = int(((np.sign(j.up) != np.sign(j.up_ex2022))
                 | (j.up_ex2022.abs() < 0.5 * j.up.abs())).sum())
    say(f"  3. EPISODE   {flips} of {len(j)} sectors lose their sign or over half")
    say(f"     their size once the {EPISODES[-1][0]} months are removed "
        f"({ex.date.nunique()} rates-UP")
    say(f"     months left of {up.date.nunique()}).")
    return r


# ------------------------------------------------ what a cash account could do
def compounded(d: pd.DataFrame, C: pd.DataFrame) -> pd.DataFrame:
    """Rule 4. The regime label is lookahead, so the regime-conditional tilt is
    not implementable. The implementable thing is an always-on sector tilt, so
    compound each sector equal-weight month to month and compare with 14.82%.

    Returns come from ratios of two adjusted closes, which is a valid total
    return. No level is used.
    """
    dates = sorted(d.date.unique())
    ho_dates = [pd.Timestamp(x) for x in dates if pd.Timestamp(x) >= HOLDOUT_START]
    if len(ho_dates) < 4:
        say("  too few holdout dates to compound")
        return pd.DataFrame()
    members = {(pd.Timestamp(dt), s): grp.symbol.tolist()
               for (dt, s), grp in d.groupby(["date", "sector"])}
    univ = {pd.Timestamp(dt): grp.symbol.tolist()
            for dt, grp in d.groupby("date")}

    sectors = sorted(d.sector.unique())
    curves = {s: 1.0 for s in sectors}
    curves["EW universe"] = 1.0
    curves[MKT] = 1.0
    for t0, t1 in zip(ho_dates[:-1], ho_dates[1:]):
        if t0 not in C.index or t1 not in C.index:
            continue
        p0, p1 = C.loc[t0], C.loc[t1]
        for s in sectors:
            syms = [x for x in members.get((t0, s), []) if x in C.columns]
            if len(syms) < MIN_NAMES:
                continue
            r = (p1[syms] / p0[syms] - 1).dropna()
            if len(r):
                curves[s] *= 1 + r.mean()
        syms = [x for x in univ.get(t0, []) if x in C.columns]
        r = (p1[syms] / p0[syms] - 1).dropna()
        if len(r):
            curves["EW universe"] *= 1 + r.mean()
        curves[MKT] *= p1[MKT] / p0[MKT]

    years = (ho_dates[-1] - ho_dates[0]).days / 365.25
    r = pd.DataFrame({"total": pd.Series(curves) - 1})
    r["cagr"] = (r.total + 1) ** (1 / years) - 1
    r = r.sort_values("cagr", ascending=False)
    say("")
    say("=" * 94)
    say("  WHAT A LONG-ONLY CASH ACCOUNT COULD ACTUALLY HOLD")
    say("=" * 94)
    say(f"  Always-on equal-weight sector, rebalanced at each of the "
        f"{len(ho_dates)} holdout decision dates,")
    say(f"  {ho_dates[0]:%Y-%m-%d}..{ho_dates[-1]:%Y-%m-%d} ({years:.2f} years). "
        f"No regime switching: the regime label is")
    say("  lookahead and cannot be traded. Compare to the house bar.")
    say("")
    say(f"  {'holding':<24}{'total':>12}{'CAGR':>10}{'vs 14.82% EW':>16}")
    say("  " + "-" * 90)
    for x in r.itertuples():
        say(f"  {x.Index:<24}{x.total * 100:>+11.1f}%{x.cagr * 100:>+9.2f}%"
            f"{x.cagr * 100 - EW_UNIVERSE_CAGR:>+15.2f}%")
    say("  " + "-" * 90)
    say(f"  Bar: SPY {SPY_CAGR:.2f}% and equal-weight universe "
        f"{EW_UNIVERSE_CAGR:.2f}% CAGR over 2013-01..2026-06.")
    say("  The holdout window is shorter than that, so the EW universe and SPY")
    say("  rows above are the like-for-like comparison and the 14.82% figure is")
    say("  the standing bar the whole project is held to.")
    return r


def main() -> None:
    say("LOADING")
    d, C = load_panel()
    syms = sorted(set(d.symbol) & set(C.columns))
    say(f"  {len(syms)} symbols present in px_close")

    b_m, b_r = two_factor_betas(C, syms)
    bm = b_m.stack().rename("b_mkt").reset_index()
    bm.columns = ["date", "symbol", "b_mkt"]
    br = b_r.stack().rename("b_rate").reset_index()
    br.columns = ["date", "symbol", "b_rate"]
    d = (d.merge(bm, on=["date", "symbol"], how="left")
         .merge(br, on=["date", "symbol"], how="left"))
    n_before = len(d)
    d = d.dropna(subset=["b_mkt", "b_rate", "fwd63"])
    say(f"  joint {BETA_WINDOW}d betas on {MKT} and {RATE}: "
        f"{len(d):,} of {n_before:,} rows usable")

    f = forward_factor_moves(C, np.array(sorted(d.date.unique())))
    d = d[d.date.isin(f.date)]
    n_up = int((f.regime == "rates UP").sum())
    say(f"  {len(f)} months classified by the NEXT {FWD_DAYS} days of {RATE}: "
        f"{n_up} rates UP, {len(f) - n_up} rates DOWN")
    say(f"  mean {RATE} move: "
        f"{f.loc[f.regime == 'rates UP', 'tlt_fwd'].mean():+.2f}% when UP, "
        f"{f.loc[f.regime == 'rates DOWN', 'tlt_fwd'].mean():+.2f}% when DOWN")
    say(f"  mean {MKT} move: "
        f"{f.loc[f.regime == 'rates UP', 'spy_fwd'].mean():+.2f}% when rates UP, "
        f"{f.loc[f.regime == 'rates DOWN', 'spy_fwd'].mean():+.2f}% when DOWN")

    sm = sector_months(d)
    raw = regime_table(
        sm, f, "1. SECTOR RELATIVE FORWARD 63-DAY RETURN BY RATE REGIME (raw)")

    dec = decompose(sm, f)

    # Rule 2, literally: neutralise on beta252, then on both exposures.
    say("")
    say("#" * 94)
    say("  RULE 2 CHECK -- the same table on BETA-NEUTRALISED targets")
    say("#" * 94)
    say("  Demeaning within a month removed the market's level, not the sector's")
    say("  loading on it. These rebuild the table on the residual of a")
    say("  cross-sectional regression inside each month.")
    d1 = beta_neutral_target(d, ["beta252"])
    regime_table(sector_months(d1), f,
                 "2a. NEUTRALISED ON beta252 (the house market beta)")
    d2 = beta_neutral_target(d, ["beta252", "b_rate"])
    bn = regime_table(sector_months(d2), f,
                      "2b. NEUTRALISED ON beta252 AND the joint rate beta")

    episodes(sm, f, list(raw.sector))
    lc = loadings_check(sm, f, raw)
    sl = sealed(sm, f)
    compounded(d, C)

    say("")
    say("=" * 94)
    say("  SUMMARY OF THE FOUR BARS THIS ANGLE HAD TO CLEAR")
    say("=" * 94)
    top = raw.iloc[0]
    say(f"  1. SIZE        best rates-UP sector {top.sector} "
        f"{top.up:+.2f}% over {int(top.n_up)} months, "
        f"t/1.7 {top.t_up / OVERLAP_INFLATION:+.2f} vs bar {MULTI_TEST_BAR:.2f}")
    dt = dec[dec.sector == top.sector]
    if len(dt):
        say(f"  2a. RESIDUAL   of that, {dt.pred.iloc[0]:+.2f}% is exposure x "
            f"realised factor move, residual {dt.resid.iloc[0]:+.2f}% "
            f"({dt.explained_pct.iloc[0]:+.0f}% explained)")
        say(f"  2b. RESIDUAL   with exposures fitted in hindsight the residual "
            f"is {dt.resid_up.iloc[0]:+.2f}%,")
        say(f"      t/1.7 {dt.t_resid_up.iloc[0] / OVERLAP_INFLATION:+.2f}. "
            f"Largest residual across all {N_SECTORS} sectors: "
            f"{dec.resid_up.abs().max():.2f}%")
    bt = bn[bn.sector == top.sector]
    if len(bt):
        say(f"  3. BETA-NEUTRAL same sector on the two-beta-neutral target: "
            f"{bt.up.iloc[0]:+.2f}%, t/1.7 "
            f"{bt.t_up.iloc[0] / OVERLAP_INFLATION:+.2f}")
    if top.sector in sl.index:
        say(f"  4. OUT OF SAMPLE search {sl.loc[top.sector, 'search']:+.2f}% -> "
            f"holdout {sl.loc[top.sector, 'holdout']:+.2f}%")
    lt = lc[lc.sector == top.sector]
    if len(lt):
        say(f"  5. FORECAST-FREE its unconditional relative return over all "
            f"{int(top.n_up + top.n_dn)} months is")
        say(f"     {lt.uncond.iloc[0]:+.2f}%, and ex-{EPISODES[-1][0]} its "
            f"rates-UP figure is {lt.up_ex2022.iloc[0]:+.2f}%")
    say("")
    say("  And the one that decides whether any of it is tradeable: the regime")
    say("  label is the ANSWER KEY. A forecast right 60% of the time keeps")
    say("  about a fifth of a two-sided spread, because the 40% of wrong calls")
    say("  pay it in reverse. Read every rates-UP number above as a ceiling.")


if __name__ == "__main__":
    main()
