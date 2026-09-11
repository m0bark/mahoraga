"""Every screener filter, measured. Then a decision tree, held to a sealed split.

    python research/sheet/tree_screen.py               # the whole thing
    python research/sheet/tree_screen.py --sweep-only  # just the filter table
    python research/sheet/tree_screen.py --shuffles 50 # heavier null

WHAT THIS DOES
Two separate jobs, in this order, because the second one is only believable
after the first:

  1. A SINGLE-FILTER SWEEP. Every feature, one at a time, cut into deciles
     within each month. Top decile minus bottom decile forward return. This is
     the honest version of reading down a screener's filter list and asking
     which of those boxes has ever been worth ticking.

  2. A DECISION TREE, fitted on data ending 2021-12-31 and judged ONCE on
     2022 onward. The tree is allowed to find interactions a single filter
     cannot. It is also the single easiest way to fool yourself that exists in
     this domain, which is what most of this file is about.

WHY THE TARGET IS DEMEANED WITHIN EACH MONTH
Raw forward return is mostly the market. In a month when everything rose 8%,
a tree can "predict" returns by learning the date, and a screener cannot buy a
date. So the target is each name's forward 63-day return MINUS the universe
mean that month. That is the only part a stock screener could ever capture:
which names beat the others, not whether the market went up.

THE FOUR THINGS THAT STOP THIS BEING CURVE-FITTING

  SEALED HOLDOUT. Train is everything up to 2021-12-31. Holdout is 2022
  onward, and the tree never sees it during fitting or depth selection.

  AN EMBARGO AT THE BOUNDARY. The target looks 63 trading days ahead, and the
  decision dates are monthly, so the last three training months' labels are
  partly drawn from the holdout period. Those months are DROPPED. Without this
  the split leaks and the holdout flatters itself.

  GROUPED CROSS-VALIDATION. Depth is chosen by cross-validation that splits on
  DATE, never on row. Two rows from the same month are not independent
  observations; they share a market. Random k-fold over rows would put the
  same month on both sides of the fold and quietly inflate every score.

  A SHUFFLED CONTROL. The whole pipeline is re-run on a target shuffled within
  each month. That destroys any real relationship while preserving the shape of
  the data, the number of features, the depth search and the decile maths. The
  shuffled runs say what this procedure scores on pure noise. A real result has
  to beat that distribution, not zero. If a tree scores +4% on the real target
  and the shuffled runs average +3.5%, the tree found nothing and +4% was the
  house edge of the method.

WHAT A GOOD RESULT WOULD LOOK LIKE, stated before looking
A holdout top-minus-bottom decile spread that is positive, outside the
shuffled distribution, and produced by a tree whose splits are readable as
screener rules. Anything that only works in the training period, or that sits
inside the shuffled range, is reported as a failure in the same words it would
have been reported as a success.
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
from sklearn.tree import DecisionTreeRegressor, export_text
from sklearn.ensemble import GradientBoostingRegressor

HERE = os.path.dirname(os.path.abspath(__file__))
LONG = os.path.join(HERE, "cache_long")

# ---------------------------------------------------------------------------
# THE CONTAMINATION BLOCKLIST. Read this before adding anything to it.
#
# cache_long/px_close.csv and px_volume.csv are split- AND dividend-ADJUSTED,
# and there is no split/dividend table beside them to undo that. The adjustment
# factor on any past date is a function of corporate actions that happened
# AFTER that date, so any feature quoted in adjusted LEVELS is a partial
# readout of the future. Measured, not assumed:
#
#     NVDA market cap on 2013-04-30 computes to $195 million. It was about
#     $12 billion. The 61x gap is the 2021 and 2024 splits.
#     AAPL computes to $12.6 billion against about $420 billion.
#     T computes to $66 billion against about $190 billion, dividends only.
#
# The error is largest for exactly the names that rose the most, because that
# is what causes splits. So an adjusted price level, or any multiple built on
# market cap, quietly encodes "this one went up later". That is not a value
# factor, it is lookahead, and on the first pass it produced a beautiful
# holdout result for low P/E that had to be thrown away.
#
# What is IMMUNE and therefore still allowed:
#   * any RETURN or any RATIO OF TWO PRICES -- the factor cancels exactly
#     (dist_sma200, rsi14, pos_52w, perf_6m, dd_52w, vol, beta, atr_pct ...)
#   * any feature built ONLY from SEC filings, where no price appears at all
#     (roa, margins, current_ratio, growth rates, the F-Score legs ...)
# dollar_vol_60 cancels the SPLIT factor but not the cumulative DIVIDEND
# factor, so it is partially contaminated and is blocked too.
# The valuation multiples are NOT on this list any more. feat_val.py built them
# on the adjusted close and was condemned; feat_val2.py rebuilt them on
# unadjusted closes from px_raw_close.csv and verified market cap against six
# known 2013 values, four of which land within 2.4%. So the multiples loaded
# below come from val2 and are allowed. What stays blocked is the three
# adjusted-price LEVEL features out of the technical block, which cannot be
# repaired from the data available.
CONTAMINATED = {"price", "avg_volume_20", "dollar_vol_60"}

# Which valuation file to use. val2 is the corrected one; val is kept on disk
# only so the old-versus-new comparison in val_decile_check.py still runs.
VAL_BLOCK = "val2"

TRAIN_END = pd.Timestamp("2021-12-31")
EMBARGO_MONTHS = 3          # 63 trading days of forward return, monthly dates
N_DECILES = 10
DEPTHS = (1, 2, 3, 4, 5)
N_SHUFFLES = 20
CV_FOLDS = 5
MIN_LEAF_FRAC = 0.02        # no leaf smaller than 2% of the training rows
TOP_FRAC = 0.10             # the traded slice


# --------------------------------------------------------------------- data
def load() -> tuple[pd.DataFrame, list]:
    g = pd.read_csv(os.path.join(LONG, "grid.csv"), parse_dates=["date"])
    blocks = []
    for name in ("tech", VAL_BLOCK, "qual", "growth"):
        p = os.path.join(LONG, f"feat_{name}.csv")
        if not os.path.exists(p):
            say(f"  MISSING feat_{name}.csv -- that block is absent from the model")
            continue
        b = pd.read_csv(p, parse_dates=["date"])
        cols = [c for c in b.columns if c not in ("date", "symbol", "fwd63")]
        say(f"  feat_{name:<8} {len(b):>7,} rows  {len(cols):>3} features")
        blocks.append(b[["date", "symbol"] + cols])
    if not blocks:
        raise SystemExit("no feature blocks found; run the builders first")
    d = g
    for b in blocks:
        d = d.merge(b, on=["date", "symbol"], how="left")
    allf = [c for c in d.columns if c not in ("date", "symbol", "fwd63")]
    feats = [c for c in allf if c not in CONTAMINATED]
    blocked = [c for c in allf if c in CONTAMINATED]
    if blocked:
        say(f"\n  BLOCKED as adjusted-price contaminated ({len(blocked)}): "
            f"{', '.join(blocked)}")
        say("  These are excluded from every table below. See CONTAMINATED in")
        say("  this file for the measurement that condemned them.")

    # cross-sectional demeaning, the step that keeps this about SELECTION
    d["y"] = d["fwd63"] - d.groupby("date")["fwd63"].transform("mean")
    d = d.dropna(subset=["y"])
    say(f"\n  {len(d):,} rows | {len(feats)} features | "
        f"{d.date.nunique()} months")
    cov = d[feats].notna().mean().sort_values()
    thin = cov[cov < 0.30]
    if len(thin):
        say(f"  {len(thin)} features under 30% coverage: "
            f"{', '.join(thin.index[:8])}{' ...' if len(thin) > 8 else ''}")
    return d, feats


def split(d: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Train, holdout, with the overlapping months at the boundary removed."""
    cut = TRAIN_END - pd.DateOffset(months=EMBARGO_MONTHS)
    tr = d[d.date <= cut].copy()
    ho = d[d.date > TRAIN_END].copy()
    dropped = d[(d.date > cut) & (d.date <= TRAIN_END)]
    say(f"\n  train  {len(tr):>7,} rows  {tr.date.min():%Y-%m} .. "
        f"{tr.date.max():%Y-%m}")
    say(f"  embargo{len(dropped):>7,} rows dropped at the boundary "
        f"({EMBARGO_MONTHS} months of overlapping labels)")
    say(f"  holdout{len(ho):>7,} rows  {ho.date.min():%Y-%m} .. "
        f"{ho.date.max():%Y-%m}")
    return tr, ho


