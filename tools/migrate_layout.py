"""The package move, as a table and a script: what went where, and the record.

Step 1 of docs/plan.md moves the kernel under `booksmith.core` and the tree
instruments under `booksmith.tree`. A move by hand of ten modules and five
split ones, with 111 import statements in 43 files, 16 literal module
strings and paths in the battery and the tests, and five attribute swaps
that must follow their symbol, is not a move, it is a hundred and eighty
chances to leave one behind. So the table lives here,
the script applies it, and the table STAYS as the record of the rename, the
way `tools/keymap.json` records the key rename.

WHAT IT REWRITES.

* Every `from . import x` / `from ..y import z` in `src/`, resolved to an
  absolute name against the OLD package by ast, then mapped: a relative
  import changes meaning with the depth of the file, so it cannot be moved
  as text. Re-emitted ABSOLUTE (`from booksmith.core import knobs`): the
  layering is then visible in the import line itself.
* Every `from booksmith... import` in `tests/` and `tools/`.
* Split symbols: five modules give up names to `core` while the rest of the
  file stays (SYMBOLS below). `from booksmith.models.base import Block, Page,
  Recognizer` becomes two lines.
* Literal strings equal to an old module name (`one_line("booksmith.run.
  knobs", ...)`), an old src-relative path (`sources("otsl.py")`, `COPY`,
  `support.src_path(...)`) or an old repo path (`cyr.RESIDUE` keys).
* The battery's `attrs(alias, NAME=...)` for the four names whose symbol
  moved: the patch must land on the module that now OWNS the name, or the
  named check goes on passing over a mutation that reaches nothing.

WHAT IT DOES NOT DO, and was done by hand in the same commit: create the
new modules (`core/page.py`, `core/textnorm.py`, `core/book.py`,
`core/errors.py`, `core/log.py`, `tree/imports.py`), cut the moved symbols
out of their old files, fix the paths computed from `__file__` in the moved
files, replace `raise SystemExit` by `raise Refusal` and rebase the
per-module error classes, delete the seven hash copies, the four log copies,
the three `WeightsMissing` and synth's `commit()`, route the read path's
rendering through `raster.render`/`open_pdf`, rewrite `cli._tool_errors`
and add the usage-error exit code, re-key `cyr.RESIDUE`, and retarget the
attribute uses that tests make through a module alias (a second pass, by a
script that resolved each alias to its module and each name to its owner).
Running it again on the moved tree changes nothing (dry run: 0 imports, 0
strings, 0 moves).

    python3 tools/migrate_layout.py --step 2 --dry-run    print what would change
    python3 tools/migrate_layout.py --step 2              apply, with counts

STEP 2 (datasets) adds: the three metrics into `datasets/metrics/`, the
ink metric SPLIT (measurement to `processing/assess/ink.py`, the battery to
`datasets/metrics/fitness.py`), the bench builders into `datasets/make/`,
the overlay into `datasets/look.py`, the acceptance into
`datasets/accept.py`, and the `books` package under `datasets/make/`. The
wrapper classes step 2a wrote into `datasets/metrics/{contour,text,
fitness}.py` are merged into the moved files BY HAND after the script (the
script refuses to overwrite an existing file). The alias pass at the end is
what step 1 did by a second script: a name that moved is retargeted where a
test or the battery reaches it THROUGH A MODULE ALIAS (`fitness.mutations`
-> `fitmet.mutations`), because the import rewrite cannot see attribute
uses.
"""
import ast
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
PKG = os.path.join(SRC, "booksmith")

