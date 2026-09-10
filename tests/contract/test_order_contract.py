"""The reading-order contract: the word "ours" in an adapter against the guard.

An adapter puts a `reading order` field into a page's `meta` and names by it
whose order it gave; `metrics` decides by that field whether to compare the
order with truth, on one sign: the word "ours", lower case, at the start.

Both sides are fixed here: every value the adapters put into a page is run
through the guard and must be read as intended. The intent is written by hand
in the table below -- one derived from the code would agree with any corruption.
"""
import os

import pytest
import shutil

import support
from booksmith.datasets.metrics import contour as metrics
from booksmith.core import order
from booksmith.processing.layout.adapters import (
    docling as docling_heron)

# Whose order each line means. "model" -- comparable with truth; "ours" -- not,
# it would be comparing our own numbering.
EXPECTED = {
    # doclayout.py, PP-DocLayoutV2: the pointer network gives a real rank.
    "model_rank": "model",
    # doclayout.py, PP-DocLayout_plus-L: no rank, `order` is the position in our
    # own sort. An order the model did not give is ours by definition, but it
    # must be declared as a rule, not as a place in a list.
}
# The assembly rules come from `order.WORDS` and are not typed here again, so a
# drift from an adapter is refused by `order.declare`. The tail ": the
# model gives no rank" is appended by `doclayout`, where the rule is voiced by a
# live model that gave no rank; both forms must read to the guard as our order.
for _w in order.WORDS.values():
    EXPECTED[_w] = "ours"
    EXPECTED[_w + ": the model gives no rank"] = "ours"
# Plus the vendor pipeline's rules, both of which must be "ours": docling
# predicts no order with the knob or without it, and reading_order_rb is 740
# lines of rules with not a single weight.
for _mode, _rule in docling_heron._DoclingPipeline.ORDER_RULE.items():
    EXPECTED[_rule] = "ours"



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
    """The guard must strip case: `doclayout.fingerprint()` writes the same
    meaning in capitals, and a case-comparing guard would read such a string in
    a page's meta as the model's rank and compare our numbering with truth."""
    from booksmith.core.page import ours_order
    for v in ("OURS_top_down_left_right", "Ours_top_down", "OURS by choice",
              "  ours_top_down_left_right  "):
        assert ours_order(v), f"{v!r} was not recognised as our order"
    for v in ("model_rank", "", None, 0, "generation_order"):
        assert not ours_order(v), f"{v!r} wrongly taken for our order"


def test_our_order_values_start_with_lowercase_ours():
    """The sign is the word "ours" first; in page meta it is written lower case.
    Case is stripped by the guard, so lower case here is an agreement on
    uniformity; the one condition is that the word stands first."""
    for value, whose in EXPECTED.items():
        if whose == "ours":
            assert value.startswith("ours"), (
                f"{value!r} is declared our order but does not start with "
                f"the word 'ours': the guard will take it for a model rank")


def test_truth_side_has_three_answers_not_two():
    """The truth side: "marked", "unmarked", "not said" -- three answers, and a
    silent truth must not read as a marked one."""
    st = metrics._truth_order_state
    assert st({"meta": {"order_marked": True}}) == metrics.ORDER_MARKED
    assert st({"meta": {"order_marked": False}}) == metrics.ORDER_UNMARKED
    assert st({"meta": {}}) == metrics.ORDER_SILENT
    assert st({}) == metrics.ORDER_SILENT
    assert len({metrics.ORDER_MARKED, metrics.ORDER_UNMARKED,
                metrics.ORDER_SILENT}) == 3, "three states stuck into two"


# --------------------------------------------------------------------------
# The second side of the same contract: not "whose order is declared" but "is it
# that order". The meta line can be flawless and still describe something other
# than what the boxes are laid by.
#
# Checked by behaviour, not by parsing the tree, which would see `.sort(` and
# agree with any sort key. No model is raised: the graph is a stand-in.

def _fake_page(rows, labels):
    """An adapter page on a stand-in graph, so 214 MB of weights stay down.
    `rows` is what the graph's first output gives: class, score, x0, y0, x1, y1
    and, if it likes, a rank; six columns mean the model has no rank."""
    import numpy as np
    import cv2
    import tempfile

    from booksmith.processing.layout.adapters.doclayout import DocLayout

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


# The boxes are fed in descending confidence on purpose: in that order they do
# not run top down, so no sorting at all would show here.
_ROWS_NO_RANK = [                      # class, score, x0, y0, x1, y1
    [0.0, 0.99, 400.0, 700.0, 700.0, 760.0],   # lowest of all, surest of all
    [0.0, 0.90, 100.0, 100.0, 300.0, 160.0],   # top, left column
    [0.0, 0.80, 400.0, 100.0, 700.0, 160.0],   # top, right column
    [0.0, 0.70, 100.0, 400.0, 300.0, 460.0],   # middle, left
]


def test_no_rank_means_our_rule_not_the_order_of_the_graph():
    """No rank: the boxes are laid by our declared rule, not as they arrived. The
    expectation is written by hand -- top down, left to right on equal tops -- and
    the arrival order must differ, or a rule and the absence of one look alike."""
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
    """The meta line names the same rule the boxes were laid by. Both halves in
    one check on purpose: a line without an order and an order without a line
    are equally silent."""
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
    """The model's rank still beats our rule, or we decided for the model. Seven
    columns mean there is a rank; it is fed across the geometry, so our rule
    displacing it would show as an order running top down."""
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
# The ruler that judges assembly order. `books score --selfcheck` prints whether
# the choice between assembly variants holds over the whole sweep of grouping
# parameters, and the bottom of the scale, "column by column", must give zero
# extra jumps at every point of it. A floor built at the defaults alone is one
# more variant, and the verdict then comes from the ruler and not from the data.

def _pages_where_grouping_matters():
    """Two columns with a ragged type edge, neighbours overlapping vertically by
    0.75 of the box width: up to 0.7 the column holds together, at 0.8 and 0.9 it
    falls in two, which is what makes the sweep dangerous."""
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
    """The floor must give zero extra jumps at every point of the sweep, or it is
    one more variant and the verdict "this value may not be chosen by" is born of
    a variant built by one ruler and measured by another."""
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
    """The same value for a floor built at the defaults must not be zero, or the
    check above is green on data where the parameters decide nothing."""
    M = _pages_where_grouping_matters()
    fixed = metrics._by_columns(M)          # built once, at the defaults
    seen = [metrics.column_jumps(fixed, **p)["excess_jumps"]
            for p in metrics._sweep_points(metrics.COLUMN_SWEEP, False)]
    assert any(seen), (
        f"grouping decides nothing on these pages ({seen}): the check above "
        f"would pass on a broken instrument too")


def test_ranking_rebuilds_the_variants_it_measures():
    """The stability verdict is counted on rebuilt variants: the guard looks not
    at words but at whether the builder was handed a point."""
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


@pytest.mark.parametrize("source,rule,want", [
    ("model", "", order.MODEL_RANK), ("none", "", None),
    *[("ours", w, w) for w in order.WORDS.values()],
    *[("ours", r, r) for r in docling_heron._DoclingPipeline.ORDER_RULE.values()],
])
def test_declare_returns_the_vocabulary_unchanged(source, rule, want):
    assert order.declare(source, rule) == want


@pytest.mark.parametrize("source,rule", [
    ("ours", "docling_rules"), ("ours", ""), ("ours", None), ("theirs", ""),
])
def test_declare_refuses_a_word_outside_the_vocabulary(source, rule):
    with pytest.raises(ValueError):
        order.declare(source, rule)
