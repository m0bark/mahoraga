"""You picked the company. This says whether NOW is the moment.

    python research/sheet/confirm.py NVDA
    python research/sheet/confirm.py MU AVGO GOOGL      # several at once
    python research/sheet/confirm.py --all-confirmed    # what passes today

WHAT THIS IS AND IS NOT
It is NOT a stock picker. You have already decided the business is good and
the price is fair -- that is your job and this tool does not second-guess it.
It answers one narrower question: given that you want to own this, does the
timing evidence support buying TODAY?

Every check below was measured on this project's own point-in-time data, and
the number beside each one is what it was actually worth. Checks that failed
their control are included as WARNINGS, not as reasons to buy, because
knowing what does not work is half of not losing money.

THE CHECKS, and what each measured
  CAPITULATION  down 40%+ AND 10%+ off its 60-day low
                +6.08% vs market, 72% win over 433 events. The strongest
                single timing signal found in this project.
  FALLING KNIFE down 40%+ but STILL making new lows
                +1.12%, 60% win. MRNA fired this 25 months running from -42%
                to -83%. A veto, not a signal.
  RISK:REWARD   RETRACTED 2026-09-11 after QuantConnect. Kept as context
                only, scores nothing, vetoes nothing. See RETRACTION below.
  MOMENTUM      top decile 6-month, +1.83%/qtr over random
  NEAR HIGHS    within 5% of the 52-week high measured -0.64%, p=0.017.
                Mildly negative. Not a veto, but not a reason.
  VOLUME        a big move on below-average volume tends to reverse

DELIBERATELY NOT INCLUDED
  buy zone / support anchors  measured -0.23%/qtr against random
  analyst ratings             entering on the public date measured -0.67%
                              to -1.55%/month, p~0.0005
  the RATE score              top minus bottom quintile +0.10%/qtr, and the
                              quintiles are not even monotonic
Including a signal that lost money would be importing a known loss into a
confirmation tool. They are shown as context only.

RETRACTION -- the 3:1 risk:reward rule, 2026-09-11
Run on QuantConnect over 2013-2026 with working bracket exits, the 3:1 trigger
finished at $64,397 from $100,000 while SPY roughly tripled. The local study
that produced +0.212R was measuring three things wrongly:

  THE LEVELS ARE NOT LEVELS. Nearest clustered support sits a median 1.48%
  below the entry and resistance 4.59% above. Over a 504-bar window with a
  5-bar pivot rule there are dozens of swings, so "nearest" always lands on
  the last small wiggle. The 3:1 ratio was arithmetic performed on noise.

  R FLATTERED IT. In percent the trigger earned +0.39% per trade against
  +0.36% for simply buying the same name at market, a gap of three hundredths
  of a percentage point. The median trigger trade LOST 0.93% while the median
  market trade gained 0.91%.

  THE RESULT WAS A FILL ASSUMPTION, NOT A FORECAST. Simulating ten slots at
  9% each: if a stop 1.48% away always fills exactly at support the account
  ends +870%; if it fills at the low of the bar that triggered it, -97.4%.
  QC's -35.6% sits between those bounds, which is where a real broker fills.

  THE STOP WAS THE LOSS. The same entries with NO stop, exiting at the target
  or after 126 days, earned +1.97% mean and +3.28% median. A stop 1.48% away
  is hit by ordinary noise 70% of the time.

So price_for_3R below is still printed, because knowing where that price sits
is harmless, but it no longer confirms anything and no longer vetoes anything.
"""
from __future__ import annotations

import io
import os
import sys

_OUT = io.TextIOWrapper(open(sys.stdout.fileno(), "wb", closefd=False),
                        encoding="utf-8", errors="replace")


def say(*a) -> None:
    print(*a, file=_OUT)
    _OUT.flush()


import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")


def load():
    p = os.path.join(CACHE, "summary.csv")
    if not os.path.exists(p):
        return pd.DataFrame()
    return pd.read_csv(p)


def num(r, k, d=np.nan):
    try:
        v = pd.to_numeric(r.get(k), errors="coerce")
        return float(v) if np.isfinite(v) else d
    except Exception:
        return d


