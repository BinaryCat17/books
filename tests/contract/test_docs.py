"""The documents: every cited path exists, generated files are current, prose
carries no measurement, and the rules name symbols that exist."""
import glob
import os
import re

import pytest

from booksmith import cli
from booksmith.core import config
from booksmith.datasets import docsgen

ROOT = config.ROOT
TOPS = ("src/", "docs/", "tests/", "tools/", "bench/", "infra/", ".github/", "results/")


def _documents():
    docs = ["CLAUDE.md", "README.md"] + sorted(
        os.path.relpath(p, ROOT) for p in glob.glob(os.path.join(ROOT, "docs", "*.md")))
    if os.path.isfile(os.path.join(ROOT, "METRICS.md")):
        docs.append("METRICS.md")
    return docs


def _prose():
    return [d for d in _documents() if d not in docsgen.GENERATED]


def _text(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


def _cited(text):
    out = set()
    for token in re.findall(r"`([^`\s]+)`", text):
        token = token.rstrip(".,;:").split(":")[0]
        if "*" in token or "<" in token:
            continue
        if token.startswith(TOPS) or (token.endswith(".md") and "/" not in token):
            out.add(token)
    return out


def test_every_path_a_document_cites_exists():
    gone = {}
    for rel in _documents():
        missing = sorted(p for p in _cited(_text(rel))
                         if not os.path.exists(os.path.join(ROOT, p)))
        if missing:
            gone[rel] = missing
    assert not gone, f"documents point at files that do not exist: {gone}"


def test_source_comments_cite_no_missing_document():
    pat = re.compile(r"(?:docs/[\w./-]+\.md|bench/README\.md|CLAUDE\.md|README\.md|METRICS\.md)")
    gone = {}
    for top in ("src", "tests", "tools"):
        for path in glob.glob(os.path.join(ROOT, top, "**", "*.py"), recursive=True):
            with open(path, encoding="utf-8") as f:
                text = f.read()
            missing = sorted({m for m in pat.findall(text)
                              if not os.path.exists(os.path.join(ROOT, m))})
            if missing:
                gone[os.path.relpath(path, ROOT)] = missing
    assert not gone, f"source cites documents that do not exist: {gone}"


# A measurement: a number of four or more digits, a grouped thousand, a
# decimal, a percentage, or a dollar amount. Digits inside a word stay.
MEASUREMENT = re.compile(
    r"(?<![\w.])(?:\d{4,}|\d{1,3}(?:[ ,]\d{3})+|\d+\.\d+|\d+(?:\.\d+)? ?%)(?![\w.])|\$\d")


def test_prose_documents_carry_no_measurement():
    found = {}
    for rel in _prose():
        hits = [m.group(0) for m in MEASUREMENT.finditer(_text(rel))]
        if hits:
            found[rel] = hits
    assert not found, (
        f"measurements in prose: {found}. A number lives in results/ and is "
        f"rendered into METRICS.md; prose points at it")


def test_generated_documents_are_current():
    stale = []
    for rel, want in docsgen.render_all(cli.build_parser()).items():
        path = os.path.join(ROOT, rel)
        if not os.path.isfile(path) or _text(rel) != want:
            stale.append(rel)
    assert not stale, f"regenerate with `books docs`: {stale}"


def test_the_metrics_report_is_current():
    from booksmith.core.errors import Refusal
    from booksmith.datasets import report
    try:
        want = report.build(log=lambda *a: None)
    except Refusal as e:
        pytest.skip(f"nothing rendered: {str(e)[:80]}")
    assert os.path.isfile(report.OUT), "METRICS.md is missing: `books bench report` writes it"
    assert _text("METRICS.md") == want, "METRICS.md is not what the records render to: `books bench report`"


def _defines(src, symbol):
    """Does the module define `symbol`, with `Class.method` matched as a member?"""
    import ast
    tree = ast.parse(src)
    parts = symbol.split(".")
    scope = tree.body
    for i, name in enumerate(parts):
        node = next((n for n in scope if isinstance(
            n, (ast.FunctionDef, ast.ClassDef)) and n.name == name), None)
        if node is None:
            if i == len(parts) - 1 and any(
                    isinstance(n, ast.Assign) and any(
                        isinstance(t, ast.Name) and t.id == name for t in n.targets)
                    for n in scope):
                return True
            return False
        scope = node.body
    return True


def test_the_rules_name_symbols_that_exist():
    pat = re.compile(r"`((?:src|tests|tools)/[\w./-]+\.py)(?::([\w.]+))?`")
    bad = []
    for path, symbol in pat.findall(_text("docs/rules.md")):
        full = os.path.join(ROOT, path)
        if not os.path.isfile(full):
            bad.append(path)
        elif symbol and not _defines(open(full, encoding="utf-8").read(), symbol):
            bad.append(f"{path}:{symbol}")
    assert not bad, f"rules name symbols that do not exist: {bad}"


def test_the_help_names_every_command_and_no_other():
    parser = cli.build_parser()
    real = {name for name, _ in docsgen._subparsers(parser)}
    top = {name for name in real if " " not in name}
    phrases = re.findall(r"books ([a-z]+)(?: ([a-z]+))?", cli.__doc__)
    offered_top = {a for a, _ in phrases}
    offered = offered_top | {f"{a} {b}" for a, b in phrases if f"{a} {b}" in real}
    assert real - offered == set(), f"commands missing from `books --help`: {sorted(real - offered)}"
    assert offered_top - top == set(), f"`books --help` offers what does not exist: {sorted(offered_top - top)}"
