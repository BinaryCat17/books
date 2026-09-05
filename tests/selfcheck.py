"""Батарея мутаций: проверка обязана уметь провалиться.

Правило проекта сказано про метрику — «прежде чем верить числу, подай в него
заведомо испорченный вход и убедись, что число упало», — но к проверкам оно
относится ровно так же. Зелёная проверка на сломанном коде хуже отсутствующей:
отсутствующая честно молчит, а эта каждый день говорит «сошлось».

Как устроено. Каждая мутация ЛОМАЕТ проверяемое место — подменяет функцию в
памяти или подсовывает КОПИЮ исходника с одной изменённой строкой — и
называет проверки, которые обязаны от этого покраснеть. Рабочее дерево не
трогается вовсе: чинить чужие файлы руками при семи работающих рядом — верный
способ затереть чужую правку.

Печатается величина: сколько мутаций поймано, сколько нет и КАКИЕ проверки
мутацией не покрыты ни одной. Непокрытая проверка — не беда сама по себе, но
знать про неё надо числом, а не на слух.
"""
import base64
import importlib
import importlib.util
import json
import os
import shutil
import sys
import tempfile
from contextlib import contextmanager

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import support                                              # noqa: E402
from booksmith import metrics, otsl, policy                 # noqa: E402
from booksmith import fitness as fit                        # noqa: E402
from booksmith.remote import vast as vastmod
from booksmith import order
from booksmith import annopage                              # noqa: E402
from booksmith import overlay                               # noqa: E402
from booksmith import djvu                                  # noqa: E402
from booksmith.doc import apply as ap                       # noqa: E402
from booksmith.doc import crop                              # noqa: E402
from booksmith.doc import feed                              # noqa: E402
from booksmith.doc import html as dhtml                     # noqa: E402
from booksmith.doc import swap                              # noqa: E402
from booksmith.models import base as mbase                  # noqa: E402
from booksmith.models import docling_heron as dh            # noqa: E402
from booksmith.run import knobs, replay, stamp              # noqa: E402
from booksmith.models import doclayout                      # noqa: E402
from booksmith import text as booktext                      # noqa: E402
from booksmith.read import Reader, Route, Said              # noqa: E402
from booksmith.read import http as vhttp                    # noqa: E402
from booksmith.read import run as vrun                      # noqa: E402
from booksmith.read import run as vrun                      # noqa: E402
from booksmith.models.paddleocr_vl.reader import PaddleOcrVl  # noqa: E402


# --- чем ломаем ------------------------------------------------------------

@contextmanager
def attrs(obj, **kw):
    """Подменить поля объекта на время мутации и вернуть как было."""
    old = {k: getattr(obj, k) for k in kw}
    try:
        for k, v in kw.items():
            setattr(obj, k, v)
        yield
    finally:
        for k, v in old.items():
            setattr(obj, k, v)


COPY = ("models/doclayout.py", "models/docling_heron.py",
        "models/yolox_layout.py",
        # Точка входа для арендованной карты. Копия разбора `--pages`, и
        # стережёт её `test_parse_pages` — читая файл ОТСЮДА, через
        # `support.src_path`. Забыть эту строку значит оставить мутацию без
        # действия: проверка прочтёт настоящий файл мимо порчи и будет
        # зелёной на сломанном коде.
        "models/dots_ocr/entrypoint.py",
        # Прибор контуров: `test_order` разбирает его `_by_reading` и требует,
        # чтобы правило сборки спрашивалось у `order.py`, а не повторялось.
        "metrics.py",
        # Скрипт, уезжающий на арендованную карту: `test_knobs` сверяет его
        # `${ИМЯ:-умолчание}` с реестром ручек.
        "models/paddleocr_vl/run.sh",
        # Сборщик книги: `test_html_order` разбирает его `build` и требует,
        # чтобы сверка порядка была на месте и не выводилась из обхода.
        "doc/html.py")


@contextmanager
def sources(rel, old, new):
    """Копия дерева исходников с одной изменённой строкой.

    Именно копия: проверки, читающие исходник, обязаны краснеть от порчи, но
    портить рабочее дерево ради этого нельзя.
    """
    tmp = tempfile.mkdtemp(prefix="booksmith-selfcheck-")
    try:
        for r in COPY:
            dst = os.path.join(tmp, r)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copyfile(support.src_path(r), dst)
        path = os.path.join(tmp, rel)
        with open(path, encoding="utf-8") as f:
            text = f.read()
        if old not in text:
            raise AssertionError(
                f"мутация не наложилась: в {rel} нет строки {old!r} — "
                f"проверяемое место переписали, а батарея этого не знает")
        with open(path, "w", encoding="utf-8") as f:
            f.write(text.replace(old, new, 1))
        with attrs(support, SRC=tmp):
            yield
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def have_docling():
    try:
        import docling                                       # noqa: F401
        return True
    except ImportError:
        return False


def slow_on():
    return bool(os.environ.get("BOOKSMITH_TESTS_SLOW"))


# Чем мутация может быть не выполнима. Пропуск печатается вслух и с причиной:
# непроверенная мутация — это не «поймана».
NEEDS = {"нет пакета docling": have_docling,
         "медленная, только с --slow": slow_on}


# --- испорченные редакции проверяемых мест ---------------------------------

def guard_without_words(page):
    """Сторож, забывший про слово «наш»: всё считает рангом модели."""
    return True


def truth_state_defaults_to_marked(page):
    """Прежняя редакция: молчащая истина считается размеченной."""
    m = page.get("meta") or {}
    return metrics.ORDER_MARKED if m.get("порядок размечен", True) \
        else metrics.ORDER_UNMARKED


def pipeline_touches_at_off(self, blocks, w, h, index):
    """Конвейер «ничего не делает», но пересобирает список и дописывает ключ."""
    return list(blocks), {"порядок чтения": "наш, сверху вниз и слева направо",
                          "конвейер docling": {"режим": "off"}}


class GuessingTranslation(dict):
    """Перевод ярлыков правилом: чего не знаю — то текст."""

    def get(self, key, default=None):
        return dict.get(self, key, "text")


def check_against_the_union(labels, policy_name="PP-DocLayoutV2"):
    """Сверка с объединением словарей вместо названного."""
    have, mine = set(labels), set(policy.ROLE)
    if have - mine or mine - have:
        raise policy.UnknownLabel("объединение не сошлось")


def check_that_forgives(labels, policy_name="PP-DocLayoutV2"):
    """Умолчание вместо падения — та самая беда словаря порогов paddlex."""


class GuessingRole(dict):
    def __missing__(self, key):
        return "текст"


def span_takes_the_first(html, anchor):
    """Прежняя редакция: беру первую метку, ни счёта, ни выворота, ни перекрёста."""
    o, c = swap.marks(anchor)
    return html.index(o) + len(o), html.index(c)


def span_without_crossing(html, anchor):
    """Счёт «по одной» есть, проверки зацепления соседей нет."""
    o, c = swap.marks(anchor)
    if html.count(o) != 1 or html.count(c) != 1:
        raise swap.AnchorError(f"метка {anchor}: открывающих {html.count(o)}, "
                               f"закрывающих {html.count(c)}")
    a, b = html.index(o) + len(o), html.index(c)
    if b < a:
        raise swap.AnchorError(f"метка {anchor} вывернута")
    return a, b


def span_calls_nesting_a_crossing(html, anchor):
    """Вложение принято за перекрёст: любая чужая метка внутри — отказ."""
    a, b = span_without_crossing(html, anchor)
    for other in swap._marks_in(html[a:b]):
        if other != anchor:
            raise swap.AnchorError(f"метка {anchor} пересекается с {other}")
    return a, b


def marks_by_prefix(anchor):
    """Метка узнаётся по префиксу, а не поимённо."""
    return swap.OPEN.split("{}")[0], swap.CLOSE.split("{}")[0]


def anchors_sorted(html):
    return sorted(_real_anchors(html))


def anchors_swallow_unterminated(html):
    """Оборванный комментарий молча даёт пустой список."""
    out, i = [], 0
    head = swap.OPEN.split("{}")[0]
    while True:
        i = html.find(head, i)
        if i < 0:
            return out
        j = html.find("-->", i)
        if j < 0:
            return out
        out.append(html[i + len(head):j])
        i = j + 3


def swap_forgets_what_it_removed(html, anchor, fragment):
    a, b = _real_span(html, anchor)
    return html[:a] + fragment + html[b:], ""


_real_knob = knobs.knob


def knob_says_post(name):
    """Ручка выключена, а адаптеру приезжает `post`."""
    return "post" if name == "DOCLING_PIPELINE" else _real_knob(name)


def knob_returns_empty(name):
    return os.environ.get(name, "")


def knob_ignores_empty(name):
    """`os.environ.get(...) or default` — пустая строка снаружи проигрывает."""
    return os.environ.get(name) or knobs.KNOB[name].default


def snapshot_skips_debts():
    return {k.name: {"значение": knobs.knob(k.name), "умолчание": k.default,
                     "задано снаружи": k.name in os.environ, "что": k.what,
                     "долг": k.debt}
            for k in knobs.KNOBS if not k.debt}


def snapshot_only_artefacts(policy_name=None):
    return {"разряды": list(policy.ROLES), "словарь": policy_name,
            "по ярлыкам": {l: "артефакт" for l in policy.artefacts()}}


def passthrough_with_defaults():
    return {k.name: knobs.knob(k.name) for k in knobs.KNOBS}


_real_span, _real_anchors = swap.span, swap.anchors


def flipped_role():
    r = dict(policy.ROLE)
    r["table"] = "текст"
    return r


def duplicated_policy():
    p = dict(policy.POLICIES)
    p["Docling-двойник"] = dict(policy.DOCLING)
    return p


def egret_without_translation():
    d = dict(dh.EGRET_TO_DOCLING)
    d["Table"] = "Table"
    return d


def docling_egret_short():
    d = dict(policy.DOCLING_EGRET)
    d.pop("Table")
    return d


def knobs_with_phantom():
    return knobs.KNOBS + (knobs.Knob("FANTOM", "", "ручка без потребителя"),)


def knobs_with_duplicate():
    return knobs.KNOBS + (knobs.Knob("PAGE_DPI", "300", "она же второй раз"),)


def knobs_with_int_default():
    k = knobs.KNOBS[0]
    return (knobs.Knob(k.name, 144, k.what),) + knobs.KNOBS[1:]


# --- сами мутации ----------------------------------------------------------
# (имя; что ломаем; какие проверки ОБЯЗАНЫ покраснеть)

def guard_case_sensitive(value):
    """Сторож, снова сверяющий регистр, — та порча, что была дефектом.

    Подменяется ЖИВАЯ функция, а не исходник: оба читателя
    (`metrics._model_has_rank`, `doc/html._ours`) берут её из модуля в момент
    вызова, и порча доходит до обоих разом — что и надо, договор ведь общий.
    """
    return isinstance(value, str) and value.strip().startswith("наш")


def _journal_without_taken(out_dir, j):
    """Журнал забыл, ЧТО снял. Откатывать станет нечем, а put при этом
    отработает как ни в чём не бывало — беда вылезет только при откате."""
    z = {k: [{**r, "снято": ""} for r in v] for k, v in j["замены"].items()}
    return _save_journal(out_dir, {**j, "замены": z})


def _journal_invents_a_stack(out_dir):
    """Журнал отвечает стопкой там, где замен не было. «Откатывать нечего» и
    «откат не удался» перестают различаться."""
    return {"книга": "book.html",
            "замены": {"p0042-b17": [{"когда": "?", "чем": "?", "вид": "html",
                                      "sha256 поставленного": "0" * 64,
                                      "снято": "<i>выдумка</i>",
                                      "sha256 снятого": "0" * 64}]}}


def _flat_journal(out_dir, j):
    """Стопка отката схлопнута в последнее значение — среднее состояние
    пропадает молча, и «переделать другой моделью» перестаёт быть обратимым."""
    return _save_journal(out_dir, {**j, "замены": {k: v[-1:] for k, v in
                                                   j["замены"].items()}})


_save_journal = ap.save_journal



# ---- ВТОРОЙ УРОВЕНЬ: сторожа чтения --------------------------------------
# Все проверки `test_read` до сих пор не были покрыты ни одной мутацией, и
# бегун честно об этом печатал. Проверка, которую нельзя сломать, не доказана
# — правило проекта, применённое к самим проверкам.

def crop_dpi_by_the_whole_box(box, page_dpi, native, window, sheet=None):
    """Прежнее правило: зажим считается по ПОЛНОЙ рамке, а режется пересечение
    с листом. Рамка, вылезшая вдвое, получала 83.7 dpi вместо 118.4."""
    return vrun.crop_dpi_for(box, page_dpi, native, window, sheet=None)


def crop_dpi_stretches_up(box, page_dpi, native, window, sheet=None):
    """«Мелкий блок? Дотянем до нижней границы модели» — выдумка точек.

    Соблазн настоящий: 555 вырезок из 566 мельче окна, и растянуть их кажется
    улучшением. Но выше решётки скана прибавляются не чернила, а догадка
    растеризатора, и назвать её чтением нельзя.
    """
    base = float(native or page_dpi)
    if not window:
        return base, "своя резкость скана (границ модели нет)"
    lo, hi = window
    w = (box[2] - box[0]) / page_dpi
    h = (box[3] - box[1]) / page_dpi
    if w <= 0 or h <= 0:
        return base, "своя резкость скана"
    at = w * base * h * base
    if at > hi:
        return (hi / (w * h)) ** 0.5, "ужато до верхней границы модели"
    if at < lo:
        return (lo / (w * h)) ** 0.5, "растянуто до нижней границы модели"
    return base, "своя резкость скана"


def crop_dpi_ignores_the_window(box, page_dpi, native, window, sheet=None):
    """Границы модели не спрашиваем вовсе: режем своей резкостью всегда."""
    return float(native or page_dpi), "своя резкость скана"


