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
