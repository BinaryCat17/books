"""Обрыв ответа доезжает до книги, а форма невозможной таблицы называется.

ЗАЧЕМ ЭТОТ ФАЙЛ ЗАВЕДЁН, и это замер, а не опасение. `books read` считает
пять нулей порознь и называет их вслух: в слепке чтения «Технологии
огнеупоров» стоит «оборвано потолком: 14» и все четырнадцать якорей списком.
Дальше знание пропадало целиком — `grep` по дереву не находил ни `finish`, ни
«оборван» нигде за пределами `read/`. В книгу при этом вошли ВСЕ четырнадцать
(118 471 знак — 12.95 % всего прочитанного текста), и ни один не отличим
на вид от целого.

ПОЧЕМУ ПЯТИ СТОРОЖЕЙ `books apply` НЕ ХВАТИЛО. Оборванный кусок не несёт
чужих меток, не пуст, вид объявлен, набор якорей не меняет и незавершённого
комментария не содержит — то есть проходит все пятеро. Худший, `p0055-b11`,
на скане таблица 4x4, а в книге `<table>` с 2047 `<td>` в ОДНОЙ строке: одна
эта строка держит 36 % всех ячеек книги.

И ПОЧЕМУ СЧЁТЧИКИ РВАНОСТИ ЭТОГО НЕ ВИДЯТ. У `p0055-b11` они все чисты —
продолжений в никуда 0, строк разной длины 0, текст мимо тегов 0. Не потому,
что таблица цела, а потому, что в ответе нет ни одного `<nl>`: строк не с чем
сравнивать, продолжениям некуда деться. Ноль от непонимания, принятый за ноль
от проверки. Правило `torn_grid` смотрит поэтому не на рваность, а на ФОРМУ.
"""
import json
import os

from booksmith.doc import html as H


# ------------------------------------------------- форма таблицы ---

def test_torn_grid_catches_the_shape_no_tearing_counter_can_see():
    """Таблица в одну строку и в один столбец — названы, прочие молчат."""
    # Та самая `p0055-b11`: 2047 клеток в одной строке при чистой рваности.
    assert "2047" in (H.torn_grid({"rows": 1, "grid_cells": 2047}) or "")
    # И зеркальный случай — `p0166-b2` настоящей книги, 7 строк в один
    # столбец, `finish=stop`, все счётчики рваности чисты. Его не нашёл ни
    # один прибор проекта до этого правила.
    assert "7" in (H.torn_grid({"rows": 7, "grid_cells": 7}) or "")
    # Настоящая таблица книги (`p0005-b2`, «Рост производства…») — молчит.
    assert H.torn_grid({"rows": 9, "grid_cells": 63}) is None


def test_torn_grid_zero_from_absence_is_not_zero_from_checking():
    """Сетки нет — это НЕ «форма в порядке». Оба случая дают None, и это
    единственное место, где их путать можно: наверху они разведены полем
    «чтение наблюдалось», которое `None` при отсутствии `answers/`."""
    assert H.torn_grid(None) is None
    assert H.torn_grid({}) is None
    # Крошечная таблица не объявляется невозможной: 1x3 — законная шапка.
    assert H.torn_grid({"rows": 1, "grid_cells": 3}) is None
    # А 1x4 — уже нет, и граница названа числом, а не «на глаз».
    assert H.torn_grid({"rows": 1, "grid_cells": 4}) is not None
    # ТО ЖЕ С ДРУГОЙ СТОРОНЫ, и без этой пары порог столбца не держало ничто:
    # порча «rows > 3 -> rows > 1» проходила батарею незамеченной, потому что
    # ни одна проверка не подавала законный однослобцовый столбик.
    # Колонка из трёх клеток — законная (подписи строк без данных).
    assert H.torn_grid({"rows": 2, "grid_cells": 2}) is None
    assert H.torn_grid({"rows": 3, "grid_cells": 3}) is None
    # А из четырёх — уже нет.
    assert H.torn_grid({"rows": 4, "grid_cells": 4}) is not None


def test_torn_grid_falls_on_deliberately_broken_input():
    """Правило обязано уметь провалиться: подаём заведомо испорченное.

    Настоящая сетка книги, у которой отняли строки (упор в потолок обрывает
    ответ до первого `<nl>`), обязана перестать быть законной."""
    whole = {"rows": 9, "grid_cells": 63}
    assert H.torn_grid(whole) is None
    damaged = dict(whole, rows=1)
    assert H.torn_grid(damaged) is not None, (
        "таблица, у которой обрыв съел все переводы строк, объявлена "
        "законной — правило слепо ровно к тому, ради чего заведено")


