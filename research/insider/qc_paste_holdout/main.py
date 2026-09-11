# region imports
from AlgorithmImports import *
from datetime import datetime, timedelta
import base64
import zlib

from insider_data_h import PART as _PH
# endregion
#
# INSIDER CLUSTER BUYS -- HOLDOUT RUN (2023-01-01 .. 2026-08-21)
# Family: forced-information. THE one-shot holdout: this window was never
# seen by the scout or either 2007-2022 run. Spec identical and frozen
# (card: 2026-08-28-insider-cluster-concentrated).
# Pre-registered: PASS iff Alpha > 0 AND Information Ratio > 0 vs SPY,
# net of costs. One run. No mid-run changes. No reruns.


class InsiderClusterHoldout(QCAlgorithm):

    MAX_POSITIONS = 10
    HOLD_CALENDAR_DAYS = 91
    MIN_PRICE = 5.0
    MIN_DOLLAR_VOLUME = 2_000_000
    UNIVERSE_CAP = 50

    def initialize(self):
        self.set_start_date(2023, 1, 1)
        self.set_end_date(2026, 8, 21)
        self.set_cash(100_000)

        self.events = self._load_events()
        self.log(f"loaded {sum(len(v) for v in self.events.values())} "
                 f"cluster-buy events on {len(self.events)} tickers")

        self.universe_settings.resolution = Resolution.DAILY
        self.add_universe(self.select_universe)
        self._next_universe_refresh = datetime.min

        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol
        self.set_benchmark(self.spy)

        self.candidates: list[Symbol] = []
        self.basket: set[Symbol] = set()

        self.schedule.on(self.date_rules.week_start(self.spy),
                         self.time_rules.after_market_open(self.spy, 5),
                         self.rebalance)

    def _load_events(self) -> dict[str, list[datetime]]:
        blob = zlib.decompress(base64.b64decode("".join(_PH))).decode()
        events: dict[str, list[datetime]] = {}
        for rec in blob.split(";"):
            ticker, dates = rec.split(":")
            events[ticker] = [datetime.strptime("20" + d, "%Y%m%d")
                              for d in dates.split(",")]
        return events

    def _latest_event(self, ticker: str):
        dates = self.events.get(ticker)
        if not dates:
            return None
        lo = self.time - timedelta(days=self.HOLD_CALENDAR_DAYS)
        latest = None
        for d in dates:
            if lo <= d <= self.time:
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
            if self._latest_event(symbol.value) is None:
                continue
            target.add(symbol)

        for symbol in self.basket - target:
            self.liquidate(symbol)
        slot = 0.97 / self.MAX_POSITIONS
        for symbol in target - self.basket:
            self.set_holdings(symbol, slot)
        self.basket = target
