"""modledger: make game mods reversible (stdlib only).

Snapshot a game folder before modding, see exactly what a mod added or changed, park the mod's files
somewhere safe with a SHA-256 manifest, and restore them later after re-checking every hash.

  python modledger.py snapshot GAME_DIR -o baseline.json [--quick-mb 256]
  python modledger.py diff GAME_DIR baseline.json [--json]
  python modledger.py park GAME_DIR --name NAME --to PARK_DIR (--added-since baseline.json | --files F [F ...])
  python modledger.py restore PARK_DIR NAME [--game-dir DIR] [--force]
  python modledger.py list PARK_DIR

park copies, verifies the copies by hash, and only then deletes the originals (copy-verify-then-delete,
never a one-step move). restore refuses to overwrite a different file that is already in the game
folder unless --force, and keeps the parked copies. Keep the baseline file OUTSIDE the game folder.

Files above --quick-mb (default 256 MB) are compared by size and modification time only, not hashed,
so a same-size replacement that preserves the timestamp is not detected. Use --quick-mb 0 to hash all.
"""
import argparse
import hashlib
import json
import os
import shutil
import sys

MANIFEST = "manifest.json"


def sha256(path, chunk=1 << 22):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def _rel(root, path):
    return os.path.relpath(path, root).replace(os.sep, "/")


def _write_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def snapshot(game_dir, quick_mb=256):
    """Map every file under game_dir to {size, sha256} (or {size, mtime} above quick_mb).
    A file that cannot be read (locked by a running game, no permission) is recorded with an
    "error" instead of aborting the whole snapshot. Directory junctions and symlinks are not followed."""
    out = {}
    limit = quick_mb * 1024 * 1024 if quick_mb else None
    for dirpath, dirs, files in os.walk(game_dir):
        dirs[:] = [d for d in dirs if not _is_link(os.path.join(dirpath, d))]
        for name in files:
            p = os.path.join(dirpath, name)
            try:
                st = os.stat(p)
                entry = {"size": st.st_size}
                if limit is not None and st.st_size > limit:
                    entry["mtime"] = int(st.st_mtime)
                else:
                    entry["sha256"] = sha256(p)
            except OSError as e:
                entry = {"error": "%s: %s" % (type(e).__name__, e.strerror or e)}
            out[_rel(game_dir, p)] = entry
    return {"gameDir": os.path.abspath(game_dir), "quickMb": quick_mb, "files": out}


def _is_link(path):
    if os.path.islink(path):
        return True
    is_junction = getattr(os.path, "isjunction", None)  # Python 3.12+
    if is_junction is not None:
        return is_junction(path)
    try:  # older Pythons: an NTFS junction is a reparse point
        return bool(os.lstat(path).st_file_attributes & 0x400)
    except (OSError, AttributeError):
        return False


def diff(game_dir, baseline):
    """Return {added, changed, removed} relative paths versus a snapshot."""
    old = baseline["files"]
    now = snapshot(game_dir, baseline.get("quickMb", 256))["files"]
    added = sorted(set(now) - set(old))
    removed = sorted(set(old) - set(now))
    changed = []
    for rel in sorted(set(now) & set(old)):
        a, b = old[rel], now[rel]
        if "error" in a or "error" in b:
            continue  # unreadable then or now: cannot compare (snapshot reports it)
        if a.get("size") != b.get("size"):
            changed.append(rel)
        elif "sha256" in a and "sha256" in b and a["sha256"] != b["sha256"]:
            changed.append(rel)
        elif "mtime" in a and "mtime" in b and a["mtime"] != b["mtime"]:
            changed.append(rel)
    return {"added": added, "changed": changed, "removed": removed}


def park(game_dir, name, park_dir, files):
    """Copy files into park_dir/name, verify hashes, record them, then delete the originals."""
    if not files:
        raise SystemExit("nothing to park")
    man_path = os.path.join(park_dir, MANIFEST)
    man = _read_json(man_path) if os.path.exists(man_path) else {}
    dest_root = os.path.join(park_dir, name)
    if name in man or (os.path.isdir(dest_root) and os.listdir(dest_root)):
        raise SystemExit("a parked set named %r already exists; pick a new name (parking over it "
                         "would lose the files it holds)" % name)
    for rel in files:
        parts = rel.replace("\\", "/").split("/")
        if os.path.isabs(rel) or ".." in parts or not rel.strip():
            raise SystemExit("not a path inside the game folder: %r" % rel)
        if not os.path.isfile(os.path.join(game_dir, *parts)):
            raise SystemExit("not a file: %s" % os.path.join(game_dir, *parts))
    files = [r.replace("\\", "/") for r in files]
    os.makedirs(dest_root, exist_ok=True)
    recorded = {}
    for rel in files:
        src = os.path.join(game_dir, *rel.split("/"))
        dst = os.path.join(dest_root, *rel.split("/"))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
        h_src, h_dst = sha256(src), sha256(dst)
        if h_src != h_dst:
            raise SystemExit("copy mismatch on %s: nothing deleted" % rel)
        recorded[rel] = h_src
    man[name] = {"gameDir": os.path.abspath(game_dir), "files": recorded}
    _write_json(man_path, man)
    for rel in recorded:  # only after every copy verified and the manifest is on disk
        os.remove(os.path.join(game_dir, *rel.split("/")))
    return recorded


