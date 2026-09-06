"""OTSL into HTML: the model's merges reach the book.

WHY THIS FILE EXISTS. `otsl.to_html` builds EVERY table of the book -- 104 of
104 on "Технология огнеупоров", compared byte for byte against `book.html` --
and no check covered it. Proved by corruption: the function replaced whole by
the stub `<table><tr><td>RUBBISH</td></tr></table>` left the battery green --
202 checks, 0 failures, 181 mutations, none caught. A function turning every
table of the book into one word broke nothing.

WHAT IS CHECKED IN SUBSTANCE. A merge is declared by a TAG (`<lcel>` continues
the left neighbour, `<ucel>` the one above). The old translation expanded them
into repeats: 104 tables at `colspan` 0 and `rowspan` 0, while the model had
declared 235 merged cells over 403 absorbed addresses. The header «Годы» above
six columns printed six times running.

THE BORDER GUARDED HERE FROM BOTH SIDES: a merge comes from the tag and only
from it. Guessing by equal neighbouring text would lie on 13 tables of the 62
in this book, where equal neighbours stand without a single `<lcel>`
(«ⅢЛА-1,3» and «1,3» merely coincided).
"""
from booksmith import otsl


# ------------------------------------------------------- merges ---

def test_declared_colspan_survives_the_translation():
    """`<fcel>Годы` plus five `<lcel>` is one cell over six columns.

    Input taken from the real book: `p0005-b2`, «Рост производства
    огнеупорных материалов в СССР».
    """
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
    """The second `<lcel>` leans on the first, and through it on the root.

    Without the chain a merge of six addresses would fall into pairs, and
    `colspan` would come out 2 instead of 6.
    """
    h = otsl.to_html("<fcel>head<lcel><lcel><lcel><nl>"
                     "<fcel>1<fcel>2<fcel>3<fcel>4<nl>")
    assert '<td colspan="4">head</td>' in h, h


def test_equal_neighbours_without_a_tag_are_not_merged():
    """Two equal cells WITHOUT `<lcel>` stay two cells.

    The border between the model's tag and our guess.
    """
    h = otsl.to_html("<fcel>1,3<fcel>1,3<nl><fcel>a<fcel>b<nl>")
    assert "colspan" not in h, h
    assert h.count("<td>1,3</td>") == 2, h


def test_header_cells_come_from_the_model_dictionary_not_from_the_row_number():
    """`<th>` comes from the `<ched>` tag, not from "row one is the header".

    CAVEAT: "Технология огнеупоров" holds not one header tag -- the census
    over all 104 tables gives fcel 5099, lcel 193, ucel 210, ecel 164, nl 729
    and zero ched/rhed. The branch follows the `docling_core` vocabulary, not
    a measurement of this book.
    """
    h = otsl.to_html("<ched>head<lcel><nl><fcel>1<fcel>2<nl>")
    assert '<th colspan="2">head</th>' in h, h
    # And an ordinary first row is NOT declared a header.
    assert "<th" not in otsl.to_html("<fcel>a<fcel>b<nl><fcel>1<fcel>2<nl>")


def test_no_cell_disappears_in_translation():
    """As many cells out as addresses minus the absorbed ones.

    The guard against the costliest translation error: a lost column.
    """
    s = "<fcel>a<fcel>b<fcel>c<nl><fcel>1<lcel><fcel>3<nl>"
    g, _ = otsl.parse(s)
    cs, t = otsl.layout(s)
    address_count = sum(c["rows"] * c["cols"] for c in cs)
    assert address_count == len(g) == 6, (address_count, len(g))
    assert otsl.to_html(s).count("<td") == 5


def test_torn_span_is_left_flat_not_straightened():
    """A non-rectangular merge prints WITHOUT a span and is counted instead.

    Straightening it would repair the model. The book has such a case, one in
    104 tables.
    """
    # `<ucel>` under the right half of a two-cell header, nothing under the
    # left one.
    s = "<fcel>head<lcel><nl><fcel>left<ucel><nl>"
    cs, t = otsl.layout(s)
    assert t["non_rectangular_merges"] == 1, t
    h = otsl.to_html(s)
    # The cell is expanded, but NOT ONE address is lost.
    assert h.count("<td") == 4, h


