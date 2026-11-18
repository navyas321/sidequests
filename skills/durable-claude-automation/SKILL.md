---
name: durable-claude-automation
description: >-
  Make Claude Code automations on Windows SURVIVE the desktop app restarting,
  auto-updating, or crashing. Use when scheduled work must run unattended and
  reliably: "my scheduled task stopped firing", "the cron/watcher died over the
  weekend", "automation broke after an app update", "run claude headless on a
  schedule", "keep the Claude app alive", "remote session keeps disconnecting",
  "claude -p stopped working", "Claude Code CLI not found", "my background
  cache/inbox has been stale for weeks", or any unattended Claude run on Windows
  that must not depend on a long-lived in-app session.
allowed-tools: Bash, Read, Write, PowerShell
argument-hint: "[headless-task|watchdog|diagnose|resolve-cli]"
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

1. The CLI you will launch is the **real executable**, and it works:
   `& "$env:USERPROFILE\.local\bin\claude.exe" --version` and
   `... auth status` (free, no model call; JSON with `loggedIn`). Prefer the
   native installer's `~\.local\bin\claude.exe` over any `claude.cmd` wrapper on
   PATH — see **Flow E** for why a wrapper can exist and still be broken.
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

## Flow D — no-idle goal driving (interactive session + background fleets)

An interactive session driving a long `/goal` can look idle while background
work runs, and nothing external wakes it if it silently dies. The stack that
prevents real idling — and the rules that prevent *perceived* idling:

- **Layers that exist:** the `/goal` Stop hook (blocks premature turn-end);
  `/loop` ScheduleWakeup self-pacing (its fallback delay is the visible gap);
  task-notifications (background workflows/agents wake the loop immediately —
  the primary signal; the wakeup is only a safety net); a resume watcher at
  usage-limit reset (see `usage-limit-guard`); and the fully-headless autodev
  lane (scheduled watcher + watchdog) that works regardless.
- **Rules while a goal + fleet is active:**
  1. Keep the ScheduleWakeup fallback ≤ ~20 min.
  2. Before every sleep, post a coordination heartbeat + bulletin note
     (what's running, what wakes you) so dashboards show the drive as LIVE.
  3. Say in the visible turn text that fleets are running in the background —
     the transcript is what the human watches.
  4. Belt-and-braces: have the host watchdog alert (not kill) when a
     goal-driving actor goes silent >30 min while open work remains.
  5. **A user "pause to save credits" request does not disarm the `/goal` Stop
     hook by itself** (see `usage-limit-guard` Flow 0). If the goal's completion
     condition isn't fully met, the Stop hook re-fires on every turn end no
     matter what you reply, and each forced retry is a full priced completion —
     worst case a prompt-cache miss (e.g. a model switch) makes EVERY retry
     reprocess the whole context (one observed case: ~500k cache-creation tokens
     for a one-line "Paused" reply). Saying "paused" repeatedly does NOT stop the
     drain; only satisfying or cancelling the goal (or closing the session) does.

## Flow E — resolve the CLI you launch, and notice when it breaks

**The trap.** A `claude.cmd` wrapper on PATH (for example in
`%LOCALAPPDATA%\Microsoft\WindowsApps`) that locates a CLI bundled *inside the
desktop app's package* works until an app update moves or drops that bundle.
Then the wrapper prints `Claude Code CLI not found` and exits 1 — but the
wrapper file still exists, so `Test-Path` and `Get-Command claude` both say all
is well. In one deployment every headless `claude -p` spawn (inbox digest,
contact refresh, the backlog close-reviewer, a wallet extractor) failed this way
for **months**; nothing alerted because each feature swallowed its spawn error
and kept serving its last good cache.

**The fix — one resolver, used by every spawn site:**

1. An explicit override env var (each caller names the ones it honors, e.g.
   `CLAUDE_CLI`), when set and non-blank.
2. The native installer's executable: `~/.local/bin/claude.exe` on Windows,
   `~/.local/bin/claude` elsewhere.
3. `claude` on PATH.
4. The legacy wrapper/shim — **last resort only**, kept so a machine that only
   has the app's bundled CLI still works.

```python
import os, shutil
NATIVE = os.path.join(os.path.expanduser("~"), ".local", "bin",
                      "claude.exe" if os.name == "nt" else "claude")
def resolve_claude_cli(*env_names):
    for name in env_names:
        val = (os.environ.get(name) or "").strip()
        if val:
            return val
    if os.path.exists(NATIVE):
        return NATIVE
    return shutil.which("claude") or "claude"   # PATHEXT-aware: may return a .cmd wrapper
def claude_cmd(*env_names):
    exe = resolve_claude_cli(*env_names)
    # a real .exe runs directly; only a .cmd/.bat wrapper needs cmd /c
    if exe.lower().endswith((".cmd", ".bat")):
        return [os.environ.get("COMSPEC", "cmd.exe"), "/c", exe]
    return [exe]
```

`scripts/run-headless.ps1` and `watcher-reliability`'s preflight resolve in the
same order. Then make it stick:

- **Every launcher reads the resolver** — no module keeps its own hard-coded
  path. Add a regression test that greps the codebase and fails if any file
  other than the resolver names the shim path on its own.
- **Verify through the exact path the spawner uses**, cheapest first:
  `--version` (proves the binary runs), `auth status` (free; parse only the
  `loggedIn` field — the same JSON carries the account email and org, so never
  log it whole), then **one** real tiny `claude -p` spawn.
- **Logged out is not a failure to retry.** When `auth status` says
  `loggedIn: false`, queue the work, don't spend a retry, re-probe cheaply on the
  next sweep, and tell the human to run `claude auth login` once.
- **Detect by staleness, not by error.** Put an age check on what the spawns
  *produce* (a cache's `updatedAt`, a digest file's mtime): older than ~3x its
  schedule means the producer is broken, whatever its logs say. This is the
  signal that would have caught the months-long outage on day one.

## Notes & limits

- Tasks run as the **logged-on user** (needs the user logged in for the stored
  Claude OAuth) — durable against app crashes/updates/reboots, but not a
  powered-off machine. For machine-off durability use a cloud routine
  (`claude.ai/code/routines`), at ~hourly granularity.
- Never put secrets in the task definition; rely on the user's existing Claude
  auth and a gitignored `.claude/settings.local.json`.
- Keep trade/write automations to a tight `--allowedTools` server scope and a
  prompt-level guard (idempotency, circuit breaker). Test read-only first.


## Lesson (2026-07-07): exact-wall-clock hard stop
To stop a running agent session at an EXACT time (e.g. noon ET, and *only* then), register a Windows
Scheduled Task `schtasks /Create /SC ONCE /SD <date> /ST <HH:MM>` that runs a **pure-stdlib** Python
script -- never a `claude` spawn (the trigger is usually usage exhaustion, so a model call may be
blocked at fire time). Pre-author every nuanced artifact (memory, skill edits, resumption notes) and
embed them as literal strings the script writes verbatim; keep it idempotent. A scheduled task cannot
cancel a live session's ScheduleWakeup /loop or /goal, so bridge with a **sentinel file** the session
checks on each wake. Verify `Get-TimeZone` (schtasks fires at host-local time) and add an in-script ET
guard that refuses to act before the target. Validate with a `--selftest` path + `schtasks /Query`
(Next Run Time).
