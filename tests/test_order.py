"""Порядок сборки книги: одно правило на проект, и оно обязано быть одним.

ЗАЧЕМ ЭТОТ ФАЙЛ. Правило жило в ЧЕТЫРЁХ местах трёх адаптеров, и в двух из
них сортировало НЕ ТЕМ ключом, что объявляло: `docling_heron` клал в `meta`
«наш, сверху вниз и слева направо», а сортировал `(round(y/20), x)` —
корзинами по двадцать пикселей растра. Заметить это можно было только чтением
всех четырёх мест сразу; ни одна из 169 проверок этого не видела.

Замер, которым правило выбрано (шапка `order.py`): одни и те же рамки V2, 600
страниц золотого стенда, три перестановки, один `books score` — наше правило
2471 лишний прыжок, ранг модели 501, правила docling 439; по 16 точкам
развёртки наше хуже обоих УСТОЙЧИВО (пределы 3.02..7.04 против 0.23..1.73 и
0.28..1.57, не пересекаются), а docling против ранга V2 прибор НЕ различает
(пара перевёрнута, разница 0.13 при размахе линейки 4.02).
"""
import ast

import support

from booksmith import order, policy


def test_every_dictionary_has_a_translation():
    """У КАЖДОЙ политики есть перевод ярлыков, и лишних переводов нет.

    Сговор между двумя словарями, и ровно на нём проект уже терял: реестр
    ручек против сборщика задания разошлись на 13 имён из 17. Заведи кто-то
    шестую политику — `ASSEMBLY_ORDER=docling` упал бы на ней при первом же
    платном прогоне, а не здесь за миллисекунду.
    """
    have, want = set(order._LABELS), set(policy.POLICIES)
    assert have == want, (
        f"перевод ярлыков и политики разошлись: нет перевода у "
        f"{sorted(want - have)}, перевод без политики у {sorted(have - want)}")


def test_translations_name_only_labels_the_rules_look_at():
    """Перевод целит в ВОСЕМЬ имён, на которые правила вообще смотрят.

    Девятое имя не сломает прогон вслух — оно просто не сработает, и
    колонтитул уедет в тело страницы молча. Список снят разбором самого
    `reading_order_rb.py`.
    """
    eight = {"caption", "code", "footnote", "page_footer", "page_header",
             "picture", "table", "text"}
    for name, tr in order._LABELS.items():
        bad = set(tr.values()) - eight
        assert not bad, f"{name}: перевод целит в {sorted(bad)}, а правила " \
                        f"смотрят только на {sorted(eight)}"


def test_translations_use_labels_that_exist():
    """Переводится то, что модель ВПРАВДУ отдаёт, а не выдуманное имя.

    Опечатка в ключе — молчаливый ноль: правило не найдёт ярлык, объект
    поедет как текст, и никто не узнает.
    """
    for name, tr in order._LABELS.items():
        bad = set(tr) - set(policy.POLICIES[name])
        assert not bad, (
            f"{name}: перевод знает ярлыки {sorted(bad)}, которых у модели "
            f"нет — такой ключ не сработает НИКОГДА и молча")


def test_ours_needs_neither_labels_nor_docling():
    """Правило `ours` смотрит на одни координаты — ни ярлыков, ни пакета.

    Умеет провалиться: заставьте `cover` спрашивать политику всегда, и
    подставной словарь из одного ярлыка уронит прогон на правиле, которое
    ярлыков и не касается.
    """
    assert order.cover(["никакой такой политики нет"], "ours") is None
    boxes = [(10, 300, 90, 380), (10, 10, 90, 90), (200, 10, 280, 90)]
    perm = order.permutation(["x"] * 3, boxes, 400, 600, 0, ["x"], "ours")
    assert perm == [1, 2, 0], f"сверху вниз и слева направо дало {perm}"


def test_docling_returns_a_permutation_and_touches_no_box():
    """Правила docling ПЕРЕСТАВЛЯЮТ, а не правят: набор рамок тот же.

    Проверка существа, а не выхода: правила разводят колонтитулы и тело по
    трём спискам и сшивают обратно; потеряйся там элемент — рамка исчезла бы
    из книги молча, а число рамок «после» выглядело бы просто чуть меньшим.
    """
    try:
        import docling  # noqa: F401
    except ImportError:
        support.skip("нет пакета docling: правило `docling` не проверить")
    labels = ["text", "table", "header", "text", "image"]
    boxes = [(50, 400, 300, 500), (50, 200, 300, 380), (50, 20, 300, 60),
             (330, 400, 580, 500), (330, 100, 580, 380)]
    vocab = list(policy.POLICIES["PP-DocLayoutV2"])
    perm = order.permutation(labels, boxes, 600, 800, 0, vocab, "docling")
    assert sorted(perm) == list(range(len(boxes))), (
        f"не перестановка: {perm} на {len(boxes)} рамках")


