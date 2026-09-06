"""DjVu on the way in: unfold to PDF and cut the spreads.

The pipeline reads only PDF: the recognizer renders the pages itself, so the
source format is none of its business.  djvu is therefore unfolded before the
run -- locally, free and checkable by eye, not on a rented card where a mistake
costs money.

WHAT MUST NOT BE MISSED: **djvu book scans often lie as spreads.**  Two of the
three books added are such: 189 and 381 "pages" in the file against 378 and 760
in the book (the second has two portrait sheets: 379 x 2 + 2; it said "762" here,
a count of every sheet in the file rather than of the landscape ones).  Such a
file tells the recognizer to read two pages as one: the layout detector sees
two columns where there are none, the reading order scrambles, and the folios
of two pages land in one block.  Checking is cheap (look at a page), not
checking is dear -- the trouble looks like "the model reads badly".

A spread is recognized by width greater than height: crude, but a book page is
almost always taller than wide.  The decision is PER BOOK -- if spreads are the
majority, cut every landscape sheet and leave the rare portrait ones (cover,
inserts) whole.  The converse holds too: in a book of single pages a stray
landscape page is a full-width table, and cutting it is forbidden.

The cut line is found by ink, not taken at the middle: in scans the gutter
rarely falls exactly on the half.  We take the column with the least ink in the
middle fifth of the sheet, and fall back to the middle only when the probe is
too narrow to say anything.  And if CONTENT lies where the gutter should be --
a table across the whole spread -- we do not cut at all.  This used to promise a
"fall back to the middle, no worse than before", false twice over: there was no
fallback code, and with a full-width table the middle is the worst place there
is.
"""
import os
import re
import shutil
import subprocess

MIN_SPREAD_RATIO = 1.15     # wider than tall by this much -- call it a spread
GUTTER_BAND = 0.20          # where to look for the cut: middle ± a tenth
PROBE_DPI = 72              # ink counted on a reduced page.  IT WAS 36, where
                            # the signal is INSEPARABLE AT ANY THRESHOLD: over
                            # 379 spreads of the "Справочник" the blackest place
                            # in the book is 0.109, a scan blot (spread 17),
                            # while three real tables across the gutter give
                            # 0.000, 0.043 and 0.038 -- the false one stronger
                            # than the true.  At 72 the gap is complete: 0.376
                            # at the table (spread 193), EXACTLY 0.000 at the
                            # other 378.  Cost 15%: the book probe 32 s -> 37 s.
                            # Rebuilt, the "Справочник" went 760 -> 759 pages
                            # (one spread saved), "Огнеупоры" 378 -> 378 (there
                            # the veto fires at no dpi).  tests/test_djvu.py
                            # counts the step FROM THIS KNOB, not from 36, or it
                            # could not be moved
RULE_BAND = 0.012           # band around the cut, in fractions of spread width
RULE_INK = 96               # how dark a pixel must be to count as black
RULE_RUN = 0.25             # black across this fraction of the width is a rule.
                            # The threshold stands IN A CHASM, not with "2.3x
                            # headroom": that old note was measured at
                            # PROBE_DPI = 36 and OVER A MISSED POSITIVE -- 0.109
                            # is a scan blot, and the tables across the gutter
                            # never entered it at all, because they gave zero.
                            # At 72 the quantity over 568 spreads of two books
                            # takes TWO values: 0.376 at the one visible table
                            # across the gutter, 0.000 at the other 567
RULE_EDGE = 0.03            # border band of the probe: the black edge of the
                            # scan, not content.  Over 568 spreads false vetoes
                            # end at an inset of 10 rows out of 599 (1.67% of
                            # height) and the nearest real rule stands on row 33
                            # (5.5%), NOT ONE in between; the threshold is the
                            # middle of that gap (in the log), 1.8x both ways


class NoDjvuTools(SystemExit):
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
        raise SystemExit(
            f"could not read the page count: {path}\n{out.stderr}")
    return int(m.group(0))


