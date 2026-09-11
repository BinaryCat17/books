import json
import os

from conftest import as_user
from test_api import _registry, _upload
from test_viewer_routes import _bench_into, _detect


def _page(client, book, i):
    r = client.get(f"/api/books/{book}/truth/pages/{i}")
    assert r.status_code == 200, r.text
    return r.json()


def test_a_layer_is_the_newest_word_on_a_page(app, home, bench, served_endpoint, metrics):
    _registry(home, {"fake": {"kind": "layout", "endpoint": served_endpoint, "knobs": {}}})
    _bench_into(home, bench)
    admin = as_user(app, "root", "pw", "admin")
    user = as_user(app, "ann")
    _detect(admin, "bench/tiny")
    base = "/api/books/bench/tiny"
    before = _page(admin, "bench/tiny", 1)
    assert len(before["blocks"]) == 3 and "author" not in (before.get("meta") or {})
    assert user.get(f"{base}/truth/pages/1").status_code == 403
    assert user.put(f"{base}/truth/pages/1", json=before).status_code == 403
    page = {**before, "blocks": before["blocks"][:1], "meta": {**before["meta"], "labelled": True}}
    r = admin.put(f"{base}/truth/pages/1", json=page)
    assert r.status_code == 200, r.text
    assert r.json()["layer"].startswith("bench/tiny/truth.layers/0001-") and r.json()["layer"].endswith("-root.json")
    after = _page(admin, "bench/tiny", 1)
    assert len(after["blocks"]) == 1 and after["meta"]["author"] == "root" and after["meta"]["when"]
    assert len(_page(admin, "bench/tiny", 0)["blocks"]) == 3, "other pages keep the base"
    base_file = os.path.join(home, "bench", "tiny", "truth", "0001.json")
    with open(base_file, encoding="utf-8") as f:
        assert len(json.load(f)["blocks"]) == 3, "the base file is untouched"
    pairs = admin.get(f"{base}/runs/detect/truth/pages/1/pairs").json()
    assert len(pairs["truth"]) == 1 and len(pairs["extras"]) == 2, "pairs see the layer"
    assert admin.put(f"{base}/truth/pages/2", json=page).status_code == 409, "index must agree"
    assert admin.put(f"{base}/truth/pages/1", json={**page, "width": 1}).status_code == 409
    assert admin.put(f"{base}/truth/pages/1", json={**page, "blocks": [{"box": [1, 2, 3]}]}).status_code == 409
    layers = sorted(os.listdir(os.path.join(home, "bench", "tiny", "truth.layers")))
    assert len(layers) == 1
    admin.put(f"{base}/truth/pages/1", json={**page, "blocks": []})
    assert _page(admin, "bench/tiny", 1)["blocks"] == []
    assert admin.get(f"{base}/truth/pages/9").status_code == 409


def test_a_users_book_borrows_the_truth_of_the_bench_with_its_hash(app, home, bench, served_endpoint, metrics):
    _registry(home, {"fake": {"kind": "layout", "endpoint": served_endpoint, "knobs": {}}})
    _bench_into(home, bench)
    user = as_user(app, "ann")
    book = _upload(user, bench.pdf, "mine")
    _detect(user, book)
    run = user.get(f"/api/books/{book}/runs/detect/truth").json()
    assert run["truth"] == "borrowed"
    pairs = user.get(f"/api/books/{book}/runs/detect/truth/pages/1/pairs")
    assert pairs.status_code == 200 and pairs.json()["compared"] and "truth" not in pairs.json()
    assert metrics.seen[-1][1]["truth"] == "bench/tiny/truth"
    recs = user.get(f"/api/books/{book}/runs/detect/truth/pages/1/metrics").json()
    assert {r["metric"] for r in recs} == {"fitness", "contour"}
    assert user.get(f"/api/books/{book}/truth/pages/1").status_code == 403
    assert user.post(f"/api/books/{book}/truth").status_code == 403


def test_the_admin_starts_a_blank_truth_and_labels_it(app, home, bench, served_endpoint, metrics):
    _registry(home, {"fake": {"kind": "layout", "endpoint": served_endpoint, "knobs": {}}})
    admin = as_user(app, "root", "pw", "admin")
    book = _upload(admin, bench.pdf, "fresh")
    _detect(admin, book)
    assert admin.get(f"/api/books/{book}/runs/detect/truth").json()["truth"] is None
    assert admin.get(f"/api/books/{book}/runs/detect/truth/pages/0/pairs").status_code == 409
    r = admin.post(f"/api/books/{book}/truth")
    assert r.status_code == 200, r.text
    assert r.json() == {"truth": "processed/fresh/truth", "pages": 3}
    assert admin.post(f"/api/books/{book}/truth").status_code == 409
    page = _page(admin, book, 0)
    assert page["blocks"] == [] and page["meta"]["labelled"] is False and page["width"] > 0
    assert admin.get(f"/api/books/{book}/runs/detect/truth").json()["truth"] == "own"
    assert admin.get(f"/api/books/{book}/runs/detect/truth/pages/0/pairs").json()["compared"] is False
    page["blocks"] = [{"block_id": 0, "box": [10, 10, 100, 100], "label": "text", "order": 0}]
    page["meta"] = {**page["meta"], "labelled": True}
    assert admin.put(f"/api/books/{book}/truth/pages/0", json=page).status_code == 200
    got = admin.get(f"/api/books/{book}/runs/detect/truth/pages/0/pairs").json()
    assert got["compared"] and len(got["truth"]) == 1


def test_the_class_table_is_served(app):
    user = as_user(app, "ann")
    t = user.get("/api/classes").json()
    assert t["classes"]["text"]["role"] == "text" and t["vocabularies"] and t["roles"]
    assert not any(k.startswith("$") for k in t)
