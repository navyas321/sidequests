import ping_report as pr


def _csv(tmp_path, header, rows):
    p = tmp_path / "p.csv"
    p.write_text(",".join(header) + "\n" + "\n".join(",".join(map(str, r)) for r in rows) + "\n", encoding="utf-8")
    return str(p)


def test_device_side_plateaus_exonerate_the_network(tmp_path):
    rows = []
    for i in range(100):
        dev = 120 if 20 <= i < 26 or 60 <= i < 64 else 6
        rows.append([i * 700, 2, 5, dev])
    path = _csv(tmp_path, ["t_ms", "gw", "tv", "handheld"], rows)
    res = pr.analyse(*pr.load(path), high_ms=30, suspect="handheld")
    hh = res["targets"]["handheld"]
    assert hh["high"] == 10 and hh["plateaus"] == 2 and hh["spikes"] == 0
    assert res["overlap"]["gw|handheld"]["both"] == 0
    assert res["verdict"].startswith("network exonerated")


def test_shared_cause_when_everyone_spikes_together(tmp_path):
    rows = []
    for i in range(50):
        bad = i in (10, 11, 12, 30, 31)
        rows.append([i * 700, 80 if bad else 2, 90 if bad else 5, 95 if bad else 6])
    res = pr.analyse(*pr.load(_csv(tmp_path, ["t_ms", "gw", "tv", "pc"], rows)), suspect="pc")
    assert res["verdict"].startswith("shared cause likely")


def test_loss_counts_as_high_and_is_reported(tmp_path):
    rows = [[0, 2, -1], [700, 2, -1], [1400, 2, 4], [2100, 2, 5]]
    res = pr.analyse(*pr.load(_csv(tmp_path, ["t_ms", "gw", "dev"], rows)), suspect="dev")
    assert res["targets"]["dev"]["lost"] == 2
    assert res["targets"]["dev"]["p50"] == 4.5
    assert res["targets"]["dev"]["spikes"] == 1


def test_quiet_run_says_reproduce(tmp_path):
    rows = [[i * 700, 2, 5] for i in range(20)]
    res = pr.analyse(*pr.load(_csv(tmp_path, ["t_ms", "gw", "dev"], rows)), suspect="dev")
    assert "reproduce" in res["verdict"]


def test_one_isolated_spike_is_not_enough_to_clear_the_network(tmp_path):
    rows = [[i * 700, 2, 5, 90 if i == 50 else 6] for i in range(200)]
    res = pr.analyse(*pr.load(_csv(tmp_path, ["t_ms", "gw", "tv", "dev"], rows)), suspect="dev")
    assert res["verdict"].startswith("too little evidence")


def test_unknown_suspect_is_an_error(tmp_path):
    rows = [[i * 700, 2, 5] for i in range(5)]
    path = _csv(tmp_path, ["t_ms", "gw", "dev"], rows)
    try:
        pr.analyse(*pr.load(path), suspect="192.168.1.99")
        assert False
    except ValueError as e:
        assert "not a column" in str(e)


def test_short_last_row_from_a_stopped_recorder_is_ignored(tmp_path):
    p = tmp_path / "p.csv"
    p.write_text("t_ms,gw,dev\n0,2,5\n700,2,6\n1400,2\n", encoding="utf-8")
    targets, series = pr.load(str(p))
    assert series["dev"] == [5.0, 6.0]


def test_percentiles_interpolate():
    assert pr.pct([1, 2, 3, 4], 50) == 2.5
    assert pr.pct([], 50) is None


def test_cli_text_output(tmp_path, capsys):
    rows = [[i * 700, 2, 50 if i == 3 else 5] for i in range(10)]
    assert pr.main([_csv(tmp_path, ["t_ms", "gw", "dev"], rows), "--suspect", "dev"]) == 0
    assert "VERDICT" in capsys.readouterr().out
