"""Grid search over momentum variants, with a sealed holdout.

    python research/sheet/optimize.py --search     # TRAIN only, prints a ranking
    python research/sheet/optimize.py --holdout    # scores the finalists ONCE

WHY THIS IS STRUCTURED AS TWO COMMANDS

A grid search over ~200 variants will always produce a winner. With 200 draws
the best pure-noise variant sits about sqrt(2*ln(200)) = 3.3 standard errors
above zero, so "the best config scored +6%" is the expected result even when
nothing works. The only defence is a period the search never touched.

    TRAIN    2010-01 .. 2021-12   search freely, look as often as you like
    HOLDOUT  2022-01 .. today     scored ONCE, at the end, for <= 5 finalists

If a variant's HOLDOUT edge collapses toward zero, the TRAIN number was
selection, not signal. That gap IS the finding, and it is printed.

WHY THE RANDOM-BASKET CONTROL IS NOT ENOUGH  (found by audit, 2026-09-09)

The earlier claim here -- "both legs draw from the same biased list, so the
bias cancels" -- is FALSE for momentum, and this was the single biggest error
in the whole project.

Write r_s = mu_s + b_s + e_s, where b_s is the uplift a name gets purely from
being in TODAY's index. The control removes the AVERAGE uplift b_pool. What
survives is (b_picks - b_pool), which vanishes only if b is uncorrelated with
the strategy's weights. For momentum it is strongly correlated, because S&P
INDEX ADDITION IS ITSELF A MOMENTUM RULE: companies are promoted after they
have grown into large-cap status, i.e. after strong trailing returns. Momentum
ranks on the same variable, so it systematically overweights exactly the names
whose presence in the file is conditioned on having risen.

Measured on the contaminated universe: names first listed after 2015 supplied
55.5% of the holdout edge. APP alone was 12.6% (first price 2021, added to the
index in 2025 after a ~30x run). The edge grew monotonically toward the date
the constituent list was pulled -- 2011-15 +2.2%, rising to 2024-26 +21.2%,
trend +1.42%/yr with t=6.67 -- and the entire trend sat in the long leg while
the short leg was flat. That is the signature of addition-conditioning, not of
a strengthening signal.

THE FIX APPLIED HERE: universe by LAGGED LIQUIDITY, not index membership.
A name is eligible on date d only if it was already in the top LIQ_TOP by
60-day dollar volume as of d minus LIQ_LAG_Y years. Selection then cannot see
anything about what the name became. This does not recover companies DELETED
from the index (they are absent from the price file entirely), but that
omission biases the measured edge DOWNWARD -- deletions are past losers, they
would have sat in the pool, been passed over by momentum, and dragged the
control mean down -- so it is conservative.

Residual honesty: cross-era edge comparisons remain only partly interpretable,
because cross-sectional dispersion itself roughly doubled over the sample.
"""
from __future__ import annotations

import io
import itertools
import json
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
FINALISTS = os.path.join(HERE, "finalists.json")

TRAIN_END = "2021-12-31"
LIQ_TOP = 350          # universe = top N by dollar volume ...
LIQ_LAG_Y = 3          # ... as measured this many years EARLIER
N_RANDOM = 300
N_BOOT = 2000
_CTRL_CACHE: dict = {}


def load():
    c = pd.read_csv(os.path.join(LONG, "px_close.csv"), index_col=0,
                    parse_dates=True).sort_index()
    v = pd.read_csv(os.path.join(LONG, "px_volume.csv"), index_col=0,
                    parse_dates=True).sort_index()
    u = pd.read_csv(os.path.join(HERE, "sp500.csv"))
    syms = [s for s in u.symbol if s in c.columns]
    return c, v, syms, u.set_index("symbol")["sector"].to_dict()


def month_ends(idx):
    s = pd.Series(idx, index=idx)
    return s.groupby([idx.year, idx.month]).last().tolist()


