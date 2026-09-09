"""The FITNESS instrument: how it can be won without finding anything.

WHY THIS FILE EXISTS. `books fitness` chose the detector and judged the docling
pipeline, and `grep fitness tests/` found NOT ONE line: the only check on it
was its own battery, which corrupted the model's output and neither the truth
nor its own thresholds.

Every defect below was reproduced, not supposed:

  * a box off the top-left corner covered two thirds of the sheet (a negative
    slice end in numpy counts FROM THE END);
  * a pixel under an artefact box and a text box at once counted TWICE, and the
    doubled markup rewrote the expensive "lost" into the cheap "left as text".
    Full run: `bench/annopage` 90 -> 86, `bench/hard` 44 -> 42 -- six records,
    four DISTINCT objects (hard is built from the same books), one real trouble
    among them: p. 94 `table`, 14% of its ink in the open. Seven SMALL benches
    gave zero, and by that zero it was called harmless -- exactly what a sample
    cannot find;
  * an empty raster printed "outside every box 100.0% -- this is what will
    vanish from the HTML": a zero from misunderstanding, dressed as a measure;
  * "no truth supplied" printed when truth was supplied and held no artefacts:
    two different zeros in one line;
  * of FIVE thresholds the report declared one, the battery checked two, and
    dpi -- the unit of everything counted here -- nobody;
  * the merging-blindness line stood AFTER the returns by truth, so the
    truthless mode, the one real scans are measured in, never printed it;
  * raster memory saved nothing on the very bench it was raised for, twice: a
    cap in pages with a full clear, then a cap in bytes evicting the oldest.

The report is checked apart from the numbers because the battery looks at
NUMBERS and can say nothing about printing. Page shapes here are REAL: the
memory check written on toy 64x64 pages was green on code that saved nothing --
a byte cap never binds on such pages.
"""
import os
import tempfile

import pytest

import numpy as np
import pymupdf

from booksmith.core.config import ROOT

from booksmith.datasets.bench import Run
from booksmith.datasets.metrics import base
from booksmith.datasets.metrics.probes.fitness import probes
from booksmith.processing.assess import ink as fitness


# --- what we measure with ---------------------------------------------------
# The page is built here, whole: 200x200 pt, the ink a rectangle with known
# edges. No ONNX, no weights, no bench on disk; every expected number comes
# from geometry, not off a run.

def _book(rects, out):
    doc = pymupdf.open()
    pg = doc.new_page(width=200, height=200)
    for r in rects:
        pg.draw_rect(pymupdf.Rect(*r), color=(0, 0, 0), fill=(0, 0, 0))
    pdf = os.path.join(out, "p.pdf")
    doc.save(pdf)
    doc.close()
    return pdf


def _pages(blocks, out, name):
    d = os.path.join(out, name)
    os.makedirs(d, exist_ok=True)
    p = {"index": 0, "width": 200, "height": 200, "dpi": 72.0,
         "blocks": [{"block_id": j, "box": list(b), "label": lab, "score": None,
                     "order": j, "content": None, "kind": "none"}
                    for j, (b, lab) in enumerate(blocks)]}
    import json
    with open(os.path.join(d, "0000.json"), "w", encoding="utf-8") as f:
        json.dump(p, f, ensure_ascii=False)
    return d


def _said(res):
    out = []
    fitness.report(res, log=out.append)
    return "\n".join(out)


# --- slicing boxes ----------------------------------------------------------

def test_box_off_the_sheet_covers_nothing():
    """A box wholly off the sheet covers not one pixel.

    The old slice `m[max(0, int(y0)):int(y1) + 1]` counted a negative `y1` FROM
    THE END of the array: the box [-40, -40, -20, -20] covered 6561 pixels of
    10000. The metric could be won with rubbish.
    """
    assert int(fitness._mask((100, 100), [[-40, -40, -20, -20]]).sum()) == 0
    assert fitness._clip((100, 100), [-40, -40, -20, -20]) is None


