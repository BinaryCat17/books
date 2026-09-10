"""Is the model output fit to push OCR through without losing meaning.

Counted over the raster pixel, and so over `PAGE_DPI`: the ink -- an object's
dark pixels inside boxes of the artefact role; whether it arrives in one box or
spread over two; and the role, an object under text boxes alone never reaching
level two. Area under boxes is printed beside them, or finding nothing wins.

Merging is barely penalised here by construction, so "arrived with company", the
one number that grows with it, is printed too. Truth is not required: without it
the same is counted over the whole page's ink, which is what leaves the HTML.
"""
import json
import os
import statistics

from booksmith.core import policy
from booksmith.core import raster
from booksmith.core import page
from booksmith.core.errors import Unmeasurable
# The spread-cutter's own numbers, imported and not copied: a second set here
# would be free to drift from the code that pays for them in false vetoes.
from booksmith.processing.extract.djvu import (
    GUTTER_BAND, MIN_SPREAD_RATIO, RULE_RUN)
from booksmith.core.log import log

# The "this is ink" threshold: darker is content, lighter is paper. A knowing
# second copy of `synth.INK`, since the metric must not depend on who draws the
# bench; `test_fitness` and a mutation hold the two together.
INK = 160
# The shares that sort objects into classes of survival, printed in the report:
# where "whole" ends and "bitten" begins is our decision and must be visible.
WHOLE, ALMOST, BITTEN = 0.99, 0.95, 0.80
# Width of the edge band, as a share of the shorter side of the sheet.
EDGE = 0.04
# Solid dark column: the share of the sheet's height a pixel column must be dark
# over to count as a scan defect rather than as content. `EDGE` sees the sheet's
# edges only, and the gutter shadow is the same phenomenon inside it; without
# this number a box laid on the shadow reads as a delivery. The rule is
# structural -- a full-height table rule qualifies too -- so positions are
# printed and never assumed.
GUTTER = 0.5
# Where a binding can be: outside the middle three fifths of the width, or -- on
# a sheet still wide enough to be an uncut spread -- in the middle fifth where
# `djvu` would have cut it.
MID = 0.20
# A binding shadow is a strip: wider than this share of the sheet it is something
# else, whatever its position (widest true shadow measured 0.067, narrowest
# positional run rejected 0.106).
JUNK_WIDTH = 0.10


# The page raster does not change between runs and the probes make some thirty
# passes over a book, so the ink mask and the junk mask are cached per page,
# packed by the bit, under a cap in bytes. The threshold is part of the key: the
# probes move it to check it is alive, and a mask from a key that ignored it
# would make a live threshold look dead.
#
# Eviction drops pages of other books and never our own: the walk within a book
# is sequential, so our own page is exactly what the next pass wants. The cap was
# derived for `PAGE_DPI = 144`, where the golden bench is 375 MiB packed against
# 2998 MiB unpacked; at 300 dpi the same bench is 1.6 GiB and only a fifth of the
# renders are saved.
_INK_CACHE = {}
_INK_CACHE_BYTES = 0
_INK_CACHE_MAX_BYTES = 512 << 20


def _evict_foreign(pdf):
    """Drop one page of a foreign book. False -- no foreign pages left."""
    global _INK_CACHE_BYTES
    for k in _INK_CACHE:
        if k[0] != pdf:
            _INK_CACHE_BYTES -= _INK_CACHE.pop(k)[1].nbytes
            return True
    return False


def _ink_of(pdf, doc, i, dpi):
    """The page ink mask, cached. The key includes the threshold."""
    import numpy as np
    global _INK_CACHE_BYTES
    # The threshold is in the key: the probes move INK to check it is alive.
    key = (pdf, i, int(dpi), INK)
    hit = _INK_CACHE.get(key)
    if hit is None:
        m = _ink(doc[i], dpi)
        packed = np.packbits(m)
        # Room is freed at the expense of other books and of them only: our own
        # page is what the next pass needs, the previous book never again.
        while (_INK_CACHE_BYTES + packed.nbytes > _INK_CACHE_MAX_BYTES
               and _evict_foreign(pdf)):
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
    """The box clipped to the sheet, as a pair of slices; None if it is off it.

    Clipping is explicit, not "numpy will trim it": numpy trims from the top
    only, so a negative far edge counts from the end and a box off the top-left
    corner would cover almost the whole sheet.
    """
    h, w = shape
    x0, y0, x1, y1 = (int(v) for v in box)
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(w - 1, x1), min(h - 1, y1)
    if x1 < x0 or y1 < y0:
        return None
    return slice(y0, y1 + 1), slice(x0, x1 + 1)


