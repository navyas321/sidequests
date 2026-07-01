---
name: feature
description: >-
  Drive a feature end-to-end through a full agile-scrum SDLC pipeline: scope &
  design (with a plan-mode approval gate), implement, test & verify
  (acceptance + regression + security + code review until green), and release
  (commit/PR + deploy-and-verify + status + retro).
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

---

## Step 0 — Classify the work item, then apply only the matching stages

Before entering Stage 1, identify the type of work item and select the
appropriate pipeline. Do not run the full feature pipeline for a bug or spike —
and do not skip stages for an epic or story that genuinely needs them.

| Work-item type | Definition | Pipeline to run |
|----------------|------------|-----------------|
| **Epic** | Large initiative (weeks–months) that must be decomposed into multiple stories before any coding starts. Crosses sprint boundaries. | **Scope decomposition gate → per-story `/feature` runs → integration → Release.** Scope the epic first (Stage 1 read-only), break it into stories, run each story through its own `/feature` pipeline, then integrate and release the whole. |
| **Story / Feature** | A user-facing increment deliverable in one sprint. Adds new value observable by a user. | **Full four-stage pipeline** (this skill): Scope gate → Implement → Test & verify → Release. |
| **Task** | A small, internal unit of work (under ~half a sprint). No new user-facing surface, but supports a story or keeps the system healthy. Chores ("upgrade library X", "refactor Y") are tasks. | **Condensed pipeline:** light Scope (no heavy plan-mode gate — brief intent statement suffices), Implement → Test → Release. Skip the formal plan-mode approval; proceed after a one-paragraph intent check. |
| **Bug** | A defect: the system behaves contrary to its specification or user expectation. | **Use `/bugfix` instead** (Reproduce → Fix → Regression-test → Release). Do not run this skill for bugs. |
| **Spike** | Time-boxed research or prototyping to reduce uncertainty. Produces a recommendation or decision, not shippable code. | **Scope/research only** (Stage 1 extended): timebox the investigation, produce a written recommendation, and stop. Do not implement or release. |

**Decision rule:** if unsure between Story and Task, ask: does it add
user-observable value and require acceptance criteria? Yes → Story (full
pipeline). No → Task (condensed pipeline). If it might be an Epic, ask: can
it be done in one sprint? No → decompose into stories first.

After classifying, state the type at the top of your first status block and
confirm with the user if uncertain. Then proceed with the matching pipeline.

---

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
- **Right altitude — inline vs. subagent.** Do the work inline when the path is
  known and sequential (most coding is): spawning agents costs ~4x the tokens
  and multi-agent is a poor fit for shared context and tight dependencies.
  Reach for subagents to (a) preserve main-context on a broad read-only sweep,
  (b) run genuinely independent units in parallel, or (c) get an independent
  reviewer. Scale effort to the task: 1 agent for a fact-find, a few for
  comparisons/parallel units. Have each subagent return a condensed summary,
  not its raw transcript.
- **Evidence, not assertion.** The dominant failure is "looks done" — output is
  plausible so the agent stops before verifying. Never claim a stage passed on
  a plausible-looking result: paste the exact command run and its output, the
  test result, or the observed run. If you cannot show evidence, the stage is
  not passed. Fix root causes; never suppress, swallow, or work around an error
  to make a check go green.
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
2. **Orient, then research.** If resuming (fresh or post-compaction session),
   first read `docs/STATUS.md` and recent git history to recover where prior
   work left off, and smoke-test that prior work still runs before building on
   it. Then research the problem: read the relevant code, configs, and docs;
   use `Grep`/`Glob` to map where the change lands; for unfamiliar
   libraries/APIs use `WebSearch`/`WebFetch`. For a large unknown codebase,
   spawn an `Explore` subagent via `Task` to map the area in parallel and
   return a condensed summary.
3. **Produce a task breakdown** — the sprint backlog. For each task give:
   - a one-line title (verb-first),
   - the files/areas it touches,
   - **acceptance criteria** (how we will know it is done — observable,
     testable),
   - dependencies / parallelizable flag.
4. **Sketch the design / approach** before committing to a backlog. For any
   non-trivial change, briefly state the design: the approach chosen, the main
   alternatives considered and why they were rejected, the data/contract/API
   shape, and the blast radius (what else this touches). Note security and
   privacy implications here so they're designed in, not bolted on. Keep it
   proportional — a paragraph for a small feature, a short section for a large
   one. This is the lightweight design review that prevents building the wrong
   thing well.
