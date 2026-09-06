"""Cyrillic ratchet: how much is left, and WHERE. A number, not a verdict.

The project is being translated to English. A translation this large has no
test that can judge it -- no checker reads prose for meaning. What it does have
is a quantity: how many Cyrillic codepoints are left in each area. That number
is the progress of the work, and this file is the instrument that reads it.

WHY CODEPOINTS AND NOT LINES OR WORDS. Rewrapping a comment, splitting a
paragraph or merging two sentences changes lines and words while changing
nothing that matters. Only translation moves codepoints. Measured: rewrapping
one comment across five lines left the count untouched; adding a single letter
moved it by one.

WHY AREAS AND NOT ONE TOTAL. A total lets a shrinking area hide a growing one.
Comments, docstrings, string literals and identifiers are four different jobs
with four different risks -- literals are read by tests, identifiers are read by
the import machinery, comments are read by nobody but us -- and they are counted
apart so that each has to fall on its own.

WHY BOOK PROSE IS EXEMPT BY NAME, NOT BY FILE. `src/booksmith/books/*.py` holds
9105 Cyrillic characters, of which only 682 are book content; the rest is our
own commentary. An exemption written as a file glob would leave 8423 characters
untranslated forever and silently. So the exemption names the constants that
hold page text, and everything around them is counted like any other prose.

    python3 tools/cyr.py            print the table
    python3 tools/cyr.py --save     write cyr-baseline.json
    python3 tools/cyr.py --check    fail if any area grew above the baseline

The counting lives here rather than in `tools/` for one reason: the mutation
battery breaks modules by importing them, and `tools/` is not importable. An
instrument the battery cannot break is an instrument nobody has checked.
"""
import ast
import collections
import io
import json
import os
import subprocess
import sys
import tokenize

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BASELINE = os.path.join(ROOT, "cyr-baseline.json")

# Cyrillic (U+0400..U+04FF) and Cyrillic Supplement (U+0500..U+052F).
#
# Deliberately not "non-ASCII": the project legitimately contains typographic
# dashes, arrows and box drawing, and counting those would make the ratchet
# impossible to bring to zero. An instrument that cannot reach its own target
# teaches everyone to ignore it.
#
# The bounds are escapes rather than letters for the same reason: written as
# characters they are four Cyrillic codepoints, and this file would then hold
# a floor of four under `src.literals` that no amount of translation removes.
def cyr(s: str) -> int:
    return sum(1 for c in s if "\u0400" <= c <= "\u04ff" or
               "\u0500" <= c <= "\u052f")


def latin(s: str) -> int:
    """ASCII letters, counted alongside the Cyrillic they are replacing.

    WHY A SECOND QUANTITY IS NEEDED. The Cyrillic count measures what is LEFT,
    not what was DONE, and the cheapest way to move it is not to translate but
    to delete. Measured on a copy: deleting every whole comment line carrying
    Cyrillic across `src/booksmith/*.py` removed 176 515 characters -- a
    quarter of everything the project has written into its comments -- and left
    the runner green, the mutation battery green, all five acceptance reports
    identical, zero keys below floor, and the ratchet reporting a quarter of
    the translation done.

    Translation moves Cyrillic into Latin. Deletion moves it into nothing. With
    both counted, the two are no longer the same event.
    """
    return sum(1 for c in s if "a" <= c <= "z" or "A" <= c <= "Z")


# Constants whose value IS book content. Russian books stay Russian; these hold
# the text that gets drawn onto synthetic pages, not our explanation of it.
CONTENT_NAMES = ("PROSE_RU", "ENTRY_RU", "ABOUT", "CASES", "AGING", "WORDS_RU")

# Everything tracked that is not a .py and not book data. Kept as an explicit
# list because the first version of this instrument counted only `.py .md .toml
# .yml` and thereby missed 13 217 characters in nine tracked files -- including
# `run.sh`, which executes on a rented GPU, where a mistranslation costs money
# rather than a red test.
OTHER_GLOBS = ("*.md", "*.sh", "*.toml", "*.yml", "*.yaml", "*.in", "*.txt",
               "*.cfg", "*.ini", "*.json", "*.log", "*.js", "*.css", "*.html",
               "*.lock", ".gitignore", ".env.example", "infra/base/Dockerfile")

# Tracked data files: their Cyrillic is book content and format keys, and both
# are handled elsewhere (keys by the migration, content never). Counting them
# here would drown the prose signal in 432 250 characters that must not move.
DATA_PREFIXES = ("bench/",)


def tracked(*globs):
    """Files git would keep: tracked, plus untracked that are not ignored.

    NOT `git ls-files` alone. That counts only what is staged or committed, so
    a new file is invisible until `git add` and the whole baseline jumps at
    commit time -- which is exactly how the first baseline of this instrument
    came out 941 characters low, and the ratchet was red the moment its own
    commit landed.
    """
    r = subprocess.run(["git", "ls-files", "-z", "--cached", "--others",
                        "--exclude-standard"] + list(globs),
                       capture_output=True, text=True, cwd=ROOT)
    out = {p for p in r.stdout.split("\0") if p}
    return sorted(p for p in out if os.path.isfile(os.path.join(ROOT, p)))


def _content_nodes(tree):
    """String nodes that hold book content, by the constant they are assigned to."""
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Assign):
            names = [t.id for t in n.targets if isinstance(t, ast.Name)]
            if any(x in CONTENT_NAMES for x in names):
                for k in ast.walk(n.value):
                    if isinstance(k, ast.Constant) and isinstance(k.value, str):
                        out.add(id(k))
    return out


