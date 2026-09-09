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

import pytest

import support
from booksmith.datasets import metrics as registry
from booksmith.datasets.bench import Bench
from booksmith.datasets.metrics.base import (Metric, Probe, Scalar,
                                             applicable, run_battery)

ROOT = os.path.dirname(os.path.dirname(support.SRC))
SLOVAR = os.path.join(ROOT, "bench", "slovar")


def _slovar():
    if not (os.path.isdir(os.path.join(SLOVAR, "truth"))
            and os.path.isdir(os.path.join(SLOVAR, "detect", "PP-DocLayoutV2", "pages"))
            and os.path.isfile(os.path.join(SLOVAR, "slovar.pdf"))):
        pytest.skip("bench/slovar is not built here (books synth --book slovar)")
    b = Bench.open(SLOVAR)
    # NAMED, not "the" run: the book holds one directory per model now, and
    # `run()` refuses when there are several -- which is the point of it.
    return b, b.run("PP-DocLayoutV2")


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
    s = Scalar(None, over=(0, 5), unit="pages", why="nothing marked")
    assert s.to_json() == {"value": None, "over": {"n": 0, "of": 5, "unit": "pages"},
                           "why": "nothing marked"}
    assert Scalar.from_json(s.to_json()) == s
    try:
        Scalar(0.5, over=(1, 2))
    except ValueError:
        pass
    else:
        raise AssertionError("coverage without a unit was accepted")


def test_records_agree_with_the_raw_dict_they_carry():
    """The scalars are views of `detail`; a view that drifts from the dict
    is the hand-typed copy the table was built to abolish."""
    b, r = _slovar()
    for m in registry.METRICS:
        rec = m.run(b, r)
        assert rec.metric == m.name and rec.bench == "slovar" and rec.run == "PP-DocLayoutV2"
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
    assert contour.scalars["artefacts_found"].count == (d["totals"]["found"], d["totals"]["artifacts"])
    x = d["text_and_furniture"]
    tf = contour.scalars["text_furniture_found"]
    assert tf.count == (x["found"], x["block_count"]) and tf.unit == "pages"
    assert tf.over == (x["pages_with_text_markup"], x["pages_total"])
    assert contour.params["COVER_MATCH"] == 0.75
    fit = registry.BY_NAME["fitness"].run(b, r)
    f = fit.detail
    assert abs(fit.scalars["ink_under_boxes"].value - f["ink_under_boxes"] / f["ink_total"]) < 1e-12


def test_applicability_on_the_golden_bench_excludes_the_reading_metric():
    """AnnoPage annotates boxes and no text: `text` needs content it has
    not got. On the real, tracked truth, not on a fake."""
    from booksmith.core import config
    root = os.path.join(config.ROOT, "bench", "annopage")
    if not os.path.isdir(os.path.join(root, "truth")):
        pytest.skip("bench/annopage/truth is not here")
    b = Bench.open(root)
    names = sorted(m.name for m in applicable(registry.METRICS, b, object()))
    assert "text" not in names, names
    assert "contour" in names, names


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

    # A run that READ something, as the reading metric's fourth prerequisite
    # now asks. Given as parsed pages, the shape `table.rows` passes.
    read = {"0000": {"blocks": [{"content": "x"}]}}
    names = lambda b, r=read: sorted(
        m.name for m in applicable(registry.METRICS, b, object(), None, r))
    # pages alone: the truth-free metrics; truth adds the contour; a PDF and
    # characters add the ink and the reading metrics
    assert names(Truthless()) == ["assembly", "reading", "snapshot"]
    assert names(Golden()) == ["assembly", "contour", "reading", "snapshot"]
    assert names(Full()) == ["assembly", "contour", "fitness", "reading",
                             "snapshot", "text"]
    # And the same bench with a run that read NOTHING loses only the reading
    # metric -- the prerequisite is about the run, not about the bench.
    blank = {"0000": {"blocks": [{"content": None}]}}
    assert names(Full(), blank) == ["assembly", "contour", "fitness", "snapshot"]


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


def test_the_truth_free_batteries_catch_every_probe_on_slovar():
    """The assembly and snapshot metrics need no truth and must still be
    able to fail. The three truth-based batteries are locked by the
    acceptance reports (score-, text-, fitness-selfcheck)."""
    b, r = _slovar()
    lines = []
    assert registry.BY_NAME["assembly"].battery(b, r, log=lines.append) == 0, lines
    assert any(l.startswith("assembly battery: probes 3") for l in lines), lines
    assert registry.BY_NAME["snapshot"].battery(b, r, log=lambda *a: None) == 0


