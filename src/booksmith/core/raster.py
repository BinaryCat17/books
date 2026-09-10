"""Cut an artifact out of a page along the model's box.

Cut from the PDF, not from the raster the detector was fed: detection runs at
`PAGE_DPI` = 144, six or seven dots per character height on a dense unruled
table, while from the PDF any resolution can be had without asking again.

Two knobs, both in the registry. `CROP_DPI` is the crop resolution, empty
meaning the scan's own -- all the ink the file holds and not one dot invented.
`CROP_MARGIN` is padding around the box in fractions of its size; a negative
one cuts into the box, which the rules forbid, and is refused aloud.
"""
import os
from collections.abc import Sequence
from typing import Any

from booksmith.core import knobs
from booksmith.core.errors import Refusal

# Box tolerance in PDF points: pymupdf works in float32, and 0.01 pt (1/7200
# inch) is below the smallest typographic space, so a smaller gap is noise.
EPS_PT = 0.01


def native_dpi(page: Any) -> float | None:
    """The page's own resolution: how much ink it holds, above which a cut
    interpolates. The most detailed image covering the whole sheet, a PDF out of
    djvu carrying two. `None` is "nothing to say with", never "144".
    """
    w_pt = float(page.rect.width)
    if w_pt <= 0:
        return None
    try:
        imgs = page.get_images(full=True)
    except Exception:
        return None
    best = 0.0
    for im in imgs:
        xref, w_px = im[0], im[2]
        if w_px <= 0:
            continue
        try:
            rects = page.get_image_rects(xref)
        except Exception:
            continue
        for r in rects:
            # Only images covering the whole sheet: an inset may be arbitrarily detailed.
            if r.width < w_pt * 0.9 or r.width <= 0:
                continue
            # By the placement width, not the sheet's: a spread raster is wider
            # than the sheet that takes half of it, and would overstate the grid.
            best = max(best, w_px / float(r.width) * 72.0)
    return best or None


def params(page_dpi: float | None = None,
           page_native: float | None = None,
           want_dpi: bool = True) -> dict:
    """The crop values in force, going into the snapshot whole; `dpi_source`
    names where the resolution came from. `page_dpi` is the detection run's,
    `page_native` the page's own, and `want_dpi=False` asks the margin alone.
    """
    margin = knobs.number("CROP_MARGIN", negative=True)
    if margin < 0:
        raise ValueError(
            f"CROP_MARGIN={margin}: a negative margin CUTS the model's box "
            f"instead of adding room. Editing the model's box is forbidden by "
            f"a project rule, and no crop quantity shows such a cut "
            f"(\"clipped by the sheet\" is about the sheet edge, not our "
            f"knife)")
    if not want_dpi:
        return {"dpi": None, "dpi_source": "named by the caller, not by a knob",
                "margin": margin}
    raw = knobs.knob("CROP_DPI")
    if raw:
        # Zero and negative are refused aloud: `get_pixmap(dpi=0)` falls back to
        # 72 dpi in silence. The finite check lives once, in `knobs.number`.
        try:
            _v = knobs.number("CROP_DPI")
        except Refusal as e:
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
        # The detection resolution was not named: take the environment and say so.
        dpi, src = knobs.number("PAGE_DPI"), "PAGE_DPI of this process"
    return {"dpi": dpi, "dpi_source": src, "margin": margin}


def box_to_points(box: Sequence[float], page_dpi: float) -> tuple[float, ...]:
    """A box in raster pixels at `page_dpi` -> PDF points (72 per inch)."""
    k = 72.0 / page_dpi
    return tuple(v * k for v in box)


def _clipped(rect: Any, clip: Any) -> bool:
    """Is `rect` clipped down to `clip`, with tolerance rather than exactly.

    The one comparison rule of the file: an exact one lies at every resolution
    whose conversion factor is not binary-exact (see `EPS_PT`).
    """
    return (abs(clip.width - rect.width) > EPS_PT
            or abs(clip.height - rect.height) > EPS_PT)


