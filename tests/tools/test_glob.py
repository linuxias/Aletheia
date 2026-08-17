import os

from core.tools.glob import GlobTool


def test_recursive_pattern(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "b.py").write_text("y = 2\n")
    out = GlobTool().run(pattern="**/*.py", path=str(tmp_path))
    assert str(tmp_path / "a.py") in out
    assert str(sub / "b.py") in out


def test_skips_junk_dirs(tmp_path):
    (tmp_path / "ok.py").write_text("")
    for junk in ("__pycache__", "node_modules", ".git"):
        d = tmp_path / junk
        d.mkdir()
        (d / "hidden.py").write_text("")
    out = GlobTool().run(pattern="**/*.py", path=str(tmp_path))
    assert "ok.py" in out
    assert "hidden.py" not in out


def test_mtime_ordering_newest_first(tmp_path):
    old = tmp_path / "old.py"
    new = tmp_path / "new.py"
    old.write_text("")
    new.write_text("")
    os.utime(old, (1, 1))
    os.utime(new, (2, 2))
    out = GlobTool().run(pattern="*.py", path=str(tmp_path))
    assert out.index("new.py") < out.index("old.py")


def test_no_match(tmp_path):
    assert GlobTool().run(pattern="*.zzz", path=str(tmp_path)) == "No files found"


def test_path_must_be_directory(tmp_path):
    p = tmp_path / "file.txt"
    p.write_text("")
    out = GlobTool().run(pattern="*.txt", path=str(p))
    assert out.startswith("Error:")
