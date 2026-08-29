"""Реестр ручек: что не объявлено — то не читается, и наоборот.

Правило проекта: «Ручка объявляется в реестре `run/knobs.py`. Чтение окружения
мимо реестра — ошибка: ручка, которой нет в реестре, не попадёт в слепок, и
прогон станет неповторимым молча». Молчаливую беду здесь ловить нечем — кроме
проверок.

Сам реестр про свою слепоту говорит честно: `VL_MODEL_DIR` поймал не он, а
удалённый `tests/test_knobs_registry.py`, разбиравший исходники деревом.
Половина того ловца восстановлена как `readers()`/`audit()` — здесь она
поставлена под проверку, а заодно закрыт кусок, который `readers()` за собой
не берёт вовсе: сверка объявлений `knobs_read()` у адаптеров с тем, что они
читают на самом деле. Там три списка, набранных руками, и расхождение в них
даёт слепок УВЕРЕННЫЙ И НЕВЕРНЫЙ — величина названа, а к прогону не относится.
"""
import os
import re

import support
from booksmith.models.doclayout import DocLayout
from booksmith.models.docling_heron import DoclingEgret, DoclingHeron
from booksmith.models.yolox_layout import YoloXLayout
from booksmith.run import knobs

ADAPTERS = ((DocLayout, "models/doclayout.py"),
            (DoclingHeron, "models/docling_heron.py"),
            (DoclingEgret, "models/docling_heron.py"),
            (YoloXLayout, "models/yolox_layout.py"))


def test_unknown_knob_raises_not_returns_empty():
    """Незаявленное имя бросает, а не отдаёт пустую строку.

    Пустая строка тут — это прогон, который выглядит настроенным и не
    повторяется.
    """
    try:
        knobs.knob("MULTIVIEW")          # была ручкой, снесена вместе с заплаткой
    except KeyError as e:
        assert "MULTIVIEW" in str(e) and "KNOBS" in str(e), (
            f"жалоба не называет ни ручку, ни реестр: {e}")
    else:
        raise AssertionError(
            "реестр отдал значение ручке, которой в нём нет: она не попадёт в "
            "слепок, и прогон станет неповторимым молча")


def test_names_are_unique():
    """Дубль имени молча затёр бы одну ручку другой в словаре KNOB."""
    names = [k.name for k in knobs.KNOBS]
    assert len(names) == len(set(names)), (
        f"имена ручек повторяются: "
        f"{sorted({n for n in names if names.count(n) > 1})}")


def test_defaults_are_strings():
    """Умолчание хранится СТРОКОЙ — ровно как приехало бы из окружения.

    Иначе слепок пишет `2.0` там, где прогон видел `"2"`, и сверка двух
    прогонов спотыкается о тип, а не о значение.
    """
    for k in knobs.KNOBS:
        assert isinstance(k.default, str), (
            f"{k.name}: умолчание {k.default!r} не строка")
        assert k.what, f"{k.name}: не сказано, что она делает"


def test_snapshot_holds_every_knob_with_every_field():
    s = knobs.snapshot()
    assert set(s) == set(knobs.names()), (
        f"в слепке {len(s)} ручек из {len(knobs.names())}: "
        f"{sorted(set(knobs.names()) ^ set(s))}")
    for name, rec in s.items():
        assert set(rec) == {"значение", "умолчание", "задано снаружи", "что",
                            "долг"}, f"{name}: поля слепка {sorted(rec)}"


def test_snapshot_tells_set_from_default():
    """«Задано снаружи» — отдельный вопрос от «значение».

    Пустая строка в окружении это ЗНАЧЕНИЕ, а не отсутствие: `${X:-0}` в
    оболочке и умолчание реестра обязаны говорить одно и то же.
    """
    name = "PAGE_DPI"
    old = os.environ.get(name)
    try:
        os.environ.pop(name, None)
        s = knobs.snapshot()[name]
        assert s["задано снаружи"] is False
        assert s["значение"] == s["умолчание"] == knobs.KNOB[name].default
        os.environ[name] = "999"
        s = knobs.snapshot()[name]
        assert s["задано снаружи"] is True and s["значение"] == "999"
        assert s["умолчание"] == knobs.KNOB[name].default, (
            "умолчание в слепке подменилось заданным: сравнить прогон с "
            "умолчанием станет не с чем")
        os.environ[name] = ""
        assert knobs.knob(name) == "", "пустая строка снаружи проиграла умолчанию"
    finally:
        os.environ.pop(name, None)
        if old is not None:
            os.environ[name] = old


