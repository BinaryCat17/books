"""BOOK ASSEMBLY ORDER -- one rule for the project, not four copies.

WHAT IT DECIDES. Level one returns contours; the book still has to be folded
into a sequence. Two models of six predict the reading order THEMSELVES --
`PP-DocLayoutV2` and `V3`, a real network rank. `plus-L`, `heron`, `egret` and
`YOLOX` have none, so we set the order. This file is "we".

WHY A FILE OF ITS OWN. The rule lived in FOUR places of three adapters, and in
two of them it was NOT what it declared:

    doclayout.py:441   our_order_key       -> (y0, x0)          declared right
    yolox_layout.py    kept.sort           -> (y0, x0)          declared right
    docling_heron.py   kept.sort  x2       -> (round(y/20), x)  DECLARED AS
                                              "ours, top down and left to
                                              right", which it is not

Twenty-pixel buckets are the very thing `doclayout.py` had rejected (the
reason stands below, at the sort). Two rules under one name, visible only by
reading all four places at once. Now the place is one.

WHICH RULE IS BETTER IS MEASURED, AND OURS LOST. THE SAME `PP-DocLayoutV2`
boxes, 600 golden pages, permuted three ways, one `books score`, one
denominator (464 pages counted):

    ours (y0, x0)             2471 extra jumps   5.33 per page
    the model's own rank, V2   501               1.08
    docling rules              439               0.95
    docling rules blindfolded  454               0.98   (every label = text)

Control: the "rank" variant gave exactly the 501 `books score` prints on the
working output -- coordinates untouched, only the list permuted. The
blindfolded run shows the win comes NOT from our label translation but from the
rules finding columns; 439 against 454 is the price of the translation, small.

STABILITY IS CHECKED, AND THE ANSWER IS TWO DIFFERENT ONES.
`metrics.column_jumps_ranking` over 16 sweep points of the grouping
parameters:

    RULER SPAN 4.02
    bounds:  ours (y0, x0)      3.021 .. 7.041
             model rank V2      0.229 .. 1.733
             docling rules      0.284 .. 1.569
    inverted pairs: "model rank V2 against docling rules"

* **ours is worse than both STABLY** -- the bounds do not overlap at any of the
  16 points. That is the one being replaced;
* **docling rules against the V2 rank the instrument CANNOT TELL APART** -- the
  pair inverts, the difference at the default being 0.13 against a span of
  4.02. So V2 and V3 keep their rank: trading working and free for a 54 MB
  dependency without a number is taste, not measurement.

WHY (y0, x0) LOSES THOUGH IT SOUNDS RIGHT: on a two-column page it reads ACROSS
the columns -- a line of the left, a line of the right, the left again. Every
crossing is an extra jump, justly: a book folded that way interleaves columns.

WHAT THIS IS NOT: fixing the model. No box coordinate is touched, nothing
merged, cut or dropped -- only the ORDER OF THE LIST, and that was always ours.
The rule "nobody fixes the model" does not apply here.

WHAT `docling` COSTS, before switching it on:

* `docling-slim` and `rtree`, +54 MB (no torch);
* THE ORDER DEPENDS ON THE PYTHON VERSION. `reading_order_rb.py` holds two
  non-transitive `sorted()` calls (lines 535 and 556, both sorting
  `PageElement` by one `__lt__`), and on the same 600 pages python 3.12.3 and
  3.13.13 diverged on THREE pages, the boxes identical to the last digit. The
  version travels into the snapshot (`detect._packages`), so the divergence is
  at least visible;
* the rules look at only EIGHT labels of their vocabulary, translated by name
  in `_LABELS`.
"""
import functools

RULES = ("ours", "docling")
DEFAULT = "ours"

# Words for the page `meta`, and also what `metrics._model_has_rank` reads:
# `ours` MUST stay the first word of the string (case is folded for it in
# `models/base.ours_order`), or the metric takes a foreign rule for a model
# rank and prints an agreement percentage out of nothing.
WORDS = {
    "ours": "ours_top_down_left_right",
    "docling": ("ours_by_choice_but_the_rule_is_foreign: reading_order_rb "
                "docling -- 740 lines of rules, not a single weight, "
                "not a model"),
}


def rule() -> str:
    """Which rule is in force. The knob comes through the registry, not the
    environment."""
    from .run import knobs
    v = (knobs.knob("ASSEMBLY_ORDER") or DEFAULT).strip()
    if v not in RULES:
        raise SystemExit(
            f"ASSEMBLY_ORDER={v!r}: знаю только {list(RULES)}. Правило сборки "
            f"книги — не то место, где можно ошибиться молча: перепутанное имя "
            f"перемешало бы абзацы, а рамки остались бы теми же, и ни одна "
            f"метрика рамок этого не заметила бы.")
    return v


