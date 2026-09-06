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

from .run import knobs

W, H = 1012, 1466                 # a bench page at 144 dpi
DPI = 144.0
PT = 72.0 / DPI                   # pixel -> point
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"
FONT_MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"

ABOUT = ("English technical handbook of the fifties: dense two-column "
         "setting, tables without rules, drawings, spreads and rotations")

# DRAWN ONTO THE PAGE, therefore book content, therefore a name ending in
# `_RU` -- see `booksmith.cyr`. These were inline literals and an inline
# literal is counted as untranslated prose: the ratchet asked for them in
# English, and English here would have changed the raster of the two Cyrillic
# pages of the handbook and moved every ink figure measured on them.
BOX_TITLE_RU = "ВРЕЗКА"
FIG_CAPTION_RU = "Рис. 3.  Схема испытания"
HEADS_RU = ("Марка", "σ, МПа", "δ, %", "НВ",
            "Примечание")

PROSE_EN = (
    "The lead screw must be lowered to obtain a correct alignment with the "
    "half nuts. In addition, the lead screw must be aligned to the bed ways. "
    "To test this alignment the lead screw is inserted in the bearings and "
    "the carriage is placed at the mid-point on the bed ways, closing the "
    "half nuts on the lead screw. A simple indicating jig is then made up. ")
PROSE_RU = (
    "Испытание образцов проводилось при температуре восемьсот пятьдесят "
    "градусов в течение сорока минут с последующим охлаждением на воздухе. "
    "Полученные значения приведены в таблице, откуда видно, что предел "
    "прочности возрастает при увеличении содержания хрома. ")


class SynthError(RuntimeError):
    """The page came out other than intended. Raise, never ship a blank."""


# ------------------------------------------------------ truth of CHARACTERS
# `content` was `None` on all 4984 blocks of all six books until this existed.
#
# WHY A SEPARATE DICT, NOT A SIXTH TUPLE ELEMENT. `truth.append((...))` occurs
# 62 times in the bench (37 here, 25 in `books/*.py`), and five places take the
# 5-tuple apart and rebuild it -- BEHAVING DIFFERENTLY: three would silently
# drop a sixth element (`_measure`, rebuilding a 5-tuple through `out.append`;
# the rotation; the skew), two would fail on unpacking (the
# `for x0, y0, x1, y1, lab in boxes` loop and the points-to-pixels pass in
# `build`). In three places of five the character truth would vanish WITHOUT A
# WORD -- exactly how this file has already lied four times with
# healthy-looking numbers. The key is the BLOCK NUMBER, the `block_id` of
# `models/base.py`.
#
# The dict is filled while a page is drawn and taken right after. All four
# transforms preserve the order of `truth`, so a block's number is its place
# in the truth list.
_SAID: dict[int, dict] = {}


def _said_reset() -> None:
    _SAID.clear()


def _said_take() -> dict[int, dict]:
    out = dict(_SAID)
    _SAID.clear()
    return out


def _say(truth, text=None, *, cells=None, spans=None, add=False):
    """Record character truth for the LAST truth block added.

    Called immediately after `truth.append((...))`, so the block number is
    `len(truth) - 1` and the link depends on nothing else. Breaking that
    adjacency is the only way to lie here, so a second write to the same number
    without `add=True` raises: truth overwritten is indistinguishable from
    truth absent.
    """
    if not truth:
        raise SynthError("`_say` called before a truth box was added")
    i = len(truth) - 1
    rec = _SAID.get(i)
    if rec is not None and not add:
        raise SynthError(
            f"character truth of block {i} ({truth[i][4]}) is being written "
            f"a second time: was {rec!r}, now {text!r}. Either `_say` is one "
            f"block behind `append`, or add=True is wanted")
    if rec is None:
        rec = {}
        _SAID[i] = rec
    if text is not None:
        t = " ".join(str(text).split())
        rec["text"] = (rec["text"] + " " + t).strip() if add and "text" in rec else t
    if cells is not None:
        rec["rows"] = len(cells)
        rec["cols"] = max((len(r) for r in cells), default=0)
        rec["cells"] = [[" ".join(str(c).split()) for c in row] for row in cells]
    if spans is not None:
        rec["spans"] = spans
    return rec


def _fill(pg, rect, text, size, font="F"):
    """Pack the box with prose TO CAPACITY and return WHAT WAS DRAWN.

    Checking the return code is not pedantry: without it the box stays empty
    silently and the bench measures blank paper, believing it measures prose.

    The BODY is returned, not the leftover height: nobody read the leftover
    (checked on all ten calls), and only the body says what landed in the box.

    THE TEXT LAYER SEES MORE THAN ONE PASS: at `rc > size*1.4` the body grows
    and `insert_textbox` runs again over what is already drawn. Measured on one
    210x80 pt box: two passes, 108 words in the body, 175 in the PDF text
    layer. Only the last line of each intermediate pass differs, its
    justification changing once a line appears below -- a smear on the raster,
    ghosts in the layer. Hence `_text_check` counts ghosts SEPARATELY.
    """
    import pymupdf
    body = text
    for _ in range(40):
        rc = pg.insert_textbox(rect, body, fontname=font, fontsize=size,
                               lineheight=1.15, align=pymupdf.TEXT_ALIGN_JUSTIFY)
        if rc < 0:
            body = body[:int(len(body) * 0.9)]
            if len(body) < 20:
                raise SynthError(f"not even 20 characters fit the box {rect}")
            continue
        if rc > size * 1.4 and len(body) < len(text) * 12:
            body = body + text
            continue
        return body
    raise SynthError(f"filling the box {rect} did not converge")


def _rect(x0, y0, x1, y1):
    import pymupdf
    return pymupdf.Rect(x0, y0, x1, y1)


def _table(pg, truth, x, y, cols, rows, size=6.4, label="table",
           ruled=False, colw=62.0, step=9.0):
    """A table of the requested size. `ruled` -- with or without rules.

    Both are needed: in our books tables hold together by aligned whitespace,
    the hardest kind for a detector, but ruled ones occur too, and the
    difference must show as a number, not be assumed.
    """
    grid = [[c for c, _cx in cols]]
    for c, cx in cols:
        pg.insert_text((cx, y), c, fontname="F", fontsize=size)
    for r in range(rows):
        row = []
        for j, (_c, cx) in enumerate(cols):
            cell = f"0 to .00{(r + j) % 7 + 2}\""
            pg.insert_text((cx, y + 10 + r * step), cell,
                           fontname="F", fontsize=size)
            row.append(cell)
        grid.append(row)
    x1 = cols[-1][1] + colw
    y1 = y + 10 + (rows - 1) * step + 4
    if ruled:
        for yy in (y - 8, y + 3, y1):
            pg.draw_line(_rect(x - 6, yy, x1, yy).tl,
                         _rect(x - 6, yy, x1, yy).tr, color=(0, 0, 0), width=0.5)
        for _c, cx in cols[1:]:
            pg.draw_line(_rect(cx - 8, y - 8, cx - 8, y1).tl,
                         _rect(cx - 8, y - 8, cx - 8, y1).bl,
                         color=(0, 0, 0), width=0.4)
    truth.append((x - 6, y - 8, x1, y1, label))
    # Header as the FIRST grid row: it becomes `th` in HTML, and without it a
    # lost header -- the commonest table damage -- cannot be caught at all.
    _say(truth, cells=grid)
    return y1 + 6


def _grid(x, n, colw=62.0, gap=8.0):
    """Headings of n columns, starting at x."""
    return [(f"Col {i + 1}", x + i * (colw + gap)) for i in range(n)]


def _chart(pg, truth, x, y, w, h, caption="Fig. 9  Hardness vs carbon"):
    """Chart: axes and a curve. The model has a separate `chart` class."""
    import math
    pg.draw_line(_rect(x, y + h, x, y).bl, _rect(x, y + h, x, y).tl,
                 color=(0, 0, 0), width=0.7)
    pg.draw_line(_rect(x, y + h, x + w, y + h).bl,
                 _rect(x, y + h, x + w, y + h).br, color=(0, 0, 0), width=0.7)
    import pymupdf
    pts = [pymupdf.Point(x + w * i / 24.0,
                         y + h - h * (0.2 + 0.7 * math.sin(i / 7.0) ** 2))
           for i in range(25)]
    for a, b in zip(pts, pts[1:]):
        pg.draw_line(a, b, color=(0, 0, 0), width=0.6)
    for i in range(6):
        pg.insert_text((x - 12, y + h - i * h / 5.0), str(i * 20),
                       fontname="F", fontsize=5.2)
    # Axis numbers are drawn INSIDE the chart box and get no box of their own:
    # they are the chart's content, not page text. `content` stays null.
    truth.append((x - 14, y - 4, x + w + 4, y + h + 6, "chart"))
    _caption(pg, truth, x + 10, y + h + 18, caption)
    return y + h + 24


