"""Ingest a StockAnalysis.com export you downloaded yourself, and merge it
into the watchlist.

WHY THIS SHAPE: StockAnalysis has no API -- their help centre says so
explicitly, because they license data from third parties and are not
permitted to redistribute it programmatically. Scraping the site (there are
third-party scrapers on offer) is the thing that licensing forbids and it
puts your account at risk. So the automation starts AFTER the file lands:
you click export in your own account -- data you pay for -- and everything
downstream is automatic.

Pro = 1 download/day. Unlimited = unlimited. Either works; this reads
whatever the newest export in your Downloads folder is.

Usage:
    python research/tool/ingest_stockanalysis.py                # newest export
    python research/tool/ingest_stockanalysis.py path/to/file.csv
"""
from __future__ import annotations
import sys, io, glob, os, re, warnings
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
warnings.filterwarnings("ignore")
import pandas as pd

DOWNLOADS = os.path.expanduser("~/Downloads")
# StockAnalysis column names -> canonical names used by the watchlist tool
ALIASES = {
    "symbol": "ticker", "ticker": "ticker", "company name": "name", "company": "name",
    "market cap": "mcap", "marketcap": "mcap",
    "pe ratio": "pe", "pe": "pe", "forward pe": "fwd_pe", "pe (fwd)": "fwd_pe",
    "ps ratio": "ps", "pb ratio": "pb", "ev/ebitda": "ev_ebitda", "ev/sales": "ev_sales",
    "revenue growth": "rev_growth", "rev growth": "rev_growth",
    "revenue growth (yoy)": "rev_growth", "eps growth": "eps_growth",
    "profit margin": "margin", "net margin": "margin", "operating margin": "op_margin",
    "gross margin": "gross_margin", "fcf margin": "fcf_margin",
    "debt/equity": "debt_equity", "debt / equity": "debt_equity",
    "debt/ebitda": "debt_ebitda", "current ratio": "current_ratio",
    "return on equity": "roe", "roe": "roe", "return on capital": "roic", "roic": "roic",
    "free cash flow": "fcf", "dividend yield": "div_yield",
    "52-week high": "hi52", "52-week low": "lo52",
    "price": "price", "stock price": "price", "change": "chg",
}


def find_latest() -> str | None:
    pats = ["stockanalysis*.csv", "stock-analysis*.csv", "screener*.csv", "*export*.csv"]
    hits = [f for p in pats for f in glob.glob(os.path.join(DOWNLOADS, p))]
    if not hits:
        hits = sorted(glob.glob(os.path.join(DOWNLOADS, "*.csv")),
                      key=os.path.getmtime, reverse=True)[:5]
        hits = [h for h in hits if _looks_like_export(h)]
    return max(hits, key=os.path.getmtime) if hits else None


def _looks_like_export(path: str) -> bool:
    try:
        head = pd.read_csv(path, nrows=1)
    except Exception:
        return False
    cols = {c.strip().lower() for c in head.columns}
    return bool(cols & {"symbol", "ticker"}) and len(cols) >= 4


def norm(df: pd.DataFrame) -> pd.DataFrame:
    ren = {}
    for c in df.columns:
        k = re.sub(r"\s+", " ", str(c).strip().lower())
        if k in ALIASES:
            ren[c] = ALIASES[k]
    df = df.rename(columns=ren)
    for c in df.columns:
        if c in ("ticker", "name"):
            continue
        df[c] = (df[c].astype(str)
                 .str.replace(r"[,$]", "", regex=True)
                 .str.replace("%", "", regex=False)
                 .str.replace(r"^\s*-\s*$", "", regex=True))
        df[c] = pd.to_numeric(df[c], errors="ignore")
    if "ticker" in df:
        df["ticker"] = df["ticker"].astype(str).str.strip().str.upper()
    return df


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else find_latest()
    if not path or not os.path.exists(path):
        print(f"No export found in {DOWNLOADS}.")
        print("In StockAnalysis: Screener -> set your filters -> Export -> CSV.")
        print("Then re-run this. (Pro allows 1 download/day.)")
        return
    df = norm(pd.read_csv(path))
    age_h = (pd.Timestamp.now() - pd.Timestamp(os.path.getmtime(path), unit="s")).total_seconds() / 3600
    print(f"source: {os.path.basename(path)}  ({len(df)} rows, "
          f"{df.shape[1]} cols, {age_h:.1f}h old)")
    mapped = [c for c in df.columns if c in set(ALIASES.values())]
    print(f"recognised columns: {', '.join(mapped) if mapped else '(none)'}")
    unmapped = [c for c in df.columns if c not in set(ALIASES.values())]
    if unmapped:
        print(f"passed through unmapped: {', '.join(map(str, unmapped[:12]))}"
              f"{' ...' if len(unmapped) > 12 else ''}")

    out = "research/tool/sa_latest.csv"
    df.to_csv(out, index=False)
    print(f"\nwrote {out}")
    if "ticker" in df:
        tk = df["ticker"].dropna().tolist()
        with open("research/tool/sa_tickers.txt", "w", encoding="utf-8") as f:
            f.write(" ".join(tk))
        print(f"wrote research/tool/sa_tickers.txt ({len(tk)} tickers)")
        print("\nnext:")
        print("  python research/tool/watchlist.py --file research/tool/sa_tickers.txt")
    if age_h > 30:
        print("\nNOTE: export is over a day old -- re-export before acting on it.")


if __name__ == "__main__":
    main()
