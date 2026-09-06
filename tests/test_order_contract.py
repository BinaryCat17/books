"""The READING-ORDER contract: the word "ours" in an adapter against the guard.

The contract. An adapter puts a `reading order` field into a page's `meta` and
names by it WHOSE order it gave. `metrics` decides by that field whether to
compare the order with truth or to say NOT COMPARED, and it decides by one
sign: the word "ours", lower case, at the start of the string.

Nowhere is the contract written whole: half in a comment in `docling_heron.py`,
half in the docstring of `metrics._model_has_rank`, and the values that must be
recognised are SEVEN, in three files. Let them drift and the metric prints a
percentage out of nothing. It has: on hard36 stood "pairs 211, agrees 73%"
where order is marked on none of the 36 pages, and detectors were ranked by
those percentages.

BOTH SIDES ARE FIXED HERE at once: every value the adapters really put into a
page is run through the guard itself and must be read as intended. The intent
is written in the table below by hand, apart from the code: a table derived
from the code would agree with any corruption of it.
"""
import os
import shutil

import support
from booksmith import metrics
from booksmith import order
from booksmith.models import doclayout, docling_heron, yolox_layout

# WHOSE ORDER EACH LINE MEANS. "model" -- comparable with truth; "ours" -- not,
# it would be comparing our own numbering.
EXPECTED = {
    # doclayout.py, PP-DocLayoutV2: the pointer network gives a real rank.
    "model_rank": "model",
    # doclayout.py, PP-DocLayout_plus-L: no rank, `order` is the position in
    # OUR sort. Without this line the metric printed "agrees"
    # 29/36/41/44/46/44% over six benches instead of "NOT COMPARED".
    #
    # The words changed with the deed. Here stood "ours, position in the list:
    # the model gives no rank", and that position was the position after
    # duplicate suppression -- BY DESCENDING CONFIDENCE (100.0% of 3354
    # neighbouring pairs on 200 pages of `bench/annopage`), while "top down"
    # holds for about half of them, a coin toss; the exact figure diverged
    # between copies, caveat in section 18 of `docs/contour-notes.md`. An order
    # the model did not give is ours by definition, but it must be declared as
    # a RULE, not as a place in a list.
}
# THE ASSEMBLY RULES COME FROM `order.WORDS`, THEY ARE NOT TYPED HERE AGAIN.
# Two of them stood in this table as literals -- a third copy of the words for
# two writing adapters. Now the source is one: drift from an adapter and
# `test_no_unknown_order_values` falls, instead of a human noticing.
#
# The tail ": the model gives no rank" is appended by `doclayout`, where the
# rule is voiced by a live model that gave no rank and has to say so in the
# same line. Both forms must read to the guard as OUR order.
for _w in order.WORDS.values():
    EXPECTED[_w] = "ours"
    EXPECTED[_w + ": the model gives no rank"] = "ours"
# Plus the vendor pipeline's rules: two of them, long, and both MUST be "ours".
# docling predicts no order with the knob or without it, and reading_order_rb
# is 740 lines of rules with not a single weight.
for _mode, _rule in docling_heron._DoclingPipeline.ORDER_RULE.items():
    EXPECTED[_rule] = "ours"

ADAPTERS = (("models/doclayout.py", doclayout),
            ("models/docling_heron.py", docling_heron),
            ("models/yolox_layout.py", yolox_layout))


def guard():
    """The metric's guard. Renamed, we fall out loud instead of going green."""
    for name in ("_model_has_rank", "_has_order"):
        fn = getattr(metrics, name, None)
        if fn is not None:
            return fn
    raise AssertionError(
        "metrics has neither `_model_has_rank` nor `_has_order`: the order "
        "guard was renamed, and nobody holds the contract with the adapters")


def says_model_rank(value) -> bool:
    return bool(guard()({"meta": {support.ORDER_KEY: value}}))


def test_adapters_declare_order_rule_at_all():
    """Every adapter has a value. An empty set is not "all is well"."""
    for rel, mod in ADAPTERS:
        vals = support.page_order_values(rel, mod)
        assert vals, (f"{rel}: not one {support.ORDER_KEY} value in a page's "
                      f"meta. The metric's guard would take the default "
                      f"'model rank' and print a percentage off our own "
                      f"numbering")


