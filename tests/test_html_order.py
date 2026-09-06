"""The book builder and the reading-order contract.

The `reading order` field has TWO readers -- the metric's guard and the book
builder -- and only the first was watched: a skeptic put a drifted copy of the
rule (no case folding) back into `doc/html._ours` and all sixty checks stayed
green. The cost is known from next door: on `bench/hard36` the metric printed
"reading order agrees 73%" where order is marked on none of the 36 pages. A
number out of nothing is born of two copies of one contract.
"""
from booksmith.doc import html as H
from booksmith.models import base as B


def test_book_builder_reads_the_order_rule_through_the_one_contract():
    """`doc/html` must call `models.base.ours_order`, not a copy of its own.

    THE PROBE SET MUST CONTAIN BOTH ANSWERS, and that is asserted rather than
    assumed. After the marker word moved from the Russian one to `ours` these
    values were left behind, and every one of the nine then returned False from
    BOTH sides: the check compared False with False nine times and would have
    passed a broken copy whole. It was caught while translating the prose
    around it, not by the check itself and not by the battery -- the mutation
    that guards it plants a Russian-worded copy and so kept working by
    accident.
    """
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
    """The anchor is PER PAGE: `block_id` restarts on every page.

    A book-wide `b17` over five hundred pages would give five hundred identical
    anchors, and a second-level swap would land in the wrong place.
    """
    assert H.anchor_of(42, 17) == "p0042-b17"
    assert H.anchor_of(0, 0) == "p0000-b0"
    assert H.anchor_of(1, 17) != H.anchor_of(2, 17)


# --- crops: the builder's contract with the model's box ---------------------
#
# One contract, one file: `doc/html` cuts with `doc/crop` by the model's box
# and prints its numbers into the caption. Each check below closes a trouble
# reproduced on `bench/atlas`.

def _sheet():
    """An empty 720x506 pt sheet in memory. No bench: this must run in any
    tree, not only where the bench is cut."""
    import pymupdf
    doc = pymupdf.open()
    doc.new_page(width=720, height=506)
    return doc


def test_clipping_is_measured_with_a_tolerance_not_exactly():
    """The "clipped by the sheet" flag at a dpi with no binary-exact scale.

    pymupdf holds coordinates in single precision and runs them through float32
    again when intersecting. On `bench/atlas` at `PAGE_DPI` = 144 the scale
    72/144 = 0.5 is exact and 0 of 28 were clipped; at 150, 28 of 28, and 26
    crops of 26 got "the box left the sheet" over a disagreement of 1.7e-05 pt.

    AND THE REVERSE: a real clip must stay visible. A metric that cannot fire
    is not proven.
    """
    import os
    import tempfile
    from booksmith.doc import crop
    doc = _sheet()
    dpi = 150.0                       # 72/150 = 0.48 -- NOT binary-exact
    # The box is IN PIXELS, and not round on purpose: at 100 and 300 px the
    # points come out whole and the check would be green on broken code. 113 px
    # gives 54.239999999999995 pt -- what it used to fail on.
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
    """A degenerate or an inverted box is not "off the sheet".

    Both gave an empty intersection and got the wrong diagnosis -- "does not
    meet the sheet" -- for a box in the middle of the paper, sending the reader
    after shifted coordinates.

    THE PROBE WORDS ARE `doc/crop`'s OWN, and that file is still Russian: this
    check greps its message, so the words stay as they are until it is
    translated.
    """
    import os
    import tempfile
    from booksmith.doc import crop
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
    """A negative `CROP_MARGIN` CUTS the model's box instead of giving margin.

    Before the fix: `CROP_MARGIN=-0.1` on the box (96, 96, 192, 144) pt
    returned (105.6, 100.8, 182.4, 139.2) -- a tenth eaten off each side --
    with both clip flags False. Editing the model's box is forbidden, hence a
    failure and not a silent clamp to zero.
    """
    import os
    from booksmith.doc import crop
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
    """Native sharpness is counted from the image's PLACEMENT width.

    A spread scan is WIDER than the sheet: `books prepare` halves it and lays
    both halves with `show_pdf_page`, so a 2867 px raster sits on 688 pt while
    the sheet is 278 pt. Dividing by the sheet overstated the grid by the
    factor the raster is wider -- up to 2.47x on four books of six. `djvudump`
    declares 300 / 600 / 300 dpi on three books of three; the new formula
    agrees, the old one does not. `native_dpi` did not appear in `tests/` at
    all.
    """
    import pymupdf
    from booksmith.doc import crop

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
    from booksmith.doc import crop

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
    """Sharpness counts the box's INTERSECTION with the sheet, not the box.

    `crop.cut` cuts the intersection -- the model's box may hang off the paper.
    By the FULL box, one hanging over by half got 83.7 dpi instead of 118.4, so
    the model's window was never filled. On the bench such boxes are 28 of
    33 640 and hang over by at most 4.8 px -- real data never caught it, but
    the two numbers must be counted on one rectangle.
    """
    from booksmith.read.run import crop_dpi_for
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
    """An empty `CROP_DPI` is not "as in THIS process", and it names its home.

    The default moved twice, by measurement. It was "`PAGE_DPI` of the current
    process": detection of `bench/atlas` at `PAGE_DPI=150` and a build at the
    default printed "26 crops at 144 dpi" while coordinates came from 150. Then
    "same as detection", also too little -- on a real 200 dpi scan, cutting at
    144 throws away 48% of the ink in the file (measured in `crop.params`).
    Today it is the scan's OWN sharpness; the guard is unchanged: a number must
    name its source, and a silent environment may not be one.

    The two probe words below are `doc/crop`'s own answers and stay Russian
    until that file is translated.
    """
    from booksmith.doc import crop
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
    """Crop sharpness is a rule: all there is, but no more than the window.

    None of the three is ours: sharpness from the scan, bounds from the model
    (`Reader.pixels`), box size from the detector. Above our own grid we NEVER
    go -- that would invent dots and call them reading.
    """
    from booksmith.read.run import crop_dpi_for
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
    """`Block.order = None` is allowed OUTRIGHT -- the build may not fall.

    Three adapters of four give no rank (yolox and both docling), and in the
    fourth it is empty for exactly what the first level cuts out as pictures
    (100% of `image`, `figure_title`, `table`). A "rank / no rank" pair on one
    rectangle brought the WHOLE book down: `TypeError: '>=' not supported
    between instances of 'NoneType' and 'int'`.
    """
    from booksmith.models.base import Block
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