def _figure(pg, truth, x, y, w, h, caption="Fig. 26.67  General arrangement"):
    """Line drawing: outline, circles, centre lines, dimension arrows.

    NOT parallel hatching across the whole rectangle. The first edition drew
    that, and a large drawing came out as a ruled form -- forty-seven even
    lines the full width. The detector honestly declined to call it `image`,
    and I filed the refusal as a model defect. A drawing must look like a
    drawing, or the bench measures something other than its name.
    """
    import math
    import pymupdf
    R = pymupdf.Rect(x, y, x + w, y + h)
    pg.draw_rect(R, color=(0, 0, 0), width=0.7)
    cx, cy = x + w * 0.38, y + h * 0.5
    r = min(w, h) * 0.22
    for k in (1.0, 0.62, 0.28):
        pg.draw_circle(pymupdf.Point(cx, cy), r * k, color=(0, 0, 0), width=0.6)
    # centre lines
    pg.draw_line(pymupdf.Point(cx - r * 1.35, cy), pymupdf.Point(cx + r * 1.35, cy),
                 color=(0, 0, 0), width=0.35, dashes="[2 2] 0")
    pg.draw_line(pymupdf.Point(cx, cy - r * 1.35), pymupdf.Point(cx, cy + r * 1.35),
                 color=(0, 0, 0), width=0.35, dashes="[2 2] 0")
    # body on the right: a stepped outline
    bx = x + w * 0.62
    pts = [(bx, cy + r), (bx, cy - r * 0.8), (bx + w * 0.12, cy - r * 0.8),
           (bx + w * 0.12, cy - r * 1.25), (bx + w * 0.3, cy - r * 1.25),
           (bx + w * 0.3, cy + r)]
    for a, b in zip(pts, pts[1:]):
        pg.draw_line(pymupdf.Point(*a), pymupdf.Point(*b), color=(0, 0, 0),
                     width=0.6)
    # section hatching -- in a SMALL patch, as on a real drawing
    for i in range(9):
        t0 = bx + i * (w * 0.3 / 9)
        pg.draw_line(pymupdf.Point(t0, cy + r), pymupdf.Point(t0 + r * 0.5, cy),
                     color=(0, 0, 0), width=0.3)
    # dimension line with arrows
    yd = y + h - 8
    pg.draw_line(pymupdf.Point(cx - r, yd), pymupdf.Point(cx + r, yd),
                 color=(0, 0, 0), width=0.4)
    for sx, d in ((cx - r, 1), (cx + r, -1)):
        pg.draw_line(pymupdf.Point(sx, yd), pymupdf.Point(sx + 4 * d, yd - 2),
                     color=(0, 0, 0), width=0.4)
        pg.draw_line(pymupdf.Point(sx, yd), pymupdf.Point(sx + 4 * d, yd + 2),
                     color=(0, 0, 0), width=0.4)
    pg.insert_text((cx - 8, yd - 3), "A-A", fontname="F", fontsize=5.0)
    # "A-A" is the drawing's own lettering, not page text: `content` null.
    truth.append((x, y, x + w, y + h, "image"))
    _caption(pg, truth, x + 10, y + h + 12, caption)
    return y + h + 16


def _text_w(text: str, size: float, font: str = "F") -> float:
    """Line width BY FONT METRICS, not by len(text)*coefficient.

    The old estimate `len(caption) * 3.1` fell short on all thirteen captions
    of the bench, and `_measure` can only shrink to the ink and grow by GROW
    pixels -- so an undersized box stayed undersized, an undeserved miss.
    """
    import pymupdf
    f = pymupdf.Font(fontfile=FONT_MONO if font == "M" else FONT)
    return f.text_length(text, fontsize=size)


def _caption(pg, truth, x, y, text, size=6.2, label="figure_title"):
    """Figure caption: drawn, and boxed BY MEASURE, not by eye."""
    pg.insert_text((x, y), text, fontname="F", fontsize=size)
    truth.append((x - 2, y - size - 1, x + _text_w(text, size) + 2, y + 2,
                  label))
    _say(truth, text)
    return y + size + 2


