---
name: fable-fleet-orchestration
description: >-
  Run a multi-session agent FLEET where a top-tier coordinator session (fable/opus) orchestrates
  peer worker sessions (opus/sonnet/haiku) that the USER spins up — every tier a real, user-visible
  session in the user's app that they can watch, steer, and message, NOT hidden subagents. The
  orchestrator sizes the fleet (headcount + model classes), writes per-tier instruction files and
  paste-in kickoff prompts, arbitrates via a coordination bus + shared backlog, reviews closes with
  executed evidence, and keeps everyone non-idle with self-armed monitors + direct session nudges.
  Use when a project is too big for one session, when work splits into judgment/build/grind tiers,
  when the user says "spin up agents for this" / "orchestrate opus and sonnet sessions" / "how many
  agents do I need", or when a single-session build keeps stalling on serialized long tasks.
  Proven shape: the 2026-07-14 hearth-forge overnight wave (3+1 sessions, ~20 items, one release).
---

# Fable fleet orchestration — user-visible session fleets

One coordinator session + N worker sessions, all spun up BY THE USER so each is visible and
steerable from their app/phone. The coordinator (highest-capability model) owns judgment:
architecture, arbitration, strict review, specs-down, fleet liveness. Workers own execution.
The user stays in the loop by construction — they see every tier's transcript live.

## Why sessions, not subagents

- **Visibility/steering**: the user can open any tier, read it working, and inject course
  corrections mid-wave (screenshots, priority flips) without going through the coordinator.
- **Persistence**: sessions survive across turns and hold their own context/monitors; subagents
  are one-shot and invisible.
- Subagents still have a place INSIDE a tier: the coordinator fans out research/read-only work to
  background subagents while peers build (keeps coordinator context lean).

## Headcount planning (a coordinator duty — do this FIRST and at every phase boundary)

Tell the user exactly what to start: how many sessions, what model class each, and the kickoff
prompt to paste into each. Sizing heuristics:

- **Tier-fit**: judgment/review/architecture -> top tier (1, the coordinator). Core build +
  validation -> strong tier (opus-class). Grind (downloads, benches, docs, UI polish) ->
  mid tier (sonnet-class). Pure-mechanical sweeps -> small tier (haiku-class).
- **Parallelizability caps headcount**: if work serializes on one resource (a single GPU, one
  deploy target), useful builder count is ~2 (one on-resource, one off-resource); extra sessions
  add coordination cost, not throughput. File-disjoint backlogs justify more.
- **Verification isolation**: give adversarial verification its OWN session when it must not share
  context/assumptions with the builder (it will find what the builder can't see).
- **Coordination overhead grows with N**: each actor adds bus traffic, lease contention, and
  liveness tracking. 3-5 total is the sweet spot; beyond that, split the project instead.
- **Revise live**: an idling tier = merge lanes or hand it queued work; a backed-up queue = ask the
  user for one more session (name the class and the kickoff prompt).

## The substrate (all of it required)

1. **Per-tier instruction files** in the repo: `agents/SHARED.md` (cold-start protocol, coordination
   rules, ground truth, safety rails, verification bar) + one file per tier (duties, owns/does-NOT,
   token discipline). Each session reads exactly SHARED + its own file.
2. **A coordination bus**: append-only bulletin + actor heartbeats (see the agent-coordination-gates
   skill for a reference impl). Hard rules: announce pickups/handoffs/reviews/resource-state changes;
   posts are short pointers (check for length-limit rejections — a bounced post is silent data loss);
   durable detail lives in backlog comments/repo artifacts.
3. **A shared backlog with lifecycle gates**: every wave is an item; pickup=owner, pause=progress
   note, close=resolution + how-verified. The coordinator reviews closes — never rubber-stamps.
4. **File leases** for shared files (lock files, bench docs) — bus posts do not replace leases.
5. **Anti-idle stack** (see anti-idle-anti-stall skill + below): self-armed bus monitors before any
   park, direct session-to-session nudges as the escalation, an alert-only staleness watchdog.

## Coordinator duties per wave

- **Kickoff**: size the fleet (above), write/refresh tier files, post the lineup + paste-in prompts.
- **Specs down, never code down**: a delegation spec = goal, constraints, exit criterion,
  verification command, files-may-touch, files-must-NOT-touch. One page max. Mark untested command
  strings as hypotheses — never hand down an untested "fix".
- **Arbitrate**: resource windows (claim/ACK handshake for disruptive actions — a queue-empty check
  alone is NOT restart-safe), stand-down scopes, takeover decisions (liveness = bus/commit/item
  recency + activity API, never process existence; corroborate >=2 signals before challenging).
- **Review gate**: every phase close gets coordinator review with an INDEPENDENT executed probe of
  the artifact (decode the video, view the image, listen to the audio, hash the file). Dims, bytes,
  and exit codes are never evidence. Verdicts: PASS / PASS-with-findings / FAIL with ranked findings.
- **Anti-idle**: split-order partial dependencies (the non-blocked 70% starts now); re-sequence the
  moment a tier reports empty-queue; direct-nudge parked sessions that miss clearances.
- **Wrap**: wave-closed post -> gated cleanup of fleet-added artifacts (inventoried, hash-gated
  deletes) -> release per the releasing skill -> retro (wins/failures -> memory + skills).

## Failure modes this model has already hit (and the fixes to bake in)

| Failure | Fix |
|---|---|
| Worker honors a superseded hold (stale world-model) | stale-hold rule: re-read the bus before honoring any hold >10 min old; timestamp-compare watchers (ring buffers defeat length-compare) |
| Silent parks (no wake mechanism) | no parking without an armed monitor + parked post naming the wake condition |
| Item-reaper sweeps held items despite bus heartbeats | reapers count ITEM updates - touch the item every ~90 min during long holds |
| Restart kills a peer's just-announced job | claim/ACK window handshake, not just queue-depth checks |
| Watchdog counts its own restart as a second crash | boot-grace window + timeout-vs-down classification + never-restart-while-queued |
| Two tiers edit a shared lock file | lease-required list for shared files |
| Coordinator gates work behind ceremonial milestones | gate on real dependencies only |
| Length-limited bus silently drops orders | check every post response; long content -> item comments |

## Kickoff prompt template (per worker session)

"You are the <TIER> tier for <project>, session N of wave W. Read <repo>/agents/SHARED.md (run its
COLD START first - pull, plan sections, bus bulletin, your open items), then agents/<TIER>.md. Your
queue per PLAN section <n>: <items>. Coordination rules are binding: post cold start on the bus
before acting; end every turn with a completed handoff or a parked post + armed monitor."
