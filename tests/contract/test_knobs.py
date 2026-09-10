"""The knob registry: what is not declared is not read, and the reverse.

The project rule -- a knob absent from `core/knobs.py` never reaches the snapshot
and the run becomes silently unrepeatable -- is held by these checks alone.

The registry is blind to a knob an adapter reads without declaring it. Half of
that walk lives in `tests/contract/test_snapshot.py`; the piece left here is the
adapters' `knobs_read()` against what they really read -- three hand-typed lists
whose drift gives a snapshot confident and wrong.
"""
import os
import re


import support
from booksmith.core.errors import Refusal
from booksmith.processing.layout.adapters.doclayout import DocLayout
from booksmith.processing.layout.adapters.docling import (
    DoclingEgret,
    DoclingHeron)
from booksmith.processing.layout.adapters.served import Served
from booksmith.processing.layout.adapters.yolox import YoloXLayout
from booksmith.core import knobs

ADAPTERS = ((DocLayout, "processing/layout/adapters/doclayout.py"),
            (DoclingHeron, "processing/layout/adapters/docling.py"),
            (DoclingEgret, "processing/layout/adapters/docling.py"),
            (YoloXLayout, "processing/layout/adapters/yolox.py"),
            (Served, "processing/layout/adapters/served.py"))


def test_unknown_knob_raises_not_returns_empty():
    """An undeclared name raises instead of returning an empty string, which
    would be a run that looks configured and does not repeat."""
    try:
        knobs.knob("MULTIVIEW")          # a name the registry does not hold
    except KeyError as e:
        assert "MULTIVIEW" in str(e) and "KNOBS" in str(e), (
            f"the complaint names neither the knob nor the registry: {e}")
    else:
        raise AssertionError(
            "the registry gave a value for a knob it does not hold: that "
            "knob will not reach the snapshot, and the run becomes silently "
            "unrepeatable")


def test_names_are_unique():
    """A duplicate name would silently overwrite one knob in KNOB."""
    names = [k.name for k in knobs.KNOBS]
    assert len(names) == len(set(names)), (
        f"knob names repeat: "
        f"{sorted({n for n in names if names.count(n) > 1})}")


def test_defaults_are_strings():
    """A default is kept as a string, as it would arrive from the shell:
    otherwise the snapshot writes `2.0` where the run saw `"2"`, and comparing
    two runs trips over the type instead of the value."""
    for k in knobs.KNOBS:
        assert isinstance(k.default, str), (
            f"{k.name}: the default {k.default!r} is not a string")
        assert k.what, f"{k.name}: it does not say what it does"


def test_snapshot_holds_every_knob_with_every_field():
    s = knobs.snapshot()
    assert set(s) == set(knobs.names()), (
        f"the snapshot holds {len(s)} knobs of {len(knobs.names())}: "
        f"{sorted(set(knobs.names()) ^ set(s))}")
    for name, rec in s.items():
        assert set(rec) == {"value", "default", "set_externally", "what",
                            "debt"}, f"{name}: snapshot fields {sorted(rec)}"


def test_snapshot_tells_set_from_default():
    """Whether a knob was set is a question apart from its value: an empty
    string in the environment is a value, not an absence, and `${X:-0}` in the
    shell and the registry default must say one and the same thing."""
    name = "PAGE_DPI"
    old = os.environ.get(name)
    try:
        os.environ.pop(name, None)
        s = knobs.snapshot()[name]
        assert s["set_externally"] is False
        assert s["value"] == s["default"] == knobs.KNOB[name].default
        os.environ[name] = "999"
        s = knobs.snapshot()[name]
        assert s["set_externally"] is True and s["value"] == "999"
        assert s["default"] == knobs.KNOB[name].default, (
            "the default in the snapshot was replaced by the value given: "
            "there is nothing left to compare a run against the default with")
        os.environ[name] = ""
        assert knobs.knob(name) == "", "an empty string from outside lost to the default"
    finally:
        os.environ.pop(name, None)
        if old is not None:
            os.environ[name] = old


def test_passthrough_carries_only_what_was_set():
    """What ships to the card is what was SET; defaults live in one place."""
    old = os.environ.get("PASSES")
    try:
        os.environ.pop("PASSES", None)
        assert "PASSES" not in knobs.passthrough()
        os.environ["PASSES"] = "3"
        assert knobs.passthrough()["PASSES"] == "3"
        assert set(knobs.passthrough()) <= set(knobs.names())
    finally:
        os.environ.pop("PASSES", None)
        if old is not None:
            os.environ["PASSES"] = old


