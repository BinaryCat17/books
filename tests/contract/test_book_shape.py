"""Every book directory is in the shape `core/book.py` declares.

"Not a single outdated file" as a property of the tree, not a tidy-up someone
did once. The declaration is `core.book`: BOOK_ROOTS, ALLOWED, BESIDE_A_RUN,
INSIDE_A_RUN, ROOT_FILES. The walk is here, and it goes one level into a book
and one level into `detect/` and `read/`, which is where a wrong name shows.
"""
import glob
import json
import os

import pytest

from booksmith.core import book as book_mod
from booksmith.core.config import ROOT
from booksmith.core.page import Page

MISSING_SCAN = "the scan the manifest names is NOT HERE"


def _scan_of(book):
    """The one pdf name this book's manifest claims, or None."""
    try:
        with open(os.path.join(book, "manifest.json"), encoding="utf-8") as f:
            return ((json.load(f).get("source") or {}).get("name")) or None
    except (OSError, ValueError):
        return None


def strays(root=ROOT):
    """path -> why it does not belong. Empty means the tree is in shape."""
    bad = {}
    allowed, roots = book_mod.ALLOWED, book_mod.BOOK_ROOTS
    inside, beside = book_mod.INSIDE_A_RUN, book_mod.BESIDE_A_RUN
    exact = {a for a in allowed if not a.endswith("/") and "<" not in a}
    dirs = {a.rstrip("/").split("/")[0] for a in allowed if a.endswith("/")}
    dirs |= {a.split("/")[0] for a in allowed if "/" in a}
    for rel in book_mod.Book.list(root):
        book = os.path.join(root, rel)
        scan = _scan_of(book)
        if (scan and rel.split(os.sep)[0] == "bench"
                and not os.path.isfile(os.path.join(book, scan))):
            # A missing bench scan leaves every measurement over it unrepeatable.
            # Asked of `bench/` only: a built book keeps its scan in `raw/`.
            bad[f"{rel}/{scan}"] = (
                f"{MISSING_SCAN}, so nothing can be re-measured over this "
                f"bench and its sha256 checks nothing")
        for name in sorted(os.listdir(book)):
            p = os.path.join(book, name)
            if os.path.isdir(p):
                if name not in dirs:
                    bad[f"{rel}/{name}"] = (
                        f"not a part of a book directory; the parts are "
                        f"{', '.join(sorted(dirs))}")
                elif name in ("detect", "read"):
                    for run in sorted(os.listdir(p)):
                        q = os.path.join(p, run)
                        if not os.path.isdir(q):
                            bad[f"{rel}/{name}/{run}"] = (
                                "a file directly under detect/ or read/; a "
                                "run is a DIRECTORY named for the model")
                        elif run.endswith(beside):
                            base = run.rsplit(".", 1)[0]
                            if not os.path.isdir(os.path.join(p, base)):
                                bad[f"{rel}/{name}/{run}"] = (
                                    f"written beside a run that is not here: "
                                    f"there is no {name}/{base}/")
                        elif not book_mod.LABEL_OK.match(run):
                            bad[f"{rel}/{name}/{run}"] = (
                                "a run directory is the MODEL's name; this "
                                "is not one")
                        else:
                            for f in sorted(os.listdir(q)):
                                if f not in inside[name]:
                                    bad[f"{rel}/{name}/{run}/{f}"] = (
                                        f"not part of a {name} run; a "
                                        f"{name} run holds "
                                        f"{', '.join(inside[name])}")
                elif name == "look":
                    runs = set(os.listdir(os.path.join(book, "detect"))) \
                        if os.path.isdir(os.path.join(book, "detect")) else set()
                    for f in sorted(os.listdir(p)):
                        if not f.endswith(".pdf"):
                            bad[f"{rel}/look/{f}"] = (
                                "look/ holds one pdf per model and nothing "
                                "else")
                        elif f[:-4] != "truth" and f[:-4] not in runs:
                            bad[f"{rel}/look/{f}"] = (
                                f"named for `{f[:-4]}`, which has no run "
                                f"under detect/ -- a sheet of boxes nobody "
                                f"can trace to the model that drew them")
            elif name == scan:
                continue
            elif name not in exact:
                bad[f"{rel}/{name}"] = (
                    f"not a file of a book directory; the files are "
                    f"{', '.join(sorted(exact))} and the scan the manifest "
                    f"names ({scan or 'none named'})")
    for top in roots:
        d = os.path.join(root, top)
        if not os.path.isdir(d):
            continue
        for name in sorted(os.listdir(d)):
            p = os.path.join(d, name)
            if os.path.isdir(p):
                if not os.path.isfile(os.path.join(p, "manifest.json")):
                    bad[f"{top}/{name}"] = (
                        "under a root that holds BOOKS and has no "
                        "manifest.json, so nothing says which scan it is "
                        "about")
            elif name not in book_mod.ROOT_FILES:
                bad[f"{top}/{name}"] = (
                    f"a loose file under a root that holds BOOKS; only "
                    f"{', '.join(book_mod.ROOT_FILES) or 'book directories'} "
                    f"belong here")
    return bad


