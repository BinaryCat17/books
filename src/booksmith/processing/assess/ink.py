"""Is the model output fit to push OCR through without losing meaning.

The two older numbers answer other questions. "Outlined precisely" (two-sided
cover 0.75) measures the PRECISION of the box and penalises merging, which
costs this pipeline almost nothing: level two gets a wider picture and splits
it in two. "Meaning intact" penalises merging too. Both understate fitness
badly: on the 36 hardest golden-bench pages the first gives 20%, against 91% of
objects reaching level two undamaged (intact 365 of 402). All 600 golden pages
are a DIFFERENT bench, never to be mixed with those 36: there one picture cuts
1014 of 1230 = 82% (intact 1018, 83%), by `books fitness
bench/annopage/annopage.pdf --detect … --truth …`, on a denominator of 1230 and
not 1232 because two ink-less truth objects are counted apart.

Counted here is what the result depends on:

  INK. The share of an object's dark pixels lying inside boxes of the artefact
  role. This settles "the box is tighter than the reference": the margin round
  a figure holds no ink, a cut-off table row is restored by nothing. dots.ocr
  leads on strict match (37% against 20%) and TRAILS on ink, 88.6% against
  94.8%, for exactly that reason.

  ONE BOX OR TWO. An object wholly inside ONE box is cut as one picture, with
  or without a neighbour; spread over two it arrives in two pieces and the
  table falls apart.

  ROLE. An object covered by text boxes only never reaches level two: it leaves
  as a line of text, and the structure with it (`_carried_as_text`).

One box over the whole sheet gives 100% of the ink and 100% of the objects
whole, so AREA UNDER BOXES is printed beside them: without it the metric is won
by finding nothing.

WHAT THE INSTRUMENT CANNOT SEE, AND SAYS SO IN ITS OWN OUTPUT, before the
numbers and truth or no truth. Merging neighbouring boxes is barely penalised
here by construction -- that is the design -- but merging is not free: merged
into one enclosing box per page, on bench/hard36 nearly every number here
improves (intact 365 -> 385, torn 28 -> 13, object ink 94.8% -> 96.1%), so the
worst thing that happens to structure scores as an improvement. On exactly this
the vendor docling pipeline came out costing "seven objects" instead of a
hundred and thirty-two.

  ARRIVED WITH COMPANY exists for that -- the one number here that GROWS with
  merging, and the battery demands both at once: the older numbers hold, this
  one rises. Truth objects arriving in a shared box are the work level two will
  do taking one picture apart: on those 36 pages 309 -> 385 at 32 -> 35 boxes
  carrying two objects or more. From the same ink by the same "intact"
  threshold, without a new one; `books score` does not duplicate it, that one
  checks boxes against truth.

THE UNIT IS THE RASTER PIXEL, so everything here depends on `PAGE_DPI`. On
bench/real/tables20.pdf with the box geometry unchanged: ink under artefact
24.83% (144 dpi) -> 25.63% (300) -> 25.99% (600); ink under boxes 99.26 ->
99.25 -> 99.24%. Small, real and one-directional, so dpi is printed on the
first line: without it two numbers from two runs are incomparable.

TRUTH IS NOT REQUIRED. Without it the same is counted over the ink of the WHOLE
page: how much stayed outside every box, i.e. what will vanish from the HTML.
That works on any book nobody has annotated yet.
"""
import os

import numpy as np

from booksmith.core import policy
from booksmith.core import raster
from booksmith.core import page
from booksmith.core.errors import Unmeasurable