def _halftone(pg, truth, x, y, w, h, caption="Fig. 31  Milling head, photograph"):
    """A halftone PHOTOGRAPH in dots, not a line drawing.

    Different physics: a drawing is thin black lines on white, a photograph a
    grey mass of printer's dots. The model calls both `image` but confuses
    each with text differently, so both must be measured.
    """
    import numpy as np
    import pymupdf
    n = 4
    gh, gw = int(h * n), int(w * n)
    yy, xx = np.mgrid[0:gh, 0:gw] / float(max(gh, gw))
    g = 0.45 + 0.35 * np.sin(6.0 * xx) * np.cos(4.0 * yy)
    g += 0.25 * ((xx - 0.55) ** 2 + (yy - 0.45) ** 2 < 0.03)
    g += 0.06 * np.random.default_rng(3).normal(0, 1, g.shape)
    g = np.clip(g, 0.05, 0.95)
    # screen: threshold on a regular 4x4 grid -- the printer's dot itself
    m = (np.arange(16).reshape(4, 4) + 0.5) / 16.0
    thr = np.tile(m, (gh // 4 + 1, gw // 4 + 1))[:gh, :gw]
    dot = ((g > thr) * 255).astype(np.uint8)
    pix = pymupdf.Pixmap(pymupdf.csGRAY, gw, gh, dot.tobytes(), 0)
    pg.insert_image(_rect(x, y, x + w, y + h), pixmap=pix)
    pg.draw_rect(_rect(x, y, x + w, y + h), color=(0, 0, 0), width=0.5)
    truth.append((x, y, x + w, y + h, "image"))
    _caption(pg, truth, x + 8, y + h + 12, caption)
    return y + h + 16


def _stamp(pg, truth, x, y, r=34.0):
    """Oval stamp over the text: the model has a separate `seal` class."""
    import pymupdf
    R = _rect(x - r, y - r * 0.6, x + r, y + r * 0.6)
    pg.draw_oval(R, color=(0.25, 0.25, 0.25), width=1.1)
    pg.draw_oval(_rect(x - r * 0.8, y - r * 0.45, x + r * 0.8, y + r * 0.45),
                 color=(0.25, 0.25, 0.25), width=0.6)
    pg.insert_text((x - r * 0.6, y + 2), "BIBLIOTEKA", fontname="F",
                   fontsize=6.0, color=(0.25, 0.25, 0.25))
    pg.insert_text((x - r * 0.42, y + 11), "No. 4187", fontname="F",
                   fontsize=5.0, color=(0.25, 0.25, 0.25))
    truth.append((R.x0, R.y0, R.x1, R.y1, "seal"))
    # An artifact: its glyphs go to the artifact truth beside the block, not
    # to `content`. The second level must read them off the image, and without
    # a recorded reference there would be nothing to check that by.
    _say(truth, "BIBLIOTEKA No. 4187")
    return R.y1


def _leader_table(pg, truth, x, y, rows, w=230.0, size=6.4, label="table"):
    """Table on dot leaders: a column of names, dots, a column of numbers.

    Exactly what separates a contents list from a table -- ONE feature, and the
    model trips on it. Here it is a TABLE; in `contents_dots`, a contents list.
    """
    grid = []
    for i in range(rows):
        yy = y + i * 9.4
        name = f"Bearing bronze {i + 3}"
        pg.insert_text((x, yy), name + " " + "." * 28, fontname="F", fontsize=size)
        pg.insert_text((x + w - 26, yy), f"{12 + i * 3}.{i % 9}", fontname="F",
                       fontsize=size)
        # LEADER DOTS ARE NOT PART OF THE CELL -- a decision, not sloppiness:
        # a leader is a typographic rule set in dots, standing BETWEEN two
        # cells and belonging to neither. In the cell, it would oblige the
        # second level to emit twenty-eight dots to "match" -- a penalty for
        # the right answer.
        grid.append([name, f"{12 + i * 3}.{i % 9}"])
    truth.append((x - 4, y - 8, x + w, y + (rows - 1) * 9.4 + 4, label))
    _say(truth, cells=grid)
    return y + (rows - 1) * 9.4 + 10


def _span_header_table(pg, truth, x, y, groups, rows, colw=54.0, size=6.2):
    """Two-tier header with a spanning cell over a group of columns."""
    cols = []
    cx = x
    top, second, spans = [], [], []
    for name, n in groups:
        span = n * colw
        pg.insert_text((cx + span / 2 - len(name) * 1.6, y), name,
                       fontname="F", fontsize=size)
        pg.draw_line(_rect(cx, y + 3, cx + span - 8, y + 3).tl,
                     _rect(cx, y + 3, cx + span - 8, y + 3).tr,
                     color=(0, 0, 0), width=0.4)
        # A spanning cell takes TWO records: the name in the group's first
        # cell, blanks in the rest, plus "row 0, column c, width n". A grid
        # alone cannot express it, and without the second record a two-tier
        # header is indistinguishable from a plain one -- this case's chief
        # damage, "header flattened into one row", would go uncaught.
        spans.append({"row": 0, "col": len(cols), "cols": n})
        for j in range(n):
            cols.append(cx + j * colw)
            top.append(name if j == 0 else "")
            second.append(f"d{j + 1}")
            pg.insert_text((cx + j * colw, y + 13), f"d{j + 1}", fontname="F",
                           fontsize=size)
        cx += span
    grid = [top, second]
    for r in range(rows):
        row = []
        for j, ccx in enumerate(cols):
            cell = f"{(r * 3 + j) % 90 + 10}.{j}"
            pg.insert_text((ccx, y + 25 + r * 9.0), cell,
                           fontname="F", fontsize=size)
            row.append(cell)
        grid.append(row)
    y1 = y + 25 + (rows - 1) * 9.0 + 4
    truth.append((x - 5, y - 9, cols[-1] + colw - 8, y1, "table"))
    _say(truth, cells=grid, spans=spans)
    return y1 + 6


# -------------------------------------------------------- drawers for books
# Everything below is called from `booksmith/books/*.py`. Each drawer takes
# coordinates EXPLICITLY and never reads the sheet size from the module: the
# bench books differ in format, and a drawer taking the size from there would
# silently draw on the wrong sheet.

def _has_glyphs(text: str, font: str = "F") -> list[str]:
    """Which characters the font lacks. A missing glyph draws as a .notdef box
    -- INK -- which `_measure` will happily take for content: the page comes
    out with squares instead of a formula and the numbers look healthy."""
    import pymupdf
    f = pymupdf.Font(fontfile=FONT_MONO if font == "M" else FONT)
    return sorted({c for c in text if c.strip() and not f.has_glyph(ord(c))})


def _line(pg, x0, y0, x1, y1, width=0.9):
    """A rule. Floor thickness 0.5 pt: at 144 dpi a 0.3 pt line gives ZERO
    pixels darker than INK, so for the truth it does not exist at all."""
    import pymupdf
    if width < 0.5:
        raise SynthError(f"a rule {width} pt is under the floor of 0.5: "
                         f"neither `_measure` nor the model will see it")
    pg.draw_line(pymupdf.Point(x0, y0), pymupdf.Point(x1, y1),
                 color=(0, 0, 0), width=width)


def _put(pg, x, y, text, size=6.4, font="F", right=None, sheet_w=None):
    """A line, checked to fit on the sheet.

    THE SECOND TRAP OF THE SAME KIND as `insert_textbox`. Past the right edge
    `insert_text` clips the ink and returns 1, as on success: a line 1516 pt
    wide on a 506 pt sheet is "drawn" and 505 pt of it is visible, while the
    truth box claims the full width -- a permanent miss.
    """
    w = _text_w(text, size, font)
    if right is not None:
        x = right - w
    if sheet_w is not None and x + w > sheet_w + 0.5:
        raise SynthError(
            f"the line {text[:24]!r}, {w:.0f} pt wide, does not fit a "
            f"{sheet_w:.0f} pt sheet from x={x:.0f}: `insert_text` will clip "
            f"it silently")
    pg.insert_text((x, y), text, fontname=font, fontsize=size)
    return w


ENTRY_EN = ("{h}, n. The part of the mechanism that carries the load. "
            "Used in lathes and presses. See also {s}.")
ENTRY_RU = ("{h}, -а, м. Часть механизма, передающая усилие. Применяется "
            "в станках и прессах. См. также ст. {s}.")


def _entries(pg, truth, x, y, y_end, w, sheet_w, words, size=5.8,
             hang=8.0, bold_head=False, label="text", lead=1.25,
             tpl=ENTRY_EN, start=0):
    """A column of dictionary ENTRIES with hanging indent. Each entry is its
    own truth block: an entry is a paragraph."""
    step = size * lead
    n = start
    while y < y_end - step * 2:
        head = words[n % len(words)]
        body = tpl.format(h=head, s=words[(n + 3) % len(words)])
        lines, cur = [], ""
        for word in body.split():
            trial = (cur + " " + word).strip()
            if _text_w(trial, size) > w - (hang if lines else 0):
                lines.append(cur)
                cur = word
            else:
                cur = trial
        lines.append(cur)
        if y + step * len(lines) > y_end:
            break
        y0 = y
        drawn = []
        for k, ln in enumerate(lines):
            xx = x + (hang if k else 0)
            if k == 0 and bold_head:
                # A bold DejaVuSerif may be absent from the system; the entry
                # is letter-spaced instead -- visible, and needs no font.
                sp = " ".join(head)
                wl = _put(pg, xx, y, sp, size, sheet_w=sheet_w)
                rest = ln[len(head):].lstrip()
                _put(pg, xx + wl + 2, y, rest, size, sheet_w=sheet_w)
                # Truth is WHAT IS DRAWN, letter by letter: the spaced-out
                # "A b u t" is recorded as such. Recording the logical
                # "Abutment" would declare a divergence from the paper normal,
                # and the text-layer check would stop being a check.
                drawn.append(sp + " " + rest)
            else:
                _put(pg, xx, y, ln, size, sheet_w=sheet_w)
                drawn.append(ln)
            y += step
        truth.append((x - 1, y0 - size, x + w, y - step + 2, label))
        _say(truth, " ".join(drawn))
        y += step * 0.55
        n += 1
    return y


def _running_head(pg, truth, x0, x1, y, left, right, page_no, size=5.6,
                  rule=True):
    """Running head: a word left, a word right, a rule under them, a folio."""
    # TWO blocks, not one across the width. Checked: the model returns two
    # `header` boxes at 0.92, left word and right, and it is right -- half a
    # measure of blank paper lies between them. The glued truth read "header 0
    # of 12", blaming the model for our own error of granularity.
    wl = _put(pg, x0, y, left, size, sheet_w=x1 + 40)
    truth.append((x0 - 2, y - size - 1, x0 + wl + 2, y + 2, "header"))
    _say(truth, left)
    wr = _put(pg, 0, y, right, size, right=x1, sheet_w=x1 + 40)
    truth.append((x1 - wr - 2, y - size - 1, x1 + 2, y + 2, "header"))
    _say(truth, right)
    if rule:
        _line(pg, x0, y + 4, x1, y + 4, 0.6)
    w = _put(pg, (x0 + x1) / 2 - 6, y + 16, str(page_no), size,
             sheet_w=x1 + 40)
    truth.append(((x0 + x1) / 2 - 8, y + 16 - size - 1,
                  (x0 + x1) / 2 - 6 + w + 2, y + 18, "number"))
    _say(truth, str(page_no))


def _formula(pg, truth, x, y, text, size=8.5, number=None, right=None,
             sheet_w=None):
    """A display formula, optionally numbered at the right margin."""
    bad = _has_glyphs(text, "M")
    if bad:
        raise SynthError(
            f"the font lacks {bad}: they draw as empty boxes, and the bench "
            f"would measure squares instead of a formula")
    w = _put(pg, x, y, text, size, font="M", sheet_w=sheet_w)
    truth.append((x - 3, y - size - 1, x + w + 3, y + 3, "display_formula"))
    # An artifact by policy (cropped as an image): glyphs to the artifact
    # truth, not to `content`. One rule, no exceptions.
    _say(truth, text)
    if number is not None and right is not None:
        nw = _put(pg, 0, y, number, size - 2, right=right, sheet_w=sheet_w)
        truth.append((right - nw - 2, y - size + 1, right + 2, y + 2,
                      "formula_number"))
        _say(truth, number)
    return y + size * 1.9


def _matrix(pg, truth, x, y, rows, cols, size=6.6, kind="matrix",
            sheet_w=None):
    """A bracketed matrix or determinant: the chief label trap,
    `display_formula` against `table` -- by eye it is a grid of numbers."""
    step, colw = size * 1.55, size * 3.4
    drawn = []
    for r in range(rows):
        row = []
        for c in range(cols):
            _put(pg, x + 10 + c * colw, y + r * step,
                 f"a{r + 1}{c + 1}", size, font="M", sheet_w=sheet_w)
            row.append(f"a{r + 1}{c + 1}")
        drawn.append(" ".join(row))
    x1 = x + 10 + (cols - 1) * colw + _text_w("a11", size, "M") + 8
    y1 = y + (rows - 1) * step + 3
    if kind == "matrix":                      # round brackets from strokes
        for xx, d in ((x + 4, 1), (x1, -1)):
            _line(pg, xx, y - size, xx, y1, 0.7)
            _line(pg, xx, y - size, xx + 4 * d, y - size - 3, 0.6)
            _line(pg, xx, y1, xx + 4 * d, y1 + 3, 0.6)
    else:                                     # determinant -- straight bars
        _line(pg, x + 4, y - size, x + 4, y1, 0.7)
        _line(pg, x1, y - size, x1, y1, 0.7)
    truth.append((x, y - size - 4, x1 + 5, y1 + 4, "display_formula"))
    # Recorded as ROWS, not cells: the truth must say "one formula", not "a
    # rows x cols table". As a grid, the bench would hand the second level the
    # very answer whose wrongness it is meant to catch.
    _say(truth, " ; ".join(drawn))
    return y1 + size * 1.4


def _box_insert(pg, truth, x, y, w, h, prose, size=5.8, title=BOX_TITLE_RU):
    """A boxed insert: to the eye, a one-cell table."""
    import pymupdf
    pg.draw_rect(pymupdf.Rect(x, y, x + w, y + h), color=(0, 0, 0), width=0.8)
    _put(pg, x + 8, y + 12, title, size + 1, sheet_w=x + w)
    body = _fill(pg, _rect(x + 8, y + 18, x + w - 8, y + h - 6), prose, size)
    truth.append((x, y, x + w, y + h, "text"))
    _say(truth, title + " " + body)
    return y + h + 8


def _refs(pg, truth, x, y, y_end, w, sheet_w, size=5.6, start=1):
    """Reference list: a bracketed number and an indent."""
    step = size * 1.3
    n = start
    y0 = y
    drawn = []
    while y < y_end - step:
        ln = (f"[{n}] Ivanov A. B. Machine tool design, vol. {n}. "
              f"Moscow, {1950 + n}, p. {40 + n * 7}.")
        while _text_w(ln, size) > w:
            ln = ln[:-2]
        _put(pg, x, y, ln, size, sheet_w=sheet_w)
        drawn.append(ln)
        y += step
        n += 1
    truth.append((x - 2, y0 - size, x + w, y - step + 2, "reference_content"))
    _say(truth, " ".join(drawn))
    return y


def _frame_stamp(pg, truth, x0, y0, x1, y1, title="GENERAL ARRANGEMENT",
                 no="26.67"):
    """A drawing frame with a TITLE BLOCK in the lower right corner.

    The title block is a grid of celled text, a table to the eye and `table`
    in the truth, which is what it is. The drawing frame runs along the sheet
    edge and does NOT enter the truth: the detector must not box the whole
    sheet, and if it does, the spill counter says so.
    """
    import pymupdf
    pg.draw_rect(pymupdf.Rect(x0, y0, x1, y1), color=(0, 0, 0), width=1.4)
    sw, sh = 168.0, 46.0
    sx, sy = x1 - 6 - sw, y1 - 6 - sh
    pg.draw_rect(pymupdf.Rect(sx, sy, sx + sw, sy + sh), color=(0, 0, 0),
                 width=0.9)
    for k in (1, 2):
        _line(pg, sx, sy + k * sh / 3, sx + sw, sy + k * sh / 3, 0.6)
    _line(pg, sx + sw * 0.62, sy, sx + sw * 0.62, sy + sh, 0.6)
    _put(pg, sx + 4, sy + 11, title[:22], 5.6, sheet_w=x1)
    _put(pg, sx + 4, sy + 11 + sh / 3, "Scale 1:2", 5.2, sheet_w=x1)
    _put(pg, sx + 4, sy + 11 + 2 * sh / 3, "Sheet 1 of 3", 5.2, sheet_w=x1)
    _put(pg, sx + sw * 0.62 + 4, sy + 11, f"No. {no}", 5.6, sheet_w=x1)
    _put(pg, sx + sw * 0.62 + 4, sy + 11 + sh / 3, "Drawn A.B.", 5.2,
         sheet_w=x1)
    _put(pg, sx + sw * 0.62 + 4, sy + 11 + 2 * sh / 3, "1953", 5.2, sheet_w=x1)
    truth.append((sx, sy, sx + sw, sy + sh, "table"))
    # A 3x2 grid with no header: it has no row of headings, and recording the
    # first row as one would be a lie about the structure.
    _say(truth, cells=[[title[:22], f"No. {no}"],
                       ["Scale 1:2", "Drawn A.B."],
                       ["Sheet 1 of 3", "1953"]])
    return sx, sy


def _callouts(pg, truth, cx, cy, r, items, sheet_w):
    """Callouts: a line from the part to a number in a circle."""
    import math
    import pymupdf
    for k, (ang, n) in enumerate(items):
        a = math.radians(ang)
        x0, y0 = cx + r * math.cos(a), cy + r * math.sin(a)
        x1, y1 = cx + (r + 46) * math.cos(a), cy + (r + 46) * math.sin(a)
        pg.draw_line(pymupdf.Point(x0, y0), pymupdf.Point(x1, y1),
                     color=(0, 0, 0), width=0.5)
        pg.draw_circle(pymupdf.Point(x1, y1), 6.0, color=(0, 0, 0), width=0.6)
        _put(pg, x1 - 2.5, y1 + 2.5, str(n), 5.4, sheet_w=sheet_w)


def _plate(pg, truth, x, y, w, h, views=1):
    """Drawing field: one or two views, dashed lines, centre lines."""
    import math
    import pymupdf
    for v in range(views):
        vx = x + v * (w / views)
        vw = w / views - (10 if views > 1 else 0)
        cx, cy = vx + vw * 0.5, y + h * 0.5
        r = min(vw, h) * 0.3
        pg.draw_rect(pymupdf.Rect(vx, y, vx + vw, y + h), color=(0, 0, 0),
                     width=0.8)
        for k in (1.0, 0.7, 0.42, 0.18):
            pg.draw_circle(pymupdf.Point(cx, cy), r * k, color=(0, 0, 0),
                           width=0.6)
        pg.draw_line(pymupdf.Point(cx - r * 1.3, cy),
                     pymupdf.Point(cx + r * 1.3, cy),
                     color=(0, 0, 0), width=0.35, dashes="[3 3] 0")
        pg.draw_line(pymupdf.Point(cx, cy - r * 1.3),
                     pymupdf.Point(cx, cy + r * 1.3),
                     color=(0, 0, 0), width=0.35, dashes="[3 3] 0")
        for i in range(8):
            a = math.radians(i * 45)
            pg.draw_line(
                pymupdf.Point(cx + r * 0.42 * math.cos(a),
                              cy + r * 0.42 * math.sin(a)),
                pymupdf.Point(cx + r * 0.7 * math.cos(a),
                              cy + r * 0.7 * math.sin(a)),
                color=(0, 0, 0), width=0.5)
        truth.append((vx, y, vx + vw, y + h, "image"))
    return y + h


# --------------------------------------------------------------------- cases
# A handbook page is DENSE top to bottom -- its chief property, which the first
# edition did not reproduce: content filled the upper half, the rest was blank
# paper, and such a page looks like nothing to a detector.
#
# All coordinates here are in POINTS (1 point = 2 pixels at 144 dpi). Mixing
# units has already cost one spread: the half at `x0 + 46` with `x0` in pixels
# ran off the sheet and the right-hand page came out blank.
PW, PH = W * PT, H * PT          # sheet in points: 506 x 733
MARGIN, COLW, GUT = 34.0, 210.0, 18.0
TOP, BOT = 40.0, 700.0
COL_X = (MARGIN, MARGIN + COLW + GUT)


def _page(doc, wide=False, pw=None, ph=None):
    """A sheet. The size is an EXPLICIT parameter, not only a module constant.

    Bench books differ in format: the dictionary is narrow, the atlas
    landscape. With the size from the module alone, a drawer called for another
    book would silently draw on the handbook format -- the same unit trap that
    already cost one spread.
    """
    import pymupdf
    pw = PW if pw is None else pw
    ph = PH if ph is None else ph
    pg = doc.new_page(width=(2 * pw if wide else pw), height=ph)
    pg.insert_font(fontname="F", fontfile=FONT)
    pg.insert_font(fontname="M", fontfile=FONT_MONO)
    return pg


def _flow(pg, t, x, y, y_end, prose, w=COLW, size=6.6, gap=8.0):
    """Fill a column with paragraphs TO THE BOTTOM. Returns the y reached."""
    n = 0
    while y < y_end - 24:
        h = min(y_end - y, 34 + (n * 17) % 62)
        body = _fill(pg, _rect(x, y, x + w, y + h), prose, size)
        t.append((x, y, x + w, y + h, "text"))
        _say(t, body)
        y += h + gap
        n += 1
    return y


def c_two_columns(doc, rng):
    """A plain page: two dense columns, an unruled table, a figure."""
    pg = _page(doc); t = []
    y = _flow(pg, t, COL_X[0], TOP, 300, PROSE_EN)
    _table(pg, t, COL_X[0] + 6, y + 14, [("Tool Room", COL_X[0] + 6),
                                         ("12\" to 18\"", COL_X[0] + 76),
                                         ("20\" to 36\"", COL_X[0] + 146)], 5)
    _flow(pg, t, COL_X[0], y + 120, BOT, PROSE_EN)
    y2 = _flow(pg, t, COL_X[1], TOP, 260, PROSE_EN)
    _figure(pg, t, COL_X[1], y2 + 12, COLW, 100)
    _flow(pg, t, COL_X[1], y2 + 132, BOT, PROSE_EN)
    pg.insert_text((PW / 2 - 8, BOT + 18), "307", fontname="F", fontsize=6.4)
    t.append((PW / 2 - 10, BOT + 11, PW / 2 + 10, BOT + 20, "number"))
    _say(t, "307")
    return pg, t


def c_table_across_gutter(doc, rng):
    """A full-width table across the gutter (p. 313)."""
    pg = _page(doc); t = []
    for x in COL_X:
        _flow(pg, t, x, TOP, 230, PROSE_EN)
    _table(pg, t, MARGIN + 6, 250,
           [(f"Col {i}", MARGIN + 6 + i * 105) for i in range(4)], 7)
    for x in COL_X:
        _flow(pg, t, x, 380, BOT, PROSE_EN)
    return pg, t


def c_three_column_table(doc, rng):
    """Three SEPARATE tables side by side: the model takes one of three
    (p. 317).

    The gaps between the tables are deliberately three times the gaps between
    their columns, and each has its own caption. The first edition did neither:
    the gaps were equal and what was drawn was ONE six-column table. The
    detector returned one box and was right; I filed that as a defect.
    """
    pg = _page(doc); t = []
    _flow(pg, t, MARGIN, TOP, 190, PROSE_EN, w=2 * COLW + GUT)
    for i, x in enumerate((MARGIN + 6, MARGIN + 158, MARGIN + 310)):
        pg.insert_text((x, 214), f"TABLE {i + 1}", fontname="F", fontsize=6.0)
        t.append((x - 4, 206, x + 46, 217, "paragraph_title"))
        _say(t, f"TABLE {i + 1}")
        _table(pg, t, x, 236, [(f"Col {i+1}", x), ("inc.", x + 46)], 9,
               colw=46)
    _flow(pg, t, MARGIN, 380, BOT, PROSE_EN, w=2 * COLW + GUT)
    return pg, t


def c_formula_next_to_table(doc, rng):
    """A display formula beside a table: a LABEL error on a right box (p. 40)."""
    pg = _page(doc); t = []
    _flow(pg, t, MARGIN, TOP, 180, PROSE_EN, w=2 * COLW + GUT)
    lines = ("s = (a + b) / 2c", "R = 4 s^2 / (h - k)")
    for i, s in enumerate(lines):
        pg.insert_text((160, 210 + i * 16), s, fontname="M", fontsize=8.5)
    t.append((156, 198, 340, 230, "display_formula"))
    _say(t, " ; ".join(lines))
    _table(pg, t, MARGIN + 6, 260, [("d, mm", MARGIN + 6), ("R, MPa", MARGIN + 90),
                                    ("K", MARGIN + 174)], 6)
    _flow(pg, t, MARGIN, 380, BOT, PROSE_EN, w=2 * COLW + GUT)
    return pg, t


def c_contents_dots(doc, rng):
    """Contents on dot leaders (p. 4): looks like a table, is not one."""
    pg = _page(doc); t = []
    pg.insert_text((PW / 2 - 30, TOP + 14), "CONTENTS", fontname="F", fontsize=12)
    t.append((PW / 2 - 34, TOP + 2, PW / 2 + 34, TOP + 18, "doc_title"))
    _say(t, "CONTENTS")
    y = TOP + 40
    drawn = []
    while y < BOT:
        name = f"Sec. 26.{int(y)}  Lead Screw Alignment and Bed Ways"
        pg.insert_text((MARGIN + 6, y), name + " " + "." * 46,
                       fontname="F", fontsize=6.6)
        pg.insert_text((PW - MARGIN - 26, y), str(100 + int(y) % 400),
                       fontname="F", fontsize=6.6)
        # Leader dots: the same typographic rule as in `_leader_table`, kept
        # out of the character truth for the same reason.
        drawn.append(f"{name} {100 + int(y) % 400}")
        y += 10.5
    t.append((MARGIN + 2, TOP + 32, PW - MARGIN, y - 4, "content"))
    _say(t, " ".join(drawn))
    return pg, t


def c_no_artefacts(doc, rng):
    """Solid prose, no artifacts -- a check against false positives."""
    pg = _page(doc); t = []
    for x in COL_X:
        _flow(pg, t, x, TOP, BOT, PROSE_EN)
    return pg, t


def c_full_page_table(doc, rng):
    """A table filling the sheet: no text at all."""
    pg = _page(doc); t = []
    _table(pg, t, MARGIN + 6, TOP + 10,
           [(f"Col {i}", MARGIN + 6 + i * 88) for i in range(5)], 66)
    return pg, t


def c_two_figures_side(doc, rng):
    """Two figures side by side: horizontal merging."""
    pg = _page(doc); t = []
    _flow(pg, t, MARGIN, TOP, 200, PROSE_EN, w=2 * COLW + GUT)
    _figure(pg, t, COL_X[0], 230, COLW, 120, "Fig. 1  Cross feed screw")
    _figure(pg, t, COL_X[1], 230, COLW, 120, "Fig. 2  Compound rest screw")
    for x in COL_X:
        _flow(pg, t, x, 380, BOT, PROSE_EN)
    return pg, t


def c_russian(doc, rng):
    """Cyrillic: our books are in it, a Latin bench gives no such class."""
    pg = _page(doc); t = []
    y = _flow(pg, t, COL_X[0], TOP, 300, PROSE_RU)
    # Three of the five, and NOT the first three: the narrow table carries
    # grade, strength and hardness, skipping elongation.
    narrow = (HEADS_RU[0], HEADS_RU[1], HEADS_RU[3])
    _table(pg, t, COL_X[0] + 6, y + 14,
           list(zip(narrow, (COL_X[0] + 6, COL_X[0] + 76,
                             COL_X[0] + 146))), 6)
    _flow(pg, t, COL_X[0], y + 130, BOT, PROSE_RU)
    y2 = _flow(pg, t, COL_X[1], TOP, 280, PROSE_RU)
    _figure(pg, t, COL_X[1], y2 + 12, COLW, 100, FIG_CAPTION_RU)
    _flow(pg, t, COL_X[1], y2 + 132, BOT, PROSE_RU)
    return pg, t


def _half(pg, t, x0, rng, kind):
    """Half a spread. `x0` is an offset IN POINTS, not in pixels."""
    cx = (x0 + MARGIN, x0 + MARGIN + COLW + GUT)
    if kind == "table":
        y = _flow(pg, t, cx[0], TOP, 280, PROSE_EN)
        _table(pg, t, cx[0] + 6, y + 14, [("Tool Room", cx[0] + 6),
                                          ("12\" inc.", cx[0] + 76),
                                          ("20\" inc.", cx[0] + 146)], 6)
        _flow(pg, t, cx[0], y + 140, BOT, PROSE_EN)
        _flow(pg, t, cx[1], TOP, BOT, PROSE_EN)
    else:
        _flow(pg, t, cx[0], TOP, BOT, PROSE_EN)
        y2 = _flow(pg, t, cx[1], TOP, 260, PROSE_EN)
        _figure(pg, t, cx[1], y2 + 12, COLW, 100, "Fig. 4  Bed ways")
        _flow(pg, t, cx[1], y2 + 132, BOT, PROSE_EN)
    pg.insert_text((x0 + PW / 2 - 8, BOT + 18), "307", fontname="F", fontsize=6.4)
    t.append((x0 + PW / 2 - 10, BOT + 11, x0 + PW / 2 + 10, BOT + 20, "number"))
    _say(t, "307")


def c_spread(doc, rng):
    """A SPREAD: two book pages scanned as one sheet.

    Half our library lies this way -- 1693 pages of 3268. The sheet is wider
    than tall, with a shadowed gutter down the middle. It checks two things:
    the spread cut in `djvu.py`, and the detector if a spread reached it whole.
    """
    pg = _page(doc, wide=True); t = []
    _half(pg, t, 0.0, rng, "table")
    _half(pg, t, PW, rng, "figure")
    return pg, t


def c_spread_rotated(doc, rng):
    """A SPREAD ROTATED 90°: for a large full-width table.

    Everywhere in handbooks: a table or drawing that will not fit across is
    printed along. Reading order for such a page is undefined, and the detector
    sees it squashed into 800x800 without keeping the aspect ratio -- the
    distortion is at its worst here.
    """
    pg = _page(doc, wide=True); t = []
    _flow(pg, t, MARGIN, TOP, 150, PROSE_EN, w=2 * PW - 2 * MARGIN)
    _table(pg, t, MARGIN + 6, 180,
           [(f"Col {i}", MARGIN + 6 + i * 118) for i in range(8)], 34)
    pg.insert_text((PW - 20, BOT + 18), "308-309", fontname="F", fontsize=6.4)
    t.append((PW - 24, BOT + 11, PW + 20, BOT + 20, "number"))
    _say(t, "308-309")
    return pg, t


# --- tables of various sizes: their contours are what matters now -----------
def c_table_half_page(doc, rng):
    """A half-sheet table, the full measure wide."""
    pg = _page(doc); t = []
    _flow(pg, t, MARGIN, TOP, 330, PROSE_EN, w=2 * COLW + GUT)
    _table(pg, t, MARGIN + 6, 360, _grid(MARGIN + 6, 5, colw=76), 30, colw=76)
    return pg, t


def c_table_full_width(doc, rng):
    """A full-width table mid-page, text above and below."""
    pg = _page(doc); t = []
    _flow(pg, t, MARGIN, TOP, 230, PROSE_EN, w=2 * COLW + GUT)
    _table(pg, t, MARGIN + 6, 260, _grid(MARGIN + 6, 6, colw=62), 12)
    _flow(pg, t, MARGIN, 420, BOT, PROSE_EN, w=2 * COLW + GUT)
    return pg, t


def c_table_tall_narrow(doc, rng):
    """A narrow tall table in one column, prose beside it."""
    pg = _page(doc); t = []
    _table(pg, t, COL_X[0] + 6, TOP + 10, _grid(COL_X[0] + 6, 2, colw=90), 58,
           colw=90)
    _flow(pg, t, COL_X[1], TOP, BOT, PROSE_EN)
    return pg, t


def c_table_wide_short(doc, rng):
    """A wide three-row table: shorter than a paragraph."""
    pg = _page(doc); t = []
    _flow(pg, t, MARGIN, TOP, 260, PROSE_EN, w=2 * COLW + GUT)
    _table(pg, t, MARGIN + 6, 290, _grid(MARGIN + 6, 7, colw=52), 3, colw=52)
    _flow(pg, t, MARGIN, 350, BOT, PROSE_EN, w=2 * COLW + GUT)
    return pg, t


def c_table_ruled(doc, rng):
    """The same table, but RULED: how much easier the detector finds it."""
    pg = _page(doc); t = []
    _flow(pg, t, MARGIN, TOP, 240, PROSE_EN, w=2 * COLW + GUT)
    _table(pg, t, MARGIN + 6, 270, _grid(MARGIN + 6, 5, colw=76), 14,
           colw=76, ruled=True)
    _flow(pg, t, MARGIN, 460, BOT, PROSE_EN, w=2 * COLW + GUT)
    return pg, t


def c_table_split_a(doc, rng):
    """A table cut off by the page foot (continued on the next)."""
    pg = _page(doc); t = []
    _flow(pg, t, MARGIN, TOP, 300, PROSE_EN, w=2 * COLW + GUT)
    _table(pg, t, MARGIN + 6, 330, _grid(MARGIN + 6, 5, colw=76), 34, colw=76)
    return pg, t


def c_table_split_b(doc, rng):
    """The same table continued from the top of the next page."""
    pg = _page(doc); t = []
    _table(pg, t, MARGIN + 6, TOP + 6, _grid(MARGIN + 6, 5, colw=76), 22,
           colw=76)
    _flow(pg, t, MARGIN, 280, BOT, PROSE_EN, w=2 * COLW + GUT)
    return pg, t


def c_chart_page(doc, rng):
    """A chart with axes: the model has a separate `chart` class."""
    pg = _page(doc); t = []
    _flow(pg, t, MARGIN, TOP, 220, PROSE_EN, w=2 * COLW + GUT)
    _chart(pg, t, MARGIN + 30, 250, 2 * COLW + GUT - 60, 150)
    _flow(pg, t, MARGIN, 460, BOT, PROSE_EN, w=2 * COLW + GUT)
    return pg, t


def c_figure_full_width(doc, rng):
    """A figure the full measure wide."""
    pg = _page(doc); t = []
    _flow(pg, t, MARGIN, TOP, 220, PROSE_EN, w=2 * COLW + GUT)
    _figure(pg, t, MARGIN, 250, 2 * COLW + GUT, 190, "Fig. 7  General layout")
    _flow(pg, t, MARGIN, 480, BOT, PROSE_EN, w=2 * COLW + GUT)
    return pg, t


def c_russian_table_wide(doc, rng):
    """Cyrillic plus a wide full-width table."""
    pg = _page(doc); t = []
    _flow(pg, t, MARGIN, TOP, 230, PROSE_RU, w=2 * COLW + GUT)
    _table(pg, t, MARGIN + 6, 260,
           list(zip(HEADS_RU, (MARGIN + 6, MARGIN + 96, MARGIN + 186,
                               MARGIN + 276, MARGIN + 356))), 16, colw=76)
    _flow(pg, t, MARGIN, 470, BOT, PROSE_RU, w=2 * COLW + GUT)
    return pg, t


def c_spread_table_wide(doc, rng):
    """A SPREAD with a table ACROSS THE GUTTER: it runs over both pages."""
    pg = _page(doc, wide=True); t = []
    for x0 in (0.0, PW):
        _flow(pg, t, x0 + MARGIN, TOP, 250, PROSE_EN, w=2 * COLW + GUT)
    _table(pg, t, MARGIN + 6, 290,
           _grid(MARGIN + 6, 11, colw=76), 20, colw=76)
    for x0 in (0.0, PW):
        _flow(pg, t, x0 + MARGIN, 560, BOT, PROSE_EN, w=2 * COLW + GUT)
    return pg, t


def c_spread_rotated_figure(doc, rng):
    """A SPREAD ROTATED 90°, with a large full-width drawing."""
    pg = _page(doc, wide=True); t = []
    _flow(pg, t, MARGIN, TOP, 130, PROSE_EN, w=2 * PW - 2 * MARGIN)
    _figure(pg, t, MARGIN, 160, 2 * PW - 2 * MARGIN, 440,
            "Fig. 12  Machine tool bed, general arrangement")
    return pg, t


# --- added cases: harder than the earlier ones ------------------------------
# The earlier twenty-three mostly held one artifact per page with wide gaps.
# A real book does not: two artifacts of different kinds stand adjacent, column
# gaps are narrower than the leading, and a library stamp sits over it all.

def c_table_two_side_by_side(doc, rng):
    """TWO tables side by side -- a common handbook spread (three exist)."""
    pg = _page(doc); t = []
    _flow(pg, t, MARGIN, TOP, 250, PROSE_EN, w=2 * COLW + GUT)
    for k, x0 in enumerate((MARGIN + 6, PW / 2 + 24)):
        pg.insert_text((x0, 272), f"TABLE {k + 1}", fontname="F", fontsize=7.4)
        t.append((x0 - 3, 264, x0 + 44, 276, "paragraph_title"))
        _say(t, f"TABLE {k + 1}")
        _table(pg, t, x0, 292, _grid(x0, 2, colw=64), 14, colw=64)
    _flow(pg, t, MARGIN, 460, BOT, PROSE_EN, w=2 * COLW + GUT)
    return pg, t


def c_table_two_stacked(doc, rng):
    """Two tables ONE UNDER THE OTHER: this catches vertical merging."""
    pg = _page(doc); t = []
    _flow(pg, t, MARGIN, TOP, 150, PROSE_EN, w=2 * COLW + GUT)
    y = 176
    for k in range(2):
        pg.insert_text((MARGIN + 6, y), f"TABLE {k + 4}.  Shaft fits",
                       fontname="F", fontsize=7.0)
        t.append((MARGIN + 3, y - 8, MARGIN + 3 + 96, y + 4, "paragraph_title"))
        _say(t, f"TABLE {k + 4}.  Shaft fits")
        y = _table(pg, t, MARGIN + 6, y + 22, _grid(MARGIN + 6, 5, colw=84), 11,
                   colw=84) + 26
    _flow(pg, t, MARGIN, y, BOT, PROSE_EN, w=2 * COLW + GUT)
    return pg, t


def c_table_spanning_header(doc, rng):
    """A two-tier header with spanning cells over groups of columns."""
    pg = _page(doc); t = []
    _flow(pg, t, MARGIN, TOP, 190, PROSE_EN, w=2 * COLW + GUT)
    _span_header_table(pg, t, MARGIN + 8, 226,
                       [("CLEARANCE", 3), ("INTERFERENCE", 3), ("TRANSITION", 2)],
                       22)
    _flow(pg, t, MARGIN, 480, BOT, PROSE_EN, w=2 * COLW + GUT)
    return pg, t


def c_table_dense_no_rules(doc, rng):
    """A dense unruled table: column gaps as narrow as the leading.

    The hardest kind and the commonest in our books. A bench without it
    measures an easier task than the real one -- the reproach it once earned.
    """
    pg = _page(doc); t = []
    _flow(pg, t, MARGIN, TOP, 130, PROSE_EN, w=2 * COLW + GUT)
    _table(pg, t, MARGIN + 6, 158, _grid(MARGIN + 6, 9, colw=44, gap=2.0), 62,
           colw=44, step=7.4, size=5.6)
    _flow(pg, t, MARGIN, 620, BOT, PROSE_EN, w=2 * COLW + GUT)
    return pg, t


def c_table_leaders(doc, rng):
    """A table on dot leaders -- one feature separates it from contents."""
    pg = _page(doc); t = []
    _flow(pg, t, MARGIN, TOP, 150, PROSE_EN, w=2 * COLW + GUT)
    _leader_table(pg, t, MARGIN + 8, 190, 26)
    _leader_table(pg, t, PW / 2 + 14, 190, 26, w=200)
    _flow(pg, t, MARGIN, 470, BOT, PROSE_EN, w=2 * COLW + GUT)
    return pg, t


def c_photo_halftone(doc, rng):
    """A halftone photograph beside prose."""
    pg = _page(doc); t = []
    _flow(pg, t, MARGIN, TOP, 170, PROSE_EN, w=2 * COLW + GUT)
    _halftone(pg, t, MARGIN + 10, 200, 2 * COLW + GUT - 20, 250)
    _flow(pg, t, MARGIN, 480, BOT, PROSE_EN, w=2 * COLW + GUT)
    return pg, t


def c_figure_and_table(doc, rng):
    """A drawing and a table FLUSH: two artifact kinds with no gap."""
    pg = _page(doc); t = []
    _flow(pg, t, MARGIN, TOP, 150, PROSE_EN, w=2 * COLW + GUT)
    _figure(pg, t, MARGIN + 6, 178, COLW - 6, 200,
            "Fig. 44  Tailstock")
    _table(pg, t, MARGIN + COLW + GUT + 10, 178,
           _grid(MARGIN + COLW + GUT + 10, 2, colw=76), 20, colw=76)
    _flow(pg, t, MARGIN, 420, BOT, PROSE_EN, w=2 * COLW + GUT)
    return pg, t


def c_figure_text_wrap(doc, rng):
    """Text wraps a figure: the column breaks, the figure sits in its body."""
    pg = _page(doc); t = []
    _flow(pg, t, MARGIN, TOP, 130, PROSE_EN, w=2 * COLW + GUT)
    _figure(pg, t, MARGIN + 6, 160, COLW - 10, 170, "Fig. 51  Chuck jaw")
    x2 = MARGIN + COLW + GUT
    _flow(pg, t, x2, 160, 350, PROSE_EN, w=COLW)
    _flow(pg, t, MARGIN, 366, BOT, PROSE_EN, w=2 * COLW + GUT)
    return pg, t


def c_marginalia(doc, rng):
    """Notes in the outer margin: a narrow column beside the main one."""
    pg = _page(doc); t = []
    for y0, y1 in ((TOP, 300), (320, 560), (580, BOT)):
        r = _rect(MARGIN, y0, MARGIN + COLW + GUT + 30, y1)
        body = _fill(pg, r, PROSE_EN, 6.6)
        t.append((MARGIN, y0, MARGIN + COLW + GUT + 30, y1, "text"))
        _say(t, body)
    xm = MARGIN + COLW + GUT + 46
    for k, y0 in enumerate((TOP + 20, 260, 470, 640)):
        r = _rect(xm, y0, PW - MARGIN, y0 + 60)
        body = _fill(pg, r,
                     "Note. See Sec. 26 for the tolerance grades used here. ",
                     5.6)
        t.append((xm, y0, PW - MARGIN, y0 + 60, "aside_text"))
        _say(t, body)
    return pg, t


def c_footnotes_rule(doc, rng):
    """Footnotes under a short rule at the foot of the measure."""
    pg = _page(doc); t = []
    _flow(pg, t, MARGIN, TOP, 560, PROSE_EN, w=2 * COLW + GUT)
    pg.draw_line(_rect(MARGIN, 590, MARGIN + 120, 590).tl,
                 _rect(MARGIN, 590, MARGIN + 120, 590).tr,
                 color=(0, 0, 0), width=0.5)
    for k in range(3):
        r = _rect(MARGIN, 598 + k * 26, MARGIN + 2 * COLW + GUT, 620 + k * 26)
        body = _fill(pg, r,
                     f"{k + 1} Trans. A.S.M.E., vol. 61, p. {120 + k * 7}. ",
                     5.6)
        t.append((MARGIN, 598 + k * 26, MARGIN + 2 * COLW + GUT, 620 + k * 26,
                  "footnote"))
        _say(t, body)
    pg.insert_text((PW / 2 - 6, BOT + 14), "417", fontname="F", fontsize=6.4)
    t.append((PW / 2 - 8, BOT + 6, PW / 2 + 12, BOT + 17, "number"))
    _say(t, "417")
    return pg, t


def c_stamp_over_text(doc, rng):
    """A library stamp over the text, a table under it."""
    pg = _page(doc); t = []
    _flow(pg, t, MARGIN, TOP, 220, PROSE_EN, w=2 * COLW + GUT)
    _table(pg, t, MARGIN + 6, 250, _grid(MARGIN + 6, 4, colw=86), 16, colw=86)
    _flow(pg, t, MARGIN, 440, BOT, PROSE_EN, w=2 * COLW + GUT)
    _stamp(pg, t, PW - MARGIN - 60, 120)
    return pg, t


def c_rotated_single_table(doc, rng):
    """A SINGLE page rotated 90° for a wide table."""
    pg = _page(doc); t = []
    _flow(pg, t, MARGIN, TOP, 140, PROSE_EN, w=2 * COLW + GUT)
    _table(pg, t, MARGIN + 6, 170, _grid(MARGIN + 6, 8, colw=50), 36, colw=50,
           step=8.4)
    return pg, t


def c_chart_pair(doc, rng):
    """Two charts side by side -- adjacent axes glue into one box easily."""
    pg = _page(doc); t = []
    _flow(pg, t, MARGIN, TOP, 160, PROSE_EN, w=2 * COLW + GUT)
    _chart(pg, t, MARGIN + 24, 200, COLW - 40, 150, "Fig. 61  Hardness")
    _chart(pg, t, MARGIN + COLW + GUT + 24, 200, COLW - 40, 150,
           "Fig. 62  Toughness")
    _flow(pg, t, MARGIN, 420, BOT, PROSE_EN, w=2 * COLW + GUT)
    return pg, t


CASES = {
    # --- plain pages ---
    "two_columns": c_two_columns,
    "no_artefacts": c_no_artefacts,
    "contents_dots": c_contents_dots,
    "russian": c_russian,
    # --- tables of various sizes ---
    "table_across_gutter": c_table_across_gutter,
    "three_column_table": c_three_column_table,
    "table_half_page": c_table_half_page,
    "table_full_width": c_table_full_width,
    "table_tall_narrow": c_table_tall_narrow,
    "table_wide_short": c_table_wide_short,
    "table_ruled": c_table_ruled,
    "table_full_page": c_full_page_table,
    "table_split_a": c_table_split_a,
    "table_split_b": c_table_split_b,
    "russian_table_wide": c_russian_table_wide,
    "formula_next_to_table": c_formula_next_to_table,
    "table_two_side_by_side": c_table_two_side_by_side,
    "table_two_stacked": c_table_two_stacked,
    "table_spanning_header": c_table_spanning_header,
    "table_dense_no_rules": c_table_dense_no_rules,
    "table_leaders": c_table_leaders,
    # --- figures and charts ---
    "two_figures_side": c_two_figures_side,
    "figure_full_width": c_figure_full_width,
    "chart_page": c_chart_page,
    "chart_pair": c_chart_pair,
    "photo_halftone": c_photo_halftone,
    "figure_and_table": c_figure_and_table,
    "figure_text_wrap": c_figure_text_wrap,
    # --- other page furniture ---
    "marginalia": c_marginalia,
    "footnotes_rule": c_footnotes_rule,
    "stamp_over_text": c_stamp_over_text,
    "rotated_single_table": c_rotated_single_table,
    # --- spreads and rotations ---
    "spread": c_spread,
    "spread_table_wide": c_spread_table_wide,
    "spread_rotated": c_spread_rotated,
    "spread_rotated_figure": c_spread_rotated_figure,
}
# Cases to be rotated 90° after drawing.
ROTATE = {"spread_rotated": 90, "spread_rotated_figure": 90,
          "rotated_single_table": 90}
# Spread cases: a binding shadow is drawn onto them.
SPREADS = {"spread", "spread_table_wide", "spread_rotated",
           "spread_rotated_figure"}


# --------------------------------------------------------------------- aging
# Profiles are NAMED sets, not scattered knobs: their parameters go into the
# snapshot whole, so naming the profile is enough to repeat a run.
AGING = {
    "clean": {},
    "scan": dict(blur=0.5, noise=3.0, speck=0.0004, tint=(244, 6, 4),
                 skew=0.5, jpeg=85),
    "old": dict(blur=0.8, noise=5.5, speck=0.0012, tint=(232, 12, 8),
                skew=1.2, jpeg=68),
    # decayed: show-through from the back and a dark scan edge added to `old`.
    # Neither moves a truth box. The skew is DELIBERATELY that of `old`, skew
    # being the ONLY part of aging that does move them (through `_xform_box`);
    # at equal skew the two profiles' boxes match byte for byte, so a
    # difference in the number belongs to the paper. The old edition set 1.8
    # while the README promised "decayed does not move truth boxes" -- it moved
    # all 382.
    "decayed": dict(blur=1.1, noise=7.5, speck=0.0026, tint=(214, 20, 14),
                   skew=1.2, jpeg=52, bleed=0.16, edge=0.55),
}


def _age(img, profile: str, seed: int):
    """Age the raster. Returns (raster, rotation matrix or None).

    Aging is not decoration: measured on one page, the CLEAN page has no
    `table` box at all while the aged one grows one (0.583) -- with a competing
    `text` 0.567 on the same rectangle, the signature of the very defect
    diagnosed on a real book. Clean paper would measure a different task.
    """
    import cv2
    import numpy as np

    p = AGING[profile]
    if not p:
        return img, None
    rng = np.random.default_rng(seed)
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)
    g = cv2.GaussianBlur(g, (0, 0), p["blur"])          # ink spread
    h, w = g.shape
    if p.get("bleed"):
        # Show-through: the mirrored page, blurred and weak. The plague of old
        # thin paper, and exactly the kind of "text" that is not on the page
        # while a box can still land on it. With an OFFSET: without one,
        # symmetric layout puts the mirror on its own text and show-through
        # becomes thicker ink, testing something other than its name. A book's
        # back lines up with its front neither by line nor by column.
        back = cv2.GaussianBlur(g[:, ::-1], (0, 0), p["blur"] * 3.0)
        sx, sy = int(w * 0.035), int(h * 0.012)
        back = np.roll(np.roll(back, sy, axis=0), sx, axis=1)
        g = 255.0 - (255.0 - g) - p["bleed"] * (255.0 - back)
        g = np.clip(g, 0, 255)
    yy, xx = np.mgrid[0:h, 0:w]
    base, gx, gy = p["tint"]
    g = np.minimum(g, 255) / 255.0 * (base - gx * (xx / w) - gy * (yy / h))
    g += rng.normal(0, p["noise"], g.shape)             # paper grain
    spec = rng.random(g.shape) < p["speck"]             # specks
    g[spec] = rng.uniform(40, 120, spec.sum())
    if p.get("edge"):
        # Dark scan edge: a book shot on a flatbed has a black border. A band
        # 1-3% of the sheet wide, on one random side. Its own generator, or the
        # edge draws would shift the stream and the SKEW ANGLE of a profile
        # with an edge would differ from one without -- truth boxes diverging
        # where a match is promised.
        erng = np.random.default_rng(seed + 991)
        side = int(erng.integers(0, 4))
        d = int(max(6, min(h, w) * erng.uniform(0.008, 0.03)))
        k = 1.0 - p["edge"]
        if side == 0:
            g[:d, :] *= k
        elif side == 1:
            g[-d:, :] *= k
        elif side == 2:
            g[:, :d] *= k
        else:
            g[:, -d:] *= k
    g = np.clip(g, 0, 255).astype(np.uint8)
    M = None
    if p["skew"]:
        # Its OWN generator: from the shared one the angle would depend on how
        # many draws were taken above, and that count depends on `speck`. That
        # is how two profiles with the SAME skew diverged on all 382 truth
        # boxes, by up to 28 pixels, and cross-profile comparison silently
        # measured a different truth.
        ang = np.random.default_rng(seed + 4409).uniform(-p["skew"], p["skew"])
        M = cv2.getRotationMatrix2D((w / 2, h / 2), ang, 1.0)
        g = cv2.warpAffine(g, M, (w, h), flags=cv2.INTER_CUBIC,
                           borderMode=cv2.BORDER_REPLICATE)
    ok, enc = cv2.imencode(".jpg", g, [cv2.IMWRITE_JPEG_QUALITY, p["jpeg"]])
    if not ok:
        raise SynthError("could not re-compress the page to JPEG")
    return cv2.imdecode(enc, cv2.IMREAD_COLOR), M


def _binding(img, seed: int):
    """The binding shadow down the middle of a spread.

    The very shadow the cut veto once got wrong eleven times out of eleven: the
    blackness at the gutter came from the shadow while the code checked a band
    rather than a continuous rule. A synthetic spread must carry it, or the
    veto is checked on a case that does not exist in nature.
    """
    import cv2
    import numpy as np

    rng = np.random.default_rng(seed + 7)
    h, w = img.shape[:2]
    cx = w // 2 + int(rng.integers(-w // 60, w // 60))
    band = max(8, w // 40)
    xx = np.arange(w)
    prof = np.exp(-((xx - cx) ** 2) / (2 * (band / 2.2) ** 2))
    # Denser at the top: on spread scans the head of the gutter is blackest.
    depth = np.linspace(0.62, 0.30, h)[:, None] * prof[None, :]
    out = img.astype(np.float32) * (1.0 - depth[:, :, None])
    return np.clip(out, 0, 255).astype(np.uint8), cx


def _xform_box(box, M):
    """A box after an affine transform: the rectangle bounding its corners.

    For a model with axis-aligned boxes that is the correct truth: a rotated
    rectangle cannot be expressed there, and the one bounding it is exactly
    what the detector is obliged to return.
    """
    import numpy as np
    x0, y0, x1, y1 = box
    pts = np.array([[x0, y0, 1], [x1, y0, 1], [x1, y1, 1], [x0, y1, 1]]).T
    q = M @ pts
    return (float(q[0].min()), float(q[1].min()),
            float(q[0].max()), float(q[1].max()))


def _clip_box(box, w, h):
    """A box inside the raster. Skew pushes edges off the sheet, and unclipped
    the truth would partly lie outside the page -- where the model cannot put a
    box by construction, so the miss would be undeserved."""
    x0, y0, x1, y1 = box
    return (max(0.0, min(x0, w)), max(0.0, min(y0, h)),
            max(0.0, min(x1, w)), max(0.0, min(y1, h)))


def _rot90_box(box, src_h):
    """A box after the raster is rotated 90° clockwise.

    A point y goes to x' = src_h - 1 - y, so [y0, y1] becomes
    [src_h-1-y1, src_h-1-y0]; the RIGHT edge is half-open and so equals
    src_h - y0, not src_h - 1 - y0. The old edition lost a pixel on every box
    of a rotated page -- little, but exactly the direction the truth is obliged
    not to err in.
    """
    x0, y0, x1, y1 = box
    return (src_h - 1 - y1, x0, src_h - y0, x1)


def _commit() -> str:
    """The commit of the SOURCE REPOSITORY, not of the process working dir."""
    import subprocess
    root = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))
    try:
        p = subprocess.run(["git", "-C", root, "status", "--porcelain"],
                           capture_output=True, text=True, timeout=10)
        h = subprocess.run(["git", "-C", root, "rev-parse", "HEAD"],
                           capture_output=True, text=True, timeout=10)
        if h.returncode != 0:
            return "not a repository"
        return h.stdout.strip() + (" (dirty tree)" if p.stdout.strip() else "")
    except Exception as e:
        return f"git was not asked: {e}"


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# --------------------------------------------------------- measured truth
# Truth boxes are measured AGAINST THE INK, not declared as numbers. The reason
# is money: in one evening this generator lied about boxes four times, and all
# four times the numbers looked healthy -- empty text boxes, the right half of
# a spread past the sheet edge (pixels in a field that counts points), a ruled
# form instead of a drawing, and a formula box 83 points wider than the
# formula, a constant set by eye. The last cost the model a false accusation:
# `formula_next_to_table` was filed as its refusal.
#
# Measured, a box cannot come out wider than the drawing, and an empty box
# FAILS instead of keeping quiet.
INK = 160          # darker than this is ink (clean page, before aging)
KEEP = 2           # this many pixels of margin left around the measurement
# Labels whose boxes the cases set by eye around text: they may not only shrink
# to the ink but grow to it. Geometric boxes (table, figure, chart, text
# column) are computed by code and only shrink.
GUESSED = {"figure_title", "display_formula", "doc_title", "paragraph_title",
           "number", "content", "footnote"}
