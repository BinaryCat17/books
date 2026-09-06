"""Replacing a block with second-level markup: pure functions, checked whole.

`doc/swap.py` calls itself the one layer of the pipeline checkable entirely
without a second of compute, "and so the one to cover before all others".
Covered.

Four functions carry the promise of the two-level scheme -- `span`, `get`,
`swap`, `restore`: a replacement can be CHECKED, ROLLED BACK and redone by
another model without touching the book. Without rollback it is an edit of the
book.

Corruption here is quiet by construction. The markup comes from a model and
can be anything -- unclosed tags, stray `<`, broken entities -- none visible
to the eye in a five-hundred-page book. One thing will be: at the NEXT
replacement, "opening 0, closing 1" about another block.
"""
from booksmith.doc import swap

A, B = "p0042-b17", "p0042-b18"


def doc(a_body="a table as a picture", b_body="a figure as a picture"):
    return ("<p>before</p>" + swap.wrap(A, a_body) + "<p>between</p>"
            + swap.wrap(B, b_body) + "<p>after</p>")


def test_wrap_and_get_are_inverse():
    assert swap.get(doc(), A) == "a table as a picture"
    assert swap.get(doc(), B) == "a figure as a picture"


def test_anchors_keep_document_order():
    """Appearance order is the reading order; sorting it is forbidden."""
    d = ("<p/>" + swap.wrap("p0002-b9", "x") + swap.wrap("p0001-b3", "y")
         + swap.wrap("p0002-b1", "z"))
    assert swap.anchors(d) == ["p0002-b9", "p0001-b3", "p0002-b1"]


def test_swap_returns_what_it_removed_and_restore_puts_it_back():
    """Rollback must return the document BYTE FOR BYTE."""
    before = doc()
    new, was = swap.swap(before, A, "<table><tr><td>1</td></tr></table>")
    assert was == "a table as a picture"
    assert new != before
    assert swap.get(new, A) == "<table><tr><td>1</td></tr></table>"
    assert swap.restore(new, A, was) == before


def test_swap_leaves_the_neighbour_byte_for_byte():
    """The neighbour untouched: "without touching the book" rests on it."""
    new, _ = swap.swap(doc(), A, "anything at all")
    assert swap.get(new, B) == "a figure as a picture"
    assert new.count(swap.OPEN.format(B)) == 1
    assert new.count(swap.CLOSE.format(B)) == 1


def test_broken_markup_from_the_model_goes_in_as_is():
    """No HTML parsing here, deliberately: the model returns what it returns.

    An unclosed tag and a bare `<` must arrive byte for byte, or the first
    crooked answer would spread over the whole book.
    """
    fragment = "<table><tr><td>a < b<td>2</table"
    new, _ = swap.swap(doc(), A, fragment)
    assert swap.get(new, A) == fragment
    assert swap.get(new, B) == "a figure as a picture"


def test_missing_anchor_is_loud():
    try:
        swap.get(doc(), "p9999-b1")
    except swap.AnchorError as e:
        assert "opening 0" in str(e)
    else:
        raise AssertionError("a swap at a place that does not exist passed silently")


def test_double_anchor_is_loud():
    """An anchor collision: a running `b17` would give five hundred alike.

    "Take the first" means rewriting the wrong block and never learning of it.
    """
    d = doc() + swap.wrap(A, "the same one on another page")
    try:
        swap.span(d, A)
    except swap.AnchorError as e:
        assert "opening 2" in str(e)
    else:
        raise AssertionError("two identical marks were taken for one")


def test_inverted_anchor_is_loud():
    d = "<p>" + swap.CLOSE.format(A) + "body" + swap.OPEN.format(A) + "</p>"
    try:
        swap.span(d, A)
    except swap.AnchorError as e:
        assert "is inverted" in str(e)
    else:
        raise AssertionError("a closing mark before its opening one was accepted")


def test_crossed_anchors_are_loud():
    """A crossing: both marks once each, and the borders interlocked.

    Counting "one each" misses it. `get(A)` returned a body with a foreign
    opening mark inside, `swap(A, …)` erased it with the body, and it showed
    at the NEXT replacement, the book already half re-marked.
    """
    d = (swap.OPEN.format(A) + "1" + swap.OPEN.format(B) + "2"
         + swap.CLOSE.format(A) + "3" + swap.CLOSE.format(B))
    try:
        swap.span(d, A)
    except swap.AnchorError as e:
        assert A in str(e) and B in str(e), (
            f"the complaint does not name both parties to the crossing: {e}")
    else:
        raise AssertionError(
            "a crossing of marks was accepted: swapping A would destroy B's "
            "boundary, and it would only surface at B")


def test_nested_anchors_are_not_a_crossing():
    """Nesting is not a crossing, and the two are not to be muddled.

    BOTH marks of B lie inside A's body: a replacement does not tear the
    neighbour's border, only the neighbour -- seen at once, not a hundred
    pages later.
    """
    d = (swap.OPEN.format(A) + "before" + swap.wrap(B, "inner") + "after"
         + swap.CLOSE.format(A))
    assert swap.get(d, B) == "inner"
    assert swap.get(d, A) == "before" + swap.wrap(B, "inner") + "after"


def test_unterminated_mark_is_loud():
    """A truncated comment does not read as "no marks"."""
    try:
        swap.anchors("<p>text<!--bs:p0001-b1 and that is all")
    except swap.AnchorError as e:
        assert "not closed" in str(e)
    else:
        raise AssertionError("a truncated mark quietly gave an empty list")
