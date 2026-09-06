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
