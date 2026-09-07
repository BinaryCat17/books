"""One measurement, one document -- counted, so the claim is not a matter of
taste.

CLAUDE.md opens with the disease: "One figure -- the artifacts V2 finds on the
golden bench -- stood here twice, in the contour journal three times and in the
source six more. A second copy drifts, and it drifts silently." The rule was
stated and then guarded in exactly one place: `tests/test_docs_map.py` forbids
four named numbers from returning to the map. Between the documents themselves
nothing counted at all.

WHAT COUNTS AS A MEASUREMENT, and why the bar is where it is. Four significant
digits, a money amount, or a percentage given to a decimal. Three-digit numbers
collide by chance -- 144 is a dpi and a page count and a byte size -- and the
instrument must not cry wolf: measured over these documents, a three-digit rule
finds 114 "duplicates" and a four-digit one 29, of which two are a year and a
graphics card. An instrument that reports 114 gets switched off.

WHAT IS NOT READ. `docs/journal/*` -- a journal entry is a dated record of one
moment, like `runs/ledger.jsonl`. Its numbers are what was true that day and
are rewritten by nothing; forbidding them a second copy would forbid a journal
from quoting the tree it was written about.

THE CEILING MAY FALL AND NEVER RISE, the same shape as the Cyrillic ratchet.
Step 5 of `docs/plan.md` is the documentation split, and this is the number it
has to move: every duplicate below is one document quoting another instead of
pointing at it.

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
CEILING = 25


def documents():
    """Every document a reader is sent to. Journals excluded, see the header."""
    out = {"CLAUDE.md", os.path.join("bench", "README.md")}
    for p in glob.glob(os.path.join(ROOT, "docs", "*.md")):
        out.add(os.path.relpath(p, ROOT))
    return sorted(out)


def measurements(rel):
    """The measurements one document states."""
    out = set()
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        text = f.read()
    for m in NUMBER.findall(text):
        n = re.sub(r"[   ]", "", m)
        if n in NOT_A_MEASUREMENT:
            continue
        if n.startswith("$") or n.endswith("%") or len(re.sub(r"\D", "", n)) >= 4:
            out.add(n)
    return out


def duplicates():
    """measurement -> the documents that state it, for those stated twice."""
    where = collections.defaultdict(list)
    for rel in documents():
        for n in measurements(rel):
            where[n].append(rel)
    return {n: sorted(v) for n, v in where.items() if len(v) > 1}


def main(argv):
    d = duplicates()
    for n, docs in sorted(d.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        print(f"  {n:<12} {', '.join(docs)}")
    print(f"\n  {len(d)} measurements stated in more than one document "
          f"(ceiling {CEILING})")
    if "--check" in argv:
        if len(d) > CEILING:
            print(f"ROSE: {len(d)} against a ceiling of {CEILING}. A second "
                  f"copy drifts, and it drifts silently -- point at the "
                  f"document that owns the number instead of restating it.")
            return 1
        if len(d) < CEILING:
            print(f"the ceiling is stale: {len(d)} left, and it says "
                  f"{CEILING}. Lower it in tree/figures.py.")
            return 1
        print(f"holds: {len(d)} duplicates, none new")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
