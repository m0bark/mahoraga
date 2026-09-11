# S&P 500 Dashboard — Architecture

## The one decision everything else follows from

**Two refresh speeds, not one.**

Prices are one bulk request for all 503 names (~8 seconds). Fundamentals are
one request *per ticker* — 503 sequential calls, roughly 12 minutes. Macro
betas need 2 years of history and a regression per name.

Refreshing all of it hourly would mean 12,000 fundamental requests a day to
restate numbers that change **four times a year**. So:

| job | every | what it does | cost |
|---|---|---|---|
| `hourly` | 60 min | prices, technicals, support/resistance, SMA flags, alerts | ~15 sec |
| `daily` | 1×/day, after close | fundamentals, scores, macro betas, earnings dates | ~15 min |
| `alerts` | 5 min | check watchlist triggers, push Telegram | ~5 sec |

The hourly job never touches the slow data. It reads the daily job's cache.

## Data flow

```
                    ┌─────────────────┐
  Wikipedia ───────►│  sp500.csv      │  503 names + sector (weekly)
  federalreserve ──►│  fomc_dates.txt │  67 decision dates
                    └─────────────────┘
                             │
        ┌────────────────────┼────────────────────┐
        ▼                    ▼                    ▼
  ┌───────────┐      ┌──────────────┐     ┌──────────────┐
  │  DAILY    │      │   HOURLY     │     │   ALERTS     │
  │ yfinance  │      │  yfinance    │     │  reads       │
  │  .info    │      │  bulk prices │     │  prices.csv  │
  │  2y hist  │      │              │     │  + watchlist │
  └─────┬─────┘      └──────┬───────┘     └──────┬───────┘
        │                   │                    │
        ▼                   ▼                    ▼
  fundamentals.csv     technicals.csv       Telegram push
  macro_betas.csv      prices.csv
        │                   │
        └─────────┬─────────┘
                  ▼
        ┌──────────────────────┐
        │  sp500_dashboard.xlsx │  5 sheets, formatted
        │  + the same CSVs for  │
        │    Power Query        │
        └──────────────────────┘
```

**Why CSVs *and* xlsx:** if the workbook is open in Excel, a rewrite fails with
a file lock. The CSVs are always written. Point Excel's Power Query at them
with *Refresh every 60 minutes* and the workbook updates itself while open,
with no lock fight. The .xlsx is the standalone snapshot for when you just
want to open one file.

## Sheets

**1. Technicals** — price, day %, 52w high/low, % from high, SMA20/50/200,
ABOVE/BELOW 200-SMA, nearest support, nearest resistance, % to each, RSI(14),
ATR(14), avg volume, relative strength vs SPY.

*Support/resistance method:* find swing pivots (a local high with `n` lower
highs either side, and the mirror for lows) over 2 years, cluster levels within
1.5% of each other, weight by touch count and recency. Nearest cluster below
spot = support; nearest above = resistance. The touch count is shown, because
a level touched once is not a level.

**2. Fundamentals** — market cap, P/E, forward P/E, PEG, P/S, P/B, EV/EBITDA,
gross/operating/net margin, ROE, ROA, debt/equity, current ratio, revenue
growth, earnings growth, FCF yield, dividend yield, payout ratio.

*The RATE:* a 0–100 composite, sector-neutral (a utility is scored against
utilities, not against semis, or every REIT ranks bottom on P/E forever).
Four equally-weighted blocks, each a percentile rank within sector:
- **Value** — earnings yield, FCF yield, P/S, EV/EBITDA
- **Quality** — ROE, ROA, gross margin, net margin
- **Safety** — debt/equity, current ratio, earnings variability
- **Growth** — revenue growth, earnings growth

Every component column is shown next to the score. A score you cannot
decompose is a black box, and this project has already been burned by one.

**3. Macro** — for each stock, a *multivariate* regression of daily returns on
five factor returns at once:

    r_stock = α + β1·SPY + β2·TLT + β3·GLD + β4·OIL + β5·DXY + ε

Multivariate, not five separate regressions — oil and the dollar move together,
so univariate betas double-count. Columns: each β, the R², and residual vol.
Plus **FOMC-day behaviour**: mean move and mean |move| on the 67 real decision
dates versus all other days, and the ratio.

Reading it: β_TLT of −0.4 means when bonds rally 1%, this stock tends to fall
0.4% *after* removing what the market as a whole did.

**4. Summary** — one row per stock: price, 200-SMA flag, distance to support,
fundamental rate, beta, sector, halal flag, last analyst action. The sheet you
actually scan.

**5. Readme** — every column defined, plus the caveats, in the file itself.

## Alerts (Telegram)

`watchlist.csv`, which you edit by hand:

```
symbol,type,level,note
MSFT,price_below,360,"good buy zone"
NVDA,price_below,150,
AAPL,sma200_cross_down,,"trend break"
AMD,rsi_below,30,"oversold"
KO,near_support,2.0,"within 2% of support"
```

The alert daemon polls every 5 minutes during market hours, fires once per
trigger (a `fired` timestamp column prevents the same alert repeating every
5 minutes for a week), and re-arms only when the condition clears and returns.

**You must create the bot yourself** — message `@BotFather` on Telegram, send
`/newbot`, and it hands you a token. Then message your own bot once and I fetch
your chat id. Both go in `config.json`. I cannot create it for you.

## Suggestions you did not ask for

1. **Halal screen column.** Given the account is halal, every row gets a flag:
   sector exclusion (banks, insurers, alcohol, tobacco, gambling, defence,
   adult, conventional lenders) plus the standard financial ratios —
   debt/market-cap < 33%, interest income < 5% of revenue. Roughly 40% of the
   S&P fails, and right now you would be checking that by hand. **This is the
   one I would build first.**
2. **Join the analyst tape.** 11,567 dated rating events are already collected
   with 2,247 analysts. Add "last action / date / target / upside" to every
   row so the sheet shows if someone just upgraded it.
3. **Earnings proximity flag.** Days until next report. Buying three days
   before earnings is a different bet than buying after.
4. **Position sizer.** Given ATR and a fixed dollar risk, how many shares.
   With a <$25k cash account this decides more than the entry does.
5. **More alert types than price:** 200-SMA cross, RSI < 30, new 52-week low,
   within X% of support, analyst upgrade from the tape.
6. **"Why did it move" column.** Daily return minus what the macro betas
   predicted — separates a company-specific move from the market dragging it.

## Files

```
research/sheet/
  sp500.csv            503 names + sector          [done]
  fomc_dates.txt       67 decision dates           [done]
  config.json          telegram token, cadence, thresholds
  watchlist.csv        your price triggers
  fetch_daily.py       fundamentals + macro betas -> cache
  fetch_hourly.py      prices -> technicals
  compute.py           SMA / S&R / RSI / scores / betas / halal
  build_workbook.py    the .xlsx
  alerts.py            watchlist -> Telegram
  run.py              `--hourly | --daily | --alerts | --all`
  cache/*.csv          what Power Query points at
  sp500_dashboard.xlsx the workbook
```

Scheduling on Windows: three Task Scheduler entries calling
`run.py --hourly`, `--daily`, `--alerts`. I generate the commands.

## Honest limits

- yfinance fundamentals are as-reported and occasionally stale or wrong for a
  handful of names. Every number carries the timestamp it was fetched.
- Macro betas are backward-looking over 2 years and unstable for anything with
  a short history or a merger in the window. R² is shown; a beta with R² of
  0.05 is noise and should be read as such.
- Support/resistance is a descriptive statistic, not a prediction. Measured
  earlier in this project: a level bounce beats a coin flip by about 0.5
  percentage points.
