"""Full forensic breakdown of today's move, one row per stock.

Answers, in order:
    HOW BIG      in percent, in ATRs, in standard deviations, and where it
                 ranks against the last year of that stock's own days
    WHEN         gap at the open (overnight news) vs drift during the session
                 (flow) -- these have completely different causes
    CONFIRMED?   volume versus its own 20-day average; a big move on no volume
                 is usually not news
    WHO ELSE     the equal-weight move of its GICS sector peers, and what
                 fraction of them went the same way. A stock falling 4% while
                 its whole sector falls 4% has not had a bad day, its sector has
    WHAT DROVE   each macro factor's contribution separately, in percentage
                 points: beta_factor x factor_return_today. These sum to the
                 explained part; the remainder is company-specific
    CATALYST     analyst action recorded today, earnings proximity, unusual
                 option premium
    VERDICT      one plain-English sentence assembled from the above

Every contribution is an ATTRIBUTION, not a cause. A -0.4pp oil contribution
means "a stock with this oil beta, on a day oil did what it did, would be
expected to move -0.4pp". It does not mean oil moved this stock today.
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
FACTORS = {"spy": "SPY", "tlt": "TLT", "gld": "GLD",
           "oil": "USO", "dxy": "UUP", "vix": "^VIX"}
FACTOR_LABEL = {"spy": "the market", "tlt": "bonds", "gld": "gold",
                "oil": "oil", "dxy": "the dollar", "vix": "volatility"}


def _last_two(s: pd.Series):
    s = s.dropna()
    return (float(s.iloc[-1]), float(s.iloc[-2])) if len(s) >= 2 else (np.nan, np.nan)


def build(close, openp, high, low, vol, betas, fund, tape, options,
          universe) -> pd.DataFrame:
    sect = universe.set_index("symbol")["sector"].to_dict()
    name = (fund.set_index("symbol")["shortName"].to_dict()
            if "shortName" in fund else {})

    # today's factor returns, computed once
    fret = {}
    for k, col in FACTORS.items():
        if col in close:
            a, b = _last_two(close[col])
            fret[k] = a / b - 1 if np.isfinite(a) and np.isfinite(b) and b else np.nan
    b_idx = betas.set_index("symbol") if not betas.empty else pd.DataFrame()

    # sector move: equal-weight average of the sector's own members TODAY
    day = {}
    for s in close.columns:
        a, b = _last_two(close[s])
        day[s] = (a / b - 1) if np.isfinite(a) and np.isfinite(b) and b else np.nan
    day = pd.Series(day)
    sec_move, sec_share = {}, {}
    for sec in set(sect.values()):
        mem = [s for s, v in sect.items() if v == sec and s in day
               and np.isfinite(day[s])]
        if len(mem) >= 3:
            d = day[mem]
            sec_move[sec] = float(d.mean())
            sec_share[sec] = d

    # catalysts
    act = {}
    if not tape.empty:
        t = tape.copy()
        t["d"] = pd.to_datetime(t["date"], format="%b %d, %Y", errors="coerce")
        recent = t[t["d"] >= pd.Timestamp.now().normalize() - pd.Timedelta(days=2)]
        for sym, g in recent.groupby("symbol"):
            g = g.sort_values("d")
            r = g.iloc[-1]
            act[sym] = (f"{r['action']} -> {r['rating']}"
                        + (f" PT ${r['target']}" if pd.notna(r.get("target")) else "")
                        + f" ({r['firm']})")
    unusual = set()
    if not options.empty and "UNUSUAL" in options:
        unusual = set(options.loc[options["UNUSUAL"] == "UNUSUAL", "symbol"])
    earn = {}
    if "next_earnings" in fund:
        ne = pd.to_datetime(fund["next_earnings"], errors="coerce")
        d2e = (ne - pd.Timestamp.now().normalize()).dt.days
        earn = dict(zip(fund["symbol"], d2e))

    rows = []
    for s in close.columns:
        if s not in sect:
            continue
        c = close[s].dropna()
        if len(c) < 60:
            continue
        px, prev = float(c.iloc[-1]), float(c.iloc[-2])
        if not (np.isfinite(px) and np.isfinite(prev) and prev):
            continue
        mv = px / prev - 1
        o = float(openp[s].iloc[-1]) if s in openp and np.isfinite(
            openp[s].iloc[-1]) else np.nan
        gap = (o / prev - 1) if np.isfinite(o) else np.nan
        intraday = (px / o - 1) if np.isfinite(o) and o else np.nan
        dr = c.pct_change().dropna()
        sd = float(dr.tail(252).std())
        z = mv / sd if sd else np.nan
        hi = high[s].dropna() if s in high else c
        lo = low[s].dropna() if s in low else c
        tr = float((hi.tail(15) - lo.tail(15)).mean())
        in_atr = (px - prev) / tr if tr else np.nan
        rank = float((dr.tail(252).abs() < abs(mv)).mean() * 100)
        bigger = int((dr.tail(252).abs() >= abs(mv)).sum())
        v = vol[s].dropna() if s in vol else pd.Series(dtype=float)
        vx = (float(v.iloc[-1]) / float(v.tail(21).mean())
              if len(v) > 21 and v.tail(21).mean() else np.nan)

        sec = sect[s]
        smv = sec_move.get(sec, np.nan)
        peers = sec_share.get(sec)
        same = (float((np.sign(peers) == np.sign(mv)).mean() * 100)
                if peers is not None and len(peers) else np.nan)

        r = {"symbol": s, "name": name.get(s, ""), "sector": sec, "price": px,
             "move_pct": mv * 100,
             "gap_pct": gap * 100 if np.isfinite(gap) else np.nan,
             "intraday_pct": intraday * 100 if np.isfinite(intraday) else np.nan,
             "move_where": ("GAP (overnight)" if np.isfinite(gap) and abs(gap) > abs(mv) * 0.6
                            else "INTRADAY (session)" if np.isfinite(intraday)
                            and abs(intraday) > abs(mv) * 0.6 else "mixed"),
             "move_in_sigma": z, "move_in_atr": in_atr,
             "pctile_vs_own_year": rank,
             "bigger_days_past_yr": bigger,
             "volume_x_normal": vx,
             "volume_confirms": ("YES" if np.isfinite(vx) and vx >= 1.5
                                 else "no" if np.isfinite(vx) else ""),
             "sector_move_pct": smv * 100 if np.isfinite(smv) else np.nan,
             "vs_sector_pct": (mv - smv) * 100 if np.isfinite(smv) else np.nan,
             "pct_peers_same_way": same}

        expl, contrib = 0.0, {}
        if s in b_idx.index:
            b = b_idx.loc[s]
            for k in FACTORS:
                col = f"beta_{k}"
                if col in b and np.isfinite(b[col]) and np.isfinite(fret.get(k, np.nan)):
                    cval = float(b[col]) * fret[k]
                    contrib[k] = cval
                    r[f"from_{k}_pp"] = cval * 100
                    expl += cval
            r["r2_of_model"] = float(b["r2"]) if "r2" in b else np.nan
        r["explained_pp"] = expl * 100
        resid = mv - expl
        r["company_specific_pp"] = resid * 100
        r["residual_sigma"] = resid / sd if sd else np.nan
        if contrib:
            top = max(contrib, key=lambda k: abs(contrib[k]))
            r["biggest_macro_driver"] = FACTOR_LABEL[top]
            r["driver_pp"] = contrib[top] * 100

        r["analyst_action"] = act.get(s, "")
        r["days_to_earnings"] = earn.get(s, np.nan)
        r["unusual_options"] = "YES" if s in unusual else ""

        # ---- the sentence
        bits = []
        size = ("a huge" if abs(z) > 3 else "a big" if abs(z) > 2
                else "a notable" if abs(z) > 1 else "a quiet")
        bits.append(f"{size} {'up' if mv > 0 else 'down'} day "
                    f"({mv*100:+.1f}%, {abs(z):.1f} sigma)")
        if np.isfinite(gap) and abs(gap) > abs(mv) * 0.6:
            bits.append("almost all of it gapped overnight")
        elif np.isfinite(intraday) and abs(intraday) > abs(mv) * 0.6:
            bits.append("it moved during the session, not on the open")
        if np.isfinite(smv):
            if abs(mv - smv) < abs(smv) * 0.4:
                bits.append(f"but its whole sector moved {smv*100:+.1f}%, so this "
                            "is sector-wide, not company news")
            elif np.isfinite(same) and same < 45:
                bits.append(f"and peers did NOT follow (only {same:.0f}% same "
                            "direction) - this looks company-specific")
        if abs(resid) > abs(expl) * 1.5 and abs(r.get("residual_sigma", 0)) > 1:
            bits.append("macro factors do not explain it")
        elif contrib:
            bits.append(f"mostly attributable to {FACTOR_LABEL[top]}")
        if r["analyst_action"]:
            bits.append(f"analyst action today: {r['analyst_action']}")
        if np.isfinite(r["days_to_earnings"]) and 0 <= r["days_to_earnings"] <= 5:
            bits.append(f"earnings in {int(r['days_to_earnings'])} days")
        if r["unusual_options"]:
            bits.append("unusual option premium today")
        if np.isfinite(vx) and vx >= 2:
            bits.append(f"on {vx:.1f}x normal volume")
        elif np.isfinite(vx) and vx < 0.8 and abs(z) > 1.5:
            bits.append(f"on only {vx:.1f}x normal volume, so treat it with caution")
        r["VERDICT"] = "; ".join(bits) + "."
        rows.append(r)

    d = pd.DataFrame(rows)
    front = ["symbol", "name", "sector", "price", "move_pct", "VERDICT",
             "move_where", "gap_pct", "intraday_pct", "move_in_sigma",
             "move_in_atr", "pctile_vs_own_year", "bigger_days_past_yr",
             "volume_x_normal", "volume_confirms", "sector_move_pct",
             "vs_sector_pct", "pct_peers_same_way", "company_specific_pp",
             "residual_sigma", "explained_pp", "biggest_macro_driver",
             "driver_pp"] + [f"from_{k}_pp" for k in FACTORS] + \
            ["r2_of_model", "analyst_action", "days_to_earnings",
             "unusual_options"]
    d = d[[c for c in front if c in d.columns]
          + [c for c in d.columns if c not in front]]
    return d.sort_values("move_pct", key=lambda s: s.abs(), ascending=False)
