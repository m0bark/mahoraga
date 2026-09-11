# Do chart levels predict bounce vs break? — tested 2026-08-30

Prompted by a Telegram TA channel's calls on Kuwaiti stocks. Question:
when price reaches a "support" or "resistance", does anything about the
level predict whether it holds?

**Setup.** 60 liquid US large caps, 2006–2026, daily. Level = rolling
60-day extreme of High (resistance) / Low (support), shifted. Event =
close comes within 0.5% of the level after 5 days clearly away from it.
Resolution within 15 trading days. Baseline = identical barriers measured
from a *random* day with the level set to that day's close.

Caveats: current-member ticker list (survivorship-biased upward), adjusted
closes, no costs. Measures conditional probability, not a strategy.

## Result 1 — resistance carries ~no information

| | n | broke | fwd 10d mean | median |
|---|---|---|---|---|
| At a 60-day high | 2,849 | **75.4%** | +0.85% | +1.51% |
| Random day (baseline) | 19,967 | **74.9%** | +0.99% | +1.51% |

The level adds **0.5pp** over a day picked at random, and the forward
return at the level is *slightly worse* than the baseline.

## Result 2 — volume "confirmation" is inverted

| volume at the level | n | broke |
|---|---|---|
| < 0.8× avg | 678 | **77.4%** |
| 0.8–1.2× | 1,356 | 75.4% |
| 1.2–2.0× | 685 | 73.9% |
| > 2× avg | 130 | **73.8%** |

Monotonically *decreasing*. "It broke on high volume so it will continue"
is not merely unsupported here — it runs the wrong way.

## Result 3 — support: hit-rate edge that pays nothing

Barriers +5% bounce vs −2% break (asymmetric, so read against baseline only).

| | n | "bounced" | fwd 10d |
|---|---|---|---|
| At a 60-day low | 1,413 | 38.8% | +0.96% |
| Random day (baseline) | 19,112 | 34.9% | +0.99% |

+3.9pp on hit rate (≈3 SE) but **zero difference in forward return** — a
path artifact of short-term reversal, not money. Consistent with the dip
atlas finding that depth is memoryless.

## Result 4 — conditioning on *why* price is there

Splitting touches by whether a news-sized move (top 2% daily move for that
stock, within 3 days) brought price to the level:

| | n | outcome |
|---|---|---|
| Resistance, quiet drift | 2,785 | broke 75.7% |
| Resistance, news-sized move | 63 | broke 65.1% |
| Support, quiet drift | 1,348 | bounced 38.9% |
| Support, news-sized move | 65 | bounced 35.4% |

Underpowered (n≈63), no usable signal either way.

## Verdict

**Levels are descriptions of where price has been, not forecasts.** Nothing
tested here — the level itself, volume at the level, or the manner of
approach — separates a bounce from a break by enough to act on.

A price stops moving only when someone is *obligated* to trade there:
a tender offer at a fixed price, a cash-out merger, an index fund's
mandatory close, a buyback with a daily budget. "Support" and "resistance"
have no such agent behind them. This is the same conclusion the
forced-flows lane reached from the other direction, and it is why the
event sleeve is the live lane and the chart families are retired.

Scripts: `level_test.py`, `level_test2.py`, `sup_baseline.py`.
