"""Did that edit touch only prose? Compare the code, ignoring what people read.

WHY THIS EXISTS. The translation moves 570 000 characters of comments and
docstrings, in files up to 2000 lines. The runner will catch a change that
breaks behaviour, but not one that quietly drops a branch, reorders arguments
or loses a default while a file is being rewritten around it -- those show up
as a failing test only if a test happens to cover that line, and coverage here
is 261 checks over 24 000 lines.

WHAT IT COMPARES. Both versions are parsed, every docstring is replaced by a
single marker, and the syntax trees are dumped and compared. Comments never
reach the tree at all. So:

    prose changed, code identical   -> SAME
    one operand swapped anywhere    -> DIFFERENT, with the first divergence

It does not care about line numbers, blank lines or wrapping, which is what
makes it usable on a file that has just been reflowed.

    python3 tools/prose_only.py <old-file> <new-file>
    python3 tools/prose_only.py --against <git-ref> <path> [<path> ...]
"""
import ast
import subprocess
import sys


def skeleton(src: str) -> str:
    """The tree with every docstring blanked. Comments are absent by nature."""
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)) and node.body:
            first = node.body[0]
            if (isinstance(first, ast.Expr)
                    and isinstance(first.value, ast.Constant)
                    and isinstance(first.value.value, str)):
                first.value.value = "<docstring>"
    return ast.dump(tree, indent=1)


def first_difference(a: str, b: str) -> str:
    la, lb = a.split("\n"), b.split("\n")
    for i, (x, y) in enumerate(zip(la, lb)):
        if x != y:
            return f"line {i} of the dump:\n  was: {x.strip()}\n  now: {y.strip()}"
    return f"one dump is longer: {len(la)} vs {len(lb)} lines"


def compare(old_src: str, new_src: str):
    try:
        a, b = skeleton(old_src), skeleton(new_src)
    except SyntaxError as e:
        return False, f"does not parse: {e}"
    if a == b:
        return True, "code identical, prose only"
    return False, first_difference(a, b)


def main(argv):
    if "--against" in argv:
        i = argv.index("--against")
        ref, paths = argv[i + 1], argv[i + 2:]
        bad = 0
        for path in paths:
            old = subprocess.run(["git", "show", f"{ref}:{path}"],
                                 capture_output=True, text=True)
            if old.returncode:
                print(f"  NEW      {path}")
                continue
            same, why = compare(old.stdout, open(path, encoding="utf-8").read())
            print(f"  {'SAME    ' if same else 'DIFFERENT'} {path}"
                  + ("" if same else f"\n      {why}"))
            bad += not same
        print(f"\nfiles whose code changed: {bad}")
        return 1 if bad else 0
    if len(argv) != 2:
        print(__doc__)
        return 2
    same, why = compare(open(argv[0], encoding="utf-8").read(),
                        open(argv[1], encoding="utf-8").read())
    print(("SAME: " if same else "DIFFERENT: ") + why)
    return 0 if same else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
