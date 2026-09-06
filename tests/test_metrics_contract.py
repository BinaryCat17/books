"""Every registered metric obeys the contract, and the contract can fail.

`datasets.metrics.base` says what a metric returns: a `Record` whose
scalars carry a value, what it was counted over, and a reason when there is
no value. The three wrappers are checked on the slovar bench when it is on
disk (it is behind .gitignore: a skip with a reason otherwise), and the
contract itself is checked on made-up input so that a fresh clone still
checks something.
"""
import json
import os
import tempfile

import support
from booksmith.datasets import metrics as registry
from booksmith.datasets.bench import Bench, Run
from booksmith.datasets.metrics.base import (Metric, Probe, Record, Scalar,
                                             applicable, run_battery)

ROOT = os.path.dirname(os.path.dirname(support.SRC))
SLOVAR = os.path.join(ROOT, "bench", "slovar")


def _slovar():
    if not (os.path.isdir(os.path.join(SLOVAR, "truth"))
            and os.path.isdir(os.path.join(SLOVAR, "detect", "pages"))
            and os.path.isfile(os.path.join(SLOVAR, "slovar.pdf"))):
        support.skip("bench/slovar is not built here (books synth --book slovar)")
    b = Bench.open(SLOVAR)
    return b, b.run("detect")


def test_every_registered_metric_declares_the_contract():
    assert registry.METRICS, "no metric registered"
    for m in registry.METRICS:
        assert isinstance(m, Metric) and m.name, m
        assert m.needs and m.needs <= set(registry.base.NEEDS), (m.name, m.needs)
        assert "pages" in m.needs, f"{m.name} measures nothing without pages"
    assert len({m.name for m in registry.METRICS}) == len(registry.METRICS)


def test_a_scalar_without_a_value_must_say_why():
    try:
        Scalar(None)
    except ValueError:
        pass
    else:
        raise AssertionError("a valueless scalar with no reason was accepted")
    try:
        Scalar(True)
    except ValueError:
        pass
    else:
        raise AssertionError("a flag was accepted as a number")
    s = Scalar(None, (0, 5), why="nothing marked")
    assert s.to_json() == {"value": None, "over": {"n": 0, "of": 5}, "why": "nothing marked"}


def test_records_agree_with_the_raw_dict_they_carry():
    """The scalars are views of `detail`; a view that drifts from the dict
    is the hand-typed copy the table was built to abolish."""
    b, r = _slovar()
    for m in registry.METRICS:
        rec = m.run(b, r)
        assert rec.metric == m.name and rec.bench == "slovar" and rec.run == "detect"
        assert rec.detail and rec.scalars, m.name
        for k, s in rec.scalars.items():
            assert isinstance(s, Scalar), (m.name, k)
            if s.value is not None:
                assert isinstance(s.value, (int, float)), (m.name, k, s)
            else:
                assert s.why, (m.name, k)
        json.dumps(rec.to_json())          # serialisable, whole
    contour = registry.BY_NAME["contour"].run(b, r)
    d = contour.detail
    assert contour.scalars["artefacts_found"].value == d["totals"]["share"]
    assert contour.scalars["artefacts_found"].over == (d["totals"]["found"], d["totals"]["artifacts"])
    assert contour.params["COVER_MATCH"] == 0.75
    fit = registry.BY_NAME["fitness"].run(b, r)
    f = fit.detail
    assert abs(fit.scalars["ink_under_boxes"].value - f["ink_under_boxes"] / f["ink_total"]) < 1e-12


def test_applicability_is_by_prerequisite_not_by_trait():
    class Truthless:
        truth_dir = ""
        pdf = None

        def has_content(self, pages=None):
            return False

    class Golden(Truthless):
        truth_dir = "/t"

    class Full(Golden):
        pdf = "/x.pdf"

        def has_content(self, pages=None):
            return True

    names = lambda b: sorted(m.name for m in applicable(registry.METRICS, b, object()))
    assert names(Truthless()) == []
    assert names(Golden()) == ["contour"]
    assert names(Full()) == ["contour", "fitness", "text"]


def test_the_battery_loop_counts_what_it_printed():
    lines = []
    seen, mute, bad = run_battery([
        Probe("a spoiled thing", "the number falls", lambda: True),
        Probe("nothing to spoil", "no data", lambda: None),
        Probe("a spoiled thing the metric ignores", "the number falls", lambda: False),
        Probe("a probe that breaks", "the number falls", lambda: 1 / 0),
        Probe("a spoiled thing with a note", "falls", lambda: (True, "12 -> 3")),
    ], log=lines.append)
    assert (seen, mute, bad) == (5, 1, 2), (seen, mute, bad)
    assert any("THE PROBE THREW ZeroDivisionError" in l for l in lines), lines
    assert any("[12 -> 3]" in l for l in lines), lines
    assert sum("no data" in l for l in lines) == 1
