# sidequests

> An open-source sink of reusable, project-agnostic **agent-ops tooling** and
> **Claude Code skills** — each one born as a *side quest* while building
> something else, then distilled here so it's reusable everywhere.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
![Claude Code plugin](https://img.shields.io/badge/Claude%20Code-plugin-7c5cff)
![skills](https://img.shields.io/badge/skills-25-2ea043)

What started as two one-off migrations (Google Photos → iCloud de-dupe, and
song/source identification from a clip) has grown into a catalog of runbooks
distilled from real problems solved across the author's projects — a personal
hub, autonomous dev fleets, an agentic trading stack, and a gaming rig. The bulk
of it is **agent operations**: how to make a fleet of autonomous Claude agents
pick up the right work, coordinate without collisions, stay alive across usage
limits and app restarts, and never silently stall.

Every tool is packaged as a [Claude Code](https://code.claude.com) **skill** — a
runbook the agent follows, most with bundled stdlib scripts — but the scripts
also run perfectly well on their own from the command line. Use them through
Claude, or just `python` them directly.

---

## Catalog

25 skills, grouped by theme. Each links to its runbook; one line is the gist.

### 🤖 Building agents & multi-agent orchestration

| Skill | What it does |
| --- | --- |
| **[fable-fleet-orchestration](skills/fable-fleet-orchestration/SKILL.md)** | Run a fleet of USER-VISIBLE peer sessions (a top-tier coordinator orchestrating opus/sonnet/haiku workers the user spins up) — headcount planning, tier files + kickoff prompts, bus/backlog substrate, review gates, anti-idle. The working model behind a ~20-item overnight release. |
| **[agentic-best-practices](skills/agentic-best-practices/SKILL.md)** | A working checklist of Anthropic's current guidance for building with Claude — prompting, agent-vs-workflow design, skills/subagents/hooks/CLAUDE.md, context engineering, tool & MCP design, and reliability. |
| **[agent-task-pickup](skills/agent-task-pickup/SKILL.md)** | Rank a shared backlog so an autonomous agent picks the RIGHT next task (severity, provenance, unblocking, quick-wins) while gating risky work to a human lane. Ships `pickup.py` + tests. |
| **[agent-coordination-gates](skills/agent-coordination-gates/SKILL.md)** | Let a fleet of agents share ONE backlog without collisions — enforce the create/pickup/pause/close lifecycle at the data layer, plus a file-lease + bulletin bus. Ships `coord.py` + `gates.py`. |
| **[anti-idle-anti-stall](skills/anti-idle-anti-stall/SKILL.md)** | Two deterministic guards that keep an agent fleet draining and never idling — a Stop hook that blocks parking while work remains, and a stall-reaper that frees a stalled shield-holder's leases. |
| **[two-agent-build-test-loop](skills/two-agent-build-test-loop/SKILL.md)** | An autonomous SDLC where a BUILD agent self-verifies and ships a test-ready artifact, and a TEST agent on REAL target hardware runs a command-level scorecard and opens a report PR — the git handoff is the loop. Captures the branch/CI-tier/release conventions + the stale-alpha, merge-fusion, and device-gated traps. |
| **[local-coding-agent](skills/local-coding-agent/SKILL.md)** | Make a small LOCAL coding model (opencode + Ollama, 4B on ~8 GB) genuinely competent instead of "useless" — model choice on tight RAM, the config that stops it denying its own tools, teaching correct tool use via exact recipes + a global AGENTS.md, killing trap/duplicate tools, two-sided guardrails (one-sided "do NOT commit unless asked" makes it refuse even when asked — "the request IS the approval" + the branch→verify→commit→push→`gh pr create` flow), and cross-session memory a weak model can use (auto-inject recall + a deterministic `/remember` write). The line between a local agent that's a toy and one that's useful. |

### 🩺 Watchers, reliability & durable automation

| Skill | What it does |
| --- | --- |
| **[watcher-reliability](skills/watcher-reliability/SKILL.md)** | Preflight pattern for headless Claude/MCP watchers — verify auth, MCP servers, codec, and repo state up front so scheduled runs fail loud at the start, not silently mid-run. Ships `watcher-preflight.ps1`. |
| **[watcher-cleanup](skills/watcher-cleanup/SKILL.md)** | Scan for and clean dead/orphaned custom watchers — reconcile the prompt-file + scheduled-task + health-record trio so config litter and stale health entries don't accumulate. |
| **[durable-claude-automation](skills/durable-claude-automation/SKILL.md)** | Make scheduled Claude runs and the remote session survive desktop-app restarts/updates/crashes — move the schedule into Windows Task Scheduler (headless `claude -p`) + an app watchdog. |

### 🏃 Dev SDLC (agile-scrum)

| Skill | What it does |
| --- | --- |
| **[feature](skills/feature/SKILL.md)** | Drive a feature end-to-end through a full agile-scrum SDLC — scope & design (plan-mode gate), implement, test & verify (adversarial review), release. |
| **[bugfix](skills/bugfix/SKILL.md)** | Drive a bug to a verified fix via a lightweight scrum loop — reproduce, fix the root cause, add a regression test, verify green, release. |
| **[releasing](skills/releasing/SKILL.md)** | Cut clean releases the right way — continuous-beta / tag-cut-stable: bump beta, generate a changelog from git, and (on request) tag an annotated stable. |
| **[receipts](skills/receipts/SKILL.md)** | Unbiased "show me the receipts" audit — an independent sub-agent checks every instruction from a time window against what actually shipped (git/backlog/code) and files a ticket per miss. |

### 🧠 Context, memory & continuity

| Skill | What it does |
| --- | --- |
| **[session-context](skills/session-context/SKILL.md)** | Keep continuity across sessions — orient a new agent on where a project stands, or checkpoint state so the next session resumes exactly where this one left off. |
| **[memory-compaction](skills/memory-compaction/SKILL.md)** | Keep an agent's memory lean and its context compaction-resilient — compact the `MEMORY.md` index + one-fact files (merge, prune, split, fix drift) and steer live `/compact` so durable facts survive. |
| **[context-engine](skills/context-engine/SKILL.md)** | Local, zero-spend recall for an agent — a stdlib BM25 index (+ optional CPU LSA/hybrid) over notes/backlog so a fresh session finds prior decisions & dupes at pickup. No vector DB or embeddings API. |

### ⏳ Usage limits & cost control

| Skill | What it does |
| --- | --- |
| **[usage-limit-guard](skills/usage-limit-guard/SKILL.md)** | Keep a repo-backed autonomous loop making progress across Claude's 5h/weekly limits and outages — read local token-burn, detect the limit headlessly, and resume from durable repo state instead of `--resume`. |
| **[github-actions-cost-control](skills/github-actions-cost-control/SKILL.md)** | Diagnose and stop GitHub Actions free-tier minute burn — find the biggest burners (paused-project crons, macOS 10× runners, burst-commit CI) and fix them. |

### 🎮 Gaming rig & desktop (Windows)

| Skill | What it does |
| --- | --- |
| **[steam-shortcut](skills/steam-shortcut/SKILL.md)** | Add a non-Steam game (any `.exe`/launcher) to the Steam library by safely editing `shortcuts.vdf` — parses, preserves, backs up, round-trip-verifies. Cross-platform. |
| **[hdr-gaming-setup](skills/hdr-gaming-setup/SKILL.md)** | Set up and PROVE the Windows 11 HDR gaming stack on an OLED + NVIDIA RTX rig — monitor OSD, Windows HDR Calibration (HGIG), RTX HDR + Dynamic Vibrance, and a driver-log engagement test. |
| **[display-off-shortcut](skills/display-off-shortcut/SKILL.md)** | Start-menu shortcut + conflict-free `Ctrl+Alt+<key>` hotkey that turns the monitor off while the PC keeps running (downloads/streaming continue); wake with any mouse move or keypress. |
| **[isolated-streaming-host-mock](skills/isolated-streaming-host-mock/SKILL.md)** | Stand up an ISOLATED mock game-streaming host (Sunshine/Apollo/Vibepollo) next to a real one for testing a client — copied prefix + offset ports + virtual-display + kill-by-port — without disrupting real gaming or the real host. Ships `start-mock.ps1` / `stop-mock.ps1` / `mock.conf`. |

### 🎬 Media & migration (the original side quests)

| Skill | What it does |
| --- | --- |
| **[photo-reconciler](skills/photo-reconciler/SKILL.md)** | Reconcile a Google Photos export against iCloud and upload only what's genuinely missing — no duplicates. Windows + iCloud for Windows. |
| **[source-finder](skills/source-finder/SKILL.md)** | Identify the song/media playing in a video or audio clip and return the source (artist + title + link) — handles live covers and un-catalogued originals that Shazam can't. |

Several skills below have a deeper walkthrough — the rest are fully documented in
their own `SKILL.md`.

---

## Requirements

- **Python 3.10+**
- Each tool has its own `requirements.txt`. `ffmpeg` is bundled via
  `imageio-ffmpeg`, so there's **no system ffmpeg install** to worry about.
- `session-context` only needs `git` (and optionally `gh` for the PR list).
- `source-finder` is cross-platform. `photo-reconciler`'s staging/dehydration
  bits are Windows + "iCloud for Windows"; its hashing core is portable.

---

## Installation

### As a Claude Code plugin (recommended)

```text
/plugin marketplace add navyas321/sidequests
/plugin install sidequests@sidequests
```

Skills load at **session start**, so open a **new Claude Code session** after
installing. Then type `/` and you'll see all the skills in the menu. Install
Python deps once:

```bash
pip install -r ~/.claude/plugins/cache/sidequests/sidequests/*/skills/source-finder/requirements.txt
pip install -r ~/.claude/plugins/cache/sidequests/sidequests/*/skills/photo-reconciler/requirements.txt
```

(`session-context` has no Python deps — it's pure bash + git.)

### Standalone (no Claude)

```bash
git clone https://github.com/navyas321/sidequests
cd sidequests
pip install -r skills/source-finder/requirements.txt
pip install -r skills/photo-reconciler/requirements.txt
```

---

## 🔁 session-context

Keep a running project snapshot so any agent (or human) can pick up exactly
where the last session ended — in any repo, any tech stack.

**With Claude:** just say *"orient yourself"* or *"checkpoint"* and the skill
fires automatically (it triggers on natural phrases).

| Flow | Trigger phrases | Effect |
|------|----------------|--------|
| **orient** | "resume where I left off", "where are we", "orient yourself", "what's next" | Reads `docs/STATUS.md`, `CLAUDE.md`, git log, open PRs — prints current phase + exact next step. **Read-only.** |
| **checkpoint** | "checkpoint", "save session state", "update STATUS", "wrap up" | Writes `docs/STATUS.md` (phase, what this session did, next step, open decisions). Appends one-liner to `docs/SESSION_LOG.md`. |

**Standalone:**

```bash
# Snapshot the repo right now (safe, read-only):
bash skills/session-context/scripts/snapshot.sh

# Pass a different repo path:
bash skills/session-context/scripts/snapshot.sh /path/to/myrepo
```

`snapshot.sh` prints branch, recent log, working-tree status, and open PRs
(degrades gracefully when `gh` is absent). Paste the output into the
`## Snapshot` section of `docs/STATUS.md`.

**`docs/STATUS.md` shape**

```markdown
# Project Status
**Last updated:** YYYY-MM-DD
## Phase / ## This session did / ## Next step / ## Open decisions / ## Key files
## Snapshot (auto)
<snapshot.sh output>
```

---

## 🎵 source-finder

Give it a clip and it identifies what's playing. Acoustic fingerprinting (Shazam)
only matches *original studio recordings*, so this climbs a **fallback ladder**
that also handles live covers and un-catalogued originals — then **verifies**
before answering.

**With Claude:** drop a file and ask *"what's the song in this clip?"* (it
auto-triggers), or run `/source-finder <clip>`.

**Standalone:**

```bash
SF=skills/source-finder/scripts

# 0. read on-screen clues (titles, branding, a chat guessing the song)
python $SF/frames.py clip.mov --n 6 --crop right     # then look at _frames/*.jpg

# 1. acoustic fingerprint (studio originals)
python $SF/extract_audio.py clip.mov -o audio.wav --stereo
python $SF/fingerprint.py audio.wav

# 2. lyrics (works for covers -- it's the words, not the recording)
python $SF/extract_audio.py clip.mov -o eq.wav --eq
python $SF/transcribe.py eq.wav --model large-v2

# 2b. if lyrics are garbled, isolate vocals first
python $SF/separate_vocals.py audio.wav -o vox.wav
python $SF/extract_audio.py vox.wav -o vox16.wav
python $SF/transcribe.py vox16.wav --model large-v2
```

Then web-search the most distinctive lyric lines, cross-reference the on-screen
clues, and verify against the song's known lyrics.

**How the ladder works**

```
frames / on-screen clues  --+
acoustic fingerprint        +-->  lyric transcription  -->  web-search + verify  -->  source
(Shazam, studio only)      --+     (Whisper + EQ/vocal-isolation, handles covers)
```

> **Worked example.** A 32-second phone clip of a TV showing a Twitch stream.
> Shazam returned nothing (on the phone *and* via `fingerprint.py`). The video
> frames showed the streamer's branding and a chat guessing wrong titles.
> `transcribe.py` on the EQ-boosted vocals recovered enough of the lyrics that a
> web search nailed it: a streamer's **own original song** — which is exactly
> why fingerprinting never had a chance, and why lyrics did.

**Output:** `"Title" by Artist`, a link, and one line on *how* it was found
(fingerprint / lyrics+search / on-screen), plus honest caveats (e.g. "this is a
live cover; the original is...").

---

## 📷 photo-reconciler

Upload only the Google Photos items that aren't already in iCloud — no
duplicates. **It uploads to your iCloud account, so it's gated:** always dry-run,
stage a small canary first, and confirm before the bulk copy.

**With Claude:** `/photo-reconciler path/to/export.zip` and it walks the workflow.

**Standalone:**

```bash
RC=skills/photo-reconciler/scripts/reconcile.py
WORK=D:/photoscratch        # a drive with space -- NOT the system drive

# 1. hash your iCloud library (resumable; --dehydrate if disk is tight)
python $RC --work $WORK index-icloud --workers 8

# 2. hash the extracted Google export
python $RC --work $WORK index-google ./extracted-album

# 3. find what's missing (writes unique_images.txt / unique_videos.txt)
python $RC --work $WORK compare

# 4. dry-run, then canary, then the rest (gate on confirmation)
python $RC --work $WORK stage --dry-run --list $WORK/unique_images.txt --list $WORK/unique_videos.txt
python $RC --work $WORK stage --limit 25 --list $WORK/unique_images.txt   # confirm on icloud.com, then drop --limit

# 5. accounting + integrity report
python $RC --work $WORK verify --list $WORK/unique_images.txt --list $WORK/unique_videos.txt
```

**The one trap that matters:** the iCloud library is mostly **HEIC**, and Pillow
can't read HEIC without `pillow-heif`. Without it, every iCloud photo fails to
hash, iCloud looks *empty*, and the tool flags everything as new — re-uploading
your whole album as duplicates. The script registers `pillow-heif` and prints an
iCloud **error rate**; if it's high, stop and fix deps before trusting the result.

> **Real result.** A 10,531-item album — **6,822 already in iCloud** (correctly
> skipped) — **2,848 genuinely-missing** items uploaded — **0 duplicates**, all
> verified on icloud.com.

**Good to know**
- The modern iCloud-for-Windows (v14+) uploads files copied **directly** into
  `...\iCloudPhotos\Photos` — there's no "Uploads" subfolder.
- The filesystem **can't** confirm an upload (with "Download originals" on, an
  uploaded file still looks local). Ground truth is the iCloud app's counter or
  icloud.com.
- Photos whose EXIF survived the export keep their original dates; those that
  lost it get dated "today" and sit at the top of your library.

---

## 🖥️ display-off-shortcut

Turn the **monitor** off on demand while the PC keeps running — downloads, game
streaming, and background jobs all continue. Wake with any mouse move or
keypress. Broadcasts the Windows `SC_MONITORPOWER` "monitor off" message, so
there's no NirCmd or other utility to install.

**With Claude:** *"make a shortcut to turn off my display"* or *"add a hotkey to
blank the screen"*.

**Standalone:**

```powershell
# Install the Start-menu shortcut + a conflict-free Ctrl+Alt+<key> hotkey:
powershell -NoProfile -ExecutionPolicy Bypass -File skills\display-off-shortcut\scripts\install-shortcut.ps1

# Force a specific hotkey, or skip the hotkey entirely:
... install-shortcut.ps1 -Hotkey "Ctrl+Alt+M"
... install-shortcut.ps1 -Hotkey none
```

The installer scans every `.lnk` hotkey in your Start Menu and Desktop (current
+ all users) and picks the first free combo from `Ctrl+Alt+O, M, B, J, L, 0, 9`
— and never uses `Ctrl+Alt+<Arrow>` (Intel reserves those for screen rotation).

> Display-only: it won't sleep/lock the PC. To also lock, chain
> `rundll32.exe user32.dll,LockWorkStation`. A few monitors ignore the software
> power-off (driver/connection dependent) — fall back to `nircmd monitor off`.

---

## 🏃 feature + 🐛 bugfix — agile-scrum SDLC workflow

A pair of skills that run any project through a proper Scrum sprint. Four gated
stages with a **plan-mode approval gate**, **TodoWrite sprint backlog**,
**parallel subagents in git worktrees**, and **adversarial review**.

| Command | When to use |
|---------|-------------|
| `/feature <description>` | New capability — design + multi-task breakdown + adversarial review |
| `/bugfix <description / repro>` | "X is broken" — reproduce-first, fix root cause, regression test |

**The four stages:**

```
[Scope & define] --gate:approved--> [Implement] --gate:builds--> [Test & verify] --gate:green--> [Release]
```

Gates are hard checkpoints — the agent prints a status block and does not
advance until the condition is satisfied. See [`skills/feature/README.md`](skills/feature/README.md)
for the full reference and [`skills/feature/SCRUM.md`](skills/feature/SCRUM.md) for the gate table.

**With Claude:**

```
/sidequests:feature add pagination to the search results page
/sidequests:bugfix clicking submit on the login form does nothing
```

**Requirements:** `git` (required); `gh` optional (PR step degrades gracefully).
Works in any repo, any language.
## ⏳ usage-limit-guard

Make any **repo-backed autonomous loop** (a backlog watcher, a `/loop`, a nightly
headless agent) survive Claude's usage limits, outages, and session death — and
resume cleanly. The core idea: **the repo is the resume state, not the session.**
Commit per work-item, keep a tiny checkpoint + a dated journal, and a brand-new
session resumes by *reading* that state. One kill loses at most the item in flight.

**With Claude:** say *"make this survive usage limits"*, *"resume after the limit
resets"*, or *"how much usage am I burning"* and the skill fires.

**Standalone:**

```bash
ULG=skills/usage-limit-guard/scripts

# how much have I burned locally? (the ONLY programmatic usage signal)
python $ULG/token_burn.py

# in a headless loop: run one bounded item, then classify the outcome
claude -p "<do the next item>" --output-format json --max-turns 30 > run.json; rc=$?
python $ULG/detect_limit.py run.json $rc
#   OK            -> commit the item, advance CHECKPOINT.json, continue
#   LIMIT <time>  -> commit, store the reset time, EXIT (next scheduled run resumes)
#   ERROR <cat>   -> log + back off per category
```

**Two truths it bakes in**
- The only programmatic usage signal is **local transcript token-burn** (sum
  `message.usage` across `~/.claude/projects/**/*.jsonl`). The real claude.ai **5h /
  weekly limit %** is *not* API-exposed — the skill reports the burn proxy and says so.
- On **Windows, `--resume` / `-c` are buggy** (freeze, lost conversations, crash on
  killed sessions). Resume is by reading repo state — never the session.

**Durable-resume artifacts** (committed): commit-per-item + `CHECKPOINT.json`
(`lastRun` / `lastItem` / `nextItem` / `doneThisCycle` / `limitResetsAt`) + a dated
journal. A fresh `claude -p` reads them + `git log` + memory and continues. See the
[`SKILL.md`](skills/usage-limit-guard/SKILL.md) for the full procedure and a
new-repo setup checklist.

---

## 🧠 context-engine

Give an agent local recall over its own history so a fresh session doesn't re-solve a
decided question or file a duplicate. **BM25** lexical ranking (stdlib-only,
deterministic) over a folder of notes and/or a JSONL/JSON backlog, with an **optional
CPU-only** LSA + Reciprocal-Rank-Fusion hybrid arm (`numpy` + `scikit-learn`) that
switches on automatically when present. No embeddings API, no vector DB, no GPU, no
new spend.

**With Claude:** ask *"search my backlog/notes for prior work on X"* or *"did we
already decide this?"* (it auto-triggers), or run `/context-engine query "…"`.

**Standalone:**

```bash
CE=skills/context-engine/scripts/context_engine.py

# index notes and/or a JSONL backlog (auto-rebuilds when sources change)
python $CE build --root ./notes --jsonl ./backlog.jsonl

# recall at task pickup — task title + a keyword or two
python $CE query "add dark mode toggle" --root ./notes --jsonl ./backlog.jsonl --top 5

# built? stale? doc counts? hybrid available?
python $CE status --root ./notes --jsonl ./backlog.jsonl
```

The killer pattern is **un-skippable recall**: enforce the query server-side the
moment a task moves to in-progress and stamp the top hits onto the item — the agent
gets prior art with zero action. `CONTEXT_ENGINE_HYBRID=0` forces BM25-only. Tune the
BM25/LSA constants against your own (query → relevant-ids) judgments if your corpus
differs a lot — not by intuition.

---

## Repo layout

```
sidequests/
+-- .claude-plugin/
|   +-- plugin.json          # this repo is one plugin...
|   +-- marketplace.json     # ...and a marketplace exposing it
+-- skills/
    +-- <skill>/
        +-- SKILL.md          # the runbook (required — the only thing a skill needs)
        +-- README.md         # human-facing overview (some skills)
        +-- scripts/ | *.py   # bundled stdlib reference impl (some skills)
        +-- *.md              # supporting reference (SCRUM.md, PRACTICES.md, ...)
```

Every skill lives under `skills/<name>/`. A `SKILL.md` (with a `description:` in
its frontmatter, or an `H1 — one-line` heading) is all that's required to be
discoverable; many skills also ship a stdlib reference implementation you can run
standalone — e.g. `agent-coordination-gates/coord.py` + `gates.py`,
`agent-task-pickup/pickup.py` (+ tests), `context-engine/scripts/context_engine.py`
(BM25 + optional LSA hybrid), `usage-limit-guard/scripts/` (`token_burn.py`,
`detect_limit.py`), `source-finder/scripts/` (audio/fingerprint/transcribe),
`photo-reconciler/scripts/reconcile.py`, and `watcher-reliability/watcher-preflight.ps1`.

## Updating

```text
# after pushing changes (bump "version" in plugin.json for clean tracking)
/plugin marketplace update sidequests
/plugin update sidequests@sidequests
```

## Add your own sidequest

Drop a new folder under `skills/<your-tool>/` with a `SKILL.md` (and a
`scripts/` dir if it needs code), and it ships with the next plugin update. A
`SKILL.md` needs only a `description:` in its frontmatter to be discoverable;
reference bundled scripts with `${CLAUDE_SKILL_DIR}/scripts/...`.

## License

[MIT](LICENSE) © navyas321