_SHAPE = replay.shape       # снят до подмены: иначе ломалка позвала бы себя


def shape_silent_about_underived(snap):
    """Прежний `replay.shape`: невыведенная форма — пустое требование.

    Так и было: ветка «отпечаток» не попадала в требования ВОВСЕ, и слепок,
    где отпечатка нет вообще, проходил `books replay --check` с кодом 0 и
    строкой «величин в слепке 51 из 51, не хватает 0» — да ещё со словом
    СВЕРЕН рядом.
    """
    r = _SHAPE(snap)
    if r["не выведено"]:
        r["не выведено"], r["выведено"] = 0, []
    return r


def skip_by_what_is_installed(reason):
    """Прежний `support.skip`: выбор по «импортируется ли pytest».

    Под нашим бегуном первый же пропуск уходил мимо ловушек `run_case` и
    убивал прогон целиком: `Skipped` у pytest наследует BaseException.
    """
    try:
        import pytest
    except ImportError:
        raise support.Skip(reason) from None
    pytest.skip(reason)


def skip_always_ours(reason):
    """Пропуск всегда наш — под pytest он засчитается ПРОВАЛОМ."""
    raise support.Skip(reason)


def variants_built_once_at_defaults(M):
    """Прежний `metrics._order_variants`: готовые страницы, а не сборщики.

    Пол «колонка за колонкой» складывался при умолчании, а мерился на всей
    развёртке — и в точках «перекрытие x 0.8/0.9» обгонял саму модель.
    """
    return {"как отдала модель": M,
            "сверху вниз, слева направо": metrics._by_reading(M),
            "колонка за колонкой": metrics._by_columns(M),
            "по кругу через колонки": metrics._mix_columns(M)}


def ranking_without_rebuilding(variants, grid=None, cross=False,
                               key="на страницу"):
    """Приговор считается по НЕпересобранным вариантам: сборщика зовут без
    параметров точки, то есть пересборка есть только на словах."""
    names = list(variants)
    pts = metrics._sweep_points(grid or metrics.COLUMN_SWEEP, cross)
    vals = {n: [] for n in names}
    for p in pts:
        for n in names:
            v = variants[n]
            vals[n].append(metrics.column_jumps(v() if callable(v) else v,
                                                **p)[key])
    return {"пределы": {n: (None, None) for n in names}, "устойчив": True,
            "по точкам": [], "перевёрнутых пар": [], "ничьих пар": [],
            "точек": len(pts), "вариантов": len(names), "пар": 0,
            "различает пар": 0, "размах линейки": None,
            "ближайшая пара при умолчании": None, "величина": key}


def native_dpi_by_the_sheet(page):
    """Прежняя формула: пиксели делятся на ширину ЛИСТА.

    Скан разворота ШИРЕ листа, и деление на лист завышало решётку ровно во
    столько раз, во сколько растр шире, — до 2.47 раза на четырёх книгах из
    шести. Сверено с заголовком djvu: формат объявляет 300/600/300, старая
    формула давала 741.9/600.0/621.7.
    """
    w_pt = float(page.rect.width)
    if w_pt <= 0:
        return None
    best = 0.0
    for im in page.get_images(full=True):
        xref, w_px = im[0], im[2]
        if w_px <= 0:
            continue
        for r in page.get_image_rects(xref):
            if r.width < w_pt * 0.9:
                continue
            best = max(best, w_px / w_pt * 72.0)
    return best or None


def native_dpi_takes_any_image(page):
    """Порог «на весь лист» снят: марка в углу решает за всю страницу."""
    w_pt = float(page.rect.width)
    if w_pt <= 0:
        return None
    best = 0.0
    for im in page.get_images(full=True):
        xref, w_px = im[0], im[2]
        for r in page.get_image_rects(xref):
            if r.width > 0 and w_px > 0:
                best = max(best, w_px / float(r.width) * 72.0)
    return best or None



# ---- ГОДНОСТЬ ПО ЧЕРНИЛАМ: сторожа прибора, которым выбирали детектор -----
# Он был единственным из трёх, кого не разбирал никто, и у него нашлось восемь
# дефектов. Числа стендов при починке не сдвинулись ни на один из восемнадцати —
# значит записанное в `docs/contour-notes.md` в силе, а вот сторожей не было.

def clip_that_trusts_numpy(shape, box):
    """Прежняя нарезка: подрезать сверху numpy умеет, снизу — нет.

    `m[max(0,int(y0)):int(y1)+1]` при отрицательном `y1` отсчитывает конец ОТ
    КОНЦА массива. Замер: рамка [-40,-40,-20,-20] на листе 100x100 накрывала
    6561 пиксель из 10 000 — метрику можно было выиграть мусором.
    """
    x0, y0, x1, y1 = (int(v) for v in box)
    return slice(max(0, y0), y1 + 1), slice(max(0, x0), x1 + 1)


def carried_as_text_by_double_counting(sub, arte, rest, tot):
    """Сумма вместо объединения: пиксель под двумя рамками считается дважды.

    Замер на `hard36`: «уехал текстом» 21 как есть против 31 при задвоении. У
    сырого `docling-heron` задвоенных пар 4435 — это его штатное поведение, и
    дорогая беда («половина чернил не накрыта ничем») переписывалась в дешёвую
    («не потерян, чинится ярлыком»).
    """
    return (int((sub & arte).sum()) + int((sub & rest).sum())) / tot >= fit.WHOLE


def report_of_the_previous_edition(res, log=print):
    """Отчёт прежней редакции: один порог из четырёх, ни dpi, ни слова о
    слепоте к слиянию, и три разных нуля двумя строками."""
    n = res["объектов"]
    ink = max(1, res["чернил всего"])
    log(f"страниц {res['страниц']}; порог чернил {fit.INK}, "
        f"«цел» от {fit.WHOLE:.2f} чернил объекта")
    log(f"чернил страницы под рамками: {res['чернил под рамками'] / ink * 100:.1f}%, "
        f"вне всех рамок {(1 - res['чернил под рамками'] / ink) * 100:.1f}% — "
        f"это то, что исчезнет из HTML")
    if not n:
        log("истина не подана: по объектам сказать нечего — это не ноль потерь")
        return
    log(f"объектов {n}: цел {res['цел']}")


def ink_memory_that_clears_itself(pdf, doc, i, dpi):
    """Потолок памяти в СТРАНИЦАХ с полной очисткой при переполнении.

    Замер: 64 страницы — 64 рендера за семь проходов, 65 страниц — 455. Обрыв
    с полной экономии до нулевой на одной странице разницы, и ровно на том
    стенде (600 страниц), ради которого память заведена.
    """
    key = (pdf, i, int(dpi), fit.INK)
    if key not in fit._INK_CACHE:
        if len(fit._INK_CACHE) >= 64:
            fit._INK_CACHE.clear()
        m = fit._ink(doc[i], dpi)
        fit._INK_CACHE[key] = (m.shape, m)
    return fit._INK_CACHE[key][1]


def ink_memory_that_evicts_the_oldest(pdf, doc, i, dpi):
    """Потолок в байтах, упаковка по биту — и всё равно ноль экономии.

    Вытеснение старейшего при ПОСЛЕДОВАТЕЛЬНОМ обходе промахивается по
    построению: к началу следующего прохода вытеснено ровно начало книги.
    Симуляция на настоящем следе обращений и настоящих формах страниц
    золотого стенда, 23 прохода по 600 страницам, потолок 512 МиБ: 2400
    рендеров против 1800 у нынешней памяти, и 4800 против 3600 на двух
    книгах подряд.
    """
    import numpy as np
    key = (pdf, i, int(dpi), fit.INK)
    hit = fit._INK_CACHE.get(key)
    if hit is None:
        m = fit._ink(doc[i], dpi)
        packed = np.packbits(m)
        while (fit._INK_CACHE
               and fit._INK_CACHE_BYTES + packed.nbytes > fit._INK_CACHE_MAX_BYTES):
            fit._INK_CACHE_BYTES -= fit._INK_CACHE.pop(
                next(iter(fit._INK_CACHE)))[1].nbytes
        fit._INK_CACHE[key] = (m.shape, packed)
        fit._INK_CACHE_BYTES += packed.nbytes
        return m
    shape, packed = hit
    return np.unpackbits(packed, count=shape[0] * shape[1]).reshape(shape).view(bool)


def ink_memory_without_the_threshold(pdf, doc, i, dpi):
    """Порог чернил выпал из ключа памяти: правка порога возвращала маску,
    посчитанную СТАРЫМ порогом, и живой порог выглядел мёртвым."""
    key = (pdf, i, int(dpi))
    if key not in fit._INK_CACHE:
        m = fit._ink(doc[i], dpi)
        fit._INK_CACHE[key] = (m.shape, m)
    return fit._INK_CACHE[key][1]


@contextmanager
def source_swap(rel, old, new):
    """`support.tree(rel)` отдаёт разбор ИСХОДНИКА С ПОДМЕНЁННОЙ СТРОКОЙ.

    `one_line` пересобирает МОДУЛЬ, и проверкам, которые читают файл разбором,
    он не виден: они смотрят на диск. А такие проверки в этом каталоге есть —
    там, где значение договора зашито в литерал внутри метода и достать его
    исполнением нельзя, не подняв модель на 216 МБ. Без этого приёма они
    числились бы непокрываемыми, и ровно так уже случилось: скептик вынул
    поле «фильтр cv2» из копии дерева, и батарея объявила себя полностью
    исправной.

    Рабочее дерево не трогается: подменяется только то, что вернёт разбор.
    """
    import ast
    src = io_open_src(rel)
    if old not in src:
        raise AssertionError(
            f"мутация не наложилась: в {rel} нет строки {old!r} — "
            f"проверяемое место переписали, а батарея этого не знает")
    было = support.tree
    def подменённый(r):
        if r == rel:
            return ast.parse(src.replace(old, new, 1), filename=r)
        return было(r)
    support.tree = подменённый
    try:
        yield
    finally:
        support.tree = было


def io_open_src(rel):
    with open(os.path.join(support.SRC, rel), encoding="utf-8") as f:
        return f.read()


@contextmanager
def one_line(modname, old, new):
    """Модуль, пересобранный из исходника с ОДНОЙ изменённой строкой.

    `attrs` подменяет то, у чего есть имя в модуле, и потому до строки внутри
    длинной функции не дотягивается. Три проверки из-за этого числились
    «непокрываемыми», хотя дефекты у них ровно построчные: сторож молчания
    модели (`raise` -> `continue`), обрезка свесившейся рамки, выбор рамки,
    везущей объект. Здесь модуль собирается заново с подменённой строкой и на
    время мутации встаёт в `sys.modules` И атрибутом пакета — второе
    обязательно, иначе `from booksmith import fitness` в перезагружаемой
    проверке возьмёт старый модуль и мутация останется незамеченной.

    Рабочее дерево не трогается: правка живёт только в памяти.
    """
    mod = importlib.import_module(modname)
    with open(mod.__file__, encoding="utf-8") as f:
        src = f.read()
    if old not in src:
        raise AssertionError(
            f"мутация не наложилась: в {modname} нет строки {old!r} — "
            f"проверяемое место переписали, а батарея этого не знает")
    pkg, _, leaf = modname.rpartition(".")
    fake = importlib.util.module_from_spec(mod.__spec__)
    exec(compile(src.replace(old, new, 1), mod.__file__, "exec"), fake.__dict__)
    parent = sys.modules[pkg]
    sys.modules[modname] = fake
    setattr(parent, leaf, fake)
    try:
        yield
    finally:
        sys.modules[modname] = mod
        setattr(parent, leaf, mod)


_REAL_FIT_MUT = fit.mutations


def battery_summary_without_the_unmeasured(pdf, detect_dir, truth_dir="",
                                           log=print):
    """Итог батареи словом «готово»: «проб 9, непойманных 0» печаталось и
    когда пять проб из девяти не померили ничего."""
    out = []
    rc = _REAL_FIT_MUT(pdf, detect_dir, truth_dir, log=out.append)
    for line in out:
        if "нечем мерить" in line or "померено" in line:
            continue
        log(line)
    return rc


def battery_that_corrupts_only_the_model(pdf, detect_dir, truth_dir="",
                                         log=print):
    """Портится только вывод модели. Ни ИСТИНА (метрика, безразличная к
    истине, меряет один свой вход), ни СВОИ ПОРОГИ (мёртвый порог печатается
    наравне с живым). Доказано подменой `T = M`: старая батарея этого не
    ловила."""
    out = []
    rc = _REAL_FIT_MUT(pdf, detect_dir, truth_dir, log=out.append)
    for line in out:
        if "истин" in line.lower() or "порог" in line.lower():
            continue
        log(line)
    return rc




def veto_measures_the_share_of_rows(pix, x):
    """Возврат дефекта: вето мерит ДОЛЮ сквозных строк от высоты пробы.

    Ровно то, что стояло до правки. Величина квантованная — на пробе в 599
    строк это «три строки и ни строкой меньше», — и решает её высота скана:
    3/599 = 0.005008 даёт вето, 3/601 = 0.004992 не даёт. Замер: из 379
    разворотов «Справочника» 102 (27%) решались ОДНОЙ строкой.
    """
    сквозные, _ = djvu.dark_rows(pix, x)
    return djvu.RULE_RUN if len(сквозные) / max(1, pix.height) > 0.005 else 0.0


def veto_looks_at_the_whole_probe(pix, x):
    """Возврат дефекта: приграничная полоса пробы не отсекается.

    Чёрная кромка скана снова считается линейкой таблицы — 44 ложных вето из
    379 разворотов «Справочника», книга пересобирается в 716 страниц вместо
    760.
    """
    runs = [ln for _, ln in djvu.dark_runs(pix, x)]
    return (max(runs) if runs else 0) / max(1, pix.width)



