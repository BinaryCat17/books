"""The service: a store's books, and what a store other than the admin's may run."""
import json
import os

import pytest

from booksmith import service
from booksmith.core.errors import Refusal


def test_a_user_store_runs_a_preset_whole_and_the_admin_anything(tmp_path):
    presets = {"fast": {"PAGE_DPI": "72"}}
    user = str(tmp_path / "alice")
    service.check(user, {"PAGE_DPI": "72"}, presets)
    with pytest.raises(Refusal):
        service.check(user, {"PAGE_DPI": "73"}, presets)
    with pytest.raises(Refusal):
        service.check(user, {"PAGE_DPI": "72", "CROP_MARGIN": "0"}, presets)
    service.check(service.ADMIN, {"PAGE_DPI": "73"}, presets)


def test_a_store_lists_its_books(tmp_path):
    store = tmp_path / "bob"
    (store / "processed" / "one").mkdir(parents=True)
    (store / "processed" / "one" / "manifest.json").write_text(
        json.dumps({"book": "one", "source": {"name": "one.pdf", "sha256": "x"}}))
    (store / "processed" / "not-a-book").mkdir()
    assert service.books(str(store)) == [os.path.join("processed", "one")]
