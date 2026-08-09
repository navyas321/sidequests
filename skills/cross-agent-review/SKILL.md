---
name: cross-agent-review
description: "Adversarially cross-check another agent's completed or in-progress work against user intent and primary evidence. Use when asked to vet an agent, audit a session report or handoff, check whether work took shortcuts, find unsupported claims or lingering processes, prepare an amendment report, produce a factual session report from verified artifacts, or spawn a genuinely independent reviewer in another vendor's CLI (Codex) so it cannot inherit the author's blind spots. Supports two roles: independent reviewer and session reporter."
---

# Cross-Agent Review

Treat the agent's summary as a hypothesis, never as evidence. Preserve unrelated user work and perform read-only inspection unless the user separately authorizes a change.

## Choose a role

Use **reviewer** when checking another agent's work. Use **session reporter** when turning already-verified evidence into a durable report. If both are requested, complete reviewer first; the reporter may only use the resulting evidence ledger.

## Run the reviewer outside the authoring context

A fork of the authoring session inherits its blind spots, and a same-vendor subagent still shares its priors. When independence matters, drive a second vendor's CLI so the reviewer re-derives everything from primary evidence. Codex CLI works well for this and is frequently already present.

- **Locate the binary before concluding it is missing.** `which codex` commonly fails while a working CLI is installed: the ChatGPT desktop app bundles one at `%LOCALAPPDATA%\OpenAI\Codex\bin\<build-hash>\codex.exe` (Windows). Glob for it rather than trusting `PATH`.
- **Invoke non-interactively** and pipe the brief on stdin:
  `codex exec -m <model> --cd <dir> --sandbox workspace-write --skip-git-repo-check -`.
  `--skip-git-repo-check` is required outside a repository.
- **Grant network only if the reviewer must verify live systems.** The sandbox blocks it by default, which silently reduces the reviewer to paraphrasing the author: add `-c sandbox_workspace_write.network_access=true` when it needs to reach local APIs or services.
- **Confirm the account actually allows the configured model.** A model set in `~/.codex/config.toml` can still be refused with `The '<model>' model is not supported when using Codex with a ChatGPT account.` Enumerate candidates from the CLI's own state (`grep -rhoE '"gpt-[0-9a-z.-]+"' ~/.codex/`) and probe them.
- **Detect probe failure on an `^ERROR:` line, never by matching the reply text.** `codex exec` echoes the prompt into its output, so searching for a sentinel word matches your own prompt and reports every model as working — a false positive that costs a whole review cycle.
- Treat a nonzero exit with findings on disk as success; teardown noise (for example a failed MCP session `DELETE`) can set the exit code after the run completed.

### Brief the external reviewer

The reviewer has none of your context, so the brief carries the whole audit. Write claims **as claims**, never as established facts, and supply the credentials, ports, and paths it needs to check them itself. Name the two or three places your own work is most likely wrong and tell it to attack those first — a reviewer pointed only at the happy path returns a rubber stamp. Require a written findings file with an explicit `CONFIRMED` / `PARTIAL` / `REJECTED` verdict, a claim-by-claim ledger, and evidence quoted from commands it ran. Instruct it to verify only: it must not repair anything it finds.

Relay the verdict to the user in full, including findings against you. A review whose defects go unreported is worth nothing.

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
