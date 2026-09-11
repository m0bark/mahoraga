# mahoraga

Research into whether a tradeable equity edge exists under hard constraints:
**long spot only, cash account, no options or futures or margin or shorts,
retail scale (~$25k).** Mostly a record of things that do not work, measured
carefully enough to be trusted.

The code is here. The data is not, because it is 1.5 GB and every byte of it is
regenerable by a script in this repo. See **Rebuilding the data** below.

## The bar

SPY total return 2013-01-02 to 2026-06-12 was **+537.8%, a CAGR of 14.78%**.
An equal-weight version of the same universe compounded at **14.82%**. That is
what anything here has to beat. It is not the ~9% long-run historical average,
and quoting that instead understates every shortfall by about six points a year.

## What has been measured

| Signal | Result |
|---|---|
| Capitulation: down 40%+ AND 10%+ off its 60-day low | +6.08% vs market, 72% win, n=433. **Never failed a control. Not yet run on QuantConnect.** |
| Quality alone, no dip filter | 12.09%/yr vs equal-weight 11.02%, beat 3 random twins |
| Momentum, point-in-time | +1.83%/qtr over random, below its own significance bar |
| 3:1 risk:reward trigger | **Dead.** −35.6% on QC with a stop; +147.9% without one, still 7.0%/yr vs 14.78% |
| 55 screener filters, each alone | **0 survive** beta-neutralisation plus a sealed holdout |
| Decision tree + gradient boosting over those filters | Holdout −0.63% on a beta-neutral target, worse than shuffled noise |
| Buy zone / support anchors | −0.23% to −1.97%/qtr |
| Analyst rating dates | −0.67% to −1.55%/month, p≈0.0005 |
| Insider cluster buys | Discovery passed, sealed holdout failed (alpha −0.05) |
| Overreaction-reversal family | Retired at 5 sealed QuantConnect failures |
| HYG/IEF leading semis | Peak correlation at lag 0, forward test inverted |
| VIX/16 as a daily-move predictor | Arithmetic right, ~22% overstated, no predictive edge |
| Odd-lot tender / reverse-split cash-out | **Untested.** The only lane where being small is an advantage |

## Five rules that cost real mistakes to learn

1. **A same-universe random-entry control before anything else.** It correctly
   predicted a QuantConnect verdict that a naive local backtest got backwards
   by 39 points.
2. **R-expectancy is not money.** One R is the entry-to-stop distance, which is
   a different fraction of price on every trade. A strategy measured at
   +0.212R per trade lost 35.6% of the account. Always also report mean percent
   and run a slot-limited portfolio simulation.
3. **Demeaning within a month does not remove beta.** In this sample every
   volatility measure tops a filter sweep with holdout *t* near +9, then splits
   into +7.4% in up months and −7.4% in down months. Re-run on a
   beta-neutralised target before believing anything.
4. **Adjusted price *levels* are lookahead.** The price files are split- and
   dividend-adjusted with no actions table, so market cap from adjusted close
   times filed shares gave NVDA $195m on 2013-04-30 against a true ~$12bn. The
   error is largest for the names that rose most. Returns and ratios of two
   prices are fine; levels are not.
5. **Exposure times factor return is not alpha.** A −9.35% spread with *t* of
   −21.61 and perfect monotonicity turned out to be 78% (rate beta spread) ×
   (realised bond move) plus (market beta spread) × (realised market move).

## Setup on a new machine

```bash
git clone https://github.com/m0bark/mahoraga.git
cd mahoraga
python -m venv .venv && .venv/Scripts/activate   # Windows
pip install pandas numpy requests yfinance openpyxl xlsxwriter scikit-learn flask
```

Then create your own credentials file. It is gitignored and must stay that way.

```bash
cp research/sheet/config.example.json research/sheet/config.json
```

Fill in a Telegram bot token from `@BotFather` (`/newbot`) and your numeric chat
id. `research/sheet/SETUP.md` has the desk UI, alert bot and scheduled-task
details.

## Rebuilding the data

Run these in order from the repo root. Each writes into a gitignored cache
directory and each is resumable, because the SEC and Yahoo both rate-limit.

```bash
python research/sheet/fetch.py          # prices, fundamentals, option chains
python research/sheet/fetch_raw_px.py   # UNADJUSTED closes + split history
python research/sheet/sec_pit.py        # SEC XBRL companyfacts -> PIT panel
python research/sheet/pit_quality.py --save   # nine-leg Piotroski F-Score
python research/sheet/grid.py           # the point-in-time universe grid
```

Then the feature blocks, which are row-aligned to `grid.csv` and can run in any
order:

```bash
python research/sheet/feat_tech.py      # 26 technical features
python research/sheet/feat_val2.py      # 11 valuation multiples, unadjusted px
python research/sheet/feat_qual.py      # 14 profitability / balance sheet
python research/sheet/feat_growth.py    # 9 growth rates
```

Expect the SEC pull to take a while on a cold cache: it is roughly 500 company
files fetched politely.

## Layout

```
research/sheet/        the dashboard, alert bot, desk UI and most of the studies
research/qc/           QuantConnect algorithms (paste as main.py)
research/cards/        sealed verdicts, one per tested hypothesis
research/tenders/      odd-lot and reverse-split cash-out scanners
research/insider/      Form 345 cluster-buy study
research/analysts/     analyst tracker and the date-selection verdict
src/mahoraga/          adaptation engine, unrelated to market data
```

`research/PROTOCOLS.md` is the practical distillation. `research/WORKFLOW.md`
describes the evidence ladder every hypothesis has to climb.

## Reading a card

Each file in `research/cards/` is a sealed verdict with its pre-registered
gates, the run id, and the result against each gate. A card marked **SEALED
FAILED** is not an invitation to re-tune the mechanism; the point of sealing it
is that the failure branch was agreed in advance.
