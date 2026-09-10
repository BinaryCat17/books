"""OTSL: parsing the table markup the reading models answer in.

A sequence of tags, one per grid cell, plus `<nl>` for the end of a row; a
cell's text is everything between its tag and the next, byte for byte. The nine
names are the `docling_core` vocabulary, shared by PaddleOCR-VL and docling.

Our code, not the model's, and kept out of the instrument so that "the model
stayed silent", "our parse did not come together" and "the characters are
wrong" stay three answers. A spanning cell occupies all its addresses, as in
`text._TableHTML`. Torn markup is never levelled: it becomes a counter
(`tally`) and stays visible.
"""
import html as _html
import re

# Declared one by one, not by a shape rule, so a tenth name shows up as unknown.
CONTENT = ("fcel", "ched", "rhed", "srow")   # the cell carries its own text
EMPTY = ("ecel",)                            # the cell is empty, and that is a value
SPAN = ("lcel", "ucel", "xcel")              # the cell continues a neighbour
BREAK = ("nl",)
# Header cells by the model's own mark, not by row number, and named in one place.
HEADER = ("ched", "rhed")
TAGS = CONTENT + EMPTY + SPAN + BREAK

_TOK = re.compile(r"<(" + "|".join(TAGS) + r")>")


def looks_like(s) -> bool:
    """Does this look like OTSL at all. A cheap check before parsing.

    One tag is not enough: prose that merely mentions a `<lcel>` would parse into
    a 1x1 grid and stop counting as an answer that came back as text.
    """
    if not isinstance(s, str):
        return False
    toks = _TOK.findall(s)
    return "nl" in toks or len(toks) >= 2


def grid(s):
    """{(row, col): text}, or None when there are no OTSL tags at all.

    `None` is "this is not OTSL", never "the table is empty"; whoever needs the
    two apart calls `parse` and reads the tally.
    """
    return parse(s)[0] if looks_like(s) else None


def parse(s):
    """(grid, tally). The tally is what the parse did not understand, as numbers.

    Rows of unequal length, continuations with nothing to lean on, text before
    the first tag: by these a torn answer is told from a whole one.
    """
    cells, _, tally = _walk(s)
    return cells, tally


def _walk(s):
    """One walk of the tags for the whole file: (grid, address owners, tally).

    `owner` maps an address to its root, so a merge is one the model marked and
    not one guessed from equal text; `parse` and `layout` share this walk.
    """
    tally = {"grid_cells": 0, "rows": 0, "with_content": 0, "empty": 0,
             "continuations": 0, "continuations_to_nowhere": 0,
             "rows_of_unequal_length": 0, "text_before_first_tag": 0,
             "text_after_last_tag": 0, "chars": 0}
    if not looks_like(s):
        return None, {}, tally

    toks = list(_TOK.finditer(s))
    head = s[:toks[0].start()].strip()
    if head:
        # Prose before the table stays in `content` byte for byte, and is counted here.
        tally["text_before_first_tag"] = len(head)
    # The tail after the last `<nl>` is counted too, or an answer cut short
    # ("…<nl> I could not read the rest") would pass for a whole one.
    tail = s[toks[-1].end():] if toks[-1].group(1) in BREAK else ""
    if tail.strip():
        tally["text_after_last_tag"] = len(tail.strip())

    cells, r, c = {}, 0, 0
    owner = {}                  # address -> address of the root it obeys
    tag_of = {}                 # root address -> the tag declaring it
    widths = []
    for i, m in enumerate(toks):
        name = m.group(1)
        if name in BREAK:
            widths.append(c)
            r, c = r + 1, 0
            continue
        end = toks[i + 1].start() if i + 1 < len(toks) else len(s)
        txt = s[m.end():end]
        if name in CONTENT:
            cells[(r, c)] = txt
            owner[(r, c)] = (r, c)
            tag_of[(r, c)] = name
            tally["with_content"] += 1
            tally["chars"] += len(txt)
        elif name in EMPTY:
            cells[(r, c)] = ""
            owner[(r, c)] = (r, c)
            tag_of[(r, c)] = name
            tally["empty"] += 1
        else:                                   # continuation of a neighbour
            tally["continuations"] += 1
            left, up = (r, c - 1), (r - 1, c)
            if name == "lcel":
                src = left
            elif name == "ucel":
                src = up
            else:
                src = left if left in cells else up
            if src in cells:
                cells[(r, c)] = cells[src]
                # Followed to the root, not the neighbour: an `<fcel>` with five
                # `<lcel>` is one cell over six addresses, not five pairs.
                owner[(r, c)] = owner.get(src, src)
            else:
                # Nothing to lean on (`<lcel>` first in a row, `<ucel>` in the
                # first): created empty, since skipping shifts every address right.
                cells[(r, c)] = ""
                # It owns itself; a nonexistent neighbour would lose the address.
                owner[(r, c)] = (r, c)
                tag_of[(r, c)] = name
                tally["continuations_to_nowhere"] += 1
        c += 1
    if c:                       # last row with no closing <nl>
        widths.append(c)
    tally["grid_cells"] = len(cells)
    tally["rows"] = len(widths)
    if widths:
        tally["rows_of_unequal_length"] = sum(1 for w in widths
                                          if w != max(widths))
    return (cells or None), {"owner": owner, "tag": tag_of}, tally