# ------------------------------------------------ наблюдённое сбоку ---

def _answers(tmp, recs):
    os.makedirs(os.path.join(tmp, "answers"), exist_ok=True)
    with open(os.path.join(tmp, "answers", "p0001.json"), "w",
              encoding="utf-8") as f:
        json.dump({"page": 1, "answers": recs}, f, ensure_ascii=False)


def test_observed_carries_the_reason_the_block_is_bad(tmp_path=None):
    """`observed` достаёт из `answers/` причину остановки по якорю."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        _answers(tmp, [
            {"anchor": "p0001-b0", "text": "...", "outcome": "length",
             "error": None,
             "observed": {"prompt": "Table Recognition:",
                             "kind_promised": "otsl",
                             "otsl_grid": {"rows": 1, "grid_cells": 99}}},
            {"anchor": "p0001-b1", "text": "intact", "outcome": "stop",
             "error": None, "observed": {"prompt": "OCR:"}},
        ])
        o = H.observed(tmp)
        assert o["p0001-b0"]["outcome"] == "length"
        assert o["p0001-b1"]["outcome"] == "stop"
        assert H.torn_grid(o["p0001-b0"]["otsl_grid"])
        assert H.torn_grid(o["p0001-b1"].get("otsl_grid")) is None


def test_no_answers_is_silence_not_a_clean_bill():
    """Каталог без `answers/` даёт ПУСТО, и сборка обязана сказать это
    словами, а не напечатать «оборвано 0».

    Ровно та беда, из-за которой правило проекта разводит два нуля: «глав 0»
    означало «я их не узнал», а читалось как «глав в книге нет»."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        assert H.observed(tmp) == {}


