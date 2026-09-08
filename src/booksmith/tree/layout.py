"""The shape of a book directory, declared -- so "nothing outdated" is a
property of the tree and not a tidy-up someone did once.

WHY THIS FILE EXISTS. `bench/` had drifted into four different kinds of thing
under one name, plus 1369 files from a build three weeks old that the plan had
already condemned in writing, plus one overlay under two names (`check.pdf` on
six benches, `check/<model>.pdf` on two) and one detect run split across two
sibling directories (`dots/` and `dots-pages/`) that no command knew about.
None of it was caught by anything, because nothing said what a book directory
IS. Tidying it by hand fixes today; declaring it fixes the next drift.

WHAT A BOOK DIRECTORY IS. Exactly these, and a bench is a book with `truth/`:

    manifest.json     which scan this is: source {name, sha256}
    <name>.pdf        the scan itself
    truth/            only a bench has it
    detect/<model>/   a level-one run: pages/ and run.json
    read/<model>/     a level-two run
    look/<model>.pdf  boxes over the pages, for the eye
    build/            the product: book.html and its kitchen
    pages.json        a page selector, where a book has one

THE MODEL IS THE DIRECTORY, at both levels. `Detector.label()` and
`Reader.label()` name it, `core.book.safe_label` refuses anything that is not
a directory name, and that is what lets six detectors stand side by side in
one table instead of overwriting each other.

WHAT IS NOT A BOOK lives elsewhere, and that was half the mess: the
acceptance snapshots are the suite's (`tests/expected/`), the measurements are
their own (`results/`, with `METRICS.md` rendered from them), and `bench/`
holds books and nothing else.
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

# Where book directories live. Both are the same shape on purpose: a bench is
# a book with truth, and `Book.open` does not care which tree it is in.
BOOK_ROOTS = ("bench", "processed")

# A book directory holds these and nothing else. A name is either exact or a
# pattern with `<model>` in it, and `<model>` is what `safe_label` allows.
ALLOWED = (
    "manifest.json",          # what makes a directory a book
    "<source>.pdf",           # THE scan -- the one the manifest names
    # A PAGE SELECTOR, AND IT HAS NO READER -- the only tracked file in the
    # tree that nothing opens. `bench/real-holdout20/pages.json` lists the 20
    # page numbers taken out of the original scan (4, 40, 143, 292, ...), and
    # `bench/real-*/manifest.json` says of those three pdfs that they "have no
    # source anywhere -- they ARE the source". So the selector is the only
    # surviving record of WHICH pages of that book were held out, it weighs 97
    # bytes, and nothing can reconstruct it. Kept as provenance and named here
    # so the stray check does not chase it; said out loud so the next person
    # does not delete it for being unread, and does not assume `--pages` reads
    # it either.
    "pages.json",
    "truth/",                 # a bench has one
    "detect/<model>/",        # level one, one directory per model
    "read/<model>/",          # level two
    "look/<model>.pdf",       # boxes over the pages, for the eye
    "look/truth.pdf",         # ... and truth drawn with no model beside it
    "build/",                 # the product
    "assets/",                # the kitchen of a book built the old way
    "book.html",              # ... and its one file
)

# What `books crop` and `books read` write BESIDE a run, `<run dir>.crop` and
# `<run dir>.read`. Declared, because they are inside `detect/` where a name
# is otherwise a model: `MODEL` matches `PP-DocLayoutV2.crop` perfectly well,
# so without this the check could not tell a legitimate crop directory from a
# run misfiled under a name with a dot in it.
BESIDE_A_RUN = (".crop", ".read")

# WHAT A RUN DIRECTORY HOLDS, per level. The walk used to stop AT the run and
# never look in, so `detect/<model>/junk.txt` was a file no instrument in this
# project could see.
#
# TWO SETS AND NOT ONE UNION, because a union is a weaker check wearing the
# same green: `read_with.json` under a DETECTION run would mean a level-two
# artefact filed at level one, and a union cannot say so. The rented level-one
# run is the reason `job/` and `job.log` are in the first set -- dots-ocr ran
# on a card, and it is also the one run in the tree with NO `run.json`, which
# is why absence is not checked here (see the note in `strays`).
INSIDE_A_RUN = {
    "detect": ("pages", "run.json", "job", "job.log"),
    # `vllm.*` AND `progress.json` COME BACK FROM THE CARD, and leaving them
    # out was the check being wrong about the tree rather than the other way
    # round: `read/rented/paddleocr_vl/run.sh` writes both on the rented
    # machine and `remote/runner.py` fetches `run.json`, `vllm.json` and
    # `progress.json` home by name. `vllm.json` holds `vllm_startup_s`,
    # measured once on a card that billed by the minute.
    "read": ("pages", "answers", "crops", "html", "run.json",
             "read_with.json", "job.log", "job",
             "vllm.json", "vllm.log", "progress.json"),
}

# Files a root may hold that are not books. A root is for books; this is the
# short list of what else is allowed to sit there, and it is a LIST because
# there is no rule -- which is why it is short and why anything not on it is
# named.
ROOT_FILES = ("README.md",)

MODEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$")


def books():
    """Every book directory: one with a manifest.

    `os.listdir` AND NOT `glob("*")`, which skips a dotted name. A book
    directory called `.old` was walked by nothing at all, so the way to hide
    a stale bench from this instrument was to put a dot in front of it.
    """
    out = []
    for top in BOOK_ROOTS:
        d = os.path.join(ROOT, top)
        if not os.path.isdir(d):
            continue
        for name in sorted(os.listdir(d)):
            p = os.path.join(d, name)
            if os.path.isfile(os.path.join(p, "manifest.json")):
                out.append(os.path.relpath(p, ROOT))
    return out


def _scan_of(book):
    """The one pdf name this book's manifest claims, or None."""
    try:
        with open(os.path.join(book, "manifest.json"), encoding="utf-8") as f:
            return ((json.load(f).get("source") or {}).get("name")) or None
    except (OSError, ValueError):
        return None