def test_a_reading_metric_is_not_applicable_to_a_run_that_read_nothing():
    """CER 1 on a DETECTION run is not a measurement.

    `content` says the TRUTH carries characters. It was the only prerequisite
    the reading metric had, so on every synthetic bench -- whose truth carries
    characters by construction -- the metric was "applicable" to a detection
    run, which never writes one, and reported CER 1 and WER 1. That reads as
    "this model read everything wrong" where the truth is "this run did no
    reading". Harmless while a book held one run; six rows of noise wearing a
    number the moment six detectors are laid side by side.

    Both directions, because only one of them was ever wrong.
    """
    from booksmith.datasets import metrics as registry
    from booksmith.datasets.metrics import base
    b, run = _slovar()
    truth = b.pages()
    empty = run.pages()
    assert not base.run_has_content(run, empty), (
        "the fixture changed: this detect run carries characters")
    names = {m.name for m in
             base.applicable(registry.METRICS, b, run, truth, empty)}
    assert "text" not in names, (
        f"the reading metric is applicable to a run that read nothing: {names}")
    assert {"contour", "fitness", "assembly", "snapshot"} <= names, (
        f"a prerequisite about the RUN switched off the truth metrics: {names}")

    # And with one character in the run, it applies again.
    read = {k: {**v, "blocks": [{**b0, "content": "x"} if i == 0 else b0
                                for i, b0 in enumerate(v["blocks"])]}
            for k, v in empty.items()}
    assert base.run_has_content(run, read)
    names = {m.name for m in
             base.applicable(registry.METRICS, b, run, truth, read)}
    assert "text" in names, f"a run that read something is not measured: {names}"


def test_a_truth_silent_about_a_trait_is_not_counted_as_marked():
    """A missing flag answers "the file did not say", never "annotated".

    This file's own header records the defect for `order_marked` -- truth that
    never mentioned its reading order counted as annotated, and detectors were
    ranked by it. `text_marked` was still read with `.get(..., True)` in two
    places. Measured on `bench/hard36`: one page of 36 carries the flag at all
    and the other 35 say `false`, so `text_furniture_found` was 8 of 11 blocks
    taken from ONE page and published as the bench's text number. `bench/hard`
    did the same over 6 pages of 130 -- the "counted over 6 pages" caption the
    documents quote is that accident.
    """
    from booksmith.datasets.metrics import contour
    assert contour._truth_text_state({"meta": {"text_marked": True}}) == "yes"
    assert contour._truth_text_state({"meta": {"text_marked": False}}) == "no"
    assert contour._truth_text_state({"meta": {}}) == "not_said"
    assert contour._truth_text_state({}) == "not_said"

    # And through the metric: a truth that says nothing is measured over no
    # pages, not over all of them.
    truth = {i: {"index": i, "width": 100, "height": 100, "dpi": 144.0,
                 "meta": {},
                 "blocks": [{"block_id": 0, "box": [0, 0, 10, 10],
                             "label": "text", "score": 1.0, "order": 0}]}
             for i in range(3)}
    res = contour.compare_pages(truth, truth)
    x = res["text_and_furniture"]
    assert x["pages_with_text_markup"] == 0 and x["share"] is None, (
        f"a silent truth was counted as marked: {x}")


def test_an_error_count_carries_the_pairs_it_was_counted_over():
    """A bare count ranks models WRONG, because the denominator moves.

    Measured on slovar: plus-L 233 label errors of 239 matched pairs against
    V3's 442 of 495. By the printed number plus-L looks nearly twice as good;
    by the rate it is the worst of the three (0.975 against 0.893). Every
    other scalar in this record already carried its count.
    """
    from booksmith.datasets.metrics import contour
    truth = {0: {"index": 0, "width": 100, "height": 100, "dpi": 144.0,
                 "meta": {"text_marked": True},
                 "blocks": [{"block_id": i, "box": [0, 10 * i, 10, 10 * i + 8],
                             "label": "text", "score": 1.0, "order": i}
                            for i in range(4)]}}
    model = {0: {**truth[0],
                 "blocks": [{**b, "label": "abstract" if b["block_id"] < 3
                             else "text"} for b in truth[0]["blocks"]]}}
    rec = contour.ContourMetric().record(
        contour.compare_pages(truth, model), "b", "m")
    for name in ("label_errors", "role_errors"):
        sc = rec.scalars[name]
        assert sc.count is not None, f"{name} carries no denominator"
        assert sc.count[1] == 4, f"{name}: counted over {sc.count} of 4 pairs"
    assert rec.scalars["label_errors"].count[0] == 3


def test_the_five_artefact_outcomes_account_for_every_object():
    """Whole, merged, cropped, called text, not seen -- and nothing else.

    `sense_whole` was the only one of the five that reached a scalar; the
    other four lived in `detail`, where a TABLE cannot read them. Three
    sections of `docs/contour-notes.md` are about MERGING and its headline is
    "merging is 71% of ALL misses", so the generated document meant to replace
    that prose could not have stated the project's central level-one finding.

    They are checked as a PARTITION, which is what makes them readable as
    shares: if they stopped summing to the objects, each one would still look
    like a plausible fraction and the set would silently mean nothing.
    """
    from booksmith.datasets.metrics import contour
    b, run = _slovar()
    rec = contour.ContourMetric().run(b, run)
    parts = ["sense_whole", "artefacts_merged", "artefacts_cropped",
             "artefacts_called_text", "artefacts_not_seen"]
    counts = [rec.scalars[p].count for p in parts]
    assert all(c is not None for c in counts), (
        f"an outcome carries no count: {dict(zip(parts, counts))}")
    over = {c[1] for c in counts}
    assert len(over) == 1, f"the five are over different populations: {over}"
    total = sum(c[0] for c in counts)
    assert total == counts[0][1], (
        f"the five outcomes sum to {total} of {counts[0][1]} objects -- they "
        f"are not a partition, and each would still read as a plausible "
        f"share while the set means nothing")


