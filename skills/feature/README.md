# scrum-workflow — agile SDLC skills for Claude Code

A pair of Claude Code skills that run features and bugfixes through a proper
agile-Scrum pipeline: **four gated stages, a plan-mode approval gate, TodoWrite
sprint backlog, parallel subagents, and adversarial review.** Drop them into
any git repo and get a repeatable, structured SDLC from a single slash command.

| Skill | Command | Use when |
|-------|---------|----------|
| **feature** | `/feature <description>` | New capability, non-trivial change, needs design + multi-task breakdown |
| **bugfix** | `/bugfix <description / repro>` | "X is broken — track it down and fix it" |

The shared process reference is `SCRUM.md` (this directory) — both skills cite
it when a gate is ambiguous.

---

## The four stages

```
[Scope & define] --gate:approved--> [Implement] --gate:builds--> [Test & verify] --gate:green--> [Release]
```

| # | Stage | Feature | Bugfix | Gate |
|---|-------|---------|--------|------|
| 1 | **Scope / Reproduce** | Research + task breakdown + acceptance criteria in plan mode | Reproduce the failure, identify root cause | feature: user approves • bugfix: failing repro + root cause known |
| 2 | **Implement / Fix** | Task-by-task; parallel worktrees for independent tasks | Smallest correct change at root cause | All tasks complete, project builds |
| 3 | **Test & verify** | Build/test/lint loop + adversarial review by independent subagent | Regression test (was-red-now-green) + full check set | All checks green, review clean, acceptance criteria met |
| 4 | **Release** | Commit/PR + changelog + STATUS update + final report | Commit/PR + changelog + STATUS update + final report | Committed (PR if asked), docs updated, report delivered |

**Gates are hard checkpoints** — the agent does not advance until the gate
condition is satisfied. Every gate ends with a printed status block.

---

## Feature vs. bugfix

- **`/feature`** is the full pipeline: formal sprint backlog, plan-mode
  approval gate, optional parallel implementation in git worktrees, and
  multi-reviewer adversarial verification. Use it for anything new or
  non-trivial.
- **`/bugfix`** is the tighter loop: **reproduce-first** (observe the failure
  before touching code), fix the root cause, lock it with a regression test.
  Less ceremony, same quality bar. Use it for defects.

When unsure: if it needs a design decision and a multi-task breakdown, it's a
feature. If it's "this is broken — make it not broken," it's a bugfix.

---

## Claude Code primitives used

| Primitive | Role |
|-----------|------|
| **Plan mode** | Read-only scoping + approval gate (Stage 1 of feature) |
| **TodoWrite** | Sprint backlog — `pending → in_progress → completed` |
| **Task / subagents** | Parallel implementation + independent adversarial review |
| **Git worktrees** (`isolation: "worktree"`) | File-level isolation for concurrent subagents |
| **`docs/STATUS.md`** | Release-stage continuity — pairs with the `session-context` skill |

---

## Installation (via sidequests plugin)

```text
/plugin marketplace add navyas321/sidequests
/plugin install sidequests@sidequests
```

Then open a new Claude Code session and invoke:

```
/sidequests:feature add dark mode to the settings page
/sidequests:bugfix the login form submits even when email is blank
```

## Standalone usage (no plugin)

Clone the repo and point Claude at the SKILL.md files directly, or copy the
markdown into your project's `.claude/skills/` directory and invoke with the
skill name.

## Requirements

- `git` (required)
- `gh` (optional — PR step degrades to "commit only" if absent)
- Any tech stack — both skills detect build/test/lint commands from the repo

---

## License

MIT — part of [sidequests](https://github.com/navyas321/sidequests).
