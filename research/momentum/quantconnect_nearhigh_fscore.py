# region imports
from AlgorithmImports import *
from collections import deque
import numpy as np
# endregion
#
# 52-WEEK-HIGH MOMENTUM x FUNDAMENTAL QUALITY — Sentinel run.
# Card: research/momentum/PREREG-nearhigh-fscore.md
# Family: momentum/anchoring, shot #1/10. DISCOVERY (not a revision of the
# retired overreaction-reversal family — opposite sign, different mechanism).
#
# ONE TOKEN, 25 ANSWERS. Virtual tracks cost no orders, so this run carries
# the full 5x5 grid: nearness-to-52w-high quintile x F-Score-lite bucket.
# A FAIL on the headline direction still returns the separator result, the
# interaction shape, and a free replication of the -5.19%/yr deep-dip
# finding from card 2026-08-30.
#
# TRADED CELL IS NAMED IN THE PRE-REGISTRATION: N1 (nearest high) x top-two
# quality buckets. Whichever cell wins the grid is an observation for a
# FUTURE card, never a retrofitted claim about this one.
#
# GATES (frozen):
#   G1 direction   N1 CAGR - N5 CAGR                   >= +3.0%/yr
#   G2 separator   within N1: topQ CAGR - botQ CAGR    >= +3.0%/yr
#   G3 baselines   traded - EW >= +2.0%/yr AND beats 3 random twins
#   G4 money       QC alpha vs SPY > 0, net of costs
# Period 2007-01-01..2022-12-31; 2023+ sealed holdout.
#
# COST FIX (last run paid $8,079 fees / 6,808 orders): quarterly rebalance,
# quarterly universe refresh, 50-name basket. Target < 2,500 orders.


class Roll:
    """252 trailing closes -> nearness to the 252-day high."""

    def __init__(self):
        self.closes = deque(maxlen=252)

    @property
    def ready(self) -> bool:
        return len(self.closes) == 252

    @property
    def nearness(self) -> float:
        hi = max(self.closes)
        return self.closes[-1] / hi if hi > 0 else 0.0


