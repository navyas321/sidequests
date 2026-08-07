#!/usr/bin/env python3
"""checksync.py - keep the copies of videoscan.py identical across skills.

Skills are installed one directory at a time, so each one that needs video
perception ships its own copy. That only works if the copies do not drift.

  python checksync.py         # report drift, exit 1 if any
  python checksync.py --fix   # overwrite the copies from the canonical file
"""
from __future__ import annotations

import hashlib
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILLS = os.path.dirname(os.path.dirname(HERE))
CANONICAL = os.path.join(HERE, "videoscan.py")
COPIES = [
    os.path.join(SKILLS, "game-walkthrough", "scripts", "videoscan.py"),
    os.path.join(SKILLS, "source-finder", "scripts", "videoscan.py"),
]


def digest(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()[:12]


def main() -> None:
    fix = "--fix" in sys.argv
    want = digest(CANONICAL)
    drift = []
    for copy in COPIES:
        rel = os.path.relpath(copy, SKILLS)
        if not os.path.exists(copy):
            state = "MISSING"
        elif digest(copy) == want:
            print(f"ok      {rel}")
            continue
        else:
            state = "DRIFTED"
        if fix:
            os.makedirs(os.path.dirname(copy), exist_ok=True)
            shutil.copyfile(CANONICAL, copy)
            print(f"fixed   {rel}  ({state})")
        else:
            print(f"{state} {rel}")
            drift.append(rel)
    print(f"canonical {os.path.relpath(CANONICAL, SKILLS)} sha256:{want}")
    if drift:
        sys.exit(f"\n{len(drift)} copy/copies out of sync - rerun with --fix")


if __name__ == "__main__":
    main()
