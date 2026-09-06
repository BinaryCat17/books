"""Cut an artifact out of a page along the model's box.

We cut FROM THE PDF, not from the raster the detector was fed, and the reason
is a number: detection runs at `PAGE_DPI` = 144, where a dense unruled table
gives six or seven dots per character height -- level two would fail on such a
crop and be blamed for it. From the PDF any resolution can be had without
asking the detector again.

TWO KNOBS, BOTH DECLARED IN THE REGISTRY. `CROP_DPI` is the crop resolution;
empty means the scan's OWN, all the ink the file holds and not one dot
invented. `CROP_MARGIN` is padding around the box, in fractions of its size,
and its default 0 is not laziness but a VALUE: the pipeline cuts exactly on the
box (`layout_unclip_ratio` = [1.0, 1.0]), and any non-zero padding edits the
model's box, which the rules forbid. A negative one CUTS INTO that box and is
refused aloud -- `CROP_MARGIN=-0.1` ate a tenth off each side, the crop went
into the book gnawed, and no quantity showed it: "clipped by the sheet"
measures the SHEET's edge, not our knife. Should a bench show that padding is
needed, it comes back as a number with a measurement.

The measurements behind both defaults are in `params` below.
"""
import os

from ..run import knobs

# Box comparison tolerance, in PDF points. ONE for the whole file, and not to
# taste: pymupdf holds coordinates in single precision and runs intersection
# through float32 once more. Measured on `bench/atlas`: at `PAGE_DPI` = 144 the
# factor 72/144 = 0.5 is binary-exact and diverges not at all (0 boxes of 28);
# at 150, 200 and 300 it is 28 of 28, up to 1.7e-05 point, and exact comparison
# declared a box lying wholly inside the sheet clipped by it. 0.01 point is
# 1/7200 inch, below the smallest typographic space, so under it a "clip" is
# indistinguishable from representation noise.
EPS_PT = 0.01


def native_dpi(page) -> float | None:
    """The page's OWN resolution: how much ink it really holds. Above that grid
    a cut yields interpolation, not ink.

    THE MOST DETAILED OF THOSE COVERING THE WHOLE SHEET. Our own books arrive
    from djvu (`books prepare`), and such a PDF carries TWO layers on one
    sheet. Measured on `bench/real/tables20.pdf`, sheet 506 x 733 points:

        layer 0: 1408 x 2038 px = 200 dpi, covers the whole sheet
        layer 1: 4222 x 6112 px = 601 dpi, covers the whole sheet, with a mask

    The detailed layer is the letters, and the first version took a resolution
    only when the sheet held ONE image -- it gave up on such books and returned
    `None`.

    `None` means "nothing to say with": vector page (a digital PDF has no grid)
    or no image over the whole sheet. A VALUE, not a zero -- the caller must
    tell "resolution unknown" from "resolution 144".
    """
    w_pt = float(page.rect.width)
    if w_pt <= 0:
        return None
    try:
        imgs = page.get_images(full=True)
    except Exception:                              # noqa: BLE001
        return None
    best = 0.0
    for im in imgs:
        xref, w_px = im[0], im[2]
        if w_px <= 0:
            continue
        try:
            rects = page.get_image_rects(xref)
        except Exception:                          # noqa: BLE001
            continue
        for r in rects:
            # Only images COVERING THE WHOLE SHEET: a stamp or inset in a
            # corner can be arbitrarily detailed, and cutting the whole page by
            # it would inflate every crop for nothing.
            if r.width < w_pt * 0.9 or r.width <= 0:
                continue
            # DIVIDE BY THE PLACEMENT WIDTH, NOT THE SHEET WIDTH. A raster can
            # be WIDER than the sheet -- a spread scan the sheet takes half
            # of -- and dividing by the sheet overstated the grid by exactly
            # that ratio.
            #
            # Measured on five pages of each of six books: overstated in FOUR
            # of the six, up to 2.47x. Worst case, "Технология огнеупоров":
            # sheet 278.2 pt, raster 2867 px placed on 688.1 pt, read as 741.9
            # dpi against a real grid of 300.0. The price was measured against
            # the embedded raster itself: four times the pixels bought +0.02
            # correlation with truth, where the genuine detailed layer gives
            # +0.18. That is the "rasteriser's guess" `params()` promises not
            # to buy.
            best = max(best, w_px / float(r.width) * 72.0)
    return best or None


