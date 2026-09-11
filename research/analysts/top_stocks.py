"""Pull stockanalysis.com /analysts/top-stocks/ -- the site's own version of
the user's cross-reference idea: stocks ranked by how many TOP-RATED analysts
have a Buy on them, with the top analysts' consensus price target.
"""
from __future__ import annotations
import urllib.request, gzip, re, html, io, sys, csv
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import numpy as np

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"}


def get(u):
    raw = urllib.request.urlopen(urllib.request.Request(u, headers=H), timeout=30).read()
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return raw.decode("utf8", "ignore")


def num(s):
    s = s.replace(",", "").replace("%", "").strip()
    mult = 1
    if s.endswith("B"):
        mult, s = 1e9, s[:-1]
    elif s.endswith("M"):
        mult, s = 1e6, s[:-1]
    elif s.endswith("T"):
        mult, s = 1e12, s[:-1]
    try:
        return float(s) * mult
    except ValueError:
        return None


h = get("https://stockanalysis.com/analysts/top-stocks/")
tbl = re.findall(r"<table.*?</table>", h, re.S | re.I)[0]
rows = []
for tr in re.findall(r"<tr.*?</tr>", tbl, re.S | re.I):
    c = [re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", x))).strip()
         for x in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S | re.I)]
    c = [x for x in c if x]
    if len(c) < 7:
        continue
    try:
        no = int(c[0])
    except ValueError:
        continue
    rows.append({"no": no, "symbol": c[1], "name": c[2][:34], "rating": c[3],
                 "n_top_analysts": num(c[4]), "top_pt": num(c[5]),
                 "upside_pct": num(c[6]), "mcap": num(c[7]) if len(c) > 7 else None})

print(f"pulled {len(rows)} stocks from the top-analyst consensus list\n")
n = np.array([r["n_top_analysts"] for r in rows if r["n_top_analysts"]])
u = np.array([r["upside_pct"] for r in rows if r["upside_pct"] is not None])
m = np.array([r["mcap"] for r in rows if r["mcap"]])
print(f"  top analysts per stock: median {np.median(n):.0f}  range {n.min():.0f}-{n.max():.0f}")
print(f"  implied upside:         median {np.median(u):.1f}%  range {u.min():.1f}-{u.max():.1f}%")
print(f"  market cap:             median ${np.median(m)/1e9:.1f}B")
print(f"  ratings that are 'Strong Buy': "
      f"{sum(1 for r in rows if 'Strong Buy' in r['rating'])}/{len(rows)}")

print(f"\n{'sym':<7}{'n_top':>6}{'upside':>9}{'mcap $B':>10}  name")
for r in sorted(rows, key=lambda x: -(x["n_top_analysts"] or 0))[:15]:
    print(f"{r['symbol']:<7}{r['n_top_analysts']:>6.0f}{r['upside_pct']:>8.1f}%"
          f"{(r['mcap'] or 0)/1e9:>10.1f}  {r['name']}")

# does MORE agreement come with MORE or LESS implied upside?
ok = [(r["n_top_analysts"], r["upside_pct"]) for r in rows
      if r["n_top_analysts"] and r["upside_pct"] is not None]
a = np.array([x[0] for x in ok]); b = np.array([x[1] for x in ok])
print(f"\ncorrelation(number of agreeing top analysts, implied upside) = "
      f"{np.corrcoef(a, b)[0,1]:+.3f}")
cm = np.array([r["mcap"] for r in rows if r["mcap"] and r["n_top_analysts"]])
ca = np.array([r["n_top_analysts"] for r in rows if r["mcap"] and r["n_top_analysts"]])
print(f"correlation(number of agreeing top analysts, log market cap)  = "
      f"{np.corrcoef(ca, np.log(cm))[0,1]:+.3f}")

with open("research/analysts/top_stocks.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
print("\nwrote research/analysts/top_stocks.csv")