def test_the_anchor_rule_has_exactly_one_home():
    """The block name is built by `doc/html.anchor_of` and by nobody else.

    TWO private copies existed, in `doc/feed` and `doc/apply`, and they would
    have drifted silently: feed.json calling fragments by one set of names, the
    book and blocks.json by another, `books apply` answering "no such anchor in
    the book" for every read block. Checked by object identity: equal strings
    hold only until the first edit to one copy.
    """
    from booksmith.doc import apply as ap
    from booksmith.doc import feed
    assert feed.anchor_of is H.anchor_of, "doc/feed made its own anchor"
    assert ap.anchor_of is H.anchor_of, "doc/apply made its own anchor"


def test_three_kinds_of_bad_sheet_get_three_different_marks():
    """A refusing sheet comes in THREE kinds, and they may not be confused.

    There were two, and the third printed somebody else's mark: `blank` meant
    "blocks exist, no text among them", so a sheet with a single page number
    (`footer`, furniture) got the red "the whole column went into pictures" at
    `data-image-share="0.00"` -- an element contradicting itself. Measured:
    `bench/atlas` p. 0.
    """
    import json
    import os
    import tempfile

    import pymupdf
    from booksmith.models.base import Block, Page

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
        from booksmith import detect as _detect
        with open(os.path.join(det, "run.json"), "w", encoding="utf-8") as f:
            json.dump({"source": {"path": pdf,
                                    "sha256": _detect._sha256(pdf)},
                       "raster": {"dpi": 144},
                       "weights": {"layout": None}}, f, ensure_ascii=False)

        out = os.path.join(tmp, "html")
        H.build(det, out, log=lambda *_: None)
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
    """EXACTLY ONE file at the root of a build, and it points nowhere outside.

    The layout: the book is opened by double click, and a root holding four
    json files and a two-megabyte js beside it leaves the reader guessing which
    one to open. The kitchen moves into `assets/`.

    Self-sufficiency is paid for: at `HTML_MATH=local` MathJax sat in a
    neighbouring file, and the book opened over a network path
    (`\\\\wsl.localhost\\...` from Windows) showed formulas as RAW LaTeX --
    Chromium silently refuses a local script from a UNC path, the console is
    empty, and the book looks built. Images would go the same way. Hence the
    defaults `HTML_MATH=inline`, `HTML_IMAGES=inline`.

    Crops stay files in `assets/blocks` ALWAYS: edits, measurements and the
    second level read them.
    """
    import json
    import os
    import re
    import tempfile

    import pymupdf

    from booksmith import detect as _detect
    from booksmith.models.base import Block, Page

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
                       "weights": {"layout": None}}, f, ensure_ascii=False)

        out = os.path.join(tmp, "html")
        H.build(det, out, log=lambda *_: None)

        in_root = sorted(os.listdir(out))
        assert in_root == ["assets", "book.html"], (
            f"the build root holds {in_root}, and only book.html and assets/ "
            f"are expected. Everything but the book is kitchen")

        with open(os.path.join(out, "book.html"), encoding="utf-8") as f:
            s = f.read()
        # What the book LOADS, not any link: `src=` on images and scripts plus
        # stylesheets. A plain `<a href="https://…">` is not caught -- there
        # are two, both in MathJax's "About" dialog, and neither affects
        # offline reading.
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
    """The "this directory is ours" mark belongs to the BUILDER, not callers.

    The "do not overwrite what is not ours" guard in `cli.py` looked for
    `run.json` at the ROOT. The snapshot moved into `assets/`, and the guard
    began refusing a directory this very command had made a minute earlier --
    with a LIE: "this is probably a book of the previous pipeline", of which
    none are left. Under the same refusal fell the advice the build itself
    prints: "the book rebuilds without it -- `books html
    <book>/assets/source`".

    The mark lives next to whoever WRITES the snapshot; a string typed in
    another file drifts silently, and did. The old layout counts as ours TOO.
    """
    import os
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        assert not H.is_our_dir(tmp), "an empty directory was called ours"

        os.makedirs(os.path.join(tmp, H.ASSETS))
        open(os.path.join(tmp, H.ASSETS, "run.json"), "w").close()
        assert H.is_our_dir(tmp), (
            "a directory with the snapshot in the kitchen was not recognised "
            "as ours -- a rebuild in place would refuse, and the advice from "
            "the build log becomes impossible to follow")

    with tempfile.TemporaryDirectory() as tmp:
        open(os.path.join(tmp, "run.json"), "w").close()
        assert H.is_our_dir(tmp), (
            "a book of the OLD layout was declared alien -- it is ours, "
            "only built before the snapshot moved")


