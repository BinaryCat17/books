"""A mathematics course: half the page is display formulas.

WHY THIS BOOK. In the handbook `display_formula` is tested by ONE page, and
six policy labels -- `inline_formula`, `formula_number`, `algorithm`,
`abstract`, `reference`, `reference_content` -- are not tested at all.

Its main trap is the MATRIX. To the eye it is a grid of numbers in brackets,
i.e. a table; in substance it is one formula. The price of the error is named
in advance: as a table, level two parses it into a grid of cells and loses the
meaning; as a formula, it hands it over whole. The determinant is placed
beside a REAL table of the same proportions, so that "called it a table"
cannot be written off as general blindness.

Glyphs are checked BEFORE drawing: a missing glyph is drawn by DejaVu not as
emptiness but as a .notdef box -- ink -- and `_measure` would calmly take that
for a formula. The page would come out full of squares and the numbers healthy.
"""
from ..synth import (PROSE_EN, SynthError, _fill, _flow, _formula, _grid,
                     _line, _matrix, _page, _put, _rect, _refs, _say, _table,
                     _text_w)

SHEET = (936, 1324)
PT = 0.5
PW, PH = SHEET[0] * PT, SHEET[1] * PT       # 468 x 662 points
MARGIN, TOP, BOT_Y = 40.0, 44.0, 620.0
COLW = PW - 2 * MARGIN
ABOUT = ("mathematics course: numbered display formulas, matrices and "
         "determinants, systems in a brace, theorems; sets `display_formula` "
         "against `table`")

FORMULAS = (
    "s = (a + b) / 2c",
    "R = 4 s^2 / (h - k)",
    "y = sum a_i x^i + b",
    "f(x) = integral g(t) dt",
    "sigma = P / F <= [sigma]",
    "delta = (l2 - l1) / l1",
    "M = W * [sigma] * k",
)


def _sheet(doc):
    return _page(doc, pw=PW, ph=PH)


def c_mat_plain_prose(doc, rng):
    """CONTROL: one column of solid prose, not a single formula."""
    pg = _sheet(doc); t = []
    _flow(pg, t, MARGIN, TOP, BOT_Y, PROSE_EN, w=COLW)
    return pg, t


def c_mat_display_numbered(doc, rng):
    """Six display formulas numbered at the RIGHT margin.

    Is the number a separate block or part of the formula? And does the
    formula's box spill out to the margin and swallow it?
    """
    pg = _sheet(doc); t = []
    y = _flow(pg, t, MARGIN, TOP, 150, PROSE_EN, w=COLW)
    for k, f in enumerate(FORMULAS[:6]):
        y = _formula(pg, t, MARGIN + 90, y + 12, f, number=f"({3}.{k + 1})",
                     right=PW - MARGIN, sheet_w=PW)
        y = _flow(pg, t, MARGIN, y + 4, y + 52, PROSE_EN, w=COLW)
    _flow(pg, t, MARGIN, y + 8, BOT_Y, PROSE_EN, w=COLW)
    return pg, t


def c_mat_chain(doc, rng):
    """Seven formulas in a row with a 4-point gap: vertical merging on the
    formula class. On tables the vertical passes correctly -- and here?"""
    pg = _sheet(doc); t = []
    y = _flow(pg, t, MARGIN, TOP, 140, PROSE_EN, w=COLW)
    y += 16
    for f in FORMULAS:
        _formula(pg, t, MARGIN + 70, y, f, sheet_w=PW)
        y += 20
    _flow(pg, t, MARGIN, y + 10, BOT_Y, PROSE_EN, w=COLW)
    return pg, t


def c_mat_matrix(doc, rng):
    """A 5x5 determinant and a 4x6 bracketed matrix -- the label trap."""
    pg = _sheet(doc); t = []
    _flow(pg, t, MARGIN, TOP, 130, PROSE_EN, w=COLW)
    y = _matrix(pg, t, MARGIN + 40, 158, 5, 5, kind="det", sheet_w=PW)
    y = _flow(pg, t, MARGIN, y + 10, y + 70, PROSE_EN, w=COLW)
    y = _matrix(pg, t, MARGIN + 40, y + 24, 4, 6, kind="matrix", sheet_w=PW)
    _flow(pg, t, MARGIN, y + 12, BOT_Y, PROSE_EN, w=COLW)
    return pg, t


