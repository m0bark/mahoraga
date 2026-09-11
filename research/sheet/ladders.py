"""Probation ladders: every rule runs at SIX thresholds at once.

    python research/sheet/ladders.py             # record + mark to market
    python research/sheet/ladders.py --report
    python research/sheet/ladders.py --excel     # write ladders.xlsx
    python research/sheet/ladders.py --sanity    # integrity audit
    python research/sheet/ladders.py --reset bigmoney_1m

WHY LADDERS INSTEAD OF ONE RULE
Running "big money = top 5% unusual" alone means that if the real threshold is
$2m of premium and you picked $1m, you spend a month collecting the wrong
evidence and learn nothing except that your one guess failed. Six rungs run
simultaneously on the same days, so at the end of the month you know WHICH
rung works, not merely whether your single guess did.

The cost is multiple testing: 18 ladders means the best of 18 pure-noise
ledgers sits about sqrt(2*ln(18)) = 2.40 standard errors above zero. The gate
below is set for that, and it is frozen here before any data exists.

PRE-REGISTERED GATE, one per rung, cannot be moved later:
    >= 40 CLOSED positions
    AND mean return vs SPY over the identical holding window > 0
    AND t > 2.40 on that difference   (the 18-ladder selection bar)
    Anything short of all three: keep recording, take no money.

SANITY IS ENFORCED, NOT ASSUMED
--sanity re-reads every ledger and checks the things that would quietly
corrupt a forward record: an entry price that changed after the fact, the
same symbol open twice in one rung, a position marked on a date before it
opened, a row that lost its entry, P&L that disagrees with entry and last
price. A forward ledger is only worth anything if it cannot be edited by
accident, so the check runs automatically on every update.
"""
from __future__ import annotations

import io
import os
import sys
import warnings
from datetime import datetime

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
LOGS = os.path.join(HERE, "logs")
XLSX = os.path.join(HERE, "ladders.xlsx")
HOLD_DAYS = 63
STOP_ATR = 2.0
GATE_N = 40
GATE_T = 2.40                     # sqrt(2*ln(18)), the 18-ladder selection bar
COLS = ["opened", "rung", "symbol", "entry", "trigger", "rate", "sector",
        "stop", "last_price", "last_date", "pnl_pct", "spy_entry", "spy_now",
        "vs_spy_pct", "days_held", "status", "closed"]


def load(n):
    p = os.path.join(CACHE, f"{n}.csv")
    return pd.read_csv(p) if os.path.exists(p) else pd.DataFrame()


def num(d, c):
    return pd.to_numeric(d.get(c), errors="coerce")


# ------------------------------------------------------------------ rungs
# Each returns (symbols, trigger-text). Thresholds are ABSOLUTE where the
# quantity has a natural unit (dollars of option premium) and RELATIVE where
# it does not (a percentile of quality). Six rungs per family.

def _bigmoney(big, fund, lo_notional, min_voi, label):
    if big.empty or "total_notional" not in big:
        return pd.DataFrame()
    m = (num(big, "total_notional") >= lo_notional) & (num(big, "vol_vs_oi") >= min_voi)
    if "skew" in big:
        m &= big["skew"].astype(str).eq("CALL-HEAVY")
    d = big[m][["symbol"]].copy()
    d["trigger"] = (label + " | $"
                    + (num(big[m], "total_notional") / 1e6).round(1).astype(str)
                    + "m premium, vol/OI "
                    + num(big[m], "vol_vs_oi").round(2).astype(str))
    return d


def _buyzone(summ, rate_floor, need_anchors, label):
    if summ.empty or "zone_status" not in summ:
        return pd.DataFrame()
    m = summ["zone_status"].isin(["IN ZONE", "AT ZONE"])
    if rate_floor is not None:
        m &= num(summ, "RATE") >= rate_floor
    if need_anchors and "n_anchors" in summ:
        m &= num(summ, "n_anchors") >= need_anchors
    d = summ[m][["symbol"]].copy()
    d["trigger"] = (label + " | " + summ[m]["zone_status"].astype(str)
                    + " rate " + num(summ[m], "RATE").round(0).astype(str))
    return d


def _analyst(an, actions, min_upside, label):
    if an.empty or "last_action" not in an:
        return pd.DataFrame()
    m = (an["last_action"].astype(str).str.startswith(actions)
         & (num(an, "days_ago") <= 2))
    if min_upside is not None:
        m &= num(an, "last_target_upside_pct") >= min_upside
    d = an[m][["symbol"]].copy()
    d["trigger"] = (label + " | " + an[m]["last_action"].astype(str)
                    + " " + an[m]["last_rating"].astype(str)
                    + " (" + an[m]["last_firm"].astype(str) + ")")
    return d