def test_box_hanging_over_the_edge_is_cut_by_the_sheet():
    """And one hanging half off covers exactly its own part of the sheet."""
    m = fitness._mask((100, 100), [[-10, -10, 9, 9]])
    assert int(m.sum()) == 100, int(m.sum())          # 10x10 in the corner
    m = fitness._mask((100, 100), [[90, 90, 500, 500]])
    assert int(m.sum()) == 100, int(m.sum())


# --- one pixel counted twice ------------------------------------------------

def test_pixel_under_two_boxes_counts_once():
    """An object with half its ink under nothing has not "left as text".

    Doubled markup -- one area given to an artefact and to text at once -- is
    no invention: raw docling-heron has 4435 doubled pairs. `t_kept + kept`
    counted the shared pixel twice, the sum passed the threshold, and the
    object was diagnosed "not lost, fixable by a label".
    """
    with tempfile.TemporaryDirectory() as tmp:
        pdf = _book([(20, 20, 120, 120)], tmp)
        truth = _pages([((20, 20, 120, 120), "table")], tmp, "truth")
        # the artefact box and the text box are THE SAME left half of the
        # object
        det = _pages([((20, 20, 70, 120), "table"),
                      ((20, 20, 70, 120), "text")], tmp, "det")
        r = fitness.measure(pdf, det, truth)
        assert r["torn"] == 1, r
        assert r["left_as_text"] == 0, r
        # ...and when the text box really holds the rest, the diagnosis is
        # right
        det2 = _pages([((20, 20, 70, 120), "table"),
                       ((60, 20, 120, 120), "text")], tmp, "det2")
        assert fitness.measure(pdf, det2, truth)["left_as_text"] == 1


# --- zeros ------------------------------------------------------------------

def test_blank_page_is_not_a_total_loss():
    """An empty raster is "nothing to measure", not "the book is lost"."""
    with tempfile.TemporaryDirectory() as tmp:
        pdf = _book([], tmp)
        det = _pages([((10, 10, 50, 50), "table")], tmp, "det")
        said = _said(fitness.measure(pdf, det))
        assert "nothing to measure" in said, said
        assert "vanish from the HTML" not in said, said


def test_truth_without_artefacts_is_not_a_missing_truth():
    """Truth supplied, no artefacts in it -- that is ANOTHER zero."""
    with tempfile.TemporaryDirectory() as tmp:
        pdf = _book([(20, 20, 120, 120)], tmp)
        det = _pages([((20, 20, 120, 120), "text")], tmp, "det")
        truth = _pages([((20, 20, 120, 120), "text")], tmp, "truth")
        with_truth = _said(fitness.measure(pdf, det, truth))
        without = _said(fitness.measure(pdf, det))
        assert "truth supplied" in with_truth, with_truth
        assert "truth NOT supplied" in without, without
        assert with_truth != without


def test_object_without_ink_is_a_bench_defect_not_a_score():
    """A truth object without ink counts as neither "intact" nor "torn"."""
    with tempfile.TemporaryDirectory() as tmp:
        pdf = _book([(20, 20, 120, 120)], tmp)
        det = _pages([((20, 20, 120, 120), "table")], tmp, "det")
        truth = _pages([((20, 20, 120, 120), "table"),
                        ((150, 150, 190, 190), "table")], tmp, "truth")
        r = fitness.measure(pdf, det, truth)
        assert r["objects"] == 1 and r["empty_objects"] == 1, r
        assert r["intact"] + r["almost_intact"] + r["bitten"] + r["torn"] == 1, r
        assert "a bench defect" in _said(r)


def test_page_the_model_did_not_mark_is_loud():
    """A silent model is a refusal, not "no ink lost"."""
    with tempfile.TemporaryDirectory() as tmp:
        pdf = _book([(20, 20, 120, 120)], tmp)
        truth = _pages([((20, 20, 120, 120), "table")], tmp, "truth")
        det = os.path.join(tmp, "det")
        os.makedirs(det)
        import json
        with open(os.path.join(det, "0001.json"), "w", encoding="utf-8") as f:
            json.dump({"index": 1, "width": 200, "height": 200, "dpi": 72.0,
                       "blocks": []}, f)
        try:
            fitness.measure(pdf, det, truth)
        except Exception as e:
            assert "marked up no page" in str(e), e
        else:
            assert False, "the model's silence passed in silence"


