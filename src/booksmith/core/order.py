"""The book assembly order: one rule for the project, chosen by a knob.

Level one returns contours; the book still has to be folded into a sequence.
`PP-DocLayoutV2` and `V3` predict the reading order themselves; `plus-L`,
`heron`, `egret` and `YOLOX` do not, and this file supplies it. `ASSEMBLY_ORDER`
picks between `ours`, which sorts by (y0, x0), and `docling`, the vendor's rules
over eight of their labels, which find columns where (y0, x0) reads across them
and cost `docling-slim` and `rtree`, +54 MB.

No box coordinate is touched here -- only the order of the list, which is ours.
"""
import functools
from booksmith.core.errors import Refusal

RULES = ("ours", "docling")
# `ours` is free; `docling` folds better -- 439 extra column jumps against 2471.
DEFAULT = "ours"

# `ours` must stay the first word, or the metric takes our order for a model rank.
WORDS = {
    "ours": "ours_top_down_left_right",
    "docling": ("ours_by_choice_but_the_rule_is_foreign: reading_order_rb "
                "docling -- 740 lines of rules, not a single weight, "
                "not a model"),
}


MODEL_RANK = "model_rank"


def declare(source: str, rule: str = "") -> str | None:
    """The one way to write `meta["reading_order"]`.

    `"model"`: the model's own rank. `"ours"`: our order by a rule whose word
    starts with `ours`. `"none"`: the model gives no order at all.
    """
    if source == "model":
        return MODEL_RANK
    if source == "none":
        return None
    if source == "ours":
        if not (isinstance(rule, str) and rule.strip().lower().startswith("ours")):
            raise ValueError(f"an order of ours must be declared by a rule word "
                             f"starting with `ours`, not {rule!r}")
        return rule
    raise ValueError(f"reading order source {source!r}: model, ours or none")


def rule() -> str:
    """Which rule is in force. The knob comes through the registry, not the
    environment."""
    from booksmith.core import knobs
    v = (knobs.knob("ASSEMBLY_ORDER") or DEFAULT).strip()
    if v not in RULES:
        raise Refusal(
            f"ASSEMBLY_ORDER={v!r}: I know only {list(RULES)}. The book "
            f"assembly rule is no place to be wrong in silence: a muddled "
            f"name would shuffle the paragraphs while the boxes stayed the "
            f"same, and not one box metric would notice.")
    return v


# Translated by name, not by role: the rules need page header against page footer.
# They read eight names; anything unlisted rides as `text`, a value, not a default.
_LABELS = {
    "PP-DocLayoutV2": {
        "header": "page_header", "header_image": "page_header",
        "footer": "page_footer", "footer_image": "page_footer",
        "number": "page_footer",
        "footnote": "footnote", "vision_footnote": "footnote",
        "figure_title": "caption",
        "table": "table",
        "image": "picture", "chart": "picture", "seal": "picture",
        "display_formula": "picture",
        "algorithm": "code",
    },
    "PP-DocLayout_plus-L": {
        "header": "page_header", "footer": "page_footer",
        "number": "page_footer",
        "footnote": "footnote", "figure_title": "caption",
        "table": "table",
        "image": "picture", "chart": "picture", "seal": "picture",
        "formula": "picture",
        "algorithm": "code",
    },
    "Docling": {
        "page_header": "page_header", "page_footer": "page_footer",
        "footnote": "footnote", "caption": "caption",
        "table": "table", "picture": "picture", "formula": "picture",
        "code": "code",
    },
    "Docling-egret": {
        "Page-header": "page_header", "Page-footer": "page_footer",
        "Footnote": "footnote", "Caption": "caption",
        "Table": "table", "Picture": "picture", "Formula": "picture",
        "Code": "code",
    },
    "DocLayNet": {
        "Page-header": "page_header", "Page-footer": "page_footer",
        "Footnote": "footnote", "Caption": "caption",
        "Table": "table", "Picture": "picture", "Formula": "picture",
    },
}


def cover(vocab, which=None) -> str | None:
    """Is there a translation for this vocabulary. Fails before page one.

    Asked only for the `docling` rule, the one that reads labels, and by the
    model's full vocabulary -- a foreign one sails a running head into the body.
    """
    if (which or rule()) == "ours":
        return None
    from booksmith.core import policy
    name = policy.for_labels(vocab)
    if name not in _LABELS:
        raise Refusal(
            f"ASSEMBLY_ORDER=docling, but there is no label translation for "
            f"the vocabulary {name!r}: I know {sorted(_LABELS)}. The order "
            f"rules look at eight names, and under a foreign vocabulary a "
            f"running head would sail into the body of the page.")
    return name


@functools.lru_cache(maxsize=1)
def _predictor():
    """One order predictor per run.

    Its constructor sets two numbers of its own (`dilated_page_element`, the
    horizontal threshold 0.15), and one per page would let them drift.
    """
    try:
        from docling.models.postprocessing.reading_order_rb import (
            ReadingOrderPredictor)
    except ImportError as e:
        raise Refusal(
            f"ASSEMBLY_ORDER=docling, but there is no docling package: {e}. "
            f'Install: pip install -e ".[docling]"  (docling-slim and rtree, '
            f"+54 MB, no torch). Or ASSEMBLY_ORDER=ours -- then the book is "
            f"folded by our rule (y0, x0), which over the 600 golden pages "
            f"gives 2471 extra jumps against 439; a worse choice, but free of "
            f"the package.") from None
    return ReadingOrderPredictor()


def permutation(labels, boxes, width, height, index, vocab,
                which=None) -> list[int]:
    """Permutation of the block list, as indices, since three adapters carry
    three list shapes and the shared rule knows none of them. `boxes` are page
    pixels, origin top left; the docling rules count from the bottom.
    """
    which = which or rule()
    n = len(boxes)
    if n == 0:
        return []
    if which == "ours":
        # No y buckets: `round(y/20)` is raster pixels, so at another PAGE_DPI
        # row neighbours would swap places with no knob to declare it.
        return sorted(range(n), key=lambda i: (boxes[i][1], boxes[i][0]))

    # The vendor's two non-transitive sorts make this order python-version dependent.
    from docling.models.postprocessing.reading_order_rb import (
        PageElement as RoElement)
    from docling_core.types.doc import CoordOrigin, DocItemLabel, Size

    tr = _LABELS[cover(vocab, which)]
    h = float(height)
    size = Size(width=float(width), height=h)
    els = []
    for i, (lab, b) in enumerate(zip(labels, boxes, strict=True)):
        els.append(RoElement(
            cid=i, text="", page_no=int(index), page_size=size,
            label=DocItemLabel(tr.get(lab, "text")),
            l=float(b[0]), r=float(b[2]),
            b=h - float(b[3]), t=h - float(b[1]),
            coord_origin=CoordOrigin.BOTTOMLEFT))
    out = [e.cid for e in _predictor().predict_reading_order(els)]
    # A permutation must be a permutation, or a box vanishes from the book silently.
    if sorted(out) != list(range(n)):
        raise RuntimeError(
            f"the docling order rules returned something that is not a "
            f"permutation on page {index}: {n} boxes went in, {len(out)} "
            f"numbers came back")
    return out
