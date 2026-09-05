"""Сговор внутри `yolox_layout.py`: чем ужимают вход и что об этом записано.

ЧТО ЗДЕСЬ ЗАКРЕПЛЕНО И ЧЕМ ЗА ЭТО ПЛАТИЛИ. Фильтр ужатия был голым литералом
`interpolation=1` внутри `_letterbox` и в отпечаток не попадал — в отличие от
соседней подложки `PAD`, объявленной константой. А решает он больше всех
прочих чисел файла: замер на `bench/slovar` (13 страниц, прочее неизменно) —
520 рамок при LINEAR, 492 при NEAREST, 497 при CUBIC, 519 при AREA, и
СОВПАВШИХ С БАЗОЙ рамок 0, 1 и 28 соответственно. То есть подмена фильтра
меняет все координаты до единой. У `doclayout` этот же фильтр читается из
весов и лежит в отпечатке; здесь `books replay --check` увидеть его не мог по
построению, и прогон был неповторим МОЛЧА.

Величину объявили константой и завели в отпечаток — а сторожа не поставили, и
скептик это доказал прогоном: из копии дерева вынули поле «фильтр cv2», и
батарея объявила себя полностью исправной (163 проверки, 0 провалено; 139
мутаций, 139 поймано). Свежий `books detect` испорченным кодом давал слепок
без поля, а `replay --check` печатал «величин в слепке 77 из 77, не хватает 0»
и код 0. То есть неповторимость возвращалась ровно тем же молчанием.

РАЗБОРОМ ИСХОДНИКА, А НЕ ИСПОЛНЕНИЕМ: `fingerprint()` живёт на построенном
адаптере, а построить его — поднять 216 МБ весов. Разбор видит ровно то, что
увидит человек. Тот же приём, что у прочих сговоров этого каталога.
"""
import ast

import support

REL = "models/yolox_layout.py"


def _resize_call(t):
    """Единственный `cv2.resize` файла."""
    out = []
    for node in ast.walk(t):
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "resize"):
            out.append(node)
    return out


def test_the_resize_filter_is_a_named_constant_not_a_literal():
    """`cv2.resize` берёт фильтр ИМЕНЕМ, а не числом на месте.

    Умеет провалиться: верните `interpolation=1`, и проверка покраснеет.
    """
    calls = _resize_call(support.tree(REL))
    assert len(calls) == 1, f"вызовов cv2.resize {len(calls)}, ожидался один"
    kw = {k.arg: k.value for k in calls[0].keywords}
    assert "interpolation" in kw, "фильтр ужатия вообще не задан"
    v = kw["interpolation"]
    assert isinstance(v, ast.Name), (
        "фильтр ужатия задан числом на месте, а не именованной константой — "
        "значит в отпечаток он не попадёт и прогон станет неповторим молча")
    assert v.id == "INTERP", f"фильтр зовут {v.id}, а отпечаток ждёт INTERP"


def test_the_fingerprint_declares_the_resize_filter():
    """Отпечаток объявляет фильтр ужатия ТОЙ ЖЕ константой.

    Сговор здесь между двумя местами одного файла: `_letterbox` ужимает, а
    `fingerprint` записывает. Разойдясь, они оба остаются исправными на вид.
    """
    t = support.tree(REL)
    named = set()
    for node in ast.walk(t):
        if not isinstance(node, ast.Dict):
            continue
        for k, v in zip(node.keys, node.values):
            if (isinstance(k, ast.Constant) and k.value == "фильтр cv2"
                    and isinstance(v, ast.Name)):
                named.add(v.id)
    assert "INTERP" in named, (
        "в отпечатке нет поля «фильтр cv2» со значением INTERP. Подмена "
        "фильтра меняет ВСЕ координаты рамок (520 против 492/497/519 на "
        "bench/slovar, совпавших с базой 0/1/28), а слепок об этом молчит — "
        "`books replay --check` такую разницу увидеть не может")


def test_the_fingerprint_asks_the_threshold_guard_instead_of_a_literal():
    """«Расхождение порога» в отпечатке — ВЫЗОВ сторожа, а не литерал.

    ЧЕМ ЭТО ОПЛАЧЕНО. Здесь стояло зашитое `[]`, при том что
    `threshold_drift()` у этой сборки говорит непустое ВСЕГДА: родного порога
    у весов нет, действует наш `LAYOUT_SCORE_THRESHOLD`. То есть адаптер
    кричал об этом в журнал, а в `run.json` писал «расхождения нет» — слепок
    противоречил собственному сторожу, и ровно этот дефект у `docling_heron`
    уже был найден и починен, а третий адаптер из трёх забыли.

    Литерал опасен тем, что выглядит исправным: поле в слепке ЕСТЬ, и
    `books replay --check` его наличие одобряет — он сверяет ключи, а не
    значения. Разбором исходника, а не исполнением, по той же причине, что и
    у соседних проверок файла: построить адаптер значит поднять веса.
    """
    t = support.tree(REL)
    seen = []
    for node in ast.walk(t):
        if not isinstance(node, ast.Dict):
            continue
        for k, v in zip(node.keys, node.values):
            if isinstance(k, ast.Constant) and k.value == "расхождение порога":
                seen.append(v)
    assert seen, "в отпечатке нет поля «расхождение порога» вовсе"
    assert all(isinstance(v, ast.Call)
               and isinstance(v.func, ast.Attribute)
               and v.func.attr == "threshold_drift" for v in seen), (
        "поле «расхождение порога» в отпечатке — не вызов "
        "`self.threshold_drift()`. Зашитое значение врёт молча: сторож "
        "говорит «родного порога нет, действует наш LAYOUT_SCORE_THRESHOLD», "
        "а слепок отвечает «расхождения нет», и `replay --check` это "
        "одобряет, потому что сверяет наличие ключа, а не значение")
