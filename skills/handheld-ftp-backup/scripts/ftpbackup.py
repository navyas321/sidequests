"""Back up selected folders from an FTP inventory (made by ftpdu.py) to a local folder (stdlib only).
Retries dropped connections, checks every size, creates empty files too, skips macOS junk
(._* and .DS_Store), and writes MANIFEST.sha256 (sha256, size, remote path).

usage: python ftpbackup.py HOST PORT INVENTORY.tsv DEST_DIR PREFIX [PREFIX ...] [--resume]
example: python ftpbackup.py 192.168.1.50 2221 sd-inventory.tsv D:/backups/handheld-2026-11-18 /Switch/ /roms/

Use a NEW, dated DEST_DIR for every backup. DEST_DIR must be empty unless --resume is given to
continue an interrupted run of the same inventory; even then, files up to 16 MB (saves, configs)
are always downloaded again in full, because a same-size local copy may be an older save. Only
large files resume from where they stopped. Login: see ftpcommon.py.
"""
import hashlib
import os
import sys
import time

from ftpcommon import TRANSIENT, PermanentStreak, connect, is_permanent

ALWAYS_REFETCH = 16 * 1024 * 1024


def junk(p):
    b = p.rsplit("/", 1)[-1]
    return b.startswith("._") or b == ".DS_Store"


def main(argv):
    resume = "--resume" in argv
    argv = [a for a in argv if a != "--resume"]
    host, port, inv, dest = argv[0], int(argv[1]), argv[2], argv[3]
    keep = tuple(argv[4:])
    if not keep:
        sys.exit("give at least one remote path prefix to keep, e.g. /Switch/")
    if os.path.isdir(dest) and os.listdir(dest) and not resume:
        sys.exit("%s is not empty. Use a new dated folder, or --resume to continue an interrupted run." % dest)

    files = []
    for line in open(inv, encoding="utf-8"):
        t, p, s, _ = line.rstrip("\n").split("\t")
        if t == "F" and p.startswith(keep) and not junk(p):
            files.append((p, int(s)))
    total = sum(s for _, s in files)
    print(f"{len(files)} files, {total / 1e9:.2f} GB", flush=True)

    def local_path(p):
        return os.path.join(dest, *p.strip("/").split("/"))

    f = connect(host, port)
    streak = PermanentStreak()
    failed, done, aborted = [], 0, None
    for i, (p, size) in enumerate(files, 1):
        if aborted:
            break
        local = local_path(p)
        try:
            os.makedirs(os.path.dirname(local), exist_ok=True)
            if os.path.exists(local) and size <= ALWAYS_REFETCH:
                os.remove(local)  # small files are never trusted from an earlier run
        except OSError as e:  # e.g. a remote name that is illegal on Windows (':', 'CON', trailing dot)
            failed.append((p, "local path: %s" % e))
            continue
        try:
            open(local, "ab").close()  # a name Windows rejects fails here, once, not as a network error
        except OSError as e:
            failed.append((p, "local file: %s" % e))
            continue
        if size == 0:
            continue
        ok = False
        for attempt in range(30):
            have = os.path.getsize(local) if os.path.exists(local) else 0
            if have == size:
                ok = True
                break
            if have > size:
                os.remove(local)
                have = 0
            try:
                with open(local, "ab") as out:
                    f.retrbinary("RETR " + p, out.write, blocksize=1 << 20, rest=have or None)
                streak.ok()
            except Exception as e:
                if is_permanent(e):
                    failed.append((p, str(e)))
                    try:
                        streak.fail(p, e)
                    except SystemExit as stop:  # stop downloading, but still write the manifest below
                        aborted = str(stop)
                    break
                if not isinstance(e, TRANSIENT):
                    raise
                print(f"  retry {attempt + 1} {p}: {e}", flush=True)
                time.sleep(5)
                try:
                    f = connect(host, port)
                except Exception as e2:
                    print("  reconnect failed:", e2, flush=True)
        else:
            failed.append((p, "gave up after 30 attempts"))
        if not ok:
            print("  incomplete:", p, flush=True)  # a partial large file can be continued with --resume
        done += size
        if size > 50e6 or i % 25 == 0 or i == len(files):
            print(f"[{i}/{len(files)}] {done / 1e9:.2f}/{total / 1e9:.2f} GB  {p}", flush=True)

    bad = []
    with open(os.path.join(dest, "MANIFEST.sha256"), "w", encoding="utf-8") as man:
        for p, size in files:
            local = local_path(p)
            got = os.path.getsize(local) if os.path.exists(local) else -1
            if got != size:
                bad.append((p, size, got))
                continue
            h = hashlib.sha256()
            with open(local, "rb") as fh:
                for chunk in iter(lambda: fh.read(1 << 22), b""):
                    h.update(chunk)
            man.write(f"{h.hexdigest()}  {size}  {p}\n")
    for p, why in failed:
        print("FAILED", p, why)
    if aborted:
        print("STOPPED EARLY:", aborted)
        bad.append(("(run stopped early)", 0, 0))
    print("SIZE MISMATCHES:", bad if bad else "none")
    print("BACKUP COMPLETE" if not bad else "BACKUP INCOMPLETE")
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
