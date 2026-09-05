"""Замена блока в готовой КНИГЕ: файлы, журнал, откат.

`test_swap.py` стережёт чистые строки; здесь начинаются файлы, и вместе с
ними — единственное, ради чего вся двухуровневая схема затевалась: «замену
можно проверить, откатить и переделать другой моделью, не трогая книгу».

Обещание держится ровно на трёх вещах, и каждая тут проверена:
  * снятое СОХРАНЕНО, иначе откатывать нечем;
  * стопка, а не последнее значение: две замены подряд откатываются по одной,
    иначе среднее состояние пропадает молча;
  * после отката книга совпадает с исходной ПОБАЙТОВО — «почти совпадает»
    здесь ничего не значит, потому что разницу в один символ на пятистах
    страницах не увидит никто.
"""
import json
import os
import tempfile

from booksmith.doc import apply as ap
from booksmith.doc import swap

A, B = "p0042-b17", "p0042-b18"
BOOK = ("<!doctype html><html><body>\n<p>до</p>"
        + swap.wrap(A, '<figure id="p0042-b17">картинка таблицы</figure>')
        + "<p>между</p>"
        + swap.wrap(B, '<figure id="p0042-b18">картинка рисунка</figure>')
        + "<p>после</p>\n</body></html>\n")


def book(tmp):
    p = os.path.join(tmp, "book.html")
    with open(p, "w", encoding="utf-8") as f:
        f.write(BOOK)
    return p


def test_put_then_undo_restores_the_book_byte_for_byte():
    with tempfile.TemporaryDirectory() as tmp:
        book(tmp)
        ap.put(tmp, A, "<table><tr><td>1</td></tr></table>", log=lambda *_: None)
        after_put = open(os.path.join(tmp, "book.html"), encoding="utf-8").read()
        assert after_put != BOOK, "замена не изменила книгу — ставить нечего"
        ap.undo(tmp, A, log=lambda *_: None)
        assert open(os.path.join(tmp, "book.html"), encoding="utf-8").read() == BOOK, (
            "откат вернул НЕ ту книгу. Разницу в один символ на пятистах "
            "страницах не увидит никто, поэтому сверка только побайтовая")


def test_stack_unwinds_in_reverse_order():
    """Две замены подряд — две ступени отката, а не одна.

    Так и работает второй уровень: модель ответила, ответ не понравился,
    переделали другой моделью. Плоское поле «что было» потеряло бы среднее
    состояние молча.
    """
    with tempfile.TemporaryDirectory() as tmp:
        book(tmp)
        ap.put(tmp, A, "<table>первая</table>", source="модель-1", log=lambda *_: None)
        ap.put(tmp, A, "<table>вторая</table>", source="модель-2", log=lambda *_: None)
        ap.undo(tmp, A, log=lambda *_: None)
        mid = swap.get(open(os.path.join(tmp, "book.html"), encoding="utf-8").read(), A)
        assert "первая" in mid, f"после одного отката ожидалась первая замена, а стоит {mid[:60]!r}"
        ap.undo(tmp, A, log=lambda *_: None)
        assert open(os.path.join(tmp, "book.html"), encoding="utf-8").read() == BOOK


def test_neighbour_is_untouched():
    with tempfile.TemporaryDirectory() as tmp:
        book(tmp)
        ap.put(tmp, A, "<table>новое</table>", log=lambda *_: None)
        html = open(os.path.join(tmp, "book.html"), encoding="utf-8").read()
        assert swap.get(html, B) == '<figure id="p0042-b18">картинка рисунка</figure>'
        assert swap.anchors(html) == [A, B], "набор якорей книги изменился"


def test_fragment_with_marks_is_refused_by_the_fragment_check():
    """Метка внутри вставляемого куска — призрачный якорь.

    Беда вылезла бы не здесь, а на СЛЕДУЮЩЕЙ замене, сообщением «открывающих
    2» про чужой блок, когда книга уже наполовину переразмечена.

    Сторожей на это ДВА, и проверка нарочно требует ПЕРВОГО. Второй — сверка
    набора якорей после замены — поймал бы тот же кусок, и потому подмена
    первого сторожа заглушкой проходила батарею незамеченной: проверка
    краснела от чужой заслуги. Ловить надо в источнике, до того как книга
    вообще прочитана: только там видно, что дело в КУСКЕ, а не в том, что
    «замена изменила набор якорей», — разбираться со вторым сообщением
    пришлось бы дольше.
    """
    with tempfile.TemporaryDirectory() as tmp:
        book(tmp)
        try:
            ap.put(tmp, A, swap.wrap("p0001-b1", "чужое"), log=lambda *_: None)
        except ap.SwapError as e:
            assert "призрачными якорями" in str(e), (
                f"кусок отвергнут, но НЕ проверкой куска: {str(e)[:120]!r}")
        else:
            raise AssertionError("кусок с чужой меткой принят молча")
        assert open(os.path.join(tmp, "book.html"), encoding="utf-8").read() == BOOK


