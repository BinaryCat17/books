"""The instrument the project looks with its eyes.

The price of a defect here is special: `books score` lies with a number, and a
number can be rechecked by another; `books overlay` lies with a picture, and a
picture is rechecked by eye -- the reader leaves certain he saw it himself.

So the summary counts the sheets it drew and no other quantity, names every page
missing from a markup, says "nothing to compare with" rather than three zeroes,
and shouts at exactly what `books score` calls spurious.
"""
import json
import os
import tempfile

from booksmith.core import stamp

from booksmith.datasets import look as overlay
import support


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
    with support.said() as said:
        overlay.build(pdf, pdf + ".ov.pdf", marks, only=only)
    return "\n".join(said)


def _drawn_sheets(out_pdf):
    """Which output sheets really carry anything -- read off the drawings."""
    import pymupdf
    doc = pymupdf.open(out_pdf)
    got = [i for i, pg in enumerate(doc) if pg.get_drawings()]
    doc.close()
    return got


def test_pages_are_counted_from_one_like_detect():
    """`--pages` is counted here the same way as in `books detect`: one parser for
    both, so `--pages 2` draws sheet 0001. Called through the CLI, or the check
    measures the parser and not that `cmd_overlay` calls it."""
    from booksmith import cli
    with tempfile.TemporaryDirectory() as d:
        pdf = _stand(d)
        t = os.path.join(d, "truth", "pages")
        for spec, want in (("2", [1]), ("1-3", [0, 1, 2]),
                           ("1 3", [0, 2])):
            out = os.path.join(d, f"p{spec.replace(' ', '_')}.pdf")
            with support.said() as said:
                assert cli.main(["overlay", pdf, "--truth", t,
                                 "--pages", spec, "--out", out]) == 0
            # The output holds only the requested sheets, so the count is checked
            # by two quantities: how many sheets came out, and which page of
            # the book came first -- the instrument names the second itself.
            got = _drawn_sheets(out)
            assert got == list(range(len(want))), (
                f"--pages {spec!r}: the output holds sheets {got}, expected "
                f"{list(range(len(want)))} in a row from the first")
            s = "\n".join(said)
            assert f"sheets drawn {len(want)} of 3" in s, s
            if len(want) < 3:
                assert f"is page {want[0] + 1} of the book" in s, (
                    f"--pages {spec!r}: the instrument did not say which "
                    f"page of the book became the first in the file. `books "
                    f"detect` on the same input would take {want} -- you look "
                    f"at the wrong sheet and never find out.\n{s}")


def test_a_page_out_of_the_book_is_loud():
    """A number past the end of the book is a complaint, not an empty run: the
    number put straight into the index gave a silent "divergences on 0 pages"."""
    import contextlib
    import io
    from booksmith import cli
    with tempfile.TemporaryDirectory() as d:
        pdf = _stand(d)
        t = os.path.join(d, "truth", "pages")
        # A refusal leaves `main` as exit code 1 and one logged line: `cli.main`
        # catches `Refusal` so the operator sees a line and not a stack.
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = cli.main(["overlay", pdf, "--truth", t, "--pages", "9",
                           "--out", os.path.join(d, "x.pdf")])
        assert rc == 1, f"a page beyond the book was accepted in silence (rc {rc})"
        assert "3 pages" in buf.getvalue(), \
            f"the complaint is about something else: {buf.getvalue()[-300:]}"


def test_a_page_missing_from_one_markup_is_named():
    """A page missing from one markup is named, not skipped: without a counter the
    sheet comes out looking whole while the numbers improve."""
    with tempfile.TemporaryDirectory() as d:
        pdf = _stand(d, model_skip=(1,))
        s = _say(pdf, [(os.path.join(d, "truth", "pages"), "T"),
                       (os.path.join(d, "model", "pages"), "M")])
        assert "the model is MISSING 1 pages" in s and "[1]" in s, s
        assert "sheets drawn 2 of 3" in s, s


