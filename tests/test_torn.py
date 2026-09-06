"""A truncated answer reaches the book, and an impossible shape is named.

WHY THIS FILE EXISTS -- measured, not feared. `books read` counts five zeroes
apart and says them aloud: the reading snapshot of "Технология огнеупоров"
carries "hit the ceiling: 14" and lists all fourteen anchors. Past `read/` the
knowledge vanished: `grep` found neither `finish` nor "truncated" anywhere
else. All fourteen went into the book (118 471 characters, 12.95 % of
everything read), none looking torn.

WHY THE FIVE GUARDS OF `books apply` WERE NOT ENOUGH. A truncated fragment
carries no foreign markers, is not empty, declares its kind, leaves the anchor
set alone and holds no unfinished comment -- it passes all five. The worst,
`p0055-b11`, is a 4x4 table on the scan and a `<table>` with 2047 `<td>` in
ONE row in the book: that row alone holds 36 % of the cells in the book.

AND WHY THE TEARING COUNTERS MISS IT. For `p0055-b11` they are all clean --
0 continuations to nowhere, 0 rows of unequal length, 0 text outside tags.
Not because the table is whole, but because the answer holds no `<nl>` at
all: no rows to compare, nowhere for a continuation to go. A zero from not
understanding, taken for a zero from checking. So `torn_grid` looks at SHAPE.
"""
import json
import os

from booksmith.doc import html as H


# ------------------------------------------------------ table shape ---

def test_torn_grid_catches_the_shape_no_tearing_counter_can_see():
    """A one-row and a one-column table are named; a real one stays silent."""
    # The very `p0055-b11`: 2047 cells in one row, tearing counters clean.
    assert "2047" in (H.torn_grid({"rows": 1, "grid_cells": 2047}) or "")
    # And the mirror case -- `p0166-b2` of the real book: 7 rows in one
    # column, `finish=stop`, every tearing counter clean. No instrument in
    # the project found it before this rule.
    assert "7" in (H.torn_grid({"rows": 7, "grid_cells": 7}) or "")
    # A real table of the book (`p0005-b2`) -- silent.
    assert H.torn_grid({"rows": 9, "grid_cells": 63}) is None


def test_torn_grid_zero_from_absence_is_not_zero_from_checking():
    """No grid is NOT "the shape is fine". Both give None, and this is the
    only place they can be confused: above they are held apart by the field
    "reading observed", which is `None` when `answers/` is absent."""
    assert H.torn_grid(None) is None
    assert H.torn_grid({}) is None
    # A tiny table is not declared impossible: 1x3 is a legal header.
    assert H.torn_grid({"rows": 1, "grid_cells": 3}) is None
    # 1x4 is not, and the border is named by a number, not by eye.
    assert H.torn_grid({"rows": 1, "grid_cells": 4}) is not None
    # THE SAME FROM THE OTHER SIDE. Without this pair nothing held the column
    # threshold: the mutation `rows > 3 -> rows > 1` went through the battery
    # unnoticed, because no check ever fed it a legal single column.
    # Three cells in a column are legal (row labels without data).
    assert H.torn_grid({"rows": 2, "grid_cells": 2}) is None
    assert H.torn_grid({"rows": 3, "grid_cells": 3}) is None
    # Four are not.
    assert H.torn_grid({"rows": 4, "grid_cells": 4}) is not None


def test_torn_grid_falls_on_deliberately_broken_input():
    """The rule must be able to fail: feed it something knowingly broken.

    A real grid of the book with its rows taken away (hitting the ceiling
    cuts the answer before the first `<nl>`) must stop being legal."""
    whole = {"rows": 9, "grid_cells": 63}
    assert H.torn_grid(whole) is None
    damaged = dict(whole, rows=1)
    assert H.torn_grid(damaged) is not None, (
        "a table whose truncation ate every line break was declared lawful "
        "-- the rule is blind to the very thing it exists for")


# --------------------------------------------------- observed beside ---

