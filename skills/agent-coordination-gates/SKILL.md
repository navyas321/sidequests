---
name: agent-coordination-gates
description: >-
  Make a fleet of autonomous agents share ONE backlog without stepping on each other — by ENFORCING the
  work lifecycle at the API/data layer (not by hoping agents behave) plus a lightweight file/resource-lease
  + bulletin coordination bus. Every mutation is gated: creating work must file a tracked task; picking up
  (→ in-progress) requires a named OWNER; pausing (leaving in-progress without finishing) requires a
  progress+why+validation handoff; closing (any terminal state) requires a resolution + HOW-it-was-verified.
  Use when building a multi-agent/autodev/backlog-watcher system, when agents double-pick or silently drop
  or clobber each other's files, or when you can't tell WHO did WHAT or whether "done" was real. Reference
  impl included: coord.py (leases + bus, stdlib) + gates.py (the four lifecycle gates, framework-agnostic).
---

# Agent coordination gates: enforce the work lifecycle + a lease bus

**The problem.** Point several autonomous agents (or an autodev loop + interactive sessions) at one shared
backlog and, without enforcement, you get: two agents grab the same item, an agent abandons work mid-way
leaving no trace, items get closed with "done" and no proof, and two agents edit the same file and clobber
each other. Politeness in a prompt is not enough — a fresh headless session doesn't remember the etiquette.

**The fix is two layers, both enforced by CODE, not by trust:**

## 1. Lifecycle gates (in the ONE write path that mutates a task)

Put the whole team through a single `update_item(id, patch)` (an HTTP endpoint, an MCP tool, or a library
call) and reject any transition that lacks its coordinating metadata. Four gates:

| Transition | Requires | Why |
|---|---|---|
| **create** | a tracked item exists (title + type/priority) | nothing actionable is ever lost or done off-book |
| **pickup** (→ `inprogress`) | `owner` (≥2 chars) | others see who holds it → no double-pick |
| **pause** (`inprogress` → open/blocked/paused) | `owner` + progress note (WHY paused + what's done) + a validation keyword | the next agent resumes cleanly instead of redoing it |
| **close** (any terminal: done/wontfix/duplicate/deferred…) | `resolution` (≥40 chars, WHY + steps) + a verification keyword (`verif|test|smoke|curl|render|confirm|checked|passed|/api/…`) | "done" always carries proof; no silent/one-word closes |

Each gate also **appends a dated comment** to the item (picked-up / paused / closed-as-X) so the item's
timeline is a self-documenting audit trail. The gate lives at the API/schema layer so **no caller** — UI,
autopilot, /loop, a human — can bypass it. (See `gates.py` for a framework-agnostic implementation you can
drop behind any endpoint or MCP tool; wire your own storage in the two TODO hooks.)

## 2. A file/resource-lease + bulletin bus (`coord.py`)

Gates stop bad task-state; leases stop bad FILE races. `coord.py` is a stdlib, atomic, cross-process CLI +
library over one JSON blackboard:

- **Per-actor identity** — `COORD_ACTOR=<agent-id>` on every call (a machine-wide fallback COLLIDES across
  sessions — always set it). `whoami` / `heartbeat --note "<what I'm doing>"` / `status` (who's live + what
  they hold + the bulletin).
- **File leases** — `check-file PATH` (exit 2 = a LIVE actor holds it → pick other work) → `claim-file PATH`
  → `release-file PATH` / `release-all`. Always work file-disjoint.
- **Resource leases** — `acquire <name>` / `release <name>` for singletons (a render port, a server-restart,
  a git lock) so agents don't starve each other.
- **Serialized git** — `coord.py git -- <args>` runs git under a lease → no `index.lock` races between agents.
- **Bulletin** — `announce "<msg>" --kind info|warn|act` + `bulletin` (append-only; notes never clobber).
- **TTL auto-expiry** — interactive holds ~20m, cron/watcher ~7h, resources ~10m; a crashed agent never
  holds a lease forever. Atomic writes (`*.tmp` + `os.replace`), UTF-8, ASCII CLI.

**Loop for every agent:** on start set `COORD_ACTOR` → `heartbeat` → `status` (read the bus). Before editing
any file → `check-file` then `claim-file`. On task pickup → **read the item's COMMENTS first** (handoffs +
prior findings live there). Commit via `coord.py git`. `announce` what shipped. `release-all` at end.

