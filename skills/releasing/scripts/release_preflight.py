#!/usr/bin/env python3
"""release_preflight.py - deterministic gate to run BEFORE tagging a stable release.

Why: when bump class and cadence are free choices made by whichever session cuts the release,
numbering drifts (majors burned days apart, two stables on one day, minors frozen through dozens
of feature waves). This script turns those choices into checks. Pure stdlib, read-only.

Usage:
  python release_preflight.py --stable v2.4.0 --feature-justification "new reports page"
  python release_preflight.py --stable v3.0.0 --breaking-justification "config format changed"
  python release_preflight.py --stable v2.3.7                      # patch: no paperwork
  options: --repo PATH  --version-file VERSION|package.json|pyproject.toml
           --allow-same-day "REASON"   --allow-catchup "REASON"   --json

Checks (exit 0 = PASS, 2 = FAIL with reasons):
  1. The version file (minus any -beta/-rc suffix) equals the stable you are cutting:
     stable is what the beta validated, never a number nobody ran.
  2. Tag format is vX.Y.Z.
  3. At most one stable per day, unless --allow-same-day "REASON".
  4. Bump class vs the last stable tag:
       major -> needs --breaking-justification
       minor -> needs --feature-justification
       patch -> always fine (5.1.0 -> 5.1.15 is legitimate: the betas moved)
     A jump of more than one minor/major is a CATCH-UP. It passes only when the version file's
     own git history shows the beta actually held every level on the way; jumping to a level no
     beta ever ran is number burning and fails.

Why catch-ups are evidence-based instead of "at most +1": in a continuous-beta repo where stable
is cut only on request, gaps like v11.1.0 -> v11.4.3 are routine. "Stable == beta" plus "advance at
most one minor" is then unsatisfiable, every cut needs an override, and an override needed on the
normal path is a broken default. --allow-catchup is only for a repo whose version history cannot be
read (shallow clone, rewritten history).
"""
import argparse
import datetime
import io
import json
import os
import re
import subprocess
import sys

TRAIL_LIMIT = 800
WALK_LIMIT = 500
VER_RE = re.compile(r"(\d+)\.(\d+)\.(\d+)")
STRUCTURED = ("package.json", "pyproject.toml", "setup.cfg", "cargo.toml")


def git(repo, args):
    cp = subprocess.run(["git", "-C", repo] + args, capture_output=True, text=True,
                        encoding="utf-8", errors="replace", timeout=60)
    return cp.stdout.strip() if cp.returncode == 0 else ""


def parse_ver(s):
    m = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", (s or "").strip())
    return tuple(int(x) for x in m.groups()) if m else None


def _extract(text, version_file):
    """The x.y.z a version file declares (plain file: first line; json/toml: the version key)."""
    if os.path.basename(version_file).lower() in STRUCTURED:
        m = re.search(r"""^\s*"?version"?\s*[:=]\s*["']([^"']+)["']""", text, re.M | re.I)
        raw = m.group(1) if m else ""
    else:
        raw = (text.strip().splitlines() or [""])[0].strip()
    m = VER_RE.search(raw)
    return raw, (tuple(int(x) for x in m.groups()) if m else None)


def read_beta(repo, version_file):
    try:
        text = io.open(os.path.join(repo, version_file), encoding="utf-8").read()
    except OSError:
        return "", None
    return _extract(text, version_file)


def beta_levels(repo, version_file):
    """Every (major, minor) the version file actually held, from its own git history."""
    levels = set()
    out = git(repo, ["log", "-n", str(TRAIL_LIMIT), "--format=%x00", "-p", "--", version_file])
    structured = os.path.basename(version_file).lower() in STRUCTURED
    for line in out.splitlines():
        if not line.startswith("+") or line.startswith("+++"):
            continue
        body = line[1:]
        if structured and "version" not in body.lower():
            continue
        m = VER_RE.search(body)
        if m:
            levels.add((int(m.group(1)), int(m.group(2))))
    _, cur = read_beta(repo, version_file)
    if cur:
        levels.add((cur[0], cur[1]))
    return levels


def catchup_trail(last, want, levels):
    """Walk last -> want one legal level at a time (+1 minor, or +1 major to x.0), requiring beta
    evidence for each. -> (True, [levels crossed]) or (False, level where the trail stops)."""
    cur, goal, path = (last[0], last[1]), (want[0], want[1]), []
    while cur < goal:
        step_minor, step_major = (cur[0], cur[1] + 1), (cur[0] + 1, 0)
        if step_minor <= goal and step_minor in levels:
            cur = step_minor
        elif step_major <= goal and step_major in levels:
            cur = step_major
        else:
            return False, cur
        path.append(cur)
        if len(path) > WALK_LIMIT:
            return False, cur
    return True, path