def test_adapters_declare_the_knobs_they_read():
    """A contract through a file: `knobs_read()` against the adapter's source.
    A drift is silent: `books replay --check` returns 0 while `run.json` names a
    value that has nothing to do with the run."""
    for cls, rel in ADAPTERS:
        with open(support.src_path(rel), encoding="utf-8") as f:
            text = f.read()
        # And the modules that read a knob on the adapter's behalf: a knob need
        # not be read in the adapter's own file to be its own. `ASSEMBLY_ORDER`
        # is read inside order.rule(), which every adapter without a model rank
        # calls. The list is short and explicit rather than a call graph, which
        # would follow `stamp.sha256` into `os` and drown the check.
        for helper, called in (("core/order.py", ("order.rule(",
                                                  "order.permutation(")),):
            if any(c in text for c in called):
                with open(support.src_path(helper), encoding="utf-8") as f:
                    text += "\n" + f.read()
        # Both readers: `knobs.number("NAME")` is how a numeric knob is taken --
        # it refuses `nan`, which `float(knob(...))` accepted -- and a scan that
        # knows only `knob(` would declare live knobs dead.
        read = set(re.findall(
            r'(?:knob|number)\(\s*["\']([A-Z_0-9]+)["\']', text))
        told = set(object.__new__(cls).knobs_read())
        assert told == read, (
            f"{cls.__name__}: declared {sorted(told)}, and {rel} reads "
            f"{sorted(read)}. What is extra in the declaration is a confident "
            f"lie in the snapshot; what is missing is a knob that decided the "
            f"run and never reached it")
        unknown = told - set(knobs.names())
        assert not unknown, (
            f"{cls.__name__} declares knobs the registry does not have: "
            f"{sorted(unknown)} -- the VL_MODEL_DIR disease")


# -------------------------------------------------------- .sh and the registry
# `processing/read/rented/paddleocr_vl/run.sh` promises that a drift between
# its `${X:-…}` defaults and the registry is caught here.


_SH_OPEN = re.compile(r'\$\{([A-Z_][A-Z0-9_]*):-')


def _sh_scan(text):
    """Pairs (name, default) from `${NAME:-…}`, with brace counting: `run.sh`
    holds `PORT="${PORT_ARG:-${PORT:-8118}}"`, which a `[^}]*` regexp eats whole
    and never sees the inner `${PORT:-8118}`."""
    pairs = []
    for m in _SH_OPEN.finditer(text):
        name = m.group(1)
        i, depth = m.end(), 1
        while i < len(text) and depth:
            if text.startswith("${", i):
                depth += 1
                i += 2
                continue
            if text[i] == "}":
                depth -= 1
                if not depth:
                    break
            i += 1
        pairs.append((name, text[m.end():i]))
    return pairs


def _sh_defaults():
    """Every `${NAME:-default}` in the scripts that ship to the rented card."""
    out = {}
    root = os.path.join(support.SRC, "processing")
    for directory, _, files in os.walk(root):
        for f in sorted(files):
            if not f.endswith(".sh"):
                continue
            path = os.path.join(directory, f)
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
            # Comments are dropped: `run.sh` states the same `${PORT:-8118}` a
            # second time in the prose explaining the rule, and a guard that
            # falls from a comment edit measures nothing.
            without_prose = "\n".join(
                l for l in text.split("\n") if not l.lstrip().startswith("#"))
            for name, default in _sh_scan(without_prose):
                # `${X:-…}` is an example out of a comment, not a variable.
                if name == "X":
                    continue
                out.setdefault(name, []).append(
                    (os.path.relpath(path, support.SRC), default))
    return out


def test_shell_defaults_agree_with_the_registry():
    """A `.sh` default equals the registry default, or the registry entry says
    out loud that the shell owns the value; an empty default admitting nothing
    is indistinguishable from a forgotten one. Absent names are not caught."""
    registry = {k.name: k for k in knobs.KNOBS}
    found = _sh_defaults()

    # The denominator: with no `.sh` found, `troubles` stays empty and the check
    # passes having compared not one name.
    checked = sorted(n for n in found if n in registry)
    assert len(checked) >= 4, (
        f"only {len(checked)} names were compared ({checked}) -- the check "
        f"is green on nothing. At least four are expected: the scripts that "
        f"travel to the card read MODEL_NAME, PORT, RESUME, "
        f"VLLM_USE_FLASHINFER_SAMPLER and VL_MODEL_DIR. Empty here means the "
        f"`.sh` were not found or the parse stopped seeing them, not that "
        f"there is no divergence")

    troubles = []
    for name, places in sorted(found.items()):
        k = registry.get(name)
        if k is None:
            continue
        for file, default in places:
            if k.default:
                if default != k.default:
                    troubles.append(
                        f"  {name}: in {file} the default is {default!r}, "
                        f"in the registry {k.default!r}")
            elif "run.sh" not in k.what and "shell" not in k.what:
                troubles.append(
                    f"  {name}: the registry gives no default and {file} "
                    f"supplies {default!r}, and the registry entry is silent "
                    f"(«{k.what[:60]}»)")
    assert not troubles, (
        "the shell defaults diverged from the registry:\n"
        + "\n".join(troubles)
        + "\nA default has one place of residence. Once they diverge the "
          "snapshot writes one value while the rented card computes with "
          "another, and the only way to find out is the bill.")


