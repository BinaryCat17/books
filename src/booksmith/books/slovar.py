"""Словарь: узкие колонки мелким шрифтом — то, чего у справочника нет вовсе.

ГЛАВНЫЙ ВОПРОС ЭТОЙ КНИГИ. Померено, что детектор втягивает в рамку таблицы
всё, что стоит рядом по горизонтали. Померено и обратное: колонки ПРОЗЫ он
разделяет исправно — на 36 страницах справочника 98 пар текстовых рамок стоят
бок о бок. Значит слияние — свойство не соседства вообще, а таблицы.

Словарь ставит этот вопрос ребром: его колонки — проза, но по виду ближе
всего к таблице (выровненные короткие строки, висячий отступ, узкий столбец,
мелкий кегль). Просвет разворачивается от 26 пунктов до 5, и отдельная
страница ставит в просвет ВЕРТИКАЛЬНУЮ ЛИНЕЙКУ: до сих пор единственное, что
заставило детектор разделить две таблицы, была тень переплёта, то есть
физический разрез. Линейка — тот же разрез, но нарисованный.

Пара страниц `slov_index_numbers` / `slov_abbrev_table` сделана нарочно
неразличимой на глаз: одинаковая сетка, в первой это ТЕКСТ (указатель), во
второй ТАБЛИЦА. Цена ошибки ярлыка на неотличимых страницах — то, ради чего
пара и стоит.
"""
from ..synth import (ENTRY_EN, ENTRY_RU, SynthError, _entries, _figure,
                     _grid, _line, _page, _put, _running_head, _say, _table,
                     _text_w)

# Карманный формат: лист уже и ниже справочника, аспект 0.588 против 0.690.
SHEET = (680, 1156)
PT = 0.5
PW, PH = SHEET[0] * PT, SHEET[1] * PT      # 340 x 578 пунктов
MARGIN, TOP, BOT_Y = 20.0, 34.0, 552.0
ABOUT = ("карманный словарь-указатель: узкие колонки, висячий отступ, "
         "колонтитул; ставит вопрос «слияние — свойство таблицы или "
         "соседства?» на колонках ПРОЗЫ")

WORDS_EN = ("Abutment", "Backlash", "Camshaft", "Dowel", "Eccentric",
            "Flywheel", "Gudgeon", "Hardening", "Indexing", "Journal",
            "Keyway", "Lapping", "Mandrel", "Nitriding", "Overhang",
            "Pinion", "Quenching", "Reaming", "Spindle", "Tailstock")
WORDS_RU = ("Вал", "Втулка", "Гайка", "Допуск", "Заготовка", "Износ",
            "Калибр", "Люнет", "Муфта", "Наплавка", "Оправка", "Патрон",
            "Развёртка", "Суппорт", "Фаска", "Хомут", "Цанга", "Шпонка")


def _cols(n, gap):
    """Начала и ширина n колонок при заданном просвете."""
    w = (PW - 2 * MARGIN - (n - 1) * gap) / n
    return [MARGIN + i * (w + gap) for i in range(n)], w


def _sheet(doc):
    return _page(doc, pw=PW, ph=PH)


def _fill_cols(pg, t, n, gap, words, size=5.8, bold=False, y0=None,
               label="text", tpl=ENTRY_EN):
    """Колонки гнёзд. У каждой СВОЙ отрезок словника: настоящая страница
    словаря идёт по алфавиту слева направо, а не повторяет одно и то же
    четырежды."""
    xs, w = _cols(n, gap)
    for k, x in enumerate(xs):
        _entries(pg, t, x, y0 or TOP, BOT_Y, w, PW, words, size=size,
                 bold_head=bold, label=label, tpl=tpl, start=k * 5)
    return xs, w


def c_slov_2col(doc, rng):
    """КОНТРОЛЬ: две колонки, просвет 26 пт. Слияния быть не должно."""
    pg = _sheet(doc); t = []
    _fill_cols(pg, t, 2, 26.0, WORDS_EN)
    return pg, t


def c_slov_3col(doc, rng):
    """Три колонки, просвет 10 пт — с междустрочье."""
    pg = _sheet(doc); t = []
    _fill_cols(pg, t, 3, 10.0, WORDS_EN, size=5.2)
    return pg, t


def c_slov_4col_tight(doc, rng):
    """Предел: четыре колонки, просвет 5 пт, кегль 4.8."""
    pg = _sheet(doc); t = []
    _fill_cols(pg, t, 4, 5.0, WORDS_EN, size=4.8)
    return pg, t


