"""One shape for a book directory, and the moves that get there.

THE SHAPE (`docs/plan.md`, decision 2):

    <book>/manifest.json  <book>.pdf  truth/
           detect/<model>/   pages/ run.json
           read/<model>/     pages/ answers/ crops/ run.json
           look/<model>.pdf  boxes over the pages
           build/            book.html + assets/

WHAT WAS OUT OF PLACE, and each is one kind of thing under two names:

  check.pdf              one overlay file, on the six synthetic benches
  check/<model>.pdf      a DIRECTORY of them, on annopage and hard36
                         -> look/<model>.pdf everywhere. The single file has
                            no model in its name and takes the one that made
                            it, from the bench's only detect run at the time.
  dots-pages/*.json      a detect run's pages, in a sibling directory
  dots/{job.log,pass0/}  the same run's raw output, in another
                         -> detect/dots-ocr/{pages/,job/}. It is a run by a
                            model called dots-ocr and has been two directories
                            that no command knows about.
  real/*.pdf             three books with no truth, loose in one directory
                         -> real-<name>/ book directories with a manifest

THE DOTS PAGES COST $0.892 ON A RENTED CARD and have no home re-parser, so
they move under a sha256 list taken before and compared after, and `git mv`
keeps the rename visible in the index.

    python3 tools/migrate_bench.py            what would move
    python3 tools/migrate_bench.py --apply    move it
"""
import glob
import hashlib
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The overlay that carries no model in its name. Taken from the run that made
# it: at the time each of these benches held exactly one detect run.
SINGLE_OVERLAY_MODEL = "PP-DocLayoutV2"


def plan():
    """(source, destination, what) for every path out of place."""
    out = []
    for pdf in sorted(glob.glob(os.path.join(ROOT, "bench", "*", "check.pdf"))):
        book = os.path.dirname(pdf)
        out.append((pdf, os.path.join(book, "look",
                                      SINGLE_OVERLAY_MODEL + ".pdf"),
                    "overlay"))
    for d in sorted(glob.glob(os.path.join(ROOT, "bench", "*", "check"))):
        if not os.path.isdir(d):
            continue
        book = os.path.dirname(d)
        for f in sorted(os.listdir(d)):
            out.append((os.path.join(d, f), os.path.join(book, "look", f),
                        "overlay"))
    for d in sorted(glob.glob(os.path.join(ROOT, "bench", "*", "dots-pages"))):
        book = os.path.dirname(d)
        out.append((d, os.path.join(book, "detect", "dots-ocr", "pages"),
                    "dots pages"))
    for d in sorted(glob.glob(os.path.join(ROOT, "bench", "*", "dots"))):
        book = os.path.dirname(d)
        out.append((d, os.path.join(book, "detect", "dots-ocr", "job"),
                    "dots job"))
    real = os.path.join(ROOT, "bench", "real")
    for pdf in sorted(glob.glob(os.path.join(real, "*.pdf"))):
        stem = os.path.splitext(os.path.basename(pdf))[0]
        book = os.path.join(ROOT, "bench", f"real-{stem}")
        out.append((pdf, os.path.join(book, os.path.basename(pdf)), "book"))
        sel = os.path.join(real, f"{stem}.pages.json")
        if os.path.isfile(sel):
            out.append((sel, os.path.join(book, "pages.json"), "selector"))
    return out


def _hashes(p):
    if os.path.isfile(p):
        # KEYED BY NOTHING, because a single file is being RENAMED and its
        # basename is what changes. Keyed by basename, the check compared
        # `{"check.pdf": …}` against `{"PP-DocLayoutV2.pdf": …}` and called a
        # correct move corrupt -- a guard that cries wolf on the one thing it
        # is watching. A directory keeps relative paths, which the move does
        # not change.
        return {"": hashlib.sha256(open(p, "rb").read()).hexdigest()}
    out = {}
    for dirpath, _, names in os.walk(p):
        for n in names:
            f = os.path.join(dirpath, n)
            out[os.path.relpath(f, p)] = hashlib.sha256(
                open(f, "rb").read()).hexdigest()
    return out


def _tracked(p):
    r = subprocess.run(["git", "ls-files", "--error-unmatch",
                        os.path.relpath(p, ROOT)],
                       cwd=ROOT, capture_output=True, text=True)
    return r.returncode == 0


def main(argv):
    moves = plan()
    if not moves:
        print("  nothing out of place")
        return 0
    for src, dst, what in moves:
        if os.path.exists(dst):
            print(f"  REFUSED {os.path.relpath(dst, ROOT)} exists already")
            return 1
        n = len(_hashes(src))
        print(f"  {what:<11} {os.path.relpath(src, ROOT)} -> "
              f"{os.path.relpath(dst, ROOT)}  ({n} file{'s' * (n != 1)})")
    if "--apply" not in argv:
        print(f"\n  {len(moves)} moves. --apply to make them")
        return 0
    for src, dst, what in moves:
        was = _hashes(src)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if _tracked(src) or (os.path.isdir(src) and any(
                _tracked(os.path.join(src, f)) for f in os.listdir(src)[:1])):
            subprocess.run(["git", "mv", os.path.relpath(src, ROOT),
                            os.path.relpath(dst, ROOT)], cwd=ROOT, check=True)
        else:
            os.rename(src, dst)
        now = _hashes(dst)
        if now != was:
            print(f"  BYTES MOVED in {os.path.relpath(dst, ROOT)}")
            return 1
        print(f"  moved {os.path.relpath(dst, ROOT)}: {len(now)} "
              f"file{'s' * (len(now) != 1)}, byte-identical")
    # `bench/real` is empty once its books have left.
    real = os.path.join(ROOT, "bench", "real")
    if os.path.isdir(real) and not os.listdir(real):
        os.rmdir(real)
        print("  removed the empty bench/real")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