def test_the_book_carries_blocks_in_the_order_it_walked_them():
    """The book's order is CHECKED against the block list, not assumed.

    The builder walks `page.blocks` as they come and the book inherits their
    order -- the model's rank or our rule. Nothing checked that: a skeptic
    reversed the walk with one word (`reversed`) and the battery stayed green,
    201 checks, 0 failures. The book would read backwards, and all three
    instruments measure DETECTION pages, not the built document.

    SUCH A GUARD IS EASY TO MAKE TAUTOLOGICAL, and the first draft was: the
    expectation accumulated inside the loop it guards -- reverse the walk and
    the expectation reverses with it. Three corruptions (reversed, off by one,
    last one dropped) were caught by none. Hence the second half: the
    expectation is derived from `page.blocks` INDEPENDENTLY.
    """
    import ast
    import json
    import os
    import tempfile

    import pymupdf
    import support

    from booksmith import detect as _detect
    from booksmith.doc import swap
    from booksmith.models.base import Block, Page

    with tempfile.TemporaryDirectory() as tmp:
        pdf = os.path.join(tmp, "probe.pdf")
        doc = pymupdf.open()
        doc.new_page(width=500, height=700)
        doc.save(pdf)
        doc.close()

        det = os.path.join(tmp, "detect")
        os.makedirs(os.path.join(det, "pages"))
        # ASYMMETRIC on purpose: reversed, the order must not match itself. On
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
                       "weights": {"layout": None}}, f, ensure_ascii=False)

        out = os.path.join(tmp, "html")
        H.build(det, out, log=lambda *_: None)
        with open(os.path.join(out, "book.html"), encoding="utf-8") as f:
            book = f.read()

        wanted = [H.anchor_of(0, i) for i in range(3)]
        assert swap.anchors(book) == wanted, (
            f"the book is not assembled in block order: {swap.anchors(book)} "
            f"against {wanted}. The book's order IS the reading order")

    # THE EXPECTATION MAY NOT BE DERIVED FROM THE WALK, and only the source can
    # say so: a tautological guard behaves on healthy code exactly like an
    # honest one.
    t = support.tree("doc/html.py")
    fn = next(n for n in ast.walk(t)
              if isinstance(n, ast.FunctionDef) and n.name == "build")
    loops = [n for n in ast.walk(fn) if isinstance(n, ast.For)]
    for c in loops:
        inside = [n for n in ast.walk(c)
                  if isinstance(n, ast.Call)
                  and isinstance(n.func, ast.Attribute)
                  and isinstance(n.func.value, ast.Name)
                  and n.func.value.id == "expected"
                  and n.func.attr == "append"]
        assert not inside, (
            f"the order expectation accumulates INSIDE the loop (line "
            f"{inside[0].lineno}) -- the guard has become tautological: "
            f"reverse the walk and the expectation reverses with it. This has "
            f"happened before, and three corruptions were caught by none")

    # AND THE GUARD MUST BE IN PLACE. The check above compares the order
    # itself, so it would not notice the guard leaving THE BUILDER -- the book
    # still builds correctly. The guard is for a real run, where nobody
    # compares. Proved by corruption: `if got != expected` -> `if False` fails
    # no check.
    check_count = [n for n in ast.walk(fn)
              if isinstance(n, ast.Compare)
              and isinstance(n.left, ast.Name) and n.left.id == "got"
              and any(isinstance(o, ast.NotEq) for o in n.ops)]
    assert check_count, (
        "no `got != expected` comparison is left in `build` -- the builder "
        "stopped checking whether the book came out in the right order. A "
        "real run has nothing to compare with: the instruments measure "
        "detection pages, not the document")
