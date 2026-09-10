"""Cut an artifact out of a page along the model's box"""

import os
from collections.abc import Sequence
from typing import Any
from layout import knobs
from layout.errors import Refusal

EPS_PT = 0.01


def native_dpi(page: Any) -> float | None:
    w_pt = float(page.rect.width)
    if w_pt <= 0:
        return None
    try:
        imgs = page.get_images(full=True)
    except Exception:
        return None
    best = 0.0
    for im in imgs:
        xref, w_px = (im[0], im[2])
        if w_px <= 0:
            continue
        try:
            rects = page.get_image_rects(xref)
        except Exception:
            continue
        for r in rects:
            if r.width < w_pt * 0.9 or r.width <= 0:
                continue
            best = max(best, w_px / float(r.width) * 72.0)
    return best or None


def params(
    page_dpi: float | None = None, page_native: float | None = None, want_dpi: bool = True
) -> dict:
    margin = knobs.number("CROP_MARGIN", negative=True)
    if margin < 0:
        raise ValueError(
            f"""CROP_MARGIN={margin}: a negative margin CUTS the model's box instead of adding room. Editing the model's box is forbidden by a project rule, and no crop quantity shows such a cut ("clipped by the sheet" is about the sheet edge, not our knife)"""
        )
    if not want_dpi:
        return {"dpi": None, "dpi_source": "named by the caller, not by a knob", "margin": margin}
    raw = knobs.knob("CROP_DPI")
    if raw:
        try:
            _v = knobs.number("CROP_DPI")
        except Refusal as e:
            raise ValueError(str(e)) from None
        if _v <= 0:
            raise ValueError(
                f'CROP_DPI={raw!r}: crop sharpness is never zero or negative. At zero pymupdf silently takes 72 dpi, the book would go to the model four times coarser than ordered, and the record would say "0"'
            )
        dpi, src = (float(raw), "CROP_DPI")
    elif page_native:
        dpi, src = (float(page_native), "native_scan_dpi")
    elif page_dpi is not None:
        dpi, src = (
            float(page_dpi),
            "as in detection: the page's own sharpness cannot be determined (vector, or several images on the sheet)",
        )
    else:
        dpi, src = (knobs.number("PAGE_DPI"), "PAGE_DPI of this process")
    return {"dpi": dpi, "dpi_source": src, "margin": margin}


def box_to_points(box: Sequence[float], page_dpi: float) -> tuple[float, ...]:
    k = 72.0 / page_dpi
    return tuple(v * k for v in box)


def _clipped(rect: Any, clip: Any) -> bool:
    return abs(clip.width - rect.width) > EPS_PT or abs(clip.height - rect.height) > EPS_PT


def _box_trouble(w: float, h: float) -> str | None:
    if w < 0 or h < 0:
        return "INVERTED: the right edge is left of the left one, or the bottom above the top"
    if w == 0 or h == 0:
        return "DEGENERATE: zero area, nothing to cut"
    return None


def _clip(
    doc: Any,
    page_index: int,
    box: Sequence[float],
    page_dpi: float,
    dpi: float | None,
    margin: float | None,
) -> tuple[Any, Any, float, float, bool, bool]:
    import pymupdf

    p = params(page_dpi, native_dpi(doc[page_index]) if dpi is None else None, want_dpi=dpi is None)
    dpi = p["dpi"] if dpi is None else dpi
    margin = p["margin"] if margin is None else margin
    page = doc[page_index]
    x0, y0, x1, y1 = box_to_points(box, page_dpi)
    w, h = (x1 - x0, y1 - y0)
    trouble = _box_trouble(w, h)
    if trouble:
        raise ValueError(
            f"box {tuple(round(v, 1) for v in box)} on p. {page_index} {trouble} ({w:.1f} x {h:.1f} points). This is a defect of the BOX ITSELF, not of where it lies on the sheet"
        )
    if margin:
        x0, y0, x1, y1 = (x0 - w * margin, y0 - h * margin, x1 + w * margin, y1 + h * margin)
    want = pymupdf.Rect(x0, y0, x1, y1)
    raw = pymupdf.Rect(*box_to_points(box, page_dpi))
    clipped = _clipped(raw, raw & page.rect)
    clip = want & page.rect
    margin_clipped = _clipped(want, clip)
    if clip.is_empty:
        raise ValueError(
            f"box {tuple(round(v, 1) for v in box)} on p. {page_index} does not intersect the sheet {tuple(round(v, 1) for v in page.rect)}"
        )
    return (page, clip, dpi, margin, clipped, margin_clipped)


def _facts(
    pix: Any, clip: Any, dpi: float, margin: float, clipped: bool, margin_clipped: bool
) -> dict:
    return {
        "dpi": int(dpi),
        "margin": margin,
        "width": pix.width,
        "height": pix.height,
        "clipped_by_sheet": clipped,
        "margin_clipped": margin_clipped,
        "box_in_points": [round(v, 2) for v in (clip.x0, clip.y0, clip.x1, clip.y1)],
    }


def cut(
    doc: Any,
    page_index: int,
    box: Sequence[float],
    page_dpi: float,
    dst: str,
    dpi: float | None = None,
    margin: float | None = None,
) -> dict:
    page, clip, dpi, margin, clipped, margin_clipped = _clip(
        doc, page_index, box, page_dpi, dpi, margin
    )
    os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)
    pix = render(page, dpi, clip=clip)
    pix.save(dst)
    return {
        "file": os.path.basename(dst),
        **_facts(pix, clip, dpi, margin, clipped, margin_clipped),
    }


def cut_png(
    doc: Any,
    page_index: int,
    box: Sequence[float],
    page_dpi: float,
    dpi: float | None = None,
    margin: float | None = None,
) -> tuple[bytes, dict]:
    page, clip, dpi, margin, clipped, margin_clipped = _clip(
        doc, page_index, box, page_dpi, dpi, margin
    )
    pix = render(page, dpi, clip=clip)
    return (pix.tobytes("png"), _facts(pix, clip, dpi, margin, clipped, margin_clipped))


def open_pdf(path: str) -> Any:
    import pymupdf

    return pymupdf.open(path)


def render_png(page: Any, dpi: float, clip: Any = None) -> bytes:
    return render(page, dpi, clip=clip).tobytes("png")


def render(page: Any, dpi: float, clip: Any = None) -> Any:
    return page.get_pixmap(dpi=int(dpi), clip=clip)
