from fastapi.testclient import TestClient

from fleet.app import create_app


def test_the_fleet_answers(tmp_path, monkeypatch):
    monkeypatch.setenv("BOOKSMITH_HOME", str(tmp_path))
    c = TestClient(create_app())
    assert c.get("/placements").json() == []
    assert c.get("/health").json()["ready"] is True
