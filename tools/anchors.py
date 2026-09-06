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

THE THIRD PATCHER. `attrs(obj, NAME=...)` swaps an attribute in memory. It
reads the attribute first, so a NAME that moved raises `AttributeError` and
the battery aborts on the first one -- after the minutes it takes to get
there, with everything after it unmeasured. Measured on the plan for the
package move: 209 such calls on some forty objects, and no instrument looked
at them. So this tool imports the battery (its module level only captures
attributes that exist, it runs nothing) and asks `hasattr` for every
`attrs()` target it can resolve by name. A target that is a local variable
inside a function cannot be resolved here and is printed as such.
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


def _dotted(node):
    """`a.b.c` as a string, or None when the target is not a plain name chain."""
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return None
    parts.append(node.id)
    return ".".join(reversed(parts))


def attr_swaps():
    """(line, target, [names]) for every `attrs(target, NAME=...)` in the battery."""
    src = open(BATTERY, encoding="utf-8").read()
    tree = ast.parse(src, filename=BATTERY)
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "attrs" and node.args):
            continue
        yield node.lineno, _dotted(node.args[0]), [k.arg for k in node.keywords]


def battery_namespace():
    """The battery's globals, so `dh.DoclingHeron` resolves the way it does there."""
    import importlib.util
    for d in (os.path.join(ROOT, "src"), os.path.join(ROOT, "tests")):
        if d not in sys.path:
            sys.path.insert(0, d)
    spec = importlib.util.spec_from_file_location("selfcheck", BATTERY)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["selfcheck"] = mod
    spec.loader.exec_module(mod)
    return vars(mod)


def check_attrs(show):
    """How many attrs() targets resolve and carry every name they swap."""
    ns = battery_namespace()
    ok = missing = local = 0
    for line, target, names in attr_swaps():
        if target is None:
            local += 1
            print(f"  NOT A NAME selfcheck.py:{line}: attrs() on a computed target")
            continue
        head = target.split(".")[0]
        if head not in ns:
            local += 1
            if show:
                print(f"  local    selfcheck.py:{line}: {target} is not a module-level name")
            continue
        obj = ns[head]
        try:
            for part in target.split(".")[1:]:
                obj = getattr(obj, part)
        except AttributeError as e:
            missing += 1
            print(f"  NO TARGET selfcheck.py:{line}: {target}: {e}")
            continue
        gone = [n for n in names if not hasattr(obj, n)]
        if gone:
            missing += 1
            print(f"  NO ATTR  selfcheck.py:{line}: {target} has no {', '.join(gone)}")
        else:
            ok += 1
            if show:
                print(f"  has      {target}: {', '.join(names)}")
    print(f"attrs {ok + missing + local}: resolve {ok}, do not resolve {missing}, "
          f"local {local}")
    return missing


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
    unresolved = check_attrs(show)
    return 1 if (missed or unresolved) else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
