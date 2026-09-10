"""A model behind an endpoint: the describe is checked, a served run measures
as the model it serves, its identity is the model's and not the address's,
and a hybrid files as a read run with its own boxes."""
import json
import os
import shutil

import pytest

import support
from booksmith.core import config, job, served, stamp
from booksmith.core.errors import Refusal
from booksmith.datasets import table
from booksmith.datasets.bench import Bench, Run
from booksmith.processing.layout import detect
from fake_layout import FakeLayout

# A one-pixel PNG: the stand-in never looks at the image.
PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
       b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xff"
       b"\xff?\x00\x05\xfe\x02\xfe\xa7V\xbd\xfa\x00\x00\x00\x00IEND\xaeB`\x82")


def _copy(slovar, tmp_path):
    """A private copy of the drawn bench: a run written into the shared
    fixture would be a second run for every test that counts them."""
    root = str(tmp_path / "bench" / "slovar")
    shutil.copytree(slovar.root, root)
    return Bench.open(root)


def _values(records):
    return {(r.metric, n): s.value for r in records for n, s in r.scalars.items()}


def _differ(mine, perfect):
    """Scalars both sides carry a number for, and disagree on. A null with a
    reason is a statement, not a number: a bare truth run has no snapshot to
    check, a layout run has no text to weigh."""
    return {k: (mine[k], perfect[k]) for k in set(mine) & set(perfect)
            if mine[k] is not None and perfect[k] is not None
            and mine[k] != perfect[k]}


