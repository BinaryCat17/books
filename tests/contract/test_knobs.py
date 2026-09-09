"""The knob registry: what is not declared is not read, and the reverse.

The project rule -- a knob absent from `run/knobs.py` never reaches the
snapshot and the run becomes silently irreproducible -- is held here by nothing
but checks.

The registry is honest about its blindness: `VL_MODEL_DIR` was caught not by it
but by a check that parsed sources as trees. Half of that catcher walks the tree
in `tests/contract/test_snapshot.py`; the piece it does not take on is here --
the adapters' `knobs_read()` declarations against what they really read. Three
hand-typed lists, and a drift gives a snapshot CONFIDENT AND WRONG.
"""
import os
import re


import support
from booksmith.core.errors import Refusal
from booksmith.processing.layout.adapters.doclayout import DocLayout
from booksmith.processing.layout.adapters.docling import (
    DoclingEgret,
    DoclingHeron)
from booksmith.processing.layout.adapters.yolox import YoloXLayout
from booksmith.core import knobs

ADAPTERS = ((DocLayout, "processing/layout/adapters/doclayout.py"),
            (DoclingHeron, "processing/layout/adapters/docling.py"),
            (DoclingEgret, "processing/layout/adapters/docling.py"),
            (YoloXLayout, "processing/layout/adapters/yolox.py"))


