"""Is the momentum edge just compensation for extra volatility?

    python research/sheet/risk_test.py

THE QUESTION
If a top-10 momentum basket is simply a higher-beta version of the index,
then its extra return is not skill, it is leverage -- and you could get the
same thing by holding the index and taking more of it. The test:

  1. Build the actual month-by-month equity curve of the momentum rule.
  2. Build the same curve for an equal-weight RANDOM basket from the same
     point-in-time universe, and for SPY itself.
  3. Compare annualised return, volatility, Sharpe, worst drawdown.
  4. Regress the momentum basket's returns on SPY: if alpha is ~0 and beta
     is ~1.4, the strategy IS just a levered index and the answer is yes.

The decisive number is ALPHA, not return. A strategy that returns more than
the index at proportionally more risk has no alpha and is not worth the
turnover, the tracking error, or the effort.
"""
from __future__ import annotations

import io
import importlib.util
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
_s = importlib.util.spec_from_file_location("op", os.path.join(HERE, "optimize.py"))
op = importlib.util.module_from_spec(_s)
_s.loader.exec_module(op)

WINNER = {"signal": "mom126", "top_n": 10, "trend_filter": None,
          "vol_screen": None, "regime": "spy_up", "weight": "equal"}
RF = 0.02        # flat risk-free assumption for Sharpe; stated, not hidden


def curve(P, cfg, dates, close, elig, rng, random_basket=False):
    """Monthly-rebalanced equity curve, holding to the NEXT rebalance date."""
    C = P["close"]
    rets, held = [], []
    for a, b in zip(dates, dates[1:]):
        el = elig.get(a)
        if not el:
            continue
        if not random_basket and cfg["regime"] == "spy_up" \
                and not bool(P["spy_up"].get(a, True)):
            rets.append((b, 0.0))               # sat out: flat, in cash
            held.append(0)
            continue
        if random_basket:
            picks = list(pd.Index(el)[rng.integers(0, len(el), cfg["top_n"])])
        else:
            w = op.select(P, cfg, a, el)
            if w is None or w.empty:
                rets.append((b, 0.0)); held.append(0); continue
            picks = list(w.index)
        seg = C.loc[a:b, picks]
        if seg.empty:
            continue
        r = (seg.iloc[-1] / seg.iloc[0] - 1).dropna()
        if r.empty:
            continue
        # honour the weights select() computed; taking r.mean() silently
        # equal-weighted everything and made cfg["weight"] a no-op
        if random_basket:
            per = float(r.mean())
        else:
            ww = w.reindex(r.index).dropna()
            per = float((r[ww.index] * (ww / ww.sum())).sum()) if len(ww) \
                else float(r.mean())
        rets.append((b, per))
        held.append(len(r))
    s = pd.Series(dict(rets)).sort_index()
    return s, float(np.mean(held)) if held else 0.0


def stats(r: pd.Series, per_year: float = 12.0) -> dict:
    if r.empty:
        return {}
    total = float((1 + r).prod())
    yrs = len(r) / per_year
    cagr = total ** (1 / yrs) - 1 if yrs > 0 else np.nan
    vol = float(r.std(ddof=1) * np.sqrt(per_year))
    eq = (1 + r).cumprod()
    dd = float((eq / eq.cummax() - 1).min())
    return {"cagr": cagr * 100, "vol": vol * 100,
            "sharpe": (cagr - RF) / vol if vol else np.nan,
            "maxdd": dd * 100, "worst_mo": float(r.min()) * 100,
            "best_mo": float(r.max()) * 100, "months": len(r)}


