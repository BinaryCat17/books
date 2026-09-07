"""The adapter contract is compared with the pipeline, not believed.

WHY THIS FILE EXISTS. `models.base.Detector` said "exactly two things" and
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
import inspect
import os
import textwrap

import support
from booksmith.processing.layout import base

# Adapters we ship. Named explicitly: a new one lands here deliberately or not
# at all, which is the same rule `subset.TRAITS` follows.
ADAPTERS = (("doclayout.py", "DocLayout"),
            ("docling.py", "DoclingHeron"),
            ("docling.py", "DoclingEgret"),
            ("yolox.py", "YoloXLayout"))


# Every file that drives an adapter. `detect.py` is the pipeline; `cli.py`
# asks `books doctor` questions of the same object, and its `getattr(det,
# "onnx", "")` was invisible to a check that read `detect.py` alone.
DRIVERS = ("processing/layout/detect.py", "cli.py")


def _asked_of(var, rel):
    """Every attribute the named local is asked for in that source file.

    `getattr(x, "name")` counts too: a soft access is still the pipeline
    requiring something of an adapter, and writing it that way is how the one
    undeclared member hid.
    """
    src = open(os.path.join(support.SRC, rel), encoding="utf-8").read()
    tree = ast.parse(src)
    out = {n.attr for n in ast.walk(tree)
           if isinstance(n, ast.Attribute)
           and isinstance(n.value, ast.Name) and n.value.id == var}
    for n in ast.walk(tree):
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                and n.func.id == "getattr" and len(n.args) >= 2
                and isinstance(n.args[0], ast.Name) and n.args[0].id == var
                and isinstance(n.args[1], ast.Constant)):
            out.add(n.args[1].value)
    return out


def _refuses(member) -> bool:
    """Does the contract's own version of this member refuse to answer?

    Refusing is `raise NotImplementedError` and nothing else: a member with a
    body the contract stands behind (`label_map` returning `{}`) is a default
    an adapter may rely on, and a member that is not callable at all is a
    field. Read from the source of the class, so it does not depend on a
    docstring or on any convention outside the file.
    """
    if not callable(member) or not hasattr(member, "__code__"):
        return False
    try:
        body = ast.parse(textwrap.dedent(inspect.getsource(member))).body[0]
    except (OSError, SyntaxError, IndexError):
        return False
    return any(isinstance(n, ast.Raise) and _names_not_implemented(n)
               for n in ast.walk(body))


def _names_not_implemented(node) -> bool:
    e = node.exc
    if isinstance(e, ast.Call):
        e = e.func
    return isinstance(e, ast.Name) and e.id == "NotImplementedError"


def _declared():
    return ({n for n in vars(base.Detector) if not n.startswith("__")}
            | set(getattr(base.Detector, "__annotations__", {})))


def test_the_contract_declares_everything_the_pipeline_asks_for():
    """Direction one: the pipeline may ask for nothing undeclared.

    This is the direction that was broken, and it is broken silently: Python
    binds an instance attribute happily, so an adapter that happens to set
    `dir` works and one that does not fails at the line that prints the log.
    """
    asked = set()
    for rel in DRIVERS:
        asked |= _asked_of("det", rel)
    assert asked, "nothing is asked of `det` at all -- the search broke"
    missing = sorted(asked - _declared())
    assert not missing, (
        f"{' and '.join(DRIVERS)} ask an adapter for {missing}, and "
        f"`Detector` declares none of them. An adapter written to the "
        f"contract would import and then fall at the first run")


def test_the_contract_declares_every_dict_key_the_pipeline_indexes():
    """A method is not a contract. What it must RETURN is the contract.

    Declaring the methods was not enough, and it was proved by writing an
    adapter to the contract as documented: it imported cleanly, ran, and fell
    three times in a row on `page.meta["rank_ties"]`,
    `page.meta["best_rejected_by_class"]` and `fingerprint()["sha256_weights"]`
    -- subscripts, which no list of attribute names can see.

    Only the HARD ones count: a key read with `.get` degrades to a poorer log
    and is not load-bearing, and listing it would claim otherwise.
    """
    src = open(os.path.join(support.SRC, "processing/layout/detect.py"), encoding="utf-8").read()
    meta, fp = set(), set()
    for n in ast.walk(ast.parse(src)):
        if not (isinstance(n, ast.Subscript)
                and isinstance(n.slice, ast.Constant)
                and isinstance(n.slice.value, str)):
            continue
        v = n.value
        if isinstance(v, ast.Attribute) and v.attr == "meta":
            meta.add(n.slice.value)
        elif isinstance(v, ast.Name) and v.id == "fp":
            fp.add(n.slice.value)
        elif (isinstance(v, ast.Call) and isinstance(v.func, ast.Attribute)
              and v.func.attr == "fingerprint"):
            fp.add(n.slice.value)

    for what, found, declared in (
            ("page meta", meta, set(base.Detector.PAGE_META_REQUIRED)),
            ("fingerprint", fp, set(base.Detector.FINGERPRINT_REQUIRED))):
        assert found == declared, (
            f"detect.py indexes {what} keys {sorted(found)} with no default; "
            f"the contract declares {sorted(declared)}. An adapter that fills "
            f"in what the contract names would still fall on the difference")


def test_every_adapter_fills_the_keys_the_contract_names():
    """And the shipped adapters put them there. Read from the SOURCE.

    Running them means ONNX and a page of raster; what is asked instead is
    that each adapter's `read` writes every declared meta key and each
    `fingerprint` every declared fingerprint key, by the literal keys in its
    own source. Crude, and it goes red the day one is dropped.
    """
    for rel, cls_name in ADAPTERS:
        src = open(os.path.join(support.SRC, "processing", "layout", "adapters", rel),
                   encoding="utf-8").read()
        keys = {k.value for n in ast.walk(ast.parse(src))
                if isinstance(n, ast.Dict)
                for k in n.keys
                if isinstance(k, ast.Constant) and isinstance(k.value, str)}
        want = (set(base.Detector.PAGE_META_REQUIRED)
                | set(base.Detector.FINGERPRINT_REQUIRED))
        missing = sorted(want - keys)
        assert not missing, (
            f"{rel} never writes {missing}, and the pipeline indexes them "
            f"without a default: the adapter falls on the first page")


# Names that hold an adapter. Attribute accesses on ANY name were the first
# version, and it was nearly inert: 672 names matched, so a dead contract
# member escaped unless its name was invented -- `close`, `keys`, `items`,
# `count`, `width` all passed. An adapter is held in few places and they are
# nameable.
HOLDERS = ("det", "adapter", "rec", "self")


def test_the_contract_declares_nothing_nobody_asks_for():
    """The other direction: a member no caller wants is a name gone stale.

    Looked for across the package AND the checks -- `label_map` is read by the
    metrics and by the adapters' own fingerprints, and the two `*_REQUIRED`
    tuples are read by the checks beside this one. A declaration a check reads
    is read; one nobody reads at all is a name that outlived its use.
    """
    used = set()
    roots = (support.SRC, os.path.dirname(os.path.abspath(__file__)))
    for base_dir in roots:
        for root, _, files in os.walk(base_dir):
            for fn in files:
                if not fn.endswith(".py"):
                    continue
                try:
                    tree = ast.parse(open(os.path.join(root, fn),
                                          encoding="utf-8").read())
                except SyntaxError:
                    continue
                for n in ast.walk(tree):
                    if not isinstance(n, ast.Attribute):
                        continue
                    v = n.value
                    if isinstance(v, ast.Name) and v.id in HOLDERS:
                        used.add(n.attr)
                    elif isinstance(v, ast.Attribute) \
                            and v.attr == "Detector":
                        used.add(n.attr)
                    elif isinstance(v, ast.Name) and v.id == "Detector":
                        used.add(n.attr)
                for n in ast.walk(tree):
                    if (isinstance(n, ast.Call)
                            and isinstance(n.func, ast.Name)
                            and n.func.id == "getattr" and len(n.args) >= 2
                            and isinstance(n.args[0], ast.Name)
                            and n.args[0].id in HOLDERS
                            and isinstance(n.args[1], ast.Constant)):
                        used.add(n.args[1].value)
    idle = sorted(n for n in _declared() if n not in used)
    assert not idle, (
        f"`Detector` declares {idle}, which nothing reads on an adapter. "
        f"A contract term nobody asks for is a name that outlived its use")


def test_every_adapter_we_ship_satisfies_the_contract():
    """And the adapters keep it -- by behaviour, not by inheritance.

    `issubclass` proves nothing here: every member with a default is inherited
    whether or not the adapter meant it. What is asked is that the ones with
    NO default are actually implemented.

    SELECTED BY WHAT THE CONTRACT DOES, not by whether it is documented. The
    first edition asked for "callable and has a docstring", and the count came
    out at four by coincidence: `read` -- no default, the one method called
    per page -- was EXCLUDED for having no docstring, so an adapter without it
    passed; and `label_map`, which the contract grants a documented default,
    was INCLUDED, so an adapter was forbidden to rely on it. What is asked now
    is exactly the members whose contract version refuses to answer.
    """
    import importlib
    must = sorted(n for n in _declared() if _refuses(getattr(
        base.Detector, n, None)))
    assert "read" in must and "label_map" not in must, (
        f"the selection has drifted: {must}. `read` refuses and must be "
        f"required; `label_map` has a documented default and must not be")
    for rel, cls_name in ADAPTERS:
        mod = importlib.import_module(
            "booksmith.processing.layout.adapters." + rel[:-3])
        cls = getattr(mod, cls_name, None)
        assert cls is not None, f"{rel} no longer defines {cls_name}"
        assert issubclass(cls, base.Detector), (
            f"{cls_name} is not a Detector at all")
        for name in must:
            own = any(name in vars(k) for k in cls.__mro__
                      if k is not base.Detector)
            assert own, (
                f"{cls_name} does not implement {name!r}: it inherits the "
                f"contract's own version, which either raises or answers for "
                f"a model it knows nothing about")


# ------------------------------------------------- the run label and identity

def test_every_detector_declares_a_label_and_it_is_a_directory_name():
    """A label with no default, for the reason `knobs_read` has none.

    The label is the MODEL's name and it becomes a directory. An adapter
    silent out of forgetfulness would be filed under whatever a base class
    guessed, and a guessed directory is a measurement filed against the wrong
    model. Built here rather than parsed, so the answer comes from the weights
    on disk.
    """
    from booksmith.core import book
    from booksmith.processing.layout import detect
    seen = {}
    for name in detect.ADAPTERS:
        with support.env(LAYOUT_ADAPTER=name):
            try:
                det = detect._adapter()
            except Exception as e:          # weights absent on this machine
                support.skip(f"{name}: {type(e).__name__}: {str(e)[:60]}")
            lab = det.label()
            assert book.LABEL_OK.match(lab), f"{name}: {lab!r} is no directory"
            assert lab != det.name or name.startswith("docling"), (
                f"{name}: the label is the ADAPTER's name. One adapter serves "
                f"several models; their runs would share a directory")
            seen[name] = lab
    assert len(set(seen.values())) == len(seen), (
        f"two adapters claim one label: {seen}. The second run would read as "
        f"a resume of the first")


def test_the_reader_labels_by_the_model_not_by_itself():
    from booksmith.core import book
    from booksmith.processing.read.readers.paddleocr_vl import PaddleOcrVl
    r = PaddleOcrVl("PP-DocLayoutV2")
    assert r.label() != r.name, (
        "the reader labelled a run after itself; `paddleocr-vl` is the reader "
        "and the model is what answered")
    assert book.LABEL_OK.match(r.label())


def test_a_label_that_is_not_a_directory_name_is_refused_not_sanitised():
    """Two models differing only where a sanitiser bites would land in ONE
    directory, and the second would read as a resume of the first."""
    from booksmith.core import book
    from booksmith.core.errors import Refusal
    for bad in ("not declared in the weights", "a/b", "", "../up", "x" * 80):
        try:
            book.safe_label(bad, "test")
        except Refusal as e:
            assert "--run" in str(e), f"{bad!r}: the refusal names no way out"
        else:
            raise AssertionError(f"{bad!r} was accepted as a directory name")


def test_identity_ignores_what_moves_without_the_experiment():
    """The dangerous direction: two runs of one experiment getting two
    identities, so a legitimate second run is refused and the refusal looks
    like the guard working."""
    from booksmith.core import stamp
    fp = {"model": "X", "sha256_weights": "ab"}
    a = stamp.identity({**fp, "weights_dir": "/home/a"},
                       {"T": "0.5", "VLM_ENDPOINT": "http://1.2.3.4:8118/v1"})
    b = stamp.identity({**fp, "weights_dir": "/mnt/other"},
                       {"T": "0.5", "VLM_ENDPOINT": "http://9.9.9.9:8000/v1"})
    assert a == b, ("the same experiment on another machine and another "
                    "rental got another identity")
    assert a != stamp.identity({**fp, "weights_dir": "/home/a"}, {"T": "0.6"})
    assert a != stamp.identity({"model": "Y", "sha256_weights": "cd"},
                               {"T": "0.5"})


def test_identity_reads_only_the_knobs_the_run_read():
    """The snapshot's knob block is COMPLETE by design -- every knob, each
    saying who reads it. Hashing it whole would put `HTML_MATH` inside a
    detection run's identity."""
    from booksmith.core import knobs, stamp
    roles = {"PAGE_DPI": "the command", "LAYOUT_MODEL_NAME": "adapter"}
    was = knobs.snapshot_with_readers(roles)
    vals = stamp.knob_values({"knobs": was})
    assert set(vals) == set(roles), (
        f"identity reads {sorted(set(vals) - set(roles))} that this run does "
        f"not read")
    with support.env(HTML_MATH="off"):
        idle = stamp.knob_values({"knobs": knobs.snapshot_with_readers(roles)})
    assert stamp.identity({}, vals) == stamp.identity({}, idle)
    with support.env(LAYOUT_MODEL_NAME="PP-DocLayoutV3"):
        live = stamp.knob_values({"knobs": knobs.snapshot_with_readers(roles)})
    assert stamp.identity({}, vals) != stamp.identity({}, live)


def test_identity_does_not_depend_on_the_order_the_dict_was_built_in():
    """A hash over a mapping is a hash over an ORDER unless it is sorted.

    IN PROCESS, and deliberately: the first version of this check ran the
    hash in three subprocesses under three `PYTHONHASHSEED` values, which
    reads well and proves less -- a subprocess re-imports the real module, so
    the mutation that unsorts the hash never reached it and the battery
    reported the check as covered while it was not. The property itself is
    order-independence, and it is visible from here.
    """
    from booksmith.core import stamp
    a = {"b": 1, "a": [3, 2], "m": {"y": 1, "x": 2}}
    b = {"m": {"x": 2, "y": 1}, "a": [3, 2], "b": 1}
    ka = {"Z": "1", "A": "2"}
    kb = {"A": "2", "Z": "1"}
    assert stamp.identity(a, ka) == stamp.identity(b, kb), (
        "the same experiment hashed two ways depending on insertion order")
    # And a LIST is ordered content, not a set: reordering it is a change.
    assert stamp.identity({"a": [2, 3]}, {}) != stamp.identity({"a": [3, 2]}, {})