5. **Define the Definition of Done** for the whole feature: build passes, tests
   pass, lint/typecheck clean, acceptance criteria met (feature/acceptance
   tests green), security check clean, docs/changelog updated, deployed and
   verified in the target environment.
6. **Present the plan and STOP at the gate.** Surface the plan for approval
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

## Stage 3 — Test & verify  (gate: acceptance + regression green + review + security clean)

Goal: prove the feature **does the new thing it was asked to do**, is correct,
and broke nothing — in rounds, until green. Testing here is broader than
regression: it covers the new behavior plus whatever testing dimensions the
change actually touches.

1. **Run the objective checks** the repo provides — discover and run them:
   build, unit/integration tests, lint, typecheck. Detect the commands from
   the repo (package.json scripts, Makefile, pyproject, etc.); if none exist,
   say so and fall back to running the app / a smoke test.
2. **Loop until green.** If a check fails, fix it and re-run the *full* check
   set. Repeat. Never declare done on a red check.
3. **Feature / acceptance testing (the new behavior).** Prove the feature
   meets the acceptance criteria from Stage 1 — go through them item by item
   and demonstrate each is satisfied (a test, a command, or an observed run).
   Exercise the new behavior on the **real client path**, not just a unit
   harness: drive it the way a user/consumer actually will. This is the
   primary purpose of the stage — a green regression suite does not prove the
   feature works.
4. **Regression testing (nothing adjacent broke).**
   - Re-run the full existing check set (build, lint, typecheck, tests) after
     the feature change is in place.
   - Add a fails-before / passes-after test specific to this change (unit,
     integration, or documented manual repro).
   - **Verify adjacent functionality with the real client path.** For any
     server, auth, config, or routing change, exercise ALL affected entry
     points — not just the happy path. Critically: **simulate the actual
     client path, not loopback only.** Example: a web server reached via a
     reverse proxy must be tested with the proxied `Host` header and the real
     client IP, not just `127.0.0.1` — a change can pass local tests yet
     return "host not allowed" or misbehave for the phone/browser over
     Tailscale because the forwarded `Host` differs. Test every key endpoint
     and auth flow from the perspective of the real consumer.
5. **Other testing as applicable** — apply only the dimensions the change
   actually touches; skip the rest explicitly:
   - **Integration / end-to-end:** if the feature spans modules, services, or
     a DB/queue/external API, test the seams and the full flow, not just units.
   - **Security:** if it touches auth, input handling, secrets, file/network
     access, or user-supplied data, check for the relevant class of issue
     (injection, XSS, authz bypass, path traversal, leaked secrets/PII,
     unsafe deserialization). Run a `security-review` skill/command if one
     exists. Confirm no secret or credential landed in the diff.
   - **Performance:** if it's on a hot path or handles large inputs, sanity-
     check latency / memory / query count against expectations; watch for N+1s
     and accidental O(n²).
   - **Accessibility:** for UI changes, check keyboard navigation, focus
     states, labels/alt text, semantic markup, and contrast.
   - **Cross-device / cross-environment:** for UI or client-facing changes,
     verify on the real target surfaces (e.g. phone + desktop, the actual
     browser over Tailscale), not just the dev machine.
6. **Code review + adversarial review by an independent subagent.** Spawn a
   `Task` subagent (a reviewer that did NOT write the code) that sees only the
   **diff + acceptance criteria**, not your authoring reasoning, and tries to
   refute the result. Review for correctness bugs, missed edge cases, security
   issues, style/maintainability, and unmet acceptance criteria. For broad
   reviews, run several reviewers in parallel (e.g. correctness, security,
   tests) in one message. Use a `code-review` skill/command if one exists.
   **Scope the review to correctness and the stated requirements** — a reviewer
   told to find gaps always finds some, and chasing every one causes
   over-engineering. Triage findings: fix real correctness/security issues
   (loop back to step 1), record the rest as follow-ups rather than expanding
   scope.

**Gate to pass:** all objective checks green AND every acceptance criterion is
demonstrably met (feature/acceptance verified on the real client path) AND no
regressions in adjacent functionality (real client path included) AND the
applicable extra testing (integration/security/perf/a11y/cross-device) is done
or explicitly deemed N/A AND code/adversarial review surfaces no unaddressed
correctness or security issue.

---

## Stage 4 — Release  (gate: change is finalized, deployed-and-verified & recorded)

Goal: finalize, ship, and hand off. **Do destructive/remote git actions only
when the user has asked to commit/push or clearly expects it.**