GROW = 6           # how far such a box may grow, in pixels


def _measure(img, boxes, case: str):
    """Pull truth boxes to the ink. An empty box is an error, not a zero."""
    import cv2
    import numpy as np

    ink = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) < INK
    h, w = ink.shape
    out = []
    for x0, y0, x1, y1, lab in boxes:
        a, b = max(0, int(x0)), max(0, int(y0))
        c, d = min(w, int(round(x1))), min(h, int(round(y1)))
        sub = ink[b:d, a:c]
        if sub.size == 0 or not sub.any():
            raise SynthError(
                f"{case}: the truth box {lab} "
                f"{[round(v) for v in (x0, y0, x1, y1)]} is EMPTY -- not one "
                f"pixel is drawn under it. This is not \"a block with no "
                f"content\", this is NOT DRAWN, and in a measurement such a "
                f"box gives the model a permanent undeserved miss.")
        ys, xs = np.where(sub)
        L, T = a + int(xs.min()), b + int(ys.min())
        R, B = a + int(xs.max()) + 1, b + int(ys.max()) + 1
        if lab in GUESSED:
            # Growth ONLY ALONG CONTINUOUS INK. The old edition took the ink
            # box of a window widened by GROW on every side, so a foreign line
            # four pixels away set the edge -- flatly against the docstring: a
            # box is measured against ITS OWN ink. We spread while the next row
            # is non-empty and not a pixel further.
            for _ in range(GROW):
                if L > 0 and ink[T:B, L - 1].any():
                    L -= 1
                if R < w and ink[T:B, R].any():
                    R += 1
                if T > 0 and ink[T - 1, L:R].any():
                    T -= 1
                if B < h and ink[B, L:R].any():
                    B += 1
        out.append((max(0.0, L - KEEP), max(0.0, T - KEEP),
                    min(float(w), R + KEEP), min(float(h), B + KEEP), lab))
    return out


