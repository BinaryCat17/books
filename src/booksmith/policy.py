"""Что первый уровень делает с блоком: текст, картинка или служебное.

Это НАША политика, а не свойство модели, и потому она объявлена явно, целиком
и уезжает в слепок. Число «артефактов 40» без неё истолковать нельзя, не
открыв тот же коммит кода.

ПОЛИТИКА ПОЛНА ПО ПОСТРОЕНИЮ, И ЭТО ГЛАВНОЕ В ФАЙЛЕ. Ярлык, которого здесь
нет, роняет прогон. Умолчания нет нарочно: в постобработке paddlex словарь
порогов с одним классом молча ставил остальным 0.5, и «понизить порог таблиц»
меняло поведение всех двадцати пяти. Тот же капкан ждёт и здесь — новая
версия весов с двадцать шестым классом молча вылила бы его в прозу.

ТРИ РАЗРЯДА, А НЕ ДВА.

`артефакт` — вырезается картинкой и вставляется как есть. Разбирать его будет
второй уровень, в изоляции от соседей.

`текст` — остаётся текстом в потоке.

`служебное` — колонтитулы, колонцифры, сноски. Формально текст, но в книгу,
скорее всего, не нужны. Выбросить их СЕЙЧАС значит принять решение без
замера, поэтому они помечаются и остаются: пометка стоит ничего, а
восстановить выброшенное будет нечем. Решение примет стенд.
"""

# ПОЛИТИК НЕСКОЛЬКО — по одной на СЛОВАРЬ ЯРЛЫКОВ. Пока детектор был один,
# политика была одна, и вопрос «а не лучше ли другая модель» нельзя было даже
# померить: чужой ярлык ронял прогон. Теперь словарь каждой модели объявлен
# отдельно и целиком, а `ROLE` — их объединение с проверкой на противоречие:
# один и тот же ярлык не может значить в двух словарях разное.
PP_DOCLAYOUT_V2 = {
    # --- вырезается картинкой ------------------------------------------
    "table": "artifact",
    "chart": "artifact",
    "image": "artifact",
    # Формула блоком — картинка. На HTML она переводится плохо и не всегда,
    # и решать это дело второго уровня, а не наше.
    "display_formula": "artifact",
    "header_image": "artifact",
    "footer_image": "artifact",
    "seal": "artifact",

    # --- остаётся текстом ----------------------------------------------
    "abstract": "text",
    "algorithm": "text",
    "aside_text": "text",
    "content": "text",
    "doc_title": "text",
    "figure_title": "text",
    "paragraph_title": "text",
    "reference": "text",
    "reference_content": "text",
    "text": "text",
    "vertical_text": "text",
    # ОСТОРОЖНО, ПОГРАНИЧНЫЙ СЛУЧАЙ. Строчная формула живёт ВНУТРИ потока, и
    # вырезать её картинкой значит разорвать предложение посередине. Поэтому
    # текст — но с оговоркой: содержимое при этом теряется молча, а все
    # числа контуров остаются идеальными. Первый кандидат на замер.
    "inline_formula": "text",
    "formula_number": "text",

    # --- служебное: помечается, но не выбрасывается ---------------------
    "header": "furniture",
    "footer": "furniture",
    "number": "furniture",
    "footnote": "furniture",
    "vision_footnote": "furniture",
}

# DocLayNet — словарь, на котором обучены YOLO-детекторы макета (yolov10/11
# doclaynet, DocLayout-YOLO). Одиннадцать классов против наших двадцати пяти:
# формула тут одна на все виды, а порядка чтения эти модели не дают вовсе.
# Объявлено ради ЗАМЕРА: сравнить архитектуры на одних страницах нельзя, пока
# чужой ярлык роняет прогон.
DOCLAYNET = {
    "Table": "artifact",
    "Picture": "artifact",
    "Formula": "artifact",
    "Caption": "text",
    "List-item": "text",
    "Section-header": "text",
    "Text": "text",
    "Title": "text",
    "Page-header": "furniture",
    "Page-footer": "furniture",
    "Footnote": "furniture",
}

# Docling heron/egret (IBM): семнадцать классов, RT-DETRv2 на других данных.
# Объявлено ради ПЕРЕКРЁСТНОЙ СВЕРКИ: две независимые модели на одних
# страницах отвечают на вопрос, свойство ли слияние архитектуры или выборки.
# Класса `chart` у неё НЕТ вовсе — графики уходят в `picture`, и это надо
# помнить при сличении: наш `chart` ей нечем выразить.
DOCLING = {
    "table": "artifact",
    "picture": "artifact",
    "formula": "artifact",
    "code": "artifact",
    "caption": "text",
    "list_item": "text",
    "section_header": "text",
    "text": "text",
    "title": "text",
    "document_index": "text",
    "form": "text",
    "key_value_region": "text",
    "checkbox_selected": "text",
    "checkbox_unselected": "text",
    "page_header": "furniture",
    "page_footer": "furniture",
    "footnote": "furniture",
}

