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

ROOT = _module.ROOT

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


def _areas_of(src):
    """Count one module given as text, without putting it on disk.

    `py_areas` reads files, so the source is written to a scratch file inside
    the tree -- the walk itself never sees it, because the walk asks git.
    """
    import collections
    import tempfile
    c = collections.Counter()
    with tempfile.NamedTemporaryFile("w", suffix=".py", encoding="utf-8",
                                     delete=False) as f:
        f.write(src)
        path = f.name
    try:
        _cyr().py_areas([path], "x", c)
    finally:
        os.unlink(path)
    return c


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


def test_prose_was_translated_not_deleted():
    """The hole the ratchet alone cannot see, and the cheapest way to cheat it.

    The Cyrillic count measures what is LEFT, so the fastest way to move it is
    to delete rather than translate. Measured on a copy of the tree: deleting
    every whole comment line carrying Cyrillic across `src/booksmith/*.py`
    removed 176 515 characters -- a quarter of everything this project has
    written into its comments -- and left the runner green, the battery green,
    all five acceptance reports identical, and the ratchet reporting a quarter
    of the translation done.

    So each area is watched by two numbers. Translation turns Cyrillic into
    Latin; deletion turns it into nothing. A fall in one must show up as a rise
    in the other.

    THE FLOOR IS ONE QUARTER, and deliberately low. The operator asked for the
    prose to be compressed by half while it is translated, and English runs a
    little shorter than Russian for the same thought, so an honest pass may
    return well under half the characters. A quarter is far enough below that
    to never fire on real work, and far enough above zero to catch a deletion.
    """
    cyr = _cyr()
    base = json.load(open(cyr.BASELINE, encoding="utf-8"))
    now = _count()
    lost = []
    for area, was in cyr.ratchet_areas(base).items():
        fell = was - now.get(area, 0)
        if fell < 500:
            continue                     # noise; a real pass moves thousands
        gained = now.get(area + ".latin", 0) - base.get(area + ".latin", 0)
        if gained < fell * 0.25:
            lost.append(f"{area}: -{fell} cyrillic, +{gained} latin")
    assert not lost, ("prose left without arriving in English -- deleted, not "
                      "translated:\n" + "\n".join(lost))


def test_book_content_did_not_move():
    """`book_prose` is exempt, and exempt means constant, not unwatched.

    It is the one area the ratchet does not press on, so nothing else would
    notice if the Russian book text were translated away by accident -- or
    grown, which would mean our own prose had been misfiled as content.
    """
    cyr = _cyr()
    base = json.load(open(cyr.BASELINE, encoding="utf-8"))
    now = _count()
    assert now["book_prose"] == base["book_prose"], (
        f"book content moved: {base['book_prose']} -> {now['book_prose']}. "
        "The books are Russian and stay Russian.")


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
    assert cyr.latin("comment") == 7 and cyr.latin(RU_LETTER) == 0


def test_the_counter_ignores_punctuation_it_must_not_chase():
    """Not "non-ASCII": dashes, arrows and box drawing are legitimate forever.

    Counting them would make the ratchet impossible to bring to zero, and an
    instrument that cannot reach its own target teaches everyone to ignore it.
    """
    cyr = _cyr()
    assert cyr.cyr("-> \u2014 \u00b1 \u2264 \u250c\u2500\u2510 caf\u00e9") == 0
    assert cyr.cyr(chr(0x451) + chr(0x401)) == 2


