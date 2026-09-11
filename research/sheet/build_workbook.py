"""Assemble the dashboard: 10 sheets, formatted, plus CSVs for Power Query.

    python research/sheet/build_workbook.py

Writes BOTH:
  * cache/*.csv          -- what Excel's Power Query points at, so the sheet
                            can refresh itself hourly while you have it open
  * sp500_dashboard.xlsx -- a standalone snapshot for when you just want one
                            file to double-click

The .xlsx write is attempted last and failure is non-fatal: if the workbook is
open in Excel the file is locked, the CSVs are already on disk, and Power
Query will pick the new numbers up on its next refresh anyway.
"""
from __future__ import annotations

import io
import os
import sys
import warnings

_OUT = io.TextIOWrapper(open(sys.stdout.fileno(), "wb", closefd=False),
                        encoding="utf-8", errors="replace")


def say(*a) -> None:
    print(*a, file=_OUT)
    _OUT.flush()


warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
from openpyxl.formatting.rule import CellIsRule, ColorScaleRule
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

import importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
_w = importlib.util.spec_from_file_location("wd", os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "why_detail.py"))
wd = importlib.util.module_from_spec(_w)
_w.loader.exec_module(wd)
_e = importlib.util.spec_from_file_location("enc", os.path.join(
    HERE, "encyclopedia.py"))
enc = importlib.util.module_from_spec(_e)
_e.loader.exec_module(enc)
_s = importlib.util.spec_from_file_location("cp", os.path.join(HERE, "compute.py"))
cp = importlib.util.module_from_spec(_s)
_s.loader.exec_module(cp)

CACHE = os.path.join(HERE, "cache")
XLSX = os.path.join(HERE, "sp500_dashboard.xlsx")
HDR_FILL = PatternFill("solid", fgColor="1F3864")
HDR_FONT = Font(color="FFFFFF", bold=True, size=10)
BAND = PatternFill("solid", fgColor="F2F6FB")          # zebra striping
TAB_COLORS = {"Encyclopedia": "7030A0", "Summary": "1F3864",
              "Technicals": "2E75B6", "Fundamentals": "2E75B6",
              "Macro": "548235", "WhyItMoved": "548235",
              "Momentum": "00B050", "BigMoney": "BF8F00",
              "Analysts": "C00000", "BuyZone": "C00000"}
VERDICT_FILL = {"WORKS": "C6EFCE", "FAILS": "FFC7CE",
                "PROBATION": "FFEB9C", "INFO": None}
VERDICT_FONT = {"WORKS": "006100", "FAILS": "9C0006",
                "PROBATION": "7F6000", "INFO": None}
# a distinct colour per section so the eye can find its place while
# scrolling 100 rows of prose; cycled in order, not chosen per topic
SECTION_COLORS = ["1F3864", "7030A0", "C00000", "BF8F00", "548235",
                  "0070C0", "9E480E", "2E75B6", "833C00", "375623",
                  "7B1FA2", "00639B", "AD1457", "4527A0"]
SECTION_TINT = ["EAEFF7", "F3EAF9", "FBEAEA", "FBF4E4", "EDF4E8",
                "E7F1FA", "FAEDE6", "EAF2FA", "F7EDE4", "EBF1E6",
                "F5EAF8", "E6F0F8", "FBEAF1", "EEEAF7"]
SECTION_FILL = PatternFill("solid", fgColor="7030A0")
# every column that reads better as a red->green gradient
SCALE_UP = ("RATE", "MOMENTUM_SCORE", "last_target_upside_pct", "RR",
            "move_pct", "move_in_sigma", "company_specific_pp", "vs_sector_pct",
            "net_upgrades", "score_value", "score_quality",
            "score_safety", "score_growth", "unusual_score",
            "consensus_upside_pct", "ret_1m_pct", "ret_3m_pct",
            "ret_6m_pct", "ret_12m_pct", "mom_12_1_pct", "rs_3m_vs_spy",
            "chg_1d_pct", "pct_vs_200sma", "company_specific_pct",
            "move_today_pct", "r2")