# The "this is ink" threshold: darker is content, lighter is paper. The same
# INK the synthetic bench measures its truth by, and knowingly a SECOND COPY:
# `synth.INK` holds the same 160. Not merged by an import -- which would cost
# nothing (2 ms against 221 ms for this module) -- because the metric must not
# depend on who draws the bench: `books fitness` runs on real scans, where no
# `synth` exists. The two copies are held together by `test_fitness` and a
# mutation against it: let them diverge and it goes red.
INK = 160
# The shares that sort objects into classes of survival. Named by number and
# printed in the report: where "whole" ends and "bitten" begins is our decision
# and has to be visible.
WHOLE, ALMOST, BITTEN = 0.99, 0.95, 0.80
# Width of the edge band, as a share of the shorter side of the sheet.
EDGE = 0.04
# SOLID DARK COLUMN: the share of the sheet's height a pixel column must be
# dark over to count as a scan defect rather than as content.
#
# WHY, AND THIS IS A MEASUREMENT. `EDGE` sees only the edges of the sheet by
# construction; the gutter shadow is the same phenomenon INSIDE it. On
# "Технология огнеупоров" the columns fall at x 658..717 with the sheet 730
# wide, the edge band being the last 29 px; over all 378 pages, 261 solid dark
# columns on 230 pages hold 10.5 % of ALL the book's ink, 7.8 % of it outside
# the edge band and so invisible to the older counter.
#
# WHAT PAID FOR IT. Without this number the instrument REWARDS a box on the
# shadow: 261 fake boxes along those columns -- pure damage finding nothing --
# lift "ink under boxes" 85.7 % -> 96.2 % and drop "vanishes from the HTML"
# 14.3 % -> 3.8 %, while the declared guard (a full-sheet box wins) stays
# silent: area under boxes 64 % -> 65 %. Removing the 21 real `aside_text`
# boxes it scores as a WORSENING (85.7 % -> 85.4 %).
#
# WHAT IT DOES NOT CLAIM. Named after what it measures, not "gutter shadow":
# the rule is structural, and a full-height table rule qualifies. On this book
# 4 of the 261 columns stand mid-sheet (0.2..0.8 of the width) against 257 at
# the edges -- four found by the full run where a sample of 90 columns off
# every third page said none. Hence positions are printed, not assumed: on
# another book the middle share may be anything, and the honest name would go.
GUTTER = 0.5


# The page raster does not change between runs, and the battery makes
# TWENTY-THREE passes over the book (24 `measure` calls, 23 of them reading the
# raster). Counted on bench/hard36: 828 renders with no cache over 36 pages,
# exactly 23 x 36.
#
# THE COST IS MEASURED TOO, on an IDLE machine: 120 golden pages render with
# thresholding in 33.4 s -- 278 ms a page, best of three, load average 0.6-1.0
# on 16 cores. A busy machine takes three times that, so a cost taken under
# load lies threefold. Over 600 pages: no cache, 23 passes = 64 minutes; cache,
# 3 passes = 8 minutes, a 7.7-fold gain.
#
# WHY THREE PASSES AND NOT ONE. The ink threshold is part of the cache key
# (else the battery could not check it alive), and the probes `INK=0` and
# `INK=256` re-render the book each -- their masks really are different: 108
# renders with the cache over the same 36 pages, exactly 3 x 36.
#
# A CAP IN BYTES, masks packed by the bit, FOREIGN BOOKS EVICTED, OUR OWN HELD.
# Two earlier caches evicted our own pages -- 64 pages with a full flush, then
# a byte cap dropping the oldest -- and saved nothing, the walk being
# sequential; a third evicted nothing, which holds our book but leaves a second
# book in the same process not a byte, and eight benches in a row in one process
# is what both people and checks do. Simulated on the REAL access trace (23
# passes off the battery, with their thresholds) and REAL page shapes
# (bench/*/truth), cap 512 MiB:
#
#                              no cache      evicting     holding     as here
#   one book (600 pp.)             13800          2400        1800        1800
#   two books running (600+600)    27600          4200       15600        3600
#   two BIG books (375+375)        27600          4800       15600        3600
#
# The ideal is 1800 and 3600 (three passes a book), reached in both regimes,
# and no regime was found where this is worse than either older one.
#
# THE LIMIT IS NARROW: the cap was derived for `PAGE_DPI = 144`. Same bench,
# same cap:
#
#     dpi   bench, MiB   pages that fit   renders   ideal   no cache
#     144          375       600 of 600       1800    1800      13800
#     300         1626       134 of 600      11040    1800      13800
#     600         6505        30 of 600      13160    1800      13800
#
# So at 300 dpi the cache saves 20%, at 600 -- 5%, and there is nothing to
# raise the cap with: the full bench at 300 dpi is 1.6 GiB. The project's real
# scans are 300-600 dpi, so the battery stays expensive there -- known before
# the run, not after.
#
# The 512 MiB is measured: the golden bench at 144 dpi is 2998 MiB as boolean
# masks and 375 MiB packed, 1.37x of headroom; 256 MiB would hold 362 of 600.
_INK_CACHE = {}
_INK_CACHE_BYTES = 0
_INK_CACHE_MAX_BYTES = 512 << 20


