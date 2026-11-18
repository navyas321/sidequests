#!/usr/bin/env python
"""display-hotkey-agent.py - resident Ctrl+Alt+<key> -> display-off hotkey agent (Windows).

WHY THIS EXISTS: the Start-menu .lnk hotkey route relies on Explorer's shortcut-hotkey
dispatcher. On some machines that dispatcher goes quietly dead for shortcut launches: the
registration holds, the press is delivered, but the target never runs (.cmd, wscript and
pythonw targets alike), and an Explorer restart does not heal it. This agent owns the hotkey
itself through RegisterHotKey + a message loop and launches the display-off script directly.

Before declaring the .lnk hotkey dead, read the display-off log from a process OUTSIDE your
agent session (see SKILL.md): a sandboxed session can see a stale private copy of the log.

  hotkey   : Ctrl+Alt+<key>, default O (MOD_NOREPEAT - holding the combo fires once)
  action   : powershell -File <Turn-Off-Display.ps1 next to this file, or --ps1 PATH>
             (CREATE_NO_WINDOW - never flashes a console)
  instance : single (named mutex); a second copy exits quietly
  log      : %LOCALAPPDATA%\\display-off\\hotkey-agent.log
  autostart: run it with pythonw.exe from a Startup-folder shortcut or .vbs

Strip the hotkey from the Start-menu .lnk first (install-shortcut.ps1 -Hotkey none),
otherwise Explorer keeps the combo and RegisterHotKey fails.

Usage:
  pythonw display-hotkey-agent.py                 # Ctrl+Alt+O, ps1 next to this file
  pythonw display-hotkey-agent.py --key M --ps1 C:\\Tools\\Turn-Off-Display.ps1

Stdlib only. ASCII only. UTF-8 IO.
"""
import argparse
import ctypes
import ctypes.wintypes as wt
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(os.environ.get("LOCALAPPDATA", HERE), "display-off")
LOG = os.path.join(LOG_DIR, "hotkey-agent.log")

MOD_ALT, MOD_CONTROL, MOD_NOREPEAT = 0x0001, 0x0002, 0x4000
WM_HOTKEY = 0x0312
HOTKEY_ID = 0xB253  # arbitrary, unique within this thread
CREATE_NO_WINDOW = 0x08000000
ERROR_ALREADY_EXISTS = 183


def log(msg):
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write("%s  %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg))
        if os.path.getsize(LOG) > 128 * 1024:          # keep the log small
            with open(LOG, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()[-300:]
            tmp = LOG + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                f.writelines(lines)
            os.replace(tmp, LOG)
    except Exception:
        pass


def fire_display_off(ps1):
    try:
        subprocess.Popen(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-WindowStyle", "Hidden", "-File", ps1],
            creationflags=CREATE_NO_WINDOW,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        log("hotkey fired -> display off launched")
    except Exception as e:
        log("LAUNCH FAILED: %s" % e)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Own a Ctrl+Alt+<key> hotkey that turns the display off.")
    ap.add_argument("--key", default="O", help="letter or digit for Ctrl+Alt+<key> (default O)")
    ap.add_argument("--ps1", default=os.path.join(HERE, "Turn-Off-Display.ps1"),
                    help="path to Turn-Off-Display.ps1 (default: next to this file)")
    a = ap.parse_args(argv)

    key = (a.key or "O").strip().upper()
    if len(key) != 1 or not key.isalnum():
        log("FATAL: --key must be one letter or digit, got %r" % a.key)
        return 2
    vk = ord(key)   # VK codes for 0-9 and A-Z equal their ASCII upper-case codes

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    kernel32.CreateMutexW(None, False, "Global\\display-hotkey-agent")
    if kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
        return 0

    if not os.path.isfile(a.ps1):
        log("FATAL: %s missing" % a.ps1)
        return 1

    # Retry briefly at login: Explorer may still hold a stale registration from an old .lnk
    # for a few seconds while the shell settles.
    ok = False
    for _ in range(30):
        if user32.RegisterHotKey(None, HOTKEY_ID, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, vk):
            ok = True
            break
        time.sleep(2)
    if not ok:
        log("FATAL: RegisterHotKey Ctrl+Alt+%s failed after retries "
            "(someone else holds it - is the .lnk hotkey still assigned?)" % key)
        return 1

    log("registered Ctrl+Alt+%s (pid %d)" % (key, os.getpid()))
    msg = wt.MSG()
    try:
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                fire_display_off(a.ps1)
    finally:
        user32.UnregisterHotKey(None, HOTKEY_ID)
        log("exiting")
    return 0


if __name__ == "__main__":
    sys.exit(main())
