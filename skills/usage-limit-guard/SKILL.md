---
name: usage-limit-guard
description: >-
  Survive Claude Code usage limits and resume a long autonomous loop after an
  outage, session death, or rate-limit hard-stop. Use when you hear: "won't
  this die on the 5-hour limit", "make this survive usage limits", "resume after
  the limit resets", "checkpoint so a fresh session can continue", "the watcher
  died and lost its work", "run this headless overnight", "how much usage am I
  burning", "pause/stop everything to save credits", "why is usage still
  dropping after I paused", or whenever building/hardening any repo-backed loop
  (backlog watcher, /loop, nightly agent) that must make progress across limits
  and restarts.
allowed-tools: Bash, Read, Write, Edit
argument-hint: "[pause|usage|guard|resume|checkpoint]"
---

# usage-limit-guard

Make any **repo-backed autonomous loop** (a backlog watcher, a `/loop`, a nightly
headless agent) keep making forward progress across:

- the Claude subscription **5-hour rolling** + **weekly** usage caps (hard stop, no
  recovery until the window resets),
- session death / a killed terminal / a power loss,
- the fact that on **Windows `--resume` / `-c` are buggy** (freeze, lost
  conversations, crash on killed sessions) — so you may NOT depend on session
  resume here.

The core idea: **the repo is the resume state, not the session.** Commit per
work-item; keep a small machine-readable checkpoint + a dated journal. A brand-new
`claude -p` (or a human) resumes by *reading* that state. One kill loses ≤1 item.

This generalizes the life-in-tabs backlog-watcher pattern into a reusable recipe
for any repo and any tech stack. `git` is the only hard requirement.

> **Don't just survive the limit — avoid it.** See [`TOKEN-MANAGEMENT.md`](./TOKEN-MANAGEMENT.md)
> for token-saving rules (`opusplan`, model/effort tiering, subagent tiering,
> `/compact` at task boundaries, cache discipline) that stretch a session so you
> hit the cap far less often.

---

## Background — how the limits actually work (keep current)

- **5-hour rolling window**: opens on your FIRST prompt and covers the next 5h
  (not a fixed clock). Shared pool across Claude Code, Claude.ai chat, and Cowork.
  The 5h cap was **doubled 2026-05-06**.
- **Weekly cap**: resets at a **fixed time assigned to your account** — same day/time
  every week, independent of when you start. (Got a temporary +50% on 2026-05-13,
  set to expire ~2026-07-13 unless extended.)
- **At the limit** (extra-usage disabled): a **HARD STOP** with no recovery until
  the window resets. The message states the reset time, e.g.
  `session limit · resets 6:10am (America/New_York)`.
- **Non-interactive split (since 2026-06-15):** `claude -p`, the Agent SDK, GitHub
  Actions, and third-party apps authenticating with your subscription draw from a
  **separate monthly credit pool** — they no longer compete with interactive
  sessions. So a headless watcher may exhaust *credits* rather than the 5h/weekly
  caps; treat both as "the limit" and back off the same way.

---

## Flow 0 — Actually stopping the drain (`pause`)

A user asking you to **"pause" / "stop everything" to conserve credits is asking you to make
credit consumption STOP, not to narrate that it stopped.** Two independent ways a "pause" can
silently fail to do that (both observed in production):

1. **A "paused" reply does not disarm an active `/goal`'s Stop hook.** If a `/goal` loop's
   completion condition (e.g. "BOTH X and Y done") isn't fully met, its Stop hook re-fires on
   **every** turn end regardless of what you just said. Replying "Paused at your request,
   checkpointed" satisfies the *user* but not the hook — it re-triggers immediately, forcing
   another full-priced completion, in a loop, for as long as the session stays open. This is
   expensive even when short: if anything mid-session caused a **prompt-cache miss** (e.g. a model
   change), **every one of those retries reprocesses the entire cached context from scratch** —
   one observed turn billed ~500k cache-creation tokens for a one-line "Paused." reply. The
   transcript can show ten consecutive "Paused"/"Holding" turns, each a real, large charge, while
   the user watches credits drop and reasonably believes "everything was stopped" because the
   *words* said so. **The only real stop is to end the condition that re-arms the hook** — satisfy
   it, cancel/end the `/goal` itself, or close the session — not to keep answering it. If you must
   keep the session open, say so explicitly and flag that further Stop-hook nags keep costing
   real credits until the goal is cancelled.
2. **"Stop everything" is machine-wide, not project-scoped.** Disabling the current repo's own
   scheduled tasks is NOT "everything". List every enabled scheduled task
   (`Get-ScheduledTask | Where-Object State -eq Ready` on Windows, `crontab -l` + systemd timers
   elsewhere) and check **every** one that spawns `claude` / `claude -p` **across every project on
   the machine**, not just the ones this repo's notes know about. A sibling project's bot or
   watcher draws from the **same shared credit pool** and keeps firing on its own schedule,
   invisibly, after the requested project is fully quiesced. Report the state of ALL
   claude-spawning tasks, not only the ones native to the current working directory.

