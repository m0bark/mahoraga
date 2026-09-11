"""Grant perfect foreknowledge of the rate direction. Is it worth anything?

    python research/sheet/rate_foresight.py

THE QUESTION BEHIND "FOMC IS GOING TO BE A HIKE"
Whether that call is right is unknowable in advance and this file does not try.
It asks the prior question, which is the one that decides whether the call is
worth making: IF you knew the rate direction with certainty, could you turn it
into a better stock selection?

So the test cheats deliberately and in your favour. It classifies each month by
what long rates ACTUALLY DID over the following 63 days, which is information
nobody has on the decision date. That is lookahead, on purpose. It is the
best possible case for trading a rate view. If a rule cannot make money with
the answer written on the back of the card, it cannot make money with a
forecast, and the FOMC call stops mattering.

HOW RATE EXPOSURE IS MEASURED
TLT is the long-Treasury proxy in this cache. A stock's rate beta is the slope
of its daily returns against TLT's over the trailing 252 days, computed from
past data only, so the EXPOSURE is point-in-time even though the REGIME label
is not. A positive rate beta means the name rises when bonds rise, which is to
say when yields fall: a long-duration stock. A negative rate beta means it
rises when yields rise.

Rates rising shows up as TLT FALLING. The conventional view is that high-
duration names suffer in a hiking cycle, so the expectation is a negative
decile spread in rate-rising windows and a positive one in rate-falling ones.

WHAT IS REPORTED
  1. Does the regime matter for the market at all? Mean forward return of the
     whole universe in rate-rising against rate-falling windows.
  2. The rate-beta decile spread in each regime, on returns demeaned within the
     month so this measures SELECTION rather than market timing. Timing the
     index is a separate question and a cash account long-only cannot act on a
     bearish answer anyway.
  3. Whether the sign is stable, because a rule that needs the regime AND gets
     the direction backwards half the time is two coin flips.

THE SAMPLE IS THE LIMITATION, AND IT IS A REAL ONE
2013 to 2026 contains the taper, the 2015-2018 hikes, the 2020 collapse to
zero and the 2022-2023 hikes. That is genuine variation, but it is a handful of
distinct episodes rather than a hundred independent observations, so any
conclusion here is an observation about four or five regimes and is reported
that way. Overlapping 63-day windows on monthly dates make the effective
sample roughly a third of the raw count.
"""
from __future__ import annotations

import importlib.util
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

BETA_WINDOW = 252
N_DEC = 10
PROXY = "TLT"


def rate_betas(C: pd.DataFrame, syms: list) -> pd.DataFrame:
    """Rolling slope of each name's returns on TLT's, trailing only.

    Vectorised over the whole panel: cov(r_i, r_b) / var(r_b) from rolling
    means. A per-name regression loop over 465 symbols and 4,200 days is
    minutes of work for the same answer."""
    R = C[syms].pct_change()
    b = C[PROXY].pct_change()
    mb = b.rolling(BETA_WINDOW).mean()
    vb = b.rolling(BETA_WINDOW).var()
    mr = R.rolling(BETA_WINDOW).mean()
    cov = (R.mul(b, axis=0).rolling(BETA_WINDOW).mean()
           .sub(mr.mul(mb, axis=0)))
    return cov.div(vb, axis=0)


