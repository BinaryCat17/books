"""What a store other than the admin's may run: a preset whole, or the defaults."""
import pytest

from booksmith import service
from booksmith.core.errors import Refusal


def test_a_user_store_runs_a_preset_whole_or_the_defaults_and_the_admin_anything(tmp_path):
    presets = {"fast": {"PAGE_DPI": 72}}
    user = str(tmp_path / "alice")
    service.check(user, {"PAGE_DPI": "72"}, presets)
    service.check(user, {}, presets)
    with pytest.raises(Refusal):
        service.check(user, {"PAGE_DPI": "73"}, presets)
    with pytest.raises(Refusal):
        service.check(user, {"PAGE_DPI": "72", "CROP_MARGIN": "0"}, presets)
    service.check(service.ADMIN, {"PAGE_DPI": "73"}, presets)
    with pytest.raises(Refusal):
        service.detect(user, str(tmp_path / "elsewhere" / "book.pdf"), {})