def _gutter(page, rect):
    """Where to cut the spread -- and whether to cut at all.

    Returns `None` when cutting is forbidden: content lies where the gutter was
    supposed to be, and the cut would destroy it.

    WHAT WAS NOT HERE AND WHAT IT COST.  The module docstring promised a
    fallback to the middle "if the ink is even everywhere"; the code held NOT
    ONE comparison against a threshold, so `argmin` cut a table across the whole
    spread along its sparsest column.  Measured over block frames: **439 pages
    of the 1138 cut (38.6%) have a block flush against the cut** (closer than 1%
    of width) against **0 of 3740** edges on three uncut books; a table flush
    against it, 165 pages.  Three djvu books are 1693 pages of 3268, half the
    library.

    TWO SIGNALS, AND THEY DIFFER.  Little ink is not "the gutter is here" -- a
    table has white gaps between its columns too, and an ink threshold catches
    31% of the control pages.  What works is a CONTINUOUS HORIZONTAL RULE: the
    share of rows where solid black crosses the chosen column (± a band), nearly
    nil at real gutters (median 0.17%, 99th percentile 0.67%) against a median
    of 0.83% on pages taken by a full-width table.  The cost is ASYMMETRIC and
    the threshold follows it: a spurious refusal hands over a two-column spread,
    pages whole; a cut through a table destroys the numbers for good.

    FIRST CORRECTION.  The first edition declared "a 0.5% threshold catches 84%
    of the controls while refusing 1-2% of real gutters"; nothing checks that
    number today, the script that computed it never entered the tree.  On
    "Огнеупоры" the veto fired on **11 spreads of 189 (5.8%), all eleven
    false** -- dark rows at probe positions 0..2, the black edge of the scan.
    Precision 0 of 11.  Not the threshold's fault: the black was the BINDING
    SHADOW in the top rows of the gutter, and "continuous" the code never
    checked at all (see `dark_rows`).  The gauge now lives in
    `tools/spread_probe.py`, so the next claim has a way to fail.

    SECOND CORRECTION.  "Continuous" was not enough.  On the "Справочник по
    чугунному литью" the veto fired **44 times of 379 spreads (11.6%)** -- 716
    pages instead of 760 -- and all forty-four false: that scan's BLACK EDGE OF
    THE SHEET runs 214..782 px at a width of 773..790, 27..100% of the spread,
    straight through the `RULE_RUN` = 25% threshold.  All 391 continuous rows of
    the book lie within 8 rows of the edge of the probe (204 on row 0); in the
    BODY of the sheet, NOT ONE.

    THIRD CORRECTION, DEARER THAN BOTH.  It said here that no table in these
    books runs across the gutter.  FALSE: the "Справочник" has at least three,
    two of them seen by eye --

        spread 49   "Таблица I.38 … алюми|ниевых чугунов …", pp. 98-99, the
                    heading torn mid-word;
        spread 193  "Таблица V.13 … покрытий, | поставляемых …", pp. 386-387,
                    the row `ГП-2 ... 5,5` on the left continuing on the right
                    as `35  1,30-1,35  20  95  1,0  80`;
        spread 195  "Таблица V.15 … самотвердеющих | противопригарных …".

    -- and the claim came FROM THE SILENCE OF THE INSTRUMENT, silent for a
    reason of its own: at PROBE_DPI = 36 these gave 0.000, 0.043 and 0.038,
    below the scan blot.  A zero from not understanding written down as a zero
    from a check.  Hence the knob at 72.

    TWO OF THE THREE ARE CAUGHT AT NO THRESHOLD, and that must not be kept
    quiet.  At 72 dpi spread 193 gives 0.376 and stays whole; 49 and 195 give
    0.000 and are cut, because there EACH HALF CARRIES ITS OWN CLOSED FRAME --
    rules stop against it and only the torn TEXT of the heading crosses.  The
    signal is blind to them by construction and the other one is not written, so
    the count reads "1 of 3 known caught", not "0 false".

    POSITION SEPARATES THEM NOW, not length.  The scan edge lies at the edge of
    the sheet, a table rule in the body, and the gap between them is measured:
    false vetoes end at an inset of 1.67% of height (10 rows of 599), the
    nearest real rule stands at 5.5% (row 33), and over 379 spreads there is no
    black in between.  On the other two books the nearest rule is further still:
    8.1% ("Кристаллизация", 555 scans) and 7.7% ("Биохимия").  `RULE_EDGE` = 3%
    is the middle of that gap, and the gauge self-check reddens at a shift in
    BOTH directions.

    AND THE QUANTITY IS ANOTHER.  It was the share of continuous rows in the
    probe height against `RULE_MAX` = 0.005 -- on a 599-row probe "three rows and
    not one fewer", so coarse that one row decided: of 379 spreads **63 stood at
    exactly two continuous rows, 39 at exactly three**, 102 (27%) hanging on
    one.  The SCAN HEIGHT decided too -- 3/599 = 0.005008 vetoes,
    3/601 = 0.004992 does not, and eight of those thirty-nine survived only
    because the scan came out two rows taller -- while a real rule at 36 dpi
    occupies ONE row (703 blocks of 882 in the "Справочник", median 1), so
    "three rows" would never have fired on one.  Now the longest black across
    the gutter in the body of the sheet is measured, in fractions of width:
    continuous, independent of probe height, indifferent to rule thickness.
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
    """Dark rows through column `x`: a list of (row, run length).

    A row counts only if the black holds across the whole `RULE_BAND` around
    `x`.  Without that condition a run lying entirely on one side of the gutter
    would count -- a table rule on ONE page of the spread, which does not hinder
    the cut at all: 659 such blocks in the "Справочник" against zero crossing
    the gutter.
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
    """Dark rows through column `x`, split into continuous and short.

    Returns (continuous, short).  Both, not just the total: without the second,
    "there are no rules" cannot be told from "there was black and all of it
    short", and those are different answers.

    WHAT SEPARATES THEM AND WHY THIS.  The veto docstring promised a "continuous
    horizontal rule" while the code checked a band about five pixels wide -- it
    never checked "continuous" at all.  So the BINDING SHADOW got into the veto:
    in spread scans the top rows of the gutter are the blackest of all and the
    blot there is solid across the whole narrow band, evidence OF a gutter and
    the exact opposite of what the veto looks for.  Measured on "Огнеупоры", all
    11 false vetoes: a black run of 8..29 px at a probe width of 344..356,
    **3.5-8.1% of the spread width**, while a rule crossing the gutter runs
    through both pages and takes tens of percent.  `RULE_RUN` = 25% stands three
    times above that noise.

    LENGTH ALONE WAS NOT ENOUGH, and the class this does NOT count is WHERE the
    row lies: in the "Справочник" the black edge of the sheet runs 27..100% of
    the width and passes the threshold clean through -- 391 continuous rows over
    379 spreads, all at the edge.  `gutter_rule` cuts those off, not this
    function: the gauge needs both quantities raw, or it stops showing what
    happened on the sheet.
    """
    full_width, short = [], []
    need = pix.width * RULE_RUN
    for y, ln in dark_runs(pix, x):
        (full_width if ln >= need else short).append(y)
    return full_width, short


