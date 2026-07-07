---
name: context-engine
description: >-
  Give an agent local, zero-spend recall over its own history — a stdlib BM25
  index (plus an optional CPU-only LSA/hybrid arm) over a folder of markdown/notes
  and/or a JSONL backlog, so a fresh session surfaces the most-relevant prior
  decisions, rules, and duplicates instead of re-reading everything or missing
  them. Use when you hear: "add memory/recall to my agent", "search my backlog /
  notes / past decisions", "find related prior work", "local RAG without a vector
  DB / API key", "context engine", "recall at task pickup", "did we already
  decide/do this", or "de-dupe against existing items". No embeddings, no daemon,
  no new spend.
allowed-tools: Bash, Read, Write
argument-hint: "[build|query|status] <query text>"
---

# context-engine skill

Stand up a **local retrieval index** an agent queries to recall relevant prior
work — backlog items, notes, past decisions, rules — before it starts a task. It is
the antidote to two failure modes of long-running / multi-session agents:

1. **Amnesia** — a fresh session re-solves or re-litigates something already decided.
2. **Duplication** — it files/builds a thing that already exists.

The engine is **stdlib-only BM25** (deterministic lexical ranking), with an
**optional CPU-only dense/hybrid arm** (LSA + Reciprocal Rank Fusion) that switches
on automatically if `numpy` + `scikit-learn` are installed. No embeddings API, no
vector database, no GPU, no daemon, no new spend. At personal-knowledge corpus sizes
(hundreds to a few thousand short docs) this is competitive-to-better than a hosted
vector store while costing nothing.

The bundled script `${CLAUDE_SKILL_DIR}/scripts/context_engine.py` runs standalone —
through this skill, or straight from the command line.

---

## When to reach for this

- Building a backlog watcher, autodev loop, or any multi-session agent that must
  "remember" across runs.
- The user asks for search/recall over notes, a backlog, journals, or decisions.
- You want local RAG **without** standing up a vector DB or paying for embeddings.
- Before creating a ticket / writing code: check whether it already exists (dedup).

Not for: web-scale corpora, or when you genuinely need semantic search over millions
of long documents — then a real vector store earns its keep.

---

## Flow 1 — Build the index

Point it at a folder of text/markdown files, and/or a JSONL (or JSON-array) records
file. The index is derived data written next to the source (`.context-index.json`);
it **auto-rebuilds** whenever a source file changes, so there is nothing to babysit.

```bash
# a folder of notes/docs
python "${CLAUDE_SKILL_DIR}/scripts/context_engine.py" build --root ./notes

# a JSONL/JSON backlog too (one record per line, or a {"items":[...]} / [...] file)
python "${CLAUDE_SKILL_DIR}/scripts/context_engine.py" build \
    --root ./docs --jsonl ./backlog.jsonl \
    --id-field id --title-field title \
    --text-fields detail,resolution,comments
```

You rarely need to build explicitly — `query` and `status` build (and refresh) on
demand.

## Flow 2 — Query (the main event)

Run this **at task pickup, before implementing**. Feed it the task title plus a
keyword or two:

```bash
python "${CLAUDE_SKILL_DIR}/scripts/context_engine.py" query \
    "add dark mode toggle" --root ./docs --jsonl ./backlog.jsonl --top 5
```

Read the hits:
- A `[record]`/`[doc]` hit is prior/related work — open it before writing code.
- A **high-scoring hit that IS your exact task** usually means DUPLICATE or
  already-done. Verify before building.
- `--json` emits `{q, mode, results:[{score,id,title,ref,snippet}], totalDocs}` for
  programmatic use (e.g. stamping a "context recall" note onto the task).

`mode` is `bm25` or `hybrid` depending on whether the dense arm is active.

## Flow 3 — Status

```bash
python "${CLAUDE_SKILL_DIR}/scripts/context_engine.py" status --root ./docs --jsonl ./backlog.jsonl
```

Shows whether the index is built, stale, how many docs/records it holds, and whether
the hybrid arm is available.

---

## Make recall un-skippable (recommended)

An agent that *can* query but often forgets to is only half a solution. The durable
pattern (proven in the life-in-tabs hub) is to **enforce recall server-side at the
moment a task moves to in-progress**: when an item is picked up, run the query, attach
the top hits to the response, AND stamp them as a comment on the item. The agent then
receives related prior art with zero action required — and the recall is visible on
the board for humans too. Fail-soft: if the engine is disabled or errors, never block
the pickup.

If you expose a settings toggle for the engine, treat it as **user intent** — never
flip it from inside an agent.

---

## Tuning (only if your corpus is unusual)

The constants in `context_engine.py` (`K1=1.5`, `B=0.75`, `TITLE_BOOST=2`,
`LSA_DIMS=300`, `HYBRID_RRF_K=30`) were chosen by benchmarking on a real ~1-2k-doc,
identifier-heavy corpus. **Tune against your own queryset, not by intuition** — build
a small set of (query → relevant-doc-ids) judgments, measure Recall@K / MRR, and keep
only changes that improve a metric while regressing none. On that corpus, a BM25+
delta and a x3 title boost were measured and *dropped* because they hurt recall.

**Measured on the field corpus (45 queries / 185 judgments, life-in-tabs BL-1104→BL-1195):**
adding the Tier-2 hybrid arm lifted overall **Recall@5 0.447 → 0.492**, Hit@5 0.711 → 0.800,
MRR 0.665 → 0.686, and **concept-following Recall@5 by ~32% (0.320 → 0.410)** — all while
**preserving keyword MRR (~0.88)**. That guardrail is the point: the dense arm only earns its
place if it lifts concept recall *without* regressing keyword precision.

Enable/disable the dense arm without code changes via `CONTEXT_ENGINE_HYBRID=0`
(force BM25-only) — useful if `numpy`/`scikit-learn` are installed but you want pure
determinism or minimal startup cost.

---

## Requirements

- **Python 3.8+** — the core (BM25) needs only the standard library.
- Optional dense/hybrid arm: `pip install -r ${CLAUDE_SKILL_DIR}/scripts/requirements.txt`
  (`numpy`, `scikit-learn`). Absent → the engine stays BM25-only, transparently.
