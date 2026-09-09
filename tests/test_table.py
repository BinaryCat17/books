"""The table: one parse, a guarded selection, records that come back.

`books bench all` is the deliverable of step 2a and had no check of its own
until its review said so. Built on a made-up bench with one metric, so a
fresh clone checks it; the real numbers are locked by the acceptance report
`table-slovar`.
"""
import json
import os
import tempfile

from booksmith.core.errors import Refusal
from booksmith.datasets import table
from booksmith.datasets.bench import Bench
from booksmith.datasets.metrics.base import Record, Scalar
from test_bench import LABEL, _bench, at_root


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


def test_a_book_without_truth_is_measured_by_what_needs_none():
    """THE TRUTH IS PARSED ONLY IF THERE IS ANY.

    `rows` opened with `bench.pages()` unconditionally, so a book with no
    `truth/` died there -- before applicability was ever consulted -- and
    the truth-free metrics could not be reached on the only runs that have
    a level two. Reverting that one line left every check green, which is
    why this one exists.
    """
    with tempfile.TemporaryDirectory() as d, at_root(d):
        root = _bench(os.path.join(d, "b"))
        os.rename(os.path.join(root, "truth"), os.path.join(d, "away"))
        b = Bench.no_truth(root)
        recs = table.rows(b, b.run(), log=lambda *a: None)
        got = sorted(r.metric for r in recs)
        # Truth-free only, and NOT contour or text: what needs truth is
        # withheld by `applicable`, not answered with a zero.
        assert got == ["assembly", "snapshot"], got
        assert recs[0].detail is not None
        # WHAT WAS WITHHELD SAYS SO, AND SAYS WHAT IT WANTED. A metric that
        # did not apply produced no line at all, so a short table could not
        # be told from an instrument that was never run -- the two zeros,
        # in the one place with no word for either.
        said = []
        table.rows(b, b.run(), log=said.append)
        text = "\n".join(said)
        assert "contour: NOT MEASURED, this book and run give no truth" in text, text
        assert "text: NOT MEASURED, this book and run give no content, read, truth" \
            in text, text
        # The applicability question itself must not explode when the caller
        # has no pages to offer -- the documented default.
        from booksmith.datasets import metrics as registry
        from booksmith.datasets.metrics.base import applicable
        assert [m.name for m in applicable(registry.METRICS, b, b.run())] \
            == ["assembly", "snapshot"]


def test_two_levels_of_one_model_do_not_land_on_one_results_file():
    """The label is the MODEL's own name, so a detector and a reader can
    share it. Keyed on (book, label) alone the second run overwrote the
    first, and a level-two run's ink numbers describe the DETECTOR whose
    boxes it inherited."""
    with tempfile.TemporaryDirectory() as d:
        root = _bench(os.path.join(d, "b"))
        det = Bench.open(root).run()
        os.renames(os.path.join(root, "detect"), os.path.join(root, "read"))
        red = Bench.open(root).run(kind="read")
        assert det.kind == "detect" and red.kind == "read"
        a, z = table.results_path(Bench.open(root), det), \
            table.results_path(Bench.open(root), red)
        assert a != z, a
        assert os.path.basename(a) == f"b-{LABEL}.json", a
        assert os.path.basename(z) == f"b-read-{LABEL}.json", z


def test_the_report_leaves_out_a_run_of_another_level_and_counts_it():
    """A cross-DETECTOR table with a reader in the model column reads as the
    reader's work; the numbers are the detector's. Left out, never dropped
    silently -- and a file written before the field existed is `detect`."""
    from booksmith.datasets import report
    # TWO DIFFERENT RUN LABELS, and that is the whole check. Written with one
    # label in both files, `cells` was keyed the same whether the read run
    # was ingested or not, so only the COUNT could fail: the check proved
    # the tally and never the leaving out, which is the thing that keeps a
    # reader's number out of a column it did not earn.
    det = Record("fitness", "b", LABEL, {"ink_under_boxes": Scalar(0.5)})
    red = Record("fitness", "b", "SomeReader", {"ink_under_boxes": Scalar(0.9)})
    with tempfile.TemporaryDirectory() as d:
        was = report.RESULTS, table.RESULTS
        try:
            report.RESULTS = table.RESULTS = d
            table.write_json([red], os.path.join(d, "b-read-SomeReader.json"),
                             log=lambda *a: None, kind="read")
            table.write_json([det], os.path.join(d, "b-x.json"),
                             log=lambda *a: None)
            cells, _, _, other = report._cells()
            assert ("b", "SomeReader") not in cells, cells
            assert list(cells) == [("b", LABEL)], cells
            assert [(k, n, b, r) for k, n, b, r, _ in other] \
                == [("read", "b-read-SomeReader.json", "b", "SomeReader")], other
        finally:
            report.RESULTS, table.RESULTS = was


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
