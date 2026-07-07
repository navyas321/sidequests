#!/usr/bin/env python3
"""context-engine — a local, zero-dependency retrieval index for agent memory.

WHAT: a stdlib-only BM25 lexical index over a corpus you point it at — a folder of
markdown/text files and/or a JSONL file of records (e.g. a backlog, a notes store, a
set of past decisions). An agent queries it at task pickup to recall the handful of
most-relevant prior items / decisions / rules instead of re-reading whole files (or,
worse, missing a prior decision and duplicating work).

WHY BM25 (and not a vector DB): at a personal-knowledge corpus size (~hundreds to a
few thousand short docs) a local brute-force lexical index is competitive-to-better
than a hosted vector store on every axis that matters, and it needs NO embeddings,
NO API keys, NO daemon, and NO new spend. It is fully deterministic. Embedding
*generation* (not storage) is the only piece that costs money/GPU, so this ships
without it — and adds an OPTIONAL, CPU-only dense arm (below) for concept matching.

OPTIONAL DENSE/HYBRID (Tier-2): if numpy + scikit-learn are installed, the engine
fuses an LSA arm (TruncatedSVD over its own TF-IDF) with BM25 via Reciprocal Rank
Fusion — pure CPU, no GPU, no model download, so it never contends with anything
else on the box. If those deps are absent it transparently stays BM25-only; set
CONTEXT_ENGINE_HYBRID=0 to force BM25-only even when they are present.

CLI:
    context_engine.py build   [--root DIR] [--jsonl FILE] ...   # (re)build the index
    context_engine.py query "text" [--top N] [--json] [--root DIR] [--jsonl FILE] ...
    context_engine.py status  [--root DIR] [--jsonl FILE] ...   # built? stale? doc counts

The index is DERIVED data (default .context-index.json next to the root); it rebuilds
automatically when any source file changes (mtime_ns + size fingerprint). All IO is
utf-8; the index write is atomic (*.tmp + os.replace).

Tuning constants (K1/B/TITLE_BOOST/LSA_DIMS/RRF_K) below are the values a benchmark on
a real ~1-2k-doc corpus selected; re-tune against your own queryset if your corpus
differs a lot (short identifier-heavy docs vs long prose behave differently).
"""
import argparse
import json
import math
import os
import re
import sys
import datetime as _dt

try:
    import numpy as _np
    from sklearn.feature_extraction.text import TfidfVectorizer as _Tfidf
    from sklearn.decomposition import TruncatedSVD as _SVD
    from sklearn.preprocessing import normalize as _l2norm
    _HAS_LSA = True
except Exception:
    _HAS_LSA = False

# ── BM25 + tokenizer config (benchmark-tuned; see module docstring) ────────────
INDEX_VERSION = 1
K1 = 1.5             # term-frequency saturation
B = 0.75             # length normalisation
TITLE_BOOST = 2      # title tokens count 2x in tf (short queries tend to hit the title)
MAX_DOC_CHARS = 60000
DEFAULT_TOP = 8
LSA_DIMS = 300       # TruncatedSVD components for the optional dense arm
HYBRID_RRF_K = 30    # Reciprocal Rank Fusion constant (tuned lower than the classic 60 for small corpora)
TEXT_EXTS = (".md", ".markdown", ".txt", ".rst", ".text")

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_CAMEL_RE = re.compile(r"([a-z0-9])([A-Z])")   # split camelCase (fetchSearchIds -> fetch search ids) before lowercasing
_STOP = frozenset((
    "the a an and or of to in for on is are was were be been being it its this that "
    "these those with as at by from into over under after before we you i he she they "
    "them his her our your not no do does did done can could should would will "
    "id eg ie etc via per vs "
).split())


def tokenize(text):
    text = _CAMEL_RE.sub(r"\1 \2", text or "")
    return [t for t in _TOKEN_RE.findall(text.lower())
            if len(t) >= 2 and t not in _STOP]


# ── corpus extraction ─────────────────────────────────────────────────────────

def _text_files(root):
    """Every text/markdown file under `root`, deterministic order. Skips dotdirs and
    the index file itself."""
    out = []
    if not root or not os.path.isdir(root):
        return out
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        for name in sorted(filenames):
            if name.lower().endswith(TEXT_EXTS):
                out.append(os.path.join(dirpath, name))
    return out