def _split(bad):
    absent = {p: w for p, w in bad.items() if MISSING_SCAN in w}
    return absent, {p: w for p, w in bad.items() if p not in absent}


def test_every_book_directory_is_in_the_declared_shape():
    bad = strays()
    assert len(book_mod.Book.list(ROOT)) >= 10, (
        f"only {len(book_mod.Book.list(ROOT))} book directories found -- "
        f"the walk broke")
    _, rest = _split(bad)
    assert not rest, (
        "paths that are not in the declared shape of a book directory:\n"
        + "\n".join(f"  {p}: {why}" for p, why in sorted(rest.items())))


def test_a_bench_keeps_the_scan_its_manifest_names():
    """The other half: a part that is absent is not a part that is fine. A bench
    scan is untracked -- drawn or built locally -- so a clone has nothing to ask;
    a scan missing while tracked is a bench nothing can be re-measured over."""
    import subprocess
    absent, _ = _split(strays())
    r = subprocess.run(["git", "ls-files", "-z", *book_mod.BOOK_ROOTS], cwd=ROOT,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    tracked = set(p for p in r.stdout.split("\0") if p)
    gone = {p: w for p, w in absent.items() if p in tracked}
    if absent and not gone:
        pytest.skip(f"{len(absent)} bench scans are not here and not one of "
                    f"them is tracked: they are built locally")
    assert not gone, "\n".join(f"  {p}: {w}" for p, w in sorted(gone.items()))


def test_the_walk_names_a_planted_stray(tmp_path):
    """A walk that finds nothing must be shown able to find something."""
    d = tmp_path / "bench" / "toy"
    (d / "detect" / "Model" / "pages").mkdir(parents=True)
    (d / "manifest.json").write_text('{"source": {"name": "toy.pdf"}}')
    (d / "toy.pdf").write_text("x")
    (d / "detect" / "Model" / "run.json").write_text("{}")
    assert strays(str(tmp_path)) == {}, strays(str(tmp_path))
    (d / "leftovers").mkdir()
    (d / "detect" / "Model" / "junk.txt").write_text("x")
    (tmp_path / "bench" / "loose.pdf").write_text("x")
    bad = strays(str(tmp_path))
    assert set(bad) == {"bench/toy/leftovers", "bench/toy/detect/Model/junk.txt",
                        "bench/loose.pdf"}, bad


def test_the_loader_can_load_every_truth_page_this_project_has():
    """The project's own loader against the project's own truth, round-tripped:
    the production readers go through `core.page.load_pages`, which returns raw
    dicts, so a loader that drops a key is the same defect one step later."""
    files = sorted(glob.glob(os.path.join(ROOT, "bench", "*", "truth",
                                          "*.json")))
    assert len(files) > 500, (
        f"only {len(files)} truth pages under {ROOT} -- this check is "
        f"measuring nothing")
    bad, checked = [], 0
    for f in files:
        with open(f, encoding="utf-8") as fh:
            d = json.load(fh)
        if not d.get("blocks"):
            continue
        checked += 1
        try:
            back = json.loads(json.dumps(Page.from_json(d).to_json()))
        except Exception as e:
            bad.append(f"{os.path.relpath(f, ROOT)}: {type(e).__name__}: {e}")
            continue
        if back != d:
            lost = sorted(set(d.get("blocks", [{}])[0])
                          - set(back.get("blocks", [{}])[0]))
            bad.append(f"{os.path.relpath(f, ROOT)}: does not round-trip; "
                       f"keys lost: {lost}")
    assert checked > 500, f"only {checked} truth pages carried blocks"
    assert not bad, (
        f"{len(bad)} of {checked} truth pages do not survive the project's "
        f"own loader:\n" + "\n".join(bad[:5]))
