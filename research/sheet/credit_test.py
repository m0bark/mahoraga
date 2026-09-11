"""Does credit (HYG/IEF) actually LEAD semiconductors, or just move with them?

    python research/sheet/credit_test.py

THE CLAIM
"The first sign the AI trade is breaking will come from the junk bond market,
not from NVDA. Watch HYG/IEF -- high yield divided by 7-10y treasuries. When
it turns down, financing is tightening and the semiconductor complex is next."

That is a LEAD-LAG claim and it is testable three ways:

 1. CROSS-CORRELATION at explicit lags. If credit leads semis, correlation
    between credit's move at t-k and semis' move at t should PEAK at k > 0.
    If it peaks at k = 0 they are simply the same risk trade in two wrappers,
    and "watch credit for an early warning" gives you no time at all.

 2. FORWARD PREDICTION. Sort history by the credit ratio's recent trend and
    measure what semis did NEXT, at 5 / 21 / 63 trading days.

 3. INCREMENTAL VALUE. Even if credit predicts, the honest question is whether
    it adds anything over signals already on the desk -- VIX level and whether
    SPY is above its own 200-day average. Regressing forward semi returns on
    all three at once answers that. A t-stat near zero on credit means it is
    telling you what VIX already told you.

TERMINOLOGY, because the pitch inverts it
The RATIO HYG/IEF RISING = junk outperforming treasuries = risk appetite ON.
Credit SPREADS WIDENING = stress. Those are opposite directions of the same
fact, and the pitch calls the ratio rising "widening", which reads backwards.
Here, ratio up = risk-on. Always.
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
import yfinance as yf

HERE = os.path.dirname(os.path.abspath(__file__))
START = "2010-01-01"
HORIZONS = [5, 21, 63]


def load():
    u = pd.read_csv(os.path.join(HERE, "sp500.csv"))
    semis = list(u.loc[u.industry.fillna("").str.contains("Semiconduct",
                                                          case=False), "symbol"])
    say(f"semis in the index: {len(semis)}  {', '.join(semis[:12])}"
        + (" ..." if len(semis) > 12 else ""))
    px = pd.read_csv(os.path.join(HERE, "cache_long", "px_close.csv"),
                     index_col=0, parse_dates=True).sort_index()
    have = [s for s in semis if s in px.columns]
    extra = yf.download(["HYG", "IEF", "^VIX", "SPY", "SOXX", "NVDA"],
                        start=START, auto_adjust=True, progress=False,
                        threads=True)["Close"]
    df = pd.concat([px[have], extra], axis=1).dropna(how="all")
    # NVDA is in both the cache and the extra pull; a duplicated label makes
    # df["NVDA"] a DataFrame and every scalar float() on it blows up
    df = df.loc[:, ~df.columns.duplicated()]
    df = df.loc[df.index >= pd.Timestamp(START)]
    return df, have


def main() -> None:
    df, semis = load()
    need = [c for c in ("HYG", "IEF", "SPY", "^VIX") if c in df]
    if len(need) < 4:
        say(f"missing series: {set(['HYG','IEF','SPY','^VIX']) - set(need)}")
        return
    d = df.dropna(subset=["HYG", "IEF", "SPY"])
    credit = (d["HYG"] / d["IEF"]).rename("credit")
    # equal-weight semiconductor basket from the index itself
    sem = d[semis].pct_change().mean(axis=1).rename("semis")
    sem_eq = (1 + sem.fillna(0)).cumprod()
    say(f"\n{len(d)} sessions {d.index[0]:%Y-%m-%d} .. {d.index[-1]:%Y-%m-%d}")
    say(f"credit ratio HYG/IEF today {credit.iloc[-1]:.4f}  "
        f"({(credit.iloc[-1]/credit.iloc[-22]-1)*100:+.2f}% over 21 sessions, "
        f"{(credit.iloc[-1]/credit.iloc[-64]-1)*100:+.2f}% over 63)")
    pc = float(credit.rank(pct=True).iloc[-1] * 100)
    say(f"that ratio sits at the {pc:.0f}th percentile of its own history "
        f"since {START[:4]}")

    # ---------------- 1. cross-correlation at explicit lags
    cr = credit.pct_change()
    sr = sem
    say("\n1. LEAD-LAG  corr(credit move at t-k, semis move at t)")
    say(f"   {'lag k':>8}{'corr':>9}   interpretation")
    say("   " + "-" * 52)
    best, bestk = -9, None
    for k in (-5, -3, -1, 0, 1, 2, 3, 5, 10, 21):
        x = cr.shift(k)
        j = pd.concat([x, sr], axis=1).dropna()
        c = float(j.corr().iloc[0, 1])
        if c > best:
            best, bestk = c, k
        tag = ("credit LEADS semis" if k > 0 else
               "same day" if k == 0 else "semis lead credit")
        say(f"   {k:>8}{c:>9.3f}   {tag}")
    say("   " + "-" * 52)
    say(f"   peak correlation at lag {bestk} ({best:.3f})")
    if bestk == 0:
        say("   => they move TOGETHER. Credit is not an early warning; it is")
        say("      the same risk trade in a different wrapper.")
    elif bestk > 0:
        say(f"   => credit genuinely leads by about {bestk} sessions.")
    else:
        say("   => semis lead CREDIT, which is the opposite of the claim.")

    # ---------------- 2. forward prediction by credit trend
    say("\n2. FORWARD RETURNS OF SEMIS, sorted by the credit ratio's 21d trend")
    trend = credit / credit.shift(21) - 1
    for h in HORIZONS:
        fwd = sem_eq.shift(-h) / sem_eq - 1
        j = pd.concat([trend.rename("t"), fwd.rename("f")], axis=1).dropna()
        q = pd.qcut(j["t"].rank(method="first"), 5,
                    labels=["worst credit", "2", "3", "4", "best credit"])
        g = j.groupby(q)["f"].agg(["mean", "count"])
        say(f"\n   next {h} sessions:")
        for lab, row in g.iterrows():
            say(f"     {str(lab):<14}{row['mean']*100:>7.2f}%   n={int(row['count'])}")
        spread = (g["mean"].iloc[-1] - g["mean"].iloc[0]) * 100
        say(f"     best minus worst: {spread:+.2f}%")

    # ---------------- 3. does it add anything over VIX and SPY trend?
    say("\n3. INCREMENTAL VALUE  (does credit beat what you already watch?)")
    vix = d["^VIX"] if "^VIX" in d else None
    spy_up = (d["SPY"] > d["SPY"].rolling(200).mean()).astype(float)
    for h in HORIZONS:
        fwd = sem_eq.shift(-h) / sem_eq - 1
        X = pd.concat([trend.rename("credit_21d"),
                       (vix / vix.rolling(252).mean() - 1).rename("vix_rel"),
                       spy_up.rename("spy_above_200")], axis=1)
        j = pd.concat([X, fwd.rename("y")], axis=1).dropna()
        if len(j) < 300:
            continue
        A = np.column_stack([np.ones(len(j))] + [j[c].to_numpy() for c in X.columns])
        coef, *_ = np.linalg.lstsq(A, j["y"].to_numpy(), rcond=None)
        resid = j["y"].to_numpy() - A @ coef
        s2 = float((resid ** 2).sum()) / (len(j) - A.shape[1])
        cov = s2 * np.linalg.inv(A.T @ A)
        se = np.sqrt(np.diag(cov))
        # overlapping windows: deflate t by sqrt(h), the standard crude fix
        say(f"\n   horizon {h} sessions  (n={len(j)}, overlap-adjusted t)")
        for i, cname in enumerate(["intercept"] + list(X.columns)):
            t = coef[i] / se[i] / np.sqrt(h)
            say(f"     {cname:<16}{coef[i]:>10.4f}   t={t:>6.2f}"
                + ("   <-- significant" if abs(t) > 2 else ""))

    # ---------------- 4. what it says RIGHT NOW
    say("\n4. WHERE WE ACTUALLY ARE TODAY")
    z = float((credit.iloc[-1] - credit.tail(252).mean()) / credit.tail(252).std())
    say(f"   credit ratio z-score vs its own last year: {z:+.2f}")
    dd = float(credit.iloc[-1] / credit.tail(252).max() - 1) * 100
    say(f"   distance below its 1-year high: {dd:.2f}%")
    say(f"   21d trend {float(trend.iloc[-1])*100:+.2f}%   "
        f"63d {float(credit.iloc[-1]/credit.iloc[-64]-1)*100:+.2f}%")
    if "NVDA" in d:
        n = d["NVDA"]
        say(f"   NVDA vs its 200d: "
            f"{float(n.iloc[-1]/n.rolling(200).mean().iloc[-1]-1)*100:+.1f}%")
    state = ("RISK-ON, no credit stress" if z > 0.5 else
             "NEUTRAL" if z > -0.5 else "CREDIT DETERIORATING")
    say(f"   reading: {state}")
    say("\nNOTE: 'no stress yet' is the normal state of this indicator. It has")
    say("said that on almost every day of the sample. A signal that is usually")
    say("silent is only useful if it is loud BEFORE the drawdown, which is")
    say("exactly what section 1 measures.")


if __name__ == "__main__":
    main()
