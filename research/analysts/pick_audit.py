"""Audit an analyst's ACTUAL current ratings, not their headline score.

Three things the leaderboard number hides:
  1. WHAT EXCHANGE. A "top US analyst" may cover TSX names a US cash
     account cannot easily buy.
  2. WHAT ACTION. TipRanks only scores Buy and Sell as positions. A Hold
     CLOSES a position and is never itself measured.
  3. WHETHER THE FORECAST WAS RIGHT. Success = "the stock rose". Price
     target accuracy is not an input. An analyst can be scored a WIN on a
     stock that blew 35% past a target they said was the ceiling.
"""
from __future__ import annotations
import urllib.request, gzip, re, html, io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import numpy as np

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"}
WHO = ["travis-wood", "manav-gupta", "phil-hardie", "shrenik-kothari",
       "bill-papanastasiou", "paul-newsome"]


def get(u):
    raw = urllib.request.urlopen(urllib.request.Request(u, headers=H), timeout=30).read()
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return raw.decode("utf8", "ignore")


def rows_of(slug):
    h = get(f"https://stockanalysis.com/analysts/{slug}/")
    tbl = re.findall(r"<table.*?</table>", h, re.S | re.I)
    if not tbl:
        return []
    out = []
    for tr in re.findall(r"<tr.*?</tr>", tbl[0], re.S | re.I):
        cells = [re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", c))).strip()
                 for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S | re.I)]
        cells = [c for c in cells if c]
        if len(cells) < 5:
            continue
        joined = " ".join(cells)
        m = re.search(r"(-?\d+\.?\d*)%", joined)
        up = float(m.group(1)) if m else None
        act = None
        for a in ("Downgraded", "Upgraded", "Maintained", "Initiated", "Reiterated"):
            if a in joined:
                rr = re.search(rf"{a}:\s*(\w+)", joined)
                act = f"{a}:{rr.group(1)}" if rr else a
                break
        ex = "TSX" if "TSX:" in joined else ("US" if re.search(r"\b[A-Z]{1,5}\b", cells[0]) else "?")
        out.append({"raw": joined[:60], "exch": ex, "action": act, "upside": up})
    return out


for slug in WHO:
    try:
        rs = rows_of(slug)
    except Exception as e:
        print(f"{slug}: ERR {str(e)[:50]}")
        continue
    if not rs:
        print(f"{slug}: no table")
        continue
    tsx = sum(1 for r in rs if r["exch"] == "TSX")
    ups = [r["upside"] for r in rs if r["upside"] is not None]
    acts = {}
    for r in rs:
        k = (r["action"] or "?").split(":")[-1]
        acts[k] = acts.get(k, 0) + 1
    neg = sum(1 for u in ups if u < 0)
    print(f"\n=== {slug} — {len(rs)} current ratings ===")
    print(f"  exchange: {tsx} TSX / {len(rs)-tsx} other")
    print(f"  actions:  {acts}")
    if ups:
        print(f"  price target vs current price:")
        print(f"     median implied upside {np.median(ups):+.1f}%")
        print(f"     targets BELOW current price: {neg}/{len(ups)} "
              f"({neg/len(ups)*100:.0f}%)  <- stock already blew past the target")
        print(f"     worst: {min(ups):+.1f}%   best: {max(ups):+.1f}%")
