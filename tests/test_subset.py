"""The distillate: what it carries over, and what a refusal must not destroy.

WHY THIS FILE EXISTS. `subset.py` had no check at all -- 2570 characters of
prose about what it guards, and not one line proving any of it. Two defects
were found by reading it, and both are of the kind reading finds and running
does not: a guard that cannot fail, and a destruction that only shows on the
day the build refuses.
"""
import json
import os
import shutil
import tempfile

import pymupdf
import support
from booksmith import subset


def _truth(index, meta=None):
    """A page with two artifacts of one label side by side -- what qualifies."""
    return {"index": index, "width": 100, "height": 100, "dpi": 144.0,
            "meta": meta or {},
            "blocks": [{"block_id": 0, "box": [0, 0, 40, 50], "label": "table",
                        "content": None, "kind": "none"},
                       {"block_id": 1, "box": [50, 0, 90, 50], "label": "table",
                        "content": None, "kind": "none"}]}


def _bench(root, book, pages=1, meta=None):
    """A bench book on disk: a pdf of `pages` pages and a truth file each."""
    d = os.path.join(root, book)
    os.makedirs(os.path.join(d, "truth"), exist_ok=True)
    doc = pymupdf.open()
    for i in range(pages):
        doc.new_page(width=100, height=100)
        with open(os.path.join(d, "truth", f"{i:04d}.json"), "w",
                  encoding="utf-8") as f:
            json.dump(_truth(i, meta), f, ensure_ascii=False)
    doc.save(os.path.join(d, f"{book}.pdf"))
    doc.close()


def test_the_carry_over_keeps_every_truth_field():
    """Truth fields survive the carry; ours are added beside them.

    THE GUARD THAT USED TO STAND HERE COULD NOT FAIL. It was
    `lost = [k for k in src if k not in meta]` over `meta = {**src, **extra}`
    -- empty by construction, because a dict built from `**src` holds every key
    of `src`. It read as protection and protected nothing. The property is real
    and is proved here on built input instead, which is a thing that can go
    red.
    """
    src = {"order_marked": True, "text_marked": False, "dpi_note": "600"}
    got = subset._carry_meta({"meta": dict(src)},
                             {"from_book": "slovar", "page_in_book": 7},
                             "slovar/0007.json")
    for k, v in src.items():
        assert got[k] == v, (
            f"truth field {k!r} did not survive the carry: {v!r} -> "
            f"{got.get(k)!r}")
    assert got["from_book"] == "slovar" and got["page_in_book"] == 7, got


def test_a_field_of_ours_may_not_overwrite_a_truth_field():
    """The other direction, and the one that IS guarded at run time."""
    try:
        subset._carry_meta({"meta": {"from_book": "atlas"}},
                           {"from_book": "slovar"}, "atlas/0000.json")
    except subset.SubsetError as e:
        assert "from_book" in str(e), e
    else:
        raise AssertionError(
            "a distillate field silently overwrote a truth field of the same "
            "name -- truth is carried as is")


def test_a_refused_build_does_not_destroy_good_truth():
    """A build that refuses leaves the previous truth standing.

    `truth/` was emptied at the top of `build`, before a loop that can refuse
    four ways: no such pdf, no such page in it, a distillate field clashing
    with a truth field, and not one page selected. Every one of those left the
    bench truth EMPTY -- a refusal meant to protect the data destroying it.
    The same accident cost 595 of 600 files on the golden bench, and was fixed
    there and not here.

    The refusal used is the clash, because it happens in the MIDDLE of the
    loop: by then some pages have been written, so a build that wrote into
    place would already have replaced part of the truth.
    """
    tmp = tempfile.mkdtemp()
    root = os.path.join(tmp, "bench")
    _bench(root, "good", pages=2)
    out = os.path.join(tmp, "hard")

    subset.build(["good"], out, root=root, log=lambda *a: None)
    tdir = os.path.join(out, "truth")
    before = sorted(os.listdir(tdir))
    assert len(before) == 2, before
    was = open(os.path.join(tdir, before[0]), encoding="utf-8").read()

    # The same book, now with a truth field that collides with ours.
    _bench(root, "clash", pages=2, meta={"from_book": "somebody else"})
    try:
        subset.build(["good", "clash"], out, root=root, log=lambda *a: None)
    except subset.SubsetError:
        pass
    else:
        raise AssertionError("the clashing build did not refuse at all")

    now = sorted(os.listdir(tdir))
    assert now == before, (
        f"a refused build changed the truth on disk: {before} -> {now}. A "
        f"refusal must leave the previous truth standing, never emptiness")
    assert open(os.path.join(tdir, now[0]), encoding="utf-8").read() == was, (
        "the file survived by name and not by content")
    shutil.rmtree(tmp, ignore_errors=True)


def test_the_build_leaves_no_working_directory_behind():
    """The aside directory is swapped in, not left beside the truth.

    A `truth.new` left on disk would be read by nothing and copied by
    everything -- and on the next build it is silently reused.
    """
    tmp = tempfile.mkdtemp()
    root = os.path.join(tmp, "bench")
    _bench(root, "good", pages=1)
    out = os.path.join(tmp, "hard")
    subset.build(["good"], out, root=root, log=lambda *a: None)
    left = [d for d in os.listdir(out) if d.startswith("truth.")]
    assert not left, f"working directories left behind: {left}"
    shutil.rmtree(tmp, ignore_errors=True)


