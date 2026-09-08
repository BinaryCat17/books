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
from booksmith.core import schema


def test_every_declared_key_is_present_in_the_data():
    """The guard itself. Empty list, or the guard has caught a drift."""
    bad = schema.below_floor()
    lines = [f"{f}: {k} floor {n}, found {got}" for f, k, n, got in bad]
    assert not bad, "declared keys missing from the data on disk:\n" + "\n".join(lines)


# WHAT `reading_order` WAS CALLED BEFORE THE RENAME, spelt out here.
#
# IT USED TO BE LOOKED UP IN `tools/keymap.json`, 562 entries and 25 779
# bytes, and the reason given was that typing the string "would put a
# permanent floor under this file that the translation can never remove" --
# a floor under `tree/cyr.py`, the Cyrillic ratchet. That ratchet is deleted,
# so the cost of typing it is now zero and the file was kept alive by an
# argument that had already expired. Nobody re-read the argument, which is
# the failure this project keeps finding: a thing survives because the
# sentence next to it still sounds right.
#
# The map itself is not lost -- it is in git, attached to the migration that
# used it -- and it was read by this one line and nothing else in the tree.
WAS_CALLED = {"reading_order": "порядок чтения"}


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
    was = WAS_CALLED["reading_order"]
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
        src += open(os.path.join(support.SRC, "processing", "assemble", name), encoding="utf-8").read()
    found = {a for a in re.findall(r'data-[\wЀ-ӿ-]+', src)}
    declared = set(schema.HTML_ATTRS)
    assert found == declared, (
        f"code emits {sorted(found - declared)} that are not declared; "
        f"declaration names {sorted(declared - found)} the code never writes")


def _emitted_text(rel):
    """Every string the code BUILDS, read from the syntax tree.

    NOT A REGEXP OVER THE FILE, and that took three bypasses to learn. The
    text version stripped triple-quoted blocks as prose, so a template inside
    one was invisible; it could not see `'<div ' 'class' '="x">'`, where the
    text `class=` does not occur in the source at all; and it read only the
    top-level `.py` of `doc/`, while `doc/mathjax/` is already a subpackage.

    The parser joins adjacent literals for us, so the split form arrives
    whole. An f-string comes back as its literal parts with a marker where a
    value goes, which is what makes `class="{cls}"` visible AS an unreadable
    class rather than as nothing at all. Docstrings are dropped -- prose, not
    emission.
    """
    tree = ast.parse(open(rel, encoding="utf-8").read())
    docs = set()
    for n in ast.walk(tree):
        if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                          ast.ClassDef)) and n.body:
            first = n.body[0]
            if (isinstance(first, ast.Expr)
                    and isinstance(first.value, ast.Constant)
                    and isinstance(first.value.value, str)):
                docs.add(id(first.value))
    out = []
    for n in ast.walk(tree):
        if (isinstance(n, ast.Constant) and isinstance(n.value, str)
                and id(n) not in docs):
            out.append(n.value)
        elif isinstance(n, ast.JoinedStr):
            out.append("".join(
                q.value if isinstance(q, ast.Constant)
                and isinstance(q.value, str) else "\x00"
                for q in n.values))
    return out


def _doc_sources():
    """Every `.py` under `doc/`, at any depth. `doc/mathjax/` is a package."""
    out = []
    for root, _, files in os.walk(os.path.join(support.SRC, "processing", "assemble")):
        out += [os.path.join(root, f) for f in sorted(files)
                if f.endswith(".py")]
    return out



