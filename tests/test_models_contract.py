"""The adapter contract is compared with the pipeline, not believed.

WHY THIS FILE EXISTS. `models.base.Recognizer` said "exactly two things" and
declared five members while `detect.py` asked for eight. The four it did not
declare -- `dir`, `labels`, `policy_name`, `threshold_drift` -- have no default
anywhere, so an adapter written to the contract as documented would import
cleanly and fall at the first run, on the money path for any model that needs
renting.

A contract nobody compares is prose. The comparison is mechanical here: the
names come from the CODE that uses them and the declaration comes from the
class, so it fails whichever side moves.
"""
import ast
import os

import support
from booksmith.models import base

# Adapters we ship. Named explicitly: a new one lands here deliberately or not
# at all, which is the same rule `subset.TRAITS` follows.
ADAPTERS = (("doclayout.py", "DocLayout"),
            ("docling_heron.py", "DoclingHeron"),
            ("docling_heron.py", "DoclingEgret"),
            ("yolox_layout.py", "YoloXLayout"))


def _asked_of(var, rel):
    """Every attribute the named local is asked for in that source file."""
    src = open(os.path.join(support.SRC, rel), encoding="utf-8").read()
    return {n.attr for n in ast.walk(ast.parse(src))
            if isinstance(n, ast.Attribute)
            and isinstance(n.value, ast.Name) and n.value.id == var}


def _declared():
    return {n for n in vars(base.Recognizer) if not n.startswith("__")}


def test_the_contract_declares_everything_the_pipeline_asks_for():
    """Direction one: the pipeline may ask for nothing undeclared.

    This is the direction that was broken, and it is broken silently: Python
    binds an instance attribute happily, so an adapter that happens to set
    `dir` works and one that does not fails at the line that prints the log.
    """
    asked = _asked_of("det", "detect.py")
    assert asked, "nothing is asked of `det` in detect.py -- the search broke"
    missing = sorted(asked - _declared())
    assert not missing, (
        f"detect.py asks an adapter for {missing}, and `Recognizer` declares "
        f"none of them. An adapter written to the contract would import and "
        f"then fall at the first run")


def test_the_contract_declares_nothing_nobody_asks_for():
    """The other direction: a member no caller wants is a name gone stale.

    Looked for across the whole package rather than in `detect.py` alone --
    `label_map` is read by the metrics and by the adapters' own fingerprints,
    not by the pipeline.
    """
    used = set()
    for root, _, files in os.walk(support.SRC):
        for fn in files:
            if not fn.endswith(".py"):
                continue
            src = open(os.path.join(root, fn), encoding="utf-8").read()
            used |= {n.attr for n in ast.walk(ast.parse(src))
                     if isinstance(n, ast.Attribute)}
    idle = sorted(n for n in _declared() if n not in used)
    assert not idle, (
        f"`Recognizer` declares {idle}, which nothing in the package reads. "
        f"A contract term nobody asks for is a name that outlived its use")


def test_every_adapter_we_ship_satisfies_the_contract():
    """And the adapters keep it -- by behaviour, not by inheritance.

    `issubclass` proves nothing here: every member with a default is inherited
    whether or not the adapter meant it. What is asked is that the four with
    NO default are actually implemented.
    """
    import importlib
    must = sorted(n for n in _declared()
                  if callable(getattr(base.Recognizer, n, None))
                  and getattr(base.Recognizer, n).__doc__ is not None)
    for rel, cls_name in ADAPTERS:
        mod = importlib.import_module(
            "booksmith.models." + rel[:-3])
        cls = getattr(mod, cls_name, None)
        assert cls is not None, f"{rel} no longer defines {cls_name}"
        assert issubclass(cls, base.Recognizer), (
            f"{cls_name} is not a Recognizer at all")
        for name in must:
            own = any(name in vars(k) for k in cls.__mro__
                      if k is not base.Recognizer)
            assert own, (
                f"{cls_name} does not implement {name!r}: it inherits the "
                f"contract's own version, which either raises or answers for "
                f"a model it knows nothing about")
