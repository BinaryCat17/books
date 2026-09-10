from backend.errors import Refusal
from backend.layout import parse_pages

TOTAL = 10


def _outcome(value):
    try:
        return ("pages", parse_pages(value, TOTAL))
    except Refusal:
        return ("refusal aloud", None)
    except Exception as e:
        return (f"traceback {type(e).__name__}", None)


def test_the_table_of_values_is_parsed_or_refused_aloud():
    want = {
        "1": ("pages", [0]),
        "1,4,7-9": ("pages", [0, 3, 6, 7, 8]),
        "2-4": ("pages", [1, 2, 3]),
        "10": ("pages", [9]),
        "0": ("refusal aloud", None),
        "0-9": ("refusal aloud", None),
        "3-1": ("refusal aloud", None),
        "": ("pages", list(range(TOTAL))),
        "1 3": ("pages", [0, 2]),
        "1 4 7-9": ("pages", [0, 3, 6, 7, 8]),
        "1, 4 ,7-9": ("pages", [0, 3, 6, 7, 8]),
        "x": ("refusal aloud", None),
        "7-x": ("refusal aloud", None),
        "1,,3": ("pages", [0, 2]),
        "11": ("refusal aloud", None),
    }
    got = {v: _outcome(v) for v in want}
    assert got == want, {v: (got[v], want[v]) for v in want if got[v] != want[v]}


def test_the_dash_is_a_refusal_at_home():
    assert _outcome("-") == ("refusal aloud", None)