# TRANSLATED BY NAME, NOT DERIVED FROM THE ROLE. Same argument as the reading
# routes in `models/paddleocr_vl/reader.py`: each detector has its OWN
# vocabulary -- 25 names in V2, 20 in plus-L, 17 in each docling model, 11 in
# DocLayNet -- and "what I do not know is text" would silently carry the
# twenty-sixth class of new weights under a wrong name. The role
# (`policy.role`) will not do: it answers "cut out or print", while the rules
# need "page header or page footer", which the role "service" does not tell
# apart.
#
# The rules look at exactly eight names (checked by reading
# `reading_order_rb`): CAPTION, CODE, FOOTNOTE, PAGE_FOOTER, PAGE_HEADER,
# PICTURE, TABLE, TEXT. Anything unlisted is TEXT, and that is a VALUE, not a
# default: the rules have no separate behaviour for "paragraph" and "section
# header".
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
    """Is there a translation for THIS vocabulary. Fails before page one.

    ASKED ONLY WHEN NEEDED. The `ours` rule needs no labels -- it looks at
    coordinates -- and demanding a declared policy for it would kill a run over
    a vocabulary the rule never touches. The first edition did that, caught by
    a stub adapter with one label.

    `vocab` is the model's FULL vocabulary (`self.labels`), not the page's
    labels: the policy is chosen by vocabulary, not by a hand-typed name --
    `policy.for_labels` again, called here rather than rewritten.

    An unknown label inside a known vocabulary is no trouble: it rides as
    `text`, a declared value. A foreign vocabulary whole is: the rules have
    separate behaviour for running heads, and under a foreign one a running
    head would sail into the body of the page. Silently.
    """
    if (which or rule()) == "ours":
        return None
    from . import policy
    name = policy.for_labels(vocab)
    if name not in _LABELS:
        raise SystemExit(
            f"ASSEMBLY_ORDER=docling, а перевода ярлыков под словарь {name!r} "
            f"нет: знаю {sorted(_LABELS)}. Правила порядка смотрят на восемь "
            f"имён, и по чужому словарю колонтитул уехал бы в тело страницы.")
    return name


@functools.lru_cache(maxsize=1)
def _predictor():
    """ONE order predictor per run.

    Its constructor sets two numbers of its own (`dilated_page_element`, the
    horizontal expansion threshold 0.15); building it afresh per page would
    promise they may drift. Same argument as `_DoclingPipeline` in
    `models/docling_heron.py`.
    """
    try:
        from docling.models.postprocessing.reading_order_rb import (
            ReadingOrderPredictor)
    except ImportError as e:
        raise SystemExit(
            f"ASSEMBLY_ORDER=docling, а пакета docling нет: {e}. Поставить: "
            f'pip install -e ".[docling]"  (docling-slim и rtree, +54 МБ, без '
            f"torch). Либо ASSEMBLY_ORDER=ours — тогда книга складывается "
            f"нашим правилом (y0, x0), которое на 600 страницах золотого "
            f"стенда даёт 2471 лишний прыжок против 439; выбор хуже, но "
            f"свободен от пакета.") from None
    return ReadingOrderPredictor()


def permutation(labels, boxes, width, height, index, vocab,
                which=None) -> list[int]:
    """Permutation of the block list. Returns INDICES, not blocks.

    Indices on purpose: three adapters carry three list shapes (a
    `(label, score, box)` tuple in yolox and heron, a numpy row in doclayout),
    and the shared rule must know none of them. Each used to sort itself, and
    the shapes drifted along with the rules.

    `boxes` are in page pixels, origin at the TOP LEFT as everywhere here; the
    docling rules count from the BOTTOM (`self.b > other.b`), converted here.
    Fed as they come, the book would be read bottom up and no box metric would
    notice -- the trap named in section 19 of `docs/contour-notes.md`.
    """
    which = which or rule()
    n = len(boxes)
    if n == 0:
        return []
    if which == "ours":
        # NO y buckets, on purpose: `round(y/20)` is raster pixels, and at
        # another PAGE_DPI row neighbours would swap places with no knob to
        # declare it.
        return sorted(range(n), key=lambda i: (boxes[i][1], boxes[i][0]))

    from docling.models.postprocessing.reading_order_rb import (
        PageElement as RoElement)
    from docling_core.types.doc import CoordOrigin, DocItemLabel, Size

    tr = _LABELS[cover(vocab, which)]
    h = float(height)
    size = Size(width=float(width), height=h)
    els = []
    for i, (lab, b) in enumerate(zip(labels, boxes)):
        els.append(RoElement(
            cid=i, text="", page_no=int(index), page_size=size,
            label=DocItemLabel(tr.get(lab, "text")),
            l=float(b[0]), r=float(b[2]),
            b=h - float(b[3]), t=h - float(b[1]),
            coord_origin=CoordOrigin.BOTTOMLEFT))
    out = [e.cid for e in _predictor().predict_reading_order(els)]
    # A PERMUTATION MUST BE A PERMUTATION. The rules split running heads and
    # body into three lists and stitch them back; lose an element there and a
    # box would vanish from the book silently, while the count "after" would
    # merely look a little smaller.
    if sorted(out) != list(range(n)):
        raise RuntimeError(
            f"правила порядка docling вернули не перестановку на странице "
            f"{index}: было {n} рамок, вернулось {len(out)} номеров")
    return out