def _text_check(words, boxes, said, case: str):
    """Check the character truth against the PDF TEXT LAYER of the same page.

    Synthetic pages are DRAWN, not scanned, so a clean page has a text layer --
    a second witness independent of our bookkeeping: `_say` records what we
    MEANT to draw, `page.get_text("words")` what actually landed. Nothing had
    such a witness before.

    FOUR NUMBERS, DIFFERENT IN MEANING (a zero from a check and a zero from
    incomprehension are different zeros):

    `missing_from_layer` -- the truth claims a word not on the paper. The one
    real alarm: a box claimed richer than the drawing looks like this.

    `outside_truth` -- a word drawn, covered by NO truth box. Some are
    deliberate (catalogue line numbers stand left of the table box), so the
    number is printed, not forbidden: a silent counter would lie the way
    "0 chapters" lied about four books at once.

    `ghosts` -- a word in a box repeating one already claimed. Source known and
    measured: `insert_textbox` runs several times per box (30 passes for the 20
    boxes of `no_artefacts`) and the layer holds EVERY draft. Layer words
    matched all draft words exactly, 2198 against 2198, 0 unexplained.

    `unexplained` -- a word in a box the truth does not hold at all and
    repetition does not explain. Zero is the norm; anything else must be NAMED,
    so examples print beside the number. One is found: `marginalia` carries the
    fragment `sc`, left when `_fill` cut the body at `len*0.9` inside `screw`
    and the next pass appended flush against it. Nobody had seen it before.

    THE BLIND SPOT: a word lost by the truth that OCCURS AGAIN in the block
    goes to `ghosts`, not `unexplained` -- a mutation put 8 of 16 dropped last
    words there. On prose it widens with the block.

    Only roles text and service are checked: an artifact has no `content`.
    """
    from collections import Counter
    from . import policy

    inside = [[] for _ in boxes]
    outside = []
    for x0, y0, x1, y1, w in words:
        cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        # Of the covering boxes take the SMALLEST: boxes nest (a title block
        # inside a drawing field), and "first in the list" would hand the word
        # to the outer box, counting the wrong thing.
        best, area = None, None
        for j, b in enumerate(boxes):
            if b[0] <= cx <= b[2] and b[1] <= cy <= b[3]:
                a = (b[2] - b[0]) * (b[3] - b[1])
                if area is None or a < area:
                    best, area = j, a
        if best is None:
            outside.append(w)
        else:
            inside[best].append(w)

    miss = ghost = unknown = leaders = 0
    samples = []
    for j, b in enumerate(boxes):
        if policy.role(b[4]) == "artifact":
            continue
        have = Counter(inside[j])
        want = Counter((said.get(j, {}).get("text") or "").split())
        m = want - have
        e = have - want
        miss += sum(m.values())
        for w, n in e.items():
            if w in want:
                ghost += n
            elif len(w) >= 4 and set(w) == {"."}:
                # A DOT LEADER is not a word but a typographic rule (see the
                # decision in `_leader_table`). Counted separately rather than
                # as `unexplained`, or sixty contents leaders would hold the
                # alarming counter non-zero forever and hide a real find.
                leaders += n
            else:
                unknown += n
                if len(samples) < 4:
                    samples.append(f"{b[4]}#{j}: {w!r}")
        if m and len(samples) < 4:
            samples.append(f"{b[4]}#{j}: not in the layer {list(m)[:3]}")
    return {"words_in_layer": len(words), "missing_from_layer": miss,
            "outside_truth": len(outside), "ghosts": ghost,
            "dot_leaders": leaders, "unexplained": unknown,
            "outside_truth_samples": sorted(set(outside))[:8],
            "mismatch_examples": samples}


