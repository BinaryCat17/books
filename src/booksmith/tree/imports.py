"""The dependency rule, as a function the tests can ask.

The layers, bottom up: `core` imports nothing but `core`; `remote` and
`tree` import `core` and themselves; `processing` may not import
`datasets`; `datasets` may not import `cli`. Everything else is free until
its package exists. The rule is written here ONCE and enforced by
`tests/test_imports.py`, because the audit of 2026-09-06 found four
upward imports in a tree whose map said the layers were clean: the book
builder imported the reading metric (which imported the contour metric)
for one string function; the builder imported the detector for a hash; the
snapshot checker imported the builder; the reading contract imported the
swap layer. None of them was a bug in itself. Each of them was invisible.

    python3 -c "from booksmith.tree import imports; print(imports.violations())"
"""
import ast
import os

PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NAME = "booksmith"

# package -> the packages it may import (itself always). A package not listed
# is unconstrained. `remote` may be imported only by the packages in
# IMPORTERS_OF_REMOTE; that is the other half of the rule.
MAY_IMPORT = {
    "core": (),
    "remote": ("core",),
    "tree": ("core",),
    "processing": ("core", "remote"),
    "datasets": ("core", "processing"),
}
# `models` is here until step 3a of the plan moves the two rented-job specs
# (`models/paddleocr_vl`, `models/dots_ocr`) under `processing/*/rented/`.
IMPORTERS_OF_REMOTE = ("remote", "cli", "processing", "models")

# Modules and packages the plan has not placed yet. Importing one is allowed
# from anywhere until its step moves it; the tuple shrinks with each step
# and `tests/test_imports.py` demands that every name in it still exists at
# the top of the package, so a placed module cannot stay exempt by
# forgetfulness. Empty after step 3c.
UNPLACED = ("metrics", "text", "fitness", "overlay", "annopage", "subset",
            "synth", "books", "acceptance", "detect", "djvu", "models", "doc",
            "read", "cli")


def _module(path, root, name):
    rel = os.path.relpath(path, root)[:-3].split(os.sep)
    if rel[-1] == "__init__":
        rel = rel[:-1]
    mod = ".".join([name] + rel)
    pkg = mod if path.endswith("__init__.py") else mod.rsplit(".", 1)[0]
    return mod, pkg


def _resolve(node, pkg, name, known):
    """The modules an import statement names, against the tree in `known`.

    `from X import a, b` names `X.a` when that is a module of the tree, else
    `X`: the layer rule cares which PACKAGE is touched, and a function
    imported from a package touches that package.
    """
    if isinstance(node, ast.Import):
        return [a.name for a in node.names if a.name.split(".")[0] == name]
    if node.level == 0:
        if not (node.module and node.module.split(".")[0] == name):
            return []
        base = node.module
    else:
        up = pkg.split(".")
        if node.level > 1:
            up = up[:len(up) - (node.level - 1)]
        base = ".".join(up)
        if node.module:
            base = f"{base}.{node.module}"
    out = []
    for a in node.names:
        cand = f"{base}.{a.name}"
        out.append(cand if cand in known else base)
    return out


def _files(root):
    for d, dirs, files in os.walk(root):
        dirs[:] = [x for x in dirs if x != "__pycache__"]
        for fn in sorted(files):
            if fn.endswith(".py"):
                yield os.path.join(d, fn)


def edges(root=PKG, name=NAME):
    """(importer module, imported module, line) for every intra-package import."""
    files = list(_files(root))
    known = {_module(p, root, name)[0] for p in files}
    out = []
    for path in files:
        mod, pkg = _module(path, root, name)
        try:
            tree = ast.parse(open(path, encoding="utf-8").read())
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for target in _resolve(node, pkg, name, known):
                    out.append((mod, target, node.lineno))
    return out


def _top(mod, name):
    parts = mod.split(".")
    return parts[1] if len(parts) > 1 and parts[0] == name else ""


def violations(root=PKG, name=NAME):
    """Every import that crosses a layer the wrong way, one line each.

    One line per edge: the layer rule first, and the `remote` rule only for
    an edge the layer rule allowed, or every upward import into `remote`
    would be named twice and counted twice.
    """
    bad = []
    for importer, imported, line in edges(root, name):
        a, b = _top(importer, name), _top(imported, name)
        if not a or not b or a == b or b in UNPLACED:
            continue
        allowed = MAY_IMPORT.get(a)
        if allowed is not None and b not in allowed:
            bad.append(f"{importer}:{line} imports {imported}: {a} may import only "
                       f"{', '.join(allowed) or 'itself'}")
        elif b == "remote" and a not in IMPORTERS_OF_REMOTE:
            bad.append(f"{importer}:{line} imports {imported}: only "
                       f"{', '.join(IMPORTERS_OF_REMOTE)} may import remote")
    return bad
