"""`books overlay` -- look with your eyes at what the number measured.

A bench that checks itself by numbers and that nobody has seen is not an
instrument. WE SHOW DIVERGENCES, NOT EVERYTHING: a matched pair is one thin grey
box with no caption, and only the divergence is shouted -- what the model missed
and what it found that is not there. There is no legend; the colours below speak
for themselves, and a caption stands only where there is something to say.
Dashes go in AS A STRING, `"[3 3] 0"`: pymupdf takes a tuple and draws solid.
"""
import json
import os

import pymupdf
from booksmith.core import stamp
from booksmith.core.errors import Refusal
from booksmith.core import book
from booksmith.core import page as page_mod
from booksmith.core import job
from booksmith.core.log import log
from booksmith.datasets.bench import trait_state
from booksmith.datasets.metrics.contour import page_pairs

# Caption font: a PREFERENCE, not a requirement -- used when it is there, the
# built-in `helv` when it is not, which renders all three captions this module
# draws. Requiring the file would refuse the overlay on a machine that spells
# its font directory differently.
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_FALLBACK = "helv"


def _caption_font() -> str:
    """The name the text calls ask for: our loaded face, or the built-in."""
    return "L" if os.path.exists(FONT) else FONT_FALLBACK

MATCHED = (0.55, 0.55, 0.55)      # grey and thin: nothing to look at here
NOT_FOUND = (0.85, 0.10, 0.10)     # red: in truth, absent from the model
SPURIOUS = (0.95, 0.55, 0.00)       # orange: in the model, absent from truth
ONE = (0.15, 0.35, 0.85)         # blue: one markup, nothing to compare with
# A divergent label is not a spurious box and has a colour of its own: in the
# orange of "EXTRA" over a grey box, its colour contradicted its own box and a
# real "EXTRA" beside it went invisible.
LABEL = (0.45, 0.25, 0.65)        # purple: same box, different name


class OverlayError(Refusal):
    pass




def _same_book(pdf: str, marks) -> str:
    """Is the markup about this PDF. Unchecked, a foreign truth lies down
    silently and looks like the model's trouble -- it is the directory's."""
    mine = stamp.sha256(pdf)
    said, unchecked = [], []
    for d, tag in marks:
        was = len(said)
        up = os.path.dirname(d.rstrip("/"))
        for name, path_in in (("manifest.json", ("source", "sha256")),
                              ("run.json", ("source", "sha256"))):
            path = os.path.join(up, name)
            if not os.path.exists(path):
                continue
            with open(path, encoding="utf-8") as f:
                j = json.load(f)
            for k in path_in:
                j = (j or {}).get(k) if isinstance(j, dict) else None
            if not j:
                continue
            if j != mine:
                raise OverlayError(
                    f"markup {tag} ({d}) is about ANOTHER book: its "
                    f"snapshot says sha256 {j[:12]}, {pdf} says {mine[:12]}. "
                    f"The boxes drawn would look like a defect of the model.")
            if tag not in said:
                # Once per markup, not per snapshot found: both files can lie
                # in one directory.
                said.append(tag)
        if len(said) == was:
            unchecked.append(tag)
    # What was not checked is named aloud: half a guard printed as the whole
    # guard is "we did not look" dressed as "it matched".
    ok = f"sha256 verified for {', '.join(said)}" if said else None
    no = (f"NOT VERIFIED for {', '.join(unchecked)}: no snapshot lies beside "
          f"it, nothing to say whether this markup is about that book"
          ) if unchecked else None
    return "; ".join(x for x in (ok, no) if x) or "sha256: nothing to verify"


def _pages(d: str) -> dict:
    if not os.path.isdir(d):
        raise OverlayError(f"no markup directory {d}")
    out = {}
    for name in sorted(os.listdir(d)):
        if not name.endswith(".json") or name == "run.json":
            continue
        with open(os.path.join(d, name), encoding="utf-8") as f:
            p = json.load(f)
        if "blocks" not in p or "index" not in p:
            raise OverlayError(f"{name}: does not look like a markup page")
        out[int(p["index"])] = p
    if not out:
        raise OverlayError(f"{d} holds not one markup page")
    return out