def test_empty_fragment_is_refused():
    """Пустая замена стирает блок, и по виду это «модель промолчала»."""
    with tempfile.TemporaryDirectory() as tmp:
        book(tmp)
        for empty in ("", "   \n"):
            try:
                ap.put(tmp, A, empty, log=lambda *_: None)
            except ap.SwapError:
                pass
            else:
                raise AssertionError(f"пустой кусок {empty!r} принят молча")
        assert open(os.path.join(tmp, "book.html"), encoding="utf-8").read() == BOOK


def test_unknown_kind_is_refused():
    with tempfile.TemporaryDirectory() as tmp:
        book(tmp)
        try:
            ap.put(tmp, A, "<table/>", kind="markdown", log=lambda *_: None)
        except ap.SwapError as e:
            assert "markdown" in str(e)
        else:
            raise AssertionError("незаявленный вид принят молча")


def test_undo_without_a_swap_is_loud_and_distinct():
    """«Не заменяли» и «откат не удался» — разные беды, и разные сообщения."""
    with tempfile.TemporaryDirectory() as tmp:
        book(tmp)
        try:
            ap.undo(tmp, A, log=lambda *_: None)
        except ap.SwapError as e:
            assert "ни разу не заменяли" in str(e)
        else:
            raise AssertionError("откат без замены прошёл молча")


def test_edit_outside_the_journal_blocks_undo():
    """Книгу правили руками — слепой откат затёр бы эту правку.

    «Откат» звучит безопасно, и именно поэтому проверка нужна: без неё
    команда молча уничтожает чужую работу.
    """
    with tempfile.TemporaryDirectory() as tmp:
        p = book(tmp)
        ap.put(tmp, A, "<table>ответ</table>", log=lambda *_: None)
        h = open(p, encoding="utf-8").read()
        with open(p, "w", encoding="utf-8") as f:
            f.write(h.replace("ответ", "правка руками"))
        try:
            ap.undo(tmp, A, log=lambda *_: None)
        except ap.SwapError as e:
            assert "мимо журнала" in str(e)
        else:
            raise AssertionError("откат затёр правку, сделанную мимо журнала")


def test_journal_keeps_what_was_taken():
    with tempfile.TemporaryDirectory() as tmp:
        book(tmp)
        ap.put(tmp, A, "<table>x</table>", source="проба", log=lambda *_: None)
        j = json.load(open(os.path.join(tmp, ap.JOURNAL), encoding="utf-8"))
        rec = j["замены"][A][-1]
        assert rec["снято"] == '<figure id="p0042-b17">картинка таблицы</figure>', (
            "журнал не сохранил снятое — откатывать будет нечем")
        assert rec["чем"] == "проба" and rec["вид"] == "html"


def test_status_tells_three_zeroes_apart():
    with tempfile.TemporaryDirectory() as tmp:
        book(tmp)
        said = []
        r = ap.status(tmp, log=said.append)
        assert r["якорей"] == 2 and r["всего замен"] == 0
        assert any("ещё не ходил" in s for s in said), (
            "«замен нет» и «книга пуста» напечатаны одинаково — это разные нули")

def test_unterminated_mark_is_caught_by_the_anchor_guard():
    """Незакрытая метка проходит проверку КУСКА и ловится сверкой ЯКОРЕЙ.

    Второй сторож существует ровно ради этого случая: полных меток в куске
    нет, `_check_fragment` его пропускает, а `swap.anchors` находит
    закрывающий `-->` дальше по книге и рождает якорь-мусор. Проверка требует
    ИМЕННО второго сторожа — иначе, сними его, она бы краснела от первого.
    """
    with tempfile.TemporaryDirectory() as tmp:
        book(tmp)
        try:
            ap.put(tmp, A, "<p>текст <!--bs:p0001-b9 внутри</p>",
                   log=lambda *_: None)
        except ap.SwapError as e:
            assert "изменила набор якорей" in str(e), (
                f"отвергнуто, но НЕ сверкой якорей: {str(e)[:120]!r}")
        else:
            raise AssertionError("незакрытая метка принята молча")
        assert open(os.path.join(tmp, "book.html"), encoding="utf-8").read() == BOOK


