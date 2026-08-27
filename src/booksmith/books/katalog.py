"""Каталог деталей: полоса, на которой кроме таблицы нет ничего.

Зачем. У справочника таблица всегда окружена прозой, и «нашлась» она во
многом потому, что вокруг был текст, от которого её отличают. В каталоге
полоса — сама таблица: сверху колонтитул, снизу колонцифра, между ними сорок
строк цифр. Гипотеза: без окружения детектор либо обводит всю полосу, либо
рвёт таблицу на куски.

Вторая гипотеза книги — ПРОДОЛЖЕНИЕ. Настоящий каталог ведёт одну таблицу
через десяток страниц: шапка повторяется, слева стоит «Продолжение табл. 7».
Проверяется, отличит ли модель повторную шапку от шапки колонтитула и не
приклеит ли строку продолжения к таблице.

Контроль — `kat_two_stacked`: две таблицы одна под другой. На справочнике
такая пара проходит верно, значит на ней видно, что беда именно в
безокружении, а не в самой книге.
"""
from ..synth import (PROSE_EN, _flow, _grid, _line, _page, _put,
                     _running_head, _table, _text_w)

SHEET = (1012, 1466)
PT = 0.5
PW, PH = SHEET[0] * PT, SHEET[1] * PT
MARGIN, TOP, BOT_Y = 30.0, 46.0, 700.0
ABOUT = ("каталог деталей: полоса без прозы, длинные таблицы через много "
         "страниц, повторная шапка, «Продолжение табл.», сноска под таблицей")


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
        for r in range(rows):
            _put(pg, x - 20, y + 10 + r * step, f"{r + 1}", size, sheet_w=PW)
    return y1


def c_kat_full_table(doc, rng):
    """Полоса — одна таблица во всю высоту. Ни строки прозы."""
    pg = _sheet(doc); t = []
    _head(pg, t, 214)
    _cat_table(pg, t, MARGIN + 8, TOP + 34, 7, 62, colw=58.0, step=10.2)
    return pg, t


def c_kat_continued(doc, rng):
    """«Продолжение табл. 7» и повторная шапка."""
    pg = _sheet(doc); t = []
    _head(pg, t, 215)
    w = _put(pg, MARGIN + 8, TOP + 30, "Continuation of Table 7", 6.6,
             sheet_w=PW)
    t.append((MARGIN + 6, TOP + 30 - 6.6, MARGIN + 8 + w + 2, TOP + 33,
              "paragraph_title"))
    _cat_table(pg, t, MARGIN + 8, TOP + 58, 7, 58, colw=58.0, step=10.2)
    return pg, t


def c_kat_row_numbers(doc, rng):
    """Слева столбец номеров строк: отдельная рамка или часть таблицы."""
    pg = _sheet(doc); t = []
    _head(pg, t, 216)
    _cat_table(pg, t, MARGIN + 30, TOP + 34, 6, 60, colw=62.0, step=10.4,
               numbered=True)
    return pg, t


def c_kat_mid_start(doc, rng):
    """Таблица начинается В СЕРЕДИНЕ полосы, сверху — конец прозы."""
    pg = _sheet(doc); t = []
    _head(pg, t, 217)
    _flow(pg, t, MARGIN, TOP + 30, 300, PROSE_EN, w=PW - 2 * MARGIN)
    _cat_table(pg, t, MARGIN + 8, 330, 7, 36, colw=58.0, step=10.2)
    return pg, t


def c_kat_mid_end(doc, rng):
    """Таблица КОНЧАЕТСЯ в середине полосы, ниже — проза."""
    pg = _sheet(doc); t = []
    _head(pg, t, 218)
    y = _cat_table(pg, t, MARGIN + 8, TOP + 34, 7, 30, colw=58.0, step=10.2)
    _flow(pg, t, MARGIN, y + 20, BOT_Y, PROSE_EN, w=PW - 2 * MARGIN)
    return pg, t


def c_kat_footnote_under(doc, rng):
    """Сноска под таблицей за короткой линейкой: часть таблицы или нет."""
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
    return pg, t


def c_kat_two_stacked(doc, rng):
    """КОНТРОЛЬ: две таблицы одна под другой с подписями."""
    pg = _sheet(doc); t = []
    _head(pg, t, 220)
    y = TOP + 34
    for k in range(2):
        w = _put(pg, MARGIN + 8, y, f"Table {21 + k}.  Bore tolerances", 6.6,
                 sheet_w=PW)
        t.append((MARGIN + 6, y - 6.6, MARGIN + 8 + w + 2, y + 3,
                  "paragraph_title"))
        y = _cat_table(pg, t, MARGIN + 8, y + 26, 6, 26, colw=62.0,
                       step=10.2) + 30
    return pg, t


def c_kat_two_side(doc, rng):
    """Две УЗКИЕ таблицы бок о бок: тот самый дефект, но в каталоге."""
    pg = _sheet(doc); t = []
    _head(pg, t, 221)
    for x in (MARGIN + 8, PW / 2 + 20):
        _cat_table(pg, t, x, TOP + 40, 3, 54, colw=54.0, step=10.2)
    return pg, t


def c_kat_wide_rotated(doc, rng):
    """Широкая таблица на ПОВЁРНУТОЙ полосе."""
    pg = _sheet(doc); t = []
    _head(pg, t, 222)
    _cat_table(pg, t, MARGIN + 8, TOP + 40, 8, 56, colw=50.0, step=10.2)
    return pg, t


def c_kat_spread_continue(doc, rng):
    """РАЗВОРОТ: таблица идёт через корешок, шапка одна на обе половины."""
    pg = _sheet(doc, wide=True); t = []
    _running_head(pg, t, MARGIN, 2 * PW - MARGIN, TOP - 14, "PART CATALOGUE",
                  "SHAFT FITS", 223)
    _cat_table(pg, t, MARGIN + 8, TOP + 40, 14, 56, colw=62.0, step=10.2)
    return pg, t


def c_kat_sparse_tail(doc, rng):
    """Хвост таблицы в четыре строки и пустая нижняя треть полосы.

    Настоящий каталог так и кончается. Проверяет, не приклеит ли модель к
    короткому хвосту колонтитул или колонцифру.
    """
    pg = _sheet(doc); t = []
    _head(pg, t, 224)
    w = _put(pg, MARGIN + 8, TOP + 30, "Continuation of Table 7", 6.6,
             sheet_w=PW)
    t.append((MARGIN + 6, TOP + 30 - 6.6, MARGIN + 8 + w + 2, TOP + 33,
              "paragraph_title"))
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