def panels(close, vol, syms):
    """Precompute everything the grid needs, once. Vectorised over the panel."""
    C = close[syms]
    R = C.pct_change()
    P = {}
    for lb in (21, 63, 126, 189, 252):
        P[f"mom{lb}"] = C / C.shift(lb) - 1
    # skip-a-month variants: momentum measured to one month ago
    for lb in (126, 252):
        P[f"mom{lb}_s21"] = C.shift(21) / C.shift(lb) - 1
    P["sma200"] = C.rolling(200).mean()
    P["sma50"] = C.rolling(50).mean()
    P["vol60"] = R.rolling(60).std() * np.sqrt(252)
    P["vol126"] = R.rolling(126).std() * np.sqrt(252)
    P["dollar_vol"] = (C * vol[syms]).rolling(60).mean()
    P["close"] = C
    # market regime: is SPY itself above its own 200-day average
    if "SPY" in close:
        spy = close["SPY"]
        P["spy_up"] = (spy > spy.rolling(200).mean())
    return P


VARIANTS = {
    "signal": ["mom63", "mom126", "mom189", "mom252", "mom126_s21", "mom252_s21",
               "blend"],
    "top_n": [10, 20, 30, 50],
    "trend_filter": [None, "above200", "above50"],
    "vol_screen": [None, "low_half", "low_third"],
    "regime": [None, "spy_up"],
    "weight": ["equal", "invvol"],
}


def combos():
    keys = list(VARIANTS)
    for vals in itertools.product(*[VARIANTS[k] for k in keys]):
        yield dict(zip(keys, vals))


def rank_signal(P, cfg, d):
    if cfg["signal"] == "blend":
        parts = [P[k].loc[d].rank(pct=True) for k in ("mom63", "mom126", "mom252")]
        return sum(parts) / len(parts)
    return P[cfg["signal"]].loc[d].rank(pct=True)


def select(P, cfg, d, eligible):
    s = rank_signal(P, cfg, d)[eligible]
    m = s.notna()
    if cfg["trend_filter"] == "above200":
        m &= (P["close"].loc[d, eligible] > P["sma200"].loc[d, eligible])
    elif cfg["trend_filter"] == "above50":
        m &= (P["close"].loc[d, eligible] > P["sma50"].loc[d, eligible])
    if cfg["vol_screen"]:
        v = P["vol126"].loc[d, eligible]
        q = 0.5 if cfg["vol_screen"] == "low_half" else 1 / 3
        m &= v <= v.quantile(q)
    s = s[m]
    if len(s) < cfg["top_n"]:
        return None
    picks = s.nlargest(cfg["top_n"]).index
    if cfg["weight"] == "invvol":
        w = 1 / P["vol126"].loc[d, picks].replace(0, np.nan)
        w = w / w.sum()
    else:
        w = pd.Series(1 / len(picks), index=picks)
    return w.dropna()


def run(P, cfg, dates, fwd, eligible_by_date, rng, hold=63):
    rows = []
    for d in dates:
        el = eligible_by_date.get(d)
        if el is None or len(el) < 80:
            continue
        if cfg["regime"] == "spy_up" and not bool(P["spy_up"].get(d, True)):
            continue                       # sit out when the market is below trend
        w = select(P, cfg, d, el)
        if w is None or w.empty:
            continue
        r = fwd.loc[d, w.index]
        if r.isna().mean() > 0.3:
            continue
        w2 = w[r.notna()]
        if w2.empty:
            continue
        sel = float((r[w2.index] * (w2 / w2.sum())).sum())
        pool = fwd.loc[d, el].dropna().to_numpy()
        if len(pool) < 60:
            continue
        n = len(w2)
        # the random-basket mean depends only on (date, basket size), so it is
        # identical across every variant that picks n names on date d. Caching
        # it turns 1,008 x 140 draws into ~140 x (a handful of sizes).
        ck = (d, n)
        if ck not in _CTRL_CACHE:
            _CTRL_CACHE[ck] = float(
                pool[rng.integers(0, len(pool), (N_RANDOM, n))].mean(axis=1).mean())
        ctrl = _CTRL_CACHE[ck]
        rows.append((d, sel, ctrl))
    if len(rows) < 24:
        return None
    df = pd.DataFrame(rows, columns=["date", "sel", "ctrl"])
    df["edge"] = df["sel"] - df["ctrl"]
    return df


