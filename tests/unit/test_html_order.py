"""The book builder and the reading-order contract.

The `reading order` field has two readers -- the metric's guard and the book
builder -- and a second copy of the rule in the builder drifts silently: a
percentage out of nothing is born of two copies of one contract.
"""
from booksmith.core import policy
from booksmith.processing.assemble import html as H
from booksmith.core import page as B
from booksmith.core import book

_V2 = policy.POLICIES["PP-DocLayoutV2"]


def test_book_builder_reads_the_order_rule_through_the_one_contract():
    """`assemble/html` must call `core.page.ours_order`, not a copy of its own.
    The probe set must contain both answers, and that is asserted rather than
    assumed: comparing False with False nine times would pass a broken copy."""
    probes = ("ours_top_down_left_right", "OURS, in bands", "  ours  ",
              "Ours_by_choice", "model_rank", "", None, 0, "generation_order")
    answers = {B.ours_order(v) for v in probes}
    assert answers == {True, False}, (
        "the probe set no longer contains both answers: comparing two "
        "functions that both say False proves nothing")
    for v in probes:
        assert H._ours(v) == B.ours_order(v), (
            f"{v!r}: the book builder and the adapter contract diverged -- "
            f"builder {H._ours(v)}, contract {B.ours_order(v)}. This is that "
            f"second copy of one contract out of which a percentage is born "
            f"from nothing")


def test_anchor_is_page_scoped():
    """The anchor is per page: `block_id` restarts on every page, and a book-wide
    `b17` would give five hundred identical anchors for a swap to land in."""
    assert B.anchor(42, 17) == "p0042-b17"
    assert B.anchor(0, 0) == "p0000-b0"
    assert B.anchor(1, 17) != B.anchor(2, 17)


# --- crops: the builder's contract with the model's box ---------------------
#
# One contract, one file: `assemble/html` cuts with `core/raster` by the model's
# box and prints its numbers into the caption.

def _sheet():
    """An empty 720x506 pt sheet in memory. No bench: this must run in any
    tree, not only where the bench is cut."""
    import pymupdf
    doc = pymupdf.open()
    doc.new_page(width=720, height=506)
    return doc


def test_clipping_is_measured_with_a_tolerance_not_exactly():
    """The "clipped by the sheet" flag at a dpi with no binary-exact scale:
    pymupdf intersects in single precision, so a disagreement of 1.7e-05 pt read
    as "the box left the sheet". And the reverse: a real clip stays visible."""
    import os
    import tempfile
    from booksmith.core import raster as crop
    doc = _sheet()
    dpi = 150.0                       # 72/150 = 0.48 -- NOT binary-exact
    # The box is in pixels, and not round on purpose: at 100 and 300 px the
    # points come out whole and the check would be green on broken code.
    inside_px = [113, 74, 1332, 803]
    out_px = [113, 74, int((720 + 20) / 0.48), 803]      # 20 pt off the sheet
    with tempfile.TemporaryDirectory() as tmp:
        dst = os.path.join(tmp, "b.png")
        inside = crop.cut(doc, 0, inside_px, dpi, dst)
        assert inside["clipped_by_sheet"] is False, (
            "a box wholly inside the sheet was declared clipped -- that is "
            "float32 intersection, not a defect of the model")
        out = crop.cut(doc, 0, out_px, dpi, dst)
        assert out["clipped_by_sheet"] is True, (
            "a box hanging 20 points off the sheet was NOT called clipped -- "
            "the tolerance ate a real trouble")


def test_degenerate_and_inverted_boxes_are_named_by_their_own_trouble():
    """A degenerate or an inverted box is not "off the sheet": both give an empty
    intersection, and the wrong diagnosis sends the reader after shifted
    coordinates for a box in the middle of the paper."""
    import os
    import tempfile
    from booksmith.core import raster as crop
    doc = _sheet()
    with tempfile.TemporaryDirectory() as tmp:
        dst = os.path.join(tmp, "b.png")
        for box, word in (([200.0, 200.0, 200.0, 300.0], "DEGENERATE"),
                          ([300.0, 200.0, 200.0, 300.0], "INVERTED")):
            try:
                crop.cut(doc, 0, box, 144.0, dst)
            except ValueError as e:
                assert word in str(e), (
                    f"the box {box} was named by the wrong trouble: "
                    f"{str(e)[:90]!r}")
            else:
                raise AssertionError(f"the box {box} was cut silently")
        # And a real "off the sheet" must stay itself.
        try:
            crop.cut(doc, 0, [5000.0, 5000.0, 5100.0, 5100.0], 144.0, dst)
        except ValueError as e:
            assert "does not intersect the sheet" in str(e)
        else:
            raise AssertionError("a box beyond the sheet was cut silently")