def params(page_dpi: float | None = None,
           page_native: float | None = None) -> dict:
    """The crop values in force. They go into the snapshot whole.

    `page_dpi` is the DETECTION resolution (`raster.dpi` of the snapshot),
    `page_native` the page's OWN (`native_dpi`).

    WHAT AN EMPTY `CROP_DPI` MEANS -- rewritten by MEASUREMENT, not by taste.
    It used to mean "as at detection", i.e. 144. One and the same piece of a
    real scan (`bench/real/tables20.pdf`, raster 1408 x 2038 on a 506 x 733 pt
    sheet = 200 dpi):

        CROP_DPI=144   810 x 221 =  179 010 px
        CROP_DPI=200  1125 x 306 =  344 250 px   <- the scan's own grid
        CROP_DPI=288  1620 x 441 =  714 420 px   } above it interpolation,
        CROP_DPI=400  2249 x 612 = 1376 388 px   } no more ink appears

    So "as at detection" threw away 48 % of the ink that IS in the file. Empty
    now means "as much as the scan holds, not one dot more"; detection is
    untouched, it counts at `PAGE_DPI`. Nor is more safer: above the own grid
    what is added is the rasteriser's guess, and it costs twice, because
    PaddleOCR-VL has `max_pixels` around a million and squeezes an inflated
    crop back in its own processor -- we would pay to compress an invention.

    AND IT IS THE DETECTION RUN'S RESOLUTION, NOT THE CURRENT PROCESS'S. Empty
    `CROP_DPI` used to expand to `PAGE_DPI` here and now: `bench/atlas`
    detected at `PAGE_DPI=150` and assembled at the default printed 26 crops at
    144 dpi while the coordinates were converted from 150 -- "as the model saw
    it" made untrue, silently. The environment is asked only when no argument
    comes, and when the own resolution is unknown (vector, several images on a
    sheet) the detection one is taken; `dpi_source` names which it was.
    """
    margin = knobs.number("CROP_MARGIN", negative=True)
    if margin < 0:
        raise ValueError(
            f"CROP_MARGIN={margin}: a negative margin CUTS the model's box "
            f"instead of adding room. Editing the model's box is forbidden by "
            f"a project rule, and no crop quantity shows such a cut "
            f"(\"clipped by the sheet\" is about the sheet edge, not our "
            f"knife)")
    raw = knobs.knob("CROP_DPI")
    if raw:
        # ZERO AND NEGATIVE ARE REFUSED ALOUD. The string "0" is truthy and
        # went straight through this branch: `get_pixmap(dpi=0)` in pymupdf
        # falls back to 72 dpi silently, so the book was cut four times coarser
        # than ordered while the record said "dpi 0". Checked: `CROP_DPI=0`
        # gives a 150x100 px crop where 600 would give 1250x833.
        #
        # `nan` PASSED BOTH OF THESE. `float("nan")` raises nothing and
        # `nan <= 0` is False, so the guard that refuses zero out loud let the
        # worse value through in silence -- the same hole `_min_link_mbps` had.
        # The finite check lives once, in `knobs.number`; zero and negative
        # stay here, because the reason they are refused is this file's.
        try:
            _v = knobs.number("CROP_DPI")
        except SystemExit as e:
            raise ValueError(str(e)) from None
        if _v <= 0:
            raise ValueError(
                f"CROP_DPI={raw!r}: crop sharpness is never zero or "
                f"negative. At zero pymupdf silently takes 72 dpi, the book "
                f"would go to the model four times coarser than ordered, and "
                f"the record would say \"0\"")
        dpi, src = float(raw), "CROP_DPI"
    elif page_native:
        dpi, src = float(page_native), "native_scan_dpi"
    elif page_dpi is not None:
        dpi, src = float(page_dpi), ("as in detection: the page's own "
                                     "sharpness cannot be determined (vector, "
                                     "or several images on the sheet)")
    else:
        # The detection resolution was not named -- take the environment and
        # SAY so. A zero from a check and a zero from not knowing: this value
        # is not "agreed with detection", it is "nothing to agree with".
        dpi, src = knobs.number("PAGE_DPI"), "PAGE_DPI of this process"
    return {"dpi": dpi, "dpi_source": src, "margin": margin}


def box_to_points(box, page_dpi: float):
    """A box in raster pixels at `page_dpi` -> PDF points (72 per inch)."""
    k = 72.0 / page_dpi
    return tuple(v * k for v in box)


