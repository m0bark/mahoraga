# Hypothesis: Panic Reversal (overreaction-reversal)

**mechanism_id:** `overreaction-reversal`
**Status:** RETIRED as a standalone strategy (2026-08-27) — failed the
pre-registered survivorship-free test. See "QuantConnect verdict" below.
Failure classification: WEAK_EXPECTANCY + REGIME_DEPENDENT.

## QuantConnect verdict (point-in-time data, 2007–2026, two runs)

- Run 1 (dollar-volume universe, no market gate): CAGR 5.0%, Sharpe 0.16,
  maxDD 66%, alpha −0.03. Run 2 (quality universe, market-stabilization
  gate, cooldowns): CAGR 1.6%, Sharpe −0.05, maxDD 48%, alpha −0.03,
  IR −0.58. Pre-registered bar was alpha > 0: FAILED both times.
- Per-trade expectancy stayed slightly positive in both runs (~+1%/trade,
  P/L ratio ~3, win rate ~27%) — the timing signal is real but tiny.
- **The yfinance prototype's +9%/trade was ~8 points survivorship bias.**
  That gap, now measured, is the single most valuable output of this project.
- Risk gates cut drawdown but not the conclusion: sitting out crashes and
  buying stabilizations does not out-earn simply holding the index.

Lesson for the Library: the panic-reversal mechanism works as a RELATIVE
signal (crashed stocks vs the market) but not as a standalone long book.
Successor hypothesis: weekly-loser cross-sectional reversal
(`research/weekly_reversal/`), the strongest honest statistic in the
Prometheus sweep (gross t=3.0). Its open question is costs, which the
QC port exists to answer.

---

## Economic mechanism (one sentence)

When a fundamentally intact company's price collapses fast, part of the selling
is non-informational (fear, margin calls, fund redemptions, stop cascades), so
price overshoots fair value downward and partially recovers once forced selling
exhausts.

Why it persists: forced sellers are constrained, not stupid — redemptions and
risk limits force sales regardless of price. Career risk keeps institutions
from catching knives. Both frictions are structural.

## Known failure mode (the thing that kills naive versions)

Most crashes are *correct repricing* — the business actually broke. Falling
knives on average underperform. The edge, if it exists, lives entirely in the
filter that separates:

- **hysteria crash** — price down big, business intact → buy candidate
- **fundamental crash** — price down big, estimates/earnings down comparably → avoid

v1 of this prototype is price/volume-only and CANNOT see fundamentals. Treat
v1 results as an upper bound on the crash-timing component only.

---

## Rules (v1)

### Setup (dislocation)
- Drawdown from rolling 252-day high ≥ 35%
- AND fast component: 15-day return ≤ −15% (panic, not slow bleed)
- Setup stays "armed" for 60 trading days after the last day it fires

### Entry (stabilization indicator — do not catch the knife mid-air)
- During an armed setup, RSI(14) has been < 30
- Enter next open when RSI crosses back above 30
- AND drawdown still ≥ 25% (haven't missed the move)

### Exits (first to trigger, executed next open)
1. **Recovery / resistance:** close ≥ 90% of pre-crash 252-day high
2. **Thesis break:** close < the crash low that formed before entry
   (market confirmed the crash was fundamental)
3. **Time stop:** 180 trading days in the trade

### Costs
- 10 bps per side (large-cap liquid universe assumption)

---

## Validation requirements (Sentinel-style)

- [ ] Per-trade expectancy net of costs, vs SPY over same window (excess)
- [ ] Year-by-year breakdown (regime dependence — this strategy should feast
      in 2008/2020-type regimes and starve elsewhere; confirm it isn't ONLY
      a bull-market-recovery artifact)
- [ ] Win rate AND tail: median vs mean (a few 2020 moonshots can hide a
      losing base rate)
- [ ] Sample size ≥ ~80 trades before taking any statistic seriously

## Known biases in v1 (be honest)

1. **Survivorship bias (severe for this strategy):** universe = today's
   mega/large caps. Companies that crashed and *died* (Lehman, Enron, FTX-adjacent,
   regional banks 2023 that failed) are absent; companies that crashed and
   recovered are present. This inflates results for buy-the-crash specifically.
2. **No point-in-time fundamentals:** free data cannot give as-of estimates,
   so the hysteria-vs-fundamentals filter is not implemented. v2 needs
   earnings-date proximity at minimum, real estimate data ideally.
3. **Resistance exit caps winners:** exiting at prior high truncates the right
   tail. Test trailing-stop variant before concluding anything.

## v2 — knife taxonomy (implemented in backtest.py)

Same entries as v1. Each trade is classified on two axes, computable from
price data alone:

- **systemic** — SPY itself is ≥12% below its own 252-day high at entry
  (market-wide panic) vs **idiosyncratic** (the stock crashed alone)
- **shock** — the crash window contains a ≥12% single-day drop or a ≥8%
  overnight gap down (discrete information arrival: earnings, fraud, FDA)
  vs **grind** (multi-week bleed: flow, sentiment, capitulation)

And three exit policies are compared on identical entries:

1. `resistance` — v1 rules (90% of pre-crash high / crash-low stop / 180d)
2. `trailing` — no target; stop = max(crash low, 80% of highest close since
   entry); 180d time stop
3. `hold180` — no rules at all, exit day 180 (isolates knife quality from
   exit machinery)

### Registered predictions (written before running v2)

- P1: systemic-grind is the best bucket; idiosyncratic-shock is the worst.
- P2: idiosyncratic-shock expectancy is ≤ 0 net — "the market was right."
- P3: trailing beats resistance on mean return (uncapped right tail) with a
  lower win rate.
- P4: v1's stop/target machinery beats hold180 on drawdown but not
  necessarily on mean.

### v2 verdict (377 trades, 2005–2026)

- P1 **falsified**: systemic-SHOCK was the best bucket (+49.6% mean, 79% win
  under hold180), not systemic-grind. Violent capitulation days during
  market-wide panics are margin-call flushes, not company news — the purest
  hysteria in the sample.
- P2 **falsified in-sample, but untrustworthy**: idio-shock earned +22.7%
  mean — HOWEVER this bucket has the worst survivorship bias (companies
  killed by their own shock are absent from today's index). Median was only
  +8.2% on n=48. Do not trust this bucket until tested point-in-time.
- P3 **confirmed**: trailing (+10.1%) beat resistance (+8.3%), same win rate.
- P4 **surprising**: hold180 dominated everything (+29.7% mean, 67.9% win).
  The thesis-break stop systematically sells the capitulation low. BUT in a
  survivor-only universe "never sell" wins by construction — the stop's
  payoff lives entirely on the dead companies not in the sample. Treat the
  stop as insurance whose premium is visible and whose payout is hidden.
- VIX >= 30 at entry: higher raw returns, LOWER excess vs SPY (the market
  itself rebounds from those moments). Adds little beyond the SPY-drawdown
  axis; they measure the same regime.

Net: the exploitable shape is SYSTEMIC panic + capitulation shock, entered
on stabilization, held patiently (months, not weeks), with a wide trailing
stop rather than a tight thesis-break stop. Point-in-time universe (v3) is
mandatory before believing any absolute number.

## v3 roadmap
- Point-in-time universe (historical index constituents) to kill bias #1
- True earnings-date filter (calendar data) to sharpen the shock axis
- Quality screen: leverage / profitability so distressed names are excluded
