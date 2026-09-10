"""The ink instrument: how it can be won without finding anything"""

import os
import tempfile
import pytest
import numpy as np
import pymupdf
from metrics import classes as policy_mod
from metrics.settings import ROOT
from metrics.bench import Run
from metrics import base
from metrics.probes.fitness import probes
from metrics import ink as fitness
import support


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
    p = {
        "index": 0,
        "width": 200,
        "height": 200,
        "dpi": 72.0,
        "blocks": [
            {
                "block_id": j,
                "box": list(b),
                "label": lab,
                "score": None,
                "order": j,
                "content": None,
                "kind": "none",
            }
            for j, (b, lab) in enumerate(blocks)
        ],
    }
    import json

    with open(os.path.join(d, "0000.json"), "w", encoding="utf-8") as f:
        json.dump(p, f, ensure_ascii=False)
    return d


def _said(res):
    with support.said() as out:
        fitness.report(res)
    return "\n".join(out)


def test_box_off_the_sheet_covers_nothing():
    assert int(fitness._mask((100, 100), [[-40, -40, -20, -20]]).sum()) == 0
    assert fitness._clip((100, 100), [-40, -40, -20, -20]) is None


def test_box_hanging_over_the_edge_is_cut_by_the_sheet():
    m = fitness._mask((100, 100), [[-10, -10, 9, 9]])
    assert int(m.sum()) == 100, int(m.sum())
    m = fitness._mask((100, 100), [[90, 90, 500, 500]])
    assert int(m.sum()) == 100, int(m.sum())


def test_pixel_under_two_boxes_counts_once():
    with tempfile.TemporaryDirectory() as tmp:
        pdf = _book([(20, 20, 120, 120)], tmp)
        truth = _pages([((20, 20, 120, 120), "table")], tmp, "truth")
        det = _pages([((20, 20, 70, 120), "table"), ((20, 20, 70, 120), "text")], tmp, "det")
        r = fitness.measure(pdf, det, truth)
        assert r["torn"] == 1, r
        assert r["left_as_text"] == 0, r
        det2 = _pages([((20, 20, 70, 120), "table"), ((60, 20, 120, 120), "text")], tmp, "det2")
        assert fitness.measure(pdf, det2, truth)["left_as_text"] == 1


def test_blank_page_is_not_a_total_loss():
    with tempfile.TemporaryDirectory() as tmp:
        pdf = _book([], tmp)
        det = _pages([((10, 10, 50, 50), "table")], tmp, "det")
        said = _said(fitness.measure(pdf, det))
        assert "nothing to measure" in said, said
        assert "vanish from the HTML" not in said, said


def test_truth_without_artefacts_is_not_a_missing_truth():
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
    with tempfile.TemporaryDirectory() as tmp:
        pdf = _book([(20, 20, 120, 120)], tmp)
        det = _pages([((20, 20, 120, 120), "table")], tmp, "det")
        truth = _pages(
            [((20, 20, 120, 120), "table"), ((150, 150, 190, 190), "table")], tmp, "truth"
        )
        r = fitness.measure(pdf, det, truth)
        assert r["objects"] == 1 and r["empty_objects"] == 1, r
        assert r["intact"] + r["almost_intact"] + r["bitten"] + r["torn"] == 1, r
        assert "a bench defect" in _said(r)


def test_page_the_model_did_not_mark_is_loud():
    with tempfile.TemporaryDirectory() as tmp:
        pdf = _book([(20, 20, 120, 120)], tmp)
        truth = _pages([((20, 20, 120, 120), "table")], tmp, "truth")
        det = os.path.join(tmp, "det")
        os.makedirs(det)
        import json

        with open(os.path.join(det, "0001.json"), "w", encoding="utf-8") as f:
            json.dump({"index": 1, "width": 200, "height": 200, "dpi": 72.0, "blocks": []}, f)
        try:
            fitness.measure(pdf, det, truth)
        except Exception as e:
            assert "marked up no page" in str(e), e
        else:
            raise AssertionError("the model's silence passed in silence")


