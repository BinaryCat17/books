import pytest

from fleet import vast


class Sdk:
    def __init__(self):
        self.created = []
        self.instances = []

    def show_user(self):
        return {"credit": 1.0}

    def search_offers(self, query, order, storage):
        assert "gpu_name=RTX_4090" in query and "dph_total<0.5" in query
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
    entry = {"image": "model-vl", "port": 8000, "env": {"MODEL_NAME": "m"}, "max_dph": 0.5, "budget_usd": 2.0, "disk_gb": 40}
    h = v.start("vl", entry, "k" * 32)
    assert h["id"] == "99" and h["rate_usd_h"] == 0.3
    kw = sdk.created[0]
    assert kw["id"] == 1 and kw["image"] == "model-vl" and kw["label"] == "bs-svc-vl" and kw["runtype"] == "args"
    assert "-p 8000:8000" in kw["env"] and "-e BOOKSMITH_SERVE_KEY=" + "k" * 32 in kw["env"] and "-e MODEL_NAME=m" in kw["env"]
    assert v.endpoint("99", 8000) == "http://1.2.3.4:40001"
    assert v.list() == [{"id": "99", "model": "vl", "state": "running"}]
    assert v.alive("99")
    v.RETRY = ()
    import time

    time.sleep_ = time.sleep
    time.sleep = lambda s: None
    try:
        v.stop("99")
    finally:
        time.sleep = time.sleep_
    assert not v.alive("99")


@pytest.mark.vast
def test_the_account_answers_offers():
    pytest.importorskip("vastai")
    v = vast.Vast()
    if not v.available():
        pytest.skip("no vast account here")
    offers = v.offers({"gpu": "RTX_4090", "max_dph": 0.6, "disk_gb": 40})
    assert offers and all("dph_total" in o for o in offers)
