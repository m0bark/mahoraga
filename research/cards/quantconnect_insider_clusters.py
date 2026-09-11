# region imports
from AlgorithmImports import *
from collections import deque
import io
import csv
# endregion
#
# INSIDER CLUSTER BUYS — Sentinel run for card 2026-08-28-insider-clusters.
#
# Reads cluster_buys.csv (13,562 events from the complete SEC Form 4
# archive, built locally from DERA data) out of the QC OBJECT STORE, and
# trades each event: subscribe on the fly (QC maps delisted tickers ->
# survivorship handled), buy next open after the filing date, equal weight,
# max 50 concurrent, exit after 126 trading days.
#
# SETUP (one time): in the QC web IDE open the Object Store tab and upload
# cluster_buys.csv with key exactly:  insider_clusters.csv
#
# TWO RUNS, both pre-registered on the card:
#   Run A: SHIFT_DAYS = 0    (the real signal)
#   Run B: SHIFT_DAYS = 365  (placebo: same events one year later)
# GATES: A.Alpha > 0;  A.Alpha - B.Alpha >= 0.02;  A.IR > 0.
# Period 2007-01-01..2022-12-31; 2023+ reserved as the family holdout.


class InsiderClusterBridge(QCAlgorithm):

    SHIFT_DAYS = 0        # <-- set to 365 for the placebo run, nothing else
    HOLD_BARS = 126
    MAX_POSITIONS = 50
    WEIGHT = 0.019
    OBJECT_KEY = "insider_clusters.csv"

    def initialize(self):
        self.set_start_date(2007, 1, 1)
        self.set_end_date(2022, 12, 31)
        self.set_cash(100_000)
        self.set_benchmark(self.add_equity("SPY", Resolution.DAILY).symbol)

        raw = self.object_store.read(self.OBJECT_KEY)
        if not raw:
            raise ValueError(f"Object Store key '{self.OBJECT_KEY}' is empty "
                             "— upload cluster_buys.csv first")
        self.events_by_date: dict = {}
        n = 0
        for row in csv.DictReader(io.StringIO(raw)):
            try:
                d = datetime.strptime(row["date"][:10], "%Y-%m-%d") \
                    + timedelta(days=self.SHIFT_DAYS)
            except Exception:
                continue
            self.events_by_date.setdefault(d.date(), []).append(
                row["symbol"].strip().upper())
            n += 1
        self.log(f"loaded {n} cluster events, SHIFT_DAYS={self.SHIFT_DAYS}")

        self.pending: list = []              # symbols subscribed, awaiting first bar
        self.positions: dict = {}            # symbol -> bars held
        self.stats = {"fired": 0, "mapped": 0, "entered": 0}

    def on_data(self, data: Slice):
        # age positions on their own bars; exit at HOLD_BARS
        for symbol in list(self.positions):
            if symbol in data.bars:
                self.positions[symbol] += 1
                if self.positions[symbol] >= self.HOLD_BARS:
                    qty = self.portfolio[symbol].quantity
                    if qty != 0:
                        self.market_on_open_order(symbol, -qty)
                    del self.positions[symbol]

        # enter pending symbols once their data is flowing
        still_pending = []
        for symbol in self.pending:
            if symbol in data.bars and self.securities[symbol].price > 0:
                if (len(self.positions) < self.MAX_POSITIONS
                        and symbol not in self.positions):
                    price = float(data.bars[symbol].close)
                    qty = int(self.portfolio.total_portfolio_value
                              * self.WEIGHT / price)
                    if qty > 0:
                        self.market_on_open_order(symbol, qty)
                        self.positions[symbol] = 0
                        self.stats["entered"] += 1
            else:
                still_pending.append(symbol)
        self.pending = still_pending[-200:]   # drop stale unmappable names

        # fire today's events: subscribe; entry happens when data arrives
        for ticker in self.events_by_date.pop(self.time.date(), []):
            self.stats["fired"] += 1
            if len(self.positions) + len(self.pending) > self.MAX_POSITIONS + 20:
                continue
            try:
                security = self.add_equity(ticker, Resolution.DAILY)
                self.stats["mapped"] += 1
                if security.symbol not in self.positions:
                    self.pending.append(security.symbol)
            except Exception:
                pass   # ticker QC cannot map — counted via fired-mapped gap

    def on_delistings(self, delistings):
        for symbol in delistings.keys():
            self.positions.pop(symbol, None)

    def on_end_of_algorithm(self):
        self.log(f"==== INSIDER CLUSTERS (SHIFT_DAYS={self.SHIFT_DAYS}) ====")
        self.log(f"events fired={self.stats['fired']}  "
                 f"mapped by QC={self.stats['mapped']}  "
                 f"entered={self.stats['entered']}")
        self.log("Gates read off the scoreboard: Run A Alpha > 0; "
                 "A.Alpha - B.Alpha >= 0.02; A IR > 0.")
