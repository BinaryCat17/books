"""Two guards that must fire as refusals, not as NameErrors"""

import os
from backend import raster
from backend import textnorm
from backend.errors import TextError, Unmeasurable


def _with_env(name, value, fn):
    old = os.environ.get(name)
    os.environ[name] = value
    try:
        return fn()
    finally:
        if old is None:
            del os.environ[name]
        else:
            os.environ[name] = old


def test_a_non_number_crop_dpi_is_a_value_error_not_a_name_error():
    for bad in ("nan", "abc", "0", "-3"):
        try:
            _with_env("CROP_DPI", bad, lambda: raster.params(144.0))
        except ValueError as e:
            assert "CROP_DPI" in str(e), (bad, e)
        else:
            raise AssertionError(f"CROP_DPI={bad!r} was accepted")


def test_an_undeclared_normalisation_level_is_a_text_error():
    try:
        textnorm.normalize("x", "bogus")
    except TextError as e:
        assert isinstance(e, Unmeasurable)
        assert "bogus" in str(e)
    else:
        raise AssertionError("an undeclared level normalised something")


def test_a_bad_crop_dpi_does_not_break_a_path_that_names_the_resolution():
    import tempfile
    import pymupdf

    doc = pymupdf.open()
    pg = doc.new_page(width=200, height=200)
    pg.insert_text((20, 40), "a line")
    dst = os.path.join(tempfile.mkdtemp(), "c.png")
    for bad in ("nan", "abc", "0", "-3"):
        info = _with_env(
            "CROP_DPI", bad, lambda: raster.cut(doc, 0, (30, 40, 300, 100), 144.0, dst, dpi=200.0)
        )
        assert info["dpi"] == 200, (bad, info)
        assert os.path.getsize(dst) > 0
    try:
        _with_env("CROP_DPI", "0", lambda: raster.cut(doc, 0, (30, 40, 300, 100), 144.0, dst))
    except ValueError as e:
        assert "CROP_DPI" in str(e), e
    else:
        raise AssertionError("CROP_DPI=0 passed on the path that reads it")
    doc.close()


def test_cut_png_returns_the_same_cut_as_a_file():
    import tempfile
    import pymupdf

    with tempfile.TemporaryDirectory() as tmp:
        pdf = os.path.join(tmp, "p.pdf")
        doc = pymupdf.open()
        page = doc.new_page(width=300, height=400)
        page.draw_rect(pymupdf.Rect(50, 50, 150, 120), fill=(0, 0, 0))
        doc.save(pdf)
        doc.close()
        with raster.open_pdf(pdf) as d:
            facts = raster.cut(
                d, 0, (40, 40, 160, 130), 72.0, os.path.join(tmp, "c.png"), dpi=72, margin=0.0
            )
            png, facts2 = raster.cut_png(d, 0, (40, 40, 160, 130), 72.0, dpi=72, margin=0.0)
            page_png = raster.render_png(d[0], 72)
        assert png[:8] == b"\x89PNG\r\n\x1a\n"
        assert facts2 == {k: v for k, v in facts.items() if k != "file"}
        assert page_png[:4] == b"\x89PNG"