# Whole modules: old dotted name -> new dotted name, per step.
STEP1_MOVES = {
    "booksmith.run.knobs": "booksmith.core.knobs",
    "booksmith.run.stamp": "booksmith.core.stamp",
    "booksmith.run.replay": "booksmith.core.replay",
    "booksmith.policy": "booksmith.core.policy",
    "booksmith.order": "booksmith.core.order",
    "booksmith.otsl": "booksmith.core.otsl",
    "booksmith.schema": "booksmith.core.schema",
    "booksmith.config": "booksmith.core.config",
    "booksmith.doc.crop": "booksmith.core.raster",
    "booksmith.cyr": "booksmith.tree.cyr",
}
STEP2_MOVES = {
    "booksmith.metrics": "booksmith.datasets.metrics.contour",
    "booksmith.text": "booksmith.datasets.metrics.text",
    "booksmith.fitness": "booksmith.processing.assess.ink",
    "booksmith.overlay": "booksmith.datasets.look",
    "booksmith.acceptance": "booksmith.datasets.accept",
    "booksmith.annopage": "booksmith.datasets.make.annopage",
    "booksmith.subset": "booksmith.datasets.make.subset",
    "booksmith.synth": "booksmith.datasets.make.synth",
}
# Packages moved whole: every module under them follows.
STEP2_PACKAGES = {"booksmith.books": "booksmith.datasets.make.books"}

# Names that leave a module that otherwise stays or moves elsewhere:
# (old module, name) -> new module.
STEP1_SYMBOLS = {
    ("booksmith.models.base", "Block"): "booksmith.core.page",
    ("booksmith.models.base", "Page"): "booksmith.core.page",
    ("booksmith.models.base", "ours_order"): "booksmith.core.page",
    ("booksmith.models.base", "OUR_ORDER"): "booksmith.core.page",
    ("booksmith.doc.apply", "KINDS"): "booksmith.core.page",
    ("booksmith.text", "normalize"): "booksmith.core.textnorm",
    ("booksmith.text", "norm_note"): "booksmith.core.textnorm",
    ("booksmith.text", "bare_math"): "booksmith.core.textnorm",
    ("booksmith.text", "NORM"): "booksmith.core.textnorm",
    ("booksmith.text", "NORM_STEPS"): "booksmith.core.textnorm",
    ("booksmith.text", "NORM_REFUSED"): "booksmith.core.textnorm",
    ("booksmith.text", "REFUSED"): "booksmith.core.textnorm",
    ("booksmith.doc.html", "ASSETS"): "booksmith.core.book",
    ("booksmith.doc.html", "SOURCE"): "booksmith.core.book",
    ("booksmith.doc.html", "JOURNAL"): "booksmith.core.book",
    ("booksmith.doc.html", "journal_path"): "booksmith.core.book",
}
# The ink metric's battery follows the metric, its measurement the signal.
STEP2_SYMBOLS = {("booksmith.fitness", n): "booksmith.datasets.metrics.fitness"
                 for n in ("mutations", "_edit", "_scale", "_shift", "_offpage",
                           "_merge", "_double", "_at")}

# `attrs(alias, NAME=...)` in the battery, and `alias.NAME` anywhere in the
# tests, whose NAME moved with a symbol: (alias, name) -> the alias of the
# module that owns it now. The aliases on the right are added to the
# importing file.
STEP1_ATTRS = {
    ("mbase", "ours_order"): "page",
    ("ap", "KINDS"): "page",
    ("booktext", "bare_math"): "textnorm",
    ("dhtml", "journal_path"): "book",
}
STEP2_ATTRS = {(alias, n): "fitmet" for alias in ("fit", "fitness", "ink")
               for n in ("mutations", "_edit", "_scale", "_shift", "_offpage",
                         "_merge", "_double", "_at")}
ALIASES = {"page": "booksmith.core.page", "textnorm": "booksmith.core.textnorm",
           "book": "booksmith.core.book",
           "fitmet": "booksmith.datasets.metrics.fitness"}

STEPS = {1: (STEP1_MOVES, {}, STEP1_SYMBOLS, STEP1_ATTRS),
         2: (STEP2_MOVES, STEP2_PACKAGES, STEP2_SYMBOLS, STEP2_ATTRS)}
MOVES, PACKAGES, SYMBOLS, ATTR_RETARGET = STEP1_MOVES, {}, STEP1_SYMBOLS, STEP1_ATTRS
NEW_ALIASES = ALIASES