# ---------------------------------------------- contract with parse ---

def test_parse_keeps_its_old_contract():
    """`parse` still returns the grid with a spanning cell's text REPEATED.

    The reading instrument (`books text`) depends on it: without the repeat a
    header would be compared against emptiness and "fail" for a reason other
    than declared. The HTML translation takes its own grid, from `layout`.
    """
    g, t = otsl.parse("<ched>head<lcel><nl><fcel>1<fcel>2<nl>")
    assert g[(0, 0)] == g[(0, 1)] == "head"
    assert t["grid_cells"] == 4 and t["rows"] == 2


def test_not_a_table_is_empty_string_not_a_broken_tag():
    """Prose gives an empty string, not `<table></table>`."""
    assert otsl.to_html("just prose") == ""
    assert otsl.to_html("") == ""


def test_one_walk_serves_both_readers():
    """`parse` and `layout` read the tags in ONE walk.

    Two copies of one rule drifting apart is a bill this project has paid.
    Checked by source: only `_walk` may read tags.
    """
    import ast

    import support
    t = support.tree("otsl.py")
    for name in ("parse", "layout", "to_html"):
        fn = next(n for n in ast.walk(t)
                  if isinstance(n, ast.FunctionDef) and n.name == name)
        ours = [n for n in ast.walk(fn)
                if isinstance(n, ast.Attribute)
                and isinstance(n.value, ast.Name) and n.value.id == "_TOK"]
        assert not ours, (
            f"{name} parses tags on its own (line {ours[0].lineno}) -- a "
            f"second copy of the walk, and it will diverge from the first")


def test_a_row_of_continuations_still_gets_its_row():
    """A row made ENTIRELY of continuations stays a row of the table.

    Hidden, and dangerous for that. `<tr>` was printed on a change of row
    number while walking CELLS, and such a row has no cells of its own -- the
    roots are all above. Two `<tr>` came out instead of three, no address was
    lost, and the check for lost cells kept quiet: exactly as many `<td>`. But
    in a browser the `rowspan` slots are taken, the next row slides right --
    the table silently grows by the merged columns.

    Fuzzing: 2327 cases out of 40000 random OTSL. On "Технология огнеупоров"
    not one (731 `<tr>` before the fix and 731 after): in the product the
    defect never fired.
    """
    h = otsl.to_html("<fcel>A<fcel>B<nl><ucel><ucel><nl><fcel>c<fcel>d<nl>")
    assert h.count("<tr>") == 3, h
    # And `c` stands in ITS OWN row, not a foreign one.
    assert h.index("<td>c</td>") > h.index("</tr>"), h


def test_an_empty_grid_row_is_not_swallowed():
    """An empty grid row (`<nl><nl>`) stays a row.

    Swallowing it would silently level a torn answer -- what the header of
    `otsl.py` condemns the vendor's `otsl_pad_to_sqr_v2` for.
    """
    assert otsl.to_html("<fcel>a<nl><nl><fcel>b<nl>").count("<tr>") == 3


def test_a_split_span_keeps_one_tag_for_all_its_addresses():
    """An expanded non-rectangular merge does not become half a header.

    A continuation has no tag of its own, and substituting our `fcel` default
    tore one model cell in two: `<th>head</th><td>head</td>`. The tag comes
    from the ROOT.
    """
    h = otsl.to_html("<ched>head<lcel><nl><fcel>left<ucel><nl>")
    assert h.count("<th>head</th>") == 3, h
    assert "<td>head</td>" not in h, h


def test_a_short_row_is_not_padded_out():
    """A short row is NOT padded out with empty cells.

    The old translation walked a rectangle and padded; the book had 11 such
    pads on three tables. Inventing cells the model never sent is the same
    repair of the model, from the other side.
    """
    h = otsl.to_html("<fcel>a<fcel>b<fcel>c<nl><fcel>1<nl>")
    assert h.count("<td") == 4, h
    _, t = otsl.parse("<fcel>a<fcel>b<fcel>c<nl><fcel>1<nl>")
    assert t["rows_of_unequal_length"] == 1, t
