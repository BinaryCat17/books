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
    probes = c.post("/probe", json={**ask, "only": ["contour"]}).json()
    assert probes["contour"]["probes"] > 10 and probes["contour"]["uncaught"] == 0
