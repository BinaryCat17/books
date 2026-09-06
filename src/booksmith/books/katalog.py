"""A parts catalogue: a page with nothing on it but the table.

WHY. In the handbook a table is always surrounded by prose, and it was "found"
in large part BECAUSE there was text to tell it from. Here the table IS the
page: a running head above, a folio below, forty rows of figures between. The
hypothesis: with nothing around it, the detector either boxes the whole page
or tears the table into pieces.

The second hypothesis is CONTINUATION. A real catalogue carries one table
across a dozen pages: the header repeats and "Continuation of Table 7" stands
at the left. Does the model tell a repeated header from a running head, and
does it glue the continuation line onto the table?

The control is `kat_two_stacked`, two tables one under the other. The handbook
passes that pair correctly, so a failure here is about the bare page and not
about the pair itself.
"""
from ..synth import (PROSE_EN, _flow, _grid, _line, _page, _put,
                     _running_head, _say, _table, _text_w)

SHEET = (1012, 1466)
PT = 0.5
PW, PH = SHEET[0] * PT, SHEET[1] * PT
MARGIN, TOP, BOT_Y = 30.0, 46.0, 700.0
ABOUT = ("parts catalogue: a page with no prose, long tables running over "
         "many pages, a repeated header, \"Continuation of Table\", a "
         "footnote under the table")


def _sheet(doc, wide=False):
    return _page(doc, wide=wide, pw=PW, ph=PH)


def _head(pg, t, page_no, right="SHAFT FITS"):
    _running_head(pg, t, MARGIN, PW - MARGIN, TOP - 14, "PART CATALOGUE",
                  right, page_no)


def _cat_table(pg, t, x, y, n_cols, rows, colw=52.0, step=9.6, size=5.8,
               numbered=False):
    cols = _grid(x, n_cols, colw=colw, gap=6.0)
    y1 = _table(pg, t, x, y, cols, rows, size=size, colw=colw, step=step)
    if numbered:
        # ROW NUMBERS ARE DRAWN LEFT OF THE TABLE BOX (x-20 against x-6) AND
        # HAVE NO BOX OF THEIR OWN -- that IS the case `kat_row_numbers`: does
        # the model take them as a separate box or pull them into the table?
        # So they are ink and words OUTSIDE every truth box, and the bench must
        # NAME that with a number rather than hide it. The "words outside the
        # truth" counter in `build` catches exactly these, and its non-zero
        # value here is a declared property of the page, not a defect.
        for r in range(rows):
            _put(pg, x - 20, y + 10 + r * step, f"{r + 1}", size, sheet_w=PW)
    return y1


def c_kat_full_table(doc, rng):
    """The page is one table, full height. Not a line of prose."""
    pg = _sheet(doc); t = []
    _head(pg, t, 214)
    _cat_table(pg, t, MARGIN + 8, TOP + 34, 7, 62, colw=58.0, step=10.2)
    return pg, t


def c_kat_continued(doc, rng):
    """"Continuation of Table 7" and a repeated header."""
    pg = _sheet(doc); t = []
    _head(pg, t, 215)
    w = _put(pg, MARGIN + 8, TOP + 30, "Continuation of Table 7", 6.6,
             sheet_w=PW)
    t.append((MARGIN + 6, TOP + 30 - 6.6, MARGIN + 8 + w + 2, TOP + 33,
              "paragraph_title"))
    _say(t, "Continuation of Table 7")
    _cat_table(pg, t, MARGIN + 8, TOP + 58, 7, 58, colw=58.0, step=10.2)
    return pg, t


def c_kat_row_numbers(doc, rng):
    """A column of row numbers at the left: own box, or part of the table."""
    pg = _sheet(doc); t = []
    _head(pg, t, 216)
    _cat_table(pg, t, MARGIN + 30, TOP + 34, 6, 60, colw=62.0, step=10.4,
               numbered=True)
    return pg, t


def c_kat_mid_start(doc, rng):
    """The table starts IN THE MIDDLE of the page, prose ends above it."""
    pg = _sheet(doc); t = []
    _head(pg, t, 217)
    _flow(pg, t, MARGIN, TOP + 30, 300, PROSE_EN, w=PW - 2 * MARGIN)
    _cat_table(pg, t, MARGIN + 8, 330, 7, 36, colw=58.0, step=10.2)
    return pg, t


def c_kat_mid_end(doc, rng):
    """The table ENDS in the middle of the page, prose below it."""
    pg = _sheet(doc); t = []
    _head(pg, t, 218)
    y = _cat_table(pg, t, MARGIN + 8, TOP + 34, 7, 30, colw=58.0, step=10.2)
    _flow(pg, t, MARGIN, y + 20, BOT_Y, PROSE_EN, w=PW - 2 * MARGIN)
    return pg, t


