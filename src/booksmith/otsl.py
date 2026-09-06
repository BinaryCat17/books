"""OTSL: parsing the table markup the reading models answer in.

WHY A FILE OF ITS OWN AND NOT TWO LINES IN `text.py`. Parsing the answer is OUR
code, not the model's, and "why is the number bad" must have three separate
answers: the model stayed silent / our parse did not come together / the
characters are wrong. While the parse lives inside the instrument, the third
answer swallows the second.

WHAT PAID FOR IT, PRICE MEASURED. `text.py` declared `kind="otsl"` a valid kind
of answer for a table while building the grid ONLY from HTML. Measured on
`bench/slovar` (2 tables, 227 cells), one and the same FLAWLESSLY read table
fed in two kinds:

    answer in HTML: matched by address 227 (100%), cell CER 0.0000, as text 0
    answer in OTSL: matched by address   0 (0%),   cell CER 1.0000, as text 2

Impeccable reading by PaddleOCR-VL -- which returns tables in exactly OTSL --
scored zero and was accused of "the table came back as prose": the model blamed
for a defect of our parse, the rule "nobody repairs the model" read from the
other end.

WHAT OTSL IS. A sequence of tags, one per grid cell, plus a line break. Nine
names, not ours -- the `docling_core` vocabulary (`types/doc/tokens.py`), used
by PaddleOCR-VL and docling alike:

    <fcel>  cell with content            <ched>  column header cell
    <ecel>  empty cell                   <rhed>  row header cell
    <lcel>  continuation of the LEFT     <srow>  section-row cell
    <ucel>  continuation of the ABOVE
    <xcel>  continuation of both
    <nl>    end of row

A cell's text is everything BETWEEN its tag and the next one, byte for byte.

A SPANNING CELL OCCUPIES ALL ITS ADDRESSES, not one. The rule comes from
`text._TableHTML`, which parses `colspan`/`rowspan`, and comes DELIBERATELY:
otherwise a row shift in a table with a spanning header would be compared
against emptiness and "fail" for a different reason than the probe declares --
a right number out of wrong reasoning.

WHAT THIS PARSE DOES NOT DO: repair torn OTSL. A row shorter than its
neighbours, `<lcel>` in the first column, `<ucel>` in the first row all stay as
they are and become a COUNTER (`tally`) instead of being levelled. The vendor's
`otsl_pad_to_sqr_v2` does the opposite, padding and truncating in silence, which
is exactly why a table torn at the answer ceiling comes back plausible from it.
Here it stays torn and visible.
"""
import html as _html
import re

# The nine `docling_core` names. DECLARED one by one rather than derived by a
# rule "anything shaped like <?cel>": the tenth name of new weights must show up
# as unknown, not be parsed on a guess.
CONTENT = ("fcel", "ched", "rhed", "srow")   # the cell carries its own text
EMPTY = ("ecel",)                            # the cell is empty, and that is a value
SPAN = ("lcel", "ucel", "xcel")              # the cell continues a neighbour
BREAK = ("nl",)
# HEADER cells by the model's vocabulary, not by row number. A list rather than
# a `name in ("ched", "rhed")` inside the translation: vocabulary names are
# declared in one place, or the tenth name of new weights has to be hunted
# through the whole file.
HEADER = ("ched", "rhed")
TAGS = CONTENT + EMPTY + SPAN + BREAK

_TOK = re.compile(r"<(" + "|".join(TAGS) + r")>")


def looks_like(s) -> bool:
    """Does this look like OTSL at all. A cheap check BEFORE parsing.

    ONE TAG IS NOT ENOUGH, and not out of pedantry. Prose with a lone `<lcel>`
    -- and a model asked about a table may well answer in prose, mentioning a
    tag -- parsed into a 1x1 grid out of nothing, and the block stopped counting
    as "returned as text", losing the counter of an expensive defect whose
    structure cannot be recovered. A table without a single `<nl>` is no table;
    a one-cell table is reason enough to doubt.
    """
    if not isinstance(s, str):
        return False
    toks = _TOK.findall(s)
    return "nl" in toks or len(toks) >= 2


def grid(s):
    """{(row, col): text}, or None when there are no OTSL tags at all.

    `None` means "this is not OTSL", not "the table is empty", and until now the
    caller could not tell: `'<nl>'` (tags present, no cells) and prose both gave
    THE SAME `None`. `parse` now separates them -- `(None, tally)` with `rows: 1`
    on the first, an empty tally on the second -- and whoever needs the
    difference calls it.
    """
    return parse(s)[0] if looks_like(s) else None


