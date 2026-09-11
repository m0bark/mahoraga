# Reverse-engineering surges — 2026-08-30

Mined the outcome first, then asked what caused it. 1,586 surges
(>= +25% in 20 trading days), 120 liquid US names, 2011–2026.

## 1. What a surge is made of

| | |
|---|---|
| median share of the 20d move from its single biggest day | **35%** |
| surges where one day is >= 50% of the whole move | 23% |
| that biggest day opened on a **gap >= 3%** | **54%** |
| median gap as a share of that day's return | 37% |
| surges where SPY also rose > 5% (market-wide, not the name) | **48%** |

Half of all "stock surges" are the market surging. Of what's left, the
move is dominated by single days that **gap at the open** — i.e. the price
is set before anyone can trade it. That is information arriving, not a
pattern completing.

## 2. There is no pre-signature — the part that would be tradeable

| | |
|---|---|
| median volume in the 5 days BEFORE the surge, vs 60d avg | **0.93×** |
| surges with elevated pre-volume (> 1.5×) | **12%** |
| median return in the 5 days BEFORE the surge | **−4.27%** |

Volume before a surge is **below** normal, and the stock is still falling.
No accumulation footprint, no leak, no build-up. **This is the finding:**
surges are not preceded by anything visible in price or volume, because
they are caused by news, and news arrives without telegraphing itself.

## 3. Surges do come from dips — and it does NOT mean what it looks like

| drawdown state | % of all days | % of surges | lift |
|---|---|---|---|
| deep dip (< −30%) | 14.5% | **48.4%** | **3.35×** |
| −15..−30% | 21.2% | 24.0% | 1.13× |
| −5..−15% | 30.8% | 17.4% | 0.57× |
| near highs (> −5%) | 33.6% | 10.3% | 0.31× |

Forward direction, P(surge in next 20d | state today): deep dip **8.55%**
vs near highs **1.20%** — genuinely 7× more likely, and not a base-rate
artifact.

**But frequency is not return.** Same buckets, both tails:

| state | P(+25%) | P(−25%) | up/down | mean 20d | stdev |
|---|---|---|---|---|---|
| deep dip (< −30%) | 8.55% | 3.65% | 2.34× | +3.12% | 17.6% |
| −15..−30% | 2.94% | 1.22% | 2.41× | +2.08% | 12.2% |
| −5..−15% | 1.69% | 0.75% | 2.27× | +1.71% | 9.9% |
| near highs (> −5%) | 1.20% | 0.60% | 2.00× | +1.28% | 8.7% |

The up/down ratio is **flat at ~2.0–2.4× across every state.** Going deeper
into a drawdown buys you more of *both* tails at nearly the same ratio.
That is volatility, not edge.

## 4. Do NOT read the "mean 20d" column as an edge

It shows deep dips at +3.12% vs +1.28%. That column is **survivorship-
biased** — 120 current survivors, so every deep dip that never came back is
missing from the sample. This project has measured that gap at ~20 points
four separate times.

The survivorship-free answer already exists and points the other way:
card `2026-08-30-quality-dip200.md`, point-in-time 2007–2022, quality names
at the dip **6.90%/yr** vs quality names not dipping **12.09%/yr**
(−5.19%/yr). **Trust the QC number, not this column.**

## Verdict

Reverse-engineering answers the *detectability* question cleanly, and that
answer survives the survivorship problem because it is about pre-move
footprints, not returns:

**Surges are caused by information arriving, and nothing in price or volume
sees it coming.** 54% gap open, half are just the market, pre-volume is
below average, and the stock is still falling right up to the day it turns.

Scripts: `why_surge.py`, `base_rate.py`, `symmetry.py`. Data: `surges.csv`.

---

# Case studies — explaining three real surges (non-chart)

Picked from `surges.csv`, causes verified against reporting.

## MP Materials — big day 2025-07-10, +51% (opened **+60% gap**)

**Cause:** DoD announced a public-private partnership — $400M of preferred
stock making the Pentagon MP's **largest shareholder (~15%)**, plus a
10-year agreement to buy **100%** of output from the new 10X magnet
facility.

**Knowable in advance?** No. A confidential government negotiation,
announced pre-market. The +60% open means every buyer paid the new price.
*Caveat:* MP is the one name in the sample with elevated pre-volume
(**1.80×**). One observation, and 12% of surges clear 1.5× by chance —
suggestive, not evidence.

**Class:** policy / government action.

## Atlassian — big day 2026-08-06, +35% (opened **+32% gap**)

**Cause:** FQ4 beat — EPS $1.87 vs $1.50 consensus, revenue $1.77B vs
$1.66B, cloud revenue +31%, **RPO +44%**. Started the run **51% below its
52-week high**.

**Knowable in advance?** The *date* was. The *result* wasn't. But RPO +44%
and cloud +31% are disclosed quarterly and lead revenue — the direction was
visible in filings before the print.

**Class:** earnings surprise. This is the archetype of the "great company,
way down, then it rips" thesis — and it is real. The cost of owning it was
sitting through a 51% drawdown and every prior quarter that did nothing.

## Intel — big day 2026-04-24, +24% (opened **+23% gap**)

**Cause:** Q1 revenue $13.6B, EPS **$0.29 vs $0.01** consensus. Then a
reported preliminary Apple foundry agreement, a Musk "Terafab" tie-up, and
cloud supply deals extended it to **+92% in 20 days**.

**Knowable in advance?** No. And note: Intel was **at its highs** when this
started (drawdown 0%), not in a dip — the opposite of the setup thesis.

**Class:** earnings surprise + strategic deals.

## What the three have in common

All three are cleanly explainable, and **not one explanation is a chart**.
All three **gapped** (+60%, +32%, +23%) — the move happened while the market
was closed, at a price nobody could transact at.

**What is actually knowable in advance is not the surge — it is the
exposure:**

1. **The date, for earnings** (TEAM, INTC). You can be positioned. It is a
   coin flip on the result, and it cuts both ways.
2. **The structural setup** (MP). You could not know the date of a Pentagon
   deal, but you could know MP was the only scaled US rare-earth producer
   during a US-China supply-chain fight — i.e. the name that gets the call
   *if* a call gets made.
3. **Leading indicators in the filings** (TEAM's RPO +44%). Disclosed,
   public, and ahead of revenue.

That is the honest job of a screen: not predicting the surge, but **owning
the name where a plausible catalyst class exists** when it lands.
