"""Атлас конструкций: альбомный лист, крупная графика, мало текста.

Зачем. У справочника рисунок всегда стоит В ПОЛОСЕ НАБОРА среди прозы. В
атласе полоса — сам чертёж, а текста на листе может не быть вовсе, и это
другая задача: детектору не за что зацепиться, кроме самой графики.

Две ловушки книги названы заранее. Первая — ОСНОВНАЯ НАДПИСЬ чертежа: сетка
ячеек с текстом в углу поля, то есть таблица внутри рисунка; вопрос, отдаст
ли модель две рамки или одну. Вторая — ТАБЛИЦА СПЕЦИФИКАЦИИ, лежащая внутри
поля чертежа: таблица и рисунок здесь не соседи, а вложены.

Контрольная страница `atl_plate_only` не несёт ни надписи, ни спецификации:
без неё «нашёл рисунок» на странице со штампом нечем отличить от «обвёл всё
подряд».
"""
from ..synth import (PROSE_EN, _callouts, _caption, _flow, _frame_stamp,
                     _grid, _halftone, _line, _page, _plate, _put, _say,
                     _table, _text_w)

SHEET = (1440, 1012)                 # альбомный: 720 x 506 пунктов
PT = 0.5
PW, PH = SHEET[0] * PT, SHEET[1] * PT
MARGIN, TOP, BOT_Y = 26.0, 34.0, 480.0
ABOUT = ("альбом чертежей: альбомный лист, поле чертежа, основная надпись, "
         "спецификация внутри поля, выносные позиции; проверяет `image` "
         "против вложенной `table`")


def _sheet(doc, wide=False):
    return _page(doc, wide=wide, pw=PW, ph=PH)


def c_atl_plate_only(doc, rng):
    """КОНТРОЛЬ: одно поле чертежа и подпись. Ни надписи, ни спецификации."""
    pg = _sheet(doc); t = []
    _plate(pg, t, MARGIN + 40, TOP + 10, PW - 2 * MARGIN - 80, 380)
    _caption(pg, t, MARGIN + 46, TOP + 408, "Fig. 12  Machine tool bed")
    return pg, t


def c_atl_frame_stamp(doc, rng):
    """Рамка чертежа и ОСНОВНАЯ НАДПИСЬ в углу: таблица внутри рисунка."""
    pg = _sheet(doc); t = []
    _plate(pg, t, MARGIN + 30, TOP + 6, PW - 2 * MARGIN - 60, 360)
    _frame_stamp(pg, t, 10, 10, PW - 10, PH - 10)
    return pg, t


def c_atl_spec_inside(doc, rng):
    """Таблица спецификации ВНУТРИ поля чертежа, справа от вида."""
    pg = _sheet(doc); t = []
    _plate(pg, t, MARGIN, TOP, 400, 380)
    _table(pg, t, MARGIN + 430, TOP + 30,
           _grid(MARGIN + 430, 3, colw=68.0, gap=6.0), 22, size=5.6,
           colw=68.0, step=9.4)
    _frame_stamp(pg, t, 10, 10, PW - 10, PH - 10, no="26.68")
    return pg, t


def c_atl_two_views(doc, rng):
    """Два вида рядом: соседние поля чертежа — сливаются или нет.

    На справочнике два рисунка бок о бок модель разделила. Здесь они больше,
    ближе и одинаковы по устройству.
    """
    pg = _sheet(doc); t = []
    _plate(pg, t, MARGIN + 20, TOP + 10, PW - 2 * MARGIN - 40, 360, views=2)
    _caption(pg, t, MARGIN + 26, TOP + 386, "Fig. 14  Front view")
    _caption(pg, t, PW / 2 + 20, TOP + 386, "Fig. 15  Section A-A")
    return pg, t


