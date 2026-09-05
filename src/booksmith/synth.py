"""Синтетический стенд: страницы в стиле старых справочников с точной истиной.

Зачем. Метрику контуров не проверить на настоящих сканах — истины к ним нет,
а брать её у другой модели этот проект уже пробовал и удалил всё, что на этом
стояло. Здесь истина задана ПОСТРОЕНИЕМ: мы сами нарисовали рамку и знаем её
до пикселя.

ГЛАВНЫЙ УРОК ЭТОГО ФАЙЛА, ОПЛАЧЕННЫЙ ДВУМЯ ЛОЖНЫМИ ВЫВОДАМИ.

`insert_textbox` при непомещающемся тексте **не рисует ничего** и молча
возвращает отрицательное число. Две мои первые редакции стенда выдавали
страницы, где на месте прозы была пустая бумага, — и по ним был сделан вывод
«детектор синтетику не видит, стенд построить нельзя». Детектор видел ровно
то, что было: ничего. Поэтому здесь каждый вызов проверяется, а `_fill`
наполняет рамку до отказа.

СТАРЕНИЕ — НЕ УКРАШЕНИЕ, ОНО МЕНЯЕТ ОТВЕТ МОДЕЛИ. Замер на одной странице:
на чистой рамки `table` НЕТ ВОВСЕ, на состаренной она появляется (0.583) — и
появляется вместе с конкурирующей `text` 0.567 на том же прямоугольнике, то
есть стенд воспроизводит подпись дефекта, диагностированного на настоящей
книге. Чистая страница мерила бы не ту задачу.

ИСТИНА ЗНАКОВ, А НЕ ТОЛЬКО РАМОК. Стенд рисует текст сам и знает его
побуквенно — и до сих пор его выбрасывал: `content` был `None` у всех блоков
всех шести книг. Теперь у блока разряда «текст»/«служебное» заполнено
`content` (93 страницы, 1211 блоков, 393 847 знаков, 73 863 слова), а у
таблицы — строки, столбцы и текст каждой ячейки (52 таблицы, 7743 ячейки) в
`meta["истина артефактов"]` по номеру блока. Это единственное место проекта,
где текст известен не со слов другой модели: прежние числа качества чтения
аннулированы ровно за то, что мерились против вывода Mistral OCR.

У АРТЕФАКТА `content` ОСТАЁТСЯ null, И ЭТО ЗНАЧЕНИЕ. Рисунок, график,
фотография, печать и выключная формула в VLM текстом не уезжают НИ В ОДНОМ
режиме подачи (`doc/feed.py`: `crop` шлёт картинку, `masked_page` замазывает),
их знаки — ответ ВТОРОГО уровня, и эталон к ним лежит сбоку, а не в теле
блока.

ЧЕГО СТЕНД НЕ ДАЁТ, И ЭТО НАДО ЗНАТЬ. Он не воспроизводит высокую печать
пятидесятых по пожелтевшей бумаге — ту, на которой читается `Laths` вместо
`Lathes`. Знаки на нём чистые и наши, поэтому мерить им можно ВЕРНОСТЬ
СБОРКИ (что доехало, куда встало, не потерялась ли ячейка), но не стойкость
чтения к типографскому браку. Для второго нужен золотой стенд, размеченный
руками по настоящим страницам.
"""
import hashlib
import json
import os

from .run import knobs

W, H = 1012, 1466                 # как страница bench при 144 dpi
SHEET = (W, H)
DPI = 144.0
PT = 72.0 / DPI                   # пиксель -> пункт
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"
FONT_MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"

ABOUT = ("английский технический справочник пятидесятых: плотная "
         "двухколонная вёрстка, таблицы без линеек, чертежи, развороты "
         "и повороты")

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
    """Страница нарисована не так, как задумано. Роняем, а не выдаём пустую."""


# ---------------------------------------------------------- истина ЗНАКОВ
# Стенд сам рисует текст и знает его побуквенно — и до сих пор выбрасывал:
# `content` был `None` у всех 4984 блоков всех шести книг. Синтетика при этом
# ЕДИНСТВЕННОЕ место проекта, где текст известен не со слов другой модели;
# прежние числа качества чтения аннулированы ровно за то, что мерились против
# вывода Mistral OCR.
#
# ПОЧЕМУ ОТДЕЛЬНЫЙ СЛОВАРЬ, А НЕ ШЕСТОЙ ЭЛЕМЕНТ КОРТЕЖА. `truth.append((...))`
# стоит в стенде 62 раза (37 в `synth.py`, 25 в `books/*.py`), а мест, где
# пятёрку разбирают и пересобирают, — пять, и они РАЗНЫЕ ПО ПОВЕДЕНИЮ:
#   молча теряют шестой  — `_measure` (собирает новую пятёрку `out.append`),
#                          поворот `(*_rot90_box(b[:4]), b[4])` и перекос
#                          `(*_clip_box(_xform_box(b[:4]), …), b[4])`;
#   упали бы на распаковке — `for x0, y0, x1, y1, lab in boxes` в `_measure`
#                          и перевод пунктов в пиксели в `build`.
# То есть в трёх местах из пяти истина знаков исчезла бы БЕЗ ЕДИНОГО СЛОВА —
# ровно тем способом, которым этот файл уже четырежды соврал числами,
# выглядевшими здоровыми. Ключ — НОМЕР блока, тот же `block_id`, что в
# `models/base.py`: «всё наблюдённое живёт сбоку и связано с блоком по его
# номеру».
#
# Словарь заполняется во время отрисовки страницы и снимается сразу после неё
# (`build` зовёт `_said_reset()` перед каждым случаем). Порядок в `truth`
# сохраняют все четыре преобразования, поэтому номер блока = его место в
# списке истины.
_SAID: dict[int, dict] = {}


def _said_reset() -> None:
    _SAID.clear()


def _said_take() -> dict[int, dict]:
    out = dict(_SAID)
    _SAID.clear()
    return out


def _say(truth, text=None, *, cells=None, spans=None, add=False):
    """Записать истину знаков ПОСЛЕДНЕМУ добавленному блоку истины.

    Зовётся вплотную за `truth.append((...))` — тогда номер блока это
    `len(truth) - 1`, и связь не зависит ни от чего больше. Разрыв этой
    вплотности и есть единственный способ соврать здесь, поэтому повторная
    запись в тот же номер без `add=True` падает: молча затёртая истина знаков
    неотличима от её отсутствия.
    """
    if not truth:
        raise SynthError("_say позван раньше, чем добавлена рамка истины")
    i = len(truth) - 1
    rec = _SAID.get(i)
    if rec is not None and not add:
        raise SynthError(
            f"истина знаков блока {i} ({truth[i][4]}) переписывается второй "
            f"раз: было {rec!r}, стало {text!r}. Либо `_say` отстал от "
            f"`append` на блок, либо надо add=True")
    if rec is None:
        rec = {}
        _SAID[i] = rec
    if text is not None:
        t = " ".join(str(text).split())
        rec["текст"] = (rec["текст"] + " " + t).strip() if add and "текст" in rec else t
    if cells is not None:
        rec["строк"] = len(cells)
        rec["столбцов"] = max((len(r) for r in cells), default=0)
        rec["ячейки"] = [[" ".join(str(c).split()) for c in row] for row in cells]
    if spans is not None:
        rec["объединения"] = spans
    return rec


def _fill(pg, rect, text, size, font="F"):
    """Наполнить рамку прозой ДО ОТКАЗА и вернуть НАРИСОВАННОЕ.

    Проверка кода возврата здесь не педантизм: без неё рамка остаётся пустой
    молча, и стенд меряет чистую бумагу, считая, что меряет прозу.

    Возвращается ТЕЛО, а не остаток высоты: остаток не читал никто (проверено
    по всем десяти вызовам), а тело — единственный способ узнать, что именно
    легло в рамку, и записать это истиной знаков.

    ЧТО ЗДЕСЬ ЗНАТЬ ПРО ТЕКСТОВЫЙ СЛОЙ. Заходов рисующих БОЛЬШЕ ОДНОГО: при
    `rc > size*1.4` тело удлиняется и `insert_textbox` зовётся снова, поверх
    уже нарисованного. Замер на одной рамке 210x80 пт: два рисующих захода,
    108 слов в теле и 175 слов в текстовом слое PDF. Совпадающая часть ложится
    знак в знак (разбивка строк у продолженного текста та же), расходится
    только последняя строка каждого промежуточного захода — её выключка
    меняется, когда ниже появляется ещё строка. Для растра это смазанная
    строка, для текстового слоя — призраки. Поэтому сверка истины с
    `page.get_text()` считает призраков ОТДЕЛЬНЫМ числом и не прячет их в
    расхождение.
    """
    import pymupdf
    body = text
    for _ in range(40):
        rc = pg.insert_textbox(rect, body, fontname=font, fontsize=size,
                               lineheight=1.15, align=pymupdf.TEXT_ALIGN_JUSTIFY)
        if rc < 0:
            body = body[:int(len(body) * 0.9)]
            if len(body) < 20:
                raise SynthError(f"в рамку {rect} не влезает даже 20 знаков")
            continue
        if rc > size * 1.4 and len(body) < len(text) * 12:
            body = body + text
            continue
        return body
    raise SynthError(f"не сошлось наполнение рамки {rect}")


def _columns(pg, truth, x, y, width, heights, prose, size=6.6):
    for n in heights:
        r = _rect(x, y, x + width, y + n)
        body = _fill(pg, r, prose, size)
        truth.append((x, y, x + width, y + n, "text"))
        _say(truth, body)
        y += n + 7
    return y


def _rect(x0, y0, x1, y1):
    import pymupdf
    return pymupdf.Rect(x0, y0, x1, y1)