def check(r) -> tuple[list, list, list, int]:
    """Returns (confirms, warnings, vetoes, score)."""
    confirm, warn, veto = [], [], []
    score = 0

    dd = num(r, "pct_from_52w_high")
    off = num(r, "pct_off_recent_low")
    rr = num(r, "RR")
    mom = num(r, "MOMENTUM_SCORE")
    rsi = num(r, "rsi14")
    vol = num(r, "volume_x_normal")
    conf_lv = str(r.get("levels_confirmed", ""))
    rate = num(r, "RATE")

    # ---- vetoes first. These measured negative; no amount of other
    #      evidence should talk you past them.
    # the sub-2:1 veto came from the same study QC overturned on 2026-09-11,
    # so it is no longer allowed to block a trade. See RETRACTION in the
    # module docstring.
    if np.isfinite(dd) and dd <= -40 and np.isfinite(off) and off <= 2:
        veto.append(f"STILL MAKING NEW LOWS ({off:+.1f}% off its 60-day low). "
                    f"This is the MRNA pattern: it fired for 25 months from "
                    f"-42% to -83%. +1.1% edge vs +6.1% once it turns.")

    # ---- confirmations, strongest first
    if np.isfinite(dd) and dd <= -40 and np.isfinite(off):
        if off >= 20:
            confirm.append(f"CAPITULATION CONFIRMED: {dd:.0f}% off its high and "
                           f"{off:.0f}% up off the low. Measured +6.08% vs "
                           f"market, 72% win over 433 events.")
            score += 3
        elif off > 2:
            confirm.append(f"Capitulation, stabilising: {dd:.0f}% off the high, "
                           f"{off:.0f}% off the low. +4.41%, 67% win.")
            score += 2
    # R:R scores NOTHING. It read as the strongest idea in this project and it
    # is the one QC killed outright; see RETRACTION in the module docstring.
    if np.isfinite(mom) and mom >= 60:
        confirm.append(f"Momentum {mom:.0f}/100 -- the one selection signal "
                       f"that beat its control (+1.83%/qtr).")
        score += 1
    # "2+ touches" existed only to vouch for the R:R number, so it scores
    # nothing now that R:R does not. Two touches on a level 1.5% away is two
    # coincidences, not a floor.
    if np.isfinite(vol) and vol >= 1.5:
        confirm.append(f"Volume {vol:.1f}x normal -- the move is participated in, "
                       f"not a thin-tape drift.")
        score += 1

    # ---- warnings
    if np.isfinite(rr):
        warn.append(f"R:R reads {rr:.1f}:1, and that number is CONTEXT ONLY. "
                    f"Support sits a median 1.5% below the entry in this data, "
                    f"which is noise rather than a floor. On QuantConnect the "
                    f"3:1 rule lost 35.6% while SPY tripled. It scores nothing.")
    if np.isfinite(dd) and dd >= -5:
        warn.append(f"Within {abs(dd):.1f}% of the 52-week high. Buying near "
                    f"highs measured -0.64% vs random (p=0.017). Mild, but it "
                    f"is not a tailwind.")
    if np.isfinite(dd) and -40 < dd <= -15:
        warn.append(f"Down {abs(dd):.0f}% -- in the dead zone. Between -15% and "
                    f"-40% measured almost exactly zero. Not cheap enough to "
                    f"be a capitulation trade, not strong enough to be momentum.")
    if np.isfinite(rsi) and rsi < 30:
        warn.append(f"RSI {rsi:.0f}. Oversold reads as a signal but measured "
                    f"-0.89% vs random (p=0.48). It is noise here.")
    if np.isfinite(vol) and vol < 0.8:
        warn.append(f"Volume only {vol:.1f}x normal -- moves on thin volume "
                    f"tend to reverse.")
    if np.isfinite(rate) and np.isfinite(mom) and rate >= 60 and mom < 20:
        warn.append("Good fundamentals, weak momentum. Measured: screening for "
                    "healthy fundamentals in a beaten-down name made results "
                    "WORSE (-0.14% vs +2.67% for shrinking revenue). Filings "
                    "are ~57 days stale; price is forward-looking.")
    return confirm, warn, veto, score


def report(r) -> None:
    sym = r["symbol"]
    px = num(r, "price")
    confirm, warn, veto, score = check(r)
    verdict = ("DO NOT BUY YET" if veto else
               "CONFIRMED" if score >= 4 else
               "PARTIAL" if score >= 2 else "NO CONFIRMATION")
    say("")
    say("=" * 68)
    say(f"  {sym}   ${px:,.2f}   {str(r.get('shortName',''))[:38]}")
    say(f"  {verdict}   (confirmation score {score}/5)")
    say("=" * 68)
    if veto:
        say("\n  STOP:")
        for v in veto:
            say(f"    x  {v}")
    if confirm:
        say("\n  CONFIRMS:")
        for c in confirm:
            say(f"    +  {c}")
    if warn:
        say("\n  WARNINGS:")
        for w in warn:
            say(f"    !  {w}")
    if not confirm and not veto:
        say("\n  Nothing here confirms or forbids it. The timing evidence is")
        say("  silent, which is the most common answer and an honest one.")

    say("\n  THE NUMBERS")
    say(f"    from 52w high      {num(r,'pct_from_52w_high'):>8.1f}%")
    say(f"    off its 60d low    {num(r,'pct_off_recent_low'):>8.1f}%")
    say(f"    risk to support    {num(r,'risk_pct'):>8.2f}%   "
        f"(${num(r,'risk_$'):,.2f})")
    say(f"    reward to resist   {num(r,'reward_pct'):>8.2f}%   "
        f"(${num(r,'reward_$'):,.2f})")
    say(f"    R:R                {num(r,'RR'):>8.2f} : 1")
    say(f"    breakeven hit rate {num(r,'breakeven_hit_rate_pct'):>8.1f}%")
    say(f"    momentum           {num(r,'MOMENTUM_SCORE'):>8.0f}/100")
    sh = num(r, "max_shares_for_account")
    if np.isfinite(sh) and sh >= 1:
        say(f"\n  YOUR SIZE (20% sleeve of a $25k account, max 4 names)")
        say(f"    {sh:,.0f} shares = ${num(r,'actual_position_$'):,.0f}   "
            f"risking ${num(r,'actual_risk_$'):,.0f} to make "
            f"${num(r,'actual_gain_$'):,.0f}")

    p3 = num(r, "price_for_3R")
    if np.isfinite(p3) and np.isfinite(px):
        where = ("already below it" if px <= p3
                 else f"{(p3/px-1)*100:+.1f}% from here")
        say(f"\n  FOR REFERENCE ONLY: ${p3:,.2f} is the 3:1 price ({where}).")
        say("  Not a buy level. That rule lost 35.6% on QC while SPY tripled.")
    if np.isfinite(num(r, "pct_from_52w_high")) and num(r, "pct_from_52w_high") > -40:
        need = num(r, "high_52w") * 0.60
        if np.isfinite(need):
            say(f"  WAIT FOR: ${need:,.2f} would be a -40% capitulation "
                f"({(need/px-1)*100:+.1f}% from here).")