def _restamp_tool():
    """`tools/restamp.py`, by path: `tools/` is a directory of scripts, not a
    package on the test path."""
    import importlib.util
    path = os.path.join(config.ROOT, "tools", "restamp.py")
    spec = importlib.util.spec_from_file_location("restamp", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _served(url, **more):
    return job.Job(settings={"LAYOUT_ADAPTER": "served",
                             "LAYOUT_ENDPOINT": url, **more})


# ------------------------------------------------------------- the shapes

def test_a_describe_round_trips_and_a_wrong_one_is_refused_by_field():
    d = served.Describe(kind="layout", label="M", fingerprint={"sha256_weights": "ab"},
                        labels=("text",), vocabulary="PP-DocLayoutV2",
                        reading_order="own", knobs={"A": "1"})
    assert served.Describe.from_json(d.to_json()) == d
    good = d.to_json()
    for field, value in (("protocol", 2), ("kind", "oracle"), ("label", ""),
                         ("fingerprint", {}), ("labels", []),
                         ("reading_order", "maybe"), ("knobs", {"A": 1})):
        bad = {**good, field: value}
        with pytest.raises(Refusal) as e:
            served.Describe.from_json(bad)
        assert field in str(e.value) or "protocol" in str(e.value), field
    with pytest.raises(Refusal):
        served.Describe.from_json({**good, "kind": "reader"})   # no openai.model
    with pytest.raises(Refusal):
        served.Describe.from_json({**good, "kind": "hybrid"})   # no kinds
    assert served.root_of("http://h:1/v1/") == "http://h:1"
    assert served.root_of("http://h:1") == "http://h:1"


def test_identity_is_the_fingerprint_with_the_knobs_of_both_sides():
    d = served.Describe(kind="layout", label="M", fingerprint={"sha256_weights": "ab"},
                        labels=("text",), knobs={"LAYOUT_SCORE_THRESHOLD": "0.5"})
    both = served.identity_of(d, {"PAGE_DPI": "144", "LAYOUT_ENDPOINT": "http://a"})
    assert both == stamp.identity({"sha256_weights": "ab"},
                                  {"LAYOUT_SCORE_THRESHOLD": "0.5", "PAGE_DPI": "144"})
    assert both == served.identity_of(d, {"PAGE_DPI": "144", "LAYOUT_ENDPOINT": "http://b",
                                          "LAYOUT_ADAPTER": "served"}), (
        "the address or the adapter moved the identity")
    assert both != served.identity_of(d, {"PAGE_DPI": "72"})
    with pytest.raises(Refusal):
        served.identity_of(d, {"LAYOUT_SCORE_THRESHOLD": "0.6"})


# ------------------------------------------------------------ the adapter

def test_the_adapter_refuses_what_the_model_did_not_declare(slovar, tmp_path):
    png = str(tmp_path / "p.png")
    with open(png, "wb") as f:
        f.write(PNG)
    with FakeLayout(slovar.truth_dir, keep_content=True) as fake:
        with _served(fake.url).active():
            det = detect._adapter()
            assert det.label() == "truth" and det.where() == fake.url
            assert det.served()["kind"] == "layout"
            with pytest.raises(Refusal) as e:
                det.read(png, 0, 144.0)
            assert "content" in str(e.value)
    with _served("http://127.0.0.1:1").active(), pytest.raises(Refusal) as e:
        detect._adapter()
    assert "describe" in str(e.value)
    with _served("").active(), pytest.raises(Refusal):
        detect._adapter()


# ---------------------------------------------------------- a served run

def test_a_served_run_measures_as_truth_against_itself_and_a_changed_model_is_refused(slovar, tmp_path):
    b = _copy(slovar, tmp_path)
    out = os.path.join(b.root, "detect", "truth")
    with FakeLayout(b.truth_dir) as fake, support.said():
        with _served(fake.url).active():
            got = detect.run(b.pdf, out, det=detect._adapter())
        assert got == out and len(fake.seen) == 13
        assert fake.seen[0]["dpi"] == 144.0 and fake.seen[0]["bytes"] > 100
        run = Run.open(out)
        assert run.snapshot["served"]["label"] == "truth"
        assert run.snapshot["identity"] == served.identity_of(
            fake.describe, {"PAGE_DPI": "144"})
        with support.said():
            mine = _values(table.rows(b, run))
            perfect = _values(table.rows(b, Run.bare(b.truth_dir, "truth")))
        off = _differ(mine, perfect)
        assert not off, f"a served run of the truth is not truth: {off}"
        assert mine[("contour", "artefacts_found")] == 1.0
        # A layout run carries no text, and the ink metric says so.
        assert mine[("fitness", "ink_as_text")] is None
        # The same label, another model: refused before a page is rendered.
        fp = {**fake.describe.fingerprint, "sha256_weights": "ff" * 32}
        with FakeLayout(b.truth_dir, fingerprint=fp) as other:
            with _served(other.url).active(), pytest.raises(Refusal) as e:
                detect.run(b.pdf, out, det=detect._adapter())
            assert "DIFFERENT experiment" in str(e.value)
            assert other.seen == [], "a page was asked before the refusal"
    # The re-stamp tool leaves a run stamped by today's rule alone.
    old, new = _restamp_tool().restamp(os.path.join(out, "run.json"))
    assert old == new


def test_a_hybrid_files_as_a_read_run_with_its_own_boxes(slovar, tmp_path):
    b = _copy(slovar, tmp_path)
    out = os.path.join(b.root, "read", "truth")
    with FakeLayout(b.truth_dir, kind="hybrid") as fake, support.said():
        with _served(fake.url).active():
            det = detect._adapter()
            detect.run(b.pdf, out, det=det, hybrid=True)
        run = Run.open(out)
        assert run.kind == "read" and run.level == "hybrid"
        assert run.snapshot["layout"] == "own" and run.snapshot["detection"] is None
        assert run.snapshot["kinds"] == ["text"]
        assert run.snapshot["repeat_command"].startswith("books hybrid ")
        pages = run.pages()
        assert any(bl.get("content") for p in pages.values() for bl in p["blocks"])
        with support.said():
            mine = _values(table.rows(b, run))
            perfect = _values(table.rows(b, Run.bare(b.truth_dir, "truth")))
        assert any(m == "text" for m, _ in mine), "the reading metric did not apply"
        off = _differ(mine, perfect)
        assert not off, f"a hybrid run of the truth is not truth: {off}"
        assert mine[("fitness", "ink_as_text")] is not None, (
            "a hybrid carries text, and the ink metric did not see it")
    # A layout model cannot be filed as a hybrid.
    with FakeLayout(b.truth_dir) as fake, support.said():
        with _served(fake.url).active(), pytest.raises(Refusal) as e:
            detect.run(b.pdf, out + "2", det=detect._adapter(), hybrid=True)
        assert "hybrid" in str(e.value)


def test_a_served_run_of_a_tracked_model_has_the_tracked_identity(slovar):
    """The describe carries the tracked run's fingerprint and the knobs its
    adapter read; the client reads only what the detect command reads. The
    identity must be the one the tracked snapshot carries."""
    path = os.path.join(config.ROOT, "bench", "hard", "detect",
                        "PP-DocLayoutV2", "run.json")
    if not os.path.isfile(path):
        pytest.skip("no tracked PP-DocLayoutV2 run on this clone")
    with open(path, encoding="utf-8") as f:
        snap = json.load(f)
    theirs = {n: e["value"] for n, e in snap["knobs"].items()
              if e.get("for_this_run") and n not in detect.COMMAND_KNOBS}
    with FakeLayout(slovar.truth_dir, label=snap["label"],
                    fingerprint=snap["fingerprint"], knobs=theirs) as fake:
        with _served(fake.url, PAGE_DPI=snap["knobs"]["PAGE_DPI"]["value"]).active():
            det = detect._adapter()
            assert detect._identity(det, detect._knob_roles(det)) == snap["identity"]
