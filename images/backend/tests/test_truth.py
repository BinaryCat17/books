import json
import os
import shutil

import pymupdf

from conftest import as_user, wait_done
from fake_layout import FakeLayout
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
    assert admin.put(f"{base}/truth/pages/1", json={**page, "dpi": 7}).status_code == 409
    assert admin.put(f"{base}/truth/pages/1", json={**page, "blocks": [{"box": [1, 2, 3]}]}).status_code == 422
    assert admin.put(f"{base}/truth/pages/1", json={**page, "raw": {"x": 1}}).status_code == 422
    assert admin.put(f"{base}/truth/pages/1", json={**page, "extra": 1}).status_code == 422
    assert admin.put(f"{base}/truth/pages/1", json={"index": 1}).status_code == 422
    layers_dir = os.path.join(home, "bench", "tiny", "truth.layers")
    assert len(os.listdir(layers_dir)) == 1
    assert admin.put(f"{base}/truth/pages/1", json={**page, "blocks": []}).status_code == 200
    assert _page(admin, "bench/tiny", 1)["blocks"] == [], "the second layer of the same second wins"
    assert len(os.listdir(layers_dir)) == 2, "two layers, two files"
    assert admin.get(f"{base}/truth/pages/9").status_code == 409
    assert admin.put(f"{base}/truth/pages/9", json={**page, "index": 9}).status_code == 409
    ivan = as_user(app, "Иван Петров", "pw", "admin")
    r = ivan.put(f"{base}/truth/pages/1", json={**page, "blocks": page["blocks"]})
    assert r.status_code == 200 and r.json()["layer"].endswith("-admin.json") and r.json()["page"]["meta"]["author"] == "Иван Петров"
    assert len(_page(admin, "bench/tiny", 1)["blocks"]) == 1, "the newest layer wins whoever wrote it"


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
    contour = next(r for r in recs if r["metric"] == "contour")
    assert contour["detail"] == {} and "per" not in contour["scalars"]["artefacts_found"], "the truth side stays the admin's"
    assert user.get(f"/api/books/{book}/truth/pages/1").status_code == 403
    assert user.post(f"/api/books/{book}/truth", json={"kind": "detect", "label": "truth"}).status_code == 403
    admin = as_user(app, "root", "pw", "admin")
    _detect(admin, "bench/tiny")
    got = admin.get("/api/books/bench/tiny/runs/detect/truth/pages/1/metrics").json()
    assert next(r for r in got if r["metric"] == "contour")["detail"], "the admin sees the detail"
    shutil.copytree(os.path.join(home, "bench", "tiny"), os.path.join(home, "bench", "twin"))
    r = user.get(f"/api/books/{book}/runs/detect/truth")
    assert r.status_code == 409 and "2 benches" in r.json()["error"]


def test_the_admin_starts_a_blank_truth_and_labels_it(app, home, bench, served_endpoint, metrics):
    _registry(home, {"fake": {"kind": "layout", "endpoint": served_endpoint, "knobs": {}}})
    admin = as_user(app, "root", "pw", "admin")
    book = _upload(admin, bench.pdf, "fresh")
    _detect(admin, book)
    assert admin.get(f"/api/books/{book}/runs/detect/truth").json()["truth"] is None
    assert admin.get(f"/api/books/{book}/runs/detect/truth/pages/0/pairs").status_code == 409
    ref = {"kind": "detect", "label": "truth"}
    assert admin.post(f"/api/books/{book}/truth", json={**ref, "label": "nope"}).status_code == 409
    r = admin.post(f"/api/books/{book}/truth", json=ref)
    assert r.status_code == 200, r.text
    assert r.json() == {"truth": "processed/fresh/truth", "pages": 3, "dpi": 144.0}
    assert admin.post(f"/api/books/{book}/truth", json=ref).status_code == 409
    page = _page(admin, book, 0)
    assert page["blocks"] == [] and page["meta"]["labelled"] is False and page["width"] > 0
    run_page = admin.get(f"/api/books/{book}/runs/detect/truth/pages/0").json()
    assert (page["width"], page["height"], page["dpi"]) == (run_page["width"], run_page["height"], run_page["dpi"])
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


def test_a_blank_truth_is_in_the_runs_raster_whatever_the_page_size(app, home, bench, metrics):
    pdf = os.path.join(home, "a4.pdf")
    doc = pymupdf.open()
    for i in range(2):
        pg = doc.new_page(width=595.276, height=841.89)
        pg.insert_text((40, 60), f"page {i}", fontsize=11)
    doc.save(pdf)
    doc.close()
    admin = as_user(app, "root", "pw", "admin")
    with FakeLayout(bench.truth_dir, fit=True) as fake:
        _registry(home, {"fit": {"kind": "layout", "endpoint": fake.url, "knobs": {"PAGE_DPI": "110"}}})
        book = _upload(admin, pdf, "a4")
        r = admin.post("/api/jobs", json={"kind": "detect", "book": book, "model": "fit"})
        assert r.status_code == 200, r.text
        assert wait_done(admin, r.json()["id"])[1]["state"] == "done"
    r = admin.post(f"/api/books/{book}/truth", json={"kind": "detect", "label": "truth"})
    assert r.status_code == 200, r.text
    assert r.json()["dpi"] == 110.0
    for i in range(2):
        t = _page(admin, book, i)
        m = admin.get(f"/api/books/{book}/runs/detect/truth/pages/{i}").json()
        assert (t["width"], t["height"], t["dpi"]) == (m["width"], m["height"], m["dpi"]), i
        assert t["width"] % 10 != 0 or t["height"] % 10 != 0, "a page size the rounding can be seen on"


def test_a_measurement_goes_stale_when_the_truth_changes(app, home, bench, served_endpoint, metrics):
    _registry(home, {"fake": {"kind": "layout", "endpoint": served_endpoint, "knobs": {}}})
    _bench_into(home, bench)
    admin = as_user(app, "root", "pw", "admin")
    _detect(admin, "bench/tiny")
    r = admin.post("/api/jobs", json={"kind": "bench", "book": "bench/tiny", "label": "truth"})
    assert r.status_code == 200, r.text
    assert wait_done(admin, r.json()["id"])[1]["state"] == "done"
    rows = admin.get("/api/books/bench/tiny/runs/detect/truth/series").json()
    assert rows and all(r["state"] == "current" and r["truth_sha256"] for r in rows)
    page = _page(admin, "bench/tiny", 2)
    assert admin.put("/api/books/bench/tiny/truth/pages/2", json={**page, "blocks": page["blocks"][:2]}).status_code == 200
    rows = admin.get("/api/books/bench/tiny/runs/detect/truth/series").json()
    assert all(r["state"] == "stale" for r in rows), "the truth moved under the number"
