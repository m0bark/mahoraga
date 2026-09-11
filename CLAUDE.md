# Working in this repo

Read this before proposing, testing or claiming anything. Every rule below was
paid for with a real error in this project. They are not style preferences.

## The user's constraints are non-negotiable

**Long spot equities only. Cash account. No options, futures, CFDs, margin or
shorts. Halal. About $25,000, split 80% ETFs and 20% stock picking.**

Consequences that are easy to forget:

- **T+1 settlement caps turnover at roughly 1x the account per day.** Each
  dollar is usable once per day. This is why scalping and order-flow strategies
  are structurally unavailable, not merely difficult: at $2,500 a clip a ~3bp
  round-trip spread needs ~43bp net per trade to clear $100/day, about ten times
  a professional intraday edge, ten times a day.
- **Pending limit orders reserve cash.** Arming 15 orders at 6% each locks 90%
  of the account before one fills. Size against settled cash, never against
  total portfolio value.
- **A bearish signal is not actionable.** Long-only means a finding that says
  "sector X will fall" is context, not a trade.
- Never give personalised investment advice or name "best plays". Report
  measurements. The user asks for picks sometimes; decline in one sentence and
  give the measurement instead.

## The bar is 14.78% a year

SPY total return 2013-01-02 to 2026-06-12 was **+537.8%, CAGR 14.78%**, verified
from `cache_long/px_close.csv` (dividend-adjusted, so a ratio of two closes is a
valid total return). Equal-weighting the same universe gave **14.82%**.

Do **not** quote the ~9-10% long-run historical average as the bar for this
sample. That error was made repeatedly in one session and understated every
shortfall by about six points a year. 2013-2026 was an exceptional stretch, and
anything tested only on this window is judged against an extraordinary
benchmark. Say so when reporting.

## Dead. Do not revive, re-tune or re-specify

Each has a sealed card in `research/cards/` with pre-registered gates and a
pre-agreed failure branch. Re-tuning a sealed failure breaks a promise made to
the user.

- **Overreaction-reversal family** — 5 sealed QuantConnect failures.
- **Panic-reversal formula** — failed its survivorship-free test twice.
- **3:1 risk:reward trigger** — dead three ways. −35.6% on QC with a stop,
  +147.9% without one (7.0%/yr vs the 14.78% bar), and a local capacity sweep
  beat it with plain buying in 0 of 11 configurations. Both legs are negative:
  the limit loses to buying the same names, and those names lose to the whole
  universe.
- **Buy zone / support anchors** — −0.23% to −1.97%/qtr.
- **Analyst rating dates** — −0.67% to −1.55%/month, p≈0.0005.
- **Chart levels as standalone signals** — `research/levels/RESULTS.md`.
- **The RATE score** — +0.10% top-minus-bottom, not even monotonic.
- **Buyback screen** — retested with splits divided out; cleaner and deader.
- **Insider cluster buys** — discovery passed, sealed holdout failed.

Still alive: **capitulation** (−40% drawdown AND 10%+ off the 60-day low;
+6.08% vs market, 72% win, n=433, never failed a control, `research/qc/
capitulation.py` written but **not yet run**), **quality alone** without a dip
filter, and the **odd-lot tender / reverse-split cash-out** lane, which is
untested and is the only idea here where being a small account is an advantage.

## Six rules for measuring anything

1. **Run a same-universe random-entry control first, locally, before spending a
   QuantConnect backtest.** It once predicted a QC verdict that a naive local
   backtest got backwards by 39 points.

2. **R-expectancy is not money.** One R is the entry-to-stop distance, a
   different fraction of price on every trade. A strategy measured at +0.212R
   per trade lost 35.6% of the account. Always also report **mean percent per
   trade** and run a **slot-limited portfolio simulation** with real cash
   accounting.

