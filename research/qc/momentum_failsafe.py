# region imports
from AlgorithmImports import *
import numpy as np
import pandas as pd
# endregion


class MomentumFailsafe(QCAlgorithm):
    """Momentum with three circuit breakers and a mean-reversion arm.

    THE PROBLEM THIS EXISTS TO FIX
    Plain top-10 momentum on QC returned 166% over 2013-2026 with a 64.7%
    drawdown while SPY returned 538% with 33.7%. Losing to the index is bad;
    losing to it while suffering twice the drawdown is disqualifying. And the
    S&P has no such problem because it holds 500 names including defensives --
    a concentrated momentum book has nothing to fall back on. So the fallback
    has to be built.

    THE THREE BREAKERS, in the order they fire

    1. VOLATILITY TARGETING  (Barroso & Santa-Clara 2015)
       Momentum's crashes are preceded by RISING momentum-portfolio volatility,
       which is forecastable in a way returns are not. Exposure is scaled to
       TARGET_VOL / realised_vol, capped at 1.0 because a cash account cannot
       lever. In calm markets that is fully invested; in turbulent ones it
       automatically halves or quarters the book BEFORE the damage.

    2. PORTFOLIO DRAWDOWN CIRCUIT BREAKER
       If equity falls MAX_DD from its own high-water mark, everything is sold
       and the algorithm refuses to re-enter until BOTH the market is back
       above its 200-day average AND equity has recovered RE_ARM of the fall.
       A stop that re-enters immediately is not a stop, it is a whipsaw
       generator.

    3. PER-POSITION ATR STOP
       Each holding carries a 2.5-ATR stop from its entry. One name blowing up
       cannot take the book with it.

    THE MEAN-REVERSION ARM
    When the regime is risk-off, the first version sat in cash and earned zero
    for years at a time. Instead it now runs SHORT-TERM REVERSAL, which is the
    documented behaviour of that regime: buy the WORST 1-month performers among
    large, liquid, LOW-VOLATILITY names, hold one month. Reversal and momentum
    are close to uncorrelated, and reversal historically works best in exactly
    the high-volatility periods where momentum breaks.

    This is deliberately the opposite trade to the main book, run at half
    weight, and only when momentum is switched off.

    HONEST WARNING
    Every one of these is a rule added AFTER seeing momentum fail, which is the
    textbook route to an overfitted backtest. Judge it on the drawdown and the
    Sharpe, not the return -- and treat any improvement in return as suspect
    until it survives a period this design has never seen.
    """

    # ------------------------------------------------------------ parameters
    TOP_N = 10
    MOM_LOOKBACK = 126
    REGIME_SMA = 200
    UNIVERSE_SIZE = 350
    MIN_PRICE = 5.0
    MIN_DOLLAR_VOL = 5e6
    INVESTED = 0.92               # cash-account headroom; 1.00 gets orders rejected

    TARGET_VOL = 0.15             # annualised portfolio vol we aim at
    VOL_LOOKBACK = 63
    MIN_EXPOSURE = 0.25           # never scale below this while risk-on

    MAX_DD = 0.20                 # circuit breaker trips here
    RE_ARM = 0.50                 # and needs half the fall back to reset

    STOP_ATR = 2.5
    REVERSAL_N = 10               # names in the mean-reversion book
    REVERSAL_WEIGHT = 0.50        # run it at half size: it is the defensive arm

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
        self.spy_sma = self.SMA(self.spy, self.REGIME_SMA, Resolution.Daily)

        self.peak = 100000.0
        self.halted = False
        self.halt_level = 0.0
        self.entry = {}            # symbol -> (entry price, stop price)
        self.mode = "MOMENTUM"
        self.counts = {"MOMENTUM": 0, "REVERSAL": 0, "HALTED": 0, "CASH": 0}
        self.exposures = []
        self.stop_hits = 0
        self.breaker_trips = 0

        self.Schedule.On(self.DateRules.MonthStart(self.spy),
                         self.TimeRules.AfterMarketOpen(self.spy, 30),
                         self.Rebalance)
        # the breakers are checked DAILY, not monthly -- a stop that only looks
        # once a month is not a stop
        self.Schedule.On(self.DateRules.EveryDay(self.spy),
                         self.TimeRules.BeforeMarketClose(self.spy, 15),
                         self.CheckBreakers)

        self.SetWarmUp(self.REGIME_SMA + 10, Resolution.Daily)

    # -------------------------------------------------------------- universe
    def Coarse(self, coarse):
        ok = [c for c in coarse
              if c.HasFundamentalData and c.Price > self.MIN_PRICE
              and c.DollarVolume > self.MIN_DOLLAR_VOL]
        ok.sort(key=lambda c: c.DollarVolume, reverse=True)
        return [c.Symbol for c in ok[:self.UNIVERSE_SIZE]]

    def Fine(self, fine):
        return [f.Symbol for f in fine if f.MarketCap and f.MarketCap > 1e9]

    # -------------------------------------------------------------- breakers
    def CheckBreakers(self):
        if self.IsWarmingUp:
            return
        eq = self.Portfolio.TotalPortfolioValue
        self.peak = max(self.peak, eq)
        dd = eq / self.peak - 1.0

        # BREAKER 2: portfolio drawdown
        if not self.halted and dd <= -self.MAX_DD:
            self.halted = True
            self.halt_level = eq
            self.breaker_trips += 1
            self.Liquidate()
            self.entry.clear()
            return
        if self.halted:
            back = self.Securities[self.spy].Price > self.spy_sma.Current.Value \
                if self.spy_sma.IsReady else False
            recovered = eq >= self.halt_level + (self.peak - self.halt_level) * self.RE_ARM
            # BOTH conditions: a stop that re-enters on price alone whipsaws
            if back and recovered:
                self.halted = False
                self.peak = eq
            return

        # BREAKER 3: per-position ATR stop
        for sym in list(self.entry.keys()):
            if not self.Portfolio[sym].Invested:
                self.entry.pop(sym, None)
                continue
            px = self.Securities[sym].Price
            _, stop = self.entry[sym]
            if px > 0 and px <= stop:
                self.Liquidate(sym)
                self.entry.pop(sym, None)
                self.stop_hits += 1

    # ------------------------------------------------------------- exposure
    def VolScale(self, hist, picks):
        """BREAKER 1. Scale to TARGET_VOL / realised vol of an equal-weight
        book of the picks. Capped at 1.0 -- a cash account cannot lever, so
        this can only ever reduce risk, never add it."""
        try:
            rets = []
            for s in picks:
                c = hist.loc[s]["close"]
                if len(c) > self.VOL_LOOKBACK:
                    rets.append(c.pct_change().tail(self.VOL_LOOKBACK))
            if not rets:
                return self.INVESTED
            port = pd.concat(rets, axis=1).mean(axis=1)
            vol = float(port.std() * np.sqrt(252))
            if vol <= 0:
                return self.INVESTED
            scale = min(1.0, self.TARGET_VOL / vol)
            return max(self.MIN_EXPOSURE, scale) * self.INVESTED
        except Exception:
            return self.INVESTED

    # ------------------------------------------------------------ rebalance
    def Rebalance(self):
        if self.IsWarmingUp or not self.spy_sma.IsReady or self.halted:
            if self.halted:
                self.counts["HALTED"] += 1
            return

        symbols = [s for s in self.ActiveSecurities.Keys if s != self.spy]
        if len(symbols) < 50:
            return
        hist = self.History(symbols, self.MOM_LOOKBACK + 20, Resolution.Daily)
        if hist.empty or "close" not in hist.columns:
            return

        risk_on = self.Securities[self.spy].Price > self.spy_sma.Current.Value

        mom, rev, atrs = {}, {}, {}
        for sym in symbols:
            try:
                h = hist.loc[sym]
            except (KeyError, TypeError):
                continue
            c = h["close"]
            if len(c) < self.MOM_LOOKBACK + 2 or c.iloc[-self.MOM_LOOKBACK] <= 0:
                continue
            mom[sym] = c.iloc[-1] / c.iloc[-self.MOM_LOOKBACK] - 1.0
            if len(c) > 22 and c.iloc[-22] > 0:
                v = float(c.pct_change().tail(63).std() * np.sqrt(252))
                # reversal candidates must be CALM as well as beaten down;
                # the worst performer in a high-vol name is usually broken,
                # not oversold
                if 0 < v < 0.45:
                    rev[sym] = c.iloc[-1] / c.iloc[-22] - 1.0
            if "high" in h.columns and "low" in h.columns and len(c) >= 16:
                tr = pd.concat([h["high"] - h["low"],
                                (h["high"] - c.shift()).abs(),
                                (h["low"] - c.shift()).abs()], axis=1).max(axis=1)
                atrs[sym] = float(tr.iloc[-14:].mean())

        if risk_on and len(mom) >= self.TOP_N:
            picks = sorted(mom, key=mom.get, reverse=True)[:self.TOP_N]
            exposure = self.VolScale(hist, picks)
            self.mode = "MOMENTUM"
            self.counts["MOMENTUM"] += 1
        elif (not risk_on) and len(rev) >= self.REVERSAL_N:
            # THE MEAN-REVERSION ARM. Worst 1-month performers among calm,
            # liquid names. Momentum is off; sitting in cash for years earns
            # nothing, and short-term reversal is what this regime pays.
            picks = sorted(rev, key=rev.get)[:self.REVERSAL_N]
            exposure = self.INVESTED * self.REVERSAL_WEIGHT
            self.mode = "REVERSAL"
            self.counts["REVERSAL"] += 1
        else:
            self.Liquidate()
            self.entry.clear()
            self.counts["CASH"] += 1
            return

        self.exposures.append(exposure)
        for held in list(self.Portfolio.Keys):
            if self.Portfolio[held].Invested and held not in picks and held != self.spy:
                self.Liquidate(held)
                self.entry.pop(held, None)

        w = exposure / len(picks)
        batch = []
        for s in picks:
            if s not in self.Securities or self.Securities[s].Price <= 0:
                continue
            batch.append(PortfolioTarget(s, w))
        if batch:
            # ONE batched call: LEAN sells before it buys, so freed capital is
            # available in the same pass. Ten separate SetHoldings calls starve
            # each other and get rejected in a cash account.
            self.SetHoldings(batch)
            for s in picks:
                px = self.Securities[s].Price if s in self.Securities else 0
                a = atrs.get(s, px * 0.03)
                if px > 0:
                    self.entry[s] = (px, px - self.STOP_ATR * a)

    def OnEndOfAlgorithm(self):
        avg = float(np.mean(self.exposures)) if self.exposures else 0.0
        self.Log("MOMENTUM + FAILSAFE")
        self.Log(f"final {self.Portfolio.TotalPortfolioValue:,.0f} "
                 f"peak {self.peak:,.0f}")
        self.Log(f"months: mom {self.counts['MOMENTUM']} rev {self.counts['REVERSAL']}"
                 f" halted {self.counts['HALTED']} cash {self.counts['CASH']}")
        self.Log(f"avg exposure {avg*100:.0f}%  breaker trips {self.breaker_trips}"
                 f"  ATR stops hit {self.stop_hits}")
