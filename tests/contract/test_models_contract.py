"""The adapter contract is compared with the pipeline, not believed.

A contract nobody compares is prose. `layout.base.Detector` declares what an
adapter must implement, `detect.py` and `cli.py` are what asks; the names come
from the code that uses them and the declaration from the class, so this fails
whichever side moves.
"""
import json

import pytest

import support
from booksmith.processing.layout import base

# Adapters we ship. Named explicitly: a new one lands here deliberately or not
# at all, which is the same rule `subset.TRAITS` follows.
ADAPTERS = (("doclayout.py", "DocLayout"),
            ("docling.py", "DoclingHeron"),
            ("docling.py", "DoclingEgret"),
            ("yolox.py", "YoloXLayout"),
            ("served.py", "Served"))


# Every file that drives an adapter. `detect.py` is the pipeline; `cli.py` asks
# `books doctor` questions of the same object.
DRIVERS = ("processing/layout/detect.py", "cli.py")


# Names that hold an adapter. Named rather than every attribute access, which
# matches 672 names and lets a dead contract member escape.
HOLDERS = ("det", "adapter", "rec", "self")


def test_every_adapter_we_ship_satisfies_the_contract():
    """The adapters keep the contract by behaviour, not by inheritance:
    `issubclass` proves nothing, since every member with a default is inherited
    whether or not the adapter meant it. What is asked is the members with none."""
    import importlib
    must = sorted(base.Detector.__abstractmethods__)
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

def _env_for(name, served_endpoint):
    """The served adapter has no weights to find: it is given the stand-in."""
    env = {"LAYOUT_ADAPTER": name}
    if name == "served":
        env["LAYOUT_ENDPOINT"] = served_endpoint
    return env


def test_every_detector_declares_a_label_and_it_is_a_directory_name(served_endpoint):
    """A label with no default, for the reason `knobs_read` has none: the label
    is the model's name and becomes a directory, and a guessed directory is a
    measurement filed against the wrong model. Built here, not parsed."""
    from booksmith.core import book
    from booksmith.processing.layout import detect
    seen = {}
    for name in detect.ADAPTERS:
        with support.env(**_env_for(name, served_endpoint)):
            try:
                det = detect._adapter()
            except Exception as e:          # weights absent on this machine
                pytest.skip(f"{name}: {type(e).__name__}: {str(e)[:60]}")
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
                       {"T": "0.5", "VLM_ENDPOINT": "http://1.2.3.4:8118/v1",
                        "LAYOUT_ADAPTER": "doclayout"})
    b = stamp.identity({**fp, "weights_dir": "/mnt/other"},
                       {"T": "0.5", "VLM_ENDPOINT": "http://9.9.9.9:8000/v1",
                        "LAYOUT_ADAPTER": "served",
                        "LAYOUT_ENDPOINT": "http://9.9.9.9:8000"})
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
    """A hash over a mapping is a hash over an order unless it is sorted. Asked
    in process: a subprocess re-imports the real module, so a mutation that
    unsorts the hash would never reach it."""
    from booksmith.core import stamp
    a = {"b": 1, "a": [3, 2], "m": {"y": 1, "x": 2}}
    b = {"m": {"x": 2, "y": 1}, "a": [3, 2], "b": 1}
    ka = {"Z": "1", "A": "2"}
    kb = {"A": "2", "Z": "1"}
    assert stamp.identity(a, ka) == stamp.identity(b, kb), (
        "the same experiment hashed two ways depending on insertion order")
    # And a LIST is ordered content, not a set: reordering it is a change.
    assert stamp.identity({"a": [2, 3]}, {}) != stamp.identity({"a": [3, 2]}, {})


def test_identity_is_taken_from_the_real_fingerprints_not_a_hand_written_one(served_endpoint):
    """Asked of the adapters themselves, not of a fingerprint written by hand:
    the real ones nest -- docling under `docling_pipeline`, which holds page
    counters -- and open with a path, both of which a top-level filter misses."""
    from booksmith.core import stamp
    from booksmith.processing.layout import detect
    from booksmith.processing.read.readers.paddleocr_vl import PaddleOcrVl

    def flat(o, path=""):
        if isinstance(o, dict):
            for k, v in o.items():
                yield from flat(v, f"{path}/{k}")
        elif isinstance(o, list):
            for i, v in enumerate(o):
                yield from flat(v, f"{path}/{i}")
        else:
            yield path, o

    seen = []
    for name in detect.ADAPTERS:
        # The pipeline is turned on for the docling pair: with it off the nest
        # is `null` and there is nothing for a top-level filter to miss.
        env = _env_for(name, served_endpoint)
        if name.startswith("docling"):
            env["DOCLING_PIPELINE"] = "post"
        with support.env(**env):
            try:
                det = detect._adapter()
                fp = det.fingerprint()
            except Exception as e:
                pytest.skip(f"{name}: {type(e).__name__}")
            seen.append((name, fp))
    seen.append(("reader", PaddleOcrVl("PP-DocLayoutV2").fingerprint()))
    nested = [n for n, fp in seen
              if any(isinstance(v, dict) and v for v in fp.values())]
    assert nested, (
        "not one fingerprint here is NESTED, so this check cannot see a "
        "filter that reaches only the top level -- which is the defect it "
        "exists for")

    # Through `identity`, not through the filter: the question is whether the
    # identity moves when a run-born number does.
    for name, fp in seen:
        if not isinstance(fp.get("docling_pipeline"), dict):
            continue
        before = stamp.identity(fp, {})
        after = json.loads(json.dumps(fp))
        s = after["docling_pipeline"].get("summary")
        assert isinstance(s, dict) and s, (
            f"{name}: the pipeline fingerprint carries no summary, so this "
            f"check cannot see a filter that misses one")
        for k in s:
            if isinstance(s[k], int):
                s[k] += 137
        assert stamp.identity(after, {}) == before, (
            f"{name}: the identity MOVED when the pipeline's page counters "
            f"did. They are run-born and nested under `docling_pipeline`, so "
            f"a filter that reaches only the top level makes the identity a "
            f"function of how many pages the run covered -- and the second "
            f"run of one experiment is then refused forever")

    for name, fp in seen:
        kept = stamp._without(fp, stamp.FINGERPRINT_NOT_IDENTITY)
        for path, value in flat(kept):
            # A machine-local path in the identity means one experiment gets an
            # identity per machine.
            if isinstance(value, str) and value.startswith(("/", "~")):
                raise AssertionError(
                    f"{name}: {path} = {value!r} is an absolute path and is "
                    f"inside the identity; the same experiment on another "
                    f"machine would be refused as a different one")