# --- the ruler --------------------------------------------------------------

def test_report_declares_the_whole_ruler():
    """All five thresholds and the dpi in the report, not just "intact".

    A number without a declared ruler already cost an irreproducible "extra
    jumps 7.0 -> 1.3". The unit is the raster pixel, so the number rides on
    `PAGE_DPI`: the same boxes on bench/real-tables20/tables20.pdf give "ink under
    artefacts" 24.83% at 144 dpi and 25.99% at 600.
    """
    with tempfile.TemporaryDirectory() as tmp:
        pdf = _book([(20, 20, 120, 120)], tmp)
        det = _pages([((20, 20, 120, 120), "table")], tmp, "det")
        said = _said(fitness.measure(pdf, det))
        assert "72 dpi" in said, said
        # FIVE THRESHOLDS, AND EXACT COMPARISON. Four of the five were asked
        # for (`EDGE` printed only on losses, so its line could go without
        # red), and asked as a substring: `BITTEN = 0.8` passed on "0.80" by
        # accident, and `INK = 160` would pass on "1600".
        import re
        nums = re.findall(r"\d+(?:\.\d+)?", said)
        for v in (fitness.INK, fitness.WHOLE, fitness.ALMOST, fitness.BITTEN):
            want = f"{v:.2f}" if isinstance(v, float) else str(v)
            assert want in nums, (want, nums)
        assert f"{fitness.EDGE * 100:.0f}" in nums, (fitness.EDGE, nums)
        assert "edge band" in said, said


def test_report_says_out_loud_that_it_is_blind_to_merging():
    """The instrument must name what it cannot see, and name the neighbour.

    Without truth too: the line stood after both `return`s by truth, and `books
    fitness book.pdf --detect …` is the mode real scans are measured in.
    """
    with tempfile.TemporaryDirectory() as tmp:
        pdf = _book([(20, 20, 120, 120)], tmp)
        det = _pages([((20, 20, 120, 120), "table")], tmp, "det")
        truth = _pages([((20, 20, 120, 120), "table")], tmp, "truth")
        for res in (fitness.measure(pdf, det, truth), fitness.measure(pdf, det),
                    fitness.measure(_book([], tmp), det)):
            said = _said(res)
            assert "merging" in said.lower() and "books score" in said, said


def test_the_number_that_grows_when_boxes_merge():
    """The one number that GROWS when boxes merge: "arrived with company".

    The rest improve (bench/hard36: intact 365 -> 385, torn 28 -> 13, object
    ink 94.8% -> 96.1%), and by them alone merging looks profitable. This one
    went 309 -> 385 there.
    """
    with tempfile.TemporaryDirectory() as tmp:
        pdf = _book([(20, 20, 80, 80), (110, 20, 170, 80)], tmp)
        truth = _pages([((20, 20, 80, 80), "table"),
                        ((110, 20, 170, 80), "table")], tmp, "truth")
        apart = _pages([((20, 20, 80, 80), "table"),
                        ((110, 20, 170, 80), "table")], tmp, "apart")
        one = _pages([((20, 20, 170, 80), "table")], tmp, "one")
        a = fitness.measure(pdf, apart, truth)
        b = fitness.measure(pdf, one, truth)
        assert a["intact"] == b["intact"] == 2, (a, b)          # blind numbers keep quiet
        assert a["in_one_box"] == b["in_one_box"] == 2
        assert a["arrived_with_company"] == 0, a         # and this one speaks
        assert b["arrived_with_company"] == 2, b
        assert a["boxes_with_many_objects"] == 0
        assert b["boxes_with_many_objects"] == 1
        assert "arrived with company 2" in _said(b)


def test_the_ink_threshold_has_one_meaning_in_both_homes():
    """`fitness.INK` and `synth.INK` are one number in two homes.

    The bench marks its truth by this threshold, the metric measures the model
    by it; let them drift and "94.8% of ink arrived" is not about the ink the
    truth is marked by. Import would join them (cv2 in `synth` loads INSIDE
    functions, `import booksmith.synth` costs 2 ms), but the metric must not
    depend on whoever draws the bench.
    """
    from booksmith.datasets.make import synth
    assert fitness.INK == synth.INK, (fitness.INK, synth.INK)


