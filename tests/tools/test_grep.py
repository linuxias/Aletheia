from core.tools.grep import GrepTool


def test_content_mode(tmp_path):
    p = tmp_path / "a.txt"
    p.write_text("hello\nworld\nhello world\n", encoding="utf-8")
    out = GrepTool().run(pattern="hello", path=str(tmp_path))
    assert f"{p}:1:hello" in out
    assert f"{p}:3:hello world" in out
    assert "world\n" not in out.replace("hello world", "")  # line 2 alone must not match


def test_files_with_matches_mode(tmp_path):
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_text("needle\n")
    b.write_text("nothing\n")
    out = GrepTool().run(pattern="needle", path=str(tmp_path), mode="files_with_matches")
    assert str(a) in out
    assert str(b) not in out


def test_count_mode(tmp_path):
    p = tmp_path / "a.txt"
    p.write_text("x\nx\ny\n")
    out = GrepTool().run(pattern="x", path=str(tmp_path), mode="count")
    assert out.strip() == f"{p}:2"


def test_include_filter(tmp_path):
    (tmp_path / "a.py").write_text("needle\n")
    (tmp_path / "b.txt").write_text("needle\n")
    out = GrepTool().run(pattern="needle", path=str(tmp_path), include="*.py")
    assert "a.py" in out
    assert "b.txt" not in out


def test_invalid_regex(tmp_path):
    out = GrepTool().run(pattern="(", path=str(tmp_path))
    assert out.startswith("Error: invalid regex")


def test_invalid_mode(tmp_path):
    out = GrepTool().run(pattern="x", path=str(tmp_path), mode="bogus")
    assert out.startswith("Error: invalid mode")


def test_skips_binary_files(tmp_path):
    p = tmp_path / "bin.dat"
    p.write_bytes(b"needle\x00needle")
    out = GrepTool().run(pattern="needle", path=str(tmp_path))
    assert out == "No matches found"


def test_skips_junk_dirs(tmp_path):
    d = tmp_path / "__pycache__"
    d.mkdir()
    (d / "m.py").write_text("needle\n")
    (tmp_path / "ok.py").write_text("clean\n")
    out = GrepTool().run(pattern="needle", path=str(tmp_path))
    assert out == "No matches found"


def test_single_file_path(tmp_path):
    p = tmp_path / "one.txt"
    p.write_text("needle here\n")
    out = GrepTool().run(pattern="needle", path=str(p))
    assert f"{p}:1:needle here" in out


def test_missing_path(tmp_path):
    out = GrepTool().run(pattern="x", path=str(tmp_path / "nope"))
    assert out.startswith("Error: path not found")
