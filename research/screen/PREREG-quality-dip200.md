# PRE-REGISTRATION — quality-dip / 200-day setup (QC Sentinel run)

**Written before the run. Sealed by push. No mid-run edits.**

## Family accounting (read this first)

**Family: overreaction-reversal. This would be shot #5.**

That family is marked **RETIRED** in this project at 4 sealed QC failures:

| # | card | verdict |
|---|---|---|
| 1–2 | panic-reversal | alpha ≈ −0.03, twice |
| 3 | broken-decile tilt | alpha −0.022 |
| 4 | quality-broken tilt | alpha −0.001 (near-miss; gate was > 0) |

The mechanism here — *buy a quality business that has fallen* — is the same
mechanism as #4, with the drawdown screen swapped for a drawdown + 200-day
SMA proximity screen and a sector restriction. It is a **revision card**,
not a new family, and it is the second revision off the #4 near-miss
(PLAN.md caps revisions at 2 per near-miss).

PLAN.md red-team finding #1 describes precisely this failure mode: *"four
individually-clean pre-registered revisions producing a laundered overfit
with an immaculate audit trail."* Running this is a decision to un-retire a
family. That decision belongs to the user, in writing, before the run.

**Evidential class: REVISION (not DISCOVERY).**

## What is already known, locally

Local test 2026-08-30 (`RESULTS-dip200.md`), 78 names, 1,684 entries,
2013–2025, with a same-universe random-entry control:

- Setup vs random entries in the same universe: **+0.31% / −0.11% /
  +0.87% / +0.90%** at 20/60/120/250 days. Nothing.
- Panic-regime edge over random: **60d +0.38%, t = 0.20**.
- ~98% of the raw +39.6% at 250d was the survivor-biased ticker list.

The price mechanics are therefore **already predicted to fail**. The only
untested component is the **quality overlay on point-in-time fundamentals**,
which local free data cannot test without lookahead.

## Hypothesis

Among point-in-time liquid large caps, names that are (a) ≥15% below their
252-day high, (b) within −15%/+5% of their 200-day SMA, and (c) pass a
point-in-time quality screen, outperform matched baskets that fail (c),
and outperform quality names not at the setup.

## Frozen gates — all four must pass

- **G1 (mechanism)** candidate CAGR − junk CAGR ≥ **+3.0%/yr**
  (does PIT quality separate recoverers from corpses?)
- **G2 (the dip must earn its place)** candidate CAGR − quality-not-at-setup
  CAGR ≥ **+2.0%/yr**. *The local test predicts this one fails.* It is the
  load-bearing gate: if quality alone does the work, the setup is a
  stock-finder, not a timing edge, and the card dies.
- **G3 (baselines)** candidate beats equal-weight universe by ≥ **+2.0%/yr**
  AND beats all 3 turnover-matched random twins.
- **G4 (money)** QC scoreboard Alpha vs SPY **> 0**, net of costs.

## Period

**2007-01-01 .. 2022-12-31.** 2023+ remains the family's sealed one-shot
holdout and is NOT read in this run.

## Failure branch (written before the verdict, per PLAN.md P2)

If any gate fails, the card is sealed FAILED, the overreaction-reversal
family returns to RETIRED with 5 sealed failures, and **no further revision
of this mechanism is run.** No re-parameterisation of the drawdown
threshold, the SMA window, the sector list, or the quality definition.
