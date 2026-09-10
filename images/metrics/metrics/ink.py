"""Is the model output fit to push OCR through without losing meaning"""

import os
import statistics
from metrics import store as book_mod
from metrics import classes as policy
from metrics import raster
from metrics import page
from metrics.errors import Unmeasurable
from metrics.processing.extract.djvu import GUTTER_BAND, MIN_SPREAD_RATIO, RULE_RUN
from metrics.log import log

INK = 160
WHOLE, ALMOST, BITTEN = (0.99, 0.95, 0.8)
EDGE = 0.04
GUTTER = 0.5
MID = 0.2
JUNK_WIDTH = 0.1
_INK_CACHE = {}
_INK_CACHE_BYTES = 0
_INK_CACHE_MAX_BYTES = 512 << 20


def _evict_foreign(pdf):
    global _INK_CACHE_BYTES
    for k in _INK_CACHE:
        if k[0] != pdf:
            _INK_CACHE_BYTES -= _INK_CACHE.pop(k)[1].nbytes
            return True
    return False


def _ink_of(pdf, doc, i, dpi):
    import numpy as np

    global _INK_CACHE_BYTES
    key = (pdf, i, int(dpi), INK)
    hit = _INK_CACHE.get(key)
    if hit is None:
        m = _ink(doc[i], dpi)
        packed = np.packbits(m)
        while _INK_CACHE_BYTES + packed.nbytes > _INK_CACHE_MAX_BYTES and _evict_foreign(pdf):
            pass
        if _INK_CACHE_BYTES + packed.nbytes <= _INK_CACHE_MAX_BYTES:
            _INK_CACHE[key] = (m.shape, packed)
            _INK_CACHE_BYTES += packed.nbytes
        return m
    shape, packed = hit
    return np.unpackbits(packed, count=shape[0] * shape[1]).reshape(shape).view(bool)


def _ink(page, dpi):
    import numpy as np

    pm = raster.render(page, dpi)
    g = np.frombuffer(pm.samples, np.uint8).reshape(pm.height, pm.width, pm.n)
    g = g[:, :, :3].mean(2) if pm.n >= 3 else g[:, :, 0]
    return g < INK


def _clip(shape, box):
    h, w = shape
    x0, y0, x1, y1 = (int(v) for v in box)
    x0, y0 = (max(0, x0), max(0, y0))
    x1, y1 = (min(w - 1, x1), min(h - 1, y1))
    if x1 < x0 or y1 < y0:
        return None
    return (slice(y0, y1 + 1), slice(x0, x1 + 1))


_JUNK_CACHE: dict = {}


def _strips(columns) -> list:
    import numpy as np

    edge = np.diff(np.r_[0, columns.astype(np.int8), 0])
    return [
        [int(a), int(b)]
        for a, b in zip(np.flatnonzero(edge == 1), np.flatnonzero(edge == -1), strict=True)
    ]


def _junk_of(pdf, i, dpi, ink):
    key = (
        pdf,
        i,
        int(dpi),
        INK,
        GUTTER,
        MID,
        JUNK_WIDTH,
        RULE_RUN,
        GUTTER_BAND,
        MIN_SPREAD_RATIO,
        EDGE,
    )
    hit = _JUNK_CACHE.get(key)
    if hit is None:
        hit = _JUNK_CACHE[key] = _junk_columns(ink)
    return hit


def _junk_columns(ink):
    import numpy as np

    h, w = ink.shape
    dark = ink.sum(axis=0) > h * GUTTER
    junk = np.zeros(w, bool)
    if not dark.any():
        return junk
    d = np.diff(np.r_[0, dark.astype(np.int8), 0])
    starts, ends = (np.flatnonzero(d == 1), np.flatnonzero(d == -1))
    spread = w > h * MIN_SPREAD_RATIO
    k = max(1, int(min(h, w) * EDGE))
    body = ink[k : h - k] if h > 2 * k else ink
    span = int(RULE_RUN * w)
    for a, b in zip(starts, ends, strict=True):
        c = (a + b) / 2.0 / w
        if not (c < MID or c > 1 - MID or (spread and abs(c - 0.5) <= GUTTER_BAND / 2)):
            continue
        if (b - a) / w > JUNK_WIDTH:
            continue
        if span <= 0:
            continue
        full = body[:, a:b].all(axis=1)
        lo, hi = (max(0, a - span + 1), min(b - 1, w - span))
        if full.any() and span <= w and (lo <= hi):
            rows = body[full].astype(np.int32)
            cum = np.cumsum(np.hstack([np.zeros((rows.shape[0], 1), np.int32), rows]), axis=1)
            win = cum[:, lo + span : hi + span + 1] - cum[:, lo : hi + 1]
            if (win == span).any():
                continue
        junk[a:b] = True
    return junk


