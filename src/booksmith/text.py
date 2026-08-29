"""Метрика чтения: сверка прочитанного текста с известным текстом.

Прежние числа качества чтения мерились против вывода Mistral OCR — то есть
против другой модели, а не против известного текста, — и потому недействительны
все до одного (шапка `docs/ocr-notes.md`). Этот файл существует, чтобы такого
больше не вышло: он сверяет ответ модели с ИСТИНОЙ и умеет провалиться.

ЧТО ОН МЕРЯЕТ И ЧЕГО НЕ МЕРЯЕТ. Он меряет ЗНАКИ и АДРЕСА ЯЧЕЕК. Он не меряет
ни рамки (это `metrics.py`), ни доезжаемость смысла до второго уровня (это
`fitness.py`). Разделение не стилистическое: одно сводное число лечится
подгонкой одной беды за счёт другой и потому ничего не говорит.

ЧЕТЫРЕ РАЗНЫХ НУЛЯ, И ИХ НЕЛЬЗЯ ПУТАТЬ — ради них половина кода ниже.

  * `content` пуст, ПОТОМУ ЧТО АРТЕФАКТ. Истина говорит «здесь текста нет,
    здесь картинка». Молчание модели тут — правильный ответ, а не пропуск.
  * `content` пуст, ПОТОМУ ЧТО МОДЕЛЬ НЕ ОТВЕТИЛА. Это беда, и самая дешёвая
    для модели: не ответив, она получает CER 0 на отвеченном подмножестве.
    Поэтому книжный CER считает неотвеченный блок ПОЛНОСТЬЮ неверным, а CER
    «на отвеченных» печатается ОТДЕЛЬНОЙ строкой рядом.
  * `content` пуст В ИСТИНЕ на текстовом блоке — истина не размечена. Сверять
    нечем; такой блок в знаменатель не идёт и печатается своей строкой. Это
    ноль от проверки, а не ноль чтения.
  * блок не сопоставлен ВОВСЕ. Пары нет, и знать, что модель ответила, нельзя.
    Печатается числом и входит в книжный CER полной длиной истины.

ПО ЧЕМУ СВОДЯТСЯ БЛОКИ. По якорю, если он есть; иначе по геометрии.

Якорь — номер блока истины, который модель несёт при себе (`meta["якорь"]`,
`anchor`, `truth_block_id` — на блоке или в его `meta`). Второй уровень читает
ВЫРЕЗКУ конкретного блока, поэтому якорь у него есть по построению, и это
единственный способ сопоставления, который не врёт.

Геометрия врать умеет: две колонки текста рядом, рамки почти одинаковые, и
пара уезжает к соседу — CER тогда меряет не чтение, а сопоставление. Поэтому
ДОЛЯ СОПОСТАВЛЕННЫХ И СПОСОБ, КАКИМ ОНИ СВЕДЕНЫ, ПЕЧАТАЮТСЯ ВСЕГДА: без них
CER 0.02 по двум блокам из сорока читается как «модель читает отлично».

Затвор совпадения по геометрии берётся ГОТОВЫЙ — `metrics.matches`
(двустороннее покрытие 0.75 с допуском 6 пикселей по краю). Свой порог здесь
означал бы, что «нашлась рамка» в отчёте контуров и «сведён блок» в отчёте
чтения — про разное, а объяснять эту разницу будет некому.

СРЕДНЯЯ СТУПЕНЬ — НОМЕР БЛОКА, СВЕРЕННЫЙ ГЕОМЕТРИЕЙ. Когда ответ собран по
той же разметке (а так и будет: второй уровень заполняет `content` в тех же
блоках), `block_id` совпадает с обеих сторон. Верить ему на слово нельзя —
номера могли совпасть случайно, — поэтому маршрут включается, только если
номера совпали ПОГОЛОВНО и каждая пара при этом проходит геометрический
затвор. Проверенный номер, а не вера в номер.

ГРАНИЦА НОРМАЛИЗАЦИИ ОБЪЯВЛЕНА И УЕЗЖАЕТ В ОТВЕТ. Замер из
`docs/lessons-from-deleted-code.md` на шести книгах, 32 634 ячейки: NFKC и
пробелы снимают 127 расхождений при вреде 0, регистр 90 при 0, тире/дефис/
минус 376 при 0, десятичная запятая 42 при 0, хвостовая пунктуация 147 при 0.
ДАЛЬШЕ ГРАНИЦА: головная пунктуация снимает 139, но вредит 4 раза (`.850`
== `850`), вся пунктуация — 504 при вреде 108 (`6—2` == `6,2`). Двойники
кириллица/латиница отвергнуты замером: со ступенью 14 находок из 29 (лифт
2.70), без неё 16 из 29 (лифт 3.06) — подмена двойника В ЭТОМ корпусе есть
сама ошибка распознавания, а не разнопись.

ПЕРЕНОСЫ МЕТРИКА НЕ СКЛЕИВАЕТ. Склейка переносов — правило вывода МОДЕЛИ, и
если её делать при сличении, то модель, склеившая там, где склеивать было
нельзя, получит те же числа, что и правильная. Батарея это и проверяет пробой
«склеены переносы».

СДВИГ СТРОКИ В ТАБЛИЦЕ. CLAUDE.md называет его ведущим видом незаметной порчи,
и «≠» его не видит по построению. Здесь он виден по построению: ячейки
сверяются ПО АДРЕСУ (строка, столбец), а не мешком. Замер на примере ниже:
мешок ячеек до и после сдвига ОДИН И ТОТ ЖЕ (совпадает как Counter), а доля
совпавших по адресу падает 0.89 -> 0.33, ячеек 8 из 9 против 3 из 9.

ЧЕМ ЭТО ПРОВЕРЕНО, ПОКА ИСТИНЫ ТЕКСТА НЕТ. Истину текста пишут отдельно; здесь
она ещё не появилась, и потому замеры сделаны на крошечном рукописном примере
(две страницы, четыре текстовых блока, таблица 3x3, рисунок-приманка,
неразмеченный колонтитул) во временном каталоге, в стенд он не положен:

  * батарея из 25 проб — НЕ ПОЙМАННЫХ ПОРЧ 0, «нет данных» ни одной;
  * батарея умеет и провалиться: если нормализации разрешить склеивать
    переносы (запрещённая заплатка), она печатает «не пойманных порч: 2»;
  * расстояние сверено с прямым DP на 700 случайных парах — расхождений 0;
  * на настоящем `bench/slovar/truth` (13 страниц, 523 блока) метрика
    печатает не «CER 0», а «текст НЕ РАЗМЕЧЕН... это не ноль чтения»: 520
    блоков без истины, 3 артефакта-приманки, сопоставлено 523 из 523.
"""
import copy
import json
import os
import re
import unicodedata
from html.parser import HTMLParser

from . import metrics, policy


class TextError(RuntimeError):
    pass


# ------------------------------------------------------------ нормализация
#
# Уровень — ЗНАЧЕНИЕ, а не зашитое поведение: он уезжает в возвращаемый словарь,
# иначе два замера разных дней несравнимы и об этом никто не узнает.
NORM = "граница"