def _table(pg, truth, x, y, cols, rows, size=6.4, label="table",
           ruled=False, colw=62.0, step=9.0):
    """Таблица нужного размера. `ruled` — с линейками или без.

    Обе разновидности нужны: в наших книгах таблицы держатся выравниванием
    пробелов, и это самый трудный для детектора вид, — но линованные тоже
    встречаются, и разница между ними обязана быть видна числом, а не
    предполагаться.
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
    # Шапка ПЕРВОЙ строкой сетки: в HTML она станет `th`, и без неё второй
    # уровень нечем поймать на потере шапки — самой частой порче таблицы.
    _say(truth, cells=grid)
    return y1 + 6


def _grid(x, n, colw=62.0, gap=8.0):
    """Заголовки n столбцов, начиная с x."""
    return [(f"Col {i + 1}", x + i * (colw + gap)) for i in range(n)]


def _chart(pg, truth, x, y, w, h, caption="Fig. 9  Hardness vs carbon"):
    """График: оси и кривая. Отдельный класс `chart` у модели есть."""
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
    # Числа на оси нарисованы ВНУТРИ рамки графика и своей рамки не имеют:
    # график уезжает во второй уровень картинкой целиком (`doc/feed.py`:
    # артефакт не уходит в VLM текстом ни в режиме `crop`, ни в
    # `masked_page`), и знаки на нём — его собственное содержимое, а не текст
    # страницы. Поэтому `content` у него остаётся null, и это ЗНАЧЕНИЕ, а не
    # пропуск: истина знаков графика — задача второго уровня.
    truth.append((x - 14, y - 4, x + w + 4, y + h + 6, "chart"))
    _caption(pg, truth, x + 10, y + h + 18, caption)
    return y + h + 24


def _figure(pg, truth, x, y, w, h, caption="Fig. 26.67  General arrangement"):
    """Штриховой чертёж: контур, окружности, оси, выносные размеры.

    НЕ параллельная штриховка во весь прямоугольник. Первая редакция рисовала
    именно её, и на большом чертеже выходила линованная форма — сорок семь
    ровных линий во всю ширину. Детектор честно не называл это `image`, а я
    записал его отказ в дефекты модели. Чертёж обязан выглядеть чертежом,
    иначе стенд меряет не то, что назвал.
    """
    import math
    import pymupdf
    R = pymupdf.Rect(x, y, x + w, y + h)
    pg.draw_rect(R, color=(0, 0, 0), width=0.7)
    cx, cy = x + w * 0.38, y + h * 0.5
    r = min(w, h) * 0.22
    for k in (1.0, 0.62, 0.28):
        pg.draw_circle(pymupdf.Point(cx, cy), r * k, color=(0, 0, 0), width=0.6)
    # осевые линии
    pg.draw_line(pymupdf.Point(cx - r * 1.35, cy), pymupdf.Point(cx + r * 1.35, cy),
                 color=(0, 0, 0), width=0.35, dashes="[2 2] 0")
    pg.draw_line(pymupdf.Point(cx, cy - r * 1.35), pymupdf.Point(cx, cy + r * 1.35),
                 color=(0, 0, 0), width=0.35, dashes="[2 2] 0")
    # корпус справа: ступенчатый контур
    bx = x + w * 0.62
    pts = [(bx, cy + r), (bx, cy - r * 0.8), (bx + w * 0.12, cy - r * 0.8),
           (bx + w * 0.12, cy - r * 1.25), (bx + w * 0.3, cy - r * 1.25),
           (bx + w * 0.3, cy + r)]
    for a, b in zip(pts, pts[1:]):
        pg.draw_line(pymupdf.Point(*a), pymupdf.Point(*b), color=(0, 0, 0),
                     width=0.6)
    # штриховка разреза — В МАЛОМ участке, как на настоящем чертеже
    for i in range(9):
        t0 = bx + i * (w * 0.3 / 9)
        pg.draw_line(pymupdf.Point(t0, cy + r), pymupdf.Point(t0 + r * 0.5, cy),
                     color=(0, 0, 0), width=0.3)
    # выносной размер со стрелками
    yd = y + h - 8
    pg.draw_line(pymupdf.Point(cx - r, yd), pymupdf.Point(cx + r, yd),
                 color=(0, 0, 0), width=0.4)
    for sx, d in ((cx - r, 1), (cx + r, -1)):
        pg.draw_line(pymupdf.Point(sx, yd), pymupdf.Point(sx + 4 * d, yd - 2),
                     color=(0, 0, 0), width=0.4)
        pg.draw_line(pymupdf.Point(sx, yd), pymupdf.Point(sx + 4 * d, yd + 2),
                     color=(0, 0, 0), width=0.4)
    pg.insert_text((cx - 8, yd - 3), "A-A", fontname="F", fontsize=5.0)
    # «A-A» на чертеже — его собственная надпись, не текст страницы: рисунок
    # едет во второй уровень картинкой, `content` у него null по существу.
    truth.append((x, y, x + w, y + h, "image"))
    _caption(pg, truth, x + 10, y + h + 12, caption)
    return y + h + 16


def _text_w(text: str, size: float, font: str = "F") -> float:
    """Ширина строки ПО МЕТРИКЕ ШРИФТА, а не по len(text)*коэффициент.

    Прежняя оценка `len(caption) * 3.1` недобирала у всех тринадцати подписей
    стенда, а `_measure` умеет только сжимать рамку до чернил и подрастить её
    лишь на GROW пикселей — то есть заниженная рамка так и оставалась
    заниженной, и модель получала незаслуженный промах на подписи.
    """
    import pymupdf
    f = pymupdf.Font(fontfile=FONT_MONO if font == "M" else FONT)
    return f.text_length(text, fontsize=size)


def _caption(pg, truth, x, y, text, size=6.2, label="figure_title"):
    """Подпись к рисунку: рисуем и КЛАДЁМ РАМКУ ПО МЕРЕ, а не на глаз."""
    pg.insert_text((x, y), text, fontname="F", fontsize=size)
    truth.append((x - 2, y - size - 1, x + _text_w(text, size) + 2, y + 2,
                  label))
    _say(truth, text)
    return y + size + 2


def _halftone(pg, truth, x, y, w, h, caption="Fig. 31  Milling head, photograph"):
    """Полутоновая ФОТОГРАФИЯ растром, а не штриховой чертёж.

    Отдельный случай потому, что это другая физика: у чертежа тонкие чёрные
    линии на белом, у фотографии — серая масса из типографской точки. Модель
    зовёт `image` и то и другое, но путает их с текстом по-разному, и мерить
    надо оба.
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
    # растр: порог по регулярной решётке 4x4 — та самая типографская точка
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
    """Овальная печать поверх текста: у модели для неё отдельный класс `seal`."""
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
    # Печать — артефакт (уезжает картинкой), поэтому её знаки не в `content`,
    # а в истине артефактов сбоку: второй уровень обязан прочесть их с
    # картинки, и без записанного эталона проверить это нечем.
    _say(truth, "BIBLIOTEKA No. 4187")
    return R.y1


def _leader_table(pg, truth, x, y, rows, w=230.0, size=6.4, label="table"):
    """Таблица на точечных выносках: столбец имён, точки, столбец чисел.

    Ровно то, чем оглавление отличается от таблицы ОДНИМ признаком, и модель
    на этом путается. Здесь это ТАБЛИЦА, в `contents_dots` — оглавление.
    """
    grid = []
    for i in range(rows):
        yy = y + i * 9.4
        name = f"Bearing bronze {i + 3}"
        pg.insert_text((x, yy), name + " " + "." * 28, fontname="F", fontsize=size)
        pg.insert_text((x + w - 26, yy), f"{12 + i * 3}.{i % 9}", fontname="F",
                       fontsize=size)
        # ТОЧКИ ВЫНОСКИ В ЯЧЕЙКУ НЕ ВХОДЯТ, и это решение, а не небрежность:
        # выноска — типографская линейка, набранная точкой, она стоит МЕЖДУ
        # двумя ячейками и не принадлежит ни одной. Записав её в ячейку, мы
        # обязали бы второй уровень выдать двадцать восемь точек, чтобы
        # «совпасть», то есть штрафовали бы за верный ответ.
        grid.append([name, f"{12 + i * 3}.{i % 9}"])
    truth.append((x - 4, y - 8, x + w, y + (rows - 1) * 9.4 + 4, label))
    _say(truth, cells=grid)
    return y + (rows - 1) * 9.4 + 10


def _span_header_table(pg, truth, x, y, groups, rows, colw=54.0, size=6.2):
    """Шапка в два яруса со сквозной ячейкой над группой столбцов."""
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
        # Сквозная ячейка выражается ПАРОЙ: имя в первой клетке группы, пустые
        # в остальных, и отдельная запись «строка 0, столбец c, ширина n».
        # Одной сеткой это не выразить, а без второй записи двухъярусная шапка
        # неотличима от обычной — то есть главная порча этого случая
        # («шапка сплющена в одну строку») не ловится вовсе.
        spans.append({"строка": 0, "столбец": len(cols), "столбцов": n})
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


# ---------------------------------------------------- рисовальщики для книг
# Всё, что ниже, зовётся из модулей `booksmith/books/*.py`. Каждый рисовальщик
# берёт координаты ЯВНО и не читает формат листа из модуля: книги стенда
# разного формата, и рисовальщик, взявший размер из модуля, нарисовал бы на
# чужом листе молча.

def _has_glyphs(text: str, font: str = "F") -> list[str]:
    """Каких знаков нет в шрифте. Отсутствующий глиф рисуется .notdef-рамкой —
    ЧЕРНИЛАМИ, — и `_measure` спокойно примет её за содержимое. То есть
    страница выйдет с квадратиками вместо формулы, а числа будут здоровы."""
    import pymupdf
    f = pymupdf.Font(fontfile=FONT_MONO if font == "M" else FONT)
    return sorted({c for c in text if c.strip() and not f.has_glyph(ord(c))})


def _line(pg, x0, y0, x1, y1, width=0.9):
    """Линейка. Пол толщины — 0.5 пт: при 144 dpi линия в 0.3 пт даёт НОЛЬ
    пикселей темнее INK, то есть для истины её не существует вовсе."""
    import pymupdf
    if width < 0.5:
        raise SynthError(f"линейка {width} пт тоньше пола 0.5: её не увидит "
                         f"ни `_measure`, ни модель")
    pg.draw_line(pymupdf.Point(x0, y0), pymupdf.Point(x1, y1),
                 color=(0, 0, 0), width=width)


def _put(pg, x, y, text, size=6.4, font="F", right=None, sheet_w=None):
    """Строка с проверкой, что она поместилась на лист.

    ВТОРОЙ КАПКАН ТОГО ЖЕ РОДА, что `insert_textbox`. `insert_text` за правым
    краем листа молча обрезает чернила и возвращает 1, как при успехе: строка
    шириной 1516 пт на листе 506 пт «нарисована», а видно 505. Рамка истины
    при этом объявляет полную ширину, и модель получает вечный промах.
    """
    w = _text_w(text, size, font)
    if right is not None:
        x = right - w
    if sheet_w is not None and x + w > sheet_w + 0.5:
        raise SynthError(
            f"строка {text[:24]!r} шириной {w:.0f} пт не влезает на лист "
            f"{sheet_w:.0f} пт от x={x:.0f}: `insert_text` обрежет её молча")
    pg.insert_text((x, y), text, fontname=font, fontsize=size)
    return w


