"""The book assembly order: one rule for the project, and it must be one.

WHY THIS FILE. The rule lived in FOUR places of three adapters, and in two of
them sorted by a key it did not declare: `docling_heron` put "ours, top down
and left to right" into `meta` while sorting `(round(y/20), x)` -- buckets of
twenty raster pixels. Seeing it took reading all four places at once; not one
of the 169 checks saw it.

The measurement that chose the rule (`order.py` header): the same V2 boxes,
600 golden pages, three permutations, one `books score` -- our rule 2471 extra
jumps, the model rank 501, the docling rules 439. Over 16 sweep points ours is
worse than both STABLY (bounds 3.02..7.04 against 0.23..1.73 and 0.28..1.57,
not overlapping), while docling against the V2 rank the instrument CANNOT TELL
APART (the pair inverts, difference 0.13 against a ruler span of 4.02).
"""

import pytest

from booksmith.core.errors import Refusal

from booksmith.core import order, policy


def test_every_dictionary_has_a_translation():
    """EVERY policy has a label translation, and no translation is spare.

    An agreement between two dictionaries, and the project has lost on just
    that: the knob registry and the task builder diverged on 13 names of 17.
    Start a sixth policy and `ASSEMBLY_ORDER=docling` would fall on it at the
    first paid run, not here in a millisecond.
    """
    have, want = set(order._LABELS), set(policy.POLICIES)
    assert have == want, (
        f"the label translation and the policies have diverged: no "
        f"translation for {sorted(want - have)}, a translation with no policy "
        f"for {sorted(have - want)}")


def test_translations_name_only_labels_the_rules_look_at():
    """The translation aims at the EIGHT names the rules look at at all.

    A ninth would not fire, silently, and a running head would drift into the
    body. The list was taken by reading `reading_order_rb.py` itself.
    """
    eight = {"caption", "code", "footnote", "page_footer", "page_header",
             "picture", "table", "text"}
    for name, tr in order._LABELS.items():
        bad = set(tr.values()) - eight
        assert not bad, (f"{name}: the translation aims at {sorted(bad)}, "
                         f"and the rules look only at {sorted(eight)}")


def test_translations_use_labels_that_exist():
    """What is translated is what the model REALLY returns, not a made-up name.

    A typo in a key is a silent zero: the label is missed, the object travels
    as text, and nobody learns of it.
    """
    for name, tr in order._LABELS.items():
        bad = set(tr) - set(policy.POLICIES[name])
        assert not bad, (
            f"{name}: the translation knows labels {sorted(bad)} the model "
            f"does not have -- such a key will NEVER fire, and silently")


def test_ours_needs_neither_labels_nor_docling():
    """`ours` looks at coordinates alone -- no labels, no package.

    Able to fail: make `cover` always ask the policy, and a fake dictionary of
    one label will break a rule that never touches labels.
    """
    assert order.cover(["no such policy exists at all"], "ours") is None
    boxes = [(10, 300, 90, 380), (10, 10, 90, 90), (200, 10, 280, 90)]
    perm = order.permutation(["x"] * 3, boxes, 400, 600, 0, ["x"], "ours")
    assert perm == [1, 2, 0], f"top to bottom, left to right gave {perm}"


def test_docling_returns_a_permutation_and_touches_no_box():
    """The docling rules PERMUTE, they do not edit: the same set of boxes.

    A check of substance, not of output: the rules split running heads and
    body into three lists and sew them back; lose an element there and a box
    vanishes from the book silently, the count "after" merely looking smaller.
    """
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
    """An unknown knob value kills the run instead of keeping quiet.

    A muddled name would shuffle the paragraphs, the boxes staying the same
    -- no box metric would notice.
    """
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


