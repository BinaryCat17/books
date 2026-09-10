"""The distillate: bench pages where the TRUTH holds two artifacts of one class
side by side.

A bench of its own, because merging is the main level-one defect and it barely
happens on the synthetic books, where measuring it measures noise. Truth is
carried over AS IS, the out-of-scope field included -- the page does not move by
a pixel, only its number changes -- and the TRAITS travel too, their state
counted by name into the manifest: losing one changes the number silently
instead of felling the run.
"""
import json
import os
import shutil

import pymupdf

from booksmith.core import policy
from booksmith.core import stamp
from booksmith.core.errors import Refusal


class SubsetError(Refusal):
    pass


def _side_pairs(blocks):
    """Blocks of ONE label standing side by side: the verticals overlap by
    more than half, the horizontals not at all."""
    out = []
    for i in range(len(blocks)):
        for j in range(i + 1, len(blocks)):
            if blocks[i]["label"] != blocks[j]["label"]:
                continue
            a, b = blocks[i]["box"], blocks[j]["box"]
            v = min(a[3], b[3]) - max(a[1], b[1])
            h = min(a[2], b[2]) - max(a[0], b[0])
            if v > 0.5 * min(a[3] - a[1], b[3] - b[1]) and h <= 0:
                out.append((i, j))
    return out


# Truth traits without which the metric silently changes its answer. Explicit:
# a new bench trait lands here deliberately or not at all.
TRAITS = ("order_marked", "text_marked")


def _carry_meta(t: dict, extra: dict, where: str) -> dict:
    """The source page's meta plus our marks, nothing overwritten: our fields
    are the distillate's bookkeeping and not truth, and have no right to sit
    over a truth field of the same name."""
    src = dict(t.get("meta") or {})
    clash = {k: (src[k], v) for k, v in extra.items()
             if k in src and src[k] != v}
    if clash:
        raise SubsetError(
            f"{where}: distillate fields would overwrite truth fields "
            f"{clash}. Truth is carried as is; editing it here is forbidden.")
    # A "no key lost" guard here would be empty by construction; that the
    # carry-over keeps every truth field is proved on built input by
    # `tests/unit/test_subset.py`.
    return {**src, **extra}


def _trait_state(meta: dict, key: str) -> str:
    """Three answers, not two: "yes", "no", "not said". The last is NOT
    "no": a page where the trait is absent asserts nothing, and the metric
    must stay silent over it rather than count."""
    if key not in meta:
        return "not_said"
    return "yes" if meta[key] else "no"




def build(books, out_dir: str, root: str = "bench", log=print) -> dict:
    """Build the distillate out of the named bench books. Nothing half-built is
    left behind: the aside files are removed on the way out unless the swap
    completed, the default `out_dir` being tracked and ignoring none of them."""
    return _swept(_build, books, out_dir, root, log)


def _swept(fn, books, out_dir, root, log):
    """Run the build; on any failure remove what it wrote aside."""
    # `truth.previous` too: the swap leaves the old truth aside under that name,
    # and a second copy in a tracked directory says nothing about which is the
    # bench.
    aside = (os.path.join(out_dir, "truth.new"),
             os.path.join(out_dir, "truth.previous"),
             os.path.join(out_dir, "hard.pdf.new"),
             os.path.join(out_dir, "manifest.json.new"))
    try:
        return fn(books, out_dir, root, log)
    except BaseException:
        for p in aside:
            try:
                shutil.rmtree(p) if os.path.isdir(p) else os.unlink(p)
            except OSError:
                pass                  # the refusal is the news, not this
        raise


def _build(books, out_dir: str, root: str, log) -> dict:
    arte = set(policy.artefacts())
    os.makedirs(out_dir, exist_ok=True)
    tdir = os.path.join(out_dir, "truth")
    # Truth is written aside and swapped in only after the guards, the same dance
    # as `annopage.build`: emptying `truth/` before a loop that can refuse four
    # ways destroys the bench the refusal was meant to protect. All three parts
    # travel together -- truth, pdf and manifest refer to one another, `t["index"]`
    # addressing a page of THAT pdf -- or a crash between leaves a mixed bench.
    work = tdir + ".new"
    wpdf = os.path.join(out_dir, "hard.pdf.new")
    wman = os.path.join(out_dir, "manifest.json.new")
    for stale in (wpdf, wman):
        if os.path.exists(stale):
            os.unlink(stale)
    if os.path.isdir(work):
        shutil.rmtree(work)
    os.makedirs(work)

    # Closed whatever happens: a refusal inside the loop must not leave mapped
    # files held by a command that has given up.
    doc = pymupdf.open()
    try:
        return _pages(books, root, arte, doc, work, wpdf, wman, tdir, out_dir,
                      log)
    finally:
        try:
            doc.close()
        except (ValueError, RuntimeError):
            pass                      # already closed by the happy path


