import json
import os
import time
from fastapi.testclient import TestClient
from backend.db import Db
from conftest import as_user, wait_done
from fake_layout import FakeLayout
from fake_vlm import FakeVlm


def _registry(home, entries):
    with open(os.path.join(home, "models.json"), "w", encoding="utf-8") as f:
        json.dump(entries, f)


def _upload(client, pdf, name):
    with open(pdf, "rb") as f:
        r = client.post(
            "/api/books",
            files={"file": (os.path.basename(pdf), f, "application/pdf")},
            params={"name": name},
        )
    assert r.status_code == 200, r.text
    return r.json()["book"]


def test_who_may_see_what(app):
    anon = TestClient(app)
    assert anon.get("/api/me").status_code == 401
    admin = as_user(app, "root", "pw", "admin")
    assert admin.get("/api/me").json()["role"] == "admin"
    assert anon.post("/api/login", json={"name": "root", "password": "no"}).status_code == 401
    user = as_user(app, "alice")
    assert user.get("/api/models").status_code == 403
    assert admin.get("/api/models").status_code == 200
    assert user.get("/api/models/presets").status_code == 200
    assert user.post("/api/logout").status_code == 200
    assert user.get("/api/me").status_code == 401


def test_each_user_sees_only_their_own_books(app, bench):
    alice, bob = (as_user(app, "alice"), as_user(app, "bob"))
    mine = _upload(alice, bench.pdf, "mine")
    theirs = _upload(bob, bench.pdf, "theirs")
    assert [b["name"] for b in alice.get("/api/books").json()] == [mine]
    assert [b["name"] for b in bob.get("/api/books").json()] == [theirs]
    r = alice.get(f"/api/books/{theirs}/runs")
    assert r.status_code == 409 and "no book" in r.json()["error"]
    r = alice.post("/api/jobs", json={"kind": "detect", "book": theirs})
    assert r.status_code == 409
    with open(bench.pdf, "rb") as f:
        r = alice.post("/api/books", files={"file": ("again.pdf", f, "application/pdf")})
    assert r.status_code == 409 and "same sha256" in r.json()["error"]
    store = app.state.settings.store_of(app.state.db.user("alice")["id"], "user")
    assert os.listdir(os.path.join(store, "raw")) == []
    for fname, data in (
        ("manifest.json", b"%PDF-1.4 x"),
        ("detect.pdf", b"%PDF-1.4 x"),
        ("note.pdf", b"not a pdf at all"),
    ):
        r = alice.post("/api/books", files={"file": (fname, data, "application/pdf")}, params={"name": "x"})
        assert r.status_code == 409, fname
        assert not os.path.exists(os.path.join(store, "processed", "x")), fname
    assert os.path.isdir(os.path.join(store, "processed", "mine"))
    assert not os.path.exists(os.path.join(store, "processed", "theirs"))


def test_a_detect_job_runs_reports_its_progress_and_files_its_run(app, home, bench, served_endpoint):
    _registry(home, {"fake": {"kind": "layout", "endpoint": served_endpoint, "knobs": {}}})
    alice = as_user(app, "alice")
    book = _upload(alice, bench.pdf, "book")
    r = alice.post("/api/jobs", json={"kind": "detect", "book": book, "model": "fake"})
    assert r.status_code == 200, r.text
    job_id = r.json()["id"]
    lines, last = wait_done(alice, job_id)
    assert last["state"] == "done", last
    progress = [(ev["n"], ev["of"]) for ev in lines if "n" in ev and "of" in ev]
    assert progress and progress[-1] == (3, 3), progress
    row = alice.get(f"/api/jobs/{job_id}").json()
    assert row["state"] == "done" and (row["n"], row["of"]) == (3, 3)
    assert row["result"] == os.path.join("processed", "book", "detect", "truth"), (
        "the result is the run's place in the store, never a path of the server's"
    )
    runs = alice.get(f"/api/books/{book}/runs").json()
    assert runs == [
        {
            "kind": "detect",
            "label": "truth",
            "identity": runs[0]["identity"],
            "pages": 3,
            "complete": True,
            "level": "detect",
            "when": runs[0]["when"],
        }
    ]
    assert runs[0]["identity"] and len(runs[0]["identity"]) == 64
    bob = as_user(app, "bob")
    assert bob.get(f"/api/jobs/{job_id}").status_code == 409
    admin = as_user(app, "root", "pw", "admin")
    assert admin.get(f"/api/jobs/{job_id}").json()["state"] == "done"
    assert len(admin.get("/api/jobs").json()) == 1 and bob.get("/api/jobs").json() == []


def test_a_cancel_stops_a_running_job_between_pages(app, home, bench):

    def slow(page):
        time.sleep(0.4)
        return page

    with FakeLayout(bench.truth_dir, answer=slow) as fake:
        _registry(home, {"slow": {"kind": "layout", "endpoint": fake.url, "knobs": {}}})
        alice = as_user(app, "alice")
        book = _upload(alice, bench.pdf, "book")
        job_id = alice.post("/api/jobs", json={"kind": "detect", "book": book, "model": "slow"}).json()["id"]
        for _ in range(100):
            if alice.get(f"/api/jobs/{job_id}").json()["state"] == "running":
                break
            time.sleep(0.05)
        assert alice.post(f"/api/jobs/{job_id}/cancel").json()["cancelled"]
        _, last = wait_done(alice, job_id)
        assert last["state"] == "cancelled"
        assert fake.requests < 3, "the job ran to the end after the cancel"
    store = app.state.settings.store_of(app.state.db.user("alice")["id"], "user")
    run = os.path.join(store, "processed", "book", "detect", "truth")
    assert not os.path.exists(os.path.join(run, "run.json")), "a stopped run has no snapshot"


