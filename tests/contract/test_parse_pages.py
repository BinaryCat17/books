"""The `--pages` parser: what it takes, what it refuses, and how it refuses.

The string is typed by hand and once rode to a rented card, so a refusal is
a line with a sample and an exit code, never a traceback; a space separates
like a comma; the dash, a shell convention on the box, is a refusal at home,
where an empty value is spelled empty.
"""
from booksmith.core.errors import Refusal
from booksmith.processing.layout.detect import parse_pages

TOTAL = 10


def _outcome(value):
    try:
        return "pages", parse_pages(value, TOTAL)
    except Refusal:
        return "refusal aloud", None
    except Exception as e:  # the kind of failure is the finding
        return f"traceback {type(e).__name__}", None


def test_the_table_of_values_is_parsed_or_refused_aloud():
    want = {
        "1": ("pages", [0]), "1,4,7-9": ("pages", [0, 3, 6, 7, 8]),
        "2-4": ("pages", [1, 2, 3]), "10": ("pages", [9]),
        "0": ("refusal aloud", None), "0-9": ("refusal aloud", None),
        "3-1": ("refusal aloud", None), "": ("pages", list(range(TOTAL))),
        "1 3": ("pages", [0, 2]), "1 4 7-9": ("pages", [0, 3, 6, 7, 8]),
        "1, 4 ,7-9": ("pages", [0, 3, 6, 7, 8]),
        "x": ("refusal aloud", None), "7-x": ("refusal aloud", None),
        "1,,3": ("pages", [0, 2]), "11": ("refusal aloud", None),
    }
    got = {v: _outcome(v) for v in want}
    assert got == want, {v: (got[v], want[v]) for v in want if got[v] != want[v]}


def test_the_dash_is_a_refusal_at_home():
    """On the box `-` meant the whole book, a shell convention; at home an
    empty value is spelled empty, so the dash is a typo worth saying aloud."""
    assert _outcome("-") == ("refusal aloud", None)
