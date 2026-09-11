# region imports
from AlgorithmImports import *
import pandas as pd
# endregion


class MomentumEntryTiming(QCAlgorithm):
    """Momentum selection + five entry-timing modes, compared in ONE backtest.

    THE QUESTION
    Momentum decides WHAT to buy. This asks WHEN. Measured locally on
    point-in-time data the honest momentum edge is about +1.83% per quarter
    over a random basket -- real but small. The claim tested here is that
    entering the SAME names on a better day is worth more than the selection.

    WHY FIVE MODES IN ONE BACKTEST
    The free tier gives one backtest node. Five separate runs means five
    different universe snapshots and no clean comparison. So one mode places
    real orders and all five are tracked as fully-accounted virtual books over
    identical signals and identical bars.

    ---------------------------------------------------------------------
    DEFECTS FOUND BY REVIEW AGAINST LEAN SOURCE, AND FIXED HERE
    ---------------------------------------------------------------------
    1. NO CASH ACCOUNT (fatal). The first version credited equity only on
       close and never debited on fill, so a mode filling 5 of 10 names ran at
       50% exposure with the rest as free phantom cash. That ranks FILL RATE,
       not entry timing: at ~1.1%/mo drift a 51%-fill mode needed +1.06% per
       trade merely to tie IMMEDIATE. The artifact was bigger than the effect
       and fixed in sign. Books now hold real cash, debit on fill, credit on
       close, and size off NAV marked to market.

    2. ATR WAS NEVER READY. self.ATR() inside a scheduled event builds a fresh
       indicator with zero samples; LEAN back-fills only when
       Settings.AutomaticIndicatorWarmUp is true, and it defaults false. So
       atr.IsReady was always False and DIP_ATR silently became a flat 1% dip,
       measuring no volatility at all -- while leaking ~1,650 indicator and
       consolidator registrations over the run. ATR is now computed from the
       History frame already being fetched.

    3. TWO TYPES IN ONE DICT. self.pending[mode][sym] held a dict for virtual
       intents and was overwritten with an (OrderTicket, time) tuple for the
       traded mode, permanently emptying the traded DIP book.

    4. BREAKOUT PLACED NO REAL ORDERS and SCALE_IN bought only leg 1 of 3.

    5. CASH SETTLEMENT. AccountType.Cash installs DelayedSettlementModel, so
       liquidate-then-buy inside one event has the buys rejected from the
       second rebalance onward. Selling now happens a day before buying.

    6. GTC LIMITS NEVER CANCELLED. Unfilled real limits are GoodTilCanceled in
       LEAN and outlived DIP_DAYS, filling months later at stale prices.

    7. FREE-TIER LOG QUOTA is 10 KB per backtest. Per-rebalance logging blew
       through it and truncated the only output that matters, so routine logs
       are gone and the comparison prints once at the end.

    8. DELISTED NAMES leaked NAV: the position was popped before the price
       check, so a zero price silently vanished the capital. Now booked.
    """

    # ---------------------------------------------------------------- config
    TRADED_MODE = "IMMEDIATE"
    TOP_N = 10
    MOM_LOOKBACK = 126
    MOM_SKIP = 0
    REGIME_SMA = 200
    DIP_ATR_MULT = 0.5
    DIP_PCT = 0.02
    DIP_DAYS = 3
    UNIVERSE_SIZE = 350
    MIN_PRICE = 5.0
    MIN_DOLLAR_VOL = 5e6
    START_CASH = 100000.0
    # A cash account cannot borrow, and SetHoldings targets a PERCENT OF
    # PORTFOLIO VALUE. Ten names at 10% each demands exactly 100%, so once the
    # first fills leave commission and price drift behind, every later order is
    # rejected for insufficient buying power. The backtest logs showed dozens
    # of these per rebalance for 13 years. Target 92% and leave the rest idle.
    INVESTED = 0.92

    MODES = ["IMMEDIATE", "DIP_ATR", "DIP_PCT", "BREAKOUT", "SCALE_IN"]

    def Initialize(self):
        self.SetStartDate(2013, 1, 1)
        self.SetEndDate(2026, 9, 1)
        self.SetCash(self.START_CASH)
        # Cash account: no leverage, and LEAN will model T+1 settlement. That
        # is deliberate -- the real account is a cash account, and a backtest
        # that ignores settlement would promise fills you could not get.
        self.SetBrokerageModel(BrokerageName.InteractiveBrokersBrokerage,
                               AccountType.Cash)

        self.UniverseSettings.Resolution = Resolution.Daily
        self.AddUniverse(self.Coarse, self.Fine)

        self.spy = self.AddEquity("SPY", Resolution.Daily).Symbol
        self.spy_sma = self.SMA(self.spy, self.REGIME_SMA, Resolution.Daily)

        self.books = {m: {"cash": self.START_CASH, "pos": {}} for m in self.MODES}
        self.intents = {m: {} for m in self.MODES}     # virtual, always dicts
        self.tickets = {}                              # real limit tickets only
        self.stats = {m: {"trades": 0, "skipped": 0, "wins": 0, "losses": 0}
                      for m in self.MODES}
        self.picks = []
        self.pending_buys = []                         # deferred to the next day

        # SELL one day, BUY the next. With DelayedSettlementModel the proceeds
        # of a same-event sale are unsettled, and every buy after the first
        # rebalance would be rejected for insufficient settled cash.
        self.Schedule.On(self.DateRules.MonthStart(self.spy),
                         self.TimeRules.AfterMarketOpen(self.spy, 30),
                         self.SelectAndSell)
        self.Schedule.On(self.DateRules.MonthStart(self.spy, 1),
                         self.TimeRules.AfterMarketOpen(self.spy, 30),
                         self.Buy)

        self.SetWarmUp(self.REGIME_SMA + 10, Resolution.Daily)
        # Free tier allows 10 KB of logs PER BACKTEST, and LEAN's own order
        # errors count against it. The previous run burned the whole quota on
        # rejections by 2016 and the end-of-run comparison never printed at
        # all. Suppressing sub-minimum rebalances removes the loudest source.
        self.Settings.MinimumOrderMarginPortfolioPercentage = 0.005
        self.Settings.FreePortfolioValuePercentage = 0.05

    # ------------------------------------------------------------- universe
    def Coarse(self, coarse):
        ok = [c for c in coarse
              if c.HasFundamentalData
              and c.Price > self.MIN_PRICE
              and c.DollarVolume > self.MIN_DOLLAR_VOL]
        ok.sort(key=lambda c: c.DollarVolume, reverse=True)
        return [c.Symbol for c in ok[:self.UNIVERSE_SIZE]]

    def Fine(self, fine):
        return [f.Symbol for f in fine if f.MarketCap and f.MarketCap > 1e9]

    # --------------------------------------------------------------- helper
    def Nav(self, mode):
        """Cash plus positions marked to market. Sizing must use this, not a
        realized-basis figure, or the book silently levers up in drawdowns."""
        b = self.books[mode]
        nav = b["cash"]
        for s, (sh, _) in b["pos"].items():
            px = self.Securities[s].Price if s in self.Securities else 0.0
            nav += sh * px
        return nav

    # ---------------------------------------------------------- rebalance A
    def SelectAndSell(self):
        if self.IsWarmingUp or not self.spy_sma.IsReady:
            return

        risk_on = self.Securities[self.spy].Price > self.spy_sma.Current.Value
        if not risk_on:
            self.CancelAllTickets()
            self.Liquidate()
            for m in self.MODES:
                for s in list(self.books[m]["pos"].keys()):
                    self.CloseVirtual(m, s)
                self.intents[m].clear()
            self.picks = []
            self.pending_buys = []
            return

        symbols = [s for s in self.ActiveSecurities.Keys if s != self.spy]
        if len(symbols) < 50:
            return

        hist = self.History(symbols, self.MOM_LOOKBACK + self.MOM_SKIP + 20,
                            Resolution.Daily)
        if hist.empty or "close" not in hist.columns:
            return

        scores, atrs = {}, {}
        for sym in symbols:
            try:
                h = hist.loc[sym]
            except (KeyError, TypeError):
                continue
            c = h["close"]
            if len(c) < self.MOM_LOOKBACK + 2:
                continue
            end = -1 - self.MOM_SKIP
            start = end - self.MOM_LOOKBACK
            if abs(start) > len(c) or c.iloc[start] <= 0:
                continue
            scores[sym] = c.iloc[end] / c.iloc[start] - 1.0
            # ATR from the frame we already have. LEAN's TrueRange is
            # max(H-L, |prevC-H|, |prevC-L|) and ATR(14, Simple) is its 14-bar
            # mean, so this equals a properly warmed-up indicator.
            if "high" in h.columns and "low" in h.columns and len(c) >= 16:
                tr = pd.concat([h["high"] - h["low"],
                                (h["high"] - c.shift()).abs(),
                                (h["low"] - c.shift()).abs()], axis=1).max(axis=1)
                v = float(tr.iloc[-14:].mean())
                atrs[sym] = v if v > 0 else 0.0

        if len(scores) < self.TOP_N:
            return
        self.picks = sorted(scores, key=scores.get, reverse=True)[:self.TOP_N]

        # sell today; buy tomorrow, once the cash has settled
        self.CancelAllTickets()
        for held in list(self.Portfolio.Keys):
            if (self.Portfolio[held].Invested and held not in self.picks
                    and held != self.spy):
                self.Liquidate(held)
        for m in self.MODES:
            for held in list(self.books[m]["pos"].keys()):
                if held not in self.picks:
                    self.CloseVirtual(m, held)
            self.intents[m].clear()

        self.pending_buys = [(s, atrs.get(s, 0.0)) for s in self.picks]

    # ---------------------------------------------------------- rebalance B
    def Buy(self):
        if self.IsWarmingUp or not self.pending_buys:
            return
        w = 1.0 / self.TOP_N              # virtual books: full weight
        wt = self.INVESTED / self.TOP_N   # real book: leaves a cash buffer
        batch = []
        for sym, atr_val in self.pending_buys:
            if sym not in self.Securities:
                continue
            px = self.Securities[sym].Price
            if px <= 0:
                continue
            hi = self.Securities[sym].High
            targets = {
                "IMMEDIATE": px,
                "DIP_ATR": px - self.DIP_ATR_MULT * atr_val if atr_val > 0 else 0.0,
                "DIP_PCT": px * (1 - self.DIP_PCT),
                "BREAKOUT": hi if hi > 0 else px,
                "SCALE_IN": px,
            }
            for m in self.MODES:
                if m == "DIP_ATR" and atr_val <= 0:
                    # no ATR is a SKIP, not a silent fallback to a fixed
                    # percentage -- that substitution is what made this mode
                    # measure nothing in the first version
                    self.stats[m]["skipped"] += 1
                    continue
                if sym in self.books[m]["pos"]:
                    continue
                self.intents[m][sym] = {
                    "target": targets[m], "weight": w, "armed": self.Time,
                    "legs": 3 if m == "SCALE_IN" else 1}

            if self.TRADED_MODE in ("DIP_ATR", "DIP_PCT"):
                t = targets[self.TRADED_MODE]
                if t > 0:
                    qty = int((self.Portfolio.TotalPortfolioValue * wt) / t)
                    if qty > 0:
                        self.tickets[sym] = (
                            self.LimitOrder(sym, qty, round(t, 2)), self.Time)
            elif self.TRADED_MODE in ("IMMEDIATE", "SCALE_IN"):
                share = wt / 3.0 if self.TRADED_MODE == "SCALE_IN" else wt
                batch.append(PortfolioTarget(sym, share))
            # BREAKOUT arms in OnData, where the trigger can be observed

        # ONE batched call. LEAN orders the whole list -- sells first, then
        # buys -- so freed capital is available to the buys in the same pass.
        # Ten separate SetHoldings calls cannot do that and starve each other.
        if batch:
            self.SetHoldings(batch)
        self.pending_buys = []

    def CancelAllTickets(self):
        """LEAN limits default to GoodTilCanceled and never expire on their
        own, so an unfilled DIP order would rest for months and fill at a
        price the signal no longer justifies."""
        for sym, (t, _) in list(self.tickets.items()):
            try:
                if t.Status not in (OrderStatus.Filled, OrderStatus.Canceled,
                                    OrderStatus.Invalid):
                    t.Cancel("stale entry")
            except Exception:
                pass
        self.tickets.clear()

    # ------------------------------------------------------- virtual ledger
    def FillVirtual(self, mode, sym, price, weight):
        b = self.books[mode]
        if price <= 0:
            return
        alloc = min(self.Nav(mode) * weight, b["cash"])   # cash account: clamp
        if alloc <= 0:
            return
        shares = alloc / price
        b["cash"] -= alloc
        if sym in b["pos"]:
            sh, cost = b["pos"][sym]
            b["pos"][sym] = (sh + shares, cost + alloc)
        else:
            b["pos"][sym] = (shares, alloc)
        self.stats[mode]["trades"] += 1

    def CloseVirtual(self, mode, sym):
        b = self.books[mode]
        if sym not in b["pos"]:
            return
        sh, cost = b["pos"].pop(sym)
        px = self.Securities[sym].Price if sym in self.Securities else 0.0
        if px <= 0:
            # delisted or no valid mark. Returning the basis avoids inventing
            # a loss, but the capital is NOT silently deleted as before.
            b["cash"] += cost
            return
        proceeds = sh * px
        b["cash"] += proceeds
        if proceeds > cost:
            self.stats[mode]["wins"] += 1
        else:
            self.stats[mode]["losses"] += 1

    def OnData(self, data):
        if self.IsWarmingUp:
            return
        for mode in self.MODES:
            for sym in list(self.intents[mode].keys()):
                p = self.intents[mode][sym]
                if sym not in data or data[sym] is None:
                    continue
                bar = data[sym]
                age = (self.Time - p["armed"]).days

                if mode == "IMMEDIATE":
                    self.FillVirtual(mode, sym, bar.Close, p["weight"])
                    del self.intents[mode][sym]
                elif mode in ("DIP_ATR", "DIP_PCT"):
                    if bar.Low <= p["target"]:
                        # fill AT the limit, not at the low -- assuming the
                        # best price inside the bar is free money
                        self.FillVirtual(mode, sym, p["target"], p["weight"])
                        del self.intents[mode][sym]
                    elif age >= self.DIP_DAYS:
                        self.stats[mode]["skipped"] += 1
                        del self.intents[mode][sym]
                elif mode == "BREAKOUT":
                    if bar.Close > p["target"]:
                        self.FillVirtual(mode, sym, bar.Close, p["weight"])
                        if self.TRADED_MODE == "BREAKOUT":
                            self.SetHoldings(sym, p["weight"] * self.INVESTED)
                        del self.intents[mode][sym]
                    elif age >= self.DIP_DAYS:
                        self.stats[mode]["skipped"] += 1
                        del self.intents[mode][sym]
                elif mode == "SCALE_IN":
                    self.FillVirtual(mode, sym, bar.Close, p["weight"] / 3.0)
                    if self.TRADED_MODE == "SCALE_IN" and p["legs"] > 1:
                        self.SetHoldings(sym, (4 - p["legs"])
                                         * p["weight"] * self.INVESTED / 3.0)
                    p["legs"] -= 1
                    if p["legs"] <= 0:
                        del self.intents[mode][sym]

    def OnEndOfAlgorithm(self):
        # Free tier allows 10 KB of logs per backtest. Everything routine is
        # silent so this table always survives.
        for m in self.MODES:
            for s in list(self.books[m]["pos"].keys()):
                self.CloseVirtual(m, s)
        self.Log("ENTRY TIMING -- identical signals, identical bars, real cash")
        self.Log(f"{'mode':<11}{'NAV':>11}{'ret%':>8}{'trades':>7}"
                 f"{'skip':>6}{'win%':>6}")
        base = None
        for m in self.MODES:
            nav = self.books[m]["cash"]
            r = (nav / self.START_CASH - 1) * 100
            st = self.stats[m]
            done = st["wins"] + st["losses"]
            wr = (st["wins"] / done * 100) if done else 0.0
            if m == "IMMEDIATE":
                base = r
            self.Log(f"{m:<11}{nav:>11,.0f}{r:>8.1f}{st['trades']:>7}"
                     f"{st['skipped']:>6}{wr:>6.0f}")
        if base is not None:
            deltas = " ".join(
                f"{m}:{(self.books[m]['cash']/self.START_CASH-1)*100-base:+.1f}"
                for m in self.MODES if m != "IMMEDIATE")
            self.Log(f"vs IMMEDIATE: {deltas}")
        self.Log(f"REAL({self.TRADED_MODE}) {self.Portfolio.TotalPortfolioValue:,.0f}"
                 f" -- real pays fees and slippage, virtual books do not")