def build_frames() -> dict[str, pd.DataFrame]:
    u = pd.read_csv(os.path.join(HERE, "sp500.csv"))
    syms = list(u.symbol)
    close = cp.load_px("close")
    high, low, vol = cp.load_px("high"), cp.load_px("low"), cp.load_px("volume")

    say("technicals ...")
    tech = cp.technicals(close, high, low, vol, syms)
    say("macro betas ...")
    betas = cp.macro_betas(close, syms)
    say("why it moved (forensic) ...")
    openp = cp.load_px("open")
    _tape_p = os.path.join(HERE, "..", "analysts", "ratings_tape.csv")
    _tape = pd.read_csv(_tape_p) if os.path.exists(_tape_p) else pd.DataFrame()
    _opt = cp.load_cache("options")
    _fund_raw = cp.load_cache("fundamentals")
    why = wd.build(close, openp, high, low, vol, betas,
                   _fund_raw if not _fund_raw.empty else pd.DataFrame({"symbol": syms}),
                   _tape, _opt, u)

    fund = cp.load_cache("fundamentals")
    if fund.empty:
        # the old fallback announced recovery and then died two lines later on
        # a missing column; give the frame the columns the pipeline requires
        say("!! no fundamentals cache -- run fetch.py --fundamentals")
        fund = pd.DataFrame({"symbol": syms})
        for c in ("shortName", "sector", "industry", "marketCap", "forwardPE",
                  "forwardEps", "trailingPE", "totalDebt", "totalCash",
                  "next_earnings", "beta"):
            fund[c] = np.nan
        fund["sector"] = "?"
    fund = cp.fundamental_score(fund)
    fund = cp.halal_flag(fund)

    say("buy zone ...")
    bz = cp.buy_zone(tech, fund)

    # ---- momentum sheet
    mom = tech.merge(fund[["symbol", "shortName", "sector", "RATE"]],
                     on="symbol", how="left")
    for c in ("ret_1m_pct", "ret_3m_pct", "ret_6m_pct", "mom_12_1_pct",
              "rs_3m_vs_spy", "vol_surge"):
        if c in mom:
            mom[f"rank_{c}"] = mom[c].rank(pct=True, method="average") * 100
    parts = [mom[f"rank_{c}"] for c in ("ret_3m_pct", "ret_6m_pct", "mom_12_1_pct",
                                        "rs_3m_vs_spy") if f"rank_{c}" in mom]
    mom["MOMENTUM_SCORE"] = (pd.concat(parts, axis=1).mean(axis=1).round(1)
                             if parts else np.nan)
    mom["hot"] = np.where((mom["MOMENTUM_SCORE"] >= 80)
                          & (mom["rsi14"].between(50, 80))
                          & (mom["vs_200sma"] == "ABOVE"), "HOT", "")
    mom = mom.sort_values("MOMENTUM_SCORE", ascending=False)

    # ---- big money sheet (option tape as a positioning signal only)
    opt = cp.load_cache("options")
    if not opt.empty:
        opt["total_notional"] = opt["call_notional"] + opt["put_notional"]
        opt["call_pct"] = (opt["call_notional"] / opt["total_notional"].replace(0, np.nan)
                           * 100).round(1)
        opt["call_put_vol_ratio"] = (opt["call_vol"]
                                     / opt["put_vol"].replace(0, np.nan)).round(2)
        opt["vol_vs_oi"] = ((opt["call_vol"] + opt["put_vol"])
                            / (opt["call_oi"] + opt["put_oi"]).replace(0, np.nan)).round(2)
        big = opt.merge(fund[["symbol", "shortName", "sector", "marketCap"]],
                        on="symbol", how="left")
        big["notional_vs_mcap_bp"] = (big["total_notional"]
                                      / pd.to_numeric(big["marketCap"], errors="coerce")
                                      * 10000).round(2)
        # Unusual activity is RELATIVE, not absolute. Fixed thresholds
        # (vol/OI > 0.6 AND premium > 5bp) flagged ZERO of 503 names: mega
        # caps carry huge premium but low vol/OI, small caps the reverse, and
        # nothing clears both. Rank each leg across the index instead and take
        # the top of the combined rank, so the flag always surfaces the most
        # unusual names whatever the day's absolute activity level.
        # rank() skips NaN, so vol_vs_oi ranked 261 names while
        # notional_vs_mcap_bp ranked 502 -- averaging those two percentiles
        # compares positions in different populations. Score only names that
        # have BOTH legs, and rank within that common set.
        both = big["vol_vs_oi"].notna() & big["notional_vs_mcap_bp"].notna()
        r_voi = big["vol_vs_oi"].where(both).rank(pct=True)
        r_prem = big["notional_vs_mcap_bp"].where(both).rank(pct=True)
        big["unusual_score"] = ((r_voi + r_prem) / 2 * 100).round(1)
        big["UNUSUAL"] = np.where(big["unusual_score"] >= 95, "UNUSUAL",
                          np.where(big["unusual_score"] >= 90, "elevated", ""))
        big["skew"] = np.where(big["call_pct"] > 70, "CALL-HEAVY",
                       np.where(big["call_pct"] < 30, "PUT-HEAVY", ""))
        big = big.sort_values("unusual_score", ascending=False)
    else:
        big = pd.DataFrame({"symbol": syms})

    # ---- analysts sheet: local tape first, yfinance consensus as backup
    tape_p = os.path.join(HERE, "..", "analysts", "ratings_tape.csv")
    if os.path.exists(tape_p):
        t = pd.read_csv(tape_p)
        t["d"] = pd.to_datetime(t["date"], format="%b %d, %Y", errors="coerce")
        t = t.dropna(subset=["d"]).sort_values("d")
        # several ratings can share a symbol's latest DATE; tail(1) then picks
        # whichever row numpy's unstable sort happened to leave last. Break the
        # tie deterministically so the sheet does not change between builds.
        t = t.sort_values(["d", "firm", "analyst"], kind="stable")
        last = t.groupby("symbol").tail(1).set_index("symbol")
        agg = t.groupby("symbol").agg(
            n_ratings=("action", "size"),
            n_upgrades=("action", lambda s: (s.isin(["Upgrade", "Upgrades"])).sum()),
            n_downgrades=("action", lambda s: (s.isin(["Downgrade", "Downgrades"])).sum()),
            mean_target=("target", "mean"),
            last_date=("d", "max"))
        an = agg.join(last[["analyst", "firm", "action", "rating", "target",
                            "upside_pct"]].add_prefix("last_")).reset_index()
    else:
        an = pd.DataFrame({"symbol": syms})
    keep = [c for c in ("symbol", "shortName", "sector", "recommendationMean",
                        "numberOfAnalystOpinions", "targetMeanPrice",
                        "targetHighPrice", "targetLowPrice") if c in fund]
    # inner-join the S&P universe: the rating tape covers 1,520 names,
    # most of them not in the index, and an outer merge smuggles them in
    an = an.merge(fund[keep], on="symbol", how="right")
    an = an.merge(tech[["symbol", "price"]], on="symbol", how="left")
    if "targetMeanPrice" in an:
        an["consensus_upside_pct"] = ((pd.to_numeric(an["targetMeanPrice"],
                                                     errors="coerce") / an["price"] - 1)
                                      * 100).round(1)

    # ---- readable analyst sheet -------------------------------------------
    # the raw join is 21 unordered columns of mixed provenance; this turns it
    # into something scannable: freshness first, then who said what, then the
    # aggregate. Sorted by how recently anything happened.
    an["last_date"] = pd.to_datetime(an.get("last_date"), errors="coerce")
    an["days_ago"] = (pd.Timestamp.now().normalize() - an["last_date"]).dt.days
    an["FRESH"] = np.select(
        [an["days_ago"] <= 3, an["days_ago"] <= 14, an["days_ago"] <= 45],
        ["TODAY-ISH", "THIS WEEK", "THIS MONTH"], default="")
    up = pd.to_numeric(an.get("n_upgrades"), errors="coerce").fillna(0)
    dn = pd.to_numeric(an.get("n_downgrades"), errors="coerce").fillna(0)
    an["net_upgrades"] = (up - dn).astype(int)
    an["tilt"] = np.select([an["net_upgrades"] > 0, an["net_upgrades"] < 0],
                           ["UPGRADING", "DOWNGRADING"], default="flat")
    tgt = pd.to_numeric(an.get("last_target"), errors="coerce")
    an["last_target_upside_pct"] = ((tgt / an["price"] - 1) * 100).round(1)
    # recommendationMean is 1=Strong Buy .. 5=Sell, which reads backwards
    rm = pd.to_numeric(an.get("recommendationMean"), errors="coerce")
    an["consensus"] = np.select(
        [rm <= 1.5, rm <= 2.5, rm <= 3.5, rm <= 4.5],
        ["STRONG BUY", "BUY", "HOLD", "SELL"], default="STRONG SELL")
    an.loc[rm.isna(), "consensus"] = ""
    ORDER = ["symbol", "shortName", "sector", "price", "FRESH", "days_ago",
             "last_date", "last_action", "last_rating", "last_analyst",
             "last_firm", "last_target", "last_target_upside_pct",
             "consensus", "recommendationMean", "numberOfAnalystOpinions",
             "targetMeanPrice", "consensus_upside_pct", "targetLowPrice",
             "targetHighPrice", "tilt", "net_upgrades", "n_upgrades",
             "n_downgrades", "n_ratings", "mean_target"]
    an = an[[c for c in ORDER if c in an.columns]
            + [c for c in an.columns if c not in ORDER]]
    an["last_date"] = an["last_date"].dt.strftime("%Y-%m-%d")
    an = an.sort_values("days_ago", na_position="last")

    # ---- summary
    keep_f = [c for c in ("symbol", "shortName", "sector", "industry", "marketCap",
                          "RATE", "rate_grade", "score_value", "score_quality",
                          "score_safety", "score_growth", "halal_auto",
                          "halal_auto_reason", "halal_MANUAL", "next_earnings",
                          "beta") if c in fund]
    # low_52w/high_52w must travel: alerts.py's new_52w_low reads them off
    # Summary and could never fire without them
    summ = (tech[["symbol", "price", "chg_1d_pct", "vs_200sma", "pct_vs_200sma",
                  "support", "pct_to_support", "resistance", "pct_to_resistance",
                  "rsi14", "atr_pct", "pct_from_52w_high", "atr14",
                  "high_52w", "low_52w", "low_60d"]]
            .merge(fund[keep_f], on="symbol", how="left")
            .merge(bz[["symbol", "perfect_buy", "buy_zone_low", "buy_zone_high",
                       "discount_to_buy_pct", "zone_status", "pct_above_zone",
                       "zone_entry_price", "pct_to_zone_entry",
                       "dollars_to_zone", "buy_note",
                       "risk_pct", "reward_pct", "risk_$", "reward_$", "RR",
                       "breakeven_hit_rate_pct", "RR_grade", "levels_confirmed",
                       "shares_risk_$250", "cost_risk_$250",
                       "gain_if_target_$250", "max_shares_for_account",
                       "actual_position_$", "actual_risk_$", "actual_gain_$",
                       "fits_account", "ZONE", "price_for_2R", "price_for_3R",
                       "price_for_5R", "pct_to_3R", "dollars_to_3R", "CAPITULATION", "pct_off_recent_low",
                       "still_falling"]],
                   on="symbol", how="left")
            .merge(mom[["symbol", "MOMENTUM_SCORE", "hot"]], on="symbol", how="left")
            .merge(betas[["symbol", "beta_spy", "beta_tlt", "r2"]], on="symbol", how="left"))
    if not big.empty and "UNUSUAL" in big:
        summ = summ.merge(big[["symbol", "UNUSUAL", "skew"]], on="symbol", how="left")
    if "last_action" in an:
        summ = summ.merge(an[["symbol", "last_action", "last_rating", "last_date"]],
                          on="symbol", how="left")
    # position sizer: shares for a fixed dollar risk at a 2-ATR stop
    summ["shares_for_$250_risk"] = (250 / (2 * tech.set_index("symbol")
                                           .reindex(summ.symbol)["atr14"].to_numpy())
                                    ).round(0)
    summ["cost_of_that_position"] = (summ["shares_for_$250_risk"]
                                     * summ["price"]).round(0)
    if "next_earnings" in summ:
        ne = pd.to_datetime(summ["next_earnings"], errors="coerce")
        summ["days_to_earnings"] = (ne - pd.Timestamp.now().normalize()).dt.days
    # the verdict needs MOMENTUM_SCORE, which only exists after the merges
    summ = cp.verdict(summ)
    summ = summ.sort_values(["VERDICT", "RR"], ascending=[True, False])

    return {"Summary": summ, "Technicals": tech, "Fundamentals": fund,
            "Macro": betas, "WhyItMoved": why, "Momentum": mom,
            "BigMoney": big, "Analysts": an, "BuyZone": bz}


