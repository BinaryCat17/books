"""Сборник статей: смешанная вёрстка, ради которой и нужен второй уровень.

Зачем. Справочник однороден: проза, таблица, рисунок. В журнале на одной
полосе стоят заголовок статьи, аннотация втяжкой, врезка в рамке, фотография
с подписью сбоку, сноски под линейкой и колонцифра — и все они соседи.

Две ловушки. ВРЕЗКА В РАМКЕ на глаз — таблица в одну ячейку; в истине это
текст. ПОДПИСЬ СБОКУ от рисунка — не под ним, как везде в стенде: попадёт ли
она внутрь рамки рисунка.

Контроль — `zh_two_col_plain`: обычная двухколонная полоса без единой
особенности. Без неё «нашлось мало» на пёстрой полосе нечем отличить от
общей неудачи книги.
"""
from ..synth import (PROSE_EN, _box_insert, _caption, _chart, _fill, _figure,
                     _flow, _grid, _halftone, _line, _page, _put, _rect,
                     _refs, _running_head, _table, _text_w)

SHEET = (1080, 1520)
PT = 0.5
PW, PH = SHEET[0] * PT, SHEET[1] * PT       # 540 x 760 пунктов
MARGIN, TOP, BOT_Y = 38.0, 46.0, 720.0
COLW = (PW - 2 * MARGIN - 18.0) / 2
GUT = 18.0
COL_X = (MARGIN, MARGIN + COLW + GUT)
ABOUT = ("сборник статей: заголовок и авторы, аннотация, врезка в рамке, "
         "обтекание, подпись сбоку от рисунка, сноски, список литературы")


def _sheet(doc):
    return _page(doc, pw=PW, ph=PH)


def _colon(pg, t, page_no):
    w = _put(pg, PW / 2 - 6, PH - 26, str(page_no), 6.2, sheet_w=PW)
    t.append((PW / 2 - 8, PH - 26 - 6.2, PW / 2 - 6 + w + 2, PH - 24, "number"))


def c_zh_two_col_plain(doc, rng):
    """КОНТРОЛЬ: две колонки прозы, ничего больше."""
    pg = _sheet(doc); t = []
    for x in COL_X:
        _flow(pg, t, x, TOP, BOT_Y, PROSE_EN, w=COLW)
    _colon(pg, t, 61)
    return pg, t


def c_zh_article_head(doc, rng):
    """Заголовок статьи, авторы, аннотация втяжкой, потом две колонки."""
    pg = _sheet(doc); t = []
    title = "ALIGNMENT OF THE LEAD SCREW IN HEAVY LATHES"
    w = _put(pg, MARGIN + 10, TOP + 14, title, 11.0, sheet_w=PW)
    t.append((MARGIN + 8, TOP + 2, MARGIN + 10 + w + 2, TOP + 18, "doc_title"))
    au = "A. B. Ivanov and C. D. Petrov"
    wa = _put(pg, MARGIN + 10, TOP + 32, au, 7.0, sheet_w=PW)
    t.append((MARGIN + 8, TOP + 24, MARGIN + 10 + wa + 2, TOP + 35, "text"))
    r = _rect(MARGIN + 40, TOP + 46, PW - MARGIN - 40, TOP + 110)
    _fill(pg, r, PROSE_EN, 6.0)
    t.append((MARGIN + 40, TOP + 46, PW - MARGIN - 40, TOP + 110, "abstract"))
    for x in COL_X:
        _flow(pg, t, x, TOP + 128, BOT_Y, PROSE_EN, w=COLW)
    _colon(pg, t, 62)
    return pg, t


def c_zh_box_insert(doc, rng):
    """Врезка в рамке посреди колонки: на глаз таблица в одну ячейку."""
    pg = _sheet(doc); t = []
    _flow(pg, t, COL_X[0], TOP, 260, PROSE_EN, w=COLW)
    _box_insert(pg, t, COL_X[0], 274, COLW, 150, PROSE_EN)
    _flow(pg, t, COL_X[0], 440, BOT_Y, PROSE_EN, w=COLW)
    _flow(pg, t, COL_X[1], TOP, BOT_Y, PROSE_EN, w=COLW)
    _colon(pg, t, 63)
    return pg, t


def c_zh_side_caption(doc, rng):
    """Подпись СБОКУ от рисунка, а не под ним."""
    pg = _sheet(doc); t = []
    _flow(pg, t, COL_X[0], TOP, 200, PROSE_EN, w=COLW)
    _figure(pg, t, COL_X[0], 216, COLW, 170, "Fig. 4  Jig")
    # подпись второй строкой — справа от рисунка, в соседней колонке
    _caption(pg, t, COL_X[1], 300, "Fig. 5  The same, in section")
    _flow(pg, t, COL_X[1], TOP, 280, PROSE_EN, w=COLW)
    _flow(pg, t, COL_X[1], 316, BOT_Y, PROSE_EN, w=COLW)
    _flow(pg, t, COL_X[0], 410, BOT_Y, PROSE_EN, w=COLW)
    _colon(pg, t, 64)
    return pg, t


def c_zh_photo_and_table(doc, rng):
    """Фотография и таблица на одной полосе, рядом по вертикали."""
    pg = _sheet(doc); t = []
    _flow(pg, t, COL_X[0], TOP, 190, PROSE_EN, w=COLW)
    _halftone(pg, t, COL_X[0], 206, COLW, 160, "Fig. 6  Bed casting")
    _table(pg, t, COL_X[0] + 4, 400, _grid(COL_X[0] + 4, 3, colw=68.0, gap=6.0),
           22, size=5.8, colw=68.0, step=9.6)
    _flow(pg, t, COL_X[1], TOP, BOT_Y, PROSE_EN, w=COLW)
    _colon(pg, t, 65)
    return pg, t