def test_no_unknown_order_values():
    """A new value must be described HERE, not appear silently."""
    seen = set()
    for rel, mod in ADAPTERS:
        seen |= support.page_order_values(rel, mod)
    unknown = seen - set(EXPECTED)
    assert not unknown, (
        f"adapters put values into a page that the contract table does not "
        f"hold: {sorted(unknown)}. Add them to EXPECTED and say whose order "
        f"it is -- the metric's guard decides by them whether to print a "
        f"percentage")
    forgotten = set(EXPECTED) - seen
    assert not forgotten, (
        f"the contract table holds values no adapter puts down any more: "
        f"{sorted(forgotten)}. Checking the guard by them measures air")


def test_guard_reads_every_value_as_intended():
    """The main check: the guard reads EVERY value as intended."""
    wrong = []
    for value, whose in sorted(EXPECTED.items()):
        got = "model" if says_model_rank(value) else "ours"
        if got != whose:
            wrong.append(f"{value!r}: meant {whose!r}, guard read {got!r}")
    assert not wrong, (
        "guard and adapters have parted -- " + "; ".join(wrong)
        + ". This is the percentage out of nothing: the metric will compare "
          "our own numbering with truth, or keep quiet about a real model "
          "rank")


def test_guard_ignores_case():
    """The guard must strip case, and that is not cosmetics.

    `doclayout.fingerprint()` writes the same meaning in CAPITALS. While the
    guard compared case, such a string in a page's meta would read as THE
    MODEL'S RANK, and the metric would silently compare our own numbering with
    truth -- the hard36 73% of the header.
    """
    from booksmith.models.base import ours_order
    for v in ("OURS_top_down_left_right", "Ours_top_down", "OURS by choice",
              "  ours_top_down_left_right  "):
        assert ours_order(v), f"{v!r} was not recognised as our order"
    for v in ("model_rank", "", None, 0, "generation_order"):
        assert not ours_order(v), f"{v!r} wrongly taken for our order"


def test_our_order_values_start_with_lowercase_nash():
    """The sign is the word "ours" first; in page meta we write it LOWER CASE.

    Case is stripped by the guard (see `test_guard_ignores_case`), so lower
    case here is an agreement on uniformity, not a condition of work. The
    condition is one: the word "ours" must stand FIRST.
    """
    for value, whose in EXPECTED.items():
        if whose == "ours":
            assert value.startswith("ours"), (
                f"{value!r} is declared our order but does not start with "
                f"the word 'ours': the guard will take it for a model rank")


def test_fingerprint_wording_stays_out_of_page_meta():
    """LEFT EMPTY ON PURPOSE -- its subject vanished together with the defect.

    It guarded the CAPITALS spelling of `doclayout.fingerprint()` against a
    case-comparing guard, and guarded it well: the corruption "the adapter
    wrote it capitalised" was caught here.

    Case was taken out of the guard (`models/base.ours_order`) and spelling
    stopped deciding anything: the check became an identity that cannot fail
    under any corruption -- the battery showed it by leaving it without a
    single mutation. A green check that checks nothing is worse than none: it
    reports soundness. The subject is now guarded by `test_guard_ignores_case`
    (case is stripped) and `test_no_unknown_order_values` (no new spelling
    appears silently).
    """


def test_truth_side_has_three_answers_not_two():
    """The truth side: "marked", "unmarked", "not said" -- three answers.

    The default `True` here is what gave hard36 its "agrees 73%". Checked: a
    silent truth must not read as a marked one.
    """
    st = metrics._truth_order_state
    assert st({"meta": {"order_marked": True}}) == metrics.ORDER_MARKED
    assert st({"meta": {"order_marked": False}}) == metrics.ORDER_UNMARKED
    assert st({"meta": {}}) == metrics.ORDER_SILENT
    assert st({}) == metrics.ORDER_SILENT
    assert len({metrics.ORDER_MARKED, metrics.ORDER_UNMARKED,
                metrics.ORDER_SILENT}) == 3, "three states stuck into two"


# --------------------------------------------------------------------------
# THE SECOND SIDE OF THE SAME CONTRACT: not "whose order is declared" but "is
# it that order". The meta line can be flawless and still describe something
# other than what the boxes are laid by -- and so it was. `PP-DocLayout_plus-L`
# has no rank, the sorting branch at `has_order = False` was missing entirely,
# and the boxes went into the book in the order the graph gave them, by
# descending confidence (the numbers are in the EXPECTED table above). Meta
# meanwhile carried an honest "ours, position in the list" -- honest and
# useless: a position in a list is an accident, not a rule, and the book was
# built by it.
#
# Checked BY BEHAVIOUR, not by parsing the tree: parsing would see `.sort(` and
# agree with any sort key. No model is raised for it -- the graph is a
# stand-in, no ONNX is read, no weights are needed.

