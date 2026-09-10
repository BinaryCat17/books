import base64
import json
import os

import jsonschema
import pymupdf
from fastapi.testclient import TestClient

from layout import classes, job, knobs, order, serve, settings
from layout.detector import Detector
from layout.page import Block, Page


class Stub(Detector):
    name = "stub"
    dir = "nowhere"
    policy_name = "PP-DocLayoutV2"

    def label(self):
        return "stub"

    def fingerprint(self):
        return {"name": "stub", "sha256_weights": "0" * 64, "reading_order": order.MODEL_RANK}

    def knobs_read(self):
        return ("LAYOUT_SCORE_THRESHOLD",)

    def threshold_drift(self):
        return ()

    def read(self, image_path, index, dpi):
        return Page(index=index, width=400, height=600, dpi=dpi,
                    blocks=[Block(0, (10, 10, 100, 100), "text", 0.9, 0)],
                    meta={"threshold": knobs.knob("LAYOUT_SCORE_THRESHOLD"), "rank_ties": 0,
                          "best_rejected_by_class": {}})


def _schema(name):
    with open(os.path.join(settings.schema_dir(), name), encoding="utf-8") as f:
        return json.load(f)


def test_the_shim_answers_the_protocol_under_the_job_it_was_built_in():
    with job.Job(settings={"LAYOUT_SCORE_THRESHOLD": "0.7"}).active():
        svc = serve.Service(Stub(), key="k")
    c = TestClient(serve.create_app(svc))
    assert c.get("/booksmith/describe").status_code == 401
    h = {"Authorization": "Bearer k"}
    d = c.get("/booksmith/describe", headers=h).json()
    jsonschema.validate(d, _schema("describe.schema.json"))
    assert d["knobs"] == {"LAYOUT_SCORE_THRESHOLD": "0.7"} and d["reading_order"] == "own"
    assert set(d["classes"]) == set(classes.VOCABULARIES["PP-DocLayoutV2"])
    doc = pymupdf.open()
    doc.new_page(width=400, height=600)
    png = doc[0].get_pixmap(dpi=72).tobytes("png")
    body = {"index": 3, "dpi": 72.0, "image": "data:image/png;base64," + base64.b64encode(png).decode()}
    r = c.post("/booksmith/layout", json=body, headers=h)
    assert r.status_code == 200, r.text
    page = r.json()
    jsonschema.validate(page, _schema("page.schema.json"))
    assert page["index"] == 3 and page["meta"]["threshold"] == "0.7"
    jsonschema.validate(c.get("/booksmith/health", headers=h).json(), _schema("health.schema.json"))
    assert c.get("/booksmith/health", headers=h).json()["requests"] == 1
    assert c.post("/booksmith/layout", json={"index": 0, "dpi": 72, "image": "data:image/jpeg;base64,AAAA"}, headers=h).status_code == 400