def test_report_declares_the_whole_ruler():
    with tempfile.TemporaryDirectory() as tmp:
        pdf = _book([(20, 20, 120, 120)], tmp)
        det = _pages([((20, 20, 120, 120), "table")], tmp, "det")
        said = _said(fitness.measure(pdf, det))
        assert "72 dpi" in said, said
        import re

        nums = re.findall("\\d+(?:\\.\\d+)?", said)
        for v in (fitness.INK, fitness.WHOLE, fitness.ALMOST, fitness.BITTEN):
            want = f"{v:.2f}" if isinstance(v, float) else str(v)
            assert want in nums, (want, nums)
        assert f"{fitness.EDGE * 100:.0f}" in nums, (fitness.EDGE, nums)
        assert "edge band" in said, said


def test_report_says_out_loud_that_it_is_blind_to_merging():
    with tempfile.TemporaryDirectory() as tmp:
        pdf = _book([(20, 20, 120, 120)], tmp)
        det = _pages([((20, 20, 120, 120), "table")], tmp, "det")
        truth = _pages([((20, 20, 120, 120), "table")], tmp, "truth")
        for res in (
            fitness.measure(pdf, det, truth),
            fitness.measure(pdf, det),
            fitness.measure(_book([], tmp), det),
        ):
            said = _said(res)
            assert "merging" in said.lower() and "books score" in said, said


def test_the_number_that_grows_when_boxes_merge():
    with tempfile.TemporaryDirectory() as tmp:
        pdf = _book([(20, 20, 80, 80), (110, 20, 170, 80)], tmp)
        truth = _pages([((20, 20, 80, 80), "table"), ((110, 20, 170, 80), "table")], tmp, "truth")
        apart = _pages([((20, 20, 80, 80), "table"), ((110, 20, 170, 80), "table")], tmp, "apart")
        one = _pages([((20, 20, 170, 80), "table")], tmp, "one")
        a = fitness.measure(pdf, apart, truth)
        b = fitness.measure(pdf, one, truth)
        assert a["intact"] == b["intact"] == 2, (a, b)
        assert a["in_one_box"] == b["in_one_box"] == 2
        assert a["arrived_with_company"] == 0, a
        assert b["arrived_with_company"] == 2, b
        assert a["boxes_with_many_objects"] == 0
        assert b["boxes_with_many_objects"] == 1
        assert "arrived with company 2" in _said(b)


def test_the_ink_threshold_has_one_meaning_in_both_homes():
    from metrics import synth

    assert fitness.INK == synth.INK, (fitness.INK, synth.INK)


def test_merging_two_objects_into_one_box_does_not_lower_the_numbers():
    with tempfile.TemporaryDirectory() as tmp:
        pdf = _book([(20, 20, 80, 80), (110, 20, 170, 80)], tmp)
        truth = _pages([((20, 20, 80, 80), "table"), ((110, 20, 170, 80), "table")], tmp, "truth")
        apart = _pages([((20, 20, 80, 80), "table"), ((110, 20, 150, 80), "table")], tmp, "apart")
        one = _pages([((20, 20, 170, 80), "table")], tmp, "one")
        a = fitness.measure(pdf, apart, truth)
        b = fitness.measure(pdf, one, truth)
        assert a["intact"] == 1 and a["torn"] == 1, a
        assert b["intact"] == 2 and b["torn"] == 0, b
        assert b["in_one_box"] > a["in_one_box"]


_PAGE = (2200, 1700)


def _memory_probe(pages, cap, passes):
    rendered = {"n": 0}
    real, cap0 = (fitness._ink, fitness._INK_CACHE_MAX_BYTES)

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
    page = (_PAGE[0] * _PAGE[1] + 7) // 8
    held, pages, passes = (4, 10, 3)
    n = _memory_probe(pages, held * page, passes)
    assert n == pages + (passes - 1) * (pages - held), n
    assert n < pages * passes, "the cache saved nothing -- that is a miss"
    assert n > pages, "the bench is chosen so the ceiling does not bind"


