# Insider cluster-buy scout — results (2026-08-28)

Tier: SCOUTING (survivorship-biased 500-large-cap price panel; signal data
itself is complete point-in-time SEC Form 3/4/5, 2006-01 .. 2026-06,
3.47M transactions).

## Cluster buys (>=3 distinct insiders, >=$200k, 30d filing window)

13,562 events; only 562 on covered symbols (4% coverage — insider buying
skews small-cap, panel is large-cap).

| horizon | n | excess vs EW | t | win |
|---|---|---|---|---|
| 21d | 555 | +1.04% | 1.90 | 48% |
| 63d | 553 | +3.84% | 4.03 | 54% |
| 126d | 540 | +5.48% | 4.15 | 56% |

Officers/directors-only: nearly identical (63d +4.00% t=3.9).

## Control problem: cluster SELLS are also positive

12,401 covered sell events: 63d +0.97% (t=7.3), 126d +1.81% (t=9.1).
Sells should be ~0 or negative. Positive sell excess means part of the
"edge" is conditioning-on-insider-activity itself (activity clusters in
names that outperform this biased panel), not information.

**Cleaner read: buy-minus-sell spread ≈ +2.9%/63d, +3.7%/126d.** Still
meaningfully positive.

## Honest assessment

- Numerically clears the pre-registered scouting bar (t>=2.5, n>=200,
  survives 10bps trivially, mechanism story solid).
- BUT: insider buys are dip-conditioned (insiders buy after declines), so
  the measured ~20pt/yr loser-conditioning survivorship haircut partially
  applies. The 21d horizon is already weak (median negative) — the effect
  is slow (3-6 months), consistent with literature.
- 4% coverage means this scout barely samples the population where the
  literature says the effect lives (small caps).

## Next step (per PROTOCOLS/QUEUE standing constraints)

Local scouting cannot verdict this. Advance = QC point-in-time
confirmation: universe-honest event study in a QC research notebook
(user-side), then, if alive, a sealed hypothesis card + verdict run.
Family: forced-information, shot #1 (fresh family, 10 shots available).
