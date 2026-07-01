---
name: memory-compaction
description: >-
  Keep an agent's MEMORY lean and its CONTEXT compaction-resilient. Two flows:
  (1) compact the persistent memory store — a MEMORY.md index + one-fact-per-file
  memories — by merging duplicates, pruning stale/derivable facts, splitting
  bloated files, and fixing index<->file drift; (2) manage live context-window
  compaction deliberately (what to make durable so it survives, when to /compact
  at a task boundary vs. waiting for the auto-trigger, /clear, /context). Use when
  you hear: "compact memory", "consolidate my memory", "my memory files are
  bloated / too long", "prune MEMORY.md", "clean up memory", "the index is stale",
  "context is filling up", "compact before the limit", "make this survive
  compaction", "what should go in CLAUDE.md so it isn't lost", or "audit my memory".
allowed-tools: Bash, Read, Write, Edit, Glob, Grep
argument-hint: "[audit|store|context]"
---

# memory-compaction

Two different things are called "compaction" and this skill handles both, because
they trade off against each other:

- **Store compaction** — shrink the *persistent* memory (the `MEMORY.md` index +
  the per-fact `*.md` files) so it stays a sharp, non-redundant prior. This is
  editorial work on files.
- **Context compaction** — manage the *live conversation window* so the agent
  stays productive as it fills, and so the facts that matter survive the summary.
  This is timing + placement discipline.

The lever that connects them: **durable facts belong where they are re-read and
survive compaction.** Project-root `CLAUDE.md` and the auto-memory store are
re-injected/re-read; freeform conversation is not. So a well-compacted store means
the context summarizer has less to preserve, and less is silently lost.

> **Full architecture** — how Claude Code arbitrates memory/skills/tools/hooks, the
> complete three-layer compaction design + the server-side Compaction API
> (`compact-2026-01-12`, `pause_after_compaction`), rehydration asymmetries, and the
> memory/context slash-command reference — is in **[REFERENCE.md](REFERENCE.md)**.
> Read it for the "why" or a citation; keep this file as the standing runbook.

---

## Mental model (why these mechanics matter)

Keep these load-bearing facts in mind — they decide what is safe to prune and what
must be placed carefully. (Version-gated numbers move; treat them as current-as-of,
not contractual. The *shapes* are stable.)

- **Memory is a resident advisory prior, not retrieval.** `CLAUDE.md` files (cwd →
  repo root, plus `~/.claude/CLAUDE.md` and managed policy) are loaded at session
  start and stay resident; they are context, not enforced config. For a rule that
  must hold 100%, use a **PreToolUse hook**, not memory.
- **Auto-memory is the retrieval-ish part.** `MEMORY.md` is a short **index**,
  always loaded; each line points to a detail file that is pulled **progressively**
  when relevant. So the index costs tokens every turn — keep it to **one tight line
  per memory** — while the files are paid for only on demand.
- **Compaction is three layers:** *microcompaction* (large tool outputs spill to
  disk, a hot tail stays inline, cold results are referenced by path);
  *auto-compaction* near the wall (fires ~83.5% of the window, reserves ~33k tokens
  to write a structured working-state summary, clears old tool outputs first);
  *manual `/compact [focus]`* at a task boundary.
- **Rehydration has asymmetries.** After a compaction, project-root `CLAUDE.md` is
  re-read from disk and the recent files/todos/continuation are re-injected — but
  **nested** `CLAUDE.md` files reload only when you next touch that subtree, and the
  **skill listing does not reload**. If an instruction vanished post-compaction it
  was conversation-only or in a nested file.
- **compaction ≠ checkpoint.** Compaction compresses the conversation; it does not
  touch files on disk. And there is no real off switch (`autoCompactEnabled:false`
  is silently ignored) — you *steer* it, you don't disable it.

---

## Flow 1 — Store compaction (`store` / `audit`)

Run when memory is bloated, the index is stale, or on a periodic hygiene pass.

### Step 1 — Audit (read-only)

Run the bundled auditor against the memory directory. It never writes — it prints a
compaction plan.

```bash
python "${CLAUDE_SKILL_DIR}/scripts/memory_audit.py" "<MEMORY_DIR>"
# MEMORY_DIR defaults to $CLAUDE_MEMORY_DIR, else the current dir.
# add --json for machine-readable output.
```

It flags, per finding:

- **index↔file drift** — index lines pointing at a missing file; files with no
  index line.
- **duplicates / overlap** — memories whose title or description token-overlap
  exceeds a threshold (candidates to merge).
