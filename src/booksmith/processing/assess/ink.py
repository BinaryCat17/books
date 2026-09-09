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
bench/real-tables20/tables20.pdf with the box geometry unchanged: ink under artefact
24.83% (144 dpi) -> 25.63% (300) -> 25.99% (600); ink under boxes 99.26 ->
99.25 -> 99.24%. Small, real and one-directional, so dpi is printed on the
first line: without it two numbers from two runs are incomparable.

TRUTH IS NOT REQUIRED. Without it the same is counted over the ink of the WHOLE
page: how much stayed outside every box, i.e. what will vanish from the HTML.
That works on any book nobody has annotated yet.
"""
import os
import statistics

import numpy as np

from booksmith.core import policy
from booksmith.core import raster
from booksmith.core import page
from booksmith.core.errors import Unmeasurable
# THE SPREAD-CUTTER'S OWN NUMBERS, imported and not copied. `extract/djvu.py`
# measured them over 568 spreads of two books and pays for them in false
# vetoes; a second set here would be a second copy free to drift, which is
# what `tools/figures.py` counts. Stdlib-only module, 13 ms to import.
from booksmith.processing.extract.djvu import (
    GUTTER_BAND, MIN_SPREAD_RATIO, RULE_RUN)

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
# WHERE A BINDING CAN BE. Outside the middle three fifths of the width, or --
# on a sheet still wide enough to be an uncut spread -- in the middle fifth
# where `djvu` would have cut it. This number was already here, as the bare
# literal `0.2` inside the report's own sentence "in the middle of the sheet
# (0.2..0.8 of the width)", declared nowhere and reaching no `params`.
MID = 0.20
# A binding shadow is a STRIP. Wider than this share of the sheet and it is
# something else, whatever its position: the widest true shadow measured runs
# to 0.067 of the width, the narrowest positional run it rejects to 0.106.
JUNK_WIDTH = 0.10


# The page raster does not change between runs, and the battery makes THIRTY-ONE
# passes over the book (32 `measure` calls, 31 of them reading the raster).
# Counted on bench/hard36: 828 renders with no cache over 36 pages, exactly
# 23 x 36 -- that was 23 passes, and the number is a count of probes, so it
# moves whenever one is added. It is measured, not maintained: ask the battery.
#
# THE JUNK MASK RIDES THE SAME ARGUMENT and was recomputed on every one of the
# thirty-one. It is a function of the raster and six constants -- the property
# no model can move, which is what makes it cacheable -- and it cost 63 % on
# top of a warm pass over bench/hard (6.9 s against 4.2 s), 41 % of a warm
# pass over the golden bench. Cached on the same page, those 32 calls become
# 12 distinct masks: the twelve threshold combinations the battery actually
# exercises, and hits for the rest.
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
    sheet, 514 of them in `bench/annopage-lite/detect/dots-ocr/pages`, the `dots.ocr`
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


_JUNK_CACHE: dict = {}


def _junk_of(pdf, i, dpi, ink):
    """`_junk_columns`, cached on the same page the ink mask is cached on.

    IT IS A FUNCTION OF THE RASTER AND SIX CONSTANTS, which is the property
    the whole design rests on -- no model can move it -- and it is exactly
    what makes it cacheable. Recomputed, it cost 41 % of a warm pass over the
    golden bench and added 84 % to it, because the battery makes thirty-one
    passes over a book and every one of them rebuilt the same answer from a
    raster this module goes to great length to keep.

    THE KEY CARRIES THE CONSTANTS, for the reason the ink key carries `INK`:
    the battery moves all six to check they are alive, and a mask returned
    from a key that ignored them would make a live threshold look dead and
    the probe would blame the metric for nothing. The value is one boolean
    per column -- a couple of kilobytes against the megabytes of the ink mask
    it rides beside -- so it is not capped and not evicted.
    """
    key = (pdf, i, int(dpi), INK, GUTTER, MID, JUNK_WIDTH,
           RULE_RUN, GUTTER_BAND, MIN_SPREAD_RATIO, EDGE)
    hit = _JUNK_CACHE.get(key)
    if hit is None:
        hit = _JUNK_CACHE[key] = _junk_columns(ink)
    return hit


def _junk_columns(ink):
    """The pixel columns that are BINDING SHADOW or SCAN EDGE, not content.

    Junk ink is not a rounding correction: on "Технология огнеупоров" the
    right-hand five per cent of the sheet holds 7.68 % of all the book's ink
    against 0.26 % on the left, a thirtyfold asymmetry, and discarding it
    takes the reported loss from 20.8 % to 6.4 %. Left in, it is counted as
    information the model failed to deliver, and a box laid on it is counted
    as a delivery -- 261 fake boxes lift "ink under boxes" 85.7 % -> 96.2 %
    having found nothing.

    THE RULE IS POSITIONAL, NEVER "THIS COLUMN IS DARK", and that is the
    whole difference between a measurement and a laundered win. On
    `bench/annopage` 1399 of 2320 solid dark columns stand MID-SHEET and are
    dark plates and photographs -- real content. Both rules over all 600
    golden pages, one pass, the code as it stands:

        positional (this one)  discards  3.620 %  eats 0.1183 % of the
                                                  annotated object ink
        naive "dark column"    discards 46.254 %  eats 49.039 %

    ONE FIGURE, MEASURED ONCE. An earlier edition of this paragraph carried
    "4.8 % and 0.043 %" and the commit that shipped it carried "1.65 % and
    0.000 %" from a 120-page sample -- three numbers for one quantity, none
    of them checkable, because none of the new scalars is in any tracked
    result and so none reaches METRICS.md. Both were also measured before
    the veto was narrowed to the band, which raised the discard.

    Three tests, and a run must pass all three:

      WHERE. In the outer fifths, where a binding is after a spread has been
      cut -- and the cut leaves the shadow INSET from the new edge, up to
      5 % of the width in, which is why `EDGE` alone cannot see it and why
      this is not an edge band. On a sheet still wider than tall, the middle
      fifth counts too: that is an uncut spread, and `djvu` would cut it
      there. Both use the spread-cutter's own constants.

      HOW WIDE. A shadow is a strip; past `JUNK_WIDTH` of the sheet it is
      something else wherever it lies.

      WHETHER SOMETHING CROSSES IT. A full-height table rule satisfies both
      tests above and is content. So: in a row that is black clear across the
      band, is there a black run spanning `RULE_RUN` of the whole width? Then
      the band is a rule and is kept. `djvu` measured that threshold over 568
      spreads -- 0.376 at the one real table crossing a gutter, 0.000 at the
      other 567.

    The mask is a function of the RASTER and our constants alone: it never
    sees a box, so no model can move it. That is what makes discarding a
    property of the ruler rather than a repair of the model.
    """
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
    for a, b in zip(starts, ends):
        c = (a + b) / 2.0 / w
        if not (c < MID or c > 1 - MID
                or (spread and abs(c - 0.5) <= GUTTER_BAND / 2)):
            continue
        if (b - a) / w > JUNK_WIDTH:
            continue
        # THE VETO AT ITS ENDS, and it must answer there rather than switch
        # itself off. A span of zero means "any run at all is a rule", so
        # nothing is junk; a span past the sheet means no run can be one, so
        # the position and width tests decide alone. Written as `0 < span`
        # the first case SKIPPED the veto and made MORE junk instead of
        # none -- the probe for it read 10.53 % where it demanded 0, which
        # is how the battery earns its keep on the code that feeds it.
        if span <= 0:
            continue
        full = body[:, a:b].all(axis=1)
        # THE RUN MUST CROSS THIS BAND, not merely exist on the page. Asked
        # of the whole row, the veto was a PAGE-LEVEL switch: one table rule
        # anywhere on a sheet spared every band on it. Measured over the 378
        # pages of the book the mask is for, 28 of the 29 vetoed bands -- 97
        # per cent -- were spared by a run that never touched them, keeping
        # 0.652 % of the book's ink, a fifteenth of everything the mask
        # discards. `djvu` asks the narrow question (`_run_len` through the
        # candidate column) and this asked the wide one.
        #
        # A window starting at `i` covers `[i, i+span)` and meets `[a, b)`
        # when `i < b` and `i + span > a`.
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
    areas = []            # box area / page area, one per on-sheet box
    res = {"page_count": 0, "truth_pages": len(T), "dpi": [],
           "box_count": 0, "median_box_area": None,
           "ink_as_text": 0, "ink_as_picture": 0,
           # CLEAN BOTH SIDES OR NEITHER. Cleaning the
           # denominator alone gives 104.4 % under the attack
           # this exists to stop -- the instrument not merely
           # gamed but broken -- and pays the attacker nine and
           # a half points where cleaning both pays exactly zero.
           "ink_junk": 0, "ink_clean": 0, "clean_under_boxes": 0,
           "blocks_with_content": 0,
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
        # WHERE THE INK ENDS UP, by the builder's own rule and not a second
        # copy of it: `assemble/html.py` emits a crop when
        # `role == "artifact" or not b.content` and a paragraph otherwise, so
        # that is the line asked here. The question this answers is the one
        # the project is for -- how much of the book survives, and as WHAT --
        # and it was answerable from these masks all along while the report
        # said only "ink under boxes".
        #
        # A PIXEL IS COUNTED ONCE, and a picture wins the tie. Boxes overlap
        # for real (`text_inside_non_artifact_box` runs to 1935 on one book),
        # and a crop ships whole whatever lies over it, so ink under both a
        # crop and a paragraph is counted as leaving in the crop. The split
        # is therefore exhaustive against `ink_total` and never sums past it.
        pic = _mask(ink.shape, [b["box"] for b in p["blocks"]
                                if policy.role(b["label"]) == "artifact"
                                or not (b.get("content") or "").strip()])
        txt = _mask(ink.shape, [b["box"] for b in p["blocks"]
                                if policy.role(b["label"]) != "artifact"
                                and (b.get("content") or "").strip()]) & ~pic
        res["ink_as_picture"] += int((ink & pic).sum())
        res["ink_as_text"] += int((ink & txt).sum())
        res["blocks_with_content"] += sum(
            1 for b in p["blocks"] if (b.get("content") or "").strip())
        # Who arrived in which box: key is the artefact box, value is how many
        # truth objects it carries whole. Hence "arrived with company", the one
        # number of this instrument that GROWS with merging.
        riders = {}
        dpis.add(int(p["dpi"]))
        res["page_count"] += 1
        res["ink_total"] += int(ink.sum())
        junk = _junk_of(pdf, i, p["dpi"], ink)
        # COUNTED OVER THE JUNK COLUMNS ALONE, never by building a second
        # sheet. `ink.copy()` doubled the page mask to subtract a band that
        # is at most a tenth of it by construction, and this metric already
        # holds half a gigabyte of cached masks: the copy was paid on every
        # page of every pass to answer a question about a narrow strip.
        whole = int(ink.sum())
        if junk.any():
            j = int(ink[:, junk].sum())
            res["clean_under_boxes"] += (int((ink & both).sum())
                                         - int((ink[:, junk]
                                                & both[:, junk]).sum()))
        else:
            j = 0
            res["clean_under_boxes"] += int((ink & both).sum())
        res["ink_junk"] += j
        res["ink_clean"] += whole - j
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
        # HOW BIG A BOX IS, AS A SHARE OF ITS OWN PAGE. `area_under_boxes`
        # exists to catch the model that boxes everything, and it is beaten
        # from the other side: a detector that TRACES the ink with many tiny
        # boxes takes 100% of it at 43.9% of the sheet -- LOWER area than an
        # honest run's 61.4%, so the guard reads it as better than honest.
        # The two degeneracies are geometric opposites and no single number
        # separates both; this is the other half. Measured over 25 honest
        # runs on four books, the median box is 0.7%-2.6% of its page, and
        # every ink-tracing cheat falls 5x to 4234x below that band while the
        # whole-sheet box sits at 1.0 -- so NEITHER end is good and it is a
        # guard, never a rank. Per PAGE and not per sheet-size, because the
        # golden bench mixes raster sizes.
        for sl in (_clip(ink.shape, b) for b in arte + rest):
            if sl is None:      # wholly off the sheet: no area to speak of
                continue
            ys, xs = sl
            areas.append(float((ys.stop - ys.start) * (xs.stop - xs.start))
                         / ink.size)
        # EVERY BOX THE MODEL DREW, including the ones off the sheet: this is
        # the level-two bill, one crop and one paid request each.
        res["box_count"] += len(arte) + len(rest)
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
    # THE MEDIAN, NOT THE LIST. Eight thousand box areas per run would ride
    # into `detail` and from there into `results/*.json`, fifty-four times,
    # to answer one question. The median is what separates the honest band
    # from a tracing cheat; the mean would not, since one full-sheet box
    # among many tiny ones drags it back into the band.
    res["median_box_area"] = statistics.median(areas) if areas else None
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
    # AND THE SAME WITH THE BINDING DISCARDED. `books fitness` is the mode
    # real scans are measured in -- this module's own header says so -- and
    # it printed the raw loss alone, so the one number the junk mask exists
    # to correct was the one number a real scan's operator saw. On the book
    # the mask was written for that read "20.8 % will vanish" where the ink
    # that is ink says 6.4 %.
    clean = res.get("ink_clean") or 0
    if clean and res.get("ink_junk"):
        log(f"of that ink {res['ink_junk'] / ink * 100:.1f}% is binding "
            f"shadow and scan edge, not information; over the ink that IS "
            f"ink, under boxes {res['clean_under_boxes'] / clean * 100:.1f}%, "
            f"outside every box "
            f"{(1 - res['clean_under_boxes'] / clean) * 100:.1f}%")
    # WHERE IT LEAVES, when the run has read something. A detection run has
    # no content anywhere, so every block would leave as a picture by the
    # builder's rule and the split would state a fact about the run wearing
    # the shape of a fact about the model.
    if res.get("blocks_with_content"):
        log(f"of the sheet's ink {res['ink_as_text'] / ink * 100:.1f}% "
            f"leaves the book as text and "
            f"{res['ink_as_picture'] / ink * 100:.1f}% as a picture")
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