def test_negative_margin_is_refused_out_loud():
    """A negative `CROP_MARGIN` cuts the model's box instead of giving margin,
    with both clip flags False. Editing the model's box is forbidden, hence a
    failure and not a silent clamp to zero."""
    import os
    from booksmith.core import raster as crop
    was = os.environ.get("CROP_MARGIN")
    os.environ["CROP_MARGIN"] = "-0.1"
    try:
        crop.params(144.0)
    except ValueError as e:
        assert "CROP_MARGIN" in str(e)
    else:
        raise AssertionError("a negative margin was accepted silently")
    finally:
        if was is None:
            del os.environ["CROP_MARGIN"]
        else:
            os.environ["CROP_MARGIN"] = was


def test_native_dpi_divides_by_the_placement_not_by_the_sheet():
    """Native sharpness is counted from the image's placement width: a spread scan
    is wider than the sheet, `books prepare` halves it and lays both halves with
    `show_pdf_page`, and dividing by the sheet overstates the grid."""
    import pymupdf
    from booksmith.core import raster as crop

    # Sheet 200x100 pt, a 1000 px raster laid on 400 pt -- twice the sheet.
    doc = pymupdf.open()
    page = doc.new_page(width=200, height=100)
    src = pymupdf.open()
    sp = src.new_page(width=400, height=100)
    sp.insert_text((10, 50), "x")
    pix = sp.get_pixmap(dpi=180)          # 1000 px over 400 pt = 180 dpi
    img = pymupdf.open("png", pix.tobytes("png"))
    page.insert_image(pymupdf.Rect(0, 0, 400, 100), stream=img.convert_to_pdf()
                      if False else pix.tobytes("png"))
    got = crop.native_dpi(page)
    doc.close(); src.close(); img.close()
    assert got is not None, (
        "the raster covers the whole sheet, and sharpness was not determined")
    # By placement: 1000 px / 400 pt = 180 dpi. By the SHEET it would be 360.
    assert abs(got - 180.0) < 1.0, (
        f"sharpness {got:.1f} -- counted by the width of the SHEET, not of "
        f"the placement; dividing by the sheet gives 360 and doubles it")


def test_native_dpi_says_nothing_when_there_is_nothing_to_say():
    """Vector art and a corner stamp give `None`, not a guessed number."""
    import pymupdf
    from booksmith.core import raster as crop

    doc = pymupdf.open()
    page = doc.new_page(width=200, height=100)
    page.insert_text((10, 50), "text only")
    assert crop.native_dpi(page) is None, "vector art declared a grid"

    # A corner stamp: detailed, but a fifth of the width.
    small = pymupdf.open()
    sp = small.new_page(width=40, height=20)
    sp.insert_text((2, 15), "m")
    page.insert_image(pymupdf.Rect(0, 0, 40, 20),
                      stream=sp.get_pixmap(dpi=600).tobytes("png"))
    got = crop.native_dpi(page)
    doc.close(); small.close()
    assert got is None, (
        f"a stamp in the corner was declared the page's sharpness ({got}) -- "
        f"the whole sheet would be cut by it")


def test_crop_dpi_counts_what_will_actually_be_cut():
    """Sharpness counts the box's intersection with the sheet, not the box:
    `crop.cut` cuts the intersection and the model's box may hang off the paper,
    so the two numbers must be counted on one rectangle."""
    from booksmith.processing.read.driver import crop_dpi_for
    W = (112896, 1003520)
    sheet = (0.0, 0.0, 1012.0, 1466.0)
    out = (0, 0, 2024, 1466)                   # twice the sheet wide
    without, _ = crop_dpi_for(out, 144.0, 601.0, W)
    with_sheet, why = crop_dpi_for(out, 144.0, 601.0, W, sheet=sheet)
    assert with_sheet > without + 1, (
        f"by the sheet {with_sheet:.1f}, by the full box {without:.1f} -- "
        f"sharpness is counted on what is not on the paper")
    # The same box wholly ON the sheet must not change when a sheet appears.
    inside = (0, 0, 540, 700)
    a, _ = crop_dpi_for(inside, 144.0, 601.0, W)
    b, _ = crop_dpi_for(inside, 144.0, 601.0, W, sheet=sheet)
    assert abs(a - b) < 1e-9, (
        "the sheet changed the sharpness of a box lying inside it")


