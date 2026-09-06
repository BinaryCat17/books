"""The instrument the project looks with ITS EYES -- and it had no checks.

No `overlay` in `tests/`, none of the 158 checks, none of the 134 mutations.
The price is special: `books score` lies with a number, and a number can be
rechecked by another; `books overlay` lies with a PICTURE, and a picture is
rechecked by eye -- the reader leaves certain he saw it himself. In this
session we looked by eye four times, and twice it overturned a claim numbers
had held up.

Four defects are pinned here, all found by audit and all reproduced:

    --pages counted from ZERO   `books detect` counts from one, and this
                                parser knew no ranges `40-42` at all (a bare
                                ValueError). You look at the wrong sheet and
                                never learn of it -- and by eye is exactly how
                                one looks: detect a page or two and glance

    a page missing from one     3 pages of 13 taken from the model: "NOT FOUND
    markup was skipped in       6" did not budge and "divergences" got FEWER
    silence                     (10 -> 7) -- the model looked better because
                                part of its answer was gone. `books score` on
                                the same input refuses to count aloud

    one markup -> three zeroes  "matched 0, NOT FOUND 0, EXTRA 0; divergences
                                on 0 pages" with the boxes drawn. A zero from
                                not understanding, in the SUMMARY line

    "600 sheets" with one       `doc.page_count` was printed; three different
    drawn                       quantities (pages of the book, sheets, boxes)
                                travelled under one word
"""
import json
import os
import tempfile

import support

from booksmith import overlay


def _stand(d, pages=3, model_skip=()):
    """Three sheets, truth on all, model output minus `model_skip`."""
    import pymupdf
    pdf = os.path.join(d, "b.pdf")
    doc = pymupdf.open()
    for _ in range(pages):
        doc.new_page(width=200, height=300)
    doc.save(pdf)
    doc.close()
    for name, skip in (("truth", ()), ("model", model_skip)):
        pd = os.path.join(d, name, "pages")
        os.makedirs(pd)
        for i in range(pages):
            if i in skip:
                continue
            with open(os.path.join(pd, f"{i:04d}.json"), "w",
                      encoding="utf-8") as f:
                json.dump({"index": i, "width": 400, "height": 600,
                           "blocks": [{"block_id": 0, "box": [10, 10, 90, 90],
                                       "label": "text", "score": None,
                                       "order": 0, "content": None,
                                       "kind": "none"}]}, f)
    return pdf


def _say(pdf, marks, only=None):
    said = []
    overlay.build(pdf, pdf + ".ov.pdf", marks, only=only, log=said.append)
    return "\n".join(said)


def _drawn_sheets(out_pdf):
    """Which output sheets really carry anything -- read off the drawings."""
    import pymupdf
    doc = pymupdf.open(out_pdf)
    got = [i for i, pg in enumerate(doc) if pg.get_drawings()]
    doc.close()
    return got


def test_pages_are_counted_from_one_like_detect():
    """`--pages` is counted here THE SAME WAY as in `books detect`.

    One parser for both, not a second copy: `books detect --pages 2` gives
    sheet 0001, and `books overlay --pages 2` must draw that one. It used to
    draw 0002, in silence.

    CALLED THROUGH THE CLI, NOT THE PARSER DIRECTLY, and that is the substance
    of the check. Its first edition asserted `detect.parse_pages("2", 3) ==
    [1]` and then passed that set to `build` itself -- measuring that the
    parser counts from one (true before the repair too) and NOT that
    `cmd_overlay` calls it. Reverting `cli.py` whole and a point mutation on
    the repaired line both gave ZERO red checks -- a hole of the very class
    being repaired beside it.
    """
    from booksmith import cli
    with tempfile.TemporaryDirectory() as d:
        pdf = _stand(d)
        t = os.path.join(d, "truth", "pages")
        for spec, want in (("2", [1]), ("1-3", [0, 1, 2]),
                           ("1 3", [0, 2])):
            out = os.path.join(d, f"p{spec.replace(' ', '_')}.pdf")
            said = []
            was = cli.log
            cli.log = said.append          # `log` in cli is an imported name
            try:
                assert cli.main(["overlay", pdf, "--truth", t,
                                 "--pages", spec, "--out", out]) == 0
            finally:
                cli.log = was
            # The output holds ONLY the requested sheets (else `--pages 102`
            # on the golden bench would give 494 MB), so the count is checked
            # by two quantities: how many sheets came out, and WHICH page of
            # the book came first -- the instrument names the second itself.
            got = _drawn_sheets(out)
            assert got == list(range(len(want))), (
                f"--pages {spec!r}: в выходе листы {got}, ожидались "
                f"{list(range(len(want)))} подряд с первого")
            s = "\n".join(said)
            assert f"sheets drawn {len(want)} of 3" in s, s
            if len(want) < 3:
                assert f"is page {want[0] + 1} of the book" in s, (
                    f"--pages {spec!r}: прибор не сказал, какая страница "
                    f"книги стала первой в файле. `books detect` на том же "
                    f"вводе взял бы {want} — смотришь не тот лист и не "
                    f"узнаёшь об этом.\n{s}")


