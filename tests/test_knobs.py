"""The knob registry: what is not declared is not read, and the reverse.

The project rule -- a knob absent from `run/knobs.py` never reaches the
snapshot and the run becomes silently irreproducible -- is held here by nothing
but checks.

The registry is honest about its blindness: `VL_MODEL_DIR` was caught not by it
but by the deleted `tests/test_knobs_registry.py`, which parsed sources as
trees. Half of that catcher came back as `readers()`/`audit()`, put under check
here together with the piece it does not take on: the adapters' `knobs_read()`
declarations against what they really read. Three hand-typed lists, and a drift
gives a snapshot CONFIDENT AND WRONG.
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
    """An undeclared name raises instead of returning an empty string.

    An empty string here is a run that looks configured and does not repeat.
    """
    try:
        knobs.knob("MULTIVIEW")          # once a knob, removed with its patch
    except KeyError as e:
        assert "MULTIVIEW" in str(e) and "KNOBS" in str(e), (
            f"жалоба не называет ни ручку, ни реестр: {e}")
    else:
        raise AssertionError(
            "реестр отдал значение ручке, которой в нём нет: она не попадёт в "
            "слепок, и прогон станет неповторимым молча")


def test_names_are_unique():
    """A duplicate name would silently overwrite one knob in KNOB."""
    names = [k.name for k in knobs.KNOBS]
    assert len(names) == len(set(names)), (
        f"имена ручек повторяются: "
        f"{sorted({n for n in names if names.count(n) > 1})}")


def test_defaults_are_strings():
    """A default is kept as a STRING, as it would arrive from the shell.

    Otherwise the snapshot writes `2.0` where the run saw `"2"`, and comparing
    two runs trips over the type instead of the value.
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
    """Whether a knob was SET is a question apart from its value.

    An empty string in the environment is a VALUE, not an absence: `${X:-0}` in
    the shell and the registry default must say one and the same thing.
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
    """What ships to the card is what was SET; defaults live in one place."""
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
    """The declared debt agrees with the source tree.

    Two silent troubles at once: a knob started being read and `debt=True` was
    never taken off it; and the last consumer was deleted with its code while
    the knob stands as if alive.
    """
    bad = knobs.audit()
    assert bad == [], ("реестр разошёлся с деревом, расхождений "
                       f"{len(bad)}:\n  " + "\n  ".join(bad))


def test_readers_finds_consumers_and_counts_them():
    """`readers()` counts consumers instead of remembering them in prose.

    The numbers are checked against the registry: live knobs must be exactly as
    many as the total minus the declared debt.
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
    """A contract through a file: `knobs_read()` against the adapter's source.

    The comparison `readers()` does not take on. A drift is silent: `books
    replay --check` returns 0 while `run.json` names a value that has nothing
    to do with the run -- as happened with `LAYOUT_MODEL_NAME=PP-DocLayoutV2`
    in a heron run.
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
    """The knob that decided 5826 boxes must be in the registry."""
    k = knobs.KNOB["DOCLING_PIPELINE"]
    assert k.debt is False, "живая ручка помечена долгом"
    assert knobs.readers()["DOCLING_PIPELINE"], (
        "у DOCLING_PIPELINE не нашлось ни одного потребителя")


# --------------------------------------------------------------------------
# A CONTRACT BETWEEN TWO CHECK FILES: `support.skip()` and `tests/run.py`, and
# it is silent about the WHOLE run at once. `support.skip()` chose the form of
# a skip by whether pytest was IMPORTABLE, not by WHO RUNS, and in pytest
# `Skipped` inherits BaseException, not Exception -- past both traps of
# `run_case`. Measured with a stand-in module of the same contract: under our
# runner the first skip killed the run with a traceback, the line "checks 111:
# passed 110 ..." did not print AT ALL, exit code 1. Installing pytest into
# `.venv` was enough to stop 110 green checks reporting themselves.

def _fake_pytest():
    """A stand-in pytest repeating the real contract WORD FOR WORD.

    `Skipped` from BaseException (in pytest from `OutcomeException`, and that
    from BaseException) and the `skip.Exception` its `_with_exception`
    decorator sets. Real pytest is not in `.venv`, and waiting for it to learn
    of the trouble is the same as not checking.
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
    """Run with a stand-in pytest in `sys.modules`, then put it back."""
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
    """What exactly `support.skip()` ended with under a stand-in pytest.

    BaseException is caught deliberately: a broken `skip()` raises `Skipped`,
    which inherits BaseException -- let it out and it kills the OUTER runner. A
    mutation must go red as a named check, not as the death of the run.
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
    """Our runner runs -- the skip is OURS, even with pytest installed."""
    kind, why = _raised_by_skip(own_runner=True)
    assert kind == "наш Skip", (
        f"при установленном pytest пропуск поднялся как {kind}: наш бегун "
        f"его не поймает и напечатает провал вместо пропуска — а `Skipped` "
        f"наследует BaseException, так что и вовсе умрёт, не напечатав итога")
    assert why == "нечем", "причина пропуска потерялась"


def test_skip_under_pytest_stays_a_pytest_skip():
    """pytest runs -- the skip is HIS, else `Skip` reaches him as a failure."""
    kind, _ = _raised_by_skip(own_runner=False)
    assert kind == "Skipped", (
        f"под pytest пропуск объявлен как {kind} — он засчитает проверку "
        f"провалом, а не пропуском")


def _load_runner():
    """The runner itself, raised as a SEPARATE module.

    Separate because a running runner is called `__main__`, and under pytest
    there is none. Loading it declares `support.OWN_RUNNER`, and the caller
    must put that back, or the next check under pytest gets our skip instead of
    his.
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
    """A foreign skip (`pytest.skip`) is a skip, not the death of the runner.

    The second half of the fix: even if a check calls `pytest.skip()` past
    `support.skip()`, the total must print. The value here is the STATE, not
    "did not fall": a failure and a skip are different numbers.
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
                # A broken runner does not catch a foreign skip and lets it out
                # -- that is exactly how it died. Caught here so that this
                # check goes red rather than the whole run.
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
    """KeyboardInterrupt goes out: swallow it and the run cannot be stopped."""
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
# SNAPSHOT COMPLETENESS: `replay.shape()` derives the required fingerprint
# shape by parsing the adapter's source. Parsing is sometimes powerless --
# fingerprint built by a comprehension, past a loop, handed over ready -- and
# that cost the instrument its face: the "fingerprint" branch did not enter the
# requirements AT ALL, so a snapshot with no fingerprint passed `books replay
# --check` with code 0, "values in the snapshot 51 of 51, missing 0" and the
# word VERIFIED beside it. The completeness check approved an incomplete
# snapshot exactly when it had failed itself.

def _adapter_with_underivable_fingerprint(tmp):
    """A snapshot writer whose shape tree-parsing will NOT derive.

    Real in build: a class with a declared `name` and a declared
    `fingerprint()`. Parsing finds not one key in it -- they are counted during
    the run.
    """
    path = os.path.join(tmp, "myocr.py")
    with open(path, "w", encoding="utf-8") as f:
        f.write("class MyOcr:\n"
                "    name = \"myocr\"\n\n"
                "    def fingerprint(self):\n"
                "        return {k: v for k, v in self._parts.items()}\n")
    return path


def test_shape_that_could_not_be_derived_is_loud_not_silent():
    """Failure to derive the shape is a value, not silent agreement.

    At least the fingerprint BRANCH itself is required: a snapshot without it
    must be incomplete. And the ignorance is named by a number -- `not_derived`
    -- else "all checked" and "as much as we could" are indistinguishable.
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
    """The directory with `run.json` -- what `replay.selfcheck` reads."""
    import json
    out = os.path.join(tmp, "выход")
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "run.json"), "w", encoding="utf-8") as f:
        json.dump(snap, f, ensure_ascii=False)
    return out