3. **Demeaning within a month does not remove beta.** Subtracting the universe
   mean removes the market's level, not your exposure to it. Every volatility
   measure tops a filter sweep here with holdout *t* near +9, then splits into
   +7.4% in up months and −7.4% in down months, correlation +0.63 with market
   direction. Re-run on a beta-neutralised target (regress on `beta252` within
   each month, keep the residual) before believing anything.

4. **Adjusted price LEVELS are lookahead.** The price files are split- and
   dividend-adjusted with no actions table, so the factor on a past date depends
   on corporate actions after it, and the error is largest for the names that
   rose most. Market cap from adjusted close times filed shares gave NVDA $195m
   on 2013-04-30 against a true ~$12bn, and manufactured a beautiful
   out-of-sample "low P/E wins" result that was entirely fake.
   **Banned: `price`, `avg_volume_20`, `dollar_vol_60`.** Immune: any return or
   ratio of two prices, and anything built only from SEC filings. Use
   `feat_val2.csv` (unadjusted) and never `feat_val.csv`.

5. **Exposure times factor return is not alpha.** A −9.35% spread with *t* of
   −21.61 and perfect monotonicity decomposed to 78% (rate beta spread) ×
   (realised bond move) plus (market beta spread) × (realised market move). If a
   test uses any forward-looking classification, decompose it the same way and
   report the residual.

6. **A control that cannot lose is worse than no control.** Two examples from
   one session: a comparison where both arms shared an exit price while one
   entered lower, which made the winner arithmetic and returned *t* = +100.9;
   and a simulator where the control arm's orders were scheduled to fill on a
   bar already processed, so it recorded zero trades. **A *t* above about 20 is
   not a strong result, it is a bug.** Go find it.

## Before claiming a finding

- Sealed holdout: fit on dates ≤ 2021-09-30, judge once on ≥ 2022-01-01, and
  **drop the three months between** because `fwd63` looks 63 trading days ahead.
- Overlapping 63-day windows on monthly dates inflate *t* by about √3. Divide by
  1.7.
- Searched K variants? The bar is |t| > √(2 ln K), not 1.96.
- Check monotonicity across all deciles. A big top-minus-bottom gap with no
  ordering between is the signature of noise.
- Shuffle the target within each month, re-run the whole pipeline 30 times, and
  compare against that distribution rather than against zero.
- Report the whole grid, not the best cell. One good cell among fifteen is what
  noise looks like.

## Data

Nothing under `cache_long/`, `cache/`, `sec_raw/`, `coverage/` or any `raw/` is
in git. It is 1.5 GB and fully regenerable. See README.md for the rebuild order.
Never commit it, and never commit `research/sheet/config.json`, which holds a
live Telegram token.

`cache_long/grid.csv` is the universe contract: 50,825 rows of date, symbol and
`fwd63`, 158 month-end dates, 465 symbols. Every feature block is row-aligned to
it exactly, in the same order. A feature on row (date, symbol) may use only
information dated on or before that date, and for fundamentals that means the
filing's **`filed`** date, not its period end.

## House style

- Module docstring says what it measures and what would have falsified it.
- Comments explain **why**, never what. Explain non-obvious accounting choices.
- Type annotations on signatures. PEP 8. Named constants, no bare magic numbers.
- No `print()` for data. Use the `say()` helper writing to a UTF-8 wrapped
  stdout; copy the pattern from `research/sheet/pit_quality.py`.
- **Never silently swallow an exception.** A value that cannot be computed is
  NaN and appears in a coverage report.
- **Log per-leg coverage on any multi-leg score.** A card in this repo graded a
  7-leg score whose 2 trend legs populated **zero** times out of 500, and the
  conclusion it reached was worthless. Coverage logging is what catches that.
- Bash heredocs mangle backslash-n in this environment. Write files with the
  Write tool.

## Reporting to the user

They want tested results, not frameworks, and they will call out hedging. Lead
with the number. Say plainly when something failed, including when the failure
is your own earlier claim. Correct your own errors in one sentence and move on.
Keep it short.
