import shutil
import sys

import pytest

from core.sandbox import create_sandbox
from core.sandbox.local import LocalBackend


def test_local_backend():
    assert isinstance(create_sandbox("local"), LocalBackend)


def test_unknown_name_lists_valid_values():
    with pytest.raises(ValueError, match="bwrap, local"):
        create_sandbox("nope")


def test_local_does_not_import_bwrap_module():
    sys.modules.pop("core.sandbox.bwrap", None)
    create_sandbox("local")
    assert "core.sandbox.bwrap" not in sys.modules


def test_bwrap_missing_binary_is_value_error(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: None)
    with pytest.raises(ValueError, match="bubblewrap"):
        create_sandbox("bwrap")
