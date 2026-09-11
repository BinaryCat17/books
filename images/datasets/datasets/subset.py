import json
import os
import shutil
import pymupdf
from datasets import classes as policy
from datasets import identity as stamp
from datasets.errors import Refusal
from datasets.log import log


class SubsetError(Refusal):
    pass


def _side_pairs(blocks):
    out = []
    for i in range(len(blocks)):
        for j in range(i + 1, len(blocks)):
            if blocks[i]["label"] != blocks[j]["label"]:
                continue
            a, b = (blocks[i]["box"], blocks[j]["box"])
            v = min(a[3], b[3]) - max(a[1], b[1])
            h = min(a[2], b[2]) - max(a[0], b[0])
            if v > 0.5 * min(a[3] - a[1], b[3] - b[1]) and h <= 0:
                out.append((i, j))
    return out


TRAITS = ("order_marked", "text_marked", "labelled")


def _carry_meta(t: dict, extra: dict, where: str) -> dict:
    src = dict(t.get("meta") or {})
    clash = {k: (src[k], v) for k, v in extra.items() if k in src and src[k] != v}
    if clash:
        raise SubsetError(
            f"{where}: distillate fields would overwrite truth fields {clash}. Truth is carried as is; editing it here is forbidden."
        )
    return {**src, **extra}


def _trait_state(meta: dict, key: str) -> str:
    if key not in meta:
        return "not_said"
    return "yes" if meta[key] else "no"


def build(books, out_dir: str, root: str = "bench") -> dict:
    return _swept(_build, books, out_dir, root)


def _swept(fn, books, out_dir, root):
    aside = (
        os.path.join(out_dir, "truth.new"),
        os.path.join(out_dir, "truth.previous"),
        os.path.join(out_dir, "hard.pdf.new"),
        os.path.join(out_dir, "manifest.json.new"),
    )
    try:
        return fn(books, out_dir, root)
    except BaseException:
        for p in aside:
            try:
                shutil.rmtree(p) if os.path.isdir(p) else os.unlink(p)
            except OSError:
                pass
        raise


def _build(books, out_dir: str, root: str) -> dict:
    arte = set(policy.UNION.artefacts())
    os.makedirs(out_dir, exist_ok=True)
    tdir = os.path.join(out_dir, "truth")
    work = tdir + ".new"
    wpdf = os.path.join(out_dir, "hard.pdf.new")
    wman = os.path.join(out_dir, "manifest.json.new")
    for stale in (wpdf, wman):
        if os.path.exists(stale):
            os.unlink(stale)
    if os.path.isdir(work):
        shutil.rmtree(work)
    os.makedirs(work)
    doc = pymupdf.open()
    try:
        return _pages(books, root, arte, doc, work, wpdf, wman, tdir, out_dir)
    finally:
        try:
            doc.close()
        except (ValueError, RuntimeError):
            pass


def _pages(books, root, arte, doc, work, wpdf, wman, tdir, out_dir):
    kept, per_book, pairs_total = ([], {}, 0)
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
                with open(os.path.join(root, bk, "truth", name), encoding="utf-8") as f:
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
                t["meta"] = _carry_meta(
                    t,
                    {"from_book": bk, "page_in_book": i, "side_by_side_pairs": len(pr)},
                    f"{bk}/{name}",
                )
                for key in TRAITS:
                    traits[key][_trait_state(t["meta"], key)] += 1
                with open(os.path.join(work, f"{len(kept):04d}.json"), "w", encoding="utf-8") as f:
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
    man = {
        "book": "hard",
        "about": "subset: two artifacts of one label side by side in the truth",
        "page_count": len(kept),
        "side_by_side_pairs": pairs_total,
        "by_book": per_book,
        "pages": [{"book": b, "page_no": i} for b, i in kept],
        "truth_traits": traits,
        "source": {"name": os.path.basename(pdf), "sha256": stamp.sha256(wpdf)},
    }
    with open(wman, "w", encoding="utf-8") as f:
        json.dump(man, f, ensure_ascii=False, indent=1)
    keep = tdir + ".previous"
    if os.path.isdir(keep):
        shutil.rmtree(keep)
    if os.path.isdir(tdir):
        os.rename(tdir, keep)
        layers = os.path.join(out_dir, "truth.layers")
        if os.path.isdir(layers):
            os.rename(layers, os.path.join(keep, "layers"))
            log(f"the layers on the previous truth go with it: {keep}/layers")
    os.rename(work, tdir)
    os.replace(wpdf, pdf)
    os.replace(wman, os.path.join(out_dir, "manifest.json"))
    if os.path.isdir(keep):
        try:
            shutil.rmtree(keep)
        except OSError as e:
            log(
                f"WARNING: the previous truth is left at {keep} ({e}) -- the bench itself is whole, but that directory is a second copy and must be removed by hand"
            )
    log(f"pages {len(kept)} ({per_book}), side-by-side pairs {pairs_total}")
    for key, st in traits.items():
        log(
            f"trait {key!r}: yes {st['yes']}, no {st['no']}, NOT SAID {st['not_said']} of {len(kept)} pages"
            + (
                f" -- on those {st['not_said']} the metric over it will NOT be counted and must print NOT COMPARED"
                if st["not_said"]
                else ""
            )
        )
    log(f"{pdf} ({os.path.getsize(pdf) / 1000000.0:.0f} MB), truth in {tdir}")
    return man
