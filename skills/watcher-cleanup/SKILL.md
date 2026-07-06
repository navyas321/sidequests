# watcher-cleanup — dead/orphaned custom-watcher scan + clean

Companion to `watcher-reliability` (which covers a watcher **failing to run correctly**: auth,
codec, MCP-down). This skill covers the other failure mode: a watcher that **still exists as config
litter but no longer does anything** — created once via a hub's "schedule a custom watcher" feature,
then partially torn down by hand (a scheduled task deleted directly in Task Scheduler without going
through the app, or a prompt file deleted from disk) or left as an orphaned health record after the
watcher itself was fully removed. None of these serve any purpose; they accumulate as
board/Task-Scheduler noise and stale health entries that never resolve.

## The pattern (three-way registration consistency)

A hub-created custom watcher always has THREE parts that must agree:

1. A **prompt file** — `data/watchers/<slug>.prompt.txt`
2. A **scheduled task** — Windows Task Scheduler entry `<app>-watcher-<slug>`
3. An optional **health record** — `health/watcher-<slug>.json`, written by the watcher's own
   preflight/run (per `watcher-reliability`)

"Dead" = any state where the three parts have gone inconsistent so the config **no longer actually
runs anything**, or is pure leftover litter:

| hasPrompt | hasTask (confirmed) | hasHealth | Verdict |
|---|---|---|---|
| yes | confirmed NO | any | **dead** — prompt with no scheduled task never actually runs |
| no | confirmed YES | any | **dead** — orphaned task registration (prompt deleted by hand) |
| no | confirmed NO | yes | **dead** — leftover health record, nothing behind it |
| yes | confirmed YES | any | healthy — **only flagged** (not removed) if chronically failing >14d |
| any | **UNKNOWN** (query failed) | any | **never dead** — conservative: an unreadable task query must never be treated as "no task exists" |

Three things this pattern deliberately does NOT do:

- **Never touches core managed services** (the app's own watcher/watchdog/agent tasks) or diagnostic
  watchers — permanent infra with its own bare-name health-file convention (`<name>.json`, not
  `watcher-<slug>.json`), structurally excluded from the scan's health-file glob and task-name prefix.
- **Never auto-removes a fully-registered watcher just because it's failing.** Both a prompt file AND
  a task but chronically bad health = *flagged* for human review only — it may just need a re-login,
  not deletion. That failure mode is `watcher-reliability`'s job.
- **Never trusts the name prefix alone.** (Field lesson, 2026-07-06, origin deployment:) the core
  backlog watcher registered its own ONE-SHOT fast-resume task as `<app>-watcher-resume` — matching
  the custom-watcher prefix while being core infra with, by design, no prompt file. The scan
  classified it "dead" and every clean tap unregistered the pending resume, silently breaking the
  autopilot's resume chain until the next run re-registered it — and making the clean button never
  reach "all clean". **Maintain an explicit RESERVED-SLUGS set** (excluded at the task-query source
  AND belt-and-suspenders in clean) for every core task name that lives under the prefix.

## Reference implementation (life-in-tabs, BL-1079 + BL-1081)

- `serve_life.py`:
  - `_WATCHER_RESERVED_SLUGS` — core-infra task names under the prefix, never scanned/cleaned.
  - `_watcher_registered_task_slugs()` — queries `Get-ScheduledTask -TaskName '<app>-watcher-*'`
    via a timeout-guarded subprocess; returns `(ok, slugs)` where `ok=False` on ANY failure (never
    conflated with "confirmed empty"); reserved slugs excluded at the source.
  - `watchers_scan()` — pure dry-run report: `{dead:[...], flagged:[...], taskQueryOk, generatedAt}`.
  - `watchers_clean()` — re-scans, then unregisters/deletes every `dead` entry via the same registrar
    unregister path the app's own remove flow uses; leaves `flagged` alone; skips reserved slugs.
  - Routes: `GET /api/watchers/scan`, `POST /api/watchers/clean`.
- One-tap UI: a "Clear watchers" button that POSTs clean and shows removed/flagged counts inline
  ("all clean ✓" when nothing is dead).
- `tests/test_watchers_cleanup.py` — the three dead-detection rules, flag-don't-delete, core-service
  exclusion, query-failure-is-never-destructive, clean idempotency, route registration.

## How to verify (no live Task Scheduler access required)

```
python -m pytest tests/test_watchers_cleanup.py -q     # detection rules + invariants
GET  /api/watchers/scan                                # dry-run against the live host
POST /api/watchers/clean                               # idempotent; expect {ok, removed, count}
# then confirm every core task survived:
Get-ScheduledTask -TaskName '<app>-watcher-*','<core task names>'
```

## Compatibility

Same as `watcher-reliability`: Windows PowerShell 5.1-compatible `Get-ScheduledTask` query,
`CREATE_NO_WINDOW` subprocess flags (no console flash), stdlib-only.

*Origin: extracted from life-in-tabs BL-1079 (orchestrator-built scan/clean + Home button) and
hardened by the BL-1081 reserved-slug incident the same night.*
