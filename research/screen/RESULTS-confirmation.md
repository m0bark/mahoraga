# "Wait for a positive reaction on the dip" — tested 2026-08-31

User's proposal: mark dips in good companies, buy only once the stock
shows a positive reaction (confirmation), sell when valuation is at a
premium. This tests the **entry** half.

Arms, all inside a >=15% drawdown, 126 names, 2011–2026, excess vs SPY:

| arm | n | 60d | 120d | 250d | vs random | t |
|---|---|---|---|---|---|---|
| A raw_dip (buy cold) | 2,071 | +2.25% | +5.70% | +12.53% | −1.74% | −1.03 |
| B react_sma (close back above 20d SMA) | 1,881 | +2.90% | +5.77% | +18.35% | +4.08% | +1.87 |
| **C react_low (+10% off the 20d low)** | 1,704 | +3.38% | +8.27% | **+24.31%** | **+10.05%** | **+3.45** |
| D no_dip | 4,005 | +1.61% | +3.49% | +8.70% | −5.57% | −5.04 |
| R random | 7,560 | +2.35% | +5.41% | +14.26% | — | — |

Confirmation beat buying the dip cold by **+11.79% at 250d, t = +3.71**,
and beat random entries by **+10.05%, t = +3.45**.

## Why this result is not real

The same dataset answers the *base* question backwards:

| | dip | no-dip | winner |
|---|---|---|---|
| this local test | +12.53% | +8.70% | **dip** |
| QC, point-in-time, survivorship-free | +6.90%/yr | +12.09%/yr | **no-dip** |

Local says dips beat quality-not-dipped. The PIT run says the opposite,
by 5.19 pts/yr. And `D no_dip` here loses to random at **t = −5.04**,
while in the PIT run it *beat* equal-weight and all three random twins.

**Both directions of the base question are inverted in this dataset.** Any
t-statistic computed inside it is measuring the universe, not the rule.

**Mechanism.** `react_low` requires the stock to have already bounced +10%
off its low. In a survivor-only universe, every dip that kept falling into
delisting is missing. Conditioning on "it bounced" conditions on survival a
second time. That is the precise structure that manufactures a large,
significant-looking, fake edge — and it produced t = +3.45 here.

## Verdict

**Not established.** The confirmation rule is untestable with free local
data, for the same reason the underlying dip question was. It would need a
PIT run to mean anything — and per the sealed failure branch of
`2026-08-30-quality-dip200.md`, the overreaction-reversal family is retired
at 5 and no further revisions of this mechanism are run. This would be #6.

## Keeper

A high t-statistic is not evidence when the dataset gets the base rate
backwards. **Always run the sanity check: does this data reproduce a
result you already know the survivorship-free answer to?** If not, nothing
computed in it counts.
