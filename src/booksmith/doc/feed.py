"""What exactly goes to the VLM: a crop by box, or a page with holes.

Two feeds, HYPOTHESES both when written. `crop` has since run for real --
`books read`, 436 pages, $0.545; `masked_page` never has, and cannot from the
paying path: `books read` cuts its own crops and never asks `VLM_INPUT`, which
only `books feed` reads. The two are still unmeasured against each other.

    crop         one request per text block, as the PaddleOCR-VL pipeline
                 ships: measured on an earlier run, 409 requests over 25
                 pages, sixteen a page.
    masked_page  one request per page, artifacts painted over. Sixteen times
                 fewer calls, and the model sees coherent text whole --
                 hyphenation, columns, a paragraph continuing past a figure.

In BOTH, artifacts do not go to the VLM at all. That is the first level: read
the text, cut tables and figures out as pictures, do not parse them. Looking
inside a figure was tried and rejected -- the pangram `The quick brown fox`
invented off a line drawing, +2100 words of rubbish over 20 pages.

WHAT IS KNOWN AGAINST `masked_page`, BEFORE THE MEASUREMENT.

* **Empty space does not keep quiet.** The probe "a blank white sheet": five
  tries, five different Chinese office tables. A painted rectangle is that
  sheet in miniature, and an invented table can appear in its place. So what to
  paint with is the `MASK_FILL` knob, not a constant: white is the least
  neutral choice there is.
* **Context spoils reading.** Remove the third column and the model read the
  second right; with the whole page it read it wrong. Here isolation helped.
* **The answer ceiling.** The pipeline lowers `max_new_tokens` to 4096, while
  the longest SINGLE text block in our books is 8207 characters. A whole page
  is bigger, and a cutoff in this model looks like looping.

Here in `doc/`, not `models/`: all the work is box geometry and raster, the
same code as the crop. Into the model it goes as image bytes.
"""
import json
import os

from .. import policy
from ..run import knobs
from . import crop
# The block anchor is built by ONE rule for the project. Here stood a second
# copy (`f"p{page.index:04d}-b{b.block_id}"`) that would have drifted from
# `html.anchor_of` at the first rename -- silently: feed.json naming the pieces
# one way, the book and blocks.json another, nothing left to tie a feed to a
# block. Two copies of one convention is how percentages out of nothing are
# born (see tests/test_html_order.py).
from .html import anchor_of

FILLS = {"white": (1.0, 1.0, 1.0), "black": (0.0, 0.0, 0.0),
         "gray": (0.5, 0.5, 0.5)}
MODES = ("crop", "masked_page")


def params(page_dpi: float | None = None) -> dict:
    """The feed in force. It goes into the snapshot whole.

    `page_dpi` is the DETECTION resolution (`raster.dpi` of the snapshot);
    empty `CROP_DPI` and `FEED_DPI` mean "as the model saw it". Expanding those
    from the current process would call "as the model saw it" something the
    model never saw, so with no argument `page_dpi_source` names the current
    process -- guessed, not agreed.
    """
    mode = knobs.knob("VLM_INPUT")
    if mode not in MODES:
        raise ValueError(f"VLM_INPUT={mode!r}: I know only {MODES}")
    fill = knobs.knob("MASK_FILL")
    if fill not in FILLS:
        raise ValueError(f"MASK_FILL={fill!r}: I know only {tuple(FILLS)}")
    # From crop we take ONLY what belongs to the `crop` mode. The previous
    # edition expanded `crop.params()` whole, and CROP_DPI silently set the
    # resolution of the WHOLE page going to the VLM: sharpen a table crop and
    # the feed image grows fourfold -- another count of visual tokens, another
    # price, and the comparison of feeds measures something else.
    c = crop.params(page_dpi)
    feed_dpi = knobs.knob("FEED_DPI")
    if feed_dpi:
        page_out, src = float(feed_dpi), "FEED_DPI"
    elif page_dpi is not None:
        page_out, src = float(page_dpi), "as in detection"
    else:
        page_out, src = float(knobs.knob("PAGE_DPI")), "PAGE_DPI of this process"
    return {"feed_mode": mode, "hole_fill": fill,
            "crop_dpi": c["dpi"], "crop_dpi_source": c["dpi_source"],
            "crop_margin": c["margin"],
            "page_dpi": page_out, "page_dpi_source": src}


