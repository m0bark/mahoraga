# region imports
from AlgorithmImports import *
from collections import deque
# endregion
#
# PANIC REVERSAL ("broken-shit formula") — QuantConnect LEAN port
# Mirrors research/panic_reversal/FORMULA.md:
#
#   Step 1  broken:   close >= 35% below 252d high  AND  15d return <= -15%
#           (setup stays "armed" for 60 trading days)
#   Step 2  taxonomy: systemic = SPY >= 12% off its 252d high
#                     shock    = worst 1d ret <= -12% or gap <= -8% in last 60d
#                     sizing:  systemic-shock 1.0x, systemic-grind 0.75x,
#                              idio-shock 0.5x, idio-grind SKIP
#   Step 3  trigger:  RSI(14) was < 30, closes back above 30, dd still <= -25%
#                     -> market-on-open buy next day
#   Step 4  exits:    close < max(crash_low, 80% of post-entry peak close)
#                     or 180 trading days  -> market-on-open sell next day
#
# QC's point-in-time universe INCLUDES delisted companies, so this is the
# first survivorship-honest test of the formula. Expect worse numbers than
# the yfinance prototype — that gap is the truth.


class SymbolData:
    """Rolling state per security; seeded from history, updated per daily bar."""

    def __init__(self, symbol: Symbol):
        self.symbol = symbol
        self.closes = deque(maxlen=252)
        self.lows = deque(maxlen=60)
        self.rets = deque(maxlen=60)      # 1d close-to-close returns
        self.gaps = deque(maxlen=60)      # overnight open/prev-close - 1
        self.prev_close = None
        # Wilder RSI state
        self.avg_gain = None
        self.avg_loss = None
        self.rsi = 50.0
        self.rsi_prev = 50.0
        self._rsi_seed = deque(maxlen=15)
        self.armed_days_left = 0
        self.drawdown = 0.0
        self.ret_15 = 0.0

    def update(self, open_: float, low: float, close: float) -> None:
        if self.prev_close is not None and self.prev_close > 0:
            r = close / self.prev_close - 1.0
            self.rets.append(r)
            self.gaps.append(open_ / self.prev_close - 1.0)
            self._update_rsi(r)
        self.closes.append(close)
        self.lows.append(low)
        self.prev_close = close

        if len(self.closes) < 252:
            return
        high_252 = max(self.closes)
        self.drawdown = close / high_252 - 1.0
        self.ret_15 = close / self.closes[-16] - 1.0 if len(self.closes) >= 16 else 0.0

        if self.armed_days_left > 0:
            self.armed_days_left -= 1
        if self.drawdown <= -0.35 and self.ret_15 <= -0.15:
            self.armed_days_left = 60

    def _update_rsi(self, ret: float) -> None:
        gain, loss = max(ret, 0.0), max(-ret, 0.0)
        self.rsi_prev = self.rsi
        if self.avg_gain is None:
            self._rsi_seed.append((gain, loss))
            if len(self._rsi_seed) < 14:
                return
            self.avg_gain = sum(g for g, _ in self._rsi_seed) / 14.0
            self.avg_loss = sum(l for _, l in self._rsi_seed) / 14.0
        else:
            self.avg_gain = (self.avg_gain * 13 + gain) / 14.0
            self.avg_loss = (self.avg_loss * 13 + loss) / 14.0
        if self.avg_loss == 0:
            self.rsi = 100.0
        else:
            rs = self.avg_gain / self.avg_loss
            self.rsi = 100.0 - 100.0 / (1.0 + rs)

    @property
    def ready(self) -> bool:
        return len(self.closes) >= 252 and self.avg_gain is not None

    @property
    def entry_signal(self) -> bool:
        return (
            self.ready
            and self.armed_days_left > 0
            and self.rsi_prev < 30.0 <= self.rsi
            and self.drawdown <= -0.25
        )

    @property
    def is_shock(self) -> bool:
        if not self.rets:
            return False
        return min(self.rets) <= -0.12 or min(self.gaps) <= -0.08

    @property
    def crash_low(self) -> float:
        return min(self.lows) if self.lows else 0.0


class OpenTrade:  # NB: "Position" collides with a LEAN class from AlgorithmImports
    def __init__(self, crash_low: float, entry_close: float):
        self.crash_low = crash_low
        self.entry_close = entry_close
        self.peak_close = entry_close
        self.bars_held = 0


