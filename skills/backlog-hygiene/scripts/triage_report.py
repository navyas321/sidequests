#!/usr/bin/env python3
"""triage_report.py - read a JSON backlog and PROPOSE a hygiene pass. Never writes to the backlog.

Flags the patterns that make a shared backlog lie about the state of the work:

  orphan       in-progress with an owner but no activity for --orphan-hours (dead session?)
  paused-pile  paused/blocked longer than --paused-days, or paused with no owner / no resume note
  risk-ok      'accepted' (risk accepted) items whose text never names a risk -> likely a dismissal
  stale-block  non-terminal items that cite a blocker and were not touched for --block-days
  no-evidence  terminal items whose resolution is missing or says nothing about verification
  dup?         open items whose titles are near-identical (merge only after a human-style check)

Input: a JSON file that is either a list of items or {"items": [...]}. Field names are configurable.
Each item should have id, title, status; optional owner, updated/updatedAt, created, detail,
resolution, comments [{at, text}].

Usage:
  python triage_report.py backlog.json                    # markdown report
  python triage_report.py backlog.json --json             # machine-readable
  python triage_report.py backlog.json --orphan-hours 8 --paused-days 7 --block-days 14
Exit code: 0 = nothing flagged, 1 = findings (so a periodic job can surface them).
"""
import argparse
import datetime as _dt
import difflib
import io
import json
import re
import sys

TERMINAL = {"done", "shipped", "wontfix", "duplicate", "canceled", "cancelled", "accepted", "snoozed", "closed"}
PAUSED = {"paused", "blocked", "on-hold", "onhold", "waiting"}
INPROGRESS = {"inprogress", "in-progress", "in_progress", "doing", "wip", "active"}
RISK_RE = re.compile(r"secur|vulnerab|exposure|expos|leak|attack|exploit|auth|csrf|xss|rce|inject|privacy|"
                     r"pii|secret|token|credential|data.?loss|corrupt|compliance|legal|outage|abuse|"
                     r"cost|billing|spend|downtime|threat|risk of", re.I)
VERIFY_RE = re.compile(r"verif|test|smoke|curl|render|confirm|checked|passed|observ|http\s*\d|/api/|"
                       r"git show|commit [0-9a-f]{6,}|screenshot|log", re.I)
BLOCK_RE = re.compile(r"\bblock(ed|er|s)?\b|waiting (on|for)|depends on|needs? (the )?(user|human|access)|"
                      r"after .{3,40} (ships|lands|is done)|until\b", re.I)


def parse_ts(v):
    if not v:
        return None
    s = str(v).strip().replace("Z", "+00:00")
    for cut in (len(s), 26, 19, 10):
        try:
            d = _dt.datetime.fromisoformat(s[:cut])
            return d if d.tzinfo else d.replace(tzinfo=_dt.timezone.utc)
        except ValueError:
            continue
    return None


def last_touched(it, fields):
    stamps = [parse_ts(it.get(f)) for f in fields]
    for c in it.get("comments") or []:
        if isinstance(c, dict):
            stamps.append(parse_ts(c.get("at") or c.get("ts") or c.get("created")))
    stamps = [s for s in stamps if s]
    return max(stamps) if stamps else None


def text_of(it):
    parts = [str(it.get(k) or "") for k in ("title", "detail", "resolution", "progress")]
    parts += [str(c.get("text") or "") for c in (it.get("comments") or []) if isinstance(c, dict)]
    return "\n".join(parts)


def norm_title(t):
    t = re.sub(r"^\s*(task|bug|fix|build|feature|spike|research)\s*:\s*", "", (t or "").lower())
    return re.sub(r"[^a-z0-9 ]+", " ", t).strip()