def test_replay_finds_the_snapshot_in_both_layouts():
    """The snapshot is looked for in the root and in the kitchen: a detect
    directory keeps `run.json` at the root, a book directory in `assets/`, and
    "no snapshot at all" over a snapshot one floor down is a lie with a zero."""
    import json as _json
    import tempfile

    from booksmith.core.book import ASSETS
    from booksmith.core import replay

    snapshot = {"knobs": {"PAGE_DPI": {"value": "144"}}}
    with tempfile.TemporaryDirectory() as tmp:
        assert replay.facts(tmp) == {}, "a snapshot was found where there is none"

        with open(os.path.join(tmp, "run.json"), "w", encoding="utf-8") as f:
            _json.dump(snapshot, f)
        assert replay.facts(tmp) == snapshot, "the snapshot at the root was not read"

    with tempfile.TemporaryDirectory() as tmp:
        os.makedirs(os.path.join(tmp, ASSETS))
        with open(os.path.join(tmp, ASSETS, "run.json"), "w",
                  encoding="utf-8") as f:
            _json.dump(snapshot, f)
        assert replay.facts(tmp) == snapshot, (
            "the snapshot in the kitchen was not read -- `books replay "
            "--check` on a book directory will say \"no snapshot at all\" "
            "with a snapshot lying right beside it")


def test_the_aging_knob_lists_exactly_the_profiles_that_exist():
    """A knob's description names its legal values, and they must be legal: the
    description is copied verbatim into every run snapshot, and
    `synth.AGING[profile]` is a plain lookup with no default."""
    from booksmith.datasets.make import synth
    knob = [k for k in knobs.KNOBS if k.name == "SYNTH_AGING"][0]
    listed = knob.what.split(": ")[1].split("|")
    assert listed == list(synth.AGING), (
        f"the knob offers {listed}, `synth.AGING` accepts {list(synth.AGING)}")


def test_no_numeric_knob_takes_a_value_that_is_not_a_number():
    """`nan` is a legal float and compares False with everything, so a mistyped
    knob does not fail -- it makes every guard around it quietly stop holding.
    The names come from the registry, so a knob added tomorrow is covered."""
    numeric = []
    for k in knobs.KNOBS:
        try:
            float(k.default)
        except (TypeError, ValueError):
            continue
        numeric.append(k.name)
    assert len(numeric) >= 10, (
        f"only {len(numeric)} knobs look numeric: {numeric}. The registry has "
        f"changed shape and this check is now looking at almost nothing")

    was = dict(os.environ)
    try:
        for name in numeric:
            for bad in ("nan", "-nan", "inf", "-inf", "infinity"):
                os.environ[name] = bad
                try:
                    got = knobs.number(name)
                except Refusal:
                    continue
                raise AssertionError(
                    f"{name}={bad!r} was accepted as {got!r}. Every guard "
                    f"comparing it will be quietly false, and the run will "
                    f"finish and say nothing")
            os.environ.pop(name, None)
    finally:
        os.environ.clear()
        os.environ.update(was)


def test_every_numeric_knob_is_read_through_the_one_reader():
    """`float(knob(...))` is the spelling that lets `nan` in; there are none. A
    second way to read a knob as a number is a second home for that defect.
    Searched over the package, not remembered."""
    import glob
    bad = []
    root = os.path.dirname(support.SRC)
    for path in glob.glob(os.path.join(support.SRC, "**", "*.py"),
                          recursive=True):
        text = open(path, encoding="utf-8").read()
        for m in re.finditer(r'(?:float|int)\(\s*knobs?\.knob\(', text):
            line = text[:m.start()].count("\n") + 1
            bad.append(f"{os.path.relpath(path, root)}:{line}")
    assert not bad, (
        f"a knob is read as a number past `knobs.number`: {bad}. That is the "
        f"spelling `nan` walked through -- `float()` accepts it and every "
        f"comparison after it is False")