def py_areas(paths, prefix, counter):
    """Split one .py into comments / docstrings / literals / names.

    Comments come from `tokenize` and everything else from `ast`, because the
    two see different things: a `#` inside a string is not a comment, and a
    docstring is not a literal. Splitting by regex would double-count both.
    """
    for rel in paths:
        src = open(os.path.join(ROOT, rel), encoding="utf-8").read()
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type == tokenize.COMMENT:
                counter[prefix + ".comments"] += cyr(tok.string)
                counter[prefix + ".comments.latin"] += latin(tok.string)
        tree = ast.parse(src)
        content = _content_nodes(tree)
        docs = set()
        for n in ast.walk(tree):
            if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                              ast.ClassDef)) and n.body:
                first = n.body[0]
                if (isinstance(first, ast.Expr)
                        and isinstance(first.value, ast.Constant)
                        and isinstance(first.value.value, str)):
                    docs.add(id(first.value))
                    counter[prefix + ".docstrings"] += cyr(first.value.value)
                    counter[prefix + ".docstrings.latin"] += latin(first.value.value)
        for n in ast.walk(tree):
            if isinstance(n, ast.Constant) and isinstance(n.value, str):
                if id(n) in docs:
                    continue
                where = "book_prose" if id(n) in content else prefix + ".literals"
                counter[where] += cyr(n.value)
                if where != "book_prose":
                    counter[prefix + ".literals.latin"] += latin(n.value)
            elif isinstance(n, ast.Name):
                counter[prefix + ".names"] += cyr(n.id)
            elif isinstance(n, ast.arg):
                counter[prefix + ".names"] += cyr(n.arg)
            elif isinstance(n, ast.Attribute):
                counter[prefix + ".names"] += cyr(n.attr)
            elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef,
                                ast.ClassDef)):
                counter[prefix + ".names"] += cyr(n.name)
            elif isinstance(n, ast.keyword) and n.arg:
                counter[prefix + ".names"] += cyr(n.arg)


def count():
    """area -> Cyrillic codepoints. Every tracked file lands in exactly one."""
    c = collections.Counter()
    py = tracked("*.py")
    src = [p for p in py if p.startswith("src/")]
    tst = [p for p in py if p.startswith("tests/")]
    tools_ = [p for p in py if p.startswith("tools/")]
    py_areas(src, "src", c)
    py_areas(tst, "tests", c)
    py_areas(tools_, "tools", c)

    for rel in tracked(*OTHER_GLOBS):
        if any(rel.startswith(d) for d in DATA_PREFIXES) and rel.endswith(".json"):
            continue
        if rel.endswith(".py"):
            continue
        text = open(os.path.join(ROOT, rel), encoding="utf-8").read()
        n = cyr(text)
        if not n:
            continue
        if rel.endswith(".md"):
            c["docs"] += n
            c["docs.latin"] += latin(text)
        elif any(rel.startswith(d) for d in DATA_PREFIXES):
            c["bench_data"] += n
        else:
            c["config"] += n
            c["config.latin"] += latin(text)
    for k in ("src.comments", "src.docstrings", "src.literals", "src.names",
              "tests.comments", "tests.docstrings", "tests.literals",
              "tests.names", "tools.comments", "tools.docstrings",
              "tools.literals", "tools.names", "docs", "config",
              "bench_data", "book_prose"):
        c.setdefault(k, 0)
        if k not in ("bench_data", "book_prose") and not k.endswith(".names"):
            c.setdefault(k + ".latin", 0)
    return dict(c)


def ratchet_areas(c):
    """Areas the ratchet presses on: Cyrillic only, book content excluded.

    The `.latin` companions are not pressed on -- they are allowed and expected
    to rise. They are read by `test_prose_was_translated_not_deleted`, which
    asks the question this instrument could not answer on its own: did the
    Cyrillic that left an area turn into English, or into nothing?
    """
    return {k: v for k, v in c.items()
            if k not in ("book_prose", "bench_data") and not k.endswith(".latin")}


def latin_areas(c):
    """area -> latin letters, for the areas the ratchet presses on."""
    return {k[:-len(".latin")]: v for k, v in c.items() if k.endswith(".latin")}


def main(argv):
    c = count()
    if "--save" in argv:
        with open(BASELINE, "w", encoding="utf-8") as f:
            json.dump(c, f, ensure_ascii=False, indent=1, sort_keys=True)
            f.write("\n")
        print(f"baseline written: {BASELINE}")
    width = max(len(k) for k in c)
    for k in sorted(c, key=lambda k: (-c[k], k)):
        print(f"  {c[k]:>9}  {k:<{width}}")
    press = ratchet_areas(c)
    print(f"\n  {sum(press.values()):>9}  TOTAL under the ratchet")
    print(f"  {c.get('book_prose', 0):>9}  book prose (exempt, must not move)")
    if "--check" in argv:
        if not os.path.isfile(BASELINE):
            print("no baseline; run --save first")
            return 1
        base = json.load(open(BASELINE, encoding="utf-8"))
        grew = {k: (base.get(k, 0), v) for k, v in press.items()
                if v > base.get(k, 0)}
        if grew:
            for k, (was, now) in sorted(grew.items()):
                print(f"GREW  {k}: {was} -> {now}")
            return 1
        print("ratchet holds: no area grew")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
