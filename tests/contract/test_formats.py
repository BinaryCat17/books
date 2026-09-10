"""The names the code walks by must exist in the data on disk, in quantity.

The rest of the suite runs on fixtures built by the code under test, so it is
blind to code and data drifting apart -- the failure mode of every rename. The
key name comes from the code below, the count off the disk, so a rename on
either side goes red: a missing name means the code moved, a count under the
floor means the data did. The floors are measured, and are floors rather than
exact counts so that adding a bench does not redden them; they were counted on
tracked files only, `processed/` and the synthetic benches being absent from git.
"""
import collections
import glob
import json
import os

import pytest

from booksmith.core.config import ROOT


class Format:
    """One on-disk format: where its files are, and what must be inside them.
    `floors` is `key -> smallest number of occurrences over the tracked files`;
    a declared key absent from the data is the loudest thing this file says."""

    def __init__(self, name, pattern, floors):
        self.name = name
        self.pattern = pattern
        self.floors = floors

    def files(self, root=ROOT):
        return sorted(glob.glob(os.path.join(root, self.pattern),
                                recursive=True))


FORMATS = (
    # Tracked truth pages: annopage and hard. The six synthetic benches are
    # behind .gitignore, manifest apart.
    Format(
        "truth", "bench/*/truth/*.json",
        {"case": 730, "book": 730, "bucket": 1062, "category": 1062,
         "source_category": 1955, "out_of_scope": 724,
         "objects_out_of_scope": 724, "text_marked": 730,
         "order_marked": 730, "doubtful": 724, "inexpressible": 724,
         "file": 724}),
    # Three detect snapshots are tracked; `books replay --check` walks the path
    # ('knobs', <knob>, 'value').
    Format(
        "detect_run", "bench/*/detect/*/run.json",
        {"knobs": 12, "value": 432, "default": 432, "what": 432,
         "set_externally": 444, "name": 24, "prompts": 24, "by_label": 24,
         "when": 12, "raster": 12, "commit": 12, "source": 12, "args": 12}),
    # All thirteen bench manifests are tracked. `source` is the one key that
    # says which file a truth directory and a run are about.
    Format(
        "manifest", "bench/*/manifest.json",
        {"book": 147, "value": 216, "default": 216, "what": 216,
         "debt": 216, "set_externally": 216, "page_no": 130, "chars": 99,
         "char_truth": 99, "blocks_with_text": 99, "cell_count": 99,
         "source": 11}),
    # `METRICS.md` is rendered from these and nothing else. The floors are 1
    # because a clone may hold one file or fifty; what they guard is the names.
    # `kind` is absent on purpose: no tracked result carries it yet.
    Format(
        "results", "results/*.json",
        {"records": 1, "commit": 1, "when": 1, "metric": 1, "bench": 1,
         "run": 1, "scalars": 1, "params": 1, "value": 1}),
)

# The book is a format too: `books html` writes these names and `books apply`
# parses the book back out with selectors over them.
HTML_ATTRS = (
    "data-no-text", "data-kind", "data-inside", "data-image-share",
    "data-truncated", "data-repeat", "data-repeat-text", "data-empty",
    "data-role", "data-repeats-hidden", "data-sheet", "data-text",
    "data-furniture-only", "data-level", "data-table-shape",
    "data-placed-by", "data-label",
)
# The class names the builder emits.
HTML_CLASSES = ("sheet",)
# The four every built book must carry, whatever is on its pages; the other
# thirteen are conditional and cannot be required of a particular book.
HTML_CORE = ("data-role", "data-label", "data-sheet", "data-level")

# The two modules that write the book and parse it back out.
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
    """A declaration with one key renamed must read as absent from the disk."""
    fmt = [f for f in FORMATS if f.name == "truth"][0]
    seen = measure()["truth"]
    assert seen.get("text_marked", 0) >= fmt.floors["text_marked"]
    assert seen.get("text_marked_renamed", 0) == 0, "a name nothing writes is on disk"


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
    """A dead glob is a silent zero, and half a floor is worse than none: it
    looks measured."""
    for fmt in FORMATS:
        files = fmt.files()
        assert files, f"{fmt.name}: pattern {fmt.pattern} matches nothing"
        if fmt.name == "dots_pages":
            assert len(files) >= 1272, (
                f"{fmt.name}: {len(files)} files, expected at least 1272 "
                "tracked -- the pattern is missing a directory level")


def test_the_builder_emits_every_declared_attribute():
    """The code side of the book format: every declared name is emitted."""
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
