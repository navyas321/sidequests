---
name: bugfix
description: >-
  Drive a bug to a verified fix through a lightweight agile-scrum loop:
  reproduce, fix at the root cause, add a regression test, verify green, and
  release (commit/PR + status). Use when the user says "fix this bug", "there's
  a bug in X", "/bugfix", "this is broken", "reproduce and fix", "patch this
  defect", or "something's failing — track it down". Project-agnostic; works in
  any git repo.
allowed-tools: Task, TodoWrite, Read, Write, Edit, Bash, Grep, Glob, WebSearch, WebFetch
argument-hint: "[bug description / repro steps]"
---

# /bugfix — lightweight scrum bug loop

A defect rarely needs the full feature pipeline. Run this tighter loop:
**Reproduce → Fix → Regression-test → Release.** It still uses real gates and
the same task tracker, just with less ceremony. The bug is: **$ARGUMENTS**
(if empty, ask for the symptom and any repro steps first).

For a substantial new capability, use `/feature` instead. The shared process
reference is `${CLAUDE_SKILL_DIR}/../feature/SCRUM.md`.

---

## Step 0 — Classify the work item, then apply only the matching stages

Before entering Stage 1, confirm this is actually a bug, not a task, spike, or
feature. Misclassification wastes pipeline overhead in both directions.

| Work-item type | Definition | What to do |
|----------------|------------|------------|
| **Bug** | The system behaves contrary to its specification or user expectation. Something that *was* working (or should work) is broken. | **This skill — full Reproduce → Fix → Regression-test → Release loop.** |
| **Task / Chore** | Intentional internal change (refactor, upgrade, cleanup). Nothing is "broken" — this is deliberate improvement. | Use `/feature` condensed pipeline (light scope, implement, test, release). Not this skill. |
| **Story / Feature** | New user-facing capability. Nothing exists to break; this is net-new work. | Use `/feature` full pipeline. |
| **Spike** | Uncertainty about root cause requires research before a fix approach is known. | Run Stage 1 (Reproduce & diagnose) extended: investigate and produce a findings note with a recommended fix approach, then decide whether to loop back as a bug or escalate as a feature. |

**Decision rule:** does a user or test currently experience an outcome that
contradicts documented or reasonable expected behavior? Yes → Bug (this skill).
No → re-classify above.

After classifying, confirm the type at the top of your first status block.

---

## Operating principles

- Track the few steps with `TodoWrite` so the loop is visible.
- **Reproduce before you fix.** A fix you can't tie to a failing observation is
  a guess. Establish the failing state first.
- **Fix the root cause, not the symptom.** Diagnose why it happens before
  editing.
- **A bug fixed without a regression test will come back.** Add a test that
  fails before the fix and passes after, when the repo supports tests.
- **Evidence, not assertion.** The dominant failure is "looks done" — the fix
  looks right so you stop before proving it. Never declare the bug fixed on a
  plausible diff: show the repro failing before and passing after (the exact
  command + output). Fix the root cause; never suppress or swallow the error to
  make a check go green.
- Use a `Task` subagent for an independent review of the fix when the change is
  non-trivial or touches risky code — but do the diagnosis and fix inline
  (a bug is a tight, sequential path; spawning agents costs ~4x the tokens and
  suits parallel or broad read-only work, not a point fix). Give any reviewer
  the diff + expected behavior only, and scope it to correctness so it doesn't
  balloon the fix.
- **Multi-actor collision protocol** (when other agents/sessions share the
  repo; full protocol in the `agent-coordination-gates` skill): read the work
  item's COMMENTS before starting (handoffs/designs live there); claim files
  before editing (`coord.py check-file`/`claim-file`, held = pick other work);
  **targeted `git add <files>`, NEVER `git add -A`** with live actors (it
  sweeps their in-flight edits into your commit); check the bus periodically +
  announce what ships; pausing unfinished work requires a handoff comment
  (progress, why, how the state was left safe).

---

## Stage 1 — Reproduce & diagnose  (gate: confirmed failing repro + root cause)

1. **Reproduce the failure.** Derive the minimal repro from the report. Run it
   (run the app, the failing test, the command) and **observe the actual
   failure** — capture the error/output. If it can't be reproduced, report that
   and ask for more detail; do not proceed to a speculative fix.
