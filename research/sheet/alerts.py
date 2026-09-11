"""Watchlist -> Telegram. Fires once per trigger, re-arms when it clears.

    python research/sheet/alerts.py --check      # evaluate, send, update state
    python research/sheet/alerts.py --dry        # evaluate and print, send nothing
    python research/sheet/alerts.py --setup      # find your chat id
    python research/sheet/alerts.py --test       # send one test message

WATCHLIST FORMAT (watchlist.csv, edit by hand)

    symbol,type,level,note
    MSFT,price_below,360,good buy zone
    NVDA,price_below,150,
    AAPL,sma200_cross_down,,trend break
    AMD,rsi_below,30,oversold
    KO,near_support,2.0,within 2% of support
    LLY,in_buy_zone,,at the computed zone
    ANY,unusual_options,,big money showing up anywhere

TYPES
    price_below / price_above    level = a price
    rsi_below / rsi_above        level = an RSI value
    sma200_cross_down / _up      level ignored
    near_support                 level = percent, e.g. 2.0
    pct_drop_1d                  level = percent, e.g. 5 -> fires on a 5% down day
    in_buy_zone                  level ignored, uses the computed zone
    new_52w_low                  level ignored
    unusual_options              symbol may be ANY, scans the whole index

WHY THE `fired` COLUMN EXISTS
Without it a price_below alert re-sends every five minutes for as long as the
stock stays under the level -- which is days. A trigger writes its fire time,
and only re-arms once the condition is FALSE again. That is the difference
between an alert and a stuck horn.

SETUP
1. Message @BotFather on Telegram, send /newbot, copy the token.
2. Put it in config.json as telegram_token.
3. Send any message to your new bot.
4. python alerts.py --setup   -> writes your chat id into config.json
"""
from __future__ import annotations

import csv
import io
import json
import os
import sys
import urllib.parse
import urllib.request
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
CONFIG = os.path.join(HERE, "config.json")
WATCH = os.path.join(HERE, "watchlist.csv")
API = "https://api.telegram.org/bot{token}/{method}"


def load_config() -> dict:
    if not os.path.exists(CONFIG):
        return {}
    return json.load(open(CONFIG, encoding="utf-8"))


def save_config(c: dict) -> None:
    json.dump(c, open(CONFIG, "w", encoding="utf-8"), indent=2)


def tg(method: str, **params):
    c = load_config()
    tok = c.get("telegram_token", "")
    if not tok or tok.startswith("PASTE"):
        return {"ok": False, "error": "no token in config.json"}
    url = API.format(token=tok, method=method)
    data = urllib.parse.urlencode(params).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=data),
                                    timeout=20) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def send(text: str) -> bool:
    c = load_config()
    chat = c.get("telegram_chat_id", "")
    if not chat:
        say("no telegram_chat_id -- run --setup")
        return False
    r = tg("sendMessage", chat_id=chat, text=text, parse_mode="HTML",
           disable_web_page_preview="true")
    if not r.get("ok"):
        say(f"telegram send failed: {r.get('error') or r.get('description')}")
    return bool(r.get("ok"))


def setup() -> None:
    r = tg("getUpdates")
    if not r.get("ok"):
        say(f"getUpdates failed: {r.get('error') or r.get('description')}")
        say("Check telegram_token in config.json, then message your bot once.")
        return
    ids = []
    for u in r.get("result", []):
        m = u.get("message") or u.get("channel_post") or {}
        ch = (m.get("chat") or {}).get("id")
        who = (m.get("chat") or {}).get("username") or (m.get("chat") or {}).get("first_name")
        if ch and ch not in [i for i, _ in ids]:
            ids.append((ch, who))
    if not ids:
        say("No messages seen. Send any message to your bot, then rerun --setup.")
        return
    c = load_config()
    c["telegram_chat_id"] = str(ids[0][0])
    save_config(c)
    say(f"chat id {ids[0][0]} ({ids[0][1]}) saved to config.json")
    for ch, who in ids[1:]:
        say(f"  (also saw {ch} / {who})")


def load_watchlist() -> pd.DataFrame:
    if not os.path.exists(WATCH):
        return pd.DataFrame(columns=["symbol", "type", "level", "note", "fired"])
    w = pd.read_csv(WATCH)
    for c in ("level", "note", "fired"):
        if c not in w:
            w[c] = ""
    # An all-empty text column is inferred as float64, and pandas 3.x refuses
    # to put a timestamp string into it -- .at raises TypeError, the send loop
    # dies before to_csv, the fired stamp never reaches disk, and every alert
    # re-sends forever. Force object dtype on load so both the fire write and
    # the re-arm write succeed; re-applied each load, so it self-heals.
    for c in ("note", "fired"):
        w[c] = w[c].astype(object).where(w[c].notna(), "")
    return w


