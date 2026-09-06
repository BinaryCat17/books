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
    meta = {**src, **extra}
    lost = [k for k in src if k not in meta]
    if lost:
        raise SubsetError(f"{where}: traits lost in the carry-over: {lost}")
    return meta


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
    """Build the distillate out of the named bench books."""
    arte = set(policy.artefacts())
    os.makedirs(out_dir, exist_ok=True)
    tdir = os.path.join(out_dir, "truth")
    os.makedirs(tdir, exist_ok=True)
    for old in os.listdir(tdir):
        os.unlink(os.path.join(tdir, old))

    doc = pymupdf.open()
    kept, per_book, pairs_total = [], {}, 0
    traits = {k: {"yes": 0, "no": 0, "not_said": 0} for k in TRAITS}
    for bk in books:
        pdf = os.path.join(root, bk, f"{bk}.pdf")
        if not os.path.exists(pdf):
            raise SubsetError(f"no {pdf}")
        src = pymupdf.open(pdf)
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
            with open(os.path.join(tdir, f"{len(kept):04d}.json"), "w",
                      encoding="utf-8") as f:
                json.dump(t, f, ensure_ascii=False)
            kept.append((bk, i))
            per_book[bk] = per_book.get(bk, 0) + 1
            pairs_total += len(pr)
        src.close()
    if not kept:
        raise SubsetError("not one page was selected")
    pdf = os.path.join(out_dir, "hard.pdf")
    doc.save(pdf, garbage=3, deflate=True)
    doc.close()
    man = {"book": "hard", "about": "subset: two artifacts of one label "
                                    "side by side in the truth",
           "page_count": len(kept), "side_by_side_pairs": pairs_total,
           "by_book": per_book, "pages": [{"book": b, "page_no": i}
                                               for b, i in kept],
           # The trait state is part of the distillate's passport: it says
           # what CAN be measured here, before the first `books score`.
           "truth_traits": traits,
           "pdf": os.path.basename(pdf), "sha256 pdf": _sha256(pdf)}
    with open(os.path.join(out_dir, "manifest.json"), "w",
              encoding="utf-8") as f:
        json.dump(man, f, ensure_ascii=False, indent=1)
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
