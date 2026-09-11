"""Push the dashboard to Google Sheets, formatted, on every run.

    python research/sheet/to_gsheet.py --setup    # check credentials, create sheet
    python research/sheet/to_gsheet.py            # push all tabs
    python research/sheet/to_gsheet.py --fast     # push only fast-changing tabs

WHY GOOGLE SHEETS NEEDS A SERVICE ACCOUNT AND EXCEL DOES NOT

Excel writes to a local file. Google Sheets is someone else's server, so it
needs to know the writer is you. A SERVICE ACCOUNT is a robot Google account
with its own email address; you share your spreadsheet with that address the
same way you would share it with a colleague, and the robot can then write to
it forever without a browser login. That is what makes hourly unattended
updates possible.

ONE-TIME SETUP (5 minutes, you must do this part -- it needs your Google login)

 1. https://console.cloud.google.com/  ->  create a project (any name)
 2. APIs & Services -> Library -> enable "Google Sheets API"
                               -> enable "Google Drive API"
 3. APIs & Services -> Credentials -> Create credentials -> Service account
    Give it a name, click through, Done.
 4. Click the service account -> Keys -> Add key -> Create new key -> JSON.
    A .json file downloads. Save it as:
        research/sheet/gcreds.json
 5. Open that json and copy the "client_email" value. It looks like
        something@your-project.iam.gserviceaccount.com
 6. Create a blank Google Sheet, name it "SP500 Dashboard", and SHARE it with
    that client_email address as an EDITOR.
 7. Put the sheet name (or its URL) in config.json as "gsheet_name".
 8. python research/sheet/to_gsheet.py --setup

RATE LIMITS ARE THE REAL CONSTRAINT
The Sheets API allows 60 write requests per minute per user. Writing 11 tabs
cell by cell would blow through that instantly, so every tab goes up as ONE
values.update call and formatting as ONE batch_update. --fast pushes only the
tabs whose numbers actually move hourly, which keeps a 5-minute alert loop and
an hourly refresh comfortably inside the quota.
"""
from __future__ import annotations

import io
import json
import os
import sys
import time

_OUT = io.TextIOWrapper(open(sys.stdout.fileno(), "wb", closefd=False),
                        encoding="utf-8", errors="replace")


def say(*a) -> None:
    print(*a, file=_OUT)
    _OUT.flush()


import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
CREDS = os.path.join(HERE, "gcreds.json")
CONFIG = os.path.join(HERE, "config.json")
SCOPES = ["https://www.googleapis.com/auth/spreadsheets",
          "https://www.googleapis.com/auth/drive"]

# tab -> (csv stem, changes hourly?)
TABS = [
    ("Encyclopedia", None, False),
    ("Summary", "summary", True),
    ("Technicals", "technicals", True),
    ("Momentum", "momentum", True),
    ("WhyItMoved", "whyitmoved", True),
    ("Fundamentals", "fundamentals", False),
    ("Macro", "macro", False),
    ("BigMoney", "bigmoney", False),
    ("Analysts", "analysts", False),
    ("BuyZone", "buyzone", True),
]
HEADER_BG = {"red": 0.12, "green": 0.22, "blue": 0.39}


def cfg() -> dict:
    return json.load(open(CONFIG, encoding="utf-8")) if os.path.exists(CONFIG) else {}


def client():
    if not os.path.exists(CREDS):
        say(f"missing {CREDS} -- see the setup steps at the top of this file")
        return None
    import gspread
    from google.oauth2.service_account import Credentials
    c = Credentials.from_service_account_file(CREDS, scopes=SCOPES)
    return gspread.authorize(c)


def open_book(gc):
    c = cfg()
    name = c.get("gsheet_name", "SP500 Dashboard")
    try:
        if name.startswith("http"):
            return gc.open_by_url(name)
        return gc.open(name)
    except Exception:
        say(f"could not open '{name}'. Create a sheet with that name and share it")
        say("with the client_email from gcreds.json as an Editor.")
        return None


