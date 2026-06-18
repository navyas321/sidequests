---
name: display-off-shortcut
description: >-
  Create a Windows Start-menu shortcut (with a conflict-free global hotkey) that
  turns OFF the display without sleeping the PC. Use when the user wants to:
  "turn off my monitor", "blank the screen", "shortcut to turn off the display",
  "hotkey to sleep the monitor", "screen off but keep downloads running", or add
  such a shortcut/hotkey to the Start menu. Display-only — the machine keeps
  running (downloads, games, streaming continue).
allowed-tools: PowerShell, Bash, Read, Write
argument-hint: "[install|run|hotkey <Ctrl+Alt+X>]"
---

# Turn-off-display shortcut (Windows)

Puts the **monitor** to sleep on demand — the PC stays fully awake, so
downloads, game streaming, and background jobs keep running. Wake it by moving
the mouse or pressing any key.

It works by broadcasting the Windows `WM_SYSCOMMAND` / `SC_MONITORPOWER` "monitor
off" message — no third-party utility (no NirCmd) required.

## Pieces

| File | Role |
|------|------|
| `scripts/Turn-Off-Display.ps1` | Sends the monitor-off message. A 600 ms delay first, so the click/keypress that launched it doesn't instantly wake the screen. |
| `scripts/Turn-Off-Display.vbs` | Self-locating silent launcher — runs the `.ps1` via hidden PowerShell with **no console flash**. Finds the `.ps1` next to itself, so the pair relocates cleanly. |
| `scripts/install-shortcut.ps1` | Copies the two scripts to a stable dir, creates the Start-menu `.lnk`, and assigns a **conflict-free** `Ctrl+Alt+<key>` hotkey. |

## Install

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\install-shortcut.ps1
```

This copies the scripts to `%LOCALAPPDATA%\display-off`, creates
**"Turn Off Display"** in the Start menu, and prints the chosen hotkey. Then:
press the Windows key, type *"Turn Off Display"*, Enter — or use the hotkey.

Options:

```powershell
# force a specific hotkey
... install-shortcut.ps1 -Hotkey "Ctrl+Alt+M"
# no hotkey, just the Start-menu entry
... install-shortcut.ps1 -Hotkey none
# custom name / install location
... install-shortcut.ps1 -Name "Screen Off" -InstallDir "C:\Tools\display-off"
```

## How the hotkey stays conflict-free

`.lnk` shortcut hotkeys are always **`Ctrl+Alt+<key>`**. The installer:

1. Scans every `.lnk` in the current-user and all-users **Start Menu** and
   **Desktop** folders, reads each one's assigned `Hotkey`, and builds the
   used-set (normalized so `Alt+Ctrl+O` == `Ctrl+Alt+O`).
2. Picks the first free combo from a preference list
   (`Ctrl+Alt+O, M, B, J, L, 0, 9`).
3. **Never uses `Ctrl+Alt+<Arrow>`** — Intel graphics reserves those for screen
   rotation.

If you pass `-Hotkey`, that wins (no scan).

## Run it directly (no shortcut)

```powershell
wscript "%LOCALAPPDATA%\display-off\Turn-Off-Display.vbs"
# or, to see it run in the foreground:
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\Turn-Off-Display.ps1
```

## Notes & limits

- **Display only.** This does not sleep, lock, or hibernate the PC. To also lock,
  chain `rundll32.exe user32.dll,LockWorkStation` before the monitor-off call.
- **Hotkey latency.** Windows `.lnk` hotkeys aren't instant — allow a beat.
- **Fullscreen capture.** A fullscreen game/app may swallow the hotkey; the
  Start-menu entry and a desktop click still work.
- **Stubborn monitors.** A few displays ignore the software power-off (driver /
  connection dependent). If yours does, fall back to a tested utility
  (`nircmd.exe monitor off`).
- Don't move/delete the Start-menu `.lnk` or the hotkey stops working.
