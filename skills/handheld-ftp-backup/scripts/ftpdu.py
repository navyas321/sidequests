"""Inventory an FTP tree (stdlib only). Writes every entry as TSV (type, path, size, mtime) and prints
per-top-level-folder totals. Folders it could not list are reported and the run is marked INCOMPLETE.

usage: python ftpdu.py HOST PORT ROOT OUT.tsv
example: python ftpdu.py 192.168.1.50 2221 / sd-inventory.tsv

Needs a server that supports MLSD (most Android FTP server apps do). Login: see ftpcommon.py.
Git Bash on Windows rewrites arguments starting with "/" into Windows paths: export MSYS_NO_PATHCONV=1 first.
"""
import collections
import ftplib
import sys
import time

from ftpcommon import TRANSIENT, connect


def main(argv):
    host, port, root, out = argv[0], int(argv[1]), argv[2], argv[3]
    f = connect(host, port)
    gave_up = []

    def ls(path):
        nonlocal f
        for _ in range(5):
            try:
                return [(n, fa) for n, fa in f.mlsd(path)
                        if fa.get("type") not in ("cdir", "pdir") and n not in (".", "..")]
            except ftplib.error_perm as e:
                if str(e).startswith(("500", "502", "504")):
                    raise SystemExit("this server does not support MLSD (%s); use an FTP server app that does" % e)
                print("cannot list", path, e, file=sys.stderr)
                gave_up.append(path)
                return []
            except TRANSIENT as e:
                print("retry", path, e, file=sys.stderr)
                time.sleep(3)
                try:
                    f = connect(host, port)
                except Exception:
                    pass
        print("GAVE UP", path, file=sys.stderr)
        gave_up.append(path)
        return []

    rows, stack = [], [root]
    while stack:
        d = stack.pop()
        for n, fa in ls(d):
            p = d.rstrip("/") + "/" + n
            if fa.get("type") == "dir":
                stack.append(p)
                rows.append(("D", p, 0, fa.get("modify", "")))
            else:
                rows.append(("F", p, int(fa.get("size", 0) or 0), fa.get("modify", "")))

    with open(out, "w", encoding="utf-8") as o:
        for r in rows:
            o.write("\t".join(map(str, r)) + "\n")

    top = collections.defaultdict(lambda: [0, 0])
    for t, p, s, _ in rows:
        if t == "F":
            parts = p.split("/")
            k = "/" + parts[1] if len(parts) > 2 else "(root files)"
            top[k][0] += s
            top[k][1] += 1
    for k, (s, c) in sorted(top.items(), key=lambda x: -x[1][0]):
        print(f"{s / 1e9:9.2f} GB {c:7d} files  {k}")
    print("files", sum(1 for r in rows if r[0] == "F"), "bytes", sum(r[2] for r in rows))
    if gave_up:
        print("INCOMPLETE: could not list %d folder(s): %s" % (len(gave_up), ", ".join(gave_up[:10])))
    return 1 if gave_up else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
