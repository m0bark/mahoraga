"""Is VIX / 16 a good estimate of today's S&P move? And is "bigger than
implied" a signal worth acting on?

    python research/sheet/vix_rule.py

THE CLAIM (this one is mathematically sound, unlike most)
VIX quotes ANNUALISED implied volatility. There are ~252 trading days a year
and sqrt(252) = 15.87, so VIX / 16 converts it to a one-day expected move.
VIX 16 -> ~1.0%/day. VIX 24 -> ~1.5%. VIX 32 -> ~2.0%. The arithmetic is right.

WHAT IS WORTH TESTING IS THE USE, NOT THE ARITHMETIC
 1. CALIBRATION. Over 16 years, how does the actual |daily move| compare with
    what VIX/16 implied the day before? If implied systematically exceeds
    realised, the rule is not "what the market will do", it is "what options
    are charging for", and those differ by a known risk premium.
 2. COVERAGE. A 1-sigma band should contain ~68% of days if moves were normal.
    Returns are fat-tailed, so the real number matters.
 3. DOES "BIGGER THAN IMPLIED" PREDICT ANYTHING? The pitch says an outsized
    move means assumptions changed and you should consider repositioning.
    That is testable: sort days by actual/implied and look at what the S&P
    did NEXT, at 1 / 5 / 21 days.

A rule can be perfectly correct arithmetic and still carry no trading edge.
Those are separate questions and only the second one pays.
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

SQRT252 = float(np.sqrt(252))


def main() -> None:
    d = yf.download(["^GSPC", "^VIX"], start="2010-01-01", auto_adjust=True,
                    progress=False, threads=True)["Close"].dropna()
    d.columns = [str(c) for c in d.columns]
    spx, vix = d["^GSPC"], d["^VIX"]
    say(f"{len(d)} sessions {d.index[0]:%Y-%m-%d} .. {d.index[-1]:%Y-%m-%d}")
    say(f"sqrt(252) = {SQRT252:.2f}, so the 'divide by 16' shortcut is off by "
        f"{(16/SQRT252-1)*100:+.1f}% -- immaterial\n")

    ret = spx.pct_change() * 100
    # yesterday's VIX is what you would actually have had this morning
    implied = (vix.shift(1) / 16)
    j = pd.concat([implied.rename("imp"), ret.rename("ret")], axis=1).dropna()
    j["abs"] = j["ret"].abs()
    j["ratio"] = j["abs"] / j["imp"]

    say("1. CALIBRATION -- what VIX/16 implied vs what actually happened")
    say(f"   mean implied daily move   {j['imp'].mean():.2f}%")
    say(f"   mean ACTUAL |daily move|  {j['abs'].mean():.2f}%")
    say(f"   ratio actual/implied      {j['abs'].mean()/j['imp'].mean():.2f}")
    say("   NOTE: a normal distribution's mean |move| is 0.798 sigma, so a")
    say("   perfectly calibrated VIX would show ~0.80 here, not 1.00.")
    say(f"   adjusted for that: {j['abs'].mean()/j['imp'].mean()/0.798:.2f} "
        "(1.00 = options priced it exactly right)")
    say(f"   => options have been charging about "
        f"{(1-j['abs'].mean()/j['imp'].mean()/0.798)*100:.0f}% MORE than "
        "realised. That gap is the variance risk premium and it is why")
    say("      selling options is a business.\n")

    say("2. COVERAGE -- how often the actual move stayed inside the band")
    for k, want in ((1.0, 68), (1.5, 87), (2.0, 95), (3.0, 99.7)):
        inside = float((j["ratio"] <= k).mean() * 100)
        say(f"   within {k:.1f}x implied: {inside:5.1f}%   "
            f"(normal distribution would say {want}%)")
    say(f"   days that moved MORE than 2x implied: "
        f"{int((j['ratio'] > 2).sum())} of {len(j)} "
        f"({(j['ratio'] > 2).mean()*100:.1f}%)")
    say("   Fat tails: big days are more common than the normal curve says,")
    say("   so 'more than implied' happens more often than it feels like.\n")

    say("3. BY VIX LEVEL -- is the rule equally good everywhere?")
    say(f"   {'VIX range':<14}{'n':>6}{'implied':>9}{'actual':>9}{'act/imp':>9}")
    say("   " + "-" * 48)
    bins = [(0, 13), (13, 16), (16, 20), (20, 26), (26, 35), (35, 100)]
    v1 = vix.shift(1).reindex(j.index)
    for lo, hi in bins:
        m = (v1 >= lo) & (v1 < hi)
        if m.sum() < 30:
            continue
        say(f"   {f'{lo}-{hi}':<14}{int(m.sum()):>6}{j.loc[m,'imp'].mean():>8.2f}%"
            f"{j.loc[m,'abs'].mean():>8.2f}%"
            f"{j.loc[m,'abs'].mean()/j.loc[m,'imp'].mean():>9.2f}")
    say("")

    say("4. DOES 'BIGGER THAN IMPLIED' PREDICT ANYTHING NEXT?")
    for h in (1, 5, 21):
        fwd = (spx.shift(-h) / spx - 1) * 100
        k = pd.concat([j["ratio"], j["ret"], fwd.rename("f")], axis=1).dropna()
        q = pd.qcut(k["ratio"].rank(method="first"), 5,
                    labels=["quietest", "2", "3", "4", "most outsized"])
        g = k.groupby(q)["f"].agg(["mean", "count"])
        say(f"\n   next {h} session(s), sorted by actual/implied:")
        for lab, row in g.iterrows():
            say(f"     {str(lab):<16}{row['mean']:>7.2f}%   n={int(row['count'])}")
        say(f"     outsized minus quiet: "
            f"{g['mean'].iloc[-1]-g['mean'].iloc[0]:+.2f}%")
    say("")

    say("5. SPLIT BY DIRECTION -- an outsized DOWN day vs an outsized UP day")
    big = j[j["ratio"] > 1.5]
    for h in (1, 5, 21):
        fwd = (spx.shift(-h) / spx - 1) * 100
        k = pd.concat([big["ret"], fwd.rename("f")], axis=1).dropna()
        dn, up = k[k["ret"] < 0], k[k["ret"] > 0]
        base = float(((spx.shift(-h) / spx - 1) * 100).mean())
        say(f"   next {h:>2}d after a >1.5x implied DOWN day: "
            f"{dn['f'].mean():+6.2f}%  (n={len(dn)})   "
            f"UP day: {up['f'].mean():+6.2f}%  (n={len(up)})   "
            f"all days: {base:+.2f}%")
    say("")

    say("6. TODAY")
    v = float(vix.iloc[-1])
    say(f"   VIX {v:.2f}  ->  implied S&P move {v/16:.2f}% "
        f"(band +/-{v/16:.2f}%, 2x band +/-{2*v/16:.2f}%)")
    say(f"   yesterday's actual move {float(ret.iloc[-1]):+.2f}% "
        f"= {abs(float(ret.iloc[-1]))/(float(vix.iloc[-2])/16):.2f}x implied")
    say("")
    say("VERDICT: the arithmetic is right and the band is genuinely useful as")
    say("CONTEXT -- it tells you whether a red screen is ordinary or unusual,")
    say("which is a real thing to know. Whether it is a TRADING signal is")
    say("section 4, and that is a different question with its own answer.")


if __name__ == "__main__":
    main()
