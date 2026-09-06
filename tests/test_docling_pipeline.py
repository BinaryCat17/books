"""The docling vendor pipeline: translation by name, and the price of the
knob being off.

Two things, both about a conspiracy of two files.

FIRST. The translation of our weights' labels into docling's vocabulary is
declared BY NAME (`EGRET_TO_DOCLING`), not by a rule "lowercase, hyphen into
underscore". A rule would silently accept an eighteenth class of new weights
and hand it to the vendor under an invented name. So an unknown name must
fail the CONSTRUCTION of the pipeline -- on page zero and over the whole
weight vocabulary at once, not on page four hundred after twenty minutes of
counting.

SECOND. `DOCLING_PIPELINE=off` is the default, and it was bought by
measurement: the pipeline worsens merging (366 -> 461), findability (694 ->
562) and wholeness of meaning (602 -> 500). Switched off it must therefore be
not merely harmless but IDENTICAL to the earlier code: the same boxes, the
same objects, the same place for the key in meta. Otherwise the comparison
"the knob is off, nothing changed" stumbles over json key order, not boxes.
"""
import json
import os
from dataclasses import asdict

import support
from booksmith import policy
from booksmith.models import docling_heron as dh
from booksmith.models.base import Block
from booksmith.run import knobs

OFF_META_KEYS = ["reading_order"]
# The composition and order of the page's meta keys BEFORE the pipeline
# existed. The pipeline put `**pipe_meta` exactly where "reading order" had
# stood, and at `off` it unfolds into that same key -- the page comes out
# byte for byte as before.
META_BEFORE_PIPELINE = ["detector", "raster", "boxes_accepted",
                        "rank_ties", "reading_order",
                        "best_rejected_by_class"]


class env:
    """A knob for the length of a check. The environment is live:
    put back as it was.
    """

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
    """`DOCLING_PIPELINE=on` fails the run and names what it does know.

    The fall costs milliseconds and happens BEFORE docling is imported: the
    mode check is the first line of the constructor.
    """
    try:
        dh._DoclingPipeline("on", list(dh.DEFAULT_LABELS), "docling")
    except SystemExit as e:
        assert "off" in str(e) and "post" in str(e) and "full" in str(e)
    else:
        raise AssertionError("an unknown knob mode was accepted silently")


def test_translation_covers_both_dictionaries():
    """The translation is checked against BOTH policy vocabularies, not one.

    The keys of `EGRET_TO_DOCLING` are egret's display names, the values are
    heron's snake_case. Those same two sets are declared by the policies
    `Docling-egret` and `Docling`. Let them drift apart and the vendor gets
    an invented name, while `policy.check` fails the run on our own bench.
    """
    assert set(dh.EGRET_TO_DOCLING) == set(policy.DOCLING_EGRET), (
        "the translation table and the egret policy diverged: "
        f"{sorted(set(dh.EGRET_TO_DOCLING) ^ set(policy.DOCLING_EGRET))}")
    assert set(dh.EGRET_TO_DOCLING.values()) == set(policy.DOCLING), (
        "the translation does not lead into heron's vocabulary: "
        f"{sorted(set(dh.EGRET_TO_DOCLING.values()) ^ set(policy.DOCLING))}")
    assert set(dh.DEFAULT_LABELS) == set(policy.DOCLING), (
        "heron's fallback label vocabulary diverged from the Docling policy")


def test_unknown_label_dies_at_construction():
    """An unknown name fails the CONSTRUCTION, not the first page.

    Checked over the whole weight vocabulary at once: a foreign label might
    not turn up on a page, and the run is wrong all the same.
    """
    if not have_docling():
        support.skip("no docling package: pip install -e \".[docling]\"")
    good = list(dh.DEFAULT_LABELS)
    dh._DoclingPipeline("post", good, "docling")   # whole weight vocabulary
    try:
        dh._DoclingPipeline("post", good + ["Chart"], "docling")
    except SystemExit as e:
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
        support.skip("no_docling_package")
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
    """With the knob off the boxes are neither copied nor touched AT ALL.

    Identity of the object is compared, not equality: a copy made just in
    case would already be a place where something can change.
    """
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


def test_off_keeps_meta_key_order_byte_for_byte():
    """A key's place in the dict is not cosmetic: json writes keys in order."""
    keys = support.meta_keys("models/docling_heron.py", "DoclingHeron")
    assert "**pipe_meta" in keys, (
        "the page's meta no longer holds `**pipe_meta`: either the pipeline "
        "writes its keys elsewhere, or this check has fallen behind the code")
    i = keys.index("**pipe_meta")
    got = keys[:i] + OFF_META_KEYS + keys[i + 1:]
    assert got == META_BEFORE_PIPELINE, (
        f"at DOCLING_PIPELINE=off the composition or the order of the meta "
        f"keys changed:\n"
        f"  was  {META_BEFORE_PIPELINE}\n  now  {got}\n"
        f"There is no byte-for-byte match with the earlier pages any more.")


def test_adapter_at_off_builds_no_pipeline():
    """The live adapter on real weights: at off there is no vendor code at all.

    Slow (it raises an ONNX session), hence on demand: --slow.
    """
    if not os.environ.get("BOOKSMITH_TESTS_SLOW"):
        support.skip("slow (~5s, raises ONNX): run it with --slow")
    if not os.path.isdir(os.path.join(dh.MODELS, "docling-heron_onnx")):
        support.skip("no docling-heron_onnx weights")
    with env(DOCLING_PIPELINE="off"):
        a = dh.DoclingHeron()
    assert a.pipeline == "off"
    assert a._pipe is None, "the knob is off, yet the vendor pipeline is built"
    assert "DOCLING_PIPELINE" in a.knobs_read(), (
        "the knob decides the run, yet the adapter does not declare it -- "
        "the snapshots of two different runs become indistinguishable")
