import os

import pytest


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("BOOKSMITH_HOME", str(tmp_path))
    os.makedirs(tmp_path / "fleet", exist_ok=True)
    return str(tmp_path)