LADDERS = {
    # big money: the question is WHERE the premium threshold bites
    "bigmoney_500k": lambda s, a, b: _bigmoney(b, s, 5e5, 0.3, ">$0.5m"),
    "bigmoney_1m":   lambda s, a, b: _bigmoney(b, s, 1e6, 0.3, ">$1m"),
    "bigmoney_2m":   lambda s, a, b: _bigmoney(b, s, 2e6, 0.3, ">$2m"),
    "bigmoney_5m":   lambda s, a, b: _bigmoney(b, s, 5e6, 0.3, ">$5m"),
    "bigmoney_voi1": lambda s, a, b: _bigmoney(b, s, 1e6, 1.0, ">$1m, vol>OI"),
    "bigmoney_voi2": lambda s, a, b: _bigmoney(b, s, 1e6, 2.0, ">$1m, vol>2xOI"),
    # buy zone: the question is how much quality to demand alongside the level
    "buyzone_any":   lambda s, a, b: _buyzone(s, None, 0, "any rate"),
    "buyzone_r40":   lambda s, a, b: _buyzone(s, 40, 0, "rate>=40"),
    "buyzone_r55":   lambda s, a, b: _buyzone(s, 55, 0, "rate>=55"),
    "buyzone_r70":   lambda s, a, b: _buyzone(s, 70, 0, "rate>=70"),
    "buyzone_a2":    lambda s, a, b: _buyzone(s, 40, 2, "rate>=40, 2+ anchors"),
    "buyzone_a3":    lambda s, a, b: _buyzone(s, 40, 3, "rate>=40, 3 anchors"),
    # analysts: the question is which action, and how much implied upside
    "analyst_any":   lambda s, a, b: _analyst(a, ("Upgrade", "Initiates"), None, "any"),
    "analyst_upg":   lambda s, a, b: _analyst(a, ("Upgrade",), None, "upgrades only"),
    "analyst_up10":  lambda s, a, b: _analyst(a, ("Upgrade", "Initiates"), 10, "upside>=10%"),
    "analyst_up20":  lambda s, a, b: _analyst(a, ("Upgrade", "Initiates"), 20, "upside>=20%"),
    "analyst_up30":  lambda s, a, b: _analyst(a, ("Upgrade", "Initiates"), 30, "upside>=30%"),
    "analyst_init":  lambda s, a, b: _analyst(a, ("Initiates",), None, "initiations only"),
}


def path(rung):
    return os.path.join(LOGS, f"L_{rung}.csv")


def read(rung):
    p = path(rung)
    if not os.path.exists(p):
        return pd.DataFrame(columns=COLS)
    d = pd.read_csv(p)
    for c in COLS:
        if c not in d:
            d[c] = np.nan
    return d


def write(rung, d):
    os.makedirs(LOGS, exist_ok=True)
    d[COLS].to_csv(path(rung), index=False)


