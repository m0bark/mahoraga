@echo off
setlocal enableextensions enabledelayedexpansion
title mahoraga desk - launcher
color 0B

REM ============================================================
REM  mahoraga desk - one-click launcher
REM  Double-click on any Windows PC that has this repo.
REM  It sets up Python, rebuilds the Excel + data, starts the
REM  website and the Telegram bot, opens the desk in a browser,
REM  and (optionally) syncs code changes to GitHub.
REM
REM  It NEVER pushes the 1.5 GB data cache, the generated Excel,
REM  or your Telegram token - those are gitignored by design and
REM  the Excel is rebuilt fresh on every machine instead.
REM ============================================================

cd /d "%~dp0"
echo(
echo   ==========================================================
echo     mahoraga desk launcher   %DATE% %TIME%
echo     folder: %CD%
echo   ==========================================================
echo(

REM ---------- 1. find a Python to bootstrap the venv ----------
set "BOOTPY="
where py    >nul 2>&1 && set "BOOTPY=py -3"
if not defined BOOTPY ( where python >nul 2>&1 && set "BOOTPY=python" )
if not defined BOOTPY (
  echo [X] Python was not found on this PC.
  echo     Install Python 3.11+ from https://www.python.org/downloads/
  echo     During install, tick "Add Python to PATH", then re-run this file.
  echo(
  pause & exit /b 1
)
echo [1/7] Python found: %BOOTPY%

REM ---------- 2. create / reuse a local virtual env ----------
set "VPY=.venv\Scripts\python.exe"
if not exist "%VPY%" (
  echo [2/7] First run on this PC - creating an isolated environment...
  %BOOTPY% -m venv .venv
  if not exist "%VPY%" (
    echo [X] Could not create the virtual environment. Aborting.
    pause & exit /b 1
  )
  set "FRESH_VENV=1"
) else (
  echo [2/7] Environment already present.
)

REM ---------- 3. install / update dependencies ----------
echo [3/7] Ensuring dependencies (quiet; slow only on first run)...
"%VPY%" -m pip install --upgrade pip --quiet
"%VPY%" -m pip install -r requirements.txt --quiet
if errorlevel 1 (
  echo [!] pip reported a problem. Trying to continue with what is installed.
)

REM ---------- 4. pull the latest code from GitHub ----------
where git >nul 2>&1
if not errorlevel 1 (
  echo [4/7] Pulling latest code from GitHub...
  git pull --ff-only
) else (
  echo [4/7] git not installed - skipping pull.
)

REM ---------- 5. choose how much to rebuild ----------
REM  A cold machine has no cache and must do a full pull.
set "MODE="
if not exist "research\sheet\cache\summary.csv" (
  echo(
  echo   No local data found - a full download is required the first time.
  set "MODE=3"
) else (
  echo(
  echo   How do you want to start?
  echo     [1] Fast     - use existing data, just boot the desk (seconds)
  echo     [2] Refresh  - update prices + rebuild Excel, then boot (~2 min)   [default]
  echo     [3] Full     - re-pull everything incl fundamentals (~15 min)
  echo(
  choice /c 123 /t 12 /d 2 /n /m "   Pick 1/2/3 (auto 2 in 12s): "
  set "MODE=!errorlevel!"
)

if "%MODE%"=="1" (
  echo [5/7] Fast start - skipping data refresh.
)
if "%MODE%"=="2" (
  echo [5/7] Refreshing prices and rebuilding the Excel workbook...
  "%VPY%" research\sheet\run.py --hourly
)
if "%MODE%"=="3" (
  echo [5/7] Full rebuild - downloading prices, fundamentals and options.
  echo       This takes about 15 minutes. Leave it running.
  "%VPY%" research\sheet\run.py --once
)

REM ---------- 6. launch the website and the bot ----------
echo [6/7] Starting the desk website on http://127.0.0.1:8777 ...
start "mahoraga website" cmd /k %VPY% research\sheet\server.py --port 8777

REM bot only if a real Telegram token exists on this machine
if not exist "research\sheet\config.json" (
  if exist "research\sheet\config.example.json" copy "research\sheet\config.example.json" "research\sheet\config.json" >nul
)
"%VPY%" -c "import json,sys;c=json.load(open('research/sheet/config.json'));t=str(c.get('telegram_token',''));sys.exit(0 if t and 'PUT_YOUR' not in t else 1)" 2>nul
if errorlevel 1 (
  echo       Telegram bot NOT started - no token on this PC.
  echo       To enable it: put your token in research\sheet\config.json, then re-run.
) else (
  echo       Starting the Telegram bot...
  start "mahoraga telegram bot" cmd /k %VPY% research\sheet\bot.py
)

REM ---------- 7. open the desk, then offer to sync code up ----------
echo [7/7] Opening the desk in your browser...
timeout /t 4 >nul
start "" http://127.0.0.1:8777/

where git >nul 2>&1
if not errorlevel 1 (
  echo(
  choice /c YN /t 20 /d N /n /m "   Push local CODE changes to GitHub now? data/token never pushed (Y/N, auto N): "
  if not errorlevel 2 (
    echo   Syncing code to GitHub...
    git add -A
    git commit -m "desk: sync from launcher %DATE%"
    git push
    if errorlevel 1 ( echo   Nothing to push, or push failed - continuing. ) else ( echo   Pushed. )
  ) else (
    echo   Skipped GitHub push.
  )
)

echo(
echo   ==========================================================
echo     Desk is up:  http://127.0.0.1:8777
echo     Website and bot run in their own windows - close those
echo     windows to stop them.
echo   ==========================================================
echo(
pause
endlocal
