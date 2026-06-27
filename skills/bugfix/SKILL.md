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
- Use a `Task` subagent for an independent review of the fix when the change is
  non-trivial or touches risky code.

---

## Stage 1 — Reproduce & diagnose  (gate: confirmed failing repro + root cause)

1. **Reproduce the failure.** Derive the minimal repro from the report. Run it
   (run the app, the failing test, the command) and **observe the actual
   failure** — capture the error/output. If it can't be reproduced, report that
   and ask for more detail; do not proceed to a speculative fix.
2. **Locate the root cause.** Use `Grep`/`Glob`/`Read` to trace from symptom to
   cause. For a large/unknown area, spawn an `Explore` subagent via `Task`.
   State the root cause in one or two sentences before editing.
3. **Decide the fix approach** and note any risk/blast radius.

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

## Stage 3 — Regression-test & verify  (gate: was-red-now-green + checks clean)

1. **Add a regression test** that fails without the fix and passes with it
   (when the repo has a test harness). If there is genuinely no test
   infrastructure, document a manual repro that now passes.
2. **Confirm the original repro now passes** — re-run the exact thing that
   failed in Stage 1.
3. **Run the full check set** the repo provides (build, tests, lint,
   typecheck). Loop until all green — never declare done on a red check.
4. **Optional independent review.** For risky changes, spawn a `Task` reviewer
   subagent to confirm the fix is correct and complete and introduces no
   regression. Use a `code-review` skill/command if one exists.

**Gate to pass:** the previously-failing repro passes, the regression test is
in place and green, and all objective checks are green.

---

## Stage 4 — Release  (gate: change finalized & recorded)

Do destructive/remote git actions only when the user asks to commit/push or
clearly expects it.

1. If on the default branch, create a fix branch first.
2. **Commit** with a message that states the bug, the root cause, and the fix.
3. Update CHANGELOG / docs if the repo keeps them.
4. Open a PR (`gh pr create`) when requested, referencing the issue and
   including before/after test evidence.
5. Update `docs/STATUS.md` if the repo uses it (phase, what was fixed, next
   step).
6. **Final report:** root cause, the fix, the regression test, verification
   evidence, and any deferred/flagged issues.

**Gate to pass:** committed (PR opened if requested), docs/status updated,
final report delivered.

---

## Stage status block (print at each gate)

```
### Stage <n> — <name>: <PASSED|BLOCKED>
- Done: <key outcome>
- Repro: <reproduced? root cause?>
- Checks: <build/test/lint state, regression test added?>
- Gate: <required> → <met / blocked because…>
- Next: <next stage or the blocker>
```

## Notes

- Self-contained and project-agnostic: needs only `git`; `gh` optional.
- Reproduce-first is the rule that distinguishes a real fix from a guess —
  never skip Stage 1's observed failure.
