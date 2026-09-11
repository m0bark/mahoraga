# region imports
from AlgorithmImports import *
import numpy as np
import pandas as pd
# endregion


class Capitulation(QCAlgorithm):
    """Buy the -40% drawdowns. Verify the fear trade on QC's own data.

    WHAT IS BEING VERIFIED
    Measured locally on a point-in-time universe, 50,825 observations:

        drawdown worse than -40%    +4.82% vs random baskets, p=0.000
        -25% to -40%                -0.09%   nothing
        -15% to -25%                -0.04%   nothing
        within 5% of the high       -0.64%,  p=0.017

    It is a THRESHOLD, not a gradient -- nothing happens until -40%. Positive
    in 10 of 14 years, and still +3.47% after removing 2020 and 2022, so it is
    not purely crisis clustering.

    Local data cannot include companies that were DELETED from the index, and
    those are exactly the deep-drawdown names that never came back. That
    omission flatters the result and cannot be fixed with a downloaded ticker
    list. QC's universe selection runs over a security master that includes
    delisted names, which is the entire reason for re-running it here. If the
    edge survives on QC it is real; if it collapses, my version was counting
    only the survivors.

    WHAT THE LOCAL STUDY ALSO FOUND, AND WHY THERE IS NO FUNDAMENTAL FILTER
    Screening for "fundamentals still healthy" made results WORSE: down 20%+
    with revenue growing scored -0.14%, with revenue SHRINKING it scored
    +2.67%. Filings are ~57 days stale and backward-looking while price is
    forward-looking, so a collapsed price beside a healthy last 10-Q means the
    market knows something the filing does not. Depth is the signal. There is
    deliberately no earnings screen here.

    THE COST, which the average hides
    Of 1,626 historical events, 49.7% fell another 10% before recovering and
    23.8% fell another 20%. Average further drawdown after entry: -12.7%.
    MRNA appeared 8 times between -75% and -83% and lost money every time.
    That is why EQUAL WEIGHT and a HARD POSITION CAP matter more here than in
    any other strategy: the winners are enormous, the losers are frequent, and
    single-name concentration is what kills the account before the maths works.
    """

    # ------------------------------------------------------------ parameters
    DD_TRIGGER = -0.40            # the measured threshold; NOT a tuned value
    OFF_LOW_MIN = 0.10            # must be this far ABOVE its own 60-day low
    LOW_WINDOW = 60
    LOOKBACK = 252
    HOLD_DAYS = 63
    MAX_POSITIONS = 20            # the effect is a portfolio effect, not a pick
    UNIVERSE_SIZE = 500
    MIN_PRICE = 3.0
    MIN_DOLLAR_VOL = 5e6
    INVESTED = 0.90               # cash-account headroom
    USE_SPY_FALLBACK = True       # park in SPY when nothing has capitulated

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

        self.held = {}             # symbol -> bar index when bought
        self.bar = 0
        self.n_entries = 0
        self.n_exits = 0
        self.wins = 0
        self.losses = 0
        self.entry_px = {}
        self.entry_spy = {}       # SPY at entry, for the vs-market measurement
        self.deepest = []
        self.months_with_none = 0
        self.months_total = 0
        self.rel_sum = 0.0        # sum of per-trade return minus SPY's
        self.n_rel = 0
        self.cap_weight = []      # how much of the book was NOT SPY

        self.Schedule.On(self.DateRules.MonthStart(self.spy),
                         self.TimeRules.AfterMarketOpen(self.spy, 30),
                         self.Rebalance)
        self.SetWarmUp(self.LOOKBACK + 10, Resolution.Daily)

    def Coarse(self, coarse):
        ok = [c for c in coarse
              if c.HasFundamentalData and c.Price > self.MIN_PRICE
              and c.DollarVolume > self.MIN_DOLLAR_VOL]
        ok.sort(key=lambda c: c.DollarVolume, reverse=True)
        return [c.Symbol for c in ok[:self.UNIVERSE_SIZE]]

    def Fine(self, fine):
        # a real company, not a shell -- but NO earnings or growth screen,
        # because the local study measured that such a screen HURTS
        return [f.Symbol for f in fine if f.MarketCap and f.MarketCap > 5e8]

    def OnData(self, data):
        if not self.IsWarmingUp:
            self.bar += 1

    def Rebalance(self):
        if self.IsWarmingUp:
            return
        self.months_total += 1

        symbols = [s for s in self.ActiveSecurities.Keys if s != self.spy]
        if len(symbols) < 50:
            return
        hist = self.History(symbols, self.LOOKBACK + 5, Resolution.Daily)
        if hist.empty or "close" not in hist.columns:
            return

        # ---- time-based exits. These are COLLECTED, not submitted, because a
        # separate Liquidate() followed by a SetHoldings() is the exact pattern
        # that failed earlier in this project: in a cash account the sale
        # proceeds are unsettled, so the buys that follow are rejected for
        # insufficient buying power. Routing them through the one batched call
        # below lets LEAN order the sells before the buys and net the cash.
        closing = []
        spy_now = float(self.Securities[self.spy].Price)
        for sym in list(self.held.keys()):
            if self.bar - self.held[sym] >= self.HOLD_DAYS:
                if self.Portfolio[sym].Invested:
                    px = float(self.Securities[sym].Price)
                    e = self.entry_px.get(sym, px)
                    if px > e:
                        self.wins += 1
                    else:
                        self.losses += 1
                    # THE NUMBER THAT ACTUALLY TESTS THE CLAIM. The local study
                    # measured +6.08% VERSUS MARKET, not +6.08% absolute. With
                    # idle capital parked in SPY most of the time, a portfolio
                    # result lands near SPY whatever the signal does, so the
                    # tilt has to be measured per trade against SPY over the
                    # same holding window or this backtest proves nothing.
                    e_spy = self.entry_spy.get(sym, 0.0)
                    if e > 0 and e_spy > 0 and spy_now > 0:
                        self.rel_sum += ((px / e - 1.0)
                                         - (spy_now / e_spy - 1.0)) * 100
                        self.n_rel += 1
                    closing.append(sym)
                    self.n_exits += 1
                self.held.pop(sym, None)
                self.entry_px.pop(sym, None)
                self.entry_spy.pop(sym, None)

        # ---- find capitulations, using ONLY the trailing window
        cands = []
        for sym in symbols:
            if sym in self.held:
                continue
            try:
                c = hist.loc[sym]["close"]
            except (KeyError, TypeError):
                continue
            if len(c) < self.LOOKBACK - 20:
                continue
            hi = float(c.max())
            spot = float(c.iloc[-1])
            if hi <= 0 or spot <= 0:
                continue
            dd = spot / hi - 1.0
            if dd > self.DD_TRIGGER:
                continue
            # THE FALLING-KNIFE FILTER. Found by reading individual cases, not
            # averages: MRNA triggered -40% for 25 CONSECUTIVE MONTHS, from
            # -42% down to -83%, and the raw rule said buy every one of them.
            # Splitting all 1,626 historical events by whether price was still
            # making new lows:
            #     still making new lows    +1.12% edge, 60% win  (n=326)
            #     stopped making new lows  +4.41% edge, 67% win  (n=1,300)
            #     ...and 10% off the low   +4.80% edge, 67% win  (n=757)
            # MRNA itself: -17.7% while falling, +2.6% after it stopped.
            # Depth chooses WHICH stock; this chooses WHEN.
            lo = float(c.tail(self.LOW_WINDOW).min())
            if lo <= 0 or (spot / lo - 1.0) < self.OFF_LOW_MIN:
                continue
            cands.append((sym, dd))

        room = self.MAX_POSITIONS - len(self.held)
        if cands and room > 0:
            # DEEPEST first. The local record shows the effect is a threshold
            # rather than a gradient, so this is only a tie-breaker for which
            # names to take when more qualify than there is room for.
            # deepest first, among names that have already turned
            cands.sort(key=lambda t: t[1])
            take = [s for s, _ in cands[:room]]
        else:
            take = []
        self.deepest.append(len(cands))
        if not cands:
            self.months_with_none += 1

        targets = [PortfolioTarget(s, 0) for s in closing]
        n_slots = max(len(self.held) + len(take), 1)
        w = self.INVESTED / max(n_slots, 1)
        n_cap = 0
        for sym in list(self.held.keys()) + take:
            if sym in self.Securities and self.Securities[sym].Price > 0:
                targets.append(PortfolioTarget(sym, w))
                n_cap += 1
        # DILUTION, logged because without it the result is unreadable. If the
        # book is 92% SPY the run comes back near the index no matter what the
        # signal did, and the honest reading is (result - SPY) divided by this
        # weight rather than the headline return.
        self.cap_weight.append(w * n_cap)

        # park the remainder in SPY rather than earn zero: the strategy is
        # idle for long stretches and comparing an idle book to a fully
        # invested index is not a fair test of the signal
        if self.USE_SPY_FALLBACK:
            leftover = max(0.0, self.INVESTED - w * len(targets))
            if leftover > 0.02:
                targets.append(PortfolioTarget(self.spy, leftover))
        elif not targets:
            self.Liquidate()

        if targets:
            # ONE batched call: LEAN orders sells before buys, so freed cash
            # is available in the same pass. Separate calls starve each other
            # and get rejected in a cash account.
            self.SetHoldings(targets)
            for sym in take:
                self.held[sym] = self.bar
                self.entry_px[sym] = float(self.Securities[sym].Price)
                self.entry_spy[sym] = spy_now
                self.n_entries += 1

    def OnEndOfAlgorithm(self):
        # free tier allows 10 KB of logs per backtest -- everything routine is
        # silent so this always survives
        done = self.wins + self.losses
        wr = (self.wins / done * 100) if done else 0.0
        avg = float(np.mean(self.deepest)) if self.deepest else 0.0
        self.Log("CAPITULATION (-40% drawdown) on QC data")
        self.Log(f"final {self.Portfolio.TotalPortfolioValue:,.0f}")
        self.Log(f"entries {self.n_entries}  exits {self.n_exits}  win {wr:.0f}%")
        self.Log(f"avg candidates per month {avg:.1f}  "
                 f"months with none {self.months_with_none}/{self.months_total}")
        rel = self.rel_sum / self.n_rel if self.n_rel else 0.0
        cw = float(np.mean(self.cap_weight)) * 100 if self.cap_weight else 0.0
        self.Log(f"VS MARKET per trade: {rel:+.2f}%  over {self.n_rel} closed")
        self.Log("LOCAL SAID +6.08% vs market, 72% win, n=433. THAT is the")
        self.Log("claim under test -- not the headline return.")
        self.Log(f"average book in capitulation names: {cw:.0f}%  "
                 f"(rest parked in SPY)")
        self.Log("READ IT THIS WAY: if that weight is small the portfolio")
        self.Log("return is mostly SPY and tells you nothing. The vs-market")
        self.Log("figure above is the signal; the headline is mostly beta.")
        self.Log("THE BAR: SPY total return 2013-01 to 2026-09 was +556.7%,")
        self.Log("a CAGR of 14.77%. Not 9%. Judge the equity curve against")
        self.Log("that, and judge the signal against the vs-market line.")