def test_a_page_out_of_the_book_is_loud():
    """A number past the end of the book is a complaint, not an empty run.

    `overlay`'s own parser used to put the number straight into the index,
    and an empty set gave a silent "divergences on 0 pages".
    """
    from booksmith import cli
    with tempfile.TemporaryDirectory() as d:
        pdf = _stand(d)
        t = os.path.join(d, "truth", "pages")
        try:
            cli.main(["overlay", pdf, "--truth", t, "--pages", "9",
                      "--out", os.path.join(d, "x.pdf")])
        except SystemExit as e:
            assert "3 pages" in str(e), f"жалоба не про то: {e}"
            return
        raise AssertionError("страница за пределами книги принята молча")


def test_a_page_missing_from_one_markup_is_named():
    """A page missing from one markup is NAMED, not skipped.

    Can fail: bring back the `continue` without a counter -- the sheet comes
    out looking whole while the numbers improve because part of the answer
    went missing.
    """
    with tempfile.TemporaryDirectory() as d:
        pdf = _stand(d, model_skip=(1,))
        s = _say(pdf, [(os.path.join(d, "truth", "pages"), "И"),
                       (os.path.join(d, "model", "pages"), "М")])
        assert "the model is MISSING 1 pages" in s and "[1]" in s, s
        assert "sheets drawn 2 of 3" in s, s


def test_a_page_missing_from_the_truth_is_named_too():
    """The mirror side: a hole in the TRUTH is named as one in the model is.

    The sceptic showed that both sides were repaired and one was checked:
    replacing `counts["missing_in_truth"].append(i)` with `pass` reddened NOT
    ONE of the 163 checks. A guard with half of it checked is half a guard.
    """
    with tempfile.TemporaryDirectory() as d:
        pdf = _stand(d)
        os.unlink(os.path.join(d, "truth", "pages", "0001.json"))
        s = _say(pdf, [(os.path.join(d, "truth", "pages"), "И"),
                       (os.path.join(d, "model", "pages"), "М")])
        assert "truth is MISSING 1 pages" in s and "[1]" in s, s


def test_one_markup_says_there_is_nothing_to_compare():
    """One markup means "NOTHING TO COMPARE WITH", not three zeroes.

    Three zeroes with boxes drawn read as "it all agreed" -- the same zero
    from not understanding as "chapters 0" for "I did not recognise them",
    here in the summary line.
    """
    with tempfile.TemporaryDirectory() as d:
        pdf = _stand(d)
        s = _say(pdf, [(os.path.join(d, "truth", "pages"), "И")])
        assert "NOTHING TO COMPARE WITH" in s, s
        assert "matched 0" not in s, f"итог всё ещё врёт нулями:\n{s}"


def test_the_summary_counts_sheets_not_pages_of_the_book():
    """The summary names the sheets DRAWN, and the boxes separately.

    `doc.page_count` used to be printed: `--pages 102` on the golden bench
    gave "600 sheets" with one drawn.
    """
    with tempfile.TemporaryDirectory() as d:
        pdf = _stand(d)
        s = _say(pdf, [(os.path.join(d, "truth", "pages"), "И")], only=[0])
        assert "sheets drawn 1 of 3 in the book, boxes 1" in s, s


