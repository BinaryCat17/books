"""Two copies of the `--pages` parser conspire: `detect` and
`dots_ocr/entrypoint`.

WHY A COPY EXISTS. Four files ride to the rented machine (`inputs` in
`models/dots_ocr/__init__.py:spec()`); the `booksmith` package is not there,
so the page-string parser must arrive as its own text. Merging them means
shipping the whole package. Keeping them from diverging SILENTLY is possible,
and is this file.

WHAT PAID FOR IT. There was no guard, and the copy admitted it while listing
a manual check: "1", "1,4,7-9", "130", "2-4" must agree, and "0", "0-9",
"3-1" must be refused by both. That list had no SPACE in it, and the space is
exactly where the copies had diverged. Measured before the fix, 4 of 13
inputs -- on each of them `dots` raised a bare `ValueError: invalid literal
for int()`:

    "1 3"      detect [0, 2]
    "1 4 7-9"  detect [0, 3, 6, 7, 8]
    "x"        detect refuses aloud
    "7-x"      detect refuses aloud

The price is not cosmetic: the string is parsed ON THE CARD, after the
weights are unpacked and the money is running, and a bare traceback there is
rent bought for nothing. `books detect --pages "1 3"` works at home; the same
key fell on the box.

THE ONE LAWFUL DIVERGENCE is the dash. For `dots` it means the whole book --
a SHELL convention, not a parser one: `run.sh` substitutes `${4:--}` and
`spec()` sends `pages or '-'`, because an empty positional argument never
reaches `bash`. For `detect` the dash is a refusal aloud, because at home an
empty value is spelled empty. Declared here and checked, not assumed.
"""
import importlib.util
import os
import sys

import support

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))

# Inputs the copies must agree on TO THE CHARACTER. The space and the junk
# stand here on purpose: the manual list in the copy's docstring named
# neither, and the divergence lived in exactly that blind spot.
TABLE = ("1", "1,4,7-9", "2-4", "10", "0", "0-9", "3-1", "",
         "1 3", "1 4 7-9", "1, 4 ,7-9", "x", "7-x", "1,,3", "11")

# The dash is a shell convention, see the header. Checked apart, both ways.
SHELL_ALL = "-"

TOTAL = 10


def _dots_parse_pages():
    """`parse_pages` from the copy that rides to the card, loaded by path.

    Not by importing the package: `models/dots_ocr/entrypoint.py` is the
    entry point FOR THE BOX, not part of the importable tree, and pulling it
    in as a package module would check the wrong file.

    The path is asked of `support` instead of being built here from
    `__file__`, and that is not style: the damage battery (`sources()`) swaps
    `support.SRC` for a copy of the tree with one line broken. A check that
    knew the path itself would read the real file past the damage and stay
    green on broken code -- which is what happened on the first run: two
    mutations were reported as not caught, though reverting either by hand
    reddens both checks.
    """
    path = support.src_path(os.path.join("models", "dots_ocr",
                                         "entrypoint.py"))
    spec = importlib.util.spec_from_file_location("dots_entrypoint", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.parse_pages


def _outcome(fn, value):
    """What came out: pages, a refusal aloud, or NOT a refusal aloud.

    Three answers, not two. A refusal aloud (`SystemExit`) and "fell any
    which way" (any other exception) are different things: the first prints a
    sample and an exit code, the second gives a traceback. That is exactly
    where the copies diverged, and folding them into one answer would hide
    the fix.
    """
    try:
        return ("pages", fn(value, TOTAL))
    except SystemExit:
        return ("refusal aloud", None)
    except BaseException as e:               # noqa: BLE001 -- the kind matters
        return (f"fell any which way: {type(e).__name__}", None)


def test_both_copies_of_parse_pages_agree():
    """Both copies of the `--pages` parser answer THE SAME on a shared list.

    The conspiracy is between the file that counts at home and the file that
    counts for money. Diverged, both still look sound: checked at home, falls
    on the card.
    """
    from booksmith.detect import parse_pages as canon
    other = _dots_parse_pages()

    mismatches = []
    for value in TABLE:
        a, b = _outcome(canon, value), _outcome(other, value)
        if a != b:
            mismatches.append(f"  \"{value}\": detect {a} != dots {b}")
    assert not mismatches, (
        "the copies of the `--pages` parser diverged:\n"
        + "\n".join(mismatches)
        + "\nA fix in one must be repeated in the other: "
          "`detect.parse_pages` and `models/dots_ocr/entrypoint.parse_pages`. "
          "This is parsed on a rented card, where a refusal costs money.")


def test_the_dash_means_the_whole_book_only_on_the_box():
    """The dash is a SHELL convention, and the copies diverge on it ON PURPOSE.

    Checked both ways, or a declared divergence is indistinguishable from an
    unnoticed one: for `dots` the dash must give the whole book, for `detect`
    a refusal aloud. Should they agree, someone merged the copies without
    thinking, and `run.sh` with its `${4:--}` starts getting a refusal where
    it used to count the whole book.
    """
    from booksmith.detect import parse_pages as canon
    other = _dots_parse_pages()

    assert _outcome(other, SHELL_ALL) == ("pages", list(range(TOTAL))), (
        "in the copy for the card the dash stopped meaning the whole book. "
        "`run.sh` substitutes it as `${4:--}` and `spec()` sends "
        "`pages or '-'` -- there is no empty positional argument there")
    assert _outcome(canon, SHELL_ALL) == ("refusal aloud", None), (
        "`detect.parse_pages` accepted the dash. At home an empty value is "
        "spelled empty, so the dash here is a typo worth saying aloud")


def test_a_space_separates_pages_in_both_copies():
    """A space separates just like a comma -- IN BOTH copies.

    A check of its own rather than a row of the shared table, because this is
    where the copies lived their divergence: the manual list in the copy's
    docstring did not name the space, and `--pages "1 3"` fell on the card
    with a bare `ValueError` after the weights were unpacked and the money
    was running.
    """
    from booksmith.detect import parse_pages as canon
    other = _dots_parse_pages()

    for fn, name in ((canon, "detect"), (other, "dots_ocr")):
        assert _outcome(fn, "1 3") == ("pages", [0, 2]), (
            f"{name}: \"1 3\" was not understood as two pages. A space must "
            f"separate just like a comma")
        assert _outcome(fn, "x") == ("refusal aloud", None), (
            f"{name}: junk in `--pages` must be a refusal ALOUD, with a "
            f"sample and an exit code, not a traceback")