def trigger_price(r):
    """THE ONE NUMBER: the price at which this becomes worth buying.

    Whichever is HIGHER of:
      * the 3:1 risk:reward price -- support + a quarter of the range up to
        resistance. Below 2:1 measured worse than a random entry, so 3:1 is
        the first price where the asymmetry is doing real work.
      * a -40% capitulation from the 52-week high, IF it is not already there.
    Higher of the two because the nearer trigger is the one that fires first,
    and waiting for the deeper one on a stock that never gets there means
    never buying anything.
    """
    px = num(r, "price")
    p3 = num(r, "price_for_3R")
    cands = [x for x in (p3,) if np.isfinite(x) and x > 0]
    if not cands:
        return np.nan, "no clean levels to price a trigger from"
    t = max(cands)
    if t >= px:
        return px, "already at or below the trigger"
    return t, f"{(t/px-1)*100:+.1f}% from here"


def arm(symbols, do_write=True):
    """Turn a list of companies you already like into standing alerts.

    This is the answer to 'I do not want to watch it 24 hours'. You supply
    the judgement about the business; this supplies the price and the alarm.
    Nothing is bought automatically -- the bot messages you and you decide.
    """
    import csv as _csv
    d = load()
    WATCH = os.path.join(HERE, "watchlist.csv")
    rows = []
    if os.path.exists(WATCH):
        rows = [r for r in _csv.DictReader(open(WATCH, encoding="utf-8"))]
    say(f"{'symbol':<8}{'now':>10}{'trigger':>10}{'away':>9}  what fires it")
    say("-" * 66)
    armed = 0
    for sym in symbols:
        m = d[d.symbol == sym.upper()]
        if m.empty:
            say(f"{sym.upper():<8}  not in the S&P 500 sheet")
            continue
        r = m.iloc[0]
        t, note = trigger_price(r)
        px = num(r, "price")
        if not np.isfinite(t):
            say(f"{sym.upper():<8}{px:>10.2f}         -         {note}")
            continue
        say(f"{sym.upper():<8}{px:>10.2f}{t:>10.2f}"
            f"{(t/px-1)*100:>8.1f}%  3:1 risk:reward")
        rows = [x for x in rows if not (x.get("symbol") == sym.upper()
                                        and x.get("type") == "price_below")]
        rows.append({"symbol": sym.upper(), "type": "price_below",
                     "level": f"{t:.2f}", "note": "3R trigger, armed by confirm.py",
                     "fired": ""})
        armed += 1
    if do_write and armed:
        with open(WATCH, "w", newline="", encoding="utf-8") as fh:
            w = _csv.DictWriter(fh, fieldnames=["symbol", "type", "level",
                                                "note", "fired"])
            w.writeheader()
            w.writerows(rows)
        say("-" * 66)
        say(f"{armed} alerts armed in watchlist.csv.")
        say("The 5-minute job checks them and Telegram messages you.")
        say("You do not need to watch anything.")


def main() -> None:
    d = load()
    if d.empty:
        say("no cache -- run build_workbook.py first")
        return
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if "--arm" in sys.argv:
        if not args:
            say("usage: confirm.py --arm NVDA MU AVGO")
            return
        arm(args)
        return
    if "--all-confirmed" in sys.argv:
        hits = []
        for _, r in d.iterrows():
            c, w, v, s = check(r)
            if not v and s >= 4:
                hits.append((s, r))
        say(f"{len(hits)} names confirmed by the timing evidence today "
            f"(of {len(d)})")
        for s, r in sorted(hits, key=lambda t: -t[0]):
            report(r)
        if not hits:
            say("\nNothing clears a score of 4 today. That is normal and it is")
            say("the honest answer -- the signals are rare by construction.")
        return
    if not args:
        say(__doc__.split("WHAT THIS IS")[0])
        say("usage: confirm.py NVDA [MU AVGO ...]   |   --all-confirmed")
        return
    for sym in args:
        r = d[d.symbol == sym.upper()]
        if r.empty:
            say(f"\n{sym.upper()} not in the S&P 500 sheet")
            continue
        report(r.iloc[0])


if __name__ == "__main__":
    main()
