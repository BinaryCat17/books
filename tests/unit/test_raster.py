"""Two NameErrors the package move left in guards, pinned.

`core/raster.py` caught a `Refusal` it never imported, so `CROP_DPI=nan`,
the exact input the guard three lines above it was written for, died with
a NameError instead of being counted as a failed crop. `core/textnorm.py`
raised a `TextError` it could not see, so a misspelt `--norm` was a
traceback instead of "could not count". Both found by the step-1 review,
neither by the battery: no probe fed either guard the bad value.
"""
import os

from booksmith.core import raster, textnorm
from booksmith.core.errors import TextError, Unmeasurable


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
    """Our knob's error used to be charged to the model.

    `books read` and `books crop` decide each crop's resolution themselves and
    never use `CROP_DPI` -- but `params` was called unconditionally and
    validated it anyway, so `CROP_DPI=0` raised a ValueError the read driver
    files as "crop failed" and `report()` prints as "the model's box is
    degenerate or lies off the sheet. That is its defect, not ours."

    The margin is a different matter and still comes from the environment:
    the reading path applies it.
    """
    import tempfile
    import pymupdf
    doc = pymupdf.open()
    pg = doc.new_page(width=200, height=200)
    pg.insert_text((20, 40), "a line")
    dst = os.path.join(tempfile.mkdtemp(), "c.png")
    for bad in ("nan", "abc", "0", "-3"):
        info = _with_env("CROP_DPI", bad, lambda: raster.cut(
            doc, 0, (30, 40, 300, 100), 144.0, dst, dpi=200.0))
        assert info["dpi"] == 200, (bad, info)
        assert os.path.getsize(dst) > 0
    # And the value is still refused where it IS used.
    try:
        _with_env("CROP_DPI", "0", lambda: raster.cut(
            doc, 0, (30, 40, 300, 100), 144.0, dst))
    except ValueError as e:
        assert "CROP_DPI" in str(e), e
    else:
        raise AssertionError("CROP_DPI=0 passed on the path that reads it")
    doc.close()
