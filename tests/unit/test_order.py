"""The book assembly order: one rule for the project, and it must be one.

The rule is `core/order.py`: a label translation per policy, a permutation over
the boxes, and a knob naming which rule ran. A rule that sorts by a key it does
not declare in `meta` is what these checks exist to catch.
"""

import pytest

from booksmith.core.errors import Refusal

from booksmith.core import order, policy


def test_every_dictionary_has_a_translation():
    """Every policy has a label translation, and no translation is spare: a sixth
    policy would make `ASSEMBLY_ORDER=docling` fall at the first paid run rather
    than here in a millisecond."""
    have, want = set(order._LABELS), set(policy.POLICIES)
    assert have == want, (
        f"the label translation and the policies have diverged: no "
        f"translation for {sorted(want - have)}, a translation with no policy "
        f"for {sorted(have - want)}")


def test_translations_name_only_labels_the_rules_look_at():
    """The translation aims at the eight names the rules look at at all: a ninth
    would not fire, silently, and a running head would drift into the body."""
    eight = {"caption", "code", "footnote", "page_footer", "page_header",
             "picture", "table", "text"}
    for name, tr in order._LABELS.items():
        bad = set(tr.values()) - eight
        assert not bad, (f"{name}: the translation aims at {sorted(bad)}, "
                         f"and the rules look only at {sorted(eight)}")


def test_translations_use_labels_that_exist():
    """What is translated is what the model really returns, not a made-up name: a
    typo in a key is a silent zero -- the object travels as text."""
    for name, tr in order._LABELS.items():
        bad = set(tr) - set(policy.POLICIES[name])
        assert not bad, (
            f"{name}: the translation knows labels {sorted(bad)} the model "
            f"does not have -- such a key will NEVER fire, and silently")


def test_ours_needs_neither_labels_nor_docling():
    """`ours` looks at coordinates alone -- no labels, no package. Able to fail:
    a fake dictionary of one label breaks a rule that asks the policy."""
    assert order.cover(["no such policy exists at all"], "ours") is None
    boxes = [(10, 300, 90, 380), (10, 10, 90, 90), (200, 10, 280, 90)]
    perm = order.permutation(["x"] * 3, boxes, 400, 600, 0, ["x"], "ours")
    assert perm == [1, 2, 0], f"top to bottom, left to right gave {perm}"


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
    vocab = list(policy.POLICIES["PP-DocLayoutV2"])
    perm = order.permutation(labels, boxes, 600, 800, 0, vocab, "docling")
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