def summarize(df, rng, boot: bool = True):
    """Vectorised date-block bootstrap.

    The first version called df["edge"].sample() N_BOOT times per variant.
    Across 1,008 variants that is ~2 million pandas calls and the search never
    finished. One numpy fancy-index does the same job: draw the whole
    (N_BOOT x n_dates) index matrix at once and take row means.

    boot=False skips the p-value entirely -- during the grid search only the
    EDGE is needed to rank, so p is computed once, later, for the finalists.
    """
    e = df["edge"].to_numpy()
    out = {"dates": len(df), "sel": df["sel"].mean() * 100,
           "ctrl": df["ctrl"].mean() * 100, "edge": float(e.mean()) * 100,
           "win": float((e > 0).mean() * 100), "worst": float(e.min()) * 100}
    if boot and len(e) > 2:
        draws = e[rng.integers(0, len(e), (N_BOOT, len(e)))].mean(axis=1)
        out["p"] = min(float((np.sign(draws) != np.sign(e.mean())).mean() * 2), 1.0)
    else:
        out["p"] = float("nan")
    return out


def prep(hold=63):
    close, vol, syms, _ = load()
    say(f"{len(syms)} names | {len(close)} days | "
        f"{close.index[0]:%Y-%m-%d} .. {close.index[-1]:%Y-%m-%d}")
    P = panels(close, vol, syms)
    C = P["close"]
    fwd = C.shift(-hold) / C - 1
    dates = [d for d in month_ends(close.index) if d in C.index]
    dates = [d for d in dates if C.index.get_loc(d) > 260
             and C.index.get_loc(d) + hold < len(C)]
    # ELIGIBILITY IS THE LOAD-BEARING PART OF THIS FILE.
    #
    # A $5m-dollar-volume screen read AT date d still admits a name that was
    # tiny then and is only in sp500.csv because of what it later became
    # (PLTR was pickable from 2023-05, well before its index addition). So
    # eligibility is judged on liquidity as of d MINUS LIQ_LAG_Y YEARS: the
    # name had to already be a large, liquid company back then, independent
    # of anything it did afterwards.
    dv = P["dollar_vol"]
    # POINT-IN-TIME INDEX MEMBERSHIP. sp500.csv now carries date_added for all
    # 503 members (100% coverage). 47% of today's index joined after 2010, and
    # a name added in 2025 after a 30x run must not be pickable in 2015 --
    # that was the largest single bias the audit found. Deletions are still
    # missing and cannot be recovered, but that omission pushes the measured
    # edge DOWN (deleted names are past losers momentum would have skipped),
    # so what survives is conservative.
    _u = pd.read_csv(os.path.join(HERE, "sp500.csv"))
    added = (dict(zip(_u["symbol"], pd.to_datetime(_u["date_added"], errors="coerce")))
             if "date_added" in _u else {})
    say(f"point-in-time membership: {sum(pd.notna(v) for v in added.values())} "
        f"addition dates loaded")
    elig = {}
    for d in dates:
        past = d - pd.DateOffset(years=LIQ_LAG_Y)
        prior = dv.loc[:past]
        if prior.empty:
            continue
        rank_then = prior.iloc[-1].rank(ascending=False)
        # cache_long carries a few all-NaN rows (US market holidays written as
        # empty). notna().all() over a window containing one of them returns
        # False for EVERY name and silently deletes the date.
        hist = C.loc[:d].tail(252)
        hist = hist[hist.notna().any(axis=1)]
        ok = hist.notna().all()
        cand = [s for s in syms
                if ok.get(s, False) and rank_then.get(s, np.inf) <= LIQ_TOP
                and (s not in added or pd.isna(added[s]) or added[s] <= d)]
        if len(cand) >= 80:
            elig[d] = cand
    dates = [d for d in dates if d in elig]
    say(f"universe: IN THE INDEX on the date, and top {LIQ_TOP} by dollar "
        f"volume {LIQ_LAG_Y}y earlier; "
        f"median {int(np.median([len(v) for v in elig.values()]))} eligible names")
    return P, fwd, dates, elig