def use_step(n):
    """Point the module-level tables at one step's; packages expand to the
    modules under them, read from the tree."""
    global MOVES, PACKAGES, SYMBOLS, ATTR_RETARGET, PATH_MOVES, REPO_PATH_MOVES
    MOVES, PACKAGES, SYMBOLS, ATTR_RETARGET = STEPS[n]
    MOVES = dict(MOVES)
    for old, new in PACKAGES.items():
        d = os.path.join(SRC, *old.split("."))
        MOVES[old] = new
        for fn in sorted(os.listdir(d)) if os.path.isdir(d) else []:
            if fn.endswith(".py") and fn != "__init__.py":
                MOVES[f"{old}.{fn[:-3]}"] = f"{new}.{fn[:-3]}"
    # A package's bare directory name is NOT rewritten as a literal: "books"
    # is also the command's name (`prog="books"`, the repeat_command argv),
    # and the first run of step 2 turned five of those into a path. Only
    # `.py` paths and repository paths are literals anyone writes.
    PATH_MOVES = {rel_of(o): rel_of(n) for o, n in MOVES.items()
                  if rel_of(o).endswith(".py")}
    REPO_PATH_MOVES = {"src/booksmith/" + rel_of(o): "src/booksmith/" + rel_of(n)
                       for o, n in MOVES.items()}


def rel_of(mod):
    """`booksmith.doc.crop` -> `doc/crop.py`, the path tests and the battery use;
    a package maps to its directory."""
    if mod in PACKAGES or mod in PACKAGES.values():
        return os.path.join(*mod.split(".")[1:])
    return os.path.join(*mod.split(".")[1:]) + ".py"


PATH_MOVES = {rel_of(o): rel_of(n) for o, n in MOVES.items()}
REPO_PATH_MOVES = {"src/booksmith/" + o: "src/booksmith/" + n
                   for o, n in PATH_MOVES.items()}


def module_of(path):
    """The dotted name of a source file, and the package a relative import
    starts from (the file's package, or the package itself for __init__)."""
    rel = os.path.relpath(path, SRC)
    parts = rel[:-3].split(os.sep)
    if parts[-1] == "__init__":
        parts = parts[:-1]
        return ".".join(parts), ".".join(parts)
    return ".".join(parts), ".".join(parts[:-1])


def resolve(node, base_pkg):
    """The absolute module an ImportFrom names, against the OLD tree."""
    if node.level == 0:
        return node.module or ""
    up = base_pkg.split(".")
    if node.level > 1:
        up = up[:len(up) - (node.level - 1)]
    base = ".".join(up)
    return f"{base}.{node.module}" if node.module else base


def regroup(absmod, names):
    """(new module, [alias nodes]) groups for one ImportFrom, or None if unchanged."""
    groups, changed = {}, False
    for a in names:
        n = a.name
        if (absmod, n) in SYMBOLS:
            target, changed = SYMBOLS[(absmod, n)], True
            groups.setdefault(target, []).append(a)
        elif f"{absmod}.{n}" in MOVES:
            # `from .. import policy`: the NAME is a module that moved. Emit
            # it from its new parent under its new basename.
            new = MOVES[f"{absmod}.{n}"]
            parent, leaf = new.rsplit(".", 1)
            changed = True
            groups.setdefault(parent, []).append(
                ast.alias(name=leaf, asname=a.asname or (n if leaf != n else None)))
        elif absmod in MOVES:
            changed = True
            groups.setdefault(MOVES[absmod], []).append(a)
        else:
            groups.setdefault(absmod, []).append(a)
    return groups if changed else None


def emit(groups, indent):
    lines = []
    for mod, aliases in groups.items():
        names = ", ".join(a.name + (f" as {a.asname}" if a.asname else "")
                          for a in aliases)
        line = f"{indent}from {mod} import {names}"
        if len(line) > 79:
            inner = ",\n".join(f"{indent}    " + a.name +
                               (f" as {a.asname}" if a.asname else "")
                               for a in aliases)
            line = f"{indent}from {mod} import (\n{inner})"
        lines.append(line)
    return "\n".join(lines)


