---
name: two-agent-build-test-loop
description: >-
  An autonomous SDLC where a BUILD agent (compiles + self-verifies + ships a test-ready
  artifact) hands off to a TEST agent on REAL target hardware (runs a command-level scorecard,
  writes a report, opens a PR) — the handoff IS the loop. Use when you want two Claude agents to
  drive dev-and-verify without a human in the middle, when a build can only be validated on a
  device the build machine isn't (handheld, console, phone, GPU box), when you need a repeatable
  build->artifact->test->report->fix cycle, or when "the test agent got the wrong / stale build".
  Captures the branch/CI/release conventions and the hard-won merge/stale-alpha/device-gated
  traps that make it actually work. Project-agnostic; needs git + a CI that builds per-branch.
allowed-tools: Read, Write, Edit, Bash, Grep, Glob
argument-hint: "[build-agent|test-agent|setup]"
---

# Two-agent build↔test loop

Some software can only be *proven* on hardware the build machine isn't — a handheld, a console, a
phone, a specific GPU. Splitting the work across **two Claude agents** turns that constraint into
an autonomous loop:

- **Build agent** — writes code, compiles, **self-verifies**, and ships a *test-ready artifact*
  (installer / AppImage / binary) plus exact test instructions onto a feature branch.
- **Test agent** — runs on the **real target hardware**, executes a **command-level scorecard**,
  writes a concise report, and opens a PR back.

The build agent acts on the report (fix → rebuild → re-ship, or merge on PASS) and the cycle
repeats. Neither agent needs a human in the loop; the **handoff over git is the loop**. This is
Claude-prompting-Claude: the artifact + instructions are the build agent's prompt to the test
agent; the report PR is the reply.

## When to use

- A build's real behavior can only be verified on a device the build host can't run (display/GPU/
  OS-specific: a Steam Deck-class handheld, a game console, a phone, an HDR monitor, a specific
  driver stack).
- You want repeatable, unattended dev-and-verify: one self-verified test-ready PR per build cycle,
  each carrying its own pass/fail scorecard.
- Your current setup keeps handing the tester the **wrong or stale** build, or verdicts drift
  because there's no fixed evidence bar.

## Roles & handoff (the shape)

| | Build agent | Test agent |
|---|---|---|
| **Runs on** | the build machine (may be a container/VM) | the **real target hardware** |
| **Owns** | code, compile, CI, the feature branch, the artifact + instructions | running the artifact, capturing evidence, the report + PR |
| **Never** | claims a device-only result it can't observe | writes production code / pushes to the default branch |
| **Output** | `test<N>-<slug>` branch: artifact + `instructions.md` | `report.md` on a `diagnostic/<task>-report` branch + a PR |

Each agent gets a **persona file** ("who you are") plus a shared **workflow SOP** ("the step-by-step
+ templates"). A one-word keyword (e.g. `builddev` / `clienttest`) boots each role into its startup
checklist. Keep instructions **exact and self-contained** — the test agent runs them literally and
will not improvise; a worker handed incomplete context produces rework that costs more than the
handoff saved.

## Rule 1 — self-verify BEFORE the handoff (never hand over a red build)

The test agent's time (and real hardware) is expensive; never spend it on a build that was already
broken. Before shipping an artifact the build agent MUST, on the build machine:

1. **Compile clean** — the build command exits 0 with **zero errors**.
2. **Headless load-verify** — run the artifact's non-interactive self-check (a `--selftest` /
   `--version` / headless-init path that proves it *initialises* without a display). Exit 0 +
   an explicit `PASS` line.

Only then does it become a test-ready artifact. The owner/tester should never see a red X that a
30-second local check would have caught.

## Rule 2 — command-level scorecards, not "make it better"

Every test cycle ships a **numbered, command-level scorecard** — exact commands + expected output —
so the verdict is objective and the test agent (or a future you) can't fudge it. Four standing
tiers:

- **Build** — compiles clean, artifact present.
- **Smoke** — the new behavior works on the happy path (exact run + the log line that proves it).
- **Regression** — named prior features still work.
- **Negative** — degrades cleanly when the precondition is missing (host offline, setting off).

Prefer **log-grep assertions** over eyeballing: run the artifact for a bounded `timeout`, grep the
log for the expected signal, quote the 2–3 lines that answer the question. Tests are the oracle — a
model's self-judgment degrades as context fills, but a green build / a command scorecard stays
accurate. The report surfaces *signal*, not raw logs (a TL;DR table → per-tier results →
recommendation, with ≤10–20-line excerpts).

## Rule 3 — the branch convention is load-bearing

Name the branch that carries a test artifact **`test<N>-<slug>`** (e.g. `test7-streamsegue-fix`),
with `N` incrementing monotonically. This is not cosmetic:

- The artifact and its `testing/test<N>-<slug>/` directory **live only on the feature branch** —
  the default branch does not have them.
- The test agent finds the newest `test<N>-*` branch and checks it out. If you use `fix/…` or
  `feat/…`, it has no reliable way to know which branch holds the artifact and may land on the
  default branch where the test dir doesn't exist.

So: when a fix is ready for hardware, (re)name the branch `test<N>-<slug>`, commit the artifact +
`instructions.md` there, and have the instructions' checkout command reference that exact branch.
The report comes back on `diagnostic/test<N>-<slug>-report`, targeting the feature branch.

## Rule 4 — CI tier model (branch decides the build tier)

Let branch prefix pick the release tier automatically, so agents never hand-manage builds:

