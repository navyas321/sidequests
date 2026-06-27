#!/usr/bin/env python3
"""Classify a headless `claude -p --output-format json` run as OK / LIMIT / ERROR.

There is NO dedicated rate-limit exit code yet (exit 75 is an open request); claude
just exits non-zero on exhaustion. So we branch on BOTH the exit code and the
payload, and string-match the result for the limit message as a fallback.

Usage:
    claude -p "<prompt>" --output-format json > run.json; rc=$?
    python detect_limit.py run.json $rc

Prints exactly one of:
    OK
    LIMIT <reset-text-or-empty>      # back off until reset; do NOT retry
    ERROR <category>                 # overloaded / billing_error / auth / server / ...
Exit code: 0 = OK, 1 = LIMIT, 2 = ERROR (so a shell can branch on $?).
"""
import sys
import re
import json

RESET_RE = re.compile(
    r"(?:session|usage)\s+limit[^\n]*?resets?\s+([0-9: ]+[ap]m(?:\s*\([^)]+\))?)",
    re.IGNORECASE,
)
LIMIT_HINTS = ("session limit", "usage limit", "rate_limit", "rate limit",
               "resets ", "out of credit", "credit balance")
RETRY_CATEGORIES = {"rate_limit", "overloaded", "billing_error",
                    "authentication_failed", "server_error", "max_output_tokens"}


def _iter_events(raw):
    """Yield dict events from json or stream-json (one obj per line) output."""
    raw = raw.strip()
    if not raw:
        return
    try:
        obj = json.loads(raw)
        if isinstance(obj, list):
            for o in obj:
                yield o
        else:
            yield obj
        return
    except Exception:
        pass
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            yield json.loads(line)
        except Exception:
            continue


def classify(raw, rc):
    text_blob = raw
    error_category = None
    for ev in _iter_events(raw):
        if not isinstance(ev, dict):
            continue
        # api_retry / system events carry an explicit error category
        cat = ev.get("error")
        if isinstance(cat, dict):
            cat = cat.get("type") or cat.get("category")
        if isinstance(cat, str) and cat in RETRY_CATEGORIES:
            error_category = cat
        # subtype/status forms
        sub = ev.get("subtype") or ev.get("status")
        if isinstance(sub, str) and sub.lower() in ("rate_limited", "rejected"):
            error_category = error_category or "rate_limit"
        res = ev.get("result")
        if isinstance(res, str):
            text_blob += "\n" + res

    low = text_blob.lower()
    reset_m = RESET_RE.search(text_blob)
    looks_limited = (error_category == "rate_limit") or any(h in low for h in LIMIT_HINTS)

    if looks_limited:
        return "LIMIT", (reset_m.group(1).strip() if reset_m else "")
    if error_category:
        return "ERROR", error_category
    if rc != 0:
        # non-zero with no recognized signal: treat as error, unknown category
        return "ERROR", "unknown_nonzero_exit"
    return "OK", ""


def main():
    if len(sys.argv) < 2:
        print("usage: detect_limit.py <run.json> [exit_code]", file=sys.stderr)
        sys.exit(3)
    path = sys.argv[1]
    rc = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            raw = f.read()
    except Exception as e:
        print(f"ERROR could-not-read-{e.__class__.__name__}")
        sys.exit(2)
    verdict, detail = classify(raw, rc)
    print(verdict + (" " + detail if detail else ""))
    sys.exit({"OK": 0, "LIMIT": 1, "ERROR": 2}[verdict])


if __name__ == "__main__":
    main()
