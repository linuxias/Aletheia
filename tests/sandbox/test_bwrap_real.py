"""Opt-in tests against a real bwrap binary.

Skipped unless ALETHEIA_SANDBOX_E2E=1 and bwrap is installed — the
isolated environments CI runs in usually forbid the user namespaces
bwrap needs. Mirrors the ALETHEIA_E2E pattern in tests/test_e2e_tools.py.
"""
import os
import shutil
import sys

import pytest

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        os.environ.get("ALETHEIA_SANDBOX_E2E") != "1" or shutil.which("bwrap") is None,
        reason="set ALETHEIA_SANDBOX_E2E=1 with bwrap installed to run",
    ),
]

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from core.sandbox.bwrap import BwrapBackend  # noqa: E402


def test_writes_outside_workspace_are_blocked(tmp_path):
    result = BwrapBackend().run_command(
        f"touch {tmp_path / 'ok.txt'}; touch /etc/aletheia-probe", timeout=10
    )
    assert (tmp_path / "ok.txt").exists()  # cwd stays writable
    assert result.exit_code != 0  # /etc is read-only


def test_environment_is_scrubbed(monkeypatch):
    monkeypatch.setenv("LLM_KEY", "secret")
    result = BwrapBackend().run_command('echo "${LLM_KEY:-unset}"', timeout=10)
    assert result.stdout.strip() == "unset"


def test_network_is_blocked():
    # No resolver without a network namespace: getent fails outright.
    result = BwrapBackend().run_command("getent hosts example.com", timeout=15)
    assert result.exit_code != 0