def c_mat_matrix_vs_table(doc, rng):
    """THE PAIR: a matrix and a REAL table of the same proportions on one page.

    If the model calls both tables, that is blindness and not a label error,
    and without the pair there is nothing to tell the two apart with.
    """
    pg = _sheet(doc); t = []
    _flow(pg, t, MARGIN, TOP, 120, PROSE_EN, w=COLW)
    _matrix(pg, t, MARGIN + 10, 150, 5, 4, kind="matrix", sheet_w=PW)
    _table(pg, t, MARGIN + 230, 150, _grid(MARGIN + 230, 4, colw=42.0, gap=4.0),
           5, size=6.2, colw=42.0, step=10.5)
    _flow(pg, t, MARGIN, 250, BOT_Y, PROSE_EN, w=COLW)
    return pg, t


def c_mat_system(doc, rng):
    """A system of equations inside a brace."""
    pg = _sheet(doc); t = []
    _flow(pg, t, MARGIN, TOP, 150, PROSE_EN, w=COLW)
    x, y = MARGIN + 70, 190.0
    lines = ("a11 x1 + a12 x2 = b1",
             "a21 x1 + a22 x2 = b2",
             "a31 x1 + a32 x2 = b3")
    for k, ln in enumerate(lines):
        _put(pg, x + 14, y + k * 15, ln, 8.0, font="M", sheet_w=PW)
    # the brace, drawn as strokes
    _line(pg, x + 6, y - 8, x + 6, y + 2 * 15 + 4, 0.8)
    _line(pg, x + 6, y - 8, x + 11, y - 11, 0.7)
    _line(pg, x + 6, y + 2 * 15 + 4, x + 11, y + 2 * 15 + 7, 0.7)
    _line(pg, x, y + 15, x + 6, y + 15, 0.7)
    w = max(_text_w(l, 8.0, "M") for l in lines)
    t.append((x - 2, y - 12, x + 14 + w + 4, y + 2 * 15 + 9, "display_formula"))
    _say(t, " ; ".join(lines))
    _flow(pg, t, MARGIN, y + 60, BOT_Y, PROSE_EN, w=COLW)
    return pg, t


def c_mat_theorem(doc, rng):
    """Theorem and proof, indented: does the indent tear the column apart?"""
    pg = _sheet(doc); t = []
    y = _flow(pg, t, MARGIN, TOP, 130, PROSE_EN, w=COLW)
    for title in ("THEOREM 3.1.", "PROOF."):
        w = _put(pg, MARGIN + 24, y + 18, title, 7.0, sheet_w=PW)
        t.append((MARGIN + 22, y + 18 - 7, MARGIN + 24 + w + 2, y + 20,
                  "paragraph_title"))
        _say(t, title)
        r = _rect(MARGIN + 24, y + 24, PW - MARGIN - 24, y + 110)
        body = _fill(pg, r, PROSE_EN, 6.4)
        t.append((MARGIN + 24, y + 24, PW - MARGIN - 24, y + 110, "text"))
        _say(t, body)
        y += 120
    _flow(pg, t, MARGIN, y + 10, BOT_Y, PROSE_EN, w=COLW)
    return pg, t


def c_mat_numbered_list(doc, rng):
    """An indented numbered list -- a false two-column table."""
    pg = _sheet(doc); t = []
    y = _flow(pg, t, MARGIN, TOP, 140, PROSE_EN, w=COLW)
    y += 14
    for k in range(9):
        _put(pg, MARGIN + 16, y, f"{k + 1}.", 6.6, sheet_w=PW)
        ln = ("The lead screw must be lowered to obtain a correct alignment "
              "with the half nuts of the carriage.")
        while _text_w(ln, 6.6) > COLW - 60:
            ln = ln[:-2]
        _put(pg, MARGIN + 34, y, ln, 6.6, sheet_w=PW)
        t.append((MARGIN + 14, y - 6.6, MARGIN + 34 + _text_w(ln, 6.6) + 2,
                  y + 2, "text"))
        _say(t, f"{k + 1}. {ln}")
        y += 13.0
    _flow(pg, t, MARGIN, y + 12, BOT_Y, PROSE_EN, w=COLW)
    return pg, t


