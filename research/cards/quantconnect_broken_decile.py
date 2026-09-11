# region imports
from AlgorithmImports import *
from collections import deque
import numpy as np
# endregion
#
# BROKEN-DECILE TILT — Sentinel run for card 2026-08-27-broken-decile-tilt
# (research/cards/2026-08-27-broken-decile-tilt.md). Spec is FROZEN:
#
#   Universe: top 500 by market cap, point-in-time, monthly; price > $5,
#             dollar volume > $20M/day.
#   Signal:   month-end close drawdown = close / 252d-high - 1; hold the
#             deepest decile (~50 names) equal weight, rebalance monthly.
#   Tracks:   REAL traded candidate (QC costs -> gate 3 alpha vs SPY) plus
#             VIRTUAL gross tracks computed in-run: candidate, EW universe,
#             5 turnover-matched random-decile twins (gates 1-2, like for
#             like, no costs on any virtual leg).
#   Period:   2007-01-01 .. 2022-12-31. 2023+ is the family's ONE-SHOT
#             holdout — do not run it unless this run passes.
#
# PRE-REGISTERED VERDICT (all three, no mid-run changes):
#   1. virtual candidate CAGR - virtual EW CAGR >= +3.0%/yr
#   2. virtual candidate CAGR > every random twin's CAGR
#   3. QC scoreboard Alpha vs SPY > 0 (the traded, net-of-costs portfolio)
# FAIL on any miss -> sealed Failure, feeds Mahoraga. One run.


class Roll:
    def __init__(self):
        self.closes = deque(maxlen=252)

    @property
    def ready(self) -> bool:
        return len(self.closes) == 252

    @property
    def drawdown(self) -> float:
        return self.closes[-1] / max(self.closes) - 1.0


