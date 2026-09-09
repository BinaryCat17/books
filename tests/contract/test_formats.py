"""The names the code walks by must exist in the data on disk, in quantity.

The suite otherwise runs on fixtures built by the code under test, so it is
blind by construction to the code and the data on disk drifting apart -- and
that drift is the failure mode of every rename. Four renames would have been
silent: the reading-order key, the text-marked flag, the knob keys, the
out-of-scope list; the runner and the batteries stayed byte-identical while
whole lines left the reports and 350 excluded boxes were charged to a model.

The shape of the guard is what makes it work: the key NAME comes from the code
below, the COUNT comes off the disk. Both from one side and it travels with the
code; split, it goes red in both directions.

    code renamed, data untouched -> the declared name is missing from disk
    data renamed, code untouched -> the declared name is below its floor

The floors are measured, not guessed, and they are floors rather than exact
counts so that adding a bench does not redden them. They were counted on
TRACKED files only: `processed/` and the synthetic benches are absent from git,
and a guard that needs them cannot run on a fresh clone.
"""
import collections
import glob
import json
import os

import pytest

from booksmith.core.config import ROOT


class Format:
    """One on-disk format: where its files are, and what must be inside them.

    `floors` is `key -> smallest number of occurrences seen across every
    tracked file of this format`. A key present here and absent from the data
    is the loudest thing this file can say.
    """

    def __init__(self, name, pattern, floors):
        self.name = name
        self.pattern = pattern
        self.floors = floors

    def files(self, root=ROOT):
        return sorted(glob.glob(os.path.join(root, self.pattern),
                                recursive=True))


FORMATS = (
    # 1366 tracked pages: annopage, annopage-lite, hard, hard36. The six
    # synthetic benches are behind .gitignore, manifest apart.
    Format(
        "truth", "bench/*/truth/*.json",
        {"case": 1366, "book": 1366, "bucket": 2002, "category": 2002,
         "source_category": 3587, "out_of_scope": 1360,
         "objects_out_of_scope": 1359, "text_marked": 1359,
         "order_marked": 1324, "doubtful": 1359, "inexpressible": 1359,
         "file": 1359}),
    # `detect/dots-ocr/**` covers both halves on purpose: the parsed pages and
    # the card's raw output one directory deeper. A glob naming only the first
    # halves every floor here and takes `answer` -- what the paid run bought --
    # to zero. There is no home re-parser, so these cannot be regenerated.
    Format(
        "dots_pages", "bench/*/detect/dots-ocr/**/*.json",
        {"detector": 1272, "reading_order": 1272, "downscale": 1272,
         "pass_no": 1236, "prompt": 1236, "input_pixel_ceiling": 1236,
         "out_of_vram": 1236, "parse_error": 1236, "answer": 636}),
    # Three detect snapshots are tracked; `books replay --check` walks the path
    # ('knobs', <knob>, 'value').
    Format(
        "detect_run", "bench/*/detect/*/run.json",
        {"knobs": 3, "value": 72, "default": 72, "what": 72,
         "set_externally": 72, "name": 6, "prompts": 6, "by_label": 6,
         "when": 3, "raster": 3, "commit": 3, "source": 3, "args": 3}),
    # All thirteen bench manifests are tracked. `source` is the one key that
    # says WHICH file a truth directory and a run are about; a floor is only a
    # floor at the value it is measured at, and this one moved with the three
    # real scans becoming books of their own.
    Format(
        "manifest", "bench/*/manifest.json",
        {"book": 149, "value": 216, "default": 216, "what": 216,
         "debt": 216, "set_externally": 216, "page_no": 130, "chars": 99,
         "char_truth": 99, "blocks_with_text": 99, "cell_count": 99,
         "source": 13}),
    # `METRICS.md` is rendered from these and from nothing else, so they are
    # the evidence for every published number. The floors are 1 because a clone
    # may hold one file or fifty; what they guard is the NAMES. `kind` is
    # missing on purpose -- no TRACKED result carries it yet, and it is the
    # field that decides whether a run is published at all.
    Format(
        "results", "results/*.json",
        {"records": 1, "commit": 1, "when": 1, "metric": 1, "bench": 1,
         "run": 1, "scalars": 1, "params": 1, "value": 1}),
)

# THE BOOK IS A FORMAT TOO. `books html` writes these names and `books apply`
# parses the book back out with selectors over them, so renaming one in the
# code leaves every check green while the only book on disk carries the old
# names and can never be found again.
HTML_ATTRS = (
    "data-no-text", "data-kind", "data-inside", "data-image-share",
    "data-truncated", "data-repeat", "data-repeat-text", "data-empty",
    "data-role", "data-repeats-hidden", "data-sheet", "data-text",
    "data-furniture-only", "data-level", "data-table-shape",
    "data-placed-by", "data-label",
)
# The class names. Declared and then guarded by nothing, this line drifted
# exactly as predicted: it named the pre-migration word while the builder
# emitted `sheet`.
HTML_CLASSES = ("sheet",)
# The four EVERY built book must carry, whatever is on its pages: a page
# marker, a block role, a model label and a nesting level. The other thirteen
# are conditional and cannot be required of a particular book.
HTML_CORE = ("data-role", "data-label", "data-sheet", "data-level")

# What `reading_order` was called before the rename. It used to be looked up in
# a 562-entry key map kept alive for this one line; the map went with the
# migration that used it, and the string is typed here.
WAS_CALLED = {"reading_order": "порядок чтения"}

