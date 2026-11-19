import math
import os

import abtest as ab


def test_perfect_separation_gives_the_smallest_possible_p():
    a, b = [10, 11, 12, 13], [20, 21, 22, 23]
    p = ab.permutation_p(a, b)
    assert math.isclose(p, 2 / 70)  # 70 splits of 8 into 4+4; the real one and its mirror


def test_identical_groups_give_p_one():
    assert ab.permutation_p([5, 5, 5], [5, 5, 5]) == 1.0


def test_overlapping_groups_are_not_significant():
    p = ab.permutation_p([17.4, 19.5, 16.0, 16.7], [20.4, 17.0, 22.1, 22.0])
    assert 0.05 < p < 0.5


def test_runs_needed_grows_with_noise():
    tight = ab.runs_needed([10, 10.1, 9.9, 10], [11, 11.1, 10.9, 11])
    noisy = ab.runs_needed([8, 12, 9, 11], [9, 13, 10, 12])
    assert tight < noisy


def _pm(path, intervals, latency=None, dropped=()):
    lines = ["Application,MsBetweenDisplayChange,MsUntilDisplayed,Dropped"]
    for i, v in enumerate(intervals):
        lat = latency[i] if latency else ""
        lines.append("game.exe,%s,%s,%d" % (v, lat, 1 if i in dropped else 0))
    lines.append("other.exe,500,1,0")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_presentmon_run_metrics(tmp_path):
    p = tmp_path / "run1-balanced.csv"
    ints = [16.7] * 90 + [25.0] * 9 + [0]
    _pm(p, ints, latency=[7.0] * 100, dropped=(99,))
    m = ab.presentmon_run(str(p), app="game.exe", hitch_ms=25)
    assert m["frames"] == 100
    assert m["dropped_pct"] == 1.0
    assert m["hitch_pct"] == round(100 * 9 / 99, 3)
    assert 55 < m["fps_shown"] < 60
    assert m["latency_p50_ms"] == 7.0


def test_presentmon_dir_reads_mode_from_file_name(tmp_path, capsys):
    for i in range(3):
        _pm(tmp_path / ("r%d-balanced.csv" % i), [16.7] * 50 + [25.0] * 5)
        _pm(tmp_path / ("r%d-lowlat.csv" % i), [16.7] * 50 + [25.0] * 10)
    _pm(tmp_path / "unlabeled.csv", [16.7] * 10)
    runs = ab.load_presentmon_dir(str(tmp_path), ["balanced", "lowlat"], app="game.exe")
    assert len(runs) == 6
    rows = {r["metric"]: r for r in ab.compare(runs, "balanced", "lowlat")}
    assert rows["hitch_pct"]["diff"] < 0
    assert ab.main(["presentmon", str(tmp_path), "--modes", "balanced,lowlat", "--app", "game.exe"]) == 0
    out = capsys.readouterr().out
    assert "smallest p this design can show: 0.1000" in out


def test_presentmon_v1_lowercase_header(tmp_path):
    p = tmp_path / "legacy.csv"
    p.write_text(
        "Application,ProcessID,Dropped,TimeInSeconds,msBetweenPresents,msUntilDisplayed,msBetweenDisplayChange\n"
        "game.exe,1,0,0.01,16.6,6.0,16.7\n"
        "game.exe,1,1,0.03,16.6,0,0\n"
        "game.exe,1,0,0.05,16.6,7.0,33.4\n",
        encoding="utf-8")
    m = ab.presentmon_run(str(p), app="game.exe", hitch_ms=25)
    assert m["frames"] == 3 and m["dropped_pct"] == round(100 / 3, 4)
    assert m["hitch_pct"] == 50.0  # 33.4 of the two shown frames
    assert m["latency_p50_ms"] == 6.5


def test_min_p_equal_and_unequal_groups():
    assert math.isclose(ab.min_p(4, 4), 2 / 70)
    assert math.isclose(ab.min_p(3, 5), 1 / 56)  # no mirror split when sizes differ
    assert math.isclose(ab.permutation_p([1, 2, 3], [10, 11, 12, 13, 14]), 1 / 56)


def test_runs_needed_never_below_what_the_test_can_pass():
    assert ab.min_runs_per_mode() == 4
    assert ab.runs_needed([10, 10.2, 9.9, 10.1], [11, 11.2, 10.9, 11.1]) >= 4


def test_sampled_p_is_never_zero():
    a, b = list(range(12)), list(range(100, 112))
    p = ab.permutation_p(a, b, max_splits=2000)
    assert 0 < p <= 1 / 2000 + 1e-9


def test_mode_labels_match_whole_tokens():
    assert ab.mode_of("03-nogsync.csv", ["gsync", "nogsync"]) == "nogsync"
    assert ab.mode_of("04_gsync_run.csv", ["gsync", "nogsync"]) == "gsync"
    assert ab.mode_of("notes.csv", ["gsync", "nogsync"]) is None


def test_mixed_processes_need_app_and_bad_files_are_skipped(tmp_path, capsys):
    _pm(tmp_path / "1-a.csv", [16.7] * 20)  # contains game.exe AND other.exe
    try:
        ab.presentmon_run(str(tmp_path / "1-a.csv"))
        assert False, "mixed processes must require --app"
    except ValueError as e:
        assert "--app" in str(e)
    for i in range(2):
        _pm(tmp_path / ("r%d-a.csv" % i), [16.7] * 20)
        _pm(tmp_path / ("r%d-b.csv" % i), [16.7] * 20)
    (tmp_path / "r9-b.csv").write_text("Application,Foo\nx.exe,1\n", encoding="utf-8")
    skipped = []
    runs = ab.load_presentmon_dir(str(tmp_path), ["a", "b"], app="game.exe", skipped=skipped)
    assert len(runs) == 5 and [s[0] for s in skipped] == ["r9-b.csv"]


def test_runs_csv(tmp_path):
    p = tmp_path / "runs.csv"
    p.write_text("run,mode,hitch_pct\n1,A,17\n2,B,20\n3,A,18\n4,B,21\n", encoding="utf-8")
    rows = ab.compare(ab.load_runs_csv(str(p)), "A", "B")
    assert rows[0]["metric"] == "hitch_pct" and rows[0]["diff"] == -3.0