def test_unclosed_comment_is_caught_by_its_own_guard():
    """Незавершённый комментарий съедает закрывающую метку блока.

    ПЯТЫЙ сторож, и заведён он потому, что четыре прежних пропускали эту беду
    все до одного: меток блоков в куске нет, кусок не пуст, вид объявлен, а
    набор якорей НЕ МЕНЯЕТСЯ — `swap.anchors` ищет `<!--bs:`, и голый `<!--`
    ему не якорь. Замер до починки на книге из 26 блоков: команда отвечала
    «поставлено 154, снято 175, якорей 26», а по ВИДИМОЙ разметке (после того
    как браузер съест комментарии) выходило div открыто 0 -> 1, закрыто
    0 -> 0, figure 26 -> 25 — остаток книги внутри незакрытого div.

    Проверка требует ИМЕННО этого сторожа: сверка якорей здесь молчит по
    построению, и красноты от чужой заслуги тут быть не может.
    """
    with tempfile.TemporaryDirectory() as tmp:
        book(tmp)
        try:
            ap.put(tmp, A, "<table><tr><td>1</td></tr></table>"
                           "<!-- дальше не дописала", log=lambda *_: None)
        except ap.SwapError as e:
            assert "комментарий открыт и не закрыт" in str(e), (
                f"отвергнуто, но НЕ сторожем комментариев: {str(e)[:120]!r}")
        else:
            raise AssertionError("незавершённый комментарий принят молча")
        assert open(os.path.join(tmp, "book.html"), encoding="utf-8").read() == BOOK


def test_a_closed_comment_is_not_refused():
    """Сторож обязан уметь и НЕ срабатывать: закрытый комментарий законен.

    Без этой половины проверка зелена от запрета всего подряд, а второй
    уровень вправе вернуть разметку с комментарием внутри.
    """
    with tempfile.TemporaryDirectory() as tmp:
        book(tmp)
        ap.put(tmp, A, "<table><!-- строка итогов --><tr><td>1</td></tr></table>",
               log=lambda *_: None)
        h = open(os.path.join(tmp, "book.html"), encoding="utf-8").read()
        assert "<!-- строка итогов -->" in h, "законный комментарий не доехал"
        # И экранированные виды не получают ложного отказа: `render` для
        # `text`/`latex`/`otsl` превращает `<` в `&lt;`, комментария там нет.
        ap.put(tmp, B, "итог <!-- это текст, а не комментарий", kind="text",
               log=lambda *_: None)


