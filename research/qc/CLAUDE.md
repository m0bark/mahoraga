# QuantConnect algorithms

Files here are pasted into QuantConnect as `main.py`. Each trap below cost at
least one wasted backtest, and the free tier allows 99 of them.

## Hard limits

- **32 KB per file.** Check before handing one over.
- **10 KB of logs per backtest.** Everything routine must be silent or the
  `OnEndOfAlgorithm` summary gets truncated and the run is unreadable. One run
  was cut off at 2013-03 because rejected-order warnings filled the quota.
- **Pure ASCII.** A zero-width space (U+200B) once broke a paste. Assert
  `s.isascii()` before delivering.

## The MarketOnOpen timing trap

On daily resolution LEAN converts a market order sent during the session into a
**MarketOnOpen** order, which is rejected outside **04:00-09:28** local.

```
BrokerageModel declared unable to submit order: [16]
  Warning - Code: NotSupported - MarketOnOpen submission time is invalid.
  Valid local times are 04:00-09:28.
```

A `Manage()` scheduled at `BeforeMarketClose(spy, 10)` = 15:50 had **every stop
and every target rejected** for a whole 13-year backtest. The strategy looked
like it had no exits because it had none.

Fix one, preferred: place exits as **resting orders the moment the entry fills**,
inside `OnOrderEvent`. A `StopMarketOrder` and a `LimitOrder` have no submission
window problem, and it is how you would really trade it. LEAN has no native OCO,
so cancel the sibling yourself when one fills.

Fix two, for time exits that must be market orders: schedule at
`TimeRules.BeforeMarketOpen(self.spy, 30)` = 09:00, inside the valid window.
`AfterMarketOpen(spy, 30)` = 10:00 works for `SetHoldings` but do not rely on it
for a bare market order.

## Cash accounts

`SetBrokerageModel(..., AccountType.Cash)` cannot borrow, and these follow:

- **Ten `SetHoldings(sym, 0.10)` calls demand 100%** and most get rejected. Use
  **one batched** `SetHoldings(targets)` with a list of `PortfolioTarget`: LEAN
  orders sells before buys so freed cash is available in the same pass.
- **Never `Liquidate(sym)` in a loop and then `SetHoldings` separately.** The
  sale proceeds are unsettled, so the buys that follow are refused for
  insufficient buying power. Route exits through the same batched call as
  `PortfolioTarget(sym, 0)`.
- **Target about 90-92%, not 100%.** Set
  `Settings.FreePortfolioValuePercentage = 0.05`.
- **Size against `float(self.Portfolio.Cash)`, not `TotalPortfolioValue`**, and
  cap pending orders separately from positions, because a resting limit reserves
  cash before it fills.

## Indicators do not warm up by default

`self.ATR(...)` never reaches `IsReady` unless
`Settings.AutomaticIndicatorWarmUp` is true, which it is not. Either set it or
compute the indicator from the `History` frame, which is what the algorithms
here do.

## Vendor field names

LEAN calls it **`OperationRatios.OperationMargin`**, not `OperatingMargin`. The
wrong name raises `AttributeError`, gets caught, and the leg logs "unresolved"
**1,073,217 times out of 1,073,217** — a silent 0% that only the per-leg
coverage log caught.

Two rules from that: try a **tuple of candidate field names** so a rename
degrades to the next option rather than to zero, and **log per-leg coverage**.
Note that this vendor represents "absent" as exactly `0.0` for most ratios, so
treat a hard zero as unresolved rather than as a real value, and report how
often that happens.

`.ThreeYears` fields do not resolve. A card in this repo graded a 7-leg quality
score whose two improvement legs populated zero times because of this, and the
FAIL it recorded refuted a degraded screen rather than the actual claim.

## Guard every order

```python
sec = self.Securities.get(sym)
if sec is None or not sec.HasData or not sec.IsTradable:
    continue
```

Newly added universe members get ordered before their first bar otherwise.

## Limit orders never expire

LEAN limits default to `GoodTilCanceled`. An unfilled order rests for months and
eventually fills at a price the setup no longer justifies. Track the bar it was
armed on and cancel it yourself.

## Virtual portfolios need real cash accounting

An earlier algorithm ranked five entry modes using virtual books that were never
debited. It measured **fill rate, not entry timing**. If you simulate arms
inside one backtest, debit and credit them properly or do not report them.

## What to log, and how to read it

Log the benchmark comparison explicitly, because the headline return is mostly
beta. SPY returned **14.78%/yr** over 2013-2026; do not let a 7%/yr result read
as a success. If idle capital is parked in SPY, log the **average share of the
book actually in the strategy's names**, because a 92%-SPY book returns what SPY
returns whatever the signal does. And where the local claim was "X% versus
market", measure it **per trade against SPY over the same holding window**, not
as a portfolio total.

## Current state

- `capitulation.py` — the strongest local signal, **written and never run.** Run
  this before anything else here.
- `trigger_quality.py` — kept for its plumbing and its fundamental gate. Its
  docstring records why the mechanic is retired. Do not spend a backtest on it.
- `trigger.py`, `momentum_entry.py`, `momentum_failsafe.py` — superseded, kept
  for the fixes embedded in them.