ENTRY_EN = ("{h}, n. The part of the mechanism that carries the load. "
            "Used in lathes and presses. See also {s}.")
ENTRY_RU = ("{h}, -а, м. Часть механизма, передающая усилие. Применяется "
            "в станках и прессах. См. также ст. {s}.")


def _entries(pg, truth, x, y, y_end, w, sheet_w, words, size=5.8,
             hang=8.0, bold_head=False, label="text", lead=1.25,
             tpl=ENTRY_EN, start=0):
    """Столбец словарных ГНЁЗД с висячим отступом. Каждое гнездо — свой блок
    истины: словарная статья и есть абзац."""
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
                # Полужирного начертания DejaVuSerif в системе может не быть;
                # выделяем гнездо разрядкой — она видна и не требует шрифта.
                sp = " ".join(head)
                wl = _put(pg, xx, y, sp, size, sheet_w=sheet_w)
                rest = ln[len(head):].lstrip()
                _put(pg, xx + wl + 2, y, rest, size, sheet_w=sheet_w)
                # Истина — то, что НАРИСОВАНО, побуквенно: разрядка «A b u t»
                # так и записывается. Записать сюда логическое «Abutment»
                # значило бы объявить расхождение с бумагой нормой, а тогда
                # сверка с текстовым слоем перестаёт быть проверкой.
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
    """Колонтитул: слово слева, слово справа, линейка под ними, колонцифра."""
    # ДВА блока, а не один на всю ширину. Проверено: модель отдаёт на такой
    # колонтитул две рамки `header` по 0.92 — левое слово и правое, — и она
    # права: между ними пустая бумага в полполосы. Склеенная истина давала
    # «header 0 из 12», то есть обвиняла модель в собственной ошибке
    # гранулярности.
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
    """Выключная формула, при необходимости с номером у правого поля."""
    bad = _has_glyphs(text, "M")
    if bad:
        raise SynthError(
            f"в шрифте нет знаков {bad} — они нарисуются пустыми рамками, и "
            f"стенд померит квадратики вместо формулы")
    w = _put(pg, x, y, text, size, font="M", sheet_w=sheet_w)
    truth.append((x - 3, y - size - 1, x + w + 3, y + 3, "display_formula"))
    # Выключная формула по политике АРТЕФАКТ (вырезается картинкой), поэтому
    # её знаки живут не в `content`, а в истине артефактов: `content` у
    # артефакта null во всех книгах, и это одно правило без исключений.
    _say(truth, text)
    if number is not None and right is not None:
        nw = _put(pg, 0, y, number, size - 2, right=right, sheet_w=sheet_w)
        truth.append((right - nw - 2, y - size + 1, right + 2, y + 2,
                      "formula_number"))
        _say(truth, number)
    return y + size * 1.9


def _matrix(pg, truth, x, y, rows, cols, size=6.6, kind="matrix",
            sheet_w=None):
    """Матрица или определитель в скобках: главная ловушка ярлыка
    `display_formula` против `table` — на глаз это сетка чисел."""
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
    if kind == "matrix":                      # круглые скобки штрихами
        for xx, d in ((x + 4, 1), (x1, -1)):
            _line(pg, xx, y - size, xx, y1, 0.7)
            _line(pg, xx, y - size, xx + 4 * d, y - size - 3, 0.6)
            _line(pg, xx, y1, xx + 4 * d, y1 + 3, 0.6)
    else:                                     # определитель — прямые черты
        _line(pg, x + 4, y - size, x + 4, y1, 0.7)
        _line(pg, x1, y - size, x1, y1, 0.7)
    truth.append((x, y - size - 4, x1 + 5, y1 + 4, "display_formula"))
    # Сетка чисел записана СТРОКАМИ, а не ячейками: это ловушка ярлыка, и
    # истина обязана говорить «одна формула», а не «таблица rows x cols». Если
    # записать её сеткой, стенд сам подскажет второму уровню тот ответ,
    # ошибочность которого он и должен ловить.
    _say(truth, " ; ".join(drawn))
    return y1 + size * 1.4


def _box_insert(pg, truth, x, y, w, h, prose, size=5.8, title="ВРЕЗКА"):
    """Врезка в рамке: на глаз — таблица в одну ячейку."""
    import pymupdf
    pg.draw_rect(pymupdf.Rect(x, y, x + w, y + h), color=(0, 0, 0), width=0.8)
    _put(pg, x + 8, y + 12, title, size + 1, sheet_w=x + w)
    body = _fill(pg, _rect(x + 8, y + 18, x + w - 8, y + h - 6), prose, size)
    truth.append((x, y, x + w, y + h, "text"))
    _say(truth, title + " " + body)
    return y + h + 8


def _refs(pg, truth, x, y, y_end, w, sheet_w, size=5.6, start=1):
    """Список литературы: номер в квадратных скобках и втяжка."""
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
    """Рамка чертежа с ОСНОВНОЙ НАДПИСЬЮ в правом нижнем углу.

    Основная надпись — сетка ячеек с текстом, то есть на глаз таблица. В
    истине это `table`: ею она и является. Рамка чертежа при этом идёт по
    краю листа и в истину НЕ попадает — обвести лист целиком детектор не
    должен, и если обведёт, это будет видно счётчиком разлива.
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
    # Основная надпись — сетка 3x2 без шапки: в ней нет строки заголовков,
    # и записать первую строку как шапку значило бы соврать структурой.
    _say(truth, cells=[[title[:22], f"No. {no}"],
                       ["Scale 1:2", "Drawn A.B."],
                       ["Sheet 1 of 3", "1953"]])
    return sx, sy


def _callouts(pg, truth, cx, cy, r, items, sheet_w):
    """Выносные позиции: линия от детали к номеру в кружке."""
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
    """Поле чертежа: один или два вида, штриховые линии, осевые."""
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


# --------------------------------------------------------------------- случаи
# Страница справочника ПЛОТНАЯ сверху донизу — это её главное свойство, и
# первая редакция стенда его не воспроизводила: контент занимал верхнюю
# половину, остальное была чистая бумага. Детектору такая страница не
# похожа ни на что.
#
# Все координаты здесь в ПУНКТАХ (1 пункт = 2 пикселя при 144 dpi). Смешение
# единиц уже стоило одного разворота: половина `x0 + 46` при `x0` в пикселях
# уехала за край листа, и правая страница вышла пустой.
PW, PH = W * PT, H * PT          # лист в пунктах: 506 x 733
MARGIN, COLW, GUT = 34.0, 210.0, 18.0
TOP, BOT = 40.0, 700.0
COL_X = (MARGIN, MARGIN + COLW + GUT)


def _page(doc, wide=False, pw=None, ph=None):
    """Лист. Размер — ЯВНЫЙ параметр, а не только модульная константа.

    Книги стенда бывают разного формата: словарь узкий, атлас альбомный. Пока
    размер брался только из модуля, рисовальщик, позванный для другой книги,
    молча рисовал бы на формате справочника — тот же капкан единиц, что уже
    стоил одного разворота, уехавшего за край листа.
    """
    import pymupdf
    pw = PW if pw is None else pw
    ph = PH if ph is None else ph
    pg = doc.new_page(width=(2 * pw if wide else pw), height=ph)
    pg.insert_font(fontname="F", fontfile=FONT)
    pg.insert_font(fontname="M", fontfile=FONT_MONO)
    return pg


def _flow(pg, t, x, y, y_end, prose, w=COLW, size=6.6, gap=8.0):
    """Заполнить колонку абзацами ДО НИЗА. Возвращает достигнутый y."""
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
    """Обычная страница: две плотные колонки, таблица без линеек, рисунок."""
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
    """Таблица во всю ширину поперёк межколонника (стр. 313)."""
    pg = _page(doc); t = []
    for x in COL_X:
        _flow(pg, t, x, TOP, 230, PROSE_EN)
    _table(pg, t, MARGIN + 6, 250,
           [(f"Col {i}", MARGIN + 6 + i * 105) for i in range(4)], 7)
    for x in COL_X:
        _flow(pg, t, x, 380, BOT, PROSE_EN)
    return pg, t


def c_three_column_table(doc, rng):
    """Три ОТДЕЛЬНЫЕ таблицы рядом: модель берёт одну из трёх (стр. 317).

    Просветы между таблицами намеренно втрое шире, чем между столбцами
    внутри, и у каждой своя подпись. Первая редакция этого не делала:
    просветы были одинаковы, и нарисована была ОДНА таблица на шесть
    столбцов. Детектор отдавал на неё одну рамку и был прав, а в дефекты
    модели это записал я.
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
    """Формула блоком рядом с таблицей: ошибка ЯРЛЫКА при верной рамке (стр. 40)."""
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
    """Оглавление с точечными выносками (стр. 4): выглядит таблицей, ею не является."""
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
        # Точки выноски — та же типографская линейка, что в `_leader_table`, и
        # в истину знаков не идут по той же причине.
        drawn.append(f"{name} {100 + int(y) % 400}")
        y += 10.5
    t.append((MARGIN + 2, TOP + 32, PW - MARGIN, y - 4, "content"))
    _say(t, " ".join(drawn))
    return pg, t


def c_no_artefacts(doc, rng):
    """Сплошная проза без артефактов — проверка на ложные срабатывания."""
    pg = _page(doc); t = []
    for x in COL_X:
        _flow(pg, t, x, TOP, BOT, PROSE_EN)
    return pg, t


def c_full_page_table(doc, rng):
    """Таблица во весь лист: текста нет вовсе."""
    pg = _page(doc); t = []
    _table(pg, t, MARGIN + 6, TOP + 10,
           [(f"Col {i}", MARGIN + 6 + i * 88) for i in range(5)], 66)
    return pg, t


def c_two_figures_side(doc, rng):
    """Два рисунка бок о бок: слияние по горизонтали."""
    pg = _page(doc); t = []
    _flow(pg, t, MARGIN, TOP, 200, PROSE_EN, w=2 * COLW + GUT)
    _figure(pg, t, COL_X[0], 230, COLW, 120, "Fig. 1  Cross feed screw")
    _figure(pg, t, COL_X[1], 230, COLW, 120, "Fig. 2  Compound rest screw")
    for x in COL_X:
        _flow(pg, t, x, 380, BOT, PROSE_EN)
    return pg, t