class NearHighFScore(QCAlgorithm):

    UNIVERSE_SIZE = 500
    N_BUCKETS = 5
    BASKET_MAX = 50
    MIN_RANKED = 200
    N_RANDOM = 3
    INVESTED_FRACTION = 0.95
    TOP_Q = 2          # traded cell uses the top-two quality buckets

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
        self.fscore: dict[Symbol, int] = {}
        self.holdings: set[Symbol] = set()
        self._last_q: tuple[int, int] | None = None
        self.reb_count = 0
        self._cov_logged = False
        self._leg_hits = [0] * 7
        self._leg_n = 0

        # 25 grid cells + baselines, all virtual (zero orders)
        names = [f"N{n}Q{q}" for n in range(1, 6) for q in range(1, 6)]
        names += ["traded", "ew"] + [f"rand{k}" for k in range(self.N_RANDOM)]
        names += [f"N{n}" for n in range(1, 6)]
        self.tracks = {n: {"eq": 1.0, "members": {}} for n in names}

    # ------------------------------------------------------------------ #
    def select_universe(self, fundamental):
        if self.time < self._next_universe_refresh:
            return Universe.UNCHANGED
        m = ((self.time.month - 1) // 3 + 1) * 3 + 1
        y = self.time.year + (1 if m > 12 else 0)
        self._next_universe_refresh = datetime(y, m if m <= 12 else 1, 1)

        liquid = [f for f in fundamental
                  if f.has_fundamental_data and f.price > 5
                  and f.dollar_volume > 20_000_000]
        liquid.sort(key=lambda f: f.market_cap, reverse=True)
        chosen = liquid[: self.UNIVERSE_SIZE]
        for f in chosen:
            self.fscore[f.symbol] = self._fscore_lite(f)
        return [f.symbol for f in chosen]

    def _fscore_lite(self, f) -> int:
        """Piotroski-style score, 0-7, from PIT Morningstar fields.
        Each leg is attempted independently; a missing leg scores 0 rather
        than failing the whole name. Leg coverage is logged so we know how
        many legs actually populated over the run."""
        legs = []

        def leg(fn):
            try:
                v = fn()
                if v is None or (isinstance(v, float) and np.isnan(v)):
                    legs.append(None)
                else:
                    legs.append(bool(v))
            except Exception:
                legs.append(None)

        o = f.operation_ratios
        leg(lambda: float(o.roa.one_year) > 0)                       # profitable
        leg(lambda: float(o.roic.one_year) > 0)                      # returns on capital
        leg(lambda: float(o.net_margin.one_year) > 0)                # margin positive
        leg(lambda: float(o.roa.one_year) > float(o.roa.three_years))  # improving ROA
        leg(lambda: float(o.gross_margin.one_year)
            > float(o.gross_margin.three_years))                     # improving margin
        leg(lambda: float(o.total_debt_equity_ratio.one_year) < 1.0)  # leverage
        leg(lambda: float(o.current_ratio.one_year) > 1.0)           # liquidity

        self._leg_n += 1
        for i, v in enumerate(legs):
            if v is not None:
                self._leg_hits[i] += 1
        return sum(1 for v in legs if v)

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
        q = (self.time.year, (self.time.month - 1) // 3)
        is_new_q = self._last_q is not None and q != self._last_q
        self._last_q = q
        if is_new_q:
            self.rebalance()
        for symbol, roll in self.rolls.items():
            if symbol in data.bars:
                roll.closes.append(data.bars[symbol].close)

    def _mark_tracks(self) -> None:
        for tr in self.tracks.values():
            rets = []
            for sym, p0 in tr["members"].items():
                roll = self.rolls.get(sym)
                if roll and roll.closes and p0 > 0:
                    rets.append(roll.closes[-1] / p0 - 1.0)
            if rets:
                tr["eq"] *= 1.0 + float(np.mean(rets))

    # ------------------------------------------------------------------ #
    def rebalance(self) -> None:
        live = [(s, r) for s, r in self.rolls.items()
                if r.ready and self.securities[s].is_tradable
                and self.securities[s].price > 0]
        if len(live) < self.MIN_RANKED:
            return
        self._mark_tracks()
        self.reb_count += 1

        live.sort(key=lambda sr: -sr[1].nearness)      # N1 = nearest the high
        all_syms = [s for s, _ in live]
        n = len(live)
        step = n / self.N_BUCKETS

        def price(sym):
            return float(self.rolls[sym].closes[-1])

        near_bucket: dict[Symbol, int] = {}
        for idx, (s, _) in enumerate(live):
            near_bucket[s] = min(int(idx // step) + 1, self.N_BUCKETS)

        # quality buckets from F-Score-lite, ranked across the whole universe
        scored = sorted(all_syms, key=lambda s: -self.fscore.get(s, 0))
        qstep = len(scored) / self.N_BUCKETS
        q_bucket = {s: min(int(i // qstep) + 1, self.N_BUCKETS)
                    for i, s in enumerate(scored)}      # Q1 = highest score

        cells: dict[str, list] = {f"N{a}Q{b}": []
                                  for a in range(1, 6) for b in range(1, 6)}
        for s in all_syms:
            cells[f"N{near_bucket[s]}Q{q_bucket[s]}"].append(s)
        for key, syms in cells.items():
            self.tracks[key]["members"] = {s: price(s) for s in syms[: self.BASKET_MAX]}
        for a in range(1, 6):
            syms = [s for s in all_syms if near_bucket[s] == a]
            self.tracks[f"N{a}"]["members"] = {s: price(s) for s in syms}

        # the traded cell — named in the pre-registration, not chosen here
        traded = [s for s in all_syms
                  if near_bucket[s] == 1 and q_bucket[s] <= self.TOP_Q][: self.BASKET_MAX]
        self.tracks["traded"]["members"] = {s: price(s) for s in traded}
        self.tracks["ew"]["members"] = {s: price(s) for s in all_syms}

        nb = max(len(traded), 10)
        for k in range(self.N_RANDOM):
            rng = np.random.default_rng(k * 1_000_003 + self.time.year * 10
                                        + self.time.month)
            pick = rng.choice(len(all_syms), size=min(nb, len(all_syms)), replace=False)
            self.tracks[f"rand{k}"]["members"] = {all_syms[i]: price(all_syms[i])
                                                  for i in pick}

        if not self._cov_logged:
            self._cov_logged = True
            cov = [f"{h}/{self._leg_n}" for h in self._leg_hits]
            self.log(f"F-Score-lite leg coverage (populated/attempted): {cov}")
            self.log(f"universe {len(all_syms)}; traded cell N1xQ<=2 = {len(traded)}")

        if len(traded) < 10:
            return
        target = set(traded)
        for symbol in self.holdings - target:
            qty = self.portfolio[symbol].quantity
            if qty != 0:
                self.market_on_open_order(symbol, -qty)
        weight = self.INVESTED_FRACTION / len(traded)
        for symbol in target - self.holdings:
            qty = int(self.portfolio.total_portfolio_value * weight / price(symbol))
            if qty > 0:
                self.market_on_open_order(symbol, qty)
        self.holdings = target

    # ------------------------------------------------------------------ #
    def on_end_of_algorithm(self):
        self._mark_tracks()
        years = max(self.reb_count, 1) / 4.0       # quarterly rebalances
        cagr = {k: (t["eq"] ** (1 / years) - 1) if t["eq"] > 0 else -1.0
                for k, t in self.tracks.items()}

        self.log("==== 52W-HIGH x QUALITY — pre-registered verdict ====")
        self.log(f"quarters={self.reb_count}  years={years:.1f}")
        self.log("GRID (gross CAGR). rows = nearness N1 nearest high .. N5 "
                 "deepest dip; cols = quality Q1 best .. Q5 worst")
        for a in range(1, 6):
            row = "  ".join(f"Q{b}={cagr[f'N{a}Q{b}']:+.2%}" for b in range(1, 6))
            self.log(f"  N{a} (all={cagr[f'N{a}']:+.2%}):  {row}")

        n1, n5 = cagr["N1"], cagr["N5"]
        sep = cagr["N1Q1"] - cagr["N1Q5"]
        tr, ew = cagr["traded"], cagr["ew"]
        rands = [cagr[f"rand{k}"] for k in range(self.N_RANDOM)]
        self.log(f"baselines: traded={tr:+.2%}  ew={ew:+.2%}  "
                 f"rands={[f'{r:+.2%}' for r in rands]}")

        g1 = (n1 - n5) >= 0.03
        g2 = sep >= 0.03
        g3 = (tr - ew) >= 0.02 and all(tr > r for r in rands)
        self.log(f"G1 direction  N1-N5 = {n1 - n5:+.2%}/yr (need >= +3.00%)  "
                 f"{'PASS' if g1 else 'FAIL'}")
        self.log(f"G2 separator  N1Q1-N1Q5 = {sep:+.2%}/yr (need >= +3.00%)  "
                 f"{'PASS' if g2 else 'FAIL'}")
        self.log(f"G3 baselines  traded-ew = {tr - ew:+.2%}/yr (need >= +2.00% "
                 f"and beat 3 twins)  {'PASS' if g3 else 'FAIL'}")
        self.log("G4 alpha vs SPY: read from the QC scoreboard (need > 0).")
        self.log(f"FREE REPLICATION — deep-dip corner N5 = {n5:+.2%}/yr vs "
                 f"N1 = {n1:+.2%}/yr. Card 2026-08-30 measured the dip cell "
                 f"at -5.19%/yr against undipped quality; this is the "
                 f"independent check.")
        self.log("Winning grid cell (if not the traded cell) is an "
                 "OBSERVATION for a future pre-registration — never a "
                 "retrofitted claim about this run.")
