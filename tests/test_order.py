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
import ast

import support

from booksmith import order, policy


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
        support.skip("no docling package: the `docling` rule cannot be checked")
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
    except SystemExit as e:
        assert "ASSEMBLY_ORDER" in str(e) and "ours" in str(e), e
    else:
        raise AssertionError("an unknown rule was accepted in silence")
    finally:
        if was is None:
            os.environ.pop("ASSEMBLY_ORDER", None)
        else:
            os.environ["ASSEMBLY_ORDER"] = was


def test_no_adapter_sorts_by_itself_any_more():
    """NOT ONE adapter sorts by a key of its own. The rule is one.

    By source, not by running: three models mean half a gigabyte of weights,
    and the agreement must be checked on every change.

    Able to fail: put `kept.sort(key=…)` back into any adapter.
    """
    seen = {}
    for rel in ("models/doclayout.py", "models/yolox_layout.py",
                "models/docling_heron.py"):
        bad = []
        for node in ast.walk(support.tree(rel)):
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "sort"
                    and any(k.arg == "key" for k in node.keywords)):
                bad.append(node.lineno)
        seen[rel] = bad
    # `doclayout` is allowed ONE sort -- by the MODEL'S OWN RANK; that is not
    # our rule and has no place in `order.py`. `docling_heron` is allowed one
    # -- the NUMBERING before the vendor pipeline, `Cluster.id`, by which the
    # vendor sews children to their wrapper.
    assert len(seen["models/doclayout.py"]) == 1, (
        f"doclayout has {len(seen['models/doclayout.py'])} keyed sorts, and "
        f"one is lawful -- by the model's rank: "
        f"{seen['models/doclayout.py']}")
    assert len(seen["models/docling_heron.py"]) == 1, (
        f"docling_heron has {len(seen['models/docling_heron.py'])} sorts, "
        f"and one is lawful -- the numbering before the pipeline")
    assert not seen["models/yolox_layout.py"], (
        f"yolox sorts on its own again: lines "
        f"{seen['models/yolox_layout.py']}. The assembly rule lives in "
        f"order.py, and a second copy diverges from the first in silence -- "
        f"which is what happened in docling_heron")


def test_the_ruler_measures_the_same_rule_the_book_is_built_with():
    """The instrument ASKS `order.py` for the rule "ours", not repeats it.

    WHAT PAID FOR IT. `metrics._by_reading` held a second copy --
    `sorted(key=(box[1], box[0]))` -- and a docstring "the very order the
    adapters declare by the word `ours`". The keys agreed, `metrics` did not
    import `order` at all, and NOT ONE check tied them. Yet on that assembler
    the project's main conclusion was taken: "our rule was measured and lost",
    2471 extra jumps against 501 for the model rank and 439 for the docling
    rules. Editing `order.permutation` would leave the instrument measuring
    the FORMER rule and calling it the current one -- reversing the conclusion
    without touching a line of the instrument.

    That is what `order.py` was made for -- see the file header.

    By source: comparing the BEHAVIOUR of two rules is not enough -- they
    agree today, which is why they lived on as copies. What must be checked is
    that a second rule does not exist.
    """
    t = support.tree("metrics.py")
    fn = next((n for n in ast.walk(t)
               if isinstance(n, ast.FunctionDef) and n.name == "_by_reading"),
              None)
    assert fn is not None, "metrics.py lost _by_reading -- assembler removed?"

    ours = [n.lineno for n in ast.walk(fn)
            if isinstance(n, ast.Call)
            and ((isinstance(n.func, ast.Name) and n.func.id == "sorted")
                 or (isinstance(n.func, ast.Attribute) and n.func.attr == "sort"))]
    assert not ours, (
        f"`_by_reading` sorts on its own again (lines {ours}). The assembly "
        f"rule lives in `order.py`; a second copy diverges from the first in "
        f"SILENCE, and the verdict \"our rule lost\" rests on this "
        f"assembler")

    calls = [n for n in ast.walk(fn)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
             and n.func.attr == "permutation"]
    assert calls, (
        "`_by_reading` does not call `order.permutation` -- the instrument "
        "measures a rule other than the one the book is assembled by")
    named = {k.arg: k.value for c in calls for k in c.keywords}
    which = named.get("which")
    assert isinstance(which, ast.Constant) and which.value == "ours", (
        "`order.permutation` is called without `which=\"ours\"`. Without "
        "the explicit name the rule comes from the knob `ASSEMBLY_ORDER`, the "
        "column \"our rule\" starts meaning different things in different "
        "runs, and the sweep becomes incomparable")
