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


def _offered(text, declared):
    """Which commands a list of `books ...` lines OFFERS, as whole names.

    BY WHOLE WORDS, NOT BY SUBSTRING, and that is the point of the function.
    Both directions used to ask `f"books {c}" not in text`, justified by "a
    prefix counts: `books bench all` names `books bench` too". It counts any
    other prefix as well: add `sub.add_parser("doc")` and leave it out of both
    lists, and both checks pass -- `books doc` is inside `books doctor`. The
    same hole stands under `app`/`apply`, `syn`/`synth`, `sub`/`subset`,
    `over`/`overlay`. So the names are parsed out, and a group is offered by
    the line that offers any of its subcommands -- that, and only that, is the
    prefix rule.
    """
    groups = {c.split()[0] for c in declared if " " in c}
    out = set()
    for first, second in re.findall(r"books ([a-z-]+)(?: ([a-z-]+))?", text):
        if first in groups and second:
            out.add(f"{first} {second}")
            out.add(first)
        else:
            out.add(first)
    return out


def _map_lines():
    """The `books ...` lines of the map, from the line start as it writes
    them."""
    return "\n".join(re.findall(r"^books .*$", _map_text(), re.M))


def test_every_command_the_cli_declares_is_named_in_the_map():
    """A command absent from the map is a command nobody finds."""
    src = open(os.path.join(support.SRC, "cli.py"), encoding="utf-8").read()
    declared = _declared(src)
    assert declared, "no subcommands found in cli.py -- the search broke"
    missing = sorted(declared - _offered(_map_lines(), declared))
    assert not missing, f"the map does not name: {missing}"


def test_the_map_names_no_command_that_does_not_exist():
    """The other direction: a map that offers a command the CLI lost."""
    src = open(os.path.join(support.SRC, "cli.py"), encoding="utf-8").read()
    declared = _declared(src)
    ghosts = sorted(_offered(_map_lines(), declared) - declared)
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


def test_every_command_the_cli_declares_is_in_the_cli_header():
    """A group is named by the line that names its subcommand: `books bench
    all` names `books bench` too. Nothing else counts as naming."""
    src = open(os.path.join(support.SRC, "cli.py"), encoding="utf-8").read()
    declared = _declared(src)
    assert declared, "no subcommands found in cli.py -- the search broke"
    missing = sorted(declared - _offered(_cli_table(), declared))
    assert not missing, f"the cli.py header does not name: {missing}"


def test_the_cli_header_offers_no_command_that_does_not_exist():
    src = open(os.path.join(support.SRC, "cli.py"), encoding="utf-8").read()
    declared = _declared(src)
    ghosts = sorted(_offered(_cli_table(), declared) - declared)
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


def test_a_measurement_is_not_restated_in_a_second_document():
    """The rule CLAUDE.md opens with, counted at last.

    "One figure -- the artifacts V2 finds on the golden bench -- stood here
    twice, in the contour journal three times and in the source six more. A
    second copy drifts, and it drifts silently." That rule was guarded in one
    place only: four named numbers forbidden to return to the map. Between the
    documents themselves nothing counted.

    A ceiling, not a ban, and it counts COPIES: a figure in seven documents is
    six copies, not one duplicate, and a figure stated twice in ONE document
    is a copy too -- which is the case the map opens with, and which the first
    edition could not see because it read each document into a set. It may
    fall and never rise, and a fall that leaves the ceiling behind is red too,
    or the number stops pressing.
    """
    from booksmith.tree import figures
    d = figures.duplicates()
    n = figures.copies(d)
    assert n <= figures.CEILING, (
        f"{n} redundant copies of {len(d)} measurements, against a ceiling of "
        f"{figures.CEILING}. Point at the document that owns the number "
        f"instead of restating it.")
    assert n == figures.CEILING, (
        f"the ceiling is stale: {n} copies left and it says "
        f"{figures.CEILING}. Lower it in tree/figures.py -- a ratchet that "
        f"stops pressing is not a ratchet.")
    assert "METRICS.md" not in figures.documents(), (
        "the generated document is being counted: it is rendered afresh from "
        "the records and cannot drift from what it restates")


def test_the_generated_metrics_file_is_generated_and_current():
    """`METRICS.md` is rendered from `bench/results/*.json` and never edited.

    A number that lives in prose is free to drift from the run it describes --
    `tree/figures.py` counts what that cost this project. A number rendered
    from its record cannot. So the file is checked the only way a generated
    file can be: regenerate and compare.

    Skipped, not passed, when there are no results: on a fresh clone nothing
    has been measured and there is nothing to render. The file being ABSENT
    while results exist is a failure -- that is the state where the document
    and the runs have parted.
    """
    from booksmith.core.errors import Refusal
    from booksmith.datasets import report
    try:
        want = report.build(log=lambda *a: None)
    except Refusal as e:
        support.skip(f"nothing rendered: {str(e)[:80]}")
    path = report.OUT
    assert os.path.isfile(path), (
        f"{os.path.basename(path)} is missing while {report.RESULTS} holds "
        f"measurements: `books bench report` writes it")
    got = open(path, encoding="utf-8").read()
    assert got == want, (
        f"{os.path.basename(path)} is not what the records render to -- it "
        f"was edited by hand, or the measurements moved under it. Remake it: "
        f"`books bench report`")
