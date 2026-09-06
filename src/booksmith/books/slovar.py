"""A dictionary: narrow columns in small type -- what the handbook lacks.

THE QUESTION THIS BOOK ASKS. It is measured that the detector pulls into a
table's box whatever stands beside it horizontally. The converse is measured
too: columns of PROSE it separates correctly -- 98 pairs of text boxes stand
side by side over 36 handbook pages. So merging is a property of the table,
not of adjacency as such.

The dictionary puts that to the test: its columns are prose, but they look
more like a table than anything else (aligned short lines, hanging indent, a
narrow column, small type). The gap sweeps from 26 points down to 5, and one
page puts a VERTICAL RULE into the gap. Until now the only thing that made the
detector separate two tables was the gutter shadow -- a physical cut. The rule
is that same cut, drawn.

The pair `slov_index_numbers` / `slov_abbrev_table` is made deliberately
indistinguishable by eye: the same grid, TEXT (an index) in the first and a
TABLE in the second. The price of a label error on indistinguishable pages is
what the pair exists to show.
"""
from ..synth import (ENTRY_EN, ENTRY_RU, SynthError, _entries, _figure,
                     _grid, _line, _page, _put, _running_head, _say, _table,
                     _text_w)

# Pocket format: narrower and shorter than the handbook, aspect 0.588 vs 0.690.
SHEET = (680, 1156)
PT = 0.5
PW, PH = SHEET[0] * PT, SHEET[1] * PT      # 340 x 578 points
MARGIN, TOP, BOT_Y = 20.0, 34.0, 552.0
ABOUT = ("pocket dictionary and index: narrow columns, hanging indent, "
         "running head; asks \"is merging a property of the table or of "
         "adjacency?\" on columns of PROSE")

WORDS_EN = ("Abutment", "Backlash", "Camshaft", "Dowel", "Eccentric",
            "Flywheel", "Gudgeon", "Hardening", "Indexing", "Journal",
            "Keyway", "Lapping", "Mandrel", "Nitriding", "Overhang",
            "Pinion", "Quenching", "Reaming", "Spindle", "Tailstock")
# The Russian half of the parallel-text page is BOOK CONTENT: it is drawn
# onto the sheet, and the sheet is a page of a Russian-English dictionary.
# It lives in a constant whose name ends in `_RU` because that is how
# `booksmith.cyr` tells content from prose -- an inline literal would have
# been counted as untranslated prose, and translating it would have destroyed
# the page it belongs to.
TAIL_RU = "деталь, несущая нагрузку в сборке"
WORDS_RU = ("Вал", "Втулка", "Гайка", "Допуск", "Заготовка", "Износ",
            "Калибр", "Люнет", "Муфта", "Наплавка", "Оправка", "Патрон",
            "Развёртка", "Суппорт", "Фаска", "Хомут", "Цанга", "Шпонка")


def _cols(n, gap):
    """The starts and the width of n columns at the given gap."""
    w = (PW - 2 * MARGIN - (n - 1) * gap) / n
    return [MARGIN + i * (w + gap) for i in range(n)], w


def _sheet(doc):
    return _page(doc, pw=PW, ph=PH)


def _fill_cols(pg, t, n, gap, words, size=5.8, bold=False, y0=None,
               label="text", tpl=ENTRY_EN):
    """Columns of entries, each with ITS OWN slice of the word list: a real
    dictionary page runs alphabetically left to right rather than repeating
    the same thing four times."""
    xs, w = _cols(n, gap)
    for k, x in enumerate(xs):
        _entries(pg, t, x, y0 or TOP, BOT_Y, w, PW, words, size=size,
                 bold_head=bold, label=label, tpl=tpl, start=k * 5)
    return xs, w


def c_slov_2col(doc, rng):
    """CONTROL: two columns, 26 pt gap. There must be no merging."""
    pg = _sheet(doc); t = []
    _fill_cols(pg, t, 2, 26.0, WORDS_EN)
    return pg, t


def c_slov_3col(doc, rng):
    """Three columns, 10 pt gap -- about one line's leading."""
    pg = _sheet(doc); t = []
    _fill_cols(pg, t, 3, 10.0, WORDS_EN, size=5.2)
    return pg, t


