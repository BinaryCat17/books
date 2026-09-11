import json
import os

from backend import document, schema, service, settings
from conftest import make_bench
from fake_layout import FakeLayout
from fake_vlm import FakeVlm
from support import said


def test_the_run_the_document_and_the_export_keep_the_contracts(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("BOOKSMITH_HOME", str(home))
    b = make_bench(str(home / "bench" / "tiny"))
    for i in range(b.pages):
        with open(os.path.join(b.truth_dir, f"{i:04d}.json"), encoding="utf-8") as f:
            schema.validate(json.load(f), "page.schema.json")
    with FakeLayout(b.truth_dir) as fake:
        schema.validate(fake.describe.to_json(), "describe.schema.json")
        with said():
            rd = service.detect(str(home), b.root, {"LAYOUT_ENDPOINT": fake.url})
    with open(os.path.join(rd, "run.json"), encoding="utf-8") as f:
        schema.validate(json.load(f), "snapshot.schema.json")
    with said():
        d = document.write(rd)
    schema.validate(d, "document.schema.json")
    assert d["run"]["label"] == "truth" and len(d["pages"]) == b.pages
    assert {blk["role"] for blk in d["pages"][0]["blocks"]} == {"text", "artifact"}
    assert os.path.isfile(os.path.join(rd, "document.json"))
    assert document.write(rd) == d
    assert settings.Settings.from_env().relative(str(home)) == ""
    with FakeVlm({"text": "read", "finish": "stop"}) as vlm, said():
        read_dir = service.read(str(home), rd, {"VLM_ENDPOINT": vlm.url, "MODEL_NAME": vlm.model}, pages="1")
    with open(os.path.join(read_dir, "run.json"), encoding="utf-8") as f:
        schema.validate(json.load(f), "snapshot.schema.json")
    with said():
        rdoc = document.write(read_dir)
    schema.validate(rdoc, "document.schema.json")
    assert rdoc["run"]["kind"] == "read" and rdoc["observed"]
    assert any(blk["content"] == "read" for pg in rdoc["pages"] for blk in pg["blocks"])
