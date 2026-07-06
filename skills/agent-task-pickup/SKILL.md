---
name: agent-task-pickup
description: >-
  Rank a shared backlog so an autonomous agent (or a fleet of them) picks up the RIGHT task next —
  weighting severity, provenance ("did a human ask for this?"), time-criticality, unblocking, quick-wins
  and age, while GATING work an unattended agent shouldn't self-assign (security, severe/irreversible,
  architecture, underspecified, or file-conflicting) to a human/senior lane. Use when building a backlog
  watcher, an autodev/autopilot loop, a multi-agent task queue, or any "what should I work on next?"
  picker — or when your current picker buries critical work, lets agents grab risky items, or races on
  duplicate pickups. Project-agnostic; pure stdlib; ships a reference implementation (pickup.py) + tests.
---

# Agent task-pickup: WSJF-Lite band-first scorer + Autonomy Gate

A picker that feeds a shared backlog to autonomous agents has TWO jobs the naive `sort by priority`
conflates. Keep them separate:

- **ORDER** — *which eligible task ranks first.* A numeric score, but **severity is a hard BAND, not a
  weighted term.**
- **ELIGIBILITY** — *which tasks an autonomous agent must NOT self-assign.* A gate that **routes** (never
  silently drops) security / severe / architecture / underspecified / file-conflicting work to a
  human/senior lane.

`pickup.py` is a drop-in reference (`rank(items, actor, leased_paths) -> {items, gated}`). Adapt the
field names / weights / gate rules to your system — the **structure and the lessons below are the
reusable part.**

## The model

```
ORDER  key = ( severity_band ,  -wsjf_score ,  created_ASC ,  id_ASC )
                 ^hard primary    ^intra-band only              ^determinism

wsjf_score = ( 0.34·severity + 0.24·time_criticality + 0.20·provenance
             + 0.12·enablement + aging ) / job_size
```

- **severity_band** `critical<high<medium<low` is a **hard primary key** — a critical *always* outranks a
  high, regardless of score. The score only reorders items **within** one band.
- **time_criticality** = value decay if delayed: from `type` (`security`>`bug`>`task`>`feature`>…) plus a
  small **security-keyword** bump (most security work is filed as `type=bug`, not `type=security`).
- **provenance** = "came from a human?" via an **exact source allowlist**, not `startswith`.
- **enablement** = unblocking value: a scoped child of an epic is exactly the pre-decomposed work an
  autodev *should* execute.
- **aging** = a bounded anti-starvation nudge so the oldest item in a band leads its peers.
- **job_size** = the WSJF denominator (`effort` if known, else inferred from `type` + #children) — the
  "small wins first" engine: a small high-value fix outranks a big build **of the same band**.
- **Autonomy Gate** (watcher/autodev only; interactive/human bypasses): route to `gated[]` with a reason
  when `type∈{epic,spike,security}`, `priority=critical`, a security keyword hits, the item is
  underspecified, or it names a file a live actor holds.

## Lessons baked in (each is a real bug an adversarial review caught)

1. **A `/size` divisor inverts severity — band FIRST, score second.** If final rank is
   `score = numerator/size`, then because `size` (1..~12) is uncorrelated with priority, a small `high`
   (or an aged `low`) routinely outranks a fresh `critical` — the exact work you meant to surface gets
   re-buried. Reasoning about "numerator headroom" is meaningless *after* dividing. Fix: make severity a
   **hard lexicographic band**; let the WSJF score (with its divisor) only order items *inside* a band.

2. **Provenance via `startswith('user')` is trivially spoofable.** An agent that writes its own items can
   stamp `source='userspace-tidy'` / `'user_agent'` and jump the queue. Match an **exact allowlist**
   (`^user(-request|-directive|-live-review|-\d{4}-\d{2}-\d{2})?$`); everything else falls to the
   machine/quick tier. Better still: derive provenance from a **server-stamped** origin the authoring
   agent can't set.

3. **No final tie-break ⇒ non-deterministic across parallel actors ⇒ duplicate pickups.** With coarse
   scores and a stable sort, ties resolve by input/iteration order, so two agents on the same snapshot
   pick different #1s and race. End the sort key with the **item id** — stable, unique, present on every
   item — so all actors agree.

4. **Gate = eligibility, run it BEFORE ranking — and ROUTE, don't drop.** The highest-scored item can be
   the one an unattended agent should *least* touch (a critical security fix). Gating as a score *penalty*
   still hands it over; gate as a *pre-rank filter*. And put gated items in a visible `gated[]` lane with
   a reason — silently dropping them means severe work vanishes instead of reaching a human.

5. **Fix eligibility with a picker-local predicate, not by editing global status sets.** Severe items are
   often "parked" in a status your closed-set treats as done (`accepted`/`triage`), so they never reach
   the picker at all. Add a picker-only `review_eligible = {open,triage,accepted}` instead of reclassing
   those statuses everywhere else.

6. **Every term degrades to a NEUTRAL value on missing data — never a penalty, never a crash.** Real
   backlogs are sparse (here: `effort` and `source` were unset on ~100% of the open-eligible items, and
   the two `critical` items had `source=null` AND `created=null`). Unset `created` ⇒ aging 0 (not
   "infinitely old"); unset `source` ⇒ neutral 0.5 (not 0); `size` floored at 1 (no div-by-zero).

7. **Anti-starvation is bounded and severity-subordinate.** Aging must guarantee old actionable items
   eventually surface *within their band* but never let an aged `low` cross a fresh `critical`
   (band-first already enforces this; keep the aging cap below any band gap in the intra-band score).

8. **Treat self-reported `effort`/`type` as low-trust.** They're the highest-leverage levers (the size
   divisor); band-first already stops them from crossing tiers, but only honor `effort` set by a trusted
   actor and watch for `type` churn (relabel `feature`→`bug` doubles urgency and halves size).