def strays():
    """path -> why it does not belong. Empty means the tree is in shape.

    Walks one level into a book and one level into `detect/` and `read/`,
    which is where a wrong name shows: a run under a name that is not a
    model, a directory nobody declared, a file left from a shape that went.
    """
    bad = {}
    exact = {a for a in ALLOWED if not a.endswith("/") and "<" not in a}
    dirs = {a.rstrip("/").split("/")[0] for a in ALLOWED if a.endswith("/")}
    dirs |= {a.split("/")[0] for a in ALLOWED if "/" in a}
    for rel in books():
        book = os.path.join(ROOT, rel)
        scan = _scan_of(book)
        if (scan and rel.split("/")[0] == "bench"
                and not os.path.isfile(os.path.join(book, scan))):
            # A PART THAT IS ABSENT IS NOT A PART THAT IS FINE. The walk only
            # ever asked about what it FOUND, so a bench whose scan had gone
            # -- every measurement over it unrepeatable -- passed silently.
            #
            # ASKED OF `bench/` AND NOT OF `processed/`, because the two roots
            # differ here by DECISION and CLAUDE.md states it: a built book is
            # self-sufficient except for its scan, which stays in `raw/` --
            # crops are cut from it, a rebuild needs it, and reading the
            # finished book does not. Its name and sha256 live in the manifest
            # and in `assets/run.json` so the thread back to it survives. So
            # both books under `processed/` legitimately have no pdf inside,
            # and demanding one would have failed the check on the two real
            # books this project has built.
            bad[f"{rel}/{scan}"] = (
                "the scan the manifest names is NOT HERE, so nothing can be "
                "re-measured over this bench and its sha256 checks nothing")
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
                            # `os.listdir` WITHOUT `isdir` READ A FILE AS A
                            # RUN: `detect/notes.txt` matches MODEL and passed
                            # as a model's name.
                            bad[f"{rel}/{name}/{run}"] = (
                                "a file directly under detect/ or read/; a "
                                "run is a DIRECTORY named for the model")
                        elif run.endswith(BESIDE_A_RUN):
                            base = run.rsplit(".", 1)[0]
                            if not os.path.isdir(os.path.join(p, base)):
                                bad[f"{rel}/{name}/{run}"] = (
                                    f"written beside a run that is not here: "
                                    f"there is no {name}/{base}/")
                        elif not MODEL.match(run):
                            bad[f"{rel}/{name}/{run}"] = (
                                "a run directory is the MODEL's name; this "
                                "is not one")
                        else:
                            for f in sorted(os.listdir(q)):
                                if f not in INSIDE_A_RUN[name]:
                                    bad[f"{rel}/{name}/{run}/{f}"] = (
                                        f"not part of a {name} run; a "
                                        f"{name} run holds "
                                        f"{', '.join(INSIDE_A_RUN[name])}")
                elif name == "look":
                    runs = set(os.listdir(os.path.join(book, "detect"))) \
                        if os.path.isdir(os.path.join(book, "detect")) else set()
                    for f in sorted(os.listdir(p)):
                        # `look/` WAS NEVER OPENED, and the rename that gave
                        # it one name carried the OLD names inside: four
                        # sheets called `PP-plus-L.pdf` and `YOLOX-layout.pdf`
                        # after models with no such label, on the two benches
                        # where six models had run. "The single file did not
                        # say which model drew it" was the reason for the
                        # rename, and four of them said one that never was.
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
    # And nothing but books under the roots that hold books.
    for top in BOOK_ROOTS:
        d = os.path.join(ROOT, top)
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
            elif name not in ROOT_FILES:
                # A FILE UNDER THE ROOT WAS NEVER LOOKED AT, guarded away by
                # `if os.path.isdir(p)` -- so `bench/leftover.pdf` and
                # `bench/results.json`, the two shapes this instrument was
                # written after, would both have passed the check named for
                # them.
                bad[f"{top}/{name}"] = (
                    f"a loose file under a root that holds BOOKS; only "
                    f"{', '.join(ROOT_FILES)} and book directories belong "
                    f"here")
    return bad


def main(argv):
    b = books()
    print(f"  {len(b)} book directories")
    bad = strays()
    for path, why in sorted(bad.items()):
        print(f"  STRAY  {path}\n         {why}")
    if bad:
        print(f"\n  {len(bad)} paths are not in the declared shape")
        return 1
    print("  every path is in the declared shape")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