def _fake_page(rows, labels):
    """An adapter page on a STAND-IN graph: 214 MB of weights stay down.

    `rows` is what the graph's first output gives: class, score, x0, y0, x1, y1
    and, if it likes, a rank. Six columns mean "the model has no rank" --
    exactly the plus-L build.
    """
    import numpy as np
    import cv2
    import tempfile

    from booksmith.models.doclayout import DocLayout

    r = object.__new__(DocLayout)
    r.labels = list(labels)
    r.target_h = r.target_w = 800
    r.interp = 2
    r.norm_scale = True
    r.norm_type = "none"
    r.norm_mean = [0.0] * 3
    r.norm_std = [1.0] * 3
    arr = np.array(rows, np.float32)
    r.sess = type("Graph", (), {
        "run": lambda _self, _names, _feed: [arr, np.array([len(rows)])]})()
    tmp = tempfile.mkdtemp(prefix="booksmith-order-")
    png = os.path.join(tmp, "page.png")
    cv2.imwrite(png, np.zeros((1000, 800, 3), np.uint8))
    try:
        return r.read(png, 0, 144.0)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# The boxes are fed IN DESCENDING CONFIDENCE on purpose, and in that order they
# do NOT run top down: with no sorting they stay as the graph gave them, and
# both sides drift silently.
_ROWS_NO_RANK = [                      # class, score, x0, y0, x1, y1
    [0.0, 0.99, 400.0, 700.0, 700.0, 760.0],   # lowest of all, surest of all
    [0.0, 0.90, 100.0, 100.0, 300.0, 160.0],   # top, left column
    [0.0, 0.80, 400.0, 100.0, 700.0, 160.0],   # top, right column
    [0.0, 0.70, 100.0, 400.0, 300.0, 460.0],   # middle, left
]


def test_no_rank_means_our_rule_not_the_order_of_the_graph():
    """No rank -- the boxes are laid by OUR declared rule, not as they arrived.

    The expectation is written by hand: top down, and left to right on equal
    tops. The arrival order (descending confidence) must be a different one, or
    the check could not tell a rule from the absence of one.
    """
    page = _fake_page(_ROWS_NO_RANK, ["text"])
    got = [(b.box[1], b.box[0]) for b in page.blocks]
    want = sorted(got)
    assert got == want, (
        f"the boxes do not run top down and left to right: {got}. The model "
        f"gave no order, so the order is ours -- and it must be a declared "
        f"rule, not the order duplicate suppression happened to leave")
    came = [(r[3], r[2]) for r in _ROWS_NO_RANK]
    assert came != want, (
        "the boxes for this check were fed already in the wanted order: it "
        "would agree with no sorting at all")


def test_no_rank_page_declares_the_rule_it_actually_used():
    """The meta line names THE SAME rule the boxes were laid by.

    Both halves in one check on purpose: a line without an order and an order
    without a line are equally silent. It was precisely those two that drifted
    -- "ours, position in the list" with no sorting at all.
    """
    page = _fake_page(_ROWS_NO_RANK, ["text"])
    said = page.meta[support.ORDER_KEY]
    assert said in EXPECTED and EXPECTED[said] == "ours", (
        f"a page without a rank declared {said!r} -- the contract table does "
        f"not hold that as our order")
    assert "top_down" in said and "left_right" in said, (
        f"the rule is not named in words: {said!r}. The guard lets the line "
        f"through on the word 'ours', and the reader is left guessing what "
        f"laid the boxes")


def test_model_rank_still_wins_over_our_rule():
    """The MODEL's rank still beats our rule -- else we decided for her.

    Seven columns mean there is a rank. It is fed ACROSS the geometry: if our
    rule displaced the model's, the order would go top down, and that shows.
    """
    rows = [[0.0, 0.9, 100.0, 100.0, 300.0, 160.0, 3.0],
            [0.0, 0.9, 100.0, 400.0, 300.0, 460.0, 1.0],
            [0.0, 0.9, 100.0, 700.0, 300.0, 760.0, 2.0]]
    page = _fake_page(rows, ["text"])
    assert [b.order for b in page.blocks] == [1, 2, 3], (
        f"the model ranks are not kept: {[b.order for b in page.blocks]}")
    assert [b.box[1] for b in page.blocks] == [400.0, 700.0, 100.0], (
        "the boxes run top down while the model rank is alive -- our rule "
        "displaced the model's, that is, we decided for the model")
    assert page.meta[support.ORDER_KEY] == "model_rank"


