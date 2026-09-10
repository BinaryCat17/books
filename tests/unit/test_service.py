"""What a store other than the admin's may run, what the registry admits, and
what a named entry adds to a job: its endpoint after the check, its key as
a secret and never as a value."""
import json

import pytest

from booksmith import service
from booksmith.core import job, knobs
from booksmith.core.errors import Refusal

PRESETS = {"fast": {"kind": "layout", "endpoint": "http://127.0.0.1:1/",
                    "knobs": {"PAGE_DPI": 72}}}


def test_a_user_store_runs_a_preset_whole_or_the_defaults_and_the_admin_anything(tmp_path):
    user = str(tmp_path / "alice")
    service.check(user, {"PAGE_DPI": "72"}, PRESETS)
    service.check(user, {}, PRESETS)
    with pytest.raises(Refusal):
        service.check(user, {"PAGE_DPI": "73"}, PRESETS)
    with pytest.raises(Refusal):
        service.check(user, {"PAGE_DPI": "72", "CROP_MARGIN": "0"}, PRESETS)
    service.check(service.ADMIN, {"PAGE_DPI": "73"}, PRESETS)
    with pytest.raises(Refusal):
        service.detect(user, str(tmp_path / "elsewhere" / "book.pdf"), {})


def test_the_registry_is_checked_entry_by_entry():
    """An entry that cannot be run is refused by name, not carried along."""
    bad = [
        {"x": {"kind": "layout", "knobs": {}}},                # nowhere to run
        {"x": {"kind": "layout", "endpoint": "e", "image": "i",
               "provider": "docker", "knobs": {}}},           # both
        {"x": {"kind": "other", "endpoint": "e", "knobs": {}}},
        {"x": {"kind": "layout", "endpoint": "e",
               "knobs": {"NOT_A_KNOB": "1"}}},
        {"x": {"kind": "layout", "image": "i", "knobs": {}}},  # no provider
        {"x": []},
        [],
    ]
    for raw in bad:
        with pytest.raises(Refusal):
            service.registry(raw)
    ok = service.registry({"m": {"kind": "reader", "endpoint": "http://h/v1",
                                 "knobs": {"PAGE_DPI": 72}}})
    assert ok["m"]["knobs"] == {"PAGE_DPI": "72"}, "knob values are strings"


def test_a_named_entry_fills_the_endpoint_after_the_check_and_carries_its_key(tmp_path, monkeypatch):
    presets = {
        "lay": {"kind": "layout", "endpoint": "http://127.0.0.1:9/",
                "knobs": {"PAGE_DPI": "72"}},
        "vlm": {"kind": "reader", "endpoint": "http://127.0.0.1:9/v1",
                "knobs": {}, "api_key": "sk-a-secret"},
        "img": {"kind": "layout", "image": "ghcr.io/x/y:1",
                "provider": "docker", "knobs": {}},
    }
    monkeypatch.setattr(service, "models", lambda: presets)
    user = str(tmp_path / "bob")
    j = service._job(user, {"PAGE_DPI": "72"}, "lay")
    assert j.settings["LAYOUT_ADAPTER"] == "served"
    assert j.settings["LAYOUT_ENDPOINT"] == "http://127.0.0.1:9/"
    assert j.settings["PAGE_DPI"] == "72"
    # Empty settings under a named entry run the entry's knobs, not the
    # defaults: a preset runs whole.
    assert service._job(user, {}, "lay").settings["PAGE_DPI"] == "72"
    # The check sees the user's settings, not the settings plus the endpoint.
    with pytest.raises(Refusal):
        service._job(user, {"PAGE_DPI": "73"}, "lay")
    with pytest.raises(Refusal):
        service._job(user, {}, "nope")
    with pytest.raises(Refusal):
        service._job(user, {}, "img")
    j = service._job(service.ADMIN, {}, "vlm")
    assert j.settings["VLM_ENDPOINT"] == "http://127.0.0.1:9/v1"
    assert j.secrets["VLM_API_KEY"] == "sk-a-secret"
    with j.active():
        snap = knobs.snapshot()
    assert "sk-a-secret" not in json.dumps(snap), "the key reached a snapshot"
    # A layout entry's key travels under the layout adapter's name, and a
    # store other than the admin's never inherits the process's own key.
    presets["lay"]["api_key"] = "sk-lay"
    with job.Job(secrets={"VLM_API_KEY": "sk-operator"}).active():
        mine = service._job(user, {}, "lay")
        theirs = service._job(service.ADMIN, {}, "lay")
    assert mine.secrets == {"LAYOUT_API_KEY": "sk-lay"}
    assert theirs.secrets == {"VLM_API_KEY": "sk-operator", "LAYOUT_API_KEY": "sk-lay"}
