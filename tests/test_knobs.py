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
        assert set(rec) == {"value", "default", "set_externally", "what",
                            "debt"}, f"{name}: поля слепка {sorted(rec)}"


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
        assert s["set_externally"] is False
        assert s["value"] == s["default"] == knobs.KNOB[name].default
        os.environ[name] = "999"
        s = knobs.snapshot()[name]
        assert s["set_externally"] is True and s["value"] == "999"
        assert s["default"] == knobs.KNOB[name].default, (
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


# --------------------------------------------------------------------------
# СГОВОР ДВУХ ФАЙЛОВ ПРОВЕРОК: `support.skip()` и `tests/run.py`. Живёт он
# здесь по той же причине, по какой здесь живут остальные: молчаливую беду
# ловить нечем, кроме проверки, а беда тут ровно такая — и молчит она обо
# ВСЁМ прогоне сразу.
#
# Чем оплачено. `support.skip()` выбирал форму пропуска по тому, ИМПОРТИРУЕТСЯ
# ли pytest, а не по тому, КТО ГОНЯЕТ. У pytest `Skipped` наследует
# BaseException, а не Exception, — мимо обеих ловушек `run_case`. Замер
# подставным модулем с тем же договором: под нашим бегуном первый же пропуск
# убивал прогон трассой, строка «проверок 111: прошло 110 …» не печаталась
# ВОВСЕ, код возврата 1. То есть достаточно было поставить pytest в `.venv`,
# чтобы 110 зелёных проверок перестали докладывать о себе.

def _fake_pytest():
    """Подставной pytest, повторяющий договор настоящего ДОСЛОВНО.

    `Skipped` от BaseException (у pytest он от `OutcomeException`, а тот от
    BaseException) и `skip.Exception`, который ставит декоратор
    `_with_exception`. Настоящий pytest в `.venv` не стоит, и ждать его
    установки, чтобы узнать про беду, — то же самое, что не проверять.
    """
    import types
    mod = types.ModuleType("pytest")

    class Skipped(BaseException):
        pass

    def skip(reason="", allow_module_level=False):
        raise Skipped(reason)

    skip.Exception = Skipped
    mod.skip, mod.Skipped = skip, Skipped
    return mod


def _with_fake_pytest(fn):
    """Выполнить с подставным pytest в `sys.modules` и вернуть как было."""
    import sys
    had = sys.modules.get("pytest")
    sys.modules["pytest"] = _fake_pytest()
    try:
        return fn()
    finally:
        if had is None:
            sys.modules.pop("pytest", None)
        else:
            sys.modules["pytest"] = had


def _raised_by_skip(own_runner):
    """Чем именно кончился `support.skip()` при подставном pytest.

    Ловится BaseException, и это не перестраховка: испорченный `skip()`
    поднимает `Skipped`, а тот наследует BaseException — выпусти его наружу,
    и он убьёт ВНЕШНИЙ бегун вместо того, чтобы покраснеть здесь. Мутация
    обязана краснеть названной проверкой, а не смертью прогона.
    """
    def body():
        was = support.OWN_RUNNER
        support.OWN_RUNNER = own_runner
        try:
            support.skip("нечем")
        except support.Skip as e:
            return "наш Skip", str(e)
        except BaseException as e:                          # noqa: BLE001
            return type(e).__name__, str(e)
        finally:
            support.OWN_RUNNER = was
        return "не поднялось вовсе", ""
    return _with_fake_pytest(body)


def test_skip_under_our_runner_does_not_depend_on_pytest_being_installed():
    """Наш бегун гоняет — пропуск НАШ, даже когда pytest лежит рядом."""
    kind, why = _raised_by_skip(own_runner=True)
    assert kind == "наш Skip", (
        f"при установленном pytest пропуск поднялся как {kind}: наш бегун "
        f"его не поймает и напечатает провал вместо пропуска — а `Skipped` "
        f"наследует BaseException, так что и вовсе умрёт, не напечатав итога")
    assert why == "нечем", "причина пропуска потерялась"


def test_skip_under_pytest_stays_a_pytest_skip():
    """Гоняет pytest — пропуск ЕГО. Иначе `Skip` уехал бы к нему провалом."""
    kind, _ = _raised_by_skip(own_runner=False)
    assert kind == "Skipped", (
        f"под pytest пропуск объявлен как {kind} — он засчитает проверку "
        f"провалом, а не пропуском")


def _load_runner():
    """Сам бегун, поднятый ОТДЕЛЬНЫМ модулем.

    Отдельным, потому что запущенный бегун зовётся `__main__`, а под pytest
    его нет вовсе. Загрузка объявляет `support.OWN_RUNNER`, и вызывающий
    обязан вернуть его как было: иначе следующая проверка под pytest получила
    бы наш пропуск вместо его.
    """
    import importlib.util
    import os as _os

    spec = importlib.util.spec_from_file_location(
        "booksmith_tests_runner",
        _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "run.py"))
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    return runner