def test_crop_dpi_never_comes_from_the_environment_silently():
    """An empty `CROP_DPI` is not "as in this process", and it names its home:
    the default is the scan's own sharpness, then detection, and a number taken
    from the environment says so in words."""
    from booksmith.core import raster as crop
    # own sharpness known -- it is taken, detection is irrelevant
    p = crop.params(150.0, page_native=300.0)
    assert p["dpi"] == 300.0 and p["dpi_source"] == "native_scan_dpi", p
    # none of its own -- detection, and that is said in words
    p2 = crop.params(150.0)
    assert p2["dpi"] == 150.0 and "as in detection" in p2["dpi_source"], p2
    # neither -- the environment, and it is NAMED as a guess
    assert crop.params()["dpi_source"] == "PAGE_DPI of this process", (
        "sharpness was guessed from the environment, and not a word was "
        "said about it")


def test_crop_dpi_takes_the_ink_that_exists_and_invents_none():
    """Crop sharpness is a rule: all there is, but no more than the window. None
    of the three is ours -- sharpness from the scan, bounds from the model, box
    size from the detector -- and above our own grid it never goes."""
    from booksmith.processing.read.driver import crop_dpi_for
    W = (112896, 1003520)
    # block below the lower bound: stay on our grid and say so
    d, why = crop_dpi_for((0, 0, 273, 47), 144.0, 144.0, W)
    assert d == 144.0 and "below_model_min" == why, (d, why)
    # the same block in a djvu book (601 dpi text layer) -- take it all
    d, why = crop_dpi_for((0, 0, 273, 47), 144.0, 601.0, W)
    assert d == 601.0 and why == "native_scan_dpi", (d, why)
    # a big table there would pass the upper bound -- squeeze to exactly it
    d, why = crop_dpi_for((0, 0, 540, 700), 144.0, 601.0, W)
    px = (540 / 144 * d) * (700 / 144 * d)
    assert abs(px - W[1]) < 1 and why == "downscaled_to_model_max", (d, why, px)
    # the model declared no bounds -- cut at our sharpness and fix nothing
    d, why = crop_dpi_for((0, 0, 540, 700), 144.0, 601.0, None)
    assert d == 601.0 and why == "native_scan_dpi_no_model_bounds", (d, why)


def test_nesting_survives_blocks_without_a_model_rank():
    """`Block.order = None` is allowed outright and the build may not fall: three
    adapters of four give no rank, and in the fourth it is empty for exactly what
    the first level cuts out as pictures."""
    from booksmith.core.page import Block
    box = (0.0, 0.0, 100.0, 100.0)
    pairs = ((3, None), (None, 3), (None, None), (1, 2))
    for o1, o2 in pairs:
        arts = [Block(block_id=1, box=box, label="table", order=o1),
                Block(block_id=2, box=box, label="image", order=o2)]
        inner = H._nesting(arts)
        assert len(inner) == 1, (
            f"ranks {o1!r}/{o2!r}: nesting counted as {inner}, while the "
            f"boxes coincide -- one of them must go inside the other")
    # Rank decides WHO is outer, and by HER order, not by our id.
    arts = [Block(block_id=1, box=box, label="table", order=9),
            Block(block_id=2, box=box, label="image", order=1)]
    assert H._nesting(arts) == {1: 2}, (
        "the outer one named is not the one earlier by the model's rank")



