"""Swapping one block for second-level markup -- and undoing it.

A block is replaced exactly, without touching its neighbours and without parsing
the document; a pair of comments marks the borders:

    <!--bs:p0042-b17-->…any markup…<!--/bs:p0042-b17-->

Level two returns markup a model wrote, which may be anything -- unclosed tags,
stray `<`, broken entities -- and an exact string search does not care. The
price is that the marks show in the page source. Every function here is pure:
string in, string out, no files and no models.
"""

from booksmith.core.errors import Refusal
OPEN = "<!--bs:{}-->"
CLOSE = "<!--/bs:{}-->"


class AnchorError(Refusal):
    """Something is wrong with a block mark: missing, doubled, inverted."""


def marks(anchor: str) -> tuple[str, str]:
    return OPEN.format(anchor), CLOSE.format(anchor)


def wrap(anchor: str, body: str) -> str:
    """Wrap a block's markup in marks. This is how `html.py` lays it down."""
    o, c = marks(anchor)
    return o + body + c


def anchors(html: str) -> list[str]:
    """Which blocks the document holds, in order of appearance.

    The document order, not a sorted one: it is the reading order.
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
    """Borders of the block body: (after the opening mark, before the closing).

    A doubled mark is trouble said aloud rather than "take the first": that is
    how an anchor collision is caught. `block_id` restarts on every page, so the
    anchor is per page, and the check outlives the next naming scheme.
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
    # Two interlocked pairs are each "one of each", so counting cannot see them:
    # in `<!--bs:A-->1<!--bs:B-->2<!--/bs:A-->3<!--/bs:B-->` swapping A destroys
    # B's border, and it would surface only on the next swap, of B.
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

    Returns (new document, what stood there). Without the removed piece there is
    no undo, and a swap without undo is an edit of the book.
    """
    a, b = span(html, anchor)
    return html[:a] + fragment + html[b:], html[a:b]


def restore(html: str, anchor: str, previous: str) -> str:
    """Put back what was removed. The inverse of `swap`."""
    return swap(html, anchor, previous)[0]
