import json
import os

import jsonschema
from fastapi.testclient import TestClient

from fake_vlm import FakeVlm
from vlm import job, serve
from vlm.errors import Refusal

SCHEMA = os.path.join(os.path.dirname(__file__), "..", "..", "..", "schema")


def _schema(name):
    with open(os.path.join(SCHEMA, name), encoding="utf-8") as f:
        return json.load(f)


def test_a_vllm_behind_the_shim_is_read_through_unchanged():
    with FakeVlm({"text": "the words", "finish": "stop"}) as fake:
        with job.Job(settings={"VLM_TIMEOUT_S": "5", "MODEL_NAME": fake.model}).active():
            svc = serve.Service(fake.url.removesuffix("/v1"), fake.model, key="k")
        assert svc.describe.kind == "reader" and svc.ready()
        c = TestClient(serve.create_app(svc))
        assert c.get("/booksmith/describe").status_code == 401
        h = {"Authorization": "Bearer k"}
        d = c.get("/booksmith/describe", headers=h).json()
        jsonschema.validate(d, _schema("describe.schema.json"))
        assert (
            d["openai"] == {"base": "/v1", "model": fake.model} and d["fingerprint"]["sha256_weights"] is None
        )
        assert fake.model in [m["id"] for m in c.get("/v1/models", headers=h).json()["data"]]
        body = {
            "model": fake.model,
            "messages": [{"role": "user", "content": [{"type": "text", "text": "OCR:"}]}],
        }
        r = c.post("/v1/chat/completions", json=body, headers=h)
        assert r.status_code == 200 and "the words" in r.text
        assert fake.seen[-1]["prompt"] == "OCR:"
        health = c.get("/booksmith/health", headers=h).json()
        jsonschema.validate(health, _schema("health.schema.json"))
        assert health["ready"] and health["requests"] == 1


def test_the_weights_hash_is_taken_once_and_the_command_is_pinned(tmp_path):
    d = tmp_path / "vl"
    d.mkdir()
    (d / "model-00001.safetensors").write_bytes(b"\x00" * 4096)
    (d / "config.json").write_text("{}", encoding="utf-8")
    first = serve.weights_sha256(str(d))
    assert os.path.isfile(d / serve.CACHE) and serve.weights_sha256(str(d)) == first
    (d / "model-00001.safetensors").write_bytes(b"\x01" * 4096)
    assert serve.weights_sha256(str(d)) != first
    try:
        serve.weights_sha256(str(tmp_path))
        raise AssertionError("no weights, no hash")
    except Refusal:
        pass
    argv = serve.command("/models/vl", "M", 8118)
    assert argv[:3] == ["vllm", "serve", "/models/vl"] and "--served-model-name" in argv