def test_runner_counts_a_foreign_skip_as_a_skip_and_survives():
    """Чужой пропуск (`pytest.skip`) — пропуск, а не смерть бегуна.

    Вторая половина починки: даже если проверка позовёт `pytest.skip()` мимо
    `support.skip()`, итог обязан напечататься. Величина здесь — СОСТОЯНИЕ,
    а не «не упало»: провал и пропуск считаются разными числами, и подмена
    одного другим — та же ложь, что молчание.
    """
    was = support.OWN_RUNNER
    try:
        runner = _load_runner()
        def body():
            import sys
            try:
                return runner.run_case(
                    lambda: sys.modules["pytest"].skip("нечем"))
            except BaseException as e:                      # noqa: BLE001
                # Испорченный бегун чужой пропуск не ловит и выпускает его
                # наружу — именно так он и умирал. Ловим здесь, чтобы
                # покраснела эта проверка, а не весь прогон.
                return f"выпущено наружу ({type(e).__name__})", str(e)
        state, why = _with_fake_pytest(body)
    finally:
        support.OWN_RUNNER = was
    assert state == "skip", (
        f"чужой пропуск засчитан как «{state}»: `Skipped` наследует "
        f"BaseException и мимо ловушек `run_case` убивал бегун целиком — "
        f"итог не печатался вовсе")
    assert "нечем" in why, f"причина пропуска потерялась: {why!r}"


def test_runner_still_lets_a_real_interrupt_out():
    """KeyboardInterrupt наружу: бегун, который его глотает, неостановим."""
    was = support.OWN_RUNNER
    try:
        runner = _load_runner()
        def boom():
            raise KeyboardInterrupt("Ctrl+C")
        try:
            runner.run_case(boom)
        except KeyboardInterrupt:
            return
    finally:
        support.OWN_RUNNER = was
    raise AssertionError(
        "бегун проглотил Ctrl+C и записал его в состояние проверки: "
        "остановить прогон стало нечем")


# --------------------------------------------------------------------------
# ПОЛНОТА СЛЕПКА: `replay.shape()` выводит требуемую форму отпечатка разбором
# исходника адаптера. Разбор бывает бессилен — отпечаток собран включением, за
# циклом, отдан готовым полем, — и вот этот случай стоил прибору лица: ветка
# «отпечаток» не попадала в требования ВООБЩЕ, и слепок, где отпечатка нет
# вовсе, проходил `books replay --check` с кодом 0, строкой «величин в слепке
# 51 из 51, не хватает 0» и словом СВЕРЕН рядом. Проверка полноты одобряла
# неполный слепок ровно тогда, когда сама не справилась.

def _adapter_with_underivable_fingerprint(tmp):
    """Писатель слепка, чью форму разбор дерева НЕ выведет.

    Настоящий по устройству: класс с объявленным `name` и объявленным
    `fingerprint()`. Ключей в нём разбор не находит ни одного — они
    считаются на прогоне.
    """
    path = os.path.join(tmp, "myocr.py")
    with open(path, "w", encoding="utf-8") as f:
        f.write("class MyOcr:\n"
                "    name = \"myocr\"\n\n"
                "    def fingerprint(self):\n"
                "        return {k: v for k, v in self._parts.items()}\n")
    return path


