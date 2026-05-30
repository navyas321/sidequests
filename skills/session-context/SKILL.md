---
name: session-context
description: >-
  Memory, session, state, and context management for Claude or any agent — so a
  brand-new session pointed at a repo continues exactly where the last left off.
  Use when you hear: "save session state", "checkpoint", "resume where I left
  off", "update STATUS", "where were we", "what's the next step", "orient
  yourself", "pick up where we stopped", or "what did we do last time".
allowed-tools: Bash, Read, Write
argument-hint: "[orient|checkpoint]"
---

# Session-context skill

Keep continuity across Claude (or any agent) sessions by writing and reading a
small set of markdown files in the repo. Two flows:

- **orient** — called at the start of a new session to understand where the
  project stands and what to do next.
- **checkpoint** — called at the end of a session (or on request mid-session) to
  persist everything the next session needs.

The helper script `${CLAUDE_SKILL_DIR}/scripts/snapshot.sh` gathers the raw git
and PR data; use it as the first step of both flows.

---

## Flow 1 — Orient (start of session)

Run when the user says anything like "resume where we left off", "where are we",
"orient yourself", or "what's next".

### Steps

1. **Run the snapshot script** to gather current repo state:
   ```bash
   bash "${CLAUDE_SKILL_DIR}/scripts/snapshot.sh"
   ```
   Read its output — it prints branch, recent log, working-tree status, and open
   PRs. If `gh` is absent the PR section is skipped gracefully.

2. **Read `docs/STATUS.md`** if it exists:
   ```bash
   # Read the file using the Read tool — it holds the last checkpoint
   ```
   If the file is absent, note that (no prior checkpoint exists).

3. **Read `CLAUDE.md`** at the repo root if it exists — it carries project-wide
   conventions and architecture notes.

4. **Synthesize and report** to the user in this shape:

   ```
   ## Where we are
   <phase / milestone from STATUS.md, or "fresh start" if absent>

   ## What this repo is
   <one-line from CLAUDE.md or inferred from the git log>

   ## Last session did
   <summary from STATUS.md §"This session did", or "(no prior checkpoint)">

   ## The exact next step
   <from STATUS.md §"Next step", or best inference from git log + open PRs>

   ## Open decisions / blockers
   <from STATUS.md, or "(none recorded)">

   ## Key files
   <from STATUS.md, or top-level files inferred from ls>
   ```

   Keep the summary tight — one or two sentences per section. The goal is to
   let the human (or the next agent) immediately start working, not to read
   an essay.

---

## Flow 2 — Checkpoint (end of session / on request)

Run when the user says "checkpoint", "save session state", "update STATUS", or
"wrap up".

### Steps

1. **Run the snapshot script** again to capture current state:
   ```bash
   bash "${CLAUDE_SKILL_DIR}/scripts/snapshot.sh"
   ```

2. **Ask the user (or infer from context) the four things that change each
   session:**
   - What phase/milestone are we in now?
   - What did THIS session accomplish? (bullet list, concrete)
   - What is the EXACT next step? (one sentence, actionable)
   - Any open decisions or blockers the next session must know?

   If the user said "just checkpoint" without details, infer from the
   conversation history and the snapshot output, then confirm briefly.

3. **Write / overwrite `docs/STATUS.md`** using the template below. Create the
   `docs/` directory if absent.

4. **Append a one-line entry to `docs/SESSION_LOG.md`** (create if absent):
   ```
   YYYY-MM-DD  <one-line summary of what this session did>
   ```

5. Confirm: "Checkpoint saved to docs/STATUS.md and docs/SESSION_LOG.md."

---

## docs/STATUS.md template

Write exactly this structure (fill in the placeholders):

```markdown
# Project Status

**Last updated:** YYYY-MM-DD

## Phase
<current phase or milestone name>

## This session did
- <concrete thing 1>
- <concrete thing 2>
- ...

## Next step
<single actionable sentence — precise enough that the next session can start
without reading anything else>

## Open decisions / blockers
- <decision or blocker> — <brief context>
- (none) if clear

## Key files
- `<path>` — <one-line role>
- ...

## Snapshot (auto)
<!-- updated by snapshot.sh -->
```
<branch, log tail, status, open PRs pasted here by the script>
```
```

---

## Idempotency and safety

- **Orient is always read-only.** It never writes files.
- **Checkpoint overwrites `docs/STATUS.md`** (the whole file — it is a
  single-source snapshot, not an append-only log). The append-only log is
  `docs/SESSION_LOG.md`.
- Both files should be committed to the repo (add them to the PR / commit at
  checkpoint time if the user confirms).
- The skill is **agent-agnostic**: it works for any repo, any tech stack. It
  only requires `git` to be available. `gh` is optional (PRs section degrades
  gracefully).
- Running orient or checkpoint multiple times in the same session is safe.