def test_ink_memory_pays_nothing_twice_when_the_book_fits():
    page = (_PAGE[0] * _PAGE[1] + 7) // 8
    assert _memory_probe(10, 10 * page, 5) == 10


def test_ink_memory_makes_room_for_the_next_book():
    page = (_PAGE[0] * _PAGE[1] + 7) // 8
    real, cap0 = (fitness._ink, fitness._INK_CACHE_MAX_BYTES)
    rendered = {"n": 0}

    def spy(pg, dpi):
        rendered["n"] += 1
        return np.zeros(_PAGE, bool)

    class Doc:
        def __getitem__(self, i):
            return None

    fitness._ink = spy
    fitness._INK_CACHE_MAX_BYTES = 4 * page
    fitness._INK_CACHE.clear()
    fitness._INK_CACHE_BYTES = 0
    try:
        for book in ("a.pdf", "b.pdf"):
            for _ in range(3):
                for i in range(4):
                    fitness._ink_of(book, Doc(), i, 144)
        assert rendered["n"] == 8, rendered["n"]
    finally:
        fitness._ink = real
        fitness._INK_CACHE_MAX_BYTES = cap0
        fitness._INK_CACHE.clear()
        fitness._INK_CACHE_BYTES = 0


def test_the_cap_holds_the_bench_it_was_raised_for():
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
        f"the bench, {packed / 2**20:.0f} MiB packed, does not fit the ceiling of {fitness._INK_CACHE_MAX_BYTES / 2**20:.0f} MiB"
    )


def test_ink_threshold_is_part_of_the_memory_key():
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


class _Bench:
    policy = policy_mod.UNION

    def __init__(self, pdf, truth=""):
        self.pdf = pdf
        self.truth_dir = truth
        self.name = "toy"


def _probes(pdf, det, truth=""):
    ps = probes(_Bench(pdf, truth), Run.bare(det))
    with support.said() as out:
        seen, mute, bad = base.run_probes(ps)
    return (seen, mute, bad, out)


def test_the_probes_count_what_they_could_not_measure():
    with tempfile.TemporaryDirectory() as tmp:
        pdf = _book([(20, 20, 120, 120)], tmp)
        det = _pages([((20, 20, 120, 120), "table")], tmp, "det")
        truth = _pages([((20, 20, 120, 120), "table")], tmp, "truth")
        seen, mute, bad, out = _probes(pdf, det, truth)
        assert bad == 0, out
        assert mute == sum(("no data" in l for l in out)), (mute, out)
        seen2, mute2, bad2, out2 = _probes(pdf, det)
        assert bad2 == 0, out2
        assert mute2 == sum(("no data" in l for l in out2)), (mute2, out2)
        assert mute2 >= mute * 2, (mute, mute2)
        assert seen2 - mute2 < seen - mute, (seen, mute, seen2, mute2)


def test_the_probes_corrupt_all_three_sides():
    with tempfile.TemporaryDirectory() as tmp:
        pdf = _book([(20, 20, 120, 120)], tmp)
        det = _pages([((20, 20, 120, 120), "table")], tmp, "det")
        truth = _pages([((20, 20, 120, 120), "table")], tmp, "truth")
        said = "\n".join(_probes(pdf, det, truth)[3])
        assert "truth shifted" in said, said
        assert "ink threshold" in said, said
        assert "moved off the top-left corner" in said, said
        assert "merged into one" in said, said
        assert "handed out as a text one too" in said, said


def _sheet(w, h, bands=(), rules=()):
    import numpy as np

    im = np.zeros((h, w), bool)
    for x0, x1 in bands:
        im[:, x0:x1] = True
    for y, a, b in rules:
        im[y : y + 2, a:b] = True
    return im


