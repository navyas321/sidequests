---
name: display-off-shortcut
description: >-
  Create a Windows Start-menu shortcut (with a conflict-free global hotkey) that
  turns OFF the display without sleeping the PC, and can also wake it back ON.
  Use when the user wants to: "turn off my monitor", "blank the screen",
  "shortcut to turn off the display", "hotkey to sleep the monitor", "screen off
  but keep downloads running", "turn the monitor back on from a script", or add
  such a shortcut/hotkey to the Start menu. Display-only — the machine keeps
  running (downloads, games, streaming continue).
allowed-tools: PowerShell, Bash, Read, Write
argument-hint: "[install|run|hotkey <Ctrl+Alt+X>] [-Action off|on]"
---

# Turn-off-display shortcut (Windows)

Puts the **monitor** to sleep on demand — the PC stays fully awake, so
downloads, game streaming, and background jobs keep running. Wake it by moving
the mouse or pressing any key. Can also **turn the display back on** from a
script or remote button.

It works by broadcasting the Windows `WM_SYSCOMMAND` / `SC_MONITORPOWER`
message — no third-party utility (no NirCmd) required.

## Pieces

| File | Role |
|------|------|
| `scripts/Turn-Off-Display.ps1` | Sends the monitor-off or monitor-on message. Accepts `-Action off\|on` (default `off`). The `off` path has a 600 ms delay so the click/keypress that launched it doesn't instantly wake the screen. The `on` path also tries a best-effort DDC/CI hardware wake. |
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
# Turn the display off (default):
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\Turn-Off-Display.ps1
# — or explicitly:
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\Turn-Off-Display.ps1 -Action off

# Turn the display back on:
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\Turn-Off-Display.ps1 -Action on

# Silent (no console window), using the VBS launcher — off only:
wscript "%LOCALAPPDATA%\display-off\Turn-Off-Display.vbs"
```

## Off vs On — what each action does

### `off` (default) — software display-off, stays mouse-wakeable

Broadcasts `WM_SYSCOMMAND SC_MONITORPOWER` with `lParam=2`. This is the
**software / DPMS path**: the panel enters a low-power state that is immediately
cancelled by any mouse movement or keypress at the desk. The machine stays fully
awake. This is intentionally *not* DDC/CI, so no physical button or DDC command
is needed to wake it.

### `on` — software wake + best-effort DDC/CI hardware wake

1. **Input nudge** — micro mouse move (1 px right, 1 px left). Wakes a panel
   that was put to sleep via the software `off` path instantly.
2. **Power-on broadcast** — `WM_SYSCOMMAND SC_MONITORPOWER lParam=-1`.
3. **DDC/CI VCP 0xD6 = 1** — enumerates physical monitors via `dxva2.dll` and
   sends the DDC/CI "power on" command to each. Useful only if the panel was
   put into a true hardware-off state (e.g. by the monitor's power button or
   another DDC/CI tool). **Best-effort: silently skipped on monitors that do
   not support DDC/CI** — the software wake above will have already fired.
4. Second input nudge — ensures the cursor is visible after wake.

## Notes & limits

- **Display only.** This does not sleep, lock, or hibernate the PC. To also lock,
  chain `rundll32.exe user32.dll,LockWorkStation` before the monitor-off call.
- **Hotkey latency.** Windows `.lnk` hotkeys aren't instant — allow a beat.
- **Fullscreen capture.** A fullscreen game/app may swallow the hotkey; the
  Start-menu entry and a desktop click still work.
- **Stubborn monitors.** A few displays ignore the software power-off (driver /
  connection dependent). If yours does, fall back to a tested utility
  (`nircmd.exe monitor off`).
- **DDC/CI caveat.** The hardware-wake path in `-Action on` works only on
  monitors that support DDC/CI (most modern displays do). If DDC/CI is disabled
  in the OSD or the monitor doesn't support it, the command is silently ignored
  — the software wake still fires.
- Don't move/delete the Start-menu `.lnk` or the hotkey stops working.
