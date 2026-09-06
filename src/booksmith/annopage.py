"""AnnoPage: THE GOLDEN BENCH -- real pages, truth from librarians.

What the synthetic bench cannot give: it is drawn with a font, not printed by
letterpress, and says nothing about reading characters -- its own header says
so. AnnoPage is **7550 annotation files** to **5690** published pages of
historical documents, marked by experts over 25 non-text categories. Here stood
"7550 pages", which is wrong: the difference of 1860 is annotations pointing at
pages of OTHER datasets the archive does not hold (exactly that many lines in
`images.txt`), and they are the same "annotations without an image" counter.
Zenodo, DOI 10.5281/zenodo.12788419, CC BY 4.0.

WHAT THERE IS NOTHING TO SAY ABOUT, WHICH IS NOT THE SAME AS "WRONG". The
archive says only "mostly from czech written documents" (`README.md`) -- no
date, no methodology, and no DOI inside the ZIP (listed exhaustively: 13252
entries). "1485 and later, mostly Czech and German, by the Czech methodology"
stood here and is removed: nothing here can check it, which is not the same as
calling it an invention.

WHAT IS MARKED AND WHAT IS NOT. ONLY non-text objects, 25 categories. The truth
holds no text blocks at all, so this bench measures artifact localisation and
nothing else. The report line "text and service" must say "no data" on it, not
"zero": different zeros.

THREE BUCKETS OF CATEGORIES, AND THE BORDER IS OUR DECISION, DECLARED ALOUD.

* `DIRECT` -- our model has a label for exactly this. Only these enter the
  measurement.
* `DOUBTFUL` -- the match is plausible but not unambiguous (map, advertisement,
  musical notation, handwritten note). Collapsing them to `image` would decide
  a disputed case for the model and credit us with finds we did not make.
* `INEXPRESSIBLE` -- book decor: initial, vignette, frieze, exlibris, signet,
  ornament. PP-DocLayoutV2's vocabulary holds nothing about it, so a miss here
  would be the VOCABULARY's miss, not the model's.

Doubtful and inexpressible are not dropped in silence: their counts print
beside the total, so "found 40 %" cannot be read as "40 % of the page parsed".
"""
import hashlib
import json
import os
import shutil

from .run import knobs

# --- direct match: only this enters the measurement -----------------------
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
# --- plausible but disputed: does NOT enter the measurement ---------------
DOUBTFUL = ("Map", "Advertisement", "Musical notation", "Handwritten note",
            "Caricature and comics", "Barcode and QR code")
# --- inexpressible by our model at all ------------------------------------
INEXPRESSIBLE = ("Initial", "Vignette", "Frieze", "Exlibris", "Signet",
                 "Decorative inscription", "Other book decor",
                 "Symbol, logo, coat of arms")


class AnnoPageError(RuntimeError):
    pass


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _yaml_names(root):
    """The "index -> name" map from `dataset.yaml`. `None` if there is no file.

    Parsed in five lines rather than by a library: one flat `names:` section of
    "  0: Name", not worth dragging `yaml` into the module for. Split on the
    FIRST colon -- category names hold commas, and may one day hold a colon.
    """
    p = os.path.join(root, "dataset.yaml")
    if not os.path.exists(p):
        return None
    out, inside = {}, False
    for line in open(p, encoding="utf-8"):
        if line.startswith("names:"):
            inside = True
            continue
        if inside:
            if line.strip() and not line[0].isspace():
                break                          # the section has ended
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
        raise AnnoPageError(f"нет {p}: это не корень AnnoPage")
    names = [l.strip() for l in open(p, encoding="utf-8") if l.strip()]
    known = set(DIRECT) | set(DOUBTFUL) | set(INEXPRESSIBLE)
    unknown = [n for n in names if n not in known]
    if unknown:
        raise AnnoPageError(
            f"в датасете есть категории, о которых мы не высказались: "
            f"{unknown}. Умолчания нет нарочно — молчаливое «невыразимо» "
            f"превратилось бы в вечный недобор без объяснения.")
    # THE ORDER OF THE LINES IS CHECKED AGAINST A SECOND SOURCE, not taken on
    # faith: until now only the SET of names was checked. The price of missing
    # it: swap `Table` and `Vignette` in `classes.txt` and the build passes in
    # silence while the measurement gets 1121 objects instead of 1232 and 13
    # tables instead of 124 -- the whole golden bench sails, and nothing says
    # so. The second source lies in the same archive and had never been read
    # once. (Today they AGREE, 25 of 25 -- the truth is intact; the guard is
    # set not after an accident but so that there is none.)
    ymap = _yaml_names(root)
    if ymap is not None:
        wrong = [(i, n, ymap.get(i)) for i, n in enumerate(names)
                 if ymap.get(i) != n]
        if wrong or len(ymap) != len(names):
            raise AnnoPageError(
                f"classes.txt и dataset.yaml расходятся: имён {len(names)} "
                f"против {len(ymap)}, первое расхождение "
                f"{wrong[0] if wrong else '—'} (индекс, classes.txt, "
                f"dataset.yaml). Метка в разметке — это ИНДЕКС, и при "
                f"расхождении вся истина стенда собралась бы под чужими "
                f"ярлыками молча.")
    return names


