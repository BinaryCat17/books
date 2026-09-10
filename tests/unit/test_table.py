"""The table: one parse, a guarded selection, records that come back.

Built on a made-up bench with one metric, so a fresh clone checks it; the real
numbers are locked by the acceptance report `table-slovar`.
"""
import json
import os
import tempfile

from booksmith.core.errors import Refusal
from booksmith.datasets import table
from booksmith.datasets.bench import Bench
from booksmith.datasets.metrics.base import Record, Scalar
from test_bench import LABEL, _bench
import pytest
import support


def test_rows_refuse_an_unknown_and_an_inapplicable_metric():
    with tempfile.TemporaryDirectory() as d:
        b = Bench.open(_bench(os.path.join(d, "b")))
        run = b.run()
        try:
            table.rows(b, run, ["bogus"])
        except Refusal as e:
            assert "no metric named bogus" in str(e), e
        else:
            raise AssertionError("an unknown metric name was accepted")
        try:
            table.rows(b, run, ["text"])     # no content in this truth
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
        recs = table.rows(b, b.run(), ["contour"])
    assert len(loads) == 1, f"the truth was parsed {len(loads)} times"
    assert [r.metric for r in recs] == ["contour"]
    assert recs[0].detail["book"].startswith("sha256 checked"), recs[0].detail["book"]


def test_a_book_without_truth_is_measured_by_what_needs_none():
    """The truth is parsed only if there is any: opening with `bench.pages()`
    unconditionally kills a book with no `truth/` before applicability is ever
    consulted, and the truth-free metrics are what a level-two run has."""
    with tempfile.TemporaryDirectory() as d:
        # Under `processed/`, so the book's store is this directory and the
        # scan is looked for in its `raw/`, never the developer's.
        root = _bench(os.path.join(d, "processed", "b"))
        os.rename(os.path.join(root, "truth"), os.path.join(d, "away"))
        b = Bench.no_truth(root)
        recs = table.rows(b, b.run())
        got = sorted(r.metric for r in recs)
        # Truth-free only, and NOT contour or text: what needs truth is
        # withheld by `applicable`, not answered with a zero.
        assert got == ["assembly", "snapshot"], got
        assert recs[0].detail is not None
        # What was withheld says so, and says what it wanted: no line at all
        # cannot be told from an instrument that was never run.
        with support.said() as said:
            table.rows(b, b.run())
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
    """The label is the model's own name, so a detector and a reader can share
    it. Keyed on (book, label) alone the second run overwrites the first, and a
    level-two run's ink numbers would describe the detector it inherited."""
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
    """A cross-detector table with a reader in the model column reads as the
    reader's work while the numbers are the detector's. Left out, never dropped
    silently; a file written before the field existed is `detect`."""
    from booksmith.datasets import report
    # Two different run labels, and that is the whole check: with one label in
    # both files only the count could fail, never the leaving out.
    det = Record("fitness", "b", LABEL, {"ink_under_boxes": Scalar(0.5)})
    red = Record("fitness", "b", "SomeReader", {"ink_under_boxes": Scalar(0.9)})
    with tempfile.TemporaryDirectory() as d:
        table.write_json([red], os.path.join(d, "b-read-SomeReader.json"),
                         kind="read")
        table.write_json([det], os.path.join(d, "b-x.json"))
        cells, names, _, _, other = report._cells(d)
        assert ("bench/b", "SomeReader") not in cells, cells
        assert list(cells) == [("bench/b", LABEL)] and names == {("bench/b", LABEL): "b-x.json"}
        assert [(k, n, b, r) for k, n, b, r, _ in other] \
            == [("read", "b-read-SomeReader.json", "bench/b", "SomeReader")], other


def test_records_come_back_from_disk_as_json_left_them():
    rec = Record("m", "b", "r",
                 {"a": Scalar(0.5, count=(1, 2)),
                  "c": Scalar(None, over=(0, 3), unit="pages", why="none marked")},
                 {"T": 1.5}, {"by_page": {3: 1.0}})
    with tempfile.TemporaryDirectory() as d:
        path = table.write_json([rec], os.path.join(d, "x.json"))
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
    with support.said() as lines:
        table.render([rec])
    text = "\n".join(lines)
    assert "1/2" in text and "0/3 pages" in text and "[1] m/order: none marked" in text
    assert "params: T=1" in text