- **bloat** — files past a size budget or holding more than one fact (should be
  split so each file is exactly one fact).
- **malformed frontmatter** — missing `name` / `description` / `metadata.type`.
- **stale dates** — absolute ISO dates far in the past (verify the fact still holds).

If `audit` was requested, stop here and report the plan. If `store`, continue.

### Step 2 — Compact the store

Apply these edits (smallest-blast-radius first). Preserve information; delete only
what is redundant, wrong, or derivable.

1. **Merge duplicates/overlap** into the single best file; update every `[[link]]`
   that pointed at the losers; delete the losers and their index lines.
2. **Prune what shouldn't be memory at all** — anything the repo already records
   (code structure, git history, `CLAUDE.md`, past fixes) or that only mattered to
   one finished conversation. If a "fact" is really a directive about *how to work*,
   keep it as a `feedback`/`project` memory with the **why**; drop pure trivia.
3. **Split bloated files** so each holds exactly one fact; give each its own tight
   index line.
4. **Refresh stale facts** — verify against the live repo/tools; correct or delete;
   convert relative dates to absolute.
5. **Tighten the index** — one line per memory: `- [Title](file.md) — hook`. The
   hook is what makes recall fire; make it specific. Remove orphan lines.
6. **Fix links** — every `[[name]]` should resolve to an existing memory (a dangling
   link is a TODO to write that memory, not an error — leave intentional ones).

### Step 3 — Verify

Re-run the auditor; confirm the flagged findings are resolved (or consciously kept).
Report a one-line before/after: file count, index lines, bytes.

---

## Flow 2 — Context compaction (`context`)

Run when the live window is filling, before a long task, or when the user asks how
to keep something from being lost.

### Make it durable BEFORE you compact

The summary is lossy. Move anything that must survive out of the conversation and
into a re-read surface **first**:

- Durable facts (architecture, conventions, safety rules, "always/never" rules) →
  project-root `CLAUDE.md` (survives intact, re-read from disk).
- Cross-session working state (goal, next step, blockers) → the auto-memory store or
  `docs/STATUS.md` (see the `session-context` skill).
- A **`## Compact Instructions`** section in `CLAUDE.md` is the documented way to
  steer *what the summary keeps* — list the invariants and the current objective.

### Compact deliberately

- Prefer `/compact` at a **real task boundary (~60% full)** over waiting for the
  ~83.5% auto-trigger — the summary is cleaner at a stopping point.
- Steer it: `/compact focus on the API changes, drop the test refactoring`.
- `/clear` between **unrelated** tasks (a fresh window beats a summarized one).
- `/context` to see what is actually eating tokens before deciding.
- Push research into **subagents** — they keep their own window and return only a
  summary, so exploration never crowds the main thread.
- Remember `/rewind` restores prior context (and files); it is not the same as a
  checkpoint of on-disk code.

### Memory & context commands (quick reference)

- `/context` — see what is eating tokens (diagnose first).
- `/compact [focus]` — summarize now, with optional steering.
- `/clear` — fresh window between unrelated tasks (the most underused command).
- `/rewind` — undo edits / restore prior context (even from before a `/clear`).
- `/resume`, `/branch` — resume a thread; `/branch` forks at a clean point so the
  original never has to compact.
- `/memory` — open/browse memory files; `/init` — scaffold a project `CLAUDE.md`.

(Full built-in + custom-command reference is in [REFERENCE.md](REFERENCE.md) §3.)

Report the concrete actions taken (or the exact commands for the user to run).

---

## Principles / defaults

- **The index is always-on; the files are pay-per-use.** Optimize the index for
  tokens (one line), the files for completeness.
- **One fact per file.** It makes merges, prunes, and recall precise.
- **Prune aggressively, lose nothing.** Redundant/derivable/stale → gone; anything
  unique and still-true → kept and placed where it survives.
- **Durability = placement.** If it must not be lost, it goes in a re-read surface
  (`CLAUDE.md` / memory), never left in the conversation.
- **Steer, don't fight, auto-compaction.** You cannot disable it; you can make its
  job easy by keeping durable facts out of the conversation.

## Safety / idempotency

- `audit` is **read-only**. `store` edits memory files — it is safe to re-run
  (converges), but back up or commit the memory dir first if it is precious.
- Never invent memories to "fill in" the index; the index mirrors the files.
- Agent-agnostic and cross-platform: the auditor is pure Python stdlib (no deps),
  and the guidance applies to any Claude Code project.