def c_atl_callouts(doc, rng):
    """Выносные позиции в кружках вокруг вида — мелкие чернила по всему полю."""
    pg = _sheet(doc); t = []
    _plate(pg, t, MARGIN + 90, TOP, PW - 2 * MARGIN - 180, 380)
    _callouts(pg, t, PW / 2, TOP + 190, 110,
              [(20, 1), (75, 2), (135, 3), (200, 4), (250, 5), (315, 6)], PW)
    _caption(pg, t, MARGIN + 96, TOP + 400, "Fig. 16  Assembly, items 1-6")
    return pg, t


def c_atl_caption_above(doc, rng):
    """Подпись НАД рисунком, а не под ним."""
    pg = _sheet(doc); t = []
    _caption(pg, t, MARGIN + 46, TOP + 10, "Fig. 17  Tailstock, plan")
    _plate(pg, t, MARGIN + 40, TOP + 20, PW - 2 * MARGIN - 80, 380)
    return pg, t


def c_atl_photo_plate(doc, rng):
    """Полутоновая фотография во всю полосу: другая физика, тот же ярлык."""
    pg = _sheet(doc); t = []
    _halftone(pg, t, MARGIN + 60, TOP, PW - 2 * MARGIN - 120, 370,
              "Fig. 18  Milling head, photograph")
    return pg, t


def c_atl_text_and_plate(doc, rng):
    """Полоса текста внизу под чертежом: единственная проза в книге."""
    pg = _sheet(doc); t = []
    _plate(pg, t, MARGIN + 60, TOP, PW - 2 * MARGIN - 120, 300)
    _caption(pg, t, MARGIN + 66, TOP + 318, "Fig. 19  Gearbox, section")
    _flow(pg, t, MARGIN, TOP + 336, BOT_Y, PROSE_EN, w=PW - 2 * MARGIN)
    return pg, t


def c_atl_spread_plate(doc, rng):
    """РАЗВОРОТ: чертёж через корешок."""
    pg = _sheet(doc, wide=True); t = []
    _plate(pg, t, MARGIN + 40, TOP, 2 * PW - 2 * MARGIN - 80, 400)
    _caption(pg, t, MARGIN + 46, TOP + 420,
             "Fig. 20  Machine tool bed, general arrangement")
    return pg, t


def c_atl_rotated_plate(doc, rng):
    """Лист, ПОВЁРНУТЫЙ на 90°, с чертежом и основной надписью."""
    pg = _sheet(doc); t = []
    _plate(pg, t, MARGIN + 40, TOP, PW - 2 * MARGIN - 200, 370)
    _frame_stamp(pg, t, 10, 10, PW - 10, PH - 10, no="26.69")
    return pg, t


def c_atl_sparse(doc, rng):
    """Почти пустой лист: один мелкий вид в углу и подпись.

    Порядок чтения на полосе, где читать почти нечего.
    """
    pg = _sheet(doc); t = []
    _plate(pg, t, MARGIN + 40, TOP + 40, 240, 180)
    _caption(pg, t, MARGIN + 46, TOP + 236, "Fig. 21  Detail of key")
    _put(pg, PW / 2 - 8, PH - 24, "48", 6.4, sheet_w=PW)
    t.append((PW / 2 - 10, PH - 24 - 6.4, PW / 2 - 8 + _text_w("48", 6.4) + 2,
              PH - 22, "number"))
    _say(t, "48")
    return pg, t


CASES = {
    "atl_plate_only": c_atl_plate_only,
    "atl_frame_stamp": c_atl_frame_stamp,
    "atl_spec_inside": c_atl_spec_inside,
    "atl_two_views": c_atl_two_views,
    "atl_callouts": c_atl_callouts,
    "atl_caption_above": c_atl_caption_above,
    "atl_photo_plate": c_atl_photo_plate,
    "atl_text_and_plate": c_atl_text_and_plate,
    "atl_spread_plate": c_atl_spread_plate,
    "atl_rotated_plate": c_atl_rotated_plate,
    "atl_sparse": c_atl_sparse,
}
SPREADS = {"atl_spread_plate"}
ROTATE = {"atl_rotated_plate": 90}
