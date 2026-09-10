"""The viewer routes: by name, never by path; the truth side of the pairs is
the admin's; a user's own book answers its pages, its image and its crops."""
import os
import shutil

from fastapi.testclient import TestClient

from conftest import as_user, wait_done
from test_api import _registry, _upload


def _bench_into(home, slovar):
    dest = os.path.join(home, "bench", "slovar")
    os.makedirs(dest)
    shutil.copy2(os.path.join(os.path.dirname(slovar.truth_dir), "manifest.json"), dest)
    shutil.copy2(slovar.pdf, dest)
    shutil.copytree(slovar.truth_dir, os.path.join(dest, "truth"))


def _detect(client, book):
    r = client.post("/api/jobs", json={"kind": "detect", "book": book, "model": "fake"})
    assert r.status_code == 200, r.text
    _, last = wait_done(client, r.json()["id"])
    assert last["state"] == "done", last


def test_the_viewer_answers_by_name_and_the_truth_side_is_the_admins(app, home, slovar, served_endpoint):
    _registry(home, {"fake": {"kind": "layout", "endpoint": served_endpoint, "knobs": {}}})
    _bench_into(home, slovar)
    admin = as_user(app, "root", "pw", "admin")
    _detect(admin, "bench/slovar")
    base = "/api/books/bench/slovar/runs/detect/truth"
    run = admin.get(base).json()
    assert run["truth"] and run["pages"] == list(range(13)) and run["policy"]["classes"]
    page = admin.get(f"{base}/pages/1").json()
    assert page["index"] == 1 and page["blocks"] and page["blocks"][0]["role"]
    pairs = admin.get(f"{base}/pages/1/pairs").json()
    assert pairs["compared"] and pairs["truth"] and pairs["pairs"][0]["truth"]
    img = admin.get("/api/books/bench/slovar/pages/1/image", params={"dpi": 48})
    assert img.status_code == 200 and img.headers["content-type"] == "image/png"
    assert img.content[:4] == b"\x89PNG"
    crop = admin.get(f"{base}/crops/{page['blocks'][0]['anchor']}")
    assert crop.status_code == 200 and crop.content[:4] == b"\x89PNG"
    assert crop.headers["content-type"] == "image/png"
    # A user's own book: pages, image and crops answer; there is no truth to
    # pair against; the admin's bench is not theirs, by name.
    alice = as_user(app, "alice")
    mine = _upload(alice, slovar.pdf, "mine")
    _detect(alice, mine)
    ub = f"/api/books/{mine}/runs/detect/truth"
    assert alice.get(ub).json()["truth"] is False
    assert alice.get(f"{ub}/pages/0").json()["blocks"]
    r = alice.get(f"{ub}/pages/0/pairs")
    assert r.status_code == 409 and "no truth" in r.json()["error"]
    assert alice.get(f"/api/books/{mine}/pages/0/image", params={"dpi": 48}).status_code == 200
    r = alice.get(f"/api/books/{mine}/pages/0/image", params={"dpi": 5000})
    assert r.status_code == 409 and "outside" in r.json()["error"]
    assert alice.get(base).status_code == 409
    assert alice.get(f"{base}/pages/1/pairs").status_code == 409
    r = alice.get(f"{ub}/crops/nope")
    assert r.status_code == 409 and "anchor" in r.json()["error"]
    assert alice.get(f"{ub}/crops/p0000-b999").status_code == 409
    assert TestClient(app).get(f"{base}/pages/1").status_code == 401
