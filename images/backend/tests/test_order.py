"""The book assembly order: one rule for the project, and it must be one"""

import pytest
from backend.errors import Refusal
from backend import order
from backend import classes as policy


def test_every_class_aims_at_a_name_the_rules_look_at():
    eight = {
        "caption",
        "code",
        "footnote",
        "page_footer",
        "page_header",
        "picture",
        "table",
        "text",
    }
    assert set(policy.ORDER_NAMES) == eight
    for c, (_, name) in policy.CLASSES.items():
        assert name in eight, f"{c}: aims at {name!r}"
    for p in policy.POLICIES.values():
        for lab in p.labels:
            assert p.order_name(lab) in eight, f"{p.name}/{lab}"


def test_ours_needs_neither_labels_nor_docling():
    assert order.cover(None, "ours") is None
    boxes = [(10, 300, 90, 380), (10, 10, 90, 90), (200, 10, 280, 90)]
    perm = order.permutation(["x"] * 3, boxes, 400, 600, 0, None, "ours")
    assert perm == [1, 2, 0], f"top to bottom, left to right gave {perm}"


def test_docling_needs_a_policy_and_any_policy_covers():
    with pytest.raises(Refusal):
        order.cover(None, "docling")
    assert order.cover(policy.POLICIES["PP-DocLayoutV2"], "docling") is None
    own = policy.Policy.from_classes({"Grid": "table", "Prose": "text"})
    assert order.cover(own, "docling") is None


def test_an_unknown_rule_dies_loudly():
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
