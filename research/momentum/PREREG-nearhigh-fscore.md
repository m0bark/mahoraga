# PRE-REGISTRATION — 52-week-high momentum × fundamental quality (QC)

**Written before the run. Sealed by push. No mid-run edits.**

## Family accounting

**Family: momentum/anchoring — shot #1/10. Evidential class: DISCOVERY.**

This is **not** a revision of overreaction-reversal (retired, 5 sealed
failures). That family buys names *because they fell*. This one buys names
*because they are near their highs* — the opposite sign, a different
documented mechanism (George & Hwang, JF 2004: anchoring on the 52-week
high; robust in 18 of 20 markets, no long-run reversal).

Prior work in this repo on momentum was a **local yfinance sweep**
("momentum dead in large caps post-2005") — scouting, never a sealed
verdict, and run on data since shown to distort this exact question by
~26 points (`research/screen/RESULTS-nearhigh.md`).

## Why one token buys 25 answers

The traded portfolio costs orders; **virtual tracks cost nothing.** This
run carries the full grid as in-run tracks:

- **5 nearness quintiles** (price / 252-day high) N1 nearest … N5 deepest
- **× 5 quality buckets** (F-Score-lite, 0–7 legs from PIT Morningstar)
- = **25 cells**, plus EW universe, 3 turnover-matched random twins, SPY.

One backtest therefore answers, simultaneously:
1. Does nearness to the 52-week high predict returns, PIT? (the George &
   Hwang direction, never tested here on clean data)
2. Does fundamental quality separate *within* each nearness bucket?
   (the Piotroski claim: quality separates winners inside a price-selected
   group — he found +7.5%/yr within cheap stocks)
3. Is the interaction monotonic, or driven by one corner cell?
4. **Does the deep-dip corner reproduce the −5.19%/yr from card
   2026-08-30?** A replication check, free, inside this run.

A FAIL on (1) still returns (2), (3) and (4). The token is not wasted on
a single yes/no.

## The traded cell is named NOW, not after

Traded portfolio = **N1 (nearest high) ∩ top-two quality buckets**, equal
weight, max 50 names. Naming it in advance is what stops the winning cell
being chosen from the grid after the fact. If a different cell wins, that
is a logged observation for a **future** pre-registration — never a
retrofitted claim about this one.

## Frozen gates

- **G1 direction** N1 CAGR − N5 CAGR ≥ **+3.0%/yr** (the George & Hwang
  effect exists in PIT US large caps)
- **G2 separator** within N1: top-quality CAGR − bottom-quality CAGR ≥
  **+3.0%/yr** (the Piotroski claim)
- **G3 baselines** traded cell − EW ≥ **+2.0%/yr** AND beats all 3 random twins
- **G4 money** QC alpha vs SPY **> 0**, net of costs

## Cost discipline (learned from the last run)

The previous run paid **$8,079 in fees on $100k** — 5.7% of ending equity —
across 6,808 orders, monthly rebalancing. Changes: **quarterly** rebalance,
50-name basket, universe refreshed quarterly. Target < 2,500 orders. This
is a cost fix, not a signal change; the gates are unaffected.

## Period

**2007-01-01 .. 2022-12-31.** 2023+ is this family's sealed one-shot
holdout and is NOT read.

## Failure branch (written before the verdict)

If G1 fails, momentum/anchoring is sealed at 1 failure and the 52-week-high
direction is not retried in any form for 12 months. If G1 passes but G4
fails, the effect exists but does not survive costs — that is recorded as
NOT INVESTABLE, and no cost-shaving revision is run. No re-parameterising
the quintile count, the lookback, or the F-Score leg set in either case.
