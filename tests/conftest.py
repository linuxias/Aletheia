import pytest

from core.tools.base import FileState


@pytest.fixture
def file_state():
    return FileState()
