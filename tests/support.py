"""Shared by the checks: where the sources are, source as a tree, loud skips.

The checks here pin down AGREEMENTS BETWEEN FILES -- places where two files
agreed and the agreement is written nowhere. Neither types nor reading one
file catches that: the word "ours" in `models/*.py` decides whether
`metrics.py` prints a percentage or says NOT COMPARED, and each file looks
sound alone.

Hence source read as a tree. It is needed where the value of an agreement is
baked into a literal inside a method and cannot be had by running, short of
raising 214 MB of model. The tree sees what a person sees, not what a stub
returns.

A SKIP IS DECLARED OUT LOUD AND WITH A REASON. A zero from a check and a zero
from not understanding are different zeros: the runner prints skips as a
separate number, not added to the passed.
"""
import ast
import os
import sys

# The source directory. From here, not from cwd: otherwise a check run from
# another directory would silently find no adapter and be green on nothing.
SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "src", "booksmith")

# The key by which an adapter tells the metric WHOSE order it returned.
ORDER_KEY = "reading_order"


class Skip(Exception):
    """Nothing to run the check with. A reason is mandatory."""


# Who is running the checks. Set by the RUNNER itself (`tests/run.py` at
# start), not from here: asking "is pytest importable" instead of "is it
# running" has already cost a run. Measured (a fake `pytest` in `sys.modules`
# with the real contract -- `Skipped(BaseException)` and `skip()`): before the
# fix the first skip under our runner went past the `run_case` catches and
# killed the whole run -- the line «проверок 111: прошло …» was not printed AT
# ALL, so 110 passing checks vanished with one skip. There is no pytest in
# `.venv` now, and the trouble sleeps.
OWN_RUNNER = False


def skip(reason: str):
    """A skip with a reason. Under pytest -- its own, so any runner will do.

    The choice is by WHO IS RUNNING, not by what is installed. Both signs are
    read at once: our runner declares itself in `OWN_RUNNER`, and pytest, if
    it really works, is by now in `sys.modules` -- it imports itself before
    any check. The pytest import is gone from here: it turned "pytest is
    installed" into "pytest is running".
    """
    pt = sys.modules.get("pytest")
    if pt is not None and not OWN_RUNNER:
        pt.skip(reason)
    raise Skip(reason)


def foreign_skip(e) -> bool:
    """A skip declared by a FOREIGN runner: `pytest.skip()`.

    It lives NEXT TO `Skip`, not in the runner, because it is one thought:
    what counts as a skip. Two homes mean two copies of one agreement -- the
    kind that drift apart silently (the reading-order guard already drifted
    so, by letter case).

    The separate branch is needed for this: pytest's `Skipped` inherits
    BaseException, not Exception, and passes THROUGH the runner's ordinary
    catches, KILLING the run. Measured with a fake module of the same
    contract: under our runner one skip -- and the line «проверок 111: прошло
    110, …» was not printed at all, exit code 1 from a traceback.

    The type is taken FROM pytest, not by class name: `Skipped` may name a
    foreign exception, and a failure would then travel into the skips. Both
    places pytest keeps it are asked: `pytest.skip.Exception` (set by the
    `_with_exception` decorator) and `pytest.Skipped`.
    """
    pt = sys.modules.get("pytest")
    if pt is None:
        return False
    for cls in (getattr(getattr(pt, "skip", None), "Exception", None),
                getattr(pt, "Skipped", None)):
        if isinstance(cls, type) and isinstance(e, cls):
            return True
    return False


class Unresolved(RuntimeError):
    """The value is in the source, and the tree could not work it out.

    Silence is not allowed: an uncomputed value is NOT "no values", and
    passing it off as an empty set would report a zero from not understanding.
    """


def src_path(rel: str) -> str:
    p = os.path.join(SRC, rel)
    if not os.path.isfile(p):
        raise AssertionError(f"нет исходника {rel} (искали в {SRC})")
    return p