def test_an_undefined_jump_count_says_why_instead_of_printing_zero():
    """`.get(key, 0)` defaults on a missing key, not on a null one: `column_jumps`
    returns `excess_jumps: None` when no page gathered enough boxes to jump
    between, and a default of 0 never applies to it."""
    from booksmith.core import policy as policy_mod
    from booksmith.datasets.metrics import assembly

    class OnePerPage:
        label = "m"
        policy = policy_mod.UNION

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


def test_a_book_under_processed_and_a_page_set_get_their_own_file_names():
    """`bench/x` and `processed/x` are two books that share a name; a page
    set is not the book's measurement. Neither may land on the book's file."""
    with tempfile.TemporaryDirectory() as d:
        b = Bench.open(_bench(os.path.join(d, "bench", "b")))
        p = Bench.open(_bench(os.path.join(d, "processed", "b")))
        run, prun = b.run(), p.run()
    assert os.path.basename(table.results_path(b, run)) == f"b-{LABEL}.json"
    assert os.path.basename(table.results_path(p, prun)) == f"processed-b-{LABEL}.json"
    assert os.path.basename(table.results_path(b, run, pages=[3])) == f"b-{LABEL}-pages-3.json"
    assert table.pages_tail([0, 1, 2, 5, 7, 8]) == "0-2+5+7-8"
    assert table.results_path(b, run, ["contour"], pages=[1, 2]).endswith(
        f"b-{LABEL}-only-contour-pages-1-2.json")


def test_records_carry_the_runs_identity_and_the_header_the_page_set(slovar):
    """A record knows which run it measured, out of the run's snapshot, and
    a file knows which pages: a run measured on one page is not the book."""
    from booksmith.datasets.bench import Run
    from booksmith.datasets.metrics import base
    bare = Run.bare(slovar.truth_dir, "truth")
    with support.said():
        recs = table.rows(slovar, bare, ["contour"], [2, 3])
    assert len(recs) == 1
    rec = recs[0]
    assert rec.identity is None and rec.source_sha256 is None, "a bare run swears nothing"
    assert rec.scalars["text_furniture_found"].over == (2, 2)
    assert rec.detail["order_truth"]["page_count"] == 2 and "pairs" not in rec.detail
    with support.said(), tempfile.TemporaryDirectory() as d:
        path = table.write_json(recs, os.path.join(d, "x.json"), pages=[3, 2])
        d2 = table.read_file(path)
        back = table.read_json(path)
    assert d2["pages"] == [2, 3] and d2["only"] is None
    assert back[0].identity is None and "identity" in d2["records"][0]
    assert back[0].book == slovar.name, "a bench outside a store keeps its bare name"
    stamped = Record("m", "b", "r", identity="abc", source_sha256="def", book="processed/b")
    assert Record.from_json(json.loads(json.dumps(stamped.to_json()))) == stamped
    # The three states, and the fourth: a record that cannot be checked is
    # not a current one, and a snapshot that swears no identity cannot say
    # it differs.
    assert base.staleness("abc", {"identity": "abc"}) == base.CURRENT
    assert base.staleness("abc", {"identity": "xyz"}) == base.STALE
    assert base.staleness(None, {"identity": "abc"}) == base.NOT_RECORDED
    assert base.staleness("abc", None) == base.NOT_CHECKED
    assert base.staleness("abc", {"when": "now"}) == base.NOT_CHECKED
    # The scan's hash is checked too: one identity over another scan is stale.
    same = {"identity": "abc", "source": {"sha256": "s1"}}
    assert base.staleness("abc", same, "s1") == base.CURRENT
    assert base.staleness("abc", same, "s2") == base.STALE
    assert base.staleness("abc", same, None) == base.CURRENT
    with support.said(), pytest.raises(Refusal, match="no pages"):
        table.rows(slovar, bare, ["contour"], [99])
    with support.said(), pytest.raises(Refusal, match="empty page set"):
        table.rows(slovar, bare, ["contour"], [])