def test_merging_two_objects_into_one_box_does_not_lower_the_numbers():
    """Blindness fixed by measurement: merging counts here as an IMPROVEMENT.

    Not that it is right, but that it is so. Let this drift from the report's
    own text and one of the two lies.
    """
    with tempfile.TemporaryDirectory() as tmp:
        pdf = _book([(20, 20, 80, 80), (110, 20, 170, 80)], tmp)
        truth = _pages([((20, 20, 80, 80), "table"),
                        ((110, 20, 170, 80), "table")], tmp, "truth")
        # both tables boxed apart, but the right one has its edge cut off
        apart = _pages([((20, 20, 80, 80), "table"),
                        ((110, 20, 150, 80), "table")], tmp, "apart")
        one = _pages([((20, 20, 170, 80), "table")], tmp, "one")
        a = fitness.measure(pdf, apart, truth)
        b = fitness.measure(pdf, one, truth)
        assert a["intact"] == 1 and a["torn"] == 1, a
        assert b["intact"] == 2 and b["torn"] == 0, b
        assert b["in_one_box"] > a["in_one_box"]


# --- raster memory ----------------------------------------------------------

# A GOLDEN BENCH page, not a toy: 1700x2200 is 3.57 MiB as a boolean mask and
# 457 KiB packed, the order of a real one (the average `bench/annopage` page at
# 144 dpi: 5.00 MiB and 640 KiB). On toy 64x64 the byte cap NEVER binds.
_PAGE = (2200, 1700)


def _memory_probe(pages, cap, passes):
    """How many renders `passes` sequential walks over the book cost."""
    rendered = {"n": 0}
    real, cap0 = fitness._ink, fitness._INK_CACHE_MAX_BYTES

    def spy(page, dpi):
        rendered["n"] += 1
        return np.zeros(_PAGE, bool)

    class Doc:
        def __getitem__(self, i):
            return None

    fitness._ink = spy
    fitness._INK_CACHE_MAX_BYTES = cap
    fitness._INK_CACHE.clear()
    fitness._INK_CACHE_BYTES = 0
    try:
        for _ in range(passes):
            for i in range(pages):
                fitness._ink_of("book.pdf", Doc(), i, 144)
        return rendered["n"]
    finally:
        fitness._ink = real
        fitness._INK_CACHE_MAX_BYTES = cap0
        fitness._INK_CACHE.clear()
        fitness._INK_CACHE_BYTES = 0


def test_ink_memory_does_not_thrash_on_a_book_bigger_than_the_cap():
    """A book bigger than the cap is half counted from memory, not wholly anew.

    Eviction under a SEQUENTIAL walk misses by construction: what is evicted by
    the end of a pass is wanted at the start of the next. Both earlier versions
    -- 64 pages with a full clear, and a byte cap evicting the oldest -- cost
    as many renders as no memory at all. Simulated on a REAL access trace (23
    passes off the battery itself, with its ink thresholds) and real
    golden-bench page shapes, 600 pages, cap 512 MiB: no memory 13800 renders,
    eviction 2400, holding what was gathered 1800 -- the ideal (three passes:
    thresholds 160, 0 and 256 give three masks).
    """
    page = (_PAGE[0] * _PAGE[1] + 7) // 8
    held, pages, passes = 4, 10, 3
    n = _memory_probe(pages, held * page, passes)
    # the first pass pays for everything, then only what did not fit
    assert n == pages + (passes - 1) * (pages - held), n
    assert n < pages * passes, "the cache saved nothing -- that is a miss"
    assert n > pages, "the bench is chosen so the ceiling does not bind"


def test_ink_memory_pays_nothing_twice_when_the_book_fits():
    """A book that fits -- every page rendered exactly once."""
    page = (_PAGE[0] * _PAGE[1] + 7) // 8
    assert _memory_probe(10, 10 * page, 5) == 10


