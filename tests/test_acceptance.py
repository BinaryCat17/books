"""Reports are compared whole, because the headline numbers are blind.

The five figures everyone quotes -- 698/1232 found, 646 whole, 375 merged, 501
extra jumps, 89.4 % ink -- survived a full rename of all 13 996 Cyrillic keys
in `bench/annopage` without moving. They also survived the rename being stopped
halfway. What moved was the prose around them: a line reading "на объекте вне
замера: 350" simply stopped being printed, and 350 excluded boxes were charged
to the model instead.

So these checks compare every line. `booksmith.acceptance` holds the command
table and the snapshots live in `bench/expected/`.

WHAT THESE CHECKS DO NOT SEE. Each report is produced by a SUBPROCESS, so an
in-memory mutation of `metrics` or `policy` never reaches them. That is the
right shape for their job -- they are run against the tree after each step of
the translation, and they compare what the tree actually prints. Proved by
damaging the tree instead of memory: dropping one lookup of `вне замера` in
`metrics.py` turned "лишняя рамка: 110" into 460 and deleted the line "на
объекте вне замера: 350", and the diff named both.

A missing bench is a SKIP WITH A REASON, never a pass. Most of what these
commands read is behind .gitignore -- `bench/*/detect/pages` and the six
synthetic books -- so on a fresh clone three of the five cannot run. The runner
counts skips as their own number for exactly this case.
"""
import os

import support
from booksmith import acceptance


def _one(name):
    gone = acceptance.missing(name)
    if gone:
        support.skip(f"нет входа: {', '.join(gone)}")
    if not os.path.isfile(acceptance.path(name)):
        support.skip(f"нет слепка {acceptance.path(name)}: "
                     "снять `python3 tools/acceptance.py --save`")
    d = acceptance.differs(name)
    assert not d, (f"отчёт {name} разошёлся со слепком:\n" + "\n".join(d[:40]))


def test_score_on_annopage_reports_the_same_report():
    """600 real pages: the widest report the project has."""
    _one("score-annopage")


def test_score_on_hard_reports_the_same_report():
    """The only tracked bench that mixes annotated text with unannotated.

    `bench/annopage` annotates no text at all, so its text half reads НЕ
    РАЗМЕЧЕНЫ whatever happens to it. `bench/hard` is 124 AnnoPage pages plus
    6 synthetic ones, and it is the only place where the caption "считано по 6
    страницам из 130" exists to be lost.
    """
    _one("score-hard")


def test_text_on_slovar_reports_the_same_report():
    """Truth against itself: the one input where reading has a known answer."""
    _one("text-slovar")


def test_replay_check_reports_the_same_report():
    """`replay --check` returns 1 whether or not anything is wrong.

    Measured: 38 of 55 values present in the snapshot, rc=1, both before and
    after damage. The return code carries no signal here -- only the report
    does, which is why it is compared as text.
    """
    _one("replay-annopage")


def test_help_reports_the_same_text():
    """Nothing else in the suite reads the help at all.

    `grep` over `tests/` finds no occurrence of `help=`, `description=` or
    `--help`: 86 help strings and a 36-line module docstring could go wrong,
    empty or misleading and every check would stay green.
    """
    _one("help")


def test_the_command_table_covers_every_format_the_migration_touches():
    """A snapshot set that misses a format is a blind spot wearing a number."""
    argv = " ".join(a for c, _ in acceptance.COMMANDS.values() for a in c)
    for needed in ("truth", "detect/pages", "detect", "--help"):
        assert needed in argv, f"no acceptance command reads {needed}"
    assert len(acceptance.COMMANDS) >= 5


def test_the_reading_probe_battery_reports_the_same():
    """A report can be identical while the PROBE behind it has stopped working.

    Measured during the key migration: renaming the normalisation level `нет`
    to `none` in `NORM_STEPS` and not at the place that compares against it
    made `--norm none` do exactly what `boundary` does -- three levels became
    two -- and the probe that guarded that distinction threw `TextError`
    instead of measuring. `text-slovar` was byte-identical throughout. Only
    this line moved: "непойманных 0" became 1.
    """
    _one("text-selfcheck")


def test_the_built_book_reports_the_same_swaps():
    """`books html` and `books apply` were read by no report at all.

    Three of the seven defects the key migration left lived there and nowhere
    else: three sheet counters frozen at zero while the book itself marked two
    sheets, a CSS selector left in Russian so 500 furniture blocks stopped
    being dimmed, and a file quietly dropped out of `assets/source`.
    """
    _one("apply-status")
