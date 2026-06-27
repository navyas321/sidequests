# SCRUM — the agile SDLC process behind /feature and /bugfix

This is the shared reference for the two SDLC skills. It documents the stages,
the gates, and how the **feature** (full pipeline) and **bugfix** (light loop)
variants differ. Read it when a stage gate is ambiguous.

The model is a single-sprint Scrum loop run by one agent (plus subagents):
backlog → sprint work → verify (Definition of Done) → increment shipped.

## Step 0 — Work-item classification

Before selecting a pipeline, classify the work item. Each type maps to a
specific set of stages. Apply only the matching stages — do not run the full
feature pipeline for a spike, and do not skip stages for an epic or story.

| Type | Definition | SDLC stages to run | Notes |
|------|------------|-------------------|-------|
| **Epic** | Large initiative spanning multiple sprints; must be decomposed before coding. | Scope decomposition → per-story `/feature` runs → integrate → Release | Scope the epic (Stage 1 read-only), break into stories, run each story through its own pipeline, integrate, then release the whole increment. |
| **Story / Feature** | User-facing increment deliverable in one sprint. Adds observable value. | Full pipeline: Scope gate → Implement → Test & verify → Release | The default `/feature` pipeline. Requires plan-mode approval gate and adversarial review. |
| **Task / Chore** | Small internal unit: refactor, upgrade, cleanup, config change. No new user-facing surface. | Condensed: light Scope (intent statement, no plan-mode gate) → Implement → Test → Release | Skip the heavy plan-mode approval; a one-paragraph intent check suffices. Still requires a green check set before release. |
| **Bug** | System behaves contrary to specification or user expectation; something is broken. | Use `/bugfix`: Reproduce → Fix → Regression-test → Release | Never run `/feature` for bugs. Reproduce-first is the defining rule. |
| **Spike** | Time-boxed research or prototype to reduce uncertainty. Produces a recommendation, not shippable code. | Scope / research only (Stage 1 extended) — stop; output a written recommendation | Do not implement or release. Timeboxed. Spike output is an artifact (doc or decision), not a diff. |
| **Sub-task** | Atomic unit within a story or task, owned by one person for less than a day. | Implement → Test (no Scope gate, no Release stage — the parent story releases) | Used internally during Stage 2 of a story or task; not invoked as a top-level skill. |

**Decision rules**

- Does it add user-observable value and require acceptance criteria? → **Story**
  (full pipeline).
- Is it internal work, no new surface, nothing is broken? → **Task** (condensed
  pipeline).
- Is something currently broken that should work? → **Bug** (`/bugfix`).
- Is the approach unknown and research must come first? → **Spike** (Stage 1
  only, timeboxed).
- Is it too large to finish in one sprint? → **Epic** (decompose into stories
  first).

State the classified type in the first status block and confirm with the user
if classification is uncertain.

## The stages and their gates

A "gate" is a hard checkpoint. Do not advance to the next stage until the gate
is satisfied. Print a short status block at every gate.

| Stage | /feature | /bugfix | Gate to pass |
|-------|----------|---------|--------------|
| 1. Scope / Reproduce | Research + task breakdown with acceptance criteria, in **plan mode** | Reproduce the failure, find the **root cause** | feature: user approves the plan • bugfix: failing repro observed + root cause known |
| 2. Implement / Fix | Build task-by-task; worktrees if parallel | Smallest correct change at the root cause | All tasks complete (or fix done) and project builds |
| 3. Test & verify | Build/test/lint/typecheck loop + **adversarial review** until green | Add **regression test** + confirm old repro passes + checks green | All objective checks green, review clean, acceptance criteria met |
| 4. Release | Commit/PR + changelog + STATUS update + report | Commit/PR + changelog + STATUS update + report | Change committed (PR if asked), docs/status updated, report delivered |

## Why the gates exist

- **Scope gate (plan mode).** Stops the agent from coding the wrong thing.
  Plan mode is read-only and routes the plan through Claude Code's approval
  prompt — that human "yes" is the sprint-planning sign-off.
- **Implement gate.** Keeps the tree working; nothing half-built crosses into
  verification.
- **Verify gate (Definition of Done).** Objective checks plus an *independent*
  reviewer (not the author) is the quality bar. "Green" is non-negotiable.
- **Release gate.** Guarantees the increment is recorded (commit, changelog,
  STATUS) so it's shippable and the next session can resume.

## Definition of Done (feature)

Build passes • unit/integration tests pass • lint + typecheck clean • every
acceptance criterion met • adversarial review surfaces no unaddressed
correctness/security issue • docs/changelog updated • change committed and
STATUS updated.

## Definition of Done (bugfix)

Originally-failing repro now passes • a regression test fails-before /
passes-after (or a documented manual repro) • full check set green • root cause
(not symptom) addressed • change committed and STATUS updated.

## Feature vs. bugfix — the difference

- **Feature** is the full four-stage pipeline with a formal backlog of multiple
  tasks, an explicit plan-mode approval gate, optional parallel implementation
  in worktrees, and multi-reviewer adversarial verification. Use it for new
  capability or anything non-trivial.
- **Bugfix** is a tighter loop. The defining rule is **reproduce-first**:
  observe the failure before touching code, fix the root cause, and lock it
  with a regression test. Less ceremony, fewer tasks, optional single reviewer.
  Use it for defects.

When unsure which to use: if the work needs a multi-task breakdown and a design
decision, it's a feature; if it's "X is broken, make it not broken," it's a
bugfix.

## Claude Code primitives these skills lean on

- **Plan mode** — read-only scoping + approval gate (Stage 1 of feature).
- **TodoWrite** — the sprint backlog / task tracker across all stages.
- **Task tool / subagents** — parallel implementation (independent units) and
  *independent* adversarial review (reviewer ≠ author). Launch independent
  subagents in one message to run them concurrently.
- **Git worktrees** (`isolation: "worktree"` on an Agent, or
  `EnterWorktree`/`ExitWorktree`) — file isolation for parallel implementation.
- **Workflow tool / `/workflows`** — optional deterministic fan-out *engine*
  for large parallel sweeps (many-file review, broad research). These skills
  describe the orchestration in markdown rather than shipping a hand-written
  workflow definition; reach for the Workflow tool only when the fan-out is
  large enough to justify it.
- **STATUS.md** (session-context convention) — release-stage continuity so a
  fresh session resumes mid-sprint. Pairs with the `session-context` skill.

## Invocation

- `/feature <description>` — full pipeline.
- `/bugfix <description / repro>` — light loop.

Both are project-agnostic and require only `git` (`gh` optional). Run a subset
of stages if the user asks for only part of the process (e.g. "just scope it").