def update():
    summ, an, big = load("summary"), load("analysts"), load("bigmoney")
    if summ.empty:
        say("no cache -- run build_workbook.py")
        return
    if "n_anchors" not in summ:
        bz = load("buyzone")
        if not bz.empty and "n_anchors" in bz:
            summ = summ.merge(bz[["symbol", "n_anchors"]], on="symbol", how="left")
    px = summ.set_index("symbol")["price"].to_dict()
    atr = summ.set_index("symbol").get("atr14", pd.Series(dtype=float)).to_dict()
    rate = summ.set_index("symbol").get("RATE", pd.Series(dtype=float)).to_dict()
    sec = summ.set_index("symbol").get("sector", pd.Series(dtype=object)).to_dict()
    today = datetime.now().strftime("%Y-%m-%d")
    spy = np.nan
    sp = os.path.join(CACHE, "px_close.csv")
    if os.path.exists(sp):
        t = pd.read_csv(sp, index_col=0)
        if "SPY" in t:
            spy = float(pd.to_numeric(t["SPY"], errors="coerce").dropna().iloc[-1])

    tot_new = 0
    for rung, fn in LADDERS.items():
        log = read(rung)
        try:
            sig = fn(summ, an, big)
        except Exception as e:
            say(f"  {rung}: rule failed ({type(e).__name__})")
            continue
        if sig is None or sig.empty:
            sig = pd.DataFrame(columns=["symbol", "trigger"])
        openn = set(log.loc[log["status"] == "OPEN", "symbol"]) if len(log) else set()
        new = []
        for _, r in sig.iterrows():
            s = r["symbol"]
            if s in openn or s not in px or not np.isfinite(px[s]):
                continue
            openn.add(s)                      # no duplicate opens inside one pass
            a = atr.get(s, np.nan)
            new.append({"opened": today, "rung": rung, "symbol": s,
                        "entry": round(float(px[s]), 4), "trigger": r["trigger"],
                        "rate": rate.get(s, np.nan), "sector": sec.get(s, ""),
                        "stop": round(float(px[s]) - STOP_ATR * a, 4)
                                if np.isfinite(a) else np.nan,
                        "last_price": round(float(px[s]), 4), "last_date": today,
                        "pnl_pct": 0.0, "spy_entry": spy, "spy_now": spy,
                        "vs_spy_pct": 0.0, "days_held": 0, "status": "OPEN",
                        "closed": ""})
        if new:
            log = pd.concat([log, pd.DataFrame(new)], ignore_index=True)
        tot_new += len(new)

        for i in log.index[log["status"] == "OPEN"]:
            s = log.at[i, "symbol"]
            if s not in px or not np.isfinite(px[s]):
                continue
            p, e = float(px[s]), float(log.at[i, "entry"])
            log.at[i, "last_price"] = round(p, 4)
            log.at[i, "last_date"] = today
            log.at[i, "pnl_pct"] = round((p / e - 1) * 100, 3)
            log.at[i, "spy_now"] = spy
            se = pd.to_numeric(log.at[i, "spy_entry"], errors="coerce")
            if np.isfinite(se) and np.isfinite(spy) and se:
                log.at[i, "vs_spy_pct"] = round((p / e - spy / se) * 100, 3)
            held = (pd.Timestamp(today) - pd.Timestamp(log.at[i, "opened"])).days
            log.at[i, "days_held"] = held
            st = pd.to_numeric(log.at[i, "stop"], errors="coerce")
            if np.isfinite(st) and p <= st:
                log.at[i, "status"], log.at[i, "closed"] = "STOPPED", today
            elif held >= HOLD_DAYS * 1.45:
                log.at[i, "status"], log.at[i, "closed"] = "CLOSED", today
        write(rung, log)
        say(f"  {rung:<16}+{len(new):>3} new  {int((log['status']=='OPEN').sum()):>4} open"
            f"  {len(log):>5} total")
    say(f"\n{tot_new} new positions across {len(LADDERS)} rungs")


def stats(d):
    if d.empty:
        return None
    p = num(d, "pnl_pct")
    v = num(d, "vs_spy_pct").dropna()
    closed = d[d["status"] != "OPEN"]
    t = (v.mean() / (v.std(ddof=1) / np.sqrt(len(v)))
         if len(v) > 2 and v.std(ddof=1) else np.nan)
    return {"n": len(d), "open": int((d["status"] == "OPEN").sum()),
            "closed": len(closed), "win": float((p > 0).mean() * 100),
            "avg": float(p.mean()), "vs_spy": float(v.mean()) if len(v) else np.nan,
            "t": float(t) if np.isfinite(t) else np.nan}


def report():
    say(f"{'rung':<17}{'n':>5}{'open':>6}{'closed':>7}{'win%':>7}"
        f"{'avg':>8}{'vsSPY':>8}{'t':>7}  gate")
    say("-" * 79)
    fam = None
    for rung in LADDERS:
        f = rung.split("_")[0]
        if fam and f != fam:
            say("")
        fam = f
        s = stats(read(rung))
        if not s:
            say(f"{rung:<17}    no entries yet")
            continue
        passed = (s["closed"] >= GATE_N and np.isfinite(s["vs_spy"])
                  and s["vs_spy"] > 0 and np.isfinite(s["t"]) and s["t"] > GATE_T)
        gate = ("PASS" if passed else
                f"need {GATE_N - s['closed']} more closed"
                if s["closed"] < GATE_N else "fails t/vsSPY")
        say(f"{rung:<17}{s['n']:>5}{s['open']:>6}{s['closed']:>7}{s['win']:>6.0f}%"
            f"{s['avg']:>7.2f}%{s['vs_spy']:>7.2f}%"
            f"{(s['t'] if np.isfinite(s['t']) else 0):>7.2f}  {gate}")
    say("-" * 79)
    say(f"GATE (frozen): >={GATE_N} closed, vs-SPY > 0, and t > {GATE_T:.2f}.")
    say(f"t must clear {GATE_T:.2f} not 2.00 because 18 rungs run at once and the")
    say("best of 18 noise ledgers sits that far above zero on its own.")