def test_book_content_is_exempt_by_name_not_by_file():
    """The exemption follows the CONSTANT, and never the file it lives in.

    A file-level exemption for `books/*.py` was the first design and it would
    have left our own prose Russian forever: those files were 9105 characters
    of which only 682 were book text. The exemption is therefore the constant's
    NAME, and this proves it on built input rather than on the tree, so it goes
    on saying something after the last file is translated and every counted
    area is zero.

    Both directions are asserted, because only one of them was ever wrong:
    Russian under a content name must be exempt, and the SAME Russian under any
    other name must be counted as prose.
    """
    cyr = _cyr()
    c = _count()
    assert c["book_prose"] > 0, "no book content found -- exemption is dead"
    assert "book_prose" not in cyr.ratchet_areas(c)

    word = RU_LETTER * 7
    src = f'WORDS{cyr.CONTENT_SUFFIX} = ("{word}",)\nNOTES = ("{word}",)\n'
    counted = _areas_of(src)
    assert counted["book_prose"] == 7, (
        f"content under a name ending in {cyr.CONTENT_SUFFIX!r} was not "
        f"exempted: {counted}")
    assert counted["x.literals"] == 7, (
        f"the same Russian under another name was not counted as prose: "
        f"{counted}")


def test_bench_snapshots_are_weighed_even_though_they_are_exempt():
    """Exempt is a decision. Invisible is the instrument lying by omission.

    `bench/**.json` was SKIPPED outright, so 17 696 codepoints of Russian
    sitting inside nine tracked snapshots -- six manifests and three
    `detect/run.json`, all of them knob descriptions copied in when the run
    happened -- were not counted anywhere at all. The ratchet reported the job
    as smaller than it is, which is the failure this project keeps a rule
    about: a zero from a check and a zero from not looking.

    The name comes from the code (`DATA_PREFIXES`) and the number from the
    disk, so this fails in both directions: restore the skip and it goes red,
    and so does pressing the ratchet on data that must not move.
    """
    cyr = _cyr()
    want = 0
    for rel in cyr.tracked():
        if not any(rel.startswith(d) for d in cyr.DATA_PREFIXES):
            continue
        if rel in cyr.RECORD_FILES or rel.endswith(cyr.RECORD_GLOBS):
            continue
        try:
            want += cyr.cyr(open(os.path.join(ROOT, rel),
                                 encoding="utf-8").read())
        except (UnicodeDecodeError, IsADirectoryError):
            continue
    assert want > 0, "no Cyrillic under bench/ at all -- the walk broke"
    assert _count()["bench_data"] == want, (
        f"bench data weighed as {_count()['bench_data']}, and the disk holds "
        f"{want}. Something under {cyr.DATA_PREFIXES} is not being counted.")
    assert "bench_data" not in cyr.ratchet_areas(_count()), (
        "the ratchet is pressing on records of runs; they can only change by "
        "re-running, and pressing sets a floor it can never reach")


def test_every_character_left_is_declared_and_no_more():
    """The lock: what is left, and why, named file by file.

    WHY A LOCK AND NOT ONLY THE RATCHET. A ratchet goes green at any number.
    It cannot finish a job: the last thousand characters may sit there forever
    with nobody able to say whether they are evidence or oversight. Every entry
    in `RESIDUE` carries a reason, and the count is the price of that reason --
    edit the file and this goes red until somebody decides again.

    IT FAILS IN THREE DIRECTIONS, and the third is the one a ratchet is blind
    to. Russian appearing in a file that declares none is the translation going
    backwards. A declared count that moved is evidence somebody edited. And a
    declaration for Cyrillic that is no longer there is a list rotting -- which
    is exactly how the file-glob exemption and the `CONTENT_NAMES` list both
    went wrong earlier in this migration.

    The names come from the code (`RESIDUE`) and the counts from the disk.
    """
    cyr = _cyr()
    unexpected, moved, stale = cyr.undeclared()
    assert not unexpected, (
        "Cyrillic in files that declare none: "
        + ", ".join(f"{p} ({n})" for p, n in sorted(unexpected.items())))
    assert not moved, (
        "declared counts moved: "
        + "; ".join(f"{p} {was} -> {now}" for p, (was, now) in sorted(moved.items())))
    assert not stale, (
        f"RESIDUE declares Cyrillic that is gone: {stale}. Delete the entry -- "
        "a list nobody prunes stops being read.")
    assert cyr.RESIDUE, "the residue declaration is empty: the lock guards nothing"