def clean(df: pd.DataFrame) -> list[list]:
    """Sheets rejects NaN/Inf in JSON. Everything goes up as a JSON-safe cell."""
    d = df.replace([np.inf, -np.inf], np.nan)
    out = [list(map(str, d.columns))]
    for row in d.itertuples(index=False):
        r = []
        for v in row:
            if v is None or (isinstance(v, float) and not np.isfinite(v)):
                r.append("")
            elif isinstance(v, (np.integer,)):
                r.append(int(v))
            elif isinstance(v, (np.floating,)):
                r.append(round(float(v), 4))
            elif isinstance(v, (int, float, str, bool)):
                r.append(v)
            else:
                r.append(str(v))
        out.append(r)
    return out


def frames(fast_only: bool) -> dict[str, pd.DataFrame]:
    import importlib.util
    _e = importlib.util.spec_from_file_location(
        "enc", os.path.join(HERE, "encyclopedia.py"))
    enc = importlib.util.module_from_spec(_e)
    _e.loader.exec_module(enc)
    out = {}
    for tab, stem, hourly in TABS:
        if fast_only and not hourly:
            continue
        if stem is None:
            out[tab] = enc.frame()
            continue
        p = os.path.join(CACHE, f"{stem}.csv")
        if os.path.exists(p):
            out[tab] = pd.read_csv(p)
    return out


def fmt_requests(sh, tab: str, ws, df: pd.DataFrame) -> list[dict]:
    """One batch of formatting per tab: header, freeze, banding, colour scales."""
    sid = ws.id
    n, m = len(df) + 1, max(len(df.columns), 1)
    req = [
        {"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 0, "endRowIndex": 1},
            "cell": {"userEnteredFormat": {
                "backgroundColor": HEADER_BG,
                "textFormat": {"bold": True,
                               "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
                "horizontalAlignment": "CENTER",
                "wrapStrategy": "WRAP"}},
            "fields": "userEnteredFormat(backgroundColor,textFormat,"
                      "horizontalAlignment,wrapStrategy)"}},
        {"updateSheetProperties": {
            "properties": {"sheetId": sid, "gridProperties": {
                "frozenRowCount": 1,
                "frozenColumnCount": 0 if tab == "Encyclopedia" else 1}},
            "fields": "gridProperties.frozenRowCount,"
                      "gridProperties.frozenColumnCount"}},
    ]
    if tab != "Encyclopedia":
        req.append({"setBasicFilter": {"filter": {"range": {
            "sheetId": sid, "startRowIndex": 0, "endRowIndex": n,
            "startColumnIndex": 0, "endColumnIndex": m}}}})
    # red -> white -> green gradient on the columns worth reading as a gradient
    for col in ("RATE", "MOMENTUM_SCORE", "unusual_score", "chg_1d_pct",
                "pct_vs_200sma", "company_specific_pct", "ret_3m_pct",
                "mom_12_1_pct", "rs_3m_vs_spy"):
        if col in df.columns:
            i = list(df.columns).index(col)
            req.append({"addConditionalFormatRule": {"rule": {
                "ranges": [{"sheetId": sid, "startRowIndex": 1, "endRowIndex": n,
                            "startColumnIndex": i, "endColumnIndex": i + 1}],
                "gradientRule": {
                    "minpoint": {"color": {"red": 0.97, "green": 0.42, "blue": 0.42},
                                 "type": "PERCENTILE", "value": "5"},
                    "midpoint": {"color": {"red": 1, "green": 1, "blue": 1},
                                 "type": "PERCENTILE", "value": "50"},
                    "maxpoint": {"color": {"red": 0.39, "green": 0.74, "blue": 0.48},
                                 "type": "PERCENTILE", "value": "95"}}},
                "index": 0}})
    # word-match highlights
    for col, word, rgb in (("vs_200sma", "BELOW", (1.0, 0.78, 0.81)),
                           ("zone_status", "IN ZONE", (0.78, 0.94, 0.81)),
                           ("hot", "HOT", (0.78, 0.94, 0.81)),
                           ("UNUSUAL", "UNUSUAL", (1.0, 0.92, 0.62)),
                           ("halal_auto", "FAIL", (1.0, 0.78, 0.81)),
                           ("verdict", "WORKS", (0.78, 0.94, 0.81)),
                           ("verdict", "FAILS", (1.0, 0.78, 0.81)),
                           ("verdict", "UNTESTED", (1.0, 0.92, 0.62))):
        if col in df.columns:
            i = list(df.columns).index(col)
            req.append({"addConditionalFormatRule": {"rule": {
                "ranges": [{"sheetId": sid, "startRowIndex": 1, "endRowIndex": n,
                            "startColumnIndex": i, "endColumnIndex": i + 1}],
                "booleanRule": {
                    "condition": {"type": "TEXT_EQ",
                                  "values": [{"userEnteredValue": word}]},
                    "format": {"backgroundColor": {
                        "red": rgb[0], "green": rgb[1], "blue": rgb[2]}}}},
                "index": 0}})
    if tab == "Encyclopedia":
        req.append({"updateDimensionProperties": {
            "range": {"sheetId": sid, "dimension": "COLUMNS",
                      "startIndex": 2, "endIndex": 3},
            "properties": {"pixelSize": 700}, "fields": "pixelSize"}})
        req.append({"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": 1, "endRowIndex": n,
                      "startColumnIndex": 2, "endColumnIndex": 3},
            "cell": {"userEnteredFormat": {"wrapStrategy": "WRAP",
                                           "verticalAlignment": "TOP"}},
            "fields": "userEnteredFormat(wrapStrategy,verticalAlignment)"}})
    else:
        req.append({"autoResizeDimensions": {"dimensions": {
            "sheetId": sid, "dimension": "COLUMNS",
            "startIndex": 0, "endIndex": min(m, 40)}}})
    return req


