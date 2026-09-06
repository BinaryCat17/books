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
    # NO DEFAULT WORTH THE NAME. This read `annopage._classes.__doc__ or []`,
    # and `_classes` has no docstring -- so the fallback was `[]` and
    # `classes.txt` would have been a lone newline; had a docstring ever been
    # added, `list(str)` would have given a list of single CHARACTERS. Every
    # caller passes `names=`, so the branch was dead as well as wrong; a
    # refusal says so instead.
    if names is None:
        raise AssertionError("_mini needs names= -- there is no sane default")
    names = list(names)
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
            # NO CACHE TO CLEAR, and a guard hid that. The line here was
            # `knobs.knob.cache_clear() if hasattr(knobs.knob, "cache_clear")
            # else None`; `knobs.knob` is a plain function, so the `hasattr`
            # was always False and the call never ran. Harmless today and
            # blind in the direction that matters: memoise `knob()` and this
            # sweep would compare 144 against 144 and go green on a wired-in
            # scale -- the very defect it exists to catch. Asserted instead.
            assert not hasattr(knobs.knob, "cache_clear"), (
                "`knobs.knob` is memoised now: this sweep sets PAGE_DPI per "
                "pass and would read the first value every time, reporting "
                "agreement it never measured")
            try:
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


def test_a_refused_build_leaves_the_golden_bench_untouched():
    """The accident this file records, and the half of it that was missing.

    `annopage.build` learned the write-aside after a refusal destroyed 595 of
    600 truth files -- and then left `truth.new` on disk after every refusal,
    with the pdf written in place and the manifest written after the swap. So
    a refusal could leave a partial second copy of the golden bench in a
    tracked directory, and a fall between the writes could leave `truth/`
    describing one sample beside a pdf holding another.

    The refusal used is the one the file's own comment names: `--truth-only`
    over a different sample, which is caught by the page-count guard AFTER the
    main loop has written every truth file.
    """
    import json
    import shutil
    import tempfile
    tmp = tempfile.mkdtemp()
    root, out = os.path.join(tmp, "raw"), os.path.join(tmp, "out")
    names = _real_names()
    _mini(root, names=names, yaml_names=names, pages=6)
    annopage.build(root, out, split="test", log=lambda *a: None)

    tdir = os.path.join(out, "truth")
    was = {n: open(os.path.join(tdir, n), encoding="utf-8").read()
           for n in os.listdir(tdir)}
    man_was = open(os.path.join(out, "manifest.json"), encoding="utf-8").read()
    pdf_was = open(os.path.join(out, "annopage.pdf"), "rb").read()

    try:
        annopage.build(root, out, split="test", limit=3, truth_only=True,
                       log=lambda *a: None)
    except annopage.AnnoPageError:
        pass
    else:
        raise AssertionError("the mismatched --truth-only build did not refuse")

    now = {n: open(os.path.join(tdir, n), encoding="utf-8").read()
           for n in os.listdir(tdir)}
    assert now == was, (
        f"a refused build changed the truth: {len(was)} files -> {len(now)}. "
        f"This is the accident that cost 595 of 600, arriving again")
    assert open(os.path.join(out, "manifest.json"),
                encoding="utf-8").read() == man_was, "the passport moved"
    assert open(os.path.join(out, "annopage.pdf"), "rb").read() == pdf_was, (
        "the pdf moved while the truth did not")
    left = sorted(n for n in os.listdir(out)
                  if n.endswith(".new") or n.endswith(".previous"))
    assert not left, (
        f"a refused build left {left} beside the golden bench -- a partial "
        f"second copy of the truth, in a directory git tracks and does not "
        f"ignore, with nothing to say which of the two is the bench")

    # AND THE PDF TRAVELS WITH THEM. The refusal above never reaches the save
    # (`--truth-only` writes no pdf), so the window between "pdf written" and
    # "truth swapped" needs a crash of its own -- staged at the hash of the
    # aside pdf, which is the last thing before the manifest and therefore
    # after the new pdf exists and before anything is swapped.
    _mini(root, names=names, yaml_names=names, pages=4)
    real = annopage._sha256

    def boom(path):
        if path.endswith(".new"):
            raise RuntimeError("interrupted between the pdf and the swap")
        return real(path)

    annopage._sha256 = boom
    try:
        annopage.build(root, out, split="test", log=lambda *a: None)
    except RuntimeError:
        pass
    else:
        raise AssertionError("the staged crash did not happen")
    finally:
        annopage._sha256 = real

    now = {n: open(os.path.join(tdir, n), encoding="utf-8").read()
           for n in os.listdir(tdir)}
    assert now == was, "the truth moved while the pdf and manifest did not"
    assert open(os.path.join(out, "annopage.pdf"), "rb").read() == pdf_was, (
        "the pdf was replaced while the truth was not: the truth now "
        "describes one sample and the pdf beside it holds another")
    assert open(os.path.join(out, "manifest.json"),
                encoding="utf-8").read() == man_was, "the passport moved alone"
    left = sorted(n for n in os.listdir(out)
                  if n.endswith(".new") or n.endswith(".previous"))
    assert not left, f"the crash left {left} behind"
    shutil.rmtree(tmp, ignore_errors=True)