def test_broken_answers_file_does_not_silently_erase_the_others():
    """Один нечитаемый файл `answers/` не уносит с собой соседние.

    Потерять наблюдённое молча — то же самое, что не собрать его вовсе, но
    выглядит как исправный прогон."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        _answers(tmp, [{"anchor": "p0001-b0", "outcome": "length",
                        "observed": {}}])
        with open(os.path.join(tmp, "answers", "p0002.json"), "w",
                  encoding="utf-8") as f:
            f.write("{это не json")
        o = H.observed(tmp)
        assert o["p0001-b0"]["outcome"] == "length"


# ------------------------------ вторая половина: замена в книге ---

def test_the_mark_survives_the_replacement():
    """Обёртка `books apply` НЕСЁТ пометку обрыва, а не снимает её.

    Замер, ради которого проверка заведена. Сборка помечает 14 оборванных
    блоков; `books apply` ставит на место четырёх из них свой `<div>` — и в
    книге оставалось 10 пометок из 14. Терялись ровно те четыре, что доехали
    до читателя разметкой: оборванная таблица, оборванная формула, оборванный
    график. Половина правила жила в `html.py` и была закреплена проверками, а
    половина в `apply.py` — и не была: снятие двух строк из `_wrap_fragment`
    не роняло ни одной из 217 проверок.
    """
    from booksmith.doc import apply as ap
    intact = ap._wrap_fragment("p1-b0", "<fcel>a<fcel>b<nl>", "otsl", "проба",
                            torn=False)
    torn = ap._wrap_fragment("p1-b0", "<fcel>a<fcel>b<nl>", "otsl", "проба",
                             torn=True)
    assert "data-truncated" not in intact, intact
    assert 'data-truncated="yes"' in torn, torn


def test_unknown_is_not_whole():
    """`torn=None` — «не спрашивали», и пометки «цел» отсюда не следует.

    Одиночная замена (`--anchor … --file …`) наблюдённого рядом не имеет.
    Молчание тут верно; соврать было бы легко — поставить пометку по
    умолчанию либо, наоборот, объявить блок целым.
    """
    from booksmith.doc import apply as ap
    nothing = ap._wrap_fragment("p1-b0", "<fcel>a<nl>", "otsl", "руками")
    assert "data-truncated" not in nothing, nothing


def test_from_read_asks_the_sidecar_for_the_reason():
    """`from_read` обязан брать признак обрыва из `answers/`, а не выдумывать.

    Проверяется по исходнику: без явной передачи `torn=` половина правила
    снова отвалится молча — так уже было.
    """
    import ast

    import support
    t = support.tree("doc/apply.py")
    fn = next(n for n in ast.walk(t)
              if isinstance(n, ast.FunctionDef) and n.name == "from_read")
    calls = [n for n in ast.walk(fn)
             if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Name) and n.func.id == "observed"]
    assert calls, (
        "`from_read` не зовёт `observed` — признак обрыва взять неоткуда, и "
        "пометка пропадёт у тех самых блоков, что доехали разметкой")
    passes = [n for n in ast.walk(fn)
                if isinstance(n, ast.Call)
                and isinstance(n.func, ast.Name) and n.func.id == "put_into"
                and any(k.arg == "torn" for k in n.keywords)]
    assert passes, (
        "`from_read` зовёт `put_into` без `torn=` — наблюдённое прочитано и "
        "выброшено, что хуже, чем не читать его вовсе")


def test_the_torn_field_tells_three_states_apart():
    """«Оборвано», «дочитано» и «не спрашивали» — три разных значения.

    Замер: из 6156 блоков книги 14 оборваны, 6073 дочитаны, а 69 (рисунки)
    не спрашивали вовсе — маршрут у них пуст с объявленной причиной. Поле
    печатало последним двум одно и то же `False`, то есть само сливало два
    нуля, против чего и заведено. Различает их пустое `чем кончилось`.
    """
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        _answers(tmp, [
            {"anchor": "p0001-b0", "outcome": "length",
             "observed": {}},
            {"anchor": "p0001-b1", "outcome": "stop", "observed": {}},
            # Не спрашивали: ответа нет, и «цел» отсюда не следует.
            {"anchor": "p0001-b2", "outcome": None, "observed": {}},
        ])
        o = H.observed(tmp)
        # Зовём ПРАВИЛО, а не повторяем его здесь: проверка, повторяющая
        # проверяемое, тавтологична и порчу пропускает. Так и вышло — порча
        # «не спрашивали считается дочитанным» прошла мимо первой редакции.
        state = {a: H.torn_of(v) for a, v in o.items()}
        assert state == {"p0001-b0": True, "p0001-b1": False,
                             "p0001-b2": None}, state
        # И отсутствие наблюдения — тоже «сказать нечем», а не «цел».
        assert H.torn_of(None) is None and H.torn_of({}) is None


# ------------------------- величины замены: их регрессию ловить нечем ---
#
# Приёмщик прошёлся по всем 225 проверкам семью порчами и показал, что новые
# счётчики закрыты ТОЛЬКО ПО ФОРМЕ: величина заведена, а сломай её — никто не
# покраснеет. Ровно то состояние, в котором «104 таблицы при colspan 0»
# прожили целый прогон. Ниже — стенд, на котором каждая из них умеет упасть.

def _bench(tmp, chunks, cut=()):
    """Книга на N блоков, каталог чтения и наблюдённое рядом."""
    import json as _j
    import os as _o
    from booksmith.doc import apply as ap
    from booksmith.doc import swap
    with open(_o.path.join(tmp, "book.html"), "w", encoding="utf-8") as f:
        f.write("<!doctype html><html><body>\n" + "\n".join(
            swap.wrap(f"p0000-b{i}", f'<figure id="p0000-b{i}">кар</figure>')
            for i in range(len(chunks))) + "\n</body></html>\n")
    _o.makedirs(_o.path.join(tmp, ap.ASSETS), exist_ok=True)
    with open(_o.path.join(tmp, ap.ASSETS, "blocks.json"), "w",
              encoding="utf-8") as f:
        _j.dump({f"p0000-b{i}": {"role": "artifact"}
                 for i in range(len(chunks))}, f)
    _o.makedirs(_o.path.join(tmp, "read", "pages"), exist_ok=True)
    with open(_o.path.join(tmp, "read", "pages", "0000.json"), "w",
              encoding="utf-8") as f:
        _j.dump({"index": 0, "blocks": [
            {"block_id": i, "kind": "otsl", "content": c}
            for i, c in enumerate(chunks)]}, f)
    _o.makedirs(_o.path.join(tmp, "read", "answers"), exist_ok=True)
    with open(_o.path.join(tmp, "read", "answers", "p0000.json"), "w",
              encoding="utf-8") as f:
        _j.dump({"page": 0, "answers": [
            {"anchor": f"p0000-b{i}",
             "outcome": ("length" if i in cut else "stop"),
             "observed": {}} for i in range(len(chunks))]}, f)


def test_bulk_counts_spans_declared_and_placed():
    """Слияния — ДВЕ величины, и расхождение между ними видно.

    Без них регрессия перевода обратно в повторы была бы невидима в журнале:
    ровно так «104 таблицы при colspan 0» и прожили целый прогон.
    """
    import tempfile
    from booksmith.doc import apply as ap
    with tempfile.TemporaryDirectory() as tmp:
        _bench(tmp, ["<fcel>ш<lcel><nl><fcel>1<fcel>2<nl>",     # 1 слияние
                     "<fcel>a<fcel>b<nl><fcel>1<fcel>2<nl>",    # без слияний
                     # НЕПРЯМОУГОЛЬНОЕ: объявлено 1, а встать не может —
                     # без этого случая числа совпадают, и приравнять их
                     # можно было бы незаметно.
                     "<fcel>ш<lcel><nl><fcel>л<ucel><nl>"])
        t = ap.from_read(tmp, os.path.join(tmp, "read"), log=lambda *_: None)
        assert t["merges_declared"] == 2, t
        assert t["merges_in_book"] == 1, t
        assert t["tables_with_merges"] == 2, t
        assert t["merges_declared"] != t["merges_in_book"], (
            "объявленное и вставшее совпали — расхождение, ради которого "
            "заведены оба числа, стало ненаблюдаемым")


def test_bulk_counts_the_impossible_shape_of_the_book_not_of_the_run():
    """Форма считается по КНИГЕ: повторный прогон печатает то же число.

    Счёт дважды переезжал и дважды врал — то среди вновь поставленных (на
    собранной книге выходил ноль при двух невозможных таблицах), то в начале
    витка (считал блоки, которые сторожа отказались ставить).
    """
    import tempfile
    from booksmith.doc import apply as ap
    with tempfile.TemporaryDirectory() as tmp:
        _bench(tmp, ["<fcel>a<fcel>b<fcel>c<fcel>d<fcel>e<nl>",  # 1x5 — нельзя
                     "<fcel>a<fcel>b<nl><fcel>1<fcel>2<nl>"])
        first = ap.from_read(tmp, os.path.join(tmp, "read"),
                             log=lambda *_: None)
        assert first["impossible_table_shape"] == 1, first
        again = ap.from_read(tmp, os.path.join(tmp, "read"),
                             log=lambda *_: None)
        assert again["placed"] == 0 and again["already_placed"] == 2, again
        assert again["impossible_table_shape"] == 1, (
            "на повторном прогоне число обнулилось — значит оно про работу "
            "запуска, а не про книгу, и «невозможна у 0» читается как "
            "«таких нет»")


def test_bulk_marks_the_torn_block_in_the_book():
    """Обрыв доезжает до книги и через пакетную замену тоже."""
    import tempfile
    from booksmith.doc import apply as ap
    with tempfile.TemporaryDirectory() as tmp:
        _bench(tmp, ["<fcel>a<fcel>b<nl><fcel>1<fcel>2<nl>",
                     "<fcel>c<fcel>d<nl><fcel>3<fcel>4<nl>"], cut={1})
        ap.from_read(tmp, os.path.join(tmp, "read"), log=lambda *_: None)
        book = open(os.path.join(tmp, "book.html"), encoding="utf-8").read()
        assert book.count('data-truncated="yes"') == 1, book
        # И помечен ИМЕННО оборванный, а не первый попавшийся.
        i = book.index("p0000-b1")
        assert 'data-truncated="yes"' in book[i:i + 200], book[i:i + 200]


def test_bulk_names_the_rewrap_apart_from_new_work():
    """«Переобёрнуто» отделено от «поставлено».

    Смена НАШЕЙ обёртки — настоящая замена и в стопку отката ложится, но
    работой не является: байты модели те же. Сверяется sha ОТВЕТА МОДЕЛИ
    последней ступени, а не готовое тело — тело различается ровно обёрткой.
    """
    import tempfile
    from booksmith.doc import apply as ap
    with tempfile.TemporaryDirectory() as tmp:
        _bench(tmp, ["<fcel>a<fcel>b<nl><fcel>1<fcel>2<nl>"])
        t1 = ap.from_read(tmp, os.path.join(tmp, "read"), log=lambda *_: None)
        assert t1["placed"] == 1 and t1["rewrapped"] == 0, (
            "первая замена — настоящая работа, а не переобёртка")
        # ПЕРЕОБЁРТКА НАСТОЯЩАЯ: байты модели те же, обёртка другая. Так
        # выглядит книга, собранная прежней редакцией кода, после нового
        # `apply`: на «Технологии огнеупоров» это 63 блока из 412.
        was = ap._wrap_fragment

        def other_wrapper(anchor, fragment, kind, source, role="unknown",
                           torn=None):
            return was(anchor, fragment, kind, source, role=role,
                        torn=torn).replace("<div ", '<div data-проба="1" ', 1)

        ap._wrap_fragment = other_wrapper
        try:
            t2 = ap.from_read(tmp, os.path.join(tmp, "read"),
                              log=lambda *_: None)
        finally:
            ap._wrap_fragment = was
        assert t2["placed"] == 1, t2
        assert t2["rewrapped"] == 1, (
            "смена НАШЕЙ обёртки записана как новая работа — «поставлено» "
            f"в журнале означало бы работу, которой не было: {t2}")
        # А третий прогон прежней обёрткой — снова настоящая работа, потому
        # что тело опять другое; но байты модели те же, значит переобёртка.
        t3 = ap.from_read(tmp, os.path.join(tmp, "read"), log=lambda *_: None)
        assert t3["rewrapped"] == t3["placed"] == 1, t3
        # СВЕРЯЕТСЯ ПОСЛЕДНЯЯ СТУПЕНЬ СТОПКИ, А НЕ ПЕРВАЯ. Кто-то поправил
        # блок руками другой разметкой — вернуть на его место ответ модели
        # это РАБОТА, а не переобёртка, хотя в первой ступени стопки лежат те
        # же байты. Без этого случая обе сверки дают один ответ, и подмена
        # `[-1]` на `[0]` проходит незамеченной.
        ap.put(tmp, "p0000-b0", "<fcel>руками<nl>", kind="otsl",
               source="человек", log=lambda *_: None)
        t4 = ap.from_read(tmp, os.path.join(tmp, "read"), log=lambda *_: None)
        assert t4["placed"] == 1, t4
        assert t4["rewrapped"] == 0, (
            "возврат ответа модели поверх ручной правки записан как "
            f"переобёртка — сверяется первая ступень стопки, а не последняя: {t4}")


def test_a_refused_block_is_not_counted_as_being_in_the_book():
    """Блок, который сторожа не пустили, в числах КНИГИ не появляется.

    Счёт формы однажды уже стоял до сторожей и говорил о книге то, чего в
    ней нет. Отказ здесь настоящий: кусок несёт чужую метку блока, и её
    ловит `_check_fragment`.
    """
    import tempfile
    from booksmith.doc import apply as ap
    with tempfile.TemporaryDirectory() as tmp:
        _bench(tmp, ["<fcel>a<fcel>b<nl><fcel>1<fcel>2<nl>",
                     # 1x5 — форма невозможна, И кусок будет отвергнут.
                     "<fcel>a<fcel>b<fcel>c<fcel>d<fcel>e<nl>"
                     "<!--bs:p0000-b9-->"])
        t = ap.from_read(tmp, os.path.join(tmp, "read"), log=lambda *_: None)
        assert t["refused"] == 1, t
        assert t["impossible_table_shape"] == 0, (
            "отказанный блок посчитан среди блоков книги — а его в книге "
            f"нет: {t}")


def test_the_caption_names_which_zero_it_was():
    """Подпись у пустого блока называет ПРИЧИНУ, а не «не прочитан».

    Замер: у `p0024-b23` (полоса тени переплёта, 12x408 px) в `answers/`
    стоит `чем кончилось: stop`, `отказ: null`, текст пустой — модель
    ОТВЕТИЛА ПУСТЫМ. Книга говорила «не прочитан», что читается как «мы его
    не читали». Пять нулей `books read` сводились в один, и говорящий из них
    врал.
    """
    stayed_silent = H.why_empty({"outcome": "stop", "error": None})
    not_asked = H.why_empty({"outcome": None, "error": None})
    refusal = H.why_empty({"outcome": None, "error": "таймаут"})
    truncated = H.why_empty({"outcome": "length", "error": None})
    nothing_to = H.why_empty(None)
    all = [stayed_silent, not_asked, refusal, truncated, nothing_to]
    assert len(set(all)) == 5, (
        f"два разных нуля названы одинаково: {all}")
    assert "промолчала" in stayed_silent
    assert "не спрашивали" in not_asked
    assert "таймаут" in refusal