> **MANDATORY — terminal-state rationale rule.** When moving any work item to
> ANY terminal state (done / shipped / wontfix / duplicate / deferred /
> canceled), you MUST record BOTH (a) WHY it reached that state — the reason
> the decision was made — and (b) HOW it was verified — the exact test,
> command, or observation that confirms the outcome. Write both into the item's
> resolution field AND as a dated comment on the item. Never close an item
> without this why + how-verified rationale; an item with no rationale must be
> treated as still open. **Don't fake-close:** "HOW verified" must be a real,
> re-runnable check (a command + its output, a test result, an observed live
> run) — not "should work" or the mere fact that code was written. If you
> couldn't verify it, ship it as blocked/deferred with that reason stated, not
> as done.

1. **Branch hygiene.** If on the default branch (`main`/`master`), create a
   feature branch before committing.
2. **Commit** the change with a clear message describing the feature and why.
   Group into logical commits if large.
3. **Changelog / docs.** Update CHANGELOG / README / relevant docs if the repo
   keeps them. Document any new config, flags, env vars, or migration steps a
   consumer needs.
4. **Open a PR** (`gh pr create`) when the user wants one, with a summary,
   the acceptance criteria as a checklist, and test evidence.
5. **Deploy and verify in the target environment.** If the change is deployed
   (a running service restarted, a page served, a job scheduled), actually
   deploy it and then **verify it live** — smoke-test the deployed artifact on
   the real client path, not just the local build. A change that passed tests
   but was never observed working where it runs is not done. If deployment is
   out of scope (library, PR for someone else to merge), say so explicitly.
6. **Status update.** If the repo uses `docs/STATUS.md` (session-context
   convention), update it: phase, what this sprint did, exact next step. This
   keeps a fresh session able to resume. Write it to survive **context
   compaction**: a post-compaction (or brand-new) session should resume from
   STATUS + git history alone, without the current window. For long runs, keep
   the state durable *during* the sprint too — commit per coherent change with
   a descriptive message and checkpoint STATUS at each stage gate, so a
   usage-limit or crash mid-pipeline loses at most one step, not the sprint.
7. **Final report** to the user: what shipped, how it was verified (acceptance
   + regression + applicable extra testing + live check), branch/PR link, and
   any follow-ups or deferred review findings.
8. **Quick retro.** Close with one or two lines: what went well, what to do
   differently next time, and any debt or follow-up work to file (spawn a
   separate task for anything out of scope rather than expanding this one).

**Gate to pass:** committed (and PR opened if requested), deployed-and-verified
live where applicable, docs/changelog and status updated, final report + retro
delivered.

---

## Stage status block (print at each gate)

```
### Stage <n> — <name>: <PASSED|BLOCKED>
- Done: <key outcomes>
- Backlog: <x/y tasks complete>
- Checks: <build/test/lint state; acceptance + regression + applicable extra testing (integration/security/perf/a11y/cross-device)>
- Review: <code/adversarial review state; security check>
- Gate: <what was required> → <met / blocked because…>
- Next: <next stage or the blocker to resolve>
```

## Notes

- Self-contained and project-agnostic: requires only `git`; `gh` is optional
  (PR step degrades to "commit only"). Detects tooling from the repo.
- If the user wants only part of the pipeline (e.g. "just scope it"), run the
  requested stages and stop at that gate.

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
  "type": "feature",
  "session": "<short-session-slug>",
  "title": "<one-line feature title>",
  "status": "active",
  "createdAt": "<ISO timestamp>",
  "updatedAt": "<ISO timestamp>",
  "stages": [
    {"key": "scope",     "label": "Scope & define",  "status": "active", "tasks": [...]},
    {"key": "implement", "label": "Implement",        "status": "todo",   "tasks": []},
    {"key": "test",      "label": "Test & verify",    "status": "todo",   "tasks": []},
    {"key": "release",   "label": "Release",          "status": "todo",   "tasks": []}
  ]
}
```

- **Write the file as soon as Stage 1 begins** so the board shows work in
  progress immediately. Update `status` and `updatedAt` at each stage gate.
  Set top-level `status` to `done` on release.
- **Use atomic writes:** write to `<path>.tmp` then rename, so the board never
  reads a half-written file.
- The `project` field must name the repo you were working in (not the hub), so
  runs from different projects are distinguishable on the board.

**RUNKEY format:** `<PREFIX>-<TYPE>-<NN>` where PREFIX is a short all-caps
project tag, TYPE is `FE`/`BG`/`TK`/`EP`/`ST`/`SP` matching the work-item
type, and NN is a zero-padded incrementing number unique within the board
directory.
