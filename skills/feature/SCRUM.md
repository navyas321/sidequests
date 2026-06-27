# SCRUM — the agile SDLC process behind /feature and /bugfix

This is the shared reference for the two SDLC skills. It documents the stages,
the gates, and how the **feature** (full pipeline) and **bugfix** (light loop)
variants differ. Read it when a stage gate is ambiguous.

The model is a single-sprint Scrum loop run by one agent (plus subagents):
backlog → sprint work → verify (Definition of Done) → increment shipped.

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
