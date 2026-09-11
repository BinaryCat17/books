import pytest

from fleet import vast
from fleet.errors import Refusal


class Sdk:
    def __init__(self):
        self.created = []
        self.instances = []

    def show_user(self):
        return {"credit": 1.0}

    def search_offers(self, query, order, storage):
        assert "gpu_name=RTX_4090" in query and "dph_total<" in query
        return [{"id": 2, "dph_total": 0.4, "machine_id": 7}, {"id": 1, "dph_total": 0.3, "machine_id": 5}]

    def create_instance(self, **kw):
        self.created.append(kw)
        self.instances.append({"id": 99, "label": kw["label"], "actual_status": "running", "public_ipaddr": "1.2.3.4",
                               "ports": {"8000/tcp": [{"HostPort": "40001"}]}})
        return {"new_contract": 99}

    def show_instance(self, id):
        return next((i for i in self.instances if i["id"] == id), None)

    def show_instances(self):
        return list(self.instances)

    def destroy_instance(self, id):
        self.instances = [i for i in self.instances if i["id"] != id]
        return {"success": True}


def test_the_cheapest_offer_is_taken_and_the_port_is_published():
    sdk = Sdk()
    v = vast.Vast(sdk)
    from fleet import registry

    entry = registry.check({"vl": {"kind": "reader", "image": "model-vl", "provider": "vast", "env": {"MODEL_NAME": "m"},
                                   "max_dph": 0.5, "budget_usd": 2.0}})["vl"]
    h = v.start("vl", entry, "k" * 32)
    assert h["id"] == "99" and h["rate_usd_h"] == 0.3
    kw = sdk.created[0]
    assert kw["id"] == 1 and kw["image"] == "model-vl" and kw["label"] == "bs-svc-vl" and kw["runtype"] == "args"
    assert "-p 8000:8000" in kw["env"] and "-e BOOKSMITH_SERVE_KEY=" + "k" * 32 in kw["env"] and "-e MODEL_NAME=m" in kw["env"]
    assert "-e BOOKSMITH_PORT=8000" in kw["env"] and "-e BOOKSMITH_IDLE_S=1800" in kw["env"]
    assert v.endpoint("99", 8000) == "http://1.2.3.4:40001"
    assert v.list() == [{"id": "99", "model": "vl", "state": "running"}]
    assert v.alive("99")
    v.stop("99")
    assert not v.alive("99")


def test_a_rental_that_publishes_its_port_late_or_dies_is_followed(home, monkeypatch):
    from fleet import registry
    from fleet.placements import Fleet

    sdk = Sdk()
    v = vast.Vast(sdk)
    registry.save({"vl": {"kind": "reader", "image": "model-vl", "provider": "vast", "budget_usd": 2.0}})
    sdk.late = 2

    def show_instance(id):
        inst = next((i for i in sdk.instances if i["id"] == id), None)
        if inst and sdk.late > 0:
            sdk.late -= 1
            return {**inst, "ports": {}}
        return inst

    sdk.show_instance = show_instance
    f = Fleet({"vast": v}, probe=lambda e, k: e.endswith(":40001"), boot_s=60, poll_s=0.01)
    got = f.ensure("vl", "j1")
    assert got["endpoint"] == "http://1.2.3.4:40001" and f.placements()[0]["rate_usd_h"] == 0.3
    f.stop(got["placement"])
    sdk.instances = []
    sdk.late = 0
    g = Fleet({"vast": v}, probe=lambda e, k: False, boot_s=60, poll_s=0.01)
    import threading

    def die():
        for i in sdk.instances:
            i["actual_status"] = "exited"

    threading.Timer(0.05, die).start()
    with pytest.raises(Refusal, match="died"):
        g.ensure("vl", "j2")
    assert g.placements() == [] and g.ledger()[-1]["why"] == "died while starting"
    h = Fleet({"vast": v}, probe=lambda e, k: True, boot_s=60, poll_s=0.01)
    pid = h.ensure("vl", "j3")["placement"]
    real = sdk.show_instances
    sdk.show_instances = lambda: []
    assert h.reconcile()["gone"] == 0, "an empty listing is not proof that a live instance is gone"
    sdk.show_instances = real
    assert h.placements()[0]["id"] == pid


@pytest.mark.vast
def test_the_account_answers_offers():
    pytest.importorskip("vastai")
    v = vast.Vast()
    if not v.available():
        pytest.skip("no vast account here")
    offers = v.offers({"gpu": "RTX_4090", "max_dph": 0.6, "disk_gb": 40})
    assert offers and all("dph_total" in o for o in offers)