def _rect(page, box, k, color, width, dashes=None):
    page.draw_rect(pymupdf.Rect(box[0] * k, box[1] * k, box[2] * k, box[3] * k),
                   color=color, width=width, dashes=dashes)


def _label(page, box, k, color, text, above=True):
    x, y = box[0] * k + 1, box[1] * k - 2
    if not above:
        y = box[3] * k + 7
    page.insert_text((x, max(7.0, y)), text, fontname=_caption_font(),
                     fontsize=6.0,
                     color=color)


def build(pdf: str, out: str, marks: list[tuple[str, str]], only=None) -> dict:
    """Lay markup over the PDF pages, showing the divergences. `marks` is a list
    of (directory, tag); a single one is drawn whole. What truth does not mark
    up (`text_marked`) is a hairline counted apart, never spurious."""

    def die(msg: str):
        """Close the document and fail with our message. The message is built at
        the call site, BEFORE the close: pymupdf throws on a closed document, and
        that would fly out as a bare trace instead of the explanation."""
        doc.close()
        raise OverlayError(msg)

    note = _same_book(pdf, marks)
    sets = [(_pages(d), tag) for d, tag in marks]
    # Each markup's own policy: truth's is the union, a run's is its snapshot's.
    pols = [book.policy_beside(d) for d, _ in marks]
    doc = pymupdf.open(pdf)
    if only is not None:
        bad = [i for i in only if not 0 <= i < doc.page_count]
        if bad:
            die(f"{pdf} has no pages {bad}: {doc.page_count} in all")
    for pages, tag in sets:
        lost = sorted(i for i in pages if not 0 <= i < doc.page_count)
        if lost:
            die(f"markup {tag} has pages {lost[:5]} that are not in {pdf} "
                f"({doc.page_count} pages): they would vanish uncounted.")

    counts = {"matched": 0, "missed": 0, "spurious": 0, "outside_markup": 0,
              "pages_without_text_markup": 0, "pages_compared": 0,
              "pages_not_labelled": 0,
              # Misses are counted BY NAME: a page absent from one markup and
              # skipped in silence leaves a sheet that looks complete, and a
              # model that loses part of its answer looks improved.
              "missing_in_truth": [], "missing_in_model": [], "in_neither": 0,
              "pages": []}
    # Two quantities: `drawn` counts BOXES in every branch, and the "not one
    # landed" guard stands on it; `sheets` counts the SHEETS reached. Neither is
    # `doc.page_count`, which is a third.
    drawn = 0
    sheets = 0
    for i, page in enumerate(doc):
        if only is not None and i not in only:
            continue
        job.current().check()
        if (i + 1) % 20 == 0 or i + 1 == doc.page_count:
            log(f"  {i + 1}/{doc.page_count} sheets", n=i + 1, of=doc.page_count)
        if page.rotation:
            die(f"page {i} is rotated by a PDF attribute ({page.rotation}°): "
                f"the boxes would lie across it. Unrotate the PDF first.")
        # The file when it is there, the built-in otherwise. Both render
        # every caption this module draws; see the note beside FONT.
        if os.path.exists(FONT):
            page.insert_font(fontname="L", fontfile=FONT)
        else:
            page.insert_font(fontname=FONT_FALLBACK)
        p0 = sets[0][0].get(i)
        if p0 is None:
            # Missing from the FIRST markup: missing from the second too, it is
            # a sheet nobody marked up; present there, a hole in the first.
            if len(sets) > 1 and sets[1][0].get(i) is not None:
                counts["missing_in_truth"].append(i)
            else:
                counts["in_neither"] += 1
            continue
        k = page.rect.width / p0["width"]
        kh = page.rect.height / p0["height"]
        if abs(k - kh) > 1e-3:
            die(f"page {i}: markup raster {p0['width']}x{p0['height']} is "
                f"not the sheet's proportion -- boxes would lie stretched.")
        if len(sets) == 1:
            for b in p0["blocks"]:
                _rect(page, b["box"], k, ONE, 1.1)
                _label(page, b["box"], k, ONE, f"{b['label']}")
                drawn += 1
            sheets += 1
            continue
        p1 = sets[1][0].get(i)
        if p1 is None:
            counts["missing_in_model"].append(i)
            continue
        # Each markup has its own scale: one coefficient for both lays the
        # second's boxes shifted over a convincing-looking sheet.
        if (p1["width"], p1["height"]) != (p0["width"], p0["height"]):
            die(f"page {i}: truth raster {p0['width']}x{p0['height']}, "
                f"model raster {p1['width']}x{p1['height']} -- the boxes "
                f"would lie in different coordinate systems.")
        sheets += 1
        # The pairs are the metric's own, one list for sheet and number: what
        # `compare_pages` matched, missed and called extra on this page.
        res = page_pairs(p0, p1, pols[0], pols[1])
        if res is None:
            # Truth says the page is not labelled: nothing was compared, and
            # the model's boxes go down as one markup, not as agreement.
            counts["pages_not_labelled"] += 1
            for x in p1["blocks"]:
                _rect(page, x["box"], k, ONE, 1.1)
                _label(page, x["box"], k, ONE, f"{x['label']}  (truth not labelled here)")
                drawn += 1
            continue
        tb_by = {page_mod.anchor(i, b["block_id"]): b for b in p0["blocks"]}
        mb_by = {page_mod.anchor(i, b["block_id"]): b for b in p1["blocks"]}
        # The sign comes from TRUTH and is PER PAGE, three-state as the metric
        # reads it: a page that does not say is not a page that marks text.
        marked = trait_state(p0.get("meta") or {}, "text_marked") == "yes"
        counts["pages_compared"] += 1
        counts["pages_without_text_markup"] += 0 if marked else 1
        # We shout only at what the number also calls spurious: blaming the
        # model for a find beyond the scored boundary punishes it for a line WE
        # drew. An artefact extra's kind is the metric's; a text extra the
        # count never counts is loud only where truth marks text.
        pairs = [e for e in res["pairs"] if e["verdict"] == "matched"]
        lost = [e for e in res["pairs"] if e["verdict"] == "missed"]
        loud, quiet = [], []
        for e in res["extras"]:
            x = mb_by[e["run"]]
            if e["verdict"] == "not counted":
                (loud if marked else quiet).append(x)
            else:
                (loud if e["verdict"] == "spurious_box" else quiet).append(x)
        counts["matched"] += len(pairs)
        counts["missed"] += len(lost)
        counts["spurious"] += len(loud)
        counts["outside_markup"] += len(quiet)
        if lost or loud:
            counts["pages"].append(i)
        for e in pairs:
            b, x = tb_by[e["truth"]], mb_by[e["run"]]
            # A matched pair is ONE thin box with no caption; the label, where
            # it diverged, is the only thing worth saying here.
            _rect(page, x["box"], k, MATCHED, 0.7)
            if not e["label_ok"]:
                _label(page, x["box"], k, LABEL,
                       f"label: {b['label']} -> {x['label']}")
            drawn += 1
        for e in lost:
            b = tb_by[e["truth"]]
            _rect(page, b["box"], k, NOT_FOUND, 1.6)
            _label(page, b["box"], k, NOT_FOUND, f"NOT FOUND  {b['label']}")
            drawn += 1
        for x in quiet:
            # Not drawing these is not an option: the sheet would look clean
            # where in fact nothing was compared.
            _rect(page, x["box"], k, ONE, 0.5, dashes="[1 2] 0")
            drawn += 1
        for x in loud:
            _rect(page, x["box"], k, SPURIOUS, 1.6, dashes="[3 3] 0")
            s = f" {x['score']:.2f}" if x.get("score") is not None else ""
            _label(page, x["box"], k, SPURIOUS, f"EXTRA  {x['label']}{s}",
                   above=False)
            drawn += 1

    if not drawn:
        die(f"not one markup page landed on {pdf}: the PDF has "
            f"{doc.page_count} pages, and the markup indices are others")
    n = doc.page_count
    # The output carries only what was asked for: saving the whole document put
    # half a gigabyte beside a one-page request. THE NUMBERING SHIFTS BY THIS,
    # and is said aloud below -- the requested sheets run consecutively from the
    # first, and a silent renumbering in an instrument for the eye is a trap.
    picked = None
    if only is not None and len(only) < n:
        picked = sorted(only)
        doc.select(picked)
    doc.save(out, garbage=3, deflate=True)
    doc.close()
    log(note)
    log(f"{out}: sheets drawn {sheets} of {n} in the book, boxes {drawn}")
    if picked:
        log(f"  only the requested sheets went into the file, and ITS "
            f"NUMBERING IS ITS OWN: sheet 1 of the output is page "
            f"{picked[0] + 1} of the book"
            + (f", the last is {picked[-1] + 1}" if len(picked) > 1 else ""))
    if len(sets) == 1:
        # Nothing to compare with, and that is not "matched 0, NOT FOUND 0,
        # EXTRA 0", which reads as "everything agreed".
        log(f"  one markup, {sets[0][1]}: these {drawn} boxes have NOTHING "
            f"TO COMPARE WITH. This is not 'no divergences' -- a second "
            f"markup was never supplied")
    else:
        log(f"  matched {counts['matched']}, "
            f"NOT FOUND {counts['missed']}, EXTRA {counts['spurious']}; "
            f"divergences on {len(counts['pages'])} pages")
    # Misses as a quantity and by name, or an incomplete model output looks
    # like a clean sheet.
    for who, key in (("truth", "missing_in_truth"),
                     ("the model", "missing_in_model")):
        if counts[key]:
            p = counts[key]
            log(f"  {who} is MISSING {len(p)} pages that the other markup "
                f"has: {p[:8]}{' …' if len(p) > 8 else ''}. These sheets were "
                f"NOT compared, and their boxes did not enter the numbers "
                f"above -- sheet and number cannot be compared here")
    if counts["pages_not_labelled"]:
        log(f"  truth says {counts['pages_not_labelled']} pages are NOT "
            f"LABELLED: their model boxes are drawn as one markup and did "
            f"not enter the numbers above -- nothing was compared there")
    # A quantity rather than silence: without this line "EXTRA 508" reads as
    # "the whole sheet was checked".
    if counts["pages_without_text_markup"]:
        log(f"  truth does NOT mark text up on "
            f"{counts['pages_without_text_markup']} pages of "
            f"{counts['pages_compared']} (meta text_marked: false): "
            f"{counts['outside_markup']} model boxes of those classes are "
            f"drawn as a hairline and NOT counted as extra -- this is not "
            f"zero extra, it is 'there was nothing to compare with'")
    return counts


def look_at(pdf: str, detect_dir: str | None) -> str:
    """Where a sheet of boxes goes: `<book>/look/<label>.pdf` inside a book."""
    book = os.path.dirname(os.path.abspath(pdf))
    label = None
    if detect_dir:
        d = os.path.abspath(detect_dir).rstrip("/")
        if os.path.basename(d) == "pages":
            d = os.path.dirname(d)
        if os.path.basename(os.path.dirname(d)) == "detect":
            label = os.path.basename(d)
    if os.path.isfile(os.path.join(book, "manifest.json")):
        return os.path.join(book, "look", (label or "truth") + ".pdf")
    return os.path.splitext(pdf)[0] + ".overlay.pdf"