def test_the_code_emits_exactly_the_declared_html_classes():
    """The same pairing for the CLASS names, which nothing guarded at all.

    `HTML_CLASSES` was declared and read by nobody -- and it had gone stale
    exactly as the comment above it warns: it named the pre-migration Russian
    word while `assemble/html.py` was emitting `sheet`. The one name in the book
    format that no check watched is the one that drifted, which is the whole
    argument for declaring it in the first place.

    MathJax writes classes of its own into the same file, so the CODE is the
    side compared here -- `books html` emits exactly one, and the built book
    is checked for the same name below.

    AND EVERY `class=` IS ACCOUNTED FOR, not only the ones a regexp can read.
    A pattern for `class="literal"` misses a single-quoted attribute, an
    f-string hole, a concatenation, a `%s`, a `.format`, an unquoted value and
    a split literal -- eight forms, each of which would have left this check
    green over an undeclared class. It cannot parse them, so it REFUSES to
    judge them: any `class=` it cannot read as a plain declared literal fails
    and says so, which is the difference between "checked" and "did not look".
    The whole `doc/` package is read, not three files of it.
    """
    plain = re.compile(r'class="([\wЀ-ӿ-]+)"')
    found, unreadable = set(), []
    for rel in _doc_sources():
        for text in _emitted_text(rel):
            for hit in re.finditer(r"class\s*=", text):
                tail = text[hit.start():]
                m = plain.match(tail)
                if m:
                    found.add(m.group(1))
                else:
                    unreadable.append(f"{os.path.basename(rel)}: {tail[:44]!r}")
    declared = set(schema.HTML_CLASSES)
    assert found == declared, (
        f"code emits classes {sorted(found - declared)} that are not "
        f"declared; declaration names {sorted(declared - found)} the code "
        f"never writes")
    assert not unreadable, (
        f"these `class=` are not a plain declared literal: {unreadable}. An "
        f"f-string hole, a concatenation, a `%s` or two classes in one "
        f"attribute -- this check cannot read them, and will not claim to "
        f"have checked them")


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
    # The last two are crops of a book, cut by `books crop` on a bench where
    # the bench directory is not itself closed (annopage, annopage-lite, hard,
    # hard36). They were hidden by nothing at all: the two patterns standing
    # here named `books feed`'s directories, and stayed after the command was
    # deleted while the new one was named nowhere.
    must_hide = ("raw/", "processed/", "runs/", ".env",
                 "bench/annopage/detect.crop/", "bench/hard/detect.crop/")
    r = subprocess.run(["git", "check-ignore", "-v", *must_hide],
                       cwd=root, capture_output=True, text=True)
    hidden = {ln.rsplit("\t", 1)[-1] for ln in r.stdout.splitlines() if ln}
    missing = sorted(set(must_hide) - hidden)
    assert not missing, (
        f"git no longer ignores {missing} -- .gitignore was edited and "
        "something that must never be committed is now exposed")

    # THE OTHER DIRECTION, and it is the one that bites quietly. A tracked
    # file falling UNDER an ignore is invisible to `git status`: the rename
    # succeeds, the index keeps it, and the next clone is missing it. The
    # results are the evidence for every number in METRICS.md and were
    # ignored until the prose that held those numbers was deleted.
    #
    # `--no-index` IS THE WHOLE CHECK. Without it `git check-ignore` consults
    # the index and answers about TRACKED paths by never reporting them --
    # and every path below is tracked, which is what "must keep" means. So
    # this half could not fail, whatever `.gitignore` said, and it did not:
    # moving the runs under a label put `bench/*/detect/*/pages/` over the
    # dots-ocr pages and 636 tracked, PAID files went ignored underneath a
    # green check. `git ls-files -i -c` printed all 636 the moment it was
    # asked. The mutation certifying this built its tree WITHOUT `git add`,
    # so it exercised the one condition the real tree does not have.
    must_keep = ("results/slovar-PP-DocLayoutV2.json",
                 "tests/expected/help.txt",
                 "bench/annopage/detect/PP-DocLayoutV2/run.json",
                 "bench/annopage-lite/detect/dots-ocr/pages/0000.json")
    r = subprocess.run(["git", "check-ignore", "--no-index", *must_keep],
                       cwd=root, capture_output=True, text=True)
    hidden = [ln for ln in r.stdout.splitlines() if ln.strip()]
    assert not hidden, (
        f"git now IGNORES {hidden}, and these must travel with the tree: a "
        f"result is the evidence for a published number, and a snapshot says "
        f"which knobs produced one")

    # AND THE SAME QUESTION ASKED OF THE INDEX ITSELF, which is the only one
    # that sees a file already tracked AND already ignored. `--no-index`
    # above answers about the four paths named; this answers about all of
    # them, including the ones nobody thought to name.
    r = subprocess.run(["git", "ls-files", "-i", "-c", "--exclude-standard"],
                       cwd=root, capture_output=True, text=True)
    both = [ln for ln in r.stdout.splitlines() if ln.strip()]
    assert not both, (
        f"{len(both)} files are TRACKED and IGNORED at once, starting with "
        f"{both[0]}. `git status` will never mention them; the next "
        f"regenerate-and-add drops them and the clone after that is missing "
        f"data with no message anywhere")


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
    src = open(os.path.join(support.SRC, "remote", "image.py"),
               encoding="utf-8").read()
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
    tree = support.tree("processing/layout/detect.py")
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


