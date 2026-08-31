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
import importlib
import os
import shutil
import sys
import tempfile
from contextlib import contextmanager

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import support                                              # noqa: E402
from booksmith import metrics, policy                       # noqa: E402
from booksmith.doc import apply as ap                       # noqa: E402
from booksmith.doc import swap                              # noqa: E402
from booksmith.models import base as mbase                  # noqa: E402
from booksmith.models import docling_heron as dh            # noqa: E402
from booksmith.run import knobs                             # noqa: E402


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
        "models/yolox_layout.py")


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
        ("адаптер завёл значение мимо таблицы договора",
         lambda: sources("models/doclayout.py", '"наш, позиция в списке: "',
                         '"позиция в списке (ранга модель не даёт): "'),
         [("test_order_contract", "test_no_unknown_order_values")]),

        ("сторож перестал снимать регистр",
         lambda: attrs(mbase, ours_order=guard_case_sensitive),
         [("test_order_contract", "test_guard_ignores_case")]),

        ("адаптер вовсе не сказал, чей порядок",
         lambda: sources("models/yolox_layout.py",
                         '"порядок чтения": "наш, сверху вниз и слева направо",',
                         ""),
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

        ("живая ручка помечена долгом",
         lambda: attrs(knobs.KNOB["DOCLING_PIPELINE"], debt=True),
         [("test_knobs", "test_docling_pipeline_is_registered")]),
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
