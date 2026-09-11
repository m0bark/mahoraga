# region imports
from AlgorithmImports import *
from collections import deque
import numpy as np
# endregion
#
# QUALITY-DIP / 200-DAY SETUP — Sentinel run.
# Card: research/screen/PREREG-quality-dip200.md
# Family: overreaction-reversal, shot #5/10. REVISION card off the #4
# near-miss (quality-broken tilt, alpha -0.001). The family is marked
# RETIRED at 4 sealed failures — this run un-retires it, by an explicit
# user decision that must be recorded in the pre-registration first.
#
# SETUP: point-in-time liquid large cap that is (a) >=15% below its 252-day
# high, (b) within -15%/+5% of its 200-day SMA, (c) passes a PIT quality
# screen (positive P/E, positive FCF yield, positive 1y revenue growth,
# debt/equity < 1.5).
#
# The load-bearing baseline is QUALITY-NOT-AT-SETUP: quality names that are
# NOT beaten down. If the candidate cannot beat that, the dip adds nothing
# and the setup is a stock-finder, not a timing edge. A local test with a
# same-universe random-entry control already predicts exactly that failure.
#
# PRE-REGISTERED GATES (frozen; one run; no mid-run changes):
#   G1  candidate CAGR - junk CAGR             >= +3.0%/yr  (mechanism)
#   G2  candidate CAGR - quality_no_setup CAGR >= +2.0%/yr  (load-bearing)
#   G3  candidate - EW >= +2.0%/yr AND beats all 3 random twins
#   G4  QC scoreboard Alpha vs SPY > 0 (traded, net of costs)
# Period 2007-01-01..2022-12-31; 2023+ is the family's sealed holdout.


class Roll:
    """252 trailing closes -> drawdown from the 252d high and 200d SMA distance."""

    def __init__(self):
        self.closes = deque(maxlen=252)

    @property
    def ready(self) -> bool:
        return len(self.closes) == 252

    @property
    def drawdown(self) -> float:
        return self.closes[-1] / max(self.closes) - 1.0

    @property
    def dist200(self) -> float:
        window = list(self.closes)[-200:]
        sma = sum(window) / len(window)
        return self.closes[-1] / sma - 1.0 if sma > 0 else 0.0


