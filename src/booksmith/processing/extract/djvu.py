"""DjVu on the way in: unfold to PDF and cut the spreads.

In: a .djvu scan. Out: a PDF the rest of the pipeline reads, spreads cut apart.
Book scans often lie as spreads, which makes the recognizer read two pages as
one. A sheet wider than tall is a spread, and the decision is per book: with
spreads in the majority every landscape sheet is cut and the rare portrait ones
left whole; in a book of single pages a landscape sheet is a full-width table
and cutting it is forbidden. The cut line is found by ink rather than taken at
the middle, and where content lies on it there is no cut at all.
"""
import os
import re
import shutil
import subprocess
from booksmith.core.errors import Refusal

MIN_SPREAD_RATIO = 1.15     # wider than tall by this much -- call it a spread
GUTTER_BAND = 0.20          # where to look for the cut: middle ± a tenth
PROBE_DPI = 72              # at 36 a scan blot (0.109) outranks a gutter-crossing table (0.043)
RULE_BAND = 0.012           # band around the cut, in fractions of spread width
RULE_INK = 96               # how dark a pixel must be to count as black
RULE_RUN = 0.25             # a rule crosses this share of the width: 0.376 once, 0.000 on 567
RULE_EDGE = 0.03            # skip the scan edge: false vetoes end by 1.67%, rules start at 5.5%


class NoDjvuTools(Refusal):
    pass


def _tool(name):
    p = shutil.which(name)
    if not p:
        raise NoDjvuTools(
            f"no {name} -- djvu cannot be unfolded without it. Install "
            f"djvulibre:\n"
            f"    sudo apt install djvulibre-bin\n"
            f"If sudo is out of reach, it unpacks without installing:\n"
            f"    apt-get download djvulibre-bin libdjvulibre21 libjpeg-turbo8\n"
            f"    dpkg -x <each>.deb ~/.local/djvu")
    return p


def pages(path):
    """How many pages in the djvu file (file pages, not book pages)."""
    out = subprocess.run([_tool("djvused"), "-e", "n", path],
                         capture_output=True, text=True, timeout=120)
    m = re.search(r"\d+", out.stdout)
    if not m:
        raise Refusal(
            f"could not read the page count: {path}\n{out.stderr}")
    return int(m.group(0))


def _gutter(page, rect):
    """Where to cut the spread, or `None` when cutting is forbidden: content
    lies where the gutter should be, and a cut table is restored by nothing.
    """
    import pymupdf
    pix = page.get_pixmap(dpi=PROBE_DPI, colorspace=pymupdf.csGRAY, clip=rect)
    if pix.width < 8:
        return rect.x0 + rect.width / 2
    data = pix.samples
    lo = int(pix.width * (0.5 - GUTTER_BAND / 2))
    hi = int(pix.width * (0.5 + GUTTER_BAND / 2))
    best, best_ink = None, None
    for x in range(lo, max(hi, lo + 1)):
        ink = 0
        for y in range(pix.height):
            ink += 255 - data[y * pix.stride + x]
        if best_ink is None or ink < best_ink:
            best, best_ink = x, ink
    if best is None:
        return rect.x0 + rect.width / 2
    if gutter_rule(pix, best) >= RULE_RUN:
        return None
    return rect.x0 + rect.width * (best + 0.5) / pix.width


def _run_len(pix, x, y):
    """Length of the continuous black run horizontally through (x, y)."""
    data, row = pix.samples, y * pix.stride
    if 255 - data[row + x] < RULE_INK:
        return 0
    a = x
    while a > 0 and 255 - data[row + a - 1] >= RULE_INK:
        a -= 1
    b = x
    while b < pix.width - 1 and 255 - data[row + b + 1] >= RULE_INK:
        b += 1
    return b - a + 1


def dark_runs(pix, x):
    """Dark rows through column `x`: a list of (row, run length). A row counts
    only if the black holds across the whole `RULE_BAND` around `x`, or a run
    on one side of the gutter alone -- no hindrance to the cut -- would count.
    """
    half = max(1, int(pix.width * RULE_BAND / 2))
    lo, hi = max(0, x - half), min(pix.width, x + half + 1)
    data, out = pix.samples, []
    for y in range(pix.height):
        row = y * pix.stride
        if all(255 - data[row + i] >= RULE_INK for i in range(lo, hi)):
            out.append((y, _run_len(pix, x, y)))
    return out


def dark_rows(pix, x):
    """Dark rows through column `x`, split into continuous and short. Both are
    returned: without the second, "there are no rules" cannot be told from
    "there was black and all of it short". Position is `gutter_rule`'s affair.
    """
    full_width, short = [], []
    need = pix.width * RULE_RUN
    for y, ln in dark_runs(pix, x):
        (full_width if ln >= need else short).append(y)
    return full_width, short