def test_derivable_shape_still_requires_every_value():
    """The other side: where the shape WAS derived, every value is required.

    Without this half the fix could be "done" by declaring any shape
    underivable -- the branch required, and nothing inside it.
    """
    from booksmith.run import replay

    tree = replay._parse(support.src_path("models/doclayout.py"))
    fn, cls = replay._fp_def(tree, "DocLayout")
    keys = replay._returned(fn, tree, cls)
    assert len(keys) > 10, (
        f"из `DocLayout.fingerprint()` выведено {len(keys)} величин — разбор "
        f"ослеп, и требование к отпечатку осыпалось до одной ветки")


# -------------------------------------------------------- .sh AND THE REGISTRY
# A promise nothing kept BEFORE this check. `models/paddleocr_vl/run.sh` says
# word for word: "a drift will be caught by `tests/test_knobs.py`, which
# compares the right-hand sides of `${X:-…}` with it [the registry]". No such
# comparison existed: no check opened a `.sh`, and `knobs.readers()` looks in
# shell only for the PRESENCE of `$NAME`. A guard existing as one line of prose
# is worse than none: it was cited in decisions.

_SH_OPEN = re.compile(r'\$\{([A-Z_][A-Z0-9_]*):-')


def _sh_scan(text):
    """Pairs (name, default) from `${NAME:-…}`, WITH BRACE COUNTING.

    A `[^}]*` regexp will not do: `run.sh` holds
    `PORT="${PORT_ARG:-${PORT:-8118}}"`, where it eats the outer one whole and
    never sees the inner `${PORT:-8118}`. The first draft missed exactly there
    -- a `PORT` swapped in a copy of the tree (9999 against 8118 in the
    registry) went unnoticed and the check declared itself sound.
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
    """Every `${NAME:-default}` in the scripts that ship to the rented card."""
    out = {}
    root = os.path.join(support.SRC, "models")
    for directory, _, files in os.walk(root):
        for f in sorted(files):
            if not f.endswith(".sh"):
                continue
            path = os.path.join(directory, f)
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
            # COMMENTS ARE DROPPED, and that is no detail. In `run.sh` the same
            # `${PORT:-8118}` stands a SECOND time, in the prose explaining the
            # rule. Comparing prose on a par with code, the guard would fall
            # from a comment edit, which changes no behaviour. Checked:
            # corrupting ONLY the example in the comment made the check fail.
            without_prose = "\n".join(
                l for l in text.split("\n") if not l.lstrip().startswith("#"))
            for name, default in _sh_scan(without_prose):
                # `${X:-…}` is an example out of a comment, not a variable.
                if name == "X":
                    continue
                out.setdefault(name, []).append(
                    (os.path.relpath(path, support.SRC), default))
    return out


def test_shell_defaults_agree_with_the_registry():
    """A `.sh` default equals the registry default -- or is admitted out loud.

    TWO CASES, AND ONE RULER WILL NOT DO. The registry DECLARED a default
    (non-empty): the shell must substitute the same, or the snapshot writes one
    thing while the card counts by another and only the bill shows it. The
    registry gives NO default (empty string): the owner of the value is the
    shell, and the registry entry must SAY so -- otherwise an empty default is
    indistinguishable from a forgotten one, the `VL_MODEL_DIR` disease whose
    catcher, says the `run/knobs.py` header, is restored by HALF.

    A name absent from the registry it does NOT catch and does not pretend to:
    that needs a list of lawful shell variables. There are EIGHT of them, not
    six as stood here: `ENVDIR`, `MODELS`, `HF_HOME`, `VL_REPO`, `SRV`,
    `PYTORCH_CUDA_ALLOC_CONF`, plus `DOTS_DIR` (the knob past the registry the
    `run/knobs.py` header writes about) and `PORT_ARG`, the positional argument
    of `run.sh`, whose own default is `${PORT:-8118}`.

    AND WHAT IT DOES NOT COMPARE THOUGH IT LOOKS AS IF IT DID: for a knob with
    an EMPTY registry default the `.sh` value is compared with nothing, only
    the admission in the description. `${VL_MODEL_DIR:-/models/vl}` swapped for
    `/models/xxx` passes silently, proved by mutation. It cannot be otherwise:
    the owner is declared to be the shell, and there is no second home.
    """
    registry = {k.name: k for k in knobs.KNOBS}
    found = _sh_defaults()

    # THE DENOMINATOR, WITHOUT WHICH THE CHECK IS GREEN ON NOTHING. Find no
    # `.sh` and `_sh_defaults()` returns empty, `troubles` stays empty, and
    # `assert not troubles` passes having compared NOT ONE name. Proved by
    # running it: with an empty `models` directory the check was green -- a
    # zero from misunderstanding against a zero from checking.
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
            elif "run.sh" not in k.what and "shell" not in k.what:
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
    """The snapshot is looked for in the root and in the kitchen.

    A DETECTION directory keeps `run.json` at the root, a BOOK directory in
    `assets/`, where the root holds one file, the book. The completeness check
    looked only at the root and answered "no snapshot at all" on a book with
    the snapshot one floor down, returning 1 -- while the builder promises word
    for word: "`books replay --check` must return 0 here too" -- a speaking
    step lying with a zero, the rule that made "chapters 0" read as "there are
    none".
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


def test_the_aging_knob_lists_exactly_the_profiles_that_exist():
    """A knob's description names its legal values, and they must be legal.

    `SYNTH_AGING` went on advertising the fourth profile under its old name
    after the rename to `decayed`, so the documented command raised `KeyError`
    -- `synth.AGING[profile]` is a plain lookup with no default. The
    description is not a comment: it is copied verbatim into every run
    snapshot, so the wrong value travels with the record of the run.
    """
    from booksmith import synth
    knob = [k for k in knobs.KNOBS if k.name == "SYNTH_AGING"][0]
    listed = knob.what.split(": ")[1].split("|")
    assert listed == list(synth.AGING), (
        f"the knob offers {listed}, `synth.AGING` accepts {list(synth.AGING)}")