# ------------------------------------------------------------ filter sweep
def decile_spread(df: pd.DataFrame, col: str, y: str = "y") -> tuple:
    """Top minus bottom decile of one feature, cut within each month."""
    s = df[[col, y, "date"]].dropna()
    if s[col].nunique() < N_DECILES or len(s) < 500:
        return np.nan, np.nan, 0, []
    s = s.copy()
    s["dec"] = (s.groupby("date")[col]
                .transform(lambda x: pd.qcut(x.rank(method="first"), N_DECILES,
                                             labels=False, duplicates="drop")
                           if x.notna().sum() >= N_DECILES else np.nan))
    s = s.dropna(subset=["dec"])
    if s.empty:
        return np.nan, np.nan, 0, []
    means = s.groupby("dec")[y].mean()
    if 0 not in means or N_DECILES - 1 not in means:
        return np.nan, np.nan, len(s), []
    hi = s.loc[s.dec == N_DECILES - 1, y]
    lo = s.loc[s.dec == 0, y]
    se = np.sqrt(hi.var(ddof=1) / len(hi) + lo.var(ddof=1) / len(lo))
    t = (hi.mean() - lo.mean()) / se if se > 0 else np.nan
    return hi.mean() - lo.mean(), t, len(s), means.tolist()


def sweep(tr: pd.DataFrame, ho: pd.DataFrame, feats: list) -> pd.DataFrame:
    rows = []
    for c in feats:
        d_tr, t_tr, n_tr, means = decile_spread(tr, c)
        d_ho, t_ho, n_ho, _ = decile_spread(ho, c)
        mono = np.nan
        if means:
            r = pd.Series(means).corr(pd.Series(range(len(means))),
                                      method="spearman")
            mono = r
        rows.append({"feature": c, "train_spread": d_tr, "train_t": t_tr,
                     "holdout_spread": d_ho, "holdout_t": t_ho,
                     "monotonicity": mono, "n": n_tr})
    s = pd.DataFrame(rows)
    bar = float(np.sqrt(2 * np.log(max(len(feats), 2))))
    say("")
    say("=" * 92)
    say(f"  SINGLE-FILTER SWEEP -- {len(feats)} filters, each alone")
    say("=" * 92)
    say(f"  Top decile minus bottom decile, forward 63 days, demeaned within")
    say(f"  month. Testing {len(feats)} filters means the best one will look")
    say(f"  good by luck, so the bar is |t| > sqrt(2*ln({len(feats)})) = "
        f"{bar:.2f}, not 1.96.")
    say("")
    say(f"  {'filter':<22}{'train':>9}{'t':>7}{'holdout':>10}{'t':>7}"
        f"{'mono':>7}  verdict")
    say("  " + "-" * 88)
    s = s.sort_values("holdout_spread", ascending=False, na_position="last")
    for r in s.itertuples():
        if not np.isfinite(r.train_spread):
            continue
        survives = (np.isfinite(r.holdout_t) and abs(r.train_t) > bar
                    and abs(r.holdout_t) > 1.96
                    and np.sign(r.train_spread) == np.sign(r.holdout_spread))
        v = ("SURVIVES both" if survives
             else "train only" if abs(r.train_t) > bar
             else "holdout only" if np.isfinite(r.holdout_t) and abs(r.holdout_t) > bar
             else "nothing")
        say(f"  {r.feature:<22}{r.train_spread:>+8.2f}%{r.train_t:>+7.2f}"
            f"{r.holdout_spread:>+9.2f}%{r.holdout_t:>+7.2f}"
            f"{r.monotonicity:>+7.2f}  {v}")
    n_s = sum(1 for r in s.itertuples()
              if np.isfinite(r.holdout_t) and np.isfinite(r.train_t)
              and abs(r.train_t) > bar and abs(r.holdout_t) > 1.96
              and np.sign(r.train_spread) == np.sign(r.holdout_spread))
    say("  " + "-" * 88)
    say(f"  {n_s} of {len(feats)} filters survive train AND holdout with a "
        f"consistent sign.")
    say("  A filter that works in training and flips sign out of sample is")
    say("  worse than useless: it is a rule you would have traded backwards.")
    return s