_DASHES = "‐‑‒–—―−­-"
_TAIL = ".,;:!?…"
_WS = re.compile(r"\s+")
_DEC = re.compile(r"(?<=\d),(?=\d)")

NORM_STEPS = {
    "нет": [],
    "граница": ["NFKC и пробелы", "регистр", "тире/дефис/минус",
                "десятичная запятая", "хвостовая пунктуация"],
}
# Печатается рядом с числом. Иначе «CER 0.03» через месяц будет означать что
# угодно, и первым предложением будет «а давайте снимем ещё и пунктуацию».
NORM_REFUSED = ("головная пунктуация (снимает 139, вредит 4: '.850' == '850'), "
                "вся пунктуация (504 при вреде 108: '6—2' == '6,2'), "
                "двойники кир/лат (лифт 2.70 против 3.06 без неё)")


def normalize(s: str, level: str = NORM) -> str:
    """Привести строку к виду, в котором две записи одного считаются равными.

    Ступени ровно те, у которых замер показал вред 0. Ни одной сверх.
    """
    if level not in NORM_STEPS:
        raise TextError(f"уровень нормализации {level!r} не объявлен; "
                        f"есть {sorted(NORM_STEPS)}")
    if s is None:
        return ""
    if level == "нет":
        return s
    s = unicodedata.normalize("NFKC", s)
    s = _WS.sub(" ", s).strip()
    s = s.casefold()
    s = "".join("-" if c in _DASHES else c for c in s)
    s = _DEC.sub(".", s)
    return s.rstrip(_TAIL)


def norm_note(level: str = NORM) -> dict:
    return {"уровень": level, "ступени": NORM_STEPS[level],
            "не снимаем": NORM_REFUSED}


# --------------------------------------------------------------- расстояние
#
# Расстояние Левенштейна, точное, битовой строкой (Майерс, 1999): столбец
# матрицы держится двумя целыми, и работа идёт словами по 64 бита разом.
#
# ЗАЧЕМ, ЧИСЛОМ. Прямой DP — 4 млн клеток на паре абзацев в 2000 знаков, а
# страниц шестьсот. Замер на 500 парах по 869 знаков с порчей 5%: полосой
# Укконена 30.5 с, битовой строкой 1.04 с — те же расстояния до единицы на
# 700 случайных парах (проверено против прямого DP, расхождений 0). Медленная
# метрика не гоняется, а негоняемая метрика ничего не меряет.
#
# Бюджет всё равно объявлен: пара строк по 100 тысяч знаков — это 10^10
# клеток и полминуты на одну пару. За бюджетом расстояние честно называется
# ОЦЕНКОЙ СВЕРХУ и печатается отдельной строкой отчёта. Оценка, выданная за
# точную, сделала бы CER непадающим ровно на самых длинных блоках.
_BUDGET = 300_000_000     # клеток на одну пару, около секунды счёта


def _myers(a, b):
    """Точное расстояние; маска шириной в `a`, проход по `b`."""
    m = len(a)
    peq = {}
    for i, c in enumerate(a):
        peq[c] = peq.get(c, 0) | (1 << i)
    full = (1 << m) - 1
    vp, vn, score, top = full, 0, m, 1 << (m - 1)
    for c in b:
        eq = peq.get(c, 0)
        xv = eq | vn
        xh = (((eq & vp) + vp) ^ vp) | eq
        hp = vn | (full & ~(xh | vp))
        hn = vp & xh
        if hp & top:
            score += 1
        if hn & top:
            score -= 1
        hp = ((hp << 1) | 1) & full
        hn = (hn << 1) & full
        vp = (hn | (full & ~(xv | hp))) & full
        vn = hp & xv
    return score


def _dist(a, b):
    """(расстояние, точно ли). Второе поле — не украшение: см. бюджет выше."""
    if a == b:
        return 0, True
    n, m = len(a), len(b)
    if not a or not b:
        return max(n, m), True
    if n * m > _BUDGET:
        return max(n, m), False
    if n > m:
        a, b = b, a          # расстояние симметрично, маска — по короткой
    return _myers(a, b), True


# ------------------------------------------------------------------ таблицы
#
# Структурная истина таблицы приходит в `meta` блока. Формат принимаем в двух
# видах — списком строк и списком адресованных ячеек, — но НЕ УГАДЫВАЕМ: если
# в `meta` есть табличные ключи, а разобрать их нельзя, это ошибка вслух.
# Молчаливый пропуск дал бы «ячеек 0» — ноль, читаемый как «таблиц нет».
_CELLS_KEYS = ("ячейки", "cells", "строки", "rows")


def _cells_from(obj):
    """{(строка, столбец): текст} из списка строк или списка адресов."""
    if isinstance(obj, dict):
        for k in _CELLS_KEYS:
            if k in obj:
                return _cells_from(obj[k])
        return None
    if not isinstance(obj, list) or not obj:
        return None
    if all(isinstance(r, list) for r in obj):
        return {(i, j): ("" if c is None else str(c))
                for i, r in enumerate(obj) for j, c in enumerate(r)}
    if all(isinstance(c, dict) for c in obj):
        out = {}
        for c in obj:
            r = c.get("строка", c.get("row"))
            j = c.get("столбец", c.get("col", c.get("column")))
            t = c.get("текст", c.get("text", ""))
            if r is None or j is None:
                return None
            out[(int(r), int(j))] = "" if t is None else str(t)
        return out
    return None


SIDE_KEYS = ("истина артефактов", "artefact truth")


def page_side(page) -> dict:
    """Истина артефактов, лежащая СБОКУ у страницы и связанная по номеру блока.

    Мост, которого не было, и его отсутствие стоило прибора целиком. `synth`
    кладёт сетку таблицы в `meta` СТРАНИЦЫ ключом-строкой номера блока —
    ровно по правилу проекта «всё наблюдённое живёт сбоку и связано с блоком
    по его номеру», — а `_truth_grid` искала её в `meta` БЛОКА, которого у
    `Block` нет вовсе (`models/base.py`: block_id, box, label, score, order,
    content, kind — и всё). Замер на свежем `katalog`: `books synth` печатал
    «таблиц с сеткой 13, ячеек 3982», а `text.report` в ту же секунду —
    «структурной истины в этой книге нет». Два верных модуля и ни одной
    таблицы между ними.

    Ключ приводится к строке НАРОЧНО: json делает ключи строками, а в памяти
    номер блока целый, и `side[3]` промахивался бы по `side["3"]` молча.
    """
    m = (page.get("meta") or {}) if isinstance(page, dict) else {}
    for k in SIDE_KEYS:
        v = m.get(k)
        if isinstance(v, dict):
            return {str(kk): vv for kk, vv in v.items()}
    return {}


