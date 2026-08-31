"""Замена блока в готовой книге: второй уровень на месте, и откат.

Ради этого затевалась вся двухуровневая схема: «замену можно проверить,
откатить и переделать другой моделью, не трогая книгу». `swap.py` держит
обещание на уровне строк — здесь оно доводится до файлов.

ПОЧЕМУ ОТДЕЛЬНЫЙ ФАЙЛ, А НЕ ФУНКЦИИ В `swap.py`. Тот объявляет себя
единственным слоем конвейера, который проверяется целиком, не потратив ни
секунды счёта, — и это правда ровно до первого `open()`. Файлы, журнал и
время живут здесь; там остаются чистые строки.

ЖУРНАЛ ОБЯЗАТЕЛЕН, И ВОТ ПОЧЕМУ. Замена без отката — это не замена, а правка
книги: второй уровень ошибётся, и вернуть будет нечего. Журнал держит СТОПКУ
на каждый якорь, а не последнее значение: две замены подряд (VLM ответила,
ответ не понравился, переделали другой моделью) откатываются по одной, в
обратном порядке. Плоское поле «что было» потеряло бы среднее состояние
молча.

ЧЕГО ЗДЕСЬ НЕТ НАРОЧНО: ни одного обращения к модели. Этот слой умеет только
поставить готовый кусок разметки на место картинки. Кто его породил — дело
адаптера, и он подключается позже; до тех пор замену можно проверить руками,
не потратив ни цента.
"""
import hashlib
import json
import os
import time

from . import swap

JOURNAL = "swaps.json"
# Виды содержимого, которые второй уровень вправе вернуть. Список ОБЪЯВЛЕН, а
# не «любая строка»: `kind` уезжает в журнал и в книгу атрибутом, и опечатка в
# нём молча превратилась бы в новый вид, о котором никто не договаривался.
# Имена те же, что в контракте блока (`models/base.py`).
KINDS = ("html", "otsl", "latex", "text")


class SwapError(RuntimeError):
    """С заменой что-то не так — и сказано это вслух, а не молча."""


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _same(now: str, promised: str) -> bool:
    """Совпадает ли то, что лежит на месте блока, с тем, что клала замена.

    Отдельной функцией, а не строкой в `undo`, ровно ради батареи порчи: без
    шва эту проверку нечем сломать, а проверка, которую нельзя сломать, не
    доказана. Правило проекта то же, что у метрик: сперва убедись, что число
    умеет упасть.
    """
    return _sha256(now) == promised


def book_path(out_dir: str) -> str:
    p = os.path.join(out_dir, "book.html")
    if not os.path.exists(p):
        raise SwapError(f"нет {p}: сначала books html")
    return p


def load_journal(out_dir: str) -> dict:
    p = os.path.join(out_dir, JOURNAL)
    if not os.path.exists(p):
        return {"книга": "book.html", "замены": {}}
    with open(p, encoding="utf-8") as f:
        j = json.load(f)
    j.setdefault("замены", {})
    return j


def save_journal(out_dir: str, j: dict) -> str:
    p = os.path.join(out_dir, JOURNAL)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(j, f, ensure_ascii=False, indent=1)
    return p


def _check_fragment(fragment: str, anchor: str) -> None:
    """Кусок, который ставим, не должен нести чужих меток.

    Метка внутри вставляемого куска — это призрачный якорь: `swap.anchors`
    насчитает лишний, `span` следующей замены увидит «открывающих 2» и
    откажется работать, а беда вылезет не там, где сделана. Проверка стоит
    одного прохода по строке и ловит её на месте.
    """
    bad = swap._marks_in(fragment)
    if bad:
        raise SwapError(
            f"вставляемый кусок несёт метки блоков {bad}: они станут "
            f"призрачными якорями, и следующая замена откажется работать. "
            f"Второй уровень возвращает РАЗМЕТКУ БЛОКА, а не куски книги.")
    if not fragment.strip():
        raise SwapError(
            f"вставляемый кусок пуст. Пустая замена стирает блок {anchor} из "
            f"книги, и по виду это неотличимо от «модель промолчала». Если "
            f"блок и должен исчезнуть, скажи это явно другим способом.")


def _wrap_fragment(anchor: str, fragment: str, kind: str, source: str) -> str:
    """Обернуть ответ второго уровня НАШЕЙ обёрткой, не тронув его байтов.

    Метим обёртку, а не содержимое: правило проекта — распознанное
    неприкосновенно. Прежде пометки дописывались прямо в разметку, и это
    стоило девяти пропусков из тридцати трёх.
    """
    import html as _h
    return (f'<div id="{anchor}" data-роль="артефакт" data-уровень="2" '
            f'data-вид="{_h.escape(kind)}" '
            f'data-чем="{_h.escape(source)}">' + fragment + "</div>")