def main() -> None:
    g = pd.read_csv(os.path.join(LONG, "grid.csv"), parse_dates=["date"])
    C = pd.read_csv(os.path.join(LONG, "px_close.csv"), index_col=0,
                    parse_dates=True).sort_index()
    if PROXY not in C.columns:
        say(f"{PROXY} absent from the cache; cannot run")
        return
    syms = sorted(set(g.symbol) & set(C.columns))
    say(f"{len(g):,} rows | {len(syms)} symbols | proxy {PROXY}")

    RB = rate_betas(C, syms)
    rb = RB.stack().rename("rate_beta").reset_index()
    rb.columns = ["date", "symbol", "rate_beta"]
    d = g.merge(rb, on=["date", "symbol"], how="left").dropna(subset=["rate_beta"])

    # THE DELIBERATE LOOKAHEAD: what long rates actually did next.
    tlt = C[PROXY].dropna()
    fwd = {}
    for dt in d.date.unique():
        ts = pd.Timestamp(dt)
        if ts not in tlt.index:
            continue
        i = tlt.index.get_loc(ts)
        j = min(i + 63, len(tlt) - 1)
        fwd[ts] = (tlt.iloc[j] / tlt.iloc[i] - 1) * 100
    d["tlt_fwd"] = d.date.map(fwd)
    d = d.dropna(subset=["tlt_fwd"])
    # TLT down means yields UP means a hiking/hawkish window
    d["regime"] = np.where(d.tlt_fwd < 0, "rates UP", "rates DOWN")
    d["y"] = d.fwd63 - d.groupby("date")["fwd63"].transform("mean")

    say(f"{d.date.nunique()} months classified by the NEXT 63 days of {PROXY}")
    n_up = d[d.regime == "rates UP"].date.nunique()
    say(f"  rates UP: {n_up} months   rates DOWN: {d.date.nunique() - n_up}")

    say("")
    say("=" * 76)
    say("  1. DOES THE REGIME MATTER FOR THE MARKET AT ALL?")
    say("=" * 76)
    say(f"  {'regime':<14}{'months':>8}{'mean fwd 63d':>15}{'median':>10}")
    for r, sub in d.groupby("regime"):
        mm = sub.groupby("date").fwd63.mean()
        say(f"  {r:<14}{len(mm):>8}{mm.mean():>+14.2f}%{mm.median():>+9.2f}%")
    say("")
    say("  Long-only in a cash account cannot act on a bearish regime answer,")
    say("  so this is context. The actionable question is the next one.")

    say("")
    say("=" * 76)
    say("  2. RATE-BETA DECILES, WITHIN REGIME, RETURNS DEMEANED BY MONTH")
    say("=" * 76)
    say("  High decile = most positive rate beta = longest duration,")
    say("  the names conventional wisdom says a hike should punish.")
    say("")
    say(f"  {'regime':<14}{'n':>8}{'high dec':>11}{'low dec':>10}"
        f"{'high-low':>11}{'t':>8}{'mono':>7}")
    say("  " + "-" * 72)
    for r, sub in d.groupby("regime"):
        s = sub.copy()
        s["dec"] = s.groupby("date")["rate_beta"].transform(
            lambda x: pd.qcut(x.rank(method="first"), N_DEC, labels=False,
                              duplicates="drop")
            if x.notna().sum() >= N_DEC else np.nan)
        s = s.dropna(subset=["dec"])
        hi = s.loc[s.dec == s.dec.max(), "y"]
        lo = s.loc[s.dec == 0, "y"]
        if len(hi) < 2 or len(lo) < 2:
            continue
        se = np.sqrt(hi.var(ddof=1) / len(hi) + lo.var(ddof=1) / len(lo))
        t = (hi.mean() - lo.mean()) / se if se > 0 else np.nan
        means = s.groupby("dec")["y"].mean()
        mono = means.corr(pd.Series(means.index, index=means.index),
                          method="spearman")
        say(f"  {r:<14}{len(s):>8,}{hi.mean():>+10.2f}%{lo.mean():>+9.2f}%"
            f"{hi.mean() - lo.mean():>+10.2f}%{t:>+8.2f}{mono:>+7.2f}")
    say("")
    say("  Overlapping 63-day windows on monthly dates inflate these t values")
    say("  by roughly sqrt(3). Divide by about 1.7 before believing one.")

    say("")
    say("=" * 76)
    say("  3. IS THE SIGN STABLE, YEAR BY YEAR, IN RATES-UP WINDOWS ONLY?")
    say("=" * 76)
    up = d[d.regime == "rates UP"].copy()
    up["dec"] = up.groupby("date")["rate_beta"].transform(
        lambda x: pd.qcut(x.rank(method="first"), N_DEC, labels=False,
                          duplicates="drop")
        if x.notna().sum() >= N_DEC else np.nan)
    up = up.dropna(subset=["dec"])
    up["yr"] = up.date.dt.year
    say(f"  {'year':<8}{'months':>8}{'high-low':>12}")
    pos = neg = 0
    for y, sub in up.groupby("yr"):
        hi = sub.loc[sub.dec == sub.dec.max(), "y"]
        lo = sub.loc[sub.dec == 0, "y"]
        if len(hi) < 2 or len(lo) < 2:
            continue
        sp = hi.mean() - lo.mean()
        pos += sp > 0
        neg += sp <= 0
        say(f"  {int(y):<8}{sub.date.nunique():>8}{sp:>+11.2f}%")
    say("  " + "-" * 32)
    say(f"  same sign in {max(pos, neg)} of {pos + neg} years with data")

    say("")
    say("=" * 76)
    say("  WHAT THIS MEANS FOR AN FOMC CALL")
    say("=" * 76)
    say("  The regime label above is the ANSWER KEY, not a forecast. Whatever")
    say("  spread appears is the ceiling on what a correct rate call could")
    say("  have earned through stock selection, before you account for being")
    say("  wrong some of the time. A real forecast that is right 60% of the")
    say("  time captures roughly a fifth of a two-sided spread, because the")
    say("  40% of wrong calls pay the spread in reverse.")


if __name__ == "__main__":
    main()