# ------------------------------------------------------------------- trees
def fit_predict(tr: pd.DataFrame, te: pd.DataFrame, feats: list,
                depth: int, seed: int = 0) -> np.ndarray:
    X = tr[feats].to_numpy(dtype=float)
    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
    m = DecisionTreeRegressor(
        max_depth=depth, random_state=seed,
        min_samples_leaf=max(int(len(tr) * MIN_LEAF_FRAC), 50))
    m.fit(X, tr["y"].to_numpy(dtype=float))
    Xe = np.nan_to_num(te[feats].to_numpy(dtype=float),
                       nan=0.0, posinf=0.0, neginf=0.0)
    return m.predict(Xe), m


def top_minus_bottom(te: pd.DataFrame, pred: np.ndarray) -> float:
    """The traded quantity: best TOP_FRAC by prediction minus worst TOP_FRAC,
    ranked within each month so it is implementable as a monthly screen."""
    d = te[["date", "y"]].copy()
    d["p"] = pred
    # method="first" rather than the default "average". A shallow tree emits
    # only a handful of distinct predictions, so with average ranks a single
    # huge tie block can straddle the 10% line and leave BOTH slices empty,
    # which returned NaN and silently disabled the depth search and the
    # shuffled control. Breaking ties by position guarantees a real 10% slice.
    d["r"] = d.groupby("date")["p"].rank(method="first", pct=True)
    hi = d.loc[d.r > 1 - TOP_FRAC, "y"]
    lo = d.loc[d.r <= TOP_FRAC, "y"]
    if len(hi) < 2 or len(lo) < 2:
        return np.nan
    return hi.mean() - lo.mean()


