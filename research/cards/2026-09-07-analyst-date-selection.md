# SEALED — analyst rating dates carry NEGATIVE information

**Date:** 2026-09-07
**Question:** If you buy on the day an analyst publishes a rating action, do you
do better than buying the same stock on a nearby day?
**Answer:** No. You do measurably WORSE. −0.67% to −1.55% over the next month.

## Data

11,570 dated rating events · 1,520 stocks · 2,247 analysts · 147 firms
Swept from `stockanalysis.com/stocks/<SYM>/ratings/` (not paywalled; the
`/analysts/<name>/` pages are, and yielded only 44 usable events).

    Maintains 7,482 · Reiterates 3,158 · Initiates 373 · Downgrades 287 · Upgrades 270

## Design

Self-matched. Each event compared against nearby entries into THE SAME STOCK:

    f[i]    = v[i+h]/v[i] - 1
    ctrl[i] = mean(f over i±W), EXCLUDING i itself
    edge[i] = f[i] - ctrl[i]

Same stock, same weeks, same sector, same regime — only the DAY differs. No
benchmark, so no benchmark can be wrong. This design exists specifically
because the previous version (`event_study.py`, retracted) drew its control
from 15 months while the events sat in a 5-week band, and reported a
sign-flipped −18.49% / t=−2.67 that was really "semis in May 2026."

Inference by analyst-block-shift randomization (2,000 shuffles), not iid t —
overlapping same-sector windows had a measured design effect of 5.7.

## Result

42 tests attempted → Bonferroni threshold p < 0.0012. **Four clear it. All four
are negative.**

| group | h | W | n | edge | perm p |
|---|---|---|---|---|---|
| ALL | 21 | 10 | 5,643 | **−0.67%** | 0.0005 |
| ALL | 21 | 21 | 5,626 | **−0.92%** | 0.0010 |
| ALL | 21 | 63 | 5,589 | **−1.55%** | 0.0010 |
| Maintains | 21 | 10 | 3,724 | **−0.68%** | 0.0005 |

Sign is stable across every W and grows monotonically more negative as the
comparison band widens.

## The placebo that makes it believable

Identical machinery, analyst dates replaced by RANDOM dates in the same stocks
with the same per-stock counts:

| W | real | placebo |
|---|---|---|
| 10 | −0.67% | **−0.01%** |
| 21 | −0.92% | **+0.19%** |
| 63 | −1.55% | **−0.01%** |

The pipeline returns zero on random dates. The negative is the analysts.

## What did NOT survive

- **Upgrades** (n=142, h=21): −1.76%, −1.23%, **+0.61%**, −0.86% across W.
  Sign flips → no stable effect. All p > 0.09.
- **Downgrades at h=63** (n=33): +9.27%, +8.52%, +8.69%, p = 0.047/0.120/0.188.
  Consistent sign and economically interesting as a contrarian signal, but
  n=33 and it does not clear multiplicity. NOT established.

## Reading

The drift happens before or at the announcement. By the time the action is
published on a public page, the move is in the price and you are buying after
the pop. The date is informative — it tells you it is a slightly bad day to buy.

This is not a shortable finding under the account's constraints (long spot
only), so it is not an inverted edge. It is a closed door.

## Status

The pre-registered gate ("≥40 upgrade events, ≥60 trading days, excess vs
sector ETF > 0 with t > 2") is now moot for its original purpose: the tape
carries 270 upgrades, and the self-matched test — a stricter control than the
sector ETF the gate specified — returns no stable upgrade effect.

**SEALED. Do not re-run this hypothesis without new data of a different kind
(intraday timestamps, or pre-publication rating feeds).**
