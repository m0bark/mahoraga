# region imports
from AlgorithmImports import *
from collections import deque
# endregion
#
# WEEKLY-LOSER REVERSAL — QuantConnect LEAN port
# From research/prometheus_sweep/sweep.py (Lehmann 1990): each week, buy the
# ~10 biggest 1-week losers among the largest US stocks, hold one week,
# rotate. Gross edge in the survivorship-biased prototype: +11.2%/yr, t=3.0
# (the only sweep hypothesis clearing the Bonferroni bar). The prototype's
# open question is COSTS: full weekly turnover of the sleeve. QC's realistic
# fee/slippage models answer it on point-in-time data.
#
# Pre-registered pass/fail (set before the first run):
#   PASS: alpha > 0 and information ratio > 0 vs SPY, net of QC costs.
#   FAIL: retire the mechanism as a standalone book, same as panic-reversal.
#
# Mechanics: signal on Friday close, fills Monday open (market-on-open).
# Mega-cap universe keeps spreads/slippage minimal — this is deliberate,
# the strategy only plausibly survives costs in the most liquid names.


class Closes:
    def __init__(self):
        self.window = deque(maxlen=6)  # 6 closes -> one 5-day return

    @property
    def ready(self) -> bool:
        return len(self.window) == 6

    @property
    def week_return(self) -> float:
        return self.window[-1] / self.window[0] - 1.0


class WeeklyLoserReversal(QCAlgorithm):

    UNIVERSE_SIZE = 100     # top mega caps by market cap (sweep universe)
    BASKET_SIZE = 10        # bottom decile of 100
    WEIGHT = 0.095          # 10 x 9.5% leaves cash margin for MOO drift

    def initialize(self):
        self.set_start_date(2007, 1, 1)
        self.set_end_date(2026, 8, 1)
        self.set_cash(100_000)

        self.universe_settings.resolution = Resolution.DAILY
        self.add_universe(self.select_universe)
        self._next_universe_refresh = datetime.min

        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol
        self.set_benchmark(self.spy)

        self.data: dict[Symbol, Closes] = {}
        self.basket: set[Symbol] = set()

    def select_universe(self, fundamental):
        if self.time < self._next_universe_refresh:
            return Universe.UNCHANGED
        first_of_month = datetime(self.time.year, self.time.month, 1)
        self._next_universe_refresh = (first_of_month + timedelta(days=32)).replace(day=1)
        liquid = [
            f for f in fundamental
            if f.has_fundamental_data
            and f.price > 5
            and f.dollar_volume > 50_000_000
        ]
        liquid.sort(key=lambda f: f.market_cap, reverse=True)
        return [f.symbol for f in liquid[: self.UNIVERSE_SIZE]]

    def on_securities_changed(self, changes):
        for security in changes.added_securities:
            symbol = security.symbol
            if symbol == self.spy or symbol in self.data:
                continue
            c = Closes()
            for bar in self.history[TradeBar](symbol, 10, Resolution.DAILY):
                c.window.append(bar.close)
            self.data[symbol] = c
        for security in changes.removed_securities:
            symbol = security.symbol
            if symbol in self.data and symbol not in self.basket:
                del self.data[symbol]

    def on_delistings(self, delistings):
        for symbol in delistings.keys():
            self.basket.discard(symbol)
            self.data.pop(symbol, None)

    def on_data(self, data: Slice):
        for symbol, c in self.data.items():
            if symbol in data.bars:
                c.window.append(data.bars[symbol].close)

        # Friday's daily bar: stamped Fri ~16:00 under QC's precise-end-time
        # default, or Sat 00:00 under the legacy midnight convention.
        # Market-on-open orders placed here fill at Monday's open.
        wd = self.time.weekday()
        if not (wd == 5 or (wd == 4 and self.time.hour >= 15)):
            return

        ranked = sorted(
            (
                (c.week_return, symbol)
                for symbol, c in self.data.items()
                if c.ready and self.securities[symbol].is_tradable
            ),
        )
        if len(ranked) < 60:
            return
        target = {symbol for _, symbol in ranked[: self.BASKET_SIZE]}

        for symbol in self.basket - target:
            qty = self.portfolio[symbol].quantity
            if qty != 0:
                self.market_on_open_order(symbol, -qty)
        for symbol in target - self.basket:
            price = self.securities[symbol].price
            if price <= 0:
                continue
            qty = int(self.portfolio.total_portfolio_value * self.WEIGHT / price)
            if qty > 0:
                self.market_on_open_order(symbol, qty)
        self.basket = target