def build(root: str, out_dir: str, split: str = "test", limit: int = 0,
          truth_only: bool = False, log=print) -> dict:
    """Fold a bench book out of AnnoPage: a PDF plus truth in our format.

    A page gets the size at which rendering at `PAGE_DPI` returns EXACTLY the
    source raster: then truth coordinates and model boxes live in one system
    and nothing has to be converted.
    """
    import cv2
    import pymupdf

    # THE SCALE COMES FROM THE DECLARED KNOB, not from a wired-in 0.5 = 72/144
    # that was true only at the default: raise `PAGE_DPI` to 300 and the bench
    # would be built about a raster four times smaller than declared while the
    # truth went on writing "dpi: 144.0". Caught by the size check in `metrics`
    # -- a FOREIGN file, and not always; the builder itself was silent. Read
    # through the registry, or the run misses the snapshot.
    dpi = float(knobs.knob("PAGE_DPI"))
    if dpi <= 0:
        raise AnnoPageError(f"PAGE_DPI = {dpi}: масштаб листа неположителен")
    scale = 72.0 / dpi

    names = _classes(root)
    ldir = os.path.join(root, "labels", split)
    idir = os.path.join(root, "images", split)
    if not (os.path.isdir(ldir) and os.path.isdir(idir)):
        raise AnnoPageError(f"нет {ldir} или {idir}")

    stems = sorted(f[:-4] for f in os.listdir(ldir) if f.endswith(".txt"))
    os.makedirs(out_dir, exist_ok=True)
    tdir = os.path.join(out_dir, "truth")
    # TRUTH IS WRITTEN ASIDE AND SWAPPED IN ONLY AFTER THE GUARDS. `truth/` was
    # cleared HERE while the `--truth-only` guards (page count, sheet size)
    # stood a hundred lines below, after the main loop -- telling the truth,
    # and telling it LATE. On a copy of the bench `build(..., limit=5,
    # truth_only=True)` killed the build with "600 pages, truth rewritten to 5:
    # different samples", and by that moment FIVE of the 600 good truth files
    # were left: 595 destroyed by a refusal meant to protect them. Recovered by
    # `git checkout`, and only because this bench is tracked; in a fresh
    # directory, by nothing.
    work = tdir + ".новая"
    if os.path.isdir(work):
        shutil.rmtree(work)
    os.makedirs(work)

    # 1860 annotations point at pages of OTHER datasets the archive does not
    # hold. Not a loss but a declared property of the SAMPLE, so it is counted
    # before the main loop and over the whole sample. Inside the loop the count
    # broke off at --limit with it: `--split train --limit 5` printed "without
    # image 178" against an honest 1860, and on a sample whose gaps come after
    # the limit, a flat 0 -- "did not get there" dressed as "no gaps". The
    # pre-pass costs 0.1 s over 6950 annotations, only os.path.exists.
    images = {}
    for stem in stems:
        for ext in (".jpg", ".jpeg", ".png", ".tif", ".tiff"):
            p = os.path.join(idir, stem + ext)
            if os.path.exists(p):
                images[stem] = p
                break
    skipped_no_image = len(stems) - len(images)

    doc = pymupdf.open()
    pages, counts = [], {"direct": {}, "doubtful": {}, "inexpressible": {}}
    used = 0
    for stem in stems:
        img_path = images.get(stem)
        if img_path is None:
            continue
        if limit and used >= limit:
            break
        im = cv2.imread(img_path)
        if im is None:
            raise AnnoPageError(f"не читается {img_path}")
        h, w = im.shape[:2]

        blocks, outside = [], []
        drop = {"doubtful": 0, "inexpressible": 0}
        with open(os.path.join(ldir, stem + ".txt"), encoding="utf-8") as f:
            for line in f:
                q = line.split()
                if len(q) < 5:
                    continue
                cat = names[int(q[0])]
                cx, cy, bw, bh = (float(v) for v in q[1:5])
                box = [(cx - bw / 2) * w, (cy - bh / 2) * h,
                       (cx + bw / 2) * w, (cy + bh / 2) * h]
                if cat in DIRECT:
                    lab = DIRECT[cat]
                    counts["direct"][cat] = counts["direct"].get(cat, 0) + 1
                    blocks.append({"block_id": len(blocks),
                                   "box": [round(v, 1) for v in box],
                                   "label": lab, "score": None,
                                   "order": len(blocks), "content": None,
                                   "kind": "none", "source_category": cat})
                else:
                    kind = "doubtful" if cat in DOUBTFUL else "inexpressible"
                    counts[kind][cat] = counts[kind].get(cat, 0) + 1
                    drop[kind] += 1
                    # The box STAYS in the truth, in a list of its own. Drop
                    # it and every model box landing on an advertisement or an
                    # initial would count as superfluous -- and the model is
                    # not at fault there: we failed to express the category.
                    outside.append({"box": [round(v, 1) for v in box],
                                    "category": cat, "bucket": kind})

        if not truth_only:
            page = doc.new_page(width=w * scale, height=h * scale)
            with open(img_path, "rb") as f:
                page.insert_image(page.rect, stream=f.read())
        with open(os.path.join(work, f"{used:04d}.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"index": used, "width": w, "height": h, "dpi": dpi,
                       "blocks": blocks, "raw": None,
                       "meta": {"case": stem[:8], "book": "annopage",
                                "file": os.path.basename(img_path),
                                "objects_out_of_scope": drop,
                                "out_of_scope": outside,
                                # NO text blocks in the truth AT ALL.
                                "text_marked": False,
                                # AND NO READING ORDER EITHER. The `order`
                                # below is the line number in the annotation
                                # file, and that file is grouped by class: on
                                # page 51 orders 0,1,2,3 sit at y0 = 1560,
                                # 3004, 673, 4129. Checking anyone's reading
                                # order against it measures a different
                                # quantity; the metric reads this flag and
                                # prints a dash.
                                "order_marked": False}}, f,
                      ensure_ascii=False)
        pages.append({"page": used, "size": [w, h], "file": stem,
                      "block_count": len(blocks), "out_of_scope": drop})
        used += 1
        if used % 50 == 0:
            log(f"  {used} страниц")

    if not pages:
        raise AnnoPageError("ни одной страницы не собрано")
    pdf = os.path.join(out_dir, "annopage.pdf")
    if truth_only:
        doc.close()
        if not os.path.exists(pdf):
            raise AnnoPageError(f"нет {pdf}: с --truth-only он должен уже быть")
        # Page COUNT AND SIZE both: rewriting truth under a foreign pdf is the
        # trouble the sha256 check in `books score` guards, coming in here by
        # the back door.
        import pymupdf as _pm
        chk = _pm.open(pdf)
        if chk.page_count != len(pages):
            n = chk.page_count
            chk.close()
            raise AnnoPageError(
                f"в {pdf} страниц {n}, а истина переписана на {len(pages)}: "
                f"это разные выборки.")
        for rec in pages:
            r = chk[rec["page"]].rect
            w, h = rec["size"]
            if abs(r.width - w * scale) > 0.6 or abs(r.height - h * scale) > 0.6:
                chk.close()
                raise AnnoPageError(
                    f"стр. {rec['page']}: лист {r.width:.0f}x{r.height:.0f} "
                    f"пт не соответствует растру {w}x{h} — истина не про этот "
                    f"pdf.")
        chk.close()
    else:
        doc.save(pdf, garbage=3, deflate=True)
        doc.close()

    # Guards passed -- now it may be swapped. Old aside, new into place, old
    # removed: break in the middle and either the previous truth or the new one
    # is left standing, never emptiness.
    keep = tdir + ".прежняя"
    if os.path.isdir(keep):
        shutil.rmtree(keep)
    if os.path.isdir(tdir):
        os.rename(tdir, keep)
    os.rename(work, tdir)
    if os.path.isdir(keep):
        shutil.rmtree(keep)

    n_direct = sum(counts["direct"].values())
    man = {"book": "annopage",
           "about": "AnnoPage: 7550 разметок к 5690 страницам, "
                      "разметка библиотекарями, только НЕТЕКСТОВЫЕ объекты",
           "origin": "Zenodo 10.5281/zenodo.12788419, CC BY 4.0",
           "split": split, "page_count": len(pages), "PAGE_DPI": dpi,
           "text_marked": False,
           "objects_in_scope": n_direct,
           "objects_out_of_scope": {
               "doubtful": sum(counts["doubtful"].values()),
               "inexpressible": sum(counts["inexpressible"].values())},
           "by_category": counts,
           "category_map": DIRECT,
           "annotations_without_image": skipped_no_image,
           "pdf": os.path.basename(pdf), "sha256 pdf": _sha256(pdf)}
    with open(os.path.join(out_dir, "manifest.json"), "w",
              encoding="utf-8") as f:
        json.dump(man, f, ensure_ascii=False, indent=1)
    log(f"страниц {len(pages)}, в замер идёт {n_direct} объектов; "
        f"вне замера: спорных {man['objects_out_of_scope']['doubtful']}, "
        f"невыразимых {man['objects_out_of_scope']['inexpressible']}")
    log(f"разметок без картинки пропущено {skipped_no_image}")
    log(f"{pdf} ({os.path.getsize(pdf)/1e6:.0f} МБ), истина в {tdir}")
    return man
