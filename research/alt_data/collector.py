# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = [
#     "requests>=2.31",
#     "pandas>=2.2",
# ]
# ///
"""Point-in-time alt-data collector: Reddit + Stocktwits -> SQLite.

Appends only, never edits — the capture timestamp IS the point-in-time
guarantee. Every day this runs, future backtests gain one more day of
alternative data with no look-ahead question marks.

Run once (for Task Scheduler):   uv run --python 3.12 collector.py
Run forever (poll every 10min):  uv run --python 3.12 collector.py --loop

Windows Task Scheduler setup (every 15 minutes):
  schtasks /create /tn "alt-data-collector" /sc minute /mo 15 ^
    /tr "uv run --python 3.12 D:\\mahoraga\\research\\alt_data\\collector.py"
"""

from __future__ import annotations

import re
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

HERE = Path(__file__).parent
DB = HERE / "alt_data.sqlite"
TICKER_SOURCE = HERE.parent / "panic_reversal" / "prices500.pkl"
SUBREDDITS = ["wallstreetbets", "stocks", "investing", "StockMarket"]
USER_AGENT = "personal-research-collector/0.1"
POLL_SECONDS = 600

SCHEMA = """
CREATE TABLE IF NOT EXISTS reddit_posts (
    post_id TEXT PRIMARY KEY,
    captured_at TEXT NOT NULL,
    created_utc REAL,
    subreddit TEXT,
    title TEXT,
    score INTEGER,
    num_comments INTEGER,
    tickers TEXT
);
CREATE TABLE IF NOT EXISTS stocktwits_trending (
    captured_at TEXT NOT NULL,
    symbol TEXT NOT NULL,
    watchlist_count INTEGER,
    rank INTEGER,
    PRIMARY KEY (captured_at, symbol)
);
"""


def known_tickers() -> set[str]:
    try:
        frames = pd.read_pickle(TICKER_SOURCE)
        return set(frames.keys())
    except Exception:
        return set()


def extract_tickers(title: str, universe: set[str]) -> list[str]:
    dollar = set(re.findall(r"\$([A-Z]{1,5})\b", title))
    bare = set(re.findall(r"\b([A-Z]{2,5})\b", title)) & universe
    return sorted(dollar | bare)


def reddit_token() -> str | None:
    """App-only OAuth. Create a free 'script' app at reddit.com/prefs/apps,
    then set env vars REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET."""
    import os

    cid = os.environ.get("REDDIT_CLIENT_ID")
    secret = os.environ.get("REDDIT_CLIENT_SECRET")
    if not cid or not secret:
        print("  reddit: skipped (set REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET; "
              "free app at https://www.reddit.com/prefs/apps)")
        return None
    try:
        resp = requests.post(
            "https://www.reddit.com/api/v1/access_token",
            auth=(cid, secret),
            data={"grant_type": "client_credentials"},
            headers={"User-Agent": USER_AGENT},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["access_token"]
    except Exception as exc:
        print(f"  reddit auth: {exc}")
        return None


def collect_reddit(con: sqlite3.Connection, universe: set[str]) -> int:
    token = reddit_token()
    if token is None:
        return 0
    now = datetime.now(timezone.utc).isoformat()
    inserted = 0
    for sub in SUBREDDITS:
        url = f"https://oauth.reddit.com/r/{sub}/new?limit=100"
        try:
            resp = requests.get(
                url,
                headers={"User-Agent": USER_AGENT, "Authorization": f"bearer {token}"},
                timeout=30,
            )
            resp.raise_for_status()
            posts = resp.json()["data"]["children"]
        except Exception as exc:
            print(f"  reddit r/{sub}: {exc}")
            continue
        for post in posts:
            d = post["data"]
            tickers = extract_tickers(d.get("title", ""), universe)
            cur = con.execute(
                "INSERT OR IGNORE INTO reddit_posts VALUES (?,?,?,?,?,?,?,?)",
                (d["id"], now, d.get("created_utc"), sub, d.get("title"),
                 d.get("score"), d.get("num_comments"), ",".join(tickers)),
            )
            inserted += cur.rowcount
        time.sleep(2)  # be polite
    return inserted


def collect_stocktwits(con: sqlite3.Connection) -> int:
    now = datetime.now(timezone.utc).isoformat()
    url = "https://api.stocktwits.com/api/2/trending/symbols.json"
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
        resp.raise_for_status()
        symbols = resp.json().get("symbols", [])
    except Exception as exc:
        print(f"  stocktwits: {exc}")
        return 0
    inserted = 0
    for rank, s in enumerate(symbols, start=1):
        cur = con.execute(
            "INSERT OR IGNORE INTO stocktwits_trending VALUES (?,?,?,?)",
            (now, s.get("symbol"), s.get("watchlist_count"), rank),
        )
        inserted += cur.rowcount
    return inserted


def run_once() -> None:
    con = sqlite3.connect(DB)
    con.executescript(SCHEMA)
    universe = known_tickers()
    n_reddit = collect_reddit(con, universe)
    n_st = collect_stocktwits(con)
    con.commit()
    total_r = con.execute("SELECT COUNT(*) FROM reddit_posts").fetchone()[0]
    total_s = con.execute("SELECT COUNT(*) FROM stocktwits_trending").fetchone()[0]
    con.close()
    print(f"{datetime.now():%Y-%m-%d %H:%M} +{n_reddit} reddit, +{n_st} stocktwits "
          f"(archive: {total_r:,} posts, {total_s:,} trending rows)")


def main() -> None:
    if "--loop" in sys.argv:
        while True:
            run_once()
            time.sleep(POLL_SECONDS)
    else:
        run_once()


if __name__ == "__main__":
    main()
