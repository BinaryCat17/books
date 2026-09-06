"""The distillate: bench pages where the TRUTH holds two artifacts of one
class side by side.

WHY A BENCH OF ITS OWN. Merging showed up eleven times over six synthetic
books; on real AnnoPage pages it is 378 undercounts of 534 -- 71 % of every
miss. What differs is how often such pages occur: thirteen in the synthetic
set, 138 in AnnoPage. Measuring the main defect where it barely happens
measures noise. Money says the same: 700 pages to a rented model for a defect
visible on 151 is six times the price of one answer.

THE ARGUMENT AND THE CODE COUNT DIFFERENT THINGS, which the numbers above need.
13, 138 and 151 count pages holding ANY TWO artifacts side by side;
`_side_pairs` below takes a narrower rule -- two artifacts of ONE label -- and
gives 6, 124 and 130. Both counts reproduce on today's truth (a sweep over 192
definitions of a pair: same geometry, `v > 0.5*min(h)` and `h <= 0`, differing
only in "one label" against "any"). "Six times" is the wide count; by the
narrow one it is 693/130 = 5.3. Declared here, not reconciled: which selection
rule is right is a question for a measurement, not for editing a docstring.

Truth is carried over AS IS, the out-of-scope field included: the page does not
move by a pixel, only its number changes.

THE TRAITS TRAVEL TOO, NOT ONLY THE BOXES. `order_marked`, `text_marked` and
`out_of_scope` are metric inputs on a par with coordinates, and losing one does
not fell a run -- it CHANGES THE NUMBER SILENTLY. The price is measured:
`bench/hard36` was built by an outside script that carried the boxes and lost
exactly `order_marked` (124 pages of 130 carry it in `bench/hard`, none of 36
in hard36). `books score` read its absence as "order marked" and printed
"pairs 211, agreed 73 %" -- a number out of nothing, and detectors had already
been ranked by it. So traits are carried explicitly here, their state counted
by name and sent into the manifest: a distillate must be able to say what
cannot be measured in it.
"""
import hashlib
import json
import os
import shutil

import pymupdf

from . import policy


class SubsetError(RuntimeError):
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


# Truth traits without which the metric silently changes its answer. The list
# is EXPLICIT: a new bench trait lands here deliberately or not at all --
# never lost by default.
TRAITS = ("order_marked", "text_marked")


def _carry_meta(t: dict, extra: dict, where: str) -> dict:
    """The source page's meta plus our marks. Nothing overwritten.

    The old `t.setdefault("meta", {})` would die on a page with `"meta": null`
    (setdefault returns None) and, worse, silently let our fields sit over
    truth fields of the same name. Our three fields are the distillate's
    bookkeeping, not truth, and have no right to overwrite it.
    """
    src = dict(t.get("meta") or {})
    clash = {k: (src[k], v) for k, v in extra.items()
             if k in src and src[k] != v}
    if clash:
        raise SubsetError(
            f"{where}: distillate fields would overwrite truth fields "
            f"{clash}. Truth is carried as is; editing it here is forbidden.")
    # NO SECOND GUARD HERE, AND THAT IS THE FIX. There was one:
    # `lost = [k for k in src if k not in meta]` over `meta = {**src, **extra}`
    # -- empty by construction, since a dict built from `**src` holds every key
    # of `src`. It read as protection and could not fail, which is worse than
    # no guard at all: the "a metric must be able to fail" rule broken in code
    # rather than in a metric. What it was reaching for is proved on built
    # input instead, by `test_the_carry_over_keeps_every_truth_field`.
    return {**src, **extra}


