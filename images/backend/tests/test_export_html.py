from backend import classes as policy
from backend import export_html as H
from backend import document as D
from backend import page as B
from backend import store as book

_V2 = policy.POLICIES["PP-DocLayoutV2"]


def test_book_builder_reads_the_order_rule_through_the_one_contract():
    probes = (
        "ours_top_down_left_right",
        "OURS, in bands",
        "  ours  ",
        "Ours_by_choice",
        "model_rank",
        "",
        None,
        0,
        "generation_order",
    )
    answers = {B.ours_order(v) for v in probes}
    assert answers == {True, False}, (
        "the probe set no longer contains both answers: comparing two functions that both say False proves nothing"
    )
    for v in probes:
        assert D._ours(v) == B.ours_order(v), (
            f"{v!r}: the book builder and the adapter contract diverged -- builder {D._ours(v)}, contract {B.ours_order(v)}. This is that second copy of one contract out of which a percentage is born from nothing"
        )


def test_anchor_is_page_scoped():
    assert B.anchor(42, 17) == "p0042-b17"
    assert B.anchor(0, 0) == "p0000-b0"
    assert B.anchor(1, 17) != B.anchor(2, 17)


def _sheet():
    import pymupdf

    doc = pymupdf.open()
    doc.new_page(width=720, height=506)
    return doc


def test_clipping_is_measured_with_a_tolerance_not_exactly():
    import os
    import tempfile
    from backend import raster as crop

    doc = _sheet()
    dpi = 150.0
    inside_px = [113, 74, 1332, 803]
    out_px = [113, 74, int((720 + 20) / 0.48), 803]
    with tempfile.TemporaryDirectory() as tmp:
        dst = os.path.join(tmp, "b.png")
        inside = crop.cut(doc, 0, inside_px, dpi, dst)
        assert inside["clipped_by_sheet"] is False, (
            "a box wholly inside the sheet was declared clipped -- that is float32 intersection, not a defect of the model"
        )
        out = crop.cut(doc, 0, out_px, dpi, dst)
        assert out["clipped_by_sheet"] is True, (
            "a box hanging 20 points off the sheet was NOT called clipped -- the tolerance ate a real trouble"
        )


def test_degenerate_and_inverted_boxes_are_named_by_their_own_trouble():
    import os
    import tempfile
    from backend import raster as crop

    doc = _sheet()
    with tempfile.TemporaryDirectory() as tmp:
        dst = os.path.join(tmp, "b.png")
        for box, word in (
            ([200.0, 200.0, 200.0, 300.0], "DEGENERATE"),
            ([300.0, 200.0, 200.0, 300.0], "INVERTED"),
        ):
            try:
                crop.cut(doc, 0, box, 144.0, dst)
            except ValueError as e:
                assert word in str(e), f"the box {box} was named by the wrong trouble: {str(e)[:90]!r}"
            else:
                raise AssertionError(f"the box {box} was cut silently")
        try:
            crop.cut(doc, 0, [5000.0, 5000.0, 5100.0, 5100.0], 144.0, dst)
        except ValueError as e:
            assert "does not intersect the sheet" in str(e)
        else:
            raise AssertionError("a box beyond the sheet was cut silently")


def test_negative_margin_is_refused_out_loud():
    import os
    from backend import raster as crop

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
    import pymupdf
    from backend import raster as crop

    doc = pymupdf.open()
    page = doc.new_page(width=200, height=100)
    src = pymupdf.open()
    sp = src.new_page(width=400, height=100)
    sp.insert_text((10, 50), "x")
    pix = sp.get_pixmap(dpi=180)
    img = pymupdf.open("png", pix.tobytes("png"))
    page.insert_image(
        pymupdf.Rect(0, 0, 400, 100), stream=img.convert_to_pdf() if False else pix.tobytes("png")
    )
    got = crop.native_dpi(page)
    doc.close()
    src.close()
    img.close()
    assert got is not None, "the raster covers the whole sheet, and sharpness was not determined"
    assert abs(got - 180.0) < 1.0, (
        f"sharpness {got:.1f} -- counted by the width of the SHEET, not of the placement; dividing by the sheet gives 360 and doubles it"
    )