def tree(rel: str) -> ast.Module:
    with open(src_path(rel), encoding="utf-8") as f:
        return ast.parse(f.read(), filename=rel)


def _dotted(node) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return _dotted(node.value) + "." + node.attr
    raise Unresolved(f"не имя и не поле: {ast.dump(node)[:80]}")


def _lookup(module, dotted: str):
    obj = module
    for part in dotted.split("."):
        obj = getattr(obj, part, None)
        if obj is None:
            raise Unresolved(f"{dotted}: в модуле {module.__name__} такого нет")
    return obj


def _values(node, module) -> set:
    """What the right-hand side of `"reading_order": …` can expand into."""
    if isinstance(node, ast.Constant):
        return {node.value}
    if isinstance(node, ast.IfExp):
        return _values(node.body, module) | _values(node.orelse, module)
    if isinstance(node, ast.Subscript):
        obj = _lookup(module, _dotted(node.value))
        if isinstance(obj, dict):
            return set(obj.values())
        raise Unresolved(f"{_dotted(node.value)} — не словарь, а {type(obj)}")
    # CONCATENATION. `order.WORDS[which] + ": the model gives no rank"`: the
    # rule comes from the shared dictionary and the adapter appends the tail.
    # Expanded into a product -- every left value with every right one --
    # or the guard would see half the string and miss a swap of the other half.
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = _values(node.left, module), _values(node.right, module)
        return {a + b for a in left for b in right}
    raise Unresolved(
        f"значение «{ORDER_KEY}» вычислить не удалось: {ast.dump(node)[:120]}. "
        f"Это НЕ «значений нет» — допиши разбор в support._values.")


def _walk_but_fingerprint(node):
    """The whole tree except the bodies of `fingerprint()`.

    There the same field carries other values (`None` where a page's meta
    carries words), lawfully: the fingerprint is read by a person and by the
    snapshot, the metric's guard reads the meta of the PAGE. Mixing them would
    check an agreement that does not exist.
    """
    if isinstance(node, ast.FunctionDef) and node.name == "fingerprint":
        return
    yield node
    for child in ast.iter_child_nodes(node):
        yield from _walk_but_fingerprint(child)


def page_order_values(rel: str, module) -> set:
    """Every value of `meta["reading_order"]` an adapter puts INTO A PAGE.

    From the source, not from a run: by running one must raise three models
    and detect a page with each, while the agreement is checked in
    milliseconds, on every change.
    """
    out = set()
    for node in _walk_but_fingerprint(tree(rel)):
        if not isinstance(node, ast.Dict):
            continue
        for k, v in zip(node.keys, node.values):
            if isinstance(k, ast.Constant) and k.value == ORDER_KEY:
                out |= _values(v, module)
    return out


def meta_keys(rel: str, cls: str, method: str = "read") -> list:
    """The order of keys in `meta=` at the `Page(...)` call inside a method.

    Not cosmetics: with the knob off the page must come out BYTE FOR BYTE as
    before the pipeline appeared, and json writes keys in dictionary order.
    `**name` comes back as the string `**name`.
    """
    for node in ast.walk(tree(rel)):
        if not (isinstance(node, ast.ClassDef) and node.name == cls):
            continue
        for fn in node.body:
            if not (isinstance(fn, ast.FunctionDef) and fn.name == method):
                continue
            for call in ast.walk(fn):
                if not isinstance(call, ast.Call):
                    continue
                if getattr(call.func, "id", None) != "Page":
                    continue
                for kw in call.keywords:
                    if kw.arg != "meta" or not isinstance(kw.value, ast.Dict):
                        continue
                    keys = []
                    for k, v in zip(kw.value.keys, kw.value.values):
                        if k is None:
                            keys.append("**" + _dotted(v))
                        elif isinstance(k, ast.Constant):
                            keys.append(k.value)
                        else:
                            raise Unresolved(f"ключ meta не литерал в {rel}")
                    return keys
    raise AssertionError(f"{rel}: не нашли Page(meta=…) в {cls}.{method}")
