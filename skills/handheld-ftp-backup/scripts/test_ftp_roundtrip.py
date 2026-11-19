"""Round-trip the three FTP scripts against an in-memory fake FTP server: inventory -> backup -> wipe
-> restore, and check every byte came back. The scripts run unmodified via runpy."""
import ftplib
import io
import os
import runpy
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))


class FakeFTP:
    files = {}  # path -> bytes, shared like a real server
    dirs = set()

    def connect(self, host, port, timeout=None):
        pass

    def login(self, *a):
        pass

    def voidcmd(self, cmd):
        pass

    def mlsd(self, path):
        path = path.rstrip("/") or ""
        seen = set()
        for p, data in self.files.items():
            if p.startswith(path + "/"):
                rest = p[len(path) + 1:]
                head = rest.split("/", 1)[0]
                if "/" in rest:
                    if head not in seen:
                        seen.add(head)
                        yield head, {"type": "dir"}
                else:
                    yield head, {"type": "file", "size": str(len(data)), "modify": "20260101000000"}

    def retrbinary(self, cmd, callback, blocksize=8192, rest=None):
        data = self.files[cmd[5:]][rest or 0:]
        for i in range(0, len(data), 7):  # small chunks to exercise appends
            callback(data[i:i + 7])

    def storbinary(self, cmd, fh, blocksize=8192):
        self.files[cmd[5:]] = fh.read()

    def mkd(self, d):
        if d in self.dirs:
            raise ftplib.error_perm("550 exists")
        self.dirs.add(d)

    def size(self, p):
        if p not in self.files:
            raise ftplib.error_perm("550 no such file")
        return len(self.files[p])


def run(script, *args):
    old = sys.argv
    sys.argv = [script] + list(args)
    out = io.StringIO()
    real = sys.stdout
    sys.stdout = out
    try:
        runpy.run_path(os.path.join(HERE, script), run_name="__main__")
    except SystemExit as e:  # the scripts end with sys.exit(code); messages go to the output
        if e.code not in (0, 1, None):
            out.write(str(e.code))
    finally:
        sys.argv, sys.stdout = old, real
    return out.getvalue()


@pytest.fixture
def server(monkeypatch):
    FakeFTP.files = {
        "/Switch/game.xci": os.urandom(5000),
        "/roms/nds/saves/a.sav": os.urandom(512),
        "/roms/nds/empty.txt": b"",
        "/roms/._junk": b"mac",
        "/Nintendo 3DS/big.bin": os.urandom(3000),
    }
    FakeFTP.dirs = set()
    monkeypatch.setattr(ftplib, "FTP", FakeFTP)
    return FakeFTP


def test_inventory_backup_restore_round_trip(server, tmp_path):
    inv = str(tmp_path / "inv.tsv")
    out = run("ftpdu.py", "h", "21", "/", inv)
    assert "files 5" in out
    original = dict(server.files)

    dest = str(tmp_path / "backup")
    out = run("ftpbackup.py", "h", "21", inv, dest, "/Switch/", "/roms/")
    assert "BACKUP COMPLETE" in out
    manifest = open(os.path.join(dest, "MANIFEST.sha256"), encoding="utf-8").read()
    assert "/roms/._junk" not in manifest and "Nintendo 3DS" not in manifest
    assert os.path.getsize(os.path.join(dest, "roms", "nds", "empty.txt")) == 0

    server.files = {}  # "reformat the card"
    out = run("ftprestore.py", "h", "21", dest)
    assert "RESTORE COMPLETE" in out
    for p in ("/Switch/game.xci", "/roms/nds/saves/a.sav", "/roms/nds/empty.txt"):
        assert server.files[p] == original[p]
    assert "/Nintendo 3DS/big.bin" not in server.files


def test_restore_skip_prefix(server, tmp_path):
    inv = str(tmp_path / "inv.tsv")
    run("ftpdu.py", "h", "21", "/", inv)
    dest = str(tmp_path / "b")
    run("ftpbackup.py", "h", "21", inv, dest, "/Switch/", "/roms/")
    server.files = {}
    run("ftprestore.py", "h", "21", dest, "--skip", "/Switch/")
    assert "/Switch/game.xci" not in server.files
    assert "/roms/nds/saves/a.sav" in server.files


