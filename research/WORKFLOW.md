# Stock picking workflow (operating procedure, 2026-08-30)

The missing half of [PROTOCOLS.md](PROTOCOLS.md). PROTOCOLS says *when* to
buy and *when* to sell. This says *what you are allowed to buy at all*, and
in what order the decisions fire.

**Standing honesty note.** No selection layer in this project has ever
beaten the index in a survivorship-free test. Overreaction-reversal died
4×, quality-broken tilt by a hair, insider clusters on a sealed holdout.
So this workflow does not claim stock-picking alpha. It is an allocation
and eligibility discipline: index does the compounding, the rules stop you
from destroying that return with bad names and emotional timing, and one
small contractual sleeve adds uncorrelated dollars.

---

## Layer 0 — The three buckets (decide once, revisit yearly)

| Bucket | Weight | Purpose |
|---|---|---|
| Core | 60-75% | Broad index, always invested. This is where the return comes from. |
| Dip reserve | 20-35% | Cash held to deploy on the PROTOCOLS ladder. Not "waiting for a crash" — it has pre-committed triggers. |
| Event sleeve | ≤10% | Reverse-split cash-outs + odd-lot tenders. Uncorrelated, contractual, capacity-capped. |

Constraints (locked): long spot only, cash account, no options/futures/
CFDs/margin/shorts. Max **5%** of portfolio per single name, ever.

---

## Layer 1 — Eligibility screen (a name must pass ALL, or it is not a candidate)

Run this before any thesis, any chart, any story.

1. **Profitable** — positive trailing net income AND positive operating cash flow.
2. **Debt manageable** — net debt / EBITDA < 3, or net cash.
3. **Liquid** — ≥$1M median daily dollar volume (retail spread tolerance).
4. **Not a story stock** — has revenue, has customers, is not pre-product.
5. **Halal-compatible line of business** (issuer screen, same one used in the forced-flows survey).
6. **Not broken** — see Layer 3's fear-vs-broken test. Applied here as a veto.

Anything failing one line is out. No exceptions for conviction.

Why these and not a factor model: the quality filter was the one component
that measurably added (+3.2%/yr over the unconditioned tilt in the QC test)
even though the total strategy still failed. Treat quality as a *veto*, not
a signal.

---

## Layer 2 — When you're allowed to act (from PROTOCOLS)

- **Core**: buy on schedule, into the turn-of-month window (last 4 / first 3
  trading days). No timing overlay.
- **Dip reserve**: ladder on the *market*, not on names —
  SPY −10% from 252-day high → 25% of reserve; −20% → 35%; −30% → last 40%.
- **Single names**: only unlock when SPY ≥12% below its high AND VIX > 30.
  In a calm market you buy zero individual dips. That is the whole rule.

---

## Layer 3 — Name selection (only fires inside a systemic panic)

Candidate must pass Layer 1, plus:

- down ≥30% from its own 252-day high;
- **fear, not broken** (the AppLovin-vs-TradeDesk test):
  - FEAR = growth intact, the miss is small or macro, guidance still up;
  - BROKEN = slowest growth ever, guidance implying revenue *decline*,
    structural share loss, fraud or going-concern language. Skip broken.
- Entry in 2 tranches: half now, half only if it falls another 15%.
- Cap 5% of portfolio. Assume ~50% odds of one more −10% leg — that was
  measured at every depth in the dip atlas (4,751 episodes).

Rank candidates by *nothing clever*. If more than you can fund pass, take
the largest/most liquid ones. Every ranking layer this project tested
subtracted value.