2. **Locate the root cause.** Use `Grep`/`Glob`/`Read` to trace from symptom to
   cause. For a large/unknown area, spawn an `Explore` subagent via `Task`.
   State the root cause in one or two sentences before editing.
3. **Decide the fix approach** and note any risk/blast radius. For a non-trivial
   fix, briefly weigh alternatives (point fix vs. addressing the underlying
   class of bug) and flag any security or data-integrity angle so it's handled
   in the fix, not after.

**Gate to pass:** the bug is reproduced (failing state observed) and the root
cause is identified. Seed a short backlog with `TodoWrite`.

---

## Stage 2 — Fix  (gate: minimal correct change at the root cause)

1. Make the **smallest correct change** that addresses the root cause. Match
   existing conventions; read neighbouring code first.
2. Avoid scope creep — note unrelated issues spotted, but don't fix them here
   (flag them for a separate task).

**Gate to pass:** the change is implemented and the project builds.

---

## Stage 3 — Regression-test & verify  (gate: was-red-now-green + no adjacent regressions + checks clean)

> Read **[../feature/RELIABILITY.md](../feature/RELIABILITY.md)** at this gate
> and again at Release — shared hard-won invariants for the scrum pipeline
> (post-change smoke test, ASCII-only scripts, encoding traps).

1. **Add a regression test** that fails without the fix and passes with it
   (when the repo has a test harness). If there is genuinely no test
   infrastructure, document a manual repro that now passes.
2. **Confirm the original repro now passes** — re-run the exact thing that
   failed in Stage 1. This is the acceptance check for a bug: the reported
   behavior must now be correct, observed on the real client path.
3. **Run the full check set** the repo provides (build, tests, lint,
   typecheck). Loop until all green — never declare done on a red check.
4. **Verify adjacent functionality with the real client path.** Re-run the
   full existing checks after the fix is in place, then specifically probe
   functionality adjacent to the changed code. For server, auth, config, or
   routing fixes, exercise ALL affected entry points — not just loopback.
   **Simulate the actual client path:** a web server reached via a reverse
   proxy must be tested with the proxied `Host` header and the real client IP,
   not just `127.0.0.1` — a fix can pass local tests yet return "host not
   allowed" to the phone/browser over Tailscale because the forwarded `Host`
   differs. Test every key endpoint and auth flow from the real consumer's
   perspective.
5. **Other testing as applicable** — apply only what the fix actually touches,
   skip the rest explicitly:
   - **Security:** if the bug or fix touches auth, input handling, secrets, or
     user data, confirm the fix doesn't open an injection/authz/leak hole and
     that no secret landed in the diff (run a `security-review` skill if one
     exists). A security bug needs a security-minded regression test.
   - **Integration:** if the fix spans a seam between modules/services, test
     the full flow, not just the patched unit.
   - **Performance:** if the bug was a slowdown/leak, measure to confirm the
     fix actually moves the metric.
   - **Accessibility / cross-device:** for UI fixes, re-check keyboard/focus/
     labels and verify on the real target surfaces (phone + desktop).
6. **Optional independent review.** For risky changes, spawn a `Task` reviewer
   subagent to confirm the fix is correct and complete and introduces no
   regression. Use a `code-review` skill/command if one exists.

**Gate to pass:** the previously-failing repro passes (verified on the real
client path), the regression test is in place and green, no regressions in
adjacent functionality, applicable extra testing (security/integration/perf/
a11y/cross-device) done or deemed N/A, and all objective checks are green.

---

## Stage 4 — Release  (gate: change finalized & recorded)

Do destructive/remote git actions only when the user asks to commit/push or
clearly expects it.

> **MANDATORY — terminal-state rationale rule.** When moving any work item to
> ANY terminal state (done / shipped / wontfix / duplicate / deferred /
> canceled), you MUST record BOTH (a) WHY it reached that state — the reason
> the decision was made — and (b) HOW it was verified — the exact test,
> command, or observation that confirms the outcome. Write both into the item's
> resolution field AND as a dated comment on the item. Never close an item
> without this why + how-verified rationale; an item with no rationale must be
> treated as still open. **Don't fake-close:** "HOW verified" must be a real,
> re-runnable check — the repro passing (command + output), a test result, an
> observed live run — not "should be fixed" or the mere fact that a patch was
> written. If you couldn't verify it, leave it open/blocked with that reason,
> not marked fixed.

