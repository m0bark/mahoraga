# Near-52w-high vs deep-dip — tested 2026-08-31 (before building anything)

Question: George & Hwang (JF 2004) say buy near the 52-week high; the user's
instinct and this project's PIT run disagree about dips. Which direction?

Monthly quintiles by nearness = price / 252-day high. 19,757 name-months,
126 names, 2011–2025, excess vs SPY.

## Step 1 — can the dataset answer? **No.**

| | deepest-dip | nearest-high |
|---|---|---|
| this local data, 12m excess | **+26.51%** | +5.97% |
| known PIT answer (QC) | 6.90%/yr **loses** | no-dip 12.09%/yr **wins** |

The local bias points at **dips**, and it is enormous: local shows dips
ahead by **+20.5 pts**, PIT shows them behind by **−5.2 pts**. That is a
**~26-point distortion** on this exact question — the same survivorship gap
this project has now measured five times.

## Step 2 — the ranking (reported, not believed)

| bucket | n | 3m | 6m | 12m |
|---|---|---|---|---|
| Q1 nearest high | 3,980 | +1.48% | +2.90% | +5.97% |
| Q2 | 3,915 | +1.68% | +3.05% | +7.23% |
| Q3 | 3,922 | +1.42% | +3.18% | +8.18% |
| Q4 | 3,915 | +2.10% | +4.36% | +11.55% |
| Q5 deepest dip | 4,025 | +2.84% | +8.18% | **+26.51%** |

Monotonic, t = **−9.37** at 12 months against George & Hwang.

**And it is worthless.** In a survivor-only universe the deep-dip bucket is
by construction "stocks that fell a long way *and came back*" — every one
that didn't is absent. A t of −9.37 riding a tailwind is weaker evidence
than a t of 2 fighting a headwind.

## What this test was for

It was the pre-build check, and it did its job: **don't build.** The plan
was near-high ranking + Piotroski F-Score. Both legs need point-in-time
data — F-Score needs 9 accounting variables as originally reported, and
yfinance serves current constituents with restatements. Neither can be
validated locally.

## Conclusion

**Local free data is exhausted for any drawdown- or valuation-conditioned
equity selection question.** Four attempts on 2026-08-30/31 — the dip
setup, the confirmation rule (t=+3.45, fake), the F-Score plan, and this —
were all structurally incapable of answering, for the same reason.

Remaining honest options:
1. **QC token on 52-week-high momentum as a NEW family.** It is the
   opposite mechanism to overreaction-reversal (anchoring/continuation, not
   reversal), so it is not a banned revision. Prior work here was a local
   yfinance sweep ("momentum dead in large caps post-2005") — scouting, not
   a sealed verdict. Put the F-Score / quality separator inside the same run.
2. **Go back to the contractual lane**, where the payoff does not depend on
   estimating a return distribution at all.

Script: `nearhigh_test.py`.