def rewrite_imports(path, is_src):
    """Rewrite the import statements of one file. Returns (text, count)."""
    text = open(path, encoding="utf-8").read()
    tree = ast.parse(text)
    _, base_pkg = module_of(path) if is_src else ("", "")
    src_lines = text.splitlines(keepends=True)
    edits = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        absmod = resolve(node, base_pkg) if is_src else (node.module or "")
        if not absmod.startswith("booksmith"):
            continue
        groups = regroup(absmod, node.names)
        if groups is None:
            continue
        first = src_lines[node.lineno - 1]
        indent = first[:len(first) - len(first.lstrip())]
        # A comment on the import line survives on the first emitted line.
        tail = ""
        last = src_lines[node.end_lineno - 1]
        if "#" in last and last.rstrip().endswith(last.split("#", 1)[1].rstrip()):
            tail = "  #" + last.split("#", 1)[1].rstrip()
        new = emit(groups, indent)
        if tail:
            head, *rest = new.split("\n")
            new = "\n".join([head + tail] + rest)
        edits.append((node.lineno, node.end_lineno, new + "\n"))
    for lineno, end, new in sorted(edits, reverse=True):
        src_lines[lineno - 1:end] = [new]
    return "".join(src_lines), len(edits)


def rewrite_strings(path):
    """Literal strings that name an old module or an old path, exactly."""
    text = open(path, encoding="utf-8").read()
    tree = ast.parse(text)
    edits = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
            continue
        v = node.value
        new = MOVES.get(v) or PATH_MOVES.get(v) or REPO_PATH_MOVES.get(v)
        if new is None:
            continue
        edits.append((node.lineno, node.col_offset, node.end_lineno,
                      node.end_col_offset, v, new))
    lines = text.splitlines(keepends=True)
    for lineno, col, end_lineno, end_col, old, new in sorted(edits, reverse=True):
        assert lineno == end_lineno, (path, lineno, old)
        ln = lines[lineno - 1]
        seg = ln[col:end_col]
        assert old in seg, (path, lineno, seg)
        lines[lineno - 1] = ln[:col] + seg.replace(old, new) + ln[end_col:]
    return "".join(lines), len(edits)


def retarget_attrs(text):
    """`attrs(mbase, ours_order=` -> `attrs(page, ours_order=`, and every
    `alias.NAME` use, for the names whose owner changed."""
    import re
    n = 0
    for (alias, name), new in ATTR_RETARGET.items():
        for old, rep in ((f"attrs({alias}, {name}=", f"attrs({new}, {name}="),):
            c = text.count(old)
            if c:
                text = text.replace(old, rep)
                n += c
        pat = rf"(?<![\w.]){re.escape(alias)}\.{name}\b"
        c = len(re.findall(pat, text))
        if c:
            text = re.sub(pat, f"{new}.{name}", text)
            n += c
    return text, n


def add_aliases(path, text):
    """Import lines for the aliases the retargeted uses need, after the
    file's import block (or after `import support` in a test)."""
    import re
    needed = [a for a in NEW_ALIASES
              if re.search(rf"(?<![\w.]){a}\.", text)
              and not re.search(rf"^\s*from {re.escape(NEW_ALIASES[a].rsplit('.', 1)[0])} import .*\b{a}\b", text, re.M)
              and not re.search(rf"^\s*import .*\bas {a}\b", text, re.M)]
    if not needed:
        return text
    lines = "".join(f"from {NEW_ALIASES[a].rsplit('.', 1)[0]} import {NEW_ALIASES[a].rsplit('.', 1)[1]}"
                    + (f" as {a}" if NEW_ALIASES[a].rsplit('.', 1)[1] != a else "") + "\n"
                    for a in needed)
    m = re.search(r"^import support[^\n]*\n", text, re.M)
    if m:
        return text[:m.end()] + lines + text[m.end():]
    tree = ast.parse(text)
    last = 0
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            last = node.end_lineno
        elif last and not isinstance(node, ast.Expr):
            break
    src = text.splitlines(keepends=True)
    src.insert(last, lines)
    return "".join(src)


