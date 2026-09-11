"""The Encyclopedia sheet: every metric in plain language, with its test result.

Kept separate from build_workbook.py because it is content, not plumbing, and
it changes for different reasons.

Every claim about whether a signal WORKS comes from backtest.py, which scores
each signal against random baskets drawn from the same survivorship-biased
universe on the same dates. Where a metric was never tested, it says so
instead of implying it passed.
"""
from __future__ import annotations

import pandas as pd

# (section | item | plain english | verdict)
# verdict codes: WORKS / FAILS / UNTESTED / INFO
ROWS = [
    ("START HERE", "", "", "INFO"),
    ("", "What this is",
     "Every S&P 500 company on one screen: what it costs, whether it is cheap, "
     "whether it is going up, and what moves it. 10 tabs, 503 companies.",
     "INFO"),
    ("", "Which tab do I open",
     "Summary. Everything important is there, one row per company. The other "
     "tabs are the same data with more detail on one theme.",
     "INFO"),
    ("", "What actually works (measured)",
     "MOMENTUM, but smaller than it first looked. On a point-in-time universe "
     "(top 350 by dollar volume as of 3 years earlier), top-10 by 6-month "
     "momentum, held only while the S&P is above its own 200-day average, beat "
     "random baskets from that same universe by +3.40% per quarter across 93 "
     "rebalances, winning 70% of them. An earlier +9.1% figure was inflated by "
     "a survivorship effect described in the TESTING section - treat +3.4% as "
     "the number, and see the caveat below.",
     "WORKS"),
    ("", "IS +3.4% PROVEN?",
     "NOT QUITE. 1,008 variants were searched, and the best of 1,008 pure-noise "
     "draws would sit 3.72 standard errors up, which here means 4.60% - above "
     "the 3.40% actually measured. So on the strictest reading it FAILS. Two "
     "things argue it is nonetheless real: the top 60 configurations form a "
     "PLATEAU from 1.88% to 3.41% rather than a lone spike (noise-mining "
     "produces a spike), and those 1,008 variants are heavily redundant, so the "
     "effective number of independent tests is nearer 20-50, where the bar is "
     "3.03-3.46%. Overlap-adjusted t = 2.75. Read it as PROBABLY REAL, NOT "
     "PROVEN.",
     "PROBATION"),
    ("", "What does NOT work (measured)",
     "THE BUY ZONE. Buying near support / at the computed 'perfect price' LOST "
     "to random picking by -2.0% over 3 months (p=0.002). Read the perfect_buy "
     "column as 'a cheap price', never as 'a good buy'.",
     "FAILS"),
    ("", "WHAT 'PROBATION' MEANS",
     "A yellow PROBATION tag means the idea COULD NOT BE BACKTESTED, not that "
     "it failed. Some things have no past to test against -- nobody publishes "
     "free historical option chains, and point-in-time accounting data does "
     "not exist in this feed. Those ideas are recorded forward in a live "
     "ledger instead and stay on probation until they have 40+ closed "
     "positions. Green WORKS survived a controlled test. Red FAILS was "
     "measured and lost. Yellow PROBATION is simply unproven, and unproven is "
     "not the same as wrong.", "PROBATION"),
    ("", "How to refresh",
     "Hourly job updates prices. Daily job updates fundamentals. Or point Excel "
     "Power Query at research/sheet/cache/*.csv and tick Refresh every 60 min.",
     "INFO"),

    ("THE TABS", "", "", "INFO"),
    ("", "Summary", "One row per company. The scanning sheet.", "INFO"),
    ("", "Technicals", "Price, moving averages, support/resistance, RSI, ATR.", "INFO"),
    ("", "Fundamentals", "All the accounting ratios plus the 0-100 RATE.", "INFO"),
    ("", "Macro", "What each stock reacts to: bonds, gold, oil, dollar, the Fed.", "INFO"),
    ("", "WhyItMoved", "Today's move split into 'the market did it' vs 'the company did it'.", "INFO"),
    ("", "Momentum", "Which names are running. THE TAB THAT PASSED THE TEST.", "WORKS"),
    ("", "BigMoney", "Where large option premium is showing up.", "PROBATION"),
    ("", "Analysts", "11,570 recorded analyst calls, latest action per name.", "FAILS"),
    ("", "BuyZone", "The four anchors behind perfect_buy, shown separately.", "FAILS"),

    ("PRICE AND TREND", "", "", "INFO"),
    ("", "price", "Last close.", "INFO"),
    ("", "chg_1d_pct", "Percent move today.", "INFO"),
    ("", "sma20 / sma50 / sma200",
     "Average price over the last 20, 50 or 200 trading days. A smoothed line "
     "showing the trend without the daily noise.", "INFO"),
    ("", "vs_200sma",
     "ABOVE = trading over its 200-day average (uptrend). BELOW = under it "
     "(downtrend). Tested on its own: +0.45% over random, p=0.18. Weak.",
     "PROBATION"),
    ("", "pct_vs_200sma", "How far above or below that 200-day line, in percent.", "INFO"),
    ("", "high_52w / low_52w", "Highest and lowest close in the past year.", "INFO"),
    ("", "pct_from_52w_high",
     "How far below the yearly peak. -30% means it has fallen 30% from its high.", "INFO"),

    ("SUPPORT AND RESISTANCE", "", "", "FAILS"),
    ("", "support",
     "A price the stock has bounced off before. Found by locating swing lows "
     "over 2 years and merging ones within 1.5% of each other.", "INFO"),
    ("", "support_touches",
     "How many times price actually turned at that level. 1 touch is not a "
     "level, it is a coincidence. Prefer 3+.", "INFO"),
    ("", "resistance", "The mirror image: a price it has failed to break above.", "INFO"),
    ("", "pct_to_support / pct_to_resistance",
     "How far the level sits from today's price, in percent.", "INFO"),
    ("", "DOES SUPPORT WORK?",
     "Measured: buying within 2% of support LOST to random picking by -0.99% "
     "over 3 months (p=0.021). In an earlier test in this project, level "
     "bounces beat a coin flip by only ~0.5pp. Treat support as a description "
     "of where price has been, not a prediction of where it will stop.",
     "FAILS"),

    ("THE BUY ZONE", "", "", "FAILS"),
    ("", "How perfect_buy is built",
     "Four independent anchors: (1) nearest support, (2) the price at which "
     "forward P/E equals the lower of its own and its sector's median, "
     "(3) the 200-day average, (4) price minus 1.5x ATR. Take the median of "
     "whichever sit below today's price, floored so it is never more than 25% "
     "below spot.", "INFO"),
    ("", "buy_zone_low / buy_zone_high", "The lowest and median anchor.", "INFO"),
    ("", "zone_status",
     "ABOVE ZONE = expensive vs its own anchors. NEAR / IN / AT ZONE = at them. "
     "BELOW ZONE = under every anchor.", "INFO"),
    ("", "buy_note",
     "'CHEAP FOR A REASON' = bottom-quartile RATE, so no price is shown; a low "
     "price on a deteriorating company is not an entry. 'BELOW ZONE' = under "
     "every anchor, which is ambiguous: cheap and broken look identical from "
     "price alone.", "INFO"),
    ("", "DOES THE BUY ZONE WORK?",
     "NO. Measured over 29 rebalance dates: buying IN ZONE returned 2.56% over "
     "3 months while random picks from the same 503 names returned 4.52%. "
     "Edge -1.97%, p=0.002, and it only beat random on 34% of dates. In a "
     "rising market the stocks that fall back to support are the weak ones. "
     "USE THIS COLUMN TO AVOID OVERPAYING, NOT TO PICK WINNERS.", "FAILS"),

    ("MOMENTUM", "", "", "WORKS"),
    ("", "ret_1m / 3m / 6m / 12m_pct", "Plain return over that many months.", "INFO"),
    ("", "mom_12_1_pct",
     "Return over the past 12 months EXCLUDING the most recent one. Skipping "
     "the last month is deliberate: very recent moves tend to reverse, older "
     "ones tend to persist.", "INFO"),
    ("", "rs_3m_vs_spy",
     "How much it beat or lagged the S&P over 3 months. Positive = stronger "
     "than the index.", "INFO"),
    ("", "MOMENTUM_SCORE",
     "0-100. Average percentile rank across 3-month, 6-month, 12-1 month "
     "returns and relative strength. 100 = strongest name in the index.", "INFO"),
    ("", "hot",
     "Momentum score 80+, RSI between 50 and 80, and above the 200-day average. "
     "Strong but not yet blown off.", "INFO"),
    ("", "DOES MOMENTUM WORK?",
     "Probably, at about +3.4% per quarter over a random basket - not the "
     "+9.1% first measured. Best configuration found: top 10 names by 6-month "
     "momentum, equal weighted, rebalanced monthly, held only while the S&P "
     "trades above its own 200-day average. 93 rebalances 2013-2021, win rate "
     "70%, overlap-adjusted t = 2.75. NOT proven: see 'IS +3.4% PROVEN?' at "
     "the top of this sheet.", "WORKS"),
    ("", "WHAT IT COSTS YOU IN A BAD MONTH",
     "Worst single rebalance in the sample: -16.0% versus the random basket. "
     "Best: +22.4%. And it is not steady year to year - 2016 +7.2%, 2020 "
     "+8.5%, but 2015 +0.8% and 2021 MINUS 1.0%. A year of nothing is a normal "
     "outcome, not a malfunction.", "INFO"),
    ("", "WHY THE REGIME FILTER MATTERS",
     "Every top configuration in the search included 'only while SPY is above "
     "its 200-day average'. Momentum crashes at market turns - that is its "
     "known failure mode - and sitting out below-trend markets is what stops "
     "the strategy from meeting one.", "INFO"),

    ("OSCILLATORS", "", "", "PROBATION"),
    ("", "rsi14",
     "0-100 speedometer of recent buying vs selling. Under 30 is called "
     "oversold, over 70 overbought.", "INFO"),
    ("", "DOES RSI WORK?",
     "Not measurably. RSI under 30 returned -0.89% versus random over 3 months "
     "(p=0.48) and RSI over 70 returned +0.97% (p=0.64). Neither is "
     "distinguishable from noise here.", "FAILS"),
    ("", "atr14",
     "Average True Range: the typical dollar move in a day. A $500 stock with "
     "$15 ATR is calmer than a $50 stock with $5 ATR.", "INFO"),
    ("", "atr_pct", "That daily move as a percent of price. The volatility number.", "INFO"),
    ("", "vol_surge",
     "Last 5 days' average volume divided by the last 60 days'. Above 2 means "
     "something is happening.", "INFO"),

    ("THE FUNDAMENTAL RATE", "", "", "PROBATION"),
    ("", "RATE",
     "0-100 quality-and-value score, ranked WITHIN SECTOR. Four equal blocks: "
     "value, quality, safety, growth.", "INFO"),
    ("", "Why within sector",
     "An absolute P/E screen just re-discovers which sector something is in. "
     "Every utility and REIT would sit at the bottom of a raw value rank "
     "forever. Scoring a utility against utilities asks the useful question.", "INFO"),
    ("", "score_value", "Earnings yield, free-cash-flow yield, price/sales, EV/EBITDA.", "INFO"),
    ("", "score_quality", "Return on equity, return on assets, gross and net margin.", "INFO"),
    ("", "score_safety", "Debt-to-equity and current ratio. Can it survive a bad year.", "INFO"),
    ("", "score_growth", "Revenue growth and earnings growth.", "INFO"),
    ("", "rate_grade", "A/B/C/D/F banding of RATE.", "INFO"),
    ("", "IS THE RATE TESTED? YES, NOW - AND IT FAILS",
     "Tested 2026-09-10 on genuine point-in-time fundamentals from the SEC's "
     "free XBRL API (30,337 filings, 503 companies, 2009-2026, each stamped "
     "with the date it was FILED and therefore public). Median reporting lag "
     "respected: 57 days. Result over 158 rebalance dates vs random baskets "
     "from the same point-in-time universe: top quintile +0.29% (p=0.022), "
     "bottom quintile +0.19%, middle -0.32%. TOP MINUS BOTTOM: +0.10% per "
     "quarter. The quintiles are not monotonic - the bottom beats the middle - "
     "which is what a score that orders nothing looks like. Nothing clears the "
     "5-bucket Bonferroni bar of 0.010. Use RATE to avoid obviously broken "
     "companies, not to rank good ones.", "FAILS"),
    ("", "THE OLD ANSWER, AND WHY IT CHANGED",
     "NO, AND IT CANNOT BE with this data. Backtesting it needs point-in-time "
     "fundamentals - what the P/E actually was in 2023 - and the free data "
     "source only gives TODAY'S figures. Scoring 2023 with 2026 numbers is "
     "look-ahead bias and would produce a fake result. So RATE is shown "
     "unmeasured rather than dressed up.", "PROBATION"),

    ("MACRO SENSITIVITY", "", "", "INFO"),
    ("", "How the betas are built",
     "ONE regression per stock on five factors at once (market, bonds, gold, "
     "oil, dollar), not five separate ones. Oil and the dollar move together, "
     "so separate regressions credit the same move to each factor in turn and "
     "give betas that cannot all be true.", "INFO"),
    ("", "beta_spy",
     "Move for each 1% the market moves. 2.0 = twice as jumpy as the index, "
     "0.3 = barely follows it.", "INFO"),
    ("", "beta_tlt",
     "Reaction to BONDS. -0.4 means a 1% bond rally coincides with a 0.4% fall "
     "in this stock, after removing the market. Rate-sensitive names "
     "(utilities, REITs) show strongly positive numbers.", "INFO"),
    ("", "beta_gld / beta_oil / beta_dxy",
     "Same idea for gold, oil and the dollar. Miners load on gold, refiners on "
     "oil, importers negatively on the dollar.", "INFO"),
    ("", "r2",
     "How much of the stock's movement these five factors explain, 0 to 1. "
     "BELOW ABOUT 0.15 THE BETAS ARE NOISE. Read this before trusting a beta.", "INFO"),
    ("", "fomc_amplifier",
     "Average absolute move on the 67 real Fed decision dates divided by the "
     "average on ordinary days. 1.5 = it moves 50% more than usual when the "
     "Fed speaks.", "INFO"),
    ("", "fomc_mean_move_pct", "Average signed move on those Fed days.", "INFO"),
    ("", "company_specific_pct",
     "Today's move minus what the betas predicted. Large = something happened "
     "at THIS company, not to the market.", "INFO"),
    ("", "biggest_driver", "Which factor explains the most of today's move.", "INFO"),

    ("WHY IT MOVED (forensics)", "", "", "INFO"),
    ("", "VERDICT",
     "One plain sentence assembled from every column below. Read this first; "
     "the rest is the evidence behind it.", "INFO"),
    ("", "move_where / gap_pct / intraday_pct",
     "WHERE in the day the move happened. GAP means it opened at a different "
     "price than yesterday's close - that is overnight news: earnings, a "
     "guidance cut, an analyst note published before the bell. INTRADAY means "
     "it drifted during the session - that is flow, rotation or a rumour. "
     "Two completely different causes that a single daily % return hides.",
     "INFO"),
    ("", "move_in_sigma",
     "How big the move is in THIS stock's own terms. 1 sigma is an ordinary "
     "day for it, 2 is notable, 3+ is an event. A 5% day is enormous for a "
     "utility and unremarkable for a biotech; sigma makes them comparable.",
     "INFO"),
    ("", "move_in_atr", "The same idea using Average True Range instead.", "INFO"),
    ("", "pctile_vs_own_year / bigger_days_past_yr",
     "Where today ranks against the stock's last 252 days. '99th percentile, "
     "2 days beat it' means it has only had two bigger days all year.", "INFO"),
    ("", "volume_x_normal / volume_confirms",
     "Today's volume against its own 20-day average. A large move on BELOW "
     "average volume is usually not news - it is a thin tape, and it tends to "
     "reverse. YES means 1.5x or more.", "INFO"),
    ("", "sector_move_pct / vs_sector_pct / pct_peers_same_way",
     "The equal-weight move of this stock's OWN GICS sector peers today, how "
     "far this stock diverged from them, and what share of peers went the same "
     "way. A stock down 4% while its sector is down 4% has not had a bad day - "
     "its sector has. If fewer than ~45% of peers moved with it, the move is "
     "company-specific.", "INFO"),
    ("", "from_spy_pp .. from_vix_pp",
     "EACH macro factor's contribution to today's move, in percentage points: "
     "this stock's beta to that factor multiplied by what the factor actually "
     "did today. They sum to explained_pp. So 'from_oil_pp -0.40' means a "
     "stock with this oil sensitivity, on a day oil moved as it did, would be "
     "expected to lose 0.40pp.", "INFO"),
    ("", "IS THAT CAUSATION?",
     "NO. Every from_* number is an ATTRIBUTION, not a cause. It says what a "
     "stock with this historical sensitivity would be expected to do, given "
     "what the factor did. It does not establish that oil moved this stock "
     "today. Check r2_of_model before leaning on any of it.", "PROBATION"),
    ("", "explained_pp / company_specific_pp / residual_sigma",
     "The move split in two. explained_pp is the sum of the macro "
     "contributions; company_specific_pp is what is left over. When the "
     "leftover is large and residual_sigma is past 2, something happened at "
     "the COMPANY and no amount of macro explains it.", "INFO"),
    ("", "r2_of_model",
     "How much of this stock's daily movement the five factors explain "
     "historically. BELOW ~0.15 the attribution is close to meaningless and "
     "almost everything will land in company_specific by default.", "INFO"),
    ("", "analyst_action / days_to_earnings / unusual_options",
     "Catalyst check: a rating change recorded in the last two days, how close "
     "the next earnings report is, and whether option premium was unusual "
     "today. These are the three things most likely to be the actual reason.",
     "INFO"),
    ("", "WORKED EXAMPLE",
     "CASY -14.65%: gapped -15.13% overnight, +0.58% intraday, 6.2 sigma, "
     "bigger than 99% of its own year, 3.8x normal volume, sector only -1.48%, "
     "macro explains -0.12pp of it. Conclusion: overnight company news, "
     "volume-confirmed, nothing to do with the market. Contrast VRT -8.61%: "
     "moved intraday on 0.7x volume - same size of drop, far weaker evidence.",
     "INFO"),

    ("BIG MONEY (OPTIONS)", "", "", "PROBATION"),
    ("", "Why options are here",
     "As a POSITIONING SIGNAL ONLY. Reading where large premium is being paid "
     "is not itself an options trade; this account is long spot only.", "INFO"),
    ("", "call_notional / put_notional",
     "Dollars of premium traded in calls vs puts across the nearest 3 expiries.", "INFO"),
    ("", "call_pct", "Share of that premium that is calls. Over 70% is call-heavy.", "INFO"),
    ("", "vol_vs_oi",
     "Today's contract volume against existing open interest. Above 1 means "
     "more contracts traded today than were already open: NEW positioning, not "
     "existing positions being shuffled.", "INFO"),
    ("", "notional_vs_mcap_bp",
     "Option premium as basis points of the company's market cap. Puts a $100m "
     "flow into a $2tn name and a $10bn name on the same scale.", "INFO"),
    ("", "unusual_score / UNUSUAL",
     "Percentile blend of the two above. UNUSUAL = top 5% of the index today. "
     "Ranked, not fixed thresholds: fixed cutoffs flagged zero of 503 names, "
     "because mega caps have huge premium but low vol/OI and small caps the "
     "reverse.", "INFO"),
    ("", "IS BIG MONEY TESTED?",
     "NO. Historical option chains are not available from the free data source, "
     "so there is nothing to backtest against. Treat it as a place to look, "
     "not as evidence.", "PROBATION"),

    ("ANALYSTS", "", "", "FAILS"),
    ("", "last_action / last_rating / last_date",
     "The most recent recorded rating change, from a local tape of 11,570 "
     "dated calls by 2,247 analysts at 147 firms.", "INFO"),
    ("", "consensus_upside_pct",
     "Average analyst target versus today's price.", "INFO"),
    ("", "DO ANALYST CALLS WORK?",
     "NO, measurably. Buying on the public publication date of a rating "
     "underperformed buying the SAME stock on a nearby day by 0.67-1.55% over "
     "the following month (n=11,570, p~0.0005, placebo on random dates: "
     "-0.01%). By the time it is on a public webpage the move has happened. "
     "Also: across 4,703 ranked analysts, correlation between hit rate and "
     "money made was -0.03.", "FAILS"),

    ("POSITION SIZING AND RISK", "", "", "INFO"),
    ("", "shares_for_$250_risk",
     "How many shares to buy so that a 2-ATR move against you costs about "
     "$250. On a small account this decides more than the entry does.", "INFO"),
    ("", "cost_of_that_position", "What that many shares would cost.", "INFO"),
    ("", "days_to_earnings",
     "Days until the next report. Buying three days before earnings is a "
     "different bet from buying after.", "INFO"),
    ("", "halal_auto / halal_auto_reason",
     "ADVISORY ONLY: industry screen plus debt/market-cap under 33% and "
     "cash/market-cap under 33%. About 45% of the index fails.", "INFO"),
    ("", "halal_MANUAL", "Blank on purpose. Your column, your ruling.", "INFO"),

    ("HOW THE TESTING WAS DONE", "", "", "INFO"),
    ("", "The control, and where it FAILED",
     "Every signal is scored against RANDOM baskets from the same list, same "
     "dates, same size, so the average survivorship uplift cancels. That is "
     "necessary but it was NOT sufficient, and believing it was is the biggest "
     "error made in this project.", "FAILS"),
    ("", "WHY IT FAILED (this is the important one)",
     "S&P INDEX ADDITION IS ITSELF A MOMENTUM RULE - companies get added after "
     "they have grown into large-cap status, i.e. after big trailing returns. "
     "Momentum ranks on that same variable, so it systematically overweights "
     "the very names whose presence in the file is conditioned on having risen. "
     "The control removes the AVERAGE uplift; it cannot remove the correlation "
     "between the uplift and the strategy's own weights. Evidence: names first "
     "listed after 2015 supplied 55.5% of the measured edge, APP alone 12.6% "
     "(first traded 2021, added to the index in 2025 after a ~30x run). The "
     "edge grew monotonically toward the date the constituent list was pulled - "
     "+2.2% in 2011-15 rising to +21.2% in 2024-26, trend t=6.67 - and the "
     "whole trend sat in the long leg while the short leg stayed flat.",
     "FAILS"),
    ("", "THE FIX",
     "The universe is no longer 'the S&P 500'. A name is eligible on a date "
     "only if it was ALREADY in the top 350 by dollar volume THREE YEARS "
     "EARLIER, so selection cannot see what it later became. (Note: +9.1% and "
     "+3.4% are NOT the same experiment re-run - different windows, signals "
     "and universes - so read them as two separate measurements, the later "
     "and stricter one being +3.4%.) Companies DELETED from the index "
     "are still missing from the price file and cannot be recovered - but that "
     "omission pushes the edge DOWN, not up: deletions are past losers, they "
     "would have sat in the pool, been passed over, and dragged the control "
     "mean lower. So the remaining bias is conservative.", "INFO"),
    ("", "Why the raw returns look big",
     "They are inflated by exactly that bias. Random picking returned 4.5% per "
     "3 months in this window. That is the bar, not zero.", "INFO"),
    ("", "Significance",
     "Date-block bootstrap: whole rebalance dates resampled together, because "
     "500 stocks on one day are not 500 independent observations. 22 tests were "
     "run, so the honest bar is p < 0.0023, not 0.05.", "INFO"),
    ("", "Sample",
     "The momentum search used 4,198 trading days (2010-2026), 1,008 variants, "
     "93 usable train rebalances and 52 sealed holdout dates. The earlier "
     "signal tests used a shorter 2023-2026 window - one regime, a bull market. "
     "Momentum working and dip-buying failing are the same fact seen twice.",
     "INFO"),
    ("", "Why the holdout is NOT the headline",
     "The holdout (2022-2026) scored +11.5%, far ABOVE its own training period. "
     "That looks like confirmation and is not. The holdout window is the most "
     "contaminated part of the sample by the addition effect above, and "
     "cross-sectional dispersion roughly doubled over the period. The TRAIN "
     "number, +3.4%, is the conservative one and the one quoted.", "INFO"),

    ("COMBINATIONS (your idea, tested)", "", "", "INFO"),
    ("", "The hypothesis",
     "Support and fair-value gaps do nothing alone, but combined with context "
     "- a strong company, a calm or panicked market - they should work. That "
     "is a claim about INTERACTION and it was tested by crossing every pair "
     "and triple of 13 conditions, 207 sets in total.", "INFO"),
    ("", "in_fvg",
     "FAIR VALUE GAP: a three-bar imbalance where the high two bars back sits "
     "BELOW the low of the current bar, leaving a price range nothing traded "
     "through. Unfilled means no later bar has traded back into it. "
     "'Price is sitting inside an unfilled bullish gap' is the signal.", "INFO"),
    ("", "WHAT ALONE IS WORTH",
     "at_support -0.06%, momentum(top 30%) +0.23%, fair value gap +0.54%. "
     "Individually, near enough to nothing.", "FAILS"),
    ("", "WHAT COMBINED IS WORTH",
     "at_support + momentum = +0.91%. Add a fearful VIX: +1.33%. Fair value "
     "gap + momentum + calm VIX = +1.79% (p=0.009). Support contributes "
     "NOTHING alone but adds +0.68pp on top of momentum - the interaction is "
     "real and it is superadditive, exactly as predicted.", "WORKS"),
    ("", "DID IT SURVIVE THE HOLDOUT?",
     "Directionally yes, statistically no. All four finalists stayed positive "
     "on 52 sealed dates and all four IMPROVED (fvg+uptrend+momentum 1.29% -> "
     "2.01%; fvg+momentum 1.21% -> 2.00%; fvg+momentum+market_up 1.17% -> "
     "2.21%; support+momentum+market_up 1.02% -> 1.41%). Under noise you would "
     "expect half to flip sign. But individual p-values are 0.10-0.38 and the "
     "best-of-207 noise bar is 3.27 SE, so this is SUGGESTIVE, NOT PROVEN.",
     "PROBATION"),
    ("", "WHAT TO AVOID",
     "The worst combinations found, all strongly negative: low volatility + "
     "weak momentum (-1.21%), and low volatility + shallow drawdown + weak "
     "momentum (-1.62%, p=0.028). Cheap, quiet and going nowhere is the single "
     "worst thing to buy in this data.", "FAILS"),
    ("", "The fundamentals caveat",
     "'Great fundamentals' could NOT be tested - point-in-time accounting data "
     "does not exist in this feed, and using today's P/E on 2015 prices is "
     "look-ahead. Three price-derived proxies stood in: low volatility, rising "
     "200-day average, shallow drawdown. Every q_* result describes the proxy, "
     "not the balance sheet. Notably the proxies added little: momentum did "
     "nearly all the conditioning work.", "PROBATION"),

    ("HONEST LIMITS", "", "", "INFO"),
    ("", "Fundamentals may be stale",
     "As-reported from a free feed, occasionally wrong for a handful of names. "
     "fetched_utc travels with every row.", "INFO"),
    ("", "Betas are backward-looking",
     "Two years, unstable after a merger or for short histories. Check r2.", "INFO"),
    ("", "Nothing here is a forecast",
     "One signal survived a properly controlled test, at roughly a third of "
     "its first-measured size, and even that does not clear the strictest "
     "multiple-testing bar. Everything else failed or could not be tested. The "
     "sheet organises evidence; it does not predict.", "INFO"),
    ("", "SURVIVORSHIP: THE THIRD CORRECTION",
     "Wikipedia lists a Date added for all 503 members, and 47% of today's "
     "index joined after 2010. Letting a 2025 addition be pickable in 2015 was "
     "the largest remaining bias. With real membership dates enforced, the "
     "momentum edge fell again: +3.40% -> +1.83% per quarter on train, "
     "+11.34% -> +6.77% on holdout. The full sequence of honest corrections "
     "was +9.08% -> +3.40% -> +1.83%. At +1.83% it no longer clears the "
     "multiple-testing bar of 3.03% for the 1,008-variant search that found "
     "it. Still the best thing in this workbook; still not proven.", "FAILS"),
    ("", "The honest one-line summary",
     "Buy the 10 strongest 6-month performers among large liquid US stocks, "
     "monthly, and only while the market itself is in an uptrend. Expect about "
     "3% a quarter over a random basket, expect whole years of nothing, and "
     "expect a -16% quarter at some point.", "INFO"),
]


def frame() -> pd.DataFrame:
    return pd.DataFrame(ROWS, columns=["section", "item", "meaning", "verdict"])
