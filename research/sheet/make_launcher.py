r"""Build the desktop launcher: one folder, five buttons, nothing to remember.

    python research/sheet/make_launcher.py            # create/refresh
    python research/sheet/make_launcher.py --remove

WHAT LANDS ON THE DESKTOP

    SP500 Desk.bat          <- the one you double-click
    SP500 Desk\             <- everything else, out of the way
        UPDATE NOW.bat      force a full refresh, watch it run
        STOP.bat            shut the server and bot down
        OPEN EXCEL.bat      the workbook
        OPEN FOLDER.bat     the project directory
        SETUP TELEGRAM.bat  the one-time bot wiring
        STATUS.bat          are the jobs alive, how old is the data

The Desktop is found by asking Windows, not by assuming ~/Desktop -- with
OneDrive Desktop-sync turned on the real path is
%USERPROFILE%/OneDrive/Desktop and writing to the other one puts your
launcher somewhere you will never look.

The main launcher is intentionally not silent: it prints what it is starting,
so when something is broken you can see which piece.
"""
from __future__ import annotations

import io
import os
import sys

_OUT = io.TextIOWrapper(open(sys.stdout.fileno(), "wb", closefd=False),
                        encoding="utf-8", errors="replace")


def say(*a) -> None:
    print(*a, file=_OUT)
    _OUT.flush()


HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
PYW = PY.replace("python.exe", "pythonw.exe")
if not os.path.exists(PYW):
    PYW = PY
PORT = 8777


def desktop() -> str:
    """Ask Windows where the Desktop is; OneDrive moves it."""
    try:
        import ctypes.wintypes as wt
        import ctypes
        buf = ctypes.create_unicode_buffer(wt.MAX_PATH)
        # CSIDL_DESKTOPDIRECTORY = 0x10
        ctypes.windll.shell32.SHGetFolderPathW(None, 0x10, None, 0, buf)
        if buf.value and os.path.isdir(buf.value):
            return buf.value
    except Exception:
        pass
    for c in (os.path.join(os.environ.get("USERPROFILE", ""), "OneDrive", "Desktop"),
              os.path.join(os.environ.get("USERPROFILE", ""), "Desktop")):
        if os.path.isdir(c):
            return c
    return os.path.expanduser("~")


MAIN = f"""@echo off
title SP500 Desk
cd /d "{HERE}"
echo.
echo   ==========================================
echo      S ^& P   5 0 0   D E S K
echo   ==========================================
echo.
echo   starting local dashboard ...
start "" "{PYW}" "{HERE}\\server.py"
echo   starting telegram bot ...
start "" "{PYW}" "{HERE}\\bot.py"
echo.
echo   waiting for the server to come up ...
for /L %%i in (1,1,20) do (
  "{PY}" -c "import urllib.request,sys; urllib.request.urlopen('http://127.0.0.1:{PORT}/',timeout=2); sys.exit(0)" >nul 2>&1 && goto ready
  timeout /t 1 /nobreak >nul
)
:ready
echo   opening http://127.0.0.1:{PORT}
start "" "http://127.0.0.1:{PORT}"
echo.
echo   Desk is running. Close this window - it keeps running.
echo   To stop everything: "SP500 Desk\\STOP.bat"
echo.
timeout /t 6 /nobreak >nul
"""

UPDATE = f"""@echo off
title SP500 - full refresh
cd /d "{HERE}"
echo.
echo   Full refresh: prices, fundamentals, options, workbook, alerts.
echo   This takes 20-30 minutes. Leave it open.
echo.
"{PY}" "{HERE}\\run.py" --daily
echo.
echo   done. Press any key to close.
pause >nul
"""

QUICK = f"""@echo off
title SP500 - quick refresh
cd /d "{HERE}"
echo.
echo   Quick refresh: prices and the workbook only (about 1 minute).
echo.
"{PY}" "{HERE}\\run.py" --hourly
echo.
pause >nul
"""

STOP = f"""@echo off
title SP500 - stop
echo Stopping the desk server and the telegram bot ...
taskkill /f /im pythonw.exe >nul 2>&1
echo Stopped. (Scheduled background jobs are untouched.)
timeout /t 3 /nobreak >nul
"""

EXCEL = f"""@echo off
start "" "{HERE}\\sp500_dashboard.xlsx"
"""

FOLDER = f"""@echo off
start "" explorer "{HERE}"
"""

TELEGRAM = f"""@echo off
title SP500 - telegram setup
cd /d "{HERE}"
echo.
echo   TELEGRAM SETUP
echo   ---------------------------------------------------------------
echo   1. Open Telegram, message @BotFather, send /newbot, follow it.
echo   2. Copy the token it gives you.
echo   3. Paste it into config.json as "telegram_token".
echo   4. Send ANY message to your new bot.
echo   5. Come back here and press a key.
echo   ---------------------------------------------------------------
echo.
echo   Opening config.json for you now ...
start "" notepad "{HERE}\\config.json"
pause
"{PY}" "{HERE}\\alerts.py" --setup
echo.
echo   Sending a test message ...
"{PY}" "{HERE}\\alerts.py" --test
echo.
pause >nul
"""

STATUS = f"""@echo off
title SP500 - status
cd /d "{HERE}"
"{PY}" "{HERE}\\install_tasks.py" --status
echo.
"{PY}" "{HERE}\\bot.py" --test
echo.
pause >nul
"""

FILES = [("UPDATE NOW (full).bat", UPDATE), ("UPDATE (quick).bat", QUICK),
         ("STOP.bat", STOP), ("OPEN EXCEL.bat", EXCEL),
         ("OPEN FOLDER.bat", FOLDER), ("SETUP TELEGRAM.bat", TELEGRAM),
         ("STATUS.bat", STATUS)]


def write(path: str, text: str) -> None:
    with open(path, "w", encoding="utf-8", newline="\r\n") as f:
        f.write(text)


def main() -> None:
    dt = desktop()
    sub = os.path.join(dt, "SP500 Desk")
    main_bat = os.path.join(dt, "SP500 Desk.bat")

    if "--remove" in sys.argv:
        for p in [main_bat] + [os.path.join(sub, n) for n, _ in FILES]:
            if os.path.exists(p):
                os.remove(p)
                say(f"  removed {os.path.basename(p)}")
        if os.path.isdir(sub) and not os.listdir(sub):
            os.rmdir(sub)
        return

    say(f"desktop: {dt}")
    os.makedirs(sub, exist_ok=True)
    write(main_bat, MAIN)
    say(f"  {'SP500 Desk.bat':<24} <- double-click this")
    for n, body in FILES:
        write(os.path.join(sub, n), body)
        say(f"  SP500 Desk\\{n}")
    say(f"\nproject stays at {HERE}")
    say("nothing was copied or duplicated -- the .bat files point at it")


if __name__ == "__main__":
    main()