9. **Gate on structure + human intent, not severity heuristics — or you fight your own autonomy goal.**
   A gate built from "is it critical? does the title say `security`? is the detail short?" over-gates (a
   UI card mentioning "permission" gets held; the queue starves) AND, if your principle is *the agent
   owns the queue*, actively contradicts it by deferring judgement calls to a human. The durable,
   low-false-positive rails are **structural + intent-based**: (a) a human explicitly PARKED the item (a
   status like `accepted`/`blocked`), (b) the item isn't directly actionable yet (an `epic` needs
   decomposition first), (c) file-lease coordination (another live agent holds a file it touches). In the
   origin deployment the owner removed every severity/keyword/underspecified rail and kept only these
   three — pickable work jumped ~3× with no loss of safety, because the genuinely-dangerous items were
   already human-parked. Make the gate's rails a **config knob**, not a fixed policy: how much an
   autonomous agent may self-assign is a per-deployment decision, not a property of the scorer.
10. **Provenance weight must follow VERIFIABILITY, not label prestige — and reopens are a first-class
   signal.** A 2026-07 research spike on the origin board found the trust order inverted: the only
   SERVER-STAMPED human channel (phone quick-capture, stamped by the API at write time) scored 0.6
   while honor-system `user-*` labels (any agent writing the store can claim them) scored 1.0 — the
   spoofable channel outranked the provable one. Weight sources by how hard they are to fake, not by
   how human they sound. Same spike: a human REOPENING a closed item (terminal→open with fresh
   evidence) is one of the strongest priority signals in triage research, yet most scorers treat the
   reopened item as just another open row that orders by FIFO luck. Server-stamp `reopenedAt` +
   `reopenCount` at the transition and give a bounded, decaying boost. Corollary of the tie-cluster
   finding: when your factors stop discriminating (top-N all identical score → pure created-ASC), the
   scorer has silently become FIFO — add the discriminating signal rather than tuning weights blind.
11. **An OPEN item that still carries an owner is mid-handoff, not free work — gate it.** (2026-07
   incident, origin board:) a session paused a conversation-directive item back to `open` but kept
   `owner` (a reserve/handoff marker). The autonomous picker treated open-status as free, picked it,
   confidently mis-disposed it with a fabricated rationale — an independent review even APPROVED the
   plausible-sounding cancel — then re-picked it after the close: pure token churn on work another
   session already held, and a wrong disposition on the board. Add an **owner rail** to the gate
   (coordination-class, like file-leases — not a human-judgment gate): `open` + non-empty `owner` ⇒
   gated, with pause semantics "clear owner = released to anyone; keep owner = reserved". Two
   companion write-path guards close the loop: agents may never flip a TERMINAL item straight to
   in-progress (reopen explicitly first, server-stamped), and disposal states (canceled/wontfix/
   duplicate) **fail CLOSED** when the independent close-reviewer is unavailable — fail-open is only
   safe for `done`, because an unreviewed disposal is precisely the lazy-close class the gate exists
   to stop.

## Use it

```python
from pickup import rank
out = rank(backlog_items, actor="watcher",
           leased_paths={"serve_life.py": "other-agent"})   # files a live actor holds
next_task = out["items"][0]        # each has ["score"] + ["why"] (per-factor breakdown)
needs_human = out["gated"]         # each has ["gatedReason"]
# interactive/human sessions: rank(items, actor="interactive") bypasses the gate.
```

Run `python test_pickup.py` for the regression + gaming-resistance suite (ordering, spoof-cap, aging
cap, all gate triggers, determinism, null-degradation).

*Origin: extracted from the life-in-tabs multi-agent backlog picker (`backlog_next_items`). Designed via
a research → 3-proposal → adversarial-critic workflow; the 8 lessons above are the critics' high-severity
findings, fixed.*
