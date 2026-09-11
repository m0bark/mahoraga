"""Pull the stockanalysis.com / TipRanks analyst leaderboard and look at what
the numbers actually say once you put them next to a base rate."""
from __future__ import annotations
import urllib.request, gzip, re, html, io, sys, csv
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import numpy as np

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
     "Accept-Language": "en-US,en;q=0.9"}


def get(u):
    raw = urllib.request.urlopen(urllib.request.Request(u, headers=H), timeout=30).read()
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return raw.decode("utf8", "ignore")


h = get("https://stockanalysis.com/analysts/")
tbl = re.findall(r"<table.*?</table>", h, re.S | re.I)[0]
rows = []
for tr in re.findall(r"<tr.*?</tr>", tbl, re.S | re.I):
    cells = [re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", c))).strip()
             for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S | re.I)]
    cells = [c for c in cells if c]
    if len(cells) < 7:
        continue
    try:
        rank = int(cells[0])
    except ValueError:
        continue
    name = re.sub(r"\(\d\.\d+\)", "", cells[1]).strip()
    star = re.search(r"\((\d\.\d+)\)", cells[1])
    firm, sector = cells[2], cells[3]
    sr = float(cells[4].replace("%", ""))
    ar = float(cells[5].replace("%", ""))
    n = int(cells[6].replace(",", ""))
    rows.append({"rank": rank, "name": name, "stars": float(star.group(1)) if star else None,
                 "firm": firm, "sector": sector, "success": sr, "avg_return": ar,
                 "ratings": n})

rows.sort(key=lambda r: -r["rank"])
print(f"pulled {len(rows)} ranked analysts\n")
print(f"{'#':>4} {'analyst':<24}{'sector':<14}{'succ%':>7}{'avgret%':>9}{'n':>7}"
      f"{'SD above 65% base':>19}")
print("-" * 90)
for r in rows[:25]:
    se = np.sqrt(0.65 * 0.35 / r["ratings"]) * 100
    z = (r["success"] - 65.0) / se
    print(f"{r['rank']:>4} {r['name'][:23]:<24}{r['sector'][:13]:<14}"
          f"{r['success']:>7.1f}{r['avg_return']:>9.1f}{r['ratings']:>7,}{z:>19.1f}")

s = np.array([r["success"] for r in rows])
a = np.array([r["avg_return"] for r in rows])
n = np.array([r["ratings"] for r in rows])
print("-" * 90)
print(f"TOP-{len(rows)} LEADERBOARD SUMMARY")
print(f"  success rate:   median {np.median(s):.1f}%   range {s.min():.1f}-{s.max():.1f}%")
print(f"  average return: median {np.median(a):.1f}%   range {a.min():.1f}-{a.max():.1f}%")
print(f"  ratings count:  median {np.median(n):,.0f}   range {n.min():,}-{n.max():,}")
print(f"\n  analysts BELOW the ~65% large-cap base rate: "
      f"{(s < 65).sum()}/{len(s)}")
print(f"  analysts below 70%: {(s < 70).sum()}/{len(s)}")

with open("research/analysts/leaderboard.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    w.writeheader(); w.writerows(rows)
print("\nwrote research/analysts/leaderboard.csv")
