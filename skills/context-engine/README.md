# context-engine

> Local, zero-spend recall for an agent — a stdlib **BM25** index (plus an optional
> CPU-only LSA/hybrid arm) over your notes and/or a JSONL backlog, so a fresh session
> surfaces the most-relevant prior decisions, rules, and duplicates instead of
> re-reading everything or missing them.

No embeddings API. No vector database. No daemon. No GPU. No new spend.

## Why

Long-running and multi-session agents forget: a fresh session re-solves a decided
question or files a duplicate. A tiny local retrieval index fixes both — and at
personal-knowledge corpus sizes (hundreds to a few thousand short docs), local BM25
is competitive-to-better than a hosted vector store while costing nothing. Embedding
*generation*, not storage, is the only piece that costs money/GPU, so this ships
without it and adds an **optional** CPU-only dense arm for concept matching.

## Quick start

```bash
# index a folder of notes/markdown (and optionally a JSONL/JSON backlog)
python scripts/context_engine.py build --root ./notes --jsonl ./backlog.jsonl

# recall at task pickup — feed the task title + a keyword or two
python scripts/context_engine.py query "add dark mode toggle" \
    --root ./notes --jsonl ./backlog.jsonl --top 5

# is the index built / stale? how many docs? hybrid available?
python scripts/context_engine.py status --root ./notes --jsonl ./backlog.jsonl
```

`query` and `status` build/refresh the index on demand (staleness is tracked by file
mtime + size), so you rarely call `build` yourself. Add `--json` to `query` for
machine-readable output.

## How it works

- **Tier-1 (always on):** BM25 lexical ranking — deterministic, stdlib-only, with a
  title field-boost and a camelCase-splitting tokenizer so identifier queries match.
- **Tier-2 (optional):** an LSA arm (TruncatedSVD over the engine's own TF-IDF) fused
  with BM25 via Reciprocal Rank Fusion — pure CPU (`numpy` + `scikit-learn`), no model
  download, no GPU. Absent deps → BM25-only, transparently. `CONTEXT_ENGINE_HYBRID=0`
  forces BM25-only.

The index is derived data (`.context-index.json`, safe to gitignore). All IO is
UTF-8; the index write is atomic.

## Make recall un-skippable

The durable pattern: enforce recall **server-side at task pickup** — when an item
moves to in-progress, run the query, return the top hits, and stamp them as a comment
on the item so the agent (and humans) get prior art with zero action. Fail-soft:
never block a pickup if the engine is off or errors.

## Tuning

The BM25/LSA constants are benchmark-tuned for a ~1-2k-doc identifier-heavy corpus.
If yours differs a lot, build a small (query → relevant-ids) judgment set, measure
Recall@K / MRR, and keep only changes that improve a metric with none regressed —
don't tune by intuition.

## Requirements

- Python 3.8+ (core needs only the standard library).
- Optional hybrid arm: `pip install -r scripts/requirements.txt`.
