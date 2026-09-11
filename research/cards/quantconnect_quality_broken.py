# region imports
from AlgorithmImports import *
from collections import deque
import numpy as np
# endregion
#
# QUALITY-CONDITIONED BROKEN TILT — Sentinel run for card
# 2026-08-27-quality-broken-tilt (overreaction-reversal family shot #4/10).
#
# Among the deepest-drawdown quintile of point-in-time large caps, hold the
# ~50 deepest names that are PROFITABLE (P/E > 0) with POSITIVE FCF YIELD.
# The load-bearing baseline is the JUNK broken decile (deep drawdowns that
# FAIL quality) — the run measures whether quality separates recoverers
# from corpses on survivorship-free data.
#
# PRE-REGISTERED GATES (frozen; one run; no mid-run changes):
#   G1  quality-broken CAGR - junk-broken CAGR >= +3.0%/yr   (mechanism)
#   G2  quality-broken beats EW universe by >= +2.0%/yr AND beats all
#       3 random twins
#   G3  QC scoreboard Alpha vs SPY > 0 (traded portfolio, net of costs)
# Period 2007-01-01..2022-12-31; 2023+ stays the family's one-shot holdout.


class Roll:
    def __init__(self):
        self.closes = deque(maxlen=252)

    @property
    def ready(self) -> bool:
        return len(self.closes) == 252

    @property
    def drawdown(self) -> float:
        return self.closes[-1] / max(self.closes) - 1.0


class QualityBrokenTilt(QCAlgorithm):

    UNIVERSE_SIZE = 500
    QUINTILE = 0.20
    BASKET_MAX = 50
    MIN_RANKED = 200
    N_RANDOM = 3
    INVESTED_FRACTION = 0.95

    def initialize(self):
        self.set_start_date(2007, 1, 1)
        self.set_end_date(2022, 12, 31)
        self.set_cash(100_000)

        self.universe_settings.resolution = Resolution.DAILY
        self.add_universe(self.select_universe)
        self._next_universe_refresh = datetime.min

        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol
        self.set_benchmark(self.spy)

        self.rolls: dict[Symbol, Roll] = {}
        self.quality: dict[Symbol, bool] = {}
        self.holdings: set[Symbol] = set()
        self._last_ym: tuple[int, int] | None = None
        self.reb_count = 0
        self._coverage_logged = False

        names = ["candidate", "junk", "ew"] + [f"rand{k}" for k in range(self.N_RANDOM)]
        self.tracks = {n: {"eq": 1.0, "members": {}} for n in names}

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
        chosen = liquid[: self.UNIVERSE_SIZE]
        for f in chosen:
            try:
                pe = float(f.valuation_ratios.pe_ratio)
                fcf = float(f.valuation_ratios.fcf_yield)
                self.quality[f.symbol] = pe > 0 and fcf > 0
            except Exception:
                self.quality[f.symbol] = False
        return [f.symbol for f in chosen]

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
            and self.securities[symbol].price > 0
        ]
        if len(ranked) < self.MIN_RANKED:
            return
        self._mark_tracks()
        self.reb_count += 1

        ranked.sort()
        n_quint = max(20, int(len(ranked) * self.QUINTILE))
        quintile = [symbol for _, symbol in ranked[:n_quint]]
        all_syms = [symbol for _, symbol in ranked]

        q_pool = [s for s in quintile if self.quality.get(s, False)]
        j_pool = [s for s in quintile if not self.quality.get(s, False)]
        candidate = q_pool[: self.BASKET_MAX]
        junk = j_pool[: self.BASKET_MAX]

        if not self._coverage_logged:
            self._coverage_logged = True
            qc_cov = sum(1 for s in all_syms if self.quality.get(s, False))
            self.log(f"fundamental coverage check: {qc_cov}/{len(all_syms)} "
                     f"universe names flagged quality; broken quintile split "
                     f"{len(q_pool)} quality / {len(j_pool)} junk")

        def price(sym: Symbol) -> float:
            return float(self.rolls[sym].closes[-1])

        self.tracks["candidate"]["members"] = {s: price(s) for s in candidate}
        self.tracks["junk"]["members"] = {s: price(s) for s in junk}
        self.tracks["ew"]["members"] = {s: price(s) for s in all_syms}
        n_basket = max(len(candidate), 10)
        for k in range(self.N_RANDOM):
            rng = np.random.default_rng(
                k * 1_000_003 + self.time.year * 100 + self.time.month)
            pick = rng.choice(len(all_syms), size=min(n_basket, len(all_syms)),
                              replace=False)
            self.tracks[f"rand{k}"]["members"] = {
                all_syms[i]: price(all_syms[i]) for i in pick}

        if len(candidate) < 10:
            return  # too few quality names this month; hold what we have

        target = set(candidate)
        for symbol in self.holdings - target:
            qty = self.portfolio[symbol].quantity
            if qty != 0:
                self.market_on_open_order(symbol, -qty)
        weight = self.INVESTED_FRACTION / len(candidate)
        for symbol in target - self.holdings:
            px = price(symbol)
            qty = int(self.portfolio.total_portfolio_value * weight / px)
            if qty > 0:
                self.market_on_open_order(symbol, qty)
        self.holdings = target

    def on_end_of_algorithm(self):
        self._mark_tracks()
        years = max(self.reb_count, 1) / 12.0
        cagr = {n: tr["eq"] ** (1 / years) - 1 for n, tr in self.tracks.items()}
        cand, junk, ew = cagr["candidate"], cagr["junk"], cagr["ew"]
        rands = [cagr[f"rand{k}"] for k in range(self.N_RANDOM)]

        self.log("==== QUALITY-BROKEN TILT — pre-registered verdict ====")
        self.log(f"months={self.reb_count}  virtual gross CAGR: "
                 f"quality-broken={cand:.2%}  junk-broken={junk:.2%}  "
                 f"ew={ew:.2%}  rands={[f'{r:.2%}' for r in rands]}")
        g1 = cand - junk >= 0.03
        g2 = (cand - ew >= 0.02) and all(cand > r for r in rands)
        self.log(f"G1 mechanism: quality-junk = {cand - junk:+.2%}/yr "
                 f"(need >= +3.00%) -> {'PASS' if g1 else 'FAIL'}")
        self.log(f"G2 vs EW = {cand - ew:+.2%}/yr (need >= +2.00%) and "
                 f"beats all twins -> {'PASS' if g2 else 'FAIL'}")
        self.log("G3 = QC scoreboard Alpha > 0 (read off the report)")
        self.log(f"VERDICT (G1+G2): "
                 f"{'PASS so far — check Alpha for G3' if g1 and g2 else 'FAIL — seal it; family retirement proposed'}")
