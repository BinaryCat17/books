"""The shim: a detector of the tree's own behind the three routes answers as
itself, a run through it is the run of that model, a vLLM behind describe
and health is read through unchanged, and a key is demanded when set."""
import json
import os
import threading
from contextlib import contextmanager

import pytest

import support
from booksmith.core import job, knobs, order, policy, served
from booksmith.core import page as page_mod
from booksmith.core.errors import Refusal
from booksmith.processing.layout import detect
from booksmith.processing.layout.base import Detector
from booksmith.processing.read import Ask
from booksmith.processing.read.transports import openai_http
from booksmith.serving import layout as serving_layout
from booksmith.serving import vlm as serving_vlm
from fake_layout import truth_pages
from fake_vlm import FakeVlm


class TruthDetector(Detector):
    """A detector answering the drawn bench's truth: the shim's half is what
    is checked here, not a model. It reads the one knob it declares."""
    name = "truth-detector"
    dir = "nowhere"
    policy_name = "PP-DocLayoutV2"

    def __init__(self, truth_dir):
        self.pages = truth_pages(truth_dir)
        self.labels = policy.POLICIES["PP-DocLayoutV2"].labels

    def label(self):
        return "truth"

    def fingerprint(self):
        return {"name": self.name, "model": "truth", "sha256_weights": "0" * 64,
                "reading_order": order.MODEL_RANK, "label_map": {},
                "prompts": {}}

    def knobs_read(self):
        return ("LAYOUT_SCORE_THRESHOLD",)

    def threshold_drift(self):
        return ()

    def read(self, image_path, index, dpi):
        # The value read at read time goes into the page: a request thread
        # that reads another job than the describe was taken under shows here.
        seen = knobs.knob("LAYOUT_SCORE_THRESHOLD")
        d = json.loads(json.dumps(self.pages[index]))
        for b in d["blocks"]:
            b.pop("source_category", None)
            b["content"], b["kind"] = None, "none"
        d["meta"] = {**d["meta"], "detector": self.name,
                     "boxes_accepted": len(d["blocks"]), "rank_ties": 0,
                     "best_rejected_by_class": {},
                     "reading_order": order.MODEL_RANK,
                     "threshold_read": seen}
        d["raw"] = None
        return page_mod.Page.from_json(d)


@contextmanager
def _up(module, svc):
    srv = module.serve(svc)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        yield f"http://127.0.0.1:{srv.server_address[1]}"
    finally:
        srv.shutdown()
        srv.server_close()


def _raster(bench, tmp_path):
    from booksmith.core import raster
    png = str(tmp_path / "p0.png")
    with raster.open_pdf(bench.pdf) as doc:
        raster.render(doc[0], 144).save(png)
    return png


def _client(url, **more):
    return job.Job(settings={"LAYOUT_ADAPTER": "served",
                             "LAYOUT_ENDPOINT": url, **more})


# ------------------------------------------------------------ the layout shim

def test_a_detector_behind_the_shim_is_the_same_experiment(slovar, tmp_path):
    """The server's knob values ride in the describe; a run through the shim
    hashes to the run of the same detector in this process under the same
    settings, whatever the client itself read."""
    png = _raster(slovar, tmp_path)
    with job.Job(settings={"LAYOUT_SCORE_THRESHOLD": "0.7"}).active():
        local = TruthDetector(slovar.truth_dir)
        svc = serving_layout.Service(local)
        want = local.read(png, 0, 144.0).to_json()
        mine = detect._identity(local, detect._knob_roles(local))
    assert svc.describe.knobs == {"LAYOUT_SCORE_THRESHOLD": "0.7"}
    assert svc.describe.classes == policy.VOCABULARIES["PP-DocLayoutV2"]
    assert svc.describe.reading_order == "own"
    assert svc.describe.adapter_sha256 and len(svc.describe.adapter_sha256) == 64
    with _up(serving_layout, svc) as url:
        with _client(url).active():
            det = detect._adapter()
            assert det.label() == "truth" and det.served()["kind"] == "layout"
            got = det.read(png, 0, 144.0).to_json()
            theirs = detect._identity(det, detect._knob_roles(det))
        assert got == want, "the page changed on the way through the shim"
        assert got["meta"]["threshold_read"] == "0.7", (
            "the request thread read another job than the describe was taken under")
        health = served.Health.from_json(served.fetch(url + served.HEALTH))
        assert health.ready and health.requests == 1 and health.last_request
    assert theirs == mine, "a served run is not the in-process run's experiment"


def test_the_shim_demands_its_key_and_refuses_what_is_not_a_page(slovar, tmp_path):
    png = _raster(slovar, tmp_path)
    svc = serving_layout.Service(TruthDetector(slovar.truth_dir), key="k")
    with _up(serving_layout, svc) as url:
        with _client(url).active(), pytest.raises(Refusal) as e:
            detect._adapter()
        assert "401" in str(e.value)
        with job.Job(settings={"LAYOUT_ADAPTER": "served", "LAYOUT_ENDPOINT": url},
                     secrets={"LAYOUT_API_KEY": "k"}).active():
            det = detect._adapter()
            assert det.read(png, 0, 144.0).index == 0
        # Not a PNG: a 400 with the reason, which the adapter refuses aloud.
        with pytest.raises(served.Unreachable) as e2:
            served.fetch(url + served.LAYOUT,
                         {"index": 0, "dpi": 144.0, "image": "data:image/jpeg;base64,AAAA"},
                         headers=served.bearer("k"))
        assert e2.value.code == 400 and "PNG" in e2.value.why
    with pytest.raises(Refusal):
        serving_layout.Service(TruthDetector(slovar.truth_dir), kind="hybrid")