def _clipped(rect, clip) -> bool:
    """Is `rect` clipped down to `clip` -- WITH TOLERANCE, not exactly.

    The comparison rule in this file is ONE, and it lives here. "Clipped by the
    sheet" used to compare exactly (`(raw & page.rect) != raw`) while its
    neighbour "margin clipped by the sheet" used the 0.01 tolerance: two rules
    on two adjacent lines, and the first lied at every resolution whose factor
    is not binary-exact (see `EPS_PT`).
    """
    return (abs(clip.width - rect.width) > EPS_PT
            or abs(clip.height - rect.height) > EPS_PT)


def _box_trouble(w: float, h: float) -> str | None:
    """What is wrong with the box itself: `INVERTED` | `DEGENERATE` | None.

    Both gave an empty intersection with the sheet and so drew the foreign
    diagnosis "does not intersect the sheet" -- for a box lying in the middle
    of the paper, sending the reader after slipped coordinates and a sheet
    edge. `read/run.py` catches the ValueError from `cut` and counts it as
    "crop failed", so the exception type did not change with the split.

    A SEPARATE FUNCTION for the mutation battery: a diagnosis sewn as two `if`s
    inside `cut` cannot be broken, and a guard that cannot be broken is not
    proven.
    """
    if w < 0 or h < 0:
        return ("INVERTED: the right edge is left of the left one, or the "
                "bottom above the top")
    if w == 0 or h == 0:
        return "DEGENERATE: zero area, nothing to cut"
    return None


def cut(doc, page_index: int, box, page_dpi: float, dst: str,
        dpi: float | None = None, margin: float | None = None) -> dict:
    """Cut the box into a file. Returns WHAT exactly was cut.

    Not "done" but quantities: resulting size in points, margin applied,
    clipping by the page edge. Without them "we cut a table" cannot be told
    from "we cut its left half, because the box ran off the sheet".
    """
    import pymupdf

    # The own resolution is asked for ONLY when it was not named. Before,
    # `native_dpi(doc[page_index])` was computed always, including when `dpi`
    # is passed explicitly and the answer thrown away: measured over the bench,
    # 15 601 `get_images` calls over 600 pages, none of them useful, because
    # `books read` decides each crop's resolution itself.
    p = params(page_dpi, native_dpi(doc[page_index]) if dpi is None else None)
    dpi = p["dpi"] if dpi is None else dpi
    margin = p["margin"] if margin is None else margin

    page = doc[page_index]
    x0, y0, x1, y1 = box_to_points(box, page_dpi)
    w, h = x1 - x0, y1 - y0
    trouble = _box_trouble(w, h)
    if trouble:
        raise ValueError(
            f"box {tuple(round(v,1) for v in box)} on p. {page_index} "
            f"{trouble} ({w:.1f} x {h:.1f} points). This is a defect of the "
            f"BOX ITSELF, not of where it lies on the sheet")
    if margin:
        x0, y0, x1, y1 = (x0 - w * margin, y0 - h * margin,
                          x1 + w * margin, y1 + h * margin)
    want = pymupdf.Rect(x0, y0, x1, y1)
    # Intersection with the sheet. The model's box may run off the edge -- its
    # defect, and it must be SEEN as a number, not silently trimmed.
    #
    # The model's defect and the consequence of OUR knob are different numbers.
    # The former version measured the overrun of the box ALREADY widened by
    # CROP_MARGIN, so setting a margin was enough for a box lying wholly inside
    # the sheet to be declared clipped, and the block's caption in the book
    # gained "the box ran off the sheet" -- a false accusation of the model,
    # the more frequent the larger the margin.
    raw = pymupdf.Rect(*box_to_points(box, page_dpi))
    clipped = _clipped(raw, raw & page.rect)
    clip = want & page.rect
    margin_clipped = _clipped(want, clip)
    if clip.is_empty:
        raise ValueError(
            f"box {tuple(round(v,1) for v in box)} on p. {page_index} "
            f"does not intersect the sheet "
            f"{tuple(round(v,1) for v in page.rect)}")

    os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)
    pix = page.get_pixmap(dpi=int(dpi), clip=clip)
    pix.save(dst)
    return {"file": os.path.basename(dst), "dpi": int(dpi), "margin": margin,
            "width": pix.width, "height": pix.height,
            "clipped_by_sheet": clipped,
            "margin_clipped": margin_clipped,
            "box_in_points": [round(v, 2) for v in (clip.x0, clip.y0,
                                                      clip.x1, clip.y1)]}
