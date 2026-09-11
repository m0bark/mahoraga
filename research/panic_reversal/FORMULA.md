# The Broken-Shit Formula (panic-reversal, v2-tested)

Every number below comes from the 377-trade backtest (2005–2026, US large
caps) in this folder — not from opinion. Caveats at the bottom are part of
the formula. Not investment advice; a research rule set.

---

## Step 0 — Universe (what you're allowed to touch)

Large, liquid, real companies only (S&P 100-type names). The whole edge is
"quality company, panicked holders." Small caps and story stocks are where
knives kill.

**Never buy** when the collapse is fraud/accounting/going-concern — that's
information, not emotion. (Enron-type knives are absent from our data
because they're dead. That absence IS the lesson.)

## Step 1 — Is it BROKEN? (both required)

- **B1. Deep:** price ≥ 35% below its 252-day high
- **B2. Fast:** down ≥ 15% in the last 15 trading days

Deep-but-slow = melting ice cube (worst tested bucket: 55% win, weakest
returns). Deep AND fast = panic.

## Step 2 — What KIND of knife? (decides size, or skip)

| Type | Definition | 180d hist. win | 180d hist. mean | Action |
|---|---|---|---|---|
| **Systemic-shock** | SPY ≥12% off its high AND a ≥12% down-day / ≥8% gap in the crash | 79% | +50% | Best. Full interest |
| Systemic-grind | SPY ≥12% off its high, no shock day | 67% | +19% | Good |
| Idio-shock | Market fine; single-day bomb (earnings etc.) | 60%* | +23%* | *Biased upward — half interest, skip if news smells fundamental |
| Idio-grind | Market fine; stock bleeding alone for weeks | 55% | +15% | Weakest. Usually skip |

The counterintuitive tested truth: **the scariest moment (market-wide panic
+ violent flush) is the best buy**, because that seller is a margin clerk,
not an analyst.

## Step 3 — WHEN to buy (never mid-fall)

- RSI(14) dropped below 30 during the crash, and
- **Trigger: RSI closes back above 30.** Buy the next open.

You will miss the exact bottom. That's the point — you're buying the first
evidence the forced selling exhausted.

## Step 4 — Exits (tested ranking)

1. **Hold with a wide trailing stop:** exit if price closes 20% below its
   highest close since your entry (but never wider than the crash low).
   Beat the tight-stop version (+10.1% vs +8.3% mean per trade).
2. **Thesis break:** a close below the crash low = the market voted
   "fundamental." Exit. (Costs ~21 pts of mean return in a survivor-only
   backtest — but it's the insurance that stops you riding a Lehman to 0.
   Keep it.)
3. **Patience:** winners took months. Median productive hold ≈ 2–6 months.
   Do not take +8% and leave — the whole edge lives in the +50–200% tail.

## Step 5 — Sizing reality (why this works as a portfolio, not a trade)

Even the deployed version wins only ~35–45% of the time. Expect the stop to
fire on 2 of every 3 knives at ≈ −11% each; the survivors pay for all of it.
So: **many small equal slices, never one big catch.** If a single position's
loss would change your behavior, it's too big.

---

## Run it live

```bash
uv run --python 3.12 screen.py
```

Screens the universe against Steps 1–3 today and prints: active BUY
triggers, knives still falling (wait), armed setups (watch), and the
current market regime (SPY drawdown / VIX → which row of the Step-2 table
you're in).

## Honesty box

- Backtest universe = today's survivors → all absolute numbers are upper
  bounds. The *ranking* of buckets is more trustworthy than the levels.
- One market (US mega caps), one era (2005–2026), ~377 trades.
- The formula's numbers (35/15/25/30/20%) were set a priori, not optimized —
  don't tune them to the backtest (see ARCHITECTURE.md: forbidden mutations).
