from core.tools.read import ReadTool


def _write(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


def test_numbered_output_and_range(tmp_path):
    p = _write(tmp_path, "f.txt", "\n".join(f"line{i}" for i in range(1, 6)))
    out = ReadTool().run(file_path=str(p), offset=2, limit=2)
    assert "     2\tline2" in out
    assert "     3\tline3" in out
    assert "line1" not in out
    assert "line4" not in out
    assert "(showing lines 2-3 of 5)" in out


def test_full_read_defaults(tmp_path):
    p = _write(tmp_path, "f.txt", "a\nb\n")
    out = ReadTool().run(file_path=str(p))
    assert "     1\ta" in out
    assert "(showing lines 1-2 of 2)" in out


def test_missing_file(tmp_path):
    out = ReadTool().run(file_path=str(tmp_path / "nope.txt"))
    assert out.startswith("Error: file not found")


def test_directory_error(tmp_path):
    out = ReadTool().run(file_path=str(tmp_path))
    assert "is a directory" in out


def test_binary_rejected(tmp_path):
    p = tmp_path / "bin.dat"
    p.write_bytes(b"abc\x00def")
    out = ReadTool().run(file_path=str(p))
    assert "binary" in out


def test_empty_file(tmp_path):
    p = _write(tmp_path, "empty.txt", "")
    assert ReadTool().run(file_path=str(p)) == "(file is empty)"


def test_offset_past_end(tmp_path):
    p = _write(tmp_path, "f.txt", "only line\n")
    out = ReadTool().run(file_path=str(p), offset=5)
    assert out.startswith("Error: offset 5 is past the end")


def test_marks_file_read(tmp_path, file_state):
    p = _write(tmp_path, "f.txt", "content\n")
    ReadTool(file_state).run(file_path=str(p))
    assert file_state.was_read(str(p))


def test_long_output_is_clipped(tmp_path):
    p = _write(tmp_path, "big.txt", "x" * 40_000 + "\n")
    out = ReadTool().run(file_path=str(p))
    assert "characters truncated" in out
    assert len(out) < 40_000