def test_ink_memory_makes_room_for_the_next_book():
    """The previous book gives way to the next; our own pages do not.

    `_INK_CACHE` is a module global, and a process measuring more than one book
    (eight benches in a row is ordinary) got this: book A fills the cap, book B
    gets NOT ONE BYTE. Simulated on the real trace and real page shapes, cap
    512 MiB, two books of 600 pages: holding what was gathered 15600 renders,
    evicting in order 4200, evicting OTHER books 3600 -- the ideal. Inside a
    book eviction stays forbidden: the walk is sequential and what is evicted
    is wanted on the next pass (one book: 1800 against 2400).
    """
    page = (_PAGE[0] * _PAGE[1] + 7) // 8
    real, cap0 = fitness._ink, fitness._INK_CACHE_MAX_BYTES
    rendered = {"n": 0}

    def spy(pg, dpi):
        rendered["n"] += 1
        return np.zeros(_PAGE, bool)

    class Doc:
        def __getitem__(self, i):
            return None

    fitness._ink = spy
    fitness._INK_CACHE_MAX_BYTES = 4 * page      # room for exactly one book
    fitness._INK_CACHE.clear()
    fitness._INK_CACHE_BYTES = 0
    try:
        for book in ("a.pdf", "b.pdf"):
            for _ in range(3):
                for i in range(4):
                    fitness._ink_of(book, Doc(), i, 144)
        # each book rendered once: the second evicted the first, but INSIDE a
        # book no page was read twice
        assert rendered["n"] == 8, rendered["n"]
    finally:
        fitness._ink = real
        fitness._INK_CACHE_MAX_BYTES = cap0
        fitness._INK_CACHE.clear()
        fitness._INK_CACHE_BYTES = 0


def test_the_cap_holds_the_bench_it_was_raised_for():
    """The cap must hold the golden bench WHOLE -- else it gives nothing.

    The number was derived from this bench, and the link must stay checkable:
    here stood "460 MB boolean and 58 MB packed, they fit whole" -- wrong by
    six and a half times, and they did not fit.
    """
    # `truth/` IS READ, NOT `detect/pages`: the second is under `.gitignore`
    # (`bench/*/detect/pages/`), so on a fresh clone the check was skipped
    # silently -- and a skip counts under mutation as a check that did NOT go
    # red, so "cap lowered below the golden bench" printed NOT CAUGHT and
    # `--selfcheck` returned 1. The shapes are in `truth/` as well: the same
    # 600 files, in git, the same sum.
    import json
    d = os.path.join(ROOT, "bench", "annopage", "truth")
    if not os.path.isdir(d):
        pytest.skip("no bench/annopage/truth: the golden bench is not built")
    packed = 0
    for name in sorted(os.listdir(d)):
        if not name.endswith(".json") or name == "run.json":
            continue
        with open(os.path.join(d, name), encoding="utf-8") as f:
            p = json.load(f)
        packed += (p["height"] * p["width"] + 7) // 8
    assert packed <= fitness._INK_CACHE_MAX_BYTES, (
        f"the bench, {packed / 2 ** 20:.0f} MiB packed, does not fit the "
        f"ceiling of {fitness._INK_CACHE_MAX_BYTES / 2 ** 20:.0f} MiB")


def test_ink_threshold_is_part_of_the_memory_key():
    """Move the threshold, recount the mask -- else a live one looks dead."""
    rendered = {"n": 0}
    real = fitness._ink

    def spy(page, dpi):
        rendered["n"] += 1
        return np.zeros((8, 8), bool)

    class Doc:
        def __getitem__(self, i):
            return None

    fitness._ink = spy
    old = fitness.INK
    try:
        fitness._INK_CACHE.clear()
        fitness._INK_CACHE_BYTES = 0
        fitness._ink_of("book.pdf", Doc(), 0, 144)
        fitness._ink_of("book.pdf", Doc(), 0, 144)
        assert rendered["n"] == 1
        fitness.INK = old + 1
        fitness._ink_of("book.pdf", Doc(), 0, 144)
        assert rendered["n"] == 2, rendered["n"]
    finally:
        fitness.INK = old
        fitness._ink = real
        fitness._INK_CACHE.clear()
        fitness._INK_CACHE_BYTES = 0