def _evict_foreign(pdf):
    """Drop one page of a FOREIGN book. False -- no foreign pages left."""
    global _INK_CACHE_BYTES
    for k in _INK_CACHE:
        if k[0] != pdf:
            _INK_CACHE_BYTES -= _INK_CACHE.pop(k)[1].nbytes
            return True
    return False


def _ink_of(pdf, doc, i, dpi):
    """The page ink mask, cached. The key includes the THRESHOLD."""
    global _INK_CACHE_BYTES
    # The threshold is in the key for a reason: the battery moves INK to check
    # it is alive, and without it a mask computed with the OLD threshold would
    # come back -- a live threshold would look dead and the probe would blame
    # the metric for nothing.
    key = (pdf, i, int(dpi), INK)
    hit = _INK_CACHE.get(key)
    if hit is None:
        m = _ink(doc[i], dpi)
        packed = np.packbits(m)
        # Room is freed AT THE EXPENSE OF OTHER BOOKS and of them only: the
        # walk within a book is sequential, so our own page is exactly what the
        # next pass needs, while the previous book is needed never again.
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
    pm = raster.render(page, dpi)
    g = np.frombuffer(pm.samples, np.uint8).reshape(pm.height, pm.width, pm.n)
    g = g[:, :, :3].mean(2) if pm.n >= 3 else g[:, :, 0]
    return g < INK


def _clip(shape, box):
    """The box clipped to the sheet, as a pair of slices; None if it is off it.

    Clipping is EXPLICIT, not "numpy will trim it". Numpy trims from the top
    only: `[:int(y1) + 1]` with a negative `y1` counts FROM THE END, so a box
    off the top-left corner covers almost the whole sheet -- `_mask((100, 100),
    [[-40, -40, -20, -20]])` gave 6561 pixels of 10000. A full walk of every
    annotation in git (42 565 boxes, 3187 pages) finds 516 boxes wholly off the
    sheet, 514 of them in `bench/annopage-lite/dots-pages`, the `dots.ocr`
    output that measured 636 layout pages.

    Whether that spoiled a recorded number was CHECKED, not assumed: all 516 ran
    DOWN (`y0 >= height`), none has a negative far edge, and the old slicing
    broke on a negative far edge only. Old against new by mask over all 3187
    pages: pages that differ ZERO. Not one number was hurt, but by luck. A
    metric that can be won with rubbish is no argument -- hence the probe.
    """
    h, w = shape
    x0, y0, x1, y1 = (int(v) for v in box)
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(w - 1, x1), min(h - 1, y1)
    if x1 < x0 or y1 < y0:
        return None
    return slice(y0, y1 + 1), slice(x0, x1 + 1)


def _mask(shape, boxes):
    m = np.zeros(shape, bool)
    for b in boxes:
        win = _clip(shape, b)
        if win is not None:
            m[win] = True
    return m


