"""The job: settings over the environment, a stop, and one sink."""
import pytest
import support

from booksmith.core import job, knobs
from booksmith.core.errors import Cancelled, Refusal
from booksmith.core.log import log


def test_a_bound_setting_wins_and_an_undeclared_one_is_refused():
    with support.env(PAGE_DPI="300"):
        with job.Job(settings={"PAGE_DPI": "72"}).active():
            assert knobs.knob("PAGE_DPI") == "72"
            assert knobs.snapshot()["PAGE_DPI"]["set_externally"] is True
            assert knobs.passthrough() == {"PAGE_DPI": "72"}
        assert knobs.knob("PAGE_DPI") == "300"
    with pytest.raises(Refusal), job.Job(settings={"NOT_A_KNOB": "1"}).active():
        pass


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
    assert events == [{"text": "p. 3 read", "page": 3, "read": 7},
                      {"text": "from a thread"}]