def search():
    P, fwd, dates, elig = prep()
    tr = [d for d in dates if d <= pd.Timestamp(TRAIN_END)]
    ho = [d for d in dates if d > pd.Timestamp(TRAIN_END)]
    say(f"TRAIN {len(tr)} rebalance dates ({tr[0]:%Y-%m} .. {tr[-1]:%Y-%m})")
    say(f"HOLDOUT {len(ho)} dates ({ho[0]:%Y-%m} .. {ho[-1]:%Y-%m}) -- SEALED\n")
    rng = np.random.default_rng(17)
    all_cfg = list(combos())
    say(f"searching {len(all_cfg)} variants on TRAIN only ...")
    res = []
    for i, cfg in enumerate(all_cfg, 1):
        df = run(P, cfg, tr, fwd, elig, rng)
        if df is None:
            continue
        s = summarize(df, rng, boot=False)      # p only for finalists
        res.append({**cfg, **s, "_df": df})
        if i % 100 == 0:
            say(f"  {i}/{len(all_cfg)}")
    r = pd.DataFrame([{k: v for k, v in x.items() if k != "_df"} for x in res])
    keep = {id(x): x["_df"] for x in res}
    r["_id"] = [id(x) for x in res]
    r = r.sort_values("edge", ascending=False)
    for j in r.head(15).index:                  # bootstrap the printed rows only
        r.loc[j, "p"] = summarize(keep[r.loc[j, "_id"]], rng, boot=True)["p"]
    r = r.drop(columns=["_id"])
    r.to_csv(os.path.join(HERE, "optimize_train.csv"), index=False)
    say(f"\n{len(r)} variants scored. TOP 15 ON TRAIN:")
    say(f"{'signal':<12}{'n':>4}{'trend':<10}{'vol':<11}{'regime':<9}{'wt':<8}"
        f"{'edge':>8}{'win':>6}{'p':>7}")
    say("-" * 76)
    for _, x in r.head(15).iterrows():
        say(f"{x['signal']:<12}{int(x['top_n']):>4}{str(x['trend_filter']):<10}"
            f"{str(x['vol_screen']):<11}{str(x['regime']):<9}{x['weight']:<8}"
            f"{x['edge']:>7.2f}%{x['win']:>5.0f}%{x['p']:>7.3f}")
    # finalists: best of each SIGNAL family, so we do not send five clones
    fin = (r.sort_values("edge", ascending=False)
             .groupby("signal", as_index=False).head(1)
             .sort_values("edge", ascending=False).head(5))
    keys = list(VARIANTS)
    json.dump([{k: (None if pd.isna(x[k]) else x[k]) for k in keys}
               for _, x in fin.iterrows()], open(FINALISTS, "w"), indent=1)
    say(f"\nexpected best-of-{len(r)} edge under pure noise: "
        f"{np.sqrt(2*np.log(max(len(r),2))):.2f} standard errors above zero.")
    say(f"wrote {len(fin)} finalists to finalists.json -- now run --holdout")


def holdout():
    if not os.path.exists(FINALISTS):
        say("no finalists.json -- run --search first")
        return
    fin = json.load(open(FINALISTS))
    P, fwd, dates, elig = prep()
    tr = [d for d in dates if d <= pd.Timestamp(TRAIN_END)]
    ho = [d for d in dates if d > pd.Timestamp(TRAIN_END)]
    rng = np.random.default_rng(99)
    say(f"scoring {len(fin)} finalists on {len(ho)} SEALED holdout dates "
        f"({ho[0]:%Y-%m} .. {ho[-1]:%Y-%m})\n")
    say(f"{'signal':<12}{'n':>4}{'trend':<10}{'vol':<11}{'regime':<9}{'wt':<8}"
        f"{'TRAIN':>8}{'HOLD':>8}{'gap':>8}{'win':>6}{'p':>7}")
    say("-" * 92)
    for cfg in fin:
        a = run(P, cfg, tr, fwd, elig, rng)
        b = run(P, cfg, ho, fwd, elig, rng)
        if a is None or b is None:
            say(f"{cfg['signal']:<12} insufficient data")
            continue
        sa, sb = summarize(a, rng), summarize(b, rng)
        say(f"{cfg['signal']:<12}{cfg['top_n']:>4}{str(cfg['trend_filter']):<10}"
            f"{str(cfg['vol_screen']):<11}{str(cfg['regime']):<9}{cfg['weight']:<8}"
            f"{sa['edge']:>7.2f}%{sb['edge']:>7.2f}%"
            f"{sb['edge']-sa['edge']:>7.2f}%{sb['win']:>5.0f}%{sb['p']:>7.3f}")
    say("")
    say("gap = HOLDOUT minus TRAIN. A large negative gap means the TRAIN number")
    say("was selection across the grid, not signal. HOLDOUT is now spent --")
    say("scoring another variant on it makes it a second training set.")


if __name__ == "__main__":
    a = sys.argv[1:]
    if "--holdout" in a:
        holdout()
    else:
        search()