def test_shape_that_could_not_be_derived_is_loud_not_silent():
    """«Вывести не удалось» — величина, а не молчаливое согласие.

    Требуется хотя бы САМА ветка отпечатка: слепок без неё обязан быть
    неполным. И незнание названо числом — `не выведено`, — иначе «проверено
    всё» и «проверено то, что смогли» неразличимы.
    """
    import shutil as _sh
    import tempfile

    from booksmith.run import replay

    tmp = tempfile.mkdtemp(prefix="booksmith-shape-")
    was = replay.PKG
    try:
        path = _adapter_with_underivable_fingerprint(tmp)
        replay.PKG = tmp
        snap = {}
        for p, _ in replay._base(knobs.names()):
            cur = snap
            for k in p[:-1]:
                cur = cur.setdefault(k, {})
            cur[p[-1]] = "есть"
        snap["adapter"] = {"name": "myocr", "module": "booksmith.myocr",
                           "sha256": replay._sha256(path)}
        assert replay.FP not in snap, "ветку отпечатка кладём не мы"
        sh = replay.shape(snap)
        assert sh["not_derived"] == 1, (
            "форму отпечатка вывести не удалось, а прибор об этом молчит: "
            "молчание тут читается как «проверено всё»")
        miss = replay.missing(snap, replay.required(snap, sh))
        assert [p for p, _ in miss] == [(replay.FP,)], (
            f"слепок ВОВСЕ БЕЗ ветки «{replay.FP}» объявлен полным: "
            f"не хватает {len(miss)}, а `books replay --check` вернул бы 0")
        assert not sh["verified"], (
            "форма не выведена, а отпечаток назван сверенным — слово СВЕРЕН "
            "рядом с невыведенной формой и было главной ложью")
        assert replay.selfcheck(_tmp_out(tmp, snap), log=lambda *_a: None) > 0, (
            "батарея слепка вернула ноль на слепке без отпечатка: ноль от "
            "непонимания выдан за ноль от проверки")
    finally:
        replay.PKG = was
        _sh.rmtree(tmp, ignore_errors=True)


def _tmp_out(tmp, snap):
    """Каталог с `run.json` — то, что `replay.selfcheck` читает с диска."""
    import json
    out = os.path.join(tmp, "выход")
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "run.json"), "w", encoding="utf-8") as f:
        json.dump(snap, f, ensure_ascii=False)
    return out


def test_derivable_shape_still_requires_every_value():
    """Обратная сторона: где форма ВЫВЕЛАСЬ, требуется не одна ветка, а всё.

    Без этой половины починку можно было бы «сделать», объявив невыводимой
    любую форму: ветка требуется, а внутри — ничего.
    """
    from booksmith.run import replay

    tree = replay._parse(support.src_path("models/doclayout.py"))
    fn, cls = replay._fp_def(tree, "DocLayout")
    keys = replay._returned(fn, tree, cls)
    assert len(keys) > 10, (
        f"из `DocLayout.fingerprint()` выведено {len(keys)} величин — разбор "
        f"ослеп, и требование к отпечатку осыпалось до одной ветки")


# ---------------------------------------------------------------- .sh И РЕЕСТР
# Обещание, которое ДО этой проверки не выполнялось ничем. В
# `models/paddleocr_vl/run.sh` стоит дословно: «Расхождение поймает
# `tests/test_knobs.py`, который сверяет правые части `${X:-…}` с ним
# [реестром]». Такой сверки не было: ни одна проверка каталога не открывала
# `.sh` вовсе, а `knobs.readers()` ищет в оболочке только НАЛИЧИЕ `$ИМЯ`, не
# значение. То есть обещанный сторож существовал одной строкой прозы, и это
# хуже отсутствующего: на него ссылались, принимая решения.

_SH_OPEN = re.compile(r'\$\{([A-Z_][A-Z0-9_]*):-')


