"""Rename format names in the code, by position in the syntax tree.

WHY NOT `sed`. The same word is a dict key in one line and part of a sentence
printed to the operator in the next. `src/` holds 6039 Cyrillic string
literals; only 556 of them are keys. A textual replacement would rewrite the
report text along with the format, and the report text belongs to step 7, where
it moves together with the 226 assertions that read it.

WHAT COUNTS AS A KEY POSITION. Five, and they were found by reading the code
rather than assumed:

    {"ключ": v}                 a literal dict
    d["ключ"]                   a subscript, load or store
    d.get("ключ") / .setdefault / .pop
    "ключ" in d                 a membership test -- easy to forget, and it is
                                how `policy` and `synth` ask about a field
    {"ключ": v for ...}         a comprehension

Anything else -- an argument, a return value, a comparison, a log line -- is
left alone. The names that live as VALUES rather than keys are a separate job
with a separate map, because `текст` under `роль` is a class and `текст` under
`текст` is a page of a Russian book.

    python3 tools/migrate_code.py --dry     report, touch nothing
    python3 tools/migrate_code.py --apply   rewrite
"""
import ast
import collections
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAP = os.path.join(ROOT, "tools", "keymap.json")


def files():
    r = subprocess.run(["git", "ls-files", "-z", "*.py"],
                       capture_output=True, text=True, cwd=ROOT)
    return sorted(p for p in r.stdout.split("\0") if p)


def key_nodes(tree):
    """Every string constant standing in a key position, with its location."""
    out = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Dict):
            out += [k for k in n.keys
                    if isinstance(k, ast.Constant) and isinstance(k.value, str)]
        elif isinstance(n, ast.DictComp):
            if isinstance(n.key, ast.Constant) and isinstance(n.key.value, str):
                out.append(n.key)
        elif isinstance(n, ast.Subscript):
            if isinstance(n.slice, ast.Constant) and isinstance(n.slice.value, str):
                out.append(n.slice)
        elif isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) \
                and n.func.attr in ("get", "setdefault", "pop") and n.args \
                and isinstance(n.args[0], ast.Constant) \
                and isinstance(n.args[0].value, str):
            out.append(n.args[0])
        elif isinstance(n, ast.Compare):
            for op, right in zip(n.ops, n.comparators):
                if isinstance(op, (ast.In, ast.NotIn)) \
                        and isinstance(n.left, ast.Constant) \
                        and isinstance(n.left.value, str):
                    out.append(n.left)
    return out


def rewrite(src, keymap):
    """(new source, {old: count}). Edits by line and column, back to front.

    Rewriting the text rather than unparsing the tree: `ast.unparse` would
    reformat all 24 000 lines and lose every comment, and the comments are half
    of what this project is.

    COLUMN OFFSETS IN `ast` ARE BYTES, not characters. On a line holding
    Cyrillic every offset is roughly double what a character slice would want,
    so each line is cut in UTF-8 and decoded back. Sliced as characters, the
    first attempt indexed past the end of the line and crashed -- which was
    lucky: a shorter line would have silently cut a literal in half.
    """
    tree = ast.parse(src)
    edits = []
    for node in key_nodes(tree):
        new = keymap.get(node.value)
        if new is None or new == node.value:
            continue
        edits.append((node.lineno, node.col_offset, node.end_lineno,
                      node.end_col_offset, node.value, new))
    lines = src.split("\n")
    hits = collections.Counter()
    for lineno, col, end_lineno, end_col, old, new in sorted(edits, reverse=True):
        if lineno != end_lineno:
            continue                     # a multi-line literal is never a key
        raw = lines[lineno - 1].encode("utf-8")
        chunk = raw[col:end_col].decode("utf-8")
        if not chunk or chunk[0] not in "\"'" or old not in chunk:
            continue
        quote = chunk[0]
        lines[lineno - 1] = (raw[:col].decode("utf-8") + quote + new + quote
                             + raw[end_col:].decode("utf-8"))
        hits[old] += 1
    return "\n".join(lines), hits


def main(argv):
    keymap = json.load(open(MAP, encoding="utf-8"))
    apply_it = "--apply" in argv
    total = collections.Counter()
    touched = []
    for rel in files():
        path = os.path.join(ROOT, rel)
        src = open(path, encoding="utf-8").read()
        new_src, hits = rewrite(src, keymap)
        if not hits:
            continue
        ast.parse(new_src)               # never write source that will not parse
        touched.append((rel, sum(hits.values())))
        total.update(hits)
        if apply_it:
            open(path, "w", encoding="utf-8").write(new_src)
    for rel, n in sorted(touched, key=lambda t: -t[1]):
        print(f"  {n:>5}  {rel}")
    print(f"\nfiles {len(touched)}, names {len(total)}, "
          f"replacements {sum(total.values())}")
    if not apply_it:
        print("(dry run -- nothing written)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