def cv_depth(tr: pd.DataFrame, feats: list) -> int:
    """Choose depth by date-grouped CV. Folds are contiguous blocks of months,
    so a fold's training data never contains the month it is scored on."""
    months = np.array(sorted(tr.date.unique()))
    folds = np.array_split(months, CV_FOLDS)
    say("")
    say(f"  {'depth':<8}{'CV top-minus-bottom':>24}")
    best, best_s = DEPTHS[0], -1e9
    for dep in DEPTHS:
        scores = []
        for f in folds:
            te = tr[tr.date.isin(f)]
            trn = tr[~tr.date.isin(f)]
            if len(te) < 200 or len(trn) < 1000:
                continue
            p, _ = fit_predict(trn, te, feats, dep)
            scores.append(top_minus_bottom(te, p))
        sc = float(np.mean(scores)) if scores else np.nan
        say(f"  {dep:<8}{sc:>+23.2f}%")
        if np.isfinite(sc) and sc > best_s:
            best, best_s = dep, sc
    say(f"  chosen depth {best} (CV {best_s:+.2f}%)")
    return best


def shuffled_null(tr: pd.DataFrame, ho: pd.DataFrame, feats: list,
                  depth: int, n: int) -> np.ndarray:
    """Re-run the identical pipeline on a within-month shuffled target."""
    out = []
    rng = np.random.default_rng(12345)
    for i in range(n):
        t2 = tr.copy()
        t2["y"] = (t2.groupby("date")["y"]
                   .transform(lambda s: rng.permutation(s.to_numpy())))
        p, _ = fit_predict(t2, ho, feats, depth, seed=i)
        out.append(top_minus_bottom(ho, p))
    return np.array(out)


