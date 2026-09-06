"""A repeat inside the page: what is proved by comparison, what only nested.

WHY THIS FILE. `inline_formula` is the second most frequent label of
"Технология огнеупоров" (2012 blocks of 6156). The detector draws its own box
around in-line maths over the paragraph, the second level reads it apart --
and the same place arrives in the book twice: inside the paragraph and as a
separate `<p>`. We pay 32.7 % of all requests to the card for it.

WHAT IS PROVED HERE. One claim: "hide this block and not a character of the
page is lost". Not "this is a duplicate", not "the owner contains it" -- only
that, and only by comparison.

THE ERROR HALF THESE CHECKS WERE WRITTEN FOR. The first version compared a
block WITH ITSELF: it lay inside the prose it was looked for in, and the
number came out 99.0 %. Beside it stood a "chance background" of 1.9-6.7 %,
taken with a shift onto a foreign page where self-matching is impossible by
construction -- so it was not two rules compared but a rule with itself, and
the fifteenfold gap was invented whole. The right numbers: 21.4 % at a worst
background of 2.2 %.

THE SECOND TRAP -- MUTUAL HIDING. Two repeats of one place "have each other",
and both can be hidden, leaving none in the book. So the comparison runs only
against the blocks that REMAIN.
"""
from booksmith.doc import html as H
from booksmith.models.base import Block, Page


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
    """Text not found -- the block stays in the book, marked `differs`.

    Hiding the unproved would lose text silently. Two readings of one place
    diverge in transcription, but may carry different things too.
    """
    para = _b(0, (0, 0, 100, 20), "about something else entirely")
    formula = _b(1, (10, 5, 40, 12), r"\[1728^{\circ}\mathrm{C}\]",
                 label="inline_formula")
    r = H.repeats_on(_page(para, formula), _covered)
    assert r[1][1] == "differs", r


def test_a_block_is_never_compared_with_itself():
    """A block is not looked for inside itself -- else ANY block repeats.

    Exactly this error gave 99.0 % where 21.4 % is right.
    """
    para = _b(0, (0, 0, 100, 20), "empty")
    one = _b(1, (10, 5, 40, 12), "a unique text", label="inline_formula")
    r = H.repeats_on(_page(para, one), _covered)
    assert r[1][1] == "differs", (
        "the block was declared a repeat although its text exists nowhere "
        f"but in itself -- it is being compared with itself: {r}")


def test_two_equal_nested_blocks_are_not_hidden_together():
    """Two equal nested blocks do not hide each other.

    Each "exists at the neighbour", and a naive rule would hide both -- the
    text would vanish from the book.
    """
    para = _b(0, (0, 0, 100, 20), "a box without those words")
    a = _b(1, (10, 5, 40, 12), "one and the same", label="inline_formula")
    b = _b(2, (50, 5, 80, 12), "one and the same", label="inline_formula")
    r = H.repeats_on(_page(para, a, b), _covered)
    assert r[1][1] == "differs" and r[2][1] == "differs", (
        f"both repeats are hidden -- not one is left in the book: {r}")


def test_a_block_nested_in_an_artefact_is_not_a_candidate():
    """A block nested in an ARTEFACT is not judged here.

    It has its own trouble and its own counter (`text_inside_artifact_boxes`):
    the ink went into a picture too. Hiding it is forbidden -- the picture
    becomes the only form of that text if no replacement comes.
    """
    # The content is chosen so the formula's text IS in it: else the mutation
    # "judge an artefact like text" would pass unnoticed -- the texts would
    # not match anyway, and the check would be green on nothing.
    table = Block(block_id=0, box=(0, 0, 100, 20), label="table", score=0.9,
                    content=r"<fcel>1728^{\circ}\mathrm{C}<nl>", kind="otsl")
    formula = _b(1, (10, 5, 40, 12), r"\[1728^{\circ}\mathrm{C}\]",
                 label="inline_formula")
    from booksmith import text as T
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
    """The comparison stage is in the normalisation registry, not hidden.

    A number without a declared stage means anything a month later.
    """
    from booksmith import text as T
    assert "latex" in T.NORM_STEPS, sorted(T.NORM_STEPS)
    note = T.norm_note("latex")
    assert note["steps"], note
    # A MEANINGFUL command name SURVIVES, a decorative one is stripped.
    assert T.bare_math(r"\alpha") == "alpha"
    assert T.bare_math(r"\mathrm{C}").strip() == "C"
    # The wrapper comes off both ends.
    assert T.bare_math(r"\[x\]").strip() == "x"
    assert T.bare_math(r"$x$").strip() == "x"