def c_slov_4col_tight(doc, rng):
    """The limit: four columns, 5 pt gap, 4.8 pt type."""
    pg = _sheet(doc); t = []
    _fill_cols(pg, t, 4, 5.0, WORDS_EN, size=4.8)
    return pg, t


def c_slov_4col_ruled(doc, rng):
    """The same, with a vertical rule in EVERY gap.

    Until now the only thing that made the detector separate two tables was
    the gutter shadow, a physical cut. The rule is that cut, drawn.
    """
    pg = _sheet(doc); t = []
    xs, w = _fill_cols(pg, t, 4, 5.0, WORDS_EN, size=4.8)
    for x in xs[1:]:
        _line(pg, x - 2.5, TOP - 6, x - 2.5, BOT_Y, 0.8)
    return pg, t


def c_slov_index_numbers(doc, rng):
    """An index: a word and page numbers, comma separated, three columns.

    TEXT, not a table. The pair to `slov_abbrev_table`, where the same grid IS
    a table.
    """
    pg = _sheet(doc); t = []
    xs, w = _cols(3, 10.0)
    # A truth block is the GROUP of lines under a letter, not one line. A
    # single line is never a block: no detector returns such a box at any
    # threshold, and "found 0 of 204" would have read as the model being blind
    # when it was our own granularity mistake.
    for c, x in enumerate(xs):
        y = TOP
        n = c * 7
        while y < BOT_Y - 20:
            letter = "ABCDEFGHIJKL"[(n // 7) % 12]
            lw = _put(pg, x, y, letter, 7.0, sheet_w=PW)
            t.append((x - 1, y - 7.0, x + lw + 1, y + 2, "paragraph_title"))
            _say(t, letter)
            y += 10.0
            y0 = y
            drawn = []
            for _ in range(7):
                if y > BOT_Y - 8:
                    break
                word = WORDS_EN[n % len(WORDS_EN)]
                nums = ", ".join(str(100 + (n * 37 + k * 13) % 400)
                                 for k in range(4))
                ln = f"{word} {nums}"
                while _text_w(ln, 5.4) > w:
                    ln = ln.rsplit(",", 1)[0]
                _put(pg, x, y, ln, 5.4, sheet_w=PW)
                drawn.append(ln)
                y += 7.6
                n += 1
            t.append((x - 1, y0 - 5.4, x + w, y - 7.6 + 1.5, "text"))
            _say(t, " ".join(drawn))
            y += 5.0
    return pg, t


def c_slov_abbrev_table(doc, rng):
    """A table of abbreviations in four narrow columns. The pair to the index
    above: the same by eye, one `table` in the truth."""
    pg = _sheet(doc); t = []
    _put(pg, MARGIN, TOP, "TABLE OF ABBREVIATIONS", 7.0, sheet_w=PW)
    t.append((MARGIN - 2, TOP - 8, MARGIN + _text_w("TABLE OF ABBREVIATIONS", 7.0) + 2,
              TOP + 2, "paragraph_title"))
    _say(t, "TABLE OF ABBREVIATIONS")
    cols = _grid(MARGIN + 4, 4, colw=68.0, gap=6.0)
    _table(pg, t, MARGIN + 4, TOP + 24, cols, 52, size=5.2, colw=68.0, step=9.6)
    return pg, t


def c_slov_parallel(doc, rng):
    """Parallel text: entry and translation, aligned line for line.

    The most table-like kind of TEXT there is: two columns, rows at one height.
    """
    pg = _sheet(doc); t = []
    xs, w = _cols(2, 14.0)
    y = TOP
    k = 0
    # A truth block is the PARAGRAPH of five aligned lines, not one line.
    while y < BOT_Y - 50:
        y0, yy = y, y
        for x, lang in zip(xs, ("en", "ru")):
            yy = y0
            drawn = []
            for j in range(5):
                src = WORDS_EN if lang == "en" else WORDS_RU
                tail = ("the part that carries the load in the assembly"
                        if lang == "en" else TAIL_RU)
                ln = f"{src[(k + j) % len(src)]} — {tail}"
                while _text_w(ln, 5.4) > w:
                    ln = ln[:-2]
                _put(pg, x, yy, ln, 5.4, sheet_w=PW)
                drawn.append(ln)
                yy += 8.2
            t.append((x - 1, y0 - 5.4, x + w, yy - 8.2 + 1.5, "text"))
            _say(t, " ".join(drawn))
        y = yy + 9.0
        k += 5
    return pg, t


def c_slov_grammar_block(doc, rng):
    """A 3x4 grid of forms INSIDE a narrow column, text tight above and below.

    Vertical merging has only ever been tested on a full-measure page.
    """
    pg = _sheet(doc); t = []
    xs, w = _cols(2, 20.0)
    _entries(pg, t, xs[0], TOP, 250, w, PW, WORDS_EN, size=5.4)
    _table(pg, t, xs[0] + 4, 268, _grid(xs[0] + 4, 3, colw=44.0, gap=4.0), 4,
           size=5.2, colw=44.0, step=9.0)
    _entries(pg, t, xs[0], 330, BOT_Y, w, PW, WORDS_EN[5:], size=5.4)
    _entries(pg, t, xs[1], TOP, BOT_Y, w, PW, WORDS_RU, size=5.4, tpl=ENTRY_RU)
    return pg, t


def c_slov_running_head(doc, rng):
    """A running head with a word range, a rule and a folio.

    The class `header` has never been tested by the bench: the handbook has
    only `number`.
    """
    pg = _sheet(doc); t = []
    _running_head(pg, t, MARGIN, PW - MARGIN, TOP - 12, "ABUTMENT", "CAMSHAFT",
                  417)
    _fill_cols(pg, t, 2, 18.0, WORDS_EN, size=5.6, y0=TOP + 22)
    return pg, t


def c_slov_headword_bold(doc, rng):
    """Headwords set in letter-spacing: does emphasis tear the column up?"""
    pg = _sheet(doc); t = []
    _fill_cols(pg, t, 2, 18.0, WORDS_EN, size=5.6, bold=True)
    return pg, t


def c_slov_cyrillic(doc, rng):
    """SCRIPT CONTROL: the same construction, in Cyrillic."""
    pg = _sheet(doc); t = []
    _fill_cols(pg, t, 3, 10.0, WORDS_RU, size=5.2, tpl=ENTRY_RU)
    return pg, t


def c_slov_letter_divider(doc, rng):
    """A full-measure letter divider between the entries."""
    pg = _sheet(doc); t = []
    xs, w = _cols(2, 18.0)
    for x in xs:
        _entries(pg, t, x, TOP, 240, w, PW, WORDS_EN, size=5.6)
    _line(pg, MARGIN, 256, PW - MARGIN, 256, 1.2)
    ww = _put(pg, PW / 2 - 6, 274, "B", 13.0, sheet_w=PW)
    t.append((PW / 2 - 8, 274 - 13, PW / 2 - 6 + ww + 2, 277, "doc_title"))
    _say(t, "B")
    _line(pg, MARGIN, 284, PW - MARGIN, 284, 1.2)
    for x in xs:
        _entries(pg, t, x, 300, BOT_Y, w, PW, WORDS_EN[7:], size=5.6)
    return pg, t


def c_slov_small_cut(doc, rng):
    """A small figure INSIDE a narrow column, text flowing above and below."""
    pg = _sheet(doc); t = []
    xs, w = _cols(2, 18.0)
    _entries(pg, t, xs[0], TOP, 200, w, PW, WORDS_EN, size=5.6)
    _figure(pg, t, xs[0] + 6, 214, w - 12, 96, "Fig. 3  Spindle nose")
    _entries(pg, t, xs[0], 330, BOT_Y, w, PW, WORDS_EN[4:], size=5.6)
    _entries(pg, t, xs[1], TOP, BOT_Y, w, PW, WORDS_RU, size=5.6, tpl=ENTRY_RU)
    return pg, t


CASES = {
    "slov_2col": c_slov_2col,
    "slov_3col": c_slov_3col,
    "slov_4col_tight": c_slov_4col_tight,
    "slov_4col_ruled": c_slov_4col_ruled,
    "slov_index_numbers": c_slov_index_numbers,
    "slov_abbrev_table": c_slov_abbrev_table,
    "slov_parallel": c_slov_parallel,
    "slov_grammar_block": c_slov_grammar_block,
    "slov_running_head": c_slov_running_head,
    "slov_headword_bold": c_slov_headword_bold,
    "slov_cyrillic": c_slov_cyrillic,
    "slov_letter_divider": c_slov_letter_divider,
    "slov_small_cut": c_slov_small_cut,
}
SPREADS: set = set()
ROTATE: dict = {}