def test_unknown_knob_raises_not_returns_empty():
    """An undeclared name raises instead of returning an empty string.

    An empty string here is a run that looks configured and does not repeat.
    """
    try:
        knobs.knob("MULTIVIEW")          # once a knob, removed with its patch
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
    """A default is kept as a STRING, as it would arrive from the shell.

    Otherwise the snapshot writes `2.0` where the run saw `"2"`, and comparing
    two runs trips over the type instead of the value.
    """
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
    """Whether a knob was SET is a question apart from its value.

    An empty string in the environment is a VALUE, not an absence: `${X:-0}` in
    the shell and the registry default must say one and the same thing.
    """
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

    The comparison `readers()` does not take on. A drift is silent: `books
    replay --check` returns 0 while `run.json` names a value that has nothing
    to do with the run -- as happened with `LAYOUT_MODEL_NAME=PP-DocLayoutV2`
    in a heron run.
    """
    for cls, rel in ADAPTERS:
        with open(support.src_path(rel), encoding="utf-8") as f:
            text = f.read()
        # AND THE MODULES THAT READ A KNOB ON THE ADAPTER'S BEHALF. A knob
        # need not be read in the adapter's own file to be the adapter's:
        # `ASSEMBLY_ORDER` is read inside `core/order.py:rule()`, which every
        # adapter without a model rank calls to order its blocks. Declared by
        # none of them for exactly that reason, it rode into four models'
        # snapshots as "NOBODY IN THIS RUN" while steering their output --
        # formally complete and inoperative. Proved: two runs at two values
        # gave one identity.
        #
        # The list is short and explicit rather than a call graph: a graph
        # would follow `stamp.sha256` into `os` and the check would drown.
        for helper, called in (("core/order.py", ("order.rule(",
                                                  "order.permutation(")),):
            if any(c in text for c in called):
                with open(support.src_path(helper), encoding="utf-8") as f:
                    text += "\n" + f.read()
        # BOTH READERS. `knobs.number("NAME")` is how a numeric knob is taken
        # -- it refuses `nan`, which `float(knob(...))` accepted -- and a scan
        # that knows only `knob(` declared three live knobs dead the moment
        # the adapters moved onto it.
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


# --------------------------------------------------------------------------
# A CONTRACT BETWEEN TWO CHECK FILES: `pytest.skip()` and pytest, and
# it is silent about the WHOLE run at once. `pytest.skip()` chose the form of
# a skip by whether pytest was IMPORTABLE, not by WHO RUNS, and in pytest
# `Skipped` inherits BaseException, not Exception -- past both traps of
# `run_case`. Measured with a stand-in module of the same contract: under our
# runner the first skip killed the run with a traceback, the line "checks 111:
# passed 110 ..." did not print AT ALL, exit code 1. Installing pytest into
# `.venv` was enough to stop 110 green checks reporting themselves.

# -------------------------------------------------------- .sh AND THE REGISTRY
# A promise nothing kept BEFORE this check. `processing/read/rented/paddleocr_vl/run.sh` says
# word for word: "a drift will be caught by `tests/contract/test_knobs.py`, which
# compares the right-hand sides of `${X:-…}` with it [the registry]". No such
# comparison existed: no check opened a `.sh`, and `knobs.readers()` looks in
# shell only for the PRESENCE of `$NAME`. A guard existing as one line of prose
# is worse than none: it was cited in decisions.

_SH_OPEN = re.compile(r'\$\{([A-Z_][A-Z0-9_]*):-')


def _sh_scan(text):
    """Pairs (name, default) from `${NAME:-…}`, WITH BRACE COUNTING.

    A `[^}]*` regexp will not do: `run.sh` holds
    `PORT="${PORT_ARG:-${PORT:-8118}}"`, where it eats the outer one whole and
    never sees the inner `${PORT:-8118}`. The first draft missed exactly there
    -- a `PORT` swapped in a copy of the tree (9999 against 8118 in the
    registry) went unnoticed and the check declared itself sound.
    """
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
            # COMMENTS ARE DROPPED, and that is no detail. In `run.sh` the same
            # `${PORT:-8118}` stands a SECOND time, in the prose explaining the
            # rule. Comparing prose on a par with code, the guard would fall
            # from a comment edit, which changes no behaviour. Checked:
            # corrupting ONLY the example in the comment made the check fail.
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
    """A `.sh` default equals the registry default -- or is admitted out loud.

    TWO CASES, AND ONE RULER WILL NOT DO. The registry DECLARED a default
    (non-empty): the shell must substitute the same, or the snapshot writes one
    thing while the card counts by another and only the bill shows it. The
    registry gives NO default (empty string): the owner of the value is the
    shell, and the registry entry must SAY so -- otherwise an empty default is
    indistinguishable from a forgotten one, the `VL_MODEL_DIR` disease whose
    catcher, says the `run/knobs.py` header, is restored by HALF.

    A name absent from the registry it does NOT catch and does not pretend to:
    that needs a list of lawful shell variables. There are EIGHT of them, not
    six as stood here: `ENVDIR`, `MODELS`, `HF_HOME`, `VL_REPO`, `SRV`,
    `PYTORCH_CUDA_ALLOC_CONF`, plus `DOTS_DIR` (the knob past the registry the
    `run/knobs.py` header writes about) and `PORT_ARG`, the positional argument
    of `run.sh`, whose own default is `${PORT:-8118}`.

    AND WHAT IT DOES NOT COMPARE THOUGH IT LOOKS AS IF IT DID: for a knob with
    an EMPTY registry default the `.sh` value is compared with nothing, only
    the admission in the description. `${VL_MODEL_DIR:-/models/vl}` swapped for
    `/models/xxx` passes silently, proved by mutation. It cannot be otherwise:
    the owner is declared to be the shell, and there is no second home.
    """
    registry = {k.name: k for k in knobs.KNOBS}
    found = _sh_defaults()

    # THE DENOMINATOR, WITHOUT WHICH THE CHECK IS GREEN ON NOTHING. Find no
    # `.sh` and `_sh_defaults()` returns empty, `troubles` stays empty, and
    # `assert not troubles` passes having compared NOT ONE name. Proved by
    # running it: with an empty `models` directory the check was green -- a
    # zero from misunderstanding against a zero from checking.
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
    """The snapshot is looked for in the root and in the kitchen.

    A DETECTION directory keeps `run.json` at the root, a BOOK directory in
    `assets/`, where the root holds one file, the book. The completeness check
    looked only at the root and answered "no snapshot at all" on a book with
    the snapshot one floor down, returning 1 -- while the builder promises word
    for word: "`books replay --check` must return 0 here too" -- a speaking
    step lying with a zero, the rule that made "chapters 0" read as "there are
    none".
    """
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
    """A knob's description names its legal values, and they must be legal.

    `SYNTH_AGING` went on advertising the fourth profile under its old name
    after the rename to `decayed`, so the documented command raised `KeyError`
    -- `synth.AGING[profile]` is a plain lookup with no default. The
    description is not a comment: it is copied verbatim into every run
    snapshot, so the wrong value travels with the record of the run.
    """
    from booksmith.datasets.make import synth
    knob = [k for k in knobs.KNOBS if k.name == "SYNTH_AGING"][0]
    listed = knob.what.split(": ")[1].split("|")
    assert listed == list(synth.AGING), (
        f"the knob offers {listed}, `synth.AGING` accepts {list(synth.AGING)}")


def test_no_numeric_knob_takes_a_value_that_is_not_a_number():
    """`nan` is a legal float, and it compares False with EVERYTHING.

    So a mistyped knob did not fail -- it made every guard around it quietly
    stop holding. Driven across the tree: `CROP_DPI` and `CROP_MARGIN` walked
    past guards that refuse zero and negatives; `VLM_TEMPERATURE` and
    `VLM_TOP_P` reached the PAID path; `VLM_TIMEOUT_S` reached urllib;
    `LAYOUT_SCORE_THRESHOLD` reached every box comparison. Worst of them,
    `PAGE_DPI=nan` built the GOLDEN BENCH to completion -- truth coordinates
    in one system, pdf geometry in pymupdf's default letter page, `nan` in the
    manifest, and not one word said.

    The names come from the registry, not from a list here: a numeric knob
    added tomorrow is covered the day it is declared.
    """
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
    """`float(knob(...))` is the spelling that let `nan` in. There are none.

    A second way to read a knob as a number is a second place for this defect
    to live, and it would look exactly like the first: no failure, no message,
    a guard that stops holding. Searched over the package, not remembered.
    """
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