def readme() -> pd.DataFrame:
    R = [
        ("HOW TO REFRESH", ""),
        ("hourly", "run.py --hourly : prices, technicals, S/R, alerts (~15s)"),
        ("daily", "run.py --daily : fundamentals, scores, betas, options (~25m)"),
        ("alerts", "run.py --alerts : watchlist -> Telegram (~5s)"),
        ("live refresh", "Point Power Query at research/sheet/cache/*.csv and set "
                         "Refresh every 60 min. Works while the file is open."),
        ("", ""),
        ("SHEETS", ""),
        ("Summary", "one row per stock, the sheet to scan"),
        ("Technicals", "price, SMA, support/resistance, RSI, ATR, momentum"),
        ("Fundamentals", "all ratios + the 0-100 RATE and its four components"),
        ("Macro", "betas to SPY/bonds/gold/oil/dollar/VIX + FOMC behaviour"),
        ("WhyItMoved", "today's move split into factor-explained vs company-specific"),
        ("Momentum", "which names are running, 12-1 momentum and rel strength"),
        ("BigMoney", "option-tape notional, unusual activity, call/put skew"),
        ("Analysts", "local 11.5k-event rating tape + consensus targets"),
        ("BuyZone", "the four anchors behind perfect_buy, shown separately"),
        ("", ""),
        ("KEY COLUMNS", ""),
        ("RATE", "0-100, percentile-ranked WITHIN SECTOR. Four equal blocks: "
                 "value, quality, safety, growth. Sector-neutral so the score "
                 "does not just re-discover which sector a stock is in."),
        ("perfect_buy", "median of the anchors below spot, floored at -25%. A "
                        "DISCIPLINE TOOL, NOT A FORECAST."),
        ("buy_note", "'CHEAP FOR A REASON' = bottom-quartile rate, no price shown. "
                     "'BELOW ZONE' = already under every anchor; cheap and broken "
                     "look identical from price alone."),
        ("beta_tlt", "after removing the market: -0.4 means a 1% bond rally "
                     "tends to coincide with a 0.4% fall in this stock"),
        ("r2", "how much of the stock's movement the factors explain. Below "
               "~0.15 the betas are noise and should be read as such."),
        ("fomc_amplifier", "mean |move| on the 67 real FOMC decision dates "
                           "divided by mean |move| on other days"),
        ("company_specific_pct", "today's move minus what the betas predicted"),
        ("UNUSUAL", "option volume > 0.6x open interest AND premium > 5bp of "
                    "market cap. A positioning signal read from the option "
                    "tape - the account itself is long spot only."),
        ("halal_auto", "ADVISORY ONLY. Industry text screen + debt/mcap<33% + "
                       "cash/mcap<33%. Fill halal_MANUAL yourself."),
        ("shares_for_$250_risk", "position size at a 2-ATR stop"),
        ("", ""),
        ("HONEST LIMITS", ""),
        ("support/resistance", "descriptive, not predictive. Measured earlier in "
                               "this project: level bounces beat a coin by ~0.5pp."),
        ("fundamentals", "yfinance as-reported; occasionally stale or wrong for a "
                         "few names. fetched_utc travels with every row."),
        ("betas", "backward-looking over 2y, unstable after a merger or for short "
                  "histories. Read r2 before trusting a beta."),
        ("analyst data", "entering on the public rating date underperformed a "
                         "nearby day by 0.67-1.55pp over the next month "
                         "(n=11,570, p~0.0005). Shown for context, not as a buy."),
    ]
    return pd.DataFrame(R, columns=["item", "meaning"])