def _truth_grid(b, side=None):
    """Сетка истины таблицы, или None — таблица без структурной истины.

    `side` — истина артефактов страницы (см. `page_side`). Сетка ищется и в
    `meta` блока, и сбоку: первое на случай разметки, пришедшей с сеткой
    внутри блока, второе — то, что даёт наш стенд.
    """
    m = b.get("meta") or {}
    if not m and side:
        m = side.get(str(b.get("block_id")), {}) or {}
    src = None
    for k in ("таблица", "table", "структура", "structure"):
        if isinstance(m.get(k), (dict, list)):
            src = m[k]
            break
    if src is None:
        if not any(k in m for k in _CELLS_KEYS):
            return None
        src = m
    g = _cells_from(src)
    if g is None:
        raise TextError(
            f"блок {b.get('block_id')}: в meta есть табличные ключи "
            f"{[k for k in m if k in _CELLS_KEYS or k in ('таблица','table')]}, "
            f"а сетка из них не читается. Пропустить это молча значит "
            f"напечатать «ячеек 0» там, где ячейки есть.")
    return g


class _TableHTML(HTMLParser):
    """Сетка из HTML-таблицы: tr/td/th, colspan и rowspan.

    Сквозная ячейка занимает все свои адреса — иначе сдвиг строки в таблице со
    сквозной шапкой сравнивался бы с пустотой и «падал» бы по другой причине,
    чем объявлено пробой.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.cells, self.buf = {}, None
        self.r, self.c, self.busy = -1, 0, {}
        self.span = (1, 1)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "tr":
            self._close()
            self.r += 1
            self.c = 0
        elif tag in ("td", "th"):
            self._close()
            if self.r < 0:
                self.r = 0
            try:
                cs = max(1, int(a.get("colspan", 1)))
                rs = max(1, int(a.get("rowspan", 1)))
            except ValueError:
                cs = rs = 1
            self.span = (rs, cs)
            self.buf = []
        elif tag == "br" and self.buf is not None:
            self.buf.append(" ")

    def handle_endtag(self, tag):
        if tag in ("td", "th", "tr", "table"):
            self._close()

    def handle_data(self, d):
        if self.buf is not None:
            self.buf.append(d)

    def _close(self):
        if self.buf is None:
            return
        text = "".join(self.buf)
        self.buf = None
        while self.busy.get((self.r, self.c)):
            self.c += 1
        rs, cs = self.span
        for i in range(rs):
            for j in range(cs):
                self.busy[(self.r + i, self.c + j)] = True
                self.cells[(self.r + i, self.c + j)] = text
        self.c += cs

    def close(self):
        self._close()
        super().close()


def _html_grid(s):
    """Сетка из ответа модели, или None — разметки таблицы в ответе нет."""
    if not s or "<t" not in s.lower():
        return None
    p = _TableHTML()
    try:
        p.feed(s)
        p.close()
    except Exception:
        return None
    return p.cells or None


def _grid_html(g):
    """Сетка обратно в HTML. Нужна батарее: порчу удобно делать над сеткой,
    а метрика обязана получить ровно то, что получала бы от модели."""
    if not g:
        return "<table></table>"
    rows = max(r for r, _ in g) + 1
    cols = max(c for _, c in g) + 1
    out = ["<table>"]
    for r in range(rows):
        out.append("<tr>")
        for c in range(cols):
            out.append("<td>" + g.get((r, c), "") + "</td>")
        out.append("</tr>")
    out.append("</table>")
    return "".join(out)


def _shape(g):
    if not g:
        return (0, 0)
    return (max(r for r, _ in g) + 1, max(c for _, c in g) + 1)


# ------------------------------------------------------------- сопоставление
_ANCHOR_RE = re.compile(r"^p(\d+)-b(\d+)$")


def _anchor_num(v):
    """Номер блока из якоря. Понимает и число, и метку проекта `p0042-b17`.

    Метку понимать ОБЯЗАТЕЛЬНО: ровно её пишет сборщик книги (`doc/html.py`,
    `anchor_of`), ровно она стоит в `blocks.json` и ровно ею второй уровень
    находит, что заменять. Прежняя редакция принимала только число и на
    настоящем выводе конвейера падала `TextError`; сопоставление по якорю
    работало ноль раз из ноль, а всё сводилось геометрией — то есть
    объявленная первой ступень не выполнялась никогда.

    Номер СТРАНИЦЫ отбрасывается намеренно: сопоставление идёт внутри уже
    выбранной страницы, и `p0042-b17` на странице 42 значит блок 17. Если
    номер страницы разойдётся с той, где якорь найден, это поймает ступень
    «якорь в никуда» — она уже есть.
    """
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, str):
        t = v.strip()
        m = _ANCHOR_RE.match(t)
        if m:
            return int(m.group(2))
        try:
            return int(t)
        except ValueError:
            return None
    return None


def _anchor(b):
    """Номер блока истины, объявленный самим ответом, или None."""
    for src in (b, b.get("meta") or {}):
        if not isinstance(src, dict):
            continue
        for k in ("якорь", "anchor", "truth_block_id", "истина_block_id"):
            v = src.get(k)
            if v is not None:
                n = _anchor_num(v)
                if n is None:
                    raise TextError(
                        f"якорь {v!r} не разобран: ни число, ни постраничная "
                        f"метка вида p0042-b17. Сопоставить по нему нельзя, а "
                        f"тихо перейти на геометрию значит соврать про способ")
                return n
    return None


def _box(b):
    v = b.get("box")
    if not v or len(v) != 4:
        return None
    return tuple(float(x) for x in v)


def _match(tb, pb):
    """Пары (индекс истины, индекс ответа, чем сведены) и остатки.

    Порядок ступеней: якорь -> поголовно совпавший номер, сверенный
    геометрией -> геометрия. Каждая ступень называется в отчёте своим именем:
    доля сопоставленных 100% по якорю и 100% по геометрии — разной цены числа.
    """
    pairs, dead = [], 0
    t_by_id = {}
    for i, b in enumerate(tb):
        t_by_id.setdefault(b.get("block_id"), i)
    used_t, used_p = set(), set()

    anchored = [(j, _anchor(b)) for j, b in enumerate(pb)]
    for j, a in anchored:
        if a is None:
            continue
        i = t_by_id.get(a)
        if i is None or i in used_t:
            dead += 1          # якорь в никуда: громкая беда, не тихий промах
            used_p.add(j)
            continue
        used_t.add(i)
        used_p.add(j)
        pairs.append((i, j, "якорь"))

    # Поголовный номер — только когда якорей нет ВОВСЕ: смешивать объявленный
    # якорь с угаданным номером значит потерять, чем сведён блок.
    if not any(a is not None for _, a in anchored) and len(tb) == len(pb):
        ids_t = [b.get("block_id") for b in tb]
        ids_p = [b.get("block_id") for b in pb]
        if None not in ids_t and sorted(ids_t) == sorted(ids_p) \
                and len(set(ids_t)) == len(ids_t):
            p_by_id = {b.get("block_id"): j for j, b in enumerate(pb)}
            cand = []
            for i, b in enumerate(tb):
                j = p_by_id[b["block_id"]]
                x, y = _box(b), _box(pb[j])
                # Номер верим ТОЛЬКО сверенный: совпасть номера могут и
                # случайно, а рамки на другой книге — нет.
                if x is None or y is None or not metrics.matches(x, y):
                    cand = None
                    break
                cand.append((i, j, "номер"))
            if cand:
                return cand, [], [], dead

    # Геометрия: жадно по IoU сверху вниз. Сортировка с отрывом по номерам —
    # чтобы два прогона на одних данных давали одни пары.
    cand = []
    for i, b in enumerate(tb):
        if i in used_t:
            continue
        x = _box(b)
        if x is None:
            continue
        for j, p in enumerate(pb):
            if j in used_p:
                continue
            y = _box(p)
            if y is None or not metrics.matches(x, y):
                continue
            cand.append((-metrics.iou(x, y), i, j))
    for _, i, j in sorted(cand):
        if i in used_t or j in used_p:
            continue
        used_t.add(i)
        used_p.add(j)
        pairs.append((i, j, "геометрия"))
    lost_t = [i for i in range(len(tb)) if i not in used_t]
    lost_p = [j for j in range(len(pb)) if j not in used_p]
    return pairs, lost_t, lost_p, dead


# ------------------------------------------------------------------- замер
def _load(d):
    """Страницы каталога, ключ — индекс страницы.

    Свой, а не `metrics._load`: там ошибка зовётся MetricError и говорит про
    рамки, здесь беды другие. Проверка та же и по той же причине — каталог с
    чужими json'ами дал бы правдоподобное число ни о чём.
    """
    if not os.path.isdir(d):
        raise TextError(f"нет каталога {d}")
    out = {}
    for name in sorted(os.listdir(d)):
        if name.endswith(".json") and name not in ("run.json", "manifest.json"):
            with open(os.path.join(d, name), encoding="utf-8") as f:
                p = json.load(f)
            if "blocks" not in p or "index" not in p:
                raise TextError(f"{name}: не похоже на страницу разметки")
            out[int(p["index"])] = p
    if not out:
        raise TextError(f"в {d} нет страниц")
    return out


def measure(truth_dir: str, pages_dir: str, norm: str = NORM) -> dict:
    """Сверить прочитанное с истиной. Числа — в возвращаемом словаре."""
    T, P = _load(truth_dir), _load(pages_dir)
    # Сверка книги и растра — готовая, из метрики контуров: беда та же (истина
    # одной книги против ответа другой; координаты в разных растрах), и ответ
    # обязан быть тот же. Берётся через getattr нарочно: это внутренние имена
    # чужого файла, и если их однажды переименуют, метрика чтения обязана
    # сказать «НЕ СВЕРЕНО» вслух, а не упасть AttributeError в стороне от дела
    # и не промолчать.
    def _check(name, *a):
        fn = getattr(metrics, name, None)
        if fn is None:
            return f"{name} НЕ СВЕРЕНО: проверки нет в metrics.py"
        return fn(*a)

    note = f"{_check('_same_book', truth_dir, pages_dir)}; " \
           f"{_check('_same_raster', T, P)}"
    res = measure_pages(T, P, norm=norm)
    res["книга"] = note
    return res


def measure_pages(T: dict, P: dict, norm: str = NORM) -> dict:
    """То же, но над уже загруженными страницами: этим кормится батарея."""
    txt = {"блоков": 0, "знаков истины": 0, "слов истины": 0,
           "расстояние знаков": 0, "расстояние слов": 0,
           "расстояние знаков (отвеченные)": 0,
           "знаков истины (отвеченные)": 0,
           "без ответа": 0, "не сопоставлено": 0, "истина пуста": 0,
           "оценено сверху": 0}
    tab = {"блоков": 0, "ячеек": 0, "совпало ячеек": 0, "знаков ячеек": 0,
           "расстояние ячеек": 0, "без ответа": 0, "отдана текстом": 0,
           "структура не разобрана": 0, "сетка разошлась": 0,
           "не сопоставлено": 0}
    bait = {"артефактов": 0, "прочитано": 0, "промолчано": 0,
            "не сопоставлено": 0}
    mt = {"блоков истины": 0, "по якорю": 0, "по номеру": 0, "по геометрии": 0,
          "не сопоставлено (истина)": 0, "лишних в ответе": 0,
          "якорь в никуда": 0, "без рамки в ответе": 0}
    pg = {"истина": len(T), "ответ": len(P), "без ответа": 0, "лишних": 0}
    unmarked = 0          # истина не размечена — НЕ ноль чтения
    unmarked_answered = 0
    kind_bad = 0
    per_block = []

    pg["лишних"] = len(set(P) - set(T))
    for i in sorted(T):
        t = T[i]
        p = P.get(i)
        tb = t["blocks"]
        side = page_side(t)
        mt["блоков истины"] += len(tb)
        if p is None:
            # Страницы нет в ответе. Её блоки не «прочитаны на ноль», их не
            # сопоставили вовсе — и это отдельная строка отчёта.
            pg["без ответа"] += 1
            pairs, lost_t, lost_p, dead = [], list(range(len(tb))), [], 0
            pb = []
        else:
            pb = p["blocks"]
            pairs, lost_t, lost_p, dead = _match(tb, pb)
        mt["якорь в никуда"] += dead
        mt["лишних в ответе"] += len(lost_p)
        mt["без рамки в ответе"] += sum(1 for b in pb if _box(b) is None)
        for _, _, how in pairs:
            mt["по " + {"якорь": "якорю", "номер": "номеру",
                        "геометрия": "геометрии"}[how]] += 1

        got = {i_: (j_, how) for i_, j_, how in pairs}
        for i_, b in enumerate(tb):
            j_, how = got.get(i_, (None, None))
            ans = pb[j_] if j_ is not None else None
            rec = {"страница": i, "блок": b.get("block_id"),
                   "ярлык": b.get("label"), "сведён": how or "нет пары"}
            grid = _truth_grid(b, side)
            content = b.get("content")
            role = policy.role(b["label"])

            if grid is not None:                       # ---------- таблица
                tab["блоков"] += 1
                rec["разряд"] = "таблица"
                cells = {k: normalize(v, norm) for k, v in grid.items()}
                chars = sum(len(v) for v in cells.values())
                tab["ячеек"] += len(cells)
                tab["знаков ячеек"] += chars
                mg = None
                if ans is None:
                    tab["не сопоставлено"] += 1
                    mt["не сопоставлено (истина)"] += 1
                else:
                    mg = _html_grid(ans.get("content"))
                    if mg is None:
                        c = ans.get("content")
                        if c is None or not c.strip():
                            tab["без ответа"] += 1
                        else:
                            # Таблица, отданная прозой: адреса ячеек пропали, а
                            # знаки остались. Это НЕ то же, что молчание, и
                            # цена другая — структуру не восстановить.
                            tab["отдана текстом"] += 1
                if mg is None:
                    tab["расстояние ячеек"] += chars
                    rec["совпало ячеек"] = 0
                else:
                    mgn = {k: normalize(v, norm) for k, v in mg.items()}
                    if _shape(mgn) != _shape(cells):
                        tab["сетка разошлась"] += 1
                    hit = d_sum = 0
                    for k, v in cells.items():
                        got_v = mgn.get(k, "")
                        d, exact = _dist(v, got_v)
                        if not exact:
                            txt["оценено сверху"] += 1
                        d_sum += d
                        hit += (v == got_v)
                    tab["совпало ячеек"] += hit
                    tab["расстояние ячеек"] += d_sum
                    rec["совпало ячеек"] = hit
                    rec["ячеек"] = len(cells)
                    if ans.get("kind") not in ("html", "otsl"):
                        kind_bad += 1
                per_block.append(rec)
                continue

            if isinstance(content, str) and content.strip():   # ------ текст
                txt["блоков"] += 1
                rec["разряд"] = "текст"
                ref = normalize(content, norm)
                rw = ref.split()
                txt["знаков истины"] += len(ref)
                txt["слов истины"] += len(rw)
                if ans is None:
                    txt["не сопоставлено"] += 1
                    mt["не сопоставлено (истина)"] += 1
                    txt["расстояние знаков"] += len(ref)
                    txt["расстояние слов"] += len(rw)
                    rec["CER"] = rec["WER"] = None
                    per_block.append(rec)
                    continue
                out = ans.get("content")
                if out is None or not out.strip():
                    txt["без ответа"] += 1
                    txt["расстояние знаков"] += len(ref)
                    txt["расстояние слов"] += len(rw)
                    rec["CER"] = rec["WER"] = None
                    per_block.append(rec)
                    continue
                hyp = normalize(out, norm)
                hw = hyp.split()
                dc, exact = _dist(ref, hyp)
                if not exact:
                    txt["оценено сверху"] += 1
                dw, _ = _dist(rw, hw)
                txt["расстояние знаков"] += dc
                txt["расстояние слов"] += dw
                txt["расстояние знаков (отвеченные)"] += dc
                txt["знаков истины (отвеченные)"] += len(ref)
                rec["CER"] = dc / len(ref) if ref else None
                rec["WER"] = dw / len(rw) if rw else None
                rec["знаков"] = len(ref)
                if ans.get("kind") != "text":
                    kind_bad += 1
                per_block.append(rec)
                continue

            if isinstance(content, str):        # ---- истина пуста строкой
                txt["истина пуста"] += 1
                rec["разряд"] = "истина пуста"
                per_block.append(rec)
                continue

            if role == "артефакт":                        # ------- приманка
                bait["артефактов"] += 1
                rec["разряд"] = "приманка"
                if ans is None:
                    bait["не сопоставлено"] += 1
                    mt["не сопоставлено (истина)"] += 1
                else:
                    c = ans.get("content")
                    if c is not None and c.strip():
                        bait["прочитано"] += 1
                        rec["прочитано знаков"] = len(c)
                    else:
                        bait["промолчано"] += 1
                per_block.append(rec)
                continue

            # content null на текстовом блоке — истина НЕ РАЗМЕЧЕНА.
            unmarked += 1
            rec["разряд"] = "истина не размечена"
            if ans is None:
                mt["не сопоставлено (истина)"] += 1
            elif (ans.get("content") or "").strip():
                # Модель тут что-то прочла, а сверить не с чем. Ни в CER, ни в
                # приманки это не идёт: и то и другое было бы выдумкой.
                unmarked_answered += 1
            per_block.append(rec)

    def frac(a, b):
        return (a / b) if b else None

    matched = mt["по якорю"] + mt["по номеру"] + mt["по геометрии"]
    res = {
        "нормализация": norm_note(norm),
        "затвор геометрии": {"двустороннее покрытие": metrics.COVER_MATCH,
                             "допуск, пикселей": metrics.TOL_PX},
        "страницы": pg,
        "сопоставление": dict(mt, сопоставлено=matched,
                              доля=frac(matched, mt["блоков истины"])),
        "текст": dict(txt,
                      CER=frac(txt["расстояние знаков"], txt["знаков истины"]),
                      WER=frac(txt["расстояние слов"], txt["слов истины"]),
                      **{"CER на отвеченных": frac(
                          txt["расстояние знаков (отвеченные)"],
                          txt["знаков истины (отвеченные)"]),
                         "доля без ответа": frac(txt["без ответа"],
                                                 txt["блоков"])}),
        "таблицы": dict(tab,
                        **{"доля совпавших ячеек": frac(tab["совпало ячеек"],
                                                        tab["ячеек"]),
                           "CER ячеек": frac(tab["расстояние ячеек"],
                                             tab["знаков ячеек"])}),
        "приманки": dict(bait, доля=frac(bait["прочитано"], bait["артефактов"])),
        "истина не размечена": unmarked,
        "ответов на неразмеченном": unmarked_answered,
        "вид ответа не тот": kind_bad,
        "по блокам": per_block,
    }
    return res


# ------------------------------------------------------------------- отчёт
def report(res: dict, log=print) -> None:
    if res.get("книга"):
        log(res["книга"])
    n = res["нормализация"]
    log(f"нормализация: {n['уровень']} — " + ", ".join(n["ступени"] or ["нет"]))
    log(f"  НЕ снимаем: {n['не снимаем']}")
    p, s = res["страницы"], res["сопоставление"]
    log(f"страниц: истины {p['истина']}, ответа {p['ответ']}, "
        f"без ответа {p['без ответа']}, лишних {p['лишних']}")
    d = s["доля"]
    # Доля сопоставленных печатается ПЕРВОЙ и всегда: CER, посчитанный по двум
    # блокам из сорока, — число про сопоставление, а не про чтение.
    log(f"сопоставлено {s['сопоставлено']}/{s['блоков истины']}"
        f" ({'—' if d is None else f'{d*100:.0f}%'}): по якорю {s['по якорю']}, "
        f"по номеру {s['по номеру']}, по геометрии {s['по геометрии']}")
    log(f"  НЕ сопоставлено: истины {s['не сопоставлено (истина)']}, "
        f"лишних в ответе {s['лишних в ответе']}, "
        f"якорь в никуда {s['якорь в никуда']}, "
        f"без рамки в ответе {s['без рамки в ответе']}")
    t = res["текст"]
    if not t["блоков"]:
        log("текст: НЕ РАЗМЕЧЕН в этой истине — сверять нечего "
            "(это не ноль чтения)")
    else:
        cer, wer = t["CER"], t["WER"]
        ans = t["CER на отвеченных"]
        log(f"текст: блоков {t['блоков']}, знаков {t['знаков истины']}, "
            f"слов {t['слов истины']}; "
            f"CER {'—' if cer is None else f'{cer:.4f}'}, "
            f"WER {'—' if wer is None else f'{wer:.4f}'}")
        log(f"  на отвеченных CER "
            f"{'—' if ans is None else f'{ans:.4f}'} по "
            f"{t['знаков истины (отвеченные)']} знакам; "
            f"без ответа {t['без ответа']} "
            f"({(t['доля без ответа'] or 0)*100:.0f}%), "
            f"не сопоставлено {t['не сопоставлено']}, "
            f"истина пуста {t['истина пуста']}")
        if t["оценено сверху"]:
            log(f"  расстояние ОЦЕНЕНО СВЕРХУ у {t['оценено сверху']} блоков: "
                f"строки длиннее бюджета в {_BUDGET} клеток")
    b = res["таблицы"]
    if not b["блоков"]:
        log("таблицы: структурной истины в этой книге нет — "
            "сверять нечего (это не ноль по ячейкам)")
    else:
        dc, cc = b["доля совпавших ячеек"], b["CER ячеек"]
        log(f"таблицы: блоков {b['блоков']}, ячеек {b['ячеек']}, "
            f"совпало по адресу {b['совпало ячеек']} "
            f"({'—' if dc is None else f'{dc*100:.0f}%'}), "
            f"CER ячеек {'—' if cc is None else f'{cc:.4f}'}")
        log(f"  без ответа {b['без ответа']}, отдана текстом "
            f"{b['отдана текстом']}, сетка разошлась {b['сетка разошлась']}, "
            f"не сопоставлено {b['не сопоставлено']}")
    a = res["приманки"]
    if not a["артефактов"]:
        log("приманки: артефактов без текста в истине нет — "
            "проверить выдумывание не на чем")
    else:
        log(f"приманки: артефактов {a['артефактов']}, ПРОЧИТАНО "
            f"{a['прочитано']} ({(a['доля'] or 0)*100:.0f}%), "
            f"промолчано {a['промолчано']}, "
            f"не сопоставлено {a['не сопоставлено']}")
    log(f"истина НЕ РАЗМЕЧЕНА: блоков {res['истина не размечена']}, из них "
        f"с ответом модели {res['ответов на неразмеченном']} — сверять их не с "
        f"чем, это НЕ ноль чтения; вид ответа не тот: "
        f"{res['вид ответа не тот']}")
    # Только блоки С ОШИБКОЙ: строка «худший блок: CER 0.000» — не худший блок,
    # а признание, что печатать нечего, и место в отчёте она занимает как
    # настоящая.
    err = [r for r in res["по блокам"] if r.get("CER")]
    if res["текст"]["блоков"] and not err:
        log(f"  блоков с ошибкой знаков нет: CER 0 на всех "
            f"{res['текст']['блоков']}")
    for r in sorted(err, key=lambda r: -r["CER"])[:3]:
        log(f"  худший блок с.{r['страница']} б.{r['блок']} ({r['ярлык']}, "
            f"{r['сведён']}): CER {r['CER']:.3f}, WER {r['WER']:.3f}, "
            f"знаков {r['знаков']}")


# ----------------------------------------------------------------- мутации
#
# Число, которое не умеет упасть, ничего не меряет. Порча ТРЁХСТОРОННЯЯ:
# ответ модели, ИСТИНА (метрика, безразличная к истине, меряет один свой вход
# и всегда «права») и НАШЕ СОБСТВЕННОЕ сопоставление — оно тоже вход, и оно
# тоже обязано уметь сломаться.
#
# Каждая проба портит РОВНО ОДНО. Две порчи разом не отличают живую величину
# от слипшейся с соседней: в метрике контуров ровно так девять пробегов подряд
# рапортовали «упало» при мёртвом пороге.
def _pages(P):
    return sorted(P)


def _blocks(P):
    for i in _pages(P):
        for j, b in enumerate(P[i]["blocks"]):
            yield i, j, b


def _pick_text(P, T, want=None):
    """Первый блок ответа, у которого в истине есть непустой текст.

    `want` сужает выбор: проба «подменена одна цифра» на блоке без цифр честно
    печатала «нет данных» — сторож не соврал, но и пробы не было. Портить надо
    там, где есть что портить, иначе батарея из 25 проб ставит 24.
    """
    for i in _pages(T):
        if i not in P:
            continue
        ids = {b.get("block_id"): b for b in T[i]["blocks"]}
        side = page_side(T[i])
        for j, b in enumerate(P[i]["blocks"]):
            t = ids.get(b.get("block_id"))
            c = b.get("content")
            if t is None or _truth_grid(t, side) is not None:
                continue
            if isinstance(t.get("content"), str) and t["content"].strip() \
                    and isinstance(c, str) and c.strip() \
                    and (want is None or want(c)):
                return i, j
    return None, None


def _pick_table(P, T):
    for i in _pages(T):
        if i not in P:
            continue
        ids = {b.get("block_id"): b for b in T[i]["blocks"]}
        side = page_side(T[i])
        for j, b in enumerate(P[i]["blocks"]):
            t = ids.get(b.get("block_id"))
            if t is not None and _truth_grid(t, side) is not None \
                    and _html_grid(b.get("content")):
                return i, j
    return None, None


def _pick_bait(P, T):
    for i in _pages(T):
        if i not in P:
            continue
        ids = {b.get("block_id"): b for b in T[i]["blocks"]}
        side = page_side(T[i])
        for j, b in enumerate(P[i]["blocks"]):
            t = ids.get(b.get("block_id"))
            if t is None or t.get("content") is not None:
                continue
            if _truth_grid(t, side) is None and policy.role(t["label"]) == "артефакт":
                return i, j
    return None, None


def _edit(P, i, j, fn):
    Q = copy.deepcopy(P)
    b = Q[i]["blocks"][j]
    b["content"] = fn(b.get("content"))
    return Q


def _drop10(s):
    """Выброшен каждый десятый знак."""
    return "".join(c for k, c in enumerate(s) if (k + 1) % 10)


def _swap_lines(s):
    ls = s.split("\n")
    if len(ls) < 2:
        return None
    ls[0], ls[1] = ls[1], ls[0]
    return "\n".join(ls)


def _swap_words(s):
    w = s.split()
    if len(w) < 2:
        return None
    w[0], w[1] = w[1], w[0]
    return " ".join(w)


_HYPH = re.compile(r"(\w)-\s*\n\s*(\w)")


def _glue(s):
    """Склеить переносы там, где их не было: дефис на конце строки съеден
    вместе с переводом строки. Ровно то, что делает модель, приученная
    склеивать, — и метрика обязана это увидеть."""
    out = _HYPH.sub(r"\1\2", s)
    return None if out == s else out


def _shift_rows(html):
    """СДВИГ СТРОКИ В ТАБЛИЦЕ. Первый столбец (подписи строк) на месте,
    данные съезжают на строку вниз по кругу. Набор ячеек тот же, каждое
    значение приписано чужой строке — ведущий вид незаметной порчи."""
    g = _html_grid(html)
    if not g:
        return None
    rows, cols = _shape(g)
    if rows < 2 or cols < 2:
        return None
    out = {}
    for (r, c), v in g.items():
        out[(r, c) if c == 0 else ((r + 1) % rows, c)] = v
    return _grid_html(out)


def _detable(html):
    """Таблица отдана простым текстом: разметка снята, знаки целы."""
    g = _html_grid(html)
    if not g:
        return None
    rows, cols = _shape(g)
    return " ".join(g.get((r, c), "") for r in range(rows) for c in range(cols))


def _blank_cell(html):
    g = _html_grid(html)
    if not g:
        return None
    for k in sorted(g):
        if g[k].strip():
            g[k] = ""
            return _grid_html(g)
    return None


def _digit(s):
    """Подменить одну цифру. Порча содержательная и мелкая: если она не видна,
    значит нормализация съела больше, чем объявлено."""
    for k, c in enumerate(s):
        if c.isdigit():
            return s[:k] + ("8" if c != "8" else "3") + s[k + 1:]
    return None


def _spelling(s):
    """Разнопись, которую граница ОБЯЗАНА снять: регистр, вид тире, ширина
    знака (NFKC), точка на конце. Число тут двигаться не должно."""
    out = s.upper().replace("-", "—") + "."
    out = out.replace("A", "Ａ")
    return out if out != s else None


def _shift_boxes(P, frac=0.9):
    Q = copy.deepcopy(P)
    for _, _, b in _blocks(Q):
        x = _box(b)
        if x is None:
            continue
        d = frac * max(4.0, min(x[2] - x[0], x[3] - x[1]))
        b["box"] = [x[0] + d, x[1] + d, x[2] + d, x[3] + d]
    return Q


def _anchor_all(P):
    Q = copy.deepcopy(P)
    for _, _, b in _blocks(Q):
        b.setdefault("meta", {})["якорь"] = b.get("block_id")
    return Q


def _shuffle_pages(P):
    """Ответ сдвинут на страницу по кругу: сверка идёт по индексу страницы."""
    ks = _pages(P)
    if len(ks) < 2:
        return None
    return {k: {**copy.deepcopy(P[ks[(n + 1) % len(ks)]]), "index": k}
            for n, k in enumerate(ks)}


def _corrupt_truth(T, fn):
    """Порча САМОЙ ИСТИНЫ. Метрика, безразличная к истине, меряет один свой
    вход — и всегда будет права."""
    Q = copy.deepcopy(T)
    for i, _, b in _blocks(Q):
        c = b.get("content")
        if isinstance(c, str) and c.strip():
            out = fn(c)
            if out is not None and out != c:
                b["content"] = out
                return Q, True
    return Q, False


def _corrupt_truth_cell(T):
    """Испортить одну ячейку САМОЙ ИСТИНЫ. Метрика обязана упасть и здесь.

    Проба существует потому, что метрика, слепая к порче эталона, мерит не то,
    что думает: она сравнивает ответ с чем-то, а с чем именно — не знает.

    Сетка живёт СБОКУ у страницы (`meta["истина артефактов"]`, ключ — номер
    блока строкой), а не в блоке: у `Block` поля `meta` нет вовсе. Прежняя
    редакция правила `meta` блока и потому не портила ничего — проба честно
    печатала бы «нет данных», то есть батарея ставила бы себе зачёт за
    непроведённый опыт.
    """
    Q = copy.deepcopy(T)
    for i, _, b in _blocks(Q):
        side = page_side(Q[i])
        if _truth_grid(b, side) is None:
            continue
        holders = []
        m = b.get("meta") or {}
        if m:
            holders.append(m)
        raw = ((Q[i].get("meta") or {}).get("истина артефактов") or {})
        for key in (str(b.get("block_id")), b.get("block_id")):
            if isinstance(raw.get(key), dict):
                holders.append(raw[key])
                break
        for h in holders:
            src = h
            for key in ("таблица", "table", "структура", "structure"):
                if isinstance(h.get(key), dict):
                    src = h[key]
                    break
            cells = next((src[k] for k in _CELLS_KEYS if k in src), None)
            if isinstance(cells, list) and cells and isinstance(cells[0], list):
                for row in cells:
                    for k, v in enumerate(row):
                        if isinstance(v, str) and v.strip():
                            row[k] = v + "X"
                            return Q, True
    return Q, False

def _map_all(P, fn):
    Q = copy.deepcopy(P)
    for _, _, b in _blocks(Q):
        b["content"] = fn(b.get("content"))
    return Q


def _drop_block(P):
    for i in _pages(P):
        if len(P[i]["blocks"]) > 1:
            Q = copy.deepcopy(P)
            Q[i]["blocks"].pop(0)
            return Q
    return None


def _add_block(P):
    """Лишний блок в ответе — рамкой поверх существующей, чтобы он проходил
    затвор и всё-таки оставался лишним: пара уже занята."""
    i = _pages(P)[0]
    Q = copy.deepcopy(P)
    b = copy.deepcopy(Q[i]["blocks"][0])
    b["block_id"] = 10_000
    Q[i]["blocks"].append(b)
    return Q


def _dead_anchor(P):
    i = _pages(P)[0]
    Q = copy.deepcopy(P)
    Q[i]["blocks"][0].setdefault("meta", {})["якорь"] = 99_999
    return Q


def mutations(truth_dir: str, pages_dir: str, log=print) -> int:
    """Прогнать батарею. Возвращает число НЕ пойманных порч (0 — метрика жива)."""
    T, P = _load(truth_dir), _load(pages_dir)
    base = measure_pages(T, P)
    b_cer = base["текст"]["CER"]
    b_wer = base["текст"]["WER"]
    b_none = base["текст"]["доля без ответа"]
    b_cell = base["таблицы"]["доля совпавших ячеек"]
    b_cellcer = base["таблицы"]["CER ячеек"]
    b_bait = base["приманки"]["доля"]
    b_match = base["сопоставление"]["доля"]
    b_lost = base["сопоставление"]["не сопоставлено (истина)"]
    b_extra = base["сопоставление"]["лишних в ответе"]
    b_dead = base["сопоставление"]["якорь в никуда"]
    b_flat = base["таблицы"]["отдана текстом"]

    def s(x, f="{:.4f}"):
        return "—" if x is None else f.format(x)

    log(f"исходно: сопоставлено {s(b_match, '{:.2f}')}, CER {s(b_cer)}, "
        f"WER {s(b_wer)}, без ответа {s(b_none, '{:.2f}')}, "
        f"ячеек совпало {s(b_cell, '{:.2f}')}, CER ячеек {s(b_cellcer)}, "
        f"приманок {s(b_bait, '{:.2f}')}, "
        f"не сопоставлено {b_lost}, лишних {b_extra}")

    ti, tj = _pick_text(P, T)
    di, dj = _pick_text(P, T, want=lambda c: any(x.isdigit() for x in c))
    bi, bj = _pick_table(P, T)
    ai, aj = _pick_bait(P, T)

    def M(pp=None, tt=None):
        return measure_pages(tt or T, pp or P)

    def cer(pp=None, tt=None):
        return M(pp, tt)["текст"]["CER"]

    def one(fn):
        """Порча ОДНОГО текстового блока ответа; None — портить нечего."""
        if ti is None:
            return None
        old = P[ti]["blocks"][tj].get("content")
        new = fn(old)
        if new is None or new == old:
            return None
        return _edit(P, ti, tj, lambda _: new)

    def one_tab(fn):
        if bi is None:
            return None
        old = P[bi]["blocks"][bj].get("content")
        new = fn(old)
        if new is None or new == old:
            return None
        return _edit(P, bi, bj, lambda _: new)

    def grew(now, was):
        return None if (now is None or was is None) else now > was

    def fell(now, was):
        return None if (now is None or was is None) else now < was

    def cer_up(mm):
        return None if mm is None else grew(cer(mm), b_cer)

    probes = []

    # --- порча ОТВЕТА модели: знаки
    probes.append(("выброшен каждый десятый знак", "CER вырос",
                   lambda: cer_up(one(_drop10))))
    probes.append(("переставлены две строки внутри блока", "CER вырос",
                   lambda: cer_up(one(_swap_lines))))
    probes.append(("переставлены два слова", "WER вырос",
                   lambda: (lambda mm: None if mm is None
                            else grew(M(mm)["текст"]["WER"], b_wer))(
                       one(_swap_words))))
    probes.append(("склеены переносы там, где их не было", "CER вырос",
                   lambda: cer_up(one(_glue))))

    def digit():
        """Порча содержательная и мелкая: если она не видна, значит
        нормализация съела больше, чем объявлено границей."""
        if di is None:
            return None
        new = _digit(P[di]["blocks"][dj]["content"])
        if new is None:
            return None
        return cer_up(_edit(P, di, dj, lambda _: new))

    probes.append(("подменена одна цифра", "CER вырос", digit))
    probes.append(("пустой ответ на непустом блоке", "без ответа больше",
                   lambda: (lambda mm: None if mm is None else
                            grew(M(mm)["текст"]["доля без ответа"], b_none))(
                       one(lambda s_: ""))))
    probes.append(("пустой ответ на непустом блоке", "CER вырос",
                   lambda: cer_up(one(lambda s_: ""))))
    probes.append(("все ответы выброшены", "CER ровно 1.0 и без ответа 1.0",
                   lambda: (lambda r: r["текст"]["CER"] == 1.0
                            and r["текст"]["доля без ответа"] == 1.0)(
                       M(_map_all(P, lambda c: None)))))

    # Ответ от СОСЕДНЕГО блока: подстановка чужого текста целиком. Ловится
    # только сравнением с истиной ЭТОГО блока — метрика, считающая «похоже на
    # текст вообще», такое пропустит.
    def neighbour():
        if ti is None:
            return None
        src = None
        for i, j, b in _blocks(P):
            c = b.get("content")
            if isinstance(c, str) and c.strip() and (i, j) != (ti, tj):
                src = c
                break
        if src is None:
            return None
        return cer_up(_edit(P, ti, tj, lambda _: src))

    probes.append(("ответ от СОСЕДНЕГО блока целиком", "CER вырос", neighbour))

    # --- порча ОТВЕТА: таблица
    probes.append(("СДВИГ СТРОКИ В ТАБЛИЦЕ (набор ячеек тот же)",
                   "совпавших ячеек меньше",
                   lambda: (lambda mm: None if mm is None else
                            fell(M(mm)["таблицы"]["доля совпавших ячеек"],
                                 b_cell))(one_tab(_shift_rows))))
    probes.append(("опустошена одна ячейка", "совпавших ячеек меньше",
                   lambda: (lambda mm: None if mm is None else
                            fell(M(mm)["таблицы"]["доля совпавших ячеек"],
                                 b_cell))(one_tab(_blank_cell))))
    probes.append(("таблица отдана простым текстом", "отданных текстом больше",
                   lambda: (lambda mm: None if mm is None else
                            grew(M(mm)["таблицы"]["отдана текстом"], b_flat))(
                       one_tab(_detable))))
    probes.append(("таблица отдана простым текстом", "CER ячеек вырос",
                   lambda: (lambda mm: None if mm is None else
                            grew(M(mm)["таблицы"]["CER ячеек"], b_cellcer))(
                       one_tab(_detable))))

    # --- порча ОТВЕТА: приманка
    def bait():
        if ai is None:
            return None
        mm = _edit(P, ai, aj, lambda _: "Рис. 4. Схема установки, 12 подписей")
        return grew(M(mm)["приманки"]["доля"], b_bait)

    probes.append(("артефакту дописан текст (приманка)", "приманок больше",
                   bait))

    # --- порча НАШЕГО СОПОСТАВЛЕНИЯ: оно тоже вход
    probes.append(("рамки ответа сдвинуты на 0.9 своего размера",
                   "сопоставлено меньше",
                   lambda: fell(M(_shift_boxes(P))["сопоставление"]["доля"],
                                b_match)))
    def dropped():
        mm = _drop_block(P)
        return None if mm is None else grew(
            M(mm)["сопоставление"]["не сопоставлено (истина)"], b_lost)

    probes.append(("блок выкинут из ответа", "не сопоставлено больше", dropped))
    probes.append(("лишний блок в ответе", "лишних больше",
                   lambda: grew(M(_add_block(P))["сопоставление"]
                                ["лишних в ответе"], b_extra)))
    probes.append(("якорь указывает в никуда", "якорей в никуда больше",
                   lambda: grew(M(_dead_anchor(P))["сопоставление"]
                                ["якорь в никуда"], b_dead)))
    probes.append(("ответ сдвинут на страницу", "CER вырос",
                   lambda: (lambda mm: None if mm is None else cer_up(mm))(
                       _shuffle_pages(P))))
    # Свойство ЯКОРЯ, а не беда: объявленный якорь сильнее геометрии, и сдвиг
    # рамок его не ломает. Печатается пробой, чтобы это было видно числом, а
    # не подразумевалось.
    probes.append(("с якорями рамки сдвинуты на 0.9", "сопоставление держится",
                   lambda: M(_shift_boxes(_anchor_all(P)))["сопоставление"]
                   ["доля"] == b_match))

    # --- порча ИСТИНЫ: метрика обязана смотреть на ОБА входа
    def truth_chars():
        tt, ok = _corrupt_truth(T, _drop10)
        return None if (not ok or b_cer is None) else cer(tt=tt) > b_cer

    probes.append(("в истине выброшен каждый десятый знак", "CER вырос",
                   truth_chars))
    probes.append(("в истине испорчена ячейка таблицы",
                   "совпавших ячеек меньше",
                   lambda: (lambda tt: None if not tt[1] else
                            fell(M(tt=tt[0])["таблицы"]["доля совпавших ячеек"],
                                 b_cell))(_corrupt_truth_cell(T))))

    # --- ОБРАТНЫЕ пробы: число обязано СТОЯТЬ
    probes.append(("вход не испорчен вовсе", "все числа на месте",
                   lambda: M() == base))
    probes.append(("разнопись внутри границы (регистр, тире, NFKC, точка)",
                   "CER не изменился",
                   lambda: (lambda mm: None if mm is None
                            else cer(mm) == b_cer)(one(_spelling))))
    # Та же разнопись при уровне «нет» ОБЯЗАНА двигать число: иначе
    # нормализация мертва, и предыдущая проба хвалит не работу, а бездействие.
    probes.append(("та же разнопись при нормализации «нет»", "CER изменился",
                   lambda: (lambda mm: None if mm is None else
                            measure_pages(T, mm, norm="нет")["текст"]["CER"]
                            != measure_pages(T, P, norm="нет")["текст"]["CER"])(
                       one(_spelling))))

    bad = 0
    for name, want, probe in probes:
        ok = probe()
        mark = "нет данных" if ok is None else ("ok " if ok else "НЕТ")
        log(f"  {mark:>10}  {name}: {want}")
        bad += ok is False

    log("чего эта батарея НЕ ловит: неверную ИСТИНУ (сверять её не с чем, "
        "кроме скана и глаз); выдумку модели, попавшую в истину дважды; "
        "ошибку внутри границы нормализации — она снята нарочно и замером; "
        "чтение, потерянное ДО метрики, если блока нет ни в истине, ни в "
        "ответе.")
    log(f"не пойманных порч: {bad}")
    return bad