def _carried_as_text(sub, arte, rest, tot):
    """Do boxes hold the object AT ALL -- text ones included.

    A diagnosis, not a class: an object no artefact box holds, but some box
    holds whole, is not lost -- it leaves as a line and the structure goes with
    it. Cured by a label rather than by a model, so cheaper than a loss.

    A UNION, NOT A SUM, and the rule has one home. `t_kept + kept` stood inline
    in the measurement, and a pixel under an artefact box and a text box both
    counted TWICE.

    THE COST IS MEASURED ON REAL OUTPUT. "Zero false positives on
    PP-DocLayoutV2" came off seven SMALL benches; a full pass over the two big
    ones gives six records -- `bench/annopage` 90 -> 86, `bench/hard` 44 -> 42
    -- over four DISTINCT objects, `bench/hard` being built from the same books.
    One of the four is real trouble: annopage p. 94, `table` -- 0.666 of its ink
    under artefact boxes, 0.860 under boxes of any kind, sum 1.167. Fourteen
    percent covered by NOTHING, which the old count called "not lost, cured by a
    label": an expensive trouble rewritten as a cheap one. The other three are
    borderline (0.981, 0.990, 0.989 against 0.99). What matters more: the seven
    small benches had NONE, and by that zero the defect was declared harmless.

    Doubled annotation is no invention: raw `docling-heron` has 4435 doubled
    pairs. On bench/hard36, handing every artefact box out again as text grew
    "left as text" from 21 to 31.
    """
    return int((sub & (arte | rest)).sum()) / tot >= WHOLE


