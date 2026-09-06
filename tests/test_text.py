"""The READING instrument: the last line of the report, and its zeros.

WHY THIS FILE EXISTS. `text.report` was called by NOT ONE check and not one
probe of the battery -- and it is exactly the function a person reads. The
price of leaving it unguarded showed up the same day, twice over:

  * an artifact record carries no `WER` (words are not counted in a formula)
    and the "worst block" line printed it -- one wrong letter in one formula
    brought `books text` down with `KeyError: 'WER'`. On a paid run that
    means: money spent, answers written, no report;
  * the denominator of the last line was counted over text blocks and the
    numerator over text AND artifact blocks, so a book with formulas printed
    "CER 0 on all 130 computed of 104". The guard "there was NOTHING to
    compare" never fired: a silent model again got "no blocks with an error".

The corruption battery cannot catch this by construction -- it looks at
NUMBERS, and this is about printing. So: a check.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from booksmith import text                                  # noqa: E402


def _pages(blocks, side=None):
    """One page of truth or answer, in the `Page` shape."""
    return {0: {"index": 0, "width": 100, "height": 100, "dpi": 144.0,
                "blocks": blocks,
                "meta": {"artifact_truth": side} if side else {}}}


def _text_block(i, content):
    return {"block_id": i, "box": [0, i * 10, 90, i * 10 + 8], "label": "text",
            "content": content, "kind": "text" if content else "none"}


def _formula_block(i, content):
    return {"block_id": i, "box": [0, i * 10, 90, i * 10 + 8],
            "label": "display_formula", "content": content,
            "kind": "latex" if content else "none"}


def _say(truth, answer):
    """The report as lines. Exactly what a person will see."""
    out = []
    text.report(text.measure_pages(truth, answer), log=out.append)
    return "\n".join(out)


# ---------------------------------------------------------- the last line ---

def test_silence_is_not_reported_as_perfect_reading():
    """The model was silent on all of them -- and that is NOT "CER 0 on all N"."""
    T = _pages([_text_block(0, "first"), _text_block(1, "second")])
    P = _pages([_text_block(0, None), _text_block(1, None)])
    s = _say(T, P)
    assert "there was NOTHING to compare" in s
    # The CLAIM "CER 0 on all" must not appear. The claim is what is looked
    # for: the correcting line itself ends by quoting "this is NOT 'CER 0 on
    # all'", so a plain substring test would redden a correct report.
    assert "no text blocks with an error" not in s


def test_perfect_reading_counts_only_text_in_the_text_line():
    """The denominator of the last line is text blocks, and only those.

    Measured before the fix: a book of 104 text blocks and 26 formulas printed
    "CER 0 on all 130 computed of 104" -- the numerator over both roles, the
    denominator over one.
    """
    T = _pages([_text_block(0, "prose"), _formula_block(1, None)],
               side={"1": {"text": "x = 1"}})
    P = _pages([_text_block(0, "prose"), _formula_block(1, "x = 1")])
    s = _say(T, P)
    assert "no text blocks with an error: CER 0 on all 1 computed of 1" in s
    assert ("no artifact blocks with an error: CER 0 on all 1 computed "
            "of 1") in s


def test_one_wrong_letter_in_a_formula_does_not_crash():
    """An error in a formula is printed, not fatal to the instrument.

    An artifact record carries no `WER`, and the "worst block" line printed it.
    """
    T = _pages([_text_block(0, "prose"), _formula_block(1, None)],
               side={"1": {"text": "x = 1"}})
    P = _pages([_text_block(0, "prose"), _formula_block(1, "z = 1")])
    s = _say(T, P)                      # does not throw: that IS the check
    assert "worst artifact block" in s
    assert "WER" not in s.split("worst artifact block")[1].split("\n")[0]


def test_silent_formulas_are_not_a_measured_one():
    """Silence on EVERY formula is "nothing to compare", not "CER 1.0"."""
    T = _pages([_text_block(0, "prose"), _formula_block(1, None)],
               side={"1": {"text": "x = 1"}})
    P = _pages([_text_block(0, "prose"), _formula_block(1, None)])
    s = _say(T, P)
    assert "THERE IS NO ANSWER TO A SINGLE ONE" in s
    assert "CER 1.0000" not in s


# --------------------------------------------------------------- roles ------

def test_artefact_with_truth_is_not_a_bait():
    """A formula HAS a truth: reading it is work, not invention."""
    T = _pages([_formula_block(0, None)], side={"0": {"text": "x = 1"}})
    P = _pages([_formula_block(0, "x = 1")])
    r = text.measure_pages(T, P)
    assert r["artifacts_with_truth"]["block_count"] == 1
    assert r["artifacts_with_truth"]["CER"] == 0.0
    assert r["baits"]["artifacts"] == 0


def test_artefact_without_truth_stays_a_bait():
    """A figure has none: any text in the answer is invention."""
    T = _pages([{"block_id": 0, "box": [0, 0, 90, 8], "label": "image",
                 "content": None, "kind": "none"}])
    P = _pages([{"block_id": 0, "box": [0, 0, 90, 8], "label": "image",
                 "content": "made up", "kind": "text"}])
    r = text.measure_pages(T, P)
    assert r["baits"]["artifacts"] == 1 and r["baits"]["read"] == 1
    assert r["artifacts_with_truth"]["block_count"] == 0


def test_invention_on_declared_emptiness_is_counted():
    """The artifact's truth is an empty string and the model wrote something:
    a quantity of its own.

    CER cannot see this at all (there is nothing to divide by), and without a
    counter, invention on declared emptiness would vanish in silence.
    """
    T = _pages([_formula_block(0, None)], side={"0": {"text": ""}})
    P = _pages([_formula_block(0, "made up fourteen")])
    r = text.measure_pages(T, P)
    assert r["artifacts_with_truth"]["invented_on_empty_truth"] == 1


def test_two_truths_on_one_artefact_are_loud():
    """Both a grid and characters on one block: a refusal out loud, not a quiet
    choice."""
    T = _pages([_formula_block(0, None)],
               side={"0": {"text": "x = 1", "table": [["a", "b"]]}})
    P = _pages([_formula_block(0, "x = 1")])
    try:
        text.measure_pages(T, P)
    except text.TextError as e:
        assert "BOTH a table grid" in str(e) or "grid" in str(e)
    else:
        raise AssertionError("two truths on one block passed in silence")


# ------------------------------------------------------------- tables ---

def test_table_in_otsl_scores_like_the_same_table_in_html():
    """The same correct answer in two kinds gives the same numbers."""
    grid = [["A", "B"], ["1", "2"]]
    T = _pages([{"block_id": 0, "box": [0, 0, 90, 8], "label": "table",
                 "content": None, "kind": "none"}],
               side={"0": {"table": grid}})
    as_html = ("<table><tr><td>A</td><td>B</td></tr>"
               "<tr><td>1</td><td>2</td></tr></table>")
    as_otsl = "<fcel>A<fcel>B<nl><fcel>1<fcel>2<nl>"
    got = []
    for body, kind in ((as_html, "html"), (as_otsl, "otsl")):
        P = _pages([{"block_id": 0, "box": [0, 0, 90, 8], "label": "table",
                     "content": body, "kind": kind}])
        b = text.measure_pages(T, P)["tables"]
        got.append((b["cells_matched"], b["given_as_text"], b["cer_cells"]))
    assert got[0] == got[1] == (4, 0, 0.0), got


def test_a_cell_with_angle_brackets_survives_the_round_trip():
    """A cell with `<` and `&` comes back from HTML THE SAME. Or the
    instrument lies.

    WHAT PAID FOR THIS. `_grid_html` did not escape, so the round trip
    grid -> HTML -> grid lost content: `a<b&c` came back as `a`, because the
    parser read `<b&c` as an opening tag. The corruption battery damages THE
    GRID and hands the metric that string -- so the cell was truncated BEFORE
    the damage went in, and the number belonged to a different string than the
    one the battery reported on. The neighbouring `otsl.to_html` has escaped
    since day one; this was a second, diverged copy of the same loop.

    THE MEASUREMENT THAT JUSTIFIED IT WAS WRONG. It said here that not one
    cell of 6812 blocks read by a real model held `<` or `&`, and that the
    first chemistry book would change it. In fact the book in the corpus IS a
    chemistry book, and it holds 24 such cells of 5726 (`< 3`, `<1,0`,
    `<28 ...`). The zero came out because the cells were extracted with the
    regexp `<fcel>([^<]*)` -- an instrument carrying the very defect it was
    fixing: it stops at `<`. A circular argument.

    The fix stands, but its price is different: none of the 24 was corrupted,
    because a browser treats `<` as a literal when no letter follows.
    Dangerous is `<` before a letter -- absent from the corpus -- and the check
    stands here for the first table where it appears.
    """
    was = {(0, 0): "a<b & c", (0, 1): "plain",
           (1, 0): '"quoted"', (1, 1): "5 > 3"}
    now = text._html_grid(text._grid_html(was))
    assert now == was, (
        f"the grid round trip lost content:\n  was  {was}\n"
        f"  now  {now}\nA cell must be escaped -- otherwise the battery "
        f"measures a different string than the one it reports on")