**Targeted `git add <files>` — NEVER `git add -A`** while other actors are live. Leases only cover files an
actor remembered to claim; a blanket `-A` sweeps every OTHER actor's in-flight, uncommitted edits into your
commit (a real incident: a watcher's `git add -A` committed 6 lines of another agent's half-finished work).
Stage exactly the files your item touched, plus your own journal/board/coordination records.

## Why it works
The metadata the gates force (owner, resolution, verification, progress-on-pause) is *exactly* what another
agent needs to coordinate — so enforcing it at the write path makes the backlog self-coordinating and the
history trustworthy. The leases make "work file-disjoint" mechanical, not a hope. Together a fleet drains one
queue with no double-picks, no silent drops, no clobbering, and a verifiable trail of who-did-what.

## Files
- `coord.py` — the lease + bus CLI/library (stdlib; run `python coord.py --help`).
- `gates.py` — the four lifecycle gates as a framework-agnostic `apply_update(item, patch)` (wire storage).
- Adapt the verification-keyword regex + TTLs to your project; keep the "one enforced write path" rule.


## Field-tested improvements (life-in-tabs, 2026-07-05, BL-1042 adversarial process review)
Three fixes that removed the biggest frictions in a ~30-review-cycle production session; port them into any
deployment of these gates:
1. **Reviewer context + prior-rejection feedback.** Independent close-reviewers judging only title+detail+
   resolution oscillate across draws (identical evidence rejected then approved; hallucinated objections).
   Feed the reviewer the item's last ~2 comments AND its own previous rejection reason with the instruction
   to judge whether THAT objection is now addressed. Verdicts converge; reviewers even self-verify files.
2. **Capture-time fuzzy dedupe.** One incident arrives as several messages; each minted id costs a full
   review cycle later. At capture, match normalized titles against open items <48h old (sequence ratio
   >=0.85 OR token-containment >=0.9 for prefix/subset resends); on match, append the message as a comment
   on the original instead of a new id. Conservative thresholds + a forceNew opt-out + fail-open.
3. **Auto run-file at pickup.** If your edit-gate requires live bookkeeping (in-progress item + fresh run
   file), CREATE the run file server-side inside the pickup mutation and auto-complete it on terminal
   close. Hand-written bookkeeping lags reality and produces false gate denials (~5 in one session).
4. **Parallelize the EXECUTION, not just the plan (2026-07-06, BL-1087).** A worktree-fleet design
   easily ships with a planner that builds file-disjoint parallel batches and an executor that quietly
   runs them serially — the throughput loss is invisible because everything still completes. Wire the
   wave through a thread pool (each unit already isolated in its own worktree/branch), serialize ONLY
   the shared-git-state steps (worktree add/registry on a lock; merges on the git lease), and prove it
   with a time-scaled test asserting wall-clock ≈ max(items), not sum.
5. **Group small items per sub-session (2026-07-06, BL-1077).** Every headless spawn re-pays the full
   context load (~10-15k tokens of project docs + prompt). Batch file-disjoint SMALL items (task/spike,
   low/medium priority) up to ~3 per sub-session — one context load, several items, one merge; grouped
   failures must reopen EVERY member. Keep bugs/features/criticals per-item.
6. **Wait on process exit, never pipe EOF (2026-07-06, BL-1090, Windows).** A headless child that spawns
   its own children (agents, MCP servers) leaks inherited pipe write-handles; `communicate()` then blocks
   until the grandchildren exit — the fleet "idles waiting for other agents" and misclassifies finished
   runs as timeouts. Feed stdin + drain stdout/stderr on daemon threads and block only in `p.wait()`.