def _union_rects(holes):
    """Merge intersecting holes into connected groups (by bounding boxes).

    MERGES TO EXHAUSTION, NOT IN ONE PASS, and that is not nitpicking: a merged
    box is the BOUNDING one, so it grows, and may cover one this same pass has
    already set aside as disjoint. On a constructed input
    `[[0,20,4,30], [0,0,10,10], [5,5,8,80]]` the old code printed "holes 2"
    (`[0,20,4,30]` and `[0,0,10,80]`) though the second covers the first
    entirely and the group is one. The feed is chosen by the number of holes,
    and an inflated number makes `masked_page` dearer on paper than it is.

    Over nine `bench/*/detect` directories (762 pages with artifacts) old and
    new agreed to the unit, 1701 holes: the trouble has not surfaced in the
    tree, and is fixed because it is not what chooses the input.
    """
    out = []
    for h in holes:
        cur = list(h)
        rest = list(out)
        grew = True
        while grew:
            grew = False
            keep = []
            for o in rest:
                if (cur[0] < o[2] and o[0] < cur[2]
                        and cur[1] < o[3] and o[1] < cur[3]):
                    cur = [min(cur[0], o[0]), min(cur[1], o[1]),
                           max(cur[2], o[2]), max(cur[3], o[3])]
                    grew = True
                else:
                    keep.append(o)
            rest = keep
        out = rest + [cur]
    return out


def _union_area(holes):
    """Area of the union of rectangles: a sweep along the vertical."""
    if not holes:
        return 0
    xs = sorted({v for h in holes for v in (h[0], h[2])})
    total = 0
    for a, b in zip(xs, xs[1:]):
        spans = sorted((h[1], h[3]) for h in holes if h[0] <= a and h[2] >= b)
        cov, end = 0, None
        for y0, y1 in spans:
            if end is None or y0 > end:
                cov += y1 - y0
                end = y1
            elif y1 > end:
                cov += y1 - end
                end = y1
        total += cov * (b - a)
    return total


def masked_page(doc, page_index: int, boxes, page_dpi: float, dst: str,
                dpi: float | None = None, fill: str | None = None) -> dict:
    """The whole page, artifacts painted over. Returns the feed values.

    Painted AFTER rendering, straight onto the raster: drawing over the PDF
    would change the source, and it has to stay untouched -- the crops for the
    second level are cut from it.
    """
    import pymupdf

    p = params(page_dpi)
    dpi = p["page_dpi"] if dpi is None else dpi
    fill = p["hole_fill"] if fill is None else fill

    page = doc[page_index]
    pix = page.get_pixmap(dpi=int(dpi))
    # The boxes arrive in pixels of the detection raster; converted to pixels
    # of THIS one. Without that the holes would drift and the page would still
    # look whole.
    k = dpi / page_dpi
    holes = []
    for b in boxes:
        r = pymupdf.IRect(int(b[0] * k), int(b[1] * k),
                          int(b[2] * k), int(b[3] * k))
        r = r & pymupdf.IRect(0, 0, pix.width, pix.height)
        if r.is_empty:
            continue
        pix.set_rect(r, tuple(int(c * 255) for c in FILLS[fill]))
        holes.append([r.x0, r.y0, r.x1, r.y1])
    # Area by UNION, not by sum. The model returns `chart` and `image` on one
    # rectangle with a tied rank -- its documented behaviour -- and a sum of
    # areas on such a page overstated "share of page painted" exactly twofold,
    # while "holes 2" stood at one hole. These are the numbers the feed is
    # chosen by.
    area = _union_area(holes)
    merged = _union_rects(holes)
    os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)
    pix.save(dst)
    return {"file": os.path.basename(dst), "dpi": int(dpi),
            "width": pix.width, "height": pix.height,
            "holes_count": len(merged), "model_boxes": len(holes), "fill": fill,
            "page_share_masked": round(area / (pix.width * pix.height), 4),
            "holes": holes}


def prepare(doc, page, out_dir: str, page_dpi: float, log=print) -> dict:
    """Prepare what would go to the VLM, and count NOTHING.

    Not one call to the model: local and free, so the feeds can be looked at
    and compared BEFORE the money goes.
    """
    p = params(page_dpi)
    os.makedirs(out_dir, exist_ok=True)
    tag = f"p{page.index:04d}"           # the PAGE file name, not an anchor
    art = [b for b in page.blocks if policy.role(b.label) == "artifact"]
    txt = [b for b in page.blocks if policy.role(b.label) != "artifact"]

    if p["feed_mode"] == "crop":
        items = []
        for b in txt:
            a = anchor_of(page.index, b.block_id)
            rel = f"{a}.png"
            info = crop.cut(doc, page.index, b.box, page_dpi,
                            os.path.join(out_dir, rel))
            items.append({"anchor": a, "label": b.label, **info})
        return {"feed_mode": "crop", "requests": len(items),
                "artifacts_not_sent": len(art), "chunks": items}

    rel = f"{tag}.png"
    info = masked_page(doc, page.index, [b.box for b in art], page_dpi,
                       os.path.join(out_dir, rel))
    return {"feed_mode": "masked_page", "requests": 1,
            "artifacts_masked": len(art),
            "text_blocks_on_page": len(txt),
            # Where to put the placeholders back. The model will not say: its
            # prompt is two words, no system message, nothing to ask a marker
            # with. So the hole geometry is ours to remember.
            "page": info}


def dump(result: dict, out_dir: str) -> str:
    path = os.path.join(out_dir, "feed.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    return path