def test_a_dead_process_leaves_failed_rows_not_running_or_queued_ones(home):
    from backend.app import create_app
    from backend.settings import Settings

    s = Settings.from_env()
    db = Db(s.db_path)
    db.add_user("x", "h", "user")
    running = db.add_job(1, home, "detect", "processed/b", "", "", {})
    db.set_state(running, "running", started=time.time())
    queued = db.add_job(1, home, "detect", "processed/c", "", "", {})
    db.close()
    app = create_app(s)
    try:
        assert app.state.db.job(running)["error"] == "process died"
        assert app.state.db.job(queued)["state"] == "failed"
        assert "before the start" in app.state.db.job(queued)["error"]
        assert app.state.pool.orphaned == 2
    finally:
        app.state.db.close()


def test_a_cancel_that_lands_before_the_start_wins(home):
    from backend.app import create_app
    from backend.pool import Pool
    from backend.settings import Settings

    s = Settings.from_env()
    app = create_app(s)
    try:
        db = app.state.db
        db.add_user("x", "h", "user")
        pool = Pool.__new__(Pool)
        pool.db, pool.lock, pool.stops, pool.listeners = (
            db,
            __import__("threading").Lock(),
            {},
            {},
        )
        job_id = db.add_job(1, home, "detect", "processed/nowhere", "", "", {"book": "processed/nowhere"})
        assert pool.cancel(job_id)
        pool._run(job_id)
        assert db.job(job_id)["state"] == "cancelled"
        assert pool.cancel(job_id) is False
    finally:
        app.state.db.close()


def test_a_users_read_job_carries_the_entrys_key(app, home, bench, served_endpoint):
    with FakeVlm({"text": "read", "finish": "stop"}) as vlm:
        _registry(
            home,
            {
                "lay": {"kind": "layout", "endpoint": served_endpoint, "knobs": {}},
                "vl": {
                    "kind": "reader",
                    "endpoint": vlm.url,
                    "api_key": "sk-entry",
                    "knobs": {"MODEL_NAME": vlm.model, "VLM_CONCURRENCY": "2"},
                },
            },
        )
        alice = as_user(app, "alice")
        book = _upload(alice, bench.pdf, "book")
        done = alice.post("/api/jobs", json={"kind": "detect", "book": book, "model": "lay"}).json()["id"]
        assert wait_done(alice, done)[1]["state"] == "done"
        rd = alice.post(
            "/api/jobs",
            json={"kind": "read", "book": book, "model": "vl", "label": "truth", "pages": "1"},
        ).json()["id"]
        lines, last = wait_done(alice, rd)
        assert last["state"] == "done", (last, [ln["text"] for ln in lines][-5:])
        assert vlm.seen and all(s["authorization"] == "Bearer sk-entry" for s in vlm.seen)
        assert any(s.get("path", "").endswith("/models") for s in vlm.seen)
        runs = alice.get(f"/api/books/{book}/runs").json()
        assert [r["kind"] for r in runs] == ["detect", "read"]
        assert runs[1]["label"] == vlm.model and runs[1]["complete"]


def test_the_registry_is_written_checked_and_users_are_the_admins(app, home):
    admin = as_user(app, "root", "pw", "admin")
    bad = {"x": {"kind": "layout", "knobs": {}}}
    assert admin.put("/api/models", json=bad).status_code == 409
    assert not os.path.exists(os.path.join(home, "models.json"))
    good = {
        "m": {
            "kind": "reader",
            "endpoint": "http://h/v1",
            "knobs": {"PAGE_DPI": 72},
            "api_key": "sk",
        }
    }
    assert admin.put("/api/models", json=good).status_code == 200
    assert admin.get("/api/models").json()["m"]["knobs"] == {"PAGE_DPI": "72"}
    user = as_user(app, "alice")
    assert user.get("/api/models/presets").json() == [
        {"name": "m", "kind": "reader", "knobs": {"PAGE_DPI": "72"}}
    ]
    assert user.post("/api/users", json={"name": "eve", "password": "p"}).status_code == 403
    r = admin.post("/api/users", json={"name": "eve", "password": "p"})
    assert r.status_code == 200 and r.json()["role"] == "user"
    assert admin.post("/api/users", json={"name": "eve", "password": "p"}).status_code == 409
    listed = admin.get("/api/users").json()
    assert [u["name"] for u in listed] == ["root", "alice", "eve"]
    assert all("hash" not in u for u in listed)


def test_an_unknown_kind_of_job_is_refused_and_a_login_costs_the_same_either_way(app, bench):
    alice = as_user(app, "alice")
    book = _upload(alice, bench.pdf, "book")
    r = alice.post("/api/jobs", json={"kind": "oracle", "book": book})
    assert r.status_code == 409 and "a job is one of" in r.json()["error"]
    anon = TestClient(app)
    t0 = time.time()
    anon.post("/api/login", json={"name": "nobody", "password": "x"})
    unknown = time.time() - t0
    t0 = time.time()
    anon.post("/api/login", json={"name": "alice", "password": "x"})
    known = time.time() - t0
    assert unknown > known / 4, (unknown, known)