- **`test**` branches → `alpha`** builds (per-branch throwaway artifacts for a test cycle).
- **default branch → `beta`** builds (integration).
- **`stable` is explicit** (a `workflow_dispatch` / `release/**` action) — cut at milestones only.

Publish artifacts the test agent can actually download **only** from the tiers it needs (e.g. only
`test**` and the default branch publish to Releases; other prefixes build as CI artifacts but don't
publish).

**The smart-build trap (this bites constantly):** a CI "did anything change?" gate typically sets
`should_build=false` when the **HEAD commit touches only docs** (`.md`/`.txt`), and then **skips the
artifact build entirely**. CI evaluates the HEAD commit, so:

```
git commit -m "fix: real code change"      # touches .cpp/.qml/.ts — good
git commit -m "docs: add test instructions" # .md only  <-- now HEAD
git push                                     # CI sees HEAD = docs-only -> SKIPS the build
```

…and the test agent downloads the **previous** artifact. **The last commit before a release-bearing
push MUST touch a code file.** Order commits so the code change is HEAD (or bundle the instructions
into the code commit). `workflow_dispatch` alone does not save you — it still runs through the same
gate.

## Rule 5 — release cadence (bump per shipped wave)

Keep the version moving so it never lags the work:

- **Bump MINOR** when a feature wave merges to the default branch; **PATCH** for a fix-only wave.
  Bump the single version source (e.g. `version.txt`) in the same push as (or right after) the merge.
- **A direct push may not cut a release.** On many setups betas publish **only on PR-merge commits
  that touch code** — a direct push (even code-touching) doesn't release; it cuts at the next PR
  merge, or via an explicit `workflow_dispatch`. Know which trigger actually releases in your CI
  and don't assume a push did.
- **Stable stays explicit** — tag it at milestones (after a verification wave clears); don't let it
  lag many minors behind beta.

## Hard-won gotchas (each cost real cycles — do not skip)

### (a) The stale-alpha trap — re-verify merged fixes on BETA, not the per-branch alpha

A fix that lands on a **later** branch never reaches the **original** branch's alpha artifact — that
alpha was built from the older tip. If you re-run the original test cycle, the test agent re-downloads
the **stale alpha** and the fix looks absent. **After merging a fix, verify it on the freshly built
BETA (default-branch) artifact**, not the original `test<N>` alpha. Treat each `test<N>` alpha as a
snapshot of *that branch at build time*, nothing later.

### (b) Keep-both merge-fusion — brace-balance + headless-load-verify after batch merges

Resolving conflicts by "keep both" (common when two feature branches both add to the same UI/config
file) can silently **fuse two adjacent elements** — e.g. two QML/JSON/code blocks merged into one with
a **duplicate `id:` / duplicate key** or a **missing closing `}`**. That's a hard parse error. A smoke
test that never opens the fused screen **won't catch it** — the app starts fine, the broken screen just
fails when navigated to. So after any batch/keep-both merge: **brace-/bracket-balance-check the touched
files AND headless-load-verify the specific screen** (open it in the self-test path), don't just boot
the app.

### (c) Device-gated verification ledger — track code-complete ≠ runtime-proven separately

Some fixes are code-complete but their proof needs hardware you don't currently have (a specific
device, a display state, a GPU). **Do not mark those "done."** Keep a separate ledger of
*device-gated* items — code merged, runtime verification pending — distinct from fully-verified work.
An off-hardware agent may run launcher-only / self-test / static tiers, but must mark any GPU / stream /
device-mode tier **N/A (not on target hardware)** and never claim a device-only PASS off-device. Close
a device-gated item only when the real-hardware evidence actually lands.

## Terminal-state rule (both agents)

When moving any work item to a terminal state (done / merged / wontfix), record **why** it got there
**and how it was verified** — the exact command + output, test result, or observed run. "Should work"
or "code was written" is not verification. If you couldn't verify (device-gated), ship it as
blocked/deferred with that reason, not as done.

## Setup checklist (bootstrapping the loop in a repo)

1. **Two persona files** + one **workflow SOP** with the instruction/report **templates**; a
   keyword per role that runs a fixed startup checklist (fetch → read the report queue → pick the
   next branch/item).
2. **Branch conventions:** `feat/`|`fix/`|`docs/`|`chore/` for work; **`test<N>-<slug>`** for a test
   cycle; `diagnostic/<task>-report` for reports.
3. **CI tiers** wired to branch prefix (`test**`→alpha, default→beta, stable explicit) with the
   docs-only smart-build gate — and the "HEAD must touch code" rule written where agents will read it.
4. **A shared queue** (a checklist file / backlog) the test agent works **top-down**, one cycle per
   session, ticking each row in the same commit as its report; a `✗` row stays at the front until the
   build agent re-pushes a fix on the same `test<N>` branch.
5. **A device-gated ledger** for code-complete-but-hardware-pending items.
6. **A hands-off alert path** so an agent can reach the human on a true blocker (e.g. a CI job that
   opens+closes a transient @-mention issue) without a standing open channel.

## Notes & limits

- Self-contained and project-agnostic: needs `git` and a CI that builds per branch; `gh` optional
  (PR/alert steps degrade to "commit only").
- The examples name a compile+AppImage / handheld pairing, but the pattern fits any
  build-machine-can't-run-the-target situation (mobile app + phone, firmware + board, GPU kernel +
  specific card).
- Right-size the model per role: routine build/log/PR work is fine on a fast, economical tier;
  reserve a stronger tier for multi-file architecture decisions, cross-layer debugging, and reviewing
  a stack of merge resolutions. If a task *feels* like it needs the stronger model, flag it before
  digging in.