def triage(items, now, a):
    out = []

    def add(kind, it, why, suggest):
        out.append({"kind": kind, "id": it.get("id"), "status": it.get(a.status_field),
                    "title": str(it.get("title") or "")[:90], "why": why, "suggest": suggest})

    open_items = []
    for it in items:
        st = str(it.get(a.status_field) or "").lower()
        touched = last_touched(it, a.time_fields)
        age_h = (now - touched).total_seconds() / 3600 if touched else None
        txt = text_of(it)
        owner = str(it.get(a.owner_field) or "").strip()

        if st in INPROGRESS and (age_h is None or age_h > a.orphan_hours):
            add("orphan", it, "in progress, owner %r, no activity for %s" % (
                owner or "-", "%.0fh" % age_h if age_h is not None else "an unknown time"),
                "check the owner is alive with 2+ signals (session list, recent commits, heartbeat); "
                "if dead, move to open with a handoff comment of what is done")
        elif st in PAUSED:
            reasons = []
            if age_h is not None and age_h > a.paused_days * 24:
                reasons.append("paused %.0f days" % (age_h / 24))
            if not owner:
                reasons.append("no owner")
            if not re.search(r"resume|next step|waiting for|blocked (on|by)|until", txt, re.I):
                reasons.append("no resume condition written down")
            if reasons:
                add("paused-pile", it, ", ".join(reasons),
                    "verify against the live system: finished -> done with evidence; work remains -> open "
                    "(clear the owner); genuinely waiting -> keep, with owner + resume condition")
        elif st == "accepted" and not RISK_RE.search(txt):
            add("risk-ok", it, "marked risk-accepted but the text names no risk",
                "a dismissal wearing a risk label: wontfix with the real reason (with the user's say-so), "
                "or reopen if it is still worth doing")

        if st not in TERMINAL and BLOCK_RE.search(txt) and age_h is not None and age_h > a.block_days * 24:
            add("stale-block", it, "cites a blocker, untouched %.0f days" % (age_h / 24),
                "re-check the blocker NOW; blockers clear silently. Record what you found as a dated comment")

        if st in TERMINAL and st not in ("snoozed",):
            res = str(it.get("resolution") or "")
            if len(res) < 40 or not VERIFY_RE.search(res + " " + str(it.get("verification") or "")):
                add("no-evidence", it, "closed as %s without a why + how-verified resolution" % st,
                    "re-verify; if it is not really finished, reopen it")

        if st not in TERMINAL:
            open_items.append(it)

    seen = set()
    for i, x in enumerate(open_items):
        tx = norm_title(x.get("title"))
        for y in open_items[i + 1:]:
            ty = norm_title(y.get("title"))
            if tx and ty and difflib.SequenceMatcher(None, tx, ty).ratio() >= a.dup_ratio:
                key = (x.get("id"), y.get("id"))
                if key not in seen:
                    seen.add(key)
                    add("dup?", x, "title close to %s" % y.get("id"),
                        "merge only if it is REALLY the same work: move any unique scope to the canonical "
                        "item first, then close the other as duplicate naming the canonical id")
    return out


def counts(items, field):
    c = {}
    for it in items:
        k = str(it.get(field) or "?").lower()
        c[k] = c.get(k, 0) + 1
    return dict(sorted(c.items(), key=lambda kv: -kv[1]))


def main(argv=None):
    ap = argparse.ArgumentParser(description="Propose a backlog hygiene pass (read-only).")
    ap.add_argument("backlog")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--status-field", default="status")
    ap.add_argument("--owner-field", default="owner")
    ap.add_argument("--time-fields", default="updated,updatedAt,modified,lastActivity,created",
                    help="comma list of timestamp fields; the latest one (or comment) counts")
    ap.add_argument("--orphan-hours", type=float, default=8)
    ap.add_argument("--paused-days", type=float, default=7)
    ap.add_argument("--block-days", type=float, default=14)
    ap.add_argument("--dup-ratio", type=float, default=0.88)
    a = ap.parse_args(argv)
    a.time_fields = [f.strip() for f in a.time_fields.split(",") if f.strip()]
    try:   # Windows consoles default to cp1252 and crash on the first non-ASCII title
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    with io.open(a.backlog, encoding="utf-8") as f:
        data = json.load(f)
    items = data.get("items", []) if isinstance(data, dict) else data
    items = [it for it in items if isinstance(it, dict)]
    now = _dt.datetime.now(_dt.timezone.utc)
    found = triage(items, now, a)
    report = {"total": len(items), "byStatus": counts(items, a.status_field), "findings": found}

    if a.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print("# Backlog hygiene proposal\n")
        print("%d items; by status: %s\n" % (len(items), ", ".join("%s %d" % kv for kv in report["byStatus"].items())))
        if not found:
            print("Nothing flagged.")
        for kind in ("orphan", "paused-pile", "risk-ok", "stale-block", "no-evidence", "dup?"):
            rows = [x for x in found if x["kind"] == kind]
            if not rows:
                continue
            print("## %s (%d)\n" % (kind, len(rows)))
            for x in rows:
                print("- **%s** [%s] %s\n  - why: %s\n  - suggest: %s" % (x["id"], x["status"], x["title"], x["why"], x["suggest"]))
            print()
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