def test_what_was_not_checked_by_sha256_is_named():
    """Unverified markup is NAMED, not passed over in silence.

    It used to print "sha256 checked for И" and not a word about "М" being
    unchecked at all: half a guard read as the whole guard.
    """
    with tempfile.TemporaryDirectory() as d:
        pdf = _stand(d)
        with open(os.path.join(d, "truth", "manifest.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"sha256 pdf": overlay._sha256(pdf)}, f)
        s = _say(pdf, [(os.path.join(d, "truth", "pages"), "И"),
                       (os.path.join(d, "model", "pages"), "М")])
        assert "verified for И" in s and "NOT VERIFIED for М" in s, s


def test_the_sheet_shouts_at_exactly_what_the_number_calls_extra():
    """"EXTRA" on the sheet == "spurious box" in `books score`. One rule.

    WHY. The instrument split boxes into loud and quiet by one sign -- an
    artefact label -- and shouted orange at everything: on the golden bench
    508 boxes, of which `books score` calls 110 spurious and DELIBERATELY
    forgives 350 (69 %) as "on an object outside the measure". A person looked
    and sentenced the model by a number the instrument beside it refutes.

    Can fail: bring back the sign by label and "EXTRA" grows past "spurious
    box". Here it shows on three boxes instead of 350, but the rule is the
    same and it is ONE: `metrics.extra_kind`, called by both.
    """
    import json as _j

    from booksmith import metrics

    with tempfile.TemporaryDirectory() as d:
        pdf = _stand(d, pages=1)
        # Truth: one artefact inside the measure plus one OUTSIDE it.
        t = {"index": 0, "width": 400, "height": 600,
             "blocks": [{"block_id": 0, "box": [10, 10, 90, 90],
                         "label": "table", "score": None, "order": 0,
                         "content": None, "kind": "none"}],
             "meta": {"out_of_scope": [{"box": [200, 200, 300, 300],
                                      "category": "Vignette",
                                      "bucket": "inexpressible"}]}}
        # Model: found the table, plus a box ON an object outside the
        # measure, plus a genuinely spurious one in empty space.
        m = {"index": 0, "width": 400, "height": 600,
             "blocks": [{"block_id": 0, "box": [10, 10, 90, 90],
                         "label": "table", "score": 0.9, "order": 0,
                         "content": None, "kind": "none"},
                        {"block_id": 1, "box": [205, 205, 295, 295],
                         "label": "image", "score": 0.8, "order": 1,
                         "content": None, "kind": "none"},
                        {"block_id": 2, "box": [320, 400, 380, 460],
                         "label": "image", "score": 0.7, "order": 2,
                         "content": None, "kind": "none"}]}
        for name, page in (("truth", t), ("model", m)):
            with open(os.path.join(d, name, "pages", "0000.json"), "w",
                      encoding="utf-8") as f:
                _j.dump(page, f)
        counts = {}
        overlay.build(pdf, os.path.join(d, "o.pdf"),
                      [(os.path.join(d, "truth", "pages"), "И"),
                       (os.path.join(d, "model", "pages"), "М")],
                      log=lambda *a: None)
        c = metrics.compare(os.path.join(d, "truth", "pages"),
                            os.path.join(d, "model", "pages"))
        del counts
        beds = c["troubles"] if "troubles" in c else {}
        want = beds.get("spurious_box", 0)
        said = []
        got = overlay.build(pdf, os.path.join(d, "o2.pdf"),
                            [(os.path.join(d, "truth", "pages"), "И"),
                             (os.path.join(d, "model", "pages"), "М")],
                            log=said.append)["spurious"]
        assert want == 1, f"стенд собран не так: score зовёт лишними {want}"
        assert got == want, (
            f"лист кричит про {got} рамок, а число зовёт лишними {want}. "
            f"Прибор и метрика разошлись на одной и той же рамке — а лист "
            f"судят глазами и переспросить его нечем")


def test_a_changed_label_is_not_painted_like_an_extra_box():
    """The caption "label: A -> B" and "EXTRA" get DIFFERENT colours.

    Both used to take the one orange constant, and the caption hung over a
    GREY box: its colour contradicted the box it belongs to. Measured by eye
    on `bench/slovar` p. 2 (56 such captions of 56 pairs): of the two genuine
    "EXTRA" boxes on the sheet one was invisible -- three points from a
    caption of the same colour in the same size.

    Can fail: bring the colours back together.
    """
    assert overlay.LABEL != overlay.SPURIOUS, (
        "смена ярлыка красится как лишняя рамка — оранжевый перестаёт "
        "значить «модель нашла лишнее», и настоящая лишняя в нём тонет")
    assert overlay.LABEL != overlay.MATCHED, (
        "подпись слилась с рамкой, к которой относится")
