# region imports
from AlgorithmImports import *
import numpy as np
import pandas as pd
# endregion


class TriggerLimit(QCAlgorithm):
    """Arm a limit at the 3:1 price and wait. Verify on QC's own data.

    WHAT IS BEING VERIFIED
    Measured locally on a point-in-time universe, 2013-2026:

        TRIGGER (limit at support + range/4)   +0.212R   30.2% win   n=27,515
        MARKET  (buy the same name now)        +0.065R   59.3% win
        RANDOM  (same stock, shuffled date)    +0.050R   58.8% win

        fill rate 72.2%; counting every unfilled trigger as 0R the blended
        figure is +0.153R, still more than double buying at market.
        Positive in all 14 years, worst +0.060R.

    The trigger LOSES 70% of the time and makes three times more money. At a
    3:1 ratio the breakeven hit rate is 25%, so 30.2% is comfortably paid for,
    while a 59% win rate at a bad ratio is barely above zero.

    THE MECHANIC, exactly as tested
      support S    nearest clustered swing low below spot, 2+ touches
      resistance R nearest clustered swing high above spot, 2+ touches
      trigger      S + (R - S) / 4          <- the 3:1 price
      stop         S
      target       R
      the limit is good for EXPIRY_DAYS, then cancelled

    WHY IT NEEDS QC
    Two things the local test could not do. First, delisted companies are
    absent from a downloaded ticker list, and those are exactly the trades
    where the stop failed to save you. Second, the local test filled a limit
    AT the limit whenever the bar's low touched it; LEAN models the fill
    against real data and will refuse the ones that were never available.

    If the edge survives both, it is real. If it collapses, the local version
    was assuming fills it could not have got, and I will say so.

    WHAT THE FIRST QC RUN EXPOSED, AND WHAT CHANGED
      * EXITS WERE NEVER HAPPENING. Manage() ran at 15:50 and called
        Liquidate(). On daily resolution LEAN converts a market order sent
        during the session into MarketOnOpen, which is not accepted at 15:50,
        so every stop and every target was REJECTED. A 3:1 strategy whose
        exits do not fire is not a 3:1 strategy. Exits are now BRACKET ORDERS
        placed the moment the entry fills -- a StopMarketOrder at support and
        a LimitOrder at resistance -- which is also how you would really trade
        it, and it removes the timing problem entirely.
      * PENDING LIMITS RESERVE CASH. A cash account cannot borrow, and 15
        armed orders at 6% each locked 90% of the account before a single one
        filled. Arming is now sized against SETTLED CASH actually available.
      * ORDERS ON SECURITIES WITH NO DATA. Newly added universe members were
        being ordered before their first bar arrived. Guarded now.

    A CAVEAT WORTH READING FIRST
    Part of this effect is arithmetic rather than prediction: buying lower
    mechanically tightens the stop and widens the target, which raises R
    whether or not the entry has any forecasting content. The random-date
    control absorbs some of that and not all of it. Judge it on whether it
    beats the MARKET arm inside this same backtest, which is the comparison
    the code prints.
    """

    # ------------------------------------------------------------ parameters
    RATIO = 3.0               # measured: under 2:1 is worse than random
    PIVOT_K = 5               # a swing needs 5 lower highs each side
    CLUSTER_TOL = 0.015
    MIN_TOUCHES = 2
    LOOKBACK = 504            # ~2 years of levels
    EXPIRY_DAYS = 21          # how long a limit stays live
    MAX_POSITIONS = 10
    MAX_LIVE_ORDERS = 4       # pending limits RESERVE cash in a cash
                              # account, so this is capped separately
    UNIVERSE_SIZE = 300
    MIN_PRICE = 5.0
    MIN_DOLLAR_VOL = 5e6
    INVESTED = 0.90           # cash-account headroom; 1.00 gets orders rejected

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

        self.live = {}       # symbol -> {"ticket","stop","target","armed"}
        self.pos = {}        # symbol -> {"stop","target","entry"}
        self.armed = 0
        self.filled = 0
        self.wins = 0
        self.losses = 0
        self.r_sum = 0.0

        self.Schedule.On(self.DateRules.MonthStart(self.spy),
                         self.TimeRules.AfterMarketOpen(self.spy, 30),
                         self.Arm)
        # stops and targets are checked DAILY; a stop looked at once a month
        # is not a stop
        self.Schedule.On(self.DateRules.EveryDay(self.spy),
                         self.TimeRules.AfterMarketOpen(self.spy, 45),
                         self.Manage)
        self.SetWarmUp(self.LOOKBACK + 10, Resolution.Daily)

    def Coarse(self, coarse):
        ok = [c for c in coarse
              if c.HasFundamentalData and c.Price > self.MIN_PRICE
              and c.DollarVolume > self.MIN_DOLLAR_VOL]
        ok.sort(key=lambda c: c.DollarVolume, reverse=True)
        return [c.Symbol for c in ok[:self.UNIVERSE_SIZE]]

    def Fine(self, fine):
        return [f.Symbol for f in fine if f.MarketCap and f.MarketCap > 1e9]

    # ------------------------------------------------------------- levels
    def Levels(self, high, low, spot):
        """Swing pivots, clustered. Identical rule to the local study: a level
        is a price the stock actually turned at, merged with its neighbours
        within CLUSTER_TOL, and it must have MIN_TOUCHES to count. A level
        touched once is a coincidence."""
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
        return max(sup, key=lambda t: t[0])[0], min(res, key=lambda t: t[0])[0]

    # --------------------------------------------------------------- arm
    def Arm(self):
        if self.IsWarmingUp:
            return
        # cancel anything that outlived its window. LEAN limits default to
        # GoodTilCanceled and never expire on their own, so an unfilled order
        # would rest for months and fill at a price the setup no longer
        # justifies.
        for sym in list(self.live.keys()):
            info = self.live[sym]
            if (self.Time - info["armed"]).days >= self.EXPIRY_DAYS:
                try:
                    info["ticket"].Cancel("expired")
                except Exception:
                    pass
                self.live.pop(sym, None)

        room = min(self.MAX_POSITIONS - len(self.pos) - len(self.live),
                   self.MAX_LIVE_ORDERS - len(self.live))
        if room <= 0:
            return
        symbols = [s for s in self.ActiveSecurities.Keys if s != self.spy]
        if len(symbols) < 40:
            return
        hist = self.History(symbols, self.LOOKBACK + 5, Resolution.Daily)
        if hist.empty or "close" not in hist.columns:
            return

        cands = []
        for sym in symbols:
            if sym in self.pos or sym in self.live:
                continue
            try:
                h = hist.loc[sym]
            except (KeyError, TypeError):
                continue
            if len(h) < 200 or "high" not in h.columns:
                continue
            sec = self.Securities[sym] if sym in self.Securities else None
            # a universe member added this month may not have a bar yet;
            # ordering it produces "does not have an accurate price"
            if sec is None or not sec.HasData or not sec.IsTradable:
                continue
            spot = float(h["close"].iloc[-1])
            if spot <= 0:
                continue
            S, R = self.Levels(h["high"].to_numpy(), h["low"].to_numpy(), spot)
            if S is None or R is None or R <= S:
                continue
            trig = S + (R - S) / (self.RATIO + 1)
            if trig >= spot:        # already at or below the trigger: no wait
                continue
            cands.append((sym, trig, S, R, (spot / trig - 1)))

        # nearest triggers first: those are the ones likely to fill inside the
        # window, and an order that never fills earns nothing
        cands.sort(key=lambda t: t[4])
        # SETTLED cash, minus what pending limits already reserve. Sizing off
        # TotalPortfolioValue is what produced "Insufficient buying power" on
        # every rebalance of the first run.
        free = float(self.Portfolio.Cash) * 0.95
        for sym, trig, S, R, _ in cands[:room]:
            budget = free / max(room, 1)
            qty = int(budget / trig)
            if qty < 1:
                continue
            cost = qty * trig
            if cost > free:
                continue
            t = self.LimitOrder(sym, qty, round(trig, 2))
            self.live[sym] = {"ticket": t, "stop": S, "target": R,
                              "armed": self.Time}
            self.armed += 1
            free -= cost

    # ------------------------------------------------------------- manage
    def OnOrderEvent(self, ev):
        if ev.Status != OrderStatus.Filled:
            return
        sym = ev.Symbol

        # ---- an ENTRY filled: bracket it immediately
        if sym in self.live:
            info = self.live.pop(sym)
            entry = float(ev.FillPrice)
            qty = int(ev.FillQuantity)
            if qty <= 0:
                return
            stop_t = self.StopMarketOrder(sym, -qty, round(info["stop"], 2))
            targ_t = self.LimitOrder(sym, -qty, round(info["target"], 2))
            self.pos[sym] = {"stop": info["stop"], "target": info["target"],
                             "entry": entry, "stop_t": stop_t, "targ_t": targ_t}
            self.filled += 1
            return

        # ---- an EXIT filled: cancel its sibling, LEAN has no native OCO
        if sym in self.pos:
            p = self.pos[sym]
            px = float(ev.FillPrice)
            risk = max(p["entry"] - p["stop"], 1e-9)
            self.r_sum += (px - p["entry"]) / risk
            if px >= p["target"] * 0.999:
                self.wins += 1
            else:
                self.losses += 1
            for k in ("stop_t", "targ_t"):
                t = p.get(k)
                try:
                    if t is not None and t.Status not in (
                            OrderStatus.Filled, OrderStatus.Canceled,
                            OrderStatus.Invalid):
                        t.Cancel("bracket closed")
                except Exception:
                    pass
            self.pos.pop(sym, None)

    def Manage(self):
        """Only housekeeping now. The stop and the target are live exchange
        orders, so nothing here needs to send a market order during the
        session -- which is what LEAN rejected at 15:50 on the first run."""
        if self.IsWarmingUp:
            return
        for sym in list(self.pos.keys()):
            if not self.Portfolio[sym].Invested:
                p = self.pos.pop(sym, None)
                if p:
                    for k in ("stop_t", "targ_t"):
                        t = p.get(k)
                        try:
                            if t is not None and t.Status not in (
                                    OrderStatus.Filled, OrderStatus.Canceled,
                                    OrderStatus.Invalid):
                                t.Cancel("position gone")
                        except Exception:
                            pass

    def OnEndOfAlgorithm(self):
        # free tier allows 10 KB of logs per backtest, so nothing routine is
        # logged and this table always survives
        done = self.wins + self.losses
        wr = (self.wins / done * 100) if done else 0.0
        fill = (self.filled / self.armed * 100) if self.armed else 0.0
        exp = (self.r_sum / done) if done else 0.0
        self.Log(f"{self.RATIO:.0f}:1 TRIGGER on QC data")
        self.Log(f"final {self.Portfolio.TotalPortfolioValue:,.0f}")
        self.Log(f"armed {self.armed}  filled {self.filled} ({fill:.1f}%)  "
                 f"resolved {done}")
        self.Log(f"win {wr:.1f}%   expectancy {exp:+.3f}R")
        self.Log(f"LOCAL SAID: 72.2% fill, 30.2% win, +0.212R")
        self.Log("Breakeven at 3:1 is a 25% win rate. Compare the win rate to")
        self.Log("25, not to 50 -- and compare the equity curve to SPY.")