def _sh_scan(text):
    """Пары (имя, умолчание) из `${ИМЯ:-…}`, СО СЧЁТОМ СКОБОК.

    Регэксп `[^}]*` здесь не годится, и это не педантизм: в `run.sh` стоит
    `PORT="${PORT_ARG:-${PORT:-8118}}"`, и такой регэксп съедает внешнее
    целиком, а внутреннее `${PORT:-8118}` не видит ВОВСЕ. Первая редакция
    этой проверки так и промахнулась: подменённый в копии дерева `PORT`
    (9999 против 8118 в реестре) прошёл незамеченным, и проверка объявила
    себя исправной. Сторож, слепой к вложенности, стережёт не то, что обещает.
    """
    pairs = []
    for m in _SH_OPEN.finditer(text):
        name = m.group(1)
        i, depth = m.end(), 1
        while i < len(text) and depth:
            if text.startswith("${", i):
                depth += 1
                i += 2
                continue
            if text[i] == "}":
                depth -= 1
                if not depth:
                    break
            i += 1
        pairs.append((name, text[m.end():i]))
    return pairs


def _sh_defaults():
    """Все `${ИМЯ:-умолчание}` из скриптов, что уезжают на арендованную карту."""
    out = {}
    root = os.path.join(support.SRC, "models")
    for directory, _, files in os.walk(root):
        for f in sorted(files):
            if not f.endswith(".sh"):
                continue
            path = os.path.join(directory, f)
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
            # КОММЕНТАРИИ ОТБРАСЫВАЮТСЯ, и это не мелочь. В `run.sh` те же
            # `${PORT:-8118}` стоят ВТОРОЙ раз — в прозе, объясняющей правило.
            # Сверяя прозу наравне с кодом, сторож падал бы от правки
            # комментария, то есть от того, что поведения не меняет. Проверено:
            # порча ТОЛЬКО примера в комментарии роняла проверку.
            without_prose = "\n".join(
                l for l in text.split("\n") if not l.lstrip().startswith("#"))
            for name, default in _sh_scan(without_prose):
                # `${X:-…}` — образец из комментария, а не переменная.
                if name == "X":
                    continue
                out.setdefault(name, []).append(
                    (os.path.relpath(path, support.SRC), default))
    return out