Verify a real pause with **evidence**, not narration: re-list scheduled tasks (none enabled should
spawn `claude`), confirm no `/goal` is still armed, and check that no new transcript turns are
being appended after the "pause" reply.

**Pattern for a genuine "stop the drain" button:** a machine-wide, *behavior-based* (not
name-list-based) pause. Walk every scheduled task's action — following `.vbs`/`.ps1`/`.cmd`
wrapper indirection a few hops deep — looking for an actual `claude` / `claude -p` invocation;
disable every match that is currently enabled; record exactly what you disabled to a state file so
`--resume` restores precisely those (never a task that was already off, never one you didn't
touch). A `--dry-run` lists matches with no changes.

**Scheduled hard stop at a fixed clock time.** When the ask is "hard-stop at exactly HH:MM, not
before", register an OS-scheduled job at that local time (confirm the host's time zone first —
`[System.TimeZoneInfo]::Local.Id` / `timedatectl`) running a **pure-stdlib** script — never a
`claude` spawn, since the trigger is usually usage exhaustion and a model call may be blocked at
fire time. The script refuses to act before the target time (an in-script guard, not just the
trigger). An OS scheduler cannot reach into a *live* interactive session to cancel its
`/loop` / `ScheduleWakeup` chain or abandon a `/goal`, so bridge that with a **sentinel file** the
live session checks on every wake and honors. Pre-author any nuanced content (memory, skill edits,
resumption notes) while context is fresh and embed it as literal strings the script writes
verbatim — don't defer "lessons learned" to a hypothetical future session, and don't make the
script fake judgment it doesn't have. Validate with a `--selftest` / `--dry-run` path that
exercises every step with zero side effects, then confirm the scheduler's next run time is the
target moment.

**Caveat — check for an in-flight duplicate build before shipping your own.** Two independent
agent sessions once built two different hard-stop mechanisms for the same ticket concurrently and
ended up with two jobs both armed for the same minute. Context recall surfaces *related* prior
items but not a sibling's *live in-flight* build of the exact same one — before registering a new
scheduled job, check `git log --oneline` and the board's run files for a suspiciously fresh
commit/run on the same ticket id.

**Caveat — an orphan-reaper can kill live siblings, not just dead ones.** A "reap orphaned
`claude -p`" step that kills any `claude -p` whose parent is *named* `python.exe` / `pythonw.exe`,
without checking whether that parent is alive and legitimately driving it, kills real in-flight
work on a host running several agent sessions. Always dry-run a pause/reap script first and
eyeball what it would actually kill.

---

## Flow 1 — Usage visibility (`usage`)

> **The only programmatic usage signal is local transcript token-burn.** The real
> claude.ai **5h / weekly limit %** is NOT exposed by any API.

There are two distinct things people mean by "my usage":

1. **Local token burn** — how many tokens this machine spent (what `ccusage` /
   serve_life's `/api/usage` report). This IS programmatically derivable: scan
   `~/.claude/projects/**/*.jsonl` transcripts and sum the `message.usage`
   (`input_tokens`, `output_tokens`, `cache_creation_input_tokens`,
   `cache_read_input_tokens`) per time bucket (today / 5h block / 7d).
2. **The actual limit gauge** (the "you're at 36% of your 5h window" number) —
   **not API-exposed.** It only shows in the Claude UI / the limit message. Any
   stored plan-% file is a *manual snapshot*, not a live reading.

### How to read local burn

Run the bundled helper (pure stdlib Python, no deps):

```bash
python "${CLAUDE_SKILL_DIR}/scripts/token_burn.py"
```

It prints today / 5h-block / 7d totals and the last transcript timestamp. Use the
5h-block number as a **proxy** for how hard the current rolling window has been hit
— rising fast → you are approaching the cap. (It is a proxy, not the true %, because
the cap is account-wide and shared with chat.)

Reference implementation to mirror if you reimplement: life-in-tabs
`serve_life.py` → `local_token_burn()` / `claude_usage_payload()` (serves
`/api/usage`). It caps the scan (most-recent-modified files, 8-day window) so a
polling page can't stampede the disk.

**Report to the user honestly:** give the local burn numbers, and state plainly that
the true 5h/weekly limit % is not available programmatically — only the burn proxy
and whatever limit message Claude last surfaced.

---

## Flow 2 — Limit guard for a headless run (`guard`)

Wrap each unattended run so it **detects** the limit and **backs off cleanly**
instead of dying mid-edit.

1. **Bound the run.** Process ≤N items per invocation; add `--max-turns <n>`; keep a
   soft wall-clock budget. Short runs rarely exhaust a window, and a 6h scheduled
   cadence roughly aligns with the ~5h rolling window so each run gets fresh-ish
   budget.

2. **Run headless with structured output** so you parse signals instead of scraping:
   ```bash
   claude -p "<prompt>" --output-format json --max-turns 30 > run.json
   rc=$?
   ```
   (`stream-json` for incremental; `--output-format json` is enough for a per-item run.)

3. **Detect the limit.** There is **no dedicated rate-limit exit code yet** (`exit 75`
   is an open request); `claude -p` just exits non-zero on exhaustion. So branch on
   BOTH the exit code and the payload:
   - In streamed events, a retryable failure emits a `system` / `api_retry`-style
     event carrying an `error` category — branch when `error == "rate_limit"`
     (others: `overloaded`, `billing_error`, `authentication_failed`,
     `server_error`, `max_output_tokens`).
   - As a fallback, **string-match the result** for `session limit · resets` (and
     `rate_limit` / `usage limit`). The reset clock is in that text — e.g.
     `resets 6:10am (America/New_York)`.
   - Parse the reset time out and store it (see Flow 3 → `limitResetsAt`).

   The helper `scripts/detect_limit.py` does this parse for you:
   ```bash
   python "${CLAUDE_SKILL_DIR}/scripts/detect_limit.py" run.json $rc
   # prints one of:  OK  |  LIMIT <reset-text-or-empty>  |  ERROR <category>
   ```

4. **Back off, don't retry.** On a limit: finish the current item's commit (Flow 3),
   write `limitResetsAt` to the checkpoint, and **exit cleanly**. Do NOT busy-retry —
   it can't succeed until the window resets. The next scheduled run (or a one-shot
   wake just after the reset time) resumes.

