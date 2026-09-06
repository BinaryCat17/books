"""Swapping one block for second-level markup -- and undoing it.

The whole two-level scheme exists for this: "a swap can be checked, undone and
redone by another model without touching the book". That rests on one thing --
replacing a block EXACTLY, without touching its neighbours and without parsing
the document. Hence a pair of comments for the borders:

    <!--bs:p0042-b17-->…any markup…<!--/bs:p0042-b17-->

Parsing HTML would be a needless risk: the second level returns markup a model
wrote, and it can be anything -- unclosed tags, stray `<`, broken entities. An
exact string search does not care. The price: the marks show in the page
source, not in the browser.

Every function here is PURE -- string in, string out, no files, no models -- so
this is the one layer checkable whole without a second of compute, and the
first one to cover.
"""

OPEN = "<!--bs:{}-->"
CLOSE = "<!--/bs:{}-->"


class AnchorError(ValueError):
    """Something is wrong with a block mark: missing, doubled, inverted."""


def marks(anchor: str) -> tuple[str, str]:
    return OPEN.format(anchor), CLOSE.format(anchor)


def wrap(anchor: str, body: str) -> str:
    """Wrap a block's markup in marks. This is how `html.py` lays it down."""
    o, c = marks(anchor)
    return o + body + c


def anchors(html: str) -> list[str]:
    """Which blocks the document holds, in order of appearance.

    The DOCUMENT order, not a sorted one: it is the reading order, and losing
    it is not allowed.
    """
    out, i = [], 0
    head = OPEN.split("{}")[0]          # "<!--bs:"
    while True:
        i = html.find(head, i)
        if i < 0:
            return out
        j = html.find("-->", i)
        if j < 0:
            raise AnchorError(f"mark not closed: {html[i:i+40]!r}")
        out.append(html[i + len(head):j])
        i = j + 3


def _marks_in(fragment: str) -> list[str]:
    """Anchor names whose marks occur in the fragment (opening and closing)."""
    out, i = [], 0
    for head in (OPEN.split("{}")[0], CLOSE.split("{}")[0]):
        i = 0
        while True:
            i = fragment.find(head, i)
            if i < 0:
                break
            j = fragment.find("-->", i)
            if j < 0:
                break
            out.append(fragment[i + len(head):j])
            i = j + 3
    return sorted(set(out))


def span(html: str, anchor: str) -> tuple[int, int]:
    """Borders of the block BODY: (after the opening mark, before the closing).

    A doubled mark is trouble said aloud, not "take the first": that is how an
    anchor collision is caught. `block_id` restarts on every page, so a
    book-wide `b17` over five hundred pages would give five hundred identical
    anchors. The per-page `p0042-b17` forbids it, but the check costs one
    `count` and will outlive the next naming scheme.
    """
    o, c = marks(anchor)
    n_o, n_c = html.count(o), html.count(c)
    if n_o != 1 or n_c != 1:
        raise AnchorError(
            f"mark {anchor}: opening {n_o}, closing {n_c}, "
            f"and there must be one of each")
    a = html.index(o) + len(o)
    b = html.index(c)
    if b < a:
        raise AnchorError(f"mark {anchor} is inverted: the closing one comes "
                          f"before the opening")
    # CROSSING. Counting "one each" catches a lost, a doubled and an inverted
    # pair of ONE anchor, but not two interlocked: in
    # `<!--bs:A-->1<!--bs:B-->2<!--/bs:A-->3<!--/bs:B-->` both marks are one
    # each and nothing complained. `get('A')` returned a body with a foreign
    # opening mark inside, `swap('A', …)` erased it along with the body, and
    # the trouble surfaced at the NEXT swap -- "opening 0, closing 1" -- with
    # the book already half re-marked and the message naming the wrong block.
    body = html[a:b]
    for other in _marks_in(body):
        if other == anchor:
            continue
        oo, oc = marks(other)
        if (oo in body) != (oc in body):
            raise AnchorError(
                f"mark {anchor} crosses {other}: only ONE of the neighbour's "
                f"marks lies inside its body. Swapping {anchor} would destroy "
                f"the neighbour's border, and it would show only on him.")
    return a, b


def get(html: str, anchor: str) -> str:
    """What stands in the block's place now."""
    a, b = span(html, anchor)
    return html[a:b]


def swap(html: str, anchor: str, fragment: str) -> tuple[str, str]:
    """Put new markup in the block's place.

    Returns (new document, WHAT stood there). The second is not a convenience
    but the condition of the promise: without the removed piece there is no
    undo, and a swap without undo is not a swap but an edit of the book.
    """
    a, b = span(html, anchor)
    return html[:a] + fragment + html[b:], html[a:b]


def restore(html: str, anchor: str, previous: str) -> str:
    """Put back what was removed. The inverse of `swap`."""
    return swap(html, anchor, previous)[0]