def _answers(tmp, recs):
    os.makedirs(os.path.join(tmp, "answers"), exist_ok=True)
    with open(os.path.join(tmp, "answers", "p0001.json"), "w",
              encoding="utf-8") as f:
        json.dump({"page": 1, "answers": recs}, f, ensure_ascii=False)


def test_observed_carries_the_reason_the_block_is_bad(tmp_path=None):
    """`observed` pulls the stop reason out of `answers/` by anchor."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        _answers(tmp, [
            {"anchor": "p0001-b0", "text": "...", "outcome": "length",
             "error": None,
             "observed": {"prompt": "Table Recognition:",
                             "kind_promised": "otsl",
                             "otsl_grid": {"rows": 1, "grid_cells": 99}}},
            {"anchor": "p0001-b1", "text": "intact", "outcome": "stop",
             "error": None, "observed": {"prompt": "OCR:"}},
        ])
        o = H.observed(tmp)
        assert o["p0001-b0"]["outcome"] == "length"
        assert o["p0001-b1"]["outcome"] == "stop"
        assert H.torn_grid(o["p0001-b0"]["otsl_grid"])
        assert H.torn_grid(o["p0001-b1"].get("otsl_grid")) is None


def test_no_answers_is_silence_not_a_clean_bill():
    """No `answers/` gives EMPTY, and the build must say so in words rather
    than print "truncated 0" -- the trouble the project rule about two zeroes
    is made of: "chapters 0" meant "I did not recognise them"."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        assert H.observed(tmp) == {}


