import os
import re
import support
from backend.errors import Refusal
from backend.served import Served
from backend import knobs

ADAPTERS = ((Served, "served.py"),)


def test_unknown_knob_raises_not_returns_empty():
    try:
        knobs.knob("MULTIVIEW")
    except KeyError as e:
        assert "MULTIVIEW" in str(e) and "KNOBS" in str(e), (
            f"the complaint names neither the knob nor the registry: {e}"
        )
    else:
        raise AssertionError(
            "the registry gave a value for a knob it does not hold: that knob will not reach the snapshot, and the run becomes silently unrepeatable"
        )


def test_names_are_unique():
    names = [k.name for k in knobs.KNOBS]
    assert len(names) == len(set(names)), (
        f"knob names repeat: {sorted({n for n in names if names.count(n) > 1})}"
    )


def test_defaults_are_strings():
    for k in knobs.KNOBS:
        assert isinstance(k.default, str), f"{k.name}: the default {k.default!r} is not a string"
        assert k.what, f"{k.name}: it does not say what it does"


def test_snapshot_holds_every_knob_with_every_field():
    s = knobs.snapshot()
    assert set(s) == set(knobs.names()), (
        f"the snapshot holds {len(s)} knobs of {len(knobs.names())}: {sorted(set(knobs.names()) ^ set(s))}"
    )
    for name, rec in s.items():
        assert set(rec) == {"value", "default", "set_externally", "what", "debt"}, (
            f"{name}: snapshot fields {sorted(rec)}"
        )


def test_snapshot_tells_set_from_default():
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
            "the default in the snapshot was replaced by the value given: there is nothing left to compare a run against the default with"
        )
        os.environ[name] = ""
        assert knobs.knob(name) == "", "an empty string from outside lost to the default"
    finally:
        os.environ.pop(name, None)
        if old is not None:
            os.environ[name] = old


def test_passthrough_carries_only_what_was_set():
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


_SH_OPEN = re.compile("\\$\\{([A-Z_][A-Z0-9_]*):-")


def test_no_numeric_knob_takes_a_value_that_is_not_a_number():
    numeric = []
    for k in knobs.KNOBS:
        try:
            float(k.default)
        except (TypeError, ValueError):
            continue
        numeric.append(k.name)
    assert len(numeric) >= 10, (
        f"only {len(numeric)} knobs look numeric: {numeric}. The registry has changed shape and this check is now looking at almost nothing"
    )
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
                    f"{name}={bad!r} was accepted as {got!r}. Every guard comparing it will be quietly false, and the run will finish and say nothing"
                )
            os.environ.pop(name, None)
    finally:
        os.environ.clear()
        os.environ.update(was)


def test_every_numeric_knob_is_read_through_the_one_reader():
    import glob

    bad = []
    root = support.SRC
    for path in glob.glob(os.path.join(support.SRC, "**", "*.py"), recursive=True):
        text = open(path, encoding="utf-8").read()
        for m in re.finditer("(?:float|int)\\(\\s*knobs?\\.knob\\(", text):
            line = text[: m.start()].count("\n") + 1
            bad.append(f"{os.path.relpath(path, root)}:{line}")
    assert not bad, (
        f"a knob is read as a number past `knobs.number`: {bad}. That is the spelling `nan` walked through -- `float()` accepts it and every comparison after it is False"
    )