def build(out_dir: str, cases=None, seed: int = 1, aging: str = "old",
          book: str = "spravochnik", log=print) -> dict:
    """Build the synthetic book: a PDF plus exact truth for every page.

    The product is an ordinary PDF, so `books detect`, `books html` and
    `books feed` work on it unamended: the bench is not a separate pipeline,
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
    from .books import load
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
        # as text in any feed mode (`doc/feed.py`), its characters are the
        # SECOND level's answer, and their reference lies beside, in
        # `meta["artifact_truth"]`, by block number. The `Block` schema is
        # untouched: a sixth field there would break `Page.from_json`.
        from . import policy
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

    src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "synth.py")
    man = {"book": book, "about": getattr(mod, "ABOUT", ""),
           "page_count": len(pages), "synth_seed": seed, "aging": aging,
           "generator": {"file": "synth.py", "sha256": _sha256(src),
                         "commit": _commit(),
                         "cases": names, "book": book,
                         "sha256_book_module": _sha256(mod.__file__),
                         "guessed_labels": sorted(GUESSED),
                         "INK": INK, "KEEP": KEEP, "GROW": GROW},
           "knobs": knobs.snapshot() if hasattr(knobs, "snapshot") else None,
           "aging_params": AGING[aging],
           "fonts": {os.path.basename(FONT): _sha256(FONT),
                      os.path.basename(FONT_MONO): _sha256(FONT_MONO)},
           "pdf": os.path.basename(pdf), "sha256 pdf": _sha256(wpdf),
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