# --- the probes -------------------------------------------------------------

class _Bench:
    """A bench of two directories: what the probes ask for, and no more."""

    def __init__(self, pdf, truth=""):
        self.pdf = pdf
        self.truth_dir = truth
        self.name = "toy"


def _probes(pdf, det, truth=""):
    """Run every probe of the ink metric over a hand-built book."""
    out = []
    ps = probes(_Bench(pdf, truth), Run.bare(det))
    seen, mute, bad = base.run_probes(ps, log=out.append)
    return seen, mute, bad, out


def test_the_probes_count_what_they_could_not_measure():
    """Saying "uncaught 0" over five unmeasured probes is a word, not a number.

    Without truth more probes have nothing to measure, and the count must say
    how many, or the battery looks green having measured a part of itself. The
    ARITHMETIC is checked, not a literal: as many probes as print "no data" must
    stand in the silent count.
    """
    with tempfile.TemporaryDirectory() as tmp:
        pdf = _book([(20, 20, 120, 120)], tmp)
        det = _pages([((20, 20, 120, 120), "table")], tmp, "det")
        truth = _pages([((20, 20, 120, 120), "table")], tmp, "truth")
        seen, mute, bad, out = _probes(pdf, det, truth)
        assert bad == 0, out
        assert mute == sum("no data" in l for l in out), (mute, out)
        seen2, mute2, bad2, out2 = _probes(pdf, det)
        assert bad2 == 0, out2
        assert mute2 == sum("no data" in l for l in out2), (mute2, out2)
        # WITHOUT TRUTH MORE PROBES GO SILENT, AND THE COUNT SAYS HOW MANY.
        # TWICE AS MANY, not merely one more: direction alone is satisfied by a
        # single probe going quiet, and the regression to catch is a dozen
        # truth-gated probes answering "pass" without truth instead of "no
        # data". The FACTOR is the stable form -- growing the truth-free half,
        # which is the work, cannot reduce the number of probes that NEED truth,
        # while "under half the probes measured" broke the day the truth-free
        # half grew.
        assert mute2 >= mute * 2, (mute, mute2)
        assert seen2 - mute2 < seen - mute, (seen, mute, seen2, mute2)


def test_the_probes_corrupt_all_three_sides():
    """The model's output, the TRUTH and OUR OWN thresholds -- each apart.

    Moved together they hide the inert one: a metric indifferent to truth
    measures one input, and a dead threshold prints beside a live one.
    """
    with tempfile.TemporaryDirectory() as tmp:
        pdf = _book([(20, 20, 120, 120)], tmp)
        det = _pages([((20, 20, 120, 120), "table")], tmp, "det")
        truth = _pages([((20, 20, 120, 120), "table")], tmp, "truth")
        said = "\n".join(_probes(pdf, det, truth)[3])
        assert "truth shifted" in said, said          # the third side
        assert "ink threshold" in said, said          # the second
        assert "moved off the top-left corner" in said, said
        assert "merged into one" in said, said
        assert "handed out as a text one too" in said, said


# --- the junk mask: the three tests, each on a raster built to isolate it ---

def _sheet(w, h, bands=(), rules=()):
    """A raster with vertical `bands` (x0, x1) and horizontal `rules`.

    Built as an array rather than drawn into a PDF: `_junk_columns` takes the
    ink mask, so the page is the mask, and a check that goes through pymupdf
    would be asking about the renderer as well.
    """
    import numpy as np
    im = np.zeros((h, w), bool)
    for x0, x1 in bands:
        im[:, x0:x1] = True
    for y, a, b in rules:
        im[y:y + 2, a:b] = True
    return im


