"""One measurement, one place -- counted, so the claim is not a matter of taste.

CLAUDE.md opens with the disease: "One figure -- the artifacts V2 finds on the
golden bench -- stood here twice, in the contour journal three times and in the
source six more. A second copy drifts, and it drifts silently." The rule was
stated and then guarded in exactly one place: `tests/test_docs_map.py` forbids
four named numbers from returning to the map. Between the documents themselves
nothing counted at all.

WHAT COUNTS AS A MEASUREMENT, and why the bar is where it is. FOUR CONSECUTIVE
DIGITS, a money amount, or a percentage given to a decimal. Not "four
significant digits", which this header claimed and the code has never done:
`1.234`, `12.34` and `1,232` all carry four significant digits and are
invisible here, while `1232` and `1 232` are seen. Three-digit numbers collide
by chance -- 144 is a dpi, a page count and a byte size -- and the instrument
must not cry wolf: over these documents a three-digit rule finds 114
"duplicates" and a four-digit one 28. An instrument that reports 114 gets
switched off.

WHAT IS COUNTED IS COPIES, NOT DISTINCT FIGURES. The first edition counted
`len(duplicates())`, so a figure standing in two documents and the same figure
standing in seven both counted as one, and duplication could grow while the
ratchet held. And `measurements()` returned a SET, so a figure stated TWICE IN
ONE DOCUMENT was invisible -- which is literally the case the map opens with.
Both are counted now, so the number is the one the rule is about.

WHAT IS NOT READ. `METRICS.md` alone, exempt BY NAME: it is GENERATED from
`results/*.json` and rendered afresh, so it cannot drift from what it
restates -- which is the whole thing this file counts. Every other document is
read, the front page included; it was missing, and it holds three of these
copies. The narrative of how the tree got here lives in commit messages, where
git keeps it attached to the change it describes. A number in a commit message
is a record of one moment and is rewritten by nothing; a number in a document
is a claim about the tree as it is NOW, and two documents claiming it is where
drift begins.

THE CEILING MAY FALL AND NEVER RISE. Step 5 of `docs/plan.md` is the
documentation split, and this is the number it has to move: every copy is one
document quoting another instead of pointing at it.

    python3 tools/figures.py           what is duplicated, and where
    python3 tools/figures.py --check   red if the count rose
"""
import collections
import glob
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

# A money amount, a percentage to a decimal, or a run of digits (with the thin
# and ordinary spaces this project groups thousands with).
NUMBER = re.compile(r"\$\d+(?:\.\d+)?|\d+\.\d+ ?%|\d[\d   ]*\d")

# NOT MEASUREMENTS, and each says why. A short list on purpose: the moment it
# grows, the four-digit rule is wrong and should be changed instead.
NOT_A_MEASUREMENT = {
    "2026": "the year",
    "4090": "the graphics card, in its name (RTX_4090)",
    "5090": "the graphics card",
    "4096": "the model's token ceiling: a specification, and the two places "
            "that name it are the model's page and the plan that must respect "
            "it",
}

# The count today. It may fall and never rise; step 5 takes it to zero.
#
# RE-FOUNDED at 127 from 25, and the rise is the instrument being corrected,
# not the tree getting worse. Three changes, each of which the old number was
# blind to: copies are counted instead of distinct figures (a figure in seven
# documents counted as one), a figure stated twice in ONE document is a copy
# (the case the map opens with, previously invisible because the reader
# returned a set), and `README.md` is read at last -- the front page, which
# holds three of them.
CEILING = 127


# Rendered, never written: it cannot drift from what it restates, so it is not
# a second copy. Named here rather than left out in silence.
GENERATED = ("METRICS.md",)


def documents():
    """Every document a reader is sent to.

    THE FRONT PAGE IS ONE, and was missing. So is anything under `docs/` at
    any depth: the old glob was `docs/*.md` and would not have seen
    `docs/reference/`, which step 5 creates.
    """
    out = {"CLAUDE.md", "README.md", os.path.join("bench", "README.md")}
    for p in glob.glob(os.path.join(ROOT, "docs", "**", "*.md"),
                       recursive=True):
        out.add(os.path.relpath(p, ROOT))
    return sorted(p for p in out if p not in GENERATED
                  and os.path.isfile(os.path.join(ROOT, p)))


def measurements(rel):
    """measurement -> how many times this document states it.

    A COUNT, not a set. Twice in one document is a second copy too, and it is
    the case the map opens with -- one figure stood there twice.
    """
    out = collections.Counter()
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        text = f.read()
    for m in NUMBER.findall(text):
        n = re.sub(r"[\u2009 ]", "", m)
        if n in NOT_A_MEASUREMENT:
            continue
        if n.startswith("$") or n.endswith("%") or len(re.sub(r"\D", "", n)) >= 4:
            out[n] += 1
    return out


def duplicates():
    """measurement -> the documents that state it (a document stating it
    twice appears twice), for every one stated more than once anywhere."""
    where = collections.defaultdict(list)
    for rel in documents():
        for n, k in measurements(rel).items():
            where[n] += [rel] * k
    return {n: sorted(v) for n, v in where.items() if len(v) > 1}


def copies(d=None) -> int:
    """Redundant copies: the quantity the rule is about. One statement of a
    figure is not a copy; every further one is."""
    d = duplicates() if d is None else d
    return sum(len(v) - 1 for v in d.values())


def main(argv):
    d = duplicates()
    n_copies = copies(d)
    for n, docs in sorted(d.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        seen = collections.Counter(docs)
        print(f"  {n:<12} " + ", ".join(
            f"{k}{'' if v == 1 else f' x{v}'}" for k, v in sorted(seen.items())))
    print(f"\n  {n_copies} redundant copies of {len(d)} measurements "
          f"(ceiling {CEILING})")
    if "--check" in argv:
        if n_copies > CEILING:
            print(f"ROSE: {n_copies} against a ceiling of {CEILING}. A second "
                  f"copy drifts, and it drifts silently -- point at the "
                  f"document that owns the number instead of restating it.")
            return 1
        if n_copies < CEILING:
            print(f"the ceiling is stale: {n_copies} left, and it says "
                  f"{CEILING}. Lower it in tree/figures.py -- a ratchet that "
                  f"stops pressing is not a ratchet.")
            return 1
        print(f"holds: {n_copies} copies of {len(d)} measurements, none new")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
