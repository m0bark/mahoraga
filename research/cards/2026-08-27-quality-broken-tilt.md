# Hypothesis card — Quality-Conditioned Broken Tilt

**card_id:** 2026-08-27-quality-broken-tilt
**mechanism family:** overreaction-reversal — **family shot #4 of 10.**
If this fails, the family should be retired: it would mean even the
theory-favored variant carries no honest alpha.
**evidential class:** DISCOVERY on honest data (the quality conditioning has
never been tested anywhere in this project — QC's point-in-time fundamentals
are the first data capable of testing it).

## Mechanism (one sentence)

Forced and fearful selling crushes solvent and insolvent companies alike,
but only the solvent ones systematically recover — so among deep-drawdown
large caps, profitability + positive free cash flow separates the recovery
premium from the graveyard, which is precisely the split survivorship bias
fakes in any local backtest.

## Spec (frozen)

- Universe: top 500 US by market cap, point-in-time, monthly; price > $5,
  dollar volume > $20M/day.
- Quality flag (from Morningstar PIT fundamentals at universe selection):
  P/E > 0 (profitable) AND FCF yield > 0 (cash-generating).
- Signal: month-end drawdown vs 252-day high. From the deepest-drawdown
  QUINTILE (~100 names): candidate = up to 50 deepest QUALITY names;
  junk track = up to 50 deepest NON-quality names.
- Tracks in the SAME run: candidate (traded, QC costs), junk broken decile
  (virtual), EW universe (virtual), 3 random-decile twins (virtual),
  SPY benchmark.
- Period: 2007-01-01 → 2022-12-31. 2023+ remains the family's reserved
  one-shot holdout.

## Pre-registered verdict (ALL required)

- **G1 (mechanism):** quality-broken CAGR − junk-broken CAGR ≥ **+3.0%/yr**
- **G2:** quality-broken CAGR − EW-universe CAGR ≥ **+2.0%/yr** and above
  every random twin
- **G3:** QC scoreboard Alpha vs SPY > 0 (traded portfolio, net of costs)

FAIL on any → sealed Failure; family retirement formally proposed.
One run. No mid-run changes.

## Status

- [x] Run executed on QC (2007–2022)
- [x] **VERDICT: FAILED (2026-08-27).** G3 missed: Alpha = **−0.001**
  (hairline, but frozen is frozen). CAGR 7.80%, beta 1.06, Sharpe 0.30,
  IR +0.02, maxDD 60.6%. G1/G2 virtual-track logs not yet transcribed —
  attach when available; they cannot change the verdict.
- **The informative part:** quality conditioning recovered +3.2%/yr over
  the unconditioned tilt (CAGR 4.57% → 7.80%; alpha −0.022 → −0.001).
  The MECHANISM is real — quality separates recoverers from corpses —
  but its entire premium only closes the gap back to market-equivalent.
  End state: matches SPY with 60% drawdowns. No reason to hold it over
  the index.
- **FAMILY RETIRED: overreaction-reversal, 4 sealed failures** (panic
  formula ×2, broken decile, quality-broken). Four generations converged
  monotonically to alpha ≈ 0 — the empirical signature of a correctly
  priced effect. No further family shots without fundamentally new data
  (matured alt-data archive) or a fundamentally different mechanism class.
