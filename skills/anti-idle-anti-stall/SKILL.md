---
name: anti-idle-anti-stall
description: >-
  Keep an autonomous agent fleet DRAINING and never idling — two deterministic guards. (1) A Stop
  hook that BLOCKS a session from ending its turn while the backlog still has non-terminal work AND
  no genuinely-live drainer is making progress, re-injecting the next concrete pickup instead of
  letting it park on a ScheduleWakeup. (2) A stall-reaper that proactively force-releases the
  claims/leases of a shield-holding actor whose heartbeat went stale with no commits (the corpse
  that wedges the drain), and kills its process. Use when building an autodev/backlog-watcher or
  /loop "finish everything" system and it (a) ends turns / sleeps while open work remains and nobody
  is shipping, or (b) has one stalled agent holding shields that block every other lane. Windows +
  a coord.py-style lease bus assumed; pure stdlib; both guards are lightweight + fail-open.
---

# Anti-idle + anti-stall playbook

Two failure modes plague an autonomous fleet that shares one backlog:

- **Idle:** a session ends its turn (often parked on a bare wakeup) while OPEN items sit untouched
  and NO other agent is actually shipping. The user watches dead wall-clock.
- **Stall:** one actor holds file/backlog/resource shields, its heartbeat goes stale, but its
  claims stay HELD — so every other lane that needs those shields is blocked behind a corpse
  (real case: a "rebench" actor held 9 shields for ~26 min producing ~67 bytes).

Discipline rules alone don't hold. Make BOTH deterministic.

## Guard 1 — the anti-idle Stop hook

Register a `Stop` hook (Claude Code `.claude/settings.json`, **additive** — never clobber existing
hooks). Contract: stdin JSON in, stdout JSON out. ALLOW the stop = print nothing, exit 0. BLOCK =
print `{"decision":"block","reason":"<next instruction>"}`, exit 0 (the host feeds `reason` back to
the model, so the turn continues).

**BLOCK iff BOTH hold:**
- (a) there ARE non-terminal backlog items — status NOT in
  `{done, wontfix, duplicate, canceled/cancelled, snoozed, accepted, paused, closed, ...}`; AND
- (b) NO genuinely-live drainer OTHER than this session — no repo commit in the last ~10 min
  (`git log -1 --pretty=%ct`), AND no other coord actor with a fresh heartbeat (< ~12 min) holding
  claims, AND no other agent reported `working` by the fleet's activity endpoint.

Else ALLOW — a **drained board** or a **live fleet already draining** is a legitimate stop.
(Heartbeating an EMPTY board is *also* idling; the hook must not nag when the work is done.)

**Non-negotiable design constraints:**
- LIGHTWEIGHT — a couple of short, time-boxed API calls + one `git log`. **No full-context reload**
  (that is what drains tokens during a "pause").
- Fail-OPEN on ANY error/ambiguity — a broken anti-idle hook must NEVER wedge a session in an
  un-endable turn.
- Self-limiting — if the payload carries `stop_hook_active` (you already blocked once this turn),
  ALLOW. Never loop the model forever.
- Opt-out env var (e.g. `LIT_NO_ANTIIDLE=1`) + a repo/API override env for a test rig.

Reference impl: `life-in-tabs/scripts/anti-idle-guard.py`.

## Guard 2 — the stall-reaper

A lease bus (coord.py-style) auto-expires a stale actor's holds — but only on the *next* load/mutate.
Nothing forces that sweep when the fleet is quiet. Add a reaper on a ~15-min schedule (+ on-demand,
`--dry-run`).

**Detect a STALL — ALL of:** the actor holds shields (`claimed[]` and/or file leases and/or resource
leases); its heartbeat age > ~12 min (past the interactive TTL); AND no commit is attributable to it
in the window. Attribution is conservative — a commit message can't be pinned to an actor, so reap
only when **NO repo commit landed at all** in the stall window (the corpse signature: long-stale +
zero commits). A recent commit -> DEFER the reap that cycle (someone is productive). EXEMPT the
long-lived scheduled watcher (its legit TTL is hours; a separate hung-run/leaked-lock watchdog owns
it).

**Reclaim — idempotent + fail-soft:** force-release via `COORD_ACTOR=<actor> coord.py release-all`
(makes the eventual prune happen NOW); match the actor's OS process by `COORD_ACTOR=<actor>` in its
command line (Windows: PowerShell CIM `Win32_Process.CommandLine`) and kill its tree; announce the
reclaim on the bus so live lanes see the freed shields. Read the RAW held shields BEFORE the bus's
in-memory prune would zero them. Write a health record; exit 0 always (a reaper must never fail its
own scheduled task).