def routes_guess_by_role(self):
    """Маршрут ВЫВОДИТСЯ из разряда вместо объявления. Так двадцать шестой
    класс новых весов молча поехал бы промтом текста."""
    from booksmith.read import Route
    from booksmith import policy
    out = {}
    for lab in policy.POLICIES[self.policy_name]:
        out[lab] = Route("OCR:", "text")
    return out


def cover_forgives(self, labels):
    """`cover` прощает ярлык без маршрута."""
    return None


def route_check_forgives(self, label):
    """Маршрут не сверяет ни вид, ни причину молчания."""
    return None


def kind_sniffed_from_the_answer(text, *a, **kw):
    """Вид берётся из ОТВЕТА, а не из промта — запрещённая починка модели."""
    from booksmith.read import run as vrun
    return vrun._sniff(text or "")


def grid_only_from_html(s, kind=None):
    """Возврат дефекта: таблица разбирается только из HTML, OTSL слепнет."""
    from booksmith import text as _t
    return _t._html_grid(s)


def refusal_looks_like_silence(self, ask):
    """Отказ доставки записывается молчанием модели: два нуля слиты в один."""
    from booksmith.read import Said
    return Said(anchor=ask.anchor, text="", finish="stop")


def transport_check_only_pings(self, model=None):
    """Проверка спрашивает «жив ли», а не «как тебя зовут»."""
    return {"адрес": self.server, "модели на сервере": [], "спрашиваем": model,
            "совпало": True}


# ---- ВТОРОЙ УРОВЕНЬ: проход книги, транспорт, разбор ответа --------------
# Девятнадцать проверок `test_read` и девять `test_text` бегун печатал в
# списке «без мутации»: они стерегли на вид. Через второй уровень скоро пойдут
# деньги, а `books text` — прибор, которым будут судить модель; обе половины
# обязаны краснеть от ПРАВДОПОДОБНОГО дефекта — от того, который человек и
# вправду написал бы, а не от заглушки, бросающей исключение.
#
# Где шва нет, порча возвращает ту же ВЕЛИЧИНУ, что вернул бы дефект. Сторожа
# `measure_pages` и `read_book` живут внутри функций на две сотни строк, и
# подменить там одну ветку нечем; подмена всей функции копией доказывала бы
# только то, что копия отличается от оригинала.

_real_send = vhttp.Http.send
_real_http_init = vhttp.Http.__init__
_real_data_uri = vhttp._data_uri
_real_to_json = Said.to_json
_real_read_book = vrun.read_book
_real_sniff = vrun._sniff
_real_detect_facts = vrun._detect_facts
_real_parse, _real_grid = otsl.parse, otsl.grid
_real_routes = PaddleOcrVl.routes
_real_reader_fingerprint = PaddleOcrVl.fingerprint
_real_measure = booktext.measure_pages
_real_truth_text = booktext._truth_text


def send_asks_again_on_silence(self, ask):
    """Пустой ответ переспрашивается: «модель промолчала — спрошу ещё раз».

    Переспрос после ответа — починка модели в самом чистом виде, и он платный:
    200 с пустотой это ОТВЕТ, порождение за него уже оплачено.
    """
    said = _real_send(self, ask)
    if said.answered() and not (said.text or "").strip():
        said = _real_send(self, ask)
    return said


def http_takes_retries_for_attempts(self, server=None, model=None):
    """`VLM_RETRIES` понято как число ПОПЫТОК, а не повторов.

    Промах на единицу в `range(max(1, self.retries + 1))`: при двух повторах
    обращений выходит два, и «повторяем, пока ответа не было» молча
    укорачивается — на длинной таблице это разница между донесённым ответом и
    отказом доставки.
    """
    _real_http_init(self, server, model)
    self.retries = max(0, self.retries - 1)


def data_uri_without_the_empty_guard(path):
    """Сторож пустой вырезки снят.

    На пустом белом листе эта модель выдаёт полноценные таблицы — пять разных
    за пять попыток, — и выдумка записалась бы чтением.
    """
    ext = os.path.splitext(path)[1].lower()
    raw = open(path, "rb").read()
    return ("data:" + vhttp.MIME[ext] + ";base64,"
            + base64.b64encode(raw).decode(), len(raw))