def measure(pdf: str, detect_dir: str, truth_dir: str = "") -> dict:
    """Fitness of the model output. Truth is not required."""
    if not os.path.exists(pdf):
        raise Unmeasurable(f"no {pdf}")
    M = page.load_pages(detect_dir)
    T = page.load_pages(truth_dir) if truth_dir else {}
    doc = raster.open_pdf(pdf)
    res = {"page_count": 0, "truth_pages": len(T), "dpi": [],
           "ink_total": 0, "ink_under_boxes": 0,
           "ink_under_artifact": 0, "sheet_area": 0, "boxes_area": 0,
           "ink_outside_boxes_at_edge": 0,
           # TWO NUMBERS, NOT ONE: the second is the part the edge band cannot
           # see by construction. Without it the addition would look already
           # counted.
           "ink_in_dark_columns": 0,
           "ink_in_dark_columns_off_edge": 0,
           "dark_columns": 0, "pages_with_dark_column": 0,
           # Where they fell, as a list of width shares. The rule is
           # structural and knows nothing of gutters; position is the only
           # thing that tells a shadow from a table rule.
           "dark_columns_positions": [],
           "objects": 0, "object_ink": 0, "object_ink_in_boxes": 0,
           "intact": 0, "almost_intact": 0, "bitten": 0, "torn": 0,
           "in_one_box": 0, "split_between_boxes": 0, "left_as_text": 0,
           "arrived_with_company": 0, "boxes_with_many_objects": 0,
           "empty_objects": 0, "thresholds": {"ink": INK, "intact": WHOLE,
                                            "almost": ALMOST, "bitten": BITTEN,
                                            "edge_band": EDGE}}
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
                if policy.role(b["label"]) == "artifact"]
        rest = [b["box"] for b in p["blocks"]
                if policy.role(b["label"]) != "artifact"]
        ma, mr = _mask(ink.shape, arte), _mask(ink.shape, rest)
        both = ma | mr
        # Who arrived in which box: key is the artefact box, value is how many
        # truth objects it carries whole. Hence "arrived with company", the one
        # number of this instrument that GROWS with merging.
        riders = {}
        dpis.add(int(p["dpi"]))
        res["page_count"] += 1
        res["ink_total"] += int(ink.sum())
        res["ink_under_boxes"] += int((ink & both).sum())
        res["ink_under_artifact"] += int((ink & ma).sum())
        # Half the golden bench's "lost" ink lies in the four-percent band at
        # the edge -- the dark rim of the scan, not content. Counted apart:
        # without it a black border reads as "the model lost a quarter of the
        # book".
        out = ink & ~both
        h, w = ink.shape
        k = max(1, int(min(h, w) * EDGE))
        edge = np.zeros_like(out)
        edge[:k] = edge[-k:] = True
        edge[:, :k] = edge[:, -k:] = True
        res["ink_outside_boxes_at_edge"] += int((out & edge).sum())
        # SOLID DARK COLUMNS as a quantity of their own, reasoning at `GUTTER`.
        # Counted over ALL the ink of the sheet, not over the lost: a box on the
        # shadow turns that ink into "found", and that is where it lies.
        columns = ink.sum(axis=0) > h * GUTTER
        if columns.any():
            res["ink_in_dark_columns"] += int(ink[:, columns].sum())
            # ITS OWN column mask, not a row of `edge`: that one is
            # two-dimensional and its first `k` ROWS are filled solid, so
            # `edge[0]` is all True. Taken from there, "off the edge" would be
            # zero always and the addition would silently mean nothing.
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
                round(float(a + b) / 2 / w, 2) for a, b in zip(start, end))
        res["sheet_area"] += ink.size
        res["boxes_area"] += int(both.sum())
        for b in T.get(i, {}).get("blocks", []):
            if policy.role(b["label"]) != "artifact":
                continue
            win = _clip(ink.shape, b["box"])
            sub = ink[win] if win else np.zeros((0, 0), bool)
            tot = int(sub.sum())
            if tot == 0:
                # An object with no ink is a defect of the BENCH, not of the
                # model, and is counted apart: hidden in "intact" it gives the
                # model an unearned point, in "torn" an unearned miss. A truth
                # object wholly off the sheet lands here too -- no ink by
                # construction, and that is the bench again.
                res["empty_objects"] += 1
                continue
            res["objects"] += 1
            res["object_ink"] += tot
            kept = int((sub & ma[win]).sum())
            res["object_ink_in_boxes"] += kept
            r = kept / tot
            res["intact" if r >= WHOLE else "almost_intact" if r >= ALMOST
                else "bitten" if r >= BITTEN else "torn"] += 1
            # "One box" IS COUNTED BY THE SAME INK as "intact", the difference
            # being only how many boxes hold the object -- their union, or one.
            # So the numbers nest strictly, never fewer intact than cut as one
            # picture. The older revision counted "one box" by box GEOMETRY and
            # "intact" by ink, and the nesting broke: 92 golden-bench objects
            # were "without loss" without being "cut whole", and as many the
            # other way round.
            #
            # The intersection of two rectangles is a rectangle, so ink under
            # one box is counted right in the object's window. Before, a
            # full-sheet boolean mask was built for every artefact box of EVERY
            # object and thrown away at once -- gigabytes of allocation on the
            # golden bench for a count in a window the size of a table.
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
                # The object rides in THIS box -- the one `books crop` will cut.
                riders[best_j] = riders.get(best_j, 0) + 1
            elif r >= WHOLE:
                res["split_between_boxes"] += 1
            if r < WHOLE and _carried_as_text(sub, ma[win], mr[win], tot):
                res["left_as_text"] += 1
        for k in riders.values():
            if k >= 2:
                res["arrived_with_company"] += k
                res["boxes_with_many_objects"] += 1
    doc.close()
    res["dpi"] = sorted(dpis)
    return res


