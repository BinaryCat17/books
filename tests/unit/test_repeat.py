"""A repeat inside the page: what is proved by comparison, what only nested.

One claim is proved here: "hide this block and not a character of the page is
lost". Not "this is a duplicate", not "the owner contains it" -- only that, and
only by comparison.

Two traps the checks hold: a block compared with itself makes any block a
repeat, and two repeats of one place that "have each other" could both be
hidden, so the comparison runs only against the blocks that remain.
"""
from booksmith.processing.assemble import html as H
from booksmith.core.page import Block, Page


def _page(*blocks):
    return Page(index=0, width=100.0, height=100.0, dpi=144,
                blocks=list(blocks))


def _b(i, box, content, label="text"):
    return Block(block_id=i, box=box, label=label, score=0.9, order=i,
                 content=content, kind="text")


# Nesting is judged by the same rule the book is assembled with.
_covered = H._covered


def test_a_nested_block_found_in_a_remaining_one_is_proven():
    """A formula inside a paragraph whose text carries it: a proven repeat."""
    para = _b(0, (0, 0, 100, 20), r"melts at $1728^{\circ}\mathrm{C}$ here")
    formula = _b(1, (10, 5, 40, 12), r"\[1728^{\circ}\mathrm{C}\]",
                 label="inline_formula")
    r = H.repeats_on(_page(para, formula), _covered)
    assert 1 in r and r[1][1] == "verbatim", r
    # The owner is named by block number, not guessed.
    assert r[1][0] == 0, r
    # The paragraph itself is no candidate: it is nested in nothing.
    assert 0 not in r, r


def test_a_nested_block_whose_text_is_absent_is_not_hidden():
    """Text not found -- the block stays in the book, marked `differs`: hiding the
    unproved would lose text silently, and two readings of one place may carry
    different things, not only different transcriptions."""
    para = _b(0, (0, 0, 100, 20), "about something else entirely")
    formula = _b(1, (10, 5, 40, 12), r"\[1728^{\circ}\mathrm{C}\]",
                 label="inline_formula")
    r = H.repeats_on(_page(para, formula), _covered)
    assert r[1][1] == "differs", r


def test_a_block_is_never_compared_with_itself():
    """A block is not looked for inside itself, or any block repeats: that error
    gave 99.0 % where 21.4 % is right."""
    para = _b(0, (0, 0, 100, 20), "empty")
    one = _b(1, (10, 5, 40, 12), "a unique text", label="inline_formula")
    r = H.repeats_on(_page(para, one), _covered)
    assert r[1][1] == "differs", (
        "the block was declared a repeat although its text exists nowhere "
        f"but in itself -- it is being compared with itself: {r}")


def test_two_equal_nested_blocks_are_not_hidden_together():
    """Two equal nested blocks do not hide each other: each "exists at the
    neighbour", and a naive rule would hide both, losing the text."""
    para = _b(0, (0, 0, 100, 20), "a box without those words")
    a = _b(1, (10, 5, 40, 12), "one and the same", label="inline_formula")
    b = _b(2, (50, 5, 80, 12), "one and the same", label="inline_formula")
    r = H.repeats_on(_page(para, a, b), _covered)
    assert r[1][1] == "differs" and r[2][1] == "differs", (
        f"both repeats are hidden -- not one is left in the book: {r}")


def test_a_block_nested_in_an_artefact_is_not_a_candidate():
    """A block nested in an artefact is not judged here: it has its own counter
    (`text_inside_artifact_boxes`), and hiding it would leave the picture as the
    only form of that text if no replacement comes."""
    # The content is chosen so the formula's text is in it: otherwise the texts
    # would not match anyway and the check would be green on nothing.
    table = Block(block_id=0, box=(0, 0, 100, 20), label="table", score=0.9,
                    content=r"<fcel>1728^{\circ}\mathrm{C}<nl>", kind="otsl")
    formula = _b(1, (10, 5, 40, 12), r"\[1728^{\circ}\mathrm{C}\]",
                 label="inline_formula")
    from booksmith.core import textnorm as T
    assert T.normalize(formula.content, "latex") in T.normalize(
        table.content, "latex"), "the fixture does not test what it exists for"
    r = H.repeats_on(_page(table, formula), _covered)
    assert r.get(1, (None, ""))[1] != "verbatim", (
        "the block was declared a repeat OF AN ARTIFACT -- but an artifact "
        "travels as a picture, and if no swap arrives no text is left in the "
        f"book at all: {r}")