def data_uri_shrinks_the_crop(path):
    """«Ужмём вырезку, чтобы влезала в контекст».

    До модели доезжают ДРУГИЕ байты, а слепок уверяет, что послана та самая.
    Так уже было на первом уровне: переменная цикла затёрла коэффициент
    масштаба, и 36 страниц из 36 записались неразобранными при безупречном
    ответе модели.
    """
    uri, n = _real_data_uri(path)
    head, b64 = uri.split(",", 1)
    raw = base64.b64decode(b64)[:max(1, n // 2)]
    return head + "," + base64.b64encode(raw).decode(), len(raw)


def said_json_without_finish(self):
    """Запись ответа забыла, ЧЕМ кончилось порождение.

    Оборванная по потолку таблица становится неотличима от целой, а
    вендорский `otsl_pad_to_sqr_v2` возвращает её правдоподобной и короткой:
    пятый ноль сливается с первым.
    """
    d = _real_to_json(self)
    d.pop("чем кончилось", None)
    return d


def said_json_strips_the_text(self):
    """«Уберём лишние пробелы, чтобы книга была опрятной».

    Правка БАЙТОВ модели. Распознанное неприкосновенно, и это правило уже
    стоило девяти пропусков из тридцати трёх.
    """
    d = _real_to_json(self)
    if isinstance(d.get("текст"), str):
        d["текст"] = d["текст"].strip()
    return d


def said_json_writes_the_guess_into_the_text(self):
    """Догадка о виде дописана В ТЕКСТ, а не сбоку.

    Та самая беда, ради которой наблюдённое живёт отдельным файлом и связано
    с блоком по якорю: пометка дописывалась раньше, чем считалась подпись.
    """
    d = _real_to_json(self)
    if isinstance(d.get("текст"), str) and d["текст"]:
        d["текст"] += "  <!-- вид: " + _real_sniff(d["текст"]) + " -->"
    return d


def routes_read_the_pictures_too(self):
    """Рисунки тоже спрашиваем — «вдруг там подписи».

    Замер это отверг: выноски не прочитаны, выдуманная панграмма на двух
    страницах, срыв в цикл на третьей, +2100 слов мусора на двадцати. И «не
    спрошено» перестаёт быть отдельным нулём — молчание модели и наше
    объявленное молчание сливаются.
    """
    r = _real_routes(self)
    for lab, rt in list(r.items()):
        if not rt.asked():
            r[lab] = Route("OCR:", "text")
    return r


def reader_fingerprint_with_the_address(self):
    """В отпечаток чтеца дописан АДРЕС — «чтобы видеть, куда ходили».

    Величина меняется от прогона к прогону (порт подставного сервера, петля
    на боксе), «чем читали» не совпадает никогда, и возобновление
    переспрашивает книгу целиком — за деньги.
    """
    d = _real_reader_fingerprint(self)
    d["адрес"] = knobs.knob("VLM_ENDPOINT")
    return d


def reader_fingerprint_without_prompts(self):
    """Промты убраны из отпечатка — «слепок и так толстый».

    Поле «промты» снова пусто у всех прогонов проекта, а промт здесь
    единственное, чем управляют ответом: не записать его значит не записать
    прогон.
    """
    d = _real_reader_fingerprint(self)
    d.pop("промты", None)
    return d


def detect_facts_refresh_the_hash(detect_dir):
    """Слепок детекции «починен»: sha256 книги пересчитывается по тому файлу,
    который лежит сейчас.

    Так и чинят эту беду в первый раз — сверка ведь «сломалась» на
    арендованной машине. После починки она сверяет файл сам с собой и сходится
    всегда: рамки считаны по одному файлу, режем из другого, а ответ выглядит
    чтением.
    """
    f = _real_detect_facts(detect_dir)
    p = (f.get("исходник") or {}).get("путь")
    if p and os.path.exists(p):
        f = {**f, "исходник": dict(f["исходник"], **{"sha256": stamp.sha256(p)})}
    return f


def read_book_shrugs_at_zero_pages(*a, **kw):
    """Сторож «ни одной страницы к чтению» снят: выше уже есть проверка на
    пустой каталог, и второй кажется лишним. Опечатка в `--pages` после этого
    отчитывается нулями и кодом 0 — пустой прогон выглядит успешным."""
    try:
        return _real_read_book(*a, **kw)
    except SystemExit as e:
        if "ни одной страницы" not in str(e):
            raise
        return {"страниц": 0, "блоков": 0, "спрошено": 0, "не спрошено": 0,
                "прочитано": 0, "модель промолчала": 0, "отказ доставки": 0,
                "оборвано потолком": 0, "взято из прошлого прогона": 0,
                "по видам": {}}


def sniff_calls_emptiness_text(text):
    """Пустой ответ нюхается наравне с прочим и объявляется текстом.

    «Пусто» и «проза» слиты в один ответ, а это разные нули: молчание модели
    перестаёт быть видно в наблюдённом.
    """
    out = _real_sniff(text)
    return "text" if out == "пусто" else out


def parse_pads_like_the_vendor(s):
    """Разбор по-вендорски, как `otsl_pad_to_sqr_v2`: строки выравниваются
    молча, рваность НЕ считается, и порванная по потолку таблица возвращается
    правдоподобной."""
    g, t = _real_parse(s)
    return g, dict(t, **{"строк разной длины": 0, "продолжений в никуда": 0})


def grid_of_prose_is_an_empty_table(s):
    """«Вернём пустую сетку, чтобы вызывающему не проверять None».

    «Это не OTSL» и «таблица пуста» сливаются в один ноль, и проза, отданная
    вместо таблицы, перестаёт считаться отданной текстом.
    """
    return _real_grid(s) or {}


def policies_with_a_new_class():
    """Двадцать шестой класс новых весов появился в словаре детектора, а
    маршрута чтения ему никто не завёл."""
    p = dict(policy.POLICIES)
    p["PP-DocLayoutV2"] = dict(p["PP-DocLayoutV2"], sidebar="текст")
    return p


def span_ends_at_the_last_closing_mark(html, anchor):
    """Конец блока ищется по ПРЕФИКСУ закрывающей метки — «всё равно наша».

    Замена съедает соседний блок целиком вместе с его границей, и книга
    оказывается наполовину переразмеченной.
    """
    o, _c = swap.marks(anchor)
    return html.index(o) + len(o), html.rindex(swap.CLOSE.split("{}")[0])


def status_reads_only_the_journal(out_dir, log=print):
    """Прежняя редакция: `status` читает ЖУРНАЛ и не открывает книгу.

    Число якорей берётся из журнала — на нетронутой книге это ноль, и «книга
    пуста» становится неотличимо от «второй уровень по ней ещё не ходил».
    """
    j = ap.load_journal(out_dir)
    live = {k: len(v) for k, v in j["замены"].items() if v}
    log(f"якорей в журнале {len(j['замены'])}; заменено блоков {len(live)}, "
        f"всего замен {sum(live.values())}")
    if not j["замены"]:
        log("якорей нет вовсе — это не «всё заменено», а пустая книга")
    return {"якорей": len(j["замены"]), "заменено блоков": len(live),
            "всего замен": sum(live.values()), "откачено до конца": 0,
            "разошлось": 0, "нет в книге": 0, "по якорям": live}


def anchor_without_the_page(page_index, block_id):
    """Якорь сквозной, без номера страницы: на книге в пятьсот страниц
    пятьсот одинаковых `b17`, и замена второго уровня попадает не туда."""
    return f"b{block_id}"


# ---- ПРИБОР ЧТЕНИЯ: `books text` -----------------------------------------
# Сторожа `measure_pages` стоят внутри функции на две сотни строк, шва к ним
# нет. Порча возвращает ту величину, которую вернул бы дефект, — и названа по
# дефекту, а не по способу.

def measure_scores_silence_as_zero(T, P, *a, **kw):
    """Блок без ответа получает CER 0, а не None: «модель ничего не наврала».

    Молчание становится безупречным чтением, сторож «сверять было НЕЧЕГО» не
    срабатывает никогда, и последняя строка отчёта докладывает «CER 0 на
    всех».
    """
    r = _real_measure(T, P, *a, **kw)
    for rec in r["по блокам"]:
        if (rec.get("разряд") in ("текст", "артефакт по истине")
                and rec.get("CER") is None):
            rec["CER"] = 0.0
    return r


def measure_calls_artefacts_text(T, P, *a, **kw):
    """Артефакт записан разрядом «текст»: числитель последней строки снова
    считает оба разряда, а знаменатель — один. Замер до починки: «CER 0 на
    всех 130 посчитанных из 104» на книге со 104 текстовыми блоками."""
    r = _real_measure(T, P, *a, **kw)
    for rec in r["по блокам"]:
        if rec.get("разряд") == "артефакт по истине":
            rec["разряд"] = "текст"
    return r


def measure_counts_words_in_a_formula(T, P, *a, **kw):
    """Ветки текста и артефакта слиты в одну, и запись формулы понесла `WER`.

    В формуле слов не считают: величина бессмысленна, а печатается как
    измеренная. Ровно на этом поле прибор и падал — строка «худший блок»
    печатала `WER`, которого у артефакта нет, и `books text` умирал
    `KeyError` тогда, когда ему есть что сказать.
    """
    r = _real_measure(T, P, *a, **kw)
    for rec in r["по блокам"]:
        if (rec.get("разряд") == "артефакт по истине"
                and rec.get("CER") is not None):
            rec["WER"] = rec["CER"]
    return r


def measure_counts_silence_as_an_answer(T, P, *a, **kw):
    """Молчание на артефакте засчитано ОТВЕТОМ (пустым).

    «Сверять нечего» превращается в измеренный «CER 1.0» — ноль от
    непонимания, напечатанный как величина.
    """
    r = _real_measure(T, P, *a, **kw)
    r["артефакты по истине"]["без ответа"] = 0
    return r


def measure_forgets_invention_on_empty_truth(T, P, *a, **kw):
    """Счётчик «выдумано на пустой истине» снят — «его же нет в CER».

    В CER это и вправду не видно (делить не на что), и потому выдумка на
    объявленной пустоте пропадает молча.
    """
    r = _real_measure(T, P, *a, **kw)
    r["артефакты по истине"]["выдумано на пустой истине"] = 0
    return r


def truth_text_reads_only_tables(b, side=None):
    """Прежняя редакция: знаковую истину артефакта прибор не читает вовсе —
    сбоку он искал только табличную сетку.

    Замер на `bench/matematika`: 26 формул, заполненных истиной побайтово,
    давали «приманки: артефактов 26, ПРОЧИТАНО 26 (100%)» — безупречное
    чтение объявлялось стопроцентной выдумкой.
    """
    return None


def truth_text_empty_instead_of_none(b, side=None):
    """«Нет истины — пустая строка».

    Приманка становится артефактом с объявленной пустотой, и выдумка по
    штриховому чертежу считается верной работой.
    """
    return _real_truth_text(b, side) or ""


def truth_both_chooses_silently(b, side=None):
    """Сторож «и сетка, и знаки у одного блока» снят: ветка таблицы стоит
    первой и знаки выбрасываются молча — за оператора решено, какой истине
    верить."""
    return None


# ---- КНИГА: журнал, комментарии, вырезка ---------------------------------
# Проверки, дописанные в `test_apply` и `test_html_order` уже во время этой
# работы: через них тоже пойдут деньги второго уровня, и стеречь на вид им
# нечего.

_real_load_journal = ap.load_journal
_real_cut = crop.cut
_real_params = crop.params


def comments_guard_is_off(body, anchor):
    """Пятый сторож снят: сверка якорей всё равно ловит незакрытые метки.

    Не ловит: `swap.anchors` ищет `<!--bs:`, и голый `<!--` ему не якорь.
    Замер на книге из 26 блоков — «поставлено 154, снято 175, якорей 26», а
    браузер съедал нашу закрывающую метку вместе с остатком книги.
    """
    return None


def comments_are_refused_wholesale(body, anchor):
    """Сторож рубит сплеча: любой `<!--` в замене — отказ.

    Второй уровень вправе вернуть разметку с комментарием внутри, и сторож,
    запрещающий всё подряд, зелен ни на чём: он не умеет НЕ сработать.
    """
    if "<!--" in body:
        raise ap.SwapError(
            f"в замене {anchor} комментарий открыт и не закрыт: {body[:40]!r}")


def journal_unreadable_is_an_empty_one(out_dir):
    """Нечитаемый журнал принят за пустой — «не читается, начнём заново».

    Следующая же замена запишет поверх огрызка одну свою запись, и стопка
    отката ВСЕЙ книги исчезнет молча и необратимо.
    """
    try:
        return _real_load_journal(out_dir)
    except ap.SwapError:
        return {"книга": "book.html", "замены": {}}


def journal_written_in_place(out_dir, j):
    """Журнал пишется прямо на своё место, без временного файла.

    `open(p, "w")` обрезает старый файл ПЕРВЫМ делом, до единого записанного
    байта: обрыв записи (нет места, Ctrl-C, снятый диск) оставляет огрызок
    там, где лежала стопка отката всей книги. Замер: 2101 байт превращались
    в 1076, не читаемых как json.
    """
    p = os.path.join(out_dir, ap.JOURNAL)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(j, f, ensure_ascii=False, indent=1)
    return p


def clipped_only_when_nothing_is_left(rect, clip) -> bool:
    """«Срезано листом» понято как «от рамки ничего не осталось».

    Рамка, у которой лист отнял пятую часть, объявляется целой: в книгу
    уезжает вырезка половины таблицы без единой пометки, а величина «срезано
    листом» перестаёт уметь сработать.

    ПОЧЕМУ ИМЕННО ЭТА ПОРЧА. Прямая — точное сравнение вместо допуска, тот
    самый прежний дефект, — на входе этой пробы НЕ ВИДНА: при dpi 150
    координаты 100 и 300 пунктов проходят через float32 туда и обратно без
    расхождения, `raw.width == (raw & page.rect).width` точно, и проба
    остаётся зелёной. Первая её половина сегодня меряет воздух; работает
    вторая — «настоящий срез обязан остаться видимым», — и ломается она.
    """
    return bool(clip.is_empty)


def cut_without_the_named_troubles(doc, page_index, box, page_dpi, dst,
                                   **kw):
    """Вырожденная и перевёрнутая рамка снова получают ЧУЖОЙ диагноз.

    Обе дают пустое пересечение с листом, и без именных проверок читающий
    видит «не пересекается с листом» про рамку посреди бумаги — и идёт искать
    съехавшие координаты вместо дефекта самой рамки.
    """
    try:
        return _real_cut(doc, page_index, box, page_dpi, dst, **kw)
    except ValueError as e:
        if "ВЫРОЖДЕНА" in str(e) or "ПЕРЕВЁРНУТА" in str(e):
            raise ValueError(
                f"рамка {tuple(box)} на стр. {page_index} не пересекается с "
                f"листом") from None
        raise


def params_clamps_the_margin(page_dpi=None):
    """Отрицательное `CROP_MARGIN` молча зажато в ноль.

    Ручка при этом объявлена действующей, а на деле она РЕЖЕТ рамку модели:
    замер `CROP_MARGIN=-0.1` съедал десятую долю с каждой стороны, и обе
    величины среза стояли False.
    """
    def clamped(name):
        v = _real_knob(name)
        return "0" if name == "CROP_MARGIN" and float(v) < 0 else v

    with attrs(knobs, knob=clamped):
        return _real_params(page_dpi)


def params_takes_the_dpi_from_the_environment(page_dpi=None):
    """Резкость вырезки берётся из окружения, а не у ДЕТЕКЦИИ.

    Замер: детекция `bench/atlas` при PAGE_DPI=150, сборка при умолчании —
    «вырезок 26 при 144 dpi», хотя координаты пересчитаны из 150.
    """
    return _real_params(None)


def nesting_compares_raw_order(arts):
    """Прежняя строка: ранги сравниваются кортежами `(order, block_id)`.

    `Block.order = None` контракт разрешает прямо — ранга не даёт ни один
    адаптер из трёх, — и пара «ранг есть / ранга нет» на одном прямоугольнике
    роняет ВСЮ сборку книги: `TypeError: '>=' not supported between instances
    of 'NoneType' and 'int'`.
    """
    def area(b):
        return max(0.0, b.box[2] - b.box[0]) * max(0.0, b.box[3] - b.box[1])

    inner = {}
    for b in arts:
        for o in arts:
            if o.block_id == b.block_id or not dhtml._covered(b.box, o.box):
                continue
            ab, ao = area(b), area(o)
            if ab > ao * 1.02:
                continue
            if (abs(ab - ao) <= ao * 0.02
                    and (o.order, o.block_id) >= (b.order, b.block_id)):
                continue
            inner[b.block_id] = o.block_id
            break
    return inner


def sheet_trouble_with_two_marks(blocks, arts):
    """Прежняя редакция: отказов лист даёт три, а пометки было две.

    Лист с одной колонцифрой (`footer`, разряд «служебное») получал красное
    «вся полоса ушла в картинки» при `data-доля-в-картинках="0.00"` — элемент
    противоречил сам себе. Замер: `bench/atlas` стр. 0; на всей книге «страниц
    без единого текстового блока» стояло 9 при восьми настоящих.
    """
    if not blocks:
        return "пусто"
    if any(policy.role(b.label) == "текст" for b in blocks):
        return None
    return "без-текста"


def anchor_of_a_private_copy(page_index, block_id):
    """`doc/feed` завёл СВОЮ копию правила якоря.

    Сегодня она совпадает строкой, и разойдутся копии молча: feed.json звал бы
    куски одними именами, книга и blocks.json другими, а `books apply` отвечал
    бы «якоря нет в книге» на каждый блок чтения.
    """
    return f"p{page_index:04d}-b{block_id}"


def mutations():
    m = [
        ("журнал не сохраняет снятое",
         lambda: attrs(ap, save_journal=_journal_without_taken),
         [("test_apply", "test_journal_keeps_what_was_taken"),
          ("test_apply", "test_put_then_undo_restores_the_book_byte_for_byte")]),

        ("вид содержимого принимается любой",
         lambda: attrs(ap, KINDS=ap.KINDS + ("markdown",)),
         [("test_apply", "test_unknown_kind_is_refused")]),

        ("журнал выдумывает стопку там, где замен не было",
         lambda: attrs(ap, load_journal=_journal_invents_a_stack),
         [("test_apply", "test_undo_without_a_swap_is_loud_and_distinct")]),

        ("сверка набора якорей после замены снята",
         lambda: attrs(ap, _anchors_unchanged=lambda a, b: True),
         [("test_apply", "test_unterminated_mark_is_caught_by_the_anchor_guard")]),

        ("замена не проверяет вставляемый кусок",
         lambda: attrs(ap, _check_fragment=lambda *a, **k: None),
         [("test_apply", "test_fragment_with_marks_is_refused_by_the_fragment_check"),
          ("test_apply", "test_empty_fragment_is_refused")]),

        ("стопка отката схлопнута в последнее значение",
         lambda: attrs(ap, save_journal=_flat_journal),
         [("test_apply", "test_stack_unwinds_in_reverse_order")]),

        ("откат не сверяет, что лежит на месте блока",
         lambda: attrs(ap, _same=lambda now, promised: True),
         [("test_apply", "test_edit_outside_the_journal_blocks_undo")]),

        ("сторож метрики не смотрит на слово «наш»",
         lambda: attrs(metrics, _model_has_rank=guard_without_words),
         [("test_order_contract", "test_guard_reads_every_value_as_intended")]),

        ("молчащая истина считается размеченной (беда hard36)",
         lambda: attrs(metrics, _truth_order_state=truth_state_defaults_to_marked),
         [("test_order_contract", "test_truth_side_has_three_answers_not_two")]),

        # ПРОБА ПЕРЕЦЕЛЕНА, а не выброшена. Здесь стояло «адаптер написал
        # «Наш» с заглавной», и она ловилась ровно потому, что сторож сверял
        # регистр. Сверка регистра сама была дефектом: `doclayout.fingerprint`
        # пишет «НАШ» с заглавной, и такая строка, попав в meta страницы,
        # читалась бы как ранг модели. Регистр снят — и прежняя порча
        # перестала быть порчей, то есть проба стала непроваливаемой. Проба,
        # которая не может провалиться, хуже отсутствующей: она докладывает
        # об исправности, ничего не проверив. Теперь портится то, что
        # ДЕЙСТВИТЕЛЬНО держит договор, — снятие регистра в самом стороже.
        # Значение, которого нет в таблице договора: адаптер поменял слова, а
        # таблицу никто не дописал. Сторож примет его за РАНГ МОДЕЛИ (не
        # начинается со слова «наш») и метрика напечатает процент по нашей же
        # нумерации — та самая беда hard36, только с другого конца.
        # Портится ХВОСТ, который дописывает адаптер, а не само правило:
        # правило теперь одно (`order.WORDS`) и таблица договора выводится из
        # него же, так что подмена правила двигает обе стороны разом и порчей
        # не является. А хвост адаптер дописывает сам — вот он и есть то
        # место, где значение может уехать мимо таблицы.
        ("адаптер завёл значение мимо таблицы договора",
         lambda: sources("models/doclayout.py",
                         '+ ": модель ранга не даёт"',
                         '+ " (ранга модель не даёт)"'),
         [("test_order_contract", "test_no_unknown_order_values")]),

        # Второй читатель договора — сборщик книги. Прежде он держался на
        # честном слове: подмена его правила своей копией не роняла ни одной
        # проверки из шестидесяти.
        ("сборщик книги завёл СВОЮ копию правила порядка",
         lambda: attrs(dhtml, _ours=lambda v: isinstance(v, str)
                       and v.strip().startswith("наш")),
         [("test_html_order",
           "test_book_builder_reads_the_order_rule_through_the_one_contract")]),

        ("сторож перестал снимать регистр",
         lambda: attrs(mbase, ours_order=guard_case_sensitive),
         [("test_order_contract", "test_guard_ignores_case")]),

        ("адаптер вовсе не сказал, чей порядок",
         lambda: sources("models/yolox_layout.py",
                         '"порядок чтения": order.WORDS[which],', ""),
         [("test_order_contract", "test_adapters_declare_order_rule_at_all")]),

        ("правило конвейера перестало начинаться со слова «наш»",
         lambda: attrs(dh._DoclingPipeline, ORDER_RULE={
             "post": "порядок docling", "full": "порядок docling"}),
         [("test_order_contract",
           "test_our_order_values_start_with_lowercase_nash")]),

        ("конвейер при off пересобирает рамки и дописывает ключ",
         lambda: attrs(dh.DoclingHeron, _run_pipeline=pipeline_touches_at_off),
         [("test_docling_pipeline", "test_off_returns_the_very_same_frames"),
          ("test_docling_pipeline", "test_off_adds_exactly_one_meta_key")]),

        ("ключ конвейера уехал в конец meta",
         lambda: sources("models/docling_heron.py",
                         "                  **pipe_meta,\n", ""),
         [("test_docling_pipeline",
           "test_off_keeps_meta_key_order_byte_for_byte")]),

        ("умолчание ручки переставили на full",
         lambda: attrs(knobs.KNOB["DOCLING_PIPELINE"], default="full"),
         [("test_docling_pipeline", "test_pipeline_default_is_off")]),

        ("в режимы ручки добавили четвёртый",
         lambda: attrs(dh, PIPELINE_MODES=("off", "post", "full", "вкл")),
         [("test_docling_pipeline", "test_three_modes_not_two"),
          ("test_docling_pipeline", "test_unknown_mode_dies_loudly")]),

        ("перевод ярлыков угадывается правилом «чего не знаю — то текст»",
         lambda: attrs(dh, EGRET_TO_DOCLING=GuessingTranslation(
             dh.EGRET_TO_DOCLING)),
         [("test_docling_pipeline", "test_unknown_label_dies_at_construction")],
         "нет пакета docling"),

        ("витринное имя egret осталось непереведённым",
         lambda: attrs(dh, EGRET_TO_DOCLING=egret_without_translation()),
         [("test_docling_pipeline", "test_egret_names_translate_whole"),
          ("test_docling_pipeline",
           "test_translation_covers_both_dictionaries")],
         "нет пакета docling"),

        ("словарь политики egret потерял класс",
         lambda: attrs(policy, DOCLING_EGRET=docling_egret_short()),
         [("test_docling_pipeline",
           "test_translation_covers_both_dictionaries")]),

        ("политика прощает незнакомый ярлык",
         lambda: attrs(policy, check=check_that_forgives),
         [("test_policy", "test_unknown_label_raises"),
          ("test_policy", "test_label_missing_from_model_also_raises"),
          ("test_policy", "test_unknown_policy_name_raises"),
          ("test_policy", "test_check_does_not_use_the_union")]),

        ("политика сверяется с объединением словарей",
         lambda: attrs(policy, check=check_against_the_union),
         [("test_policy", "test_check_passes_on_its_own_dictionary")]),

        ("разряд угадывается для неизвестного ярлыка",
         lambda: attrs(policy, ROLE=GuessingRole(policy.ROLE)),
         [("test_policy", "test_role_raises_on_unknown")]),

        ("разрядов стало два вместо трёх",
         lambda: attrs(policy, ROLES=("текст", "артефакт")),
         [("test_policy", "test_every_label_has_one_of_three_roles")]),

        ("в объединении у table другой разряд",
         lambda: attrs(policy, ROLE=flipped_role()),
         [("test_policy", "test_union_agrees_with_every_dictionary"),
          ("test_policy", "test_artefacts_are_not_empty_and_are_artefacts")]),

        ("два словаря политики совпали",
         lambda: attrs(policy, POLICIES=duplicated_policy()),
         [("test_policy", "test_for_labels_picks_by_dictionary_not_by_name")]),

        ("адаптер объявил чужую политику",
         lambda: attrs(dh.DoclingHeron, policy_name="DocLayNet"),
         [("test_policy", "test_adapters_and_policies_agree")]),

        ("слепок политики несёт только артефакты",
         lambda: attrs(policy, snapshot=snapshot_only_artefacts),
         [("test_policy", "test_snapshot_carries_whole_dictionary")]),

        ("span берёт первую метку (прежняя редакция)",
         lambda: attrs(swap, span=span_takes_the_first),
         [("test_swap", "test_double_anchor_is_loud"),
          ("test_swap", "test_inverted_anchor_is_loud"),
          ("test_swap", "test_missing_anchor_is_loud"),
          ("test_swap", "test_crossed_anchors_are_loud")]),

        ("span не ловит перекрёста меток",
         lambda: attrs(swap, span=span_without_crossing),
         [("test_swap", "test_crossed_anchors_are_loud")]),

        ("span считает вложение перекрёстом",
         lambda: attrs(swap, span=span_calls_nesting_a_crossing),
         [("test_swap", "test_nested_anchors_are_not_a_crossing")]),

        ("метка узнаётся по префиксу, а не поимённо",
         lambda: attrs(swap, marks=marks_by_prefix),
         [("test_swap", "test_wrap_and_get_are_inverse"),
          ("test_swap", "test_broken_markup_from_the_model_goes_in_as_is"),
          ("test_swap", "test_swap_leaves_the_neighbour_byte_for_byte"),
          ("test_swap", "test_nested_anchors_are_not_a_crossing")]),

        ("swap не возвращает снятое — откат невозможен",
         lambda: attrs(swap, swap=swap_forgets_what_it_removed),
         [("test_swap",
           "test_swap_returns_what_it_removed_and_restore_puts_it_back")]),

        ("порядок якорей отсортирован",
         lambda: attrs(swap, anchors=anchors_sorted),
         [("test_swap", "test_anchors_keep_document_order")]),

        ("оборванная метка молча даёт пустой список",
         lambda: attrs(swap, anchors=anchors_swallow_unterminated),
         [("test_swap", "test_unterminated_mark_is_loud")]),

        ("реестр отдаёт пустую строку вместо падения",
         lambda: attrs(knobs, knob=knob_returns_empty),
         [("test_knobs", "test_unknown_knob_raises_not_returns_empty")]),

        ("пустая строка снаружи проигрывает умолчанию",
         lambda: attrs(knobs, knob=knob_ignores_empty),
         [("test_knobs", "test_snapshot_tells_set_from_default")]),

        ("слепок пропускает ручки-долги",
         lambda: attrs(knobs, snapshot=snapshot_skips_debts),
         [("test_knobs", "test_snapshot_holds_every_knob_with_every_field")]),

        ("на машину уезжают и умолчания",
         lambda: attrs(knobs, passthrough=passthrough_with_defaults),
         [("test_knobs", "test_passthrough_carries_only_what_was_set")]),

        ("в реестре ручка без потребителя",
         lambda: attrs(knobs, KNOBS=knobs_with_phantom()),
         [("test_knobs", "test_audit_finds_no_disagreement"),
          ("test_knobs", "test_readers_finds_consumers_and_counts_them")]),

        ("имя ручки задвоено",
         lambda: attrs(knobs, KNOBS=knobs_with_duplicate()),
         [("test_knobs", "test_names_are_unique")]),

        ("умолчание ручки не строка",
         lambda: attrs(knobs, KNOBS=knobs_with_int_default()),
         [("test_knobs", "test_defaults_are_strings")]),

        ("адаптер не объявил ручку, которую читает",
         lambda: attrs(dh.DoclingHeron,
                       knobs_read=lambda self: ("LAYOUT_SCORE_THRESHOLD",)),
         [("test_knobs", "test_adapters_declare_the_knobs_they_read")]),

        ("ручка off не дошла до адаптера — конвейер построен всё равно",
         lambda: attrs(knobs, knob=knob_says_post),
         [("test_docling_pipeline", "test_adapter_at_off_builds_no_pipeline")],
         "медленная, только с --slow"),

        # ---- второй уровень ------------------------------------------
        ("маршрут выводится из разряда, а не объявляется",
         lambda: attrs(PaddleOcrVl, routes=routes_guess_by_role),
         [("test_read", "test_kind_comes_from_the_prompt_not_from_the_answer"),
          ("test_read", "test_silence_carries_a_reason")]),

        ("cover прощает ярлык без маршрута",
         lambda: attrs(Reader, cover=cover_forgives),
         [("test_read", "test_unknown_label_is_loud")]),

        ("маршрут не сверяет ни вид, ни причину молчания",
         lambda: attrs(Route, check=route_check_forgives),
         [("test_read", "test_route_with_unknown_kind_is_loud")]),

        ("прибор чтения снова слепнет на OTSL",
         lambda: attrs(booktext, _answer_grid=grid_only_from_html),
         [("test_read", "test_otsl_grid_matches_html_grid_cell_for_cell"),
          ("test_text",
           "test_table_in_otsl_scores_like_the_same_table_in_html")]),

        ("отказ доставки записывается молчанием модели",
         lambda: attrs(vhttp.Http, send=refusal_looks_like_silence),
         [("test_read", "test_delivery_refusal_does_not_look_like_silence"),
          ("test_read", "test_delivery_refusal_is_a_value_not_a_throw")]),

        ("проверка адреса спрашивает «жив ли», а не «как тебя зовут»",
         lambda: attrs(vhttp.Http, check=transport_check_only_pings),
         [("test_read", "test_wrong_model_name_stops_the_run"),
          ("test_read", "test_transport_asks_who_is_answering")]),

        # ТРЕТЬЯ копия правила якоря нашлась уже после починки двух: `feed.py`
        # свели с `html.anchor_of`, а `doc/apply.from_read` завёл свою в тот же
        # день. Мутация именно поэтому: копия заводится не по злому умыслу, а
        # потому что строка `f"p{i:04d}-b{j}"` короче импорта.
        ("doc/apply завёл свою копию правила якоря",
         lambda: attrs(ap, anchor_of=anchor_of_a_private_copy),
         [("test_html_order", "test_the_anchor_rule_has_exactly_one_home")]),

        # --- слепок входа: «вывести не удалось» это величина, а не согласие
        ("невыведенная форма отпечатка объявляется полной",
         lambda: attrs(replay, shape=shape_silent_about_underived),
         [("test_knobs",
           "test_shape_that_could_not_be_derived_is_loud_not_silent")]),

        ("разбор отпечатка ослеп на все адаптеры",
         lambda: attrs(replay, _returned=lambda *a, **k: set()),
         [("test_knobs", "test_derivable_shape_still_requires_every_value")]),

        # --- пропуск: бегун обязан быть любой
        ("пропуск выбирается по установленному, а не по бегуну",
         lambda: attrs(support, skip=skip_by_what_is_installed),
         [("test_knobs",
           "test_skip_under_our_runner_does_not_depend_on_pytest_being_installed")]),

        ("пропуск всегда наш — чужой бегун засчитает провал",
         lambda: attrs(support, skip=skip_always_ours),
         [("test_knobs", "test_skip_under_pytest_stays_a_pytest_skip")]),

        ("бегун не знает чужого пропуска",
         lambda: attrs(support, foreign_skip=lambda e: False),
         [("test_knobs",
           "test_runner_counts_a_foreign_skip_as_a_skip_and_survives")]),

        ("бегун считает пропуском ЛЮБОЕ BaseException",
         lambda: attrs(support, foreign_skip=lambda e: True),
         [("test_knobs", "test_runner_still_lets_a_real_interrupt_out")]),

        # --- порядок, которого модель не дала
        # Шов переехал вместе с правилом: прежде портился `our_order_key` в
        # `doclayout`, теперь — общая `order.permutation`. Порча та же по
        # существу: порядок, которого модель не дала, не задан вовсе, и рамки
        # уходят в книгу в том порядке, в каком их отдал граф.
        ("порядок, которого модель не дала, не задан вовсе",
         lambda: attrs(order, permutation=lambda labels, boxes, w, h, index,
                       vocab, which=None: list(range(len(boxes)))),
         [("test_order_contract",
           "test_no_rank_means_our_rule_not_the_order_of_the_graph")]),

        ("наше правило вытеснило ранг модели",
         lambda: attrs(doclayout, has_rank=lambda out: False),
         [("test_order_contract", "test_model_rank_still_wins_over_our_rule")]),

        # --- линейка, которой судят порядок сборки
        ("варианты сборки складываются раз и при умолчании",
         lambda: attrs(metrics, _order_variants=variants_built_once_at_defaults),
         [("test_order_contract",
           "test_floor_variant_is_a_floor_at_every_point_of_the_sweep")]),

        ("развёртка ужата до одной точки",
         lambda: attrs(metrics, COLUMN_SWEEP={"overlap": (0.50,)}),
         [("test_order_contract",
           "test_floor_built_at_defaults_would_not_be_a_floor")]),

        ("приговор считается по НЕпересобранным вариантам",
         lambda: attrs(metrics, column_jumps_ranking=ranking_without_rebuilding),
         [("test_order_contract",
           "test_ranking_rebuilds_the_variants_it_measures")]),

        ("своя резкость делится на ширину ЛИСТА, а не размещения",
         lambda: attrs(crop, native_dpi=native_dpi_by_the_sheet),
         [("test_html_order",
           "test_native_dpi_divides_by_the_placement_not_by_the_sheet")]),

        ("резкостью страницы объявляется любая картинка на ней",
         lambda: attrs(crop, native_dpi=native_dpi_takes_any_image),
         [("test_html_order",
           "test_native_dpi_says_nothing_when_there_is_nothing_to_say")]),

        # --- годность по чернилам ---------------------------------------
        ("нарезка рамок доверена numpy",
         lambda: attrs(fit, _clip=clip_that_trusts_numpy),
         [("test_fitness", "test_box_off_the_sheet_covers_nothing")]),

        ("пиксель под двумя рамками считается дважды",
         lambda: attrs(fit, _carried_as_text=carried_as_text_by_double_counting),
         [("test_fitness", "test_pixel_under_two_boxes_counts_once")]),

        ("отчёт прежней редакции: один порог, ни dpi, ни слова о слепоте",
         lambda: attrs(fit, report=report_of_the_previous_edition),
         [("test_fitness", "test_report_declares_the_whole_ruler"),
          ("test_fitness", "test_report_says_out_loud_that_it_is_blind_to_merging"),
          ("test_fitness", "test_blank_page_is_not_a_total_loss"),
          ("test_fitness", "test_truth_without_artefacts_is_not_a_missing_truth"),
          ("test_fitness", "test_object_without_ink_is_a_bench_defect_not_a_score")]),

        ("память растра чистится целиком при переполнении",
         lambda: attrs(fit, _ink_of=ink_memory_that_clears_itself),
         [("test_fitness",
           "test_ink_memory_does_not_thrash_on_a_book_bigger_than_the_cap")]),

        # Память не помнит вовсе. Цена померена: 120 страниц золотого стенда
        # рендерятся с порогом за 33.4 с на свободной машине, то есть 278 мс
        # на страницу; батарея зовёт `measure` 24 раза и читает растр 23
        # прохода, и на 600 страницах это 64 минуты рендера против восьми.
        ("память растра не помнит ничего",
         lambda: attrs(fit, _ink_of=lambda pdf, doc, i, dpi: fit._ink(doc[i], dpi)),
         [("test_fitness", "test_ink_memory_pays_nothing_twice_when_the_book_fits"),
          ("test_fitness",
           "test_ink_memory_does_not_thrash_on_a_book_bigger_than_the_cap")]),

        # Вытеснение старейшего вместо удержания набранного. Отдельная мутация,
        # а не разновидность предыдущей: потолок в байтах и упаковка по биту
        # были на месте, а экономии всё равно не было — при последовательном
        # обходе вытесняется ровно то, с чего начнётся следующий проход.
        # Замер на настоящем следе обращений и настоящих формах страниц
        # золотого стенда, 23 прохода по 600 страницам: вытеснением 2400
        # рендеров против 1800, а на двух книгах подряд 4800 против 3600.
        ("память растра вытесняет старейшее",
         lambda: attrs(fit, _ink_of=ink_memory_that_evicts_the_oldest),
         [("test_fitness",
           "test_ink_memory_does_not_thrash_on_a_book_bigger_than_the_cap")]),

        # Потолок, не вмещающий стенда, ради которого выведен. Здесь стояло
        # «460 МБ булевыми и 58 МБ упакованными, влезают целиком» — мимо в
        # шесть с половиной раз: стенд это 2998 и 375 МиБ, и 256 МиБ держали
        # 362 страницы из 600.
        # Своя книга держится, а чужая не выселяется — то есть ровно прежнее
        # «удержание набранного». Одна книга от этого не страдает, вторая в
        # том же процессе не получает ни байта: на настоящем следе обращений
        # 15600 рендеров против 3600.
        ("память растра не уступает места следующей книге",
         lambda: attrs(fit, _evict_foreign=lambda pdf: False),
         [("test_fitness", "test_ink_memory_makes_room_for_the_next_book")]),

        ("потолок памяти опущен ниже золотого стенда",
         lambda: attrs(fit, _INK_CACHE_MAX_BYTES=256 << 20),
         [("test_fitness", "test_the_cap_holds_the_bench_it_was_raised_for")]),

        # --- построчные: до этих мест `attrs` не дотягивается ---------------
        ("сторож молчания модели снят",
         lambda: one_line("booksmith.fitness",
                          "        if i not in M:\n"
                          "            raise metrics.MetricError(",
                          "        if i not in M:\n"
                          "            continue\n"
                          "        if False:\n"
                          "            raise metrics.MetricError("),
         [("test_fitness", "test_page_the_model_did_not_mark_is_loud")]),

        ("свесившаяся рамка отвергается целиком",
         lambda: one_line("booksmith.fitness",
                          "    x0, y0 = max(0, x0), max(0, y0)\n"
                          "    x1, y1 = min(w - 1, x1), min(h - 1, y1)",
                          "    if x0 < 0 or y0 < 0 or x1 > w - 1 or y1 > h - 1:\n"
                          "        return None"),
         [("test_fitness", "test_box_hanging_over_the_edge_is_cut_by_the_sheet")]),

        ("рамка, шире объекта в полтора раза, его не везёт",
         lambda: one_line("booksmith.fitness",
                          "                if one > best:",
                          "                if (x[2] - x[0]) > 1.5 * "
                          "(b['box'][2] - b['box'][0]):\n"
                          "                    continue\n"
                          "                if one > best:"),
         [("test_fitness",
           "test_merging_two_objects_into_one_box_does_not_lower_the_numbers"),
          ("test_fitness", "test_the_number_that_grows_when_boxes_merge")]),

        # Единственное число прибора, которое от слияния РАСТЁТ. Считай его по
        # рамке, а не по объектам, — и оно снова замолчит: рамок с несколькими
        # объектами на bench/hard36 33 против 35 при слиянии, а самих объектов
        # 309 против 385.
        ("«не в одиночку» считает рамки, а не объекты",
         lambda: one_line("booksmith.fitness",
                          '                res["приехал не в одиночку"] += k',
                          '                res["приехал не в одиночку"] += 1'),
         [("test_fitness", "test_the_number_that_grows_when_boxes_merge")]),

        ("порог чернил разошёлся с порогом стенда",
         lambda: attrs(fit, INK=fit.INK + 1),
         [("test_fitness", "test_the_ink_threshold_has_one_meaning_in_both_homes")]),

        ("порог чернил выпал из ключа памяти",
         lambda: attrs(fit, _ink_of=ink_memory_without_the_threshold),
         [("test_fitness", "test_ink_threshold_is_part_of_the_memory_key")]),

        ("итог батареи не считает непомеренное",
         lambda: attrs(fit, mutations=battery_summary_without_the_unmeasured),
         [("test_fitness", "test_battery_counts_what_it_could_not_measure")]),

        ("батарея портит только вывод модели",
         lambda: attrs(fit, mutations=battery_that_corrupts_only_the_model),
         [("test_fitness", "test_battery_corrupts_all_three_sides")]),

        # Возврат к `put` внутри цикла: правило снова слито с вводом-выводом,
        # и книга перечитывается на каждую замену.
        ("пакетная замена читает книгу на каждый блок",
         lambda: one_line(
             "booksmith.doc.apply",
             "                html, entry, _ = put_into(html, anchor, body,",
             "                put(out_dir, anchor, body, source=src,\n"
             "                    log=lambda *a: None); entry = {}; _x = ("),
         [("test_apply", "test_bulk_reads_the_book_once_not_once_per_block")]),

        ("разряды блоков берутся по одному",
         lambda: one_line("booksmith.doc.apply",
                          "    roles = block_roles(out_dir)",
                          "    roles = {}"),
         [("test_apply", "test_bulk_reads_the_book_once_not_once_per_block")]),

        # --- сроки аренды: оба потолка отбраковывали ГОДНЫЕ машины --------
        # Возврат к счёту «пришло ли ровно столько мегабайт»: недобор снова
        # становится нулём, то есть «мы медленные» = «машина сломана».
        ("зонд снова мерит размер, а не время",
         lambda: one_line("booksmith.remote.box",
                          "        return got * 8 / 1e6 / dt",
                          "        return got * 8 / 1e6 / dt "
                          "if got >= 4 * 1024 * 1024 else 0.0"),
         [("test_rent_deadlines",
           "test_a_narrow_channel_is_measured_not_called_broken")]),

        ("зонд занижает скорость вдесятеро",
         lambda: one_line("booksmith.remote.box",
                          "        return got * 8 / 1e6 / dt",
                          "        return got * 8 / 1e6 / dt / 10"),
         [("test_rent_deadlines",
           "test_a_broken_machine_still_gives_a_number_below_any_floor")]),

        # Возврат к сравнению с порогом отбраковки: одна ручка снова тянет в
        # две стороны, и ослабление порога развязывает руки вечному списку.
        ("вечный список снова решает по порогу отбраковки",
         lambda: one_line("booksmith.remote.runner",
                          "    if best_link < 3 * link:",
                          "    if ours < 2 * link:"),
         # Только эта: подпись мутация тела не трогает, у неё своя ниже.
         [("test_rent_deadlines",
           "test_a_machine_is_blamed_only_with_a_witness")]),

        # Порог отбраковки возвращается в ПОДПИСЬ сторожа — то есть одна
        # ручка снова получает две противоположные работы.
        ("порог отбраковки вернулся в сторож вечного списка",
         lambda: one_line(
             "booksmith.remote.runner",
             "def blame_machine(offer: dict, reason: str, *, ours: float, "
             "link: float,",
             "def blame_machine(offer: dict, reason: str, *, ours: float, "
             "link: float, limit: float = 2.0,"),
         [("test_rent_deadlines",
           "test_the_verdict_cannot_depend_on_the_rejection_floor")]),

        ("свидетель для вечного списка больше не нужен",
         lambda: one_line("booksmith.remote.runner",
                          "    if best_link < 3 * link:",
                          "    if False:"),
         [("test_rent_deadlines",
           "test_a_machine_is_blamed_only_with_a_witness")]),

        ("мёртвая труба выдаётся за живой канал",
         lambda: one_line("booksmith.remote.box",
                          "        return got * 8 / 1e6 / dt",
                          "        return max(got * 8 / 1e6 / dt, 0.5)"),
         [("test_rent_deadlines", "test_a_dead_channel_is_the_only_zero")]),

        ("подъём контейнера снова режется своим потолком",
         lambda: one_line(
             "booksmith.remote.runner",
             "    vast.wait_running(iid, timeout=max(30.0, "
             "t_end - time.time()))",
             "    vast.wait_running(iid, timeout=max(30.0, min(120.0, "
             "t_end - time.time())))"),
         [("test_rent_deadlines",
           "test_connect_gives_the_boot_the_whole_attempt")]),

        ("отступы уничтожения снова плоские",
         lambda: attrs(vastmod.Vast, RETRY_S=(4, 4, 4, 4, 4)),
         [("test_rent_deadlines",
           "test_destroy_backs_off_instead_of_hammering")]),

        ("ждём дольше, чем машина живёт сама",
         lambda: attrs(vastmod.Vast, RETRY_S=(4, 40, 400, 4000, 40000)),
         [("test_rent_deadlines",
           "test_destroy_backs_off_instead_of_hammering")]),

        ("отказ доступа зовётся отказом машины",
         lambda: one_line("booksmith.remote.vast",
                          '                нас_не_пускают = any(k in str(e) '
                          'for k in ("403", "429"))',
                          "                нас_не_пускают = False"),
         [("test_rent_deadlines",
           "test_a_refusal_of_access_is_named_apart_from_a_stubborn_machine")]),

        # --- порядок сборки: одно правило на проект ------------------------
        ("перевод ярлыков потерял одну политику",
         lambda: attrs(order, _LABELS={k: v for k, v in order._LABELS.items()
                                       if k != "DocLayNet"}),
         [("test_order", "test_every_dictionary_has_a_translation")]),

        ("перевод целит в ярлык, которого правила не знают",
         lambda: attrs(order, _LABELS=dict(
             order._LABELS,
             DocLayNet=dict(order._LABELS["DocLayNet"], Table="section_header"))),
         [("test_order", "test_translations_name_only_labels_the_rules_look_at")]),

        ("в ключе перевода опечатка — он не сработает никогда",
         lambda: attrs(order, _LABELS=dict(
             order._LABELS,
             DocLayNet={("Tabel" if k == "Table" else k): v
                        for k, v in order._LABELS["DocLayNet"].items()})),
         [("test_order", "test_translations_use_labels_that_exist")]),

        # Правилу `ours` ярлыки не нужны вовсе; спрашивать под него политику
        # значит ронять прогон на словаре, которого правило и не касается.
        ("правило ours требует описанной политики",
         lambda: one_line("booksmith.order",
                          '    if (which or rule()) == "ours":\n        return None',
                          "    pass"),
         [("test_order", "test_ours_needs_neither_labels_nor_docling")]),

        ("правила порядка теряют рамку, а не переставляют",
         lambda: one_line("booksmith.order",
                          "    out = [e.cid for e in _predictor()"
                          ".predict_reading_order(els)]",
                          "    out = [e.cid for e in _predictor()"
                          ".predict_reading_order(els)][:-1]"),
         [("test_order", "test_docling_returns_a_permutation_and_touches_no_box")]),

        ("незнакомое правило сборки принимается молча",
         lambda: one_line("booksmith.order", "    if v not in RULES:",
                          "    if False:"),
         [("test_order", "test_an_unknown_rule_dies_loudly")]),

        # Второй экземпляр правила в адаптере — ровно то, чем болел
        # `docling_heron`: сортировал одним ключом, объявлял другой.
        ("адаптер снова сортирует своим ключом",
         lambda: source_swap("models/yolox_layout.py",
                             "        which = order.rule()",
                             "        kept.sort(key=lambda t: (t[2][1],"
                             " t[2][0]))\n        which = order.rule()"),
         [("test_order", "test_no_adapter_sorts_by_itself_any_more")]),

        # --- прибор, которым смотрят ГЛАЗАМИ: проверок не было вовсе -----
        # Бьёт по МЕСТУ ПОЧИНКИ в cli.py, а не по разборщику. Первая редакция
        # проверки звала `detect.parse_pages` напрямую и мимо `cmd_overlay`:
        # откат cli.py целиком не красил НИ ОДНОЙ проверки из 163.
        ("cmd_overlay зовёт свой разбор страниц вместо общего",
         lambda: one_line("booksmith.cli",
                          "only = detect.parse_pages(a.pages, total)",
                          'only = [int(x) for x in '
                          'a.pages.replace(",", " ").split()]'),
         [("test_overlay", "test_pages_are_counted_from_one_like_detect"),
          ("test_overlay", "test_a_page_out_of_the_book_is_loud")]),

        # Зеркальная сторона того же сторожа: чинил обе, проверял одну.
        ("страница, которой нет у истины, пропускается молча",
         lambda: one_line("booksmith.overlay",
                          'counts["нет у истины"].append(i)',
                          "pass"),
         [("test_overlay",
           "test_a_page_missing_from_the_truth_is_named_too")]),

        ("лист кричит по ярлыку, а не по правилу метрики",
         lambda: one_line(
             "booksmith.overlay",
             '                (loud if kind == "лишняя рамка" '
             'else quiet).append(x)',
             '                loud.append(x)'),
         [("test_overlay",
           "test_the_sheet_shouts_at_exactly_what_the_number_calls_extra")]),

        ("смена ярлыка красится как лишняя рамка",
         lambda: attrs(overlay, ЯРЛЫК=overlay.ЛИШНЯЯ),
         [("test_overlay",
           "test_a_changed_label_is_not_painted_like_an_extra_box")]),

        # --- yolox: величина, которая решает все координаты ---------------
        ("фильтр ужатия снова литерал на месте",
         lambda: source_swap("models/yolox_layout.py",
                             "interpolation=INTERP", "interpolation=1"),
         [("test_yolox_fingerprint",
           "test_the_resize_filter_is_a_named_constant_not_a_literal")]),

        ("фильтр ужатия убран из отпечатка",
         lambda: source_swap("models/yolox_layout.py",
                             '"фильтр cv2": INTERP', '"подложка2": PAD'),
         [("test_yolox_fingerprint",
           "test_the_fingerprint_declares_the_resize_filter")]),

        # --- повтор не смеет растить стопку отката -------------------------
        # Снимешь — и второй `books apply` на той же книге удвоит журнал, не
        # изменив ни знака: 412 замен станут 824, а `--undo` придётся звать
        # дважды. Ровно на этом держится безопасность умолчания команды.
        ("повтор замены снова растит стопку отката",
         lambda: one_line("booksmith.doc.apply",
                          "    if swap.get(html, anchor) == body:",
                          "    if False:"),
         [("test_apply", "test_putting_the_same_markup_twice_changes_nothing")]),

        # --- порядок книги: дыра, которую не ловило НИЧТО ------------------
        # Скептик перевернул обход блоков одной строкой, и полная батарея
        # осталась зелёной: 201 проверка, 0 провалов. Книга читалась бы задом
        # наперёд, а все три прибора мерят СТРАНИЦЫ детекции, не документ.
        ("книга собирается в перевёрнутом порядке",
         lambda: one_line("booksmith.doc.html",
                          "        for b in page.blocks:",
                          "        for b in reversed(page.blocks):"),
         [("test_html_order",
           "test_the_book_carries_blocks_in_the_order_it_walked_them")]),

        # Сторож ЛЕГКО сделать тавтологичным, и первая редакция такой и была:
        # ожидание копилось внутри стерегомого цикла. Три порчи не поймались
        # ни одна. Разбор АСТ в проверке требует, чтобы оно жило снаружи.
        ("ожидание порядка снова копится внутри цикла",
         lambda: one_line("booksmith.doc.html",
                          "        ждём.extend(anchor_of(page.index, b.block_id) for b in page.blocks)",
                          "        pass"),
         [("test_html_order",
           "test_the_book_carries_blocks_in_the_order_it_walked_them")]),

        # И сам сторож в сборщике: проверка сравнивает порядок своими руками,
        # поэтому его снятие она заметит только разбором исходника.
        # `sources`, а НЕ `one_line`: проверка ловит это РАЗБОРОМ ИСХОДНИКА,
        # а `one_line` пересобирает модуль в памяти и до файла не доходит. На
        # этом я ошибся третий раз подряд — механизм у мутации решает не
        # меньше, чем сама порча.
        ("сборщик перестал сверять порядок книги",
         lambda: sources("doc/html.py",
                         "    if вышло != ждём:",
                         "    if False:"),
         [("test_html_order",
           "test_the_book_carries_blocks_in_the_order_it_walked_them")]),

        # Три места, где переезд кухни в `assets/` ломал работающее, и все
        # три нашла перекрёстная проверка, а не разбор кода.
        ("журнал прежней раскладки снова невидим",
         lambda: one_line("booksmith.doc.apply",
                          '        старый = os.path.join(out_dir, "swaps.json")',
                          '        старый = os.path.join(out_dir, "нет.json")'),
         [("test_apply",
           "test_a_journal_from_the_old_layout_is_seen_not_declared_empty")]),

        ("сборщик снова не узнаёт свой каталог по слепку в кухне",
         lambda: one_line("booksmith.doc.html",
                          '    return (os.path.exists(os.path.join(out_dir, ASSETS, "run.json"))',
                          '    return (False'),
         [("test_html_order", "test_the_builder_recognises_its_own_directory")]),

        ("слепок снова ищется только в корне",
         lambda: one_line("booksmith.run.replay",
                          '              os.path.join(outdir, ASSETS, "run.json")):',
                          '              ):'),
         [("test_knobs", "test_replay_finds_the_snapshot_in_both_layouts")]),

        # Источник внутри книги — единственное, что переживает её перенос.
        # Сними приоритет, и `books apply` на скопированной книге пойдёт по
        # абсолютному пути из слепка, которого на новой машине нет.
        ("источник внутри книги перестал быть главнее пути из слепка",
         lambda: one_line("booksmith.doc.apply",
                          '    if os.path.isdir(os.path.join(свой, "pages")):',
                          "    if False:"),
         [("test_apply",
           "test_the_source_inside_the_book_beats_the_recorded_path")]),

        # Книга помнит, из чего собрана: без этого `books apply` без ключей
        # не знал бы, что ставить, и умолчание пришлось бы отменить.
        ("книга перестала помнить свой источник",
         lambda: one_line("booksmith.doc.apply",
                          '    путь = ((снимок.get("аргументы") or {}).get("detect") or "").strip()',
                          '    путь = ""'),
         [("test_apply", "test_the_book_remembers_where_it_was_built_from")]),

        # --- книга обязана нести себя сама ---------------------------------
        # Умолчания ручек — то, что получит читатель. Верни их в режим
        # соседнего файла, и книга, открытая по сетевому пути, покажет сырой
        # LaTeX вместо формул, не сказав ни слова.
        ("умолчание HTML_MATH снова ссылается на соседний файл",
         # `one_line`, а НЕ `sources`: проверка ИСПОЛНЯЕТ сборщик, а тот
         # спрашивает умолчание у импортированного модуля. Подмена файла на
         # диске до него не доходит — на первом прогоне мутация была «НЕ
         # ПОЙМАНА» ровно поэтому.
         lambda: one_line("booksmith.run.knobs",
                          'Knob("HTML_MATH", "inline",',
                          'Knob("HTML_MATH", "local",'),
         [("test_html_order",
           "test_the_book_is_alone_at_the_root_and_carries_itself")]),

        # --- умолчания оболочки против реестра -----------------------------
        # Обещание из `run.sh` («расхождение поймает tests/test_knobs.py»)
        # жило одной строкой прозы: сверки не было ни одной. Мутация ломает
        # умолчание в скрипте, который уезжает на арендованную карту.
        ("умолчание в run.sh разошлось с реестром",
         lambda: sources("models/paddleocr_vl/run.sh",
                         "${PORT:-8118}", "${PORT:-9999}"),
         [("test_knobs", "test_shell_defaults_agree_with_the_registry")]),

        # --- круговой ход сетки не смеет терять содержимое -----------------
        # Без экранирования ячейка `a<b&c` приезжает обратно как `a`, и
        # батарея порчи мерит усечённую строку, отчитываясь о полной.
        ("ячейка таблицы снова не экранируется",
         lambda: one_line("booksmith.text",
                          '            out.append("<td>" + _html.escape('
                          'g.get((r, c), "")) + "</td>")',
                          '            out.append("<td>" + g.get((r, c), "")'
                          ' + "</td>")'),
         [("test_text",
           "test_a_cell_with_angle_brackets_survives_the_round_trip")]),

        # --- прибор мерит ТО ЖЕ правило, которым собирается книга ----------
        # Вторая копия правила «наш» жила в `metrics._by_reading` вместе с
        # докстрокой «тот самый порядок». Ключи совпадали, `metrics` не
        # импортировал `order` вовсе, и связи не было ни одной — а на этом
        # сборщике снят главный вывод проекта (2471 прыжок против 501 и 439).
        ("прибор снова сортирует своей копией правила",
         lambda: sources("metrics.py",
                         '        idx = order.permutation(',
                         '        idx = _naive_reading_order('),
         [("test_order",
           "test_the_ruler_measures_the_same_rule_the_book_is_built_with")]),

        # --- денежный путь: пульс брошенной машины -------------------------
        # Кто завёл пульс, тот и гасит при отказе. Снимешь — и брошенная
        # машина остаётся бессмертной: наш же поток стучит ей `touch
        # /root/.alive`, а дозор мертвеца на ней единственный, кто не зависит
        # ни от нашего ключа, ни от нашего процесса.
        ("пульс не гасится, когда связь оборвалась после него",
         lambda: one_line("booksmith.remote.runner",
                          "            box.stop_heartbeat()",
                          "            pass"),
         [("test_rent_deadlines",
           "test_a_failed_connect_leaves_no_machine_with_a_live_pulse")]),

        # --- две копии разбора `--pages`: дома и на карте ------------------
        # Свести их в одну нельзя — на бокс уезжают четыре файла, пакета там
        # нет. Значит стеречь надо совпадение, и вот чем. До сторожа копии
        # разошлись на четырёх входах из тринадцати, и разбирается строка НА
        # КАРТЕ, где голая трассировка означает пустую аренду.
        ("пробел перестал разделять страницы в копии для карты",
         lambda: sources("models/dots_ocr/entrypoint.py",
                         'str(spec).replace(" ", ",").split(",")',
                         'str(spec).split(",")'),
         [("test_parse_pages", "test_both_copies_of_parse_pages_agree"),
          ("test_parse_pages", "test_a_space_separates_pages_in_both_copies")]),

        ("дефис на карте перестал значить «вся книга»",
         lambda: sources("models/dots_ocr/entrypoint.py",
                         'if not spec or spec == "-":',
                         'if not spec:'),
         [("test_parse_pages",
           "test_the_dash_means_the_whole_book_only_on_the_box")]),

        # Откат к зашитому значению: слепок начинает отвечать «расхождения
        # нет», пока сторож рядом говорит обратное. Без этой мутации правка
        # держалась ни на чём — поле в слепке ЕСТЬ, и `replay --check` его
        # одобряет, потому что сверяет ключи, а не значения.
        ("расхождение порога снова зашито литералом",
         lambda: source_swap("models/yolox_layout.py",
                             '"расхождение порога": self.threshold_drift()',
                             '"расхождение порога": []'),
         [("test_yolox_fingerprint",
           "test_the_fingerprint_asks_the_threshold_guard_instead_of_a_literal"
           )]),

        ("--pages overlay считается с нуля, а detect — с единицы",
         lambda: one_line("booksmith.detect",
                          "return [p - 1 for p in sorted(set(want))]",
                          "return sorted(set(want))"),
         [("test_overlay", "test_pages_are_counted_from_one_like_detect")]),

        ("страница, которой нет у модели, пропускается молча",
         lambda: one_line("booksmith.overlay",
                          'counts["нет у модели"].append(i)',
                          "pass"),
         [("test_overlay", "test_a_page_missing_from_one_markup_is_named")]),

        ("итог называет страницы книги, а не нарисованные листы",
         lambda: one_line(
             "booksmith.overlay",
             'log(f"{out}: листов нарисовано {sheets} из {n} в книге, '
             'рамок {drawn}")',
             'log(f"{out}: листов нарисовано {n} из {n} в книге, '
             'рамок {drawn}")'),
         # Только эта: `test_pages_are_counted…` переписана на счёт рамок
         # по `get_drawings()` в выходном PDF и от итоговой строки больше не
         # зависит — она смотрит на то, что НАРИСОВАНО, а не на то, что
         # сказано. Это и был смысл переписывания.
         [("test_overlay",
           "test_the_summary_counts_sheets_not_pages_of_the_book")]),

        ("одна разметка отчитывается тремя нулями",
         lambda: one_line(
             "booksmith.overlay",
             'log(f"  одна разметка «{sets[0][1]}»: сличать эти {drawn} рамок НЕ "',
             'log(f"  совпало 0, НЕ НАШЛА 0, ЛИШНИХ 0 «{sets[0][1]}» {drawn} "'),
         [("test_overlay",
           "test_one_markup_says_there_is_nothing_to_compare")]),

        ("несверенная разметка не называется",
         lambda: one_line("booksmith.overlay", "unchecked.append(tag)", "pass"),
         [("test_overlay", "test_what_was_not_checked_by_sha256_is_named")]),

        # --- золотой стенд: сборщик, у которого не было ни одной проверки --
        ("порядок классов принимается на веру",
         lambda: attrs(annopage, _yaml_names=lambda root: None),
         [("test_annopage",
           "test_class_order_is_checked_against_the_second_source")]),

        # Построчная: истина снова пишется прямо на место, а не в сторону.
        # `attrs` сюда не дотягивается — правка внутри длинной `build`.
        ("истина пишется на место, до сторожей",
         lambda: one_line("booksmith.annopage",
                          'work = tdir + ".новая"',
                          'work = tdir'),
         [("test_annopage",
           "test_a_failed_build_does_not_destroy_good_truth")]),

        # Построчная: масштаб листа снова зашит числом вместо ручки.
        ("размер листа стенда зашит, а не взят из PAGE_DPI",
         lambda: one_line("booksmith.annopage",
                          "page = doc.new_page(width=w * scale, "
                          "height=h * scale)",
                          "page = doc.new_page(width=w * 0.5, height=h * 0.5)"),
         [("test_annopage", "test_the_sheet_follows_the_declared_knob")]),

        # --- разрез разворотов: вето было сломано В ОБЕ СТОРОНЫ ------------
        ("вето смотрит всю пробу, вместе с кромкой скана",
         lambda: attrs(djvu, gutter_rule=veto_looks_at_the_whole_probe),
         [("test_djvu", "test_scan_edge_at_the_top_does_not_veto"),
          ("test_djvu", "test_scan_edge_at_the_bottom_does_not_veto"),
          ("test_djvu", "test_veto_does_not_depend_on_the_height_of_the_scan"),
          ("test_djvu", "test_the_probe_selfcheck_agrees_with_the_veto")]),

        ("приграничная полоса съедает тело листа",
         lambda: attrs(djvu, RULE_EDGE=0.06),
         [("test_djvu", "test_rule_near_the_edge_of_the_body_still_vetoes")]),

        ("вето мерит долю сквозных строк, а не длину линейки",
         lambda: attrs(djvu, gutter_rule=veto_measures_the_share_of_rows),
         [("test_djvu", "test_hairline_rule_of_a_single_probe_row_vetoes"),
          ("test_djvu", "test_rule_across_the_gutter_vetoes"),
          ("test_djvu", "test_veto_does_not_depend_on_the_height_of_the_scan")]),

        # Ручка пробы. Единственная мутация файла, которая бьёт не по
        # устройству вето, а по его РАЗРЕШЕНИЮ: остальные проверки djvu
        # нарочно безразличны к `PROBE_DPI` (лист задан в пикселях пробы), и
        # без этой мутации ручку можно было бы вернуть на 36 при полностью
        # зелёной батарее — погубив три настоящие таблицы через корешок.
        ("проба огрублена до прежних 36 dpi",
         lambda: attrs(djvu, PROBE_DPI=36),
         [("test_djvu",
           "test_a_thin_rule_across_the_gutter_needs_the_probe_we_declared")]),

        ("линейкой считается любая чернота через корешок",
         lambda: attrs(djvu, RULE_RUN=0.05),
         [("test_djvu", "test_binding_shadow_in_the_body_does_not_veto")]),

        ("порог длины задран выше любой линейки",
         lambda: attrs(djvu, RULE_RUN=0.9),
         [("test_djvu", "test_rule_across_the_gutter_vetoes"),
          ("test_djvu", "test_hairline_rule_of_a_single_probe_row_vetoes"),
          ("test_djvu", "test_rule_near_the_edge_of_the_body_still_vetoes")]),

        ("живая ручка помечена долгом",
         lambda: attrs(knobs.KNOB["DOCLING_PIPELINE"], debt=True),
         [("test_knobs", "test_docling_pipeline_is_registered")]),

        # ---- второй уровень: транспорт --------------------------------
        ("пустой ответ переспрашивается",
         lambda: attrs(vhttp.Http, send=send_asks_again_on_silence),
         [("test_read", "test_answer_200_is_never_repeated")]),

        ("повторы поняты как попытки — промах на единицу",
         lambda: attrs(vhttp.Http, __init__=http_takes_retries_for_attempts),
         [("test_read", "test_delivery_refusal_is_repeated")]),

        ("сторож пустой вырезки снят",
         lambda: attrs(vhttp, _data_uri=data_uri_without_the_empty_guard),
         [("test_read", "test_empty_crop_is_loud")]),

        ("вырезка ужимается перед отправкой",
         lambda: attrs(vhttp, _data_uri=data_uri_shrinks_the_crop),
         [("test_read", "test_the_very_crop_reaches_the_model")]),

        # ---- второй уровень: запись ответа ----------------------------
        ("запись ответа не несёт, чем кончилось порождение",
         lambda: attrs(Said, to_json=said_json_without_finish),
         [("test_read", "test_five_zeroes_are_counted_apart")]),

        ("байты модели подчищены пробелами",
         lambda: attrs(Said, to_json=said_json_strips_the_text),
         [("test_read", "test_model_bytes_are_untouched")]),

        ("догадка о виде дописана в текст блока",
         lambda: attrs(Said, to_json=said_json_writes_the_guess_into_the_text),
         [("test_read", "test_observed_lives_beside_not_inside")]),

        # ---- второй уровень: проход книги -----------------------------
        ("рисунки тоже спрашиваем",
         lambda: attrs(PaddleOcrVl, routes=routes_read_the_pictures_too),
         [("test_read", "test_read_fills_content_in_the_same_page_schema")]),

        ("в отпечаток чтеца дописан адрес",
         lambda: attrs(PaddleOcrVl,
                       fingerprint=reader_fingerprint_with_the_address),
         [("test_read", "test_resume_does_not_ask_twice")]),

        ("отпечаток чтеца больше не несёт промтов",
         lambda: attrs(PaddleOcrVl,
                       fingerprint=reader_fingerprint_without_prompts),
         [("test_read", "test_snapshot_carries_prompts_and_our_parser")]),

        ("слепок детекции пересчитывает sha256 книги под текущий файл",
         lambda: attrs(vrun, _detect_facts=detect_facts_refresh_the_hash),
         [("test_read", "test_swapped_pdf_stops_the_run")]),

        ("ноль страниц к чтению — просто пустой итог",
         lambda: attrs(vrun, read_book=read_book_shrugs_at_zero_pages),
         [("test_read", "test_empty_run_is_not_a_success")]),

        # ---- второй уровень: маршруты и виды --------------------------
        ("в словаре детектора класс, которому не завели маршрут",
         lambda: attrs(policy, POLICIES=policies_with_a_new_class()),
         [("test_read", "test_every_label_of_every_dictionary_has_a_route")]),

        ("книга разучилась принимать latex",
         lambda: attrs(ap, KINDS=("html", "otsl", "text")),
         [("test_read", "test_declared_kinds_agree_with_the_book")]),

        # ---- второй уровень: разбор OTSL ------------------------------
        ("пустой ответ нюхается как текст",
         lambda: attrs(vrun, _sniff=sniff_calls_emptiness_text),
         [("test_read", "test_sniffed_kind_never_overrides_the_declared_one")]),

        ("рваность OTSL не считается (по-вендорски)",
         lambda: attrs(otsl, parse=parse_pads_like_the_vendor),
         [("test_read", "test_torn_otsl_is_counted_not_repaired")]),

        ("продолжение соседа заведено клеткой с собственным текстом",
         lambda: attrs(otsl, CONTENT=otsl.CONTENT + otsl.SPAN),
         [("test_read", "test_otsl_span_occupies_all_its_addresses")]),

        ("не-OTSL возвращается пустой сеткой вместо None",
         lambda: attrs(otsl, grid=grid_of_prose_is_an_empty_table),
         [("test_read", "test_not_otsl_is_none_not_empty")]),

        # ---- книга: замена, журнал, якорь -----------------------------
        ("конец блока ищется по последней закрывающей метке",
         lambda: attrs(swap, span=span_ends_at_the_last_closing_mark),
         [("test_apply", "test_neighbour_is_untouched")]),

        ("status читает журнал и не открывает книгу",
         lambda: attrs(ap, status=status_reads_only_the_journal),
         [("test_apply", "test_status_tells_three_zeroes_apart")]),

        ("якорь сквозной, без номера страницы",
         lambda: attrs(dhtml, anchor_of=anchor_without_the_page),
         [("test_html_order", "test_anchor_is_page_scoped")]),

        # ---- прибор чтения: `books text` ------------------------------
        ("блок без ответа получает CER 0",
         lambda: attrs(booktext, measure_pages=measure_scores_silence_as_zero),
         [("test_text", "test_silence_is_not_reported_as_perfect_reading")]),

        ("артефакт записан разрядом «текст»",
         lambda: attrs(booktext, measure_pages=measure_calls_artefacts_text),
         [("test_text",
           "test_perfect_reading_counts_only_text_in_the_text_line")]),

        ("в формуле считаются слова: запись артефакта несёт WER",
         lambda: attrs(booktext,
                       measure_pages=measure_counts_words_in_a_formula),
         [("test_text", "test_one_wrong_letter_in_a_formula_does_not_crash")]),

        ("молчание на артефакте засчитано ответом",
         lambda: attrs(booktext,
                       measure_pages=measure_counts_silence_as_an_answer),
         [("test_text", "test_silent_formulas_are_not_a_measured_one")]),

        ("знаковая истина артефакта снова не читается",
         lambda: attrs(booktext, _truth_text=truth_text_reads_only_tables),
         [("test_text", "test_artefact_with_truth_is_not_a_bait")]),

        ("нет истины — пустая строка",
         lambda: attrs(booktext, _truth_text=truth_text_empty_instead_of_none),
         [("test_text", "test_artefact_without_truth_stays_a_bait")]),

        ("счётчик выдумки на пустой истине снят",
         lambda: attrs(booktext,
                       measure_pages=measure_forgets_invention_on_empty_truth),
         [("test_text", "test_invention_on_declared_emptiness_is_counted")]),

        ("две истины на одном блоке выбираются молча",
         lambda: attrs(booktext, _truth_both=truth_both_chooses_silently),
         [("test_text", "test_two_truths_on_one_artefact_are_loud")]),

        # ---- книга: журнал и комментарии ------------------------------
        ("сторож незакрытого комментария снят",
         lambda: attrs(ap, _check_comments=comments_guard_is_off),
         [("test_apply", "test_unclosed_comment_is_caught_by_its_own_guard")]),

        ("сторож комментариев запрещает их все",
         lambda: attrs(ap, _check_comments=comments_are_refused_wholesale),
         [("test_apply", "test_a_closed_comment_is_not_refused")]),

        ("нечитаемый журнал считается пустым",
         lambda: attrs(ap, load_journal=journal_unreadable_is_an_empty_one),
         [("test_apply", "test_a_broken_journal_is_not_an_empty_journal")]),

        ("журнал пишется прямо на своё место",
         lambda: attrs(ap, save_journal=journal_written_in_place),
         [("test_apply", "test_journal_is_written_atomically")]),

        # ---- книга: вырезка -------------------------------------------
        ("«срезано листом» значит «не осталось ничего»",
         lambda: attrs(crop, _clipped=clipped_only_when_nothing_is_left),
         [("test_html_order",
           "test_clipping_is_measured_with_a_tolerance_not_exactly")]),

        ("вырожденная рамка получает чужой диагноз",
         lambda: attrs(crop, cut=cut_without_the_named_troubles),
         [("test_html_order",
           "test_degenerate_and_inverted_boxes_are_named_by_their_own_trouble")]),

        ("отрицательное поле зажато в ноль",
         lambda: attrs(crop, params=params_clamps_the_margin),
         [("test_html_order", "test_negative_margin_is_refused_out_loud")]),

        ("резкость вырезки берётся из окружения, а не у скана",
         lambda: attrs(crop, params=params_takes_the_dpi_from_the_environment),
         [("test_html_order",
           "test_crop_dpi_never_comes_from_the_environment_silently")]),

        # Три порчи на одно правило, и все три — то, что человек и вправду
        # напишет: «возьмём побольше, модель разберётся», «ужмём и мелкое
        # тоже», «границы модели — мелочь, обойдёмся».
        ("резкость вырезки тянется ВВЕРХ выше решётки скана",
         lambda: attrs(vrun, crop_dpi_for=crop_dpi_stretches_up),
         [("test_html_order",
           "test_crop_dpi_takes_the_ink_that_exists_and_invents_none")]),

        ("зажим считается по полной рамке, а режется пересечение",
         lambda: attrs(vrun, crop_dpi_for=crop_dpi_by_the_whole_box),
         [("test_html_order", "test_crop_dpi_counts_what_will_actually_be_cut")]),

        ("окно модели не спрашивается — режем как придётся",
         lambda: attrs(vrun, crop_dpi_for=crop_dpi_ignores_the_window),
         [("test_html_order",
           "test_crop_dpi_takes_the_ink_that_exists_and_invents_none")]),

        ("вложенность сравнивает голый ранг",
         lambda: attrs(dhtml, _nesting=nesting_compares_raw_order),
         [("test_html_order",
           "test_nesting_survives_blocks_without_a_model_rank")]),

        ("отказов листа три, а пометки две",
         lambda: attrs(dhtml, _sheet_trouble=sheet_trouble_with_two_marks),
         [("test_html_order",
           "test_three_kinds_of_bad_sheet_get_three_different_marks")]),

        ("doc/feed завёл свою копию правила якоря",
         lambda: attrs(feed, anchor_of=anchor_of_a_private_copy),
         [("test_html_order", "test_the_anchor_rule_has_exactly_one_home")]),
    ]
    return [(t + ("",))[:4] if len(t) == 3 else t for t in m]


# --- прогон батареи --------------------------------------------------------

def fresh(name):
    """Свежий импорт проверки: её таблицы строятся из кода при импорте."""
    if name in sys.modules:
        return importlib.reload(sys.modules[name])
    return importlib.import_module(name)


def reddens(mod_name, test_name):
    """Покраснела ли названная проверка. Пропуск красным НЕ считается."""
    mod = fresh(mod_name)
    fn = getattr(mod, test_name, None)
    if fn is None:
        return False, f"проверки {mod_name}::{test_name} больше нет"
    try:
        fn()
    except support.Skip as e:
        return False, f"пропущена ({e})"
    except (Exception, SystemExit) as e:
        return True, type(e).__name__
    return False, "прошла как ни в чём не бывало"


def all_tests():
    out = set()
    for fn in sorted(os.listdir(HERE)):
        if fn.startswith("test_") and fn.endswith(".py"):
            mod = fresh(fn[:-3])
            for n in vars(mod):
                if n.startswith("test_") and callable(getattr(mod, n)):
                    out.add((fn[:-3], n))
    return out


def main():
    caught = missed = 0
    covered = set()
    skipped = []
    for name, broken, targets, needs in mutations():
        if needs and not NEEDS[needs]():
            skipped.append(f"{name} — {needs}")
            continue
        bad = []
        try:
            with broken():
                for mod_name, test_name in targets:
                    red, why = reddens(mod_name, test_name)
                    if not red:
                        bad.append(f"{mod_name}::{test_name} {why}")
        finally:
            for mod_name, _ in targets:
                fresh(mod_name)          # вернуть проверку к неиспорченному коду
        covered |= set(targets)
        if bad:
            missed += 1
            print(f"  НЕ ПОЙМАНА  {name}: " + "; ".join(bad))
        else:
            caught += 1
            print(f"  поймана     {name} ({len(targets)} проверки)")
    total = len(mutations())
    uncovered = sorted(all_tests() - covered)
    print(f"\nмутаций {total}: поймано {caught}, НЕ поймано {missed}, "
          f"пропущено {len(skipped)}")
    for s in skipped:
        print(f"  пропущена мутация: {s}")
    print(f"проверок под мутацией {len(covered)} из {len(all_tests())}; "
          f"без мутации {len(uncovered)}"
          + (": " + ", ".join(f"{m}::{t}" for m, t in uncovered)
             if uncovered else ""))
    return 1 if missed else 0


if __name__ == "__main__":
    sys.path.insert(0, os.path.join(os.path.dirname(HERE), "src"))
    sys.exit(main())
