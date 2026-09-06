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
    assumed. After the marker word moved from `наш` to `ours` these values were
    left behind, and every one of the nine then returned False from BOTH sides:
    the check compared False with False nine times and would have passed a
    broken copy whole. It was caught while translating the prose around it, not
    by the check itself and not by the battery -- the mutation that guards it
    plants a `наш` copy and so kept working by accident.
    """
    probes = ("ours_top_down_left_right", "OURS, in bands", "  ours  ",
              "Ours_by_choice", "model_rank", "", None, 0, "generation_order")
    answers = {B.ours_order(v) for v in probes}
    assert answers == {True, False}, (
        "the probe set no longer contains both answers: comparing two "
        "functions that both say False proves nothing")
    for v in probes:
        assert H._ours(v) == B.ours_order(v), (
            f"{v!r}: сборщик книги и контракт адаптера разошлись — "
            f"сборщик {H._ours(v)}, контракт {B.ours_order(v)}. Это та самая "
            f"вторая копия договора, из-за которой рождается процент из ничего")


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
            "рамка целиком внутри листа объявлена срезанной — это float32 "
            "пересечения, а не дефект модели")
        out = crop.cut(doc, 0, out_px, dpi, dst)
        assert out["clipped_by_sheet"] is True, (
            "рамка, вылезшая за лист на 20 пунктов, срезанной НЕ названа — "
            "допуск съел настоящую беду")


def test_degenerate_and_inverted_boxes_are_named_by_their_own_trouble():
    """A degenerate or an inverted box is not "off the sheet".

    Both gave an empty intersection and got the wrong diagnosis -- "does not
    meet the sheet" -- for a box in the middle of the paper, sending the reader
    after shifted coordinates.
    """
    import os
    import tempfile
    from booksmith.doc import crop
    doc = _sheet()
    with tempfile.TemporaryDirectory() as tmp:
        dst = os.path.join(tmp, "b.png")
        for box, word in (([200.0, 200.0, 200.0, 300.0], "ВЫРОЖДЕНА"),
                          ([300.0, 200.0, 200.0, 300.0], "ПЕРЕВЁРНУТА")):
            try:
                crop.cut(doc, 0, box, 144.0, dst)
            except ValueError as e:
                assert word in str(e), (
                    f"рамка {box} названа не своей бедой: {str(e)[:90]!r}")
            else:
                raise AssertionError(f"рамка {box} вырезана молча")
        # And a real "off the sheet" must stay itself.
        try:
            crop.cut(doc, 0, [5000.0, 5000.0, 5100.0, 5100.0], 144.0, dst)
        except ValueError as e:
            assert "не пересекается с листом" in str(e)
        else:
            raise AssertionError("рамка за пределами листа вырезана молча")


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
        raise AssertionError("отрицательное поле принято молча")
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
    assert got is not None, "растр на весь лист, а резкость не определилась"
    # By placement: 1000 px / 400 pt = 180 dpi. By the SHEET it would be 360.
    assert abs(got - 180.0) < 1.0, (
        f"резкость {got:.1f} — считана по ширине ЛИСТА, а не размещения; "
        f"деление на лист даёт 360 и завышает вдвое")


def test_native_dpi_says_nothing_when_there_is_nothing_to_say():
    """Vector art and a corner stamp give `None`, not a guessed number."""
    import pymupdf
    from booksmith.doc import crop

    doc = pymupdf.open()
    page = doc.new_page(width=200, height=100)
    page.insert_text((10, 50), "только текст")
    assert crop.native_dpi(page) is None, "вектор объявил решётку"

    # A corner stamp: detailed, but a fifth of the width.
    small = pymupdf.open()
    sp = small.new_page(width=40, height=20)
    sp.insert_text((2, 15), "m")
    page.insert_image(pymupdf.Rect(0, 0, 40, 20),
                      stream=sp.get_pixmap(dpi=600).tobytes("png"))
    got = crop.native_dpi(page)
    doc.close(); small.close()
    assert got is None, (
        f"марка в углу объявлена резкостью страницы ({got}) — по ней резался "
        f"бы весь лист")


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
        f"по листу {with_sheet:.1f}, по полной рамке {without:.1f} — резкость "
        f"считается по тому, чего на бумаге нет")
    # The same box wholly ON the sheet must not change when a sheet appears.
    inside = (0, 0, 540, 700)
    a, _ = crop_dpi_for(inside, 144.0, 601.0, W)
    b, _ = crop_dpi_for(inside, 144.0, 601.0, W, sheet=sheet)
    assert abs(a - b) < 1e-9, "лист изменил резкость рамки, лежащей внутри него"


def test_crop_dpi_never_comes_from_the_environment_silently():
    """An empty `CROP_DPI` is not "as in THIS process", and it names its home.

    The default moved twice, by measurement. It was "`PAGE_DPI` of the current
    process": detection of `bench/atlas` at `PAGE_DPI=150` and a build at the
    default printed "26 crops at 144 dpi" while coordinates came from 150. Then
    "same as detection", also too little -- on a real 200 dpi scan, cutting at
    144 throws away 48% of the ink in the file (measured in `crop.params`).
    Today it is the scan's OWN sharpness; the guard is unchanged: a number must
    name its source, and a silent environment may not be one.
    """
    from booksmith.doc import crop
    # own sharpness known -- it is taken, detection is irrelevant
    p = crop.params(150.0, page_native=300.0)
    assert p["dpi"] == 300.0 and p["dpi_source"] == "native_scan_dpi", p
    # none of its own -- detection, and that is said in words
    p2 = crop.params(150.0)
    assert p2["dpi"] == 150.0 and "как у детекции" in p2["dpi_source"], p2
    # neither -- the environment, and it is NAMED as a guess
    assert crop.params()["dpi_source"] == "PAGE_DPI текущего процесса", (
        "резкость угадана по окружению, и об этом не сказано ни слова")


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
            f"ранги {o1!r}/{o2!r}: вложенность посчитана как {inner}, а рамки "
            f"совпадают — одна обязана уйти внутрь другой")
    # Rank decides WHO is outer, and by HER order, not by our id.
    arts = [Block(block_id=1, box=box, label="table", order=9),
            Block(block_id=2, box=box, label="image", order=1)]
    assert H._nesting(arts) == {1: 2}, (
        "внешней названа не та, что раньше по рангу модели")


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
    assert feed.anchor_of is H.anchor_of, "doc/feed завёл свой якорь"
    assert ap.anchor_of is H.anchor_of, "doc/apply завёл свой якорь"


def test_three_kinds_of_bad_sheet_get_three_different_marks():
    """A refusing sheet comes in THREE kinds, and they may not be confused.

    There were two, and the third printed somebody else's mark: `blank` meant
    "blocks exist, no text among them", so a sheet with a single page number
    (`footer`, furniture) got the red "the whole page went to pictures" at
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
        pdf = os.path.join(tmp, "проба.pdf")
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
                           label="text", score=0.9, order=0, content="строки"),
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
        f"лист из одного служебного помечен как {marks['0']!r} — а картинок "
        f"на нём нет вовсе")
    assert 'data-no-text' not in marks["0"], (
        "лист без единой картинки назван ушедшим в картинки: "
        f"{marks['0']!r}")
    assert ('data-no-text' in marks["1"]
            and 'data-furniture-only' not in marks["1"]), marks["1"]
    assert 'data-empty' in marks["2"], marks["2"]
    assert marks["3"].strip().endswith('"'), (
        f"здоровый лист получил пометку отказа: {marks['3']!r}")
    # Each mark has wording of its own -- else they differ only in name.
    for word in ("вся полоса ушла в картинки", "модель не нашла на листе ничего",
                 "на листе только служебное"):
        assert word in book, f"надписи «{word}» в книге нет"


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
        pdf = os.path.join(tmp, "проба.pdf")
        doc = pymupdf.open()
        doc.new_page(width=500, height=700)
        doc.save(pdf)
        doc.close()

        det = os.path.join(tmp, "detect")
        os.makedirs(os.path.join(det, "pages"))
        pg = Page(index=0, width=1000, height=1400, dpi=144.0, blocks=[
            Block(block_id=0, box=(50.0, 50.0, 950.0, 400.0), label="text",
                  score=0.9, order=0, content="строки"),
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
            f"в корне сборки {in_root}, а ожидается только book.html и "
            f"assets/. Всё, кроме книги, — кухня")

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
            f"книга подгружает со стороны: {loads[:5]}. По сетевому пути "
            f"(\\\\wsl.localhost\\...) браузер эти файлы молча не загрузит, и "
            f"книга откроется без формул и картинок, выглядя исправной")

        assert os.path.isdir(os.path.join(out, "assets", "blocks")), (
            "вырезок нет в assets/blocks. Они обязаны лежать файлами даже "
            "когда вшиты в книгу: их читают правки, замеры и второй уровень")


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
        assert not H.is_our_dir(tmp), "пустой каталог признан нашим"

        os.makedirs(os.path.join(tmp, H.ASSETS))
        open(os.path.join(tmp, H.ASSETS, "run.json"), "w").close()
        assert H.is_our_dir(tmp), (
            "каталог со слепком в кухне не признан своим — пересборка на "
            "месте откажет, и совет из журнала сборки станет невыполним")

    with tempfile.TemporaryDirectory() as tmp:
        open(os.path.join(tmp, "run.json"), "w").close()
        assert H.is_our_dir(tmp), (
            "книга ПРЕЖНЕЙ раскладки объявлена чужой — она наша, просто "
            "собрана до переезда слепка")


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
        pdf = os.path.join(tmp, "проба.pdf")
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
                  score=0.9, order=0, content="первый"),
            Block(block_id=1, box=(50.0, 400.0, 950.0, 700.0), label="text",
                  score=0.9, order=1, content="второй"),
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
            f"книга сложена не в порядке блоков: {swap.anchors(book)} против "
            f"{wanted}. Порядок книги — это порядок чтения")

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
            f"ожидание порядка копится ВНУТРИ цикла (строка {inside[0].lineno}"
            f") — сторож стал тавтологичным: перевернёшь обход, перевернётся "
            f"и ожидание. Так уже было, и три порчи не поймались ни одна")

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
        "в `build` не осталось сверки `вышло != ждём` — сборщик перестал "
        "проверять, в том ли порядке сложилась книга. Настоящему прогону "
        "сравнивать нечем: приборы мерят страницы детекции, а не документ")