def c_zh_wrap_figure(doc, rng):
    """Рисунок в теле колонки, текст обтекает его сверху и снизу."""
    pg = _sheet(doc); t = []
    _flow(pg, t, COL_X[0], TOP, 240, PROSE_EN, w=COLW)
    _chart(pg, t, COL_X[0] + 26, 262, COLW - 40, 140, "Fig. 7  Hardness")
    _flow(pg, t, COL_X[0], 440, BOT_Y, PROSE_EN, w=COLW)
    _flow(pg, t, COL_X[1], TOP, BOT_Y, PROSE_EN, w=COLW)
    _colon(pg, t, 66)
    return pg, t


def c_zh_footnotes(doc, rng):
    """Сноски под короткой линейкой в подвале обеих колонок."""
    pg = _sheet(doc); t = []
    for x in COL_X:
        _flow(pg, t, x, TOP, 590, PROSE_EN, w=COLW)
        _line(pg, x, 604, x + 90, 604, 0.7)
        for k in range(3):
            ln = (f"{k + 1} Trans. A.S.M.E., vol. {60 + k}, p. {110 + k * 9}, "
                  f"1953.")
            _put(pg, x, 618 + k * 10, ln, 5.4, sheet_w=PW)
            t.append((x - 1, 618 + k * 10 - 5.4, x + _text_w(ln, 5.4) + 1,
                      620 + k * 10, "footnote"))
    _colon(pg, t, 67)
    return pg, t


def c_zh_references(doc, rng):
    """Список литературы в две колонки: втяжка и номера в скобках."""
    pg = _sheet(doc); t = []
    w = _put(pg, MARGIN + 10, TOP + 12, "REFERENCES", 9.0, sheet_w=PW)
    t.append((MARGIN + 8, TOP + 2, MARGIN + 10 + w + 2, TOP + 15,
              "paragraph_title"))
    for k, x in enumerate(COL_X):
        _refs(pg, t, x, TOP + 34, BOT_Y, COLW, PW, start=1 + k * 20)
    _colon(pg, t, 68)
    return pg, t


def c_zh_pull_quote(doc, rng):
    """Выделенная цитата крупным кеглем между двумя линейками."""
    pg = _sheet(doc); t = []
    _flow(pg, t, COL_X[0], TOP, 250, PROSE_EN, w=COLW)
    _line(pg, COL_X[0], 268, COL_X[0] + COLW, 268, 1.1)
    r = _rect(COL_X[0], 278, COL_X[0] + COLW, 350)
    _fill(pg, r, "A simple indicating jig is then made up and the carriage "
                 "is placed at the mid-point on the bed ways. ", 8.4)
    t.append((COL_X[0], 278, COL_X[0] + COLW, 350, "aside_text"))
    _line(pg, COL_X[0], 360, COL_X[0] + COLW, 360, 1.1)
    _flow(pg, t, COL_X[0], 374, BOT_Y, PROSE_EN, w=COLW)
    _flow(pg, t, COL_X[1], TOP, BOT_Y, PROSE_EN, w=COLW)
    _colon(pg, t, 69)
    return pg, t


def c_zh_mixed(doc, rng):
    """Всё сразу: колонтитул, врезка, рисунок с подписью, таблица, сноска."""
    pg = _sheet(doc); t = []
    _running_head(pg, t, MARGIN, PW - MARGIN, TOP - 16, "MACHINE TOOLS",
                  "SEC. 26", 70)
    _flow(pg, t, COL_X[0], TOP + 20, 200, PROSE_EN, w=COLW)
    _box_insert(pg, t, COL_X[0], 214, COLW, 110, PROSE_EN, title="NOTE")
    _figure(pg, t, COL_X[0], 344, COLW, 150, "Fig. 8  Half nuts")
    _flow(pg, t, COL_X[0], 520, 600, PROSE_EN, w=COLW)
    _flow(pg, t, COL_X[1], TOP + 20, 300, PROSE_EN, w=COLW)
    _table(pg, t, COL_X[1] + 4, 320, _grid(COL_X[1] + 4, 3, colw=68.0, gap=6.0),
           18, size=5.8, colw=68.0, step=9.6)
    _flow(pg, t, COL_X[1], 510, 600, PROSE_EN, w=COLW)
    for x in COL_X:
        _line(pg, x, 614, x + 90, 614, 0.7)
        ln = "1 See Table 21 for the corresponding grades."
        _put(pg, x, 628, ln, 5.4, sheet_w=PW)
        t.append((x - 1, 628 - 5.4, x + _text_w(ln, 5.4) + 1, 630, "footnote"))
    return pg, t


CASES = {
    "zh_two_col_plain": c_zh_two_col_plain,
    "zh_article_head": c_zh_article_head,
    "zh_box_insert": c_zh_box_insert,
    "zh_side_caption": c_zh_side_caption,
    "zh_photo_and_table": c_zh_photo_and_table,
    "zh_wrap_figure": c_zh_wrap_figure,
    "zh_footnotes": c_zh_footnotes,
    "zh_references": c_zh_references,
    "zh_pull_quote": c_zh_pull_quote,
    "zh_mixed": c_zh_mixed,
}
SPREADS: set = set()
ROTATE: dict = {}
