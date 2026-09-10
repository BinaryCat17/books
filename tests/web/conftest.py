"""A data home of its own per test, an application over it, and a client
per user: the cookie jar is the user."""
import pytest
from fastapi.testclient import TestClient

from booksmith.web import auth


@pytest.fixture
def home(tmp_path, monkeypatch):
    h = tmp_path / "home"
    h.mkdir()
    monkeypatch.setenv("BOOKSMITH_HOME", str(h))
    monkeypatch.setenv("BOOKSMITH_WORKERS", "1")
    return str(h)


@pytest.fixture
def app(home):
    from booksmith.web.app import create_app
    from booksmith.web.settings import Settings
    a = create_app(Settings.from_env())
    yield a
    a.state.db.close()


def as_user(app, name, password="pw", role="user"):
    """A logged-in client for a user made on the spot."""
    if app.state.db.user(name) is None:
        user_id = auth.add_user(app.state.db, name, password, role)
        app.state.settings.store_of(user_id, role)
    c = TestClient(app)
    r = c.post("/api/login", json={"name": name, "password": password})
    assert r.status_code == 200, r.text
    return c


def wait_done(client, job_id, timeout=120.0):
    """The job's events until it ends; the lines and the last state."""
    lines, last = [], None
    with client.stream("GET", f"/api/jobs/{job_id}/events", timeout=timeout) as r:
        for raw in r.iter_lines():
            if not raw.startswith("data: "):
                continue
            import json
            ev = json.loads(raw[6:])
            if ev.get("event") == "line":
                lines.append(ev)
            elif ev.get("event") == "state":
                last = ev
                if ev.get("state") in ("done", "failed", "cancelled"):
                    break
    return lines, last