def test_a_broken_journal_is_not_an_empty_journal():
    """Нечитаемый журнал обязан остановить работу, а не притвориться пустым.

    Соблазн вернуть `{"замены": {}}` стоил бы всей книги: следующая же замена
    записала бы поверх огрызка одну свою запись, и стопка отката ВСЕХ прежних
    замен исчезла бы молча. Проверяем и то, что огрызок остался на диске
    нетронутым: чинить его будут руками.
    """
    with tempfile.TemporaryDirectory() as tmp:
        book(tmp)
        ap.put(tmp, A, "<table>первая</table>", log=lambda *_: None)
        p = os.path.join(tmp, ap.JOURNAL)
        whole = open(p, encoding="utf-8").read()
        with open(p, "w", encoding="utf-8") as f:
            f.write(whole[:len(whole) // 2])          # обрыв записи
        stump = open(p, encoding="utf-8").read()
        try:
            ap.put(tmp, B, "<table>вторая</table>", log=lambda *_: None)
        except ap.SwapError as e:
            assert "не читается как json" in str(e), (
                f"отвергнуто, но не по причине нечитаемого журнала: {str(e)[:120]!r}")
        else:
            raise AssertionError(
                "замена по нечитаемому журналу прошла — стопка отката всей "
                "книги затёрта молча")
        assert open(p, encoding="utf-8").read() == stump, (
            "огрызок журнала переписан, а в нём единственный след прежних замен")


def test_journal_is_written_atomically():
    """Обрыв записи журнала не смеет стирать стопку отката всей книги.

    `open(p, "w")` обрезает старый файл ПЕРВЫМ делом, и всё, что случится
    дальше, оставляет на его месте огрызок. Замер на журнале в три замены
    (2101 байт): прежним способом на диске оставалось 1076 байт, не читаемых
    как json; нынешним журнал цел, а огрызок уходит в `swaps.json.tmp`.
    """
    import json as _json

    class Boom(RuntimeError):
        pass

    with tempfile.TemporaryDirectory() as tmp:
        book(tmp)
        for i in range(3):
            ap.put(tmp, A, f"<table>вариант {i}</table>", log=lambda *_: None)
        p = os.path.join(tmp, ap.JOURNAL)
        whole = open(p, encoding="utf-8").read()

        def half(obj, f, **kw):
            s = _json.dumps(obj, ensure_ascii=False, indent=1)
            f.write(s[:len(s) // 2])
            raise Boom("обрыв записи посередине")

        j = ap.load_journal(tmp)
        j["замены"]["p9999-b9"] = [{"мусор": "x"}]
        real, _json.dump = _json.dump, half
        try:
            ap.save_journal(tmp, j)
        except Boom:
            pass
        else:
            raise AssertionError("подмена не сработала — замер ничего не мерил")
        finally:
            _json.dump = real
        assert open(p, encoding="utf-8").read() == whole, (
            "оборванная запись затёрла журнал: стопка отката всей книги "
            "потеряна")
        assert len(ap.load_journal(tmp)["замены"][A]) == 3, "стопка укоротилась"


def _bulk_stand(tmp, blocks=6):
    """Книга на N блоков и каталог чтения к ней."""
    with open(os.path.join(tmp, "book.html"), "w", encoding="utf-8") as f:
        f.write("<!doctype html><html><body>\n" + "\n".join(
            swap.wrap(f"p0000-b{i}",
                      f'<figure id="p0000-b{i}">картинка</figure>')
            for i in range(blocks)) + "\n</body></html>\n")
    with open(os.path.join(tmp, "blocks.json"), "w", encoding="utf-8") as f:
        json.dump({f"p0000-b{i}": {"роль": "артефакт"} for i in range(blocks)}, f)
    os.makedirs(os.path.join(tmp, "read", "pages"))
    with open(os.path.join(tmp, "read", "pages", "0000.json"), "w",
              encoding="utf-8") as f:
        json.dump({"index": 0, "blocks": [
            {"block_id": i, "kind": "html",
             "content": f"<table><tr><td>{i}</td></tr></table>"}
            for i in range(blocks)]}, f)


def test_bulk_reads_the_book_once_not_once_per_block():
    """Пакетная замена читает книгу ОДИН раз, а не на каждый блок.

    Чем оплачено: `from_read` звал `put` на каждую замену, а тот перечитывал
    книгу целиком и дважды разбирал в ней ВСЕ якоря; `block_role` вдобавок
    перечитывал `blocks.json` на каждый блок. Замер на «Технологии
    огнеупоров» (2.3 МБ, 6156 блоков, 412 замен): 363 секунды против 5 после
    починки, несколько гигабайт чтения. Тела книг при этом совпали побайтово,
    журнал тоже — 412 якорей с теми же хэшами, — значит ускорение ничего не
    изменило по существу.

    Считаются ОТКРЫТИЯ ФАЙЛОВ, а не время: время меряет машину, а открытия —
    устройство. Умеет провалиться: верните `put` внутрь цикла.
    """
    import builtins

    with tempfile.TemporaryDirectory() as tmp:
        _bulk_stand(tmp, blocks=6)
        считано = {"book": 0, "blocks": 0}
        было = builtins.open

        def счётчик(f, *a, **kw):
            имя = os.path.basename(str(f))
            mode = (a[0] if a else kw.get("mode", "r"))
            if "r" in mode and "w" not in mode:
                if имя == "book.html":
                    считано["book"] += 1
                elif имя == "blocks.json":
                    считано["blocks"] += 1
            return было(f, *a, **kw)

        builtins.open = счётчик
        try:
            res = ap.from_read(tmp, os.path.join(tmp, "read"),
                               log=lambda *_: None)
        finally:
            builtins.open = было

    assert res["поставлено"] == 6, f"поставлено {res['поставлено']} из 6"
    assert считано["book"] == 1, (
        f"книга прочитана {считано['book']} раз на 6 замен — правило снова "
        f"слито с вводом-выводом, и на шести тысячах блоков это шесть минут")
    assert считано["blocks"] <= 1, (
        f"blocks.json прочитан {считано['blocks']} раз — разряды берутся по "
        f"одному вместо одного чтения на всю книгу")


def test_bulk_and_single_put_agree_block_for_block():
    """Пакетная и одиночная замена дают ОДНУ И ТУ ЖЕ книгу.

    Ускорение обязано быть только ускорением. Проверяется тем же способом,
    каким проверена настоящая книга: тела сравниваются побайтово.
    """
    with tempfile.TemporaryDirectory() as t1, tempfile.TemporaryDirectory() as t2:
        _bulk_stand(t1)
        _bulk_stand(t2)
        ap.from_read(t1, os.path.join(t1, "read"), log=lambda *_: None)
        for i in range(6):
            ap.put(t2, f"p0000-b{i}",
                   f"<table><tr><td>{i}</td></tr></table>",
                   source="read", log=lambda *_: None)
        a = open(os.path.join(t1, "book.html"), encoding="utf-8").read()
        b = open(os.path.join(t2, "book.html"), encoding="utf-8").read()
    assert a == b, "пакетная и одиночная замена дали РАЗНЫЕ книги"