def test_three_kinds_of_bad_sheet_get_three_different_marks():
    """A refusing sheet comes in three kinds and they may not be confused: a sheet
    with a single page number is furniture, not "the whole column went into
    pictures" at `data-image-share="0.00"`, which contradicts itself."""
    import json
    import os
    import tempfile

    import pymupdf
    from booksmith.core.page import Block, Page

    def page(i, blocks):
        return Page(index=i, width=1000, height=1400, dpi=144.0,
                    blocks=blocks, meta={"reading_order": "model_rank"})

    art = Block(block_id=0, box=(50.0, 50.0, 950.0, 1350.0), label="table",
                score=0.9, order=0)
    with tempfile.TemporaryDirectory() as tmp:
        pdf = os.path.join(tmp, "probe.pdf")
        doc = pymupdf.open()
        for _ in range(4):
            doc.new_page(width=500, height=700)
        doc.save(pdf)
        doc.close()

        det = os.path.join(tmp, "detect")
        os.makedirs(os.path.join(det, "pages"))
        pages = [
            page(0, [Block(block_id=0, box=(200.0, 1300.0, 300.0, 1340.0),
                           label="footer", score=0.8, order=0)]),
            page(1, [art]),
            page(2, []),
            page(3, [Block(block_id=0, box=(50.0, 50.0, 950.0, 600.0),
                           label="text", score=0.9, order=0, content="lines"),
                     Block(block_id=1, box=(50.0, 700.0, 950.0, 1300.0),
                           label="table", score=0.9, order=1)]),
        ]
        for p in pages:
            with open(os.path.join(det, "pages", f"{p.index:04d}.json"),
                      "w", encoding="utf-8") as f:
                json.dump(p.to_json(), f, ensure_ascii=False)
        from booksmith.processing.layout import detect as _detect
        with open(os.path.join(det, "run.json"), "w", encoding="utf-8") as f:
            json.dump({"source": {"path": pdf,
                                    "sha256": _detect._sha256(pdf)},
                       "raster": {"dpi": 144},
                       "policy": _V2.snapshot(),
                       "weights": {"layout": None}}, f, ensure_ascii=False)

        out = os.path.join(tmp, "html")
        H.build(det, out)
        book = open(os.path.join(out, "book.html"), encoding="utf-8").read()

    import re
    marks = dict(re.findall(r'<hr class="sheet" data-sheet="(\d+)"([^>]*)>', book))
    assert 'data-furniture-only' in marks["0"], (
        f"a sheet of one furniture block is marked {marks['0']!r} -- and it "
        f"holds no pictures at all")
    assert 'data-no-text' not in marks["0"], (
        "a sheet without a single picture was called gone into pictures: "
        f"{marks['0']!r}")
    assert ('data-no-text' in marks["1"]
            and 'data-furniture-only' not in marks["1"]), marks["1"]
    assert 'data-empty' in marks["2"], marks["2"]
    assert marks["3"].strip().endswith('"'), (
        f"a healthy sheet got a refusal mark: {marks['3']!r}")
    # Each mark has wording of its own -- else they differ only in name.
    for word in ("the whole column went into pictures",
                 "the model found nothing on this sheet",
                 "only furniture on this sheet"):
        assert word in book, f"the wording \"{word}\" is not in the book"


def test_the_book_is_alone_at_the_root_and_carries_itself():
    """Exactly one file at the root of a build, beside the kitchen and the
    manifest, and it points nowhere outside: over a network path a browser
    silently refuses a local script, hence `HTML_MATH` and `HTML_IMAGES` inline."""
    import json
    import os
    import re
    import tempfile

    import pymupdf

    from booksmith.processing.layout import detect as _detect
    from booksmith.core.page import Block, Page

    with tempfile.TemporaryDirectory() as tmp:
        pdf = os.path.join(tmp, "probe.pdf")
        doc = pymupdf.open()
        doc.new_page(width=500, height=700)
        doc.save(pdf)
        doc.close()

        det = os.path.join(tmp, "detect")
        os.makedirs(os.path.join(det, "pages"))
        pg = Page(index=0, width=1000, height=1400, dpi=144.0, blocks=[
            Block(block_id=0, box=(50.0, 50.0, 950.0, 400.0), label="text",
                  score=0.9, order=0, content="lines"),
            Block(block_id=1, box=(50.0, 500.0, 950.0, 1300.0), label="table",
                  score=0.9, order=1)])
        with open(os.path.join(det, "pages", "0000.json"), "w",
                  encoding="utf-8") as f:
            json.dump(pg.to_json(), f, ensure_ascii=False)
        with open(os.path.join(det, "run.json"), "w", encoding="utf-8") as f:
            json.dump({"source": {"path": pdf,
                                    "sha256": _detect._sha256(pdf)},
                       "raster": {"dpi": 144},
                       "policy": _V2.snapshot(),
                       "weights": {"layout": None}}, f, ensure_ascii=False)

        out = os.path.join(tmp, "html")
        H.build(det, out)

        in_root = sorted(os.listdir(out))
        # "Exactly one file at the root" is about what a reader meets on a double
        # click. A manifest is not a candidate for opening: it is what makes the
        # directory a book, and `core.book.Book.list`, `datasets.bench.Bench.open`
        # and the format floors all identify a book by it.
        assert in_root == ["assets", "book.html", "manifest.json"], (
            f"the build root holds {in_root}, and only book.html, assets/ "
            f"and manifest.json are expected. Everything but the book and "
            f"the fact of which book it is, is kitchen")
        with open(os.path.join(out, "manifest.json"), encoding="utf-8") as f:
            man = json.load(f)
        assert (man.get("source") or {}).get("sha256") == _detect._sha256(pdf), (
            f"the manifest does not name the scan this book was built from: "
            f"{man.get('source')}. That is the one fact it carries, and "
            f"`Bench.open` and the layout check both read it")

        with open(os.path.join(out, "book.html"), encoding="utf-8") as f:
            s = f.read()
        # What the book loads, not any link: `src=` on images and scripts plus
        # stylesheets. A plain `<a href="https://…">` is not caught: there are two,
        # both in MathJax's "About" dialog, and neither affects offline reading.
        loads = [u for u in re.findall(r'\ssrc="([^"]+)"', s)
                  if not u.startswith("data:")]
        loads += re.findall(r'<link[^>]+href="([^"]+)"', s)
        assert not loads, (
            f"the book loads from outside: {loads[:5]}. Over a network path "
            f"(\\\\wsl.localhost\\...) the browser will silently not load "
            f"these files, and the book opens without formulas and pictures, "
            f"looking sound")

        assert os.path.isdir(os.path.join(out, "assets", "blocks")), (
            "no crops in assets/blocks. They must lie as files even when "
            "inlined into the book: edits, measurements and the second level "
            "read them")


