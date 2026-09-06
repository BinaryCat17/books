"""A conspiracy inside `yolox_layout.py`: what shrinks the input, and what
the fingerprint records about it.

WHAT IS PINNED HERE AND WHAT IT COST. The shrink filter was a bare
`interpolation=1` inside `_letterbox` and never reached the fingerprint --
unlike the neighbouring `PAD`, declared a constant. Yet it decides more than
any other number in the file: on `bench/slovar` (13 pages, all else
unchanged) 520 boxes at LINEAR, 492 at NEAREST, 497 at CUBIC, 519 at AREA, of
which MATCHING THE BASELINE 0, 1 and 28. Swapping the filter moves every
coordinate there is. `doclayout` reads the same filter out of its weights and
keeps it in the fingerprint; here `books replay --check` could not see it by
construction, and the run was unrepeatable SILENTLY.

The value became a constant and reached the fingerprint -- with no guard set,
and a sceptic proved that by running: with the `cv2_filter` field cut out of
a copy of the tree the battery declared itself entirely sound (163 checks, 0
failed; 139 mutations, 139 caught), a fresh `books detect` on the broken code
wrote a snapshot without the field, and `replay --check` printed 77
quantities of 77, 0 missing, and exited 0. The unrepeatability came back
through the very same silence.

BY PARSING THE SOURCE, NOT BY RUNNING IT: `fingerprint()` lives on a built
adapter, and building one raises 216 MB of weights. The parse sees exactly
what a person sees -- the trick of every conspiracy in this directory.
"""
import ast

import support

REL = "models/yolox_layout.py"


def _resize_call(t):
    """The one and only `cv2.resize` of the file."""
    out = []
    for node in ast.walk(t):
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "resize"):
            out.append(node)
    return out


def test_the_resize_filter_is_a_named_constant_not_a_literal():
    """`cv2.resize` takes the filter BY NAME, not by a number in place.

    Can fail: put `interpolation=1` back and the check reddens.
    """
    calls = _resize_call(support.tree(REL))
    assert len(calls) == 1, f"cv2.resize calls {len(calls)}, expected one"
    kw = {k.arg: k.value for k in calls[0].keywords}
    assert "interpolation" in kw, "the shrink filter is not given at all"
    v = kw["interpolation"]
    assert isinstance(v, ast.Name), (
        "the shrink filter is a number in place, not a named constant -- so "
        "it will not reach the fingerprint and the run goes unrepeatable "
        "silently")
    assert v.id == "INTERP", (
        f"the filter is called {v.id}, the fingerprint expects INTERP")


def test_the_fingerprint_declares_the_resize_filter():
    """The fingerprint declares the shrink filter by THE SAME constant.

    A conspiracy between two places in one file: `_letterbox` shrinks,
    `fingerprint` records. Diverged, both still look sound alone.
    """
    t = support.tree(REL)
    named = set()
    for node in ast.walk(t):
        if not isinstance(node, ast.Dict):
            continue
        for k, v in zip(node.keys, node.values):
            if (isinstance(k, ast.Constant) and k.value == "cv2_filter"
                    and isinstance(v, ast.Name)):
                named.add(v.id)
    assert "INTERP" in named, (
        "the fingerprint has no `cv2_filter` field holding INTERP. Swapping "
        "the filter moves ALL box coordinates (520 against 492/497/519 on "
        "bench/slovar, matching the baseline 0/1/28) while the snapshot "
        "keeps quiet -- `books replay --check` cannot see such a difference")


def test_the_fingerprint_asks_the_threshold_guard_instead_of_a_literal():
    """`threshold_drift` in the fingerprint is a CALL of the guard, not a
    literal.

    WHAT PAID FOR IT. A hard-wired `[]` stood here, while `threshold_drift()`
    on this build says non-empty ALWAYS: the weights carry no threshold of
    their own, ours -- `LAYOUT_SCORE_THRESHOLD` -- is in force. The adapter
    shouted that into the log and wrote "no drift" into `run.json`: the
    snapshot contradicted its own guard. This very defect was found and fixed
    in `docling_heron`, and the third adapter of the three was forgotten.

    A literal is dangerous because it looks sound: the field IS in the
    snapshot, and `books replay --check` approves its presence -- it compares
    keys, not values. By parsing the source rather than running, for the same
    reason as the neighbouring checks: building the adapter means raising the
    weights.
    """
    t = support.tree(REL)
    seen = []
    for node in ast.walk(t):
        if not isinstance(node, ast.Dict):
            continue
        for k, v in zip(node.keys, node.values):
            if isinstance(k, ast.Constant) and k.value == "threshold_drift":
                seen.append(v)
    assert seen, "the fingerprint has no `threshold_drift` field at all"
    assert all(isinstance(v, ast.Call)
               and isinstance(v.func, ast.Attribute)
               and v.func.attr == "threshold_drift" for v in seen), (
        "the `threshold_drift` field of the fingerprint is not a call of "
        "`self.threshold_drift()`. A hard-wired value lies silently: the "
        "guard says the weights have no threshold of their own and our "
        "LAYOUT_SCORE_THRESHOLD is in force, the snapshot answers \"no "
        "drift\", and `replay --check` approves it, because it compares the "
        "presence of a key, not its value")