def test_shell_defaults_agree_with_the_registry():
    """Умолчание в `.sh` совпадает с умолчанием реестра — или признано вслух.

    ДВА РАЗНЫХ СЛУЧАЯ, И ИХ НЕЛЬЗЯ МЕРИТЬ ОДНОЙ МЕРКОЙ.

    Реестр ОБЪЯВИЛ умолчание (непустое) — оболочка обязана подставлять то же.
    Разойдясь, они дают прогон, где слепок пишет одно, а карта считает другим,
    и заметить это можно только по счёту.

    Реестр умолчания НЕ ДАЁТ (пустая строка) — значит хозяин значения не он, а
    оболочка, и это обязано быть СКАЗАНО в самой записи реестра. Иначе пустое
    умолчание неотличимо от забытого: ровно болезнь `VL_MODEL_DIR`, о которой
    шапка `run/knobs.py` пишет, что ловец её восстановлен НАПОЛОВИНУ.

    Имя, которого в реестре нет вовсе, эта проверка НЕ ловит — и не
    притворяется ловящей: для этого нужен список законных переменных оболочки,
    а его нет. Их ВОСЕМЬ, а не шесть, как стояло здесь: к `ENVDIR`, `MODELS`,
    `HF_HOME`, `VL_REPO`, `SRV`, `PYTORCH_CUDA_ALLOC_CONF` добавляются
    `DOTS_DIR` (та самая ручка мимо реестра, о которой пишет шапка
    `run/knobs.py`) и `PORT_ARG` — позиционный аргумент `run.sh`, чьё
    умолчание само есть `${PORT:-8118}`.

    ЧЕГО ЭТА ПРОВЕРКА НЕ СВЕРЯЕТ, ХОТЯ ВЫГЛЯДИТ СВЕРЯЮЩЕЙ. У ручки с ПУСТЫМ
    умолчанием реестра значение из `.sh` не сверяется ни с чем — сверяется
    только признание в описании. То есть подмена `${VL_MODEL_DIR:-/models/vl}`
    на `/models/xxx` проходит молча, и это проверено мутацией. Иначе нельзя:
    хозяин значения объявлен оболочкой, и второго места для него нет.
    """
    registry = {k.name: k for k in knobs.KNOBS}
    found = _sh_defaults()

    # ЗНАМЕНАТЕЛЬ, БЕЗ КОТОРОГО ПРОВЕРКА ЗЕЛЕНА НИ НА ЧЁМ. Не найдись ни
    # одного `.sh` — `_sh_defaults()` вернёт пустоту, `беды` останутся
    # пустыми, и `assert not беды` пройдёт, не сверив НИ ОДНОГО имени.
    # Проверено исполнением: при пустом каталоге `models` проверка была
    # зелёной. Это «ноль от проверки против нуля от непонимания», и соседняя
    # проверка этого же файла защищается ровно так же — числом.
    checked = sorted(n for n in found if n in registry)
    assert len(checked) >= 4, (
        f"сверено всего {len(checked)} имён ({checked}) — проверка зелена ни "
        f"на чём. Ждём хотя бы четыре: скрипты, уезжающие на карту, читают "
        f"MODEL_NAME, PORT, RESUME, VLLM_USE_FLASHINFER_SAMPLER и "
        f"VL_MODEL_DIR. Пусто здесь значит, что `.sh` не нашлись или разбор "
        f"перестал их видеть, а не что расхождений нет")

    troubles = []
    for name, places in sorted(found.items()):
        k = registry.get(name)
        if k is None:
            continue
        for file, default in places:
            if k.default:
                if default != k.default:
                    troubles.append(
                        f"  {name}: в {file} умолчание {default!r}, "
                        f"в реестре {k.default!r}")
            elif "run.sh" not in k.what and "оболочк" not in k.what:
                troubles.append(
                    f"  {name}: реестр умолчания не даёт, а {file} подставляет "
                    f"{default!r}, и запись реестра об этом молчит "
                    f"(«{k.what[:60]}»)")
    assert not troubles, (
        "умолчания оболочки разошлись с реестром:\n" + "\n".join(troubles)
        + "\nУ умолчания одно место жительства. Разойдясь, слепок пишет одно, "
          "а арендованная карта считает другим — и узнать об этом можно "
          "только по счёту.")


def test_replay_finds_the_snapshot_in_both_layouts():
    """Слепок ищется и в корне, и в кухне — два законных места.

    У каталога ДЕТЕКЦИИ `run.json` лежит в корне, у каталога КНИГИ — в
    `assets/`: там в корне ровно один файл, сама книга. Проверка полноты
    смотрела только корень и на книге отвечала «слепка нет вовсе» при слепке
    этажом ниже, возвращая 1. При этом сборщик обещает дословно: «`books
    replay --check` обязан вернуть 0 и здесь».

    Говорящий шаг, врущий нулём, — то же правило, из-за которого «глав 0»
    читалось как «глав в книге нет».
    """
    import json as _json
    import tempfile

    from booksmith.doc.html import ASSETS
    from booksmith.run import replay

    snapshot = {"knobs": {"PAGE_DPI": {"value": "144"}}}
    with tempfile.TemporaryDirectory() as tmp:
        assert replay.facts(tmp) == {}, "слепок найден там, где его нет"

        with open(os.path.join(tmp, "run.json"), "w", encoding="utf-8") as f:
            _json.dump(snapshot, f)
        assert replay.facts(tmp) == snapshot, "слепок в корне не прочитан"

    with tempfile.TemporaryDirectory() as tmp:
        os.makedirs(os.path.join(tmp, ASSETS))
        with open(os.path.join(tmp, ASSETS, "run.json"), "w",
                  encoding="utf-8") as f:
            _json.dump(snapshot, f)
        assert replay.facts(tmp) == snapshot, (
            "слепок в кухне не прочитан — `books replay --check` на каталоге "
            "книги скажет «слепка нет вовсе» при лежащем рядом слепке")
