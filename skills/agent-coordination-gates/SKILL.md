---
name: agent-coordination-gates
description: >-
  Make a fleet of autonomous agents share ONE backlog without stepping on each other — by ENFORCING the
  work lifecycle at the API/data layer (not by hoping agents behave) plus a lightweight file/resource-lease
  + bulletin coordination bus. Every mutation is gated: creating work must file a tracked task; picking up
  (→ in-progress) requires a named OWNER; pausing (leaving in-progress without finishing) requires a
  progress+why+validation handoff; closing (any terminal state) requires a resolution + HOW-it-was-verified.
  Use when building a multi-agent/autodev/backlog-watcher system, when agents double-pick or silently drop
  or clobber each other's files, when you can't tell WHO did WHAT or whether "done" was real, or when agent
  closes are slipping past the reviewer by looking like the human (e.g. PowerShell's Mozilla User-Agent).
  Reference impl included: coord.py (leases + bus, stdlib) + gates.py (the lifecycle gates, an optional
  server-owned reviewer hook, and a human-vs-agent User-Agent classifier; framework-agnostic).
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
| **close → done/shipped** | `resolution` (≥40 chars, WHY + steps) + a verification keyword (`verif|test|smoke|curl|render|confirm|checked|passed|/api/…`) | "done" always carries proof; no silent/one-word closes |
| **close → any DISPOSAL state** (`wontfix`/`canceled`/`duplicate`/`deferred`) | the done-close requirements **PLUS an independent review** of the drop | disposal is where work gets *quietly dropped*; force a skeptic to justify NOT doing it — wontfix/cancel "did you exhaust it?", deferred "genuinely blocked or avoiding buildable work?", **duplicate "REALLY the same item, or distinct work dropped under a dup label? — name the canonical id"** |
| **human-only states** (default `accepted` = "risk accepted") | the caller is the human on the board | an agent that can write "risk accepted" parks inconvenient work there; most of such a pile turns out not to be a risk at all |

Each gate also **appends a dated comment** to the item (picked-up / paused / closed-as-X) so the item's
timeline is a self-documenting audit trail. The gate lives at the API/schema layer so **no caller** — UI,
autopilot, /loop, a human — can bypass it. (See `gates.py` for a framework-agnostic implementation you can
drop behind any endpoint or MCP tool; wire your own storage in the two TODO hooks.)

### The review must be server-owned, and "the human" must be classified properly

Two holes that let agent closes skip review in production — check both in any deployment:

- **A typed review token is not a review.** The minimal gate accepts a resolution containing
  `adversarial` as proof of review — but the author can write that word without any review
  happening, and a fork of the author's own context reviewing its own work inherits its blind
  spots. The robust form: the write path itself spawns the reviewer (a fresh model call, a second
  vendor's CLI, or a human queue — never the author's context), and stamps a **server-owned**
  `reviewedBy` field the caller cannot set. `gates.apply_update(..., reviewer=fn)` does exactly
  this; the regex token stays only as the fallback when no reviewer is wired. If the reviewer is
  unavailable, `done` proceeds with an `auditFlag`; **disposals fail closed**.
- **"Starts with Mozilla" is not "is a human".** Gates usually exempt the human on the board (a
  human disposition needs no reviewer) and key that off the request User-Agent. Windows PowerShell's
  `Invoke-RestMethod` / `Invoke-WebRequest` send `Mozilla/5.0 (Windows NT; …) WindowsPowerShell/5.1…`,
  so with a bare `ua.startswith("Mozilla")` test, **every agent on Windows that calls the API from
  PowerShell is booked as the human** — closes go through in seconds with no review stamp. Fix:
  browser = Mozilla prefix **AND** no scripted-client token (`powershell`, `headlesschrome`, `curl/`,
  `python`, `node-fetch`, `okhttp`, …) — `gates.is_human_ua()`. Put it in **one** shared classifier,
  call it from every human-only rule, and add a regression test that fails if any module tests the
  `mozilla` prefix itself. Document the limit honestly: a UA is self-declared, so a script that sends
  a full browser UA still passes — this stops honest scripted clients, not deliberate impersonation.
  Agents (and audit sub-agents filing tickets) should send an explicit non-browser UA such as
  `my-agent/1.0`; after a close, check the item carries the reviewer's stamp.

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
- `gates.py` — the lifecycle gates as a framework-agnostic `apply_update(item, patch, reviewer=, actor_is_human=)`
  (wire storage), plus `is_human_ua(ua)`. `python gates.py` runs a self-demo of every gate.
- Adapt the verification-keyword regex + TTLs to your project; keep the "one enforced write path" rule.


## Field-tested improvements (2026-07, from an adversarial process review of a production fleet)
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
4. **Parallelize the EXECUTION, not just the plan (2026-07-06).** A worktree-fleet design
   easily ships with a planner that builds file-disjoint parallel batches and an executor that quietly
   runs them serially — the throughput loss is invisible because everything still completes. Wire the
   wave through a thread pool (each unit already isolated in its own worktree/branch), serialize ONLY
   the shared-git-state steps (worktree add/registry on a lock; merges on the git lease), and prove it
   with a time-scaled test asserting wall-clock ≈ max(items), not sum.
5. **Group small items per sub-session (2026-07-06).** Every headless spawn re-pays the full
   context load (~10-15k tokens of project docs + prompt). Batch file-disjoint SMALL items (task/spike,
   low/medium priority) up to ~3 per sub-session — one context load, several items, one merge; grouped
   failures must reopen EVERY member. Keep bugs/features/criticals per-item.
6. **Wait on process exit, never pipe EOF (2026-07-06, Windows).** A headless child that spawns
   its own children (agents, MCP servers) leaks inherited pipe write-handles; `communicate()` then blocks
   until the grandchildren exit — the fleet "idles waiting for other agents" and misclassifies finished
   runs as timeouts. Feed stdin + drain stdout/stderr on daemon threads and block only in `p.wait()`.
7. **Don't let the close-gate over-tighten into a lockout (2026-07-07).** The mirror hazard of
   gate #close: stacking anti-lazy-close layers (adversarial LLM reviewer on every terminal transition +
   an N-reject "route to human" cap) eventually rejects LEGIT, evidence-backed closes and then PERMANENTLY
   locks them — an agent literally cannot close its own real work ("you should be able to close your own
   tasks"). Recalibrate: the LLM reviewer VERIFIES the evidence and DEFAULTS TO APPROVE once the
   deterministic gates already passed (resolution + a concrete verification token); at the reject cap a
   `done` close AUTO-APPROVES with an `auditFlag` (auditable + reversible) instead of a permanent block,
   while DISPOSALS (wontfix/canceled/duplicate) keep the human route (an unreviewed disposal is the exact
   lazy-DROP class the gate exists for). Principle: gate on EVIDENCE, not on an LLM's subjective
   re-litigation, and make over-rejection auditable + reversible — never a permanent lockout.

## Field learnings (2026-07-14 overnight fleet wave)

- **Check every bus-post response**: a length-limited bulletin (500 chars) SILENTLY rejects long
  posts — two coordinator orders bounced unnoticed until the response was checked. Long content
  goes in item comments; the bus carries one-line pointers.
- **Resource windows need a claim/ACK handshake**: a queue-empty check is NOT restart-safe (a
  backend restart killed a job announced 29s earlier that hadn't reached the queue yet). Post
  intent, wait for ACK or ~60s of silence from anyone who announced resource work in the last
  5 min, then act.
- **Lease-required list for shared files**: bus discipline does not prevent two actors' edits to
  the same lock/bench file landing in each other's commits — enumerate the shared files that
  REQUIRE a lease and enforce the habit in every repo the fleet touches, not just the primary one.
- **Liveness = >=2 corroborating signals** (bus/commit recency, item updates, activity endpoint,
  session list) before challenging or taking over — a single probe can land in a legitimate
  trough (model-swap gap read as a dead loop).
