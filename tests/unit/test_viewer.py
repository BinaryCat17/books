"""The viewer's data, by name inside a store: a run as it is opened, one of
its pages as the builder's own data pass gives it, the metric's pairs with
the truth side withheld from a user, and the scan's page and one block's
crop as PNG."""
import dataclasses
import os
import shutil
import struct

import pytest

import support
from booksmith import service
from booksmith.core import book
from booksmith.core.errors import Refusal
from booksmith.processing.assemble import html as html_mod

BOOK = "bench/slovar"


def _png_size(b):
    assert b[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG"
    return struct.unpack(">II", b[16:24])


@pytest.fixture
def store(tmp_path, monkeypatch, slovar, served_endpoint):
    """A data home holding the drawn bench and one detect run of the truth
    served as a model. The bench is copied piece by piece: the session's
    bench directory may carry runs other checks filed there."""
    home = tmp_path / "home"
    dest = home / "bench" / "slovar"
    dest.mkdir(parents=True)
    src = os.path.dirname(slovar.truth_dir)
    shutil.copy2(os.path.join(src, "manifest.json"), dest)
    shutil.copy2(slovar.pdf, dest)
    shutil.copytree(slovar.truth_dir, dest / "truth")
    monkeypatch.setenv("BOOKSMITH_HOME", str(home))
    with support.said():
        rd = service.detect(str(home), str(dest),
                            {"LAYOUT_ADAPTER": "served", "LAYOUT_ENDPOINT": served_endpoint})
    return str(home), rd


def test_a_run_and_its_page_are_the_builders_own_data(store):
    home, rd = store
    r = service.run(home, BOOK, "detect", "truth")
    data = html_mod.gather(rd, verify=False)
    assert r["pages"] == [p.index for p in data.pages] and len(r["pages"]) == 13
    assert r["level"] == "detect" and r["truth"] is True and r["observed"] is False
    assert r["identity"] and len(r["identity"]) == 64
    assert r["policy"] == data.policy.snapshot() and r["dpi"] == data.page_dpi
    got = service.page(home, BOOK, "detect", "truth", 3)
    assert got == dataclasses.asdict(data.pages[3])
    assert got["blocks"], "an empty page proves nothing"
    for b in got["blocks"]:
        assert b["role"] == data.policy.role(b["label"])
        assert b["anchor"] == f"p0003-b{b['block_id']}"
    with pytest.raises(Refusal, match="no page 99"):
        service.page(home, BOOK, "detect", "truth", 99)
    with pytest.raises(Refusal, match="no detect run"):
        service.page(home, BOOK, "detect", "other", 0)


def test_the_pairs_carry_the_truth_only_for_the_truth_side(store):
    home, rd = store
    mine = service.pairs(home, BOOK, "detect", "truth", 2, truth_side=True)
    theirs = service.pairs(home, BOOK, "detect", "truth", 2, truth_side=False)
    assert mine["compared"] and mine["labelled"] == "not_said"
    assert len(mine["truth"]) == len(mine["pairs"]) and mine["truth"]
    assert all(e["verdict"] == "matched" and e["label_ok"] for e in mine["pairs"])
    assert [e["truth"] for e in mine["pairs"]] == [t["anchor"] for t in mine["truth"]]
    assert "truth" not in theirs and "out_of_scope" not in theirs
    assert all("truth" not in e for e in theirs["pairs"])
    assert [e["run"] for e in theirs["pairs"]] == [e["run"] for e in mine["pairs"]]
    # A page truth says is not labelled is not compared, and the answer says so.
    from booksmith.core.page import write_json
    import json
    tp = os.path.join(home, "bench", "slovar", "truth", "0002.json")
    with open(tp, encoding="utf-8") as f:
        t = json.load(f)
    t["meta"]["labelled"] = False
    write_json(tp, t)
    off = service.pairs(home, BOOK, "detect", "truth", 2, truth_side=True)
    assert off["compared"] is False and off["labelled"] == "no"
    assert off["pairs"] == [] and off["extras"] == [] and off["truth"]
    # A book without truth has nothing to pair against.
    b = book.Book.open(os.path.join(home, "bench", "slovar"))
    other = os.path.join(home, "processed", "copy")
    os.makedirs(os.path.dirname(other))
    shutil.copytree(b.root, other)
    shutil.rmtree(os.path.join(other, "truth"))
    with pytest.raises(Refusal, match="no truth"):
        service.pairs(home, "processed/copy", "detect", "truth", 0)


def test_the_page_image_is_bounded_cached_and_the_crop_is_one_block(store):
    home, rd = store
    service._render.cache_clear()
    small = service.page_image(home, BOOK, 0, dpi=36)
    big = service.page_image(home, BOOK, 0, dpi=72)
    (w1, h1), (w2, h2) = _png_size(small), _png_size(big)
    assert w1 and abs(w2 - 2 * w1) <= 2 and abs(h2 - 2 * h1) <= 2
    assert service.page_image(home, BOOK, 0, dpi=36) == small
    assert service._render.cache_info().hits == 1
    for dpi in (1, 5000):
        with pytest.raises(Refusal, match="outside"):
            service.page_image(home, BOOK, 0, dpi=dpi)
    with pytest.raises(Refusal, match="no page 99"):
        service.page_image(home, BOOK, 99)
    pg = service.page(home, BOOK, "detect", "truth", 0)
    blk = pg["blocks"][0]
    png = service.crop_png(home, BOOK, "detect", "truth", blk["anchor"])
    cw, ch = _png_size(png)
    # The crop is the box and no more: narrower than the page on both axes.
    x0, y0, x1, y1 = blk["box"]
    assert cw < w2 * 4 and ch < h2 * 4
    assert abs(cw / ch - (x1 - x0) / (y1 - y0)) < 0.15
    for bad in ("p0000", "zzz", "p0000-b999", "p0099-b0"):
        with pytest.raises(Refusal):
            service.crop_png(home, BOOK, "detect", "truth", bad)
