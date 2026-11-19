"""Restore a backup made by ftpbackup.py to an FTP root (stdlib only). Uploads every file in
MANIFEST.sha256 except skipped prefixes, checks every size, and re-downloads files under 100 MB to
compare SHA-256.

usage: python ftprestore.py HOST PORT BACKUP_DIR [--skip PREFIX ...] [--force]
example: python ftprestore.py 192.168.1.50 2221 D:/backups/handheld-2026-11-18 --skip /gm9/

A file that already exists on the device with DIFFERENT content (a newer save, say) is never
overwritten by default: it is listed as a CONFLICT and left alone. With --force, the device's copy
is first downloaded to BACKUP_DIR/_device-copies-<time>/ and only then replaced.

If every upload fails with 550/551, the FTP app's root folder points at a path that no longer exists
(e.g. after reformatting the SD card): re-pick the root folder in the app and restart its server.
Login: see ftpcommon.py.
"""
import ftplib
import hashlib
import os
import sys
import time

from ftpcommon import TRANSIENT, PermanentStreak, connect, is_permanent

HASH_LIMIT = 100e6


def main(argv):
    force = "--force" in argv
    args = [a for a in argv if a != "--force"]
    skip = ()
    if "--skip" in args:
        i = args.index("--skip")
        skip, args = tuple(args[i + 1:]), args[:i]
    host, port, src = args[0], int(args[1]), args[2]

    entries = []
    for line in open(os.path.join(src, "MANIFEST.sha256"), encoding="utf-8"):
        h, size, p = line.rstrip("\n").split("  ", 2)
        if skip and p.startswith(skip):
            continue
        entries.append((p, int(size), h))
    total = sum(s for _, s, _ in entries)
    print(f"{len(entries)} files, {total / 1e9:.2f} GB", flush=True)

    state = {"f": connect(host, port, timeout=120), "no_size": False}
    made = set()

    def reconnect():
        time.sleep(5)
        try:
            state["f"] = connect(host, port, timeout=120)
            made.clear()
        except Exception as e2:
            print("  reconnect failed:", e2, flush=True)

    def ensure_dir(d):
        parts = d.strip("/").split("/")
        for i in range(1, len(parts) + 1):
            sub = "/" + "/".join(parts[:i])
            if sub in made:
                continue
            try:
                state["f"].mkd(sub)
            except ftplib.error_perm:
                pass  # usually "already exists"; a real failure surfaces on the STOR below
            made.add(sub)

    def remote_size(p):
        """Size of p on the server, or None if it does not exist."""
        f = state["f"]
        if not state["no_size"]:
            try:
                return f.size(p)
            except ftplib.error_perm as e:
                if not str(e).startswith(("500", "502", "504")):
                    return None  # 550: no such file
                state["no_size"] = True  # server lacks SIZE: fall back to listing the folder
        parent, name = p.rsplit("/", 1)
        try:
            for n, fa in f.mlsd(parent or "/"):
                if n == name and fa.get("type") == "file":
                    return int(fa.get("size", 0) or 0)
        except ftplib.error_perm:
            pass
        return None

    def remote_sha(p):
        d = hashlib.sha256()
        state["f"].retrbinary("RETR " + p, d.update, blocksize=1 << 20)
        return d.hexdigest()

    stamp = time.strftime("%Y%m%d-%H%M%S")
    started = set()  # files this run began uploading: a partial copy left by a dropped upload is ours
    streak = PermanentStreak()
    done, bad, conflicts, kept = 0, [], [], []
    for i, (p, size, h) in enumerate(entries, 1):
        local = os.path.join(src, *p.strip("/").split("/"))
        for attempt in range(20):
            try:
                rs = remote_size(p)
                if rs is not None and p not in started:
                    same = rs == size and (size >= HASH_LIMIT or size == 0 or remote_sha(p) == h)
                    if same:
                        break  # already there
                    if not force:
                        conflicts.append(p)
                        break
                    keep_path = os.path.join(src, "_device-copies-" + stamp, *p.strip("/").split("/"))
                    os.makedirs(os.path.dirname(keep_path), exist_ok=True)
                    with open(keep_path, "wb") as out:
                        state["f"].retrbinary("RETR " + p, out.write, blocksize=1 << 20)
                    kept.append(keep_path)
                ensure_dir(p.rsplit("/", 1)[0])
                started.add(p)
                with open(local, "rb") as fh:
                    state["f"].storbinary("STOR " + p, fh, blocksize=1 << 20)
                streak.ok()
                if size == 0 or remote_size(p) == size:
                    break
                print(f"  size mismatch after upload, retrying {p}", flush=True)
            except Exception as e:
                if is_permanent(e):
                    streak.fail(p, e)
                    bad.append((p, str(e)))
                    break
                if not isinstance(e, TRANSIENT):
                    raise
                print(f"  retry {attempt + 1} {p}: {e}", flush=True)
                reconnect()
        else:
            bad.append((p, "upload failed"))
        done += size
        if size > 50e6 or i % 20 == 0 or i == len(entries):
            print(f"[{i}/{len(entries)}] {done / 1e9:.2f}/{total / 1e9:.2f} GB  {p}", flush=True)

    print("verifying...", flush=True)
    failed = {p for p, _ in bad} | set(conflicts)
    for p, size, h in entries:
        if p in failed:
            continue
        for attempt in range(5):
            try:
                rs = remote_size(p) if size > 0 else 0
                if rs != size:
                    bad.append((p, f"size {rs} != {size}"))
                elif 0 < size < HASH_LIMIT and remote_sha(p) != h:
                    bad.append((p, "sha256 mismatch"))
                break
            except TRANSIENT as e:
                print(f"  verify retry {p}: {e}", flush=True)
                reconnect()
        else:
            bad.append((p, "could not verify"))
    for p in conflicts:
        print("CONFLICT (device copy differs, left alone; --force saves it, then replaces):", p)
    for k in kept:
        print("saved device copy before replacing:", k)
    print("PROBLEMS:", bad if bad else "none")
    ok = not bad and not conflicts
    print("RESTORE COMPLETE" if ok else "RESTORE INCOMPLETE")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