class PanicReversalAlgorithm(QCAlgorithm):

    UNIVERSE_SIZE = 500
    BASE_WEIGHT = 0.05          # 5% slice per full-size position
    MAX_POSITIONS = 20
    TRAIL_FRACTION = 0.80
    TIME_STOP_BARS = 180
    COOLDOWN_AFTER_EXIT = 20   # bars before the same name may re-enter
    COOLDOWN_AFTER_LOSS = 60   # a failed catch = evidence the crash was informational
    BUCKET_MULT = {
        ("systemic", "shock"): 1.00,
        ("systemic", "grind"): 0.75,
        ("idio", "shock"): 0.50,
        ("idio", "grind"): 0.00,   # weakest tested bucket: skip
    }

    def initialize(self):
        self.set_start_date(2007, 1, 1)   # includes GFC; try 2010+ separately
        self.set_end_date(2026, 8, 1)
        self.set_cash(100_000)

        self.universe_settings.resolution = Resolution.DAILY
        self.add_universe(self.select_universe)
        self._next_universe_refresh = datetime.min

        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol
        self.set_benchmark(self.spy)
        self.spy_data = SymbolData(self.spy)
        for bar in self.history[TradeBar](self.spy, 320, Resolution.DAILY):
            self.spy_data.update(bar.open, bar.low, bar.close)

        self.data: dict[Symbol, SymbolData] = {}
        self.positions: dict[Symbol, OpenTrade] = {}
        self.bar_index = 0
        self.cooldown_until: dict[Symbol, int] = {}

    # ---- universe: top N by dollar volume, refreshed monthly (point-in-time) ----
    def select_universe(self, fundamental):
        if self.time < self._next_universe_refresh:
            return Universe.UNCHANGED
        first_of_month = datetime(self.time.year, self.time.month, 1)
        self._next_universe_refresh = (first_of_month + timedelta(days=32)).replace(day=1)
        # Step 0 of the formula: QUALITY large caps only. Ranking by dollar
        # volume let junky high-churn names in (v1 QC run: EXK etc.) and the
        # edge drowned. Market-cap ranking + liquidity floor ~= point-in-time
        # S&P 500 without the survivorship problem.
        liquid = [
            f for f in fundamental
            if f.has_fundamental_data
            and f.price > 5
            and f.dollar_volume > 20_000_000
            and f.market_cap > 10_000_000_000
        ]
        liquid.sort(key=lambda f: f.market_cap, reverse=True)
        return [f.symbol for f in liquid[: self.UNIVERSE_SIZE]]

    def on_securities_changed(self, changes):
        for security in changes.added_securities:
            symbol = security.symbol
            if symbol == self.spy or symbol in self.data:
                continue
            sd = SymbolData(symbol)
            history = self.history[TradeBar](symbol, 320, Resolution.DAILY)
            for bar in history:
                sd.update(bar.open, bar.low, bar.close)
            self.data[symbol] = sd
        for security in changes.removed_securities:
            symbol = security.symbol
            # keep state while a position is open; exit logic will close it
            if symbol in self.data and symbol not in self.positions:
                del self.data[symbol]

    def on_delistings(self, delistings):
        # a holding that dies mid-trade is the survivorship reality the
        # yfinance prototype could never see; LEAN liquidates it for us
        for symbol in delistings.keys():
            if symbol in self.positions:
                self.log(f"DELISTED while held: {symbol.value}")
            self.positions.pop(symbol, None)
            self.data.pop(symbol, None)

    # ---- daily: update state, manage exits, then entries (fills next open) ----
    def on_data(self, data: Slice):
        self.bar_index += 1
        if self.spy in data.bars:
            bar = data.bars[self.spy]
            self.spy_data.update(bar.open, bar.low, bar.close)
        systemic = self.spy_data.ready and self.spy_data.drawdown <= -0.12
        # THE MARKET ITSELF can be the falling knife. While the index is in
        # freefall, a stock's RSI recross is a bear-market rally, not seller
        # exhaustion — so the market must pass the same stabilization test
        # as the stock before any new catch is allowed.
        market_falling = self.spy_data.ready and (
            self.spy_data.rsi < 30.0 or self.spy_data.ret_15 <= -0.10
        )

        for symbol, sd in self.data.items():
            if symbol in data.bars:
                bar = data.bars[symbol]
                sd.update(bar.open, bar.low, bar.close)

        # exits (Step 4)
        for symbol in list(self.positions):
            if symbol not in data.bars:
                continue
            pos = self.positions[symbol]
            close = data.bars[symbol].close
            pos.peak_close = max(pos.peak_close, close)
            pos.bars_held += 1
            stop = max(pos.crash_low, self.TRAIL_FRACTION * pos.peak_close)
            if close < stop or pos.bars_held >= self.TIME_STOP_BARS:
                reason = "stop" if close < stop else "time"
                self.market_on_open_order(symbol, -self.portfolio[symbol].quantity)
                del self.positions[symbol]
                failed_catch = reason == "stop" and close < pos.entry_close
                self.cooldown_until[symbol] = self.bar_index + (
                    self.COOLDOWN_AFTER_LOSS if failed_catch else self.COOLDOWN_AFTER_EXIT
                )
                self.log(f"EXIT  {symbol.value} ({reason}) after {pos.bars_held} bars")

        # entries (Steps 1-3) — blocked entirely while the market is mid-fall
        if market_falling or len(self.positions) >= self.MAX_POSITIONS:
            return
        for symbol, sd in self.data.items():
            if len(self.positions) >= self.MAX_POSITIONS:
                break
            if symbol in self.positions or not sd.entry_signal:
                continue
            if self.cooldown_until.get(symbol, 0) > self.bar_index:
                continue
            if symbol not in data.bars or not self.securities[symbol].is_tradable:
                continue
            bucket = (
                "systemic" if systemic else "idio",
                "shock" if sd.is_shock else "grind",
            )
            mult = self.BUCKET_MULT[bucket]
            if mult <= 0:
                continue
            close = data.bars[symbol].close
            qty = int(self.portfolio.total_portfolio_value * self.BASE_WEIGHT * mult / close)
            if qty <= 0:
                continue
            self.market_on_open_order(symbol, qty)
            self.positions[symbol] = OpenTrade(sd.crash_low, close)
            self.log(
                f"ENTRY {symbol.value} {bucket[0]}-{bucket[1]} "
                f"dd={sd.drawdown:.0%} rsi={sd.rsi:.0f} mult={mult}"
            )