# column name -> excel number format. Raw floats like 107.262497 are
# unreadable in a grid; every numeric column gets an explicit format.
FMT_RULES = [
    (("price", "support", "resistance", "sma20", "sma50", "sma200", "high_52w",
      "low_52w", "atr14", "perfect_buy", "buy_zone_low", "buy_zone_high",
      "anchor_support", "anchor_valuation", "anchor_trend", "anchor_volatility",
      "target", "mean_target", "zone_entry_price", "dollars_to_zone",
      "targetMeanPrice", "targetHighPrice",
      "targetLowPrice", "cost_of_that_position"), '"$"#,##0.00'),
    (("marketCap", "enterpriseValue", "totalDebt", "totalCash", "totalRevenue",
      "ebitda", "freeCashflow", "operatingCashflow", "call_notional",
      "put_notional", "total_notional", "max_strike_notional",
      ), '"$"#,##0,,"M"'),
    # share counts and volumes are COUNTS, not dollars -- formatting them as
    # "$123M" destroyed both columns
    (("avg_vol_20d", "sharesOutstanding", "call_notional_shares"), '#,##0,,"M"'),
    # margins / yields arrive as FRACTIONS (0.0341 = 3.41%); "0.00" left one
    # significant digit, so every margin in the book read 0.03 / 0.07 / 0.21
    (("grossMargins", "operatingMargins", "profitMargins", "ebitdaMargins",
      "returnOnEquity", "returnOnAssets", "dividendYield", "payoutRatio",
      "revenueGrowth", "earningsGrowth", "earningsQuarterlyGrowth",
      "earnings_yield", "fcf_yield", "heldPercentInstitutions",
      "shortPercentOfFloat"), "0.0%"),
    (("RATE", "score_value", "score_quality", "score_safety", "score_growth",
      "MOMENTUM_SCORE", "unusual_score", "rsi14"), "0.0"),
    (("beta", "beta_spy", "beta_tlt", "beta_gld", "beta_oil", "beta_dxy",
      "beta_vix", "r2", "vol_surge", "vol_vs_oi", "call_put_vol_ratio",
      "fomc_amplifier"), "0.00"),
    (("shares_for_$250_risk", "days_to_earnings", "support_touches",
      "resistance_touches", "n_ratings", "n_upgrades", "n_downgrades",
      "call_vol", "put_vol", "call_oi", "put_oi"), "#,##0"),
]


