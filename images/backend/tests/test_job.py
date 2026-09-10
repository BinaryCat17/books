import pytest
import support
from backend import job
from backend import knobs
from backend.errors import Cancelled, Refusal
from backend.log import log


def test_a_bound_setting_wins_and_an_undeclared_one_is_refused():
    with support.env(PAGE_DPI="300"):
        with job.Job(settings={"PAGE_DPI": "72"}).active():
            assert knobs.knob("PAGE_DPI") == "72"
            assert knobs.snapshot()["PAGE_DPI"]["set_externally"] is True
            assert knobs.passthrough() == {"PAGE_DPI": "72"}
        assert knobs.knob("PAGE_DPI") == "300"
    with pytest.raises(Refusal), job.Job(settings={"NOT_A_KNOB": "1"}).active():
        pass


def test_a_secret_is_not_a_setting_and_reaches_no_snapshot():
    j = job.Job(settings={"PAGE_DPI": "72"}, secrets={"VLM_API_KEY": "sk-x"})
    with j.active():
        assert job.current().secrets["VLM_API_KEY"] == "sk-x"
        snap = knobs.snapshot()
    assert "sk-x" not in str(snap) and "VLM_API_KEY" not in snap
    assert job.Job().secrets == {}


def test_a_stop_is_seen_by_check_and_a_field_reaches_the_sink_from_any_thread():
    events = []
    j = job.Job(sink=events.append)
    with j.active():
        log("p. 3 read", page=3, read=7)
        job.spawn(log, "from a thread").join()
        j.check()
        j.stop.set()
        with pytest.raises(Cancelled):
            j.check()
    assert events == [{"text": "p. 3 read", "page": 3, "read": 7}, {"text": "from a thread"}]
