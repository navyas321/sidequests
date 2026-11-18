---
name: backlog-hygiene
description: >-
  Spring-clean a shared backlog that agents and people both write to, so its states tell the truth
  again: close only what is verifiably finished, move "paused" items to open or done, re-judge
  "risk accepted" items that are really dismissals, recover orphaned in-progress items, re-verify
  stale blockers, merge true duplicates, and split unresolved follow-ups out before anything
  closes, with every terminal close independently reviewed. Use when the user says "do some
  backlog cleanup / spring cleaning / grooming", "why are there N items in paused", "close what's
  done", "most of these risk-accepted items aren't risks", "merge the duplicates", "the board
  says nobody is working but items are in progress", or before a status report. Ships a read-only
  triage_report.py that proposes the pass.
allowed-tools: Bash, Read, Grep, Glob
argument-hint: "[full|paused|risk|orphans|blockers|dups] <backlog file or API>"
---

# backlog-hygiene

A backlog shared by autonomous agents drifts in predictable ways: items sit "in progress" under a
session that died weeks ago, "paused" becomes a parking lot, "risk accepted" fills with things
nobody wanted to say no to, blockers that cleared long ago still block, and finished work stays
open while unfinished work gets closed. A hygiene pass fixes the states **with evidence** and then
removes the cause so the pile does not come back.

## 0. Ground rules

- **Verify against the live system, not the item's text.** "Done" means you ran something that
  shows it is done (a command, an API call, a file on disk, a log line) and you quote it in the
  resolution. An item that only *sounds* finished stays open.
- **Every terminal close goes through an independent reviewer** in a different context — never
  the session doing the cleanup, never a fork of it. If the tracker has a server-side reviewer,
  make sure your calls are classified as an agent (send a non-browser User-Agent such as
  `cleanup-agent/1.0`; PowerShell's default UA starts with `Mozilla` and can be booked as the
  human, skipping review) and check each closed item carries the reviewer's stamp. See
  `agent-coordination-gates` and `cross-agent-review`.
- **Agents do not dispose of a person's ask on their own judgment.** Closing a captured user
  request as wontfix / canceled / out of scope needs the user's say-so: either the cleanup request
  explicitly covers it ("move the non-risks to won't fix") or it goes on a "for your call" list.
  Closing as **done** with evidence needs no permission.
- **Split before you close.** If part of an item is finished and part is not, file the remainder
  as its own linked item first, then close the parent. A follow-up mentioned only in a resolution
  is lost.
- **One tracking item for the wave.** The cleanup itself gets an item (and a run record if the
  board mirrors live work), closed with a why + how-verified summary of every change.
- **Leave what is not yours.** Items owned by a live session, user-owned items, other projects'
  items, and live deadline work are reported, not touched.

## 1. Inventory and propose

```bash
python ${CLAUDE_SKILL_DIR}/scripts/triage_report.py backlog.json            # markdown proposal
python ${CLAUDE_SKILL_DIR}/scripts/triage_report.py backlog.json --json     # for a script
```

Read-only. It counts items by status and flags: **orphan** (in progress, no activity for
`--orphan-hours`), **paused-pile** (paused too long, no owner, or no resume condition),
**risk-ok** (risk-accepted with no risk named), **stale-block** (cites a blocker, untouched for
`--block-days`), **no-evidence** (closed without a why + how-verified resolution), and **dup?**
(near-identical open titles). Field names are flags (`--status-field`, `--owner-field`,
`--time-fields`). If the backlog lives behind an API, dump it to JSON first. Read each item's
comments before acting: handoffs, partial progress and earlier decisions live there.

## 2. Work each class

| class | check | outcome |
|---|---|---|
| **orphan** in progress | is the owner alive? Use 2+ signals (session list, recent commits, heartbeat, item activity) — one probe can land in a quiet spell | dead: back to **open** with a handoff comment (what is done, what is next); alive: leave it |
| **paused** | run the item's acceptance check now | finished: **done** with evidence; work remains: **open**, owner cleared; truly waiting on something: keep, with owner + a written resume condition |
| **risk accepted** | does it name a real risk the user knowingly carries (security exposure, data-loss window, cost, compliance)? | real: keep; a dismissal ("not worth it", "won't build"): **wontfix** with the real reason (user's say-so); still worth doing: **open** |
| **stale blocker** | re-run whatever proves the blocker: access, a release, an upstream fix, a person's answer | cleared: unblock and say so in a dated comment; still blocked: refresh the comment with today's evidence |
| **closed without evidence** | re-verify | holds: add the evidence; does not: reopen |
| **duplicate?** | is it REALLY the same work? Diff the details, not the titles | same: move any unique scope to the canonical item, then close as duplicate naming it; different: retitle so they stop looking alike |
| **open, finished** | the acceptance check | **done** with evidence |
| **open, stale facts** | re-check numbers, versions, paths it quotes | add a dated comment with the current facts |

## 3. Fix the cause

A pile comes back unless the thing that builds it changes. Common causes and fixes:

- **Paused piles** come from sessions that pause on exit and never return. Make a pause require a
  live owner and a resume condition, or auto-release (owner cleared, back to open) after N days.
- **Orphans** come from sessions that die mid-item. Add a reaper that returns in-progress items
  with a dead owner to open, with a comment.
- **Risk-accepted piles** come from agents being allowed to set that state. Make it human-only.
- **Silent closes** come from gates a client can slip past. Classify callers properly and stamp
  reviews server-side.
- **Stale blockers** come from nobody re-checking. Have the periodic report flag them.

Run `triage_report.py` on a schedule you already have (exit code 1 = findings) so drift shows up
as a short list, not a spring-cleaning day.

## 4. Report

Counts by status before and after; each change with its reason and evidence; what was split out
(new ids); the "for your call" list; and what was deliberately left alone and why. Then close the
wave's tracking item with that summary, through the reviewer.

## Files

- `scripts/triage_report.py` — read-only proposal (markdown or `--json`; exit 1 when anything is
  flagged).
- `scripts/test_triage_report.py` — `python test_triage_report.py`.

*Origin: repeated cleanup passes on a personal multi-agent backlog (2026-07 to 2026-11): a
paused pile of nine items with no live owners, a "risk OK" filter that was mostly dismissals, and
blockers that had cleared months before anyone re-checked them.*