def _read(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()[:MAX_DOC_CHARS]
    except Exception:
        return ""


def _first_heading(text, fallback):
    for line in (text or "").splitlines():
        s = line.strip().lstrip("#").strip()
        if s:
            return s[:160]
    return fallback


def _jsonl_records(path, id_field, title_field, text_fields):
    """Yield (id, title, text) from a .jsonl (one JSON object per line) or a .json list."""
    recs = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            head = f.read()
    except Exception:
        return recs
    objs = []
    stripped = head.lstrip()
    if stripped.startswith("["):                       # a JSON array
        try:
            data = json.loads(head)
            objs = data if isinstance(data, list) else []
        except Exception:
            objs = []
    elif stripped.startswith("{") and '"items"' in head[:200]:
        try:
            data = json.loads(head)
            objs = data.get("items", []) if isinstance(data, dict) else []
        except Exception:
            objs = []
    else:                                              # JSONL: one object per line
        for line in head.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                o = json.loads(line)
                if isinstance(o, dict):
                    objs.append(o)
            except Exception:
                pass
    for i, o in enumerate(objs):
        if not isinstance(o, dict):
            continue
        rid = str(o.get(id_field) or ("rec-%d" % i))
        title = str(o.get(title_field) or rid)
        parts = []
        for fld in text_fields:
            v = o.get(fld)
            if isinstance(v, list):
                for e in v:
                    if isinstance(e, dict):
                        parts.append(" ".join(str(x) for x in e.values() if isinstance(x, str)))
                    else:
                        parts.append(str(e))
            elif v is not None:
                parts.append(str(v))
        recs.append((rid, title, " ".join(parts)[:MAX_DOC_CHARS]))
    return recs


# ── index build ────────────────────────────────────────────────────────────────

def _sources(root, jsonl):
    return ([jsonl] if jsonl else []) + _text_files(root)


def _fingerprint(root, jsonl):
    fp = {}
    for p in _sources(root, jsonl):
        try:
            st = os.stat(p)
            fp[os.path.abspath(p)] = [st.st_mtime_ns, st.st_size]
        except OSError:
            pass
    return fp


def _index_path(root, jsonl, explicit):
    if explicit:
        return explicit
    base = root if root and os.path.isdir(root) else (os.path.dirname(os.path.abspath(jsonl)) if jsonl else ".")
    return os.path.join(base, ".context-index.json")


def build(root=".", jsonl=None, index_file=None, id_field="id",
          title_field="title", text_fields=("detail", "resolution", "comments", "body", "text")):
    docs, doclens, postings = [], [], {}

    def _add(doc_id, kind, title, ref, text):
        title_toks = tokenize(title)
        body_toks = tokenize(text)
        tf = {}
        for t in title_toks:
            tf[t] = tf.get(t, 0) + TITLE_BOOST
        for t in body_toks:
            tf[t] = tf.get(t, 0) + 1
        i = len(docs)
        docs.append({"id": doc_id, "kind": kind, "title": (title or doc_id)[:160], "ref": ref})
        doclens.append(len(title_toks) + len(body_toks))
        for t, n in tf.items():
            postings.setdefault(t, []).append([i, n])

    if jsonl:
        for rid, title, text in _jsonl_records(jsonl, id_field, title_field, list(text_fields)):
            _add(rid, "record", title, os.path.abspath(jsonl) + "#" + rid, text)
    for p in _text_files(root):
        text = _read(p)
        rel = os.path.relpath(p, root if os.path.isdir(root) else ".")
        _add(rel, "doc", _first_heading(text, os.path.basename(p)), os.path.abspath(p), text)

    n = len(docs)
    idx = {
        "v": INDEX_VERSION,
        "builtAt": _dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "fingerprint": _fingerprint(root, jsonl),
        "avgdl": (sum(doclens) / n) if n else 0.0,
        "docs": docs, "doclens": doclens, "postings": postings,
    }
    path = _index_path(root, jsonl, index_file)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(idx, f, ensure_ascii=False)
    os.replace(tmp, path)
    return idx


def _load(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            idx = json.load(f)
        if isinstance(idx, dict) and idx.get("v") == INDEX_VERSION:
            return idx
    except Exception:
        pass
    return None


def _get_index(root, jsonl, index_file, **build_kw):
    path = _index_path(root, jsonl, index_file)
    idx = _load(path)
    if idx is None or idx.get("fingerprint") != _fingerprint(root, jsonl):
        idx = build(root=root, jsonl=jsonl, index_file=path, **build_kw)
    return idx


# ── optional dense/hybrid arm (LSA + RRF) ──────────────────────────────────────

def _hybrid_on():
    return _HAS_LSA and os.environ.get("CONTEXT_ENGINE_HYBRID", "1") != "0"


def _identity(x):
    return x


def _corpus_tokens(idx, root, jsonl):
    """Per-doc token lists in the index's doc order — same tokenizer/vocab as BM25.
    Re-reads sources; fine for a CLI one-shot (an in-process server would cache)."""
    by = {}
    if jsonl:
        for rid, title, text in _jsonl_records(jsonl, "id", "title",
                                               ["detail", "resolution", "comments", "body", "text"]):
            by[rid] = title + " " + text
    out = []
    for d in idx["docs"]:
        if d["kind"] == "record":
            out.append(tokenize(by.get(d["id"], d.get("title") or "")))
        else:
            ref = d.get("ref") or ""
            out.append(tokenize((d.get("title") or "") + " " + _read(ref)))
    return out


def _dense_rank(idx, root, jsonl, q, topn=25):
    toks = _corpus_tokens(idx, root, jsonl)
    vec = _Tfidf(analyzer=_identity, lowercase=False)
    X = vec.fit_transform(toks)
    dims = min(LSA_DIMS, X.shape[1] - 1, X.shape[0] - 1)
    if dims < 2:
        return []
    svd = _SVD(n_components=dims, random_state=0)
    D = _l2norm(svd.fit_transform(X))
    qv = _l2norm(svd.transform(vec.transform([tokenize(q)])))
    sims = D @ qv[0]
    return [int(i) for i in _np.argsort(-sims)[:topn]]


def _rrf(bm_idx, dn_idx, k=HYBRID_RRF_K, topn=25):
    s = {}
    for pos, i in enumerate(bm_idx, 1):
        s[i] = s.get(i, 0.0) + 1.0 / (k + pos)
    for pos, i in enumerate(dn_idx, 1):
        s[i] = s.get(i, 0.0) + 1.0 / (k + pos)
    return sorted(s.items(), key=lambda kv: -kv[1])[:topn]


# ── query ───────────────────────────────────────────────────────────────────────

def _snippet(idx, doc, terms, root, jsonl, width=220):
    text = ""
    if doc["kind"] == "record" and jsonl:
        for rid, title, body in _jsonl_records(jsonl, "id", "title",
                                               ["detail", "resolution", "comments", "body", "text"]):
            if rid == doc["id"]:
                text = title + " " + body
                break
    else:
        text = _read(doc.get("ref") or "")
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return ""
    low = text.lower()
    pos = -1
    for t in terms:
        p = low.find(t)
        if p >= 0 and (pos < 0 or p < pos):
            pos = p
    if pos < 0:
        pos = 0
    start = max(0, pos - 60)
    out = text[start:start + width]
    return ("..." if start > 0 else "") + out + ("..." if start + width < len(text) else "")


def search(q, top=DEFAULT_TOP, root=".", jsonl=None, index_file=None, **build_kw):
    q = (q or "").strip()
    if len(q) < 2:
        return {"q": q, "results": [], "error": "query too short (min 2 chars)"}
    idx = _get_index(root, jsonl, index_file, **build_kw)
    terms = []
    for t in tokenize(q):
        if t not in terms:
            terms.append(t)
    docs, doclens, postings = idx["docs"], idx["doclens"], idx["postings"]
    n = len(docs)
    avgdl = idx["avgdl"] or 1.0
    scores = {}
    for t in terms:
        plist = postings.get(t)
        if not plist:
            continue
        df = len(plist)
        idf = math.log(1.0 + (n - df + 0.5) / (df + 0.5))
        for i, tf in plist:
            denom = tf + K1 * (1.0 - B + B * (doclens[i] / avgdl))
            scores[i] = scores.get(i, 0.0) + idf * (tf * (K1 + 1.0)) / denom
    try:
        top = max(1, min(50, int(top)))
    except (TypeError, ValueError):
        top = DEFAULT_TOP
    bm_ranked = [i for i, _ in sorted(scores.items(), key=lambda kv: (-kv[1], docs[kv[0]]["id"]))]
    mode = "bm25"
    if terms and _hybrid_on():
        try:
            dn = _dense_rank(idx, root, jsonl, q, topn=50)
        except Exception:
            dn = []
        if dn:
            ranked = _rrf(bm_ranked[:50], dn, k=HYBRID_RRF_K, topn=top)
            mode = "hybrid"
        else:
            ranked = [(i, scores[i]) for i in bm_ranked[:top]]
    else:
        ranked = [(i, scores[i]) for i in bm_ranked[:top]]
    results = []
    for i, sc in ranked:
        d = docs[i]
        results.append({"score": round(sc, 3), "id": d["id"], "kind": d["kind"],
                        "title": d["title"], "ref": d["ref"],
                        "snippet": _snippet(idx, d, terms, root, jsonl)})
    return {"q": q, "mode": mode, "results": results, "totalDocs": n,
            "builtAt": idx.get("builtAt", "")}


def status(root=".", jsonl=None, index_file=None):
    path = _index_path(root, jsonl, index_file)
    idx = _load(path)
    st = {"indexFile": path, "indexed": idx is not None,
          "hybrid": _hybrid_on(), "hybridDeps": _HAS_LSA,
          "stale": idx is None or idx.get("fingerprint") != _fingerprint(root, jsonl)}
    if idx:
        st["builtAt"] = idx.get("builtAt", "")
        st["totalDocs"] = len(idx.get("docs", []))
        st["records"] = sum(1 for d in idx["docs"] if d.get("kind") == "record")
        st["docs"] = sum(1 for d in idx["docs"] if d.get("kind") == "doc")
    return st


# ── CLI ──────────────────────────────────────────────────────────────────────────

def _main(argv):
    ap = argparse.ArgumentParser(prog="context_engine.py", description=__doc__.strip().splitlines()[0])
    ap.add_argument("cmd", choices=["build", "query", "status"])
    ap.add_argument("text", nargs="*", help="query text (for the query command)")
    ap.add_argument("--root", default=".", help="folder of text/markdown files to index (default: .)")
    ap.add_argument("--jsonl", default=None, help="a .jsonl / .json records file to index as well")
    ap.add_argument("--index-file", default=None, help="where to store the index (default: .context-index.json)")
    ap.add_argument("--id-field", default="id")
    ap.add_argument("--title-field", default="title")
    ap.add_argument("--text-fields", default="detail,resolution,comments,body,text")
    ap.add_argument("--top", type=int, default=DEFAULT_TOP)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    build_kw = dict(id_field=args.id_field, title_field=args.title_field,
                    text_fields=tuple(f for f in args.text_fields.split(",") if f))

    if args.cmd == "build":
        idx = build(root=args.root, jsonl=args.jsonl, index_file=args.index_file, **build_kw)
        print("built %s — %d docs (%d records + %d files)" % (
            _index_path(args.root, args.jsonl, args.index_file), len(idx["docs"]),
            sum(1 for d in idx["docs"] if d["kind"] == "record"),
            sum(1 for d in idx["docs"] if d["kind"] == "doc")))
        return 0
    if args.cmd == "status":
        print(json.dumps(status(args.root, args.jsonl, args.index_file), indent=1, ensure_ascii=False))
        return 0
    # query
    q = " ".join(args.text).strip()
    out = search(q, top=args.top, root=args.root, jsonl=args.jsonl,
                 index_file=args.index_file, **build_kw)
    if args.json:
        print(json.dumps(out, indent=1, ensure_ascii=False))
        return 0
    if out.get("error"):
        print("context-engine: " + out["error"])
        return 1
    if not out["results"]:
        print("context-engine: no hits for %r (%d docs indexed)" % (q, out.get("totalDocs", 0)))
        return 0
    print("context-engine: top %d of %d docs for %r (%s)" % (
        len(out["results"]), out["totalDocs"], q, out.get("mode", "bm25")))
    for r in out["results"]:
        print("  %6.3f  [%s] %s — %s" % (r["score"], r["kind"], r["id"], r["title"]))
        if r["snippet"]:
            print("          %s" % r["snippet"][:200])
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