def _trait_state(meta: dict, key: str) -> str:
    """Three answers, not two: "yes", "no", "not said". The last is NOT
    "no": a page where the trait is absent asserts nothing, and the metric
    must stay silent over it rather than count."""
    if key not in meta:
        return "not_said"
    return "yes" if meta[key] else "no"


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build(books, out_dir: str, root: str = "bench", log=print) -> dict:
    """Build the distillate out of the named bench books.

    NOTHING HALF-BUILT IS LEFT BEHIND. Every refusal used to leave `truth.new`
    beside the truth -- and the default `out_dir` is `bench/hard`, which is
    tracked and does not ignore that name, so a refused `books subset` put a
    partial second copy of the bench truth into the working tree. The aside
    files are removed on the way out unless the swap completed.
    """
    return _swept(_build, books, out_dir, root, log)


def _swept(fn, books, out_dir, root, log):
    """Run the build; on any failure remove what it wrote aside."""
    # `truth.previous` TOO. The sweep listed only what a build WRITES, and the
    # swap also leaves the old truth aside under that name -- `bench/hard` is
    # tracked and ignores neither, so an interrupted build left a second copy
    # of the bench truth in the working tree with nothing to say which is the
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
    # TRUTH IS WRITTEN ASIDE AND SWAPPED IN ONLY AFTER THE GUARDS, the same
    # dance as `annopage.build` and for the same reason. `truth/` used to be
    # emptied HERE, before a loop that can refuse four ways -- no such pdf, no
    # such page in it, a distillate field clashing with a truth field, and not
    # one page selected. Every one of those left the bench truth EMPTY: a
    # refusal meant to protect the data destroying it instead. On the golden
    # bench that cost 595 of 600 files, recovered only because it is tracked.
    #
    # ALL THREE PARTS TRAVEL TOGETHER, and the first edition of this fix moved
    # only the truth. The distillate is truth, pdf and manifest, and they refer
    # to one another: `t["index"]` addresses a page of THAT pdf, the manifest
    # holds its sha256 and page count. Writing the pdf in place while the truth
    # waited aside meant a crash in between left `truth/` describing four pages
    # and `hard.pdf` holding eight -- the mixed bench the write-aside was meant
    # to make impossible, moved one file over.
    work = tdir + ".new"
    wpdf = os.path.join(out_dir, "hard.pdf.new")
    wman = os.path.join(out_dir, "manifest.json.new")
    for stale in (wpdf, wman):
        if os.path.exists(stale):
            os.unlink(stale)
    if os.path.isdir(work):
        shutil.rmtree(work)
    os.makedirs(work)

    # CLOSED WHATEVER HAPPENS. A refusal from inside the loop used to leave
    # both `doc` and the source handle open; on a bench of six books that is
    # seven mapped files held by a command that has already given up.
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
           "pdf": os.path.basename(pdf), "sha256 pdf": _sha256(wpdf)}
    with open(wman, "w", encoding="utf-8") as f:
        json.dump(man, f, ensure_ascii=False, indent=1)

    # GUARDS PASSED -- NOW ALL THREE MAY BE SWAPPED, and nothing between here
    # and the end can refuse. Old truth aside, new into place, old removed:
    # break in the middle and either the previous truth or the new one stands,
    # never emptiness. The pdf and the manifest go by `os.replace`, which does
    # not leave a half-written file.
    #
    # The last `rmtree` is caught: it runs AFTER the point of no return, and an
    # exception there used to leave the manifest unwritten -- the bench then
    # carried a new truth and a stale passport, which is the mixture this
    # whole dance exists to prevent.
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
    # THE QUANTITY, NOT THE WORD "carried". The line below is the only place
    # showing that the distillate brought the traits over; silence here has
    # already cost us 73 %, printed out of nothing.
    for key, st in traits.items():
        log(f"trait {key!r}: yes {st['yes']}, no {st['no']}, "
            f"NOT SAID {st['not_said']} of {len(kept)} pages"
            + (f" -- on those {st['not_said']} the metric over it will NOT "
               f"be counted and must print NOT COMPARED"
               if st["not_said"] else ""))
    log(f"{pdf} ({os.path.getsize(pdf)/1e6:.0f} MB), truth in {tdir}")
    return man
