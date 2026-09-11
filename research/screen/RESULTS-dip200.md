# Quality-dip / 200-day setup — backtest 2026-08-30

**Setup tested.** Hot-sector name (semis, software/AI, clean, EV, infra),
>=15% below its 252-day high, trading within −15%/+5% of its 200-day SMA.
Buy, hold 20/60/120/250 trading days. 78 names, 2013–2025, 1,684 entries,
max one entry per name per quarter.

**Controls.** (1) SPY over the identical window. (2) **Random entries in the
same universe**, 3× oversampled — the load-bearing one, because the ticker
list is today's survivors and drifts up regardless of signal. Both arms
carry the same bias, so signal − random is the honest excess.

**Not tested.** The quality overlay. yfinance serves only *current*
fundamentals; screening 2016 entries on 2026 financials is lookahead.
Price mechanics only.

## Result 1 — the setup adds nothing

| hold | signal | random | sig vs SPY | rnd vs SPY | **edge** |
|---|---|---|---|---|---|
| 20d | +2.66% | +2.05% | +1.30% | +0.98% | **+0.31%** |
| 60d | +7.49% | +7.20% | +3.72% | +3.82% | **−0.11%** |
| 120d | +16.44% | +15.16% | +9.32% | +8.45% | **+0.87%** |
| 250d | +39.59% | +38.03% | +24.41% | +23.51% | **+0.90%** |

+39.6% at 250 days looks superb until the control lands at +38.0%. **~98%
of the apparent return is the universe, not the signal.** Fourth clean
measurement of this project's survivorship gap, this time with the control
built into the same run.

## Result 2 — the panic gate is beta, not selection

Excess vs SPY, split by SPY drawdown at entry:

| regime | arm | n | 60d | 250d |
|---|---|---|---|---|
| SPY ≤ −12% | signal | 254 | +8.47% | +39.96% |
| SPY ≤ −12% | random | 520 | +8.09% | +25.48% |
| SPY −5..−12% | signal | 426 | +4.31% | +17.91% |
| SPY −5..−12% | random | 729 | +6.14% | +25.39% |
| SPY > −5% | signal | 1004 | +2.26% | +23.24% |
| SPY > −5% | random | 3803 | +2.80% | +22.88% |

Panic-only edge (signal − random): **60d +0.38%, t = +0.20**; 250d +14.47%,
**t = +1.57** — not significant, and the 254 panic entries cluster into
roughly four crash episodes, so effective n is ~4, not 254. Treat the 250d
number as unestablished, not promising.

The +8.5% 60-day outperformance after a crash is real but it is **high-beta
names rebounding harder than the index** — random entries got +8.09% of it.
That is beta, available without any screen, and it carries the matching
downside.

## Verdict

The screen is a way to *find* businesses worth owning. It is **not** an
entry timing edge, in any regime, at any horizon tested. Consistent with
the sealed QC verdict on the quality-broken tilt (alpha −0.001) and with
tonight's levels test.

Scripts: `backtest_dip200.py`, `regime_control.py`.