def test_an_unknown_rule_dies_loudly():
    """Незнакомое значение ручки роняет прогон, а не молчит.

    Перепутанное имя перемешало бы абзацы, а рамки остались бы теми же — ни
    одна метрика рамок этого не заметила бы.
    """
    import os
    was = os.environ.get("ASSEMBLY_ORDER")
    os.environ["ASSEMBLY_ORDER"] = "сверхуВниз"
    try:
        order.rule()
    except SystemExit as e:
        assert "ASSEMBLY_ORDER" in str(e) and "ours" in str(e), e
    else:
        raise AssertionError("незнакомое правило принято молча")
    finally:
        if was is None:
            os.environ.pop("ASSEMBLY_ORDER", None)
        else:
            os.environ["ASSEMBLY_ORDER"] = was


def test_no_adapter_sorts_by_itself_any_more():
    """НИ ОДИН адаптер не сортирует своим ключом. Правило одно.

    Разбором исходника, а не прогоном: поднять три модели значит поднять
    полгигабайта весов, а договор надо проверять на каждом изменении.

    Умеет провалиться: верните `kept.sort(key=…)` в любой адаптер.
    """
    seen = {}
    for rel in ("models/doclayout.py", "models/yolox_layout.py",
                "models/docling_heron.py"):
        bad = []
        for node in ast.walk(support.tree(rel)):
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "sort"
                    and any(k.arg == "key" for k in node.keywords)):
                bad.append(node.lineno)
        seen[rel] = bad
    # У `doclayout` законна ОДНА сортировка — по РАНГУ САМОЙ МОДЕЛИ; это не
    # наше правило, и в `order.py` ему не место. У `docling_heron` законна
    # одна — НУМЕРАЦИЯ перед вендорским конвейером, `Cluster.id`, по нему
    # вендор сшивает детей с обёрткой.
    assert len(seen["models/doclayout.py"]) == 1, (
        f"в doclayout сортировок с ключом {len(seen['models/doclayout.py'])}, "
        f"а законна одна — по рангу модели: {seen['models/doclayout.py']}")
    assert len(seen["models/docling_heron.py"]) == 1, (
        f"в docling_heron сортировок {len(seen['models/docling_heron.py'])}, "
        f"а законна одна — нумерация перед конвейером")
    assert not seen["models/yolox_layout.py"], (
        f"yolox снова сортирует сам: строки {seen['models/yolox_layout.py']}. "
        f"Правило сборки живёт в order.py, и второй экземпляр разойдётся с "
        f"первым молча — так уже было в docling_heron")


def test_the_ruler_measures_the_same_rule_the_book_is_built_with():
    """Прибор спрашивает правило «наш» У `order.py`, а не повторяет его.

    ЧЕМ ЭТО ОПЛАЧЕНО. `metrics._by_reading` держал вторую копию —
    `sorted(key=(box[1], box[0]))` — и докстроку «тот самый порядок, который
    адаптеры объявляют словом „наш"». Ключи совпадали, `metrics` не
    импортировал `order` вовсе, и НИ ОДНА проверка их не связывала. А на этом
    сборщике снят главный вывод проекта: «наше правило замерено и проиграло»,
    2471 лишний прыжок против 501 у ранга модели и 439 у правил docling.
    Правка `order.permutation` оставила бы прибор мерить ПРЕЖНЕЕ правило и
    называть его нынешним — то есть развернула бы вывод, не тронув ни одной
    строки прибора.

    Ровно за такое `order.py` и заведён: правило жило в четырёх местах трёх
    адаптеров, и в двух сортировало `(round(y/20), x)`, объявляя в `meta`
    «сверху вниз и слева направо».

    Разбором исходника: сравнить ПОВЕДЕНИЕ двух правил мало — они совпадают
    сегодня, потому и прожили копией. Проверять надо, что второго правила нет.
    """
    t = support.tree("metrics.py")
    fn = next((n for n in ast.walk(t)
               if isinstance(n, ast.FunctionDef) and n.name == "_by_reading"),
              None)
    assert fn is not None, "в metrics.py не стало _by_reading — сборщик снят?"

    ours = [n.lineno for n in ast.walk(fn)
            if isinstance(n, ast.Call)
            and ((isinstance(n.func, ast.Name) and n.func.id == "sorted")
                 or (isinstance(n.func, ast.Attribute) and n.func.attr == "sort"))]
    assert not ours, (
        f"`_by_reading` снова сортирует сам (строки {ours}). Правило сборки "
        f"живёт в `order.py`; вторая копия разойдётся с первой МОЛЧА, а на "
        f"этом сборщике стоит вывод «наше правило проиграло»")

    calls = [n for n in ast.walk(fn)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
             and n.func.attr == "permutation"]
    assert calls, (
        "`_by_reading` не зовёт `order.permutation` — прибор мерит не то "
        "правило, которым собирается книга")
    named = {k.arg: k.value for c in calls for k in c.keywords}
    which = named.get("which")
    assert isinstance(which, ast.Constant) and which.value == "ours", (
        "`order.permutation` позван без `which=\"ours\"`. Без явного имени "
        "правило возьмётся из ручки `ASSEMBLY_ORDER`, и столбец «наше "
        "правило» станет означать разное в разных прогонах — сравнивать "
        "развёртку будет нельзя")