Reference impl: `life-in-tabs/scripts/stall_reaper.py` (sibling to `autodev_watchdog.py`).

## Wiring checklist

1. Drop both scripts in `scripts/`. Reuse the lease bus's canonical TTL/age/freshness helpers.
2. Register the Stop hook in `.claude/settings.json` **additively**.
3. Schedule the reaper every ~15 min (Task Scheduler / cron), health-file heartbeat + lock like any
   other watcher.
4. Verify: hook ALLOWs on a drained board / live fleet, BLOCKs with the injected pickup when work
   remains + no drainer; reaper `--dry-run` reports candidates and never touches the exempt watcher.
5. Record the learnings in memory so the *behavior* rule survives even if a hook is disabled.

## Field learnings (2026-07-14 hearth-forge wave — interactive session fleets)

Beyond the two deterministic guards, interactive multi-SESSION fleets need three more patterns
(proven overnight, see the fable-fleet-orchestration skill for the full model):

- **Self-armed bus monitor before ANY park**: a parked session cannot see the bus; arm a
  persistent Monitor on the coordination feed (compare TIMESTAMPS, not list length — a capped
  ring buffer never changes length; that exact bug stalled a worker on a superseded hold) with a
  silence alarm (~15 min) and API-down alerts, so silence is never mistaken for success.
- **Direct session nudge as the escalation**: when a parked/stale session misses its clearance,
  a session-manager message (user-visible) revives it in minutes; bus posts alone cannot wake it.
- **Reaper counts ITEM updates, not bus heartbeats**: actors heartbeating the bus still lost 8
  held items to the item-reaper in one night. During long holds: bus heartbeat every 15 min for
  peers AND a one-line item comment every ~90 min for the reaper. Also: split-order partial
  dependencies — "waiting on a partial dependency is not a hold"; the unblocked 70% starts now.

## Field learnings (2026-07-21 vibemis PR-integration wave — orchestrator + background subagents)

The wave stalled ~20 min mid-pipeline and the user had to nudge ("why did you just stop working").
RCA: a background subagent STOPPED with the message "CI is still building; my background watcher
will resume me" — but a stopped subagent has NO live watcher: the moment it emits a completion
notification, whatever `gh run watch` it thought it owned is gone with its process. The parent
orchestrator took the claim at face value and parked on the (never-coming) second notification.
Two rules, both now standing:

- **A stopped subagent's "I'll be resumed by X" is false by default.** When any lane's completion
  notification carries a self-parking claim instead of results, the parent must IMMEDIATELY verify
  the watched condition itself (one cheap poll: `gh run list`, release list, log tail) and, if the
  condition already holds, SendMessage-resume the lane with the verified facts in the message.
  Verification-plus-nudge cost ~2 tool calls; the passive wait cost 20 min of dead wall-clock.
- **Arm a fallback heartbeat whenever the main loop is notification-parked.** Before ending a turn
  that waits on background lanes, schedule a wakeup (ScheduleWakeup or equivalent) whose prompt
  re-checks every live lane against its watched condition and nudges the stragglers. Cancel/stop
  it when the board drains. A lost notification then costs one heartbeat interval, not a user
  intervention. (This is Guard 1's spirit applied to the ORCHESTRATOR's own wait states — the
  Stop hook can't see that a "live" lane is actually a corpse whose watcher died with it.)
- **Heartbeat cadence: <=10 minutes while lanes are ACTIVELY working** (maintainer directive,
  2026-07-21, after 20-min beats let two stalls sit until the user noticed first). The cost of a
  quiet wakeup is a couple of cheap polls; the cost of a slow beat is dead wall-clock the user
  sees. Reserve 20-30 min beats for genuinely idle waits with no live lanes; never slower than
  the longest step a lane is expected to take.
- **Escalation on repeat stalls: recover + take over, don't re-nudge.** If the SAME lane stalls a
  second time, stop messaging it — recover its on-disk/on-device artifacts (logs, screenshots,
  extracts, backups) and finish its remaining scope directly. A lane that died post-work leaves
  everything needed; both real cases (P2b retest, BL-2243 icon verify) were completed this way in
  minutes from recovered artifacts.
