import hashlib
import json
import os
import shutil
from datasets import knobs
from datasets import identity as stamp
from datasets.age import AGING, _age, _binding, _clip_box, _rot90_box, _xform_box
from datasets.draw import DPI, FONT, FONT_MONO, PT, SynthError, _said_reset, _said_take
from datasets.truth import GROW, GUESSED, INK, KEEP, _measure, _text_check
from datasets.log import log

__all__ = ["build", "AGING", "INK", "SynthError"]


def build(out_dir: str, cases=None, seed: int = 1, aging: str = "old", book: str = "spravochnik") -> dict:
    aside = (
        os.path.join(out_dir, "truth.new"),
        os.path.join(out_dir, "truth.previous"),
        os.path.join(out_dir, f"{book}.pdf.new"),
        os.path.join(out_dir, "manifest.json.new"),
    )
    try:
        return _build(out_dir, cases, seed, aging, book)
    except BaseException:
        for p in aside:
            try:
                shutil.rmtree(p) if os.path.isdir(p) else os.unlink(p)
            except OSError:
                pass
        raise


def _build(out_dir, cases, seed, aging, book) -> dict:
    import cv2
    import numpy as np
    import pymupdf

    if aging not in AGING:
        raise SynthError(f"ageing profile {aging!r}: I know only {tuple(AGING)}")
    from datasets.books import load

    mod = load(book)
    B_CASES = mod.CASES
    B_SPREADS = getattr(mod, "SPREADS", set())
    B_ROTATE = getattr(mod, "ROTATE", {})
    names = list(cases or B_CASES)
    bad = [n for n in names if n not in B_CASES]
    if bad:
        raise SynthError(f"book {book} has no such cases: {bad}. It has: {sorted(B_CASES)}")
    for f in (FONT, FONT_MONO):
        if not os.path.exists(f):
            raise SynthError(
                f"no font {f}. The bench draws with it, and without it the pages come out blank. Install fonts-dejavu or set a path."
            )
    os.makedirs(out_dir, exist_ok=True)
    truth_dir = os.path.join(out_dir, "truth")
    work = truth_dir + ".new"
    wpdf = os.path.join(out_dir, f"{book}.pdf.new")
    wman = os.path.join(out_dir, "manifest.json.new")
    for stale in (wpdf, wman):
        if os.path.exists(stale):
            os.unlink(stale)
    if os.path.isdir(work):
        shutil.rmtree(work)
    os.makedirs(work)
    out = pymupdf.open()
    pages, counts = ([], {})
    for i, name in enumerate(names):
        doc = pymupdf.open()
        page_seed = (
            seed
            ^ int.from_bytes(hashlib.blake2b(f"{book}/{name}".encode(), digest_size=4).digest(), "big")
            & 2147483647
        )
        _said_reset()
        pg, t = B_CASES[name](doc, np.random.default_rng(page_seed))
        said = _said_take()
        raw_words = [
            (w[0] * DPI / 72.0, w[1] * DPI / 72.0, w[2] * DPI / 72.0, w[3] * DPI / 72.0, w[4])
            for w in pg.get_text("words")
        ]
        bad_id = [j for j in said if j >= len(t)]
        if bad_id:
            raise SynthError(
                f"{name}: character truth was written for blocks {bad_id}, and there are only {len(t)} truth boxes. `_say` fell behind `truth.append`: the link by block number is broken, and the characters would have gone to the wrong boxes"
            )
        pix = pg.get_pixmap(dpi=int(DPI))
        img = cv2.cvtColor(
            np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, pix.n),
            cv2.COLOR_RGB2BGR,
        )
        doc.close()
        k = DPI / 72.0
        boxes = [(x0 * k, y0 * k, x1 * k, y1 * k, lab) for x0, y0, x1, y1, lab in t]
        boxes = _measure(img, boxes, name)
        if len(boxes) != len(t):
            raise SynthError(
                f"{name}: `_measure` returned {len(boxes)} boxes against {len(t)} declared -- the block numbers have shifted, and the character truth would land on someone else's boxes"
            )
        check = _text_check(raw_words, boxes, said, name)
        left = (cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) < INK).astype(np.uint8)
        for bx in boxes:
            left[max(0, int(bx[1])) : int(round(bx[3])), max(0, int(bx[0])) : int(round(bx[2]))] = 0
        n_spots, _lbl, stats, _ctr = cv2.connectedComponentsWithStats(left, 8)
        spot = max((stats[j] for j in range(1, n_spots)), key=lambda r: r[cv2.CC_STAT_AREA], default=None)
        undecl = {"pixels": int(left.sum()), "largest_blob": None}
        spot_box = None
        if spot is not None:
            sx, sy = (int(spot[cv2.CC_STAT_LEFT]), int(spot[cv2.CC_STAT_TOP]))
            sw, sh = (int(spot[cv2.CC_STAT_WIDTH]), int(spot[cv2.CC_STAT_HEIGHT]))
            undecl["largest_blob"] = {
                "area": int(spot[cv2.CC_STAT_AREA]),
                "size_on_clean_raster": [sw, sh],
                "box": None,
            }
            spot_box = (sx, sy, sx + sw, sy + sh)
        gutter = None
        if name in B_SPREADS:
            img, gutter = _binding(img, page_seed)
        rot = B_ROTATE.get(name, 0)
        if rot == 90:
            src_h = img.shape[0]
            img = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
            boxes = [(*_rot90_box(b[:4], src_h), b[4]) for b in boxes]
            if spot_box is not None:
                spot_box = _rot90_box(spot_box, src_h)
            if gutter is not None:
                gutter = None
        img, M = _age(img, aging, page_seed)
        h, w = img.shape[:2]
        if M is not None:
            boxes = [(*_clip_box(_xform_box(b[:4], M), w, h), b[4]) for b in boxes]
            if spot_box is not None:
                spot_box = _clip_box(_xform_box(spot_box, M), w, h)
        if spot_box is not None:
            undecl["largest_blob"]["box"] = [round(v, 1) for v in spot_box]
        thin = [b for b in boxes if b[2] - b[0] < 2 or b[3] - b[1] < 2]
        if thin:
            raise SynthError(
                f"{name}: after ageing a truth box collapsed: {[(round(v, 1) for v in t[:4]) for t in thin[:2]]}"
            )
        page = out.new_page(width=w * PT, height=h * PT)
        ok, enc = cv2.imencode(".png", img)
        page.insert_image(page.rect, stream=enc.tobytes())
        from datasets import classes as policy

        blocks, art_truth = ([], {})
        no_chars = []
        for j, b in enumerate(boxes):
            rec = said.get(j, {})
            role = policy.POLICIES["PP-DocLayoutV2"].role(b[4])
            blk = {
                "block_id": j,
                "box": [round(v, 1) for v in b[:4]],
                "label": b[4],
                "score": None,
                "order": j,
                "content": None,
                "kind": "none",
            }
            if role == "artifact":
                if rec:
                    art_truth[str(j)] = rec
            else:
                txt = rec.get("text")
                if txt:
                    blk["content"] = txt
                    blk["kind"] = "text"
                else:
                    no_chars.append(f"{b[4]}#{j}")
            blocks.append(blk)
        for b in blocks:
            counts[b["label"]] = counts.get(b["label"], 0) + 1
        char_count = sum(len(b["content"]) for b in blocks if b["content"])
        word_count = sum(len(b["content"].split()) for b in blocks if b["content"])
        with_text = sum(1 for b in blocks if b["content"])
        chars = {
            "chars": char_count,
            "words": word_count,
            "blocks_with_text": with_text,
            "text_blocks_without_chars": len(no_chars),
            "which_without_chars": no_chars[:6],
            "tables_with_grid": sum(1 for v in art_truth.values() if "cells" in v),
            "cell_count": sum(v["rows"] * v["cols"] for v in art_truth.values() if "cells" in v),
        }
        with open(os.path.join(work, f"{i:04d}.json"), "w", encoding="utf-8") as f:
            json.dump(
                {
                    "index": i,
                    "width": w,
                    "height": h,
                    "dpi": DPI,
                    "blocks": blocks,
                    "raw": None,
                    "meta": {
                        "case": name,
                        "book": book,
                        "aging": aging,
                        "synth_seed": page_seed,
                        "rotation": rot,
                        "gutter": gutter,
                        "ink_outside_truth": undecl,
                        "text_marked": not no_chars,
                        "order_marked": True,
                        "char_truth": chars,
                        "text_layer_check": check,
                        "artifact_truth": art_truth,
                    },
                },
                f,
                ensure_ascii=False,
            )
        pages.append(
            {
                "case": name,
                "page": i,
                "size": [w, h],
                "block_count": len(blocks),
                "rotation": rot,
                "spread": name in B_SPREADS,
                "ink_outside_truth": undecl,
                "char_truth": chars,
                "text_layer_check": check,
            }
        )
        big = undecl["largest_blob"]
        log(
            f"  {i:2d} {name:22s} {w}x{h}, blocks {len(blocks)}"
            + ("  (spread)" if name in B_SPREADS else "")
            + (f"  (rotated {rot} deg)" if rot else "")
            + f", outside truth {undecl['pixels']} px"
            + (
                f" (blob {big['size_on_clean_raster'][0]}x{big['size_on_clean_raster'][1]} = {big['area']} px)"
                if big
                else ""
            )
            + f"; chars {chars['chars']}, words {chars['words']} in {chars['blocks_with_text']} blocks"
            + (
                f", NO CHARS {chars['text_blocks_without_chars']} ({', '.join(chars['which_without_chars'])})"
                if no_chars
                else ""
            )
            + (
                f", cells {chars['cell_count']} in {chars['tables_with_grid']} tables"
                if chars["tables_with_grid"]
                else ""
            )
            + f"; words outside truth {check['outside_truth']}"
            + (f" {check['outside_truth_samples']}" if check["outside_truth"] else "")
            + (f", NOT IN LAYER {check['missing_from_layer']}" if check["missing_from_layer"] else "")
            + (f", UNEXPLAINED {check['unexplained']}" if check["unexplained"] else "")
            + (f" {check['mismatch_examples']}" if check["mismatch_examples"] else "")
            + f", ghosts {check['ghosts']}"
            + (f", leaders {check['dot_leaders']}" if check["dot_leaders"] else "")
        )
    pdf = os.path.join(out_dir, f"{book}.pdf")
    out.save(wpdf, garbage=3, deflate=True, no_new_id=True)
    out.close()

    def total_of(key, margin):
        return sum(pp[key][margin] for pp in pages)

    total = {
        "chars": total_of("char_truth", "chars"),
        "words": total_of("char_truth", "words"),
        "blocks_with_text": total_of("char_truth", "blocks_with_text"),
        "text_blocks_without_chars": total_of("char_truth", "text_blocks_without_chars"),
        "tables_with_grid": total_of("char_truth", "tables_with_grid"),
        "cell_count": total_of("char_truth", "cell_count"),
        "words_outside_truth": total_of("text_layer_check", "outside_truth"),
        "missing_from_layer": total_of("text_layer_check", "missing_from_layer"),
        "unexplained": total_of("text_layer_check", "unexplained"),
        "ghosts": total_of("text_layer_check", "ghosts"),
        "dot_leaders": total_of("text_layer_check", "dot_leaders"),
        "words_in_text_layer_total": total_of("text_layer_check", "words_in_layer"),
    }
    here = os.path.dirname(os.path.abspath(__file__))
    package = {
        f: stamp.sha256(os.path.join(here, f)) for f in ("__init__.py", "draw.py", "age.py", "truth.py")
    }
    man = {
        "book": book,
        "about": getattr(mod, "ABOUT", ""),
        "page_count": len(pages),
        "synth_seed": seed,
        "aging": aging,
        "generator": {
            "file": "datasets/synth.py",
            "sha256": package["__init__.py"],
            "package": package,
            "commit": stamp.commit(),
            "cases": names,
            "book": book,
            "sha256_book_module": stamp.sha256(mod.__file__),
            "guessed_labels": sorted(GUESSED),
            "INK": INK,
            "KEEP": KEEP,
            "GROW": GROW,
        },
        "knobs": knobs.snapshot() if hasattr(knobs, "snapshot") else None,
        "aging_params": AGING[aging],
        "fonts": {
            os.path.basename(FONT): stamp.sha256(FONT),
            os.path.basename(FONT_MONO): stamp.sha256(FONT_MONO),
        },
        "source": {"name": os.path.basename(pdf), "sha256": stamp.sha256(wpdf)},
        "blocks_by_label": counts,
        "char_truth": total,
        "pages": pages,
    }
    with open(wman, "w", encoding="utf-8") as f:
        json.dump(man, f, ensure_ascii=False, indent=1)
    keep = truth_dir + ".previous"
    if os.path.isdir(keep):
        shutil.rmtree(keep)
    if os.path.isdir(truth_dir):
        os.rename(truth_dir, keep)
    os.rename(work, truth_dir)
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
        f"pages {len(pages)}, truth blocks {sum(counts.values())} ({', '.join((f'{k} {v}' for k, v in sorted(counts.items())))})"
    )
    log(
        f"character truth: {total['chars']} chars, {total['words']} words in {total['blocks_with_text']} blocks"
        + (
            f"; text blocks with NO CHARS {total['text_blocks_without_chars']}"
            if total["text_blocks_without_chars"]
            else ""
        )
        + f"; tables with a grid {total['tables_with_grid']}, cells {total['cell_count']}"
    )
    log(
        f"words drawn outside every truth box: {total['words_outside_truth']} of {total['words_in_text_layer_total']} in the text layer"
    )
    log(
        f"against the text layer: not in the layer {total['missing_from_layer']}, unexplained {total['unexplained']}, ghosts of a re-fill {total['ghosts']}, dot leaders {total['dot_leaders']}"
    )
    log(f"{pdf} ({os.path.getsize(pdf) / 1000000.0:.1f} MB), truth in {truth_dir}")
    return man