def layout(s):
    """(cells with merges, tally): where a merge's root is and how far it runs.

    One record per cell rather than per address. A non-rectangular merge is
    printed without a span and counted: straightening would repair the model.

    """
    cells, own, tally = _walk(s)
    tally = dict(tally, **{"merges": 0, "non_rectangular_merges": 0})
    if not cells:
        return [], tally
    owner, tag_of = own["owner"], own["tag"]
    ours = {}
    for addr, root in owner.items():
        ours.setdefault(root, []).append(addr)
    out = []
    for root in sorted(ours):
        addresses = ours[root]
        r0, c0 = root
        rs = {r for r, _ in addresses}
        cs = {c for _, c in addresses}
        h, w = max(rs) - min(rs) + 1, max(cs) - min(cs) + 1
        # The root is always the top-left of its addresses: `<lcel>` leans left,
        # `<ucel>` up, so no owner stands further right or lower than its address.
        rect = len(addresses) == h * w
        if h * w > 1:
            tally["merges"] += 1
            if not rect:
                tally["non_rectangular_merges"] += 1
        if h * w > 1 and rect:
            out.append({"row": r0, "col": c0, "rows": h,
                        "cols": w, "text": cells.get(root, ""),
                        "tag": tag_of.get(root, "fcel")})
        else:
            # A single cell or a non-rectangular merge: every address stands for
            # itself. The tag comes from the root, which `_walk` always sets, or
            # `<ched>head<lcel>` would print half a header and half not.
            root_one = tag_of[root]
            for a in sorted(addresses):
                out.append({"row": a[0], "col": a[1], "rows": 1,
                            "cols": 1, "text": cells.get(a, ""),
                            "tag": tag_of.get(a, root_one)})
    out.sort(key=lambda d: (d["row"], d["col"]))
    return out, tally


def to_html(s) -> str:
    """OTSL -> an HTML table. A translation, not a repair: the same cell count.

    A span collapses into `colspan`/`rowspan` by the model's mark and `<th>`
    follows `<ched>`/`<rhed>`; a short row is printed as the model gave it.

    """
    cs, t = layout(s)
    if not cs:
        return ""
    # A table row is a grid row, not "a row where a root turned up": a row made
    # entirely of continuations, or an empty one (`<nl><nl>`), keeps its `<tr>`,
    # or the cells below it drift into other columns.
    by_rows = {}
    for c in cs:
        by_rows.setdefault(c["row"], []).append(c)
    rows = t["rows"]
    out = ["<table>"]
    for r in range(rows):
        out.append("<tr>")
        for cell in by_rows.get(r, ()):
            tag = "th" if cell["tag"] in HEADER else "td"
            span = ""
            if cell["cols"] > 1:
                span += f' colspan="{cell["cols"]}"'
            if cell["rows"] > 1:
                span += f' rowspan="{cell["rows"]}"'
            out.append(f"<{tag}{span}>" + _html.escape(cell["text"])
                       + f"</{tag}>")
        out.append("</tr>")
    out.append("</table>")
    return "".join(out)
