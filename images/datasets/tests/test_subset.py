"""The distillate: what it carries over, and what a refusal must not destroy"""

import json
import os
import shutil
import tempfile
import pymupdf
from datasets import identity as stamp
from datasets import subset
import support


def _truth(index, meta=None):
    return {
        "index": index,
        "width": 100,
        "height": 100,
        "dpi": 144.0,
        "meta": meta or {},
        "blocks": [
            {
                "block_id": 0,
                "box": [0, 0, 40, 50],
                "label": "table",
                "content": None,
                "kind": "none",
            },
            {
                "block_id": 1,
                "box": [50, 0, 90, 50],
                "label": "table",
                "content": None,
                "kind": "none",
            },
        ],
    }


def _bench(root, book, pages=1, meta=None):
    d = os.path.join(root, book)
    os.makedirs(os.path.join(d, "truth"), exist_ok=True)
    doc = pymupdf.open()
    for i in range(pages):
        doc.new_page(width=100, height=100)
        with open(os.path.join(d, "truth", f"{i:04d}.json"), "w", encoding="utf-8") as f:
            json.dump(_truth(i, meta), f, ensure_ascii=False)
    doc.save(os.path.join(d, f"{book}.pdf"))
    doc.close()


def test_the_carry_over_keeps_every_truth_field():
    src = {"order_marked": True, "text_marked": False, "dpi_note": "600"}
    got = subset._carry_meta(
        {"meta": dict(src)}, {"from_book": "slovar", "page_in_book": 7}, "slovar/0007.json"
    )
    for k, v in src.items():
        assert got[k] == v, f"truth field {k!r} did not survive the carry: {v!r} -> {got.get(k)!r}"
    assert got["from_book"] == "slovar" and got["page_in_book"] == 7, got


def test_a_field_of_ours_may_not_overwrite_a_truth_field():
    try:
        subset._carry_meta(
            {"meta": {"from_book": "atlas"}}, {"from_book": "slovar"}, "atlas/0000.json"
        )
    except subset.SubsetError as e:
        assert "from_book" in str(e), e
    else:
        raise AssertionError(
            "a distillate field silently overwrote a truth field of the same name -- truth is carried as is"
        )


def test_a_refused_build_does_not_destroy_good_truth():
    tmp = tempfile.mkdtemp()
    root = os.path.join(tmp, "bench")
    _bench(root, "good", pages=2)
    out = os.path.join(tmp, "hard")
    subset.build(["good"], out, root=root)
    tdir = os.path.join(out, "truth")
    before = sorted(os.listdir(tdir))
    assert len(before) == 2, before
    was = open(os.path.join(tdir, before[0]), encoding="utf-8").read()
    _bench(root, "clash", pages=2, meta={"from_book": "somebody else"})
    try:
        subset.build(["good", "clash"], out, root=root)
    except subset.SubsetError:
        pass
    else:
        raise AssertionError("the clashing build did not refuse at all")
    now = sorted(os.listdir(tdir))
    assert now == before, (
        f"a refused build changed the truth on disk: {before} -> {now}. A refusal must leave the previous truth standing, never emptiness"
    )
    assert open(os.path.join(tdir, now[0]), encoding="utf-8").read() == was, (
        "the file survived by name and not by content"
    )
    shutil.rmtree(tmp, ignore_errors=True)


def test_the_build_leaves_no_working_directory_behind():
    tmp = tempfile.mkdtemp()
    root = os.path.join(tmp, "bench")
    _bench(root, "good", pages=1)
    out = os.path.join(tmp, "hard")
    subset.build(["good"], out, root=root)
    left = [d for d in os.listdir(out) if d.startswith("truth.")]
    assert not left, f"working directories left behind: {left}"
    shutil.rmtree(tmp, ignore_errors=True)


def _aside(out):
    return sorted((n for n in os.listdir(out) if n.endswith(".new") or n.endswith(".previous")))


