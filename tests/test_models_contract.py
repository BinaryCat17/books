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
import json

import pytest

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


# Names that hold an adapter. Attribute accesses on ANY name were the first
# version, and it was nearly inert: 672 names matched, so a dead contract
# member escaped unless its name was invented -- `close`, `keys`, `items`,
# `count`, `width` all passed. An adapter is held in few places and they are
# nameable.
HOLDERS = ("det", "adapter", "rec", "self")


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


def test_identity_is_taken_from_the_real_fingerprints_not_a_hand_written_one():
    """Both identity defects hid behind a fixture.

    The checks above build a fingerprint by hand -- `{"model": "X",
    "sha256_weights": "ab", "weights_dir": …}` -- and the only end-to-end one
    runs `doclayout`, the single adapter whose fingerprint is neither nested
    nor run-born. So two defects lived in the shape of the REAL ones:

      docling nests the vendor pipeline's fingerprint under
      `docling_pipeline`, and that nest holds accumulating page counters
      under `summary`. The exclusion filtered the top level only, so a
      pipeline run's identity was a function of how many pages it covered.

      the reader's `weights` block opens with `dir`, which is `VL_MODEL_DIR`
      -- the exact fact the knob exclusion exists for, admitted one field
      over. Two readings on two rented cards, two identities.

    So this one asks the adapters themselves.
    """
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
        # THE PIPELINE IS TURNED ON for the docling pair, and that is the
        # whole point of this check: with `DOCLING_PIPELINE=off` the nest is
        # `null` and there is nothing for a top-level filter to miss -- so a
        # check that only ever asked the default configuration passed while
        # the defect was live. The nest holds the pipeline's ACCUMULATING
        # PAGE COUNTERS.
        env = {"LAYOUT_ADAPTER": name}
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

    # THROUGH `identity`, NOT THROUGH THE FILTER. The first edition of this
    # check called `_without` itself and passed under a mutation that broke
    # `identity`'s USE of it -- the filter was still recursive, and nothing
    # asked what the function that matters does. So the question is asked the
    # way the guard asks it: does the identity MOVE when a run-born number
    # moves.
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
            # A machine-local path in the identity means one experiment gets
            # an identity per machine. Two readings on two rented cards.
            if isinstance(value, str) and value.startswith(("/", "~")):
                raise AssertionError(
                    f"{name}: {path} = {value!r} is an absolute path and is "
                    f"inside the identity; the same experiment on another "
                    f"machine would be refused as a different one")
