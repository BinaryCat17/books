"""The table: one parse, a guarded selection, records that come back.

`books bench all` is the deliverable of step 2a and had no check of its own
until its review said so. Built on a made-up bench with one metric, so a
fresh clone checks it; the real numbers are locked by the acceptance report
`table-slovar`.
"""
import json
import os
import tempfile

import support
from booksmith.core.errors import Refusal
from booksmith.datasets import table
from booksmith.datasets.bench import Bench
from booksmith.datasets.metrics.base import Record, Scalar
from test_bench import _bench, _page


def test_rows_refuse_an_unknown_and_an_inapplicable_metric():
    with tempfile.TemporaryDirectory() as d:
        b = Bench.open(_bench(os.path.join(d, "b")))
        run = b.run()
        try:
            table.rows(b, run, ["bogus"], log=lambda *a: None)
        except Refusal as e:
            assert "no metric named bogus" in str(e), e
        else:
            raise AssertionError("an unknown metric name was accepted")
        try:
            table.rows(b, run, ["text"], log=lambda *a: None)     # no content in this truth
        except Refusal as e:
            assert "text cannot be measured" in str(e) and "content" in str(e), e
        else:
            raise AssertionError("an inapplicable metric was measured")


def test_rows_parse_the_truth_once_and_pass_dicts_to_the_metrics():
    with tempfile.TemporaryDirectory() as d:
        b = Bench.open(_bench(os.path.join(d, "b")))
        loads = []
        real = b.pages
        b.pages = lambda: (loads.append(1), real())[1]
        recs = table.rows(b, b.run(), ["contour"], log=lambda *a: None)
    assert len(loads) == 1, f"the truth was parsed {len(loads)} times"
    assert [r.metric for r in recs] == ["contour"]
    assert recs[0].detail["book"].startswith("sha256 checked"), recs[0].detail["book"]


def test_records_come_back_from_disk_as_json_left_them():
    rec = Record("m", "b", "r",
                 {"a": Scalar(0.5, count=(1, 2)),
                  "c": Scalar(None, over=(0, 3), unit="pages", why="none marked")},
                 {"T": 1.5}, {"by_page": {3: 1.0}})
    with tempfile.TemporaryDirectory() as d:
        path = table.write_json([rec], os.path.join(d, "x.json"), log=lambda *a: None)
        back = table.read_json(path)
    assert len(back) == 1 and back[0].scalars == rec.scalars and back[0].params == rec.params
    # detail comes back as JSON left it: integer keys are strings there
    assert back[0].detail == json.loads(json.dumps(rec.detail))
    assert back[0].to_json() == json.loads(json.dumps(rec.to_json()))


def test_the_selection_names_its_own_result_file():
    with tempfile.TemporaryDirectory() as d:
        b = Bench.open(_bench(os.path.join(d, "b")))
        run = b.run()
    full = table.results_path(b, run)
    part = table.results_path(b, run, ["contour"])
    assert full.endswith("b-PP-DocLayoutV2.json") and part.endswith(
        "b-PP-DocLayoutV2-only-contour.json")


def test_render_prints_counts_coverage_and_footnotes():
    rec = Record("m", "b", "r", {
        "found": Scalar(0.5, count=(1, 2)),
        "order": Scalar(None, over=(0, 3), unit="pages", why="none marked"),
    }, {"T": 1})
    lines = []
    table.render([rec], log=lines.append)
    text = "\n".join(lines)
    assert "1/2" in text and "0/3 pages" in text and "[1] m/order: none marked" in text
    assert "params: T=1" in text


def test_an_undefined_jump_count_says_why_instead_of_printing_zero():
    """`.get(key, 0)` defaults on a MISSING key, not on a null one.

    `column_jumps` returns `excess_jumps: None` whenever not one page gathered
    enough boxes to jump between -- "the quantity is UNDEFINED", which is the
    whole reason it says so -- and the assembly record asked for it with a
    default of 0. The default never applied, so `Scalar(None)` raised "a
    scalar without a value must say why" and the whole table died.

    Found by the sweep, on the first (bench, model) pair that ever produced
    an empty count: `bench/katalog` under yolox, where every box is
    full-width. Nothing in the tree had made one before, which is the point
    of running every model over every bench.
    """
    from booksmith.datasets.metrics import assembly
    from booksmith.datasets.bench import Run

    class OnePerPage:
        label = "m"

        def pages(self):
            return {i: {"index": i, "width": 100, "height": 100, "dpi": 144.0,
                        "meta": {}, "blocks": [
                            {"block_id": 0, "box": [0, 0, 100, 20],
                             "label": "text", "score": 1.0, "order": 0}]}
                    for i in range(3)}

    run = OnePerPage()
    rec = assembly.AssemblyMetric().run(None, run)
    for name in ("excess_jumps", "excess_jumps_per_page"):
        sc = rec.scalars[name]
        assert sc.value is None, f"{name} invented a value out of no pages"
        assert sc.why and "UNDEFINED" in sc.why, (
            f"{name} is absent and does not say why: {sc.why!r}. A zero here "
            f"would read as 'no excess jumps', which is another thing")