def evaluate(repo, version_file, stable, breaking="", feature="", same_day="", catchup=""):
    res = {"stable": stable, "ok": False, "blocking": [], "paperwork": [], "notes": [],
           "lastStable": "none", "betaVersion": "", "bumpClass": ""}
    want = parse_ver(stable)
    if not want or not stable.startswith("v"):
        res["blocking"].append("--stable must be vX.Y.Z (got '%s')" % stable)
        return res

    raw, beta = read_beta(repo, version_file)
    res["betaVersion"] = raw
    if beta != want:
        res["blocking"].append("%s says '%s' but you are cutting %s - stable must equal what the beta "
                               "validated (bump the beta first, let it run, then cut)" % (version_file, raw, stable))

    tags = [t for t in git(repo, ["tag", "--sort=-creatordate"]).splitlines() if parse_ver(t)]
    top = max(tags, key=parse_ver) if tags else None      # highest version, not newest tag (hotfix lines)
    last = parse_ver(top) if top else (0, 0, 0)
    res["lastStable"] = top or "none"

    today = datetime.date.today().isoformat()
    for t in tags:   # the TAG's own date (tagger date for annotated tags), not its commit's
        if git(repo, ["for-each-ref", "--format=%(creatordate:short)", "refs/tags/" + t]) == today:
            if same_day.strip():
                res["notes"].append("same-day stable %s exists; overridden: %s" % (t, same_day))
            else:
                res["paperwork"].append("a stable (%s) was already cut today - one per day unless "
                                        "--allow-same-day \"<reason>\"" % t)
            break

    dmaj, dmin = want[0] - last[0], want[1] - last[1]
    res["bumpClass"] = "major" if dmaj >= 1 else ("minor" if dmin >= 1 else "patch")
    if want <= last:
        res["blocking"].append("%s is not ahead of the last stable %s" % (stable, res["lastStable"]))
    else:
        single = (dmaj == 0 and dmin in (0, 1)) or (dmaj == 1 and want[1] == 0)
        if not single:
            ok, info = catchup_trail(last, want, beta_levels(repo, version_file))
            if ok:
                res["notes"].append("catch-up %s -> %s: the beta held every level on the way (%s)"
                                    % (res["lastStable"], stable, ", ".join("%d.%d" % lv for lv in info)))
            elif catchup.strip() and beta == want:
                res["notes"].append("catch-up with no readable beta trail; overridden: %s" % catchup)
            else:
                res["blocking"].append("number burning: %s -> %s jumps past %d.%d to a level no beta ever ran"
                                       % (res["lastStable"], stable, info[0], info[1]))
    if dmaj >= 1 and not breaking.strip():
        res["paperwork"].append("MAJOR bump needs --breaking-justification (breaking change or redesign)")
    if dmaj == 0 and dmin >= 1 and not feature.strip():
        res["paperwork"].append("MINOR bump needs --feature-justification (the user-facing feature wave it ships)")
    res["ok"] = not res["blocking"] and not res["paperwork"]
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(description="Gate a stable tag before you cut it.")
    ap.add_argument("--stable", required=True, help="the tag you intend to cut, e.g. v2.4.0")
    ap.add_argument("--repo", default=".")
    ap.add_argument("--version-file", default="VERSION")
    ap.add_argument("--breaking-justification", default="")
    ap.add_argument("--feature-justification", default="")
    ap.add_argument("--allow-same-day", default="", metavar="REASON")
    ap.add_argument("--allow-catchup", default="", metavar="REASON")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    res = evaluate(os.path.abspath(a.repo), a.version_file, a.stable, a.breaking_justification,
                   a.feature_justification, a.allow_same_day, a.allow_catchup)
    if a.json:
        print(json.dumps(res, indent=2))
        return 0 if res["ok"] else 2
    for n in res["notes"]:
        print("note: " + n)
    fails = res["blocking"] + res["paperwork"]
    if fails:
        print("RELEASE PREFLIGHT: FAIL (%d)" % len(fails))
        for f in fails:
            print("  - " + f)
        return 2
    print("RELEASE PREFLIGHT: PASS - %s (%s bump) ok to tag; last stable %s"
          % (a.stable, res["bumpClass"], res["lastStable"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