def c_russian(doc, rng):
    """Кириллица: наши книги на ней, латинский стенд этого класса не даёт."""
    pg = _page(doc); t = []
    y = _flow(pg, t, COL_X[0], TOP, 300, PROSE_RU)
    _table(pg, t, COL_X[0] + 6, y + 14, [("Марка", COL_X[0] + 6),
                                         ("σ, МПа", COL_X[0] + 76),
                                         ("НВ", COL_X[0] + 146)], 6)
    _flow(pg, t, COL_X[0], y + 130, BOT, PROSE_RU)
    y2 = _flow(pg, t, COL_X[1], TOP, 280, PROSE_RU)
    _figure(pg, t, COL_X[1], y2 + 12, COLW, 100, "Рис. 3.  Схема испытания")
    _flow(pg, t, COL_X[1], y2 + 132, BOT, PROSE_RU)
    return pg, t


def _half(pg, t, x0, rng, kind):
    """Половина разворота. `x0` — сдвиг В ПУНКТАХ, не в пикселях."""
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
    """РАЗВОРОТ: две книжные страницы отсканированы одним листом.

    Половина нашей библиотеки лежит именно так — 1693 страницы из 3268. Лист
    шире, чем выше, посередине корешок с тенью. Проверяет сразу двоих: разрез
    разворота в `djvu.py` и детектор, если разворот дошёл до него целым.
    """
    pg = _page(doc, wide=True); t = []
    _half(pg, t, 0.0, rng, "table")
    _half(pg, t, PW, rng, "figure")
    return pg, t


def c_spread_rotated(doc, rng):
    """РАЗВОРОТ, ПОВЁРНУТЫЙ НА 90°: под большую таблицу во всю ширину.

    В справочниках сплошь: таблицу или чертёж, не влезающие поперёк, печатают
    вдоль. Порядок чтения для такой страницы не определён вовсе, а детектор
    видит её сплющенной в 800x800 без сохранения пропорций — искажение здесь
    сильнее всего.
    """
    pg = _page(doc, wide=True); t = []
    _flow(pg, t, MARGIN, TOP, 150, PROSE_EN, w=2 * PW - 2 * MARGIN)
    _table(pg, t, MARGIN + 6, 180,
           [(f"Col {i}", MARGIN + 6 + i * 118) for i in range(8)], 34)
    pg.insert_text((PW - 20, BOT + 18), "308-309", fontname="F", fontsize=6.4)
    t.append((PW - 24, BOT + 11, PW + 20, BOT + 20, "number"))
    _say(t, "308-309")
    return pg, t


# --- таблицы разных размеров: контуры именно их сейчас главное --------------
def c_table_half_page(doc, rng):
    """Таблица в половину листа, во всю ширину набора."""
    pg = _page(doc); t = []
    _flow(pg, t, MARGIN, TOP, 330, PROSE_EN, w=2 * COLW + GUT)
    _table(pg, t, MARGIN + 6, 360, _grid(MARGIN + 6, 5, colw=76), 30, colw=76)
    return pg, t


def c_table_full_width(doc, rng):
    """Таблица во всю ширину посреди страницы, текст сверху и снизу."""
    pg = _page(doc); t = []
    _flow(pg, t, MARGIN, TOP, 230, PROSE_EN, w=2 * COLW + GUT)
    _table(pg, t, MARGIN + 6, 260, _grid(MARGIN + 6, 6, colw=62), 12)
    _flow(pg, t, MARGIN, 420, BOT, PROSE_EN, w=2 * COLW + GUT)
    return pg, t


def c_table_tall_narrow(doc, rng):
    """Узкая высокая таблица в одну колонку, рядом проза."""
    pg = _page(doc); t = []
    _table(pg, t, COL_X[0] + 6, TOP + 10, _grid(COL_X[0] + 6, 2, colw=90), 58,
           colw=90)
    _flow(pg, t, COL_X[1], TOP, BOT, PROSE_EN)
    return pg, t


def c_table_wide_short(doc, rng):
    """Широкая таблица в три строки: высота меньше абзаца."""
    pg = _page(doc); t = []
    _flow(pg, t, MARGIN, TOP, 260, PROSE_EN, w=2 * COLW + GUT)
    _table(pg, t, MARGIN + 6, 290, _grid(MARGIN + 6, 7, colw=52), 3, colw=52)
    _flow(pg, t, MARGIN, 350, BOT, PROSE_EN, w=2 * COLW + GUT)
    return pg, t


def c_table_ruled(doc, rng):
    """Та же таблица, но С ЛИНЕЙКАМИ: насколько легче она даётся детектору."""
    pg = _page(doc); t = []
    _flow(pg, t, MARGIN, TOP, 240, PROSE_EN, w=2 * COLW + GUT)
    _table(pg, t, MARGIN + 6, 270, _grid(MARGIN + 6, 5, colw=76), 14,
           colw=76, ruled=True)
    _flow(pg, t, MARGIN, 460, BOT, PROSE_EN, w=2 * COLW + GUT)
    return pg, t


def c_table_split_a(doc, rng):
    """Таблица, оборванная низом страницы (продолжение — на следующей)."""
    pg = _page(doc); t = []
    _flow(pg, t, MARGIN, TOP, 300, PROSE_EN, w=2 * COLW + GUT)
    _table(pg, t, MARGIN + 6, 330, _grid(MARGIN + 6, 5, colw=76), 34, colw=76)
    return pg, t


def c_table_split_b(doc, rng):
    """Продолжение той же таблицы с верха следующей страницы."""
    pg = _page(doc); t = []
    _table(pg, t, MARGIN + 6, TOP + 6, _grid(MARGIN + 6, 5, colw=76), 22,
           colw=76)
    _flow(pg, t, MARGIN, 280, BOT, PROSE_EN, w=2 * COLW + GUT)
    return pg, t


def c_chart_page(doc, rng):
    """График с осями: у модели для него отдельный класс `chart`."""
    pg = _page(doc); t = []
    _flow(pg, t, MARGIN, TOP, 220, PROSE_EN, w=2 * COLW + GUT)
    _chart(pg, t, MARGIN + 30, 250, 2 * COLW + GUT - 60, 150)
    _flow(pg, t, MARGIN, 460, BOT, PROSE_EN, w=2 * COLW + GUT)
    return pg, t


def c_figure_full_width(doc, rng):
    """Рисунок во всю ширину набора."""
    pg = _page(doc); t = []
    _flow(pg, t, MARGIN, TOP, 220, PROSE_EN, w=2 * COLW + GUT)
    _figure(pg, t, MARGIN, 250, 2 * COLW + GUT, 190, "Fig. 7  General layout")
    _flow(pg, t, MARGIN, 480, BOT, PROSE_EN, w=2 * COLW + GUT)
    return pg, t


def c_russian_table_wide(doc, rng):
    """Кириллица плюс широкая таблица во всю ширину."""
    pg = _page(doc); t = []
    _flow(pg, t, MARGIN, TOP, 230, PROSE_RU, w=2 * COLW + GUT)
    _table(pg, t, MARGIN + 6, 260, [("Марка", MARGIN + 6), ("σ, МПа", MARGIN + 96),
                                    ("δ, %", MARGIN + 186), ("НВ", MARGIN + 276),
                                    ("Примечание", MARGIN + 356)], 16, colw=76)
    _flow(pg, t, MARGIN, 470, BOT, PROSE_RU, w=2 * COLW + GUT)
    return pg, t


def c_spread_table_wide(doc, rng):
    """РАЗВОРОТ с таблицей ЧЕРЕЗ КОРЕШОК: она идёт по обеим страницам."""
    pg = _page(doc, wide=True); t = []
    for x0 in (0.0, PW):
        _flow(pg, t, x0 + MARGIN, TOP, 250, PROSE_EN, w=2 * COLW + GUT)
    _table(pg, t, MARGIN + 6, 290,
           _grid(MARGIN + 6, 11, colw=76), 20, colw=76)
    for x0 in (0.0, PW):
        _flow(pg, t, x0 + MARGIN, 560, BOT, PROSE_EN, w=2 * COLW + GUT)
    return pg, t


def c_spread_rotated_figure(doc, rng):
    """РАЗВОРОТ, ПОВЁРНУТЫЙ НА 90°, с большим чертежом во всю ширину."""
    pg = _page(doc, wide=True); t = []
    _flow(pg, t, MARGIN, TOP, 130, PROSE_EN, w=2 * PW - 2 * MARGIN)
    _figure(pg, t, MARGIN, 160, 2 * PW - 2 * MARGIN, 440,
            "Fig. 12  Machine tool bed, general arrangement")
    return pg, t


# --- добавленные случаи: труднее прежних ------------------------------------
# Прежние двадцать три были в основном по одному артефакту на страницу и с
# широкими просветами. Настоящая книга так себя не ведёт: рядом стоят два
# артефакта разного рода, просветы между столбцами уже междустрочья, а поверх
# всего стоит библиотечный штамп.

def c_table_two_side_by_side(doc, rng):
    """ДВЕ таблицы рядом — частый разворот справочника (три уже есть)."""
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
    """Две таблицы ОДНА ПОД ДРУГОЙ: слияние по вертикали ловится этим."""
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
    """Шапка в два яруса со сквозными ячейками над группами столбцов."""
    pg = _page(doc); t = []
    _flow(pg, t, MARGIN, TOP, 190, PROSE_EN, w=2 * COLW + GUT)
    _span_header_table(pg, t, MARGIN + 8, 226,
                       [("CLEARANCE", 3), ("INTERFERENCE", 3), ("TRANSITION", 2)],
                       22)
    _flow(pg, t, MARGIN, 480, BOT, PROSE_EN, w=2 * COLW + GUT)
    return pg, t


def c_table_dense_no_rules(doc, rng):
    """Плотная таблица без линеек: просвет между столбцами с междустрочье.

    Самый трудный вид и самый частый в наших книгах. Если стенд его не несёт,
    он меряет задачу легче настоящей — именно это и было ему в упрёк.
    """
    pg = _page(doc); t = []
    _flow(pg, t, MARGIN, TOP, 130, PROSE_EN, w=2 * COLW + GUT)
    _table(pg, t, MARGIN + 6, 158, _grid(MARGIN + 6, 9, colw=44, gap=2.0), 62,
           colw=44, step=7.4, size=5.6)
    _flow(pg, t, MARGIN, 620, BOT, PROSE_EN, w=2 * COLW + GUT)
    return pg, t


def c_table_leaders(doc, rng):
    """Таблица на точечных выносках — от оглавления её отличает один признак."""
    pg = _page(doc); t = []
    _flow(pg, t, MARGIN, TOP, 150, PROSE_EN, w=2 * COLW + GUT)
    _leader_table(pg, t, MARGIN + 8, 190, 26)
    _leader_table(pg, t, PW / 2 + 14, 190, 26, w=200)
    _flow(pg, t, MARGIN, 470, BOT, PROSE_EN, w=2 * COLW + GUT)
    return pg, t