def _mask(shape, boxes):
    import numpy as np

    m = np.zeros(shape, bool)
    for b in boxes:
        win = _clip(shape, b)
        if win is not None:
            m[win] = True
    return m


def _carried_as_text(sub, arte, rest, tot):
    return int((sub & (arte | rest)).sum()) / tot >= WHOLE


def measure(pdf: str, detect_dir: str, truth_dir: str = "", pol=None, tp=None, want=None) -> dict:
    import numpy as np

    if not os.path.exists(pdf):
        raise Unmeasurable(f"no {pdf}")
    M = page.load_pages(detect_dir)
    T = page.load_pages(truth_dir) if truth_dir else {}
    pol = pol or book_mod.policy_beside(detect_dir)
    tp = tp or policy.UNION
    doc = raster.open_pdf(pdf)
    areas = []
    res = {
        "page_count": 0,
        "truth_pages": len(T),
        "dpi": [],
        "box_count": 0,
        "median_box_area": None,
        "ink_as_text": 0,
        "ink_as_picture": 0,
        "ink_junk": 0,
        "ink_clean": 0,
        "clean_under_boxes": 0,
        "blocks_with_content": 0,
        "ink_total": 0,
        "ink_under_boxes": 0,
        "ink_under_artifact": 0,
        "sheet_area": 0,
        "boxes_area": 0,
        "ink_outside_boxes_at_edge": 0,
        "ink_in_dark_columns": 0,
        "ink_in_dark_columns_off_edge": 0,
        "dark_columns": 0,
        "pages_with_dark_column": 0,
        "dark_columns_positions": [],
        "objects": 0,
        "object_ink": 0,
        "object_ink_in_boxes": 0,
        "intact": 0,
        "almost_intact": 0,
        "bitten": 0,
        "torn": 0,
        "in_one_box": 0,
        "split_between_boxes": 0,
        "left_as_text": 0,
        "arrived_with_company": 0,
        "boxes_with_many_objects": 0,
        "empty_objects": 0,
        "thresholds": {
            "ink": INK,
            "intact": WHOLE,
            "almost": ALMOST,
            "bitten": BITTEN,
            "edge_band": EDGE,
        },
        "pages": {},
        "per_object": {},
    }
    dpis = set()
    pages = sorted(T) if T else sorted(M)
    if want is not None:
        gone = sorted(set(want) - set(pages))
        if gone:
            raise Unmeasurable(
                f"no pages {gone[:5]} to measure: {('truth' if T else 'the run')} has none"
            )
        pages = [i for i in pages if i in want]
        res["truth_pages"] = sum((1 for i in pages if i in T))
    for i in pages:
        if i not in M:
            raise Unmeasurable(
                f"the model marked up no page {i}: nothing to count. An empty answer here would look like 'no ink lost'."
            )
        p = M[i]
        ink = _ink_of(pdf, doc, i, p["dpi"])
        if ink.shape != (p["height"], p["width"]):
            raise Unmeasurable(
                f"page {i}: raster {ink.shape[1]}x{ink.shape[0]}, markup {p['width']}x{p['height']} — the boxes will fall wide"
            )
        arte = [b["box"] for b in p["blocks"] if pol.role(b["label"]) == "artifact"]
        rest = [b["box"] for b in p["blocks"] if pol.role(b["label"]) != "artifact"]
        ma, mr = (_mask(ink.shape, arte), _mask(ink.shape, rest))
        both = ma | mr
        pic = _mask(
            ink.shape,
            [
                b["box"]
                for b in p["blocks"]
                if pol.role(b["label"]) == "artifact" or not (b.get("content") or "").strip()
            ],
        )
        txt = (
            _mask(
                ink.shape,
                [
                    b["box"]
                    for b in p["blocks"]
                    if pol.role(b["label"]) != "artifact" and (b.get("content") or "").strip()
                ],
            )
            & ~pic
        )
        as_picture, as_text = (int((ink & pic).sum()), int((ink & txt).sum()))
        res["ink_as_picture"] += as_picture
        res["ink_as_text"] += as_text
        res["blocks_with_content"] += sum(
            (1 for b in p["blocks"] if (b.get("content") or "").strip())
        )
        riders: dict = {}
        dpis.add(int(p["dpi"]))
        res["page_count"] += 1
        whole = int(ink.sum())
        under = int((ink & both).sum())
        res["ink_total"] += whole
        junk = _junk_of(pdf, i, p["dpi"], ink)
        if junk.any():
            j = int(ink[:, junk].sum())
            clean_under = under - int((ink[:, junk] & both[:, junk]).sum())
        else:
            j = 0
            clean_under = under
        res["clean_under_boxes"] += clean_under
        res["ink_junk"] += j
        res["ink_clean"] += whole - j
        under_art = int((ink & ma).sum())
        res["ink_under_boxes"] += under
        res["ink_under_artifact"] += under_art
        out = ink & ~both
        h, w = ink.shape
        k = max(1, int(min(h, w) * EDGE))
        edge = np.zeros_like(out)
        edge[:k] = edge[-k:] = True
        edge[:, :k] = edge[:, -k:] = True
        res["ink_outside_boxes_at_edge"] += int((out & edge).sum())
        columns = ink.sum(axis=0) > h * GUTTER
        if columns.any():
            res["ink_in_dark_columns"] += int(ink[:, columns].sum())
            row_edge = np.zeros(w, bool)
            row_edge[:k] = row_edge[-k:] = True
            res["ink_in_dark_columns_off_edge"] += int(ink[:, columns & ~row_edge].sum())
            col_edge = np.diff(np.r_[0, columns.astype(np.int8), 0])
            start = np.flatnonzero(col_edge == 1)
            end = np.flatnonzero(col_edge == -1)
            res["dark_columns"] += len(start)
            res["pages_with_dark_column"] += 1
            res["dark_columns_positions"].extend(
                (round(float(a + b) / 2 / w, 2) for a, b in zip(start, end, strict=True))
            )
        res["sheet_area"] += ink.size
        res["boxes_area"] += int(both.sum())
        for sl in (_clip(ink.shape, b) for b in arte + rest):
            if sl is None:
                continue
            ys, xs = sl
            areas.append(float((ys.stop - ys.start) * (xs.stop - xs.start)) / ink.size)
        res["box_count"] += len(arte) + len(rest)
        res["pages"][i] = {
            "ink_total": whole,
            "ink_under_boxes": under,
            "ink_under_artifact": under_art,
            "ink_junk": j,
            "ink_clean": whole - j,
            "clean_under_boxes": clean_under,
            "ink_as_text": as_text,
            "ink_as_picture": as_picture,
            "box_count": len(arte) + len(rest),
            "junk_strips": _strips(junk),
            "edge": k,
        }
        for b in T.get(i, {}).get("blocks", []):
            if tp.role(b["label"]) != "artifact":
                continue
            win = _clip(ink.shape, b["box"])
            sub = ink[win] if win else np.zeros((0, 0), bool)
            tot = int(sub.sum())
            if tot == 0:
                res["empty_objects"] += 1
                continue
            res["objects"] += 1
            res["object_ink"] += tot
            kept = int((sub & ma[win]).sum())
            res["object_ink_in_boxes"] += kept
            r = kept / tot
            fate = (
                "intact"
                if r >= WHOLE
                else "almost_intact"
                if r >= ALMOST
                else "bitten"
                if r >= BITTEN
                else "torn"
            )
            res[fate] += 1
            anchor = page.anchor(i, b["block_id"])
            obj = res["per_object"][anchor] = {
                "fate": fate,
                "ink": tot,
                "kept": kept,
                "in_one_box": False,
                "left_as_text": False,
                "with_company": False,
            }
            ys, xs = win
            best, best_j = (0, -1)
            for j, x in enumerate(arte):
                c = _clip(ink.shape, x)
                if c is None:
                    continue
                r0 = max(ys.start, c[0].start) - ys.start
                r1 = min(ys.stop, c[0].stop) - ys.start
                c0 = max(xs.start, c[1].start) - xs.start
                c1 = min(xs.stop, c[1].stop) - xs.start
                if r1 <= r0 or c1 <= c0:
                    continue
                one = int(sub[r0:r1, c0:c1].sum())
                if one > best:
                    best, best_j = (one, j)
                    if best == tot:
                        break
            if best / tot >= WHOLE:
                res["in_one_box"] += 1
                obj["in_one_box"] = True
                riders.setdefault(best_j, []).append(anchor)
            elif r >= WHOLE:
                res["split_between_boxes"] += 1
            if r < WHOLE and _carried_as_text(sub, ma[win], mr[win], tot):
                res["left_as_text"] += 1
                obj["left_as_text"] = True
        for anchors in riders.values():
            if len(anchors) >= 2:
                res["arrived_with_company"] += len(anchors)
                res["boxes_with_many_objects"] += 1
                for a in anchors:
                    res["per_object"][a]["with_company"] = True
    doc.close()
    res["dpi"] = sorted(dpis)
    res["median_box_area"] = statistics.median(areas) if areas else None
    return res


