import os

import pytest

import journal as j


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def test_init_then_add_change_rows_in_order(tmp_path):
    repo = str(tmp_path / "cfg")
    j.init(repo, "Gaming PC config", "Streaming host")
    r1 = j.add(repo, "Wi-Fi roaming: Lowest", "Roaming aggressiveness to Lowest", date="2026-10-25")
    r2 = j.add(repo, "Startup trim", "Edge auto-launch off | reversible", date="2026-11-06")
    assert r1 == "docs/2026-10-25-wi-fi-roaming-lowest.md"
    readme = read(os.path.join(repo, "README.md"))
    rows = [ln for ln in readme.splitlines() if ln.startswith("| 2026-")]
    assert rows[0].startswith("| 2026-10-25 | [Wi-Fi roaming: Lowest](docs/2026-10-25-wi-fi-roaming-lowest.md)")
    assert rows[1].startswith("| 2026-11-06 |") and "Edge auto-launch off / reversible" in rows[1]
    # rows stay inside the change-log section, before Analyses
    assert readme.index(rows[1]) < readme.index("## Analyses")
    doc = read(os.path.join(repo, *r2.split("/")))
    for heading in ("## Before", "## Reversal", "## Ruled out", "## Amendments after review"):
        assert heading in doc


def test_analysis_and_runbook_links_go_in_their_sections(tmp_path):
    repo = str(tmp_path / "cfg")
    j.init(repo, "Handheld config", "")
    j.add(repo, "Usage log analysis", "Token and error breakdown", date="2026-08-15", kind="analysis")
    j.add(repo, "Media stack rebuild", "Install and wire the stack", date="2026-08-16", kind="runbook")
    readme = read(os.path.join(repo, "README.md"))
    a = readme.index("## Analyses")
    r = readme.index("## Rebuild runbooks")
    g = readme.index("## Guiding rules")
    assert a < readme.index("docs/2026-08-15-usage-log-analysis.md") < r
    assert r < readme.index("docs/2026-08-16-media-stack-rebuild.md") < g


def test_add_never_overwrites(tmp_path):
    repo = str(tmp_path / "cfg")
    j.init(repo, "X", "")
    j.add(repo, "Same title", "one", date="2026-01-01")
    with pytest.raises(SystemExit):
        j.add(repo, "Same title", "two", date="2026-01-01")


def test_init_refuses_existing_readme(tmp_path):
    repo = str(tmp_path / "cfg")
    j.init(repo, "X", "")
    with pytest.raises(SystemExit):
        j.init(repo, "X", "")


def test_add_works_on_a_readme_without_the_section(tmp_path):
    repo = tmp_path / "cfg"
    (repo / "docs").mkdir(parents=True)
    (repo / "README.md").write_text("# Old repo\n\nSome notes.\n", encoding="utf-8")
    j.add(str(repo), "First entry", "did a thing", date="2026-02-02")
    readme = (repo / "README.md").read_text(encoding="utf-8")
    assert "## Change log" in readme and "| 2026-02-02 |" in readme


def test_slugify():
    assert j.slugify("DLSS 5: MW4 & Cyberpunk!") == "dlss-5-mw4-cyberpunk"
    assert j.slugify("***") == "entry"


def test_pipe_in_title_does_not_break_the_table(tmp_path):
    repo = str(tmp_path / "cfg")
    j.init(repo, "X", "")
    j.add(repo, "Wi-Fi | roaming", "a | b", date="2026-03-03")
    row = [ln for ln in read(os.path.join(repo, "README.md")).splitlines() if ln.startswith("| 2026-03-03")][0]
    assert row.count("|") == 4  # three cells


def test_wrong_repo_path_writes_nothing(tmp_path):
    with pytest.raises(SystemExit):
        j.add(str(tmp_path / "nope"), "T", "s", date="2026-03-03")
    assert not os.path.exists(str(tmp_path / "nope"))