def test_backup_resumes_a_partial_file(server, tmp_path):
    inv = str(tmp_path / "inv.tsv")
    run("ftpdu.py", "h", "21", "/", inv)
    dest = str(tmp_path / "b")
    part = os.path.join(dest, "Switch", "game.xci")
    os.makedirs(os.path.dirname(part))
    with open(part, "wb") as f:
        f.write(server.files["/Switch/game.xci"][:1234])  # an interrupted earlier run
    out = run("ftpbackup.py", "h", "21", inv, dest, "/Switch/", "--resume")
    assert "BACKUP COMPLETE" in out
    assert open(part, "rb").read() == server.files["/Switch/game.xci"]


def test_second_backup_into_the_same_folder_is_refused_and_resume_refetches_saves(server, tmp_path):
    inv = str(tmp_path / "inv.tsv")
    run("ftpdu.py", "h", "21", "/", inv)
    dest = str(tmp_path / "b")
    run("ftpbackup.py", "h", "21", inv, dest, "/roms/")
    server.files["/roms/nds/saves/a.sav"] = b"N" * 512  # the game saved again: same size, new bytes
    out = run("ftpbackup.py", "h", "21", inv, dest, "/roms/")
    assert "not empty" in out
    out = run("ftpbackup.py", "h", "21", inv, dest, "/roms/", "--resume")
    assert "BACKUP COMPLETE" in out
    assert open(os.path.join(dest, "roms", "nds", "saves", "a.sav"), "rb").read() == b"N" * 512


def test_restore_never_overwrites_a_different_device_file_without_force(server, tmp_path):
    inv = str(tmp_path / "inv.tsv")
    run("ftpdu.py", "h", "21", "/", inv)
    dest = str(tmp_path / "b")
    run("ftpbackup.py", "h", "21", inv, dest, "/roms/")
    newer = b"NEWER-SAVE" * 60
    server.files["/roms/nds/saves/a.sav"] = newer
    out = run("ftprestore.py", "h", "21", dest)
    assert "CONFLICT" in out and "RESTORE INCOMPLETE" in out
    assert server.files["/roms/nds/saves/a.sav"] == newer  # untouched
    out = run("ftprestore.py", "h", "21", dest, "--force")
    assert "RESTORE COMPLETE" in out
    kept = [os.path.join(r, n) for r, _d, fs in os.walk(dest) for n in fs if "_device-copies-" in r]
    assert len(kept) == 1 and open(kept[0], "rb").read() == newer  # saved before replacing


def test_permanent_errors_abort_fast(server, tmp_path, monkeypatch):
    inv = str(tmp_path / "inv.tsv")
    run("ftpdu.py", "h", "21", "/", inv)
    dest = str(tmp_path / "b")
    run("ftpbackup.py", "h", "21", inv, dest, "/Switch/", "/roms/")
    server.files = {}

    def refuse(self, cmd, fh, blocksize=8192):
        raise ftplib.error_perm("550 root folder no longer exists")
    monkeypatch.setattr(FakeFTP, "storbinary", refuse)
    out = run("ftprestore.py", "h", "21", dest)
    assert "permanent FTP errors in a row" in out or "PROBLEMS" in out
    assert server.files == {}


def test_a_dropped_upload_is_retried_not_reported_as_a_conflict(server, tmp_path, monkeypatch):
    inv = str(tmp_path / "inv.tsv")
    run("ftpdu.py", "h", "21", "/", inv)
    dest = str(tmp_path / "b")
    run("ftpbackup.py", "h", "21", inv, dest, "/Switch/")
    original = server.files["/Switch/game.xci"]
    server.files = {}
    real = FakeFTP.storbinary
    calls = {"n": 0}

    def flaky(self, cmd, fh, blocksize=8192):
        calls["n"] += 1
        if calls["n"] == 1:  # first upload dies halfway, leaving a partial file on the device
            self.files[cmd[5:]] = fh.read()[:100]
            raise EOFError("connection dropped")
        return real(self, cmd, fh, blocksize)
    monkeypatch.setattr(FakeFTP, "storbinary", flaky)
    monkeypatch.setattr("time.sleep", lambda s: None)
    out = run("ftprestore.py", "h", "21", dest)
    assert "CONFLICT" not in out and "RESTORE COMPLETE" in out
    assert server.files["/Switch/game.xci"] == original