def body_band(pix):
    """Bounds of the sheet body: (first row, one past the last). The border
    rows hold the black edge of the scan; the band is a fraction of the probe
    height, not pixels, so it does not drift after `PROBE_DPI`.
    """
    edge = int(pix.height * RULE_EDGE)
    return edge, pix.height - edge


def gutter_rule(pix, x):
    """The longest black across the gutter in the body of the sheet, in
    fractions of width. Zero means none was found there, which is not the zero
    of "there was black, all of it on the edge" -- that shows in `dark_rows`.
    """
    lo, hi = body_band(pix)
    runs = [ln for y, ln in dark_runs(pix, x) if lo <= y < hi]
    return (max(runs) if runs else 0) / max(1, pix.width)


def _forced_gutter(page, rect):
    """Cut by ink with no veto -- for `--split yes`."""
    import pymupdf
    pix = page.get_pixmap(dpi=PROBE_DPI, colorspace=pymupdf.csGRAY, clip=rect)
    if pix.width < 8:
        return rect.x0 + rect.width / 2
    data = pix.samples
    lo = int(pix.width * (0.5 - GUTTER_BAND / 2))
    hi = int(pix.width * (0.5 + GUTTER_BAND / 2))
    best, best_ink = None, None
    for x in range(lo, max(hi, lo + 1)):
        ink = sum(255 - data[y * pix.stride + x] for y in range(pix.height))
        if best_ink is None or ink < best_ink:
            best, best_ink = x, ink
    if best is None:
        return rect.x0 + rect.width / 2
    return rect.x0 + rect.width * (best + 0.5) / pix.width


def to_pdf(src, dst=None, split="auto", log=print):
    """Unfold djvu into PDF, cutting the spreads; returns the PDF's path.
    `split` is `auto` (per book), `yes` (all landscape sheets) or `no`. A
    finished file is judged by the mark in its metadata, not mtime; unmarked is stale.
    """
    import pymupdf

    src = os.path.abspath(src)
    if dst is None:
        dst = os.path.splitext(src)[0] + ".pdf"
    mark = f"{src}|{split}"
    if (os.path.exists(dst)
            and os.path.getmtime(dst) >= os.path.getmtime(src)):
        ready = pymupdf.open(dst)
        was = (ready.metadata or {}).get("keywords") or ""
        n = ready.page_count
        ready.close()
        if was == mark:
            log(f"already unfolded: {os.path.basename(dst)} ({n} pp.)")
            return dst
        log(f"rebuilding {os.path.basename(dst)}: built "
            + (f"from another input ({was})" if was
               else "by an older version"))

    n_src = pages(src)
    log(f"{os.path.basename(src)}: pages in the file {n_src}")

    raw = dst + ".raw.pdf"
    subprocess.run([_tool("ddjvu"), "-format=pdf", "-quality=90", src, raw],
                   check=True, timeout=3600)
    doc = pymupdf.open(raw)

    wide = sum(1 for p in doc if p.rect.width > p.rect.height * MIN_SPREAD_RATIO)
    if split == "auto":
        cut = wide * 2 > doc.page_count
        log(f"landscape pages {wide} of {doc.page_count} -- "
            + ("these are spreads, cutting" if cut
               else "no spreads, not cutting"))
    else:
        cut = split == "yes"

    out = pymupdf.open()
    made = 0
    spared, forced = [], []
    for page in doc:
        r = page.rect
        halves = [r]
        if cut and r.width > r.height * MIN_SPREAD_RATIO:
            x = _gutter(page, r)
            if x is None and split == "yes":
                # `yes` is the operator's will and beats the veto, or the flag is decoration.
                x = _forced_gutter(page, r)
                forced.append(page.number + 1)
            if x is None:
                # Content on the cut line: handed over whole -- a cut table is restored by nothing.
                spared.append(page.number + 1)
            else:
                halves = [pymupdf.Rect(r.x0, r.y0, x, r.y1),
                          pymupdf.Rect(x, r.y0, r.x1, r.y1)]
        for h in halves:
            np = out.new_page(width=h.width, height=h.height)
            np.show_pdf_page(np.rect, doc, page.number, clip=h)
            made += 1
    # Before save: metadata set after the write never reaches the disk.
    out.set_metadata({"keywords": mark})
    out.save(dst, garbage=3, deflate=True)
    out.close()
    doc.close()
    os.unlink(raw)
    if forced:
        log(f"cut against the veto (--split yes): {len(forced)}, "
            f"sheets {forced[:12]}" + (" ..." if len(forced) > 12 else ""))
    if spared:
        # A count, not "done": many refusals on solid prose mean a broken threshold.
        log(f"not cut (content on the cut line): {len(spared)} of {wide}, "
            f"sheets {spared[:12]}"
            + (" ..." if len(spared) > 12 else ""))
    log(f"unfolded: {os.path.basename(dst)}, pages {made} "
        f"({os.path.getsize(dst) / 1e6:.0f} MB)")
    return dst