def body_band(pix):
    """Bounds of the sheet BODY: (first row, one past the last).

    The border rows of the probe are cut away: the black edge of the scan lies
    there.  The band is measured off the probe height rather than in pixels --
    otherwise it would drift after `PROBE_DPI`, while the edge is tied to the
    sheet, not to the resolution.
    """
    edge = int(pix.height * RULE_EDGE)
    return edge, pix.height - edge


def gutter_rule(pix, x):
    """The longest black across the gutter IN THE BODY of the sheet, in
    fractions of width.

    Zero means "no black across the gutter was found in the body", and that is
    not the zero of "there was black, all of it on the edge": the second is
    visible through `dark_rows`, and the gauge prints both.

    The quantity is CONTINUOUS, and that is the point of it.  The old one, the
    share of continuous rows in the probe height, was quantized in steps of
    1/599 at a threshold of 0.005 -- see `_gutter` for what one row decided
    there.  Here `RULE_RUN` = 0.25 has not "2.3x" of headroom but a chasm: over
    568 spreads of two books the quantity is 0.376 at one spread and exactly
    0.000 at the other 567, with nothing in between.
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
    """Unfold djvu into PDF, cutting the spreads.

    `split`: `auto` decides per book, `yes` cuts every landscape sheet, `no`
    does not cut at all.  Returns the path to the finished PDF.

    A finished file is not redone: unfolding takes minutes, and both `books
    prepare` and a hand call it.  Modification time alone is not enough to call
    it finished, and that is tested: with an explicit `--out` a file built from
    ANOTHER book came back as ready, and `--split yes` over an already unfolded
    `--split no` did nothing at all -- the mode was not part of the check, so the
    flag was decoration.  The PDF now carries in its metadata what it was built
    from and how, and that is what is compared; a file with no mark counts as
    stale, a minute of rebuilding being cheaper than handing back the wrong
    book.
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
                # `yes` is the operator's will, and it beats the veto: the
                # docstring promises "cut every landscape sheet", while the veto
                # silently left the book uncut against an explicitly given mode.
                # The only way to override it, or the flag is decoration.
                x = _forced_gutter(page, r)
                forced.append(page.number + 1)
            if x is None:
                # Content lies where the gutter should be: the spread is
                # taken by a full-width table.  We hand it to the recognizer
                # whole -- it will read two columns worse than two pages, but it
                # will read them; a cut table is restored by nothing.
                spared.append(page.number + 1)
            else:
                halves = [pymupdf.Rect(r.x0, r.y0, x, r.y1),
                          pymupdf.Rect(x, r.y0, r.x1, r.y1)]
        for h in halves:
            np = out.new_page(width=h.width, height=h.height)
            np.show_pdf_page(np.rect, doc, page.number, clip=h)
            made += 1
    # BEFORE save, not after: metadata set after the write never reaches the
    # disk at all, and the freshness check quietly stops working.
    out.set_metadata({"keywords": mark})
    out.save(dst, garbage=3, deflate=True)
    out.close()
    doc.close()
    os.unlink(raw)
    if forced:
        log(f"cut against the veto (--split yes): {len(forced)}, "
            f"sheets {forced[:12]}" + (" ..." if len(forced) > 12 else ""))
    if spared:
        # A number, not "done": it shows whether the veto fired sensibly.
        # Many refusals on a book of solid prose signal a broken threshold.
        log(f"not cut (content on the cut line): {len(spared)} of {wide}, "
            f"sheets {spared[:12]}"
            + (" ..." if len(spared) > 12 else ""))
    log(f"unfolded: {os.path.basename(dst)}, pages {made} "
        f"({os.path.getsize(dst) / 1e6:.0f} MB)")
    return dst
