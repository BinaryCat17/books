from backend import document as H
from backend.page import Block, Page


def _page(*blocks):
    return Page(index=0, width=100.0, height=100.0, dpi=144, blocks=list(blocks))


def _b(i, box, content, label="text"):
    return Block(block_id=i, box=box, label=label, score=0.9, order=i, content=content, kind="text")


_covered = H._covered


def test_a_nested_block_found_in_a_remaining_one_is_proven():
    para = _b(0, (0, 0, 100, 20), "melts at $1728^{\\circ}\\mathrm{C}$ here")
    formula = _b(1, (10, 5, 40, 12), "\\[1728^{\\circ}\\mathrm{C}\\]", label="inline_formula")
    r = H.repeats_on(_page(para, formula), _covered)
    assert 1 in r and r[1][1] == "verbatim", r
    assert r[1][0] == 0, r
    assert 0 not in r, r


def test_a_nested_block_whose_text_is_absent_is_not_hidden():
    para = _b(0, (0, 0, 100, 20), "about something else entirely")
    formula = _b(1, (10, 5, 40, 12), "\\[1728^{\\circ}\\mathrm{C}\\]", label="inline_formula")
    r = H.repeats_on(_page(para, formula), _covered)
    assert r[1][1] == "differs", r


def test_a_block_is_never_compared_with_itself():
    para = _b(0, (0, 0, 100, 20), "empty")
    one = _b(1, (10, 5, 40, 12), "a unique text", label="inline_formula")
    r = H.repeats_on(_page(para, one), _covered)
    assert r[1][1] == "differs", (
        f"the block was declared a repeat although its text exists nowhere but in itself -- it is being compared with itself: {r}"
    )


def test_two_equal_nested_blocks_are_not_hidden_together():
    para = _b(0, (0, 0, 100, 20), "a box without those words")
    a = _b(1, (10, 5, 40, 12), "one and the same", label="inline_formula")
    b = _b(2, (50, 5, 80, 12), "one and the same", label="inline_formula")
    r = H.repeats_on(_page(para, a, b), _covered)
    assert r[1][1] == "differs" and r[2][1] == "differs", (
        f"both repeats are hidden -- not one is left in the book: {r}"
    )


def test_a_block_nested_in_an_artefact_is_not_a_candidate():
    table = Block(
        block_id=0,
        box=(0, 0, 100, 20),
        label="table",
        score=0.9,
        content="<fcel>1728^{\\circ}\\mathrm{C}<nl>",
        kind="otsl",
    )
    formula = _b(1, (10, 5, 40, 12), "\\[1728^{\\circ}\\mathrm{C}\\]", label="inline_formula")
    from backend import textnorm as T

    assert T.normalize(formula.content, "latex") in T.normalize(table.content, "latex"), (
        "the fixture does not test what it exists for"
    )
    r = H.repeats_on(_page(table, formula), _covered)
    assert r.get(1, (None, ""))[1] != "verbatim", (
        f"the block was declared a repeat OF AN ARTIFACT -- but an artifact travels as a picture, and if no swap arrives no text is left in the book at all: {r}"
    )


def test_an_empty_block_is_not_a_candidate():
    para = _b(0, (0, 0, 100, 20), "text")
    blank = _b(1, (10, 5, 40, 12), None, label="inline_formula")
    r = H.repeats_on(_page(para, blank), _covered)
    assert 1 not in r, r


def test_the_latex_stage_is_declared_with_its_measurement():
    from backend import textnorm as T

    assert "latex" in T.NORM_STEPS, sorted(T.NORM_STEPS)
    note = T.norm_note("latex")
    assert note["steps"], note
    assert T.bare_math("\\alpha") == "alpha"
    assert T.bare_math("\\mathrm{C}").strip() == "C"
    assert T.bare_math("\\[x\\]").strip() == "x"
    assert T.bare_math("$x$").strip() == "x"


def test_the_latex_stage_falls_on_deliberately_broken_input():
    from backend import textnorm as T

    a = T.normalize("\\[1728^{\\circ}\\mathrm{C}\\]", "latex")
    b = T.normalize("\\[1675^{\\circ}\\mathrm{C}\\]", "latex")
    assert a != b, (a, b)
    assert T.normalize("\\[\\alpha\\]", "latex") != T.normalize("\\[\\beta\\]", "latex")


def test_the_typeset_form_is_not_traded_for_the_raw_one():
    carrier = _b(0, (0, 0, 100, 20), "Fig. V.5. Phase diagram of FeO-SiO_{2}")
    formula = _b(1, (10, 5, 40, 12), "\\[\\mathrm{FeO}-\\mathrm{SiO}_{2}\\]", label="inline_formula")
    r = H.repeats_on(_page(carrier, formula), _covered)
    assert r[1][1] == "layout", f"the typeset formula is hidden and the raw latex is kept: {r}"


def test_the_answer_names_the_carrier_not_the_enclosing_frame():
    box = _b(0, (0, 0, 60, 20), "an empty enclosing box")
    carrier = _b(1, (0, 0, 100, 40), "here stands 1728°C and a full stop")
    formula = _b(2, (5, 5, 40, 12), "\\[1728^{\\circ}\\mathrm{C}\\]", label="inline_formula")
    r = H.repeats_on(_page(box, carrier, formula), _covered)
    assert r[2][1] == "verbatim", r
    assert r[2][0] == 1, f"block 0 (the enclosing box) was named, and the text lies in block 1: {r}"


def test_a_two_character_match_is_not_evidence():
    assert H.REPEAT_MIN >= 3, H.REPEAT_MIN
    carrier = _b(0, (0, 0, 100, 20), "at 50°C and onward")
    tiny = _b(1, (10, 5, 40, 12), "\\[50\\]", label="inline_formula")
    r = H.repeats_on(_page(carrier, tiny), _covered)
    assert r[1][1] == "differs", f"a two-digit coincidence was taken for proof: {r}"


def test_a_match_across_the_seam_of_two_blocks_is_not_evidence():
    first = _b(0, (0, 0, 100, 20), "end of the line abc")
    second = _b(1, (0, 20, 100, 40), "defg beginning")
    candidate = _b(2, (5, 5, 40, 12), "abcdefg", label="inline_formula")
    r = H.repeats_on(_page(first, second, candidate), _covered)
    assert r[2][1] == "differs", (
        f"a match across the seam was taken for proof -- no single block in the book holds that text: {r}"
    )