def put(out_dir: str, anchor: str, fragment: str, kind: str = "html",
        source: str = "", log=print) -> dict:
    """Поставить разметку на место блока. Возвращает величины, а не «готово»."""
    if kind not in KINDS:
        raise SwapError(f"вид {kind!r} не объявлен: знаю только {KINDS}")
    _check_fragment(fragment, anchor)

    path = book_path(out_dir)
    with open(path, encoding="utf-8") as f:
        html = f.read()

    before = swap.anchors(html)
    if anchor not in before:
        raise SwapError(
            f"якоря {anchor} в книге нет. Есть {len(before)} других; "
            f"имена постраничные, вида p0042-b17 — посмотри blocks.json.")

    body = _wrap_fragment(anchor, fragment, kind, source or "руками")
    new_html, taken = swap.swap(html, anchor, body)

    # ГЛАВНАЯ ПРОВЕРКА, и она про соседей, а не про наш блок. `span` стережёт
    # пересечение меток на ЧТЕНИИ; здесь сверяется результат: набор якорей
    # обязан остаться тем же самым. Разойдётся — значит замена съела чужую
    # границу, и книга наполовину переразмечена; лучше не записать вовсе.
    after = swap.anchors(new_html)
    if after != before:
        lost = sorted(set(before) - set(after))
        got = sorted(set(after) - set(before))
        raise SwapError(
            f"замена {anchor} изменила набор якорей книги: пропало {lost}, "
            f"появилось {got}. Книга не записана.")

    j = load_journal(out_dir)
    j["замены"].setdefault(anchor, []).append({
        "когда": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "чем": source or "руками",
        "вид": kind,
        "sha256 поставленного": _sha256(body),
        "снято": taken,
        "sha256 снятого": _sha256(taken),
    })
    with open(path, "w", encoding="utf-8") as f:
        f.write(new_html)
    save_journal(out_dir, j)

    log(f"{anchor}: поставлено {len(body)} знаков ({kind}, {source or 'руками'}), "
        f"снято {len(taken)}; якорей в книге {len(after)}, стопка отката "
        f"{len(j['замены'][anchor])}")
    return {"якорь": anchor, "поставлено": len(body), "снято": len(taken),
            "якорей": len(after), "глубина отката": len(j["замены"][anchor])}


def undo(out_dir: str, anchor: str, log=print) -> dict:
    """Вернуть то, что стояло до последней замены."""
    path = book_path(out_dir)
    j = load_journal(out_dir)
    stack = j["замены"].get(anchor) or []
    if not stack:
        raise SwapError(
            f"откатывать нечего: {anchor} ни разу не заменяли. Это НЕ то же "
            f"самое, что «откат не удался» — журнал про этот якорь молчит.")

    with open(path, encoding="utf-8") as f:
        html = f.read()
    rec = stack[-1]

    # Сверяем, ЧТО СЕЙЧАС стоит на месте блока, с тем, что мы туда клали.
    # Разошлось — книгу правили мимо журнала, и слепой откат затёр бы чужую
    # работу. Прежде такой сверки не было бы вовсе, а «откат» звучит
    # безопасно.
    now = swap.get(html, anchor)
    if not _same(now, rec["sha256 поставленного"]):
        raise SwapError(
            f"на месте {anchor} лежит не то, что клала последняя замена "
            f"(sha256 {_sha256(now)[:12]} против {rec['sha256 поставленного'][:12]}). "
            f"Книгу правили мимо журнала; откат затёр бы эту правку. "
            f"Разберись руками.")

    new_html = swap.restore(html, anchor, rec["снято"])
    stack.pop()
    if not stack:
        j["замены"].pop(anchor, None)
    with open(path, "w", encoding="utf-8") as f:
        f.write(new_html)
    save_journal(out_dir, j)

    log(f"{anchor}: откачено к {rec['sha256 снятого'][:12]} "
        f"({len(rec['снято'])} знаков, замена от {rec['когда']}); "
        f"осталось в стопке {len(stack)}")
    return {"якорь": anchor, "возвращено": len(rec["снято"]),
            "глубина отката": len(stack)}


def status(out_dir: str, log=print) -> dict:
    """Что в книге заменено, а что ещё картинка. Числа, а не перечисление."""
    path = book_path(out_dir)
    with open(path, encoding="utf-8") as f:
        html = f.read()
    j = load_journal(out_dir)
    a = swap.anchors(html)
    swapped = {k: len(v) for k, v in j["замены"].items()}
    # Три разных нуля, и они разные строки: якорей нет вовсе (книга пуста),
    # замен нет (второй уровень не начинали) и замены есть, но все откачены
    # (журнал пуст по-другому — записи удалены при опустошении стопки).
    log(f"якорей в книге {len(a)}; заменено блоков {len(swapped)}, "
        f"всего замен {sum(swapped.values())}")
    if not a:
        log("якорей нет вовсе — это не «всё заменено», а пустая книга")
    elif not swapped:
        log("замен нет: второй уровень по этой книге ещё не ходил")
    return {"якорей": len(a), "заменено блоков": len(swapped),
            "всего замен": sum(swapped.values()), "по якорям": swapped}
