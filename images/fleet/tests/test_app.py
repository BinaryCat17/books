from fastapi.testclient import TestClient

from fleet.app import create_app


def test_the_registry_is_checked_and_kept(tmp_path, monkeypatch):
    monkeypatch.setenv("BOOKSMITH_HOME", str(tmp_path))
    c = TestClient(create_app())
    assert c.get("/models").json() == {}
    for bad in ({"x": {"kind": "layout", "knobs": {}}}, {"x": {"kind": "other", "endpoint": "e"}},
                {"x": {"kind": "layout", "endpoint": "e", "image": "i", "provider": "docker"}},
                {"x": {"kind": "layout", "image": "i"}}):
        assert c.put("/models", json=bad).status_code == 409, bad
    good = {"m": {"kind": "reader", "endpoint": "http://h/v1", "knobs": {"PAGE_DPI": 72}, "key": "sk"}}
    assert c.put("/models", json=good).status_code == 200
    assert c.get("/models").json()["m"]["knobs"] == {"PAGE_DPI": "72"}
    assert c.get("/placements").json() == []