def test_passthrough_carries_only_what_was_set():
    """На арендованную машину уезжает ЗАДАННОЕ, умолчания живут в одном месте."""
    old = os.environ.get("PASSES")
    try:
        os.environ.pop("PASSES", None)
        assert "PASSES" not in knobs.passthrough()
        os.environ["PASSES"] = "3"
        assert knobs.passthrough()["PASSES"] == "3"
        assert set(knobs.passthrough()) <= set(knobs.names())
    finally:
        os.environ.pop("PASSES", None)
        if old is not None:
            os.environ["PASSES"] = old


def test_audit_finds_no_disagreement():
    """Объявленный долг сходится с деревом исходников.

    Две тихие беды разом: ручку начали читать, а `debt=True` с неё не сняли; и
    последнего потребителя удалили вместе с кодом, а ручка стоит как живая.
    """
    bad = knobs.audit()
    assert bad == [], ("реестр разошёлся с деревом, расхождений "
                       f"{len(bad)}:\n  " + "\n  ".join(bad))


def test_readers_finds_consumers_and_counts_them():
    """`readers()` считает потребителей, а не помнит их прозой.

    Числа сверяются с реестром: живых ручек должно быть ровно столько,
    сколько всего минус объявленный долг.
    """
    who = knobs.readers()
    assert set(who) == set(knobs.names())
    live = sum(1 for v in who.values() if v)
    assert live == len(knobs.KNOBS) - len(knobs.debts()), (
        f"ручек {len(knobs.KNOBS)}, потребитель нашёлся у {live}, долгом "
        f"объявлено {len(knobs.debts())} — три числа не сходятся")
    for name in knobs.debts():
        assert knobs.KNOB[name].debt is True
        assert not who[name], f"{name}: объявлена долгом, а её читает {who[name]}"


def test_adapters_declare_the_knobs_they_read():
    """Сговор через файл: `knobs_read()` адаптера против его же исходника.

    Именно эту сверку `readers()` за собой не берёт, и живёт она тремя
    списками, набранными руками. Расхождение молчит: `books replay --check`
    вернёт 0, а `run.json` назовёт величину, к прогону не относящуюся, — как
    было с `LAYOUT_MODEL_NAME=PP-DocLayoutV2` в прогоне heron.
    """
    for cls, rel in ADAPTERS:
        with open(support.src_path(rel), encoding="utf-8") as f:
            text = f.read()
        read = set(re.findall(r'knob\(\s*["\']([A-Z_0-9]+)["\']', text))
        told = set(object.__new__(cls).knobs_read())
        assert told == read, (
            f"{cls.__name__}: объявлено {sorted(told)}, а в {rel} читается "
            f"{sorted(read)}. Лишнее в объявлении — уверенная неправда в "
            f"слепке, недостающее — ручка, решившая прогон и в него не "
            f"попавшая")
        unknown = told - set(knobs.names())
        assert not unknown, (
            f"{cls.__name__} объявляет ручки, которых нет в реестре: "
            f"{sorted(unknown)} — болезнь VL_MODEL_DIR")


def test_docling_pipeline_is_registered():
    """Ручка, решившая разницу в 5826 рамок, обязана быть в реестре."""
    k = knobs.KNOB["DOCLING_PIPELINE"]
    assert k.debt is False, "живая ручка помечена долгом"
    assert knobs.readers()["DOCLING_PIPELINE"], (
        "у DOCLING_PIPELINE не нашлось ни одного потребителя")