def _box_trouble(w: float, h: float) -> str | None:
    """What is wrong with the box itself: `INVERTED` | `DEGENERATE` | None.

    Kept apart from "does not intersect the sheet", which both would otherwise
    draw, and its own function so a probe can break the guard.
    """
    if w < 0 or h < 0:
        return ("INVERTED: the right edge is left of the left one, or the "
                "bottom above the top")
    if w == 0 or h == 0:
        return "DEGENERATE: zero area, nothing to cut"
    return None


def _clip(doc: Any, page_index: int, box: Sequence[float], page_dpi: float,
          dpi: float | None, margin: float | None) -> tuple:
    """The page, the rect to render, the dpi and margin used, and what was clipped."""
    import pymupdf

    # The own resolution and `CROP_DPI` are asked for only when the caller names
    # neither, or a knob a path ignores could come back as "crop failed".
    p = params(page_dpi, native_dpi(doc[page_index]) if dpi is None else None,
               want_dpi=dpi is None)
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
    # A box running off the sheet is the model's defect and shows as a number,
    # measured on the raw box: on the widened one our margin would accuse the model.
    raw = pymupdf.Rect(*box_to_points(box, page_dpi))
    clipped = _clipped(raw, raw & page.rect)
    clip = want & page.rect
    margin_clipped = _clipped(want, clip)
    if clip.is_empty:
        raise ValueError(
            f"box {tuple(round(v,1) for v in box)} on p. {page_index} "
            f"does not intersect the sheet "
            f"{tuple(round(v,1) for v in page.rect)}")

    return page, clip, dpi, margin, clipped, margin_clipped


def _facts(pix: Any, clip: Any, dpi: float, margin: float, clipped: bool,
           margin_clipped: bool) -> dict:
    return {"dpi": int(dpi), "margin": margin,
            "width": pix.width, "height": pix.height,
            "clipped_by_sheet": clipped,
            "margin_clipped": margin_clipped,
            "box_in_points": [round(v, 2) for v in (clip.x0, clip.y0,
                                                      clip.x1, clip.y1)]}


def cut(doc: Any, page_index: int, box: Sequence[float], page_dpi: float, dst: str,
        dpi: float | None = None, margin: float | None = None) -> dict:
    """Cut the box into a file. Returns what exactly was cut: size, margin, clipping."""
    page, clip, dpi, margin, clipped, margin_clipped = _clip(
        doc, page_index, box, page_dpi, dpi, margin)
    os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)
    pix = render(page, dpi, clip=clip)
    pix.save(dst)
    return {"file": os.path.basename(dst),
            **_facts(pix, clip, dpi, margin, clipped, margin_clipped)}


def cut_png(doc: Any, page_index: int, box: Sequence[float], page_dpi: float,
            dpi: float | None = None, margin: float | None = None) -> tuple[bytes, dict]:
    """The same cut as PNG bytes, for a caller that serves it rather than files it."""
    page, clip, dpi, margin, clipped, margin_clipped = _clip(
        doc, page_index, box, page_dpi, dpi, margin)
    pix = render(page, dpi, clip=clip)
    return pix.tobytes("png"), _facts(pix, clip, dpi, margin, clipped, margin_clipped)


# ------------------------------------------------------------ rendering ---
# Every rasterisation on the read path goes through these two, so one file knows
# the renderer; the writers that draw and assemble PDFs keep pymupdf themselves.

def open_pdf(path: str) -> Any:
    """The document, as pymupdf opens it. One place to swap the engine.

    pymupdf is imported here and not at the top: the knob registry's readers and
    the box entrypoint import this module before any PDF is touched.
    """
    import pymupdf
    return pymupdf.open(path)


def render_png(page: Any, dpi: float, clip: Any = None) -> bytes:
    """The page (or a clip of it) as PNG bytes at `dpi`."""
    return render(page, dpi, clip=clip).tobytes("png")


def render(page: Any, dpi: float, clip: Any = None) -> Any:
    """The page (or a clip of it) as a pixmap at `dpi`, integer as pymupdf wants.

    pymupdf truncates a fractional dpi itself, so callers pass the dpi they record.
    """
    return page.get_pixmap(dpi=int(dpi), clip=clip)