def test_a_page_asked_alone_is_measured_as_the_book_measures_it(slovar):
    """A truth that names its labelled pages leaves a silent page out of
    the whole; asked for that page alone, the table refuses rather than
    compare what the book's own measure does not. And a page with no
    artefact has no share of them, not a zero."""
    from booksmith.datasets.bench import Run
    from booksmith.core.page import write_json
    import shutil
    with tempfile.TemporaryDirectory() as d:
        truth = os.path.join(d, "truth")
        shutil.copytree(slovar.truth_dir, truth)
        for n, flag in ((2, True), (3, None)):
            tp = os.path.join(truth, f"{n:04d}.json")
            with open(tp, encoding="utf-8") as f:
                t = json.load(f)
            if flag is not None:
                t["meta"]["labelled"] = flag
            write_json(tp, t)
        b = Bench.bare(truth)
        run = Run.bare(slovar.truth_dir, "truth")
        with support.said():
            whole = table.rows(b, run, ["contour"])[0]
            one = table.rows(b, run, ["contour"], [2])[0]
        assert whole.detail["labelled"] == {"yes": 1, "no": 0, "not_said": 12}
        assert one.detail["order_truth"]["page_count"] == 1
        with support.said(), pytest.raises(Refusal, match="not labelled in this truth"):
            table.rows(b, run, ["contour"], [3])
    pages = json.load(open(os.path.join(slovar.truth_dir, "0001.json"), encoding="utf-8"))
    from booksmith.core import policy
    if not any(policy.UNION.role(x["label"]) == "artifact" for x in pages["blocks"]):
        with support.said():
            rec = table.rows(slovar, Run.bare(slovar.truth_dir, "truth"), ["contour"], [1])[0]
        s = rec.scalars["artefacts_found"]
        assert s.value is None and s.why == "no artefact in the truth" and s.count == (0, 0)


def _check(report, results, store):
    cells, names, _, _, other = report._cells(results)
    return report.check_runs(cells, other, names, store)


def test_the_report_refuses_a_record_of_a_run_that_is_gone_and_counts_the_rest():
    """A results file whose record names another identity than the run on
    disk is refused as a dirty commit is; one naming none, or of a run not
    here, is counted and said, never called current."""
    from booksmith.datasets import report
    rec = Record("fitness", "b", LABEL, {"ink_under_boxes": Scalar(0.5)},
                 identity="one", book="bench/b")
    with tempfile.TemporaryDirectory() as d:
        run_dir = os.path.join(d, "bench", "b", "detect", LABEL)
        os.makedirs(run_dir)
        with open(os.path.join(run_dir, "run.json"), "w", encoding="utf-8") as f:
            json.dump({"identity": "one"}, f)
        results = os.path.join(d, "results")
        with support.said():
            table.write_json([rec], os.path.join(results, f"b-{LABEL}.json"))
        assert _check(report, results, d)["current"] == 1
        with open(os.path.join(run_dir, "run.json"), "w", encoding="utf-8") as f:
            json.dump({"identity": "two"}, f)
        with pytest.raises(Refusal, match="no longer the one on disk"):
            _check(report, results, d)
        os.unlink(os.path.join(run_dir, "run.json"))
        states = _check(report, results, d)
        assert states["not checked"] == 1 and states["current"] == 0
        with support.said():
            table.write_json([Record("fitness", "b", LABEL, {"ink_under_boxes": Scalar(0.5)})],
                             os.path.join(results, f"b-{LABEL}.json"))
        assert _check(report, results, d)["not recorded"] == 1
        # A selection and a page set are not cells, by their headers.
        with support.said():
            table.write_json([rec], os.path.join(results, "b-x.json"), pages=[1])
            table.write_json([rec], os.path.join(results, "b-y.json"), only=["fitness"])
        cells, *_ = report._cells(results)
        assert list(cells) == [("bench/b", LABEL)]


def test_a_bench_and_a_processed_book_of_one_name_are_two_cells_each_checked_against_its_own_run():
    """`bench/x` and `processed/x` measured under one commit: two cells,
    two runs, and the state of each is its own -- keyed on the name alone
    the second record was checked against the first's run and called stale."""
    from booksmith.datasets import report
    with tempfile.TemporaryDirectory() as d:
        for root, ident in (("bench", "one"), ("processed", "two")):
            run_dir = os.path.join(d, root, "x", "read", "R")
            os.makedirs(run_dir)
            with open(os.path.join(run_dir, "run.json"), "w", encoding="utf-8") as f:
                # The processed one is a hybrid: a read run with its own boxes.
                json.dump({"identity": ident, **({"layout": "own"} if root == "processed" else {})}, f)
            rec = Record("fitness", "x", "R", {"ink_under_boxes": Scalar(0.5)},
                         identity=ident, book=f"{root}/x")
            name = ("processed-" if root == "processed" else "") + "x-read-R.json"
            with support.said():
                table.write_json([rec], os.path.join(d, "results", name),
                                 kind="hybrid" if root == "processed" else "read")
        cells, names, _, _, other = report._cells(os.path.join(d, "results"))
        assert cells == {} and sorted(b for _, _, b, _, _ in other) == ["bench/x", "processed/x"]
        states = report.check_runs(cells, other, names, d)
        assert states["current"] == 2, states
        assert report._column("bench/x") == "x" and report._column("processed/x") == "processed/x"