def test_broken_answers_file_does_not_silently_erase_the_others():
    """One unreadable `answers/` file does not take its neighbours with it.

    Losing the observed silently is the same as never collecting it, but it
    looks like a healthy run."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        _answers(tmp, [{"anchor": "p0001-b0", "outcome": "length",
                        "observed": {}}])
        with open(os.path.join(tmp, "answers", "p0002.json"), "w",
                  encoding="utf-8") as f:
            f.write("{this is not json")
        o = H.observed(tmp)
        assert o["p0001-b0"]["outcome"] == "length"


# ----------------------------- second half: the swap inside the book ---

def test_the_mark_survives_the_replacement():
    """The `books apply` wrapper CARRIES the truncation mark, not strips it.

    The build marks 14 truncated blocks; `books apply` puts its own `<div>`
    over four of them -- and the book was left with 10 marks of 14. The four
    lost were exactly those that reached the reader as markup: a torn table,
    formula and chart. Half the rule lived in `html.py` and was held by
    checks, half in `apply.py` and was not: deleting two lines of
    `_wrap_fragment` reddened none of the 217 checks.
    """
    from booksmith.doc import apply as ap
    intact = ap._wrap_fragment("p1-b0", "<fcel>a<fcel>b<nl>", "otsl",
                               "a probe", torn=False)
    torn = ap._wrap_fragment("p1-b0", "<fcel>a<fcel>b<nl>", "otsl", "a probe",
                             torn=True)
    assert "data-truncated" not in intact, intact
    assert 'data-truncated="yes"' in torn, torn


def test_unknown_is_not_whole():
    """`torn=None` means "not asked"; "whole" does not follow from it.

    A single swap (`--anchor … --file …`) has nothing observed beside it.
    Silence is right; lying was easy either way -- mark by default, or
    declare the block whole.
    """
    from booksmith.doc import apply as ap
    nothing = ap._wrap_fragment("p1-b0", "<fcel>a<nl>", "otsl", "by hand")
    assert "data-truncated" not in nothing, nothing


def test_from_read_asks_the_sidecar_for_the_reason():
    """`from_read` must take truncation from `answers/`, not invent it.

    Checked against the source: without an explicit `torn=`, half the rule
    falls off silently again -- as it already did once.
    """
    import ast

    import support
    t = support.tree("doc/apply.py")
    fn = next(n for n in ast.walk(t)
              if isinstance(n, ast.FunctionDef) and n.name == "from_read")
    calls = [n for n in ast.walk(fn)
             if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Name) and n.func.id == "observed"]
    assert calls, (
        "`from_read` does not call `observed` -- there is nowhere to take "
        "the truncation flag from, and the mark vanishes from exactly the "
        "blocks that arrived as markup")
    passes = [n for n in ast.walk(fn)
                if isinstance(n, ast.Call)
                and isinstance(n.func, ast.Name) and n.func.id == "put_into"
                and any(k.arg == "torn" for k in n.keywords)]
    assert passes, (
        "`from_read` calls `put_into` without `torn=` -- the observed data "
        "is read and thrown away, which is worse than not reading it")


def test_the_torn_field_tells_three_states_apart():
    """"Truncated", "read to the end" and "not asked" are three values.

    Measured: of 6156 blocks 14 are truncated, 6073 were read to the end, and
    69 (pictures) were never asked -- their route is empty with a declared
    reason. The field printed the same `False` for the last two, merging the
    two zeroes it exists to keep apart. An empty `outcome` separates them.
    """
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        _answers(tmp, [
            {"anchor": "p0001-b0", "outcome": "length",
             "observed": {}},
            {"anchor": "p0001-b1", "outcome": "stop", "observed": {}},
            # Not asked: there is no answer, and "whole" does not follow.
            {"anchor": "p0001-b2", "outcome": None, "observed": {}},
        ])
        o = H.observed(tmp)
        # Call the RULE instead of repeating it here: a check that restates
        # what it checks is a tautology and lets mutations through. It did --
        # the mutation "not asked counts as read" passed the first edition.
        state = {a: H.torn_of(v) for a, v in o.items()}
        assert state == {"p0001-b0": True, "p0001-b1": False,
                             "p0001-b2": None}, state
        # No observation at all is also "nothing to say", not "whole".
        assert H.torn_of(None) is None and H.torn_of({}) is None


# ---------------- swap quantities: nothing caught their regression ---
#
# The acceptance pass ran seven mutations against all 225 checks and showed
# the new counters closed BY FORM ONLY: the quantity exists, break it and
# nobody reddens -- the state in which "104 tables at colspan 0" lived a whole
# run. Below is the bench on which each of them can fail.

def _bench(tmp, chunks, cut=()):
    """A book of N blocks, a reading directory and the observed beside it."""
    import json as _j
    import os as _o
    from booksmith.doc import apply as ap
    from booksmith.doc import swap
    with open(_o.path.join(tmp, "book.html"), "w", encoding="utf-8") as f:
        f.write("<!doctype html><html><body>\n" + "\n".join(
            swap.wrap(f"p0000-b{i}", f'<figure id="p0000-b{i}">pic</figure>')
            for i in range(len(chunks))) + "\n</body></html>\n")
    _o.makedirs(_o.path.join(tmp, ap.ASSETS), exist_ok=True)
    with open(_o.path.join(tmp, ap.ASSETS, "blocks.json"), "w",
              encoding="utf-8") as f:
        _j.dump({f"p0000-b{i}": {"role": "artifact"}
                 for i in range(len(chunks))}, f)
    _o.makedirs(_o.path.join(tmp, "read", "pages"), exist_ok=True)
    with open(_o.path.join(tmp, "read", "pages", "0000.json"), "w",
              encoding="utf-8") as f:
        _j.dump({"index": 0, "blocks": [
            {"block_id": i, "kind": "otsl", "content": c}
            for i, c in enumerate(chunks)]}, f)
    _o.makedirs(_o.path.join(tmp, "read", "answers"), exist_ok=True)
    with open(_o.path.join(tmp, "read", "answers", "p0000.json"), "w",
              encoding="utf-8") as f:
        _j.dump({"page": 0, "answers": [
            {"anchor": f"p0000-b{i}",
             "outcome": ("length" if i in cut else "stop"),
             "observed": {}} for i in range(len(chunks))]}, f)


def test_bulk_counts_spans_declared_and_placed():
    """Merges are TWO quantities, and the gap between them is visible.

    Without both, a regression back into repeated cells is invisible in the
    log.
    """
    import tempfile
    from booksmith.doc import apply as ap
    with tempfile.TemporaryDirectory() as tmp:
        _bench(tmp, ["<fcel>h<lcel><nl><fcel>1<fcel>2<nl>",     # 1 merge
                     "<fcel>a<fcel>b<nl><fcel>1<fcel>2<nl>",    # no merges
                     # NON-RECTANGULAR: 1 declared, and it cannot be
                     # placed -- without this case the two numbers agree
                     # and could have been equated unnoticed.
                     "<fcel>h<lcel><nl><fcel>v<ucel><nl>"])
        t = ap.from_read(tmp, os.path.join(tmp, "read"), log=lambda *_: None)
        assert t["merges_declared"] == 2, t
        assert t["merges_in_book"] == 1, t
        assert t["tables_with_merges"] == 2, t
        assert t["merges_declared"] != t["merges_in_book"], (
            "declared and placed agreed -- the discrepancy both numbers "
            "exist for became unobservable")


def test_bulk_counts_the_impossible_shape_of_the_book_not_of_the_run():
    """The shape is counted over the BOOK: a repeat run prints the same.

    The count moved twice and lied twice: among the newly placed (zero on an
    assembled book holding two impossible tables), and at the top of the loop
    (counting blocks the guards refused to place).
    """
    import tempfile
    from booksmith.doc import apply as ap
    with tempfile.TemporaryDirectory() as tmp:
        _bench(tmp, ["<fcel>a<fcel>b<fcel>c<fcel>d<fcel>e<nl>",  # 1x5 -- no
                     "<fcel>a<fcel>b<nl><fcel>1<fcel>2<nl>"])
        first = ap.from_read(tmp, os.path.join(tmp, "read"),
                             log=lambda *_: None)
        assert first["impossible_table_shape"] == 1, first
        again = ap.from_read(tmp, os.path.join(tmp, "read"),
                             log=lambda *_: None)
        assert again["placed"] == 0 and again["already_placed"] == 2, again
        assert again["impossible_table_shape"] == 1, (
            "on a repeat run the number went to zero -- so it is about the "
            "work of THIS run and not about the book, and \"impossible for "
            "0\" reads as \"there are none\"")


def test_bulk_marks_the_torn_block_in_the_book():
    """Truncation reaches the book through the bulk swap as well."""
    import tempfile
    from booksmith.doc import apply as ap
    with tempfile.TemporaryDirectory() as tmp:
        _bench(tmp, ["<fcel>a<fcel>b<nl><fcel>1<fcel>2<nl>",
                     "<fcel>c<fcel>d<nl><fcel>3<fcel>4<nl>"], cut={1})
        ap.from_read(tmp, os.path.join(tmp, "read"), log=lambda *_: None)
        book = open(os.path.join(tmp, "book.html"), encoding="utf-8").read()
        assert book.count('data-truncated="yes"') == 1, book
        # And the mark sits on the TRUNCATED one, not the first to hand.
        i = book.index("p0000-b1")
        assert 'data-truncated="yes"' in book[i:i + 200], book[i:i + 200]


def test_bulk_names_the_rewrap_apart_from_new_work():
    """"Rewrapped" is held apart from "placed".

    Changing OUR wrapper is a real swap and joins the undo stack, but it is
    not work: the model bytes are the same. So the sha compared is of the
    MODEL ANSWER, not of the finished body, which differs by the wrapper.
    """
    import tempfile
    from booksmith.doc import apply as ap
    with tempfile.TemporaryDirectory() as tmp:
        _bench(tmp, ["<fcel>a<fcel>b<nl><fcel>1<fcel>2<nl>"])
        t1 = ap.from_read(tmp, os.path.join(tmp, "read"), log=lambda *_: None)
        assert t1["placed"] == 1 and t1["rewrapped"] == 0, (
            "the first swap is real work, not a re-wrap")
        # A REAL REWRAP: same model bytes, a different wrapper. This is how a
        # book assembled by an older edition of the code looks after a new
        # `apply`: on the refractories book, 63 blocks of 412.
        was = ap._wrap_fragment

        def other_wrapper(anchor, fragment, kind, source, role="unknown",
                           torn=None):
            return was(anchor, fragment, kind, source, role=role,
                        torn=torn).replace("<div ", '<div data-probe="1" ', 1)

        ap._wrap_fragment = other_wrapper
        try:
            t2 = ap.from_read(tmp, os.path.join(tmp, "read"),
                              log=lambda *_: None)
        finally:
            ap._wrap_fragment = was
        assert t2["placed"] == 1, t2
        assert t2["rewrapped"] == 1, (
            "a change to OUR wrapper was recorded as new work -- \"placed\" "
            f"in the journal would mean work that never happened: {t2}")
        # A third run with the old wrapper: the body differs again, the model
        # bytes do not -- work AND a rewrap.
        t3 = ap.from_read(tmp, os.path.join(tmp, "read"), log=lambda *_: None)
        assert t3["rewrapped"] == t3["placed"] == 1, t3
        # THE LAST STACK STEP IS COMPARED, NOT THE FIRST. Someone fixed the
        # block by hand -- putting the model answer back is WORK, though the
        # first step of the stack holds the same bytes. Without this case both
        # comparisons answer alike and `[-1]` -> `[0]` passes unnoticed.
        ap.put(tmp, "p0000-b0", "<fcel>by hand<nl>", kind="otsl",
               source="a person", log=lambda *_: None)
        t4 = ap.from_read(tmp, os.path.join(tmp, "read"), log=lambda *_: None)
        assert t4["placed"] == 1, t4
        assert t4["rewrapped"] == 0, (
            "putting the model's answer back over a hand edit was recorded "
            f"as a re-wrap -- the FIRST step of the stack is being compared, "
            f"not the last: {t4}")


def test_a_refused_block_is_not_counted_as_being_in_the_book():
    """A block the guards refused never enters the numbers OF THE BOOK.

    The shape count once stood before the guards and told of the book what is
    not in it. The refusal here is real: a foreign block marker inside the
    fragment, caught by `_check_fragment`.
    """
    import tempfile
    from booksmith.doc import apply as ap
    with tempfile.TemporaryDirectory() as tmp:
        _bench(tmp, ["<fcel>a<fcel>b<nl><fcel>1<fcel>2<nl>",
                     # 1x5: impossible shape, AND the fragment is refused.
                     "<fcel>a<fcel>b<fcel>c<fcel>d<fcel>e<nl>"
                     "<!--bs:p0000-b9-->"])
        t = ap.from_read(tmp, os.path.join(tmp, "read"), log=lambda *_: None)
        assert t["refused"] == 1, t
        assert t["impossible_table_shape"] == 0, (
            "a refused block was counted among the book's blocks -- and it "
            f"is not in the book: {t}")


def test_the_caption_names_which_zero_it_was():
    """The caption of an empty block names the REASON, not "not read".

    Measured: `p0024-b23` (a binding-shadow strip, 12x408 px) carries
    `outcome: stop`, `error: null` and empty text in `answers/` -- the model
    ANSWERED WITH NOTHING. The book said "not read", read as "we never read
    it". The five zeroes of `books read` collapsed into one, and the one that
    spoke was lying.
    """
    stayed_silent = H.why_empty({"outcome": "stop", "error": None})
    not_asked = H.why_empty({"outcome": None, "error": None})
    refusal = H.why_empty({"outcome": None, "error": "timeout"})
    truncated = H.why_empty({"outcome": "length", "error": None})
    nothing_to = H.why_empty(None)
    all = [stayed_silent, not_asked, refusal, truncated, nothing_to]
    assert len(set(all)) == 5, (
        f"two different zeros were given the same name: {all}")
    assert "kept quiet" in stayed_silent
    assert "never asked" in not_asked
    assert "timeout" in refusal
