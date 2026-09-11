import json
import pytest
from backend import service
from backend import job
from backend import knobs
from backend.errors import Refusal

PRESETS = {"fast": {"kind": "layout", "endpoint": "http://127.0.0.1:1/", "knobs": {"PAGE_DPI": 72}}}


def test_a_user_store_runs_a_preset_whole_or_the_defaults_and_the_admin_anything(tmp_path):
    user = str(tmp_path / "alice")
    service.check(user, {"PAGE_DPI": "72"}, PRESETS)
    service.check(user, {}, PRESETS)
    with pytest.raises(Refusal):
        service.check(user, {"PAGE_DPI": "73"}, PRESETS)
    with pytest.raises(Refusal):
        service.check(user, {"PAGE_DPI": "72", "CROP_MARGIN": "0"}, PRESETS)
    service.check(service.admin(), {"PAGE_DPI": "73"}, PRESETS)
    with pytest.raises(Refusal):
        service.detect(user, str(tmp_path / "elsewhere" / "book.pdf"), {})


def test_the_registry_is_checked_entry_by_entry():
    bad = [
        {"x": {"kind": "layout", "knobs": {}}},
        {"x": {"kind": "layout", "endpoint": "e", "image": "i", "provider": "docker", "knobs": {}}},
        {"x": {"kind": "other", "endpoint": "e", "knobs": {}}},
        {"x": {"kind": "layout", "endpoint": "e", "knobs": {"NOT_A_KNOB": "1"}}},
        {"x": {"kind": "layout", "image": "i", "knobs": {}}},
        {"x": []},
        [],
    ]
    for raw in bad[2:4] + bad[5:]:
        with pytest.raises(Refusal):
            service.check_entries(raw)
    assert service.check_entries({"m": {"kind": "reader", "endpoint": "http://h/v1", "knobs": {"PAGE_DPI": 72}}})


def test_a_named_entry_fills_the_endpoint_after_the_check_and_carries_its_key(tmp_path, monkeypatch):
    presets = {
        "lay": {"kind": "layout", "endpoint": "http://127.0.0.1:9/", "knobs": {"PAGE_DPI": "72"}},
        "vlm": {
            "kind": "reader",
            "endpoint": "http://127.0.0.1:9/v1",
            "knobs": {},
            "api_key": "sk-a-secret",
        },
        "img": {"kind": "layout", "image": "ghcr.io/x/y:1", "provider": "docker", "knobs": {}},
    }
    monkeypatch.setattr(service, "models", lambda: presets)
    user = str(tmp_path / "bob")
    j = service._job(user, {"PAGE_DPI": "72"}, "lay")
    assert j.settings["LAYOUT_ENDPOINT"] == "http://127.0.0.1:9/"
    assert j.settings["PAGE_DPI"] == "72"
    assert service._job(user, {}, "lay").settings["PAGE_DPI"] == "72"
    with pytest.raises(Refusal):
        service._job(user, {"PAGE_DPI": "73"}, "lay")
    with pytest.raises(Refusal):
        service._job(user, {}, "nope")
    with pytest.raises(Refusal, match="fleet"):
        monkeypatch.setenv("BOOKSMITH_FLEET", "http://127.0.0.1:1")
        service._job(user, {}, "img")
    j = service._job(service.admin(), {}, "vlm")
    assert j.settings["VLM_ENDPOINT"] == "http://127.0.0.1:9/v1"
    assert j.secrets["VLM_API_KEY"] == "sk-a-secret"
    with j.active():
        snap = knobs.snapshot()
    assert "sk-a-secret" not in json.dumps(snap), "the key reached a snapshot"
    presets["lay"]["api_key"] = "sk-lay"
    with job.Job(secrets={"VLM_API_KEY": "sk-operator"}).active():
        mine = service._job(user, {}, "lay")
        theirs = service._job(service.admin(), {}, "lay")
    assert mine.secrets == {"LAYOUT_API_KEY": "sk-lay"}
    assert theirs.secrets == {"VLM_API_KEY": "sk-operator", "LAYOUT_API_KEY": "sk-lay"}