def test_no_refusal_leaves_a_half_built_bench_behind():
    tmp = tempfile.mkdtemp()
    root = os.path.join(tmp, "bench")
    _bench(root, "good", pages=2)
    out = os.path.join(tmp, "hard")
    subset.build(["good"], out, root=root)
    _bench(root, "clash", pages=1, meta={"from_book": "somebody else"})
    for books in (["good", "nosuchbook"], ["good", "clash"]):
        try:
            subset.build(books, out, root=root)
        except subset.SubsetError:
            pass
        else:
            raise AssertionError(f"{books} did not refuse at all")
        assert not _aside(out), (
            f"after refusing {books}, {_aside(out)} is left in {out} -- a partial second copy of the bench, and nothing says which is it"
        )
    shutil.rmtree(tmp, ignore_errors=True)


def test_truth_pdf_and_manifest_are_swapped_together():
    tmp = tempfile.mkdtemp()
    root = os.path.join(tmp, "bench")
    _bench(root, "small", pages=2)
    out = os.path.join(tmp, "hard")
    subset.build(["small"], out, root=root)
    was = {
        n: open(os.path.join(out, "truth", n), encoding="utf-8").read()
        for n in os.listdir(os.path.join(out, "truth"))
    }
    man_was = open(os.path.join(out, "manifest.json"), encoding="utf-8").read()
    pdf_was = open(os.path.join(out, "hard.pdf"), "rb").read()
    _bench(root, "more", pages=4)
    real = stamp.sha256

    def boom(path):
        if path.endswith(".new"):
            raise RuntimeError("interrupted between the pdf and the swap")
        return real(path)

    stamp.sha256 = boom
    try:
        subset.build(["small", "more"], out, root=root)
    except RuntimeError:
        pass
    else:
        raise AssertionError("the staged crash did not happen")
    finally:
        stamp.sha256 = real
    now = {
        n: open(os.path.join(out, "truth", n), encoding="utf-8").read()
        for n in os.listdir(os.path.join(out, "truth"))
    }
    assert now == was, "the truth moved while the pdf and manifest did not"
    assert open(os.path.join(out, "hard.pdf"), "rb").read() == pdf_was, (
        "the pdf was replaced while the truth was not: `t['index']` now addresses pages of a DIFFERENT book"
    )
    assert open(os.path.join(out, "manifest.json"), encoding="utf-8").read() == man_was, (
        "the manifest moved on its own: its sha256 and page_count no longer describe the bench beside it"
    )
    assert not _aside(out), f"aside files left behind: {_aside(out)}"
    shutil.rmtree(tmp, ignore_errors=True)


def test_the_traits_reach_the_manifest_and_the_log():
    tmp = tempfile.mkdtemp()
    root = os.path.join(tmp, "bench")
    _bench(root, "good", pages=2, meta={"order_marked": True})
    out = os.path.join(tmp, "hard")
    with support.said() as said:
        man = subset.build(["good"], out, root=root)
    assert subset.TRAITS, "TRAITS is empty: the passport declares nothing"
    got = man.get("truth_traits") or {}
    assert set(got) == set(subset.TRAITS), (
        f"the manifest's passport covers {sorted(got)}, the declaration names {sorted(subset.TRAITS)}"
    )
    for key in subset.TRAITS:
        assert sum(got[key].values()) == man["page_count"], (
            f"trait {key!r} is counted over {sum(got[key].values())} pages of {man['page_count']} -- some page was neither yes, no nor not_said, which is a fourth answer nobody declared"
        )
        assert any((key in line for line in said)), (
            f"trait {key!r} is in the manifest and not in the log: the quantity was carried and never said"
        )
    on_disk = json.load(open(os.path.join(out, "manifest.json"), encoding="utf-8"))
    assert on_disk["truth_traits"] == got, (
        "the passport returned differs from the passport written down"
    )
    shutil.rmtree(tmp, ignore_errors=True)
