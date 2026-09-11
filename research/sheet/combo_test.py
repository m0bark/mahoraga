"""Do weak signals become strong when COMBINED with context?

    python research/sheet/combo_test.py --search    # TRAIN only
    python research/sheet/combo_test.py --holdout   # finalists, scored once

THE HYPOTHESIS BEING TESTED
Support, resistance and fair-value gaps do not work alone -- measured earlier:
buying within 2% of support lost 0.99% to a random basket over 3 months. The
claim is that they work CONDITIONALLY: a quality company that reaches support
while the market regime is calm should bounce, even though "at support" on its
own means nothing.

That is a real, testable claim about INTERACTION, and it is tested here by
crossing every pair and triple of conditions and scoring each against random
baskets from the same point-in-time universe.

WHAT CANNOT BE TESTED, AND THE HONEST SUBSTITUTE
"Great fundamentals" cannot be backtested: yfinance gives only TODAY'S P/E,
ROE and margins, so scoring 2015 with 2026 accounts is look-ahead and would
fabricate the answer. Instead three PRICE-DERIVED quality proxies are used and
labelled as proxies:
    q_lowvol     bottom-third of trailing 6-month volatility
    q_uptrend    200-day average rising over the last 3 months
    q_stable     shallower than median 1-year drawdown
These correlate with quality; they are not quality. Any result here is about
the proxy, and that limitation is printed with the output.

FAIR VALUE GAP
A three-bar imbalance: bar i-2's HIGH is below bar i's LOW (bullish gap) and
no later bar has traded back through it. The untouched zone between them is
the gap. "Price returned to an unfilled bullish FVG" is fvg_retest below.

MULTIPLICITY
Every pair and triple of ~14 conditions is thousands of tests, and the best of
N noise draws grows as sqrt(2 ln N). So TRAIN is searched freely, a handful of
finalists are frozen, and HOLDOUT is scored once.
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
import importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
_s = importlib.util.spec_from_file_location("op", os.path.join(HERE, "optimize.py"))
op = importlib.util.module_from_spec(_s)
_s.loader.exec_module(op)

HOLD = 63
TRAIN_END = "2021-12-31"
N_RANDOM = 300
N_BOOT = 2000
MIN_PICKS = 5
MIN_DATES = 24
FIN = os.path.join(HERE, "combo_finalists.json")


def fair_value_gaps(high: np.ndarray, low: np.ndarray, close: np.ndarray,
                    lookback: int = 126) -> tuple[bool, float]:
    """Is price sitting in an UNFILLED bullish 3-bar imbalance?

    Bullish gap at bar i: high[i-2] < low[i]. The gap is (high[i-2], low[i]).
    It is 'filled' once any later bar's low trades back below high[i-2].
    Returns (price is inside an unfilled gap, distance to its top in %).
    """
    n = len(close)
    start = max(2, n - lookback)
    spot = close[-1]
    best = None
    for i in range(start, n):
        lo_edge, hi_edge = high[i - 2], low[i]
        if not (np.isfinite(lo_edge) and np.isfinite(hi_edge)) or lo_edge >= hi_edge:
            continue
        later = low[i + 1:]
        if len(later) and np.nanmin(later) < lo_edge:
            continue                                   # gap already filled
        if lo_edge <= spot <= hi_edge:
            d = (hi_edge / spot - 1) * 100
            if best is None or abs(d) < abs(best):
                best = d
    return (best is not None), (best if best is not None else np.nan)


def build(P, close, high, low, syms, dates, elig):
    """One row per (date, symbol) with every CONDITION evaluated as of d."""
    C, H, L = P["close"], high[syms], low[syms]
    vix = close["^VIX"] if "^VIX" in close else None
    spy = close["SPY"]
    fomc = set(pd.DatetimeIndex(
        [l.strip() for l in open(os.path.join(HERE, "fomc_dates.txt"))
         if l.strip()]).date) if os.path.exists(
        os.path.join(HERE, "fomc_dates.txt")) else set()
    rows = []
    for d in dates:
        el = elig.get(d)
        if not el:
            continue
        i = C.index.get_loc(d)
        win = slice(max(0, i - 378), i + 1)
        sub = C.iloc[win]
        spot = sub.iloc[-1]
        sma200 = sub.tail(200).mean()
        sma200_3mo = sub.iloc[-63:].rolling(200).mean() if len(sub) > 263 else None
        vol126 = sub.pct_change().tail(126).std() * np.sqrt(252)
        dd = spot / sub.tail(252).max() - 1
        mom126 = spot / sub.iloc[-127] - 1 if len(sub) > 127 else pd.Series(np.nan)
        # market context, identical for every name on this date
        v = float(vix.loc[:d].iloc[-1]) if vix is not None else np.nan
        v_med = float(vix.loc[:d].tail(252).median()) if vix is not None else np.nan
        spy_up = bool(spy.loc[:d].iloc[-1] > spy.loc[:d].tail(200).mean())
        days_to_fomc = min([abs((pd.Timestamp(f) - d).days) for f in fomc],
                           default=999) if fomc else 999
        for s in el:
            if s not in sub or not np.isfinite(spot.get(s, np.nan)):
                continue
            p = float(spot[s])
            hh = H[s].iloc[win].to_numpy()
            ll = L[s].iloc[win].to_numpy()
            cc = sub[s].to_numpy()
            ok = np.isfinite(ll) & np.isfinite(hh)
            if ok.sum() < 80:
                continue
            sup = None
            lows = []
            k = 5
            lo_ok = ll[ok]
            for j in range(k, len(lo_ok) - k):
                w = lo_ok[j - k:j + k + 1]
                if lo_ok[j] == w.min() and (w == lo_ok[j]).sum() == 1:
                    lows.append((j, float(lo_ok[j])))
            cl = op.__dict__.get("cluster")
            import importlib.util as _iu
            _c = _iu.spec_from_file_location("cp", os.path.join(HERE, "compute.py"))
            # cluster lives in compute.py; import once lazily
            if not hasattr(build, "_cp"):
                m = _iu.module_from_spec(_c)
                _c.loader.exec_module(m)
                build._cp = m
            cands = [c for c in build._cp.cluster(lows, len(lo_ok))
                     if c["price"] < p * 0.995]
            if cands:
                strong = [c for c in cands if c["touches"] >= 2]
                sup = max((strong or cands), key=lambda c: c["price"])["price"]
            in_fvg, fvg_d = fair_value_gaps(hh[ok], ll[ok], cc[ok])
            rows.append({
                "date": d, "symbol": s, "price": p,
                "pct_to_support": (sup / p - 1) * 100 if sup else np.nan,
                "in_fvg": in_fvg, "fvg_dist": fvg_d,
                "above200": p > float(sma200.get(s, np.nan)),
                "vol126": float(vol126.get(s, np.nan)),
                "drawdown": float(dd.get(s, np.nan)),
                "mom126": float(mom126.get(s, np.nan)) if hasattr(mom126, "get") else np.nan,
                "vix": v, "vix_med": v_med, "spy_up": spy_up,
                "days_to_fomc": days_to_fomc,
            })
    df = pd.DataFrame(rows)
    # cross-sectional, per date
    for c in ("vol126", "drawdown", "mom126"):
        df[f"r_{c}"] = df.groupby("date")[c].rank(pct=True)
    return df


CONDS = {
    "at_support": lambda d: d["pct_to_support"] > -3,
    "in_fvg": lambda d: d["in_fvg"],
    "q_lowvol": lambda d: d["r_vol126"] <= 0.33,
    "q_uptrend": lambda d: d["above200"],
    "q_stable": lambda d: d["r_drawdown"] >= 0.5,
    "mom_top30": lambda d: d["r_mom126"] >= 0.70,
    "mom_bot30": lambda d: d["r_mom126"] <= 0.30,
    "calm_vix": lambda d: d["vix"] <= d["vix_med"],
    "scared_vix": lambda d: d["vix"] > d["vix_med"],
    "market_up": lambda d: d["spy_up"],
    "market_down": lambda d: ~d["spy_up"],
    "near_fomc": lambda d: d["days_to_fomc"] <= 5,
    "far_fomc": lambda d: d["days_to_fomc"] > 5,
}
EXCLUSIVE = [("calm_vix", "scared_vix"), ("market_up", "market_down"),
             ("near_fomc", "far_fomc"), ("mom_top30", "mom_bot30")]


def score(df, mask, fwd_col, rng):
    per = []
    for d, g in df.groupby("date"):
        r = g[fwd_col]
        ok = r.notna()
        if ok.sum() < 60:
            continue
        m = mask.loc[g.index] & ok
        if m.sum() < MIN_PICKS:
            continue
        pool = r[ok].to_numpy()
        n = int(m.sum())
        ctrl = float(pool[rng.integers(0, len(pool), (N_RANDOM, min(n, 40)))]
                     .mean(axis=1).mean())
        per.append((d, float(r[m].mean()), ctrl, n))
    if len(per) < MIN_DATES:
        return None
    x = pd.DataFrame(per, columns=["date", "sel", "ctrl", "n"])
    x["edge"] = x["sel"] - x["ctrl"]
    return x


def summ(x, rng):
    e = x["edge"].to_numpy()
    b = e[rng.integers(0, len(e), (N_BOOT, len(e)))].mean(axis=1)
    return {"dates": len(x), "picks": x["n"].mean(), "edge": e.mean() * 100,
            "win": (e > 0).mean() * 100,
            "p": min(float((np.sign(b) != np.sign(e.mean())).mean() * 2), 1.0)}


def prepare():
    close, vol, syms, _ = op.load()
    high = pd.read_csv(os.path.join(op.LONG, "px_high.csv"), index_col=0,
                       parse_dates=True).sort_index()
    low = pd.read_csv(os.path.join(op.LONG, "px_low.csv"), index_col=0,
                      parse_dates=True).sort_index()
    P, fwd, dates, elig = op.prep(hold=HOLD)
    say("evaluating conditions at every rebalance date (this is the slow part) ...")
    df = build(P, close, high, low, syms, dates, elig)
    f = fwd.stack().rename("fwd").reset_index()
    f.columns = ["date", "symbol", "fwd"]
    df = df.merge(f, on=["date", "symbol"], how="left")
    say(f"{len(df):,} (date, symbol) rows over {df['date'].nunique()} dates")
    return df


def search():
    df = prepare()
    tr = df[df.date <= pd.Timestamp(TRAIN_END)]
    rng = np.random.default_rng(31)
    say(f"TRAIN {tr['date'].nunique()} dates\n")
    names = list(CONDS)
    tests = [(n,) for n in names]
    tests += [c for c in itertools.combinations(names, 2)]
    tests += [c for c in itertools.combinations(names, 3)]
    bad = {frozenset(p) for p in EXCLUSIVE}
    tests = [t for t in tests
             if not any(frozenset(p) <= set(t) for p in bad)]
    say(f"{len(tests)} condition sets (singles, pairs, triples)")
    res = []
    for i, t in enumerate(tests, 1):
        m = pd.Series(True, index=tr.index)
        for n in t:
            m &= CONDS[n](tr).fillna(False)
        x = score(tr, m, "fwd", rng)
        if x is None:
            continue
        res.append({"combo": " + ".join(t), "k": len(t), **summ(x, rng)})
        if i % 100 == 0:
            say(f"  {i}/{len(tests)}")
    r = pd.DataFrame(res).sort_values("edge", ascending=False)
    r.to_csv(os.path.join(HERE, "combo_train.csv"), index=False)
    say(f"\n{len(r)} scored. TOP 18 ON TRAIN:")
    say(f"{'combination':<52}{'dates':>6}{'picks':>7}{'edge':>8}{'win':>6}{'p':>7}")
    say("-" * 86)
    for _, x in r.head(18).iterrows():
        say(f"{x['combo']:<52}{int(x['dates']):>6}{x['picks']:>7.0f}"
            f"{x['edge']:>7.2f}%{x['win']:>5.0f}%{x['p']:>7.3f}")
    say("\nWORST 5 (what to avoid):")
    for _, x in r.tail(5).iterrows():
        say(f"{x['combo']:<52}{int(x['dates']):>6}{x['picks']:>7.0f}"
            f"{x['edge']:>7.2f}%{x['win']:>5.0f}%{x['p']:>7.3f}")
    # does support gain anything from context?
    say("\nDOES SUPPORT IMPROVE WHEN CONDITIONED?")
    base = r[r.combo == "at_support"]
    if len(base):
        say(f"  at_support alone            {base.iloc[0]['edge']:+.2f}%")
    sup = r[r.combo.str.contains("at_support")].sort_values("edge", ascending=False)
    for _, x in sup.head(6).iterrows():
        say(f"  {x['combo']:<40}{x['edge']:+7.2f}%  (n={int(x['picks'])})")
    fv = r[r.combo.str.contains("in_fvg")].sort_values("edge", ascending=False)
    say("\nFAIR VALUE GAP, best conditionings:")
    for _, x in fv.head(5).iterrows():
        say(f"  {x['combo']:<40}{x['edge']:+7.2f}%  (n={int(x['picks'])})")
    fin = r.head(6)["combo"].tolist()
    json.dump(fin, open(FIN, "w"), indent=1)
    say(f"\nexpected best-of-{len(r)} under noise: "
        f"{np.sqrt(2*np.log(max(len(r),2))):.2f} SE above zero")
    say(f"froze {len(fin)} finalists -> combo_finalists.json; run --holdout")


def holdout():
    if not os.path.exists(FIN):
        say("run --search first")
        return
    fin = json.load(open(FIN))
    df = prepare()
    tr = df[df.date <= pd.Timestamp(TRAIN_END)]
    ho = df[df.date > pd.Timestamp(TRAIN_END)]
    rng = np.random.default_rng(77)
    say(f"\nSEALED HOLDOUT: {ho['date'].nunique()} dates\n")
    say(f"{'combination':<52}{'TRAIN':>8}{'HOLD':>8}{'gap':>8}{'win':>6}{'p':>7}")
    say("-" * 89)
    for combo in fin:
        parts = combo.split(" + ")
        ma = pd.Series(True, index=tr.index)
        mb = pd.Series(True, index=ho.index)
        for n in parts:
            ma &= CONDS[n](tr).fillna(False)
            mb &= CONDS[n](ho).fillna(False)
        a, b = score(tr, ma, "fwd", rng), score(ho, mb, "fwd", rng)
        if a is None or b is None:
            say(f"{combo:<52}  insufficient data")
            continue
        sa, sb = summ(a, rng), summ(b, rng)
        say(f"{combo:<52}{sa['edge']:>7.2f}%{sb['edge']:>7.2f}%"
            f"{sb['edge']-sa['edge']:>7.2f}%{sb['win']:>5.0f}%{sb['p']:>7.3f}")
    say("\nQuality here is a PRICE PROXY (low vol / rising 200d / shallow")
    say("drawdown), not real fundamentals -- point-in-time accounting data does")
    say("not exist in this feed. Read every q_* result as 'the proxy', not")
    say("'the balance sheet'.")


if __name__ == "__main__":
    holdout() if "--holdout" in sys.argv[1:] else search()