def test_a_binding_shadow_is_junk_and_a_mid_sheet_plate_is_not():
    """THE POSITION TEST, WHICH NOTHING GUARDED.

    The rule this commit exists to reject is "a dark column is junk", and it
    was measured on the golden bench as discarding 50.71 % of the ink and
    eating 49.815 % of the annotated object ink -- half the bench's plates,
    because 1399 of its 2320 dark columns stand mid-sheet. Inverting the gate
    in `_junk_columns` turns the shipped rule into exactly that one, and the
    whole suite stayed green: `bench/slovar` carries no dark column at all,
    so six of the ten junk probes read "no data" and the pinned battery
    output recorded their silence as if it were agreement.
    """
    from booksmith.processing.assess import ink
    w, h = 1000, 1400
    shadow = ink._junk_columns(_sheet(w, h, bands=[(958, 986)]))
    assert shadow.any() and shadow[970], "a shadow at the binding is not junk"
    plate = ink._junk_columns(_sheet(w, h, bands=[(480, 508)]))
    assert not plate.any(), "a dark column mid-sheet was discarded as junk"


def test_a_band_too_wide_to_be_a_shadow_is_kept():
    """THE WIDTH TEST. A binding shadow is a strip; a dark region taking a
    fifth of the sheet at the edge is a plate bled to the margin."""
    from booksmith.processing.assess import ink
    w, h = 1000, 1400
    assert not ink._junk_columns(_sheet(w, h, bands=[(800, 999)])).any(), \
        "a band a fifth of the sheet wide was called a shadow"
    # ...and one just inside the cap, at the same place, still is one.
    assert ink._junk_columns(_sheet(w, h, bands=[(910, 999)])).any(), \
        "a strip within the width cap was not called a shadow"


def test_a_rule_crossing_the_band_keeps_it():
    """THE VETO. A full-height table rule sits where a binding sits and is
    content, so a black run crossing the band spares it -- and a run that
    does NOT cross it must not, or one rule anywhere on a page switches the
    binding correction off for the whole sheet."""
    from booksmith.processing.assess import ink
    w, h = 1000, 1400
    band = [(958, 986)]
    crossed = _sheet(w, h, bands=band, rules=[(700, 300, 999)])
    assert not ink._junk_columns(crossed).any(), \
        "a band with a table rule running through it was discarded"
    apart = _sheet(w, h, bands=band, rules=[(700, 10, 400)])
    assert ink._junk_columns(apart).any(), \
        "a rule that never touches the band vetoed it anyway"


def test_a_whitespace_answer_is_not_text_that_arrived():
    """`"   "` IS TRUTHY, and both the metric and the builder trusted it.

    `ink_as_text` is ranked "better higher", and every block given a single
    space scored 0.944970 on bench/slovar -- bit-identical to every block
    given real recognised text. The builder shares the predicate and shares
    the bug: `html.py` took the paragraph branch, wrote `<p></p>`, cut no
    crop, and the block's ink left the book while the number said it
    arrived. One line up in the same file `from_text` already asked
    `(b.content or "").strip()`; the two disagreed about what an answer is.
    """
    with tempfile.TemporaryDirectory() as tmp:
        pdf = _book([(20, 20, 120, 120)], tmp)
        real = _pages([((20, 20, 120, 120), "text")], tmp, "real")
        blank = _pages([((20, 20, 120, 120), "text")], tmp, "blank")
        import json
        for d, val in ((real, "recognised text"), (blank, "   ")):
            f = os.path.join(d, "0000.json")
            p = json.load(open(f, encoding="utf-8"))
            for b in p["blocks"]:
                b["content"] = val
            json.dump(p, open(f, "w", encoding="utf-8"))
        got = fitness.measure(pdf, real)["ink_as_text"]
        assert got > 0, "real text did not leave as text"
        assert fitness.measure(pdf, blank)["ink_as_text"] == 0, \
            "a whitespace answer counted as text that arrived"


def _junk_book(out):
    """A 200x200 sheet with a 7-pt binding strip at the right edge.

    THE INPUT THE JUNK PROBES NEVER HAD. They were written against
    `bench/slovar`, which is drawn with no binding at all, so six of them
    read `no data` and four more asserted `0 == 0`; the whole mask could be
    deleted with the battery green. The one book in the tree that does
    exercise them lives under `raw/` and `processed/`, and `git ls-files`
    returns nothing for either -- so on a fresh clone those probes had never
    run anywhere. Drawn here instead, where every clone has it.
    """
    return _book([(20, 20, 120, 120), (185, 0, 192, 200)], out)