def restore(park_dir, name, force=False, game_dir=None):
    """Copy parked files back after checking every hash. Returns the restored relative paths.
    game_dir overrides the folder recorded at park time (use it after the game was moved)."""
    man = _load_manifest(park_dir)
    if name not in man:
        raise SystemExit("no parked set named %r (have: %s)" % (name, ", ".join(sorted(man)) or "none"))
    entry = man[name]
    game_dir = game_dir or entry["gameDir"]
    if not os.path.isdir(game_dir):
        raise SystemExit("game folder %s does not exist (moved or uninstalled?); pass --game-dir" % game_dir)
    plan = []
    for rel, want in entry["files"].items():
        src = os.path.join(park_dir, name, *rel.split("/"))
        if sha256(src) != want:
            raise SystemExit("parked copy changed: %s (nothing restored)" % rel)
        dst = os.path.join(game_dir, *rel.split("/"))
        if os.path.exists(dst) and sha256(dst) != want and not force:
            raise SystemExit("%s exists and differs; close the game, check it, or pass --force" % dst)
        plan.append((src, dst, rel))
    for src, dst, _rel_ in plan:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
    return [rel for _s, _d, rel in plan]


def _load_manifest(park_dir):
    path = os.path.join(park_dir, MANIFEST)
    if not os.path.exists(path):
        raise SystemExit("no %s in %s: nothing has been parked there" % (MANIFEST, park_dir))
    return _read_json(path)


def _outside_baseline(game_dir, baseline_path, rels):
    """Leave the baseline file itself out if it was saved inside the game folder."""
    rel = os.path.relpath(os.path.abspath(baseline_path), os.path.abspath(game_dir)).replace(os.sep, "/")
    if rel.startswith(".."):
        return rels
    print("note: %s is inside the game folder and is left out (keep baselines outside)" % rel)
    return [r for r in rels if r != rel]


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("snapshot")
    s.add_argument("game_dir")
    s.add_argument("-o", "--out", required=True)
    s.add_argument("--quick-mb", type=int, default=256, help="above this size record size+mtime, not a hash (0 = hash all)")
    d = sub.add_parser("diff")
    d.add_argument("game_dir")
    d.add_argument("baseline")
    d.add_argument("--json", action="store_true")
    p = sub.add_parser("park")
    p.add_argument("game_dir")
    p.add_argument("--name", required=True)
    p.add_argument("--to", required=True, dest="park_dir")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--added-since", help="park every file added since this snapshot")
    g.add_argument("--files", nargs="+", help="relative paths inside GAME_DIR")
    r = sub.add_parser("restore")
    r.add_argument("park_dir")
    r.add_argument("name")
    r.add_argument("--force", action="store_true")
    r.add_argument("--game-dir", help="restore into this folder instead of the one recorded at park time")
    li = sub.add_parser("list")
    li.add_argument("park_dir")
    a = ap.parse_args(argv)

    if a.cmd == "snapshot":
        snap = snapshot(a.game_dir, a.quick_mb)
        _write_json(a.out, snap)
        errors = [k for k, v in snap["files"].items() if "error" in v]
        print("%d files recorded -> %s" % (len(snap["files"]), a.out))
        if errors:
            print("could not read %d file(s) (is the game running?): %s" % (len(errors), ", ".join(errors[:10])))
    elif a.cmd == "diff":
        res = diff(a.game_dir, _read_json(a.baseline))
        res["added"] = _outside_baseline(a.game_dir, a.baseline, res["added"])
        if a.json:
            print(json.dumps(res, indent=2))
        else:
            for k in ("added", "changed", "removed"):
                print("%s (%d)" % (k.upper(), len(res[k])))
                for rel in res[k]:
                    print("  " + rel)
    elif a.cmd == "park":
        files = a.files or _outside_baseline(a.game_dir, a.added_since,
                                             diff(a.game_dir, _read_json(a.added_since))["added"])
        done = park(a.game_dir, a.name, a.park_dir, files)
        print("parked %d files as %r in %s" % (len(done), a.name, a.park_dir))
    elif a.cmd == "restore":
        done = restore(a.park_dir, a.name, a.force, a.game_dir)
        print("restored %d files (parked copies kept)" % len(done))
    elif a.cmd == "list":
        man = _load_manifest(a.park_dir)
        for name, e in sorted(man.items()):
            print("%-24s %3d files  %s" % (name, len(e["files"]), e["gameDir"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
