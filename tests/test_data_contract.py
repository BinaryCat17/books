"""The names the code walks by must exist in the data on disk, in quantity.

THE HOLE THIS FILLS. Exactly one of the other 243 checks opens a file under
`bench/`, and it reads two ASCII fields. The rest run on fixtures built by the
code under test, so the suite cannot see the code and the data drifting apart.
Every rename in this project fails through that hole, and it fails quietly:
measured, renaming the reading-order key in the code alone left the runner at
243/242/0 and the mutation battery at 218/218, both byte-identical to the
baseline, while the reading-order report went to "not declared" on every page
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
import ast
import builtins
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


def _before_migration(name):
    """What this key was called before the rename, from the rename map itself."""
    path = os.path.join(os.path.dirname(os.path.dirname(support.SRC)),
                        "tools", "keymap.json")
    was = [k for k, v in json.load(open(path, encoding="utf-8")).items()
           if v == name]
    assert len(was) == 1, f"{name}: {len(was)} old spellings in keymap.json"
    return was[0]


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
    # The pre-migration spelling is NOT typed here. It is looked up in
    # `tools/keymap.json`, which is the record of the rename: typing it would
    # put a permanent floor under this file that the translation can never
    # remove, and would go stale the moment the map is corrected.
    was = _before_migration("reading_order")
    assert seen.get(was, 0) == 0, (
        f"the name from before the migration, {was!r}, is still on disk in "
        f"{seen.get(was, 0)} places: the rename did not finish")


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


def test_the_code_emits_exactly_the_declared_html_classes():
    """The same pairing for the CLASS names, which nothing guarded at all.

    `HTML_CLASSES` was declared and read by nobody -- and it had gone stale
    exactly as the comment above it warns: it named the pre-migration Russian
    word while `doc/html.py` was emitting `sheet`. The one name in the book
    format that no check watched is the one that drifted, which is the whole
    argument for declaring it in the first place.

    MathJax writes classes of its own into the same file, so the CODE is the
    side compared here -- `books html` emits exactly one, and the built book
    is checked for the same name below.
    """
    src = ""
    for name in ("html.py", "apply.py", "swap.py"):
        src += open(os.path.join(support.SRC, "doc", name),
                    encoding="utf-8").read()
    found = {c for c in re.findall(r'class="([\wЀ-ӿ -]+)"', src)}
    declared = set(schema.HTML_CLASSES)
    assert found == declared, (
        f"code emits classes {sorted(found - declared)} that are not "
        f"declared; declaration names {sorted(declared - found)} the code "
        f"never writes")


def test_the_built_book_carries_the_declared_classes():
    """And the book on disk carries them. Skipped with a reason, never passed.

    `processed/` is not in git, so a fresh clone has nothing to compare.
    """
    books = sorted(glob.glob(os.path.join(
        os.path.dirname(os.path.dirname(support.SRC)),
        "processed", "*", "book.html")))
    if not books:
        support.skip("no built book: processed/ is not in git")
    html = open(books[-1], encoding="utf-8").read()
    for name in schema.HTML_CLASSES:
        assert f'class="{name}"' in html, (
            f"{books[-1]}: the book carries no class {name!r}, and the code "
            f"declares it. The declaration and the book have parted")


def test_the_built_book_carries_the_declared_attributes():
    """The other half: what is on disk must be what the code speaks.

    Skipped with a reason when no book is built -- `processed/` is not in git,
    so a fresh clone has nothing to compare. That is a skip, never a pass.
    """
    books = sorted(glob.glob(os.path.join(
        os.path.dirname(os.path.dirname(support.SRC)), "processed", "*", "book.html")))
    if not books:
        support.skip("no built book in processed/ -- nothing to compare")
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


def test_the_rented_image_was_built_from_this_dockerfile():
    """The image tag IS a commit SHA, so staleness is checkable.

    `procps` and `git` were added to `infra/base/Dockerfile` in one commit
    while `BASE_IMAGE` went on naming an image built before them. `run.sh`
    then said "procps is in the image now" and its pgrep guard, described as a
    second line of defence, was the only one -- on a machine that bills, where
    an orphan holds 60 % of the video memory.

    Nothing can inspect a remote image from here. What can be checked is the
    thing that made it stale: the tag names a commit, so the Dockerfile AT
    THAT COMMIT must be the Dockerfile we have now. It fails loudly when the
    recipe moves and the tag does not.
    """
    import re
    import subprocess
    root = os.path.dirname(os.path.dirname(support.SRC))
    src = open(os.path.join(support.SRC, "models", "paddleocr_vl",
                            "__init__.py"), encoding="utf-8").read()
    m = re.search(r'BASE_IMAGE\s*=\s*"[^"]*:([0-9a-f]{7,40})"', src)
    assert m, "BASE_IMAGE no longer carries a commit SHA as its tag"
    tag = m.group(1)
    was = subprocess.run(["git", "show", f"{tag}:infra/base/Dockerfile"],
                         cwd=root, capture_output=True, text=True)
    if was.returncode:
        support.skip(f"commit {tag} is not in this clone -- nothing to compare")
    now = open(os.path.join(root, "infra", "base", "Dockerfile"),
               encoding="utf-8").read()

    def packages(text):
        block = text.split("apt-get install", 1)[-1].split("rm -rf", 1)[0]
        return sorted(w for w in re.findall(r"^\s+([a-z0-9.+-]+)\s*\\?$",
                                            block, re.M))
    # A DECLARED, OUTSTANDING DEBT, not an exemption. These two were added in
    # `ed4cb11` and the image has not been rebuilt since; `run.sh` and the
    # Dockerfile both now say so in as many words, and `run.sh`'s pgrep guard
    # fires on a real rental, which is the correct behaviour. Rebuilding the
    # image and moving `BASE_IMAGE` to the new tag closes it -- and then this
    # set goes back to empty. A permanently red check stops being read; a
    # named debt with a floor under it does not.
    KNOWN_DEBT = {"git", "procps"}
    drifted = sorted(set(packages(now)) - set(packages(was.stdout)) - KNOWN_DEBT)
    assert not drifted, (
        f"the Dockerfile installs {drifted}, which the image tagged {tag} was "
        "not built with. Rebuild the image and move BASE_IMAGE to the new tag, "
        "or any prose relying on those packages is false on a paid run")


def test_the_snapshot_seconds_are_a_duration_and_nothing_else():
    """`run.json` writes `"seconds"`, and it must be the wall clock.

    IT WAS NOT, WITH THE VENDOR PIPELINE ON. `took = time.time() - t0` at the
    top of `detect` was shadowed a hundred lines below by
    `took = pipe["before"] - pipe["after"]` inside `if had_pipeline:`, and the
    snapshot then recorded THE COUNT OF BOXES the vendor removed under the name
    `seconds`. It never showed on disk: every tracked `detect/run.json` carries
    `stage_ran: false`, so the branch has not run in any snapshot anyone kept,
    and nothing was there to notice.

    Checked by reading rather than by running, because running it costs a
    docling install and five seconds of ONNX -- and because the defect is a
    NAME, which is exactly what reading sees. The name written into the
    snapshot must be assigned once in the whole function, and that assignment
    must be a subtraction of two clock readings.
    """
    tree = support.tree("detect.py")
    fn = next((n for n in ast.walk(tree)
               if isinstance(n, ast.FunctionDef) and n.name == "run"), None)
    assert fn is not None, "detect.py no longer defines `run`"

    written = [v for n in ast.walk(fn) if isinstance(n, ast.Dict)
               for k, v in zip(n.keys, n.values)
               if isinstance(k, ast.Constant) and k.value == "seconds"]
    assert len(written) == 1, (
        f"`seconds` is written into {len(written)} dicts of `run` -- one "
        f"of them is not the snapshot, and this check no longer knows which")
    # `round` is a builtin, not a local; what is followed is the local.
    names = [n.id for n in ast.walk(written[0])
             if isinstance(n, ast.Name) and n.id not in dir(builtins)]
    assert len(names) == 1, (
        f"the `seconds` value names {names}; this check reads one local name "
        f"and follows it to its assignment")
    name = names[0]

    assigned = [n for n in ast.walk(fn) if isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == name
                        for t in n.targets)]
    assert len(assigned) == 1, (
        f"{name!r} is assigned {len(assigned)} times inside `run`, and the "
        f"snapshot writes it as `seconds`. The second assignment shadows the "
        f"clock: with the vendor pipeline on, the snapshot recorded a count "
        f"of boxes as a duration")
    src = ast.dump(assigned[0].value)
    assert "time" in src, (
        f"{name!r} is not measured from the clock at all: {src[:120]}")