1. If on the default branch, create a fix branch first.
2. **Commit** with a message that states the bug, the root cause, and the fix.
3. Update CHANGELOG / docs if the repo keeps them.
4. Open a PR (`gh pr create`) when requested, referencing the issue and
   including before/after test evidence.
5. **Deploy and verify the fix live.** If the fix runs somewhere (a restarted
   service, a served page, a scheduled job), deploy it and confirm the bug is
   actually gone in the real environment on the real client path — not just in
   the test harness. If deployment is out of scope, say so.
6. Update `docs/STATUS.md` if the repo uses it (phase, what was fixed, next
   step). Write it so a post-compaction or fresh session can resume from
   STATUS + git history alone; commit the fix so the durable state survives a
   crash or usage-limit reset mid-loop.
7. **Final report:** root cause, the fix, the regression test, verification
   evidence (including the live check), and any deferred/flagged issues.
8. **Quick retro.** One line: how the bug slipped in and what would catch the
   class of bug earlier (a test, a check, a guardrail). File follow-ups as
   separate tasks rather than expanding this fix.

**Gate to pass:** committed (PR opened if requested), deployed-and-verified
live where applicable, docs/status updated, final report + retro delivered.

---

## Stage status block (print at each gate)

```
### Stage <n> — <name>: <PASSED|BLOCKED>
- Done: <key outcome>
- Repro: <reproduced? root cause?>
- Checks: <build/test/lint state, regression test added?, applicable extra testing (security/integration/perf/a11y)>
- Gate: <required> → <met / blocked because…>
- Next: <next stage or the blocker>
```

## Notes

- Self-contained and project-agnostic: needs only `git`; `gh` optional.
- Reproduce-first is the rule that distinguishes a real fix from a guess —
  never skip Stage 1's observed failure.

## Central scrum board (optional, env-configured)

If the environment variable `SCRUM_CENTRAL_BOARD` is set, write all run files
to that directory instead of cwd-relative `data/workflow/`. This lets a hub
(e.g. a personal dashboard) aggregate runs from every project on the machine
into one visible board.

**How to use:**

1. Set `SCRUM_CENTRAL_BOARD` to an absolute path of a directory that your
   dashboard's server globs for `*.json` run files, for example:
   `SCRUM_CENTRAL_BOARD=/path/to/my-hub/data/workflow`
2. Optionally set `SCRUM_CENTRAL_BACKLOG` to an absolute path of a
   `backlog.json` file the hub reads, so backlog items from any project appear
   on the hub's Backlog board.
3. If either variable is unset, fall back to the cwd-relative paths
   (`data/workflow/<RUNKEY>.json` and `data/backlog.json`).

**Run-file schema** (write exactly this shape):

```json
{
  "id": "<RUNKEY>",
  "project": "<the actual repo/project you are working in — not the hub repo>",
  "type": "bug",
  "session": "<short-session-slug>",
  "title": "<one-line bug title>",
  "updatedAt": "<ISO timestamp>",
  "stages": [
    {"key": "reproduce", "label": "Reproduce & diagnose", "status": "active", "tasks": [...]},
    {"key": "fix",       "label": "Fix",                  "status": "todo",   "tasks": []},
    {"key": "test",      "label": "Regression-test",      "status": "todo",   "tasks": []},
    {"key": "release",   "label": "Release",              "status": "todo",   "tasks": []}
  ]
}
```

- **Write the file as soon as Stage 1 begins** so the board shows the run in
  progress immediately. Update `status` and `updatedAt` at each stage gate.
- **Use atomic writes:** write to `<path>.tmp` then rename, so the board never
  reads a half-written file.
- The `project` field must name the repo you were working in (not the hub), so
  runs from different projects are distinguishable on the board.

**RUNKEY format:** `<PREFIX>-BG-<NN>` where PREFIX is a short all-caps project
tag and NN is a zero-padded incrementing number unique within the board
directory.
