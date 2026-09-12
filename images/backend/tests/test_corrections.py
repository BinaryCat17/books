import json
import os
import shutil

from conftest import as_user
from fake_vlm import FakeVlm
from support import said
from test_api import _registry
from test_viewer_routes import _bench_into, _detect
from backend import service


def _read_run(home):
    rd = os.path.join(home, "bench", "tiny", "detect", "truth")
    with FakeVlm({"text": "read", "finish": "stop"}) as vlm, said():
        out = service.read(home, rd, {"VLM_ENDPOINT": vlm.url, "MODEL_NAME": vlm.model}, pages="1-3")
    return os.path.basename(out)


def _page(client, book, kind, label, i):
    r = client.get(f"/api/books/{book}/runs/{kind}/{label}/pages/{i}")
    assert r.status_code == 200, r.text
    return r.json()


def test_a_correction_is_a_derived_run_and_the_base_is_never_touched(app, home, bench, served_endpoint, metrics):
    _registry(home, {"fake": {"kind": "layout", "endpoint": served_endpoint, "knobs": {}}})
    _bench_into(home, bench)
    admin = as_user(app, "root", "pw", "admin")
    _detect(admin, "bench/tiny")
    label = _read_run(home)
    book = "bench/tiny"
    base = f"/api/books/{book}/runs/read/{label}"
    before = _page(admin, book, "read", label, 1)
    assert before["blocks"][0]["content"] == "read" and before["blocks"][0]["reading"]
    assert admin.get(f"{base}/corrections").json() == {"base": label, "run": None, "corrections": [], "stale": False}
    r = admin.post(f"{base}/corrections", json={"anchor": "p0001-b0", "content": "fixed"})
    assert r.status_code == 200, r.text
    derived = r.json()["run"]
    assert derived == f"{label}.corrected" and len(r.json()["corrections"]) == 1
    assert r.json()["corrections"][0]["author"] == "root"
    rows = admin.get(f"/api/books/{book}/runs").json()
    assert {x["label"]: x["level"] for x in rows if x["kind"] == "read"} == {label: "read", derived: "corrected"}
    info = admin.get(f"/api/books/{book}/runs/read/{derived}").json()
    assert info["level"] == "corrected" and info["derived_from"]["label"] == label and len(info["corrections"]) == 1
    assert info["identity"] != admin.get(base).json()["identity"]
    after = _page(admin, book, "read", derived, 1)
    assert after["blocks"][0]["content"] == "fixed" and after["blocks"][0]["reading"]["outcome"] == "corrected"
    assert after["blocks"][0]["reading"]["corrected"]["author"] == "root" and after["blocks"][0]["hit_ceiling"] is None
    assert after["blocks"][0]["kind"] == "text"
    assert _page(admin, book, "read", label, 1)["blocks"][0]["content"] == "read", "the base keeps the model's word"
    assert after["blocks"][1]["reading"]["outcome"] != "corrected", "the other blocks keep their reading"
    doc = admin.get(f"/api/books/{book}/runs/read/{derived}/document").json()
    assert doc["run"]["label"] == derived and doc["pages"][1]["blocks"][0]["content"] == "fixed"
    assert "fixed" in admin.get(f"/api/books/{book}/runs/read/{derived}/export/text").text
    crop = admin.get(f"/api/books/{book}/runs/read/{derived}/crops/p0001-b0")
    assert crop.status_code == 200 and crop.content[:4] == b"\x89PNG"
    first = info["identity"]
    r = admin.post(f"/api/books/{book}/runs/read/{derived}/corrections", json={"anchor": "p0001-b1", "label": "figure_title"})
    assert r.status_code == 200 and len(r.json()["corrections"]) == 2
    assert admin.get(f"/api/books/{book}/runs/read/{derived}").json()["identity"] != first, "a correction changes the identity"
    relabelled = _page(admin, book, "read", derived, 1)["blocks"][1]
    assert relabelled["label"] == "figure_title" and relabelled["reading"]["outcome"] != "corrected", "a label keeps the reading"
    r = admin.post(f"{base}/corrections", json={"anchor": "p0002-b0", "content": None})
    assert r.status_code == 200, r.text
    erased = _page(admin, book, "read", derived, 2)["blocks"][0]
    assert erased["content"] is None and erased["as_picture"] and erased["why_empty"] == "erased by a correction"
    assert admin.delete(f"{base}/corrections/2").status_code == 200
    r = admin.post(f"{base}/corrections", json={"anchor": "p0001-b2", "drop": True})
    assert r.status_code == 200 and len(r.json()["corrections"]) == 3
    assert [b["block_id"] for b in _page(admin, book, "read", derived, 1)["blocks"]] == [0, 1]
    assert len(_page(admin, book, "read", label, 1)["blocks"]) == 3
    assert admin.post(f"{base}/corrections", json={"anchor": "p0001-b2", "label": "text"}).status_code == 409, "dropped already"
    assert admin.post(f"{base}/corrections", json={"anchor": "p0001-b0", "drop": False}).status_code == 422
    assert admin.post(f"{base}/corrections", json={"anchor": "p0001-b0", "label": "nope"}).status_code == 409
    assert admin.post(f"{base}/corrections", json={"anchor": "p0001-b9", "content": "x"}).status_code == 409
    assert admin.post(f"{base}/corrections", json={"anchor": "p0001-b0"}).status_code == 409
    assert admin.post(f"{base}/corrections", json={"anchor": "b0", "content": "x"}).status_code == 422
    assert admin.post(f"{base}/corrections", json={"anchor": "p0001-b0", "content": "x", "extra": 1}).status_code == 422
    recs = admin.get(f"/api/books/{book}/runs/read/{derived}/pages/1/metrics").json()
    assert {x["metric"] for x in recs} == {"fitness", "contour"}, "a derived run is measured like any run"
    with open(os.path.join(home, "bench", "tiny", "read", derived, "run.json"), encoding="utf-8") as f:
        snap = json.load(f)
    assert {k: snap["derived_from"][k] for k in ("kind", "label", "identity")} == {"kind": "read", "label": label, "identity": admin.get(base).json()["identity"]}
    assert os.path.islink(os.path.join(home, "bench", "tiny", "read", derived, "crops"))
    assert snap["derived_from"]["when"] and admin.get(f"/api/books/{book}/runs/read/{derived}").json()["stale"] is False
    base_snap = os.path.join(home, "bench", "tiny", "read", label, "run.json")
    with open(base_snap, encoding="utf-8") as f:
        again = json.load(f)
    again["when"] = "2030-01-01T00:00:00+0000"
    with open(base_snap, "w", encoding="utf-8") as f:
        json.dump(again, f)
    assert admin.get(f"/api/books/{book}/runs/read/{derived}").json()["stale"] is True, "the base ran again"
    assert admin.get(f"{base}/corrections").json()["stale"] is True
    r = admin.post(f"/api/books/{book}/runs/read/{derived}/corrections/again")
    assert r.status_code == 200 and r.json()["stale"] is False and len(r.json()["corrections"]) == 3
    aside = os.path.join(home, "bench", "tiny", "read", f"{label}.old")
    shutil.copytree(os.path.join(home, "bench", "tiny", "read", label), aside)
    assert f"{label}.old" not in [x["label"] for x in admin.get(f"/api/books/{book}/runs").json()]
    assert admin.get(f"/api/books/{book}/runs/read/{label}.old").status_code == 409
    shutil.rmtree(aside)
    r = admin.delete(f"{base}/corrections/0")
    assert r.status_code == 200 and len(r.json()["corrections"]) == 2
    assert _page(admin, book, "read", derived, 1)["blocks"][0]["content"] == "read"
    assert admin.delete(f"{base}/corrections/5").status_code == 409
    admin.delete(f"{base}/corrections/0")
    r = admin.delete(f"/api/books/{book}/runs/read/{derived}/corrections/0")
    assert r.status_code == 200 and r.json() == {"base": label, "run": None, "corrections": [], "stale": False}
    assert not os.path.exists(os.path.join(home, "bench", "tiny", "read", derived))
    assert admin.get(f"/api/books/{book}/runs/read/{derived}").status_code == 409
    user = as_user(app, "ann")
    assert user.get(f"{base}/corrections").status_code == 409, "another store"
    own = os.path.join(home, "bench", "tiny", "read", f"{label}.corrected")
    shutil.copytree(os.path.join(home, "bench", "tiny", "read", label), own)
    r = admin.post(f"{base}/corrections", json={"anchor": "p0001-b0", "content": "x"})
    assert r.status_code == 409 and "run of its own" in r.json()["error"], "a model run by that name is not rewritten"
    assert _page(admin, book, "read", f"{label}.corrected", 1)["blocks"][0]["content"] == "read"
