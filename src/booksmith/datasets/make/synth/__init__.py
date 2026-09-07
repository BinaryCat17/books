"""Synthetic bench: old-handbook pages with exact truth.

WHY. Contour metrics cannot be checked on real scans: there is no truth for
them, and truth borrowed from another model is what this project already
deleted. Here it is given BY CONSTRUCTION -- we drew the box.

THE LESSON OF THIS FILE, PAID FOR WITH TWO FALSE CONCLUSIONS.
`insert_textbox` draws **nothing** when the text does not fit, and silently
returns a negative number. My first two editions shipped pages with blank
paper where the prose should be, and the conclusion drawn from them was "the
detector cannot see synthetics". It saw exactly what was there. So every call
is checked here, and `_fill` packs the box to capacity.

AGING IS NOT DECORATION, IT CHANGES THE MODEL'S ANSWER -- measured, see `_age`.

TRUTH OF CHARACTERS, NOT ONLY OF BOXES. The bench draws the text and knows it
letter by letter -- and used to throw it away: `content` was `None` on every
block of all six books. Now a block of role text/service carries `content`
(93 pages, 1211 blocks, 393 847 characters, 73 863 words), and a table carries
rows, columns and every cell's text (52 tables, 7743 cells) in
`meta["artifact_truth"]` by block id. An artifact keeps `content` null, a value
-- see `build`. This is the only place in the project where text is known other
than on another model's word: the old reading quality numbers were annulled for
being measured against Mistral OCR output.

WHAT IT DOES NOT GIVE. It does not reproduce fifties letterpress on yellowed
paper -- the kind that reads `Laths` for `Lathes`. Its glyphs are clean and
ours, so it measures ASSEMBLY FIDELITY (what arrived, where it landed, whether
a cell was lost), not reading robustness to typographic damage. That needs the
golden bench, hand-marked on real pages.
"""
import hashlib
import json
import os
import shutil

from booksmith.core import knobs
from booksmith.core import stamp
from booksmith.datasets.make.synth.age import (AGING, _age, _binding, _clip_box,
                                               _rot90_box, _xform_box)
from booksmith.datasets.make.synth.draw import (DPI, FONT, FONT_MONO, PT, SynthError,
                                                _said_reset, _said_take)
from booksmith.datasets.make.synth.truth import (GROW, GUESSED, INK, KEEP, _measure,
                                                 _text_check)

__all__ = ["build", "AGING", "INK", "SynthError"]

def build(out_dir: str, cases=None, seed: int = 1, aging: str = "old",
          book: str = "spravochnik", log=print) -> dict:
    """Build the synthetic book: a PDF plus exact truth for every page.

    The product is an ordinary PDF, so `books detect`, `books html` and
    `books crop` work on it unamended: the bench is not a separate pipeline,
    just such a book with a known answer.

    NOTHING HALF-BUILT SURVIVES A REFUSAL. The aside files are removed on the
    way out unless the swap completed -- `bench/<book>/truth.new` beside a
    tracked bench is a partial second copy of the truth, and the next reader
    has no way to tell which one is the bench.
    """
    # `truth.previous` too: the swap leaves the old truth aside under that
    # name, and a bench directory ignores neither it nor `truth.new`.
    aside = (os.path.join(out_dir, "truth.new"),
             os.path.join(out_dir, "truth.previous"),
             os.path.join(out_dir, f"{book}.pdf.new"),
             os.path.join(out_dir, "manifest.json.new"))
    try:
        return _build(out_dir, cases, seed, aging, book, log)
    except BaseException:
        for p in aside:
            try:
                shutil.rmtree(p) if os.path.isdir(p) else os.unlink(p)
            except OSError:
                pass                  # the refusal is the news, not this
        raise