def test_a_page_missing_from_the_truth_is_named_too():
    """The mirror side: a hole in the truth is named as one in the model is. A
    guard with half of it checked is half a guard."""
    with tempfile.TemporaryDirectory() as d:
        pdf = _stand(d)
        os.unlink(os.path.join(d, "truth", "pages", "0001.json"))
        s = _say(pdf, [(os.path.join(d, "truth", "pages"), "T"),
                       (os.path.join(d, "model", "pages"), "M")])
        assert "truth is MISSING 1 pages" in s and "[1]" in s, s


def test_one_markup_says_there_is_nothing_to_compare():
    """One markup means "nothing to compare with", not three zeroes: three zeroes
    with boxes drawn read as "it all agreed"."""
    with tempfile.TemporaryDirectory() as d:
        pdf = _stand(d)
        s = _say(pdf, [(os.path.join(d, "truth", "pages"), "T")])
        assert "NOTHING TO COMPARE WITH" in s, s
        assert "matched 0" not in s, f"the summary still lies with zeros:\n{s}"


def test_the_summary_counts_sheets_not_pages_of_the_book():
    """The summary names the sheets drawn, and the boxes separately:
    `doc.page_count` printed instead gave "600 sheets" with one drawn."""
    with tempfile.TemporaryDirectory() as d:
        pdf = _stand(d)
        s = _say(pdf, [(os.path.join(d, "truth", "pages"), "T")], only=[0])
        assert "sheets drawn 1 of 3 in the book, boxes 1" in s, s


def test_what_was_not_checked_by_sha256_is_named():
    """Unverified markup is named, not passed over in silence: half a guard read
    as the whole guard."""
    with tempfile.TemporaryDirectory() as d:
        pdf = _stand(d)
        with open(os.path.join(d, "truth", "manifest.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"source": {"name": os.path.basename(pdf),
                                  "sha256": stamp.sha256(pdf)}}, f)
        s = _say(pdf, [(os.path.join(d, "truth", "pages"), "T"),
                       (os.path.join(d, "model", "pages"), "M")])
        assert "verified for T" in s and "NOT VERIFIED for M" in s, s


def test_the_sheet_shouts_at_exactly_what_the_number_calls_extra():
    """"EXTRA" on the sheet is "spurious box" in `books score`, by one rule:
    `metrics.extra_kind`, called by both. Splitting boxes by label instead shouts
    at every box on an object outside the measure, which score forgives."""
    import json as _j

    from booksmith.datasets.metrics import contour as metrics

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
                      [(os.path.join(d, "truth", "pages"), "T"),
                       (os.path.join(d, "model", "pages"), "M")])
        c = metrics.compare(os.path.join(d, "truth", "pages"),
                            os.path.join(d, "model", "pages"))
        del counts
        beds = c["troubles"] if "troubles" in c else {}
        want = beds.get("spurious_box", 0)
        with support.said():
            got = overlay.build(pdf, os.path.join(d, "o2.pdf"),
                                [(os.path.join(d, "truth", "pages"), "T"),
                                 (os.path.join(d, "model", "pages"), "M")])["spurious"]
        assert want == 1, f"the bench is built wrong: score calls {want} spurious"
        assert got == want, (
            f"the sheet shouts about {got} boxes while the number calls "
            f"{want} spurious. Instrument and metric diverged on the very "
            f"same box -- and a sheet is judged by eye, with nothing to ask "
            f"it again")


def test_a_changed_label_is_not_painted_like_an_extra_box():
    """The caption "label: A -> B" and "EXTRA" get different colours: one orange
    constant for both hangs the caption over a grey box and drowns a real
    spurious box three points from a caption of the same colour."""
    assert overlay.LABEL != overlay.SPURIOUS, (
        "a changed label is painted as a spurious box -- orange stops "
        "meaning 'the model found something extra', and a real spurious box "
        "drowns in it")
    assert overlay.LABEL != overlay.MATCHED, (
        "the caption merged with the box it belongs to")
