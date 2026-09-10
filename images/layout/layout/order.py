import functools
from collections.abc import Sequence
from typing import Any
from layout.errors import Refusal

RULES = ("ours", "docling")
DEFAULT = "ours"
WORDS = {
    "ours": "ours_top_down_left_right",
    "docling": "ours_by_choice_but_the_rule_is_foreign: reading_order_rb docling -- 740 lines of rules, not a single weight, not a model",
}
MODEL_RANK = "model_rank"


def declare(source: str, rule: str = "") -> str | None:
    if source == "model":
        return MODEL_RANK
    if source == "none":
        return None
    if source == "ours":
        if not (isinstance(rule, str) and rule.strip().lower().startswith("ours")):
            raise ValueError(
                f"an order of ours must be declared by a rule word starting with `ours`, not {rule!r}"
            )
        return rule
    raise ValueError(f"reading order source {source!r}: model, ours or none")


def rule() -> str:
    from layout import knobs

    v = (knobs.knob("ASSEMBLY_ORDER") or DEFAULT).strip()
    if v not in RULES:
        raise Refusal(
            f"ASSEMBLY_ORDER={v!r}: I know only {list(RULES)}. The book assembly rule is no place to be wrong in silence: a muddled name would shuffle the paragraphs while the boxes stayed the same, and not one box metric would notice."
        )
    return v


def cover(pol: object, which: str | None = None) -> None:
    if (which or rule()) == "ours":
        return None
    from layout.classes import Policy

    if not isinstance(pol, Policy):
        raise Refusal(
            "ASSEMBLY_ORDER=docling needs the model's policy to translate its labels for the order rules, and none was given."
        )
    return None


@functools.lru_cache(maxsize=1)
def _predictor() -> Any:
    try:
        from docling.models.postprocessing.reading_order_rb import ReadingOrderPredictor
    except ImportError as e:
        raise Refusal(
            f"ASSEMBLY_ORDER=docling, but there is no docling package: {e}. Install: the docling extra  (docling-slim and rtree, +54 MB, no torch). Or ASSEMBLY_ORDER=ours -- then the book is folded by our rule (y0, x0), which over the 600 golden pages gives 2471 extra jumps against 439; a worse choice, but free of the package."
        ) from None
    return ReadingOrderPredictor()


def permutation(
    labels: Sequence[str],
    boxes: Sequence,
    width: float,
    height: float,
    index: int,
    pol: object,
    which: str | None = None,
) -> list[int]:
    which = which or rule()
    n = len(boxes)
    if n == 0:
        return []
    if which == "ours":
        return sorted(range(n), key=lambda i: (boxes[i][1], boxes[i][0]))
    from docling.models.postprocessing.reading_order_rb import PageElement as RoElement
    from docling_core.types.doc import CoordOrigin, DocItemLabel, Size

    cover(pol, which)
    from layout.classes import Policy

    assert isinstance(pol, Policy)
    h = float(height)
    size = Size(width=float(width), height=h)
    els = []
    for i, (lab, b) in enumerate(zip(labels, boxes, strict=True)):
        els.append(
            RoElement(
                cid=i,
                text="",
                page_no=int(index),
                page_size=size,
                label=DocItemLabel(pol.order_name(lab)),
                l=float(b[0]),
                r=float(b[2]),
                b=h - float(b[3]),
                t=h - float(b[1]),
                coord_origin=CoordOrigin.BOTTOMLEFT,
            )
        )
    out = [e.cid for e in _predictor().predict_reading_order(els)]
    if sorted(out) != list(range(n)):
        raise RuntimeError(
            f"the docling order rules returned something that is not a permutation on page {index}: {n} boxes went in, {len(out)} numbers came back"
        )
    return out