def c_photo_halftone(doc, rng):
    """Полутоновая фотография растром рядом с прозой."""
    pg = _page(doc); t = []
    _flow(pg, t, MARGIN, TOP, 170, PROSE_EN, w=2 * COLW + GUT)
    _halftone(pg, t, MARGIN + 10, 200, 2 * COLW + GUT - 20, 250)
    _flow(pg, t, MARGIN, 480, BOT, PROSE_EN, w=2 * COLW + GUT)
    return pg, t


def c_figure_and_table(doc, rng):
    """Чертёж и таблица ВПЛОТНУЮ: два артефакта разного рода без просвета."""
    pg = _page(doc); t = []
    _flow(pg, t, MARGIN, TOP, 150, PROSE_EN, w=2 * COLW + GUT)
    _figure(pg, t, MARGIN + 6, 178, COLW - 6, 200,
            "Fig. 44  Tailstock")
    _table(pg, t, MARGIN + COLW + GUT + 10, 178,
           _grid(MARGIN + COLW + GUT + 10, 2, colw=76), 20, colw=76)
    _flow(pg, t, MARGIN, 420, BOT, PROSE_EN, w=2 * COLW + GUT)
    return pg, t


def c_figure_text_wrap(doc, rng):
    """Текст обтекает рисунок: колонка рвётся, а рисунок сидит в её теле."""
    pg = _page(doc); t = []
    _flow(pg, t, MARGIN, TOP, 130, PROSE_EN, w=2 * COLW + GUT)
    _figure(pg, t, MARGIN + 6, 160, COLW - 10, 170, "Fig. 51  Chuck jaw")
    x2 = MARGIN + COLW + GUT
    _flow(pg, t, x2, 160, 350, PROSE_EN, w=COLW)
    _flow(pg, t, MARGIN, 366, BOT, PROSE_EN, w=2 * COLW + GUT)
    return pg, t


def c_marginalia(doc, rng):
    """Заметки на внешнем поле: узкая колонка сбоку от основной."""
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
    """Сноски под короткой линейкой внизу полосы."""
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
    """Библиотечный штамп поверх текста и таблица под ним."""
    pg = _page(doc); t = []
    _flow(pg, t, MARGIN, TOP, 220, PROSE_EN, w=2 * COLW + GUT)
    _table(pg, t, MARGIN + 6, 250, _grid(MARGIN + 6, 4, colw=86), 16, colw=86)
    _flow(pg, t, MARGIN, 440, BOT, PROSE_EN, w=2 * COLW + GUT)
    _stamp(pg, t, PW - MARGIN - 60, 120)
    return pg, t


def c_rotated_single_table(doc, rng):
    """ОДИНОЧНАЯ страница, повёрнутая на 90° ради широкой таблицы."""
    pg = _page(doc); t = []
    _flow(pg, t, MARGIN, TOP, 140, PROSE_EN, w=2 * COLW + GUT)
    _table(pg, t, MARGIN + 6, 170, _grid(MARGIN + 6, 8, colw=50), 36, colw=50,
           step=8.4)
    return pg, t


def c_chart_pair(doc, rng):
    """Два графика рядом — соседние оси легко склеиваются в одну рамку."""
    pg = _page(doc); t = []
    _flow(pg, t, MARGIN, TOP, 160, PROSE_EN, w=2 * COLW + GUT)
    _chart(pg, t, MARGIN + 24, 200, COLW - 40, 150, "Fig. 61  Hardness")
    _chart(pg, t, MARGIN + COLW + GUT + 24, 200, COLW - 40, 150,
           "Fig. 62  Toughness")
    _flow(pg, t, MARGIN, 420, BOT, PROSE_EN, w=2 * COLW + GUT)
    return pg, t


CASES = {
    # --- обычные страницы ---
    "two_columns": c_two_columns,
    "no_artefacts": c_no_artefacts,
    "contents_dots": c_contents_dots,
    "russian": c_russian,
    # --- таблицы разных размеров ---
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
    # --- рисунки и графики ---
    "two_figures_side": c_two_figures_side,
    "figure_full_width": c_figure_full_width,
    "chart_page": c_chart_page,
    "chart_pair": c_chart_pair,
    "photo_halftone": c_photo_halftone,
    "figure_and_table": c_figure_and_table,
    "figure_text_wrap": c_figure_text_wrap,
    # --- прочая обстановка страницы ---
    "marginalia": c_marginalia,
    "footnotes_rule": c_footnotes_rule,
    "stamp_over_text": c_stamp_over_text,
    "rotated_single_table": c_rotated_single_table,
    # --- развороты и повороты ---
    "spread": c_spread,
    "spread_table_wide": c_spread_table_wide,
    "spread_rotated": c_spread_rotated,
    "spread_rotated_figure": c_spread_rotated_figure,
}
# Случаи, которые надо повернуть на 90° после отрисовки.
ROTATE = {"spread_rotated": 90, "spread_rotated_figure": 90,
          "rotated_single_table": 90}
# Случаи-развороты: им дорисовывается тень переплёта.
SPREADS = {"spread", "spread_table_wide", "spread_rotated",
           "spread_rotated_figure"}


# ------------------------------------------------------------------ старение
# Профили — НАЗВАННЫЕ наборы, а не россыпь ручек: их параметры целиком уезжают
# в слепок, так что назвать профиль достаточно, чтобы прогон повторился.
AGING = {
    "clean": {},
    "scan": dict(blur=0.5, noise=3.0, speck=0.0004, tint=(244, 6, 4),
                 skew=0.5, jpeg=85),
    "old": dict(blur=0.8, noise=5.5, speck=0.0012, tint=(232, 12, 8),
                skew=1.2, jpeg=68),
    # Ветхий: к прежнему добавлены просвет с оборота и тёмный край скана. Оба
    # не двигают рамок истины — значит, сравнимы с `old` при том же зерне, и
    # разницу в числе можно отнести именно к ним.
    # Перекос у «ветхого» НАМЕРЕННО тот же, что у `old`: перекос — ЕДИНСТВЕННОЕ
    # в старении, что двигает рамки истины (аффинная матрица переносит их
    # через `_xform_box`). При равном перекосе рамки истины двух профилей
    # совпадают побайтно, и разницу в числе можно отнести к бумаге, а не к
    # сместившейся истине. Прежняя редакция ставила 1.8 и при этом обещала в
    # README «ветхий не двигает рамок истины» — двигал, все 382.
    "ветхий": dict(blur=1.1, noise=7.5, speck=0.0026, tint=(214, 20, 14),
                   skew=1.2, jpeg=52, bleed=0.16, edge=0.55),
}


def _age(img, profile: str, seed: int):
    """Состарить растр. Возвращает (растр, матрица поворота или None).

    Старение здесь не украшение: замер на одной странице показал, что на
    ЧИСТОЙ странице рамки `table` нет вовсе, а на состаренной она появляется
    (0.583) — вместе с конкурирующей `text` 0.567 на том же прямоугольнике,
    то есть с подписью того самого дефекта, что диагностирован на настоящей
    книге. Мерить по чистой бумаге значило бы мерить не ту задачу.
    """
    import cv2
    import numpy as np

    p = AGING[profile]
    if not p:
        return img, None
    rng = np.random.default_rng(seed)
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)
    g = cv2.GaussianBlur(g, (0, 0), p["blur"])          # растекание краски
    h, w = g.shape
    if p.get("bleed"):
        # Просвет с оборота: зеркальная страница, размытая и слабая. Настоящая
        # беда старой тонкой бумаги — и ровно тот вид «текста», которого на
        # странице нет, а рамка на него встать может.
        # Со СДВИГОМ. Без него на симметричной вёрстке зеркало ложится ровно
        # на свой же текст, и «просвет с оборота» выходит утолщением краски —
        # то есть проверяет не то, чем назван. Оборот книги не совпадает с
        # лицом ни по строкам, ни по колонкам.
        back = cv2.GaussianBlur(g[:, ::-1], (0, 0), p["blur"] * 3.0)
        sx, sy = int(w * 0.035), int(h * 0.012)
        back = np.roll(np.roll(back, sy, axis=0), sx, axis=1)
        g = 255.0 - (255.0 - g) - p["bleed"] * (255.0 - back)
        g = np.clip(g, 0, 255)
    yy, xx = np.mgrid[0:h, 0:w]
    base, gx, gy = p["tint"]
    g = np.minimum(g, 255) / 255.0 * (base - gx * (xx / w) - gy * (yy / h))
    g += rng.normal(0, p["noise"], g.shape)             # зерно бумаги
    spec = rng.random(g.shape) < p["speck"]             # крапины
    g[spec] = rng.uniform(40, 120, spec.sum())
    if p.get("edge"):
        # Тёмный край скана: у книги, снятой на планшете, борт полосы чёрный.
        # Полоса шириной в 1–3% листа с одной случайной стороны.
        # Свой генератор: иначе выборки края сдвинули бы поток, и УГОЛ
        # ПЕРЕКОСА у профиля с краем отличался бы от профиля без него — то
        # есть рамки истины разошлись бы там, где обещано совпадение.
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
        # Угол — из СОБСТВЕННОГО генератора. Из общего он зависел бы от числа
        # выборок, сделанных выше, а их число зависит от `speck`: крапин
        # больше — поток ушёл дальше — угол другой. Так у двух профилей с
        # ОДИНАКОВЫМ перекосом расходились все 382 рамки истины, до 28
        # пикселей, и межпрофильное сравнение молча меряло другую истину.
        ang = np.random.default_rng(seed + 4409).uniform(-p["skew"], p["skew"])
        M = cv2.getRotationMatrix2D((w / 2, h / 2), ang, 1.0)
        g = cv2.warpAffine(g, M, (w, h), flags=cv2.INTER_CUBIC,
                           borderMode=cv2.BORDER_REPLICATE)
    ok, enc = cv2.imencode(".jpg", g, [cv2.IMWRITE_JPEG_QUALITY, p["jpeg"]])
    if not ok:
        raise SynthError("не удалось пережать страницу в JPEG")
    return cv2.imdecode(enc, cv2.IMREAD_COLOR), M


