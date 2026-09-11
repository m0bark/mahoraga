# CARD — 52-week-high × F-Score — **SEALED FAILED**

- **Date:** 2026-08-31
- **Family:** momentum/anchoring — **shot #1/10**
- **Evidential class:** DISCOVERY
- **Pre-registration:** `research/momentum/PREREG-nearhigh-fscore.md`
- **Run:** LEAN v2.5.0.0.18041, id `a2bf81a39afb66792cb020088a21bcff`,
  2007-01-01..2022-12-31, 63 quarters, 4,101 orders
- **Holdout:** 2023+ NOT read.

## Verdict: FAILED on all four gates

| gate | requirement | result | |
|---|---|---|---|
| G1 direction | N1 − N5 ≥ +3.00%/yr | **−3.85%** | FAIL |
| G2 separator | N1Q1 − N1Q5 ≥ +3.00%/yr | **−1.44%** | FAIL |
| G3 baselines | traded − EW ≥ +2.00%, beat 3 twins | **−3.31%**, lost all 3 | FAIL |
| G4 money | alpha vs SPY > 0 | **−0.004** | FAIL |

Traded portfolio: CAGR 6.85% vs SPY 8.52%. Beta 0.832, max DD 52.4%
(vs SPY 55.2%), Sharpe 0.288, PSR 0.027%, fees $4,429.

**The grid** (gross CAGR; rows = nearness, N1 nearest high → N5 deepest dip):

| | all | Q1 best | Q2 | Q3 | Q4 | Q5 worst |
|---|---|---|---|---|---|---|
| N1 | +8.17% | +8.45% | +3.66% | +6.02% | +7.40% | +9.90% |
| N2 | +11.72% | +12.98% | +4.25% | +11.16% | +9.03% | +12.19% |
| N3 | +10.79% | +7.54% | +9.80% | +8.21% | +12.26% | +5.25% |
| N4 | +11.62% | +0.16%* | +13.00% | +13.79% | +7.32% | +10.04% |
| N5 | +12.02% | +0.00%* | +6.50% | +12.86% | +14.07% | +7.13% |

baselines: traded +7.83% · EW +11.14% · twins +9.51/+10.34/+12.70%

\* N5Q1 = exactly 0.00% and N4Q1 = 0.16% are **empty or near-empty
tracks**, not returns. High-quality names deep in drawdown are rare, so
those cells have almost no members. Do not read them.

## Finding 1 — George & Hwang did not appear, and reversed

Nearness to the 52-week high did not predict returns in PIT US large caps.
The gradient runs the other way and is near-monotonic:
N1 8.17% → N2 11.72% → N3 10.79% → N4 11.62% → N5 12.02%.

The traded cell (nearest-high × top quality) at **+7.83%** was beaten by
equal-weight (+11.14%) and by **all three random twins**. It was close to
the worst thing in the run.

## Finding 2 — G2 is NOT a clean test of Piotroski. Read the coverage line.

`F-Score-lite leg coverage: ['500/500','500/500','500/500','0/500','0/500','500/500','500/500']`

**Legs 4 and 5 populated zero times out of 500.** Those are the two
*improvement* legs — ROA improving vs 3-year, gross margin improving vs
3-year. The Morningstar `.three_years` fields did not resolve.

So the score that ran was a **5-leg static-quality score**, not a 7-leg
Piotroski-style one, and it was missing **both trend legs**. Piotroski's
F-Score is largely about improvement. G2's FAIL therefore refutes a
degraded static screen, **not** the Piotroski claim. That claim remains
untested here.

This is why the coverage log was built in. It worked.

## Finding 3 — the free replication DID NOT replicate. Correcting card 2026-08-30.

Card `2026-08-30-quality-dip200.md` concluded, in bold, that the drawdown
filter is an **anti-signal** costing −5.19%/yr. This run measures the
deep-dip quintile at **+12.02%/yr against the near-high quintile's
+8.17%** — dips ahead by +3.85%.

Both are PIT QC runs. They are not measuring the same thing:

| | card 2026-08-30 | this run |
|---|---|---|
| "dip" | ≥15% off high **AND** within −15%/+5% of the 200d SMA | deepest quintile by nearness only |
| comparison | quality names **not at that setup** | nearest-high quintile |
| quality | applied to both arms | bucketed separately |

So the narrow claim survives — *that specific setup* (deep drawdown sitting
on its 200-day, quality-filtered) underperformed its comparison group. The
**broad generalisation does not**: drawdown depth by itself was not an
anti-signal here; it was the better half of the sort.

**`research/WORKFLOW.md` Layer 3 is corrected accordingly.** The earlier
amendment overstated the evidence.

## Consequence (pre-registered failure branch)

- Momentum/anchoring sealed at **1 failure**. The 52-week-high direction is
  **not retried in any form for 12 months**.
- No cost-shaving revision, no re-parameterising quintile count, lookback,
  or leg set.
- The winning grid cells (N4Q3, N5Q4) are **observations only**. They are
  not a claim about this run and must not seed a strategy without their own
  pre-registration on fresh data.

## Keeper

Two independent PIT runs produced opposite-signed headlines about "dips"
because they defined the term differently. **A finding is only as portable
as its definition.** Card 2026-08-30's headline was written more broadly
than its own test supported, and it took a contradicting run to catch it.
Future cards state the exact condition in the headline, not a paraphrase.