def evaluate(w: pd.DataFrame, summ: pd.DataFrame, big: pd.DataFrame):
    """Return (triggered rows, cleared indices) without sending anything."""
    s = summ.set_index("symbol")
    fired, cleared = [], []
    for i, r in w.iterrows():
        sym = str(r["symbol"]).strip().upper()
        typ = str(r["type"]).strip()
        lvl = pd.to_numeric(r.get("level"), errors="coerce")
        # NaN is TRUTHY in Python, so `r.get("fired") or ""` returns NaN for an
        # empty cell, str(NaN) == "nan", and every rule reads as already-fired.
        # That silently disabled the entire alert engine. Test it with pd.isna.
        _f = r.get("fired")
        already = not (pd.isna(_f) or str(_f).strip() in ("", "nan"))
        cond, msg = False, ""

        if typ == "unusual_options":
            hits = big[big.get("UNUSUAL", "") == "UNUSUAL"] if not big.empty else pd.DataFrame()
            if sym not in ("ANY", "NAN", ""):
                hits = hits[hits.symbol == sym]
            if len(hits):
                cond = True
                names = ", ".join(f"{h.symbol} ({h.skew or 'mixed'})"
                                  for h in hits.head(6).itertuples())
                msg = f"BIG MONEY: unusual option activity in {names}"
        elif sym in s.index:
            row = s.loc[sym]
            if isinstance(row, pd.DataFrame):
                row = row.iloc[0]
            px = float(row.get("price", np.nan))
            nm = row.get("shortName", sym)
            if typ == "price_below" and np.isfinite(lvl):
                cond = px <= lvl
                msg = f"{sym} {nm} at ${px:,.2f} — at or below your ${lvl:,.2f}"
            elif typ == "price_above" and np.isfinite(lvl):
                cond = px >= lvl
                msg = f"{sym} {nm} at ${px:,.2f} — at or above your ${lvl:,.2f}"
            elif typ == "rsi_below" and np.isfinite(lvl):
                v = float(row.get("rsi14", np.nan))
                cond = np.isfinite(v) and v <= lvl
                msg = f"{sym} RSI {v:.0f} (below {lvl:.0f}) at ${px:,.2f}"
            elif typ == "rsi_above" and np.isfinite(lvl):
                v = float(row.get("rsi14", np.nan))
                cond = np.isfinite(v) and v >= lvl
                msg = f"{sym} RSI {v:.0f} (above {lvl:.0f}) at ${px:,.2f}"
            elif typ == "sma200_cross_down":
                cond = str(row.get("vs_200sma")) == "BELOW"
                msg = (f"{sym} broke BELOW its 200-day SMA "
                       f"({row.get('pct_vs_200sma', float('nan')):.1f}%) at ${px:,.2f}")
            elif typ == "sma200_cross_up":
                cond = str(row.get("vs_200sma")) == "ABOVE"
                msg = f"{sym} back ABOVE its 200-day SMA at ${px:,.2f}"
            elif typ == "near_support" and np.isfinite(lvl):
                d = float(row.get("pct_to_support", np.nan))
                cond = np.isfinite(d) and abs(d) <= lvl
                msg = (f"{sym} within {abs(d):.1f}% of support "
                       f"${row.get('support', float('nan')):,.2f} at ${px:,.2f}")
            elif typ == "pct_drop_1d" and np.isfinite(lvl):
                d = float(row.get("chg_1d_pct", np.nan))
                cond = np.isfinite(d) and d <= -abs(lvl)
                msg = f"{sym} down {d:.1f}% today to ${px:,.2f}"
            elif typ == "in_buy_zone":
                z = str(row.get("zone_status", ""))
                cond = z in ("IN ZONE", "AT ZONE")
                msg = (f"{sym} {z} — ${px:,.2f} vs zone "
                       f"${row.get('buy_zone_low', float('nan')):,.2f}"
                       f"-${row.get('buy_zone_high', float('nan')):,.2f}")
            elif typ == "new_52w_low":
                d = float(row.get("pct_from_52w_high", np.nan))
                lo = float(row.get("low_52w", np.nan)) if "low_52w" in row else np.nan
                cond = np.isfinite(lo) and px <= lo * 1.005
                msg = f"{sym} at a new 52-week low, ${px:,.2f}"
            if cond and msg:
                rate = row.get("RATE", np.nan)
                _n = r.get("note")
                note = "" if pd.isna(_n) else str(_n).strip()
                extra = []
                if np.isfinite(pd.to_numeric(rate, errors="coerce")):
                    extra.append(f"rate {float(rate):.0f}/100")
                if str(row.get("halal_auto", "")) == "FAIL":
                    extra.append("halal auto-screen FAIL")
                bn = str(row.get("buy_note") or "")
                if bn:
                    extra.append(bn)
                if extra:
                    msg += "\n  " + " | ".join(extra)
                if note:
                    msg += f"\n  note: {note}"

        if cond and not already:
            fired.append((i, msg))
        elif not cond and already:
            cleared.append(i)
    return fired, cleared


def check(dry: bool = False) -> None:
    summ_p = os.path.join(CACHE, "summary.csv")
    if not os.path.exists(summ_p):
        say("no summary.csv -- run build_workbook.py first")
        return
    summ = pd.read_csv(summ_p)
    big = pd.read_csv(os.path.join(CACHE, "bigmoney.csv")) \
        if os.path.exists(os.path.join(CACHE, "bigmoney.csv")) else pd.DataFrame()
    w = load_watchlist()
    if w.empty:
        say("watchlist.csv is empty")
        return

    fired, cleared = evaluate(w, summ, big)
    say(f"{len(w)} rules | {len(fired)} firing | {len(cleared)} re-arming")
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    for i, msg in fired:
        say(f"  FIRE  {msg.splitlines()[0]}")
        if not dry:
            if send(f"<b>ALERT</b>\n{msg}"):
                w.at[i, "fired"] = now
    for i in cleared:
        say(f"  rearm {w.at[i, 'symbol']} {w.at[i, 'type']}")
        if not dry:
            w.at[i, "fired"] = ""
    if not dry:
        w.to_csv(WATCH, index=False)


def main() -> None:
    a = sys.argv[1:]
    if "--setup" in a:
        setup()
    elif "--test" in a:
        say("sent" if send("Test from your S&P 500 dashboard. Alerts are wired up.")
            else "failed")
    elif "--dry" in a:
        check(dry=True)
    else:
        check(dry=False)


if __name__ == "__main__":
    main()
