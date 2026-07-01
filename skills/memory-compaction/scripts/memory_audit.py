#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""memory_audit.py -- READ-ONLY audit of an agent memory store for COMPACTION.

Given a memory directory that holds a MEMORY.md index plus one-fact-per-file *.md
memories (the Claude Code auto-memory layout), report what a compaction pass should
merge, prune, split, or fix. It NEVER writes anything -- it prints a plan for the
agent (or a human) to act on.

Findings:
  * DRIFT     -- index line -> missing file, or file with no index line
  * DUPLICATE -- two memories whose title/description token-overlap >= --overlap
  * BLOAT     -- a file larger than --max-chars (likely more than one fact)
  * FRONTMATTER -- missing name / description / metadata.type
  * STALE     -- an absolute ISO date older than --stale-days (verify still true)

Usage:
  python memory_audit.py [MEMORY_DIR] [--json] [--max-chars N]
                         [--overlap F] [--stale-days N]

MEMORY_DIR defaults to $CLAUDE_MEMORY_DIR, else the current directory.
Pure Python 3.8+ standard library -- no dependencies, runs on any OS.
"""
import argparse
import datetime
import json
import os
import re
import sys

INDEX_NAME = "MEMORY.md"
# "- [Title](file.md) - hook"  (also tolerates ./file.md and extra spaces)
_INDEX_RE = re.compile(r"^\s*[-*]\s*\[(?P<title>[^\]]+)\]\((?P<href>[^)]+)\)\s*(?P<hook>.*)$")
_DATE_RE = re.compile(r"\b(20\d{2})-(\d{2})-(\d{2})\b")
_WORD_RE = re.compile(r"[a-z0-9]+")
_STOP = set("the a an and or of to for in on at is are be with your you it this that "
            "as by from use used using when where how what via not no per its their "
            "so if than then into over out up do does i me my we our -- -".split())


def _tokens(text):
    return {w for w in _WORD_RE.findall((text or "").lower()) if w not in _STOP and len(w) > 2}


def _overlap(a, b):
    if not a or not b:
        return 0.0
    inter = len(a & b)
    return inter / float(min(len(a), len(b)))  # containment: catches "subset" dupes


def _parse_frontmatter(text):
    """Return (meta_dict, body). Frontmatter is between the first two '---' lines."""
    if not text.startswith("---"):
        return {}, text
    lines = text.splitlines()
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return {}, text
    meta, mtype = {}, None
    in_meta = False
    for ln in lines[1:end]:
        s = ln.strip()
        if s == "metadata:":
            in_meta = True
            continue
        m = re.match(r"^([A-Za-z_]+):\s*(.*)$", ln)
        if m and not ln.startswith(" "):
            in_meta = False
            meta[m.group(1)] = m.group(2).strip()
        elif in_meta:
            mm = re.match(r"^\s+([A-Za-z_]+):\s*(.*)$", ln)
            if mm and mm.group(1) == "type":
                mtype = mm.group(2).strip()
    if mtype is not None:
        meta["type"] = mtype
    body = "\n".join(lines[end + 1:]).strip()
    return meta, body


def _parse_index(path):
    """Return (entries, raw_line_count). entries: list of {title, href, hook}."""
    entries = []
    if not os.path.isfile(path):
        return entries
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for ln in f:
            m = _INDEX_RE.match(ln)
            if m:
                href = m.group("href").strip().lstrip("./")
                entries.append({"title": m.group("title").strip(),
                                "href": href,
                                "hook": m.group("hook").strip(" -—")})
    return entries


def audit(mem_dir, max_chars, overlap, stale_days):
    findings = []
    index_path = os.path.join(mem_dir, INDEX_NAME)
    index = _parse_index(index_path)
    index_hrefs = {e["href"] for e in index}

    files = sorted(fn for fn in os.listdir(mem_dir)
                   if fn.lower().endswith(".md") and fn != INDEX_NAME) if os.path.isdir(mem_dir) else []

    today = datetime.date.today()
    mems = []  # {file, meta, body, size, tokens}
    for fn in files:
        p = os.path.join(mem_dir, fn)
        try:
            with open(p, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError:
            continue
        meta, body = _parse_frontmatter(text)
        toks = _tokens(meta.get("description", "")) | _tokens(meta.get("name", fn))
        mems.append({"file": fn, "meta": meta, "body": body, "size": len(text), "tokens": toks})

        # FRONTMATTER
        missing = [k for k in ("name", "description") if not meta.get(k)]
        if not meta.get("type"):
            missing.append("metadata.type")
        if missing:
            findings.append({"kind": "FRONTMATTER", "file": fn,
                             "detail": "missing " + ", ".join(missing)})
        # BLOAT
        if len(text) > max_chars:
            findings.append({"kind": "BLOAT", "file": fn,
                             "detail": "%d chars > %d budget (split to one fact/file?)" % (len(text), max_chars)})
        # STALE
        for y, mo, d in _DATE_RE.findall(text):
            try:
                dt = datetime.date(int(y), int(mo), int(d))
            except ValueError:
                continue
            age = (today - dt).days
            if age >= stale_days:
                findings.append({"kind": "STALE", "file": fn,
                                 "detail": "date %s is %d days old (still true?)" % (dt.isoformat(), age)})
                break
        # DRIFT: file not indexed
        if fn not in index_hrefs:
            findings.append({"kind": "DRIFT", "file": fn, "detail": "file has NO line in " + INDEX_NAME})

    # DRIFT: index -> missing file
    present = {m["file"] for m in mems}
    for e in index:
        if e["href"] not in present:
            findings.append({"kind": "DRIFT", "file": e["href"],
                             "detail": "index line '%s' points at a MISSING file" % e["title"]})

    # DUPLICATE / OVERLAP (pairwise; memory stores are small)
    for i in range(len(mems)):
        for j in range(i + 1, len(mems)):
            ov = _overlap(mems[i]["tokens"], mems[j]["tokens"])
            if ov >= overlap:
                findings.append({"kind": "DUPLICATE", "file": mems[i]["file"],
                                 "detail": "%.0f%% token-overlap with %s (merge?)" % (ov * 100, mems[j]["file"])})

    return {
        "memory_dir": mem_dir,
        "files": len(mems),
        "index_lines": len(index),
        "total_bytes": sum(m["size"] for m in mems),
        "findings": findings,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="Read-only audit of an agent memory store for compaction.")
    ap.add_argument("memory_dir", nargs="?",
                    default=os.environ.get("CLAUDE_MEMORY_DIR", "."),
                    help="memory dir (default: $CLAUDE_MEMORY_DIR or .)")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--max-chars", type=int, default=1500, help="bloat budget per file (default 1500)")
    ap.add_argument("--overlap", type=float, default=0.6, help="duplicate token-overlap threshold 0..1 (default 0.6)")
    ap.add_argument("--stale-days", type=int, default=180, help="flag ISO dates older than N days (default 180)")
    args = ap.parse_args(argv)

    mem_dir = os.path.abspath(args.memory_dir)
    if not os.path.isdir(mem_dir):
        print("error: not a directory: %s" % mem_dir, file=sys.stderr)
        return 2

    report = audit(mem_dir, args.max_chars, args.overlap, args.stale_days)

    if args.json:
        print(json.dumps(report, indent=2))
        return 0

    print("memory-compaction audit: %s" % report["memory_dir"])
    print("  %d memories | %d index lines | %d bytes"
          % (report["files"], report["index_lines"], report["total_bytes"]))
    if report["files"] and report["index_lines"] != report["files"]:
        print("  NOTE: index lines (%d) != files (%d) -- drift below."
              % (report["index_lines"], report["files"]))
    order = {"DRIFT": 0, "DUPLICATE": 1, "BLOAT": 2, "FRONTMATTER": 3, "STALE": 4}
    fnd = sorted(report["findings"], key=lambda f: (order.get(f["kind"], 9), f["file"]))
    if not fnd:
        print("  OK -- no compaction findings. Store is lean.")
        return 0
    print("  %d finding(s):" % len(fnd))
    for f in fnd:
        print("   [%-11s] %-32s %s" % (f["kind"], f["file"], f["detail"]))
    print("\nnext: merge DUPLICATEs, split BLOAT to one-fact files, fix DRIFT/ FRONTMATTER,")
    print("      verify STALE facts. Re-run to confirm convergence. (This script writes nothing.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
