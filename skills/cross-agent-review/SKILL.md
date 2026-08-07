---
name: cross-agent-review
description: "Adversarially cross-check another agent's completed or in-progress work against user intent and primary evidence. Use when asked to vet an agent, audit a session report or handoff, check whether work took shortcuts, find unsupported claims or lingering processes, prepare an amendment report, or produce a factual session report from verified artifacts. Supports two roles: independent reviewer and session reporter."
---

# Cross-Agent Review

Treat the agent's summary as a hypothesis, never as evidence. Preserve unrelated user work and perform read-only inspection unless the user separately authorizes a change.

## Choose a role

Use **reviewer** when checking another agent's work. Use **session reporter** when turning already-verified evidence into a durable report. If both are requested, complete reviewer first; the reporter may only use the resulting evidence ledger.

## Evidence pass

1. State the audit scope: user instructions, stated time window, repositories, systems, and artifacts.
2. Extract each distinct claimed action and each user requirement. Mark missing provenance rather than inventing it.
3. Inspect primary evidence appropriate to the claim:
   - Git: status, branch/upstream relation, commit contents, diffs, tracked files, and tests or build output.
   - Artifacts: existence, contents, timestamps, generated-output validity, and secret exposure.
   - Tracker: status, ownership, links, and whether a claimed delivery was actually closed or deliberately deferred.
   - Runtime: relevant processes, parent chains, listeners, services, scheduled tasks, temporary files, and process start times. Distinguish expected managed services from probable leftovers.
4. Cross-check implementation against the user's actual intent, including scope, safety, cleanup, portability, and acceptance criteria. A passing command alone does not prove the requested behavior.
5. Label every conclusion **verified**, **contradicted**, **partially verified**, or **not verifiable from available evidence**. Quote the smallest useful evidence and include the exact path, commit, command, or identifier.

Never terminate a process, change a tracker, push, or delete files solely to make the audit clean. Report the precise remediation and request authority for consequential cleanup.

## Reviewer output

Lead with a compact verdict and a prioritized findings table:

| Severity | Finding | Evidence | Smallest remediation |
| --- | --- | --- | --- |

Include all of the following where applicable:

- intent mismatch, missed requirements, and unverified acceptance criteria;
- shortcuts, brittle assumptions, test gaps, configuration drift, and misleading precision;
- claimed cleanup versus actual runtime/process state; identify PID, parent, start time, listener/task, and why it is likely managed or likely leftover;
- repository and installation drift, including source-versus-installed copies;
- a claim-by-claim evidence ledger, including claims that were correct.

Write an **amendment report**, not a rewritten self-congratulatory session summary. Correct the source report by section, state the impact, and keep destructive or privileged follow-up explicitly separate from observations.

## Session reporter output

Start from the reviewer ledger or other independently gathered evidence. Structure the report as: scope and date; deliverables; verified changes; intentionally open/deferred items; runtime/cleanup state; risks and follow-ups; commit/tracker trail; and evidence limitations.

Use precise counts only when the underlying query is recorded. Do not claim a push, clean tree, successful test, process cleanup, secret scan, or external-system result without direct evidence. Record corrections and failed attempts plainly. Separate user-requested actions from incidental discoveries so the next session can resume without guessing.

## Quality gate

Before finalizing, ensure that every material sentence is either evidence-backed or explicitly qualified. Re-check the report's own totals, repository names, paths, status labels, installation locations, and process conclusions. If evidence conflicts, preserve the conflict and recommend the lowest-risk verification step.
