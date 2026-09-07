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
from booksmith.core import schema

ROOT = os.path.dirname(os.path.dirname(support.SRC))


def _map_text():
    return open(schema.DOC_MAP, encoding="utf-8").read()


def _declared(src):
    """Every command the CLI declares, nested ones as "group sub".

    A parser made by `sub.add_parser` is a top command; a parser made on any
    other subparsers object is nested under the top command whose
    `add_subparsers` made that object. Read in source order, which is how
    argparse builds it.
    """
    out, groups, last_top = set(), {}, None
    for m in re.finditer(r'(?:(\w+)\s*=\s*)?(\w+)\.add_parser\("([a-z-]+)"'
                         r'|(\w+)\s*=\s*(\w+)\.add_subparsers\(', src):
        var, on, name, subvar, parent = m.groups()
        if name is not None:
            if on == "sub":
                out.add(name)
                last_top = name
            elif on in groups:
                out.add(f"{groups[on]} {name}")
        elif subvar is not None and parent != "ap":
            groups[subvar] = last_top
    return out


def test_every_command_the_cli_declares_is_named_in_the_map():
    """A command absent from the map is a command nobody finds."""
    src = open(os.path.join(support.SRC, "cli.py"), encoding="utf-8").read()
    declared = _declared(src)
    assert declared, "no subcommands found in cli.py -- the search broke"
    text = _map_text()
    missing = sorted(c for c in declared if f"books {c}" not in text)
    assert not missing, f"the map does not name: {missing}"


def test_the_map_names_no_command_that_does_not_exist():
    """The other direction: a map that offers a command the CLI lost."""
    src = open(os.path.join(support.SRC, "cli.py"), encoding="utf-8").read()
    declared = _declared(src)
    groups = {c.split()[0] for c in declared if " " in c}
    named = set()
    for first, second in re.findall(r'^books ([a-z]+)(?: ([a-z]+))?', _map_text(), re.M):
        named.add(f"{first} {second}" if first in groups and second else first)
    ghosts = sorted(named - declared)
    assert not ghosts, f"the map offers commands the CLI does not have: {ghosts}"


# ---------------------------------------------------- the CLI's own header
# The map is not the only list of commands: `cli.py` opens with one too, and
# it is what `books --help` prints. It CLAIMED to be checked against
# `sub.add_parser` and was not -- so it went on offering `books feed` after
# the command was deleted, and never learned about `books bench all`. A list
# that says it is checked and is not is worse than one that says nothing.


def _cli_table():
    """The command table at the top of `cli.py`, verbatim.

    Only the indented `books ...` lines are taken, not the prose below them:
    the prose names deleted commands ON PURPOSE, saying what they were and
    why they went, and that is a record, not an offer.
    """
    src = open(os.path.join(support.SRC, "cli.py"), encoding="utf-8").read()
    doc = src.split('"""')[1]
    return "\n".join(l for l in doc.splitlines() if l.startswith("    books "))


def _cli_commands(declared):
    """What the table OFFERS, nested commands as "group sub"."""
    groups = {c.split()[0] for c in declared if " " in c}
    out = set()
    # `books bench all <run>` is one nested command, `books ls | books down
    # 12345 | books reap` is three; the two are the same shape to a regex, so
    # the nesting is decided by the groups the CLI actually declares.
    for first, second in re.findall(r"books ([a-z-]+)(?: ([a-z-]+))?",
                                    _cli_table()):
        out.add(f"{first} {second}" if first in groups and second else first)
    return out


def test_every_command_the_cli_declares_is_in_the_cli_header():
    """Named as a PREFIX counts: `books bench all` names `books bench` too --
    a group with one subcommand needs no line of its own."""
    src = open(os.path.join(support.SRC, "cli.py"), encoding="utf-8").read()
    declared = _declared(src)
    table = _cli_table()
    missing = sorted(c for c in declared if f"books {c}" not in table)
    assert not missing, f"the cli.py header does not name: {missing}"


def test_the_cli_header_offers_no_command_that_does_not_exist():
    src = open(os.path.join(support.SRC, "cli.py"), encoding="utf-8").read()
    declared = _declared(src)
    ghosts = sorted(_cli_commands(declared) - declared)
    assert not ghosts, (
        f"the cli.py header offers commands the CLI does not have: {ghosts}")


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
