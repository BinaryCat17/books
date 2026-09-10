from backend import otsl


def test_declared_colspan_survives_the_translation():
    h = otsl.to_html(
        "<fcel>Материалы<fcel>Годы<lcel><lcel><lcel><lcel><lcel><nl><ucel><fcel>1913<fcel>1931<fcel>1935<fcel>1940<fcel>1945<fcel>1950<nl>"
    )
    assert '<td colspan="6">Годы</td>' in h, h
    assert '<td rowspan="2">Материалы</td>' in h, h
    assert h.count("Годы") == 1, h
    assert h.count("<td") == 8, h


def test_span_chain_resolves_to_the_root_not_to_the_neighbour():
    h = otsl.to_html("<fcel>head<lcel><lcel><lcel><nl><fcel>1<fcel>2<fcel>3<fcel>4<nl>")
    assert '<td colspan="4">head</td>' in h, h


def test_equal_neighbours_without_a_tag_are_not_merged():
    h = otsl.to_html("<fcel>1,3<fcel>1,3<nl><fcel>a<fcel>b<nl>")
    assert "colspan" not in h, h
    assert h.count("<td>1,3</td>") == 2, h


def test_header_cells_come_from_the_model_dictionary_not_from_the_row_number():
    h = otsl.to_html("<ched>head<lcel><nl><fcel>1<fcel>2<nl>")
    assert '<th colspan="2">head</th>' in h, h
    assert "<th" not in otsl.to_html("<fcel>a<fcel>b<nl><fcel>1<fcel>2<nl>")


def test_no_cell_disappears_in_translation():
    s = "<fcel>a<fcel>b<fcel>c<nl><fcel>1<lcel><fcel>3<nl>"
    g, _ = otsl.parse(s)
    cs, t = otsl.layout(s)
    address_count = sum(c["rows"] * c["cols"] for c in cs)
    assert address_count == len(g) == 6, (address_count, len(g))
    assert otsl.to_html(s).count("<td") == 5


def test_torn_span_is_left_flat_not_straightened():
    s = "<fcel>head<lcel><nl><fcel>left<ucel><nl>"
    cs, t = otsl.layout(s)
    assert t["non_rectangular_merges"] == 1, t
    h = otsl.to_html(s)
    assert h.count("<td") == 4, h


def test_parse_keeps_its_old_contract():
    g, t = otsl.parse("<ched>head<lcel><nl><fcel>1<fcel>2<nl>")
    assert g[0, 0] == g[0, 1] == "head"
    assert t["grid_cells"] == 4 and t["rows"] == 2


def test_not_a_table_is_empty_string_not_a_broken_tag():
    assert otsl.to_html("just prose") == ""
    assert otsl.to_html("") == ""


def test_a_row_of_continuations_still_gets_its_row():
    h = otsl.to_html("<fcel>A<fcel>B<nl><ucel><ucel><nl><fcel>c<fcel>d<nl>")
    assert h.count("<tr>") == 3, h
    assert h.index("<td>c</td>") > h.index("</tr>"), h


def test_an_empty_grid_row_is_not_swallowed():
    assert otsl.to_html("<fcel>a<nl><nl><fcel>b<nl>").count("<tr>") == 3


def test_a_split_span_keeps_one_tag_for_all_its_addresses():
    h = otsl.to_html("<ched>head<lcel><nl><fcel>left<ucel><nl>")
    assert h.count("<th>head</th>") == 3, h
    assert "<td>head</td>" not in h, h


def test_a_short_row_is_not_padded_out():
    h = otsl.to_html("<fcel>a<fcel>b<fcel>c<nl><fcel>1<nl>")
    assert h.count("<td") == 4, h
    _, t = otsl.parse("<fcel>a<fcel>b<fcel>c<nl><fcel>1<nl>")
    assert t["rows_of_unequal_length"] == 1, t
