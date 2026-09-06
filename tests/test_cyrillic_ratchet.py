"""The translation to English may not go backwards, and it is measured.

WHY A RATCHET AND NOT A LOCK. A lock ("no Cyrillic anywhere") can only be
switched on at the very end of the work, and until then it guards nothing. The
work it would guard is 693 633 codepoints across some 90 files -- too large for
one sitting, and therefore exactly the kind of job that drifts back to a
mixture. A ratchet works from the first day: every area may fall, none may
rise, and the number left is the progress of the job.

WHY THIS IS NOT A STYLE CHECK. The count is not an opinion about prose. It is
the one quantity available here at all: no checker reads a comment for meaning,
so no test can say whether a translation kept the point. What a test can say is
whether the work went forwards. That is what this one says, and it says it with
a number.

WHAT IT COST TO LEARN THE SHAPE. The first version of the instrument counted
`.py .md .toml .yml` and missed 13 217 characters in nine tracked files --
among them `models/paddleocr_vl/run.sh`, which executes on a rented GPU, where
a half-translated file is discovered by paying for it. The exemption for book
content was likewise written as a file glob and would have left 8423 characters
of our own prose Russian forever, because `books/*.py` is 9105 characters of
which only 682 are book text.
"""
import json
import os

import support
from booksmith import cyr as _module

# Cyrillic built rather than typed. A test of the counter needs Cyrillic input,
# and typing it here would put a permanent floor under `tests.literals` that no
# translation can remove -- the instrument would be unable to reach its target
# because of its own check.
RU_COMMENT = "# " + "".join(chr(c) for c in (0x43e, 0x434, 0x438, 0x43d))
RU_LETTER = chr(0x44b)

_CACHE = {}


def _cyr():
    return _module


def _count():
    """Counted once per run: the walk is 1.2 s and four checks want the same
    numbers. Cached here rather than inside the tool, because the tool is also
    a command and a command must read the tree as it is now."""
    if "count" not in _CACHE:
        _CACHE["count"] = _cyr().count()
    return _CACHE["count"]


def test_the_baseline_exists_and_covers_every_area():
    """A missing area in the baseline is a hole the ratchet cannot press on."""
    cyr = _cyr()
    assert os.path.isfile(cyr.BASELINE), "no baseline: run tools/cyr.py --save"
    base = json.load(open(cyr.BASELINE, encoding="utf-8"))
    now = _count()
    missing = sorted(set(now) - set(base))
    assert not missing, f"areas absent from the baseline: {missing}"


def test_no_area_grew():
    """The whole point. Each area separately, so a fall cannot hide a rise."""
    cyr = _cyr()
    base = json.load(open(cyr.BASELINE, encoding="utf-8"))
    now = cyr.ratchet_areas(_count())
    grew = {k: (base.get(k, 0), v) for k, v in now.items() if v > base.get(k, 0)}
    assert not grew, f"Cyrillic grew: {grew}"


def test_the_counter_counts_codepoints_not_lines():
    """Rewrapping must be free; translating must not be.

    Proved on the instrument itself rather than on the tree: feeding it two
    strings that differ only by line breaks has to give one number, and adding
    a single letter has to give one more. Without this, a reformatting pass
    would look like progress and a lost sentence like none.
    """
    cyr = _cyr()
    one_line = RU_COMMENT + " " + RU_COMMENT[2:]
    wrapped = RU_COMMENT + "\n# " + RU_COMMENT[2:]
    assert cyr.cyr(one_line) == cyr.cyr(wrapped)
    assert cyr.cyr(one_line + RU_LETTER) == cyr.cyr(one_line) + 1


def test_the_counter_ignores_punctuation_it_must_not_chase():
    """Not "non-ASCII": dashes, arrows and box drawing are legitimate forever.

    Counting them would make the ratchet impossible to bring to zero, and an
    instrument that cannot reach its own target teaches everyone to ignore it.
    """
    cyr = _cyr()
    assert cyr.cyr("-> \u2014 \u00b1 \u2264 \u250c\u2500\u2510 caf\u00e9") == 0
    assert cyr.cyr(chr(0x451) + chr(0x401)) == 2


def test_book_content_is_exempt_by_name_not_by_file():
    """`books/*.py` is 92.5 % our prose; a file-level exemption would hide it."""
    cyr = _cyr()
    c = _count()
    assert c["book_prose"] > 0, "no book content found -- exemption is dead"
    press = cyr.ratchet_areas(c)
    assert "book_prose" not in press
    assert c["src.docstrings"] > c["book_prose"] * 10, (
        "book prose is not being separated from the prose around it")
