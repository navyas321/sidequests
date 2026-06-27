---
name: feature
description: >-
  Drive a feature end-to-end through a full agile-scrum SDLC pipeline: scope &
  define (with a plan-mode approval gate), implement, test & verify
  (adversarial review until green), and release (commit/PR + status update).
  Use when the user says "build a feature", "implement <feature>", "/feature",
  "run the scrum workflow", "do this as a full SDLC", "ship this feature
  properly", or "scope, build, test and release X". Project-agnostic; works in
  any git repo.
allowed-tools: Task, TodoWrite, Read, Write, Edit, Bash, Grep, Glob, WebSearch, WebFetch
argument-hint: "[feature description]"
---

# /feature — full agile-scrum feature pipeline

Run a feature through four gated stages, mirroring a Scrum sprint:
**Scope & define → Implement → Test & verify → Release.** Each stage has an
explicit exit gate; do not advance until the gate is met. The feature to build
is: **$ARGUMENTS** (if empty, ask the user for a one-line description first).

This is the heavyweight variant. For a small defect, use `/bugfix` instead.
The shared process reference is `${CLAUDE_SKILL_DIR}/SCRUM.md` — read it if a
stage gate is ambiguous.

## Operating principles

- **One source of truth for tasks.** Maintain the sprint backlog with the
  `TodoWrite` tool. Every task gets `pending → in_progress → completed`. Keep
  exactly one task `in_progress` at a time unless subagents run in parallel.
- **Gates are real.** Never start implementing before the scope is approved.
  Never release before verification is green.
- **Subagents for fan-out and independence.** Use the `Task` tool to spawn
  subagents for parallel implementation of independent units and for
  *independent* review (the reviewer must not be the author). Launch
  independent subagents in a single message so they run concurrently.
- **Deterministic fan-out engine (optional).** When a stage benefits from
  large, deterministic parallelism (e.g. reviewing many files, or a broad
  research sweep), the Workflow tool / `/workflows` is the right engine — but
  only reach for it when the fan-out is genuinely large. For normal features,
  parallel `Task` subagents are simpler and sufficient.
- **Report at every gate.** End each stage with a short status block so the
  user can follow the sprint.

---

## Stage 1 — Scope & define  (gate: user approves the plan)

Goal: turn the request into a clear, testable plan. This stage is **read-only
research + planning**; do not edit code yet.

1. **Enter plan mode for the approval gate.** Plan mode keeps this stage
   read-only and routes the result through Claude Code's built-in approval
   prompt. If the session is not already in plan mode, tell the user:
   "Switch to plan mode (Shift+Tab) so the scope can go through the approval
   gate," or proceed read-only and present the plan via `ExitPlanMode` if that
   tool is available.
2. **Research the problem.** Read the relevant code, configs, and docs. Use
   `Grep`/`Glob` to map where the change lands. For unfamiliar libraries/APIs
   use `WebSearch`/`WebFetch`. For a large unknown codebase, spawn an `Explore`
   subagent via `Task` to map the area in parallel.
3. **Produce a task breakdown** — the sprint backlog. For each task give:
   - a one-line title (verb-first),
   - the files/areas it touches,
   - **acceptance criteria** (how we will know it is done — observable,
     testable),
   - dependencies / parallelizable flag.
4. **Define the Definition of Done** for the whole feature: build passes, tests
   pass, lint/typecheck clean, acceptance criteria met, docs/changelog updated.
5. **Present the plan and STOP at the gate.** Surface the plan for approval
   (plan mode's approval prompt, or an explicit "Approve this plan? (y/n)").
   Do not proceed until the user approves. Incorporate feedback and re-present
   if they ask for changes.

**Gate to pass:** user has approved the task breakdown and acceptance criteria.
On approval, seed the backlog with `TodoWrite` (one todo per task) and proceed.

---

## Stage 2 — Implement  (gate: every task complete & self-checked)

Goal: build the feature one unit at a time, keeping the tree working.

1. **Work task-by-task.** Mark a task `in_progress`, implement it, then mark it
   `completed` before moving on. Keep changes small and coherent.
2. **Parallelize independent units with subagents.** If two or more tasks are
   independent (per Stage 1 flags) and the user wants speed, dispatch them to
   parallel `Task` subagents. For file-level isolation between parallel agents,
   run each in its own git **worktree** (`isolation: "worktree"` on the Agent
   call, or `EnterWorktree`/`ExitWorktree` if available) so concurrent edits
   don't collide; merge results back when each finishes.
3. **Keep it green as you go.** After each task, run the fast local check
   (build/compile or the file's unit tests) so breakage is caught immediately.
   Do not batch all verification to the end.
4. **Follow existing conventions.** Match the repo's style, libraries, and
   patterns — read neighbouring files first. Do not add dependencies without
   noting it in the status report.

**Gate to pass:** all backlog tasks are `completed` and the project at least
builds. Then proceed to dedicated verification.

---

## Stage 3 — Test & verify  (gate: green + adversarial review clean)

Goal: prove the feature works and is correct, in rounds, until green.

1. **Run the objective checks** the repo provides — discover and run them:
   build, unit/integration tests, lint, typecheck. Detect the commands from
   the repo (package.json scripts, Makefile, pyproject, etc.); if none exist,
   say so and fall back to running the app / a smoke test.
2. **Loop until green.** If a check fails, fix it and re-run the *full* check
   set. Repeat. Never declare done on a red check.
3. **Adversarial review by an independent subagent.** Spawn a `Task` subagent
   (a reviewer that did NOT write the code) to review the diff for correctness
   bugs, missed edge cases, security issues, and unmet acceptance criteria.
   For broad reviews, run several reviewers in parallel (e.g. correctness,
   security, tests) in one message. If a `code-review` skill/command exists,
   use it. Triage findings: fix real issues (loop back to step 1), record the
   rest.
4. **Check every acceptance criterion** from Stage 1 explicitly, item by item.

**Gate to pass:** all objective checks green AND adversarial review surfaces no
unaddressed correctness/security issue AND every acceptance criterion is met.

---

## Stage 4 — Release  (gate: change is finalized & recorded)

Goal: finalize and hand off. **Do destructive/remote git actions only when the
user has asked to commit/push or clearly expects it.**

1. **Branch hygiene.** If on the default branch (`main`/`master`), create a
   feature branch before committing.
2. **Commit** the change with a clear message describing the feature and why.
   Group into logical commits if large.
3. **Changelog / docs.** Update CHANGELOG / README / relevant docs if the repo
   keeps them.
4. **Open a PR** (`gh pr create`) when the user wants one, with a summary,
   the acceptance criteria as a checklist, and test evidence.
5. **Status update.** If the repo uses `docs/STATUS.md` (session-context
   convention), update it: phase, what this sprint did, exact next step. This
   keeps a fresh session able to resume.
6. **Final report** to the user: what shipped, how it was verified, branch/PR
   link, and any follow-ups or deferred review findings.

**Gate to pass:** committed (and PR opened if requested), docs/changelog and
status updated, final report delivered.

---

## Stage status block (print at each gate)

```
### Stage <n> — <name>: <PASSED|BLOCKED>
- Done: <key outcomes>
- Backlog: <x/y tasks complete>
- Checks: <build/test/lint state>
- Gate: <what was required> → <met / blocked because…>
- Next: <next stage or the blocker to resolve>
```

## Notes

- Self-contained and project-agnostic: requires only `git`; `gh` is optional
  (PR step degrades to "commit only"). Detects tooling from the repo.
- If the user wants only part of the pipeline (e.g. "just scope it"), run the
  requested stages and stop at that gate.
