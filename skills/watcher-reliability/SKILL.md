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

The preflight does four things in order:

1. **Force UTF-8 everywhere** — sets `PYTHONUTF8=1`, `PYTHONIOENCODING=utf-8`,
   `[Console]::OutputEncoding`, `$OutputEncoding`, and runs `chcp 65001`. This fixes the
   recurring cp1252 crash class once and for all.

2. **Auth ping** — sends a one-shot `claude -p` prompt asking for a fixed token
   (`PREFLIGHT_OK`). If the response does not contain that token, the watcher aborts with
   status `AUTH_FAIL`. The fix is to run `claude /login` interactively on the host.

3. **MCP server check** — runs `claude mcp list` and verifies that every server named in
   `-RequiredServers` appears with status `Connected`. Missing servers → `TOOLS_MISSING`.

4. **Health record write** — atomically writes a JSON health record to `$HealthDir`
   (default: `~\ask-claude\health\<name>.json`) so dashboards and alert endpoints can read
   it without running anything.

## Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `-Name` | string | (required) | Watcher identifier; used as the health record filename |
| `-RequiredServers` | string[] | `@()` | MCP server names that must be `Connected` |
| `-Claude` | string | `%LOCALAPPDATA%\Microsoft\WindowsApps\claude.cmd` | Path to the `claude` binary; falls back to `Get-Command claude` |
| `-HealthDir` | string | `~\ask-claude\health` | Directory for health JSON records |
| `-SkipAuthPing` | switch | off | Skip the auth ping (use when claude is unavailable but tools are local) |

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

Status values: `OK` | `AUTH_FAIL` | `TOOLS_MISSING` | `ERROR`

`lastSuccessAt` is only present when `status == "OK"`. A dashboard comparing
`checkedAt` vs `lastSuccessAt` can detect watchers that are running but stuck failing.

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

## Reference implementation

**life-in-tabs** (private, Windows/Tailscale hub) is the canonical reference:

- `scripts/watcher-preflight.ps1` — the script mirrored here
- `scripts/backlog-watcher.ps1` — dot-sources preflight; drains a JSON backlog every 6h headless
- `scripts/robinhood-planb.ps1` — dot-sources preflight with `-RequiredServers robinhood-trading`
- `serve_life.py` `/api/health/watchers` — globs `~\ask-claude\health\*.json`, adds staleness flag, serves to the hub dashboard
- `/life/Monitor.html` — surfaces watcher health alongside MCP server status

## Compatibility

- Windows PowerShell 5.1 (no `-AsHashtable`, no ternary `?:`, no null-coalescing `??`)
- Requires `claude` CLI with subscription auth (not API key — remove `ANTHROPIC_API_KEY` from env)
- Works with any MCP server registered in the user's claude config
