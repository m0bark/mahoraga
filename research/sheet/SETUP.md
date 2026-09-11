# Setup

## 1. Telegram (5 minutes, you must do this part)

1. Open Telegram, message **@BotFather**, send `/newbot`, follow prompts.
2. Copy the token it gives you into `research/sheet/config.json` -> `telegram_token`.
3. Send **any message** to your new bot (this is what makes your chat visible to it).
4. Run:

    C:\Users\mobar\AppData\Local\Programs\Python\Python314\python.exe D:\mahoraga\research\sheet\alerts.py --setup

   It writes your chat id into config.json.
5. Test it:

    C:\Users\mobar\AppData\Local\Programs\Python\Python314\python.exe D:\mahoraga\research\sheet\alerts.py --test

## 2. Schedule it (Windows Task Scheduler)

Run each of these once in an **Administrator** PowerShell:

```
schtasks /create /tn "SP500 hourly" /tr "C:\Users\mobar\AppData\Local\Programs\Python\Python314\python.exe D:\mahoraga\research\sheet\run.py --hourly" /sc hourly /st 09:35 /f

schtasks /create /tn "SP500 daily" /tr "C:\Users\mobar\AppData\Local\Programs\Python\Python314\python.exe D:\mahoraga\research\sheet\run.py --daily" /sc daily /st 17:30 /f

schtasks /create /tn "SP500 alerts" /tr "C:\Users\mobar\AppData\Local\Programs\Python\Python314\python.exe D:\mahoraga\research\sheet\alerts.py --check" /sc minute /mo 5 /f
```

Check them: `schtasks /query /tn "SP500 hourly"`
Remove one: `schtasks /delete /tn "SP500 hourly" /f`

## 3. Make Excel refresh itself

The jobs always write `research/sheet/cache/*.csv`. Point Excel at those and
it updates while the file is open — no file-lock fight.

In Excel: **Data -> Get Data -> From File -> From Text/CSV** ->
`D:\mahoraga\research\sheet\cache\summary.csv` -> **Load**.
Then **Data -> Queries & Connections -> right-click the query -> Properties ->
tick "Refresh every 60 minutes"** and "Refresh data when opening the file".

Repeat for any sheet you want live: technicals, fundamentals, macro,
momentum, bigmoney, analysts, whyitmoved, buyzone.

`sp500_dashboard.xlsx` is the standalone snapshot if you just want one file.

## 4. Watchlist

Edit `research/sheet/watchlist.csv`:

```
symbol,type,level,note,fired
MSFT,price_below,360,my buy price,
NVDA,rsi_below,30,oversold,
AAPL,in_buy_zone,,at the computed zone,
ANY,unusual_options,,big money anywhere,
```

Leave `fired` blank. The daemon fills it when an alert sends, and clears it
when the condition goes away, so you get one message per event and not one
every five minutes for a week.

Types: price_below, price_above, rsi_below, rsi_above, sma200_cross_down,
sma200_cross_up, near_support, pct_drop_1d, in_buy_zone, new_52w_low,
unusual_options.

---

## 5. Google Sheets (auto-updating, shareable, works on your phone)

Google needs to know who is writing. A **service account** is a robot Google
account with its own email address — you share your sheet with it like you
would share with a colleague, and it can then write forever with no browser
login. That is what makes unattended hourly updates possible.

**One-time, you must do this part (needs your Google login):**

1. https://console.cloud.google.com/ → create a project (any name)
2. **APIs & Services → Library** → enable **Google Sheets API** and **Google Drive API**
3. **APIs & Services → Credentials → Create credentials → Service account** → name it → Done
4. Click the service account → **Keys → Add key → Create new key → JSON**.
   Save the downloaded file as `research/sheet/gcreds.json`
5. Open it, copy the `client_email` (looks like `x@project.iam.gserviceaccount.com`)
6. Create a blank Google Sheet named **SP500 Dashboard**, and **Share** it with
   that address as an **Editor**
7. Add to `config.json`: `"gsheet_name": "SP500 Dashboard"`

Then verify:

```
C:\Users\mobar\AppData\Local\Programs\Python\Python314\python.exe D:\mahoraga\research\sheet\to_gsheet.py --setup
```

Push everything:

```
C:\Users\mobar\AppData\Local\Programs\Python\Python314\python.exe D:\mahoraga\research\sheet\to_gsheet.py
```

Once `gcreds.json` exists, the hourly job pushes automatically — no extra
scheduling needed. Hourly runs push only the fast-changing tabs (`--fast`);
the daily run pushes all 10.

**Rate limits:** Sheets allows 60 writes/minute. Each tab goes up as ONE update
call plus ONE formatting batch, so a full push is ~20 requests — well inside
the quota.

## 6. What the jobs do now

| command | does |
|---|---|
| `run.py --hourly` | prices → workbook → Sheets (fast tabs) → alerts |
| `run.py --daily` | + fundamentals, options → all Sheets tabs |
| `run.py --alerts` | watchlist → Telegram only |
| `run.py --gsheet` | push to Google Sheets only |
| `run.py --once` | full cold start |