def test_the_junk_mask_is_actually_applied_to_the_numbers():
    """`_junk_columns` may be right and reach nothing.

    Deleting the one line that applies it -- `clean[:, junk] = False` --
    leaves the mask correct, `ink_junk` zero, `clean` equal to `ink`, and
    the entire feature inert. Every junk probe is gated on `dark_columns` or
    `ink_junk`, the very quantities that line produces, so breaking it makes
    the probes fall silent rather than fail: `no data` where they should say
    NO. This asks the numbers instead of the mask.
    """
    with tempfile.TemporaryDirectory() as tmp:
        pdf = _junk_book(tmp)
        det = _pages([((20, 20, 120, 120), "table")], tmp, "det")
        r = fitness.measure(pdf, det)
        # TWO dark columns, and only one of them is junk: the plate at 0.35
        # of the width is dark over more than half the sheet exactly as the
        # strip at 0.94 is, and the naive rule this mask replaces would eat
        # it. So the fixture proves the position gate on the APPLIED path,
        # not only on `_junk_columns` in isolation.
        assert r["dark_columns"] == 2, r["dark_columns_positions"]
        assert r["ink_junk"] > 0, "the binding strip was not found as junk"
        assert r["ink_clean"] > r["ink_junk"] * 4, \
            "the mid-sheet plate went with the binding strip"
        assert r["ink_clean"] == r["ink_total"] - r["ink_junk"], r
        # AND BOTH SIDES ARE CLEANED. The strip lies outside every box here,
        # so cleaning must move the denominator and leave the numerator --
        # a denominator-only mask is what gives a share above 100 %.
        assert r["clean_under_boxes"] == r["ink_under_boxes"], r
        assert r["ink_clean"] < r["ink_total"], r
        assert r["clean_under_boxes"] / r["ink_clean"] \
            > r["ink_under_boxes"] / r["ink_total"], "cleaning changed nothing"


def test_a_box_laid_on_the_binding_earns_nothing():
    """The attack the mask exists to stop, on a bench every clone has.

    A box over the strip is pure damage finding nothing. It must lift the
    RAW share and move the clean one by not one pixel -- the gradient of the
    attack against the honest number is exactly zero.
    """
    with tempfile.TemporaryDirectory() as tmp:
        pdf = _junk_book(tmp)
        honest = _pages([((20, 20, 120, 120), "table")], tmp, "honest")
        cheat = _pages([((20, 20, 120, 120), "table"),
                        ((185, 0, 192, 200), "text")], tmp, "cheat")
        a, b = fitness.measure(pdf, honest), fitness.measure(pdf, cheat)
        assert b["ink_under_boxes"] > a["ink_under_boxes"], "the attack found nothing to take"
        assert b["clean_under_boxes"] == a["clean_under_boxes"], \
            "a box on the binding moved the clean number"


def test_the_destination_split_is_exhaustive_and_counts_a_pixel_once():
    """Text plus picture is exactly the boxed ink, overlaps included.

    This was asserted inside the battery, where it could not be a probe: it
    reads the UNMUTATED measurement, so no mutator reaches it, and on a
    bench that read nothing it reduces to `0 + X == X`. Asked here on a
    fixture that has both content AND a box overlapping the artefact, which
    is the only case the tie-break `& ~pic` exists for -- removing it makes
    the two shares sum past the ink they divide.
    """
    import json
    with tempfile.TemporaryDirectory() as tmp:
        pdf = _book([(20, 20, 120, 120)], tmp)
        det = _pages([((20, 20, 120, 120), "table"),
                      ((20, 20, 120, 120), "text")], tmp, "det")
        f = os.path.join(det, "0000.json")
        p = json.load(open(f, encoding="utf-8"))
        for b in p["blocks"]:
            b["content"] = "recognised text"
        json.dump(p, open(f, "w", encoding="utf-8"))
        r = fitness.measure(pdf, det)
        assert r["ink_as_text"] + r["ink_as_picture"] == r["ink_under_boxes"], r
        # The overlap is real: both boxes cover the same object, so a sum
        # that ignored it would exceed the ink under boxes.
        assert r["ink_as_picture"] > 0 and r["ink_under_boxes"] > 0, r
