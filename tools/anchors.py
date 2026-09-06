"""Every mutation that patches source by literal text -- does its line still exist?

WHY THIS EXISTS. A mutation in `tests/selfcheck.py` reaches inside a function
by replacing one exact line of source. Move that line -- reflow it, translate
it, rename a variable in it -- and the mutation stops landing. The battery
refuses to certify a mutation it could not apply, so it ABORTS; but it aborts
on the FIRST one and takes minutes to get there, and everything after it goes
unmeasured.

Measured: reformatting `Knob("SYNTH_AGING", ...)` onto two lines killed the
mutation that guards it, and nothing said so until the battery was run whole.

This asks the same question in under a second, and about ALL of them at once.

    python3 tools/anchors.py            # every anchor, silent when they land
    python3 tools/anchors.py --list     # what each one patches, and where

WHAT IT CANNOT SEE. Only calls whose arguments are literal strings; a mutation
that builds its patch at run time is skipped, and skipped is printed, never
counted as landed.
"""
import ast
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BATTERY = os.path.join(ROOT, "tests", "selfcheck.py")
# `one_line` and `sources` both take (target, old, new); the first names a
# module, the second a path relative to `src/booksmith/`.
PATCHERS = {"one_line": "module", "sources": "path"}


def literal(node):
    """The string this argument is, or None if it is not a plain string.

    Implicit concatenation ('a' 'b') arrives already joined by the parser;
    anything computed -- a name, an f-string, a call -- is not an anchor this
    tool can chase.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def calls():
    """(line, kind, target, old) for every literal source patch in the battery."""
    tree = ast.parse(open(BATTERY, encoding="utf-8").read(), filename=BATTERY)
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
            continue
        kind = PATCHERS.get(node.func.id)
        if kind is None or len(node.args) < 2:
            continue
        target, old = literal(node.args[0]), literal(node.args[1])
        yield node.lineno, kind, target, old


def source_of(kind, target):
    if kind == "module":
        return os.path.join(ROOT, "src", target.replace(".", os.sep) + ".py")
    return os.path.join(ROOT, "src", "booksmith", target)


def main(argv):
    show = "--list" in argv
    lands = missed = skipped = 0
    for line, kind, target, old in calls():
        if target is None or old is None:
            skipped += 1
            print(f"  SKIPPED  selfcheck.py:{line}: the patch is not a literal")
            continue
        path = source_of(kind, target)
        if not os.path.isfile(path):
            missed += 1
            print(f"  NO FILE  selfcheck.py:{line}: {path} does not exist")
            continue
        n = open(path, encoding="utf-8").read().count(old)
        if n == 1:
            lands += 1
            if show:
                print(f"  lands    {target}: {old.strip()[:70]}")
        elif n == 0:
            missed += 1
            print(f"  GONE     selfcheck.py:{line}: {target} has no line "
                  f"{old.strip()[:70]!r}")
        else:
            # Not fatal -- `replace(..., 1)` still patches the first -- but it
            # patches an ARBITRARY one of them, so the mutation no longer says
            # what it claims to say.
            missed += 1
            print(f"  {n} TIMES selfcheck.py:{line}: {target} carries "
                  f"{old.strip()[:60]!r} more than once")
    print(f"\nanchors {lands + missed + skipped}: land {lands}, "
          f"do not land {missed}, not literal {skipped}")
    return 1 if missed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
