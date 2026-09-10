"""The adapter contract is compared with the pipeline, not believed"""

import json
import pytest
import support
from layout import classes as policy
from layout import base

ADAPTERS = (
    ("doclayout.py", "DocLayout"),
    ("docling.py", "DoclingHeron"),
    ("docling.py", "DoclingEgret"),
    ("yolox.py", "YoloXLayout"),
    ("served.py", "Served"),
)
DRIVERS = ("processing/layout/detect.py", "cli.py")
HOLDERS = ("det", "adapter", "rec", "self")


def test_every_adapter_we_ship_satisfies_the_contract():
    import importlib

    must = sorted(base.Detector.__abstractmethods__)
    assert "read" in must and "label_map" not in must, (
        f"the selection has drifted: {must}. `read` refuses and must be required; `label_map` has a documented default and must not be"
    )
    for rel, cls_name in ADAPTERS:
        mod = importlib.import_module("layout." + rel[:-3])
        cls = getattr(mod, cls_name, None)
        assert cls is not None, f"{rel} no longer defines {cls_name}"
        assert issubclass(cls, base.Detector), f"{cls_name} is not a Detector at all"
        for name in must:
            own = any((name in vars(k) for k in cls.__mro__ if k is not base.Detector))
            assert own, (
                f"{cls_name} does not implement {name!r}: it inherits the contract's own version, which either raises or answers for a model it knows nothing about"
            )


def _env_for(name, served_endpoint):
    env = {"LAYOUT_ADAPTER": name}
    if name == "served":
        env["LAYOUT_ENDPOINT"] = served_endpoint
    return env


def test_every_detector_declares_a_label_and_it_is_a_directory_name(served_endpoint):
    from layout import store as book
    from layout import detect

    seen = {}
    for name in detect.ADAPTERS:
        with support.env(**_env_for(name, served_endpoint)):
            try:
                det = detect._adapter()
            except Exception as e:
                pytest.skip(f"{name}: {type(e).__name__}: {str(e)[:60]}")
            lab = det.label()
            assert book.LABEL_OK.match(lab), f"{name}: {lab!r} is no directory"
            assert lab != det.name or name.startswith("docling"), (
                f"{name}: the label is the ADAPTER's name. One adapter serves several models; their runs would share a directory"
            )
            seen[name] = lab
    assert len(set(seen.values())) == len(seen), (
        f"two adapters claim one label: {seen}. The second run would read as a resume of the first"
    )


def test_the_reader_labels_by_the_model_not_by_itself():
    from layout import store as book
    from layout.reader import PaddleOcrVl

    r = PaddleOcrVl(policy.POLICIES["PP-DocLayoutV2"])
    assert r.label() != r.name, (
        "the reader labelled a run after itself; `paddleocr-vl` is the reader and the model is what answered"
    )
    assert book.LABEL_OK.match(r.label())


def test_a_label_that_is_not_a_directory_name_is_refused_not_sanitised():
    from layout import store as book
    from layout.errors import Refusal

    for bad in ("not declared in the weights", "a/b", "", "../up", "x" * 80):
        try:
            book.safe_label(bad, "test")
        except Refusal as e:
            assert "--run" in str(e), f"{bad!r}: the refusal names no way out"
        else:
            raise AssertionError(f"{bad!r} was accepted as a directory name")


def test_identity_ignores_what_moves_without_the_experiment():
    from layout import identity as stamp

    fp = {"model": "X", "sha256_weights": "ab"}
    a = stamp.identity(
        {**fp, "weights_dir": "/home/a"},
        {"T": "0.5", "VLM_ENDPOINT": "http://1.2.3.4:8118/v1", "LAYOUT_ADAPTER": "doclayout"},
    )
    b = stamp.identity(
        {**fp, "weights_dir": "/mnt/other"},
        {
            "T": "0.5",
            "VLM_ENDPOINT": "http://9.9.9.9:8000/v1",
            "LAYOUT_ADAPTER": "served",
            "LAYOUT_ENDPOINT": "http://9.9.9.9:8000",
        },
    )
    assert a == b, "the same experiment on another machine and another rental got another identity"
    assert a != stamp.identity({**fp, "weights_dir": "/home/a"}, {"T": "0.6"})
    assert a != stamp.identity({"model": "Y", "sha256_weights": "cd"}, {"T": "0.5"})