def _build(out_dir, cases, seed, aging, book, log) -> dict:
    import cv2
    import numpy as np
    import pymupdf

    if aging not in AGING:
        raise SynthError(f"ageing profile {aging!r}: I know only {tuple(AGING)}")
    from booksmith.datasets.make.synth.books import load
    mod = load(book)
    B_CASES = mod.CASES
    B_SPREADS = getattr(mod, "SPREADS", set())
    B_ROTATE = getattr(mod, "ROTATE", {})
    names = list(cases or B_CASES)
    bad = [n for n in names if n not in B_CASES]
    if bad:
        raise SynthError(f"book {book} has no such cases: {bad}. "
                         f"It has: {sorted(B_CASES)}")
    for f in (FONT, FONT_MONO):
        if not os.path.exists(f):
            raise SynthError(
                f"no font {f}. The bench draws with it, and without it the "
                f"pages come out blank. Install fonts-dejavu or set a path.")

    os.makedirs(out_dir, exist_ok=True)
    truth_dir = os.path.join(out_dir, "truth")
    # WRITTEN ASIDE AND SWAPPED IN ONLY AFTER THE LAST REFUSAL -- the third of
    # the three bench builders to learn this, and the same accident each time.
    # `truth/` was emptied HERE, before a loop that raises `SynthError` eight
    # ways (an empty truth box, a `_say` out of step with `truth.append`, a
    # box count that does not match, a collapsed box after ageing, a page that
    # will not re-compress). Any of them left the bench a MIXTURE: some truth
    # files from the new build, the rest destroyed, the pdf and manifest from
    # the old one. Cheaper here than on the golden bench, since synth rebuilds
    # from a seed -- but a mixture is not a bench, and nothing said so.
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
    pages, counts = [], {}
    for i, name in enumerate(names):
        doc = pymupdf.open()
        # Seed by CASE NAME, not by position: positional seeding meant that
        # inserting one page silently changed the aging of every page after it,
        # and two runs with different `--cases` were incomparable.
        page_seed = seed ^ (int.from_bytes(
            hashlib.blake2b(f"{book}/{name}".encode(), digest_size=4).digest(),
            "big") & 0x7FFFFFFF)
        _said_reset()
        pg, t = B_CASES[name](doc, np.random.default_rng(page_seed))
        said = _said_take()
        # The text layer is taken from the CLEAN page and before `doc.close()`:
        # after rasterizing and aging it is gone, the page becomes an image.
        # Coordinates are in points -- converted by the same k as the boxes.
        raw_words = [(w[0] * DPI / 72.0, w[1] * DPI / 72.0,
                      w[2] * DPI / 72.0, w[3] * DPI / 72.0, w[4])
                     for w in pg.get_text("words")]
        bad_id = [j for j in said if j >= len(t)]
        if bad_id:
            raise SynthError(
                f"{name}: character truth was written for blocks {bad_id}, "
                f"and there are only {len(t)} truth boxes. `_say` fell behind "
                f"`truth.append`: the link by block number is broken, and the "
                f"characters would have gone to the wrong boxes")
        pix = pg.get_pixmap(dpi=int(DPI))
        img = cv2.cvtColor(
            np.frombuffer(pix.samples, np.uint8)
              .reshape(pix.height, pix.width, pix.n), cv2.COLOR_RGB2BGR)
        doc.close()

        # The truth was drawn in POINTS -- converted to raster pixels, then
        # MEASURED against the clean raster: a declared box is intent, ink is
        # fact, and the model must be measured against the fact.
        k = DPI / 72.0
        boxes = [(x0 * k, y0 * k, x1 * k, y1 * k, lab) for x0, y0, x1, y1, lab in t]
        boxes = _measure(img, boxes, name)
        if len(boxes) != len(t):
            raise SynthError(
                f"{name}: `_measure` returned {len(boxes)} boxes against "
                f"{len(t)} declared -- the block numbers have shifted, and the "
                f"character truth would land on someone else's boxes")
        # On the CLEAN page and the MEASURED boxes: aging is out (no text
        # layer after rasterizing) and so is rotation (it happens below, and
        # turning the words by the same two matrices gains the number nothing).
        check = _text_check(raw_words, boxes, said, name)

        # THE OTHER SIDE OF THE SAME CHECK: ink WITHOUT a truth box.
        # `_measure` holds one side -- no truth box without ink under it -- and
        # NOTHING held the other: the bench kept quiet about what was drawn and
        # not declared, and the number looked healthy. And so it went:
        # `contents_dots` declared a 68 pt box under the word "CONTENTS", whose
        # width is 73 pt, and the last letter stayed outside the truth (a blob
        # 13x18 px = 93 px). That box is now laid by measure (`_text_w`, as in
        # `_caption`) and the number fell 93 -> 0.
        #
        # A MAGNITUDE, NOT A BAN AND NOT AN AMNESTY. Some ink outside the truth
        # is drawn ON PURPOSE: the drawing frame along the sheet edge (17030 px
        # over three atlas pages), the rules under running heads and over
        # footnotes, the dictionary column rules. No "outside the measurement"
        # field as annopage has, and there will not be one: there the amnesty
        # covers a librarian's category our dictionary cannot express, here we
        # drew it ourselves, and forgiving the model our own box would decide
        # for it where it may err. So the magnitude is counted and logged: a
        # blob that grew undeclared shows on the first build.
        left = (cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) < INK).astype(np.uint8)
        for bx in boxes:
            left[max(0, int(bx[1])):int(round(bx[3])),
                 max(0, int(bx[0])):int(round(bx[2]))] = 0
        n_spots, _lbl, stats, _ctr = cv2.connectedComponentsWithStats(left, 8)
        spot = max((stats[j] for j in range(1, n_spots)),
                   key=lambda r: r[cv2.CC_STAT_AREA], default=None)
        undecl = {"pixels": int(left.sum()), "largest_blob": None}
        spot_box = None
        if spot is not None:
            sx, sy = int(spot[cv2.CC_STAT_LEFT]), int(spot[cv2.CC_STAT_TOP])
            sw, sh = int(spot[cv2.CC_STAT_WIDTH]), int(spot[cv2.CC_STAT_HEIGHT])
            undecl["largest_blob"] = {
                "area": int(spot[cv2.CC_STAT_AREA]),
                "size_on_clean_raster": [sw, sh], "box": None}
            spot_box = (sx, sy, sx + sw, sy + sh)

        # The binding shadow comes BEFORE the rotation. The gutter halves the
        # SPREAD, not the raster: on a page rotated 90° it runs across the
        # sheet. The old edition drew it after the rotation, across the real
        # gutter, and the truth's "gutter" field named the wrong axis.
        gutter = None
        if name in B_SPREADS:
            img, gutter = _binding(img, page_seed)

        rot = B_ROTATE.get(name, 0)
        if rot == 90:
            src_h = img.shape[0]
            img = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
            boxes = [(*_rot90_box(b[:4], src_h), b[4]) for b in boxes]
            # The blob rides the same two transforms as the truth boxes: it
            # must lie in the coordinates of THE page it is recorded beside.
            # Untransformed, the box on `atl_rotated_plate` gave x=1421 on a
            # sheet 1012 wide, pointing off the sheet -- the trouble the gutter
            # cost, fixed the same way, by order of operations.
            if spot_box is not None:
                spot_box = _rot90_box(spot_box, src_h)
            if gutter is not None:
                gutter = None       # after rotation this is no longer an x

        img, M = _age(img, aging, page_seed)
        h, w = img.shape[:2]
        if M is not None:
            boxes = [(*_clip_box(_xform_box(b[:4], M), w, h), b[4])
                     for b in boxes]
            if spot_box is not None:
                spot_box = _clip_box(_xform_box(spot_box, M), w, h)
        if spot_box is not None:
            undecl["largest_blob"]["box"] = [round(v, 1) for v in spot_box]
        thin = [b for b in boxes if b[2] - b[0] < 2 or b[3] - b[1] < 2]
        if thin:
            raise SynthError(
                f"{name}: after ageing a truth box collapsed: "
                f"{[(round(v,1) for v in t[:4]) for t in thin[:2]]}")
        page = out.new_page(width=w * PT, height=h * PT)
        ok, enc = cv2.imencode(".png", img)
        page.insert_image(page.rect, stream=enc.tobytes())

        # CHARACTERS GO INTO A BLOCK BY THE LABEL'S ROLE, NOT BY THE LABEL.
        # `content` is filled only for roles text and service -- there the
        # characters ARE the first level's product. An ARTIFACT keeps `content`
        # null, and that is a VALUE, not an omission: it never travels to a VLM
        # as text at all -- the reader routes an artefact label nowhere
        # (`read/__init__.py`) -- its characters are the
        # SECOND level's answer, and their reference lies beside, in
        # `meta["artifact_truth"]`, by block number. The `Block` schema is
        # untouched: a sixth field there would break `Page.from_json`.
        from booksmith.core import policy
        blocks, art_truth = [], {}
        no_chars = []
        for j, b in enumerate(boxes):
            rec = said.get(j, {})
            role = policy.role(b[4])
            blk = {"block_id": j, "box": [round(v, 1) for v in b[:4]],
                   "label": b[4], "score": None, "order": j,
                   "content": None, "kind": "none"}
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
        chars = {"chars": char_count, "words": word_count, "blocks_with_text": with_text,
                 "text_blocks_without_chars": len(no_chars),
                 "which_without_chars": no_chars[:6],
                 "tables_with_grid": sum(1 for v in art_truth.values()
                                        if "cells" in v),
                 "cell_count": sum(v["rows"] * v["cols"]
                              for v in art_truth.values() if "cells" in v)}
        with open(os.path.join(work, f"{i:04d}.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"index": i, "width": w, "height": h, "dpi": DPI,
                       "blocks": blocks, "raw": None,
                       "meta": {"case": name, "book": book,
                                "aging": aging,
                                "synth_seed": page_seed, "rotation": rot,
                                "gutter": gutter,
                                # Pixels and blob size on the CLEAN raster,
                                # before aging and rotation: aging sprinkles
                                # specks, and the number would measure noise,
                                # not a forgotten box. The blob box is in THIS
                                # page's coordinates, to be found by eye.
                                "ink_outside_truth": undecl,
                                # A FLAG, NOT A GUESS. `subset.py` and
                                # `books score` read `text_marked` as three
                                # answers -- yes, no, not said -- and the last
                                # is not no. The synthetics used to say
                                # NOTHING. Set BY FACT: yes only when every
                                # block of role text and service has
                                # characters; one silent hole and it says no.
                                "text_marked": not no_chars,
                                # THE READING ORDER IS KNOWN BY CONSTRUCTION:
                                # the drawers append blocks in the order a
                                # reader takes them, and `order` above is
                                # that index. The flag was missing, and the
                                # one bench where order is exact could not
                                # score it: thirteen pages of slovar printed
                                # NOT SAID (the audit of 2026-09-06). A case
                                # that draws out of reading order is a truth
                                # defect for the eyes and `books look`.
                                # THE CONVENTION FOR WHAT IS NOT PROSE: the
                                # order metric scores every matched block,
                                # furniture and artefacts included, and the
                                # generator places them by the book's habit,
                                # not by a reader's -- the folio last on the
                                # handbook, the atlas and the magazine, the
                                # running head and folio FIRST on the
                                # dictionary and the catalogue; marginalia
                                # after the body they stand beside; footnotes
                                # per column. A model's disagreement on those
                                # pairs is disagreement with a convention.
                                "order_marked": True,
                                "char_truth": chars,
                                "text_layer_check": check,
                                # ARTIFACT truth: beside, by block number. For
                                # a table, rows, columns and every cell's text
                                # -- without them the second level (table ->
                                # HTML) cannot be checked at all, and "boxed
                                # correctly" says nothing about a table.
                                "artifact_truth": art_truth}},
                      f, ensure_ascii=False)
        pages.append({"case": name, "page": i, "size": [w, h],
                      "block_count": len(blocks), "rotation": rot,
                      "spread": name in B_SPREADS,
                      "ink_outside_truth": undecl,
                      "char_truth": chars,
                      "text_layer_check": check})
        big = undecl["largest_blob"]
        log(f"  {i:2d} {name:22s} {w}x{h}, blocks {len(blocks)}"
            + ("  (spread)" if name in B_SPREADS else "")
            + (f"  (rotated {rot} deg)" if rot else "")
            + f", outside truth {undecl['pixels']} px"
            + (f" (blob {big['size_on_clean_raster'][0]}"
               f"x{big['size_on_clean_raster'][1]}"
               f" = {big['area']} px)" if big else "")
            + f"; chars {chars['chars']}, words {chars['words']} "
              f"in {chars['blocks_with_text']} blocks"
            + (f", NO CHARS {chars['text_blocks_without_chars']} "
               f"({', '.join(chars['which_without_chars'])})"
               if no_chars else "")
            + (f", cells {chars['cell_count']} in "
               f"{chars['tables_with_grid']} tables"
               if chars["tables_with_grid"] else "")
            + f"; words outside truth {check['outside_truth']}"
            + (f" {check['outside_truth_samples']}" if check["outside_truth"] else "")
            + (f", NOT IN LAYER {check['missing_from_layer']}"
               if check["missing_from_layer"] else "")
            + (f", UNEXPLAINED {check['unexplained']}"
               if check["unexplained"] else "")
            + (f" {check['mismatch_examples']}"
               if check["mismatch_examples"] else "")
            + f", ghosts {check['ghosts']}"
            + (f", leaders {check['dot_leaders']}" if check["dot_leaders"] else ""))

    # Named after the BOOK, not `synth.pdf` everywhere: six books under one
    # file name confuse at the first glance at a directory.
    pdf = os.path.join(out_dir, f"{book}.pdf")
    # `no_new_id=True` -- NOT DECORATION. Without it MuPDF writes random bytes
    # into `/ID` on every save, and one command with one seed gave DIFFERENT
    # files: two consecutive `books synth --book slovar` runs, the same size to
    # the byte, 51 bytes of difference, all 51 in `/ID`. The truth reproduced
    # exactly, file by file.
    #
    # What those 51 bytes cost. `bench/README.md` promises the benches rebuild
    # byte-identical from one command, and on that rests their not being
    # versioned (472 MB for annopage). `books html` compares the book's sha256
    # with the detection snapshot and refuses to build on a mismatch -- so
    # rebuilding a bench silently invalidated EVERY earlier run over it,
    # discoverable only by a refused build. With this flag two runs give
    # byte-equal files; `reproducible=True` does NOT.
    out.save(wpdf, garbage=3, deflate=True, no_new_id=True)
    out.close()

    # THE TRUTH SNAPSHOT. Without it editing any drawer changes the truth
    # silently, and yesterday's number becomes incomparable with today's.
    # `books score` uses it to check that truth and model output are about one
    # PDF; here it also records HOW that truth was built.
    def total_of(key, margin):
        return sum(pp[key][margin] for pp in pages)
    total = {"chars": total_of("char_truth", "chars"),
            "words": total_of("char_truth", "words"),
            "blocks_with_text": total_of("char_truth", "blocks_with_text"),
            "text_blocks_without_chars":
                total_of("char_truth", "text_blocks_without_chars"),
            "tables_with_grid": total_of("char_truth", "tables_with_grid"),
            "cell_count": total_of("char_truth", "cell_count"),
            "words_outside_truth": total_of("text_layer_check", "outside_truth"),
            "missing_from_layer": total_of("text_layer_check", "missing_from_layer"),
            "unexplained": total_of("text_layer_check", "unexplained"),
            "ghosts": total_of("text_layer_check", "ghosts"),
            "dot_leaders": total_of("text_layer_check", "dot_leaders"),
            "words_in_text_layer_total": total_of("text_layer_check",
                                           "words_in_layer")}

    # The generator hashes ITSELF by its own `__file__`, not by a path built
    # beside it: the package move rewrote the sibling name once and the hash
    # would have pointed at a file that is not there.
    here = os.path.dirname(os.path.abspath(__file__))
    package = {f: stamp.sha256(os.path.join(here, f))
               for f in ("__init__.py", "draw.py", "age.py", "truth.py")}
    man = {"book": book, "about": getattr(mod, "ABOUT", ""),
           "page_count": len(pages), "synth_seed": seed, "aging": aging,
           # THE GENERATOR IS A PACKAGE: four files decide a page, and the
           # book module a fifth. Each is hashed by its own `__file__`; a
           # path built beside the file once pointed at a file that had
           # moved.
           "generator": {"file": "datasets/make/synth/__init__.py",
                         "sha256": package["__init__.py"], "package": package,
                         "commit": stamp.commit(),
                         "cases": names, "book": book,
                         "sha256_book_module": stamp.sha256(mod.__file__),
                         "guessed_labels": sorted(GUESSED),
                         "INK": INK, "KEEP": KEEP, "GROW": GROW},
           "knobs": knobs.snapshot() if hasattr(knobs, "snapshot") else None,
           "aging_params": AGING[aging],
           "fonts": {os.path.basename(FONT): stamp.sha256(FONT),
                      os.path.basename(FONT_MONO): stamp.sha256(FONT_MONO)},
           "pdf": os.path.basename(pdf), "sha256 pdf": stamp.sha256(wpdf),
           "blocks_by_label": counts, "char_truth": total,
           "pages": pages}
    with open(wman, "w", encoding="utf-8") as f:
        json.dump(man, f, ensure_ascii=False, indent=1)

    # Nothing below here can refuse. Truth, pdf and manifest go together: they
    # refer to one another, and a bench holding two of the three from
    # different builds is worse than one that failed outright.
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
            log(f"WARNING: the previous truth is left at {keep} ({e}) -- the "
                f"bench itself is whole, but that is a second copy and must "
                f"be removed by hand")
    log(f"pages {len(pages)}, truth blocks {sum(counts.values())} "
        f"({', '.join(f'{k} {v}' for k, v in sorted(counts.items()))})")
    # A MAGNITUDE, NOT THE WORD "DONE". Each of these has caught trouble the
    # word "done" would have passed: blocks_with_text below the count of text
    # blocks is a silent hole in the truth; missing-from-layer above zero is a
    # truth richer than the paper; words outside the truth is a piece of the
    # page never declared (the catalogue numbers).
    log(f"character truth: {total['chars']} chars, {total['words']} words "
        f"in {total['blocks_with_text']} blocks"
        + (f"; text blocks with NO CHARS "
           f"{total['text_blocks_without_chars']}"
           if total["text_blocks_without_chars"] else "")
        + f"; tables with a grid {total['tables_with_grid']}, "
          f"cells {total['cell_count']}")
    log(f"words drawn outside every truth box: "
        f"{total['words_outside_truth']} of "
        f"{total['words_in_text_layer_total']} in the text layer")
    log(f"against the text layer: not in the layer "
        f"{total['missing_from_layer']}, "
        f"unexplained {total['unexplained']}, "
        f"ghosts of a re-fill {total['ghosts']}, "
        f"dot leaders {total['dot_leaders']}")
    log(f"{pdf} ({os.path.getsize(pdf)/1e6:.1f} MB), truth in {truth_dir}")
    return man
