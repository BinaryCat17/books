"""The book assembly order: one rule for the project, and it must be one.

The rule is `core/order.py`: a label translation per policy, a permutation over
the boxes, and a knob naming which rule ran. A rule that sorts by a key it does
not declare in `meta` is what these checks exist to catch.
"""

import pytest

from booksmith.core.errors import Refusal

from booksmith.core import order, policy


def test_every_class_aims_at_a_name_the_rules_look_at():
    """A class's order name is one of the eight the rules look at at all: a
    ninth would not fire, silently, and a running head would drift into the
    body. So every policy, a served model's included, is covered."""
    eight = {"caption", "code", "footnote", "page_footer", "page_header",
             "picture", "table", "text"}
    assert set(policy.ORDER_NAMES) == eight
    for c, (_, name) in policy.CLASSES.items():
        assert name in eight, f"{c}: aims at {name!r}"
    for p in policy.POLICIES.values():
        for lab in p.labels:
            assert p.order_name(lab) in eight, f"{p.name}/{lab}"


def test_ours_needs_neither_labels_nor_docling():
    """`ours` looks at coordinates alone -- no labels, no package, no policy."""
    assert order.cover(None, "ours") is None
    boxes = [(10, 300, 90, 380), (10, 10, 90, 90), (200, 10, 280, 90)]
    perm = order.permutation(["x"] * 3, boxes, 400, 600, 0, None, "ours")
    assert perm == [1, 2, 0], f"top to bottom, left to right gave {perm}"


def test_docling_needs_a_policy_and_any_policy_covers():
    """The docling rule reads labels through the policy's order names: no
    policy is a refusal before page one, and a served model's own mapping
    covers as the tree's own do."""
    with pytest.raises(Refusal):
        order.cover(None, "docling")
    assert order.cover(policy.POLICIES["PP-DocLayoutV2"], "docling") == "PP-DocLayoutV2"
    own = policy.Policy.from_classes({"Grid": "table", "Prose": "text"})
    assert order.cover(own, "docling") == "the model's own classes"


def test_docling_returns_a_permutation_and_touches_no_box():
    """The docling rules permute, they do not edit: the same set of boxes. The
    rules split running heads and body into three lists and sew them back, and a
    lost element makes a box vanish from the book silently."""
    try:
        import docling  # noqa: F401
    except ImportError:
        pytest.skip("no docling package: the `docling` rule cannot be checked")
    labels = ["text", "table", "header", "text", "image"]
    boxes = [(50, 400, 300, 500), (50, 200, 300, 380), (50, 20, 300, 60),
             (330, 400, 580, 500), (330, 100, 580, 380)]
    perm = order.permutation(labels, boxes, 600, 800, 0,
                             policy.POLICIES["PP-DocLayoutV2"], "docling")
    assert sorted(perm) == list(range(len(boxes))), (
        f"not a permutation: {perm} over {len(boxes)} boxes")


def test_an_unknown_rule_dies_loudly():
    """An unknown knob value kills the run instead of keeping quiet: a muddled
    name would shuffle the paragraphs with the boxes unchanged, and no box
    metric would notice."""
    import os
    was = os.environ.get("ASSEMBLY_ORDER")
    os.environ["ASSEMBLY_ORDER"] = "topToBottom"
    try:
        order.rule()
    except Refusal as e:
        assert "ASSEMBLY_ORDER" in str(e) and "ours" in str(e), e
    else:
        raise AssertionError("an unknown rule was accepted in silence")
    finally:
        if was is None:
            os.environ.pop("ASSEMBLY_ORDER", None)
        else:
            os.environ["ASSEMBLY_ORDER"] = was


