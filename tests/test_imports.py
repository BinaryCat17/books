"""The dependency rule holds, and the instrument that says so can fail.

`booksmith.tree.imports` reads every import in the package and names the
ones that cross a layer upward. The rule is in that file; this check runs it
against the tree and, separately, against a planted violation, so that a
resolver that silently sees nothing cannot pass as a clean tree.
"""
import os
import tempfile

from booksmith.tree import imports


def test_the_tree_has_no_upward_import():
    bad = imports.violations()
    assert not bad, "\n".join(bad)


def test_the_tree_has_edges_at_all():
    """A resolver that finds no import at all would report a clean tree."""
    e = imports.edges()
    assert len(e) > 50, len(e)
    assert any(t.startswith("booksmith.core.") for _, t, _ in e)


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
        bad = imports.violations(root)
    assert len(bad) == 2, bad
    assert any("core.a:1" in b and "may import only itself" in b for b in bad), bad
    assert any("datasets.m:1" in b and "may import only core, processing" in b
               for b in bad), bad


def test_the_remote_rule_names_an_importer_outside_its_list():
    with tempfile.TemporaryDirectory() as tmp:
        root = _plant(tmp, {
            "__init__.py": "",
            "remote/__init__.py": "",
            "remote/vast.py": "",
            "elsewhere/__init__.py": "",
            "elsewhere/x.py": "from booksmith.remote.vast import Vast\n",
        })
        bad = imports.violations(root)
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
        e = {(a, b) for a, b, _ in imports.edges(root)}
    assert ("booksmith.processing.read.driver", "booksmith.core.page") in e, e
    assert ("booksmith.processing.read.driver", "booksmith.processing.read") in e, e
    assert ("booksmith.processing.read", "booksmith.processing.read.driver") in e, e