# PP-DocLayout_plus-L — предшественник V2 в том же семействе: двадцать классов
# вместо двадцати пяти, ОДИН класс `formula` на выключную и строчную, и НЕТ
# порядка чтения (его добавила указательная сеть V2). Объявлено ради замера
# родословной: что дала прибавка пяти классов и указательной сети.
PP_DOCLAYOUT_PLUS_L = {
    "table": "artifact",
    "chart": "artifact",
    "image": "artifact",
    "formula": "artifact",
    "seal": "artifact",
    "abstract": "text",
    "algorithm": "text",
    "aside_text": "text",
    "content": "text",
    "doc_title": "text",
    "figure_title": "text",
    "paragraph_title": "text",
    "reference": "text",
    "reference_content": "text",
    "text": "text",
    "formula_number": "text",
    "header": "furniture",
    "footer": "furniture",
    "number": "furniture",
    "footnote": "furniture",
}

# Docling egret (D-FINE): те же семнадцать классов, что у heron, но имена
# записаны иначе — с заглавной и через дефис. Отдельная политика, а не свод:
# свод стёр бы разницу словарей, а она у нас единственный способ отличить
# ошибку перевода от ошибки модели.
DOCLING_EGRET = {
    "Table": "artifact",
    "Picture": "artifact",
    "Formula": "artifact",
    "Code": "artifact",
    "Caption": "text",
    "List-item": "text",
    "Section-header": "text",
    "Text": "text",
    "Title": "text",
    "Document Index": "text",
    "Form": "text",
    "Key-Value Region": "text",
    "Checkbox-Selected": "text",
    "Checkbox-Unselected": "text",
    "Page-header": "furniture",
    "Page-footer": "furniture",
    "Footnote": "furniture",
}

POLICIES = {
    "PP-DocLayoutV2": PP_DOCLAYOUT_V2,
    "Docling-egret": DOCLING_EGRET,
    "PP-DocLayout_plus-L": PP_DOCLAYOUT_PLUS_L,
    "DocLayNet": DOCLAYNET,
    "Docling": DOCLING,
}

ROLE: dict[str, str] = {}
for _name, _table in POLICIES.items():
    for _lab, _r in _table.items():
        if ROLE.get(_lab, _r) != _r:
            raise RuntimeError(
                f"ярлык {_lab!r} значит в разных словарях разное: "
                f"{ROLE[_lab]!r} и {_r!r}. Объединение тут молча выбрало бы "
                f"одно из двух, и разряд блока зависел бы от порядка импорта.")
        ROLE[_lab] = _r

ROLES = ("text", "artifact", "furniture")


class UnknownLabel(RuntimeError):
    """Ярлык модели не описан политикой. Роняем, а не догадываемся."""


def check(labels, policy: str = "PP-DocLayoutV2") -> None:
    """Политика обязана покрывать словарь модели ЦЕЛИКОМ.

    Проверяется при каждом прогоне, а не однажды: словарь приезжает из весов,
    и смена весов — самый вероятный способ завести двадцать шестой класс.
    Лишнее в политике тоже беда: `"figure"` вместо `"image"` дало бы
    «артефактов 0» навсегда и молча.

    Сверяется с ОДНИМ названным словарём, а не с объединением: объединение
    покрывает и чужие ярлыки, и проверка перестала бы ловить как раз то, ради
    чего написана.
    """
    if policy not in POLICIES:
        raise UnknownLabel(f"нет политики {policy!r}: есть {sorted(POLICIES)}")
    have, mine = set(labels), set(POLICIES[policy])
    if have - mine:
        raise UnknownLabel(
            f"политика не описывает ярлыки модели: {sorted(have - mine)}. "
            f"Опишите их в policy.ROLE — умолчания здесь нет нарочно.")
    if mine - have:
        raise UnknownLabel(
            f"политика описывает ярлыки, которых нет у модели: "
            f"{sorted(mine - have)}. Опечатка тут не видна ничем, кроме "
            f"вечного нуля в отчёте.")


def for_labels(labels) -> str:
    """Какая политика описывает ИМЕННО этот словарь ярлыков.

    Политика выбирается СЛОВАРЁМ МОДЕЛИ, а не именем, которое мы набрали
    руками: имя весов можно перепутать, а список классов приезжает из самих
    весов. Ни одной подходящей — падаем; двух подходящих не бывает, потому
    что множества классов у наших моделей различны.
    """
    have = set(labels)
    fit = [n for n, t in POLICIES.items() if set(t) == have]
    if len(fit) == 1:
        return fit[0]
    if not fit:
        raise UnknownLabel(
            f"нет политики под словарь из {len(have)} ярлыков: "
            f"{sorted(have)[:6]}… Опишите его в policy.POLICIES — умолчания "
            f"здесь нет нарочно.")
    raise UnknownLabel(f"под этот словарь подходит несколько политик: {fit}")


def role(label: str) -> str:
    try:
        return ROLE[label]
    except KeyError:
        raise UnknownLabel(f"ярлык {label!r} не описан политикой") from None


def artefacts() -> tuple[str, ...]:
    return tuple(sorted(l for l, r in ROLE.items() if r == "artifact"))


def snapshot(policy: str | None = None) -> dict:
    """Политика целиком — в слепок."""
    if policy:
        return {"buckets": list(ROLES), "vocabulary": policy,
                "by_label": dict(sorted(POLICIES[policy].items()))}
    return {"buckets": list(ROLES), "vocabularies": sorted(POLICIES),
            "by_label": dict(sorted(ROLE.items()))}
