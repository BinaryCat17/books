"""The handbook: a dense two-column English technical handbook of the
fifties, the first book of the bench and the one whose cases the drawers
were written for. Its sheet is the drawers' default.
"""
from booksmith.datasets.make.synth.draw import (
    BOT,
    COLW,
    COL_X,
    FIG_CAPTION_RU,
    GUT,
    HEADS_RU,
    MARGIN,
    PROSE_EN,
    PROSE_RU,
    PW,
    TOP,
    W,
    H,
    _chart,
    _figure,
    _fill,
    _flow,
    _grid,
    _halftone,
    _leader_table,
    _page,
    _rect,
    _say,
    _span_header_table,
    _stamp,
    _table)

SHEET = (W, H)

ABOUT = ("English technical handbook of the fifties: dense two-column "
         "setting, tables without rules, drawings, spreads and rotations")


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
    """Three SEPARATE tables side by side: the model takes one of three (p. 317).
    The gaps between the tables are three times the gaps between their columns
    and each has its own caption, or what is drawn is one table."""
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
                             COL_X[0] + 146), strict=False)), 6)
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
    """A SPREAD: two book pages scanned as one sheet, as half our library lies.
    Wider than tall, with a shadowed gutter down the middle; it checks the spread
    cut in `djvu.py` and the detector if a spread reaches it whole."""
    pg = _page(doc, wide=True); t = []
    _half(pg, t, 0.0, rng, "table")
    _half(pg, t, PW, rng, "figure")
    return pg, t


def c_spread_rotated(doc, rng):
    """A SPREAD ROTATED 90°, as a handbook prints a table that will not fit
    across. Reading order for such a page is undefined, and the detector sees it
    squashed into a square without the aspect ratio -- the worst distortion."""
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
                               MARGIN + 276, MARGIN + 356), strict=False)), 16, colw=76)
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


# --- the harder cases -------------------------------------------------------
# A real book does not hold one artifact per page with wide gaps: two artifacts
# of different kinds stand adjacent, column gaps are narrower than the leading,
# and a library stamp sits over it all.

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
    """A dense unruled table, column gaps as narrow as the leading: the hardest
    kind and the commonest in our books, and a bench without it measures an
    easier task than the real one."""
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
    for _k, y0 in enumerate((TOP + 20, 260, 470, 640)):
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