def test_native_dpi_says_nothing_when_there_is_nothing_to_say():
    import pymupdf
    from backend import raster as crop

    doc = pymupdf.open()
    page = doc.new_page(width=200, height=100)
    page.insert_text((10, 50), "text only")
    assert crop.native_dpi(page) is None, "vector art declared a grid"
    small = pymupdf.open()
    sp = small.new_page(width=40, height=20)
    sp.insert_text((2, 15), "m")
    page.insert_image(pymupdf.Rect(0, 0, 40, 20), stream=sp.get_pixmap(dpi=600).tobytes("png"))
    got = crop.native_dpi(page)
    doc.close()
    small.close()
    assert got is None, (
        f"a stamp in the corner was declared the page's sharpness ({got}) -- the whole sheet would be cut by it"
    )


def test_crop_dpi_counts_what_will_actually_be_cut():
    from backend.driver import crop_dpi_for

    W = (112896, 1003520)
    sheet = (0.0, 0.0, 1012.0, 1466.0)
    out = (0, 0, 2024, 1466)
    without, _ = crop_dpi_for(out, 144.0, 601.0, W)
    with_sheet, why = crop_dpi_for(out, 144.0, 601.0, W, sheet=sheet)
    assert with_sheet > without + 1, (
        f"by the sheet {with_sheet:.1f}, by the full box {without:.1f} -- sharpness is counted on what is not on the paper"
    )
    inside = (0, 0, 540, 700)
    a, _ = crop_dpi_for(inside, 144.0, 601.0, W)
    b, _ = crop_dpi_for(inside, 144.0, 601.0, W, sheet=sheet)
    assert abs(a - b) < 1e-09, "the sheet changed the sharpness of a box lying inside it"


def test_crop_dpi_never_comes_from_the_environment_silently():
    from backend import raster as crop

    p = crop.params(150.0, page_native=300.0)
    assert p["dpi"] == 300.0 and p["dpi_source"] == "native_scan_dpi", p
    p2 = crop.params(150.0)
    assert p2["dpi"] == 150.0 and "as in detection" in p2["dpi_source"], p2
    assert crop.params()["dpi_source"] == "PAGE_DPI of this process", (
        "sharpness was guessed from the environment, and not a word was said about it"
    )


def test_crop_dpi_takes_the_ink_that_exists_and_invents_none():
    from backend.driver import crop_dpi_for

    W = (112896, 1003520)
    d, why = crop_dpi_for((0, 0, 273, 47), 144.0, 144.0, W)
    assert d == 144.0 and "below_model_min" == why, (d, why)
    d, why = crop_dpi_for((0, 0, 273, 47), 144.0, 601.0, W)
    assert d == 601.0 and why == "native_scan_dpi", (d, why)
    d, why = crop_dpi_for((0, 0, 540, 700), 144.0, 601.0, W)
    px = 540 / 144 * d * (700 / 144 * d)
    assert abs(px - W[1]) < 1 and why == "downscaled_to_model_max", (d, why, px)
    d, why = crop_dpi_for((0, 0, 540, 700), 144.0, 601.0, None)
    assert d == 601.0 and why == "native_scan_dpi_no_model_bounds", (d, why)


def test_nesting_survives_blocks_without_a_model_rank():
    from backend.page import Block

    box = (0.0, 0.0, 100.0, 100.0)
    pairs = ((3, None), (None, 3), (None, None), (1, 2))
    for o1, o2 in pairs:
        arts = [
            Block(block_id=1, box=box, label="table", order=o1),
            Block(block_id=2, box=box, label="image", order=o2),
        ]
        inner = D._nesting(arts)
        assert len(inner) == 1, (
            f"ranks {o1!r}/{o2!r}: nesting counted as {inner}, while the boxes coincide -- one of them must go inside the other"
        )
    arts = [
        Block(block_id=1, box=box, label="table", order=9),
        Block(block_id=2, box=box, label="image", order=1),
    ]
    assert D._nesting(arts) == {1: 2}, "the outer one named is not the one earlier by the model's rank"


def test_the_builder_recognises_its_own_directory():
    import os
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        assert not H.is_our_dir(tmp), "an empty directory was called ours"
        os.makedirs(os.path.join(tmp, book.ASSETS))
        open(os.path.join(tmp, book.ASSETS, "run.json"), "w").close()
        assert H.is_our_dir(tmp), (
            "a directory with the snapshot in the kitchen was not recognised as ours -- a rebuild in place would refuse, and the advice from the build log becomes impossible to follow"
        )