# --------------------------------------------------------------------------
# THE RULER THAT JUDGES ASSEMBLY ORDER. `books score --selfcheck` prints
# whether the choice between assembly variants holds over the whole sweep of
# grouping parameters, and the bottom of the scale is declared to be "column by
# column": "extra jumps in it are zero BY CONSTRUCTION".
#
# True only at the parameters the variant was built at. The floor was built at
# the DEFAULT and measured over the whole sweep -- at "x overlap 0.8/0.9" it
# gave 1.81 and 1.93 jumps per page against 1.69 and 1.73 for the model itself.
# Hence the battery printed "a model or an assembly rule may NOT be chosen by
# this value": a verdict from the instrument's ruler, not from the data, and
# against section 18 of `contour-notes`. Exactly 1 pair of 6 flipped, the one
# the floor is in.

def _pages_where_grouping_matters():
    """Two columns with a RAGGED type edge: every other row shifted right, so
    neighbours overlap vertically by 0.75 of the box width.

    0.75 is not arbitrary: up to 0.7 the column holds together, at 0.8 and 0.9
    it falls in two. That is what makes the sweep dangerous -- grouping shifts
    underfoot, and a variant BUILT at one set of parameters stops being itself
    when measured at another. On an even grid the check would measure air, and
    `..._would_not_be_a_floor` guards against that.
    """
    pages = {}
    for i in range(3):
        blocks = []
        for row in range(6):
            y0 = 100.0 + row * 90.0
            for base in (40.0, 600.0):
                x0 = base + (65.0 if row % 2 else 0.0)
                blocks.append({"label": "text",
                               "box": [x0, y0, x0 + 260.0, y0 + 60.0]})
        pages[i] = {"width": 1000.0, "height": 700.0, "blocks": blocks}
    return pages


def test_floor_variant_is_a_floor_at_every_point_of_the_sweep():
    """The floor must give ZERO extra jumps at EVERY point of the sweep.

    Otherwise it is not a floor but one more variant, and the verdict "this
    value may not be chosen by" is born of a variant built by one ruler and
    measured by another.
    """
    M = _pages_where_grouping_matters()
    build = metrics._order_variants(M)["column_by_column"]
    assert callable(build), (
        "the assembly variants are handed over as ready pages: there is "
        "nothing to rebuild the floor with for a point's parameters, and it "
        "stops being a floor wherever the point leaves the default")
    bad = []
    for point in metrics._sweep_points(metrics.COLUMN_SWEEP, False):
        v = metrics.column_jumps(build(**point), **point)["excess_jumps"]
        if v:
            bad.append(f"{metrics._fmt_point(point)}: {v}")
    assert not bad, (
        "the floor of the scale gives extra jumps at points " + "; ".join(bad)
        + " -- the variant was built at one set of parameters and measured at "
          "another")


def test_floor_built_at_defaults_would_not_be_a_floor():
    """The same value for a floor built THE OLD WAY must NOT be zero.

    Without this half the check above is green on data where the parameters
    decide nothing -- that is, it measures air.
    """
    M = _pages_where_grouping_matters()
    fixed = metrics._by_columns(M)          # built once, at the defaults
    seen = [metrics.column_jumps(fixed, **p)["excess_jumps"]
            for p in metrics._sweep_points(metrics.COLUMN_SWEEP, False)]
    assert any(seen), (
        f"grouping decides nothing on these pages ({seen}): the check above "
        f"would pass on a broken instrument too")


def test_ranking_rebuilds_the_variants_it_measures():
    """The stability verdict is counted on REBUILT variants.

    The guard looks not at words but at whether the builder was handed a point:
    call it without parameters and there is no rebuilding.
    """
    M = _pages_where_grouping_matters()
    seen = []

    def spy(**par):
        seen.append(par)
        return M

    metrics.column_jumps_ranking({"sentinel": spy, "model": M})
    pts = metrics._sweep_points(metrics.COLUMN_SWEEP, False)
    assert seen, "the builder was never called -- the variant is not rebuilt"
    assert any(p for p in seen), (
        f"the builder was called {len(seen)} times and never with a point's "
        f"parameters: the rebuilding exists only in words")
    assert len(seen) <= len(pts), (
        f"the builder was called {len(seen)} times over {len(pts)} points -- "
        f"an extra count")
