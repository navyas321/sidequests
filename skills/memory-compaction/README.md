# memory-compaction

> Keep an agent's **memory** lean and its **context** compaction-resilient.

A Claude Code [skill](SKILL.md). Two flows:

- **Store compaction** — shrink the persistent memory (`MEMORY.md` index +
  one-fact-per-file `*.md` memories): merge duplicates, prune stale/derivable
  facts, split bloated files, fix index↔file drift, tighten the index.
- **Context compaction** — manage the live conversation window deliberately: move
  durable facts to a re-read surface (`CLAUDE.md` / auto-memory) *before* the
  summary, `/compact [focus]` at a task boundary (~60%) instead of waiting for the
  ~83.5% auto-trigger, `/clear` between unrelated tasks, `/context` to diagnose,
  and push research into subagents.

The connecting idea: **durable facts belong where they are re-read and survive
compaction.** A well-compacted store means the summarizer has less to preserve and
less is silently lost.

Distilled from an architecture deep-dive on how Claude Code arbitrates
memory/skills/tools/hooks and its three-layer compaction design (microcompaction →
auto-compaction → manual `/compact`). The full deep-dive — arbitration internals,
the complete compaction design + server-side Compaction API, rehydration
asymmetries, and the memory/context slash-command reference — lives in
**[REFERENCE.md](REFERENCE.md)** (loaded on demand, like `agentic-best-practices`'
`PRACTICES.md`).

## The auditor

`scripts/memory_audit.py` is a **read-only** report — it prints a compaction plan
and writes nothing. Pure Python 3.8+ stdlib, any OS.

```bash
# audit the auto-memory store (or any MEMORY.md + *.md directory)
python scripts/memory_audit.py /path/to/memory
CLAUDE_MEMORY_DIR=/path/to/memory python scripts/memory_audit.py        # or via env
python scripts/memory_audit.py /path/to/memory --json                  # machine-readable
python scripts/memory_audit.py /path/to/memory --overlap 0.5 --max-chars 1200
```

It flags: **DRIFT** (index↔file mismatch), **DUPLICATE** (high token overlap),
**BLOAT** (oversized files that likely hold >1 fact), **FRONTMATTER** (missing
`name`/`description`/`metadata.type`), and **STALE** (old absolute dates to verify).

No Python dependencies.
