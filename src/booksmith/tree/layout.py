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
import glob
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
    "*.pdf",                  # the scan, and look/ has its own below
    "pages.json",             # a page selector
    "truth/",                 # a bench has one
    "detect/<model>/",        # level one, one directory per model
    "read/<model>/",          # level two
    "look/",                  # <model>.pdf for the eye
    "build/",                 # the product
    "assets/",                # the kitchen of a book built the old way
    "book.html",              # ... and its one file
)

MODEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$")


def books():
    """Every book directory: one with a manifest."""
    out = []
    for top in BOOK_ROOTS:
        for p in sorted(glob.glob(os.path.join(ROOT, top, "*"))):
            if os.path.isfile(os.path.join(p, "manifest.json")):
                out.append(os.path.relpath(p, ROOT))
    return out


def strays():
    """path -> why it does not belong. Empty means the tree is in shape.

    Walks one level into a book and one level into `detect/` and `read/`,
    which is where a wrong name shows: a run under a name that is not a
    model, a directory nobody declared, a file left from a shape that went.
    """
    bad = {}
    exact = {a for a in ALLOWED if not a.endswith("/") and "*" not in a}
    dirs = {a.rstrip("/") for a in ALLOWED if a.endswith("/")}
    for rel in books():
        book = os.path.join(ROOT, rel)
        for name in sorted(os.listdir(book)):
            p = os.path.join(book, name)
            if os.path.isdir(p):
                if name.split("/")[0] not in {d.split("/")[0] for d in dirs}:
                    bad[f"{rel}/{name}"] = (
                        f"not a part of a book directory; the parts are "
                        f"{', '.join(sorted(dirs))}")
                elif name in ("detect", "read"):
                    for run in sorted(os.listdir(p)):
                        if not MODEL.match(run):
                            bad[f"{rel}/{name}/{run}"] = (
                                "a run directory is the MODEL's name; this "
                                "is not one")
            elif name not in exact and not name.endswith(".pdf"):
                bad[f"{rel}/{name}"] = (
                    f"not a file of a book directory; the files are "
                    f"{', '.join(sorted(exact))} and the scan")
    # And nothing but books under the roots that hold books.
    for top in BOOK_ROOTS:
        d = os.path.join(ROOT, top)
        if not os.path.isdir(d):
            continue
        for name in sorted(os.listdir(d)):
            p = os.path.join(d, name)
            if os.path.isdir(p) and not os.path.isfile(
                    os.path.join(p, "manifest.json")):
                bad[f"{top}/{name}"] = (
                    "under a root that holds BOOKS and has no manifest.json, "
                    "so nothing says which scan it is about")
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
