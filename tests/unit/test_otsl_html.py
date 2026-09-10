"""OTSL into HTML: the model's merges reach the book.

`otsl.to_html` builds every table of the book, and a merge is declared by a tag
(`<lcel>` continues the left neighbour, `<ucel>` the one above). Expanding those
tags into repeats prints a header once per column it spans.

The border is guarded from both sides: a merge comes from the tag and only from
it. Guessing by equal neighbouring text would lie wherever equal neighbours
stand without a single `<lcel>` («ⅢЛА-1,3» and «1,3» merely coincided).
"""
from booksmith.core import otsl


# ------------------------------------------------------- merges ---

def test_declared_colspan_survives_the_translation():
    """`<fcel>Годы` plus five `<lcel>` is one cell over six columns. Input taken
    from the real book: `p0005-b2`, «Рост производства огнеупорных материалов в
    СССР»."""
    h = otsl.to_html("<fcel>Материалы<fcel>Годы<lcel><lcel><lcel><lcel><lcel>"
                     "<nl><ucel><fcel>1913<fcel>1931<fcel>1935<fcel>1940"
                     "<fcel>1945<fcel>1950<nl>")
    assert '<td colspan="6">Годы</td>' in h, h
    assert '<td rowspan="2">Материалы</td>' in h, h
    # And not one repeat: «Годы» exactly once in the whole table.
    assert h.count("Годы") == 1, h
    # Cells fewer than addresses by exactly the absorbed: 14 and 8.
    assert h.count("<td") == 8, h


def test_span_chain_resolves_to_the_root_not_to_the_neighbour():
    """The second `<lcel>` leans on the first, and through it on the root: without
    the chain a merge of six addresses falls into pairs and `colspan` comes out
    2 instead of 6."""
    h = otsl.to_html("<fcel>head<lcel><lcel><lcel><nl>"
                     "<fcel>1<fcel>2<fcel>3<fcel>4<nl>")
    assert '<td colspan="4">head</td>' in h, h


def test_equal_neighbours_without_a_tag_are_not_merged():
    """Two equal cells without `<lcel>` stay two cells: the border between the
    model's tag and our guess."""
    h = otsl.to_html("<fcel>1,3<fcel>1,3<nl><fcel>a<fcel>b<nl>")
    assert "colspan" not in h, h
    assert h.count("<td>1,3</td>") == 2, h


def test_header_cells_come_from_the_model_dictionary_not_from_the_row_number():
    """`<th>` comes from the `<ched>` tag, not from "row one is the header". The
    branch follows the `docling_core` vocabulary rather than a measurement: the
    books read so far hold no header tag at all."""
    h = otsl.to_html("<ched>head<lcel><nl><fcel>1<fcel>2<nl>")
    assert '<th colspan="2">head</th>' in h, h
    # And an ordinary first row is NOT declared a header.
    assert "<th" not in otsl.to_html("<fcel>a<fcel>b<nl><fcel>1<fcel>2<nl>")


def test_no_cell_disappears_in_translation():
    """As many cells out as addresses minus the absorbed ones: the guard against
    the costliest translation error, a lost column."""
    s = "<fcel>a<fcel>b<fcel>c<nl><fcel>1<lcel><fcel>3<nl>"
    g, _ = otsl.parse(s)
    cs, t = otsl.layout(s)
    address_count = sum(c["rows"] * c["cols"] for c in cs)
    assert address_count == len(g) == 6, (address_count, len(g))
    assert otsl.to_html(s).count("<td") == 5


def test_torn_span_is_left_flat_not_straightened():
    """A non-rectangular merge prints without a span and is counted instead:
    straightening it would repair the model."""
    # `<ucel>` under the right half of a two-cell header, nothing under the
    # left one.
    s = "<fcel>head<lcel><nl><fcel>left<ucel><nl>"
    cs, t = otsl.layout(s)
    assert t["non_rectangular_merges"] == 1, t
    h = otsl.to_html(s)
    # The cell is expanded, but not one address is lost.
    assert h.count("<td") == 4, h


# ---------------------------------------------- contract with parse ---

def test_parse_keeps_its_old_contract():
    """`parse` returns the grid with a spanning cell's text repeated, which the
    reading instrument depends on: without it a header is compared against
    emptiness. The HTML translation takes its own grid, from `layout`."""
    g, t = otsl.parse("<ched>head<lcel><nl><fcel>1<fcel>2<nl>")
    assert g[(0, 0)] == g[(0, 1)] == "head"
    assert t["grid_cells"] == 4 and t["rows"] == 2


def test_not_a_table_is_empty_string_not_a_broken_tag():
    """Prose gives an empty string, not `<table></table>`."""
    assert otsl.to_html("just prose") == ""
    assert otsl.to_html("") == ""


def test_a_row_of_continuations_still_gets_its_row():
    """A row made entirely of continuations stays a row of the table: its roots
    are all above, so walking cells alone prints no `<tr>` and loses no address
    -- while in a browser the next row slides right by the merged columns."""
    h = otsl.to_html("<fcel>A<fcel>B<nl><ucel><ucel><nl><fcel>c<fcel>d<nl>")
    assert h.count("<tr>") == 3, h
    # And `c` stands in its own row, not a foreign one.
    assert h.index("<td>c</td>") > h.index("</tr>"), h


def test_an_empty_grid_row_is_not_swallowed():
    """An empty grid row (`<nl><nl>`) stays a row: swallowing it would silently
    level a torn answer, which is what `otsl.py` condemns the vendor's padding
    for."""
    assert otsl.to_html("<fcel>a<nl><nl><fcel>b<nl>").count("<tr>") == 3


def test_a_split_span_keeps_one_tag_for_all_its_addresses():
    """An expanded non-rectangular merge does not become half a header: a
    continuation has no tag of its own, so the tag comes from the root."""
    h = otsl.to_html("<ched>head<lcel><nl><fcel>left<ucel><nl>")
    assert h.count("<th>head</th>") == 3, h
    assert "<td>head</td>" not in h, h


def test_a_short_row_is_not_padded_out():
    """A short row is not padded out with empty cells: inventing cells the model
    never sent is repairing the model from the other side."""
    h = otsl.to_html("<fcel>a<fcel>b<fcel>c<nl><fcel>1<nl>")
    assert h.count("<td") == 4, h
    _, t = otsl.parse("<fcel>a<fcel>b<fcel>c<nl><fcel>1<nl>")
    assert t["rows_of_unequal_length"] == 1, t
