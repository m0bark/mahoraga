# region imports
from AlgorithmImports import *
from datetime import datetime, timedelta
# endregion
#
# INSIDER CLUSTER BUYS — concentrated (high-risk config) — QC confirmation run
# Family: forced-information, shot #1. From research/insider/SCOUT_RESULTS.md:
# local scout showed +3.8%/63d (t=4.0), +5.5%/126d (t=4.2) excess on ~550
# large-cap events, with a positive-sell-control red flag and only 4% event
# coverage. This run answers what the biased local panel cannot: point-in-time
# universe, delistings included, mid/small caps in, net of QC costs.
#
# HIGH-RISK CONFIG (deliberate): max 10 equal-weight positions, ~100%
# invested, universe reaches into mid/small caps ($2M/day liquidity floor).
# Expect 40-60% drawdowns if it works at all. No leverage, no shorts,
# cash account semantics.
#
# Pre-registered read (not a sealed verdict run — no card yet):
#   ALIVE:  alpha > 0 and IR > 0 vs SPY net of costs -> write the sealed
#           hypothesis card with in-run baselines for a verdict run.
#   DEAD:   family shot #1 recorded, mechanism re-examined before shot #2.
# Period ends 2022-12-31 — 2023+ is this family's reserved one-shot holdout.
#
# SETUP: add research/insider/cluster_buys.csv to the QC project files
# (drag-drop next to main.py). Signal dates are SEC FILING dates — public
# information; entries happen the following week's open at the earliest.


class InsiderClusterConcentrated(QCAlgorithm):

    MAX_POSITIONS = 10
    HOLD_CALENDAR_DAYS = 91      # ~63 trading days, the scout's strongest t
    MIN_PRICE = 5.0
    MIN_DOLLAR_VOLUME = 2_000_000
    UNIVERSE_CAP = 50            # candidates kept per refresh, recency-ranked

    def initialize(self):
        self.set_start_date(2007, 1, 1)
        self.set_end_date(2022, 12, 31)
        self.set_cash(100_000)

        self.events = self._load_events()     # ticker -> sorted filing dates
        self.log(f"loaded {sum(len(v) for v in self.events.values())} "
                 f"cluster-buy events on {len(self.events)} tickers")

        self.universe_settings.resolution = Resolution.DAILY
        self.add_universe(self.select_universe)
        self._next_universe_refresh = datetime.min

        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol
        self.set_benchmark(self.spy)

        self.candidates: list[Symbol] = []    # recency-ranked, set by universe
        self.basket: set[Symbol] = set()

        self.schedule.on(self.date_rules.week_start(self.spy),
                         self.time_rules.after_market_open(self.spy, 5),
                         self.rebalance)

    def _load_events(self) -> dict[str, list[datetime]]:
        events: dict[str, list[datetime]] = {}
        with open("cluster_buys.csv") as f:
            header = f.readline()
            for line in f:
                parts = line.strip().split(",")
                if len(parts) < 2:
                    continue
                ticker = parts[0].upper().strip()
                date = datetime.strptime(parts[1].split(" ")[0], "%Y-%m-%d")
                events.setdefault(ticker, []).append(date)
        for ticker in events:
            events[ticker].sort()
        return events

    def _latest_event(self, ticker: str) -> datetime | None:
        dates = self.events.get(ticker)
        if not dates:
            return None
        cutoff = self.time
        lo = self.time - timedelta(days=self.HOLD_CALENDAR_DAYS)
        latest = None
        for d in dates:                      # short lists; linear scan is fine
            if lo <= d <= cutoff:
                latest = d
        return latest

    def select_universe(self, fundamental):
        if self.time < self._next_universe_refresh:
            return Universe.UNCHANGED
        self._next_universe_refresh = self.time + timedelta(days=7)

        scored = []
        for f in fundamental:
            if f.price <= self.MIN_PRICE:
                continue
            if f.dollar_volume <= self.MIN_DOLLAR_VOLUME:
                continue
            latest = self._latest_event(f.symbol.value)
            if latest is None:
                continue
            scored.append((latest, f.symbol))
        scored.sort(reverse=True, key=lambda x: x[0])
        self.candidates = [s for _, s in scored[: self.UNIVERSE_CAP]]
        return self.candidates

    def on_delistings(self, delistings):
        for symbol in delistings.keys():
            self.basket.discard(symbol)

    def rebalance(self):
        target: set[Symbol] = set()
        for symbol in self.candidates:
            if len(target) == self.MAX_POSITIONS:
                break
            if symbol not in self.securities:
                continue
            sec = self.securities[symbol]
            if not sec.is_tradable or sec.price <= 0:
                continue
            if self._latest_event(symbol.value) is None:   # aged out
                continue
            target.add(symbol)

        for symbol in self.basket - target:
            self.liquidate(symbol)
        if not target:
            self.basket = set()
            return
        weight = 0.97 / len(target)          # cash margin for fill drift
        for symbol in target:
            self.set_holdings(symbol, weight)
        self.basket = target