def push(fast_only: bool = False) -> None:
    gc = client()
    if gc is None:
        return
    sh = open_book(gc)
    if sh is None:
        return
    fr = frames(fast_only)
    say(f"pushing {len(fr)} tabs to '{sh.title}'")
    existing = {w.title: w for w in sh.worksheets()}
    for tab, df in fr.items():
        rows, cols = len(df) + 1, max(len(df.columns), 1)
        ws = existing.get(tab)
        if ws is None:
            ws = sh.add_worksheet(title=tab, rows=rows + 10, cols=cols + 2)
        elif ws.row_count < rows or ws.col_count < cols:
            ws.resize(rows=rows + 10, cols=cols + 2)
        ws.clear()
        ws.update(values=clean(df), range_name="A1",
                  value_input_option="USER_ENTERED")
        try:
            sh.batch_update({"requests": fmt_requests(sh, tab, ws, df)})
        except Exception as e:
            say(f"  {tab}: values ok, formatting skipped ({type(e).__name__})")
        say(f"  {tab:<14}{len(df):>5} rows")
        time.sleep(1.2)                      # stay under 60 writes/min
    # a default blank Sheet1 left over from creation is just clutter
    if "Sheet1" in existing and len(sh.worksheets()) > 1:
        try:
            sh.del_worksheet(existing["Sheet1"])
        except Exception:
            pass
    say(f"\ndone: {sh.url}")


def setup() -> None:
    if not os.path.exists(CREDS):
        say(f"MISSING {CREDS}")
        say(__doc__.split("ONE-TIME SETUP")[1].split("RATE LIMITS")[0])
        return
    info = json.load(open(CREDS, encoding="utf-8"))
    say(f"service account: {info.get('client_email')}")
    say("Share your Google Sheet with that address as an EDITOR.\n")
    gc = client()
    if gc is None:
        return
    sh = open_book(gc)
    if sh is None:
        return
    say(f"connected to '{sh.title}'")
    say(f"  {sh.url}")
    say(f"  existing tabs: {[w.title for w in sh.worksheets()]}")
    say("\nready -- run without --setup to push")


if __name__ == "__main__":
    a = sys.argv[1:]
    if "--setup" in a:
        setup()
    else:
        push(fast_only="--fast" in a)