def add_battery_imports(text):
    """The new aliases the retargeted patches need, after the old import block."""
    import re
    m = re.search(r"^from booksmith import acceptance[^\n]*\n", text, re.M)
    assert m, "the battery's import block has moved; find its last line"
    extra = "".join(f"from {mod.rsplit('.', 1)[0]} import {alias}\n"
                    for alias, mod in NEW_ALIASES.items()
                    if re.search(rf"^from booksmith\.core import {alias}$", text, re.M) is None)
    return text[:m.end()] + extra + text[m.end():]


def py_files(root):
    for d, dirs, files in os.walk(root):
        dirs[:] = [x for x in dirs if x != "__pycache__"]
        for f in sorted(files):
            if f.endswith(".py"):
                yield os.path.join(d, f)


def git_mv(old, new, dry):
    os.makedirs(os.path.dirname(new), exist_ok=True)
    if dry:
        print(f"  mv {os.path.relpath(old, ROOT)} -> {os.path.relpath(new, ROOT)}")
        return
    subprocess.run(["git", "-C", ROOT, "mv", old, new], check=True)


def main(argv):
    dry = "--dry-run" in argv
    step = int(argv[argv.index("--step") + 1]) if "--step" in argv else max(STEPS)
    use_step(step)
    counts = {"imports": 0, "strings": 0, "files": 0, "moves": 0, "attrs": 0}
    # 1. rewrite imports and strings in place, BEFORE moving (module_of() reads
    #    the old layout), then move the files.
    for root, is_src in ((PKG, True), (os.path.join(ROOT, "tests"), False),
                         (os.path.join(ROOT, "tools"), False)):
        for path in py_files(root):
            if os.path.abspath(path) == os.path.abspath(__file__):
                continue
            text, n_imp = rewrite_imports(path, is_src)
            if n_imp and not dry:
                open(path, "w", encoding="utf-8").write(text)
            text2, n_str = rewrite_strings(path)
            if n_str and not dry:
                open(path, "w", encoding="utf-8").write(text2)
            # 2. attribute uses through an alias, for the split names
            text3 = open(path, encoding="utf-8").read() if not dry else text2
            text4, n_att = retarget_attrs(text3)
            if n_att:
                text4 = add_aliases(path, text4)
                counts["attrs"] += n_att
                if not dry:
                    open(path, "w", encoding="utf-8").write(text4)
            if n_imp or n_str or n_att:
                counts["files"] += 1
                counts["imports"] += n_imp
                counts["strings"] += n_str
                if dry:
                    print(f"  {os.path.relpath(path, ROOT)}: imports {n_imp}, "
                          f"strings {n_str}, attrs {n_att}")
    # 3. move packages, then modules
    for old, new in PACKAGES.items():
        o = os.path.join(SRC, *old.split("."))
        nw = os.path.join(SRC, *new.split("."))
        if os.path.isdir(o):
            git_mv(o, nw, dry)
            counts["moves"] += 1
    for old, new in MOVES.items():
        if old in PACKAGES or any(old.startswith(p + ".") for p in PACKAGES):
            continue
        o = os.path.join(SRC, *old.split(".")) + ".py"
        nw = os.path.join(SRC, *new.split(".")) + ".py"
        if os.path.exists(o):
            if os.path.exists(nw):
                raise SystemExit(f"refusing to overwrite {nw}: move it aside first")
            git_mv(o, nw, dry)
            counts["moves"] += 1
    for pkg in {new.split(".")[1] for new in MOVES.values()} | {"core", "tree"}:
        for sub in (pkg,) + tuple(
                ".".join(n.split(".")[1:-1]) for n in MOVES.values()
                if n.split(".")[1] == pkg and len(n.split(".")) > 3):
            d = os.path.join(PKG, *sub.split("."))
            init = os.path.join(d, "__init__.py")
            if os.path.isdir(d) and not os.path.exists(init) and not dry:
                open(init, "w").write("")
                subprocess.run(["git", "-C", ROOT, "add", init], check=True)
    print(f"migrate_layout step {step}:", ", ".join(f"{k} {v}" for k, v in counts.items()),
          "(dry run)" if dry else "")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
