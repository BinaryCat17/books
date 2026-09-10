"""The reading-order contract: the word "ours" in an adapter against the guard"""

import pytest
import support
from metrics import contour as metrics
from metrics import order

EXPECTED = {"model_rank": "model"}
for _w in order.WORDS.values():
    EXPECTED[_w] = "ours"
    EXPECTED[_w + ": the model gives no rank"] = "ours"


def guard():
    for name in ("_model_has_rank", "_has_order"):
        fn = getattr(metrics, name, None)
        if fn is not None:
            return fn
    raise AssertionError(
        "metrics has neither `_model_has_rank` nor `_has_order`: the order guard was renamed, and nobody holds the contract with the adapters"
    )


def says_model_rank(value) -> bool:
    return bool(guard()({"meta": {support.ORDER_KEY: value}}))


def test_guard_reads_every_value_as_intended():
    wrong = []
    for value, whose in sorted(EXPECTED.items()):
        got = "model" if says_model_rank(value) else "ours"
        if got != whose:
            wrong.append(f"{value!r}: meant {whose!r}, guard read {got!r}")
    assert not wrong, (
        "guard and adapters have parted -- "
        + "; ".join(wrong)
        + ". This is the percentage out of nothing: the metric will compare our own numbering with truth, or keep quiet about a real model rank"
    )


def test_guard_ignores_case():
    from metrics.page import ours_order

    for v in (
        "OURS_top_down_left_right",
        "Ours_top_down",
        "OURS by choice",
        "  ours_top_down_left_right  ",
    ):
        assert ours_order(v), f"{v!r} was not recognised as our order"
    for v in ("model_rank", "", None, 0, "generation_order"):
        assert not ours_order(v), f"{v!r} wrongly taken for our order"


def test_our_order_values_start_with_lowercase_ours():
    for value, whose in EXPECTED.items():
        if whose == "ours":
            assert value.startswith("ours"), (
                f"{value!r} is declared our order but does not start with the word 'ours': the guard will take it for a model rank"
            )


def test_truth_side_has_three_answers_not_two():
    st = metrics._truth_order_state
    assert st({"meta": {"order_marked": True}}) == metrics.ORDER_MARKED
    assert st({"meta": {"order_marked": False}}) == metrics.ORDER_UNMARKED
    assert st({"meta": {}}) == metrics.ORDER_SILENT
    assert st({}) == metrics.ORDER_SILENT
    assert len({metrics.ORDER_MARKED, metrics.ORDER_UNMARKED, metrics.ORDER_SILENT}) == 3, (
        "three states stuck into two"
    )


_ROWS_NO_RANK = [
    [0.0, 0.99, 400.0, 700.0, 700.0, 760.0],
    [0.0, 0.9, 100.0, 100.0, 300.0, 160.0],
    [0.0, 0.8, 400.0, 100.0, 700.0, 160.0],
    [0.0, 0.7, 100.0, 400.0, 300.0, 460.0],
]


def test_no_rank_means_our_rule_not_the_order_of_the_graph():
    page = _fake_page(_ROWS_NO_RANK, ["text"])
    got = [(b.box[1], b.box[0]) for b in page.blocks]
    want = sorted(got)
    assert got == want, (
        f"the boxes do not run top down and left to right: {got}. The model gave no order, so the order is ours -- and it must be a declared rule, not the order duplicate suppression happened to leave"
    )
    came = [(r[3], r[2]) for r in _ROWS_NO_RANK]
    assert came != want, (
        "the boxes for this check were fed already in the wanted order: it would agree with no sorting at all"
    )


def test_no_rank_page_declares_the_rule_it_actually_used():
    page = _fake_page(_ROWS_NO_RANK, ["text"])
    said = page.meta[support.ORDER_KEY]
    assert said in EXPECTED and EXPECTED[said] == "ours", (
        f"a page without a rank declared {said!r} -- the contract table does not hold that as our order"
    )
    assert "top_down" in said and "left_right" in said, (
        f"the rule is not named in words: {said!r}. The guard lets the line through on the word 'ours', and the reader is left guessing what laid the boxes"
    )


def test_model_rank_still_wins_over_our_rule():
    rows = [
        [0.0, 0.9, 100.0, 100.0, 300.0, 160.0, 3.0],
        [0.0, 0.9, 100.0, 400.0, 300.0, 460.0, 1.0],
        [0.0, 0.9, 100.0, 700.0, 300.0, 760.0, 2.0],
    ]
    page = _fake_page(rows, ["text"])
    assert [b.order for b in page.blocks] == [1, 2, 3], (
        f"the model ranks are not kept: {[b.order for b in page.blocks]}"
    )
    assert [b.box[1] for b in page.blocks] == [400.0, 700.0, 100.0], (
        "the boxes run top down while the model rank is alive -- our rule displaced the model's, that is, we decided for the model"
    )
    assert page.meta[support.ORDER_KEY] == "model_rank"


def _pages_where_grouping_matters():
    pages = {}
    for i in range(3):
        blocks = []
        for row in range(6):
            y0 = 100.0 + row * 90.0
            for base in (40.0, 600.0):
                x0 = base + (65.0 if row % 2 else 0.0)
                blocks.append({"label": "text", "box": [x0, y0, x0 + 260.0, y0 + 60.0]})
        pages[i] = {"width": 1000.0, "height": 700.0, "blocks": blocks}
    return pages


def test_floor_variant_is_a_floor_at_every_point_of_the_sweep():
    M = _pages_where_grouping_matters()
    build = metrics._order_variants(M)["column_by_column"]
    assert callable(build), (
        "the assembly variants are handed over as ready pages: there is nothing to rebuild the floor with for a point's parameters, and it stops being a floor wherever the point leaves the default"
    )
    bad = []
    for point in metrics._sweep_points(metrics.COLUMN_SWEEP, False):
        v = metrics.column_jumps(build(**point), **point)["excess_jumps"]
        if v:
            bad.append(f"{metrics._fmt_point(point)}: {v}")
    assert not bad, (
        "the floor of the scale gives extra jumps at points "
        + "; ".join(bad)
        + " -- the variant was built at one set of parameters and measured at another"
    )


def test_floor_built_at_defaults_would_not_be_a_floor():
    M = _pages_where_grouping_matters()
    fixed = metrics._by_columns(M)
    seen = [
        metrics.column_jumps(fixed, **p)["excess_jumps"]
        for p in metrics._sweep_points(metrics.COLUMN_SWEEP, False)
    ]
    assert any(seen), (
        f"grouping decides nothing on these pages ({seen}): the check above would pass on a broken instrument too"
    )


def test_ranking_rebuilds_the_variants_it_measures():
    M = _pages_where_grouping_matters()
    seen = []

    def spy(**par):
        seen.append(par)
        return M

    metrics.column_jumps_ranking({"sentinel": spy, "model": M})
    pts = metrics._sweep_points(metrics.COLUMN_SWEEP, False)
    assert seen, "the builder was never called -- the variant is not rebuilt"
    assert any(p for p in seen), (
        f"the builder was called {len(seen)} times and never with a point's parameters: the rebuilding exists only in words"
    )
    assert len(seen) <= len(pts), (
        f"the builder was called {len(seen)} times over {len(pts)} points -- an extra count"
    )


@pytest.mark.parametrize(
    "source,rule", [("ours", "docling_rules"), ("ours", ""), ("ours", None), ("theirs", "")]
)
def test_declare_refuses_a_word_outside_the_vocabulary(source, rule):
    with pytest.raises(ValueError):
        order.declare(source, rule)