5. **Cadence + observability.** Schedule the loop (e.g. every 6h) with
   "start when available" so it fires after a missed/outage window, and
   restart-on-failure. Log to a file; surface last-run / next-item / `limitResetsAt`
   somewhere visible.

---

## Flow 3 — Durable resume (`checkpoint` / `resume`)

This is the half that makes a *fresh* session continue. Three artifacts, committed:

### A. Commit per item
After **every** work-item: update the board/backlog, append the journal, then
`git commit` (and push if remote). **The commit IS the checkpoint.** A kill at any
point loses at most the one item in flight.

### B. `CHECKPOINT.json` — the machine-readable resume pointer
Write/overwrite after each item. Minimal shape:

```json
{
  "epic": "<optional epic/loop id>",
  "loop": "<watcher / loop name>",
  "lastRun": "<ISO8601 with offset>",
  "lastItem": "<id of the item just finished>",
  "nextItem": "<id to do next, or null if drained>",
  "doneThisCycle": ["<ids done this run>"],
  "limitResetsAt": "<ISO8601 or human reset text, or null>",
  "summary": "<one line: where we stopped / why>"
}
```

### C. Dated journal `docs/journal/<YYYY-MM-DD>.md`
Append-only, one structured entry per item: id, type, what changed, test result,
commit hash, follow-ups, and an explicit `STOPPED:` line when the run ends (budget
hit, limit hit, or drained) naming the next item.

### Resume procedure (a fresh `claude -p` / new session does this on start)

1. **Read `CHECKPOINT.json`** → `lastItem`, `nextItem`, `limitResetsAt`.
   If `limitResetsAt` is in the future, **stop** — the window hasn't reset.
2. **Read the open work** — `data/backlog.json` (by priority) and any board files
   (`data/workflow/*.json`) — to confirm `nextItem` and pick up if it's stale.
3. **Read the latest `docs/journal/<date>.md`** for context on the last item.
4. **Read `git log`** — each per-item commit is a checkpoint; reconcile against the
   journal if they disagree (newest commit wins).
5. **Read project memory / `CLAUDE.md` / `docs/STATUS.md`** for conventions.
6. Continue from `nextItem`. **Do NOT use `claude --resume` / `-c` on Windows** —
   they freeze / lose the conversation / crash on killed sessions. Resume is by
   *reading repo state*, full stop. (On macOS/Linux `--resume <session-id>` captured
   from `--output-format json` is fine if you prefer it, run from the same dir.)

This also applies to an interactive `/loop`: keep the board, backlog,
`docs/journal`, and memory current every loop so a post-compaction or post-limit
fresh session reads them and continues. **Never hold critical state only in the
conversation.**

---

## Setup checklist (bootstrapping the pattern in a new repo)

- [ ] `docs/journal/` exists with a `README.md` explaining the resume order.
- [ ] `docs/journal/CHECKPOINT.json` exists (seed with `nextItem` = first item).
- [ ] A work source the loop reads (`data/backlog.json` or issues) with priorities.
- [ ] The run prompt includes the explicit rule: *"near the limit → commit + journal
      + push + end; do not start a new item."*
- [ ] Scheduled with start-when-available + restart-on-failure; logs to a file.
- [ ] A short `docs/USAGE-LIMITS-AND-RESUME.md` playbook in-repo (copy this skill's
      Background + Flows 2–3 and tailor).

## Safety / idempotency

- `usage` and `resume` (orient) are **read-only**.
- `CHECKPOINT.json` is overwritten (single source of truth); the journal is
  append-only; the backlog/board are edited in place then committed.
- Re-running resume is safe — it just re-reads state.
- The pattern is agent-agnostic and stack-agnostic; only `git` is required. `gh`
  (push) and a scheduler are optional.
