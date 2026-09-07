"""The Cyrillic lock: which files hold Russian, how much, and why it stays.

THE TRANSLATION IS DONE, and this is what is left of the instrument that did
it. Every character it now finds is a Russian BOOK TITLE, text quoted from one
of those books, page text drawn onto a synthetic page, or the two regexps that
hunt for Russian and therefore contain its alphabet. None can be translated:
inventing an English name for a real book of this project would cut the thread
between a number in `docs/` and the comment that measured it.

WHAT WENT WITH THE JOB, and what it knew. There was a ratchet over four areas
per file -- comments, docstrings, string literals, identifiers, split by
`tokenize` and `ast` and each pressed on separately -- a companion count of the
Latin that arrived where the Cyrillic left, and a tracked baseline of both. All
of it existed for a job that is finished, and the area split existed for ONE
exemption: page text lives in constants named `*_RU`, and a file-glob exemption
for the generators would have left 8423 characters of our own commentary
Russian forever. The lock does not need the split, because it declares the
FILE: `draw.py` and `books/slovar.py` carry their 468 characters of page text
in their declared counts, where a change to the book text goes red like any
other change. Simpler, and stricter -- the ratchet let Cyrillic move between
files inside an area without a word.

The one thing worth carrying out of that machinery, because the next bulk edit
of prose will meet it: the cheapest way to move a "how much is left" count is
not to translate but to DELETE. Measured on a copy of the tree, deleting every
whole comment line carrying Cyrillic across `src/booksmith` removed 176 515
characters -- a quarter of everything this project has written into its
comments -- and left the runner green, the battery green, every acceptance
report identical, and the ratchet reporting a quarter of the translation done.
That is why the job was watched by two numbers and not one.

WHY CODEPOINTS AND NOT LINES OR WORDS. Rewrapping a comment, splitting a
paragraph or merging two sentences changes lines and words while changing
nothing that matters. Only translation moves codepoints. Measured: rewrapping
one comment across five lines left the count untouched; adding a single letter
moved it by one.

WHY NOT "NON-ASCII". The project legitimately contains typographic dashes,
arrows and box drawing, and counting those would make the lock impossible to
bring to its floor. An instrument that cannot reach its own target teaches
everyone to ignore it.

    python3 tools/cyr.py            what is left, file by file, and why
    python3 tools/cyr.py --check    fail on anything undeclared

It lives here, in `booksmith.tree`, rather than in `tools/` for one reason: the
mutation battery breaks modules by importing them, and `tools/` is not
importable. An instrument the battery cannot break is an instrument nobody has
checked.
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

# Cyrillic (U+0400..U+04FF) and Cyrillic Supplement (U+0500..U+052F). The
# bounds are escapes rather than letters on purpose: written as characters
# they would be four Cyrillic codepoints in this very file, and the counter
# would count itself.
def cyr(s: str) -> int:
    return sum(1 for c in s if "\u0400" <= c <= "\u04ff" or
               "\u0500" <= c <= "\u052f")


# Tracked data. Its Cyrillic is exempt and NOT declared file by file: the keys
# were handled by the migration and the content must not move at all, so
# pressing here would set a floor the lock can never reach. Exempt, and
# weighed -- that took a second try. The first version SKIPPED `bench/**.json`
# outright, so 17 696 codepoints of stale Russian inside nine tracked
# snapshots were not merely exempt but invisible: knob descriptions copied in
# when the run happened. Exempt is a decision; invisible is the instrument
# lying by omission.
DATA_PREFIXES = ("bench/",)

# The record of the key rename, read by `tests/test_data_contract.py`.
RECORD_FILES = ("tools/keymap.json",)

# Logs of a run that was paid for. `bench/*/dots/job.log` is what the rented
# card printed while it worked, and rewriting a log after the fact destroys
# the one thing a log is for -- the argument that also keeps
# `runs/ledger.jsonl` out of any migration.
RECORD_GLOBS = ("job.log",)


def tracked():
    """Files git would keep: tracked, plus untracked that are not ignored.

    NOT `git ls-files` alone. That counts only what is staged or committed, so
    a new file is invisible until `git add` and the whole count jumps at commit
    time -- which is exactly how the first baseline of this instrument came out
    941 characters low, and it was red the moment its own commit landed.
    """
    r = subprocess.run(["git", "ls-files", "-z", "--cached", "--others",
                        "--exclude-standard"],
                       capture_output=True, text=True, cwd=ROOT)
    out = {p for p in r.stdout.split("\0") if p}
    return sorted(p for p in out if os.path.isfile(os.path.join(ROOT, p)))


def exempt(rel: str) -> bool:
    """Weighed elsewhere, never declared here. A function because the
    exemption is a DECISION, and a mutation must be able to break it."""
    return (any(rel.startswith(d) for d in DATA_PREFIXES)
            or rel in RECORD_FILES or rel.endswith(RECORD_GLOBS))


def residue():
    """path -> Cyrillic characters, over everything the lock presses on."""
    out = {}
    for rel in tracked():
        if exempt(rel):
            continue
        try:
            n = cyr(open(os.path.join(ROOT, rel), encoding="utf-8").read())
        except (UnicodeDecodeError, IsADirectoryError, FileNotFoundError):
            continue
        if n:
            out[rel] = n
    return out


def weighed():
    """The exempt classes, as one number each. Exempt, not invisible."""
    data = records = 0
    for rel in tracked():
        if not exempt(rel):
            continue
        try:
            n = cyr(open(os.path.join(ROOT, rel), encoding="utf-8").read())
        except (UnicodeDecodeError, IsADirectoryError, FileNotFoundError):
            continue
        # RECORDS FIRST: `bench/*/dots/job.log` is under a data prefix AND is
        # a paid run's log. Classifying by the prefix first moved 2499
        # characters from one exempt class to the other and made the two
        # numbers disagree with the check that walks the disk itself.
        if rel in RECORD_FILES or rel.endswith(RECORD_GLOBS):
            records += n
        else:
            data += n
    return {"bench data (records of runs, rewritten only by re-running them)":
            data,
            "records (the key rename map, and the logs of paid runs)":
            records}


# THE LOCK. What is left, and why -- named file by file, with the count as the
# price of the reason: edit the file and this goes red until somebody decides
# again. A list without counts rots; a count without a reason cannot be
# finished, because nobody can say whether the last thousand characters are
# evidence or oversight.
#
# The four kinds, and there are only four:
#   TITLE  a real book of this project. An English name for it would cut the
#          thread between a number here and the same number elsewhere.
#   DATA   text quoted from those books, or a name from before the migration.
#          The spelling IS the measurement -- see `djvu.py`, where the pipe in
#          a caption marks where the spread splits a word.
#   PAGE   Russian page text drawn onto a synthetic page. It is the book the
#          bench pretends to be; translating it would change the measurement.
#   TOOL   an instrument whose subject is Russian: the regexps that hunt for
#          Cyrillic and therefore contain its alphabet.
RESIDUE = {
    "docs/contour-notes.md": (13, "DATA: the dirty-tree marker as it stands "
                              "in the tracked run.json snapshots"),
    "docs/lessons-from-deleted-code.md": (29, "DATA: the homoglyph pair, whose "
                                          "point is that one is Cyrillic; and "
                                          "a real file name"),
    "docs/models.md": (29, "TITLE, and the pre-rename attribute name of the "
                       "egret fingerprint defect"),
    "src/booksmith/core/knobs.py": (60, "TITLE"),
    "src/booksmith/core/otsl.py": (94, "TITLE and DATA: a column header and a "
                                   "cell of the table this parser was built "
                                   "from"),
    "src/booksmith/core/raster.py": (20, "TITLE"),
    "src/booksmith/core/textnorm.py": (20, "TITLE: the book whose 1935 nested "
                                       "blocks measured the latex step"),
    "src/booksmith/datasets/make/synth/books/slovar.py": (
        136, "PAGE: the Russian half of the parallel-text page. It was an "
        "inline literal in the middle of a function once, exempted by "
        "nothing, and translating it would have destroyed the page"),
    "src/booksmith/datasets/make/synth/draw.py": (
        332, "PAGE: the words and syllables the drawers put on a synthetic "
        "sheet. The bench pretends to be a Russian technical book, and the "
        "ink measurement is taken over these very glyphs"),
    "src/booksmith/datasets/metrics/text.py": (5, "TITLE, and the name of the "
                                               "dead truth key this file "
                                               "stopped reading"),
    "src/booksmith/processing/assess/ink.py": (20, "TITLE"),
    "src/booksmith/processing/extract/djvu.py": (
        226, "TITLE and DATA: four books, and the three table captions split "
        "across the gutter"),
    "src/booksmith/processing/read/driver.py": (39, "TITLE"),
    "tests/test_data_contract.py": (4, "TOOL: the bounds of the Cyrillic "
                                    "block, in two regexps hunting Russian "
                                    "`data-` attributes and class names"),
    "tests/test_djvu.py": (68, "TITLE, four of them"),
    "tests/test_otsl_html.py": (146, "TITLE and DATA: the real table this "
                                "check is built from"),
    "tests/test_repeat.py": (20, "TITLE"),
    "tests/test_torn.py": (20, "TITLE"),
    "tools/spread_probe.py": (109, "TITLE, two of them"),
}


def undeclared(now=None):
    """(Cyrillic where none is declared, declared counts that moved, entries
    for Cyrillic that is gone).

    Three directions, and the third is the one a ratchet was blind to: a
    declaration for characters that are no longer there is a list rotting --
    which is exactly how the file-glob exemption and the constant-name list
    both went wrong earlier in this migration.
    """
    now = residue() if now is None else now
    unexpected = {p: n for p, n in now.items() if p not in RESIDUE}
    moved = {p: (RESIDUE[p][0], n) for p, n in now.items()
             if p in RESIDUE and RESIDUE[p][0] != n}
    stale = sorted(set(RESIDUE) - set(now))
    return unexpected, moved, stale


def main(argv):
    now = residue()
    for path, n in sorted(now.items(), key=lambda kv: (-kv[1], kv[0])):
        why = RESIDUE.get(path, (0, "UNDECLARED"))[1]
        print(f"  {n:>5}  {path}\n         {why}")
    print(f"\n  {sum(now.values()):>5}  ours, every character declared above")
    for what, n in weighed().items():
        print(f"  {n:>5}  {what}")
    if "--check" in argv:
        unexpected, moved, stale = undeclared(now)
        for path, n in sorted(unexpected.items()):
            print(f"UNDECLARED  {path}: {n} Cyrillic, and no entry in RESIDUE")
        for path, (was, is_) in sorted(moved.items()):
            print(f"MOVED       {path}: declared {was}, found {is_} -- "
                  f"{RESIDUE[path][1]}")
        for path in stale:
            print(f"STALE       {path}: declared {RESIDUE[path][0]}, and there "
                  f"is none left")
        if unexpected or moved or stale:
            return 1
        print(f"lock holds: {sum(now.values())} Cyrillic in {len(RESIDUE)} "
              f"files, every one declared")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