def c_kat_footnote_under(doc, rng):
    """A footnote under the table behind a short rule: part of it or not."""
    pg = _sheet(doc); t = []
    _head(pg, t, 219)
    y = _cat_table(pg, t, MARGIN + 8, TOP + 34, 7, 48, colw=58.0, step=10.2)
    _line(pg, MARGIN + 8, y + 14, MARGIN + 120, y + 14, 0.7)
    for k in range(2):
        ln = (f"* Values for grade {k + 6} are given in Table {12 + k}; "
              f"see also note on p. {180 + k * 3}.")
        _put(pg, MARGIN + 8, y + 26 + k * 10, ln, 5.4, sheet_w=PW)
        t.append((MARGIN + 6, y + 26 + k * 10 - 5.4,
                  MARGIN + 8 + _text_w(ln, 5.4) + 2, y + 28 + k * 10,
                  "footnote"))
        _say(t, ln)
    return pg, t


def c_kat_two_stacked(doc, rng):
    """CONTROL: two tables one under the other, each with a caption."""
    pg = _sheet(doc); t = []
    _head(pg, t, 220)
    y = TOP + 34
    for k in range(2):
        w = _put(pg, MARGIN + 8, y, f"Table {21 + k}.  Bore tolerances", 6.6,
                 sheet_w=PW)
        t.append((MARGIN + 6, y - 6.6, MARGIN + 8 + w + 2, y + 3,
                  "paragraph_title"))
        _say(t, f"Table {21 + k}.  Bore tolerances")
        y = _cat_table(pg, t, MARGIN + 8, y + 26, 6, 26, colw=62.0,
                       step=10.2) + 30
    return pg, t


def c_kat_two_side(doc, rng):
    """Two NARROW tables side by side: the known defect, in a catalogue."""
    pg = _sheet(doc); t = []
    _head(pg, t, 221)
    for x in (MARGIN + 8, PW / 2 + 20):
        _cat_table(pg, t, x, TOP + 40, 3, 54, colw=54.0, step=10.2)
    return pg, t


def c_kat_wide_rotated(doc, rng):
    """A wide table on a ROTATED page."""
    pg = _sheet(doc); t = []
    _head(pg, t, 222)
    _cat_table(pg, t, MARGIN + 8, TOP + 40, 8, 56, colw=50.0, step=10.2)
    return pg, t


def c_kat_spread_continue(doc, rng):
    """SPREAD: the table crosses the gutter, one header for both halves."""
    pg = _sheet(doc, wide=True); t = []
    _running_head(pg, t, MARGIN, 2 * PW - MARGIN, TOP - 14, "PART CATALOGUE",
                  "SHAFT FITS", 223)
    _cat_table(pg, t, MARGIN + 8, TOP + 40, 14, 56, colw=62.0, step=10.2)
    return pg, t


def c_kat_sparse_tail(doc, rng):
    """A four-row tail of a table and an empty bottom third of the page.

    A real catalogue ends like this. Does the model glue the running head or
    the folio onto so short a tail?
    """
    pg = _sheet(doc); t = []
    _head(pg, t, 224)
    w = _put(pg, MARGIN + 8, TOP + 30, "Continuation of Table 7", 6.6,
             sheet_w=PW)
    t.append((MARGIN + 6, TOP + 30 - 6.6, MARGIN + 8 + w + 2, TOP + 33,
              "paragraph_title"))
    _say(t, "Continuation of Table 7")
    _cat_table(pg, t, MARGIN + 8, TOP + 58, 7, 4, colw=58.0, step=10.2)
    _flow(pg, t, MARGIN, TOP + 130, BOT_Y, PROSE_EN, w=PW - 2 * MARGIN)
    return pg, t


CASES = {
    "kat_full_table": c_kat_full_table,
    "kat_continued": c_kat_continued,
    "kat_row_numbers": c_kat_row_numbers,
    "kat_mid_start": c_kat_mid_start,
    "kat_mid_end": c_kat_mid_end,
    "kat_footnote_under": c_kat_footnote_under,
    "kat_two_stacked": c_kat_two_stacked,
    "kat_two_side": c_kat_two_side,
    "kat_wide_rotated": c_kat_wide_rotated,
    "kat_spread_continue": c_kat_spread_continue,
    "kat_sparse_tail": c_kat_sparse_tail,
}
SPREADS = {"kat_spread_continue"}
ROTATE = {"kat_wide_rotated": 90}