def test_no_cyrillic_key_survives_where_the_map_says_none_does():
    """The claim, measured -- because the tool that measured it was deleted.

    `tools/keymap_check.py` walked `bench/`, `processed/` and `runs/` looking
    for Cyrillic keys; it went when the key migration finished, and the map
    then acquired the sentence "no Cyrillic key survives in any json of
    bench/, processed/ or runs/". That sentence was FALSE --
    `runs/ledger.jsonl` holds 74 of them -- and nothing was left to say so.
    Delete the code, keep the measurement: this is the measurement.

    `runs/ledger.jsonl` is the ONE declared exception and is asserted to stay
    one: it is the journal of the runs that were paid for, append-only, and
    rewriting a journal after the fact destroys the one thing a journal is
    for. So the check fails in both directions -- a Cyrillic key appearing
    anywhere else, and the exception quietly curing itself, which would mean
    the journal had been rewritten.
    """
    import glob
    import json
    import re
    CYR = re.compile("[Ѐ-ӿԀ-ԯ]")
    # THE ROOT COMES FROM `schema`, not from `support.SRC`, so the mutation
    # battery can point this walk at a doctored tree and watch it go red. A
    # check that can only ever read one directory cannot be proved to fail.
    root = schema.ROOT

    def keys(o, out):
        if isinstance(o, dict):
            for k, v in o.items():
                if CYR.search(str(k)):
                    out.add(k)
                keys(v, out)
        elif isinstance(o, list):
            for v in o:
                keys(v, out)

    bad, seen, unreadable = {}, 0, []
    for pat in ("bench/**/*.json", "processed/**/*.json", "runs/*.jsonl"):
        for f in glob.glob(os.path.join(root, pat), recursive=True):
            found = set()
            try:
                with open(f, encoding="utf-8") as fh:
                    if f.endswith(".jsonl"):
                        for line in fh:
                            if line.strip():
                                keys(json.loads(line), found)
                    else:
                        keys(json.load(fh), found)
            except (OSError, ValueError) as e:
                # A FILE THAT COULD NOT BE READ IS NOT A FILE WITH NO CYRILLIC
                # IN IT. `continue` was silent here, so `{"стр": 3,,}` --
                # unparseable, Cyrillic key in plain sight -- passed as
                # clean. The project's own rule: zero from a check and zero
                # from not understanding are different zeros.
                unreadable.append(f"{os.path.relpath(f, root)}: {e}")
                continue
            seen += 1
            if found:
                bad[os.path.relpath(f, root)] = len(found)

    # A DEAD GLOB IS A SILENT ZERO, and this walk had no floor while every
    # sibling in this file has one. Point `schema.ROOT` at an empty directory
    # and the check went green having opened nothing -- measured, and the
    # same green it reports over 2670 tracked json. The floor is deliberately
    # far below what is on disk: it has to survive a clone, where the six
    # synthetic books and all of `processed/` are behind .gitignore.
    assert seen > 1500, (
        f"only {seen} json were read under {root} -- this check is measuring "
        f"nothing. Either the three globs stopped matching or the tree is not "
        f"where schema.ROOT points.")
    assert not unreadable, (
        f"{len(unreadable)} tracked json could not be parsed, so nothing is "
        f"known about the keys in them: {unreadable[:3]}")

    LEDGER = os.path.join("runs", "ledger.jsonl")
    others = {k: v for k, v in bad.items() if k != LEDGER}
    assert not others, (
        f"Cyrillic keys where the map says there are none: {others}. The key "
        f"migration is finished and its tools are deleted; a key in Russian "
        f"here means data written by code that predates it, or a rename that "
        f"went backwards.")
    # THE EXEMPTION HALF ONLY RUNS WHERE THE JOURNAL IS, and `runs/` is in
    # .gitignore -- asserted two checks above. So on every fresh clone and on
    # any machine that has not rented a card, this half silently did not run
    # while the docstring claimed the check "fails in both directions". A
    # skip with a reason is the difference between "not applicable here" and
    # "checked and fine", and this file skips with a reason twice already.
    if not os.path.isfile(os.path.join(root, LEDGER)):
        support.skip(
            f"{LEDGER} is not here -- `runs/` is gitignored, so the "
            f"append-only half of this check has nothing to ask")
    assert bad.get(LEDGER), (
        f"{LEDGER} no longer holds a Cyrillic key. It is the journal of "
        f"the runs that were PAID FOR and is append-only -- if its old "
        f"lines are English now, the journal was rewritten after the "
        f"fact, which destroys the one thing a journal is for. If it was "
        f"rewritten on purpose, delete this half of the check and the "
        f"exception in CLAUDE.md with it.")


def test_every_book_directory_is_in_the_declared_shape():
    """"Not a single outdated file" as a property, not a tidy-up.

    `bench/` had drifted into four kinds of thing under one name: books, the
    acceptance snapshots, the measurements, and three loose pdfs. Beside them
    1369 files from a build three weeks old that `docs/plan.md` had already
    condemned in writing, one overlay under two names, and one detect run
    split across two sibling directories no command knew about. Nothing was
    caught, because nothing said what a book directory IS.

    `booksmith.tree.layout` says it. This asks.
    """
    # THROUGH THE PACKAGE, so the battery's swapped module reaches this: a
    # `from ... import layout` bound at import time would keep the real one
    # and the mutation would certify nothing.
    from booksmith import tree
    bad = tree.layout.strays()
    layout = tree.layout
    assert not bad, (
        "paths that are not in the declared shape of a book directory:\n"
        + "\n".join(f"  {p}: {why}" for p, why in sorted(bad.items())))
    assert len(layout.books()) >= 10, (
        f"only {len(layout.books())} book directories found -- the walk broke")