def test_every_scalar_that_reaches_the_document_declares_its_direction():
    """No scalar is published with a direction nobody decided.

    `report._arrow` used to answer "↑, better higher" for any name it did not
    recognise, and that silent default was wrong for five of the twenty-nine
    scalars in `results/`: the three detection failure modes
    (`artefacts_cropped`, `artefacts_called_text`, `artefacts_not_seen`),
    which were added to the metric long after the list was written, and
    `missing`/`empty`, which were IN the list under the qualified names
    `snapshot/missing` and `snapshot/empty` while `_arrow` is called with the
    bare one. So METRICS.md published "missing more artefacts is better", and
    by that legend yolox's 0.314 not-seen beat V2's 0.067.

    Both failures are the same shape and neither could be seen in the
    document: a wrong arrow reads exactly like a right one.

    ASKED OF THE REGISTRY AS WELL AS THE RECORDS, and the records alone were
    a vacuum. `results/` holds what has been MEASURED, and the reading metric
    never has been -- level two costs money -- so all ELEVEN of its scalars
    were undeclared and this check passed anyway, every run, for as long as
    it has existed. `report._arrow` refuses a name it does not know, and it
    refuses by raising: the first reading run ever measured would not have
    produced a wrong arrow, it would have made `books bench report` decline
    to write METRICS.md at all, after the money was spent. A check that
    cannot see a metric until someone pays to run it is checking the wrong
    set.
    """
    import glob
    from booksmith.datasets import report
    names = set()
    files = sorted(glob.glob(os.path.join(ROOT, "results", "*.json")))
    assert len(files) > 20, (
        f"only {len(files)} result files under results/ -- this check is "
        f"measuring nothing, and a scalar it never sees declares nothing")
    for f in files:
        with open(f, encoding="utf-8") as fh:
            for rec in json.load(fh)["records"]:
                names.update(rec.get("scalars") or {})
    measured = set(names)
    b, r = _slovar()
    for m in registry.METRICS:
        names.update(m.run(b, r).scalars)
    assert names - measured, (
        "every registered metric's scalars are already in results/ -- either "
        "a metric stopped emitting, or this loop stopped running, and the "
        "unmeasured half of the registry is exactly what it is here for")
    assert len(names) > 20, f"only {len(names)} scalars found: {sorted(names)}"
    declared = (set(report.LOWER_IS_BETTER) | set(report.HIGHER_IS_BETTER)
                | set(report.NEITHER))
    undeclared = sorted(names - declared)
    assert not undeclared, (
        f"{len(undeclared)} scalars reach METRICS.md with no declared "
        f"direction: {undeclared}. Add each to LOWER_IS_BETTER, "
        f"HIGHER_IS_BETTER or NEITHER in booksmith/datasets/report.py")
    # AND IN EXACTLY ONE. Two lists holding one name is not a declaration
    # either -- `_arrow` would answer by the order its branches happen to be
    # written in, which is not where this decision belongs.
    for n in sorted(names):
        where = [k for k, v in (("LOWER_IS_BETTER", report.LOWER_IS_BETTER),
                                ("HIGHER_IS_BETTER", report.HIGHER_IS_BETTER),
                                ("NEITHER", report.NEITHER)) if n in v]
        assert len(where) == 1, f"`{n}` is declared in {where}"


def test_the_arrows_that_were_wrong_once_are_pinned_by_name():
    """Declared in exactly one list is not the same as declared CORRECTLY.

    The direction check asks only that a name sits in one of the three
    lists, never WHICH -- so `area_under_boxes` can be moved back under `↑`
    and nothing reddens, undoing the commit named after it. Three arrows
    have been wrong in this project and each cost a commit to find; they are
    named here, with the measurement, because a wrong arrow reads exactly
    like a right one and no other check can see the difference.
    """
    from booksmith.datasets import report
    for name, want, why in (
        # One box over the whole sheet takes 100 % of the ink and 100 % of
        # the objects whole -- so this is the GUARD on those numbers and its
        # maximum is the degenerate case, not the best one.
        ("area_under_boxes", "=", "a full-sheet box scores 1.000"),
        # A composition, not a quality. The truth's own artefact-ink share
        # is the ceiling and is printed nowhere: under `↑` the column put
        # plus-L first on slovar at 0.286 against a truth share of 0.034,
        # and V3 first on zhurnal at 0.180 against 0.069, over a model
        # sitting on the truth share exactly with better object ink.
        ("ink_under_artefacts", "=", "8.5x the truth share topped the column"),
        # Missing MORE artefacts is not better. Published as `↑` by a silent
        # default, it made yolox's 0.314 not-seen beat V2's 0.067.
        ("artefacts_not_seen", "↓", "yolox 0.314 beat V2 0.067"),
    ):
        got = report._arrow(name)
        assert got == want, f"`{name}` is `{got}`, want `{want}` -- {why}"