def trees(tr: pd.DataFrame, ho: pd.DataFrame, feats: list, n_shuf: int) -> None:
    say("")
    say("=" * 92)
    say("  DECISION TREE -- fitted on train only, judged once on holdout")
    say("=" * 92)
    depth = cv_depth(tr, feats)

    p_tr, model = fit_predict(tr, tr, feats, depth)
    p_ho, _ = fit_predict(tr, ho, feats, depth)
    s_tr = top_minus_bottom(tr, p_tr)
    s_ho = top_minus_bottom(ho, p_ho)

    say("")
    say(f"  in-sample  top {TOP_FRAC:.0%} minus bottom {TOP_FRAC:.0%}: "
        f"{s_tr:+.2f}%")
    say(f"  HOLDOUT    top {TOP_FRAC:.0%} minus bottom {TOP_FRAC:.0%}: "
        f"{s_ho:+.2f}%")
    say(f"  decay      {s_ho - s_tr:+.2f}%  "
        f"({'held up' if s_ho > 0.6 * s_tr else 'mostly evaporated'})")

    say("")
    say(f"  SHUFFLED CONTROL, {n_shuf} runs of the same pipeline on noise")
    null = shuffled_null(tr, ho, feats, depth, n_shuf)
    say(f"    mean {null.mean():+.2f}%   sd {null.std(ddof=1):.2f}%   "
        f"best of {n_shuf}: {null.max():+.2f}%")
    z = (s_ho - null.mean()) / null.std(ddof=1) if null.std(ddof=1) > 0 else np.nan
    beat = (null < s_ho).mean() * 100
    say(f"    the real tree is {z:+.2f} sd above the noise mean and beats "
        f"{beat:.0f}% of shuffled runs")
    if not (np.isfinite(z) and z > 2 and beat >= 95):
        say("    VERDICT: INSIDE THE NOISE. This procedure scores about this")
        say("    much on a target with every relationship destroyed, so the")
        say("    real score is the method's house edge, not an edge in the data.")
    else:
        say("    VERDICT: outside the noise. Worth writing down as a rule.")

    say("")
    say("  THE RULE THE TREE FOUND (read it as screener filters)")
    say("  " + "-" * 88)
    txt = export_text(model, feature_names=list(feats), decimals=2,
                      max_depth=depth)
    for line in txt.splitlines()[:60]:
        say("    " + line)

    imp = pd.Series(model.feature_importances_, index=feats)
    imp = imp[imp > 0].sort_values(ascending=False)
    if len(imp):
        say("")
        say("  WHICH FILTERS THE TREE ACTUALLY USED")
        for k, v in imp.head(12).items():
            say(f"    {k:<24}{v * 100:>6.1f}%")

    # an upper bound: if a strong learner cannot do it either, nothing here can
    say("")
    say("  UPPER BOUND -- gradient boosting, same split, same target")
    X = np.nan_to_num(tr[feats].to_numpy(dtype=float), nan=0.0,
                      posinf=0.0, neginf=0.0)
    gb = GradientBoostingRegressor(n_estimators=200, max_depth=3,
                                   learning_rate=0.05, subsample=0.8,
                                   random_state=0)
    gb.fit(X, tr["y"].to_numpy(dtype=float))
    Xh = np.nan_to_num(ho[feats].to_numpy(dtype=float), nan=0.0,
                       posinf=0.0, neginf=0.0)
    s_gb = top_minus_bottom(ho, gb.predict(Xh))
    say(f"    holdout top-minus-bottom: {s_gb:+.2f}%")
    say("    A strong learner on the same features is the ceiling of what any")
    say("    combination of these filters can extract. If this is flat, no")
    say("    amount of filter-tweaking in the screener will help.")