def c_slov_4col_ruled(doc, rng):
    """То же, но в КАЖДЫЙ просвет поставлена вертикальная линейка.

    До сих пор единственное, что заставило детектор разделить две таблицы, —
    тень переплёта, физический разрез. Линейка — тот же разрез, нарисованный.
    """
    pg = _sheet(doc); t = []
    xs, w = _fill_cols(pg, t, 4, 5.0, WORDS_EN, size=4.8)
    for x in xs[1:]:
        _line(pg, x - 2.5, TOP - 6, x - 2.5, BOT_Y, 0.8)
    return pg, t


def c_slov_index_numbers(doc, rng):
    """Указатель: слово и номера страниц через запятую, три колонки.

    ТЕКСТ, а не таблица. Пара к `slov_abbrev_table`, где та же сетка — таблица.
    """
    pg = _sheet(doc); t = []
    xs, w = _cols(3, 10.0)
    # Блок истины — ГРУППА строк под буквой, а не строка. Строка блоком не
    # бывает: детектор такой рамки не отдаёт ни при каком пороге, и «нашлось
    # 0 из 204» читалось бы как слепота модели, будучи нашей же ошибкой
    # гранулярности.
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
    """Таблица сокращений в четыре узких столбца. Пара к указателю выше:
    на глаз то же, в истине — одна `table`."""
    pg = _sheet(doc); t = []
    _put(pg, MARGIN, TOP, "TABLE OF ABBREVIATIONS", 7.0, sheet_w=PW)
    t.append((MARGIN - 2, TOP - 8, MARGIN + _text_w("TABLE OF ABBREVIATIONS", 7.0) + 2,
              TOP + 2, "paragraph_title"))
    _say(t, "TABLE OF ABBREVIATIONS")
    cols = _grid(MARGIN + 4, 4, colw=68.0, gap=6.0)
    _table(pg, t, MARGIN + 4, TOP + 24, cols, 52, size=5.2, colw=68.0, step=9.6)
    return pg, t


def c_slov_parallel(doc, rng):
    """Параллельный текст: статья и перевод, строки выровнены построчно.

    Самый похожий на таблицу вид ТЕКСТА: две колонки, строки на одной высоте.
    """
    pg = _sheet(doc); t = []
    xs, w = _cols(2, 14.0)
    y = TOP
    k = 0
    # Блок истины — АБЗАЦ из пяти построчно выровненных строк, а не строка.
    while y < BOT_Y - 50:
        y0, yy = y, y
        for x, lang in zip(xs, ("en", "ru")):
            yy = y0
            drawn = []
            for j in range(5):
                src = WORDS_EN if lang == "en" else WORDS_RU
                tail = ("the part that carries the load in the assembly"
                        if lang == "en" else
                        "деталь, несущая нагрузку в сборке")
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
    """Табличка форм 3x4 ВНУТРИ узкой колонки, текст вплотную сверху и снизу.

    Вертикальное слияние проверялось только на полосе во всю ширину набора.
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
    """Колонтитул с диапазоном слов, линейка и колонцифра.

    Класс `header` стендом не проверялся ни разу: у справочника есть только
    `number`.
    """
    pg = _sheet(doc); t = []
    _running_head(pg, t, MARGIN, PW - MARGIN, TOP - 12, "ABUTMENT", "CAMSHAFT",
                  417)
    _fill_cols(pg, t, 2, 18.0, WORDS_EN, size=5.6, y0=TOP + 22)
    return pg, t


def c_slov_headword_bold(doc, rng):
    """Гнёзда выделены разрядкой: рвёт ли выделение колонку на гнёзда."""
    pg = _sheet(doc); t = []
    _fill_cols(pg, t, 2, 18.0, WORDS_EN, size=5.6, bold=True)
    return pg, t


def c_slov_cyrillic(doc, rng):
    """КОНТРОЛЬ письменности: то же устройство, кириллица."""
    pg = _sheet(doc); t = []
    _fill_cols(pg, t, 3, 10.0, WORDS_RU, size=5.2, tpl=ENTRY_RU)
    return pg, t


def c_slov_letter_divider(doc, rng):
    """Буквенный разделитель во всю ширину набора между гнёздами."""
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
    """Мелкий рисунок ВНУТРИ узкой колонки, текст обтекает его сверху и снизу."""
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