def report(res: dict, log=print) -> None:
    n, s = res["objects"], res["page_count"]
    ink = res["ink_total"]
    # THE RULER IS DECLARED WHOLE AND ON THE FIRST LINE: all four shares, where
    # ALMOST and BITTEN -- which split two of the printed columns -- appeared
    # nowhere, plus dpi, for the reason measured in the header. Read FROM THE
    # ANSWER, not from the module: the battery moves these very globals, and a
    # report reading them would lie about its own measurement.
    t = res["thresholds"]
    log(f"pages {s}, raster {'/'.join(map(str, res['dpi'])) or '?'} dpi; "
        f"ink threshold {t['ink']}; shares of the object's ink: "
        f"intact from {t['intact']:.2f}, almost intact from "
        f"{t['almost']:.2f}, bitten from {t['bitten']:.2f}")
    log(f"area under boxes "
        f"{res['boxes_area'] / max(1, res['sheet_area']) * 100:.0f}% of the "
        f"sheet — at 100% the numbers below mean nothing: a box over the "
        f"whole sheet wins the measurement having found nothing")
    # BLINDNESS IS DECLARED BEFORE THE NUMBERS AND UNCONDITIONALLY. This line
    # stood AFTER both truth `return`s, so in the truth-less mode -- the one
    # real scans are measured in -- not a word of it was printed, and its
    # numbers were someone else's run hardwired. Ours are on the "arrived with
    # company" line below.
    log("HOW THIS INSTRUMENT IS WON: merging neighbouring boxes it barely "
        "penalises by construction — a merged box improves the ink here, and "
        "'intact', and 'cuts as one picture'. Whether things stuck together "
        "— ask `books score`; a model is not chosen on this report alone")
    if not ink:
        # A ZERO FROM NOT UNDERSTANDING, NOT FROM MEASUREMENT. An empty raster
        # used to print as "outside every box 100.0% -- that is what vanishes
        # from the HTML": the divisor was swapped for `max(1, 0)`, so "nothing
        # to measure" came out as "the whole book is lost". Reproducible with a
        # white page in one call.
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
    # THE FIFTH THRESHOLD IS DECLARED UNCONDITIONALLY. The line printed only
    # when `lost > 0`, leaving `EDGE` droppable from the report without a check
    # going red. With nothing to lose the band is named all the same: a ruler
    # does not depend on what was measured with it.
    lost = ink - res["ink_under_boxes"]
    log(f"  edge band {t['edge_band'] * 100:.0f}% of the shorter side; "
        + (f"of what was lost, "
           f"{res['ink_outside_boxes_at_edge'] / lost * 100:.0f}% lies in it "
           f"— usually the dark edge of the scan, not content"
           if lost > 0 else "nothing to lose: all the ink is under boxes"))
    # THE SIXTH THRESHOLD, likewise unconditional, and standing here rather than
    # among the losses because it is about what was FOUND: a dark column under a
    # box scores as preserved content, and the box that covered it lifts the
    # line above having found nothing (`GUTTER`).
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
    # THREE DIFFERENT ZEROS, AND THEY USED TO BE ONE. "Truth not supplied" was
    # printed when truth was supplied and simply held no artefacts -- telling
    # the operator he had forgotten the `--truth` he had passed.
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
    # THE ONE NUMBER OF THIS INSTRUMENT THAT GROWS WITH MERGING; every other one
    # improves under it. Figures and reasoning in the header.
    log(f"arrived with company {res['arrived_with_company']} "
        f"({res['arrived_with_company'] / n * 100:.0f}%), "
        f"boxes with two objects or more: "
        f"{res['boxes_with_many_objects']} — that is work handed to the "
        f"second level, and ONLY this number grows with merging")
    if res["empty_objects"]:
        log(f"WARNING: {res['empty_objects']} truth objects without ink — "
            f"a bench defect, counted neither as intact nor as torn")


# ------------------------------------------------- the spoiling battery
# A number is not to be trusted until shown able to fall. Each probe spoils ONE
# thing and names what is due to move. THREE-SIDED, as in `metrics.mutations()`,
# and two sides of three were missing here: only the MODEL OUTPUT was spoiled.
# Not the TRUTH (a metric indifferent to truth measures one of its own inputs),
# not OUR OWN THRESHOLDS (a dead one prints beside a live one, looking a ruler).