_JUNK_CACHE: dict = {}


def _strips(columns) -> list:
    """Runs of marked columns as `[x0, x1)` pairs in page pixels."""
    import numpy as np
    edge = np.diff(np.r_[0, columns.astype(np.int8), 0])
    return [[int(a), int(b)] for a, b in
            zip(np.flatnonzero(edge == 1), np.flatnonzero(edge == -1), strict=True)]


def _junk_of(pdf, i, dpi, ink):
    """`_junk_columns`, cached on the same page the ink mask is cached on.

    A function of the raster and six constants -- the property the design rests
    on, that no model can move it, and what makes it cacheable. The key carries
    all six, for the reason the ink key carries `INK`; the value is one boolean
    per column, so it is neither capped nor evicted.
    """
    key = (pdf, i, int(dpi), INK, GUTTER, MID, JUNK_WIDTH,
           RULE_RUN, GUTTER_BAND, MIN_SPREAD_RATIO, EDGE)
    hit = _JUNK_CACHE.get(key)
    if hit is None:
        hit = _JUNK_CACHE[key] = _junk_columns(ink)
    return hit


def _junk_columns(ink):
    """The pixel columns that are binding shadow or scan edge, not content.

    Positional, never "this column is dark": a dark plate mid-sheet is content.
    A band is junk only if it lies in the outer fifths (or the middle fifth of
    a sheet still wider than tall, where an uncut spread's gutter is), is no
    wider than `JUNK_WIDTH` of the sheet, and no row black across it carries a
    run of `RULE_RUN` of the width, which would make it a table rule. The mask
    never sees a box, so no model can move it.
    """
    import numpy as np
    h, w = ink.shape
    dark = ink.sum(axis=0) > h * GUTTER
    junk = np.zeros(w, bool)
    if not dark.any():
        return junk
    d = np.diff(np.r_[0, dark.astype(np.int8), 0])
    starts, ends = np.flatnonzero(d == 1), np.flatnonzero(d == -1)
    spread = w > h * MIN_SPREAD_RATIO
    k = max(1, int(min(h, w) * EDGE))
    body = ink[k:h - k] if h > 2 * k else ink
    span = int(RULE_RUN * w)
    for a, b in zip(starts, ends, strict=True):
        c = (a + b) / 2.0 / w
        if not (c < MID or c > 1 - MID
                or (spread and abs(c - 0.5) <= GUTTER_BAND / 2)):
            continue
        if (b - a) / w > JUNK_WIDTH:
            continue
        # The veto must answer at its ends, not switch itself off: span 0 means
        # "any run at all is a rule", so nothing is junk; a span past the sheet
        # means no run can be one, and position and width decide alone.
        if span <= 0:
            continue
        full = body[:, a:b].all(axis=1)
        # The run must cross this band, not merely exist on the page: asked of
        # the whole row the veto is a page-level switch, one table rule anywhere
        # sparing every band on the sheet. A window starting at `i` covers
        # `[i, i+span)` and meets `[a, b)` when `i < b` and `i + span > a`.
        lo, hi = max(0, a - span + 1), min(b - 1, w - span)
        if full.any() and span <= w and lo <= hi:
            rows = body[full].astype(np.int32)
            cum = np.cumsum(np.hstack(
                [np.zeros((rows.shape[0], 1), np.int32), rows]), axis=1)
            win = cum[:, lo + span:hi + span + 1] - cum[:, lo:hi + 1]
            if (win == span).any():
                continue          # a rule crosses it: content, not junk
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
    """Do boxes hold the object at all -- text ones included.

    A diagnosis, not a class: an object no artefact box holds, but some box holds
    whole, is not lost -- it leaves as a line and the structure with it, cured by
    a label rather than by a model. A union, not a sum, or a pixel under both an
    artefact box and a text box would count twice and turn an expensive trouble
    into a cheap one.
    """
    return int((sub & (arte | rest)).sum()) / tot >= WHOLE


