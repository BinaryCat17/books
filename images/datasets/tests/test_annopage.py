"""The golden bench builder: two places where it could lie silently"""

import json
import os
import tempfile
from datasets import identity as stamp
from datasets import annopage


def _mini(root, names=None, yaml_names=None, pages=2):
    if names is None:
        raise AssertionError("_mini needs names= -- there is no sane default")
    names = list(names)
    os.makedirs(os.path.join(root, "labels", "test"), exist_ok=True)
    os.makedirs(os.path.join(root, "images", "test"), exist_ok=True)
    with open(os.path.join(root, "classes.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(names) + "\n")
    if yaml_names is not None:
        with open(os.path.join(root, "dataset.yaml"), "w", encoding="utf-8") as f:
            f.write("path: x\nnames:\n")
            for i, n in enumerate(yaml_names):
                f.write(f"  {i}: {n}\n")
    import cv2
    import numpy as np

    for k in range(pages):
        stem = f"p{k:03d}"
        with open(os.path.join(root, "labels", "test", stem + ".txt"), "w", encoding="utf-8") as f:
            f.write("0 0.5 0.5 0.2 0.2\n")
        img = np.full((200, 150, 3), 255, np.uint8)
        img[80:120, 55:95] = 0
        cv2.imwrite(os.path.join(root, "images", "test", stem + ".jpg"), img)


def _real_names():
    return list(annopage.DIRECT) + list(annopage.DOUBTFUL) + list(annopage.INEXPRESSIBLE)


def test_class_order_is_checked_against_the_second_source():
    names = _real_names()
    swapped = list(names)
    swapped[0], swapped[1] = (swapped[1], swapped[0])
    with tempfile.TemporaryDirectory() as d:
        _mini(d, names=swapped, yaml_names=names)
        try:
            annopage._classes(d)
        except annopage.AnnoPageError as e:
            assert "dataset.yaml" in str(e), f"the complaint is about the wrong file: {e}"
            return
        raise AssertionError(
            "swapping two classes was accepted silently -- a label in the markup is an INDEX, and the whole truth of the bench would assemble under other people's labels"
        )


def test_matching_sources_are_accepted():
    names = _real_names()
    with tempfile.TemporaryDirectory() as d:
        _mini(d, names=names, yaml_names=names)
        assert annopage._classes(d) == names


def test_a_failed_build_does_not_destroy_good_truth():
    names = _real_names()
    with tempfile.TemporaryDirectory() as d:
        root = os.path.join(d, "raw")
        out = os.path.join(d, "out")
        _mini(root, names=names, yaml_names=names)
        tdir = os.path.join(out, "truth")
        os.makedirs(tdir)
        for k in range(7):
            with open(os.path.join(tdir, f"{k:04d}.json"), "w", encoding="utf-8") as f:
                json.dump({"marker": "the truth that was already here"}, f)
        before = sorted(os.listdir(tdir))
        try:
            annopage.build(root, out, split="test", truth_only=True)
        except annopage.AnnoPageError:
            pass
        else:
            raise AssertionError(
                "a build with --truth-only and no pdf went through -- there is no guard at all"
            )
        after = sorted(os.listdir(tdir))
        assert after == before, (
            f"the failed build touched the truth: {len(before)} files before, {len(after)} after. A guard that destroys what it protects is worse than a missing one: it also declares itself to have fired"
        )


def test_the_sheet_follows_the_declared_knob():
    import pymupdf
    from datasets import knobs

    names = _real_names()
    seen = {}
    for dpi in ("144", "288"):
        with tempfile.TemporaryDirectory() as d:
            root, out = (os.path.join(d, "raw"), os.path.join(d, "out"))
            _mini(root, names=names, yaml_names=names)
            old = os.environ.get("PAGE_DPI")
            os.environ["PAGE_DPI"] = dpi
            assert not hasattr(knobs.knob, "cache_clear"), (
                "`knobs.knob` is memoised now: this sweep sets PAGE_DPI per pass and would read the first value every time, reporting agreement it never measured"
            )
            try:
                man = annopage.build(root, out, split="test")
            finally:
                if old is None:
                    os.environ.pop("PAGE_DPI", None)
                else:
                    os.environ["PAGE_DPI"] = old
            assert man["PAGE_DPI"] == float(dpi), (
                f"the manifest did not record the knob: {man['PAGE_DPI']} at {dpi}"
            )
            doc = pymupdf.open(os.path.join(out, "annopage.pdf"))
            seen[dpi] = doc[0].rect.width
            doc.close()
    assert abs(seen["144"] - 2 * seen["288"]) < 0.01, (
        f"the sheet did not follow the knob: at 144 the width is {seen['144']} pt, at 288 it is {seen['288']} pt, and it should be half as much. So the scale is wired in, and a bench assembled at another PAGE_DPI lies about its own raster silently"
    )


def test_a_refused_build_leaves_the_golden_bench_untouched():
    import shutil
    import tempfile

    tmp = tempfile.mkdtemp()
    root, out = (os.path.join(tmp, "raw"), os.path.join(tmp, "out"))
    names = _real_names()
    _mini(root, names=names, yaml_names=names, pages=6)
    annopage.build(root, out, split="test")
    tdir = os.path.join(out, "truth")
    was = {n: open(os.path.join(tdir, n), encoding="utf-8").read() for n in os.listdir(tdir)}
    man_was = open(os.path.join(out, "manifest.json"), encoding="utf-8").read()
    pdf_was = open(os.path.join(out, "annopage.pdf"), "rb").read()
    try:
        annopage.build(root, out, split="test", limit=3, truth_only=True)
    except annopage.AnnoPageError:
        pass
    else:
        raise AssertionError("the mismatched --truth-only build did not refuse")
    now = {n: open(os.path.join(tdir, n), encoding="utf-8").read() for n in os.listdir(tdir)}
    assert now == was, (
        f"a refused build changed the truth: {len(was)} files -> {len(now)}. This is the accident that cost 595 of 600, arriving again"
    )
    assert open(os.path.join(out, "manifest.json"), encoding="utf-8").read() == man_was, (
        "the passport moved"
    )
    assert open(os.path.join(out, "annopage.pdf"), "rb").read() == pdf_was, (
        "the pdf moved while the truth did not"
    )
    left = sorted(n for n in os.listdir(out) if n.endswith(".new") or n.endswith(".previous"))
    assert not left, (
        f"a refused build left {left} beside the golden bench -- a partial second copy of the truth, in a directory git tracks and does not ignore, with nothing to say which of the two is the bench"
    )
    _mini(root, names=names, yaml_names=names, pages=4)
    real = stamp.sha256

    def boom(path):
        if path.endswith(".new"):
            raise RuntimeError("interrupted between the pdf and the swap")
        return real(path)

    stamp.sha256 = boom
    try:
        annopage.build(root, out, split="test")
    except RuntimeError:
        pass
    else:
        raise AssertionError("the staged crash did not happen")
    finally:
        stamp.sha256 = real
    now = {n: open(os.path.join(tdir, n), encoding="utf-8").read() for n in os.listdir(tdir)}
    assert now == was, "the truth moved while the pdf and manifest did not"
    assert open(os.path.join(out, "annopage.pdf"), "rb").read() == pdf_was, (
        "the pdf was replaced while the truth was not: the truth now describes one sample and the pdf beside it holds another"
    )
    assert open(os.path.join(out, "manifest.json"), encoding="utf-8").read() == man_was, (
        "the passport moved alone"
    )
    left = sorted(n for n in os.listdir(out) if n.endswith(".new") or n.endswith(".previous"))
    assert not left, f"the crash left {left} behind"
    shutil.rmtree(tmp, ignore_errors=True)
