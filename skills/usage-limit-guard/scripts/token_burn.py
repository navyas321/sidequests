#!/usr/bin/env python3
"""Local Claude token-burn reporter (today / 5h block / 7d).

The ONLY programmatic usage signal: scan ~/.claude transcript .jsonl files and sum
message.usage tokens per time bucket. This is genuine local burn (what ccusage
reports) and is independent of the plan's 5h/weekly limit % — that true gauge is
NOT API-exposed. Pure stdlib, no dependencies.

Mirrors life-in-tabs serve_life.local_token_burn(). Caps the scan to the most
recently modified files in the 8-day window so it stays cheap.

Usage:  python token_burn.py [claude_projects_dir]
Env:    USAGE_SCAN_CAP (default 120)
"""
import os
import sys
import glob
import json
import datetime as dt


def _z():
    return {"input": 0, "output": 0, "cache_creation": 0, "cache_read": 0,
            "total": 0, "msgs": 0}


def _parse_iso(ts):
    try:
        return dt.datetime.fromisoformat((ts or "").replace("Z", "+00:00"))
    except Exception:
        return None


def burn(projects_dir, scan_cap=120):
    now = dt.datetime.now(dt.timezone.utc)
    today_local = dt.datetime.now().date()
    week_ago = now - dt.timedelta(days=7)
    block_ago = now - dt.timedelta(hours=5)
    cutoff = (now - dt.timedelta(days=8)).timestamp()
    out = {"today": _z(), "block": _z(), "week": _z(), "lastTs": "",
           "asOf": now.isoformat(timespec="seconds")}
    try:
        files = glob.glob(os.path.join(projects_dir, "**", "*.jsonl"), recursive=True)
    except Exception:
        files = []
    try:
        files = [fp for fp in files if os.path.getmtime(fp) >= cutoff]
        files.sort(key=lambda fp: os.path.getmtime(fp), reverse=True)
    except Exception:
        pass
    out["filesInWindow"] = len(files)
    out["scanned"] = min(len(files), scan_cap)
    for fp in files[:scan_cap]:
        try:
            f = open(fp, "r", encoding="utf-8", errors="ignore")
        except Exception:
            continue
        with f:
            for line in f:
                if '"usage"' not in line or '"output_tokens"' not in line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                msg = obj.get("message") if isinstance(obj.get("message"), dict) else {}
                u = msg.get("usage") or obj.get("usage")
                if not isinstance(u, dict):
                    continue
                t = _parse_iso(obj.get("timestamp"))
                if not t:
                    continue
                inp = int(u.get("input_tokens", 0) or 0)
                otp = int(u.get("output_tokens", 0) or 0)
                ccr = int(u.get("cache_creation_input_tokens", 0) or 0)
                crd = int(u.get("cache_read_input_tokens", 0) or 0)
                for key, ok in (("today", t.astimezone().date() == today_local),
                                ("block", t >= block_ago),
                                ("week", t >= week_ago)):
                    if ok:
                        b = out[key]
                        b["input"] += inp
                        b["output"] += otp
                        b["cache_creation"] += ccr
                        b["cache_read"] += crd
                        b["total"] += inp + otp + ccr + crd
                        b["msgs"] += 1
                ts = obj.get("timestamp") or ""
                if ts > out["lastTs"]:
                    out["lastTs"] = ts
    return out


def _fmt(b):
    return (f"total={b['total']:>12,}  in={b['input']:>11,}  out={b['output']:>9,}  "
            f"cache_w={b['cache_creation']:>11,}  cache_r={b['cache_read']:>12,}  "
            f"msgs={b['msgs']}")


def main():
    default = os.path.join(os.path.expanduser("~"), ".claude", "projects")
    projects = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("CLAUDE_PROJECTS", default)
    cap = int(os.environ.get("USAGE_SCAN_CAP", "120"))
    data = burn(projects, cap)
    print(f"Local Claude token burn  (as of {data['asOf']})")
    print(f"  source: {projects}")
    print(f"  scanned {data['scanned']}/{data['filesInWindow']} transcripts in the 8-day window")
    print(f"  today : {_fmt(data['today'])}")
    print(f"  5h    : {_fmt(data['block'])}   <- proxy for current rolling-window pressure")
    print(f"  7d    : {_fmt(data['week'])}")
    print(f"  last transcript ts: {data['lastTs'] or '(none)'}")
    print("  NOTE: the true claude.ai 5h/weekly limit % is NOT API-exposed; this is local burn only.")


if __name__ == "__main__":
    main()
