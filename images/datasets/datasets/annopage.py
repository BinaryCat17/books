"""AnnoPage: THE GOLDEN BENCH -- real pages, truth from librarians"""

import json
import os
import shutil
from datasets import knobs
from datasets import identity as stamp
from datasets.errors import Refusal
from datasets.log import log

DIRECT = {
    "Table": "table",
    "Graph": "chart",
    "Diagram": "chart",
    "Image": "image",
    "Photograph": "image",
    "Geometric drawing": "image",
    "Other technical drawing": "image",
    "Floor plan": "image",
    "Mathematical expression and equation": "display_formula",
    "Chemical formula and equation": "display_formula",
    "Stamp": "seal",
}
DOUBTFUL = (
    "Map",
    "Advertisement",
    "Musical notation",
    "Handwritten note",
    "Caricature and comics",
    "Barcode and QR code",
)
INEXPRESSIBLE = (
    "Initial",
    "Vignette",
    "Frieze",
    "Exlibris",
    "Signet",
    "Decorative inscription",
    "Other book decor",
    "Symbol, logo, coat of arms",
)


class AnnoPageError(Refusal):
    pass


def _yaml_names(root):
    p = os.path.join(root, "dataset.yaml")
    if not os.path.exists(p):
        return None
    out, inside = ({}, False)
    for line in open(p, encoding="utf-8"):
        if line.startswith("names:"):
            inside = True
            continue
        if inside:
            if line.strip() and (not line[0].isspace()):
                break
            if ":" not in line:
                continue
            k, v = line.split(":", 1)
            k = k.strip()
            if k.isdigit():
                out[int(k)] = v.strip()
    return out or None


def _classes(root):
    p = os.path.join(root, "classes.txt")
    if not os.path.exists(p):
        raise AnnoPageError(f"no {p}: this is not an AnnoPage root")
    names = [l.strip() for l in open(p, encoding="utf-8") if l.strip()]
    known = set(DIRECT) | set(DOUBTFUL) | set(INEXPRESSIBLE)
    unknown = [n for n in names if n not in known]
    if unknown:
        raise AnnoPageError(
            f'the dataset holds categories we have said nothing about: {unknown}. There is no default on purpose -- a silent "inexpressible" would turn into an eternal undercount with no explanation.'
        )
    ymap = _yaml_names(root)
    if ymap is not None:
        wrong = [(i, n, ymap.get(i)) for i, n in enumerate(names) if ymap.get(i) != n]
        if wrong or len(ymap) != len(names):
            raise AnnoPageError(
                f"classes.txt and dataset.yaml disagree: {len(names)} names against {len(ymap)}, first divergence {(wrong[0] if wrong else '--')} (index, classes.txt, dataset.yaml). The label in the annotation is an INDEX, and on a divergence the whole bench truth would be folded under foreign labels silently."
            )
    return names


def build(
    root: str, out_dir: str, split: str = "test", limit: int = 0, truth_only: bool = False
) -> dict:
    aside = (
        os.path.join(out_dir, "truth.new"),
        os.path.join(out_dir, "truth.previous"),
        os.path.join(out_dir, "annopage.pdf.new"),
        os.path.join(out_dir, "manifest.json.new"),
    )
    try:
        return _build(root, out_dir, split, limit, truth_only)
    except BaseException:
        for p in aside:
            try:
                shutil.rmtree(p) if os.path.isdir(p) else os.unlink(p)
            except OSError:
                pass
        raise