def parse(s):
    """(grid, tally). The tally is what the parse did NOT understand, as numbers.

    Everything observed rather than "it worked": rows of unequal length,
    continuations with nothing to lean on, text before the first tag. By these
    numbers a torn answer is told from a whole one without looking at it.
    """
    cells, _, tally = _walk(s)
    return cells, tally


def _walk(s):
    """ONE walk of the tags for the whole file: (grid, address owners, tally).

    THERE WILL BE NO SECOND WALK. `parse` returns a grid with a spanning cell's
    text MULTIPLIED across its addresses, by the rule at the head of this file,
    and such a grid can no longer tell a merge from two neighbours that merely
    share text: measured on this very book, 13 tables of 62 carry identical
    neighbouring cells with NO `<lcel>` anywhere in the model's answer (the grade
    «ⅢЛА-1,3» and the value «1,3» simply coincided). The denominator 62 is the
    tables with equal neighbours HORIZONTALLY, out of 104 in all; of those 62, 13
    have no `<lcel>` and 13 no merge mark of any kind. Over all 104 the same
    figures read 55 and 46 -- a denominator swapped mid-sentence. A guess from
    equal text would lie in every fifth table.

    So the walk returns `owner` too: address -> address of the ROOT it belongs
    to, the address where `<fcel>`/`<ched>`/`<ecel>` stood. That is a merge
    DECLARED BY THE MODEL with a mark, not inferred by us from characters that
    happen to match.

    Two copies of the walk would be the trouble already paid for here -- two
    instances of one rule drifting apart -- so `parse` and `layout` call this
    walk and parse not a single tag themselves.
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
        # The model prefaced the table with prose ("Here is the table:"). That
        # is its answer and stays in `content` byte for byte; we only count that
        # it happened -- otherwise the parse would silently eat part of it.
        tally["text_before_first_tag"] = len(head)
    # THE TAIL AFTER THE LAST `<nl>` IS COUNTED TOO, and used to not be: no
    # symmetry, though the header promised the parse would eat nothing in
    # silence. An answer like "…<nl> I could not read the rest", or a caption
    # after the table, passed for whole.
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
                # THE CHAIN IS FOLLOWED TO THE ROOT, not to the neighbour: an
                # `<fcel>` followed by five `<lcel>` is ONE cell over six
                # addresses, and the second `<lcel>` leans on the first, not on
                # the `<fcel>`. Unfollowed, the merge would fall into pairs.
                owner[(r, c)] = owner.get(src, src)
            else:
                # The continuation has nothing to lean on: `<lcel>` first in a
                # row, or `<ucel>` in the first row. The cell IS CREATED empty
                # rather than skipped: skipping would shift every address to the
                # right and turn one defect of the model into a whole row of
                # divergences.
                cells[(r, c)] = ""
                # And it owns itself: subordinating it to a neighbour that does
                # not exist would lose the address in the HTML translation.
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
    """(cells with merges, tally): where a merge's ROOT is and how far it runs.

    Returns records `{"row", "col", "rows", "cols", "text", "tag"}`, one per
    CELL rather than per address. Continuations are not in the list: they are
    that same cell taken by another address.

    WHY IT EXISTS, PRICE MEASURED. `to_html` printed an unconditional `<td>` in
    a double loop over all addresses, and merges unfolded into repeats. On
    "Технология огнеупоров": 104 tables, `colspan` 0, `rowspan` 0 -- while the
    model had declared merges by mark on 58 tables of 104, 235 merged cells over
    403 swallowed addresses (193 `<lcel>` and 210 `<ucel>`). The header «Годы»
    over six columns printed six times in a row.

    A NON-RECTANGULAR MERGE IS NOT STRAIGHTENED. A torn answer can give a root
    addresses that do not fold into a rectangle (`<ucel>` under the right half
    of a two-cell header and nothing under the left). Such a cell is printed
    WITHOUT a span, every address a cell of its own, and counted in
    `non_rectangular_merges`. Straightening would be repairing the model.
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
        # THE ROOT IS ALWAYS THE TOP-LEFT OF ITS ADDRESSES, and checking that is
        # pointless. `<lcel>` leans on (r, c-1), `<ucel>` on (r-1, c), so the
        # owner of any address stands no further right and no lower than it. The
        # guard `and min(rs) == r0 and min(cs) == c0` had 0 exceptions over the
        # book's 235 726 roots, and dropping it failed no check.
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
            # Either a single cell or a non-rectangular merge: every address
            # stands for itself, none is lost.
            # THE TAG COMES FROM THE ROOT, not from the address. A continuation
            # has no tag of its own, and our `fcel` default tore one cell of the
            # model in half: `<ched>head<lcel>` non-rectangular gave
            # `<th>head</th><td>head</td>`, half header and half not. A ROOT
            # ALWAYS HAS A TAG -- `_walk` sets `tag_of` at the same instant as
            # `owner`, for content, empty cell and continuation to nowhere alike
            # -- and the `"fcel"` default never fired on the book's 236 758 roots.
            # So the key is taken directly: breaking that contract is trouble to
            # fail aloud about, not to paper over with a tag of ours.
            root_one = tag_of[root]
            for a in sorted(addresses):
                out.append({"row": a[0], "col": a[1], "rows": 1,
                            "cols": 1, "text": cells.get(a, ""),
                            "tag": tag_of.get(a, root_one)})
    out.sort(key=lambda d: (d["row"], d["col"]))
    return out, tally


