"""The dependency rule holds, and the walker that says so can fail.

The rule is `src/booksmith/core/layers.py`; the walk over the tree is here,
run against the real package and against planted violations, so that a
resolver which silently sees nothing cannot pass as a clean tree.
"""
import ast
import os
import tempfile

from booksmith.core import layers

PKG = os.path.dirname(os.path.dirname(os.path.abspath(layers.__file__)))
NAME = "booksmith"


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

    The layer rule first, and the `remote` rule only for an edge the layer
    rule allowed, or every upward import into `remote` would be named twice
    and counted twice.
    """
    bad = []
    for importer, imported, line in edges(root, name):
        a, b = _top(importer, name), _top(imported, name)
        if not a or not b or a == b:
            continue
        allowed = layers.MAY_IMPORT.get(a)
        if allowed is not None and b not in allowed:
            bad.append(f"{importer}:{line} imports {imported}: {a} may import only "
                       f"{', '.join(allowed) or 'itself'}")
        elif b == "remote" and a not in layers.IMPORTERS_OF_REMOTE:
            bad.append(f"{importer}:{line} imports {imported}: only "
                       f"{', '.join(layers.IMPORTERS_OF_REMOTE)} may import remote")
    return bad


def test_the_tree_has_no_upward_import():
    bad = violations()
    assert not bad, "\n".join(bad)


def test_the_tree_has_edges_at_all():
    """A resolver that finds no import at all would report a clean tree."""
    e = edges()
    assert len(e) > 50, len(e)
    assert any(t.startswith("booksmith.core.") for _, t, _ in e)


def test_the_table_names_every_package_that_exists():
    """A package absent from the table is unconstrained, and in silence."""
    top = set()
    for n in os.listdir(PKG):
        if n.endswith(".py") and n != "__init__.py":
            top.add(n[:-3])
        elif os.path.isfile(os.path.join(PKG, n, "__init__.py")):
            top.add(n)
    assert top == set(layers.MAY_IMPORT), (
        f"on disk {sorted(top)}, in the table {sorted(layers.MAY_IMPORT)}")


def _plant(tmp, files):
    root = os.path.join(tmp, "booksmith")
    for rel, text in files.items():
        p = os.path.join(root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)
    return root


def test_a_planted_upward_import_is_named():
    with tempfile.TemporaryDirectory() as tmp:
        root = _plant(tmp, {
            "__init__.py": "",
            "core/__init__.py": "",
            "core/a.py": "from booksmith.remote import vast\n",
            "remote/__init__.py": "",
            "remote/vast.py": "",
            "datasets/__init__.py": "",
            "datasets/m.py": "from ..remote import vast\n",
        })
        bad = violations(root)
    assert len(bad) == 2, bad
    assert any("core.a:1" in b and "may import only itself" in b for b in bad), bad
    assert any("datasets.m:1" in b and "may import only core, processing" in b
               for b in bad), bad


def test_an_import_of_the_command_line_from_below_is_named():
    """`cli` may reach every package; no package may reach `cli`.

    An exemption stood here for the modules the plan had not placed. It faced
    the imported side, so `core` importing one of them passed.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = _plant(tmp, {
            "__init__.py": "",
            "core/__init__.py": "",
            "core/k.py": "from booksmith import cli\n",
            "cli.py": "",
            "datasets/__init__.py": "",
            "datasets/m.py": "from booksmith import cli\n",
        })
        bad = violations(root)
    assert len(bad) == 2, bad
    assert any("core.k:1" in b for b in bad), bad
    assert any("datasets.m:1" in b for b in bad), bad


def test_the_remote_rule_names_an_importer_outside_its_list():
    with tempfile.TemporaryDirectory() as tmp:
        root = _plant(tmp, {
            "__init__.py": "",
            "remote/__init__.py": "",
            "remote/vast.py": "",
            "elsewhere/__init__.py": "",
            "elsewhere/x.py": "from booksmith.remote.vast import Vast\n",
        })
        bad = violations(root)
    assert len(bad) == 1 and "may import remote" in bad[0], bad


def test_relative_imports_resolve_by_depth():
    with tempfile.TemporaryDirectory() as tmp:
        root = _plant(tmp, {
            "__init__.py": "",
            "core/__init__.py": "",
            "core/page.py": "",
            "processing/__init__.py": "",
            "processing/read/__init__.py": "from . import driver\n",
            "processing/read/driver.py": "from ...core import page\nfrom ..read import Ask\n",
        })
        e = {(a, b) for a, b, _ in edges(root)}
    assert ("booksmith.processing.read.driver", "booksmith.core.page") in e, e
    assert ("booksmith.processing.read.driver", "booksmith.processing.read") in e, e
    assert ("booksmith.processing.read", "booksmith.processing.read.driver") in e, e


def test_the_root_package_imports_nothing():
    """`import booksmith` is invisible to the resolver (the root has no top
    package), so the root must stay empty of imports: `stamp.commit` does
    exactly that import to find the package on disk, and a root that pulled
    in, say, the renting client would make every command import it."""
    src = open(os.path.join(PKG, "__init__.py"), encoding="utf-8").read()
    tree = ast.parse(src)
    bad = [n.lineno for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))]
    assert not bad, f"booksmith/__init__.py imports at lines {bad}"


def test_nothing_imports_the_command_line():
    """A package importing `cli` would reach every other one through it."""
    importers = sorted({a for a, b, _ in edges() if b.startswith("booksmith.cli")})
    assert not importers, importers
