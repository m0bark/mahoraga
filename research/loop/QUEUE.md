# Edge-research loop — experiment queue

**LOOP RESTARTED 2026-08-27 (evening).** New standing constraints from the
broken-decile QC failure (3rd sealed reversal-family death):
1. Overreaction-reversal-family candidates may NOT be advanced to cards
   from local biased-cache scouting — QC point-in-time notebook
   confirmation required first (user-side). Local runs are idea triage only.
2. **SPY/VIX-level experiments are survivorship-FREE locally** (SPY is a
   real investable series) — that lane's local results carry full weight.
3. Cross-sectional loser-conditioned results get an automatic mental
   ~20pt/yr haircut (measured 3x) before anyone gets excited.

**STOP BAR (pre-registered):** a candidate passes scouting when: mean excess
vs SPY > 0 with t >= 2.5, n >= 200 events, survives 10 bps/side, and has a
mechanism story. Then it's written as a QC-ready hypothesis card and the
loop STOPS and presents it. Local results are SCOUTING TIER (survivorship-
biased 500-current-large-caps cache) — never verdicts.

## Queue

- [x] **iter1 — retest-confirmation entry** (from Dip Atlas: bottoms are
  zones visited twice; RSI fires ~31d early with 61% false bottoms).
  Point-in-time rules: low unbroken >=10d, bounce >=8%, retest within 5% of
  low that holds (close >= 1.03x low). vs S1 RSI-recross vs random-day
  baseline, same stop (0.95x low) and 120d horizon. -> retest_entry.py
- [x] **iter2 DEAD** (iter2_tax_loss.py, 20 years): December loser excess
  came out +1.1% (t=1.5) — WRONG SIGN vs the tax-loss-pressure prediction;
  January +1.8% (t=1.8, only 55% of years positive, outlier-driven);
  combined spread t=0.4. Early-Jan concentration mild (t=1.8). And since
  survivorship INFLATES loser returns, the true January effect is even
  weaker than measured — dead in large caps, matching the literature's
  post-1990s fade. No card.
- [x] **iter3 DEAD** (iter3_spy_regimes.py, survivorship-FREE lane):
  weekly SPY regime map (VIX bucket x drawdown state, 1078 weeks) — no
  cell significantly differs from unconditional +12.2%/yr (best t=1.2 on
  n=9). Fear-peaked dip entries: 7-9 events, direction positive, t<0.6 —
  hopelessly underpowered and no evidence. Market-level VIX/drawdown
  timing carries nothing detectable at weekly/monthly frequency.
- [x] **iter8 BELOW BAR** (iter8_tom_decompose.py, survivorship-free):
  turn-of-month decomposed — effect spread across days -4..+2 (strongest
  -4th day t=2.4, last day actually negative), positive in BOTH halves but
  each half individually insignificant (t=1.85 / t=0.91). TOM-only
  exposure: 7.5% CAGR at 33% exposure, maxDD -15.5%, CAGR/vol 0.71 vs
  0.58 buy-hold. Verdict: real-but-small flow effect, below the alpha
  bar; useful ONLY as a costless scheduling nudge (time flows you'd make
  anyway into the TOM window).
- **LOOP STOPPED (2nd run, 2026-08-27 late): terminal state = local free-
  price-data space exhaustively triaged.** Remaining queue items
  (iter4/5/6) are overreaction-reversal family — formally non-predictive
  under local scouting per the standing constraint; running them would be
  manufactured activity. Every forward path now requires: (a) QC research
  notebook — quality-conditioned tilt scout [user], (b) QC verdict tokens
  [user], (c) alt-data archive maturation [~month 12+], or (d) new data
  sources. The loop has no bar-clearing move available locally.
- [ ] **iter4 — dispersion-conditioned weekly reversal**: does the weekly
  loser bounce concentrate in high cross-sectional-dispersion weeks?
  (meta-labeling precursor for the reversal sleeve)
- [ ] **iter5 — retest + market-regime interaction** (only if iter1 shows
  life): systemic vs idio split of retest entries.
- [ ] **iter6 — skip-last-day reversal variant** (microstructure bounce vs
  true reversal decomposition).

**Amendment (2026-08-27):** the stop bar additionally requires BEATING the
in-run random/dumb baseline — a positive-t candidate that loses to random
timing is NOT useful (iter1 taught this).

## Log