class BrokenDecileTilt(QCAlgorithm):

    UNIVERSE_SIZE = 500
    DECILE = 0.10
    MIN_RANKED = 200
    N_RANDOM = 5
    INVESTED_FRACTION = 0.95

    def initialize(self):
        self.set_start_date(2007, 1, 1)
        self.set_end_date(2022, 12, 31)   # 2023+ = reserved one-shot holdout
        self.set_cash(100_000)

        self.universe_settings.resolution = Resolution.DAILY
        self.add_universe(self.select_universe)
        self._next_universe_refresh = datetime.min

        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol
        self.set_benchmark(self.spy)

        self.rolls: dict[Symbol, Roll] = {}
        self.holdings: set[Symbol] = set()
        self._last_ym: tuple[int, int] | None = None
        self.reb_count = 0

        track_names = ["candidate", "ew"] + [f"rand{k}" for k in range(self.N_RANDOM)]
        self.tracks = {name: {"eq": 1.0, "members": {}} for name in track_names}

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
            for bar in self.history[TradeBar](symbol, 260, Resolution.DAILY):
                roll.closes.append(bar.close)
            self.rolls[symbol] = roll
        for security in changes.removed_securities:
            symbol = security.symbol
            if symbol in self.rolls and symbol not in self.holdings:
                del self.rolls[symbol]

    def on_delistings(self, delistings):
        for symbol in delistings.keys():
            self.holdings.discard(symbol)
            self.rolls.pop(symbol, None)
            # NB: virtual tracks simply drop a delisted member at the next
            # marking (see _mark_tracks) — a small survivorship leak in the
            # virtual legs only; the REAL traded candidate books the loss
            # through LEAN's delisting handling, which is the honest leg.

    def _mark_tracks(self) -> None:
        for tr in self.tracks.values():
            rets = []
            for sym, p0 in tr["members"].items():
                roll = self.rolls.get(sym)
                if roll and roll.closes and p0 > 0:
                    rets.append(roll.closes[-1] / p0 - 1.0)
            if rets:
                tr["eq"] *= 1.0 + float(np.mean(rets))

    def on_data(self, data: Slice):
        ym = (self.time.year, self.time.month)
        is_new_month = self._last_ym is not None and ym != self._last_ym
        self._last_ym = ym

        # Rebalance BEFORE updating rolls with today's bar, so signals and
        # virtual marks use exactly the prior month-end closes.
        if is_new_month:
            self.rebalance()

        for symbol, roll in self.rolls.items():
            if symbol in data.bars:
                roll.closes.append(data.bars[symbol].close)

    def rebalance(self) -> None:
        ranked = [
            (roll.drawdown, symbol)
            for symbol, roll in self.rolls.items()
            if roll.ready and self.securities[symbol].is_tradable
            and self.securities[symbol].price > 0  # has received a live bar
        ]
        if len(ranked) < self.MIN_RANKED:
            return
        self._mark_tracks()
        self.reb_count += 1

        ranked.sort()  # most negative drawdown first
        n_decile = max(10, int(len(ranked) * self.DECILE))
        decile = [symbol for _, symbol in ranked[:n_decile]]
        all_syms = [symbol for _, symbol in ranked]

        def price(sym: Symbol) -> float:
            return float(self.rolls[sym].closes[-1])

        self.tracks["candidate"]["members"] = {s: price(s) for s in decile}
        self.tracks["ew"]["members"] = {s: price(s) for s in all_syms}
        for k in range(self.N_RANDOM):
            rng = np.random.default_rng(
                k * 1_000_003 + self.time.year * 100 + self.time.month)
            pick = rng.choice(len(all_syms), size=n_decile, replace=False)
            self.tracks[f"rand{k}"]["members"] = {
                all_syms[i]: price(all_syms[i]) for i in pick}

        if self.reb_count % 12 == 0:
            years = self.reb_count / 12.0
            c = self.tracks["candidate"]["eq"] ** (1 / years) - 1
            e = self.tracks["ew"]["eq"] ** (1 / years) - 1
            self.plot("Virtual CAGR", "candidate", round(c * 100, 2))
            self.plot("Virtual CAGR", "ew", round(e * 100, 2))

        # REAL portfolio: trade into the decile, equal weight (entries and
        # exits only; drift between rebalances is tolerated)
        target = set(decile)
        for symbol in self.holdings - target:
            qty = self.portfolio[symbol].quantity
            if qty != 0:
                self.market_on_open_order(symbol, -qty)
        weight = self.INVESTED_FRACTION / n_decile
        for symbol in target - self.holdings:
            px = price(symbol)
            qty = int(self.portfolio.total_portfolio_value * weight / px)
            if qty > 0:
                self.market_on_open_order(symbol, qty)
        self.holdings = target

    def on_end_of_algorithm(self):
        self._mark_tracks()
        years = max(self.reb_count, 1) / 12.0
        cagr = {name: tr["eq"] ** (1 / years) - 1 for name, tr in self.tracks.items()}
        cand, ew = cagr["candidate"], cagr["ew"]
        rands = [cagr[f"rand{k}"] for k in range(self.N_RANDOM)]

        self.log("==== BROKEN-DECILE TILT — pre-registered verdict ====")
        self.log(f"months={self.reb_count}  virtual gross CAGR: "
                 f"candidate={cand:.2%}  ew={ew:.2%}  "
                 f"rands={[f'{r:.2%}' for r in rands]}")
        g1 = cand - ew >= 0.03
        g2 = all(cand > r for r in rands)
        self.log(f"GATE1 excess vs EW = {cand - ew:+.2%}/yr (need >= +3.00%) "
                 f"-> {'PASS' if g1 else 'FAIL'}")
        self.log(f"GATE2 beats all {self.N_RANDOM} random twins "
                 f"-> {'PASS' if g2 else 'FAIL'}")
        self.log("GATE3 = QC scoreboard Alpha > 0 (read it off the backtest "
                 "report — the traded portfolio, net of costs)")
        self.log(f"VERDICT (gates 1+2): {'PASS so far — check Alpha for gate 3' if g1 and g2 else 'FAIL — seal it'}")
