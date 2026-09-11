"""Register (or remove) the Windows scheduled tasks that keep the sheet live.

    python research/sheet/install_tasks.py --install
    python research/sheet/install_tasks.py --status
    python research/sheet/install_tasks.py --remove
    python research/sheet/install_tasks.py --run-now      # fire each task once

WHY THIS EXISTS
The SETUP.md instructions asked you to paste three schtasks commands by hand,
which is exactly the step that does not happen -- and then the sheet silently
never updates. This registers them itself, verifies they exist, and can fire
them once so you can see output immediately rather than waiting an hour.

WHAT GETS REGISTERED
  SP500 hourly   every 60 min   prices -> workbook -> Sheets -> alerts
  SP500 daily    17:30 daily    + fundamentals, options, full Sheets push
  SP500 alerts   every 5 min    watchlist -> Telegram
  SP500 tape     every 30 min   analyst rating sweep (the 24/7 catcher)
  SP500 zone     every 2 min    LIVE quotes -> instant zone-touch push
  SP500 desk UI  at logon       localhost dashboard on :8777 (Startup folder)
  SP500 bot      at logon       Telegram command bot (Startup folder)

Tasks run whether or not you are logged in only if you supply /RU and /RP.
Without those they run under your interactive session, which means they run
when you are logged in -- fine for a desktop that stays on, and it avoids
storing your password. That is the default here, deliberately.

pythonw.exe is used instead of python.exe so no console window pops up every
five minutes.
"""
from __future__ import annotations

import io
import os
import subprocess
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

TASKS = [
    ("SP500 hourly", ["run.py", "--hourly"], ["/sc", "hourly", "/st", "09:35"]),
    ("SP500 daily", ["run.py", "--daily"], ["/sc", "daily", "/st", "17:30"]),
    ("SP500 alerts", ["alerts.py", "--check"], ["/sc", "minute", "/mo", "5"]),
    ("SP500 tape", ["tape_watch.py", "--once"], ["/sc", "minute", "/mo", "30"]),
    # zone touches are time-sensitive: a name can enter and leave inside an
    # hour, so this one runs on live quotes every 2 minutes, not on the cache
    ("SP500 zone", ["zone_watch.py", "--once"], ["/sc", "minute", "/mo", "2"]),
]

# server.py and bot.py are long-running SERVICES, not periodic jobs. schtasks
# /sc onlogon needs elevation ("Access is denied" without it), so they go in
# the per-user Startup folder instead -- same effect, no admin required.
SERVICES = [("SP500 desk UI", "server.py"), ("SP500 bot", "bot.py")]
STARTUP = os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows",
                       "Start Menu", "Programs", "Startup")


def cmd_for(script_args: list[str]) -> str:
    script = os.path.join(HERE, script_args[0])
    rest = " ".join(script_args[1:])
    return f'"{PYW}" "{script}" {rest}'.strip()


def run(args: list[str]) -> tuple[int, str]:
    r = subprocess.run(args, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return r.returncode, ((r.stdout or "") + (r.stderr or "")).strip()


def install() -> None:
    say(f"python:  {PYW}")
    say(f"scripts: {HERE}\n")
    for name, script_args, sched in TASKS:
        target = os.path.join(HERE, script_args[0])
        if not os.path.exists(target):
            say(f"  SKIP  {name:<14} ({script_args[0]} not found)")
            continue
        rc, out = run(["schtasks", "/create", "/tn", name, "/tr",
                       cmd_for(script_args), *sched, "/f"])
        say(f"  {'OK  ' if rc == 0 else 'FAIL'}  {name:<14}{'' if rc == 0 else out[:90]}")
    install_services()
    say("")
    status()
    say("\nTasks run while you are logged in. To run them when logged out, add")
    say("  /RU <user> /RP <password>   to the schtasks lines (stores a password).")


def install_services() -> None:
    if not os.path.isdir(STARTUP):
        say(f"  SKIP  startup folder not found: {STARTUP}")
        return
    for label, script in SERVICES:
        target = os.path.join(HERE, script)
        if not os.path.exists(target):
            say(f"  SKIP  {label:<14} ({script} not found)")
            continue
        bat = os.path.join(STARTUP, f"{label.replace(' ', '_')}.bat")
        with open(bat, "w", encoding="utf-8") as f:
            f.write('@echo off\r\n'
                    f'start "" "{PYW}" "{target}"\r\n')
        say(f"  OK    {label:<14}startup: {os.path.basename(bat)}")


def service_status() -> None:
    for label, script in SERVICES:
        bat = os.path.join(STARTUP, f"{label.replace(' ', '_')}.bat")
        say(f"  {label:<14}{'installed' if os.path.exists(bat) else 'NOT INSTALLED':<12}"
            f"startup folder")


def status() -> None:
    say("current state:")
    for name, _, _ in TASKS:
        rc, out = run(["schtasks", "/query", "/tn", name, "/fo", "list"])
        if rc != 0:
            say(f"  {name:<14} NOT REGISTERED")
            continue
        d = {}
        for line in out.splitlines():
            if ":" in line:
                k, _, v = line.partition(":")
                d[k.strip()] = v.strip()
        say(f"  {name:<14}{d.get('Status', '?'):<12}"
            f"next {d.get('Next Run Time', '?'):<22}"
            f"last {d.get('Last Run Time', '?')}"
            f"  rc={d.get('Last Result', '?')}")
    service_status()


def remove() -> None:
    for name, _, _ in TASKS:
        rc, out = run(["schtasks", "/delete", "/tn", name, "/f"])
        say(f"  {'removed' if rc == 0 else 'not present'}  {name}")
    for label, _ in SERVICES:
        bat = os.path.join(STARTUP, f"{label.replace(' ', '_')}.bat")
        if os.path.exists(bat):
            os.remove(bat)
            say(f"  removed  {label} (startup)")


def run_now() -> None:
    for name, _, _ in TASKS:
        rc, out = run(["schtasks", "/run", "/tn", name])
        say(f"  {'started' if rc == 0 else 'failed '}  {name}  {out[:70]}")
    say("\nGive them a minute, then: install_tasks.py --status")


if __name__ == "__main__":
    a = sys.argv[1:]
    if "--remove" in a:
        remove()
    elif "--status" in a:
        status()
    elif "--run-now" in a:
        run_now()
    else:
        install()
