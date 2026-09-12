import json
import os

import jsonschema
from fastapi.testclient import TestClient

from metrics import settings
from metrics.app import create_app


def _schema(name):
    with open(os.path.join(settings.schema_dir(), name), encoding="utf-8") as f:
        return json.load(f)


def test_the_service_answers_the_catalog_a_measure_and_the_pairs(bench):
    c = TestClient(create_app())
    cat = c.get("/metrics").json()
    jsonschema.validate(cat, _schema("catalog.schema.json"))
    assert {m["metric"] for m in cat} == {"contour", "fitness", "text", "assembly", "reading"}
    with open(os.path.join(settings.schema_dir(), "metrics.json"), encoding="utf-8") as f:
        committed = json.load(f)
    assert committed == json.loads(json.dumps(cat, sort_keys=True)), (
        "the catalog is the metrics' contract, as openapi/backend.json is the backend's. "
        "A scalar, a gloss or a version changed: commit schema/metrics.json with it."
    )
    ask = {"store": "", "book": "bench/tiny", "kind": "detect", "run": "truth"}
    r = c.post("/measure", json=ask)
    assert r.status_code == 200, r.text
    recs = r.json()["records"]
    for rec in recs:
        jsonschema.validate(rec, _schema("record.schema.json"))
    by = {rec["metric"]: rec for rec in recs}
    assert by["contour"]["scalars"]["artefacts_found"]["value"] == 1.0
    assert by["contour"]["book"] == "bench/tiny" and len(by["contour"]["identity"]) == 64
    one = c.post("/measure", json={**ask, "pages": [1], "only": ["contour"]}).json()["records"]
    assert [x["metric"] for x in one] == ["contour"]
    assert set(one[0]["scalars"]["artefacts_found"]["per"]) == {"p0001-b1"}
    assert c.post("/measure", json={**ask, "pages": [9]}).status_code == 409
    assert c.post("/measure", json={**ask, "run": "nope"}).status_code == 422
    assert c.post("/measure", json={**ask, "book": "../etc"}).status_code == 409
    p = c.post("/pairs", json={**ask, "index": 2}).json()
    assert p["compared"] and p["labelled"] == "not_said"
    assert [e["verdict"] for e in p["pairs"]] == ["matched"] * 3 and p["extras"] == []
    assert c.post("/pairs", json={**ask, "index": 7}).status_code == 409
    probes = c.post("/probe", json=ask).json()
    assert set(probes) >= {"contour", "fitness", "assembly"}
    for name, got in probes.items():
        assert "skipped" in got or got["uncaught"] == 0, (name, got)
    assert probes["contour"]["probes"] > 10 and probes["fitness"]["probes"] > 10
    assert all(m["description"] for m in cat)


def test_a_layer_is_the_newest_word_on_a_page_and_truth_can_be_borrowed(bench, home):
    import shutil

    from metrics.page import write_json

    layers = os.path.join(bench.root, "truth.layers")
    os.makedirs(layers, exist_ok=True)
    with open(os.path.join(bench.truth_dir, "0001.json"), encoding="utf-8") as f:
        t = json.load(f)
    t["blocks"] = t["blocks"][:1]
    t["meta"] = {**t["meta"], "author": "root", "when": "2026-09-11T00:00:00+0000"}
    write_json(os.path.join(layers, "0001-20260911T000000-root.json"), t)
    c = TestClient(create_app())
    ask = {"store": "", "book": "bench/tiny", "kind": "detect", "run": "truth"}
    p = c.post("/pairs", json={**ask, "index": 1}).json()
    assert len(p["pairs"]) == 1 and len(p["extras"]) == 2, "the layer replaced the base page"
    recs = c.post("/measure", json={**ask, "pages": [1], "only": ["contour"]}).json()["records"]
    assert recs[0]["scalars"]["artefacts_found"]["why"] == "no artefact in the truth"
    other = os.path.join(home, "processed", "twin")
    shutil.copytree(bench.root, other, ignore=lambda d, names: [n for n in names if d == bench.root and n.startswith("truth")])
    ask2 = {"store": "", "book": "processed/twin", "kind": "detect", "run": "truth", "truth": "bench/tiny/truth"}
    got = c.post("/measure", json={**ask2, "only": ["contour"]}).json()["records"]
    assert got[0]["book"] == "processed/twin" and got[0]["scalars"]["artefacts_found"]["count"] == {"n": 2, "of": 2}
    assert got[0]["truth_sha256"] == recs[0]["truth_sha256"], "the record names the truth it was measured against"
    assert c.post("/pairs", json={**ask2, "index": 0}).json()["compared"]
    for bad in ("../etc", "processed/twin/truth", "bench/tiny", "/bench/tiny/truth", "bench/../bench/tiny/truth"):
        assert c.post("/measure", json={**ask2, "truth": bad}).status_code == 409, bad
    assert c.post("/measure", json={**ask, "truth": "bench/tiny/truth"}).status_code == 409, "a book with truth of its own"
    write_json(os.path.join(layers, "0001-20260911T000001.000000Z-root.json"), {**t, "blocks": []})
    write_json(os.path.join(layers, "0007-20260911T000001.000000Z-root.json"), {**t, "index": 7})
    p = c.post("/pairs", json={**ask, "index": 1}).json()
    assert p["pairs"] == [] and len(p["extras"]) == 3, "the newest layer wins; a layer for no base page is nothing"
    newer = c.post("/measure", json={**ask, "pages": [1], "only": ["contour"]}).json()["records"]
    assert newer[0]["truth_sha256"] != recs[0]["truth_sha256"], "a layer changes the truth's fingerprint"
    with open(os.path.join(other, "manifest.json"), encoding="utf-8") as f:
        man = json.load(f)
    man["source"]["sha256"] = "0" * 64
    write_json(os.path.join(other, "manifest.json"), man)
    r = c.post("/measure", json=ask2)
    assert r.status_code == 422 and "different scan" in r.json()["error"]
    shutil.rmtree(layers)
    shutil.rmtree(other)


def test_a_truth_that_names_its_labelled_pages_holds_back_only_the_metrics_that_need_it(bench, home):
    import shutil

    from metrics.page import write_json

    other = os.path.join(home, "processed", "blank")
    shutil.copytree(bench.root, other, ignore=lambda d, names: [n for n in names if d == bench.root and n.startswith("truth")])
    os.makedirs(os.path.join(other, "truth"))
    for i in range(3):
        with open(os.path.join(bench.truth_dir, f"{i:04d}.json"), encoding="utf-8") as f:
            t = json.load(f)
        write_json(os.path.join(other, "truth", f"{i:04d}.json"), {**t, "blocks": [], "meta": {"labelled": False}})
    c = TestClient(create_app())
    ask = {"store": "", "book": "processed/blank", "kind": "detect", "run": "truth", "pages": [1]}
    recs = c.post("/measure", json=ask).json()["records"]
    assert [r["metric"] for r in recs] and all(r["metric"] != "contour" for r in recs)
    assert any(r["metric"] == "fitness" for r in recs)
    r = c.post("/measure", json={**ask, "only": ["contour"]})
    assert r.status_code == 409 and "not labelled" in r.json()["error"]
    shutil.rmtree(other)