def to_html(s) -> str:
    """OTSL -> an HTML table. A TRANSLATION, not a repair: the same cell count.

    Needed by the book, not by the instrument: the instrument judges the grid in
    OTSL too (`grid`), but a browser has nothing to show for `<fcel>`. The
    model's bytes stay in the page's `content` and in the answer beside it, so
    the translation can always be replayed.

    A SPANNING CELL COLLAPSES INTO `colspan`/`rowspan`. The case for printing
    the repeat instead -- "a repeated value shows as repeated, honester than
    guessing where the span ends" -- had a false premise: there is no guess. The
    model declares the merge by MARK (`<lcel>` continues the left neighbour,
    `<ucel>` the one above), and its word here is no worse than its word about
    the cell's text. The guess would be the opposite, a span derived from
    neighbours sharing text; that price is measured at `_walk`. The price of the
    old decision is measured at `layout` and sits in the product: the header
    «Годы» over six columns printed as six separate cells, reading on screen
    «Годы Годы Годы Годы Годы Годы».

    THE SECOND CHANGE TO THE TRANSLATION, named apart or it hides inside the
    first. The old walk went over the `rows x cols` rectangle and PADDED a short
    row with empty `<td>`; this one prints the row as the model gave it. In the
    book `<td>` fell by 407, and that is NOT 407 collapsed merges: 396 collapsed
    and 11 are padding gone from three tables (`p0175-b0` 8, `p0232-b2` 2,
    `p0331-b23` 1). Same direction as the whole file: no cells invented, a torn
    row torn and visible, its length already counted in
    `rows_of_unequal_length`.

    `<th>` IS SET BY THE MODEL'S MARK, not by row number: `<ched>` and `<rhed>`
    of the `docling_core` vocabulary ARE "header cell". No "the first row is
    always the header" guess, and no `<thead>` at all -- the model declares it by
    nothing. THE CAVEAT WITHOUT WHICH THIS LIES: "Технология огнеупоров" carries
    NOT ONE header mark; a tag census over all 104 tables gives `fcel` 5099,
    `lcel` 193, `ucel` 210, `ecel` 164, `nl` 729 and zero
    `ched`/`rhed`/`srow`/`xcel`. This branch is written from the vocabulary
    rather than from a measurement, and has never been checked on a real book.
    """
    cs, t = layout(s)
    if not cs:
        return ""
    # A TABLE ROW IS A GRID ROW, not "a row where a root turned up". A walk over
    # cells opening `<tr>` on a change of row number lost the `<tr>` of rows made
    # ENTIRELY of continuations:
    # `<fcel>A<fcel>B<nl><ucel><ucel><nl><fcel>c<fcel>d<nl>` is three grid rows
    # and came out as two. No address was lost, but slots (1,0) and (1,1) in HTML
    # are held by other cells' `rowspan`, so `c` and `d` drifted into the third
    # and fourth columns. The cell-loss check could not see it: it counts `<td>`,
    # and there are exactly as many.
    #
    # Fuzzing found the trouble in 2327 of 40000 random OTSL inputs; on
    # "Технология огнеупоров" in NOT ONE (731 `<tr>` before the fix and 731
    # after), so the defect was latent rather than active.
    #
    # The same walk fixes an empty grid row (`<nl><nl>`), swallowed in silence by
    # the old translation -- the quiet levelling of a torn answer this file's
    # header condemns `otsl_pad_to_sqr_v2` for.
    # THERE ARE AS MANY ROWS AS THE WALK COUNTED. `max(t["rows"],
    # max(by_rows) + 1)` stood here, and the second half cannot occur: the row
    # number grows only on `<nl>`, and `_walk` appends the last row without
    # `<nl>` itself, so `max(by_rows) + 1 <= t["rows"]` identically. Checked
    # over 40 000 random inputs -- not one firing, and removing the `max` failed
    # no check. A guard that cannot fire is not a guard but a view of one.
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