def main() -> None:
    P, fwd, dates, elig = op.prep()
    close = P["close"]
    rng = np.random.default_rng(21)
    dates = sorted(dates)
    say(f"{len(dates)} rebalance dates {dates[0]:%Y-%m} .. {dates[-1]:%Y-%m}\n")

    mom, avg_held = curve(P, WINNER, dates, close, elig, rng)
    say(f"momentum basket: {avg_held:.1f} names held on average")

    # 200 independent random baskets, averaged -- one draw would be noise
    rnd_curves = []
    for k in range(200):
        r, _ = curve(P, WINNER, dates, close, elig,
                     np.random.default_rng(1000 + k), random_basket=True)
        rnd_curves.append(r)
    rnd = pd.concat(rnd_curves, axis=1).mean(axis=1)

    # SPY over the same dates
    spy = op.load()[0]["SPY"]
    sp = pd.Series({b: float(spy.loc[a:b].iloc[-1] / spy.loc[a:b].iloc[0] - 1)
                    for a, b in zip(dates, dates[1:])
                    if not spy.loc[a:b].empty}).sort_index()

    idx = mom.index.intersection(rnd.index).intersection(sp.index)
    mom, rnd, sp = mom.loc[idx], rnd.loc[idx], sp.loc[idx]

    say(f"\n{'':<22}{'CAGR':>8}{'vol':>8}{'Sharpe':>8}{'maxDD':>9}"
        f"{'worst mo':>10}{'best mo':>9}")
    say("-" * 74)
    for name, s in (("MOMENTUM top-10", mom), ("random basket (avg)", rnd),
                    ("SPY buy & hold", sp)):
        st = stats(s)
        say(f"{name:<22}{st['cagr']:>7.2f}%{st['vol']:>7.2f}%{st['sharpe']:>8.2f}"
            f"{st['maxdd']:>8.1f}%{st['worst_mo']:>9.1f}%{st['best_mo']:>8.1f}%")
    say("-" * 74)

    # the decisive regression: momentum on SPY
    X = np.column_stack([np.ones(len(sp)), sp.to_numpy()])
    coef, *_ = np.linalg.lstsq(X, mom.to_numpy(), rcond=None)
    resid = mom.to_numpy() - X @ coef
    ss = float(((mom - mom.mean()) ** 2).sum())
    r2 = 1 - float((resid ** 2).sum()) / ss if ss else np.nan
    # SE of an INTERCEPT is s * sqrt((X'X)^-1[0,0]), not s/sqrt(n) -- the
    # latter drops the leverage term and understates the standard error
    s2 = float((resid ** 2).sum()) / (len(sp) - 2)
    se = float(np.sqrt(s2 * np.linalg.inv(X.T @ X)[0, 0]))
    alpha_m, beta = float(coef[0]), float(coef[1])
    # the winner was CHOSEN on train, so a pooled alpha is measured partly on
    # its own selection sample; report both
    cut = pd.Timestamp(op.TRAIN_END)
    for lab, msk in (("TRAIN", sp.index <= cut), ("HOLDOUT", sp.index > cut)):
        if msk.sum() > 10:
            Xs = np.column_stack([np.ones(int(msk.sum())), sp[msk].to_numpy()])
            cs, *_ = np.linalg.lstsq(Xs, mom[msk].to_numpy(), rcond=None)
            rs = mom[msk].to_numpy() - Xs @ cs
            ss2 = float((rs ** 2).sum()) / (int(msk.sum()) - 2)
            ses = float(np.sqrt(ss2 * np.linalg.inv(Xs.T @ Xs)[0, 0]))
            say(f"  {lab:<8} n={int(msk.sum()):<4} beta {cs[1]:.2f}"
                f"  alpha {cs[0]*12*100:+.2f}%/yr  t={cs[0]/ses:.2f}")
    say(f"\nREGRESSION  momentum = alpha + beta x SPY   ({len(sp)} months, POOLED)")
    say(f"  beta        {beta:.2f}")
    say(f"  alpha       {alpha_m*100:+.2f}% per month  = {alpha_m*12*100:+.2f}%/yr"
        f"   t = {alpha_m/se:.2f}")
    say(f"  R2          {r2:.3f}")
    say("")
    lev = beta
    say(f"THE FAIR COMPARISON: {lev:.2f}x SPY has the same market exposure.")
    lev_ret = stats(sp * lev)
    say(f"  {lev:.2f}x SPY   CAGR {lev_ret['cagr']:.2f}%  vol {lev_ret['vol']:.2f}%"
        f"  maxDD {lev_ret['maxdd']:.1f}%")
    mst = stats(mom)
    say(f"  MOMENTUM     CAGR {mst['cagr']:.2f}%  vol {mst['vol']:.2f}%"
        f"  maxDD {mst['maxdd']:.1f}%")
    diff = mst["cagr"] - lev_ret["cagr"]
    say("")
    say(f"VERDICT: momentum beats its own risk-matched index by "
        f"{diff:+.2f}%/yr.")
    if abs(alpha_m / se) < 2:
        say("  Alpha is NOT statistically distinguishable from zero (|t| < 2).")
        say("  On this evidence the strategy IS essentially a higher-beta S&P,")
        say("  and holding a volatile index is the simpler way to own that.")
    else:
        say(f"  Alpha survives at t = {alpha_m/se:.2f}: the extra return is NOT")
        say("  fully explained by taking more market risk.")
    say("")
    say(f"Note: a cash account cannot lever, so '{lev:.2f}x SPY' is not actually")
    say("available to this account. The realistic alternatives are SPY itself,")
    say("or the momentum basket, or a blend -- not a levered index.")


if __name__ == "__main__":
    main()
