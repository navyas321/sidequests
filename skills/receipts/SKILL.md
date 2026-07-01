---
name: receipts
description: >-
  Unbiased "show me the receipts" audit — spin up an INDEPENDENT, skeptical
  sub-agent to review every instruction the user gave over a time window (passed
  as the skill's ARG, e.g. "from 6pm today" / "this session" / "since 14:00")
  and check each against what ACTUALLY shipped (git, backlog, code — not the
  assistant's own narration). It then FILES a backlog task for every missed /
  untracked / partial finding (not just reports them). Use after a
  fast/chaotic/rapid-fire session, when the user says they're "seeing misses",
  or before a status report. Produces a report with a prioritized MUST-FIX list
  AND the tickets it filed.
---

# receipts — unbiased instruction-vs-delivery audit

**Why it exists.** In a fast back-and-forth (especially rapid phone messages), asks get
dropped, done-but-never-tracked, or "fixed" but actually broken. A self-review is biased —
you rationalize your own work. `receipts` delegates the review to a **fresh, skeptical agent**
that trusts only the repo, not your summaries.

## When to run
- The user says they're "seeing a lot of misses" / "did you actually do X?"
- After a long rapid-fire session, before you claim it's all done.
- Before a status report, so the report is grounded in verified reality.
- Whenever the number of asks outran your ability to track them.

## The process

1. **Window = the skill's ARG.** The time range comes from the invocation arg ("from 6pm
   today", "this session", "since 14:00"). If no arg is given, default to the whole current
   session. Convert the window to the transcript's timestamp format (watch UTC vs local).

2. **Launch ONE independent, skeptical auditor** (`Agent`, `subagent_type: general-purpose`,
   `run_in_background: true`), NO stake in the prior work. Give it: the **transcript path**
   (`~/.claude/projects/<slug>/<session-id>.jsonl`), the **window**, the **repo path**, and the
   project's **capture mechanism**, plus the mandate below.

   Prompt template (adapt the specifics):
   > You are an INDEPENDENT, SKEPTICAL QA auditor with NO stake in prior work — catch misses,
   > don't justify them. Do NOT trust any assistant claim; verify against the repo.
   > 1. Read the transcript at <PATH>. Extract EVERY distinct USER instruction / request /
   >    bug / feature ask / preference / correction from <WINDOW>. Number them; short verbatim
   >    quote + timestamp. Exhaustive — missing one defeats the purpose.
   > 2. For EACH, determine the TRUE status by CHECKING REALITY: git log/diffs, the tracker,
   >    the actual source (read the code — confirm it's really there and correct, not just
   >    claimed; note if verified). Status ∈ {DONE-VERIFIED, PARTIAL-OR-BROKEN, MISSED,
   >    DONE-BUT-UNTRACKED, DEFERRED-OK, NEEDS-USER}.
   > 3. Be adversarial on anything claimed fixed — quote the code.
   > 4. FILE A BACKLOG TASK for EVERY finding that is MISSED, PARTIAL-OR-BROKEN, or
   >    DONE-BUT-UNTRACKED — do NOT just report it. DEDUPE first (grep the tracker so you don't
   >    double-file an existing item). Use the project's capture path
   >    (<CAPTURE — e.g. POST http://127.0.0.1:8766/api/capture with header 'X-Ask-Claude: 1'
   >    and JSON {title,type,priority} — NOTE the field is `title`, NOT `text` (a bare `text` 400s);
   >    if that fails, append to data/backlog.json under the
   >    data/bl-id.lock file lock>). One ticket per finding: type (bug/feature/task), priority,
   >    and a detail naming the file + the smallest fix. Record each new ticket id beside its
   >    finding. Leave DONE-VERIFIED and DEFERRED-OK items alone.
   > 5. Write a report to <REPORT_PATH>: counts by status; a numbered list (quote, status,
   >    evidence, WHAT's missing + smallest fix, and the ticket id you filed); a prioritized
   >    MUST-FIX list on top.
   > Final message: report path, counts, the list of tickets you FILED, and any finding you
   > could NOT file (so the caller finishes it).

   Optionally run **two** auditors and cross-check — divergences are where truth hides.

3. **Apply + verify (you).** The misses come back already TICKETED — now fix the PARTIAL/MISSED
   ones (or route them to the drainer/autopilot), verify the DONE-BUT-UNTRACKED, flag
   NEEDS-USER to the user, and dedupe any double-files. Re-run the smoke/verify gate. Commit.

4. **Report back** with counts, the tickets filed, and what you applied.

**Coordination note:** if a concurrent drainer (autopilot) writes the tracker directly, prefer
the LOCKED capture API when filing so you don't clobber it; note any ticket it couldn't file.

## Principles
- **Verify code, not narration.** "I fixed X" means nothing until the diff/behavior proves it.
- **Untracked ≠ done.** If it shipped without a ticket, that's a process miss — file it.
- **A rule you follow from memory will drift** — prefer a deterministic gate (API validation /
  hook) over intent. (See the scrum skill's terminal-state enforcement.)
- **Skepticism is the product.** An auditor that agrees with you is worthless; reward the one
  that finds the dropped ask.

## Origin
Born 2026-06-30 on life-in-tabs after a rapid phone live-review where several asks (Face ID
auto-open, an expiry feature, a phantom ticket, a 91-finding UI scan) were missed or shipped
untracked. A skeptical sub-agent surfaced them against git+backlog+code where self-review had
not. Sync to the `sidequests` repo as an open-source, project-agnostic skill.
