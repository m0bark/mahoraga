# region imports
from AlgorithmImports import *
import numpy as np
# endregion


class TriggerQuality(QCAlgorithm):
    """The trigger with the stop removed and a fundamental gate added.

    WHY THIS EXISTS, AND WHAT THE LAST RUN PROVED
    trigger.py ran 2013-2026 with working bracket exits and finished at
    $64,397 from $100,000 while SPY roughly tripled. The local post-mortem in
    research/sheet/trigger_diagnose.py found three things, and this algorithm
    is built on the third:

      1. THE LEVELS ARE NOT LEVELS. Nearest clustered support sits a median
         1.48% below the entry, resistance 4.59% above. Over a 504-bar window
         with a 5-bar pivot rule there are dozens of swings, so "nearest"
         always lands on the last small wiggle. A 3:1 ratio computed from
         those two numbers is arithmetic on noise.

      2. R WAS THE WRONG UNIT. In percent the trigger earned +0.39% per trade
         against +0.36% for simply buying at market. The advertised 3x edge
         was three hundredths of a percentage point, and the MEDIAN trigger
         trade lost 0.93% while the median market trade gained 0.91%.

      3. THE STOP WAS THE LOSS. The same entries with NO stop, exiting at the
         target or after 126 days, earned +1.97% mean and +3.28% median,
         against +0.39% and -0.93% with the stop. A stop 1.48% away is hit by
         ordinary noise 70% of the time. Simulated over ten slots at 9% each,
         a stop filling exactly at support ends +870% and a stop filling at the
         low of the bar that triggered it ends -97.4%. When a result swings 900
         points on the fill model, it is a bet on execution, not on price.

    So the stop is gone. The exit is the target or a time limit, which is also
    why position size is small and the name count is high: without a stop the
    only risk control left is diversification and the clock.

    DO NOT RUN THIS EXPECTING IT TO WORK. READ THIS FIRST.
    After the above was written, the comparison was redone properly and the
    no-stop variant FAILED TOO. The first version of that test shared an exit
    price between the two arms while entering lower in one of them, so the
    trigger beat it by arithmetic on every single trade and returned t = +100.9.
    A t of 100 is not a strong result, it is proof the quantity is
    deterministic. It was also measured only on the names whose limit filled,
    which conditions the control on having fallen.

    Redone with a fixed 63-day horizon for both arms and the control measured
    on EVERY armed candidate rather than only the filled ones:

        trigger, filled only                        +3.74%
        buy at the close, EVERY armed candidate     +3.68%
        trigger, blended (unfilled count as 0%)     +2.70%
        STRATEGY MINUS CONTROL                      -0.98%   t = -8.66

        buy at the close, only the names that later filled   +1.78%

    Conditional on filling, the limit matches buying at market to within six
    hundredths of a percentage point. But it fails to fill 27.8% of the time,
    and that idle capital is what turns a tie into a one-point-a-trade loss.
    The last line is the mechanism: a name that falls to your limit goes on to
    return half what the average candidate returned. The limit is not buying a
    discount, it is selecting the names that kept falling, and the ones that
    ran away were never bought at all.

    This file is kept because the fundamental gate and the LEAN plumbing in it
    are reusable, and because a QC run would confirm the local verdict rather
    than overturn it: local data omits delisted companies, so it is the
    OPTIMISTIC bound. Something that loses on optimistic data loses harder on
    honest data. Spending one of a limited number of backtests on it buys
    nothing. The trigger mechanic is retired.

    THE FUNDAMENTAL GATE, AND AN HONEST WARNING ABOUT IT
    Requested directly: do not buy a bad company at a bad price. Measured
    locally first, in research/sheet/trigger_quality.py, by cutting the 25,204
    filled triggers that had a known SEC filing into quintiles by a real
    nine-leg Piotroski F-Score aligned on the FILING date:

        quality quintile     Q1 worst   Q2      Q3      Q4      Q5 best
        mean, no stop          +2.11%  +1.70%  +2.13%  +2.11%  +1.87%

    Flat. Not negative, which is what two earlier cards in this project had
    claimed, and not positive either. Top minus bottom came to -0.25% with
    t = -1.46 and no monotonicity at all. The likely reason is a timescale
    mismatch: the median filing was 58 DAYS OLD at the moment the trigger
    armed, and these trades resolve in a handful of days. A two-month-old
    balance sheet has nothing to say about the next four days of trading.

    The gate is here anyway, for a reason that is about risk and not return:
    without a stop, a position can be held for 126 days, and over that horizon
    the difference between a solvent company and a failing one does matter. It
    is expected to change the return very little. If it changes it a lot in
    either direction, that is informative and the log will show it.

    LEG COVERAGE IS LOGGED, because card research/cards/2026-08-31-nearhigh-
    fscore.md failed for exactly this reason: two of its seven quality legs
    populated ZERO times out of 500 and the run was interpreted as a verdict on
    a score that had never actually been computed. Every leg here reports how
    often it resolved. If a leg reads 0%, the conclusion is void, and the log
    will say so rather than leaving it to be discovered later.

    TWO LEAN TRAPS ALREADY PAID FOR
      * On daily resolution LEAN converts a market order sent during the
        session into MarketOnOpen, which is rejected outside 04:00-09:28. The
        first run sent its exits at 15:50 and EVERY stop and target was
        rejected. Housekeeping here runs BEFORE the open, and the target is a
        resting limit placed the moment the entry fills.
      * Pending limit orders RESERVE cash in a cash account, which cannot
        borrow. Arming is sized against settled cash and the number of live
        orders is capped separately from the number of positions.
    """

    # ------------------------------------------------------------ parameters
    RATIO = 3.0               # where the limit sits inside the range
    PIVOT_K = 5
    CLUSTER_TOL = 0.015
    MIN_TOUCHES = 2
    LOOKBACK = 504
    EXPIRY_DAYS = 21          # how long an unfilled limit stays live
    HOLD_DAYS = 126           # the time exit, since there is no stop
    MAX_POSITIONS = 10
    MAX_LIVE_ORDERS = 4
    UNIVERSE_SIZE = 300
    MIN_PRICE = 5.0
    MIN_DOLLAR_VOL = 5e6
    MIN_LEGS = 4              # of 5; below this the gate is not comparable
    MIN_PASSED = 3            # of the legs that resolved
    CASH_USE = 0.95

    def Initialize(self):
        self.SetStartDate(2013, 1, 1)
        self.SetEndDate(2026, 9, 1)
        self.SetCash(100000)
        self.SetBrokerageModel(BrokerageName.InteractiveBrokersBrokerage,
                               AccountType.Cash)
        self.Settings.FreePortfolioValuePercentage = 0.05
        self.Settings.MinimumOrderMarginPortfolioPercentage = 0.005

        self.UniverseSettings.Resolution = Resolution.Daily
        self.AddUniverse(self.Coarse, self.Fine)
        self.spy = self.AddEquity("SPY", Resolution.Daily).Symbol

        self.live = {}        # symbol -> {"ticket", "target", "armed_bar"}
        self.pos = {}         # symbol -> {"entry", "target", "bar", "ticket"}
        self.ok_fund = set()  # symbols passing the gate at the last selection

        self.bar = 0
        self.armed = 0
        self.filled = 0
        self.hit_target = 0
        self.timed_out = 0
        self.r_sum = 0.0
        self.n_closed = 0
        self.gate_pass = 0
        self.gate_fail = 0
        # one counter per leg, so a leg that never resolves is visible
        self.leg_seen = [0] * 5
        self.leg_pass = [0] * 5
        self.fine_calls = 0

        self.Schedule.On(self.DateRules.MonthStart(self.spy),
                         self.TimeRules.AfterMarketOpen(self.spy, 30),
                         self.Arm)
        # BEFORE the open: the only window in which a market order on daily
        # data is accepted. This is where time exits are sent.
        self.Schedule.On(self.DateRules.EveryDay(self.spy),
                         self.TimeRules.BeforeMarketOpen(self.spy, 30),
                         self.Manage)
        self.SetWarmUp(self.LOOKBACK + 10, Resolution.Daily)

    def OnData(self, data):
        if not self.IsWarmingUp:
            self.bar += 1

    # ---------------------------------------------------------------- universe
    def Coarse(self, coarse):
        ok = [c for c in coarse
              if c.HasFundamentalData and c.Price > self.MIN_PRICE
              and c.DollarVolume > self.MIN_DOLLAR_VOL]
        ok.sort(key=lambda c: c.DollarVolume, reverse=True)
        return [c.Symbol for c in ok[:self.UNIVERSE_SIZE]]

    def Fine(self, fine):
        """THE FUNDAMENTAL GATE. Five static legs, deliberately NOT the
        improvement legs: the vendor's three-year fields did not resolve in an
        earlier run in this project and a leg that silently never populates is
        worse than an absent one. Every leg counts how often it resolved."""
        self.fine_calls += 1
        keep = []
        passers = set()
        for f in fine:
            if not f.MarketCap or f.MarketCap < 1e9:
                continue
            keep.append(f.Symbol)
            legs = []
            legs.append(self._leg(0, f, lambda x: x.OperationRatios.ROA.OneYear,
                                  lambda v: v > 0))
            # LEAN calls this OperationMargin, not OperatingMargin. The first
            # run asked for OperatingMargin, the attribute did not exist, the
            # AttributeError was caught, and the leg reported "unresolved"
            # 1,073,217 times out of 1,073,217 -- a silent 0% that the coverage
            # log caught and nothing else would have. A tuple of candidate
            # names now, so a vendor rename degrades to the next option instead
            # of to zero.
            legs.append(self._leg(
                1, f, lambda x: self._first(
                    x, ("OperationRatios.OperationMargin.OneYear",
                        "OperationRatios.OperationMargin.ThreeMonths",
                        "OperationRatios.NetMargin.OneYear")),
                lambda v: v > 0))
            legs.append(self._leg(
                2, f,
                lambda x: x.FinancialStatements.CashFlowStatement
                .FreeCashFlow.TwelveMonths,
                lambda v: v > 0))
            legs.append(self._leg(
                3, f, lambda x: x.OperationRatios.TotalDebtEquityRatio.OneYear,
                lambda v: 0 <= v < 2.0))
            legs.append(self._leg(
                4, f, lambda x: x.OperationRatios.CurrentRatio.OneYear,
                lambda v: v > 1.0))
            got = [v for v in legs if v is not None]
            if len(got) >= self.MIN_LEGS and sum(got) >= self.MIN_PASSED:
                passers.add(f.Symbol)
                self.gate_pass += 1
            else:
                self.gate_fail += 1
        self.ok_fund = passers
        return keep

    def _first(self, obj, paths):
        """First dotted path on obj that resolves to a usable number. Returns
        None if none do, which the caller records as an unresolved leg."""
        for p in paths:
            cur = obj
            try:
                for part in p.split("."):
                    cur = getattr(cur, part)
            except AttributeError:
                continue
            if cur is None:
                continue
            try:
                v = float(cur)
            except (TypeError, ValueError):
                continue
            if np.isfinite(v) and v != 0.0:
                return v
        return None

    def _leg(self, i, f, get, test):
        """Returns 1, 0, or None when the field did not resolve. None is NOT a
        zero: counting an unresolved field as a failed leg would quietly reject
        every company whose data is thin."""
        try:
            v = get(f)
        except Exception:
            return None
        if v is None:
            return None
        try:
            v = float(v)
        except (TypeError, ValueError):
            return None
        if not np.isfinite(v) or v == 0.0:
            # exactly zero is how this vendor represents "absent" for most of
            # these ratios, so it is treated as unresolved rather than as a
            # real zero. The coverage log makes the cost of that visible.
            return None
        self.leg_seen[i] += 1
        ok = bool(test(v))
        if ok:
            self.leg_pass[i] += 1
        return 1 if ok else 0

    # ------------------------------------------------------------------ levels
    def Levels(self, high, low, spot):
        k = self.PIVOT_K
        lows, highs = [], []
        for i in range(k, len(low) - k):
            wl = low[i - k:i + k + 1]
            if low[i] == wl.min() and (wl == low[i]).sum() == 1:
                lows.append(float(low[i]))
            wh = high[i - k:i + k + 1]
            if high[i] == wh.max() and (wh == high[i]).sum() == 1:
                highs.append(float(high[i]))

        def cluster(vals):
            out = []
            for v in sorted(vals):
                if out and abs(v - out[-1][0]) / out[-1][0] <= self.CLUSTER_TOL:
                    p, n = out[-1]
                    out[-1] = ((p * n + v) / (n + 1), n + 1)
                else:
                    out.append((v, 1))
            return out

        sup = [(p, n) for p, n in cluster(lows)
               if p < spot * 0.995 and n >= self.MIN_TOUCHES]
        res = [(p, n) for p, n in cluster(highs)
               if p > spot * 1.005 and n >= self.MIN_TOUCHES]
        if not sup or not res:
            return None, None
        return (max(sup, key=lambda t: t[0])[0],
                min(res, key=lambda t: t[0])[0])

    # --------------------------------------------------------------------- arm
    def Arm(self):
        if self.IsWarmingUp:
            return
        # LEAN limits are GoodTilCanceled and never expire on their own, so an
        # unfilled order would rest for months and eventually fill at a price
        # the setup no longer justifies.
        for sym in list(self.live.keys()):
            info = self.live[sym]
            if self.bar - info["armed_bar"] >= self.EXPIRY_DAYS:
                info["ticket"].Cancel("expired unfilled")
                self.live.pop(sym, None)

        room_pos = self.MAX_POSITIONS - len(self.pos)
        room_ord = self.MAX_LIVE_ORDERS - len(self.live)
        room = min(room_pos, room_ord)
        if room <= 0:
            return

        cands = [s for s in self.ok_fund
                 if s != self.spy and s not in self.pos and s not in self.live]
        if not cands:
            return
        hist = self.History(cands, self.LOOKBACK + 5, Resolution.Daily)
        if hist.empty or "high" not in hist.columns:
            return

        picks = []
        for sym in cands:
            sec = self.Securities.get(sym)
            if sec is None or not sec.HasData or not sec.IsTradable:
                continue
            try:
                h = hist.loc[sym]
            except (KeyError, TypeError):
                continue
            if len(h) < self.LOOKBACK - 40:
                continue
            hi = h["high"].to_numpy()
            lo = h["low"].to_numpy()
            spot = float(sec.Price)
            if spot <= 0:
                continue
            S, R = self.Levels(hi, lo, spot)
            if S is None or R is None or R <= S:
                continue
            trig = S + (R - S) / (self.RATIO + 1)
            if trig >= spot:
                continue
            picks.append((sym, trig, R, (spot - trig) / spot))

        # the limits furthest BELOW the market are the ones least likely to
        # fill, so prefer the nearest: an armed order that never fills is
        # reserved cash doing nothing
        picks.sort(key=lambda t: t[3])
        free = float(self.Portfolio.Cash) * self.CASH_USE
        slot = free / max(room, 1)
        for sym, trig, tgt, _ in picks[:room]:
            qty = int(slot / trig)
            if qty < 1:
                continue
            t = self.LimitOrder(sym, qty, round(trig, 2))
            self.live[sym] = {"ticket": t, "target": tgt, "armed_bar": self.bar}
            self.armed += 1

    # ------------------------------------------------------------------ events
    def OnOrderEvent(self, ev):
        if ev.Status != OrderStatus.Filled:
            return
        sym = ev.Symbol
        if sym in self.live:
            info = self.live.pop(sym)
            qty = self.Portfolio[sym].Quantity
            if qty <= 0:
                return
            # the ONLY resting exit is the target. There is no stop, because the
            # stop is what the post-mortem measured as the loss.
            tk = self.LimitOrder(sym, -qty, round(info["target"], 2))
            self.pos[sym] = {"entry": float(ev.FillPrice),
                             "target": info["target"],
                             "bar": self.bar, "ticket": tk}
            self.filled += 1
            return
        if sym in self.pos and not self.Portfolio[sym].Invested:
            p = self.pos.pop(sym)
            self._book(sym, p, float(ev.FillPrice), "target")

    def _book(self, sym, p, px, how):
        ret = (px / p["entry"] - 1) * 100 if p["entry"] else 0.0
        self.r_sum += ret
        self.n_closed += 1
        if how == "target":
            self.hit_target += 1
        else:
            self.timed_out += 1

    # ------------------------------------------------------------- housekeeping
    def Manage(self):
        """Time exits only. Runs before the open, the one window where a market
        order on daily data is accepted."""
        if self.IsWarmingUp:
            return
        for sym in list(self.pos.keys()):
            p = self.pos[sym]
            if self.bar - p["bar"] < self.HOLD_DAYS:
                continue
            if not self.Portfolio[sym].Invested:
                self.pos.pop(sym, None)
                continue
            try:
                p["ticket"].Cancel("time exit")
            except Exception:
                pass
            px = float(self.Securities[sym].Price)
            self.Liquidate(sym, "held 126 days, no stop to wait for")
            self.pos.pop(sym, None)
            self._book(sym, p, px, "time")

    def OnEndOfAlgorithm(self):
        fill = self.filled / max(self.armed, 1) * 100
        avg = self.r_sum / max(self.n_closed, 1)
        self.Log("TRIGGER, NO STOP, FUNDAMENTAL GATE")
        self.Log(f"final {self.Portfolio.TotalPortfolioValue:,.0f}")
        self.Log(f"armed {self.armed}  filled {self.filled} ({fill:.0f}%)")
        self.Log(f"closed {self.n_closed}  target {self.hit_target}  "
                 f"timed out {self.timed_out}")
        self.Log(f"mean return per closed trade {avg:+.2f}%")
        self.Log("LOCAL SAID: no stop, +1.97% mean, +3.28% median per trade.")
        self.Log("WITH a stop it said +0.39% and QC returned -35.6%.")
        self.Log(f"gate: {self.gate_pass} passed, {self.gate_fail} rejected "
                 f"over {self.fine_calls} selections")
        names = ["roa>0", "opmargin>0", "fcf>0", "de<2", "current>1"]
        for i, n in enumerate(names):
            seen = self.leg_seen[i]
            pr = self.leg_pass[i] / seen * 100 if seen else 0.0
            self.Log(f"  leg {n:<12} resolved {seen:>6}  pass {pr:>5.1f}%")
        self.Log("A leg resolving 0 times VOIDS the gate conclusion -- that is")
        self.Log("the exact failure of card 2026-08-31, which graded a score")
        self.Log("whose two trend legs never once populated.")
        self.Log("Judge this against SPY on the Overview tab, not against zero.")