def test_a_binding_shadow_is_junk_and_a_mid_sheet_plate_is_not():
    from metrics import ink

    w, h = (1000, 1400)
    shadow = ink._junk_columns(_sheet(w, h, bands=[(958, 986)]))
    assert shadow.any() and shadow[970], "a shadow at the binding is not junk"
    plate = ink._junk_columns(_sheet(w, h, bands=[(480, 508)]))
    assert not plate.any(), "a dark column mid-sheet was discarded as junk"


def test_a_band_too_wide_to_be_a_shadow_is_kept():
    from metrics import ink

    w, h = (1000, 1400)
    assert not ink._junk_columns(_sheet(w, h, bands=[(800, 999)])).any(), (
        "a band a fifth of the sheet wide was called a shadow"
    )
    assert ink._junk_columns(_sheet(w, h, bands=[(910, 999)])).any(), (
        "a strip within the width cap was not called a shadow"
    )


def test_a_rule_crossing_the_band_keeps_it():
    from metrics import ink

    w, h = (1000, 1400)
    band = [(958, 986)]
    crossed = _sheet(w, h, bands=band, rules=[(700, 300, 999)])
    assert not ink._junk_columns(crossed).any(), (
        "a band with a table rule running through it was discarded"
    )
    apart = _sheet(w, h, bands=band, rules=[(700, 10, 400)])
    assert ink._junk_columns(apart).any(), "a rule that never touches the band vetoed it anyway"


def test_a_whitespace_answer_is_not_text_that_arrived():
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
        assert fitness.measure(pdf, blank)["ink_as_text"] == 0, (
            "a whitespace answer counted as text that arrived"
        )


def _junk_book(out):
    return _book([(20, 20, 120, 120), (185, 0, 192, 200)], out)


def test_the_junk_mask_is_actually_applied_to_the_numbers():
    with tempfile.TemporaryDirectory() as tmp:
        pdf = _junk_book(tmp)
        det = _pages([((20, 20, 120, 120), "table")], tmp, "det")
        r = fitness.measure(pdf, det)
        assert r["dark_columns"] == 2, r["dark_columns_positions"]
        assert r["ink_junk"] > 0, "the binding strip was not found as junk"
        assert r["ink_clean"] > r["ink_junk"] * 4, "the mid-sheet plate went with the binding strip"
        assert r["ink_clean"] == r["ink_total"] - r["ink_junk"], r
        assert r["clean_under_boxes"] == r["ink_under_boxes"], r
        assert r["ink_clean"] < r["ink_total"], r
        assert r["clean_under_boxes"] / r["ink_clean"] > r["ink_under_boxes"] / r["ink_total"], (
            "cleaning changed nothing"
        )


def test_a_box_laid_on_the_binding_earns_nothing():
    with tempfile.TemporaryDirectory() as tmp:
        pdf = _junk_book(tmp)
        honest = _pages([((20, 20, 120, 120), "table")], tmp, "honest")
        cheat = _pages([((20, 20, 120, 120), "table"), ((185, 0, 192, 200), "text")], tmp, "cheat")
        a, b = (fitness.measure(pdf, honest), fitness.measure(pdf, cheat))
        assert b["ink_under_boxes"] > a["ink_under_boxes"], "the attack found nothing to take"
        assert b["clean_under_boxes"] == a["clean_under_boxes"], (
            "a box on the binding moved the clean number"
        )


def test_the_destination_split_is_exhaustive_and_counts_a_pixel_once():
    import json

    with tempfile.TemporaryDirectory() as tmp:
        pdf = _book([(20, 20, 120, 120)], tmp)
        det = _pages([((20, 20, 120, 120), "table"), ((20, 20, 120, 120), "text")], tmp, "det")
        f = os.path.join(det, "0000.json")
        p = json.load(open(f, encoding="utf-8"))
        for b in p["blocks"]:
            b["content"] = "recognised text"
        json.dump(p, open(f, "w", encoding="utf-8"))
        r = fitness.measure(pdf, det)
        assert r["ink_as_text"] + r["ink_as_picture"] == r["ink_under_boxes"], r
        assert r["ink_as_picture"] > 0 and r["ink_under_boxes"] > 0, r