def _policy_beside(pages_dir: str):
    """The run's policy out of the snapshot beside its pages, or the union of
    the tree's own vocabularies for a page directory with no snapshot."""
    for d in (pages_dir, os.path.dirname(os.path.abspath(pages_dir.rstrip("/")))):
        p = os.path.join(d, "run.json")
        if os.path.isfile(p):
            with open(p, encoding="utf-8") as f:
                snap = json.load(f)
            if isinstance(snap, dict) and snap.get("policy"):
                return policy.Policy.from_snapshot(snap["policy"])
    return policy.UNION


def measure(pdf: str, detect_dir: str, truth_dir: str = "",
            pol=None, tp=None) -> dict:
    """Fitness of the model output. Truth is not required. `pol` is the
    run's policy, found beside its pages when not given; `tp` truth's."""
    import numpy as np
    if not os.path.exists(pdf):
        raise Unmeasurable(f"no {pdf}")
    M = page.load_pages(detect_dir)
    T = page.load_pages(truth_dir) if truth_dir else {}
    pol = pol or _policy_beside(detect_dir)
    tp = tp or policy.UNION
    doc = raster.open_pdf(pdf)
    areas = []            # box area / page area, one per on-sheet box
    res = {"page_count": 0, "truth_pages": len(T), "dpi": [],
           "box_count": 0, "median_box_area": None,
           "ink_as_text": 0, "ink_as_picture": 0,
           # Clean both sides or neither: cleaning the denominator
           # alone gives 104.4 % under the attack this exists to
           # stop, and pays the attacker where cleaning both pays
           # nothing.
           "ink_junk": 0, "ink_clean": 0, "clean_under_boxes": 0,
           "blocks_with_content": 0,
           "ink_total": 0, "ink_under_boxes": 0,
           "ink_under_artifact": 0, "sheet_area": 0, "boxes_area": 0,
           "ink_outside_boxes_at_edge": 0,
           # Two numbers, not one: the second is the part the edge band cannot
           # see, and without it the addition would look already counted.
           "ink_in_dark_columns": 0,
           "ink_in_dark_columns_off_edge": 0,
           "dark_columns": 0, "pages_with_dark_column": 0,
           # Where they fell, as width shares: the rule is structural, and
           # position is the only thing telling a shadow from a table rule.
           "dark_columns_positions": [],
           "objects": 0, "object_ink": 0, "object_ink_in_boxes": 0,
           "intact": 0, "almost_intact": 0, "bitten": 0, "torn": 0,
           "in_one_box": 0, "split_between_boxes": 0, "left_as_text": 0,
           "arrived_with_company": 0, "boxes_with_many_objects": 0,
           "empty_objects": 0, "thresholds": {"ink": INK, "intact": WHOLE,
                                            "almost": ALMOST, "bitten": BITTEN,
                                            "edge_band": EDGE},
           # The same counts per page, with the junk strips and the edge band
           # in page pixels, and each truth object's fate by its anchor.
           "pages": {}, "per_object": {}}
    dpis = set()
    pages = sorted(T) if T else sorted(M)
    for i in pages:
        if i not in M:
            raise Unmeasurable(
                f"the model marked up no page {i}: nothing to count. An "
                f"empty answer here would look like 'no ink lost'.")
        p = M[i]
        ink = _ink_of(pdf, doc, i, p["dpi"])
        if ink.shape != (p["height"], p["width"]):
            raise Unmeasurable(
                f"page {i}: raster {ink.shape[1]}x{ink.shape[0]}, "
                f"markup {p['width']}x{p['height']} — the boxes will fall "
                f"wide")
        arte = [b["box"] for b in p["blocks"]
                if pol.role(b["label"]) == "artifact"]
        rest = [b["box"] for b in p["blocks"]
                if pol.role(b["label"]) != "artifact"]
        ma, mr = _mask(ink.shape, arte), _mask(ink.shape, rest)
        both = ma | mr
        # Where the ink ends up, by the builder's own rule and not a copy of
        # it: `assemble/html.py` emits a crop when `role == "artifact" or not
        # b.content` and a paragraph otherwise. A pixel is counted once and a
        # picture wins the tie, a crop shipping whole whatever lies over it, so
        # the split is exhaustive against `ink_total` and never sums past it.
        pic = _mask(ink.shape, [b["box"] for b in p["blocks"]
                                if pol.role(b["label"]) == "artifact"
                                or not (b.get("content") or "").strip()])
        txt = _mask(ink.shape, [b["box"] for b in p["blocks"]
                                if pol.role(b["label"]) != "artifact"
                                and (b.get("content") or "").strip()]) & ~pic
        as_picture, as_text = int((ink & pic).sum()), int((ink & txt).sum())
        res["ink_as_picture"] += as_picture
        res["ink_as_text"] += as_text
        res["blocks_with_content"] += sum(
            1 for b in p["blocks"] if (b.get("content") or "").strip())
        # Who arrived in which box: the artefact box against the truth
        # objects it carries whole. Hence "arrived with company".
        riders: dict = {}
        dpis.add(int(p["dpi"]))
        res["page_count"] += 1
        whole = int(ink.sum())
        under = int((ink & both).sum())
        res["ink_total"] += whole
        junk = _junk_of(pdf, i, p["dpi"], ink)
        # Counted over the junk columns alone, never by building a second
        # sheet: a copy of the page mask would be paid on every page of every
        # pass to answer a question about a strip a tenth of it wide.
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
        # Half the golden bench's "lost" ink lies in the edge band -- the dark
        # rim of the scan, not content -- so it is counted apart: without that a
        # black border reads as "the model lost a quarter of the book".
        out = ink & ~both
        h, w = ink.shape
        k = max(1, int(min(h, w) * EDGE))
        edge = np.zeros_like(out)
        edge[:k] = edge[-k:] = True
        edge[:, :k] = edge[:, -k:] = True
        res["ink_outside_boxes_at_edge"] += int((out & edge).sum())
        # Solid dark columns as a quantity of their own (`GUTTER`), counted over
        # all the sheet's ink rather than the lost: a box on the shadow turns
        # that ink into "found", which is where it then lies.
        columns = ink.sum(axis=0) > h * GUTTER
        if columns.any():
            res["ink_in_dark_columns"] += int(ink[:, columns].sum())
            # Its own column mask, not a row of `edge`: that one has its first
            # `k` rows filled solid, so `edge[0]` is all True and "off the edge"
            # would be zero always.
            row_edge = np.zeros(w, bool)
            row_edge[:k] = row_edge[-k:] = True
            res["ink_in_dark_columns_off_edge"] += int(
                ink[:, columns & ~row_edge].sum())
            col_edge = np.diff(np.r_[0, columns.astype(np.int8), 0])
            start = np.flatnonzero(col_edge == 1)
            end = np.flatnonzero(col_edge == -1)
            res["dark_columns"] += len(start)
            res["pages_with_dark_column"] += 1
            res["dark_columns_positions"].extend(
                round(float(a + b) / 2 / w, 2) for a, b in zip(start, end, strict=True))
        res["sheet_area"] += ink.size
        res["boxes_area"] += int(both.sum())
        # How big a box is, as a share of its own page. `area_under_boxes`
        # catches the model that boxes everything; this catches the opposite
        # degeneracy, a detector tracing the ink with many tiny boxes, which
        # takes all of it at a LOWER area than an honest run. Over 25 honest runs
        # on four books the median box is 0.7-2.6 % of its page and every tracing
        # cheat falls far below that band, so neither end is good and this is a
        # guard, never a rank. Per page, the golden bench mixing raster sizes.
        for sl in (_clip(ink.shape, b) for b in arte + rest):
            if sl is None:      # wholly off the sheet: no area to speak of
                continue
            ys, xs = sl
            areas.append(float((ys.stop - ys.start) * (xs.stop - xs.start))
                         / ink.size)
        # Every box the model drew, the ones off the sheet included: this is the
        # level-two bill, one crop and one paid request each.
        res["box_count"] += len(arte) + len(rest)
        res["pages"][i] = {
            "ink_total": whole, "ink_under_boxes": under,
            "ink_under_artifact": under_art, "ink_junk": j,
            "ink_clean": whole - j, "clean_under_boxes": clean_under,
            "ink_as_text": as_text, "ink_as_picture": as_picture,
            "box_count": len(arte) + len(rest),
            "junk_strips": _strips(junk), "edge": k}
        for b in T.get(i, {}).get("blocks", []):
            if tp.role(b["label"]) != "artifact":
                continue
            win = _clip(ink.shape, b["box"])
            sub = ink[win] if win else np.zeros((0, 0), bool)
            tot = int(sub.sum())
            if tot == 0:
                # An object with no ink is a defect of the bench, not of the
                # model, and is counted apart: in "intact" it would give an
                # unearned point, in "torn" an unearned miss. An object wholly
                # off the sheet lands here too.
                res["empty_objects"] += 1
                continue
            res["objects"] += 1
            res["object_ink"] += tot
            kept = int((sub & ma[win]).sum())
            res["object_ink_in_boxes"] += kept
            r = kept / tot
            fate = ("intact" if r >= WHOLE else "almost_intact" if r >= ALMOST
                    else "bitten" if r >= BITTEN else "torn")
            res[fate] += 1
            anchor = page.anchor(i, b["block_id"])
            obj = res["per_object"][anchor] = {
                "fate": fate, "ink": tot, "kept": kept,
                "in_one_box": False, "left_as_text": False, "with_company": False}
            # "One box" is counted by the same ink as "intact", the difference
            # being only how many boxes hold the object -- their union, or one --
            # so the numbers nest strictly, never fewer intact than cut as one
            # picture. The intersection of two rectangles is a rectangle, so ink
            # under one box is counted inside the object's window rather than by
            # a full-sheet mask per box.
            ys, xs = win
            best, best_j = 0, -1
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
                    best, best_j = one, j
                    if best == tot:
                        break
            if best / tot >= WHOLE:
                res["in_one_box"] += 1
                obj["in_one_box"] = True
                # The object rides in this box -- the one `books crop` will cut.
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
    # The median, not the list: thousands of box areas would ride into `detail`
    # and on into `results/*.json` to answer one question, and the mean would not
    # answer it -- one full-sheet box among many tiny ones drags it into the band.
    res["median_box_area"] = statistics.median(areas) if areas else None
    return res