def _binding(img, seed: int):
    """Тень переплёта посередине разворота.

    Та самая, на которой вето разреза однажды ошиблось одиннадцать раз из
    одиннадцати: чернота у корешка шла от тени, а код проверял полосу, а не
    сквозную линейку. Синтетический разворот обязан её нести, иначе вето
    проверяется на случае, которого в природе не бывает.
    """
    import cv2
    import numpy as np

    rng = np.random.default_rng(seed + 7)
    h, w = img.shape[:2]
    cx = w // 2 + int(rng.integers(-w // 60, w // 60))
    band = max(8, w // 40)
    xx = np.arange(w)
    prof = np.exp(-((xx - cx) ** 2) / (2 * (band / 2.2) ** 2))
    # Сверху тень гуще: у сканов разворота верх корешка чернее всего.
    depth = np.linspace(0.62, 0.30, h)[:, None] * prof[None, :]
    out = img.astype(np.float32) * (1.0 - depth[:, :, None])
    return np.clip(out, 0, 255).astype(np.uint8), cx


def _xform_box(box, M):
    """Рамка после аффинного преобразования: описанный прямоугольник углов.

    Для модели с рамками по осям это и есть верная истина: повёрнутый
    прямоугольник в такой модели не выразить, а описанный вокруг него —
    ровно то, что обязан вернуть детектор.
    """
    import numpy as np
    x0, y0, x1, y1 = box
    pts = np.array([[x0, y0, 1], [x1, y0, 1], [x1, y1, 1], [x0, y1, 1]]).T
    q = M @ pts
    return (float(q[0].min()), float(q[1].min()),
            float(q[0].max()), float(q[1].max()))


def _clip_box(box, w, h):
    """Рамка внутри растра. Перекос уводит края за лист, и без обрезки истина
    частью лежала бы вне страницы — модель туда рамку поставить не может по
    построению, и промах был бы незаслуженным."""
    x0, y0, x1, y1 = box
    return (max(0.0, min(x0, w)), max(0.0, min(y0, h)),
            max(0.0, min(x1, w)), max(0.0, min(y1, h)))


def _rot90_box(box, src_h):
    """Рамка после поворота растра на 90° по часовой.

    Точка y уезжает в x' = src_h - 1 - y, значит отрезок [y0, y1] переходит в
    [src_h-1-y1, src_h-1-y0], а ПРАВЫЙ край рамки полуоткрыт и потому равен
    src_h - y0, а не src_h - 1 - y0. Прежняя редакция теряла по пикселю на
    каждой рамке повёрнутой страницы — немного, но ровно в ту сторону, в
    которую истина обязана не ошибаться.
    """
    x0, y0, x1, y1 = box
    return (src_h - 1 - y1, x0, src_h - y0, x1)


def _commit() -> str:
    """Коммит РЕПОЗИТОРИЯ ИСХОДНИКОВ, а не рабочего каталога процесса."""
    import subprocess
    root = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))
    try:
        p = subprocess.run(["git", "-C", root, "status", "--porcelain"],
                           capture_output=True, text=True, timeout=10)
        h = subprocess.run(["git", "-C", root, "rev-parse", "HEAD"],
                           capture_output=True, text=True, timeout=10)
        if h.returncode != 0:
            return "не репозиторий"
        return h.stdout.strip() + (" (грязное дерево)" if p.stdout.strip() else "")
    except Exception as e:
        return f"не спросили git: {e}"


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ------------------------------------------------------- измеренная истина
# Рамки истины меряются ПО ЧЕРНИЛАМ, а не объявляются числом. Причина
# денежная: за один вечер этот генератор соврал рамками четыре раза, и все
# четыре раза числа выглядели здоровыми. Пустые рамки текста
# (`insert_textbox` при непомещающемся тексте не рисует ничего и молча отдаёт
# отрицательное), правая половина разворота за краем листа (пиксели в поле,
# считающем пункты), линованная форма вместо чертежа, и рамка формулы шире
# самой формулы на 83 пункта — константа, набранная на глаз. Последняя стоила
# ложного обвинения модели: `formula_next_to_table` числился её отказом.
#
# Что даёт измерение: рамка не может оказаться шире нарисованного, а пустая
# рамка ПАДАЕТ, а не молчит. Это то самое правило про ноль от проверки и ноль
# от непонимания, применённое к самому стенду.
INK = 160          # темнее этого — чернила (страница ещё чистая, без старения)
KEEP = 2           # столько пикселей поля оставить вокруг измеренного
# Ярлыки, чьи рамки в случаях набраны на глаз вокруг текста: им позволено не
# только сжаться до чернил, но и вырасти до них. Геометрические рамки
# (таблица, рисунок, график, колонка текста) считаются кодом и только сжимаются.
GUESSED = {"figure_title", "display_formula", "doc_title", "paragraph_title",
           "number", "content", "footnote"}
GROW = 6           # насколько такой рамке позволено вырасти, пикселей


def _measure(img, boxes, case: str):
    """Подтянуть рамки истины к чернилам. Пустая рамка — ошибка, а не ноль."""
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
                f"{case}: рамка истины {lab} {[round(v) for v in (x0, y0, x1, y1)]} "
                f"пуста — под ней не нарисовано ни пикселя. Это не «блок без "
                f"содержимого», это НЕ НАРИСОВАЛОСЬ, и в замере такая рамка "
                f"даёт модели вечный незаслуженный промах.")
        ys, xs = np.where(sub)
        L, T = a + int(xs.min()), b + int(ys.min())
        R, B = a + int(xs.max()) + 1, b + int(ys.max()) + 1
        if lab in GUESSED:
            # Рост ТОЛЬКО ПО СПЛОШНЫМ ЧЕРНИЛАМ. Прежняя редакция брала рамку
            # чернил в окне, расширенном на GROW во все стороны, — и чужая
            # строка, стоящая в четырёх пикселях, задавала край рамки. Это
            # прямо противоречило докстроке: рамка обязана меряться по СВОИМ
            # чернилам. Раздвигаемся, пока соседний ряд не пуст, и ни пикселя
            # дальше: просвет означает, что дальше уже не наше.
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
    """Сверить истину знаков с ТЕКСТОВЫМ СЛОЕМ PDF по той же странице.

    Зачем вообще возможна такая сверка. Синтетические страницы РИСУЮТСЯ, а не
    сканируются, поэтому у чистой страницы есть текстовый слой, и он — второй,
    независимый от нашего учёта свидетель: `_say` пишет то, что мы СОБИРАЛИСЬ
    нарисовать, `page.get_text("words")` отдаёт то, что в страницу реально
    легло. Прежде такого свидетеля не было ни у чего: `_measure` держит только
    одну сторону («рамка без чернил падает»), а знаков не проверял никто, их
    и не было.

    ЧЕТЫРЕ ЧИСЛА, И ОНИ РАЗНЫЕ ПО СМЫСЛУ — это то же правило, что «ноль от
    проверки и ноль от непонимания разные нули», применённое к знакам:

    `нет в слое` — истина объявляет слово, которого на бумаге нет. Единственная
    настоящая тревога: так выглядит рамка, объявленная богаче нарисованного.

    `вне истины` — слово нарисовано, но не накрыто НИ ОДНОЙ рамкой истины.
    Часть таких слов нарочна (номера строк каталога стоят левее рамки таблицы),
    поэтому число печатается, а не запрещается: молчащий счётчик здесь врал бы
    тем же способом, которым «глав 0» врало про четыре книги сразу.

    `призраков` — слово в рамке, повторяющее уже объявленное. Источник известен
    и померен: `insert_textbox` зовётся по нескольку раз на одну рамку (30
    рисующих заходов на 20 рамок страницы `no_artefacts`), и в текстовом слое
    лежат ВСЕ черновики. Проверено прямо: множество слов слоя совпало с
    множеством слов всех черновиков ровно, 2198 против 2198, необъяснённых 0.

    `необъяснённых` — слово в рамке, которого в истине нет вовсе и повтором оно
    не объясняется. Ноль — норма, ненулевое обязано быть НАЗВАНО, и потому
    примеры печатаются рядом с числом. Один такой уже найден и стоит того,
    чтобы его знать: `marginalia` несёт на бумаге обрывок `sc`. Это `_fill`
    обрезал тело по `len*0.9` посреди слова `screw`, черновик с обрывком
    НАРИСОВАЛСЯ, а следующий заход дописал текст встык — обрывок остался на
    бумаге, в истине его нет, и до этой сверки его не видел никто.

    ЧЕГО ЭТИ ЧИСЛА НЕ ЛОВЯТ, И ЭТО НАДО ЗНАТЬ. Потерянное истиной слово,
    которое в блоке ВСТРЕЧАЕТСЯ ЕЩЁ РАЗ, уходит в `призраков`, а не в
    `необъяснённых`: замер мутацией показал 8 из 16 отброшенных последних слов
    именно там. На прозе, где слова повторяются, слепое пятно тем шире, чем
    длиннее блок.

    Сверяются ТОЛЬКО блоки разряда «текст» и «служебное»: у артефакта знаков в
    `content` нет по построению — он уезжает во второй уровень картинкой.
    """
    from collections import Counter
    from . import policy

    inside = [[] for _ in boxes]
    outside = []
    for x0, y0, x1, y1, w in words:
        cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        # Из накрывающих берётся САМАЯ МЕЛКАЯ: рамки вкладываются (основная
        # надпись внутри поля чертежа, подпись рядом с рисунком), и «первая по
        # списку» отдала бы слово внешней рамке, то есть считала бы не то.
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
    примеры = []
    for j, b in enumerate(boxes):
        if policy.role(b[4]) == "артефакт":
            continue
        have = Counter(inside[j])
        want = Counter((said.get(j, {}).get("текст") or "").split())
        m = want - have
        e = have - want
        miss += sum(m.values())
        for w, n in e.items():
            if w in want:
                ghost += n
            elif len(w) >= 4 and set(w) == {"."}:
                # ТОЧЕЧНАЯ ВЫНОСКА — не слово. Сплошной ряд точек между именем
                # и номером страницы это типографская линейка, набранная
                # точкой; в ячейку и в текст она не входит (см. решение в
                # `_leader_table`). Своим числом, а не в «необъяснённых»:
                # иначе шестьдесят выносок оглавления навсегда держали бы
                # тревожный счётчик ненулевым и прятали бы в себе настоящую
                # находку.
                leaders += n
            else:
                unknown += n
                if len(примеры) < 4:
                    примеры.append(f"{b[4]}#{j}: {w!r}")
        if m and len(примеры) < 4:
            примеры.append(f"{b[4]}#{j}: нет в слое {list(m)[:3]}")
    return {"слов в слое": len(words), "нет в слое": miss,
            "вне истины": len(outside), "призраков": ghost,
            "выносок": leaders, "необъяснённых": unknown,
            "слова вне истины": sorted(set(outside))[:8],
            "примеры расхождений": примеры}


