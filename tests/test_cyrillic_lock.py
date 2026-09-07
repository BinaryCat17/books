"""The translation is done; this is the lock that keeps it done.

WHY A LOCK AND NOT A RATCHET, NOW. The first version of this file argued the
other way, and correctly: "a lock (no Cyrillic anywhere) can only be switched
on at the very end of the work, and until then it guards nothing. The work it
would guard is 693 633 codepoints across some 90 files -- too large for one
sitting, and therefore exactly the kind of job that drifts back to a mixture."
The job is finished. What is left CANNOT be translated -- Russian book titles,
text quoted from those books, the Russian page text drawn onto a synthetic
sheet, and the bounds of the Cyrillic block inside the counters themselves --
and each is declared by file, by count and by reason. The count itself is not
written here: it moved three times in a day while this sentence said 926, and
a number in prose beside a number in code is the drift this project keeps a
rule about. `tools/cyr.py` prints it.

The lock is strictly stronger than the ratchet was: the ratchet pressed on
area totals, so Cyrillic could move from one file to another inside an area
without a word; the lock names every file. What went with the ratchet is
`cyr-baseline.json`, the per-area press, and the companion Latin count that
answered "was it translated or deleted?" -- a question nobody is asking any
more, and one whose measurement is kept in the module's header.

WHAT IT COST TO LEARN THE SHAPE. The first version of the instrument counted
`.py .md .toml .yml` and missed 13 217 characters in nine tracked files --
among them `read/rented/paddleocr_vl/run.sh`, which executes on a rented GPU,
where a half-translated file is discovered by paying for it. The exemption for
book content was likewise written as a file glob and would have left 8423
characters of our own prose Russian forever, because `books/*.py` is 9105
characters of which only 682 are book text.
"""
import os

import support
from booksmith.tree import cyr as _module

ROOT = _module.ROOT

# Cyrillic built rather than typed. A test of the counter needs Cyrillic input,
# and typing it here would put a permanent floor under `tests.literals` that no
# translation can remove -- the instrument would be unable to reach its target
# because of its own check.
RU_COMMENT = "# " + "".join(chr(c) for c in (0x43e, 0x434, 0x438, 0x43d))
RU_LETTER = chr(0x44b)

def _cyr():
    return _module


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

    Counting them would make the lock impossible to bring to its floor, and an
    instrument that cannot reach its own target teaches everyone to ignore it.
    """
    cyr = _cyr()
    assert cyr.cyr("-> \u2014 \u00b1 \u2264 \u250c\u2500\u2510 caf\u00e9") == 0
    assert cyr.cyr(chr(0x451) + chr(0x401)) == 2


def test_page_text_is_declared_like_everything_else():
    """The exemption that cost 110 lines, and what replaced it.

    Page text lives in constants named `*_RU`, and the first design exempted
    the FILES they live in -- which would have left 8423 characters of our own
    commentary Russian forever, because `books/*.py` was 9105 characters of
    which only 682 were book text. The second design exempted the constant by
    NAME, and to find the name it split every .py into comments, docstrings,
    literals and identifiers with `tokenize` and `ast`.

    The lock needs neither: it declares the FILE and its count, so the 468
    characters of page text sit inside the two declared numbers, where a
    change to the book text goes red like any other change. Stricter than the
    exemption was -- `book_prose` was exempt and, once the baseline went,
    watched by nothing at all.
    """
    cyr = _cyr()
    now = cyr.residue()
    for rel in ("src/booksmith/datasets/make/synth/draw.py",
                "src/booksmith/datasets/make/synth/books/slovar.py"):
        assert rel in now and rel in cyr.RESIDUE, (
            f"{rel} holds the page text and is not declared: it would be "
            f"exempt and unwatched, which is how the first two designs failed")
        assert "PAGE" in cyr.RESIDUE[rel][1], (
            f"{rel} is declared without saying it is page text")


def test_bench_snapshots_are_weighed_even_though_they_are_exempt():
    """Exempt is a decision. Invisible is the instrument lying by omission.

    `bench/**.json` was SKIPPED outright, so 17 696 codepoints of Russian
    sitting inside nine tracked snapshots -- six manifests and three
    `detect/run.json`, all of them knob descriptions copied in when the run
    happened -- were not counted anywhere at all. The instrument reported the
    job as smaller than it is, which is the failure this project keeps a rule
    about: a zero from a check and a zero from not looking.

    The name comes from the code (`DATA_PREFIXES`) and the number from the
    disk, so this fails in both directions: restore the skip and it goes red,
    and so does declaring data that must not move, which would set a floor the
    lock can never reach.
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
    weighed = cyr.weighed()
    got = next(v for k, v in weighed.items() if k.startswith("bench data"))
    assert got == want, (
        f"bench data weighed as {got}, and the disk holds {want}. Something "
        f"under {cyr.DATA_PREFIXES} is not being counted.")
    assert not any(p.startswith(cyr.DATA_PREFIXES) for p in cyr.residue()), (
        "the lock is declaring records of runs; they can only change by "
        "re-running, and declaring them sets a floor it can never reach")


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
