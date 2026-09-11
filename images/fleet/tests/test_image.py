import ast
import os
import re

import fleet

PKG = os.path.dirname(os.path.abspath(fleet.__file__))
IMAGE = os.path.dirname(PKG)
ROOT = os.path.dirname(os.path.dirname(IMAGE))
OTHERS = {"backend", "metrics", "layout", "vlm", "datasets"}


def _sources():
    for d in (PKG, os.path.join(IMAGE, "tests")):
        for dp, _, fs in os.walk(d):
            for f in fs:
                if f.endswith(".py"):
                    yield os.path.join(dp, f)


def test_nothing_is_imported_from_another_image():
    bad = []
    for p in _sources():
        with open(p, encoding="utf-8") as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else (
                [node.module] if isinstance(node, ast.ImportFrom) and node.module else [])
            bad += [f"{os.path.relpath(p, IMAGE)}: {n}" for n in names if n.split(".")[0] in OTHERS]
    assert not bad, bad


def test_every_path_the_readme_cites_exists():
    with open(os.path.join(IMAGE, "README.md"), encoding="utf-8") as f:
        cited = re.findall(r"`([^`\s]+/[^`\s]+)`", f.read())
    missing = [c for c in cited if "<" not in c and "{" not in c and not c.startswith(("/", "http", "~"))
               and not os.path.exists(os.path.join(IMAGE, c)) and not os.path.exists(os.path.join(ROOT, c))]
    assert not missing, missing
