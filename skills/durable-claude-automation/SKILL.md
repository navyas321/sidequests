---
name: durable-claude-automation
description: >-
  Make Claude Code automations on Windows SURVIVE the desktop app restarting,
  auto-updating, or crashing. Use when scheduled work must run unattended and
  reliably: "my scheduled task stopped firing", "the cron/watcher died over the
  weekend", "automation broke after an app update", "run claude headless on a
  schedule", "keep the Claude app alive", "remote session keeps disconnecting",
  or any unattended Claude run on Windows that must not depend on a long-lived
  in-app session.
allowed-tools: Bash, Read, Write, PowerShell
argument-hint: "[headless-task|watchdog|diagnose]"
---

# Durable Claude automation (Windows)

In-app schedulers are **not** durable. Anything that lives inside the Claude
desktop app process dies when the app restarts/auto-updates/crashes:

- **In-session crons** (`CronCreate`) — die on app restart; `durable:true` is a
  no-op in the desktop build (nothing is written to `.claude/scheduled_tasks.json`).
- **Desktop "scheduled tasks"** (the in-app MCP) — spawn fresh sessions that
  stall on harness permission prompts (Claude Code issues #47180/#40470).
- **Remote-control bridge** — does not auto-reconnect after the owning process
  dies (issue #60790); there is no `remoteControlAtStartup` setting.

The fix is to move the schedule **out of the app process** into the OS:
**Windows Task Scheduler → headless `claude -p`**. This survives app updates AND
reboots. A second task (an app watchdog) relaunches the desktop app if it
crashes, restoring remote-session reachability.

## When to use

- A scheduled Claude job must run at a fixed time every day, unattended, even if
  the app updated itself overnight.
- An automation that "worked, then silently stopped" — diagnose with the event
  log (almost always an app auto-restart that killed an in-app scheduler).
- You drive a local session from claude.ai/phone (remote control) and want it to
  come back after a crash.

## Prerequisites (verify first)

1. `claude --version` works from PowerShell (the desktop app ships a CLI shim,
   typically `…\AppData\Local\Microsoft\WindowsApps\claude.cmd`).
2. The MCP connector you need is a **user-scoped** server added via
   `claude mcp add` (these load in headless `claude -p`; app-only claude.ai
   connectors may not). Verify:
   `claude -p "list mcp tools you can see" --permission-mode dontAsk`
3. Tools the job calls are allow-listed (single-token form works; comma-joined
   lists do NOT parse): `--allowedTools "mcp__<server>"`, plus a repo-local
   `.claude/settings.local.json` for `Bash(git *)` etc.

## Flow A — durable headless scheduled task

1. Write the job instructions to a prompt file (self-contained; the run is a
   fresh session with no memory — tell it to read its own state from a repo).
2. Register the task:
   ```powershell
   scripts\register-headless-task.ps1 `
     -TaskName "MyJob" `
     -PromptFile "C:\path\to\prompt.txt" `
     -AllowedTools "mcp__my-server" `
     -WorkingDirectory "C:\path\to\repo" `
     -At 10:04 -DaysOfWeek Mon,Tue,Wed,Thu,Fri
   ```
   It runs `scripts\run-headless.ps1`, which calls
   `claude -p <prompt> --permission-mode dontAsk --allowedTools <tools>` and tees
   output to `logs\`. `-WakeToRun` + `-StartWhenAvailable` catch up a missed run.
3. **Verify before trusting it** (this is the whole point — test, don't assume):
   - Dry run read-only: `scripts\run-headless.ps1 -PromptFile … -DryRun`
   - Scheduler-invoked: `Start-ScheduledTask -TaskName "MyJob"`, then check
     `Get-ScheduledTaskInfo MyJob` (`LastTaskResult` 0 = success) and the log.

Idempotency: a headless run has no memory, so if two runners could ever fire,
put a "did today's work already happen?" check at the top of the prompt.

## Flow B — keep the app alive (remote-session resilience)

```powershell
scripts\register-watchdog.ps1                       # default: weekdays 09:50 + 16:10, hidden, NO polling
scripts\register-watchdog.ps1 -AtTimes "08:00","20:00"   # your own discrete times
scripts\register-watchdog.ps1 -EveryMinutes 10      # legacy polling fallback
```
**Prefer discrete times over polling.** The watchdog only needs to *catch* a crash, not poll — discrete weekday triggers avoid periodic CPU/window blips entirely. (`-AtLogOn` would add reboot coverage but needs an elevated prompt to register, so it's omitted by default.)

**Gotcha (the console focus-steal):** a Task Scheduler action that runs `powershell.exe` directly **flashes a console (conhost) window on every run and steals focus** — `-WindowStyle Hidden` does NOT prevent it (the conhost appears before the style applies). Launch via **`wscript.exe run-hidden.vbs <script.ps1>`** instead: `wscript` has no console and `Run(...,0,False)` starts PowerShell with a truly hidden window. Both `register-watchdog.ps1` and (optionally) the headless tasks use this.
`claude-app-watchdog.ps1` auto-detects the Store AppID
(`(Get-StartApps | ? Name -eq 'Claude').AppID`) and relaunches via
`shell:AppsFolder\<AppID>` only when no `claude` process is running. Idempotent;
logs to `%LOCALAPPDATA%\Claude\app-watchdog.log`. Verify:
`Start-ScheduledTask ClaudeApp-Watchdog` then read the log.

## Flow C — diagnose a silently-stopped automation

```powershell
# Did the app restart? (kills in-app schedulers)
Get-WinEvent -FilterHashtable @{LogName='Application'; StartTime=(Get-Date).AddDays(-3)} |
  Where-Object { $_.Message -match 'Claude VM Service' } |
  Select-Object TimeCreated, @{N='Msg';E={($_.Message -split "`n")[0]}}
# When did the app processes last start?
Get-Process claude | Select-Object Id, StartTime
# Last boot (rule out a reboot)
(Get-CimInstance Win32_OperatingSystem).LastBootUpTime
```
A `CoworkVMService` "stopped → starting" pair = an app auto-restart; any in-app
cron/watcher armed before it is gone. Migrate that job to Flow A.

## Notes & limits

- Tasks run as the **logged-on user** (needs the user logged in for the stored
  Claude OAuth) — durable against app crashes/updates/reboots, but not a
  powered-off machine. For machine-off durability use a cloud routine
  (`claude.ai/code/routines`), at ~hourly granularity.
- Never put secrets in the task definition; rely on the user's existing Claude
  auth and a gitignored `.claude/settings.local.json`.
- Keep trade/write automations to a tight `--allowedTools` server scope and a
  prompt-level guard (idempotency, circuit breaker). Test read-only first.
