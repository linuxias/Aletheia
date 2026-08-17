from core.tools.read import ReadTool
from core.tools.write import WriteTool


def test_creates_new_file_with_parents(tmp_path):
    target = tmp_path / "nested" / "dir" / "f.txt"
    out = WriteTool().run(file_path=str(target), content="a\nb\n")
    assert target.read_text() == "a\nb\n"
    assert out == f"Wrote 2 lines to {target}"


def test_overwrite_requires_prior_read(tmp_path, file_state):
    p = tmp_path / "f.txt"
    p.write_text("original\n")
    out = WriteTool(file_state).run(file_path=str(p), content="new\n")
    assert out.startswith("Error:")
    assert "use Read first" in out
    assert p.read_text() == "original\n"  # untouched


def test_overwrite_after_read(tmp_path, file_state):
    p = tmp_path / "f.txt"
    p.write_text("original\n")
    ReadTool(file_state).run(file_path=str(p))
    out = WriteTool(file_state).run(file_path=str(p), content="new\n")
    assert out.startswith("Wrote")
    assert p.read_text() == "new\n"


def test_write_marks_file_read_for_later_edits(tmp_path, file_state):
    p = tmp_path / "f.txt"
    WriteTool(file_state).run(file_path=str(p), content="v1\n")
    assert file_state.was_read(str(p))


def test_empty_content(tmp_path):
    p = tmp_path / "empty.txt"
    out = WriteTool().run(file_path=str(p), content="")
    assert out == f"Wrote 0 lines to {p}"
    assert p.read_text() == ""