@pytest.mark.parametrize("model", ["PP-DocLayoutV2", "PP-DocLayout_plus-L"])
def test_the_real_detector_through_the_shim_gives_the_in_process_pages(slovar, tmp_path, model):
    """With weights on this machine: the tree's own detector behind the shim
    answers the pages it answers in process, byte for byte after `raw`, and
    the two runs are one experiment -- the describe taken before any page
    and the snapshot after the book saying the same thing, rank or none."""
    settings = {"LAYOUT_MODEL_NAME": model}
    try:
        with support.said(), job.Job(settings=settings).active():
            local = detect._adapter()
            svc = serving_layout.Service(local)
            mine = detect._identity(local, detect._knob_roles(local))
    except Exception as e:  # weights or onnxruntime absent
        pytest.skip(f"no in-process {model} here: {type(e).__name__}: {str(e)[:60]}")
    png = _raster(slovar, tmp_path)
    with job.Job(settings=settings).active():
        want = local.read(png, 0, 144.0).to_json()
        after = detect._identity(local, detect._knob_roles(local))
    assert after == mine, "the identity moved once a page was read"
    assert svc.describe.reading_order == ("own" if model == "PP-DocLayoutV2" else "none")
    want.pop("raw", None)
    with _up(serving_layout, svc) as url:
        with _client(url).active():
            det = detect._adapter()
            got = det.read(png, 0, 144.0).to_json()
            theirs = detect._identity(det, detect._knob_roles(det))
    got.pop("raw", None)
    assert got == want
    assert theirs == mine


def test_a_stop_ends_the_server(slovar):
    """`docker stop` is a signal, and the command line turns a signal into
    the job's stop: the server must end on it, not on a kill ten seconds on."""
    from booksmith.serving import threads
    svc = serving_layout.Service(TruthDetector(slovar.truth_dir))
    lines = []
    j = job.Job(sink=lambda e: lines.append(e["text"]))
    with j.active():
        srv = serving_layout.serve(svc)
        threading.Timer(0.3, j.stop.set).start()
        threads.run_until_stopped(srv, "truth")
    assert any("stopping" in ln for ln in lines)
    with pytest.raises(served.Unreachable):
        served.fetch(f"http://127.0.0.1:{srv.server_address[1]}" + served.HEALTH, timeout=1)


# --------------------------------------------------------------- the vlm shim

def test_a_vllm_behind_the_shim_is_read_through_unchanged(slovar, tmp_path):
    png = _raster(slovar, tmp_path)
    with FakeVlm({"text": "the words", "finish": "stop"}) as fake:
        with job.Job(settings={"VLM_TIMEOUT_S": "5"}).active():
            svc = serving_vlm.Service(fake.url.removesuffix("/v1"), fake.model)
        assert svc.describe.kind == "reader"
        assert svc.describe.openai == {"base": "/v1", "model": fake.model}
        assert svc.describe.fingerprint["sha256_weights"] is None
        assert "why_empty" in svc.describe.fingerprint
        assert svc.ready()
        with _up(serving_vlm, svc) as url:
            with job.Job(settings={"VLM_ENDPOINT": url + "/v1",
                                   "MODEL_NAME": fake.model}).active():
                t = openai_http.Http()
                who = t.check()
                assert who["matched"] and who["describe"]["kind"] == "reader"
                said = t.send(Ask(anchor="p0000-b0", image=png, prompt="OCR:",
                                  kind="text", label="text",
                                  params={"temperature": 0}))
            assert said.text == "the words" and said.error is None
            assert fake.seen[-1]["prompt"] == "OCR:"
            health = served.Health.from_json(served.fetch(url + served.HEALTH))
            assert health.ready and health.requests == 1
            with job.Job(settings={"VLM_ENDPOINT": url + "/v1",
                                   "MODEL_NAME": "another"}).active():
                with pytest.raises(Refusal):
                    openai_http.Http().check()


def test_the_weights_hash_is_taken_once_and_the_command_is_the_run_scripts(tmp_path):
    d = tmp_path / "vl"
    d.mkdir()
    (d / "model-00001.safetensors").write_bytes(b"\x00" * 4096)
    (d / "config.json").write_text("{}", encoding="utf-8")
    (d / "chat_template.jinja").write_text("x", encoding="utf-8")   # not hashed
    first = serving_vlm.weights_sha256(str(d))
    assert os.path.isfile(d / serving_vlm.CACHE)
    assert serving_vlm.weights_sha256(str(d)) == first
    (d / "model-00001.safetensors").write_bytes(b"\x01" * 4096)
    assert serving_vlm.weights_sha256(str(d)) != first, "the cache outlived the weights"
    with pytest.raises(Refusal):
        serving_vlm.weights_sha256(str(tmp_path))
    argv = serving_vlm.command("/models/vl", "M", 8118)
    assert argv[:3] == ["vllm", "serve", "/models/vl"]
    assert "--served-model-name" in argv and "M" in argv
    assert argv[argv.index("--host") + 1] == "127.0.0.1"
    assert argv[argv.index("--gpu-memory-utilization") + 1] == "0.60"