> **AMENDED 2026-08-30, CORRECTED 2026-08-31 — read before using this layer.**
>
> Two sealed point-in-time QC runs now bear on this, and they disagree
> unless you read the definitions carefully.
>
> **Run A** (card `2026-08-30-quality-dip200.md`): names >=15% off their
> high **AND sitting within -15%/+5% of the 200-day SMA**, quality-filtered,
> returned **6.90%/yr** against **12.09%/yr** for quality names not at that
> setup. That specific setup cost **-5.19%/yr**.
>
> **Run B** (card `2026-08-31-nearhigh-fscore.md`): sorting the same PIT
> universe purely by drawdown depth, the deepest quintile returned
> **+12.02%/yr** against **+8.17%** for the quintile nearest its 52-week
> high. Drawdown depth alone was the **better** half of that sort.
>
> **What this means.** The earlier amendment here said "the drawdown filter
> is an anti-signal." That was **too broad and is withdrawn.** What is
> actually supported: the *combination* of a deep drawdown with price
> pinned near the 200-day SMA underperformed. Drawdown depth on its own did
> not. The 200-day condition, or the comparison group, was doing the damage
> -- and which of the two has not been isolated.
>
> **What survived both runs:** buying near the 52-week high was measurably
> worse (Run B, G1 = -3.85%/yr), so the momentum/anchoring alternative is
> also closed, sealed for 12 months.
>
> **Practical reading:** this layer is unproven, not refuted. Do not treat
> a drawdown as a signal in either direction. Layer 1 (quality) is the only
> component with a clean positive PIT result behind it.

---

## Layer 4 — The event sleeve (the only lane with a live GO)

Weekly, ~20 minutes:

```bash
python research/tenders/reverse_split_scan.py
python research/tenders/tender_scan.py
```

Reverse-split cash-out discipline (non-negotiable, from
[forced_flows/SURVEY-2026-08-28.md](forced_flows/SURVEY-2026-08-28.md)):

- SC 13E3 filings are the high-precision signal; 14A hits are mostly
  routine compliance splits — read before acting.
- Buy **below the ratio-range MINIMUM** threshold, never between bounds.
- Prefer **post-vote** entry (1-3% near-riskless residual) over
  post-announcement (5-10% but abandonment risk).
- Check street-name vs record-holder treatment per deal; record-holder-only
  deals need a DRS transfer or you skip.
- Issuer sector screen applies here too.

**Gate before real money in this sleeve** (pre-registered, not yet met):
36-month backfilled event ledger showing ≥8 investable events, ≥85%
completion, ≥$150 avg net/event at post-vote entry — then paper one live
event end-to-end including the DRS test.

---

## Layer 5 — Exits (from PROTOCOLS, restated so the loop closes)

- Trim any position above 1.5× target weight back to target.
- Dip-buys: exit on a close 20% below the highest close since entry. Never tighter.
- Thesis break → sell 100% immediately, regardless of chart.
- Recovered to old high → it's no longer a dip trade: re-justify as a normal
  holding or trim to target.
- Never sell into "resistance" or a round number. Targets tested worse than holding.

---

## Cadence

| When | Do |
|---|---|
| Weekly (Sun) | Run both scanners. Read any SC 13E3 hit. Check SPY drawdown vs ladder triggers and VIX. |
| Turn-of-month | Execute scheduled core buys. |
| On a ladder trigger | Deploy the tranche. Same day. No waiting for "stabilization" (RSI recross fires ~31 days early, 61% false bottoms). |
| Monthly | Re-check every holding against Layer 1. Any name that has stopped passing gets the thesis-break test. |
| Quarterly | Position-size audit: anything >1.5× target gets trimmed. |
| Yearly | Revisit bucket weights. Nothing else. |

---

## Banned (tested and killed in this repo — do not reintroduce)

- Bottom-calling with indicators; RSI recross entries.
- Profit targets at prior highs / resistance.
- Tight stops near lows (wicked out 52% of the time).
- Averaging down outside the planned tranches.
- Buying a lone stock bleeding in a calm market (worst-recovering class).
- Momentum in large caps, overnight-drift trades, SMA200 as a return signal.
- Any reversal/overreaction variant (family retired at 4 sealed failures).
- Insider-cluster concentration (failed sealed holdout 2023→2026-08).
- Index-deletion, CEF-discount, and Russell-recon plays (NO-GO, high conf).
- Trusting any local yfinance backtest number as evidence — survivorship
  gap measured at ~20pts, three separate times.

**The bar every decision is measured against: SPY buy-and-hold, ~10%/yr.**
If a step in this workflow can't be argued to beat that or to reduce risk
without costing return, it doesn't belong here.
