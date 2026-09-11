# All 4,703 stockanalysis.com analysts — verdict

## The funnel (the whole argument in one table)

| ratings (n) | analysts | min hit | max hit | SPREAD | spread luck predicts |
|---|---|---|---|---|---|
| under 10 | 40 | 0.0% | 100.0% | 100.0 | 110.2 |
| 10–25 | 26 | 0.0% | 100.0% | 100.0 | 49.3 |
| 25–60 | 13 | 38.5% | 100.0% | 61.5 | 31.5 |
| 60–200 | 14 | 26.8% | 100.0% | 73.2 | 18.7 |
| 200–600 | 16 | 31.9% | 90.9% | 59.0 | 10.5 |
| 600–1200 | 25 | 35.4% | 85.4% | 50.0 | 6.7 |
| over 1200 | 21 | 46.2% | 75.7% | 29.5 | 4.2 |

Observed spread collapses 100.0 -> 29.5 as sample grows. That is the signature
of noise. Page 5 (ranks 4001–4703) confirms it from the other side: 0.00% hit
rates and returns to -114.4%, again on 1–6 ratings. Both tails are tiny samples.
Skill does not produce a symmetric tail.

## Residual dispersion at large n is SECTOR, not skill

Among n>2000 analysts, spread is 38.7 points vs 3.9 predicted by luck — 10x.
But the split is sectoral, not personal:

| sector | analysts | median hit | median return |
|---|---|---|---|
| Financials | 38 | 75.6% | 19.8% |
| Materials | 24 | 72.0% | 38.8% |
| Energy | 21 | 70.1% | 26.0% |
| Industrials | 20 | 68.8% | 24.0% |
| Technology | 58 | 64.5% | 38.2% |
| Healthcare | 35 | 60.0% | 36.8% |

The three worst large-sample analysts on the entire list (Selvaraju 55.6%/3879,
Pantginis 55.9%/3375, McCarthy 32.6%/3308) are all biotech. The best
(Daryanani 71.3%/2744) is semis. You cannot buy the analyst without buying
the sector, and the sector is the variable that moved.

## The bar, and who clears it

Expected max of N=4703 draws is +3.54 SD. Exactly one analyst clears it:
**Michael Huttner** (Berenberg, 85.4% on 900 ratings, z=4.08). Disqualified in
practice: European coverage (not reachable in a US cash account at retail size)
and the LOWEST average return of anyone near the top of the hit-rate list.

## Two facts that kill the copy-the-leaderboard plan outright

1. corr(success rate, average return) = **-0.029**. Hit rate carries no
   information about money. The two columns you are ranking on are unrelated.
2. Against their OWN coverage universe, 6 of 7 audited analysts beat the base
   rate on hit rate — but **5 of 7 made less money than just holding their
   coverage list**. Papanastasiou: 82.8% vs his own stocks' 134.2%.

Honest base rate for this covered universe over the TipRanks window: ~60%
(57–63%). A 70% analyst is +10pp on a coin that already pays 60.

## What survives

The LEVEL of a rating is dead. The CHANGE is not (Chen-Zimmermann 1993–2024:
consensus-change +0.32%/mo, t=4.5 post-2001; +0.30%/mo alpha after momentum
controls). Historical rating dates are not published, so this cannot be
backtested — only recorded forward.

`research/analysts/tracker.py` does that. Pre-registered gate, frozen:

    >= 40 recorded upgrade events, >= 60 trading days elapsed,
    mean excess return vs the stock's SECTOR ETF > 0 with t > 2.
    Below that: no money.

Status: 1 snapshot (177 ratings, 7 analysts). Needs repeat runs.

---

# Addendum, 2026-09-06 — the leaderboard is not the only door

## Three corrections to the above

**1. Rating dates ARE published.** The tracker was built on "historical
rating dates are not published, so record forward." False. The analyst
table's last column is `Updated` and carries the action date
("Jun 29, 2026"). Every visible row is already a dated event.

**2. The first tracker ledger was 100% phantom.** stockanalysis.com masks
every ticker past ~row 9 with the literal string `XXXX` (124 of 177 rows).
The diff keyed on symbol, so all masked rows collapsed into one dict entry
and the rest refired as NEW on every run. 125 "events" in one day. Real
events between 2026-09-05 and 2026-09-06, masked rows removed: **0**.

**3. My first event study was sign-flipped, and I reported it.** It drew
its random-entry control from the full 15-month history while the events
sat in two narrow bands, so `edge` measured the calendar window rather
than the analyst. Headline was −18.49%, t=−2.67. Calendar-matched: **+3.3pp,
t≈1.0, permutation p≈0.20**. And 8 of 10 events came from one analyst, one
sector, 83% window overlap — design effect 5.7, n_eff 1.8, honest |t| 1.09.
Retracted in `event_study.py`; replaced by `revision_study.py`.

Neither direction survived. That dataset was uninformative, not negative.

## The actual unlock

`/analysts/<name>/` is paywalled. `/stocks/<SYM>/ratings/` is **not** —
measured 0 masked rows across 12 sample tickers — and carries the same
data on the opposite axis:

    Analyst | Firm | Rating | Action | Price Target | Upside | Date

8 rows per stock, so depth scales inversely with coverage (NVDA's 8 span
3 days; EXOD's span 158). One sweep of N stocks yields up to 8N dated,
named, free events; repeated sweeps accumulate whatever scrolls past the
8-row window.

`sweep_ratings.py` walks a dollar-volume-ranked US common-stock universe
(6,948 names from the NASDAQ symbol directory) and appends to a deduped
tape. `revision_study.py` scores it with a control that cannot repeat the
error above: **random entry into the same stock inside a ±W trading-day
band around the event**, so regime, sector and stock selection all
difference out and only the DATE is tested. Reported across W ∈ {10, 21,
42, 63} because W is not a parameter to pick after seeing the answer, with
analyst-block-shifted randomization for inference and a Bonferroni
threshold printed alongside.

The pre-registered gate is unchanged and now reachable: upgrades were
absent from the 7 paywalled analyst pages entirely; the per-stock tape
carries `Upgrade` / `Downgrade` / `Initiates` as first-class actions.
