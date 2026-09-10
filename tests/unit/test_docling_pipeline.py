"""The docling vendor pipeline: translation by name, and the price of `off`.

The translation of our weights' labels into docling's vocabulary is declared by
name (`EGRET_TO_DOCLING`), not by a rule that would accept a new class under an
invented name; an unknown name fails the construction, not page four hundred.

`DOCLING_PIPELINE=off` is the default, and switched off the pipeline must be not
merely harmless but identical to the code without it: the same boxes, the same
objects, the same place for the key in meta.
"""
import json
import os

import pytest
from dataclasses import asdict

from booksmith.core.errors import Refusal
from booksmith.core import policy
from booksmith.processing.layout.adapters import docling as dh
from booksmith.core.page import Block
from booksmith.core import knobs

EGRET = policy.VOCABULARIES["Docling-egret"]
DOCLING = policy.VOCABULARIES["Docling"]

OFF_META_KEYS = ["reading_order"]
# The composition and order of the page's meta keys without the pipeline; at
# `off` the pipeline unfolds into that same key and the page comes out as before.
META_BEFORE_PIPELINE = ["detector", "boxes_accepted",
                        "rank_ties", "reading_order",
                        "best_rejected_by_class"]


class env:
    """A knob for the length of a check; the environment is live and is put back."""

    def __init__(self, **kw):
        self.kw, self.old = kw, {}

    def __enter__(self):
        for k, v in self.kw.items():
            self.old[k] = os.environ.get(k)
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def __exit__(self, *a):
        for k, v in self.old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def have_docling():
    try:
        import docling                                       # noqa: F401
        return True
    except ImportError:
        return False


def test_pipeline_default_is_off():
    """The default is OFF, a decision of measurement and not of taste."""
    assert knobs.KNOB["DOCLING_PIPELINE"].default == "off"
    with env(DOCLING_PIPELINE=None):
        assert knobs.knob("DOCLING_PIPELINE") == "off"


def test_three_modes_not_two():
    """`post` and `full` are different values: the effects differ."""
    assert dh.PIPELINE_MODES == ("off", "post", "full")


def test_unknown_mode_dies_loudly():
    """`DOCLING_PIPELINE=on` fails the run and names what it does know, before
    docling is imported: the mode check is the first line of the constructor."""
    try:
        dh._DoclingPipeline("on", list(dh.DEFAULT_LABELS), "docling")
    except Refusal as e:
        assert "off" in str(e) and "post" in str(e) and "full" in str(e)
    else:
        raise AssertionError("an unknown knob mode was accepted silently")


def test_translation_covers_both_dictionaries():
    """The translation is checked against both policy vocabularies, not one: the
    keys of `EGRET_TO_DOCLING` are egret's display names, the values heron's
    snake_case, and a drift hands the vendor an invented name."""
    assert set(dh.EGRET_TO_DOCLING) == set(EGRET), (
        "the translation table and the egret policy diverged: "
        f"{sorted(set(dh.EGRET_TO_DOCLING) ^ set(EGRET))}")
    assert set(dh.EGRET_TO_DOCLING.values()) == set(DOCLING), (
        "the translation does not lead into heron's vocabulary: "
        f"{sorted(set(dh.EGRET_TO_DOCLING.values()) ^ set(DOCLING))}")
    assert set(dh.DEFAULT_LABELS) == set(DOCLING), (
        "heron's fallback label vocabulary diverged from the Docling policy")


def test_unknown_label_dies_at_construction():
    """An unknown name fails the construction, not the first page: checked over
    the whole weight vocabulary at once, since a foreign label might not turn up
    on a page and the run is wrong all the same."""
    if not have_docling():
        pytest.skip("no docling package: pip install -e \".[docling]\"")
    good = list(dh.DEFAULT_LABELS)
    dh._DoclingPipeline("post", good, "docling")   # whole weight vocabulary
    try:
        dh._DoclingPipeline("post", good + ["Chart"], "docling")
    except Refusal as e:
        assert "Chart" in str(e), f"the complaint omits the label itself: {e}"
        assert "EGRET_TO_DOCLING" in str(e), (
            f"the complaint does not say WHERE to fix it: {e}")
    else:
        raise AssertionError(
            "the pipeline was built with a vocabulary holding an "
            "untranslatable label: it will reach the vendor under an "
            "invented name")


def test_egret_names_translate_whole():
    """Every egret display name translates, by that same construction."""
    if not have_docling():
        pytest.skip("no docling package: pip install -e \".[docling]\"")
    p = dh._DoclingPipeline("post", list(dh.EGRET_TO_DOCLING),
                            "docling-egret")
    assert set(p.to_docling) == set(dh.EGRET_TO_DOCLING)
    assert set(p.back) == set(dh.EGRET_TO_DOCLING.values()), (
        "the reverse translation is incomplete: outward a label must come "
        "back in the adapter's spelling, or policy.check fails the egret run")


def _blocks():
    return [Block(block_id=0, box=(10.0, 20.0, 110.0, 60.0), label="table",
                  score=0.9, order=0),
            Block(block_id=1, box=(10.0, 70.0, 110.0, 90.0), label="text",
                  score=0.8, order=1)]


def test_off_returns_the_very_same_frames():
    """With the knob off the boxes are neither copied nor touched at all: identity
    of the object is compared, not equality -- a copy made just in case is already
    a place where something can change."""
    adapter = object.__new__(dh.DoclingHeron)
    adapter._pipe = None
    blocks = _blocks()
    before = json.dumps([asdict(b) for b in blocks], ensure_ascii=False)
    out, meta = adapter._run_pipeline(blocks, 800, 1200, 0)
    assert out is blocks, "at off the boxes are rebuilt -- no longer as is"
    assert json.dumps([asdict(b) for b in out], ensure_ascii=False) == before


def test_off_adds_exactly_one_meta_key():
    """And exactly one meta key, that one. An extra key is another page."""
    adapter = object.__new__(dh.DoclingHeron)
    adapter._pipe = None
    _, meta = adapter._run_pipeline(_blocks(), 800, 1200, 0)
    assert list(meta) == OFF_META_KEYS, (
        f"at off the page's meta got {list(meta)}, while before it held the "
        f"single key {OFF_META_KEYS}")


@pytest.mark.slow
def test_adapter_at_off_builds_no_pipeline():
    """The live adapter on real weights: at off there is no vendor code at all."""
    if not os.path.isdir(os.path.join(dh.MODELS, "docling-heron_onnx")):
        pytest.skip("no docling-heron_onnx weights")
    with env(DOCLING_PIPELINE="off"):
        a = dh.DoclingHeron()
    assert a.pipeline == "off"
    assert a._pipe is None, "the knob is off, yet the vendor pipeline is built"
    assert "DOCLING_PIPELINE" in a.knobs_read(), (
        "the knob decides the run, yet the adapter does not declare it -- "
        "the snapshots of two different runs become indistinguishable")
