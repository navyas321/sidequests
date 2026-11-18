---
name: watcher-reliability
description: >-
  Preflight pattern that makes headless `claude -p` / MCP watchers (Windows
  Scheduled Tasks, background loops) fail LOUD at the start instead of silently
  mid-run: force UTF-8, resolve and prove the real Claude CLI runs, check login
  for free, verify required MCP servers are Connected, and write a health record
  a dashboard can read. Use when "the watcher stopped working and nobody
  noticed", "Scheduled Task says 0 but nothing ran", "UnicodeEncodeError cp1252",
  "claude -p fails with CLI not found", "MCP server not connected in headless",
  or when adding any new unattended claude job. Ships watcher-preflight.ps1.
---

# watcher-reliability — headless claude/MCP watcher preflight pattern

A PowerShell preflight script and reliability pattern for headless `claude -p` / MCP
watchers running as Windows Scheduled Tasks or background processes.

## The problem

Headless watchers fail silently in predictable ways that are easy to prevent:

| Failure class | Symptom | Root cause |
|---|---|---|
| Auth token rotated | Watcher 401s for hours unnoticed | No pre-check; Scheduled-Task "Last Result: 0" is meaningless for detached launchers |
| cp1252 codec crash | Python raises `UnicodeEncodeError` on any UTF-8 MCP output (e.g. checkmarks) | Windows console defaults to cp1252; headless sessions inherit it |
| MCP server down | Tool calls return errors silently | No pre-check that required servers are `Connected` before real work begins |
| CLI wrapper broken | Every spawn prints `CLI not found` for weeks; `Test-Path claude.cmd` still True | A PATH wrapper resolves a CLI bundled inside the desktop app's package; an app update removed it |
| No observability | Nobody knows the watcher is broken | Health records are never written; no dashboard surface |

**NEVER trust Scheduled-Task "Last Result".** A detached launcher (PowerShell spawning
a background process) always exits 0. The task result tells you nothing about whether
the actual watcher ran, succeeded, or crashed.

## The pattern

Every headless watcher MUST dot-source `watcher-preflight.ps1` before doing any real
work and bail out if `$global:PreflightOK` is false.

```powershell
# At the top of your watcher script (dot-source so UTF-8 env sticks):
. "$PSScriptRoot\watcher-preflight.ps1" -Name my-watcher -RequiredServers my-mcp-server
if (-not $global:PreflightOK) { exit 11 }

# ... rest of watcher work ...
```

The preflight does these things in order:

1. **Force UTF-8 everywhere** — sets `PYTHONUTF8=1`, `PYTHONIOENCODING=utf-8`,
   `[Console]::OutputEncoding`, `$OutputEncoding`, and runs `chcp 65001`. This fixes the
   recurring cp1252 crash class once and for all.

2. **Resolve and prove the CLI** — `-Claude` if given, else `$env:CLAUDE_CLI`, else the
   native installer's `~\.local\bin\claude.exe`, else `claude` on PATH, else the legacy
   `WindowsApps\claude.cmd` shim. Then `claude --version` must succeed, or the status is
   `CLI_MISSING`. A wrapper `.cmd` can exist and still be broken, so existence is not proof.
   Apply the same resolver to every other place your code spawns `claude` (see
   `durable-claude-automation` Flow E).

3. **Auth** — first `claude auth status` (free, no model call; only the `loggedIn` field is
   read, because the same JSON carries the account email/org). Logged out -> `AUTH_FAIL`
   without spending anything. Then, unless `-SkipAuthPing`, a one-shot `claude -p` asking for
   a fixed token (`PREFLIGHT_OK`) proves a real spawn works. The fix for either failure is to
   run `claude auth login` interactively on the host.

4. **MCP server check** — runs `claude mcp list` and verifies that every server named in
   `-RequiredServers` appears with status `Connected`. Missing servers → `TOOLS_MISSING`.

5. **Health record write** — atomically writes a JSON health record to `$HealthDir`
   (default: `~\ask-claude\health\<name>.json`) so dashboards and alert endpoints can read
   it without running anything.

## Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `-Name` | string | (required) | Watcher identifier; used as the health record filename |
| `-RequiredServers` | string[] | `@()` | MCP server names that must be `Connected` |
| `-Claude` | string | (resolved) | Path to the `claude` binary. Empty = `$env:CLAUDE_CLI` -> `~\.local\bin\claude.exe` -> PATH -> `WindowsApps\claude.cmd` |
| `-HealthDir` | string | `~\ask-claude\health` | Directory for health JSON records |
| `-SkipAuthPing` | switch | off | Skip the model-call auth ping (the free `auth status` check still runs) |

## Health record format

```json
{
  "name": "my-watcher",
  "status": "OK",
  "detail": "preflight passed (auth + tools)",
  "authOK": true,
  "toolsOK": true,
  "checkedAt": "2026-06-29T10:00:00.000Z",
  "lastSuccessAt": "2026-06-29T10:00:00.000Z"
}
```

Status values: `OK` | `CLI_MISSING` | `AUTH_FAIL` | `TOOLS_MISSING` | `ERROR`

`lastSuccessAt` is only present when `status == "OK"`. A dashboard comparing
`checkedAt` vs `lastSuccessAt` can detect watchers that are running but stuck failing.

**Also watch the OUTPUT, not just the watcher.** A preflight proves the watcher *could*
work; it does not prove the thing it produces is fresh. Add an age check on each artifact a
headless job writes (a cache's `updatedAt`, a digest's mtime) and alert when it is older than
~3x its schedule. In one deployment a broken CLI wrapper silently starved an inbox cache for
months; a staleness check on that cache would have flagged it the first day.

## Dashboard surface

Serve the health directory over an HTTP endpoint and poll/SSE it from your dashboard.
The health records are small atomic JSON files — any stdlib HTTP server can glob them.

Example API pattern (Python stdlib):

```python
import json, pathlib, time

HEALTH_DIR = pathlib.Path.home() / 'ask-claude' / 'health'

def get_watcher_health():
    watchers = []
    for f in HEALTH_DIR.glob('*.json'):
        try:
            rec = json.loads(f.read_text(encoding='utf-8'))
            # Flag as stale if checkedAt is more than 2h ago
            checked = rec.get('checkedAt', '')
            # ... staleness logic ...
            watchers.append(rec)
        except Exception:
            pass
    return watchers
```

## Reference shape

Extracted from a private Windows home hub where it runs in production:

- a backlog watcher script dot-sources the preflight and drains a JSON backlog headless
- a trading-journal job dot-sources it with `-RequiredServers <its-mcp-server>`
- the hub's `/api/health/watchers` globs the health directory, adds a staleness flag, and
  serves it to a monitor page next to MCP server status

## Compatibility

- Windows PowerShell 5.1 (no `-AsHashtable`, no ternary `?:`, no null-coalescing `??`)
- Requires `claude` CLI with subscription auth (not API key — remove `ANTHROPIC_API_KEY` from env)
- Works with any MCP server registered in the user's claude config