def c_mat_references(doc, rng):
    """References: indents and bracketed numbers -- another false table."""
    pg = _sheet(doc); t = []
    y = _flow(pg, t, MARGIN, TOP, 300, PROSE_EN, w=COLW)
    w = _put(pg, MARGIN, y + 22, "REFERENCES", 8.0, sheet_w=PW)
    t.append((MARGIN - 2, y + 22 - 8, MARGIN + w + 2, y + 25, "paragraph_title"))
    _say(t, "REFERENCES")
    _refs(pg, t, MARGIN, y + 40, BOT_Y, COLW, PW)
    return pg, t


def c_mat_inline(doc, rng):
    """Inline formulas INSIDE paragraphs: do they tear the paragraph up?"""
    pg = _sheet(doc); t = []
    y = TOP
    while y < BOT_Y - 40:
        r = _rect(MARGIN, y, PW - MARGIN, y + 74)
        body = _fill(pg, r, PROSE_EN, 6.6)
        t.append((MARGIN, y, PW - MARGIN, y + 74, "text"))
        _say(t, body)
        # an inline formula drawn over a line of the paragraph
        _put(pg, MARGIN + 120, y + 30, "(a + b)/2c", 6.6, font="M", sheet_w=PW)
        # The inline formula is drawn OVER the paragraph and has no box of
        # its own -- that is the case. So its characters belong to this same
        # block, and without `add=True` they would be drawn but not declared:
        # a comparison against the text layer would report a discrepancy where
        # the bench is behaving exactly as designed.
        _say(t, "(a + b)/2c", add=True)
        y += 84
    return pg, t


def c_mat_tall_fraction(doc, rng):
    """Tall fractions: the formula box is three times the line height."""
    pg = _sheet(doc); t = []
    y = _flow(pg, t, MARGIN, TOP, 160, PROSE_EN, w=COLW)
    y += 20
    for k in range(4):
        x = MARGIN + 100
        top = f"a{k + 1} x^2 + b{k + 1} x + c{k + 1}"
        bot = f"d{k + 1} x + e{k + 1}"
        _put(pg, x, y, top, 7.6, font="M", sheet_w=PW)
        wt = _text_w(top, 7.6, "M")
        _line(pg, x - 2, y + 4, x + wt + 2, y + 4, 0.8)
        _put(pg, x + (wt - _text_w(bot, 7.6, "M")) / 2, y + 16, bot, 7.6,
             font="M", sheet_w=PW)
        t.append((x - 6, y - 9, x + wt + 6, y + 20, "display_formula"))
        _say(t, f"{top} / {bot}")
        y += 40
    _flow(pg, t, MARGIN, y + 8, BOT_Y, PROSE_EN, w=COLW)
    return pg, t


def c_mat_greek(doc, rng):
    """Greek and mathematical signs: the control for "the script does not
    change the label". Every glyph is checked against the font BEFORE drawing."""
    pg = _sheet(doc); t = []
    y = _flow(pg, t, MARGIN, TOP, 150, PROSE_EN, w=COLW)
    y += 16
    for k, f in enumerate(("sigma = P / F ≤ [σ]", "α + β = γ ± δ",
                           "∑ a_i x^i → ∞", "√(x² + y²) ≥ 0",
                           "∫ f(t) dt = F(b) − F(a)")):
        _formula(pg, t, MARGIN + 60, y, f, size=8.0, sheet_w=PW)
        y += 22
    _flow(pg, t, MARGIN, y + 10, BOT_Y, PROSE_EN, w=COLW)
    return pg, t


CASES = {
    "mat_plain_prose": c_mat_plain_prose,
    "mat_display_numbered": c_mat_display_numbered,
    "mat_chain": c_mat_chain,
    "mat_matrix": c_mat_matrix,
    "mat_matrix_vs_table": c_mat_matrix_vs_table,
    "mat_system": c_mat_system,
    "mat_theorem": c_mat_theorem,
    "mat_numbered_list": c_mat_numbered_list,
    "mat_references": c_mat_references,
    "mat_inline": c_mat_inline,
    "mat_tall_fraction": c_mat_tall_fraction,
    "mat_greek": c_mat_greek,
}
SPREADS: set = set()
ROTATE: dict = {}