def _build(root, out_dir, split, limit, truth_only) -> dict:
    import cv2
    import pymupdf

    dpi = knobs.number("PAGE_DPI")
    if dpi <= 0:
        raise AnnoPageError(f"PAGE_DPI = {dpi}: the sheet scale is not positive")
    scale = 72.0 / dpi
    names = _classes(root)
    ldir = os.path.join(root, "labels", split)
    idir = os.path.join(root, "images", split)
    if not (os.path.isdir(ldir) and os.path.isdir(idir)):
        raise AnnoPageError(f"no {ldir} or {idir}")
    stems = sorted((f[:-4] for f in os.listdir(ldir) if f.endswith(".txt")))
    os.makedirs(out_dir, exist_ok=True)
    tdir = os.path.join(out_dir, "truth")
    work = tdir + ".new"
    if os.path.isdir(work):
        shutil.rmtree(work)
    os.makedirs(work)
    images = {}
    for stem in stems:
        for ext in (".jpg", ".jpeg", ".png", ".tif", ".tiff"):
            p = os.path.join(idir, stem + ext)
            if os.path.exists(p):
                images[stem] = p
                break
    skipped_no_image = len(stems) - len(images)
    doc = pymupdf.open()
    pages, counts = ([], {"direct": {}, "doubtful": {}, "inexpressible": {}})
    used = 0
    for stem in stems:
        img_path = images.get(stem)
        if img_path is None:
            continue
        if limit and used >= limit:
            break
        im = cv2.imread(img_path)
        if im is None:
            raise AnnoPageError(f"{img_path} does not read")
        h, w = im.shape[:2]
        blocks, outside = ([], [])
        drop = {"doubtful": 0, "inexpressible": 0}
        with open(os.path.join(ldir, stem + ".txt"), encoding="utf-8") as f:
            for line in f:
                q = line.split()
                if len(q) < 5:
                    continue
                cat = names[int(q[0])]
                cx, cy, bw, bh = (float(v) for v in q[1:5])
                box = [(cx - bw / 2) * w, (cy - bh / 2) * h, (cx + bw / 2) * w, (cy + bh / 2) * h]
                if cat in DIRECT:
                    lab = DIRECT[cat]
                    counts["direct"][cat] = counts["direct"].get(cat, 0) + 1
                    blocks.append(
                        {
                            "block_id": len(blocks),
                            "box": [round(v, 1) for v in box],
                            "label": lab,
                            "score": None,
                            "order": len(blocks),
                            "content": None,
                            "kind": "none",
                            "source_category": cat,
                        }
                    )
                else:
                    kind = "doubtful" if cat in DOUBTFUL else "inexpressible"
                    counts[kind][cat] = counts[kind].get(cat, 0) + 1
                    drop[kind] += 1
                    outside.append(
                        {"box": [round(v, 1) for v in box], "category": cat, "bucket": kind}
                    )
        if not truth_only:
            page = doc.new_page(width=w * scale, height=h * scale)
            with open(img_path, "rb") as f:
                page.insert_image(page.rect, stream=f.read())
        with open(os.path.join(work, f"{used:04d}.json"), "w", encoding="utf-8") as f:
            json.dump(
                {
                    "index": used,
                    "width": w,
                    "height": h,
                    "dpi": dpi,
                    "blocks": blocks,
                    "raw": None,
                    "meta": {
                        "case": stem[:8],
                        "book": "annopage",
                        "file": os.path.basename(img_path),
                        "objects_out_of_scope": drop,
                        "out_of_scope": outside,
                        "text_marked": False,
                        "order_marked": False,
                    },
                },
                f,
                ensure_ascii=False,
            )
        pages.append(
            {
                "page": used,
                "size": [w, h],
                "file": stem,
                "block_count": len(blocks),
                "out_of_scope": drop,
            }
        )
        used += 1
        if used % 50 == 0:
            log(f"  {used} pages")
    if not pages:
        raise AnnoPageError("not one page was assembled")
    pdf = os.path.join(out_dir, "annopage.pdf")
    wpdf, wman = (pdf + ".new", os.path.join(out_dir, "manifest.json.new"))
    for stale in (wpdf, wman):
        if os.path.exists(stale):
            os.unlink(stale)
    if truth_only:
        doc.close()
        if not os.path.exists(pdf):
            raise AnnoPageError(f"no {pdf}: with --truth-only it must already exist")
        import pymupdf as _pm

        chk = _pm.open(pdf)
        if chk.page_count != len(pages):
            n = chk.page_count
            chk.close()
            raise AnnoPageError(
                f"{pdf} holds {n} pages while the truth was rewritten for {len(pages)}: these are different samples."
            )
        for rec in pages:
            r = chk[rec["page"]].rect
            w, h = rec["size"]
            if abs(r.width - w * scale) > 0.6 or abs(r.height - h * scale) > 0.6:
                chk.close()
                raise AnnoPageError(
                    f"page {rec['page']}: a sheet of {r.width:.0f}x{r.height:.0f} pt does not match the raster {w}x{h} -- this truth is not about this pdf."
                )
        chk.close()
    else:
        doc.save(wpdf, garbage=3, deflate=True)
        doc.close()
    n_direct = sum(counts["direct"].values())
    man = {
        "book": "annopage",
        "about": "AnnoPage: 7550 annotations over 5690 pages, marked by librarians, NON-TEXT objects only",
        "origin": "Zenodo 10.5281/zenodo.12788419, CC BY 4.0",
        "split": split,
        "page_count": len(pages),
        "PAGE_DPI": dpi,
        "text_marked": False,
        "objects_in_scope": n_direct,
        "objects_out_of_scope": {
            "doubtful": sum(counts["doubtful"].values()),
            "inexpressible": sum(counts["inexpressible"].values()),
        },
        "by_category": counts,
        "category_map": DIRECT,
        "annotations_without_image": skipped_no_image,
        "source": {
            "name": os.path.basename(pdf),
            "sha256": stamp.sha256(wpdf if os.path.exists(wpdf) else pdf),
        },
    }
    with open(wman, "w", encoding="utf-8") as f:
        json.dump(man, f, ensure_ascii=False, indent=1)
    keep = tdir + ".previous"
    if os.path.isdir(keep):
        shutil.rmtree(keep)
    if os.path.isdir(tdir):
        os.rename(tdir, keep)
    os.rename(work, tdir)
    if os.path.exists(wpdf):
        os.replace(wpdf, pdf)
    os.replace(wman, os.path.join(out_dir, "manifest.json"))
    if os.path.isdir(keep):
        try:
            shutil.rmtree(keep)
        except OSError as e:
            log(
                f"WARNING: the previous truth is left at {keep} ({e}) -- the bench itself is whole, but that is a second copy and must be removed by hand"
            )
    log(
        f"pages {len(pages)}, {n_direct} objects enter the scoring; outside it: doubtful {man['objects_out_of_scope']['doubtful']}, inexpressible {man['objects_out_of_scope']['inexpressible']}"
    )
    log(f"annotations without an image skipped: {skipped_no_image}")
    log(f"{pdf} ({os.path.getsize(pdf) / 1000000.0:.0f} MB), truth in {tdir}")
    return man
