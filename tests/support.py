"""Общее для проверок: где лежат исходники, разбор их деревом, пропуск вслух.

Проверки в этом каталоге закрепляют СГОВОРЫ МЕЖДУ ФАЙЛАМИ — места, где два
файла договорились, а договор не записан нигде. Такое не ловится ни типами, ни
чтением одного файла: слово «наш» в `models/*.py` решает, напечатает ли
`metrics.py` процент или скажет НЕ СВЕРЯЕТСЯ, и оба файла по отдельности
выглядят исправными.

Поэтому здесь есть разбор ИСХОДНИКА деревом. Он нужен там, где значение
договора зашито в литерал внутри метода и достать его исполнением нельзя, не
подняв модель на 214 МБ. Разбор видит ровно то, что увидит человек, а не то,
что вернёт заглушка.

ПРОПУСК ОБЪЯВЛЯЕТСЯ ВСЛУХ И С ПРИЧИНОЙ. Ноль от проверки и ноль от
непонимания — разные нули: бегун печатает пропуски отдельным числом, а не
приписывает их к прошедшим.
"""
import ast
import os
import sys

# Каталог исходников. Отсюда, а не от cwd: иначе проверка из другого каталога
# молча не нашла бы ни одного адаптера и была бы зелёной ни на чём.
SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "src", "booksmith")

# Ключ, по которому адаптер называет метрике ЧЕЙ порядок он отдал.
ORDER_KEY = "порядок чтения"


class Skip(Exception):
    """Проверку выполнить нечем. Причина обязательна."""


# Кто гоняет проверки. Ставит это САМ бегун (`tests/run.py` при запуске), а
# не мы отсюда: спрашивать «импортируется ли pytest» вместо «гоняет ли он»
# уже стоило прогона. Замер (подставной модуль `pytest` в `sys.modules`, тот
# же договор, что у настоящего — `Skipped(BaseException)` и `skip()`):
# до правки первый же пропуск под нашим бегуном уходил мимо ловушек
# `run_case` и убивал прогон целиком — строка «проверок 111: прошло …» не
# печаталась ВОВСЕ, то есть 110 прошедших проверок пропадали вместе с одним
# пропуском. Сейчас pytest в `.venv` нет, и беда спит.
OWN_RUNNER = False


def skip(reason: str):
    """Пропуск с причиной. Под pytest — его же пропуск, чтобы бегун был любой.

    Выбор по ТОМУ, КТО ГОНЯЕТ, а не по тому, что установлено. Проверяются оба
    признака сразу: наш бегун объявляет себя `OWN_RUNNER`, а pytest, если он
    и правда работает, к этому мигу уже лежит в `sys.modules` — сам он себя
    импортирует раньше любой проверки. Импорта pytest здесь больше нет: он-то
    и превращал «pytest установлен» в «pytest гоняет».
    """
    pt = sys.modules.get("pytest")
    if pt is not None and not OWN_RUNNER:
        pt.skip(reason)
    raise Skip(reason)


def foreign_skip(e) -> bool:
    """Пропуск, объявленный ЧУЖИМ бегуном: `pytest.skip()`.

    Живёт РЯДОМ С `Skip`, а не в бегуне, потому что это одна и та же мысль:
    что считать пропуском. Держать её в двух домах значило бы завести две
    копии договора — те самые, что расходятся молча (сторож порядка чтения
    уже разошёлся так регистром).

    Отдельная ветка нужна вот почему: `Skipped` у pytest наследует
    BaseException, а не Exception, и мимо обычных ловушек бегуна он проходит
    насквозь, УБИВАЯ прогон. Замер подставным модулем с тем же договором: под
    нашим бегуном один пропуск — и строка «проверок 111: прошло 110, …» не
    печаталась вовсе, код возврата 1 от трассы.

    Тип берётся У САМОГО pytest, а не по имени класса: имя `Skipped` может
    оказаться и у чужого исключения, и тогда провал уехал бы в пропуски.
    Спрашиваются оба места, где pytest его держит: `pytest.skip.Exception`
    (ставит декоратор `_with_exception`) и `pytest.Skipped`.
    """
    pt = sys.modules.get("pytest")
    if pt is None:
        return False
    for cls in (getattr(getattr(pt, "skip", None), "Exception", None),
                getattr(pt, "Skipped", None)):
        if isinstance(cls, type) and isinstance(e, cls):
            return True
    return False


class Unresolved(RuntimeError):
    """Значение договора в исходнике есть, а вычислить его разбор не смог.

    Молчать тут нельзя: невычисленное значение — это НЕ «значений нет», и
    выдать его за пустой набор значило бы отчитаться нулём от непонимания.
    """


