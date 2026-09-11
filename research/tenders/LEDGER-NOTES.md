# Reverse-split cash-out ledger — build notes (2026-08-30)

Stage 1+2 of the pre-registered go-live gate from
[../forced_flows/SURVEY-2026-08-28.md](../forced_flows/SURVEY-2026-08-28.md).
Gate: >=8 investable events / 36mo, >=85% completion, >=$150 avg net at
post-vote entry.

## What was run

`build_ledger.py` — EDGAR full-text search, SC 13E3 + "reverse stock split",
2023-09-01..2026-08-30. **109 filings → 24 distinct issuers** (~8/yr).
Output: `ledger_stage1.csv`.

`build_ledger2.py` — pulls each issuer's proxy and machine-extracts the
cash-out price, share threshold, split ratio range, meeting date,
record-holder trap flag. **15/24 terms extracted on the first pass.**
Output: `ledger_stage2.csv`.

## The blocker, and the fix

**Blocker:** these issuers go private and delist. yfinance returns nothing
for 11 of the 24 (PMD, VCSA, NEUE, LFLY, CLSH, HOFV, KORE, STCN, ICLK,
LSBCF ...). Stooq's free CSV endpoint is now behind a JS bot wall (checked
2026-08-30, returns the challenge page for every symbol including AAPL).
So the 36-month backfill cannot be built from either free price vendor.

**Fix:** don't use a price vendor. Reg M-A **Item 1002(c)–(d)** obliges a
13e-3 filer to disclose, inside the proxy, the cash-out price, the share
threshold, and the stock's quarterly high/low market prices for the prior
two years. Everything the ledger needs is in the filing.

This makes the ledger **point-in-time and survivorship-free by
construction** — the property every price-based lane in this project had
to pay for or fake. It is also the reason this lane can be validated
without QuantConnect: the payoff is contractual, not statistical.

## Validation

TTSH (the survey's verified example) extracts exactly right:
cash payment **$6.60**, Minimum Number **2,000–4,000** shares, ratio
1:2,000–1:4,000, special meeting 2025-12-03. Matches the hand-read deal.

## Count so far

Of the 15 with extracted terms, **~9 carry a share threshold** — the
signature of an odd-lot cash-out rather than a straight going-private
merger:

| issuer | cash | threshold |
|---|---|---|
| SFES | $1.65 | 100 |
| MYMETICS | — | 2,000 |
| Ashford | $5.00 | 10,000 |
| PMD | $2.35 | 4,000–6,000 |
| TTSH | $6.60 | 2,000–4,000 |
| MFON | $0.29 | 25,000 |
| RDGA | $0.02 | 10,000 |
| 5&2 Studios | $3.75 | 173,750 |
| CLSH | — | 4,000,000 |

≈3/yr, consistent with the survey's 3–5 estimate. The no-threshold names
(Eargo, Via, Vacasa, NeueHealth, Leafly, HOFV, Anebulo, KORE) look like
going-private mergers, not the retail play — needs confirming per deal.

## Remaining to close the gate

1. Recover the 9 misses — most are "no proxy after 13E3" because the proxy
   preceded the 13E3; widen the form/date window both directions.
2. Extract the Item 1002(c) quarterly high/low price table per deal, plus
   the effective date, to compute post-vote entry economics per event.
3. Screen: record-holder-only treatment, sector, and whether the stock
   actually traded below the threshold-minimum price after the vote.
4. Then score the three gate numbers. Only then does one live paper event
   (including the DRS test) get run.

Nothing here is a prediction. The whole lane rests on a contract, which is
why it survived when the chart families didn't.