def test_the_builder_recognises_its_own_directory():
    """The "this directory is ours" mark belongs to the builder, not to callers:
    the snapshot lives in `assets/`, and a guard looking for `run.json` at the
    root refuses the directory this very command has just made."""
    import os
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        assert not H.is_our_dir(tmp), "an empty directory was called ours"

        os.makedirs(os.path.join(tmp, book.ASSETS))
        open(os.path.join(tmp, book.ASSETS, "run.json"), "w").close()
        assert H.is_our_dir(tmp), (
            "a directory with the snapshot in the kitchen was not recognised "
            "as ours -- a rebuild in place would refuse, and the advice from "
            "the build log becomes impossible to follow")


def test_the_book_carries_blocks_in_the_order_it_walked_them():
    """The book's order is checked against the block list, not assumed: all three
    instruments measure detection pages, not the built document. The expectation
    is derived independently, or reversing the walk reverses it too."""
    import json
    import os
    import tempfile

    import pymupdf

    from booksmith.processing.layout import detect as _detect
    from booksmith.processing.assemble import swap
    from booksmith.core.page import Block, Page

    with tempfile.TemporaryDirectory() as tmp:
        pdf = os.path.join(tmp, "probe.pdf")
        doc = pymupdf.open()
        doc.new_page(width=500, height=700)
        doc.save(pdf)
        doc.close()

        det = os.path.join(tmp, "detect")
        os.makedirs(os.path.join(det, "pages"))
        # Asymmetric on purpose: reversed, the order must not match itself. On
        # two blocks a reversal shows, on one it does not.
        pg = Page(index=0, width=1000, height=1400, dpi=144.0, blocks=[
            Block(block_id=0, box=(50.0, 50.0, 950.0, 300.0), label="text",
                  score=0.9, order=0, content="first"),
            Block(block_id=1, box=(50.0, 400.0, 950.0, 700.0), label="text",
                  score=0.9, order=1, content="second"),
            Block(block_id=2, box=(50.0, 800.0, 950.0, 1300.0), label="table",
                  score=0.9, order=2)])
        with open(os.path.join(det, "pages", "0000.json"), "w",
                  encoding="utf-8") as f:
            json.dump(pg.to_json(), f, ensure_ascii=False)
        with open(os.path.join(det, "run.json"), "w", encoding="utf-8") as f:
            json.dump({"source": {"path": pdf,
                                    "sha256": _detect._sha256(pdf)},
                       "raster": {"dpi": 144},
                       "policy": _V2.snapshot(),
                       "weights": {"layout": None}}, f, ensure_ascii=False)

        out = os.path.join(tmp, "html")
        H.build(det, out)
        with open(os.path.join(out, "book.html"), encoding="utf-8") as f:
            book = f.read()

        wanted = [B.anchor(0, i) for i in range(3)]
        assert swap.anchors(book) == wanted, (
            f"the book is not assembled in block order: {swap.anchors(book)} "
            f"against {wanted}. The book's order IS the reading order")