def sanity(verbose=True):
    """Everything that would quietly corrupt a forward record."""
    problems = []
    seen_prev = {}
    snap = os.path.join(LOGS, "_entry_fingerprint.csv")
    if os.path.exists(snap):
        fp = pd.read_csv(snap)
        seen_prev = {(r.rung, r.symbol, r.opened): r.entry for r in fp.itertuples()}
    fps = []
    for rung in LADDERS:
        d = read(rung)
        if d.empty:
            continue
        for r in d.itertuples():
            fps.append({"rung": rung, "symbol": r.symbol, "opened": r.opened,
                        "entry": r.entry})
            k = (rung, r.symbol, r.opened)
            if k in seen_prev and not np.isclose(float(seen_prev[k]),
                                                 float(r.entry), atol=1e-6):
                problems.append(f"{rung}/{r.symbol}: ENTRY CHANGED "
                                f"{seen_prev[k]} -> {r.entry}")
        op = d[d["status"] == "OPEN"]
        dup = op["symbol"][op["symbol"].duplicated()].tolist()
        if dup:
            problems.append(f"{rung}: same symbol open twice: {sorted(set(dup))}")
        if d["entry"].isna().any():
            problems.append(f"{rung}: {int(d['entry'].isna().sum())} rows lost entry")
        bad = d[pd.to_datetime(d["last_date"], errors="coerce")
                < pd.to_datetime(d["opened"], errors="coerce")]
        if len(bad):
            problems.append(f"{rung}: {len(bad)} rows marked before they opened")
        e, l, p = num(d, "entry"), num(d, "last_price"), num(d, "pnl_pct")
        calc = (l / e - 1) * 100
        off = (calc - p).abs() > 0.02
        if off.sum():
            problems.append(f"{rung}: {int(off.sum())} rows where pnl_pct "
                            f"disagrees with entry/last_price")
        if (num(d, "entry") <= 0).any():
            problems.append(f"{rung}: non-positive entry price")
    # FIRST SEEN WINS. Writing every entry back would record the corrupted
    # value and silently bless it on the next run -- the check would report a
    # problem once and never again. An entry price is stamped when the position
    # opens and is never a candidate for revision, so only genuinely new
    # (rung, symbol, opened) keys are added to the fingerprint.
    if fps:
        os.makedirs(LOGS, exist_ok=True)
        keep = [{"rung": k[0], "symbol": k[1], "opened": k[2], "entry": v}
                for k, v in seen_prev.items()]
        have = set(seen_prev)
        for r in fps:
            k = (r["rung"], r["symbol"], r["opened"])
            if k not in have:
                have.add(k)
                keep.append(r)
        pd.DataFrame(keep).to_csv(snap, index=False)
    if verbose:
        if problems:
            say(f"SANITY: {len(problems)} PROBLEM(S)")
            for x in problems:
                say(f"  !! {x}")
        else:
            n = sum(len(read(r)) for r in LADDERS)
            say(f"SANITY OK -- {n} positions across {len(LADDERS)} rungs; "
                f"no entry rewritten, no duplicate opens, P&L reconciles")
    return problems


def excel():
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment
    rows = []
    for rung in LADDERS:
        s = stats(read(rung))
        if s:
            rows.append({"rung": rung, "family": rung.split("_")[0], **s})
    summary = pd.DataFrame(rows)
    with pd.ExcelWriter(XLSX, engine="openpyxl") as xw:
        (summary if not summary.empty
         else pd.DataFrame({"note": ["no entries yet"]})).to_excel(
            xw, sheet_name="Ladder Summary", index=False)
        for rung in LADDERS:
            d = read(rung)
            if not d.empty:
                d.to_excel(xw, sheet_name=rung[:31], index=False)
        wb = xw.book
        for ws in wb.worksheets:
            ws.freeze_panes = "B2"
            for c in ws[1]:
                c.fill = PatternFill("solid", fgColor="1F3864")
                c.font = Font(color="FFFFFF", bold=True, size=10)
                c.alignment = Alignment(horizontal="center", wrap_text=True)
            for i, col in enumerate(ws.iter_cols(min_row=1, max_row=1), 1):
                ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = \
                    min(max(11, len(str(col[0].value or "")) + 2), 34)
    say(f"wrote {XLSX}  ({len(LADDERS)} rungs + summary)")


if __name__ == "__main__":
    a = sys.argv[1:]
    if "--reset" in a:
        r = a[a.index("--reset") + 1]
        if os.path.exists(path(r)):
            os.remove(path(r))
        say(f"reset {r}")
    elif "--sanity" in a:
        sanity()
    elif "--report" in a:
        report()
    elif "--excel" in a:
        excel()
    else:
        update()
        say("")
        sanity()
        say("")
        report()
        excel()
