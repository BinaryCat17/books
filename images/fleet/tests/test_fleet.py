import json
import os

import pytest
from fastapi.testclient import TestClient

from fake_provider import FakeProvider
from fleet import registry
from fleet.app import create_app
from fleet.errors import Refusal
from fleet.placements import Fleet


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def _registry(entries):
    registry.save(entries)


def test_the_registry_is_checked_and_defaulted(home):
    for bad in ({"x": {"kind": "layout"}}, {"x": {"kind": "other", "endpoint": "e"}},
                {"x": {"kind": "layout", "endpoint": "e", "image": "i", "provider": "docker"}},
                {"x": {"kind": "layout", "image": "i"}},
                {"x": {"kind": "layout", "image": "i", "provider": "vast"}}):
        with pytest.raises(Refusal):
            registry.check(bad)
    got = registry.save({"m": {"kind": "reader", "endpoint": "http://h/v1", "knobs": {"PAGE_DPI": 72}},
                         "d": {"kind": "layout", "image": "img", "provider": "docker", "gpu": "any"}})
    assert got["m"]["knobs"] == {"PAGE_DPI": "72"} and got["m"]["idle_s"] == 600.0
    assert got["d"]["port"] == 8000 and got["d"]["budget_usd"] == 0.0
    assert registry.load() == got


def test_a_lease_reuses_a_ready_placement_and_idle_stops_it(home):
    clock = Clock()
    prov = FakeProvider()
    _registry({"lay": {"kind": "layout", "image": "img", "provider": "fake", "idle_s": 100},
               "fixed": {"kind": "reader", "endpoint": "http://h/v1", "api_key": "sk"}})
    f = Fleet({"fake": prov}, clock=clock)
    assert f.ensure("fixed", "j0") == {"endpoint": "http://h/v1", "key": "sk", "lease": None, "placement": None}
    a = f.ensure("lay", "j1")
    b = f.ensure("lay", "j2")
    assert a["placement"] == b["placement"] and prov.n == 1
    assert a["lease"] != b["lease"] and a["endpoint"].startswith("http://127.0.0.1:")
    assert f.ensure("lay", "j1")["lease"] == a["lease"], "one lease per job"
    assert f.sweep() == [] and len(f.leases()) == 2
    f.release("j1")
    clock.t += 110
    f.renew("j2")
    clock.t += 110
    assert f.sweep() == [] and len(f.leases()) == 1, "a leased placement is not idle"
    f.release("j2")
    clock.t += 50
    assert f.sweep() == []
    clock.t += 60
    assert f.sweep() == [a["placement"]] and prov.stopped == ["c1"]
    rows = f.ledger()
    assert rows[-1]["why"] == "idle" and rows[-1]["cost_usd"] == 0.0
    with open(os.path.join(home, "fleet", "placements.json"), encoding="utf-8") as fh:
        assert json.load(fh) == {"placements": {}, "leases": {}}


def test_an_expired_lease_frees_the_placement_and_a_budget_ends_it(home):
    clock = Clock()
    prov = FakeProvider(rate=2.0)
    _registry({"vl": {"kind": "reader", "image": "img", "provider": "fake", "idle_s": 15, "budget_usd": 1.0}})
    f = Fleet({"fake": prov}, clock=clock)
    a = f.ensure("vl", "j1")
    p = f.placements()[0]
    assert p["deadline"] == clock.t + 1800.0 and p["state"] == "ready"
    clock.t += 130
    f.sweep()
    assert f.leases() == [], "an unrenewed lease expires"
    assert f.placements()[0]["state"] == "ready", "an expired lease counts as use until its expiry"
    f.ensure("vl", "j3")
    assert f.renew("j3") == 1 and f.renew("nobody") == 0
    clock.t += 1800
    assert f.sweep() == [a["placement"]]
    assert f.ledger()[-1]["why"] == "budget" and f.ledger()[-1]["cost_usd"] > 1.0
    assert f.leases() == []


def test_reconcile_destroys_what_the_table_does_not_know_and_forgets_what_is_gone(home):
    prov = FakeProvider()
    _registry({"lay": {"kind": "layout", "image": "img", "provider": "fake"}})
    f = Fleet({"fake": prov})
    a = f.ensure("lay", "j1")
    prov.foreign.append("stray")
    assert f.reconcile() == {"adopted": 1, "destroyed": 1, "gone": 0}
    assert "stray" in prov.stopped and len(f.placements()) == 1
    prov.stop(f.placements()[0]["handle"])
    assert f.reconcile() == {"adopted": 0, "destroyed": 0, "gone": 1}
    assert f.placements() == [] and f.leases() == [] and a["lease"]


def test_a_placement_that_never_answers_is_stopped_at_the_boot_deadline(home):
    prov = FakeProvider(ready_after=1)
    _registry({"lay": {"kind": "layout", "image": "img", "provider": "fake"}})
    f = Fleet({"fake": prov}, boot_s=0.5)
    with pytest.raises(Refusal, match="not ready"):
        f.ensure("lay", "j1")
    assert prov.stopped == ["c1"] and f.placements() == []
    with pytest.raises(Refusal, match="not available"):
        Fleet({}).ensure("lay", "j1")


def test_the_routes(home):
    prov = FakeProvider()
    f = Fleet({"fake": prov})
    with TestClient(create_app(f, sweep_s=3600)) as c:
        assert c.put("/models", json={"lay": {"kind": "layout", "image": "img", "provider": "fake"}}).status_code == 200
        assert c.put("/models", json={"x": {"kind": "layout"}}).status_code == 409
        got = c.post("/leases", json={"model": "lay", "job": "job-1"}).json()
        assert got["lease"] and got["key"] and got["endpoint"]
        assert c.get("/placements").json()[0]["state"] == "ready" and "key" not in c.get("/placements").json()[0]
        assert c.post("/leases/renew", json={"job": "job-1"}).json() == {"renewed": 1}
        assert c.post("/leases/release", json={"job": "job-1"}).json() == {"released": 1}
        assert c.get("/leases").json() == []
        pid = got["placement"]
        assert c.delete(f"/placements/{pid}").json() == {"stopped": pid}
        assert c.delete(f"/placements/{pid}").status_code == 409
        assert c.get("/ledger").json()[-1]["why"] == "asked"
        assert c.post("/reconcile").json() == {"adopted": 0, "destroyed": 0, "gone": 0}
        assert c.get("/health").json()["providers"] == ["fake"]
        assert c.post("/leases", json={"model": "nope", "job": "j"}).status_code == 409
