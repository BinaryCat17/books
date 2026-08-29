"""Вендорский конвейер docling: поимённость перевода и цена выключенной ручки.

Две вещи, обе про сговор двух файлов.

ПЕРВАЯ. Перевод ярлыков наших весов в словарь docling объявлен ПОИМЁННО
(`EGRET_TO_DOCLING`), а не правилом «в нижний регистр, дефис в подчёркивание».
Правило молча приняло бы восемнадцатый класс новых весов и подсунуло бы его
вендору под выдуманным именем. Поэтому неизвестное имя обязано ронять
ПОСТРОЕНИЕ конвейера — на нулевой странице и по всему словарю весов сразу, а
не на четырёхсотой после двадцати минут счёта.

ВТОРАЯ. `DOCLING_PIPELINE=off` — умолчание, и оно куплено замером: конвейер
ухудшает слияние (366 -> 461), находимость (694 -> 562) и целость смысла
(602 -> 500). Значит выключенный он обязан быть НЕ ПРОСТО безвредным, а
тождественным прежнему коду: те же рамки, те же объекты, то же место ключа в
meta. Иначе сверка «ручка выключена — ничего не изменилось» споткнётся о
порядок ключей json, а не о рамки.
"""
import json
import os
from dataclasses import asdict

import support
from booksmith import policy
from booksmith.models import docling_heron as dh
from booksmith.models.base import Block
from booksmith.run import knobs

OFF_META_KEYS = ["порядок чтения"]
# Состав и порядок ключей meta страницы ДО появления конвейера. Конвейер
# добавил `**pipe_meta` ровно на место бывшего «порядок чтения», и при `off`
# он разворачивается в него же — страница выходит побайтово прежней.
META_BEFORE_PIPELINE = ["распознаватель", "растр", "рамок принято",
                        "связок рангов", "порядок чтения",
                        "лучший отвергнутый по классам"]


class env:
    """Ручка на время проверки. Окружение живое — возвращаем как было."""

    def __init__(self, **kw):
        self.kw, self.old = kw, {}

    def __enter__(self):
        for k, v in self.kw.items():
            self.old[k] = os.environ.get(k)
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def __exit__(self, *a):
        for k, v in self.old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def have_docling():
    try:
        import docling                                       # noqa: F401
        return True
    except ImportError:
        return False


def test_pipeline_default_is_off():
    """Умолчание ВЫКЛЮЧЕНО, и это решение замера, а не вкус."""
    assert knobs.KNOB["DOCLING_PIPELINE"].default == "off"
    with env(DOCLING_PIPELINE=None):
        assert knobs.knob("DOCLING_PIPELINE") == "off"


def test_three_modes_not_two():
    """`post` и `full` — разные значения: эффекты разные, и их надо разводить."""
    assert dh.PIPELINE_MODES == ("off", "post", "full")


def test_unknown_mode_dies_loudly():
    """`DOCLING_PIPELINE=вкл` роняет прогон и называет, что знает.

    Падение стоит миллисекунды и происходит ДО импорта docling: проверка
    режима — первая строка конструктора.
    """
    try:
        dh._DoclingPipeline("вкл", list(dh.DEFAULT_LABELS), "docling")
    except SystemExit as e:
        assert "off" in str(e) and "post" in str(e) and "full" in str(e)
    else:
        raise AssertionError("неизвестный режим ручки принят молча")


def test_translation_covers_both_dictionaries():
    """Перевод сверяется с ОБОИМИ словарями политики, а не с одним.

    Ключи `EGRET_TO_DOCLING` — витринные имена egret, значения — снейк-кейс
    heron. Ровно эти же два набора объявлены политиками `Docling-egret` и
    `Docling`. Разъедутся — вендор получит выдуманное имя, а `policy.check`
    уронит прогон на своём же стенде.
    """
    assert set(dh.EGRET_TO_DOCLING) == set(policy.DOCLING_EGRET), (
        "словарь перевода и политика egret разошлись: "
        f"{sorted(set(dh.EGRET_TO_DOCLING) ^ set(policy.DOCLING_EGRET))}")
    assert set(dh.EGRET_TO_DOCLING.values()) == set(policy.DOCLING), (
        "перевод ведёт не в словарь heron: "
        f"{sorted(set(dh.EGRET_TO_DOCLING.values()) ^ set(policy.DOCLING))}")
    assert set(dh.DEFAULT_LABELS) == set(policy.DOCLING), (
        "запасной словарь ярлыков heron разошёлся с политикой Docling")


