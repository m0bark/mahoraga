# Hypothesis card — Insider Cluster Buys, concentrated

**card_id:** 2026-08-28-insider-cluster-concentrated
**mechanism family:** forced-information — **family shot #1 of 10.**
**evidential class:** DISCOVERY (spec frozen before first QC run; local scout
2026-08-28 was idea triage only).

## Mechanism (one sentence)

Insiders buying their own stock in clusters (>=3 distinct filers, >=$200k,
30 days) is costly, public, and informed — the market underreacts over the
following quarter, most strongly outside mega caps.

## Spec (as run)

- Events: SEC Form 4 open-market buys, filing-date point-in-time,
  2006-10..2022-12 (11,178 events embedded; 2023+ never given to the algo).
- Universe: any US stock with an event in the trailing 91 calendar days,
  price > $5, dollar volume > $2M/day; recency-ranked, cap 50.
- Portfolio: 10 freshest-cluster names, ~9.7% slots, membership-only
  trades, weekly rebalance at Monday open. No leverage, no shorts.
- Period: 2007-01-01 → 2022-12-31. **2023+ = reserved one-shot holdout.**

## Pre-registered read: ALIVE if alpha > 0 AND IR > 0 vs SPY net of costs

## Results

- **Run #1 (2026-08-28, truncated ~2021-03 at 10k-order cap):** alpha
  +0.024, IR +0.222, CAGR 12.0%, Sharpe 0.41, maxDD 64.9%.
- **Run #2 (2026-08-28, full window, 9,198 orders): ALIVE — both gates
  pass.** Alpha **+0.022**, IR **+0.194**, CAGR **10.36%**, beta 1.14,
  Sharpe 0.36, Sortino 0.40, maxDD **64.6%**, PSR 0.07%, fees $90k on
  $100k start, capacity ~$360k, win 51%, PLR 1.08.

## Honest read (written before any promotion decision)

- Beta-adjusted edge ≈ +2.2%/yr over 16 years. Positive, twice truncation-
  stable, and the first QC survivor in the project — but PSR ~0 means
  risk-adjusted it is NOT statistically better than SPY. This is
  SPY+~1.5%/yr CAGR at a 65% drawdown. Not a money printer.
- Concentration (10 names) contributes most of the risk; the scout's
  event-level t=4 suggests breadth (more names, more events) may raise
  IR at lower DD — that is a DESCENDANT hypothesis, not a revision.
- Capacity ~$360k: retail-only edge. Fine for this project's scale.

## Status / next gates (in order, none skipped)

- [ ] Verdict run with in-run baselines: 3 turnover-matched random twins +
      EW-universe track in the SAME backtest. Promote only if candidate
      beats all twins. (User elected to run the holdout FIRST, motivated
      by an overfit concern — recorded 2026-08-28 before the run.)
- [x] **HOLDOUT EXECUTED 2026-08-28 — VERDICT: FAILED.** Alpha **−0.05**,
      IR **−0.275** (both gates missed), CAGR 14.08%, beta 1.03, Sharpe
      0.31, maxDD 34.7%, PSR 5.5%, 1,686 orders. Made money absolutely
      but lost to SPY risk-adjusted on never-seen data. Per the sealed
      rule: **no real money, family shelved pending fundamentally new
      data.** The user predicted overfit before the run — correctly.
      Note (pre-registered): power was low (expected t≈0.4 even if real),
      so this is not decisive death of the mechanism — but it IS decisive
      for capital allocation. Shot consumed; no reruns.
- [ ] ~~**HOLDOUT — PRE-REGISTERED 2026-08-28, sealed before execution.**~~
      Window 2023-01-01 → 2026-08-21; events 2022-10..2026-06 (1,908,
      never previously used); spec byte-identical to the discovery runs.
      **PASS iff Alpha > 0 AND IR > 0 vs SPY net of costs. One run, no
      reruns, no mid-run changes.** This consumes the family's single
      holdout shot. Power note (honest): at discovery IR 0.19, expected
      holdout t ≈ 0.4 — a PASS is weak confirmation, a FAIL is not
      decisive death, but frozen is frozen: FAIL → no real money, family
      shelved pending new data. Code: research/insider/qc_paste_holdout/.
- [ ] 13–26 weeks paper via Sunday digest (operational gate only).