def build(out_dir: str, cases=None, seed: int = 1, aging: str = "old",
          book: str = "spravochnik", log=print) -> dict:
    """Сложить синтетическую книгу: PDF плюс точная истина к каждой странице.

    Продукт — обычный PDF, поэтому по нему работают `books detect`,
    `books html`, `books feed` без единой поправки: стенд не отдельный тракт,
    а такая же книга, только с известным ответом.
    """
    import cv2
    import numpy as np
    import pymupdf

    if aging not in AGING:
        raise SynthError(f"профиль старения {aging!r}: знаю только {tuple(AGING)}")
    from .books import load
    mod = load(book)
    B_CASES = mod.CASES
    B_SPREADS = getattr(mod, "SPREADS", set())
    B_ROTATE = getattr(mod, "ROTATE", {})
    names = list(cases or B_CASES)
    bad = [n for n in names if n not in B_CASES]
    if bad:
        raise SynthError(f"в книге {book} нет случаев: {bad}. "
                         f"Есть: {sorted(B_CASES)}")
    for f in (FONT, FONT_MONO):
        if not os.path.exists(f):
            raise SynthError(
                f"нет шрифта {f}. Стенд рисует им, и без него страницы выйдут "
                f"пустыми. Поставьте fonts-dejavu или задайте свой путь.")

    os.makedirs(out_dir, exist_ok=True)
    truth_dir = os.path.join(out_dir, "truth")
    os.makedirs(truth_dir, exist_ok=True)
    for old in os.listdir(truth_dir):
        os.unlink(os.path.join(truth_dir, old))

    out = pymupdf.open()
    pages, counts = [], {}
    for i, name in enumerate(names):
        doc = pymupdf.open()
        # Зерно по ИМЕНИ случая, а не по позиции в списке. Позиционный посев
        # означал, что вставка одной страницы молча меняет старение всех
        # последующих, а два прогона с разным `--cases` несравнимы построчно.
        page_seed = seed ^ (int.from_bytes(
            hashlib.blake2b(f"{book}/{name}".encode(), digest_size=4).digest(),
            "big") & 0x7FFFFFFF)
        _said_reset()
        pg, t = B_CASES[name](doc, np.random.default_rng(page_seed))
        said = _said_take()
        # Текстовый слой берётся с ЧИСТОЙ страницы и до `doc.close()`: после
        # растеризации и старения его уже нет, страница становится картинкой.
        # Координаты в пунктах — переводим тем же k, что и рамки истины.
        raw_words = [(w[0] * DPI / 72.0, w[1] * DPI / 72.0,
                      w[2] * DPI / 72.0, w[3] * DPI / 72.0, w[4])
                     for w in pg.get_text("words")]
        bad_id = [j for j in said if j >= len(t)]
        if bad_id:
            raise SynthError(
                f"{name}: истина знаков записана блокам {bad_id}, а рамок "
                f"истины всего {len(t)}. `_say` отстал от `truth.append` — "
                f"связь по номеру блока порвана, и знаки уехали бы не туда")
        pix = pg.get_pixmap(dpi=int(DPI))
        img = cv2.cvtColor(
            np.frombuffer(pix.samples, np.uint8)
              .reshape(pix.height, pix.width, pix.n), cv2.COLOR_RGB2BGR)
        doc.close()

        # Истина рисовалась в ПУНКТАХ — переводим в пиксели растра, а затем
        # МЕРЯЕМ по чистому растру: объявленная рамка — намерение, чернила —
        # факт, и меряться модель обязана против факта.
        k = DPI / 72.0
        boxes = [(x0 * k, y0 * k, x1 * k, y1 * k, lab) for x0, y0, x1, y1, lab in t]
        boxes = _measure(img, boxes, name)
        if len(boxes) != len(t):
            raise SynthError(
                f"{name}: `_measure` вернул {len(boxes)} рамок против {len(t)} "
                f"объявленных — номера блоков поехали, и истина знаков легла "
                f"бы на чужие рамки")
        # Сверка по ЧИСТОЙ странице и по ИЗМЕРЕННЫМ рамкам: старение сюда не
        # входит (текстового слоя после растеризации нет вовсе), поворот тоже
        # (он ниже, и слова пришлось бы вертеть теми же двумя матрицами без
        # всякой пользы для числа).
        сверка = _text_check(raw_words, boxes, said, name)

        # ВТОРАЯ СТОРОНА ТОЙ ЖЕ ПРОВЕРКИ: чернила БЕЗ рамки истины.
        # `_measure` держит одну сторону — рамки истины без чернил под ними
        # нет, и она роняет сборку. Обратной стороны не держало НИЧТО: что
        # нарисовано и не объявлено, стенд молчал об этом, а число выходило
        # здоровым на вид. Так и вышло: `contents_dots` объявлял под словом
        # «CONTENTS» рамку 68 пт при ширине слова 73 пт, и последняя литера
        # оставалась вне истины (пятно 13x18 px = 93 px). Это та же
        # «константа, набранная на глаз», что уже стоила ложного обвинения
        # модели на `formula_next_to_table`; рамка там теперь кладётся по мере
        # (`_text_w`, как в `_caption`), и число упало 93 -> 0.
        #
        # ЧИСЛО, А НЕ ЗАПРЕТ, И НЕ АМНИСТИЯ. Часть чернил вне истины
        # нарисована НАРОЧНО: рамка чертежа по краю листа (17030 px на трёх
        # страницах атласа), линейка под колонтитулом, линейка над сносками,
        # межколонные линейки словаря. Поля «вне замера», как у annopage, тут
        # нет и не будет: там амнистию задаёт ЧУЖАЯ разметка библиотекаря,
        # категорию которой не выражает наш словарь, а здесь рисовали мы —
        # прощать модели свою же рамку значило бы решать за неё, где ей
        # позволено ошибиться. Замер и показывает, что прощать нечего: рамка
        # во весь лист съедает и поле чертежа, и основную надпись, а такую
        # `metrics` не милует ни при какой разметке (счётчик «на объекте вне
        # замера» требует, чтобы рамка накрыла меньше двух артефактов истины).
        # Поэтому здесь считается ВЕЛИЧИНА и печатается в журнал: пятно,
        # выросшее без объявления, видно с первой же сборки.
        left = (cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) < INK).astype(np.uint8)
        for bx in boxes:
            left[max(0, int(bx[1])):int(round(bx[3])),
                 max(0, int(bx[0])):int(round(bx[2]))] = 0
        n_spots, _lbl, stats, _ctr = cv2.connectedComponentsWithStats(left, 8)
        spot = max((stats[j] for j in range(1, n_spots)),
                   key=lambda r: r[cv2.CC_STAT_AREA], default=None)
        undecl = {"пикселей": int(left.sum()), "крупнейшее пятно": None}
        spot_box = None
        if spot is not None:
            sx, sy = int(spot[cv2.CC_STAT_LEFT]), int(spot[cv2.CC_STAT_TOP])
            sw, sh = int(spot[cv2.CC_STAT_WIDTH]), int(spot[cv2.CC_STAT_HEIGHT])
            undecl["крупнейшее пятно"] = {
                "площадь": int(spot[cv2.CC_STAT_AREA]),
                "размер на чистом растре": [sw, sh], "рамка": None}
            spot_box = (sx, sy, sx + sw, sy + sh)

        # Тень переплёта — ДО поворота. Корешок делит РАЗВОРОТ пополам, а не
        # растр: у повёрнутой на 90° страницы он идёт поперёк листа. Прежняя
        # редакция рисовала его после поворота, то есть поперёк настоящего
        # корешка, и поле «корешок» в истине называло не ту координату.
        gutter = None
        if name in B_SPREADS:
            img, gutter = _binding(img, page_seed)

        rot = B_ROTATE.get(name, 0)
        if rot == 90:
            src_h = img.shape[0]
            img = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
            boxes = [(*_rot90_box(b[:4], src_h), b[4]) for b in boxes]
            # Пятно едет теми же двумя преобразованиями, что и рамки истины.
            # Считается оно по ЧИСТОМУ растру (иначе мерило бы крап старения),
            # но лежать обязано в координатах ТОЙ страницы, рядом с которой
            # записано: непреобразованная рамка на `atl_rotated_plate` давала
            # x=1421 при ширине листа 1012, то есть указывала за край листа.
            # Это ровно та беда, которой стоил «корешок», названный не в тех
            # координатах, — и там она чинилась порядком действий, а не
            # оговоркой в комментарии.
            if spot_box is not None:
                spot_box = _rot90_box(spot_box, src_h)
            if gutter is not None:
                gutter = None       # после поворота это уже не координата x

        img, M = _age(img, aging, page_seed)
        h, w = img.shape[:2]
        if M is not None:
            boxes = [(*_clip_box(_xform_box(b[:4], M), w, h), b[4])
                     for b in boxes]
            if spot_box is not None:
                spot_box = _clip_box(_xform_box(spot_box, M), w, h)
        if spot_box is not None:
            undecl["крупнейшее пятно"]["рамка"] = [round(v, 1) for v in spot_box]
        thin = [b for b in boxes if b[2] - b[0] < 2 or b[3] - b[1] < 2]
        if thin:
            raise SynthError(
                f"{name}: после старения рамка истины схлопнулась: "
                f"{[(round(v,1) for v in t[:4]) for t in thin[:2]]}")
        page = out.new_page(width=w * PT, height=h * PT)
        ok, enc = cv2.imencode(".png", img)
        page.insert_image(page.rect, stream=enc.tobytes())

        # ЗНАКИ ЛОЖАТСЯ В БЛОК ПО РАЗРЯДУ ЯРЛЫКА, А НЕ ПО ЯРЛЫКУ.
        # `content` заполняется только у разрядов «текст» и «служебное» — у
        # них знаки И ЕСТЬ продукт первого уровня. У АРТЕФАКТА `content`
        # остаётся null, и это ЗНАЧЕНИЕ, а не пропуск: артефакт в VLM не
        # уезжает текстом ни в одном режиме подачи (`doc/feed.py`: и `crop`, и
        # `masked_page` шлют его картинкой либо не шлют вовсе), его знаки —
        # ответ ВТОРОГО уровня, и эталон к ним лежит сбоку, в
        # `meta["истина артефактов"]`, связанный с блоком по его номеру.
        # Схему `Block` это не трогает: у блока нет своего `meta`, и дописать
        # шестое поле в словарь блока значило бы уронить `Page.from_json`.
        from . import policy
        blocks, art_truth = [], {}
        нет_знаков = []
        for j, b in enumerate(boxes):
            rec = said.get(j, {})
            роль = policy.role(b[4])
            blk = {"block_id": j, "box": [round(v, 1) for v in b[:4]],
                   "label": b[4], "score": None, "order": j,
                   "content": None, "kind": "none"}
            if роль == "артефакт":
                if rec:
                    art_truth[str(j)] = rec
            else:
                txt = rec.get("текст")
                if txt:
                    blk["content"] = txt
                    blk["kind"] = "text"
                else:
                    нет_знаков.append(f"{b[4]}#{j}")
            blocks.append(blk)
        for b in blocks:
            counts[b["label"]] = counts.get(b["label"], 0) + 1
        знаков = sum(len(b["content"]) for b in blocks if b["content"])
        слов = sum(len(b["content"].split()) for b in blocks if b["content"])
        с_текстом = sum(1 for b in blocks if b["content"])
        знаки = {"знаков": знаков, "слов": слов, "блоков с текстом": с_текстом,
                 "текстовых блоков без знаков": len(нет_знаков),
                 "какие без знаков": нет_знаков[:6],
                 "таблиц с сеткой": sum(1 for v in art_truth.values()
                                        if "ячейки" in v),
                 "ячеек": sum(v["строк"] * v["столбцов"]
                              for v in art_truth.values() if "ячейки" in v)}
        with open(os.path.join(truth_dir, f"{i:04d}.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"index": i, "width": w, "height": h, "dpi": DPI,
                       "blocks": blocks, "raw": None,
                       "meta": {"случай": name, "книга": book,
                                "старение": aging,
                                "зерно": page_seed, "поворот": rot,
                                "корешок": gutter,
                                # Пикселей — по ЧИСТОМУ растру, до старения и
                                # поворота: старение сыплет крап, и по нему
                                # число мерило бы шум, а не забытую рамку.
                                # Размер пятна — там же, на чистом растре,
                                # чтобы число не менялось от перекоса; рамка —
                                # уже в координатах ЭТОЙ страницы, чтобы по
                                # ней можно было пятно найти глазом.
                                "чернил вне истины": undecl,
                                # ПРИЗНАК, А НЕ ДОГАДКА. `subset.py` и
                                # `books score` читают `текст размечен`
                                # тремя ответами: «да», «нет», «не сказано»,
                                # и последнее — не то же, что «нет». До сих
                                # пор синтетика не говорила НИЧЕГО, и метрика
                                # по знакам обязана была молчать. Ставится по
                                # ФАКТУ: «да» только когда знаки есть у всех
                                # блоков разряда «текст» и «служебное»; одна
                                # молчащая дыра — и признак честно «нет».
                                "текст размечен": not нет_знаков,
                                "истина знаков": знаки,
                                "сверка с текстовым слоем": сверка,
                                # Истина АРТЕФАКТА — сбоку и по номеру блока.
                                # Для таблицы это строки, столбцы и текст
                                # каждой ячейки: без них второй уровень
                                # (таблица -> HTML) проверить нечем вовсе, а
                                # «обвёл верно» про таблицу не говорит ничего.
                                "истина артефактов": art_truth}},
                      f, ensure_ascii=False)
        pages.append({"случай": name, "страница": i, "размер": [w, h],
                      "блоков": len(blocks), "поворот": rot,
                      "разворот": name in B_SPREADS,
                      "чернил вне истины": undecl,
                      "истина знаков": знаки,
                      "сверка с текстовым слоем": сверка})
        big = undecl["крупнейшее пятно"]
        log(f"  {i:2d} {name:22s} {w}x{h}, блоков {len(blocks)}"
            + ("  (разворот)" if name in B_SPREADS else "")
            + (f"  (повёрнут {rot}°)" if rot else "")
            + f", вне истины {undecl['пикселей']} px"
            + (f" (пятно {big['размер на чистом растре'][0]}"
               f"x{big['размер на чистом растре'][1]}"
               f" = {big['площадь']} px)" if big else "")
            + f"; знаков {знаки['знаков']}, слов {знаки['слов']} "
              f"в {знаки['блоков с текстом']} блоках"
            + (f", БЕЗ ЗНАКОВ {знаки['текстовых блоков без знаков']} "
               f"({', '.join(знаки['какие без знаков'])})"
               if нет_знаков else "")
            + (f", ячеек {знаки['ячеек']} в {знаки['таблиц с сеткой']} табл."
               if знаки["таблиц с сеткой"] else "")
            + f"; слов вне истины {сверка['вне истины']}"
            + (f" {сверка['слова вне истины']}" if сверка["вне истины"] else "")
            + (f", НЕТ В СЛОЕ {сверка['нет в слое']}"
               if сверка["нет в слое"] else "")
            + (f", НЕОБЪЯСНЁННЫХ {сверка['необъяснённых']}"
               if сверка["необъяснённых"] else "")
            + (f" {сверка['примеры расхождений']}"
               if сверка["примеры расхождений"] else "")
            + f", призраков {сверка['призраков']}"
            + (f", выносок {сверка['выносок']}" if сверка["выносок"] else ""))

    # Имя по КНИГЕ, а не «synth.pdf» во всех каталогах разом: шесть книг с
    # одинаковым именем файла путаются при первом же взгляде на каталог.
    pdf = os.path.join(out_dir, f"{book}.pdf")
    # `no_new_id=True` — И ЭТО НЕ УКРАШЕНИЕ. Без него MuPDF при каждом
    # сохранении ставит в `/ID` случайные байты, и одна и та же команда с одним
    # зерном давала РАЗНЫЕ файлы: замер — два прогона `books synth --book
    # slovar` подряд, размер тот же до байта, различий 51 байт, и все 51 в
    # `/ID`. Истина при этом воспроизводилась точно, пофайлово.
    #
    # Цена этих 51 байта. `bench/README.md` обещает, что стенды «собираются
    # заново одной командой побайтово теми же», и на этом обещании держится
    # то, что стенды не версионируются (472 МБ у annopage). А `books html`
    # сверяет sha256 книги со слепком детекции и отказывается собирать при
    # расхождении — то есть пересборка стенда молча обесценивала КАЖДЫЙ
    # прежний прогон по нему, и узнать об этом можно было только отказом
    # сборки. Проверено: с этим ключом два прогона дают побайтово равные
    # файлы; `reproducible=True` (соседний ключ pymupdf) НЕ даёт.
    out.save(pdf, garbage=3, deflate=True, no_new_id=True)
    out.close()

    # СЛЕПОК ИСТИНЫ. Без него правка любого рисовальщика меняет истину молча,
    # и вчерашнее число становится несравнимым с сегодняшним, не сказав об
    # этом ни слова. `books score` сверяет по нему, что истина и вывод модели
    # про один PDF; здесь дополнительно записано, ЧЕМ эта истина построена.
    def сумма(ключ, поле):
        return sum(pp[ключ][поле] for pp in pages)
    итог = {"знаков": сумма("истина знаков", "знаков"),
            "слов": сумма("истина знаков", "слов"),
            "блоков с текстом": сумма("истина знаков", "блоков с текстом"),
            "текстовых блоков без знаков":
                сумма("истина знаков", "текстовых блоков без знаков"),
            "таблиц с сеткой": сумма("истина знаков", "таблиц с сеткой"),
            "ячеек": сумма("истина знаков", "ячеек"),
            "слов вне истины": сумма("сверка с текстовым слоем", "вне истины"),
            "нет в слое": сумма("сверка с текстовым слоем", "нет в слое"),
            "необъяснённых": сумма("сверка с текстовым слоем", "необъяснённых"),
            "призраков": сумма("сверка с текстовым слоем", "призраков"),
            "выносок": сумма("сверка с текстовым слоем", "выносок"),
            "слов в текстовом слое": сумма("сверка с текстовым слоем",
                                           "слов в слое")}

    src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "synth.py")
    man = {"книга": book, "о книге": getattr(mod, "ABOUT", ""),
           "страниц": len(pages), "зерно": seed, "старение": aging,
           "генератор": {"файл": "synth.py", "sha256": _sha256(src),
                         "коммит": _commit(),
                         "случаи": names, "книга": book,
                         "sha256 книги": _sha256(mod.__file__),
                         "ярлыки-догадки": sorted(GUESSED),
                         "INK": INK, "KEEP": KEEP, "GROW": GROW},
           "ручки": knobs.snapshot() if hasattr(knobs, "snapshot") else None,
           "параметры старения": AGING[aging],
           "шрифты": {os.path.basename(FONT): _sha256(FONT),
                      os.path.basename(FONT_MONO): _sha256(FONT_MONO)},
           "pdf": os.path.basename(pdf), "sha256 pdf": _sha256(pdf),
           "блоков по ярлыкам": counts, "истина знаков": итог,
           "страницы": pages}
    with open(os.path.join(out_dir, "manifest.json"), "w",
              encoding="utf-8") as f:
        json.dump(man, f, ensure_ascii=False, indent=1)
    log(f"страниц {len(pages)}, блоков истины {sum(counts.values())} "
        f"({', '.join(f'{k} {v}' for k, v in sorted(counts.items()))})")
    # ВЕЛИЧИНА, А НЕ СЛОВО «ГОТОВО». Каждое из этих чисел уже ловило беду,
    # которую слово «готово» пропустило бы: «блоков с текстом» меньше числа
    # текстовых блоков значит молчащую дыру в истине; «нет в слое» больше нуля
    # значит истину богаче бумаги; «слов вне истины» больше нуля значит кусок
    # страницы, не объявленный вовсе (номера строк каталога — как раз он).
    log(f"истина знаков: {итог['знаков']} знаков, {итог['слов']} слов "
        f"в {итог['блоков с текстом']} блоках"
        + (f"; БЕЗ ЗНАКОВ текстовых блоков {итог['текстовых блоков без знаков']}"
           if итог["текстовых блоков без знаков"] else "")
        + f"; таблиц с сеткой {итог['таблиц с сеткой']}, "
          f"ячеек {итог['ячеек']}")
    log(f"слов, нарисованных вне всякой рамки истины: "
        f"{итог['слов вне истины']} из {итог['слов в текстовом слое']} "
        f"в текстовом слое")
    log(f"сверка с текстовым слоем: нет в слое {итог['нет в слое']}, "
        f"необъяснённых {итог['необъяснённых']}, "
        f"призраков повторной заливки {итог['призраков']}, "
        f"точечных выносок {итог['выносок']}")
    log(f"{pdf} ({os.path.getsize(pdf)/1e6:.1f} МБ), истина в {truth_dir}")
    return man
