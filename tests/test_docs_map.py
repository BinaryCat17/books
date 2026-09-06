"""The map must name what exists, and point at files that are there.

WHY THIS EXISTS. `README.md` once held a second copy of the code map, and
within a month it had drifted from the tree by eight modules and four
commands: `annopage.py`, `fitness.py`, `text.py`, `subset.py`, two adapters,
`dots_ocr/` and the whole `tests/` directory were missing from it. A second
copy drifts SILENTLY -- people read it and decide by it.

The copy was removed and `CLAUDE.md` was left as the only map. That fixes the
duplication and not the drift: a single map goes stale just as quietly. So the
map is now checked against the tree.

WHAT IS CHECKED, and why only this. Two things a machine can judge without an
opinion: every command the CLI declares is named in the map, and every file
the map points at exists. Whether the prose is TRUE is not checkable here --
that is what the measurements in `docs/models.md` and the batteries are for.
"""
import os
import re

import support
from booksmith import schema

ROOT = os.path.dirname(os.path.dirname(support.SRC))


def _map_text():
    return open(schema.DOC_MAP, encoding="utf-8").read()


def test_every_command_the_cli_declares_is_named_in_the_map():
    """A command absent from the map is a command nobody finds."""
    src = open(os.path.join(support.SRC, "cli.py"), encoding="utf-8").read()
    declared = set(re.findall(r'add_parser\("([a-z-]+)"', src))
    assert declared, "no subcommands found in cli.py -- the search broke"
    text = _map_text()
    missing = sorted(c for c in declared if f"books {c}" not in text)
    assert not missing, f"the map does not name: {missing}"


def test_the_map_names_no_command_that_does_not_exist():
    """The other direction: a map that offers a command the CLI lost."""
    src = open(os.path.join(support.SRC, "cli.py"), encoding="utf-8").read()
    declared = set(re.findall(r'add_parser\("([a-z-]+)"', src))
    named = set(re.findall(r'^books ([a-z]+)', _map_text(), re.M))
    ghosts = sorted(named - declared)
    assert not ghosts, f"the map offers commands the CLI does not have: {ghosts}"


def test_every_file_the_map_points_at_exists():
    """A pointer to a file that is gone sends the reader nowhere.

    Only paths that look like real files are taken -- a backticked word with a
    slash or a known extension. Prose in backticks (`content`, `meta`) is not
    a path and is not chased.
    """
    # Only paths anchored at a top-level directory of the repository are
    # chased. `assets/run.json` and `source/` name places INSIDE a built book
    # directory, which is not a fixed path; chasing those would make the check
    # fire on correct prose, and a check that cries wolf gets switched off.
    TOPS = ("src/", "docs/", "tests/", "tools/", "bench/", "infra/", ".github/")
    text = _map_text()
    cited = set()
    for token in re.findall(r'`([^`\s]+)`', text):
        token = token.rstrip(".,;:")
        if token.startswith(TOPS) or (token.endswith(".md") and "/" not in token):
            cited.add(token)
    gone = sorted(p for p in cited
                  if "*" not in p and "<" not in p
                  and not os.path.exists(os.path.join(ROOT, p)))
    assert not gone, f"the map points at files that do not exist: {gone}"


def test_the_map_does_not_grow_back_into_a_second_copy():
    """It is a map, not a third place for measurements.

    The rule it broke: `698` lived here twice, in `docs/contour-notes.md`
    three times and in the source six more, and the same held for `4435`,
    `1025` and `412`. Those belong in `docs/models.md` now, and a map that
    starts re-accumulating them is drifting again by construction.
    """
    text = _map_text()
    moved = ["698", "4435", "1025", "0.545"]
    back = [n for n in moved if n in text]
    assert not back, (
        f"measurements are back in the map: {back}. They live in "
        "docs/models.md; the map points, it does not measure.")