def test_unknown_label_dies_at_construction():
    """Неизвестное имя роняет ПОСТРОЕНИЕ, а не первую страницу.

    Проверяется по всему словарю весов сразу: на странице чужой ярлык мог бы и
    не встретиться, а прогон всё равно неверен.
    """
    if not have_docling():
        support.skip("нет пакета docling: pip install -e \".[docling]\"")
    good = list(dh.DEFAULT_LABELS)
    dh._DoclingPipeline("post", good, "docling")      # словарь весов целиком
    try:
        dh._DoclingPipeline("post", good + ["Chart"], "docling")
    except SystemExit as e:
        assert "Chart" in str(e), f"в жалобе нет самого ярлыка: {e}"
        assert "EGRET_TO_DOCLING" in str(e), (
            f"жалоба не говорит, ГДЕ чинить: {e}")
    else:
        raise AssertionError(
            "конвейер построился со словарём, в котором есть непереводимый "
            "ярлык: он доедет до вендора под выдуманным именем")


def test_egret_names_translate_whole():
    """Витринные имена egret переводятся все до одного, тем же построением."""
    if not have_docling():
        support.skip("нет пакета docling")
    p = dh._DoclingPipeline("post", list(dh.EGRET_TO_DOCLING),
                            "docling-egret")
    assert set(p.to_docling) == set(dh.EGRET_TO_DOCLING)
    assert set(p.back) == set(dh.EGRET_TO_DOCLING.values()), (
        "обратный перевод неполон: наружу ярлык обязан возвращаться в "
        "написании адаптера, иначе policy.check уронит прогон egret")


def _blocks():
    return [Block(block_id=0, box=(10.0, 20.0, 110.0, 60.0), label="table",
                  score=0.9, order=0),
            Block(block_id=1, box=(10.0, 70.0, 110.0, 90.0), label="text",
                  score=0.8, order=1)]


def test_off_returns_the_very_same_frames():
    """При выключенной ручке рамки не копируются и не трогаются ВОВСЕ.

    Сверяется тождество объекта, а не равенство: копия, сделанная «на всякий
    случай», уже была бы местом, где что-то может измениться.
    """
    adapter = object.__new__(dh.DoclingHeron)
    adapter._pipe = None
    blocks = _blocks()
    before = json.dumps([asdict(b) for b in blocks], ensure_ascii=False)
    out, meta = adapter._run_pipeline(blocks, 800, 1200, 0)
    assert out is blocks, "при off рамки пересобираются — это уже не «как есть»"
    assert json.dumps([asdict(b) for b in out], ensure_ascii=False) == before


def test_off_adds_exactly_one_meta_key():
    """И ровно один ключ meta, тот самый. Лишний ключ — уже другая страница."""
    adapter = object.__new__(dh.DoclingHeron)
    adapter._pipe = None
    _, meta = adapter._run_pipeline(_blocks(), 800, 1200, 0)
    assert list(meta) == OFF_META_KEYS, (
        f"при off meta страницы получила {list(meta)}, а прежде в ней стоял "
        f"один ключ {OFF_META_KEYS}")


def test_off_keeps_meta_key_order_byte_for_byte():
    """Место ключа в словаре — не косметика: json пишет ключи по порядку."""
    keys = support.meta_keys("models/docling_heron.py", "DoclingHeron")
    assert "**pipe_meta" in keys, (
        "в meta страницы больше нет `**pipe_meta`: либо конвейер пишет ключи "
        "мимо, либо проверка отстала от кода")
    i = keys.index("**pipe_meta")
    got = keys[:i] + OFF_META_KEYS + keys[i + 1:]
    assert got == META_BEFORE_PIPELINE, (
        f"при DOCLING_PIPELINE=off состав или порядок ключей meta изменился:\n"
        f"  было  {META_BEFORE_PIPELINE}\n  стало {got}\n"
        f"Побайтового совпадения с прежними страницами больше нет.")


def test_adapter_at_off_builds_no_pipeline():
    """Живой адаптер на настоящих весах: при off вендорского кода нет вовсе.

    Медленная (поднимает сессию ONNX), поэтому по требованию: --slow.
    """
    if not os.environ.get("BOOKSMITH_TESTS_SLOW"):
        support.skip("медленная (~5с, поднимает ONNX): запусти с --slow")
    if not os.path.isdir(os.path.join(dh.MODELS, "docling-heron_onnx")):
        support.skip("нет весов docling-heron_onnx")
    with env(DOCLING_PIPELINE="off"):
        a = dh.DoclingHeron()
    assert a.pipeline == "off"
    assert a._pipe is None, "ручка выключена, а конвейер вендора построен"
    assert "DOCLING_PIPELINE" in a.knobs_read(), (
        "ручка решает прогон, но адаптер её не объявляет — слепок двух "
        "разных прогонов станет неотличим")
