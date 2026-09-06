"""The names the code walks by must exist in the data on disk, in quantity.

THE HOLE THIS FILLS. Exactly one of the other 243 checks opens a file under
`bench/`, and it reads two ASCII fields. The rest run on fixtures built by the
code under test, so the suite cannot see the code and the data drifting apart.
Every rename in this project fails through that hole, and it fails quietly:
measured, a rename of `порядок чтения` in the code alone left the runner at
243/242/0 and the mutation battery at 218/218, both byte-identical to the
baseline, while the reading-order report went to "не объявлено" on every page
of every book.

WHY THE NAME COMES FROM CODE AND THE NUMBER FROM DISK. A guard that reads both
from the code travels with the code. That was not a guess -- it was built and
run: with the key renamed in 20 source files, and again with 1228 keys renamed
across 628 data files, a "does the code tell the three cases apart" check was
green both times. It had to be, because both its halves moved together. Split
the halves and both directions turn red:

    code renamed, data untouched -> declared name missing from disk
    data renamed, code untouched -> declared name below its floor

`booksmith.schema` holds the names and the floors. When step 4 of the
translation renames the keys in the code, this check goes red until the data is
migrated too -- and that is the point of it, not a defect in it.
"""
import collections
import glob
import json
import os
import re

import support
from booksmith import schema


def test_every_declared_key_is_present_in_the_data():
    """The guard itself. Empty list, or the guard has caught a drift."""
    bad = schema.below_floor()
    lines = [f"{f}: {k} floor {n}, found {got}" for f, k, n, got in bad]
    assert not bad, "declared keys missing from the data on disk:\n" + "\n".join(lines)


def test_the_guard_can_fail_when_the_code_renames():
    """Direction one, proved rather than asserted.

    A copy of the declaration with one key renamed must be reported as absent.
    If this passes silently, the guard has stopped reading the disk.
    """
    fmt = [f for f in schema.FORMATS if f.name == "dots_pages"][0]
    seen = schema.measure()["dots_pages"]
    assert seen.get("reading_order", 0) >= fmt.floors["reading_order"], (
        "the declared name is not in the data: the code renamed, the data "
        "did not")
    assert seen.get("порядок чтения", 0) == 0, (
        "the name from before the migration is still on disk in "
        f"{seen.get('порядок чтения', 0)} places: the rename did not finish")


def test_the_guard_can_fail_when_the_data_renames():
    """Direction two, on a real file rather than a fixture.

    Reads one tracked page, drops the key wherever it sits, and checks the
    counter notices. Nothing is written: the drift is simulated in memory,
    because a guard that has to damage the tree to prove itself never gets run.
    """
    fmt = [f for f in schema.FORMATS if f.name == "truth"][0]
    files = fmt.files()
    assert files, "no truth files on disk -- the guard is measuring nothing"
    page = json.load(open(files[0], encoding="utf-8"))
    before = collections.Counter()
    schema._walk(page, before)
    assert before["text_marked"] > 0, (
        f"{files[0]} does not carry the key the floor is built on")
    after = collections.Counter()
    schema._walk(_drop(page, "text_marked"), after)
    assert after["text_marked"] < before["text_marked"], (
        "dropping the key did not change the count -- the walk is not "
        "descending into the object that holds it")


def _drop(obj, key):
    """The same object without `key`, at any depth. Copies, never mutates."""
    if isinstance(obj, dict):
        return {k: _drop(v, key) for k, v in obj.items() if k != key}
    if isinstance(obj, list):
        return [_drop(v, key) for v in obj]
    return obj


def test_the_floors_are_not_all_zero():
    """A floor of zero is a guard that cannot speak. Measured, not declared."""
    floors = [n for f in schema.FORMATS for n in f.floors.values()]
    assert floors, "no floors declared at all"
    assert min(floors) > 0, "a floor of zero guards nothing"
    assert sum(floors) > 10000, f"floors sum to {sum(floors)} -- too thin to trust"


def test_the_declaration_reaches_the_files_it_names():
    """Every format must actually match files; a dead glob is a silent zero.

    This is the one that would have caught the first draft of the declaration:
    `bench/*/dots*/*.json` matched 636 of the 1272 tracked dots pages, because
    half of them live one directory deeper. Half a floor is worse than none --
    it looks measured.
    """
    for fmt in schema.FORMATS:
        files = fmt.files()
        assert files, f"{fmt.name}: pattern {fmt.pattern} matches nothing"
        if fmt.name == "dots_pages":
            assert len(files) >= 1272, (
                f"{fmt.name}: {len(files)} files, expected at least 1272 "
                "tracked -- the pattern is missing a directory level")


def test_the_code_emits_exactly_the_declared_html_attributes():
    """The book's own format, declared once and checked against the code.

    `books html` writes these names and `books apply` parses the book back by
    them. Renaming one in the code passed the runner, the battery, the ratchet
    and all five acceptance reports -- and left the only real book on disk,
    412 swaps and $0.545 of reading, unreadable by the code that made it.
    """
    src = ""
    for name in ("html.py", "apply.py"):
        src += open(os.path.join(support.SRC, "doc", name), encoding="utf-8").read()
    found = {a for a in re.findall(r'data-[\wЀ-ӿ-]+', src)}
    declared = set(schema.HTML_ATTRS)
    assert found == declared, (
        f"code emits {sorted(found - declared)} that are not declared; "
        f"declaration names {sorted(declared - found)} the code never writes")


def test_the_built_book_carries_the_declared_attributes():
    """The other half: what is on disk must be what the code speaks.

    Skipped with a reason when no book is built -- `processed/` is not in git,
    so a fresh clone has nothing to compare. That is a skip, never a pass.
    """
    books = sorted(glob.glob(os.path.join(
        os.path.dirname(os.path.dirname(support.SRC)), "processed", "*", "book.html")))
    if not books:
        support.skip("собранной книги нет в processed/ — сравнивать не с чем")
    text = open(books[-1], encoding="utf-8").read()
    absent = [a for a in schema.HTML_CORE if a not in text]
    assert not absent, (
        f"{books[-1]} does not carry {absent} -- the builder and the book it "
        "built have drifted apart, and `books apply` will not find its blocks")


def test_the_things_that_must_never_be_committed_are_ignored():
    """`.gitignore` is the one file where a bad edit exposes gigabytes.

    Its own first three lines say why: a `#` at the tail of a pattern is part
    of the pattern to git, so `raw/  # 9.7 GB` stops hiding `raw/` -- silently.
    Behind these four entries sit 9.7 GB of scans, 201 MB of built books and
    paid reading, the rent journal with live vast.ai machine ids, and the
    secrets file.

    Checked by asking git, not by reading the file: a pattern can be correct
    and still be overridden by a later line.
    """
    import subprocess
    root = os.path.dirname(os.path.dirname(support.SRC))
    must_hide = ("raw/", "processed/", "runs/", ".env")
    r = subprocess.run(["git", "check-ignore", "-v", *must_hide],
                       cwd=root, capture_output=True, text=True)
    hidden = {ln.rsplit("\t", 1)[-1] for ln in r.stdout.splitlines() if ln}
    missing = sorted(set(must_hide) - hidden)
    assert not missing, (
        f"git no longer ignores {missing} -- .gitignore was edited and "
        "something that must never be committed is now exposed")