def test_the_latex_stage_falls_on_deliberately_broken_input():
    """The stage must be able to fail: different things must not match."""
    from booksmith import text as T
    a = T.normalize(r"\[1728^{\circ}\mathrm{C}\]", "latex")
    b = T.normalize(r"\[1675^{\circ}\mathrm{C}\]", "latex")
    assert a != b, (a, b)
    # And a meaningful command is not eaten: two different letters stay two.
    assert (T.normalize(r"\[\alpha\]", "latex")
            != T.normalize(r"\[\beta\]", "latex"))


def test_the_typeset_form_is_not_traded_for_the_raw_one():
    """A typeset formula is not hidden for raw latex at the carrier.

    Measured: 65 blocks of the book where the carrier shows `FeO-SiO_{2}`
    where the block holds `\\[\\mathrm{FeO}-\\mathrm{SiO}_{2}\\]`. Hiding the
    second would worsen the page and win nothing: the same characters, less
    typesetting.
    """
    carrier = _b(0, (0, 0, 100, 20), "Fig. V.5. Phase diagram of FeO-SiO_{2}")
    formula = _b(1, (10, 5, 40, 12), r"\[\mathrm{FeO}-\mathrm{SiO}_{2}\]",
                 label="inline_formula")
    r = H.repeats_on(_page(carrier, formula), _covered)
    assert r[1][1] == "layout", (
        f"the typeset formula is hidden and the raw latex is kept: {r}")


def test_the_answer_names_the_carrier_not_the_enclosing_frame():
    """The answer names the block where the proof LIES, not the outer box.

    Measured: for 23 of 841 the named box did not hold that text at all -- a
    reviewer followed the reference and found no text.
    """
    box = _b(0, (0, 0, 60, 20), "an empty enclosing box")
    carrier = _b(1, (0, 0, 100, 40), "here stands 1728\u00b0C and a full stop")
    formula = _b(2, (5, 5, 40, 12), r"\[1728^{\circ}\mathrm{C}\]",
                 label="inline_formula")
    r = H.repeats_on(_page(box, carrier, formula), _covered)
    assert r[2][1] == "verbatim", r
    assert r[2][0] == 1, (
        f"block 0 (the enclosing box) was named, and the text lies in block 1: {r}")


def test_a_two_character_match_is_not_evidence():
    """A match shorter than the threshold is not evidence.

    "°c" or "50" in a paragraph proves nothing about a block holding the
    same. The threshold is named `REPEAT_MIN`, its sweep is at `repeats_on`.
    """
    assert H.REPEAT_MIN >= 3, H.REPEAT_MIN
    carrier = _b(0, (0, 0, 100, 20), "at 50\u00b0C and onward")
    tiny = _b(1, (10, 5, 40, 12), r"\[50\]", label="inline_formula")
    r = H.repeats_on(_page(carrier, tiny), _covered)
    assert r[1][1] == "differs", (
        f"a two-digit coincidence was taken for proof: {r}")


def test_a_match_across_the_seam_of_two_blocks_is_not_evidence():
    """A match ACROSS THE SEAM of two remaining blocks is not evidence.

    Glue the remaining ones without a space and the candidate is "found"
    where no block holds it: the end of one plus the start of another. The
    text is not in the book, and the block would be hidden anyway.
    """
    first = _b(0, (0, 0, 100, 20), "end of the line abc")
    second = _b(1, (0, 20, 100, 40), "defg beginning")
    # "abcdefg" exists only across the seam: no one block holds it whole.
    candidate = _b(2, (5, 5, 40, 12), "abcdefg", label="inline_formula")
    r = H.repeats_on(_page(first, second, candidate), _covered)
    assert r[2][1] == "differs", (
        "a match across the seam was taken for proof -- no single block in "
        f"the book holds that text: {r}")