def report(res: dict) -> None:
    n, s = (res["objects"], res["page_count"])
    ink = res["ink_total"]
    t = res["thresholds"]
    log(
        f"pages {s}, raster {'/'.join(map(str, res['dpi'])) or '?'} dpi; ink threshold {t['ink']}; shares of the object's ink: intact from {t['intact']:.2f}, almost intact from {t['almost']:.2f}, bitten from {t['bitten']:.2f}"
    )
    log(
        f"area under boxes {res['boxes_area'] / max(1, res['sheet_area']) * 100:.0f}% of the sheet — at 100% the numbers below mean nothing: a box over the whole sheet wins the measurement having found nothing"
    )
    log(
        "HOW THIS INSTRUMENT IS WON: merging neighbouring boxes it barely penalises by construction — a merged box improves the ink here, and 'intact', and 'cuts as one picture'. Whether things stuck together — ask `books score`; a model is not chosen on this report alone"
    )
    if not ink:
        log(
            "NO ink found AT ALL: not one pixel darker than the threshold. This is not 'everything is lost' but 'nothing to measure' — an empty raster, the wrong threshold or the wrong book"
        )
        return
    log(
        f"page ink under boxes: {res['ink_under_boxes'] / ink * 100:.1f}% (under an artefact {res['ink_under_artifact'] / ink * 100:.1f}%), outside every box {(1 - res['ink_under_boxes'] / ink) * 100:.1f}% — that is what will vanish from the HTML"
    )
    clean = res.get("ink_clean") or 0
    if clean and res.get("ink_junk"):
        log(
            f"of that ink {res['ink_junk'] / ink * 100:.1f}% is binding shadow and scan edge, not information; over the ink that IS ink, under boxes {res['clean_under_boxes'] / clean * 100:.1f}%, outside every box {(1 - res['clean_under_boxes'] / clean) * 100:.1f}%"
        )
    if res.get("blocks_with_content"):
        log(
            f"of the sheet's ink {res['ink_as_text'] / ink * 100:.1f}% leaves the book as text and {res['ink_as_picture'] / ink * 100:.1f}% as a picture"
        )
    lost = ink - res["ink_under_boxes"]
    log(
        f"  edge band {t['edge_band'] * 100:.0f}% of the shorter side; "
        + (
            f"of what was lost, {res['ink_outside_boxes_at_edge'] / lost * 100:.0f}% lies in it — usually the dark edge of the scan, not content"
            if lost > 0
            else "nothing to lose: all the ink is under boxes"
        )
    )
    cols = res["dark_columns"]
    pos = res["dark_columns_positions"]
    middle = sum((1 for x in pos if 0.2 <= x <= 0.8))
    where = (
        "likely table rules, not a scan defect"
        if middle
        else "not one, i.e. these are the edges and the gutter"
    )
    log(
        f"  solid dark columns {cols} on {res['pages_with_dark_column']} pp. (a column dark over more than {GUTTER * 100:.0f}% of the sheet height); ink in them {res['ink_in_dark_columns'] / ink * 100:.1f}% of ALL, of it {res['ink_in_dark_columns_off_edge'] / ink * 100:.1f}% outside the edge band — the line above cannot see that by construction. "
        + (
            f"In the middle of the sheet (0.2..0.8 of the width) {middle} of {cols}: {where}"
            if cols
            else "there are none — this book was scanned without a gutter shadow"
        )
        + ". A box covering such a column RAISES the under-boxes number having found nothing"
    )
    if not res["truth_pages"]:
        log("truth NOT supplied: nothing to say about objects — this is not zero loss")
        return
    if not n:
        log(
            f"truth supplied ({res['truth_pages']} pages), but it holds not one artefact: nothing to say about objects. This is a DIFFERENT zero from 'truth NOT supplied', and neither is 'zero loss'"
        )
        return
    log(
        f"OBJECT INK PRESERVED: {res['object_ink_in_boxes'] / max(1, res['object_ink']) * 100:.1f}%"
    )
    log(
        f"objects {n}: intact {res['intact']} ({res['intact'] / n * 100:.0f}%), almost intact {res['almost_intact']}, bitten {res['bitten']}, torn {res['torn']}"
    )
    log(
        f"cuts as one picture {res['in_one_box']} ({res['in_one_box'] / n * 100:.0f}%); split between boxes {res['split_between_boxes']}; left as text {res['left_as_text']}"
    )
    log(
        f"arrived with company {res['arrived_with_company']} ({res['arrived_with_company'] / n * 100:.0f}%), boxes with two objects or more: {res['boxes_with_many_objects']} — that is work handed to the second level, and ONLY this number grows with merging"
    )
    if res["empty_objects"]:
        log(
            f"WARNING: {res['empty_objects']} truth objects without ink — a bench defect, counted neither as intact nor as torn"
        )