def _pages(books, root, arte, doc, work, wpdf, wman, tdir, out_dir, log):
    kept, per_book, pairs_total = [], {}, 0
    traits = {k: {"yes": 0, "no": 0, "not_said": 0} for k in TRAITS}
    for bk in books:
        pdf = os.path.join(root, bk, f"{bk}.pdf")
        if not os.path.exists(pdf):
            raise SubsetError(f"no {pdf}")
        src = pymupdf.open(pdf)
        try:
            for name in sorted(os.listdir(os.path.join(root, bk, "truth"))):
                if not name.endswith(".json"):
                    continue
                with open(os.path.join(root, bk, "truth", name),
                          encoding="utf-8") as f:
                    t = json.load(f)
                ab = [b for b in t["blocks"] if b["label"] in arte]
                pr = _side_pairs(ab)
                if not pr:
                    continue
                i = t["index"]
                if not 0 <= i < src.page_count:
                    raise SubsetError(f"{bk}: there is no page {i} in {pdf}")
                doc.insert_pdf(src, from_page=i, to_page=i)
                t["index"] = len(kept)
                t["meta"] = _carry_meta(t, {"from_book": bk,
                                            "page_in_book": i,
                                            "side_by_side_pairs": len(pr)},
                                        f"{bk}/{name}")
                for key in TRAITS:
                    traits[key][_trait_state(t["meta"], key)] += 1
                with open(os.path.join(work, f"{len(kept):04d}.json"), "w",
                          encoding="utf-8") as f:
                    json.dump(t, f, ensure_ascii=False)
                kept.append((bk, i))
                per_book[bk] = per_book.get(bk, 0) + 1
                pairs_total += len(pr)
        finally:
            src.close()
    if not kept:
        raise SubsetError("not one page was selected")
    pdf = os.path.join(out_dir, "hard.pdf")
    doc.save(wpdf, garbage=3, deflate=True)
    doc.close()
    man = {"book": "hard", "about": "subset: two artifacts of one label "
                                    "side by side in the truth",
           "page_count": len(kept), "side_by_side_pairs": pairs_total,
           "by_book": per_book, "pages": [{"book": b, "page_no": i}
                                               for b, i in kept],
           # The trait state is part of the distillate's passport: it says
           # what CAN be measured here, before the first `books score`.
           "truth_traits": traits,
           "source": {"name": os.path.basename(pdf),
                      "sha256": stamp.sha256(wpdf)}}
    with open(wman, "w", encoding="utf-8") as f:
        json.dump(man, f, ensure_ascii=False, indent=1)

    # Guards passed: all three may be swapped, and nothing between here and the
    # end can refuse. Old truth aside, new into place, old removed -- break in
    # the middle and one truth or the other stands, never emptiness. The last
    # `rmtree` is caught because it runs after the point of no return.
    keep = tdir + ".previous"
    if os.path.isdir(keep):
        shutil.rmtree(keep)
    if os.path.isdir(tdir):
        os.rename(tdir, keep)
    os.rename(work, tdir)
    os.replace(wpdf, pdf)
    os.replace(wman, os.path.join(out_dir, "manifest.json"))
    if os.path.isdir(keep):
        try:
            shutil.rmtree(keep)
        except OSError as e:
            log(f"WARNING: the previous truth is left at {keep} ({e}) -- the "
                f"bench itself is whole, but that directory is a second copy "
                f"and must be removed by hand")
    log(f"pages {len(kept)} ({per_book}), side-by-side pairs {pairs_total}")
    # The quantity, not the word "carried": this is the only place that shows
    # the distillate brought the traits over.
    for key, st in traits.items():
        log(f"trait {key!r}: yes {st['yes']}, no {st['no']}, "
            f"NOT SAID {st['not_said']} of {len(kept)} pages"
            + (f" -- on those {st['not_said']} the metric over it will NOT "
               f"be counted and must print NOT COMPARED"
               if st["not_said"] else ""))
    log(f"{pdf} ({os.path.getsize(pdf)/1e6:.0f} MB), truth in {tdir}")
    return man
