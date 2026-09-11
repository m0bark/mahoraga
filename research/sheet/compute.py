"""All derived columns: technicals, support/resistance, scores, betas, buy zone.

Pure functions over the cache written by fetch.py. No network. Importable by
build_workbook.py and alerts.py so the sheet and the alerts can never disagree
about what "below support" means.
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

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
# ACCOUNT SHAPE, decided 2026-09-10: 80% in ETFs (SPUS core), 20% picking.
# The sizing below is against the PICKING SLEEVE only, not total capital --
# sizing a single name off the whole account would put 20% of everything in
# one pick while the sleeve is supposed to be the entire risk budget.
ACCOUNT = 25000.0
SLEEVE_PCT = 0.20                       # the stock-picking share
SLEEVE = ACCOUNT * SLEEVE_PCT           # $5,000
MAX_POSITIONS = 4                       # concentration the sleeve can carry
MAX_POS_PCT = 1.0 / MAX_POSITIONS       # of the SLEEVE, so $1,250 a name
FACTOR_COLS = {"SPY": "SPY", "TLT": "TLT", "GLD": "GLD",
               "OIL": "USO", "DXY": "UUP", "VIX": "^VIX"}

# ---------------------------------------------------------------- loading


def load_px(field: str) -> pd.DataFrame:
    p = os.path.join(CACHE, f"px_{field}.csv")
    df = pd.read_csv(p, index_col=0, parse_dates=True)
    return df.sort_index()


def load_cache(name: str) -> pd.DataFrame:
    p = os.path.join(CACHE, f"{name}.csv")
    return pd.read_csv(p) if os.path.exists(p) else pd.DataFrame()


def fomc_dates() -> pd.DatetimeIndex:
    p = os.path.join(HERE, "fomc_dates.txt")
    if not os.path.exists(p):
        return pd.DatetimeIndex([])
    return pd.DatetimeIndex([l.strip() for l in open(p) if l.strip()])


# ------------------------------------------------------------- technicals


def rsi(s: pd.Series, n: int = 14) -> float:
    d = s.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    if dn.iloc[-1] == 0:
        return 100.0
    return float(100 - 100 / (1 + up.iloc[-1] / dn.iloc[-1]))


def atr(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14) -> float:
    """True range needs the three series ALIGNED.

    Callers hand in numpy-backed Series with a RangeIndex alongside a
    DatetimeIndexed close; pd.concat then unions the indexes, both gap legs
    come out all-NaN, and max(axis=1) silently degrades ATR to plain
    high-minus-low -- every overnight gap discarded, no error raised.
    """
    high = pd.Series(np.asarray(high, dtype="float64"))
    low = pd.Series(np.asarray(low, dtype="float64"))
    close = pd.Series(np.asarray(close, dtype="float64"))
    pc = close.shift(1)
    tr = pd.concat([high - low, (high - pc).abs(), (low - pc).abs()], axis=1).max(axis=1)
    return float(tr.ewm(alpha=1 / n, adjust=False).mean().iloc[-1])


def pivots(high: pd.Series, low: pd.Series, k: int = 5):
    """Swing pivots: a high with k lower highs on BOTH sides, and the mirror.

    k=5 means a level must dominate an 11-day window. Smaller k finds more
    levels and most of them are noise.
    """
    h, l = high.to_numpy(), low.to_numpy()
    hs, ls = [], []
    for i in range(k, len(h) - k):
        w = h[i - k:i + k + 1]
        if h[i] == w.max() and (w == h[i]).sum() == 1:
            hs.append((i, float(h[i])))
        w = l[i - k:i + k + 1]
        if l[i] == w.min() and (w == l[i]).sum() == 1:
            ls.append((i, float(l[i])))
    return hs, ls


def cluster(levels, n_bars: int, tol: float = 0.015):
    """Merge levels within tol of each other. Weight = touches + recency.

    A level touched once is not a level, so touch count travels with the
    price and is shown in the sheet.
    """
    if not levels:
        return []
    out = []
    for i, price in sorted(levels, key=lambda x: x[1]):
        if out and abs(price - out[-1]["price"]) / out[-1]["price"] <= tol:
            c = out[-1]
            c["touches"] += 1
            c["price"] = (c["price"] * (c["touches"] - 1) + price) / c["touches"]
            c["last"] = max(c["last"], i)
        else:
            out.append({"price": price, "touches": 1, "last": i})
    for c in out:
        recency = c["last"] / max(n_bars - 1, 1)          # 0 old .. 1 recent
        c["weight"] = c["touches"] * (0.5 + 0.5 * recency)
    return out


def support_resistance(high: pd.Series, low: pd.Series, spot: float,
                       bars: int = 504):
    """Levels from the last `bars` sessions (~2y), as documented.

    Previously this scanned whatever series it was handed -- the full cache,
    3.7 years -- so the sheet's levels did not match the 2-year window the
    docs and the backtest both assume.
    """
    high, low = high.tail(bars), low.tail(bars)
    hs, ls = pivots(high, low)
    n = len(high)
    res = [c for c in cluster(hs, n) if c["price"] > spot * 1.005]
    sup = [c for c in cluster(ls, n) if c["price"] < spot * 0.995]
    # nearest first, but require at least 2 touches when such a level exists
    def pick(cands, reverse):
        if not cands:
            return None
        strong = [c for c in cands if c["touches"] >= 2]
        pool = strong or cands
        return sorted(pool, key=lambda c: c["price"], reverse=reverse)[0]
    return pick(sup, True), pick(res, False)


def technicals(close: pd.DataFrame, high: pd.DataFrame, low: pd.DataFrame,
               vol: pd.DataFrame, syms: list[str]) -> pd.DataFrame:
    spy = close["SPY"] if "SPY" in close else None
    rows = []
    for s in syms:
        if s not in close:
            continue
        c = close[s].dropna()
        if len(c) < 220:
            continue
        h = high[s].reindex(c.index) if s in high else c
        l = low[s].reindex(c.index) if s in low else c
        v = vol[s].reindex(c.index) if s in vol else pd.Series(index=c.index, dtype=float)
        spot = float(c.iloc[-1])
        sma20, sma50 = c.rolling(20).mean().iloc[-1], c.rolling(50).mean().iloc[-1]
        sma200 = c.rolling(200).mean().iloc[-1]
        hi52, lo52 = float(c.tail(252).max()), float(c.tail(252).min())
        sup, res = support_resistance(h, l, spot)
        a = atr(h, l, c)
        r = {
            "symbol": s, "price": spot,
            "chg_1d_pct": float(c.pct_change().iloc[-1] * 100),
            "chg_5d_pct": float((c.iloc[-1] / c.iloc[-6] - 1) * 100) if len(c) > 6 else np.nan,
            "sma20": float(sma20), "sma50": float(sma50), "sma200": float(sma200),
            "vs_200sma": "ABOVE" if spot > sma200 else "BELOW",
            "pct_vs_200sma": float((spot / sma200 - 1) * 100),
            "high_52w": hi52, "low_52w": lo52,
            "low_60d": float(c.tail(60).min()),
            "pct_from_52w_high": float((spot / hi52 - 1) * 100),
            "pct_above_52w_low": float((spot / lo52 - 1) * 100),
            "support": round(sup["price"], 2) if sup else np.nan,
            "support_touches": sup["touches"] if sup else 0,
            "pct_to_support": float((sup["price"] / spot - 1) * 100) if sup else np.nan,
            "resistance": round(res["price"], 2) if res else np.nan,
            "resistance_touches": res["touches"] if res else 0,
            "pct_to_resistance": float((res["price"] / spot - 1) * 100) if res else np.nan,
            "rsi14": round(rsi(c), 1), "atr14": round(a, 2),
            "atr_pct": round(a / spot * 100, 2),
            "avg_vol_20d": float(v.tail(20).mean()) if v.notna().any() else np.nan,
            "vol_surge": float(v.tail(5).mean() / v.tail(60).mean())
                          if v.notna().sum() > 60 and v.tail(60).mean() else np.nan,
        }
        # momentum block
        for lb, lab in ((21, "1m"), (63, "3m"), (126, "6m"), (252, "12m")):
            r[f"ret_{lab}_pct"] = (float((c.iloc[-1] / c.iloc[-lb - 1] - 1) * 100)
                                   if len(c) > lb else np.nan)
        # 12-1 momentum: the academic definition, skipping the last month
        r["mom_12_1_pct"] = (float((c.iloc[-22] / c.iloc[-253] - 1) * 100)
                             if len(c) > 253 else np.nan)
        if spy is not None:
            sp = spy.reindex(c.index).dropna()
            j = c.reindex(sp.index)
            if len(sp) > 63:
                r["rs_3m_vs_spy"] = float(((j.iloc[-1] / j.iloc[-64])
                                           - (sp.iloc[-1] / sp.iloc[-64])) * 100)
        rows.append(r)
    return pd.DataFrame(rows)


# ------------------------------------------------------------ macro betas


def macro_betas(close: pd.DataFrame, syms: list[str], lookback: int = 504) -> pd.DataFrame:
    """ONE multivariate regression per stock, not five univariate ones.

    Oil and the dollar move together; the market leg absorbs most of both.
    Regressing on each factor separately credits the same move to every
    factor in turn and produces betas that cannot all be true at once.
    """
    fac = {}
    for name, col in FACTOR_COLS.items():
        if col in close:
            fac[name] = close[col]
    if "SPY" not in fac:
        return pd.DataFrame()
    F = pd.DataFrame(fac).pct_change().tail(lookback)
    F["VIX"] = pd.DataFrame(fac)["VIX"].pct_change().tail(lookback) if "VIX" in fac else np.nan
    F = F.dropna(how="all", axis=1)
    names = [c for c in F.columns]
    fomc = set(fomc_dates().date)
    rows = []
    for s in syms:
        if s not in close:
            continue
        y = close[s].pct_change().tail(lookback)
        d = pd.concat([y.rename("y"), F], axis=1).dropna()
        if len(d) < 120:
            continue
        X = np.column_stack([np.ones(len(d))] + [d[c].to_numpy() for c in names])
        try:
            coef, *_ = np.linalg.lstsq(X, d["y"].to_numpy(), rcond=None)
        except Exception:
            continue
        pred = X @ coef
        resid = d["y"].to_numpy() - pred
        ss_tot = float(((d["y"] - d["y"].mean()) ** 2).sum())
        r2 = 1 - float((resid ** 2).sum()) / ss_tot if ss_tot > 0 else np.nan
        row = {"symbol": s, "alpha_daily_pct": float(coef[0] * 100),
               "r2": round(r2, 3),
               "resid_vol_ann_pct": float(np.std(resid, ddof=1) * np.sqrt(252) * 100)}
        for i, c in enumerate(names, start=1):
            row[f"beta_{c.lower()}"] = round(float(coef[i]), 3)
        # FOMC behaviour on the 67 real decision dates
        isf = np.array([dd.date() in fomc for dd in d.index])
        if isf.sum() >= 4:
            row["fomc_mean_move_pct"] = float(d["y"][isf].mean() * 100)
            row["fomc_mean_abs_pct"] = float(d["y"][isf].abs().mean() * 100)
            row["normal_mean_abs_pct"] = float(d["y"][~isf].abs().mean() * 100)
            row["fomc_amplifier"] = (round(row["fomc_mean_abs_pct"]
                                           / row["normal_mean_abs_pct"], 2)
                                     if row["normal_mean_abs_pct"] else np.nan)
            row["fomc_n_days"] = int(isf.sum())
        rows.append(row)
    return pd.DataFrame(rows)


def why_it_moved(close: pd.DataFrame, betas: pd.DataFrame) -> pd.DataFrame:
    """Today's return minus what the factor betas predicted.

    Splits a move into 'the market/oil/rates dragged it' and 'something
    happened at this company'. The residual is the company-specific part.
    """
    if betas.empty:
        return pd.DataFrame()
    fac_ret = {}
    for name, col in FACTOR_COLS.items():
        if col in close:
            r = close[col].pct_change()
            if len(r) > 1:
                fac_ret[name.lower()] = float(r.iloc[-1])
    rows = []
    for _, b in betas.iterrows():
        s = b["symbol"]
        if s not in close:
            continue
        act = close[s].pct_change()
        if len(act) < 2 or not np.isfinite(act.iloc[-1]):
            continue
        act = float(act.iloc[-1])
        expl = {}
        pred = 0.0
        for f, fr in fac_ret.items():
            bcol = f"beta_{f}"
            if bcol in b and np.isfinite(b[bcol]):
                contrib = float(b[bcol]) * fr
                expl[f] = contrib
                pred += contrib
        resid = act - pred
        top = max(expl, key=lambda k: abs(expl[k])) if expl else None
        rows.append({
            "symbol": s,
            "move_today_pct": round(act * 100, 2),
            "explained_pct": round(pred * 100, 2),
            "company_specific_pct": round(resid * 100, 2),
            "biggest_driver": top,
            "driver_contrib_pct": round(expl[top] * 100, 2) if top else np.nan,
            "why": ("mostly company news" if abs(resid) > abs(pred)
                    else f"mostly {top}"),
        })
    return pd.DataFrame(rows)


# ------------------------------------------------------------- the score


def _pct_rank_within(df: pd.DataFrame, col: str, group: str,
                     higher_is_better: bool) -> pd.Series:
    if col not in df:
        return pd.Series(np.nan, index=df.index)
    v = pd.to_numeric(df[col], errors="coerce")
    r = v.groupby(df[group]).rank(pct=True, method="average")
    return r if higher_is_better else 1 - r


def fundamental_score(f: pd.DataFrame) -> pd.DataFrame:
    """0-100, ranked WITHIN SECTOR, from four equally weighted blocks.

    Sector-neutral because an absolute P/E screen just re-discovers which
    sector something is in: every REIT and utility would sit at the bottom
    of a raw value rank forever, and every software name at the bottom of
    a raw asset-turnover rank.

    Every component is emitted next to the score. A score you cannot take
    apart is a black box.
    """
    d = f.copy()
    if "sector" not in d:
        d["sector"] = "?"
    d["sector"] = d["sector"].fillna("?")
    d["earnings_yield"] = 1 / pd.to_numeric(d.get("trailingPE"), errors="coerce")
    mc = pd.to_numeric(d.get("marketCap"), errors="coerce")
    d["fcf_yield"] = pd.to_numeric(d.get("freeCashflow"), errors="coerce") / mc

    blocks = {
        "value": [("earnings_yield", True), ("fcf_yield", True),
                  ("priceToSalesTrailing12Months", False),
                  ("enterpriseToEbitda", False)],
        "quality": [("returnOnEquity", True), ("returnOnAssets", True),
                    ("grossMargins", True), ("profitMargins", True)],
        "safety": [("debtToEquity", False), ("currentRatio", True)],
        "growth": [("revenueGrowth", True), ("earningsGrowth", True)],
    }
    for blk, cols in blocks.items():
        parts = [_pct_rank_within(d, c, "sector", hib) for c, hib in cols]
        d[f"score_{blk}"] = (pd.concat(parts, axis=1).mean(axis=1) * 100).round(1)
    sub = d[[f"score_{b}" for b in blocks]]
    # require at least 3 of 4 blocks or the score is not comparable
    d["RATE"] = np.where(sub.notna().sum(axis=1) >= 3, sub.mean(axis=1).round(1), np.nan)
    d["rate_grade"] = pd.cut(d["RATE"], [-0.1, 20, 40, 60, 80, 100],
                             labels=["F", "D", "C", "B", "A"])
    return d


# ------------------------------------------------------------- buy zone


def buy_zone(tech: pd.DataFrame, fund: pd.DataFrame,
             max_discount: float = 0.25) -> pd.DataFrame:
    """Four independent anchors, shown separately, then blended.

    This is a discipline tool that stops you chasing, NOT a forecast. Level
    bounces were measured in this project at about +0.5pp over a coin flip.

    Two guards:
      * bottom-quartile RATE -> 'CHEAP FOR A REASON', no price printed. A low
        price on a deteriorating company is not an entry.
      * spot already under every anchor -> 'BELOW ZONE - verify'. Cheap and
        broken look identical from price alone.
    """
    d = tech.merge(fund[["symbol", "RATE", "forwardPE", "trailingPE", "forwardEps",
                         "sector"]], on="symbol", how="left")
    # anchor 2: price at the lower of own-median and sector-median forward P/E
    # yfinance defines forwardPE = price / forwardEps, so min(own_pe, sector_pe)
    # * eps returns THE PRICE ITSELF whenever the own leg wins -- which is half
    # the index. That is not a valuation anchor, it is the quote, and it was
    # inflating n_anchors and flipping zone labels on sub-0.5% quote drift.
    # Use the SECTOR median only, and require a real discount.
    fpe = pd.to_numeric(d["forwardPE"], errors="coerce")
    eps = pd.to_numeric(d["forwardEps"], errors="coerce")
    sect_pe = fpe.groupby(d["sector"]).transform("median")
    cand = sect_pe * eps
    d["anchor_valuation"] = np.where(
        (eps > 0) & (sect_pe > 0) & (cand < d["price"] * 0.98), cand, np.nan)
    d["anchor_support"] = d["support"]
    d["anchor_trend"] = d["sma200"]
    d["anchor_volatility"] = d["price"] - 1.5 * d["atr14"]

    A = ["anchor_support", "anchor_valuation", "anchor_trend", "anchor_volatility"]
    below = d[A].where(d[A].lt(d["price"], axis=0))
    d["n_anchors"] = below.notna().sum(axis=1)
    d["buy_zone_high"] = below.median(axis=1).round(2)
    d["buy_zone_low"] = below.min(axis=1).round(2)

    floor = d["price"] * (1 - max_discount)
    perfect = below.median(axis=1).clip(lower=floor).round(2)
    q1 = d["RATE"].quantile(0.25)

    d["perfect_buy"] = perfect
    d["buy_note"] = ""
    d.loc[d["RATE"] <= q1, "buy_note"] = "CHEAP FOR A REASON (bottom-quartile rate)"
    d.loc[d["n_anchors"] == 0, "buy_note"] = "BELOW ZONE - verify (cheap or broken?)"
    d.loc[d["RATE"].isna(), "buy_note"] = "no rate - fundamentals missing"
    d.loc[d["buy_note"] != "", "perfect_buy"] = np.nan
    d["discount_to_buy_pct"] = ((d["perfect_buy"] / d["price"] - 1) * 100).round(2)

    # ZONE_STATUS, not "at or below buy".
    # perfect_buy is the median of the anchors that are BELOW spot, so spot is
    # under it by construction is impossible -- the old boolean was tautological
    # and read "no" for all 500 rows. What actually matters is how many anchors
    # the price has already fallen through.
    d["zone_status"] = np.select(
        [d["n_anchors"] == 0,
         d["n_anchors"] == 1,
         d["price"] <= d["buy_zone_high"] * 1.03,
         d["price"] <= d["buy_zone_high"] * 1.10],
        ["BELOW ZONE", "AT ZONE", "IN ZONE", "NEAR ZONE"],
        default="ABOVE ZONE")
    d["pct_above_zone"] = ((d["price"] / d["buy_zone_high"] - 1) * 100).round(2)

    # THE EXACT PRICE THAT PUTS IT IN THE ZONE.
    # zone_status is "IN ZONE" when price <= buy_zone_high * 1.03, so the
    # trigger price is exactly that. Without this column a NEAR ZONE row tells
    # you it is close and makes you do the arithmetic yourself, which is the
    # difference between a dashboard and a to-do list.
    # ---------------- RISK / REWARD ----------------------------------
    # The one framework here that does NOT require predicting anything.
    #   risk   = distance down to the nearest support (where you'd admit
    #            you were wrong and get out)
    #   reward = distance up to the nearest resistance (where price has
    #            repeatedly failed before, so a realistic first target)
    #   R:R    = reward / risk
    # Expectancy = win_rate*reward - loss_rate*risk, so the number that
    # actually matters is the BREAKEVEN HIT RATE: 1 / (1 + R:R). At 3:1 a
    # setup only needs to work 25% of the time to break even. That is a
    # statement about arithmetic, not about the future, which is why it
    # survives when the predictive claims in this workbook do not.
    sup = pd.to_numeric(d.get("support"), errors="coerce")
    res = pd.to_numeric(d.get("resistance"), errors="coerce")
    px = d["price"]
    d["risk_pct"] = ((px - sup) / px * 100).round(2)
    d["reward_pct"] = ((res - px) / px * 100).round(2)
    d["risk_$"] = (px - sup).round(2)
    d["reward_$"] = (res - px).round(2)
    ok = (d["risk_pct"] > 0.2) & (d["reward_pct"] > 0)
    d["RR"] = np.where(ok, (d["reward_pct"] / d["risk_pct"]).round(2), np.nan)
    d["breakeven_hit_rate_pct"] = np.where(
        d["RR"].notna(), (100 / (1 + d["RR"])).round(1), np.nan)
    d["RR_grade"] = pd.cut(d["RR"], [-0.01, 1, 2, 3, 5, 999],
                           labels=["poor", "thin", "fair", "GOOD", "EXCELLENT"])
    # both levels need touches to be worth anything; a one-touch level is a
    # coincidence and an R:R built on two of them is arithmetic on noise
    st = pd.to_numeric(d.get("support_touches"), errors="coerce").fillna(0)
    rt = pd.to_numeric(d.get("resistance_touches"), errors="coerce").fillna(0)
    d["levels_confirmed"] = np.where((st >= 2) & (rt >= 2), "yes", "WEAK")

    # ---------------- THE BUY ZONE, REBUILT --------------------------
    # The old zone was the median of four anchors below spot. Measured against
    # random baskets on a point-in-time universe it returned -0.23% per
    # quarter and was ahead on 46% of dates. Tuning a definition that failed
    # only polishes it, so the zone is now anchored to the one thing that DID
    # survive its control: risk:reward.
    #
    # Between a support S and a resistance R, buying at price P gives
    #     R:R = (R - P) / (P - S)
    # Solve for the P that yields a chosen ratio k:
    #     P = S + (R - S) / (k + 1)
    # At 3:1 that is the bottom quarter of the range; at 5:1 the bottom sixth.
    # These are not opinions about where price will go -- they are the prices
    # at which the arithmetic starts paying for a 26% hit rate.
    band = (res - sup)
    valid = sup.notna() & res.notna() & (band > 0)
    d["price_for_2R"] = np.where(valid, (sup + band / 3.0).round(2), np.nan)
    d["price_for_3R"] = np.where(valid, (sup + band / 4.0).round(2), np.nan)
    d["price_for_5R"] = np.where(valid, (sup + band / 6.0).round(2), np.nan)
    d["pct_to_3R"] = ((d["price_for_3R"] / px - 1) * 100).round(2)
    d["dollars_to_3R"] = (px - d["price_for_3R"]).round(2)

    rr_now = pd.to_numeric(d.get("RR"), errors="coerce")
    conf_now = d.get("levels_confirmed", pd.Series("WEAK", index=d.index)).eq("yes")
    d["ZONE"] = np.select(
        [~valid,
         ~conf_now,
         rr_now >= 5,
         rr_now >= 3,
         rr_now >= 2,
         rr_now >= 1],
        ["no levels", "unconfirmed levels", "PRIME (5R+)", "BUY ZONE (3R+)",
         "FAIR (2R+)", "thin (1-2R)"],
        default="AVOID (under 1R)")
    # ---------------- CAPITULATION -----------------------------------
    # Measured 2026-09-10 on a point-in-time universe, 50,825 observations:
    #   drawdown worse than -40%   +4.82% vs random, p=0.000   <- switches on
    #   -25 to -40%                -0.09%                      <- nothing
    #   -15 to -25%                -0.04%                      <- nothing
    #   within 5% of the high      -0.64%, p=0.017             <- slightly bad
    # Positive in 10 of 14 years, and +3.47% even after removing 2020 and
    # 2022, so it is not just crisis clustering.
    #
    # The counterintuitive half: filtering for "fundamentals still healthy"
    # made it WORSE. Down 20%+ with revenue growing scored -0.14%; with
    # revenue SHRINKING it scored +2.67%. Filings look backward and are ~57
    # days stale; price looks forward. A collapsed price beside a healthy
    # last 10-Q means the market knows something the filing does not yet.
    # So depth is the signal and fundamental health is NOT a confirmation.
    # THE FALLING-KNIFE FILTER, found by reading the actual cases rather than
    # the averages. MRNA triggered -40% for 25 CONSECUTIVE MONTHS, from -42%
    # in Jun 2023 down to -83% in Mar 2025, and the trigger said buy the whole
    # way. Splitting those events by whether price was still making new lows:
    #     still making new lows   +1.12% edge, 60% win   (n=326)
    #     stopped making new lows +4.41% edge, 67% win   (n=1,300)
    #     ...and 20% off the low  +6.08% edge, 72% win   (n=433)
    # MRNA itself: -17.7% while still falling, +2.6% after it stopped.
    # Depth says WHICH stock. This says WHEN.
    lo60 = pd.to_numeric(d.get("low_52w"), errors="coerce")
    if "low_60d" in d:
        lo60 = pd.to_numeric(d["low_60d"], errors="coerce")
    off_low = ((px / lo60 - 1) * 100).round(1)
    d["pct_off_recent_low"] = off_low
    d["still_falling"] = np.where(off_low <= 2, "STILL FALLING", "stabilising")

    dd52 = pd.to_numeric(d.get("pct_from_52w_high"), errors="coerce")
    deep = dd52 <= -40
    d["CAPITULATION"] = np.select(
        [deep & (off_low >= 20), deep & (off_low > 2), deep,
         dd52 <= -25, dd52 <= -15, dd52 <= -5],
        ["DEEP + 20% OFF LOW (+6.1%)", "DEEP, stabilising (+4.4%)",
         "DEEP but STILL FALLING (+1.1%)", "-25 to -40 (no edge)",
         "-15 to -25 (no edge)", "-5 to -15 (no edge)"],
        default="near highs (-0.6%)")
    d["zone_entry_price"] = (d["buy_zone_high"] * 1.03).round(2)
    d["pct_to_zone_entry"] = ((d["zone_entry_price"] / d["price"] - 1) * 100).round(2)
    d["dollars_to_zone"] = (d["price"] - d["zone_entry_price"]).round(2)

    # ---------------- RISK CALCULATOR --------------------------------
    # Sizing off the ACTUAL stop (support), not a fixed percentage. Risking
    # $250 on a name whose support is 2% away buys five times the position
    # of one whose support is 10% away -- same dollars at risk, very
    # different exposure. Getting this backwards is how accounts die on
    # trades that were "only 1% risk".
    for risk in (100, 250, 500):
        shares = np.where(d["risk_$"] > 0, risk / d["risk_$"], np.nan)
        d[f"shares_risk_${risk}"] = np.floor(shares)
        d[f"cost_risk_${risk}"] = (np.floor(shares) * px).round(0)
        d[f"gain_if_target_${risk}"] = (np.floor(shares) * d["reward_$"]).round(0)

    # ---------------- CAN YOU ACTUALLY TAKE IT? ----------------------
    # A tight stop means a BIG position for the same dollar risk. KEYS has
    # support 1.34% away, so risking $250 needs an $18,482 position -- three
    # quarters of a 25k account in one name. The signal is fine; the trade is
    # not available. So the sheet sizes against the ACCOUNT first and reports
    # what you would really be risking.
    afford = SLEEVE * MAX_POS_PCT
    cap_sh = np.floor(np.where(px > 0, afford / px, np.nan))
    d["max_shares_for_account"] = cap_sh
    d["actual_position_$"] = (cap_sh * px).round(0)
    d["actual_risk_$"] = (cap_sh * d["risk_$"]).round(0)
    d["actual_gain_$"] = (cap_sh * d["reward_$"]).round(0)
    need = pd.to_numeric(d["cost_risk_$250"], errors="coerce")
    d["fits_account"] = np.where(need <= afford, "yes",
                                 np.where(cap_sh >= 1, "capped", "TOO BIG"))
    # a sub-$300 position is not worth the spread and the attention
    d["worth_taking"] = np.where(d["actual_position_$"] < 300, "too small",
                                 np.where(cap_sh < 1, "1 share unaffordable", ""))
    return d





# ------------------------------------------------------------ halal flag


ACCOUNT_DEFAULTS_SET = True

EXCLUDED_INDUSTRY_WORDS = (
    "bank", "insurance", "capital market", "consumer finance", "mortgage",
    "financial exchange", "asset management", "tobacco", "brewer",
    "distiller", "winer", "casino", "gaming", "resort", "aerospace &amp; defense",
    "defense",
)


def halal_flag(f: pd.DataFrame) -> pd.DataFrame:
    """AUTO-SUGGESTION ONLY. The operator fills the real column by hand.

    Two screens: a business screen on industry text, and the common
    financial screens (debt / market cap < 33%, cash+interest-bearing
    securities / market cap < 33%). This is a starting point for manual
    review, not a ruling.
    """
    d = f.copy()
    ind = (d.get("industry", pd.Series("", index=d.index)).fillna("").str.lower()
           + " " + d.get("sector", pd.Series("", index=d.index)).fillna("").str.lower())
    biz_fail = ind.apply(lambda t: any(w in t for w in EXCLUDED_INDUSTRY_WORDS))
    mc = pd.to_numeric(d.get("marketCap"), errors="coerce")
    debt = pd.to_numeric(d.get("totalDebt"), errors="coerce")
    cash = pd.to_numeric(d.get("totalCash"), errors="coerce")
    d["debt_to_mcap_pct"] = (debt / mc * 100).round(1)
    d["cash_to_mcap_pct"] = (cash / mc * 100).round(1)
    debt_fail = d["debt_to_mcap_pct"] > 33
    cash_fail = d["cash_to_mcap_pct"] > 33
    reason = np.where(biz_fail, "business activity",
             np.where(debt_fail, "debt/mcap > 33%",
             np.where(cash_fail, "cash/mcap > 33%", "")))
    d["halal_auto"] = np.where(biz_fail | debt_fail | cash_fail, "FAIL", "pass")
    d.loc[mc.isna(), "halal_auto"] = "unknown"
    d["halal_auto_reason"] = reason
    d["halal_MANUAL"] = ""            # operator fills this; auto is advisory
    return d


def verdict(d: pd.DataFrame) -> pd.DataFrame:
    """One column, so you do not have to weigh six others.

    MUST run on the FINAL merged frame -- MOMENTUM_SCORE is computed after
    buy_zone, so calling this inside buy_zone silently left momentum NaN and
    produced zero STRONG rows.

    Built ONLY from things that survived a control:
      R:R > 2      measured +0.02R to +0.08R over shuffled-date entries, and
                   monotonic across buckets. UNDER 2:1 measured WORSE than
                   random, so it is a hard veto, not a soft negative.
      momentum     the only signal here that beat its control (+1.83%/qtr)
      levels 2+    a one-touch level is a coincidence
      quality      bottom-quartile RATE is cheap for a reason

    Deliberately EXCLUDED: zone_status and analyst actions. Both measured
    NEGATIVE against their own controls, so putting them in a buy signal
    would be importing a known loss.
    """
    d = d.copy()
    rr = pd.to_numeric(d.get("RR"), errors="coerce")
    mom = pd.to_numeric(d.get("MOMENTUM_SCORE"), errors="coerce")
    rate = pd.to_numeric(d.get("RATE"), errors="coerce")
    conf = d.get("levels_confirmed", pd.Series("WEAK", index=d.index)).eq("yes")
    q1 = rate.quantile(0.25)

    veto = (rr < 2) | (~conf) | (rate <= q1)
    # PRIME requires the 5R zone AND momentum: the two measurements that beat
    # their controls, stacked. That is deliberately rare.
    capstr = d.get("CAPITULATION", pd.Series("", index=d.index)).astype(str)
    # a falling knife does NOT upgrade anything -- it measured +1.1%, barely
    # distinguishable from the market, and it is where MRNA lost 25 times
    cap = capstr.str.startswith("DEEP") & ~capstr.str.contains("STILL FALLING")
    # capitulation is a SEPARATE measured effect, not an R:R setup, so it can
    # stand on its own -- but it still needs real levels and a real business
    prime = (~veto) & (((rr >= 5) & (mom >= 60)) | (cap & (rr >= 3)))
    strong = (~veto) & (rr >= 3) & (mom >= 60)
    ok_ = (~veto) & (rr >= 2)
    d["VERDICT"] = np.select([veto, prime, strong, ok_],
                             ["AVOID", "PRIME", "STRONG", "OK"], default="watch")
    d.loc[rr.isna(), "VERDICT"] = "no levels"
    d["why_verdict"] = np.where(
        rr.isna(), "no clean support/resistance pair",
        np.where(rr < 2, "R:R under 2:1 -- measured WORSE than a random entry",
        np.where(~conf, "levels have under 2 touches -- not real levels",
        np.where(rate <= q1, "bottom-quartile quality -- cheap for a reason",
        np.where(strong, "R:R 3:1+, confirmed levels, momentum, sound company",
                 "R:R clears 2:1 on confirmed levels, momentum is weak")))))
    return d