# ------------------------------------------------- is it an edge, or is it beta?
def risk_or_edge(d: pd.DataFrame, tr: pd.DataFrame, ho: pd.DataFrame,
                 feats: list, s: pd.DataFrame) -> pd.DataFrame:
    """The check without which the sweep above is worthless.

    Demeaning within a month removes the market's MEAN return. It does not
    remove BETA. If the market rose 8% that month, a beta-2 name rose about
    16%, which scores +8% against the mean without anybody having predicted
    anything. Over 2013-2026 the market mostly rose, so ANY measure of
    volatility will top a sweep like this one, look beautifully monotonic, and
    be nothing but leverage.

    Two tests settle it:

      1. DOES THE SPREAD FOLLOW THE MARKET? Compute the feature's decile spread
         month by month and correlate it with that month's market return. A
         real stock-selection edge is roughly indifferent to market direction.
         Leverage in disguise earns in up months and gives it back in down
         months, so a high positive correlation and a sign flip between up and
         down months is the signature.

      2. NEUTRALISE BETA AND RE-RUN. Within each month, regress the forward
         return on beta and keep the RESIDUAL. That residual is what is left
         after paying for market exposure. A filter that still predicts the
         residual is selecting stocks. A filter that does not was selling you
         beta and calling it alpha.
    """
    say("")
    say("=" * 92)
    say("  IS IT AN EDGE, OR IS IT BETA?")
    say("=" * 92)
    if "beta252" not in d.columns:
        say("  beta252 absent; cannot run this check, so treat the sweep above")
        say("  as unverified rather than as a result.")
        return s

    mkt = d.groupby("date")["fwd63"].mean()
    up = mkt[mkt > 0].index
    dn = mkt[mkt <= 0].index
    say(f"  {len(up)} months the universe rose, {len(dn)} it fell "
        f"(mean {mkt.mean():+.2f}%)")
    say("")
    say(f"  {'filter':<18}{'up months':>12}{'down months':>14}"
        f"{'corr w/ mkt':>14}  reading")
    say("  " + "-" * 88)

    top = [r.feature for r in
           s.dropna(subset=["holdout_t"])
           .reindex(s.holdout_t.abs().sort_values(ascending=False).index)
           .head(10).itertuples()]
    for c in top:
        per = []
        for dt, g in d.groupby("date"):
            x = g[[c, "y"]].dropna()
            if len(x) < 40 or x[c].nunique() < N_DECILES:
                continue
            q = pd.qcut(x[c].rank(method="first"), N_DECILES, labels=False,
                        duplicates="drop")
            hi = x.loc[q == q.max(), "y"].mean()
            lo = x.loc[q == 0, "y"].mean()
            per.append((dt, hi - lo))
        if len(per) < 20:
            continue
        sp = pd.Series(dict(per))
        a = sp.reindex(up).dropna().mean()
        b = sp.reindex(dn).dropna().mean()
        r = sp.corr(mkt.reindex(sp.index))
        flips = np.sign(a) != np.sign(b)
        reading = ("BETA, not an edge" if flips and abs(r) > 0.4
                   else "partly beta" if abs(r) > 0.4
                   else "survives direction")
        say(f"  {c:<18}{a:>+11.2f}%{b:>+13.2f}%{r:>+14.2f}  {reading}")

    # ---- test 2: neutralise beta, re-run the whole sweep on the residual
    say("")
    say("  BETA-NEUTRALISED SWEEP -- forward return with market exposure")
    say("  regressed out within each month. What predicts what is LEFT?")
    say("")
    d2 = d.dropna(subset=["beta252"]).copy()

    def resid(g: pd.DataFrame) -> pd.Series:
        x = g["beta252"].to_numpy(dtype=float)
        yy = g["y"].to_numpy(dtype=float)
        m = np.isfinite(x) & np.isfinite(yy)
        out = pd.Series(np.nan, index=g.index)
        if m.sum() < 20:
            return out
        b1, b0 = np.polyfit(x[m], yy[m], 1)
        out.loc[g.index[m]] = yy[m] - (b0 + b1 * x[m])
        return out

    d2["y"] = d2.groupby("date", group_keys=False).apply(resid)
    d2 = d2.dropna(subset=["y"])
    cut = TRAIN_END - pd.DateOffset(months=EMBARGO_MONTHS)
    tr2, ho2 = d2[d2.date <= cut], d2[d2.date > TRAIN_END]
    bar = float(np.sqrt(2 * np.log(max(len(feats), 2))))
    rows = []
    for c in feats:
        a, t_a, _, means = decile_spread(tr2, c)
        b, t_b, _, _ = decile_spread(ho2, c)
        mono = (pd.Series(means).corr(pd.Series(range(len(means))),
                                      method="spearman") if means else np.nan)
        rows.append({"feature": c, "train_spread": a, "train_t": t_a,
                     "holdout_spread": b, "holdout_t": t_b,
                     "monotonicity": mono})
    n = pd.DataFrame(rows).dropna(subset=["train_spread"])
    n = n.reindex(n.holdout_spread.abs().sort_values(ascending=False).index)
    say(f"  {'filter':<22}{'train':>9}{'t':>7}{'holdout':>10}{'t':>7}"
        f"{'mono':>7}  verdict")
    say("  " + "-" * 88)
    kept = 0
    for r in n.head(18).itertuples():
        ok = (np.isfinite(r.holdout_t) and abs(r.train_t) > bar
              and abs(r.holdout_t) > 1.96
              and np.sign(r.train_spread) == np.sign(r.holdout_spread))
        if ok:
            kept += 1
        say(f"  {r.feature:<22}{r.train_spread:>+8.2f}%{r.train_t:>+7.2f}"
            f"{r.holdout_spread:>+9.2f}%{r.holdout_t:>+7.2f}"
            f"{r.monotonicity:>+7.2f}  "
            f"{'SURVIVES' if ok else 'no'}")
    say("  " + "-" * 88)
    say(f"  {kept} filters survive once beta is paid for.")
    say("  This is the number that matters. Anything that vanished here was")
    say("  charging you a bull market and calling itself a screen.")
    n.to_csv(os.path.join(LONG, "filter_sweep_beta_neutral.csv"), index=False)
    return d2


def main() -> None:
    say("LOADING")
    d, feats = load()
    tr, ho = split(d)
    s = sweep(tr, ho, feats)
    s.to_csv(os.path.join(LONG, "filter_sweep.csv"), index=False)
    d2 = risk_or_edge(d, tr, ho, feats, s)
    if "--sweep-only" in sys.argv:
        return
    n = (int(sys.argv[sys.argv.index("--shuffles") + 1])
         if "--shuffles" in sys.argv else N_SHUFFLES)

    say("")
    say("#" * 92)
    say("  TREE 1 of 2 -- raw target. Expect it to rediscover beta.")
    say("#" * 92)
    trees(tr, ho, feats, n)

    if d2 is not None and len(d2):
        say("")
        say("#" * 92)
        say("  TREE 2 of 2 -- BETA-NEUTRAL target. This is the real test.")
        say("  The tree may use beta as a FEATURE, but it can no longer be paid")
        say("  for holding it, so anything it finds has to be selection.")
        say("#" * 92)
        tr2, ho2 = split(d2)
        trees(tr2, ho2, feats, n)


if __name__ == "__main__":
    main()