def test_identity_reads_only_the_knobs_the_run_read():
    from layout import knobs
    from layout import identity as stamp

    roles = {"PAGE_DPI": "the command", "LAYOUT_MODEL_NAME": "adapter"}
    was = knobs.snapshot_with_readers(roles)
    vals = stamp.knob_values({"knobs": was})
    assert set(vals) == set(roles), (
        f"identity reads {sorted(set(vals) - set(roles))} that this run does not read"
    )
    with support.env(HTML_MATH="off"):
        idle = stamp.knob_values({"knobs": knobs.snapshot_with_readers(roles)})
    assert stamp.identity({}, vals) == stamp.identity({}, idle)
    with support.env(LAYOUT_MODEL_NAME="PP-DocLayoutV3"):
        live = stamp.knob_values({"knobs": knobs.snapshot_with_readers(roles)})
    assert stamp.identity({}, vals) != stamp.identity({}, live)


def test_identity_does_not_depend_on_the_order_the_dict_was_built_in():
    from layout import identity as stamp

    a = {"b": 1, "a": [3, 2], "m": {"y": 1, "x": 2}}
    b = {"m": {"x": 2, "y": 1}, "a": [3, 2], "b": 1}
    ka = {"Z": "1", "A": "2"}
    kb = {"A": "2", "Z": "1"}
    assert stamp.identity(a, ka) == stamp.identity(b, kb), (
        "the same experiment hashed two ways depending on insertion order"
    )
    assert stamp.identity({"a": [2, 3]}, {}) != stamp.identity({"a": [3, 2]}, {})


def test_identity_is_taken_from_the_real_fingerprints_not_a_hand_written_one(served_endpoint):
    from layout import identity as stamp
    from layout import detect
    from layout.reader import PaddleOcrVl

    def flat(o, path=""):
        if isinstance(o, dict):
            for k, v in o.items():
                yield from flat(v, f"{path}/{k}")
        elif isinstance(o, list):
            for i, v in enumerate(o):
                yield from flat(v, f"{path}/{i}")
        else:
            yield (path, o)

    seen = []
    for name in detect.ADAPTERS:
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
    seen.append(("reader", PaddleOcrVl(policy.POLICIES["PP-DocLayoutV2"]).fingerprint()))
    nested = [n for n, fp in seen if any((isinstance(v, dict) and v for v in fp.values()))]
    assert nested, (
        "not one fingerprint here is NESTED, so this check cannot see a filter that reaches only the top level -- which is the defect it exists for"
    )
    for name, fp in seen:
        if not isinstance(fp.get("docling_pipeline"), dict):
            continue
        before = stamp.identity(fp, {})
        after = json.loads(json.dumps(fp))
        s = after["docling_pipeline"].get("summary")
        assert isinstance(s, dict) and s, (
            f"{name}: the pipeline fingerprint carries no summary, so this check cannot see a filter that misses one"
        )
        for k in s:
            if isinstance(s[k], int):
                s[k] += 137
        assert stamp.identity(after, {}) == before, (
            f"{name}: the identity MOVED when the pipeline's page counters did. They are run-born and nested under `docling_pipeline`, so a filter that reaches only the top level makes the identity a function of how many pages the run covered -- and the second run of one experiment is then refused forever"
        )
    for name, fp in seen:
        kept = stamp._without(fp, stamp.FINGERPRINT_NOT_IDENTITY)
        for path, value in flat(kept):
            if isinstance(value, str) and value.startswith(("/", "~")):
                raise AssertionError(
                    f"{name}: {path} = {value!r} is an absolute path and is inside the identity; the same experiment on another machine would be refused as a different one"
                )
