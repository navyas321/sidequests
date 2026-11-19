import json
import os

import pytest

import modledger as ml


def _write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


@pytest.fixture
def game(tmp_path):
    g = tmp_path / "game"
    _write(str(g / "game.exe"), b"exe")
    _write(str(g / "data" / "pak0.bin"), b"x" * 1000)
    return str(g)


def test_diff_reports_added_changed_removed(game, tmp_path):
    base = ml.snapshot(game)
    _write(os.path.join(game, "winmm.dll"), b"proxy")
    _write(os.path.join(game, "reshade-shaders", "a.fx"), b"fx")
    _write(os.path.join(game, "data", "pak0.bin"), b"y" * 1000)  # same size, new content
    os.remove(os.path.join(game, "game.exe"))
    res = ml.diff(game, base)
    assert res["added"] == ["reshade-shaders/a.fx", "winmm.dll"]
    assert res["changed"] == ["data/pak0.bin"]
    assert res["removed"] == ["game.exe"]


def test_quick_mode_uses_size_and_mtime_for_big_files(game):
    assert "sha256" in ml.snapshot(game, quick_mb=0)["files"]["data/pak0.bin"]  # 0 = hash everything
    big = os.path.join(game, "data", "big.pak")
    _write(big, b"a" * (1024 * 1024 + 10))  # just over 1 MB
    base = ml.snapshot(game, quick_mb=1)
    assert set(base["files"]["data/big.pak"]) == {"size", "mtime"}
    st = os.stat(big)
    _write(big, b"b" * (1024 * 1024 + 10))  # same size, new content...
    os.utime(big, (st.st_atime, st.st_mtime + 5))  # ...and a new timestamp: detected
    assert ml.diff(game, base)["changed"] == ["data/big.pak"]
    os.utime(big, (st.st_atime, st.st_mtime))  # timestamp preserved: quick mode cannot see it (documented)
    assert ml.diff(game, base)["changed"] == []


def test_park_then_restore_round_trip(game, tmp_path):
    base = ml.snapshot(game)
    _write(os.path.join(game, "winmm.dll"), b"proxy")
    _write(os.path.join(game, "mods", "x.ini"), b"k=v")
    park = str(tmp_path / "parked")
    added = ml.diff(game, base)["added"]
    ml.park(game, "mymod", park, added)
    assert ml.diff(game, base) == {"added": [], "changed": [], "removed": []}
    man = json.load(open(os.path.join(park, "manifest.json"), encoding="utf-8"))
    assert set(man["mymod"]["files"]) == {"mods/x.ini", "winmm.dll"}
    restored = ml.restore(park, "mymod")
    assert sorted(restored) == ["mods/x.ini", "winmm.dll"]
    assert open(os.path.join(game, "winmm.dll"), "rb").read() == b"proxy"
    assert os.path.exists(os.path.join(park, "mymod", "winmm.dll"))  # parked copy kept


def test_restore_refuses_tampered_parked_copy(game, tmp_path):
    _write(os.path.join(game, "winmm.dll"), b"proxy")
    park = str(tmp_path / "parked")
    ml.park(game, "m", park, ["winmm.dll"])
    _write(os.path.join(park, "m", "winmm.dll"), b"evil")
    with pytest.raises(SystemExit):
        ml.restore(park, "m")
    assert not os.path.exists(os.path.join(game, "winmm.dll"))


def test_restore_will_not_clobber_a_different_file_without_force(game, tmp_path):
    _write(os.path.join(game, "winmm.dll"), b"proxy")
    park = str(tmp_path / "parked")
    ml.park(game, "m", park, ["winmm.dll"])
    _write(os.path.join(game, "winmm.dll"), b"another mod")
    with pytest.raises(SystemExit):
        ml.restore(park, "m")
    assert open(os.path.join(game, "winmm.dll"), "rb").read() == b"another mod"
    ml.restore(park, "m", force=True)
    assert open(os.path.join(game, "winmm.dll"), "rb").read() == b"proxy"


def test_park_missing_file_deletes_nothing(game, tmp_path):
    _write(os.path.join(game, "winmm.dll"), b"proxy")
    with pytest.raises(SystemExit):
        ml.park(game, "m", str(tmp_path / "p"), ["winmm.dll", "nope.dll"])
    assert os.path.exists(os.path.join(game, "winmm.dll"))


def test_parking_twice_under_one_name_is_refused(game, tmp_path):
    _write(os.path.join(game, "winmm.dll"), b"v1")
    park = str(tmp_path / "p")
    ml.park(game, "m", park, ["winmm.dll"])
    _write(os.path.join(game, "winmm.dll"), b"v2")
    with pytest.raises(SystemExit):
        ml.park(game, "m", park, ["winmm.dll"])
    assert open(os.path.join(park, "m", "winmm.dll"), "rb").read() == b"v1"  # first set intact
    assert os.path.exists(os.path.join(game, "winmm.dll"))  # second original not deleted


def test_paths_outside_the_game_folder_are_refused(game, tmp_path):
    _write(str(tmp_path / "other" / "save.dat"), b"save")
    for bad in ("../other/save.dat", str(tmp_path / "other" / "save.dat")):
        with pytest.raises(SystemExit):
            ml.park(game, "m", str(tmp_path / "p"), [bad])
    assert os.path.exists(str(tmp_path / "other" / "save.dat"))


def test_restore_into_a_moved_game_folder(game, tmp_path):
    _write(os.path.join(game, "winmm.dll"), b"proxy")
    park = str(tmp_path / "p")
    ml.park(game, "m", park, ["winmm.dll"])
    moved = str(tmp_path / "moved")
    os.rename(game, moved)
    with pytest.raises(SystemExit):
        ml.restore(park, "m")  # recorded folder is gone: refuse instead of recreating it
    assert not os.path.exists(game)
    ml.restore(park, "m", game_dir=moved)
    assert open(os.path.join(moved, "winmm.dll"), "rb").read() == b"proxy"


def test_baseline_saved_inside_the_game_folder_is_not_parked(game, tmp_path, capsys):
    base = os.path.join(game, "baseline.json")
    assert ml.main(["snapshot", game, "-o", base]) == 0
    _write(os.path.join(game, "dxgi.dll"), b"r")
    park = str(tmp_path / "p")
    assert ml.main(["park", game, "--name", "r", "--to", park, "--added-since", base]) == 0
    assert os.path.exists(base)
    assert "left out" in capsys.readouterr().out


def test_list_without_a_manifest_explains(tmp_path):
    with pytest.raises(SystemExit) as e:
        ml.main(["list", str(tmp_path)])
    assert "nothing has been parked" in str(e.value)


def test_cli_snapshot_and_list(game, tmp_path, capsys):
    out = str(tmp_path / "base.json")
    assert ml.main(["snapshot", game, "-o", out]) == 0
    _write(os.path.join(game, "dxgi.dll"), b"r")
    park = str(tmp_path / "p")
    assert ml.main(["park", game, "--name", "reshade", "--to", park, "--added-since", out]) == 0
    assert ml.main(["list", park]) == 0
    assert "reshade" in capsys.readouterr().out
