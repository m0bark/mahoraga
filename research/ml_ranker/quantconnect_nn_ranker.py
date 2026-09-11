# region imports
from AlgorithmImports import *
from collections import deque
import numpy as np
from sklearn.neural_network import MLPRegressor
from sklearn.preprocessing import StandardScaler
# endregion
#
# NEURAL-NET WEEKLY RANKER — trains INSIDE the backtest (walk-forward by
# construction: the engine streams data chronologically, so the model can
# never see the future — no split logic to audit, no trust required).
#
# Every Friday: compute cross-sectional features for ~500 point-in-time
# large caps, label LAST week's feature rows with realized returns, and
# (once trained) go long the 20 highest-predicted names at Monday's open.
# The MLP retrains every 13 weeks on everything accumulated so far.
#
# Pre-registered comparison: run quantconnect_weekly_reversal.py (the dumb
# one-feature baseline) on the same dates. The NN earns attention ONLY if
# it beats the baseline AND SPY on alpha/IR — otherwise the verdict is that
# the network adds nothing beyond the reversal effect it re-learns.
#
# Expect no trades for roughly the first 2 years (data accumulation before
# the first training pass) — that cash drag is part of the honest result.

STOCK_FEATURES = 10   # rev_1w rev_2w mom_4w mom_12w mom_26w mom_52w vol_12w dd_52w rsi vol_ratio
MARKET_FEATURES = 3   # spy_1w spy_4w spy_dd


class Roll:
    """Per-symbol daily state -> weekly feature vector."""

    def __init__(self):
        self.closes = deque(maxlen=300)
        self.vols = deque(maxlen=130)
        self.avg_gain = None
        self.avg_loss = None
        self.rsi = 50.0
        self._seed = deque(maxlen=15)

    def update(self, close: float, volume: float) -> None:
        if self.closes:
            ret = close / self.closes[-1] - 1.0
            gain, loss = max(ret, 0.0), max(-ret, 0.0)
            if self.avg_gain is None:
                self._seed.append((gain, loss))
                if len(self._seed) == 14:
                    self.avg_gain = sum(g for g, _ in self._seed) / 14.0
                    self.avg_loss = sum(l for _, l in self._seed) / 14.0
            else:
                self.avg_gain = (self.avg_gain * 13 + gain) / 14.0
                self.avg_loss = (self.avg_loss * 13 + loss) / 14.0
                self.rsi = 100.0 if self.avg_loss == 0 else \
                    100.0 - 100.0 / (1.0 + self.avg_gain / self.avg_loss)
        self.closes.append(close)
        self.vols.append(volume)

    @property
    def ready(self) -> bool:
        return len(self.closes) >= 252 and len(self.vols) >= 60

    def features(self) -> list[float]:
        c = self.closes
        v = self.vols
        rets = np.diff(np.array(list(c)[-61:])) / np.array(list(c)[-61:-1])
        return [
            c[-1] / c[-6] - 1.0,                       # rev_1w
            c[-1] / c[-11] - 1.0,                      # rev_2w
            c[-1] / c[-21] - 1.0,                      # mom_4w
            c[-1] / c[-61] - 1.0,                      # mom_12w
            c[-1] / c[-131] - 1.0,                     # mom_26w
            c[-21] / c[-252] - 1.0,                    # mom_52w (skip last month)
            float(np.std(rets)),                       # vol_12w
            c[-1] / max(c) - 1.0,                      # dd_52w
            self.rsi,                                  # rsi
            float(np.mean(list(v)[-5:]) / np.mean(v)),  # vol_ratio
        ]


def rank_cols(x: np.ndarray) -> np.ndarray:
    out = np.empty_like(x)
    n = x.shape[0]
    for j in range(x.shape[1]):
        out[:, j] = np.argsort(np.argsort(x[:, j])) / max(n - 1, 1)
    return out