def test_an_empty_block_is_not_a_candidate():
    """A block with no content is no candidate: nothing to compare with."""
    para = _b(0, (0, 0, 100, 20), "text")
    blank = _b(1, (10, 5, 40, 12), None, label="inline_formula")
    r = H.repeats_on(_page(para, blank), _covered)
    assert 1 not in r, r


def test_the_latex_stage_is_declared_with_its_measurement():
    """The comparison stage is in the normalisation registry, not hidden: a number
    without a declared stage means anything a month later. Asked of
    `core.textnorm`, which owns the names."""
    from booksmith.core import textnorm as T
    assert "latex" in T.NORM_STEPS, sorted(T.NORM_STEPS)
    note = T.norm_note("latex")
    assert note["steps"], note
    # A meaningful command name survives, a decorative one is stripped.
    assert T.bare_math(r"\alpha") == "alpha"
    assert T.bare_math(r"\mathrm{C}").strip() == "C"
    # The wrapper comes off both ends.
    assert T.bare_math(r"\[x\]").strip() == "x"
    assert T.bare_math(r"$x$").strip() == "x"


def test_the_latex_stage_falls_on_deliberately_broken_input():
    """The stage must be able to fail: different things must not match."""
    from booksmith.core import textnorm as T
    a = T.normalize(r"\[1728^{\circ}\mathrm{C}\]", "latex")
    b = T.normalize(r"\[1675^{\circ}\mathrm{C}\]", "latex")
    assert a != b, (a, b)
    # And a meaningful command is not eaten: two different letters stay two.
    assert (T.normalize(r"\[\alpha\]", "latex")
            != T.normalize(r"\[\beta\]", "latex"))


def test_the_typeset_form_is_not_traded_for_the_raw_one():
    """A typeset formula is not hidden for raw latex at the carrier: the same
    characters with less typesetting is a worse page and wins nothing."""
    carrier = _b(0, (0, 0, 100, 20), "Fig. V.5. Phase diagram of FeO-SiO_{2}")
    formula = _b(1, (10, 5, 40, 12), r"\[\mathrm{FeO}-\mathrm{SiO}_{2}\]",
                 label="inline_formula")
    r = H.repeats_on(_page(carrier, formula), _covered)
    assert r[1][1] == "layout", (
        f"the typeset formula is hidden and the raw latex is kept: {r}")


def test_the_answer_names_the_carrier_not_the_enclosing_frame():
    """The answer names the block where the proof lies, not the outer box: a
    reference into a box that holds no such text sends a reviewer nowhere."""
    box = _b(0, (0, 0, 60, 20), "an empty enclosing box")
    carrier = _b(1, (0, 0, 100, 40), "here stands 1728\u00b0C and a full stop")
    formula = _b(2, (5, 5, 40, 12), r"\[1728^{\circ}\mathrm{C}\]",
                 label="inline_formula")
    r = H.repeats_on(_page(box, carrier, formula), _covered)
    assert r[2][1] == "verbatim", r
    assert r[2][0] == 1, (
        f"block 0 (the enclosing box) was named, and the text lies in block 1: {r}")


def test_a_two_character_match_is_not_evidence():
    """A match shorter than the threshold is not evidence: "°c" or "50" in a
    paragraph proves nothing about a block holding the same. The threshold is
    `REPEAT_MIN`, and its sweep is at `repeats_on`."""
    assert H.REPEAT_MIN >= 3, H.REPEAT_MIN
    carrier = _b(0, (0, 0, 100, 20), "at 50\u00b0C and onward")
    tiny = _b(1, (10, 5, 40, 12), r"\[50\]", label="inline_formula")
    r = H.repeats_on(_page(carrier, tiny), _covered)
    assert r[1][1] == "differs", (
        f"a two-digit coincidence was taken for proof: {r}")


def test_a_match_across_the_seam_of_two_blocks_is_not_evidence():
    """A match across the seam of two remaining blocks is not evidence: glued
    without a space, the candidate is "found" where no block holds it, and the
    text is not in the book at all."""
    first = _b(0, (0, 0, 100, 20), "end of the line abc")
    second = _b(1, (0, 20, 100, 40), "defg beginning")
    # "abcdefg" exists only across the seam: no one block holds it whole.
    candidate = _b(2, (5, 5, 40, 12), "abcdefg", label="inline_formula")
    r = H.repeats_on(_page(first, second, candidate), _covered)
    assert r[2][1] == "differs", (
        "a match across the seam was taken for proof -- no single block in "
        f"the book holds that text: {r}")
