# The dashboard and the studies

Two things live here: the live desk (workbook, alert bot, web UI) and most of
the measurement code. The data contracts below are what keep the studies
comparable to each other.

## The universe contract

`cache_long/grid.csv` defines the universe and nothing may change it.

| column | meaning |
|---|---|
| `date` | a month-end trading day, the decision date |
| `symbol` | eligible on that date under the point-in-time rules |
| `fwd63` | forward 63-trading-day total return, percent. **The target.** |

50,825 rows, 158 dates, 465 symbols, 2013-04-30 to 2026-05-29. Eligibility is
index membership **as of the date** plus top-350 dollar volume measured **three
years earlier**, so a name that was tiny then cannot be picked on the strength of
what it later became.

Every feature block is **row-aligned to `grid.csv` exactly, in the same order**.
A block that adds, drops or reorders rows silently corrupts every later join.
Assert the pair equality, as a set and in order, before writing.

Regenerate with `python grid.py`. It calls `optimize.prep()`, which is the slow
load-bearing step, which is why it runs once and everything reads the CSV.

## Feature blocks

| file | contents | notes |
|---|---|---|
| `feat_tech.csv` | 26 technical features | 100% coverage. Includes `beta252`. |
| `feat_val2.csv` | 11 valuation multiples | **Use this one.** Unadjusted prices. |
| `feat_val.csv` | the same 11 | **Contaminated. Do not use.** Kept only so `val_decile_check.py` can show the old-versus-new comparison. |
| `feat_qual.csv` | 14 profitability / balance sheet | Includes `fscore_pct`. |
| `feat_growth.csv` | 9 growth rates | `shares_change_1y` conflates splits with dilution; `cache_long/splits.csv` fixes it, see `buyback_retest.py`. |

**Three columns are banned from every model:** `price`, `avg_volume_20`,
`dollar_vol_60`. They are adjusted-price levels and therefore partial readouts of
the future. `tree_screen.py` has the blocklist and the measurement that condemned
them. The contamination is in the CSV, not only in the docstring, so a silent
join inherits it.

## Point-in-time fundamentals

`cache_long/pit_fundamentals.csv` carries 30,337 SEC filings with a **`filed`**
column. Align on `filed`, never on the period end: a quarter ending 2015-03-31
was often filed in 2015-05, and the market did not know it until then.
`pd.merge_asof(direction="backward")` per symbol is the clean way; a single
global `merge_asof` lets one symbol's filing leak onto another's row.

Two known defects, both documented rather than fixed:

- **Comparative-column staleness.** Balance-sheet fields can be substantially
  older than the filing date implies, and annual rows carry figures roughly three
  years behind the quarters sharing their label. This weakens the fundamental
  features and is fixable only by re-deriving the panel from `sec_raw/`.
- **Thin fields.** `gross_profit` 37.6%, `revenue` 56.1%, `debt_lt` 58.6%. Any
  feature built on those carries less weight than its *t*-statistic suggests.

The median filing is **58 days old** at the decision date. That single fact
explains why fundamentals add nothing to short-horizon entry timing: a two-month
-old balance sheet has nothing to say about the next two weeks of trading.

## The studies, and what each settled

- `tree_screen.py` — the 55-filter sweep, the beta-versus-edge check and the
  decision trees. Read it before adding any feature test; it has the holdout
  split, the embargo, the shuffled control and the blocklist.
- `rate_foresight.py` — the deliberate-lookahead trick. Grant perfect knowledge
  of a factor's future, and if the rule still cannot pay, the forecast is moot.
- `trigger_diagnose.py` / `trigger_capacity.py` — the post-mortem that retired the
  trigger, including the portfolio simulation that turns per-trade numbers into
  account numbers.
- `verify_turnover.py` — how to attack a survivor: within-sector, by year, on the
  best-measured rows, and with several factors neutralised at once.
- `pit_quality.py` — the nine-leg Piotroski score, and the per-leg coverage table
  that is mandatory on any multi-leg score here.

## The live desk

`config.json` holds a **live Telegram token** and is gitignored. Copy
`config.example.json` and fill your own. `SETUP.md` has the bot, the Flask desk
UI on port 8777, the launcher and the scheduled tasks.

`build_workbook.py` regenerates the Excel workbook; `encyclopedia.py` writes the
intro sheet whose verdict tags must match what the studies actually measured.
When a study overturns a claim, update `confirm.py` and `encyclopedia.py` in the
same change, because `confirm.py` is the tool the user reads before buying and a
stale claim there is an active hazard.

## House style reminders

`say()` writing to a UTF-8 wrapped stdout, never bare `print()` for data. NaN
rather than a swallowed exception. Coverage tables on anything with legs or
thin inputs. Named constants. Comments explain why.
