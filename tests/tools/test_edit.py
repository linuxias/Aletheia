from core.tools.edit import EditTool
from core.tools.read import ReadTool


def _setup(tmp_path, name, text, file_state):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    ReadTool(file_state).run(file_path=str(p))
    return p


def test_unique_replace_with_diff(tmp_path, file_state):
    p = _setup(tmp_path, "f.txt", "a\nb\nc\n", file_state)
    out = EditTool(file_state).run(
        file_path=str(p), old_string="b", new_string="x"
    )
    assert p.read_text() == "a\nx\nc\n"
    assert "Edited" in out and "1 replacement" in out
    assert "-b" in out and "+x" in out


def test_old_string_not_found(tmp_path, file_state):
    p = _setup(tmp_path, "f.txt", "a\n", file_state)
    out = EditTool(file_state).run(file_path=str(p), old_string="zzz", new_string="x")
    assert out.startswith("Error: old_string not found")
    assert p.read_text() == "a\n"


def test_multiple_matches_rejected_without_replace_all(tmp_path, file_state):
    p = _setup(tmp_path, "f.txt", "x\nx\n", file_state)
    out = EditTool(file_state).run(file_path=str(p), old_string="x", new_string="y")
    assert "matches 2 locations" in out
    assert p.read_text() == "x\nx\n"


def test_replace_all(tmp_path, file_state):
    p = _setup(tmp_path, "f.txt", "x\nx\nx\n", file_state)
    out = EditTool(file_state).run(
        file_path=str(p), old_string="x", new_string="y", replace_all=True
    )
    assert p.read_text() == "y\ny\ny\n"
    assert "3 replacements" in out


def test_requires_prior_read(tmp_path, file_state):
    p = tmp_path / "f.txt"
    p.write_text("a\n")
    out = EditTool(file_state).run(file_path=str(p), old_string="a", new_string="b")
    assert "use Read first" in out
    assert p.read_text() == "a\n"


def test_empty_old_string(tmp_path, file_state):
    p = _setup(tmp_path, "f.txt", "a\n", file_state)
    out = EditTool(file_state).run(file_path=str(p), old_string="", new_string="b")
    assert out.startswith("Error: old_string must not be empty")


def test_multiline_replacement(tmp_path, file_state):
    p = _setup(tmp_path, "f.txt", "def f():\n    pass\n", file_state)
    out = EditTool(file_state).run(
        file_path=str(p),
        old_string="def f():\n    pass",
        new_string="def f():\n    return 1",
    )
    assert "return 1" in p.read_text()
    assert out.startswith("Edited")