def src_path(rel: str) -> str:
    p = os.path.join(SRC, rel)
    if not os.path.isfile(p):
        raise AssertionError(f"нет исходника {rel} (искали в {SRC})")
    return p


def tree(rel: str) -> ast.Module:
    with open(src_path(rel), encoding="utf-8") as f:
        return ast.parse(f.read(), filename=rel)


def _dotted(node) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return _dotted(node.value) + "." + node.attr
    raise Unresolved(f"не имя и не поле: {ast.dump(node)[:80]}")


def _lookup(module, dotted: str):
    obj = module
    for part in dotted.split("."):
        obj = getattr(obj, part, None)
        if obj is None:
            raise Unresolved(f"{dotted}: в модуле {module.__name__} такого нет")
    return obj


def _values(node, module) -> set:
    """Во что может развернуться правая часть `"порядок чтения": …`."""
    if isinstance(node, ast.Constant):
        return {node.value}
    if isinstance(node, ast.IfExp):
        return _values(node.body, module) | _values(node.orelse, module)
    if isinstance(node, ast.Subscript):
        obj = _lookup(module, _dotted(node.value))
        if isinstance(obj, dict):
            return set(obj.values())
        raise Unresolved(f"{_dotted(node.value)} — не словарь, а {type(obj)}")
    # СКЛЕЙКА. `order.WORDS[which] + ": модель ранга не даёт"`: правило берётся
    # из общего словаря, а хвост дописывает адаптер. Разворачиваем в
    # произведение — каждое левое значение с каждым правым, — иначе сторож
    # видел бы только половину строки и пропустил бы подмену второй.
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = _values(node.left, module), _values(node.right, module)
        return {a + b for a in left for b in right}
    raise Unresolved(
        f"значение «{ORDER_KEY}» вычислить не удалось: {ast.dump(node)[:120]}. "
        f"Это НЕ «значений нет» — допиши разбор в support._values.")


def _walk_but_fingerprint(node):
    """Всё дерево, кроме тел `fingerprint()`.

    В отпечатке то же поле стоит с другими словами (`НАШ` с заглавной,
    `None`), и это законно: отпечаток читает человек и слепок, а сторож
    метрики читает meta СТРАНИЦЫ. Смешать их значило бы завести проверку на
    договор, которого нет.
    """
    if isinstance(node, ast.FunctionDef) and node.name == "fingerprint":
        return
    yield node
    for child in ast.iter_child_nodes(node):
        yield from _walk_but_fingerprint(child)


def page_order_values(rel: str, module) -> set:
    """Все значения `meta["порядок чтения"]`, которые адаптер кладёт В СТРАНИЦУ.

    Собирается из исходника, а не из прогона: чтобы получить их прогоном, надо
    поднять три модели и посчитать по странице каждой, а договор надо
    проверять за миллисекунды и на каждом изменении.
    """
    out = set()
    for node in _walk_but_fingerprint(tree(rel)):
        if not isinstance(node, ast.Dict):
            continue
        for k, v in zip(node.keys, node.values):
            if isinstance(k, ast.Constant) and k.value == ORDER_KEY:
                out |= _values(v, module)
    return out


def meta_keys(rel: str, cls: str, method: str = "read") -> list:
    """Порядок ключей в `meta=` у вызова `Page(...)` внутри метода.

    Порядок здесь не косметика: при выключенной ручке страница обязана
    выходить ПОБАЙТОВО той же, что до появления конвейера, а json пишет ключи
    в порядке словаря. `**имя` возвращается строкой `**имя`.
    """
    for node in ast.walk(tree(rel)):
        if not (isinstance(node, ast.ClassDef) and node.name == cls):
            continue
        for fn in node.body:
            if not (isinstance(fn, ast.FunctionDef) and fn.name == method):
                continue
            for call in ast.walk(fn):
                if not isinstance(call, ast.Call):
                    continue
                if getattr(call.func, "id", None) != "Page":
                    continue
                for kw in call.keywords:
                    if kw.arg != "meta" or not isinstance(kw.value, ast.Dict):
                        continue
                    keys = []
                    for k, v in zip(kw.value.keys, kw.value.values):
                        if k is None:
                            keys.append("**" + _dotted(v))
                        elif isinstance(k, ast.Constant):
                            keys.append(k.value)
                        else:
                            raise Unresolved(f"ключ meta не литерал в {rel}")
                    return keys
    raise AssertionError(f"{rel}: не нашли Page(meta=…) в {cls}.{method}")