class NeuralNetWeeklyRanker(QCAlgorithm):

    UNIVERSE_SIZE = 500
    BASKET_SIZE = 20
    WEIGHT = 0.045
    RETRAIN_WEEKS = 13
    MIN_TRAIN_ROWS = 30_000
    MAX_TRAIN_ROWS = 250_000

    def initialize(self):
        self.set_start_date(2007, 1, 1)
        self.set_end_date(2026, 8, 1)
        self.set_cash(100_000)

        self.universe_settings.resolution = Resolution.DAILY
        self.add_universe(self.select_universe)
        self._next_universe_refresh = datetime.min

        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol
        self.set_benchmark(self.spy)
        self.spy_roll = Roll()
        for bar in self.history[TradeBar](self.spy, 320, Resolution.DAILY):
            self.spy_roll.update(bar.close, bar.volume)

        self.rolls: dict[Symbol, Roll] = {}
        self.basket: set[Symbol] = set()
        self.train_x: list[np.ndarray] = []
        self.train_y: list[float] = []
        self.pending = None            # (symbols, X, prices) from last Friday
        self.model = None
        self.scaler = None
        self.week_count = 0

    def select_universe(self, fundamental):
        if self.time < self._next_universe_refresh:
            return Universe.UNCHANGED
        first = datetime(self.time.year, self.time.month, 1)
        self._next_universe_refresh = (first + timedelta(days=32)).replace(day=1)
        liquid = [
            f for f in fundamental
            if f.has_fundamental_data and f.price > 5 and f.dollar_volume > 20_000_000
        ]
        liquid.sort(key=lambda f: f.market_cap, reverse=True)
        return [f.symbol for f in liquid[: self.UNIVERSE_SIZE]]

    def on_securities_changed(self, changes):
        for security in changes.added_securities:
            symbol = security.symbol
            if symbol == self.spy or symbol in self.rolls:
                continue
            roll = Roll()
            for bar in self.history[TradeBar](symbol, 320, Resolution.DAILY):
                roll.update(bar.close, bar.volume)
            self.rolls[symbol] = roll
        for security in changes.removed_securities:
            symbol = security.symbol
            if symbol in self.rolls and symbol not in self.basket:
                del self.rolls[symbol]

    def on_delistings(self, delistings):
        for symbol in delistings.keys():
            self.basket.discard(symbol)
            self.rolls.pop(symbol, None)

    def on_data(self, data: Slice):
        if self.spy in data.bars:
            bar = data.bars[self.spy]
            self.spy_roll.update(bar.close, bar.volume)
        for symbol, roll in self.rolls.items():
            if symbol in data.bars:
                bar = data.bars[symbol]
                roll.update(bar.close, bar.volume)

        # Friday's daily bar: stamped Fri ~16:00 under QC's precise-end-time
        # default, or Sat 00:00 under the legacy midnight convention.
        wd = self.time.weekday()
        if not (wd == 5 or (wd == 4 and self.time.hour >= 15)):
            return
        self.week_count += 1
        if self.week_count == 1:
            self.log(f"weekly loop alive at {self.time}")

        symbols, raw, prices = [], [], {}
        for symbol, roll in self.rolls.items():
            if roll.ready and self.securities[symbol].is_tradable:
                symbols.append(symbol)
                raw.append(roll.features())
                prices[symbol] = roll.closes[-1]
        if len(symbols) < 100:
            return
        x = rank_cols(np.array(raw))
        s = self.spy_roll
        mkt = np.array([
            s.closes[-1] / s.closes[-6] - 1.0,
            s.closes[-1] / s.closes[-21] - 1.0,
            s.closes[-1] / max(s.closes) - 1.0,
        ])
        x = np.hstack([x, np.tile(mkt, (len(symbols), 1))])

        # label last week's rows with this week's realized return ranks
        if self.pending is not None:
            p_syms, p_x, p_prices = self.pending
            rets, keep = [], []
            for i, sym in enumerate(p_syms):
                if sym in prices and p_prices[sym] > 0:
                    rets.append(prices[sym] / p_prices[sym] - 1.0)
                    keep.append(i)
            if len(keep) >= 100:
                y = np.argsort(np.argsort(rets)) / (len(rets) - 1)
                self.train_x.extend(p_x[keep])
                self.train_y.extend(y)
                if len(self.train_y) > self.MAX_TRAIN_ROWS:
                    cut = len(self.train_y) - self.MAX_TRAIN_ROWS
                    self.train_x = self.train_x[cut:]
                    self.train_y = self.train_y[cut:]
        self.pending = (symbols, x, prices)

        if self.week_count % self.RETRAIN_WEEKS == 0 and len(self.train_y) >= self.MIN_TRAIN_ROWS:
            tx = np.array(self.train_x)
            self.scaler = StandardScaler().fit(tx)
            self.model = MLPRegressor(
                hidden_layer_sizes=(64, 32), batch_size=512,
                max_iter=40, early_stopping=True, n_iter_no_change=4,
                random_state=0,
            )
            self.model.fit(self.scaler.transform(tx), np.array(self.train_y))
            self.log(f"retrained on {len(self.train_y)} rows ({self.time.date()})")

        if self.model is None:
            return
        preds = self.model.predict(self.scaler.transform(x))
        order = np.argsort(preds)[::-1]
        target = {symbols[i] for i in order[: self.BASKET_SIZE]}

        for symbol in self.basket - target:
            qty = self.portfolio[symbol].quantity
            if qty != 0:
                self.market_on_open_order(symbol, -qty)
        for symbol in target - self.basket:
            price = self.securities[symbol].price
            if price > 0:
                qty = int(self.portfolio.total_portfolio_value * self.WEIGHT / price)
                if qty > 0:
                    self.market_on_open_order(symbol, qty)
        self.basket = target