def report(res: dict) -> None:
    n, s = res["objects"], res["page_count"]
    ink = res["ink_total"]
    # The ruler is declared whole and on the first line, dpi included, and read
    # from the answer rather than from the module: the probes move these very
    # globals, and a report reading them would lie about its own measurement.
    t = res["thresholds"]
    log(f"pages {s}, raster {'/'.join(map(str, res['dpi'])) or '?'} dpi; "
        f"ink threshold {t['ink']}; shares of the object's ink: "
        f"intact from {t['intact']:.2f}, almost intact from "
        f"{t['almost']:.2f}, bitten from {t['bitten']:.2f}")
    log(f"area under boxes "
        f"{res['boxes_area'] / max(1, res['sheet_area']) * 100:.0f}% of the "
        f"sheet — at 100% the numbers below mean nothing: a box over the "
        f"whole sheet wins the measurement having found nothing")
    # Blindness is declared before the numbers and unconditionally: the
    # truth-less mode is the one real scans are measured in.
    log("HOW THIS INSTRUMENT IS WON: merging neighbouring boxes it barely "
        "penalises by construction — a merged box improves the ink here, and "
        "'intact', and 'cuts as one picture'. Whether things stuck together "
        "— ask `books score`; a model is not chosen on this report alone")
    if not ink:
        # A zero from not understanding, not from measurement: an empty raster
        # must not print as "the whole book is lost".
        log("NO ink found AT ALL: not one pixel darker than the threshold. "
            "This is not 'everything is lost' but 'nothing to measure' — an "
            "empty raster, the wrong threshold or the wrong book")
        return
    log(f"page ink under boxes: "
        f"{res['ink_under_boxes'] / ink * 100:.1f}% "
        f"(under an artefact "
        f"{res['ink_under_artifact'] / ink * 100:.1f}%), outside every box "
        f"{(1 - res['ink_under_boxes'] / ink) * 100:.1f}% — that is what "
        f"will vanish from the HTML")
    # And the same with the binding discarded: `books fitness` is the mode real
    # scans are measured in, and the raw loss alone hides the one number the junk
    # mask exists to correct -- 20.8 % against 6.4 % on the book it was written
    # for.
    clean = res.get("ink_clean") or 0
    if clean and res.get("ink_junk"):
        log(f"of that ink {res['ink_junk'] / ink * 100:.1f}% is binding "
            f"shadow and scan edge, not information; over the ink that IS "
            f"ink, under boxes {res['clean_under_boxes'] / clean * 100:.1f}%, "
            f"outside every box "
            f"{(1 - res['clean_under_boxes'] / clean) * 100:.1f}%")
    # Where it leaves, and only when the run has read something: a detection run
    # has no content, so every block would leave as a picture and the split would
    # state a fact about the run in the shape of a fact about the model.
    if res.get("blocks_with_content"):
        log(f"of the sheet's ink {res['ink_as_text'] / ink * 100:.1f}% "
            f"leaves the book as text and "
            f"{res['ink_as_picture'] / ink * 100:.1f}% as a picture")
    # Declared unconditionally: printed only on a loss, `EDGE` could be dropped
    # from the report with no check going red. A ruler does not depend on what
    # was measured with it.
    lost = ink - res["ink_under_boxes"]
    log(f"  edge band {t['edge_band'] * 100:.0f}% of the shorter side; "
        + (f"of what was lost, "
           f"{res['ink_outside_boxes_at_edge'] / lost * 100:.0f}% lies in it "
           f"— usually the dark edge of the scan, not content"
           if lost > 0 else "nothing to lose: all the ink is under boxes"))
    # Likewise unconditional, and here rather than among the losses because it is
    # about what was found: a dark column under a box scores as preserved content
    # and lifts the line above having found nothing (`GUTTER`).
    cols = res["dark_columns"]
    pos = res["dark_columns_positions"]
    middle = sum(1 for x in pos if 0.2 <= x <= 0.8)
    where = ("likely table rules, not a scan defect" if middle
             else "not one, i.e. these are the edges and the gutter")
    log(f"  solid dark columns {cols} on "
        f"{res['pages_with_dark_column']} pp. (a column dark over more than "
        f"{GUTTER * 100:.0f}% of the sheet height); ink in them "
        f"{res['ink_in_dark_columns'] / ink * 100:.1f}% of ALL, of it "
        f"{res['ink_in_dark_columns_off_edge'] / ink * 100:.1f}% outside "
        f"the edge band — the line above cannot see that by construction. "
        + (f"In the middle of the sheet (0.2..0.8 of the width) {middle} of "
           f"{cols}: "
           f"{where}"
           if cols else "there are none — this book was scanned without a "
                        "gutter shadow")
        + ". A box covering such a column RAISES the under-boxes number "
          "having found nothing")
    # Three different zeros: "truth not supplied", "truth holds no artefact" and
    # zero loss are not one answer.
    if not res["truth_pages"]:
        log("truth NOT supplied: nothing to say about objects — this is "
            "not zero loss")
        return
    if not n:
        log(f"truth supplied ({res['truth_pages']} pages), but it holds "
            f"not one artefact: nothing to say about objects. This is a "
            f"DIFFERENT zero from 'truth NOT supplied', and neither is "
            f"'zero loss'")
        return
    log(f"OBJECT INK PRESERVED: "
        f"{res['object_ink_in_boxes'] / max(1, res['object_ink']) * 100:.1f}%")
    log(f"objects {n}: intact {res['intact']} "
        f"({res['intact'] / n * 100:.0f}%), "
        f"almost intact {res['almost_intact']}, bitten {res['bitten']}, "
        f"torn {res['torn']}")
    log(f"cuts as one picture {res['in_one_box']} "
        f"({res['in_one_box'] / n * 100:.0f}%); "
        f"split between boxes {res['split_between_boxes']}; "
        f"left as text {res['left_as_text']}")
    # The one number of this instrument that grows with merging; every other one
    # improves under it.
    log(f"arrived with company {res['arrived_with_company']} "
        f"({res['arrived_with_company'] / n * 100:.0f}%), "
        f"boxes with two objects or more: "
        f"{res['boxes_with_many_objects']} — that is work handed to the "
        f"second level, and ONLY this number grows with merging")
    if res["empty_objects"]:
        log(f"WARNING: {res['empty_objects']} truth objects without ink — "
            f"a bench defect, counted neither as intact nor as torn")
