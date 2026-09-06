"""The golden bench builder: two places where it could lie silently.

THIS FILE HAD NOT ONE CHECK, and every headline number of the project stands
on its product: 698 objects of 1232, 646 whole in meaning, 94.0% of the ink,
`PP-DocLayoutV2` chosen as the base of level one. Not one of the 152 earlier
checks touched `annopage.py`.

The conspiracy is between `annopage.py` and THE AnnoPage ARCHIVE, and it was
written down as prose alone. Both defects below were found and measured on
the live bench, both were fixed after the find, and both can return -- hence
pinned here.

    class order on faith    a label in the markup is an INDEX, and its name
                            comes from line N of `classes.txt`; only the SET
                            of names was checked. Swapping `Table` and
                            `Vignette` passed silently, and the measurement
                            became 1121 objects instead of 1232, 13 tables
                            instead of 124. A second source of the same map,
                            `dataset.yaml`, lies in the same archive and had
                            never been read

    truth wiped before      `truth/` was cleaned before the main loop while
    the guards              the `--truth-only` guards stood a hundred lines
                            below. On a copy of the bench the build fell
                            saying "600 pages, truth rewritten to 5" -- and
                            by that moment FIVE of 600 good files were left.
                            595 destroyed by the refusal meant to protect
                            them

The bench here is OUR OWN, tiny and synthetic: `raw/annopage` is 3.5 GB, is
on no other machine, and a check that silently skipped itself without it
would be exactly the zero from not understanding that CLAUDE.md warns of.
"""
import json
import os
import tempfile

import support

from booksmith import annopage


def _mini(root, names=None, yaml_names=None, pages=2):
    """A tiny archive of AnnoPage shape: two pages, one object each."""
    names = list(names if names is not None else annopage._classes.__doc__ or [])
    os.makedirs(os.path.join(root, "labels", "test"), exist_ok=True)
    os.makedirs(os.path.join(root, "images", "test"), exist_ok=True)
    with open(os.path.join(root, "classes.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(names) + "\n")
    if yaml_names is not None:
        with open(os.path.join(root, "dataset.yaml"), "w",
                  encoding="utf-8") as f:
            f.write("path: x\nnames:\n")
            for i, n in enumerate(yaml_names):
                f.write(f"  {i}: {n}\n")
    import cv2
    import numpy as np
    for k in range(pages):
        stem = f"p{k:03d}"
        with open(os.path.join(root, "labels", "test", stem + ".txt"), "w",
                  encoding="utf-8") as f:
            f.write("0 0.5 0.5 0.2 0.2\n")
        img = np.full((200, 150, 3), 255, np.uint8)
        img[80:120, 55:95] = 0
        cv2.imwrite(os.path.join(root, "images", "test", stem + ".jpg"), img)


def _real_names():
    """The 25 names in the order our own register declares them."""
    return (list(annopage.DIRECT) + list(annopage.DOUBTFUL)
            + list(annopage.INEXPRESSIBLE))


def test_class_order_is_checked_against_the_second_source():
    """`classes.txt` against `dataset.yaml`: a disagreement fails ALOUD.

    Can fail: drop the comparison and swapping two lines passes silently
    while the whole bench assembles under other people's labels. On the live
    archive the two maps AGREE today (25 of 25), so the guard is not being
    set in the tracks of an accident.
    """
    names = _real_names()
    swapped = list(names)
    swapped[0], swapped[1] = swapped[1], swapped[0]
    with tempfile.TemporaryDirectory() as d:
        _mini(d, names=swapped, yaml_names=names)
        try:
            annopage._classes(d)
        except annopage.AnnoPageError as e:
            assert "dataset.yaml" in str(e), (
                f"the complaint is about the wrong file: {e}")
            return
        raise AssertionError(
            "swapping two classes was accepted silently -- a label in the "
            "markup is an INDEX, and the whole truth of the bench would "
            "assemble under other people's labels")


def test_matching_sources_are_accepted():
    """The other side: matching maps do NOT fail the build.

    Without it the guard could be "fixed" by forbidding everything.
    """
    names = _real_names()
    with tempfile.TemporaryDirectory() as d:
        _mini(d, names=names, yaml_names=names)
        assert annopage._classes(d) == names


def test_a_failed_build_does_not_destroy_good_truth():
    """A guard's refusal does NOT destroy the truth already lying there.

    That very defect: the build fell with truthful words, having already
    erased 595 files of 600. The check lays down knowingly foreign truth,
    fails the build by the `--truth-only` guard (a pdf that is not there),
    and demands the foreign truth be left untouched -- because what to do
    about a mismatch is for a human to decide, not for a fragment of a build.
    """
    names = _real_names()
    with tempfile.TemporaryDirectory() as d:
        root = os.path.join(d, "raw")
        out = os.path.join(d, "out")
        _mini(root, names=names, yaml_names=names)
        tdir = os.path.join(out, "truth")
        os.makedirs(tdir)
        for k in range(7):
            with open(os.path.join(tdir, f"{k:04d}.json"), "w",
                      encoding="utf-8") as f:
                json.dump({"marker": "the truth that was already here"}, f)
        before = sorted(os.listdir(tdir))
        try:
            annopage.build(root, out, split="test", truth_only=True,
                           log=lambda *a: None)
        except annopage.AnnoPageError:
            pass
        else:
            raise AssertionError(
                "a build with --truth-only and no pdf went through -- there "
                "is no guard at all")
        after = sorted(os.listdir(tdir))
        assert after == before, (
            f"the failed build touched the truth: {len(before)} files "
            f"before, {len(after)} after. A guard that destroys what it "
            f"protects is worse than a missing one: it also declares itself "
            f"to have fired")


def test_the_sheet_follows_the_declared_knob():
    """The sheet size is computed FROM `PAGE_DPI`, not from a wired-in 0.5.

    The size means one thing: rendering at `PAGE_DPI` must return exactly the
    source raster. A wired 0.5 is right only at the default 144; at 288 the
    bench would assemble about a raster twice as fine as declared, while the
    truth went on writing "dpi: 144.0". The size comparison in `metrics`
    caught that -- someone else's file -- and the builder itself kept quiet.

    Can fail: put `w * 0.5` back and the sheet at 288 stays as it was.
    """
    import pymupdf

    from booksmith.run import knobs

    names = _real_names()
    seen = {}
    for dpi in ("144", "288"):
        with tempfile.TemporaryDirectory() as d:
            root, out = os.path.join(d, "raw"), os.path.join(d, "out")
            _mini(root, names=names, yaml_names=names)
            old = os.environ.get("PAGE_DPI")
            os.environ["PAGE_DPI"] = dpi
            try:
                knobs.knob.cache_clear() if hasattr(knobs.knob, "cache_clear") \
                    else None
                man = annopage.build(root, out, split="test",
                                     log=lambda *a: None)
            finally:
                if old is None:
                    os.environ.pop("PAGE_DPI", None)
                else:
                    os.environ["PAGE_DPI"] = old
            assert man["PAGE_DPI"] == float(dpi), (
                f"the manifest did not record the knob: {man['PAGE_DPI']} "
                f"at {dpi}")
            doc = pymupdf.open(os.path.join(out, "annopage.pdf"))
            seen[dpi] = doc[0].rect.width
            doc.close()
    assert abs(seen["144"] - 2 * seen["288"]) < 0.01, (
        f"the sheet did not follow the knob: at 144 the width is "
        f"{seen['144']} pt, at 288 it is {seen['288']} pt, and it should be "
        f"half as much. So the scale is wired in, and a bench assembled at "
        f"another PAGE_DPI lies about its own raster silently")