def fmt_for(name: str) -> str | None:
    n = str(name)
    for names, f in FMT_RULES:
        if n in names:
            return f
    # both spellings occur: chg_1d_pct (suffix) and pct_to_support (prefix).
    # matching only the suffix left every pct_* column unformatted.
    if (n.endswith("_pct") or n.startswith("pct_") or n.endswith("_bp")
            or "margin" in n.lower() or "growth" in n.lower()
            or n in ("dividendYield", "payoutRatio", "returnOnEquity",
                     "returnOnAssets", "earnings_yield", "fcf_yield")):
        return "0.00"
    return None


def style_encyclopedia(ws) -> None:
    """Colour-banded sections, verdict badges, wrapped prose.

    Each section gets its own header colour and a matching pale tint on its
    body rows, so 100 rows of text reads as a dozen coloured blocks instead
    of one wall.
    """
    ws.column_dimensions["A"].width = 24
    ws.column_dimensions["B"].width = 30
    ws.column_dimensions["C"].width = 104
    ws.column_dimensions["D"].width = 13
    ws.sheet_view.showGridLines = False
    sec_i = -1
    for row in ws.iter_rows(min_row=2, max_col=4):
        sec, item, mean, verd = (c.value for c in row)
        for c in row:
            c.alignment = Alignment(wrap_text=True, vertical="top")
        if sec and not item:                        # section header row
            sec_i += 1
            colour = SECTION_COLORS[sec_i % len(SECTION_COLORS)]
            for c in row:
                c.fill = PatternFill("solid", fgColor=colour)
                c.font = Font(color="FFFFFF", bold=True, size=13)
            ws.row_dimensions[row[0].row].height = 26
            continue
        tint = SECTION_TINT[max(sec_i, 0) % len(SECTION_TINT)]
        for c in row:
            c.fill = PatternFill("solid", fgColor=tint)
        row[1].font = Font(bold=True, size=10,
                           color=SECTION_COLORS[max(sec_i, 0) % len(SECTION_COLORS)])
        row[2].font = Font(size=10)
        v = str(verd or "INFO")
        if VERDICT_FILL.get(v):
            row[3].fill = PatternFill("solid", fgColor=VERDICT_FILL[v])
            row[3].font = Font(color=VERDICT_FONT[v], bold=True, size=10)
            row[3].alignment = Alignment(horizontal="center", vertical="center")
            it = str(item or "")
            # a headline verdict row gets the whole prose cell tinted so the
            # measured answers stand out from the definitions around them
            if it.isupper() or it.startswith("DOES ") or it.startswith("IS ") \
                    or it.startswith("WHY ") or it.startswith("WHAT "):
                row[2].fill = PatternFill("solid", fgColor=VERDICT_FILL[v])
                row[2].font = Font(size=10, bold=True, color=VERDICT_FONT[v])
                row[1].font = Font(bold=True, size=11, color=VERDICT_FONT[v])
        est = len(str(mean or "")) / 92.0 * 15 + 17
        ws.row_dimensions[row[0].row].height = max(17, min(est, 96))