BUILDER = ("processing/assemble/html.py", "processing/assemble/apply.py")


def _walk(obj, counter):
    if isinstance(obj, dict):
        for k, v in obj.items():
            counter[k] += 1
            _walk(v, counter)
    elif isinstance(obj, list):
        for v in obj:
            _walk(v, counter)


def measure(root=ROOT):
    """format -> {key: occurrences} over the tracked files, right now."""
    out = {}
    for fmt in FORMATS:
        c = collections.Counter()
        for path in fmt.files(root):
            _walk(json.load(open(path, encoding="utf-8")), c)
        out[fmt.name] = c
    return out


def below_floor(root=ROOT):
    """[(format, key, floor, found)] -- empty means code and data agree."""
    bad = []
    seen = measure(root)
    for fmt in FORMATS:
        got = seen[fmt.name]
        for key, floor in sorted(fmt.floors.items()):
            if got.get(key, 0) < floor:
                bad.append((fmt.name, key, floor, got.get(key, 0)))
    return bad


def _drop(obj, key):
    """The same object without `key`, at any depth. Copies, never mutates."""
    if isinstance(obj, dict):
        return {k: _drop(v, key) for k, v in obj.items() if k != key}
    if isinstance(obj, list):
        return [_drop(v, key) for v in obj]
    return obj


def _books():
    return sorted(glob.glob(os.path.join(ROOT, "processed", "*", "book.html")))


def test_every_declared_key_is_present_in_the_data():
    """The guard itself. Empty list, or it has caught a drift."""
    bad = below_floor()
    lines = [f"{f}: {k} floor {n}, found {got}" for f, k, n, got in bad]
    assert not bad, "declared keys missing from the data on disk:\n" + "\n".join(lines)


def test_the_guard_can_fail_when_the_code_renames():
    """Direction one, proved rather than asserted: a declaration with one key
    renamed must read as absent from the disk."""
    fmt = [f for f in FORMATS if f.name == "dots_pages"][0]
    seen = measure()["dots_pages"]
    assert seen.get("reading_order", 0) >= fmt.floors["reading_order"], (
        "the declared name is not in the data: the code renamed, the data "
        "did not")
    was = WAS_CALLED["reading_order"]
    assert seen.get(was, 0) == 0, (
        f"the name from before the migration, {was!r}, is still on disk in "
        f"{seen.get(was, 0)} places: the rename did not finish")


def test_the_guard_can_fail_when_the_data_renames():
    """Direction two, on a real file. Nothing is written: a guard that has to
    damage the tree to prove itself never gets run."""
    fmt = [f for f in FORMATS if f.name == "truth"][0]
    files = fmt.files()
    assert files, "no truth files on disk -- the guard is measuring nothing"
    page = json.load(open(files[0], encoding="utf-8"))
    before = collections.Counter()
    _walk(page, before)
    assert before["text_marked"] > 0, (
        f"{files[0]} does not carry the key the floor is built on")
    after = collections.Counter()
    _walk(_drop(page, "text_marked"), after)
    assert after["text_marked"] < before["text_marked"], (
        "dropping the key did not change the count -- the walk is not "
        "descending into the object that holds it")


def test_the_floors_are_not_all_zero():
    """A floor of zero is a guard that cannot speak."""
    floors = [n for f in FORMATS for n in f.floors.values()]
    assert floors, "no floors declared at all"
    assert min(floors) > 0, "a floor of zero guards nothing"
    assert sum(floors) > 10000, f"floors sum to {sum(floors)} -- too thin to trust"


def test_the_declaration_reaches_the_files_it_names():
    """A dead glob is a silent zero: the first draft matched half the tracked
    dots pages, because half of them live one directory deeper, and half a
    floor is worse than none -- it looks measured."""
    for fmt in FORMATS:
        files = fmt.files()
        assert files, f"{fmt.name}: pattern {fmt.pattern} matches nothing"
        if fmt.name == "dots_pages":
            assert len(files) >= 1272, (
                f"{fmt.name}: {len(files)} files, expected at least 1272 "
                "tracked -- the pattern is missing a directory level")


def test_the_builder_emits_every_declared_attribute():
    """The code side of the book format, which nothing read while the class
    name in it went stale."""
    src = ""
    for rel in BUILDER:
        with open(os.path.join(ROOT, "src", "booksmith", rel),
                  encoding="utf-8") as f:
            src += f.read()
    absent = [a for a in HTML_ATTRS + HTML_CLASSES if a not in src]
    assert not absent, (
        f"declared and emitted by nothing: {absent}. The declaration and the "
        f"builder have parted")


def test_the_built_book_carries_the_declared_classes():
    """And the book on disk carries them. A skip with a reason, never a pass:
    `processed/` is not in git, so a fresh clone has nothing to compare."""
    books = _books()
    if not books:
        pytest.skip("no built book: processed/ is not in git")
    html = open(books[-1], encoding="utf-8").read()
    for name in HTML_CLASSES:
        assert f'class="{name}"' in html, (
            f"{books[-1]}: the book carries no class {name!r}, and the code "
            f"declares it. The declaration and the book have parted")


def test_the_built_book_carries_the_declared_attributes():
    books = _books()
    if not books:
        pytest.skip("no built book in processed/ -- nothing to compare")
    text = open(books[-1], encoding="utf-8").read()
    absent = [a for a in HTML_CORE if a not in text]
    assert not absent, (
        f"{books[-1]} does not carry {absent} -- the builder and the book it "
        "built have drifted apart, and `books apply` will not find its blocks")