class QualityDip200(QCAlgorithm):

    UNIVERSE_SIZE = 500
    DD_MAX = -0.15          # at least 15% below the 252-day high
    D200_LO, D200_HI = -0.15, 0.05
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

        names = (["candidate", "junk", "quality_no_setup", "ew"]
                 + [f"rand{k}" for k in range(self.N_RANDOM)])
        self.tracks = {n: {"eq": 1.0, "members": {}} for n in names}

    # ------------------------------------------------------------------ #
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
            self.quality[f.symbol] = self._is_quality(f)
        return [f.symbol for f in chosen]

    @staticmethod
    def _is_quality(f) -> bool:
        """Point-in-time quality. Every leg must be present and pass; a
        missing field FAILS the name rather than silently passing it."""
        try:
            pe = float(f.valuation_ratios.pe_ratio)
            fcf = float(f.valuation_ratios.fcf_yield)
            rev_g = float(f.operation_ratios.revenue_growth.one_year)
            d_e = float(f.operation_ratios.total_debt_equity_ratio.one_year)
        except Exception:
            return False
        if any(np.isnan(x) for x in (pe, fcf, rev_g, d_e)):
            return False
        return pe > 0 and fcf > 0 and rev_g > 0 and 0 <= d_e < 1.5

    # ------------------------------------------------------------------ #
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

    def on_data(self, data: Slice):
        ym = (self.time.year, self.time.month)
        is_new_month = self._last_ym is not None and ym != self._last_ym
        self._last_ym = ym
        if is_new_month:
            self.rebalance()
        for symbol, roll in self.rolls.items():
            if symbol in data.bars:
                roll.closes.append(data.bars[symbol].close)

    # ------------------------------------------------------------------ #
    def _mark_tracks(self) -> None:
        for tr in self.tracks.values():
            rets = []
            for sym, p0 in tr["members"].items():
                roll = self.rolls.get(sym)
                if roll and roll.closes and p0 > 0:
                    rets.append(roll.closes[-1] / p0 - 1.0)
            if rets:
                tr["eq"] *= 1.0 + float(np.mean(rets))

    def rebalance(self) -> None:
        live = [
            (symbol, roll) for symbol, roll in self.rolls.items()
            if roll.ready and self.securities[symbol].is_tradable
            and self.securities[symbol].price > 0
        ]
        if len(live) < self.MIN_RANKED:
            return
        self._mark_tracks()
        self.reb_count += 1

        all_syms = [s for s, _ in live]

        def at_setup(roll: Roll) -> bool:
            return (roll.drawdown <= self.DD_MAX
                    and self.D200_LO <= roll.dist200 <= self.D200_HI)

        setup = [(s, r) for s, r in live if at_setup(r)]
        # deepest drawdown first, so the basket is stable and rule-based
        setup.sort(key=lambda sr: sr[1].drawdown)

        candidate = [s for s, _ in setup
                     if self.quality.get(s, False)][: self.BASKET_MAX]
        junk = [s for s, _ in setup
                if not self.quality.get(s, False)][: self.BASKET_MAX]
        setup_set = {s for s, _ in setup}
        qns = [s for s in all_syms
               if self.quality.get(s, False) and s not in setup_set][: self.BASKET_MAX]

        if not self._coverage_logged:
            self._coverage_logged = True
            n_q = sum(1 for s in all_syms if self.quality.get(s, False))
            self.log(f"coverage: {n_q}/{len(all_syms)} universe names pass PIT "
                     f"quality; at-setup {len(setup)} -> candidate "
                     f"{len(candidate)} / junk {len(junk)}; "
                     f"quality-no-setup pool {len(qns)}")

        def price(sym: Symbol) -> float:
            return float(self.rolls[sym].closes[-1])

        self.tracks["candidate"]["members"] = {s: price(s) for s in candidate}
        self.tracks["junk"]["members"] = {s: price(s) for s in junk}
        self.tracks["quality_no_setup"]["members"] = {s: price(s) for s in qns}
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
            return  # too few names at the setup this month; hold what we have

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

    # ------------------------------------------------------------------ #
    def on_end_of_algorithm(self):
        self._mark_tracks()
        years = max(self.reb_count, 1) / 12.0
        cagr = {n: tr["eq"] ** (1 / years) - 1 for n, tr in self.tracks.items()}
        cand = cagr["candidate"]
        junk = cagr["junk"]
        qns = cagr["quality_no_setup"]
        ew = cagr["ew"]
        rands = [cagr[f"rand{k}"] for k in range(self.N_RANDOM)]

        self.log("==== QUALITY-DIP / 200-DAY — pre-registered verdict ====")
        self.log(f"months={self.reb_count}  virtual gross CAGR: "
                 f"candidate={cand:.2%}  junk={junk:.2%}  "
                 f"quality_no_setup={qns:.2%}  ew={ew:.2%}  "
                 f"rands={[f'{r:.2%}' for r in rands]}")

        g1 = (cand - junk) >= 0.03
        g2 = (cand - qns) >= 0.02
        g3 = (cand - ew) >= 0.02 and all(cand > r for r in rands)
        self.log(f"G1 mechanism    cand-junk = {cand - junk:+.2%}/yr  "
                 f"(need >= +3.00%)  {'PASS' if g1 else 'FAIL'}")
        self.log(f"G2 dip earns it cand-qns  = {cand - qns:+.2%}/yr  "
                 f"(need >= +2.00%)  {'PASS' if g2 else 'FAIL'}")
        self.log(f"G3 baselines    cand-ew   = {cand - ew:+.2%}/yr  "
                 f"(need >= +2.00% and beat 3 random twins)  "
                 f"{'PASS' if g3 else 'FAIL'}")
        self.log("G4 alpha vs SPY: read from the QC scoreboard (need > 0).")
        self.log("If ANY gate fails: seal FAILED, overreaction-reversal "
                 "returns to RETIRED at 5 sealed failures, and no further "
                 "revision of this mechanism is run.")
