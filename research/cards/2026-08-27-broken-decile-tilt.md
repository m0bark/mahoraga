# Hypothesis card — Broken-Decile Tilt

**card_id:** 2026-08-27-broken-decile-tilt
**mechanism family:** overreaction-reversal
**evidential class:** REPLICATION of a locally-mined hypothesis (mined on the
survivorship-biased 500-current-large-caps cache; the QC run tests
survivorship + cost robustness, NOT discovery)
**family history (honesty):** this family has already consumed 2 sealed QC
verdicts (panic-formula entry strategy — FAIL twice, alpha −0.03) plus a
registered weekly-reversal test and an NN-ranker test. This card is roughly
shot #4–5 of a 10-shot family lifetime.

## Mechanism (one sentence)

Holders of stocks in deep drawdowns systematically overreact and are
partially forced out (redemptions, career risk, tax-loss selling), so a
diversified basket of the market's most-fallen liquid names carries a
persistent recovery premium relative to the average stock — harvested by
patient monthly ownership, not by timing entries.

## Convergent scouting evidence (all SCOUTING tier, survivorship-biased)

1. Monthly broken-decile portfolio: **+9.8%/yr excess vs EW universe,
   t=+2.59, 248 months**, positive 53% of months, worst month −14.7%.
2. Beats **20/20 turnover-matched random-decile twins** (twins cluster at
   −0.4%/yr excess — structure alone earns nothing; the tilt is the signal).
3. Dip-phase decomposition (4,700+ episodes): the premium is FLAT across
   the dip lifecycle (+2.1–2.4% per 120d in every phase, t≈6) — no timing
   content; the tilt is the whole effect. Entry signals (RSI, retest) add
   nothing beyond it and tight stops subtract.
4. Consistent with the 52-week-high inversion found in the anomaly sweep.

## Exact QC specification (Sentinel)

- Universe: top 500 US equities by market cap, point-in-time, monthly
  refresh; price > $5; dollar volume > $20M/day.
- Signal: at each month-end close, drawdown = close / 252-day-high − 1;
  hold the deepest decile (~50 names), equal weight; rebalance next open.
- Tracks inside the SAME backtest: candidate; EW-universe track; ≥5
  turnover-matched random-decile seeds; SPY as QC benchmark.
- Costs: QC default fee + slippage models.
- Period: 2007-01-01 → 2022-12-31. **2023+ is reserved as this family's
  one-shot holdout** and may be run once, only if this run passes.

## Pre-registered verdict (frozen before the run)

PASS requires ALL of:
1. net annualized excess vs the EW-universe track ≥ **+3.0%/yr**
   (bar set well below the scouted +9.8% because the panic-formula family
   measured ~8pts of survivorship inflation; if the true tilt can't clear
   +3% on honest data, it isn't worth capital);
2. candidate excess beats **every** random-seed track;
3. alpha vs SPY > 0.

FAIL on any miss → sealed Failure, feeds Mahoraga for ≤5 descendants.
No mid-run changes. One run. Result JSON archived to the Library.

## Known risks / expected weaknesses

- Survivorship inflation is the reason this card exists — expect a large
  haircut on honest data.
- High beta in crashes: the decile is what's already falling; expect
  concentrated drawdowns (worst scouting month −14.7%). REGIME_DEPENDENT
  weakness is anticipated.
- Turnover ~30–50%/month one-way → ~1–2%/yr drag at retail costs; fine.
- Capacity: no issue under $25k (liquid large caps, monthly cadence).

## Status

- [x] Pre-registration sealed; run executed by user on QC (2007–2022)
- [x] **VERDICT: FAILED (2026-08-27).** Gate 3 missed: Alpha vs SPY =
  **−0.022** (traded portfolio, net of costs). Traded CAGR 4.57% vs SPY
  ~8.5–9% over the period; beta 1.05; Sharpe 0.19; max drawdown 59.4%;
  IR −0.16. The tilt delivered market exposure plus nothing, with worse
  drawdowns. Gates 1–2 (virtual tracks) not yet transcribed from Logs —
  attach when available; they cannot change the verdict.
- **Survivorship gap, measured a third time:** local scouting CAGR +26.3%
  → honest traded CAGR +4.6%. The deep-drawdown decile is precisely where
  dead companies lived; the local excess was overwhelmingly bias.
- **Family note (overreaction-reversal):** now 3 sealed QC failures
  (panic-formula ×2, broken-decile ×1). Failure mode: DISCOVERY ARTIFACT
  (effect absent on honest data), not cost/regime fragility. Local
  biased-cache scouting is hereby considered NON-PREDICTIVE for this
  family; any future family shot must be scouted on point-in-time data
  (QC research notebooks) and should introduce genuinely new information
  (e.g., point-in-time quality/fundamentals conditioning), else the
  family retires.
