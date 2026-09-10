"""Two copies of the `--pages` parser conspire: `detect` and the box entrypoint.

A copy exists because four files ride to the rented machine without the
`booksmith` package, so the parser must arrive as its own text; merging them
means shipping the whole package. The string is parsed on the card, after the
weights are unpacked and the money is running, so a divergence is rent bought
for nothing. The one lawful divergence is the dash: for `dots` it means the
whole book, a shell convention (`run.sh` substitutes `${4:--}`), and for
`detect` a refusal aloud, because at home an empty value is spelled empty.
"""
import importlib.util
import os

import support
from booksmith.core.errors import Refusal


# Inputs the copies must agree on to the character. The space and the junk
# stand here on purpose: the divergence lived in exactly that blind spot.
TABLE = ("1", "1,4,7-9", "2-4", "10", "0", "0-9", "3-1", "",
         "1 3", "1 4 7-9", "1, 4 ,7-9", "x", "7-x", "1,,3", "11")

# The dash is a shell convention, see the header. Checked apart, both ways.
SHELL_ALL = "-"

TOTAL = 10


def _dots_parse_pages():
    """`parse_pages` from the copy that rides to the card, loaded by path: the
    entrypoint is not part of the importable tree. The path is asked of
    `support`, so a damaged copy of the tree is the file this reads."""
    path = support.src_path(os.path.join("processing", "layout", "rented", "dots_ocr",
                                         "entrypoint.py"))
    spec = importlib.util.spec_from_file_location("dots_entrypoint", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.parse_pages


def _outcome(fn, value):
    """What came out: pages, a refusal aloud, or not a refusal aloud. A refusal
    aloud prints a sample and an exit code, anything else a traceback, and
    folding the two into one answer would hide the difference."""
    try:
        return ("pages", fn(value, TOTAL))
    except (SystemExit, Refusal):
        return ("refusal aloud", None)
    except BaseException as e:
        return (f"fell any which way: {type(e).__name__}", None)


def test_both_copies_of_parse_pages_agree():
    """Both copies answer the same on a shared list: the file that counts at
    home and the file that counts for money. Diverged, both still look sound --
    checked at home, falls on the card."""
    from booksmith.processing.layout.detect import parse_pages as canon
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
          "`detect.parse_pages` and "
          "`layout/rented/dots_ocr/entrypoint.parse_pages`. "
          "This is parsed on a rented card, where a refusal costs money.")


def test_the_dash_means_the_whole_book_only_on_the_box():
    """The dash is a shell convention, and the copies diverge on it on purpose.
    Checked both ways, or a declared divergence is indistinguishable from an
    unnoticed one: the whole book for `dots`, a refusal aloud for `detect`."""
    from booksmith.processing.layout.detect import parse_pages as canon
    other = _dots_parse_pages()

    assert _outcome(other, SHELL_ALL) == ("pages", list(range(TOTAL))), (
        "in the copy for the card the dash stopped meaning the whole book. "
        "`run.sh` substitutes it as `${4:--}` and `spec()` sends "
        "`pages or '-'` -- there is no empty positional argument there")
    assert _outcome(canon, SHELL_ALL) == ("refusal aloud", None), (
        "`detect.parse_pages` accepted the dash. At home an empty value is "
        "spelled empty, so the dash here is a typo worth saying aloud")


def test_a_space_separates_pages_in_both_copies():
    """A space separates just like a comma, in both copies. A check of its own
    rather than a row of the shared table, because this is where the copies
    diverged and `--pages "1 3"` fell on the card with a bare `ValueError`."""
    from booksmith.processing.layout.detect import parse_pages as canon
    other = _dots_parse_pages()

    for fn, name in ((canon, "detect"), (other, "dots_ocr")):
        assert _outcome(fn, "1 3") == ("pages", [0, 2]), (
            f"{name}: \"1 3\" was not understood as two pages. A space must "
            f"separate just like a comma")
        assert _outcome(fn, "x") == ("refusal aloud", None), (
            f"{name}: junk in `--pages` must be a refusal ALOUD, with a "
            f"sample and an exit code, not a traceback")