def _aside(out):
    return sorted(n for n in os.listdir(out)
                  if n.endswith(".new") or n.endswith(".previous"))


def test_no_refusal_leaves_a_half_built_bench_behind():
    """Aside files are swept on the way out, and that matters where it lands.

    The default `out_dir` is `bench/hard`, which is TRACKED and does not
    ignore `truth.new`: a refused `books subset` used to put a partial second
    copy of the bench truth into the working tree, with nothing to say which
    of the two directories is the bench.
    """
    tmp = tempfile.mkdtemp()
    root = os.path.join(tmp, "bench")
    _bench(root, "good", pages=2)
    out = os.path.join(tmp, "hard")
    subset.build(["good"], out, root=root, log=lambda *a: None)

    _bench(root, "clash", pages=1, meta={"from_book": "somebody else"})
    for books in (["good", "nosuchbook"], ["good", "clash"]):
        try:
            subset.build(books, out, root=root, log=lambda *a: None)
        except subset.SubsetError:
            pass
        else:
            raise AssertionError(f"{books} did not refuse at all")
        assert not _aside(out), (
            f"after refusing {books}, {_aside(out)} is left in {out} -- a "
            f"partial second copy of the bench, and nothing says which is it")
    shutil.rmtree(tmp, ignore_errors=True)


def test_truth_pdf_and_manifest_are_swapped_together():
    """Three parts that refer to one another, and they move as one.

    `t["index"]` addresses a page of THAT pdf and the manifest holds its
    sha256 and page count. The first edition of the write-aside moved only the
    truth, so a crash in between left `truth/` describing four pages and
    `hard.pdf` holding eight -- the mixed bench, moved one file over.

    The crash is placed after the pdf is written and before the swap, which is
    exactly the window that used to be open.
    """
    tmp = tempfile.mkdtemp()
    root = os.path.join(tmp, "bench")
    _bench(root, "small", pages=2)
    out = os.path.join(tmp, "hard")
    subset.build(["small"], out, root=root, log=lambda *a: None)
    was = {n: open(os.path.join(out, "truth", n), encoding="utf-8").read()
           for n in os.listdir(os.path.join(out, "truth"))}
    man_was = open(os.path.join(out, "manifest.json"), encoding="utf-8").read()
    pdf_was = open(os.path.join(out, "hard.pdf"), "rb").read()

    _bench(root, "more", pages=4)
    real = subset._sha256

    def boom(path):
        # `_sha256` of the aside pdf is the last thing before the manifest,
        # i.e. after the new pdf exists and before anything is swapped.
        if path.endswith(".new"):
            raise RuntimeError("interrupted between the pdf and the swap")
        return real(path)

    subset._sha256 = boom
    try:
        subset.build(["small", "more"], out, root=root, log=lambda *a: None)
    except RuntimeError:
        pass
    else:
        raise AssertionError("the staged crash did not happen")
    finally:
        subset._sha256 = real

    now = {n: open(os.path.join(out, "truth", n), encoding="utf-8").read()
           for n in os.listdir(os.path.join(out, "truth"))}
    assert now == was, "the truth moved while the pdf and manifest did not"
    assert open(os.path.join(out, "hard.pdf"), "rb").read() == pdf_was, (
        "the pdf was replaced while the truth was not: `t['index']` now "
        "addresses pages of a DIFFERENT book")
    assert open(os.path.join(out, "manifest.json"),
                encoding="utf-8").read() == man_was, (
        "the manifest moved on its own: its sha256 and page_count no longer "
        "describe the bench beside it")
    assert not _aside(out), f"aside files left behind: {_aside(out)}"
    shutil.rmtree(tmp, ignore_errors=True)


def test_the_traits_reach_the_manifest_and_the_log():
    """The passport is the thing this file exists for, and it was unguarded.

    `TRAITS` names the truth traits without which a metric silently changes
    its answer, and the manifest carries their state so a reader knows what
    CAN be measured here before the first `books score`. Emptying `TRAITS`
    left every check green while `truth_traits` became `{}` and the passport
    lines vanished from the log -- the same silence that once printed "pairs
    211, agreed 73 %" out of nothing.
    """
    tmp = tempfile.mkdtemp()
    root = os.path.join(tmp, "bench")
    _bench(root, "good", pages=2, meta={"order_marked": True})
    out = os.path.join(tmp, "hard")
    said = []
    man = subset.build(["good"], out, root=root, log=said.append)

    assert subset.TRAITS, "TRAITS is empty: the passport declares nothing"
    got = man.get("truth_traits") or {}
    assert set(got) == set(subset.TRAITS), (
        f"the manifest's passport covers {sorted(got)}, the declaration names "
        f"{sorted(subset.TRAITS)}")
    for key in subset.TRAITS:
        assert sum(got[key].values()) == man["page_count"], (
            f"trait {key!r} is counted over {sum(got[key].values())} pages of "
            f"{man['page_count']} -- some page was neither yes, no nor "
            f"not_said, which is a fourth answer nobody declared")
        assert any(key in line for line in said), (
            f"trait {key!r} is in the manifest and not in the log: the "
            f"quantity was carried and never said")
    on_disk = json.load(open(os.path.join(out, "manifest.json"),
                             encoding="utf-8"))
    assert on_disk["truth_traits"] == got, (
        "the passport returned differs from the passport written down")
    shutil.rmtree(tmp, ignore_errors=True)