def write_xlsx(frames: dict[str, pd.DataFrame]) -> bool:
    try:
        with pd.ExcelWriter(XLSX, engine="openpyxl") as xw:
            # Encyclopedia is tab 0 so the file always carries its own
            # explanation, but the workbook OPENS on Summary (wb.active = 1).
            enc.frame().to_excel(xw, sheet_name="Encyclopedia", index=False)
            for name, df in frames.items():
                df.to_excel(xw, sheet_name=name[:31], index=False)
            readme().to_excel(xw, sheet_name="Readme", index=False)
            wb = xw.book
            for ws in wb.worksheets:
                if ws.title in TAB_COLORS:
                    ws.sheet_properties.tabColor = TAB_COLORS[ws.title]
                if ws.title == "Encyclopedia":
                    for c in ws[1]:
                        c.fill, c.font = HDR_FILL, HDR_FONT
                        c.alignment = Alignment(horizontal="center")
                    ws.freeze_panes = "A2"
                    style_encyclopedia(ws)
                    continue
                is_readme = ws.title == "Readme"
                ws.freeze_panes = "A2" if is_readme else "B2"
                ws.auto_filter.ref = None if is_readme else ws.dimensions
                for c in ws[1]:
                    c.fill, c.font = HDR_FILL, HDR_FONT
                    c.alignment = Alignment(horizontal="center", wrap_text=True)
                ws.row_dimensions[1].height = 30
                n = ws.max_row
                head = {str(c.value): c.column_letter for c in ws[1]}

                if is_readme:
                    ws.column_dimensions["A"].width = 26
                    ws.column_dimensions["B"].width = 118
                    for row in ws.iter_rows(min_row=2, max_col=2):
                        row[1].alignment = Alignment(wrap_text=True, vertical="top")
                        if row[0].value and not row[1].value:
                            row[0].font = Font(bold=True, size=11)
                    continue

                # width from the widest of header and a sample of the values
                for i, col in enumerate(ws.iter_cols(min_row=1, max_row=min(n, 120)), 1):
                    hdr = str(col[0].value or "")
                    widest = max([len(hdr)] +
                                 [len(str(c.value)) for c in col[1:] if c.value is not None]
                                 or [0])
                    # Summary is sorted by RATE and the long text columns are
                    # empty in the first 120 sampled rows, so a content-only
                    # width clipped buy_note and friends to nothing.
                    floor = (90 if hdr == "VERDICT" else
                             34 if hdr in ("buy_note", "halal_auto_reason",
                                           "why", "max_strike", "industry",
                                           "name", "analyst_action",
                                           "shortName") else 9)
                    ws.column_dimensions[get_column_letter(i)].width = min(
                        max(floor, widest + 2), 95 if hdr == "VERDICT" else 38)
                    f = fmt_for(hdr)
                    if f:
                        for c in ws[get_column_letter(i)][1:]:
                            c.number_format = f

                if n > 2:
                    for r in range(2, n + 1, 2):
                        for c in ws[r]:
                            c.fill = BAND
                for cname in SCALE_UP:
                    if cname in head and n > 1:
                        ws.conditional_formatting.add(
                            f"{head[cname]}2:{head[cname]}{n}",
                            ColorScaleRule(start_type="percentile", start_value=5,
                                           start_color="F8696B",
                                           mid_type="percentile", mid_value=50,
                                           mid_color="FFFFFF",
                                           end_type="percentile", end_value=95,
                                           end_color="63BE7B"))
                if "rsi14" in head and n > 1:
                    ws.conditional_formatting.add(
                        f"{head['rsi14']}2:{head['rsi14']}{n}",
                        ColorScaleRule(start_type="num", start_value=20,
                                       start_color="63BE7B",
                                       mid_type="num", mid_value=50,
                                       mid_color="FFFFFF",
                                       end_type="num", end_value=80,
                                       end_color="F8696B"))
                if "zone_status" in head and n > 1:
                    for word, colour in (("IN ZONE", "C6EFCE"), ("AT ZONE", "C6EFCE"),
                                         ("BELOW ZONE", "FFEB9C")):
                        ws.conditional_formatting.add(
                            f"{head['zone_status']}2:{head['zone_status']}{n}",
                            CellIsRule(operator="equal", formula=[f'"{word}"'],
                                       fill=PatternFill("solid", fgColor=colour)))
                for cname, word, colour in (("vs_200sma", "BELOW", "FFC7CE"),
                                            ("hot", "HOT", "C6EFCE"),
                                            ("UNUSUAL", "UNUSUAL", "FFEB9C"),
                                            ("halal_auto", "FAIL", "FFC7CE"),
                                            ("FRESH", "TODAY-ISH", "C6EFCE"),
                                            ("FRESH", "THIS WEEK", "DDF0DC"),
                                            ("tilt", "UPGRADING", "C6EFCE"),
                                            ("tilt", "DOWNGRADING", "FFC7CE"),
                                            ("consensus", "STRONG BUY", "C6EFCE"),
                                            ("consensus", "BUY", "DDF0DC"),
                                            ("consensus", "SELL", "FFC7CE"),
                                            ("last_action", "Upgrades", "C6EFCE"),
                                            ("last_action", "Downgrades", "FFC7CE"),
                                            ("volume_confirms", "YES", "C6EFCE"),
                                            ("unusual_options", "YES", "FFEB9C"),
                                            ("move_where", "GAP (overnight)", "FFEB9C"),
                                            ("RR_grade", "EXCELLENT", "C6EFCE"),
                                            ("RR_grade", "GOOD", "DDF0DC"),
                                            ("RR_grade", "poor", "FFC7CE"),
                                            ("levels_confirmed", "WEAK", "FFEB9C"),
                                            ("VERDICT", "STRONG", "C6EFCE"),
                                            ("VERDICT", "OK", "DDF0DC"),
                                            ("VERDICT", "AVOID", "FFC7CE"),
                                            ("fits_account", "yes", "C6EFCE"),
                                            ("fits_account", "NO", "FFC7CE"),
                                            ("VERDICT", "PRIME", "63BE7B"),
                                            ("ZONE", "PRIME (5R+)", "63BE7B"),
                                            ("ZONE", "BUY ZONE (3R+)", "C6EFCE"),
                                            ("ZONE", "FAIR (2R+)", "DDF0DC"),
                                            ("ZONE", "AVOID (under 1R)", "FFC7CE"),
                                            ("CAPITULATION", "DEEP + 20% OFF LOW (+6.1%)", "63BE7B"),
                                            ("CAPITULATION", "DEEP, stabilising (+4.4%)", "C6EFCE"),
                                            ("CAPITULATION", "DEEP but STILL FALLING (+1.1%)", "FFC7CE"),
                                            ("still_falling", "STILL FALLING", "FFC7CE")):
                    if cname in head and n > 1:
                        ws.conditional_formatting.add(
                            f"{head[cname]}2:{head[cname]}{n}",
                            CellIsRule(operator="equal", formula=[f'"{word}"'],
                                       fill=PatternFill("solid", fgColor=colour)))
            wb.active = 1        # open on Summary; Encyclopedia is tab 0
        return True
    except PermissionError:
        say(f"!! {XLSX} is open in Excel -- close it and rerun; CSVs were written")
        return False


def main() -> None:
    frames = build_frames()
    os.makedirs(CACHE, exist_ok=True)
    for name, df in frames.items():
        df.to_csv(os.path.join(CACHE, f"{name.lower()}.csv"), index=False)
    readme().to_csv(os.path.join(CACHE, "readme.csv"), index=False)
    say("")
    for name, df in frames.items():
        say(f"  {name:<14}{df.shape[0]:>5} rows x {df.shape[1]:>3} cols")
    ok = write_xlsx(frames)
    say("")
    say(f"CSVs  -> {CACHE}")
    if ok:
        say(f"XLSX  -> {XLSX}")


if __name__ == "__main__":
    main()