- 2026-08-28 **forced-flows survey done** (5 parallel adversarial agents →
  research/forced_flows/SURVEY-2026-08-28.md). Index deletions NO-GO,
  CEF discounts NO-GO, Russell recon NO-GO, spin-offs MAYBE, **reverse-
  split cash-outs GO** (verified TTSH Dec-2025 completion). Scanners
  built: tenders/tender_scan.py + tenders/reverse_split_scan.py. Sleeve
  estimate $1-3k/yr on <$25k. Pre-registered go-live gate: 36-mo ledger
  backfill with >=8 investable events, >=85% completion, >=$150/event.
- 2026-08-28 **insider cluster HOLDOUT (2023→2026-08): FAILED.** Alpha
  −0.05, IR −0.275 on never-seen data (discovery window had +0.022/+0.19).
  Sealed: no real money; forced-information family shot #1 dead, family
  shelved. User called overfit before the run. Project state returns to
  terminal-local: no bar-clearing move without new data sources or
  alt-data maturation.
- 2026-08-28 **insider cluster QC run #2 (full window 2007-2022): ALIVE.**
  Alpha +0.022, IR +0.194, CAGR 10.36%, Sharpe 0.36, maxDD 64.6%, PSR
  0.07%, capacity ~$360k. Card sealed →
  cards/2026-08-28-insider-cluster-concentrated.md. Next gates: baseline
  verdict run → 2023+ holdout one-shot → 13-26wk paper. Honest read:
  beta-adjusted +2.2%/yr; SPY-plus-a-bit at 65% DD, not a money printer.
- 2026-08-28 **insider cluster QC run #1 (user-side): BOTH GATES PASS but
  truncated.** Concentrated 10-name config, 2007→~2021-03 (died at QC
  free-tier 10k-order cap; weekly re-trim churn — fixed, membership-only
  orders now). Alpha +0.024, IR +0.222, CAGR 12.0%, beta 1.15, Sharpe
  0.41, maxDD 64.9%, PSR 0.25%, capacity ~$190k. First family to survive
  a QC gate since project start. NOT sealed — full-window rerun needed,
  then card + baselines for a verdict run. 2023+ holdout untouched.
- 2026-08-28 **insider cluster-buy scout done** (insider/insider_clusters.py
  → insider/SCOUT_RESULTS.md). Forced-information family, shot #1. Buys:
  63d excess +3.84% (t=4.0), 126d +5.48% (t=4.2), n~550 — clears the bar
  numerically. Red flag: cluster SELLS also positive (+1.81%/126d, t=9.1)
  → part of the effect is activity-conditioning on the biased panel;
  buy-minus-sell spread ~+3.7%/126d is the cleaner read. Dip-conditioned →
  survivorship haircut partially applies; 4% coverage (large-cap panel,
  effect lives in small caps). NOT a verdict — advance requires QC
  point-in-time notebook confirmation (user-side).

- 2026-08-27 **iter1/1b done** (retest_entry.py). Retest-confirmation entry
  beats RSI-recross head-to-head (+1.8% vs -0.2% excess, t=+4.4 vs -0.7,
  matched stops — the atlas insight is real), BUT random-day entries inside
  the same episodes crush both (+6.6% excess, 100% of years positive).
  Interpretation: dip profits live in the recovery leg; bottom-proximity
  entries systematically locate themselves in the dangerous phase, and
  stops near a noisy low get wicked out (52% -> 37% stop rate just from
  moving the stop to entry-relative). Survivorship bias inflates all
  absolute numbers, especially random. NO candidate passes the bar.
  Follow-on queued as iter5 (regime split) and NEW iter7.
- [x] **iter7 done** (phase_decomposition.py): dip premium is FLAT across
  the lifecycle (+2.1-2.4% excess/120d every phase, t~6). No timing sweet
  spot exists; iter1's random +6.6% was partly stop-geometry artifact.
  The tradeable object is the always-invested broken-decile tilt.
- [x] **bar check done** (tilt_vs_random.py): broken-decile tilt +9.8%/yr
  excess (t=2.59, 248 months), beats 20/20 turnover-matched random twins
  (twins: -0.4%/yr avg). ALL FOUR GATES PASS.
- **LOOP STOPPED 2026-08-27**: candidate written as QC-ready card ->
  research/cards/2026-08-27-broken-decile-tilt.md. Next action is the
  user's: run the pre-registered QC test. Remaining queue (iter2/3/4/5/6)
  stays for a future /loop restart.
