"""The viewer routes: by name, never by path; the truth side of the pairs is"""

import os
import shutil
from fastapi.testclient import TestClient
from conftest import as_user, wait_done
from test_api import _registry, _upload


def _bench_into(home, bench):
    dest = os.path.join(home, "bench", "tiny")
    os.makedirs(dest)
    shutil.copy2(os.path.join(os.path.dirname(bench.truth_dir), "manifest.json"), dest)
    shutil.copy2(bench.pdf, dest)
    shutil.copytree(bench.truth_dir, os.path.join(dest, "truth"))


def _detect(client, book):
    r = client.post("/api/jobs", json={"kind": "detect", "book": book, "model": "fake"})
    assert r.status_code == 200, r.text
    _, last = wait_done(client, r.json()["id"])
    assert last["state"] == "done", last


def test_the_viewer_answers_by_name_and_the_truth_side_is_the_admins(
    app, home, bench, served_endpoint
):
    _registry(home, {"fake": {"kind": "layout", "endpoint": served_endpoint, "knobs": {}}})
    _bench_into(home, bench)
    admin = as_user(app, "root", "pw", "admin")
    _detect(admin, "bench/tiny")
    base = "/api/books/bench/tiny/runs/detect/truth"
    run = admin.get(base).json()
    assert run["truth"] and run["pages"] == list(range(3)) and run["policy"]["classes"]
    page = admin.get(f"{base}/pages/1").json()
    assert page["index"] == 1 and page["blocks"] and page["blocks"][0]["role"]
    pairs = admin.get(f"{base}/pages/1/pairs").json()
    assert pairs["compared"] and pairs["truth"] and pairs["pairs"][0]["truth"]
    img = admin.get("/api/books/bench/tiny/pages/1/image", params={"dpi": 48})
    assert img.status_code == 200 and img.headers["content-type"] == "image/png"
    assert img.content[:4] == b"\x89PNG"
    crop = admin.get(f"{base}/crops/{page['blocks'][0]['anchor']}")
    assert crop.status_code == 200 and crop.content[:4] == b"\x89PNG"
    assert crop.headers["content-type"] == "image/png"
    alice = as_user(app, "alice")
    mine = _upload(alice, bench.pdf, "mine")
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


def test_a_page_is_measured_on_request_and_the_results_say_their_state(
    app, home, bench, served_endpoint
):
    _registry(home, {"fake": {"kind": "layout", "endpoint": served_endpoint, "knobs": {}}})
    alice = as_user(app, "alice")
    mine = _upload(alice, bench.pdf, "mine")
    _detect(alice, mine)
    ub = f"/api/books/{mine}/runs/detect/truth"
    r = alice.get(f"{ub}/results")
    assert r.status_code == 409 and "not measured yet" in r.json()["error"]
    recs = alice.get(f"{ub}/pages/2/metrics").json()
    assert {x["metric"] for x in recs} == {"fitness"}
    assert "contour" not in {x["metric"] for x in recs}, "a user's book has no truth"
    assert recs[0]["identity"] and len(recs[0]["identity"]) == 64
    r = alice.post("/api/jobs", json={"kind": "bench", "book": mine, "label": "truth"})
    assert r.status_code == 200, r.text
    _, last = wait_done(alice, r.json()["id"])
    assert last["state"] == "done", last
    got = alice.get(f"{ub}/results").json()
    assert got["records"] and {x["state"] for x in got["records"]} == {"current"}
    assert [x["metric"] for x in alice.get(f"{ub}/series").json()] == ["fitness"]
    doc = alice.get(f"{ub}/document").json()
    assert doc["version"] == 1 and len(doc["pages"]) == 3
    assert alice.get(f"{ub}/pages/99/metrics").status_code == 409
