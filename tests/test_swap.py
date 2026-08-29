"""Замена блока разметкой второго уровня: чистые функции, проверяемые целиком.

`doc/swap.py` сам объявляет себя единственным слоем конвейера, который можно
проверить целиком, не потратив ни секунды счёта, — «и потому именно его надо
покрыть проверками раньше всех». Раньше всех и покрыт.

На этих четырёх функциях держится всё обещание двухуровневой схемы: замену
можно ПРОВЕРИТЬ, ОТКАТИТЬ и переделать другой моделью, не трогая книгу. Без
отката это не замена, а правка книги.

Порча тут тихая по построению. Разметку возвращает модель, она бывает какой
угодно — незакрытые теги, лишние `<`, битые сущности, — и ни один из этих
случаев не виден глазом в книге на пятьсот страниц. Видно будет одно: на
СЛЕДУЮЩЕЙ замене вылезет «открывающих 0, закрывающих 1» про чужой блок.
"""
from booksmith.doc import swap

A, B = "p0042-b17", "p0042-b18"


def doc(a_body="таблица картинкой", b_body="рисунок картинкой"):
    return ("<p>до</p>" + swap.wrap(A, a_body) + "<p>между</p>"
            + swap.wrap(B, b_body) + "<p>после</p>")


def test_wrap_and_get_are_inverse():
    assert swap.get(doc(), A) == "таблица картинкой"
    assert swap.get(doc(), B) == "рисунок картинкой"


def test_anchors_keep_document_order():
    """Порядок появления — он же порядок чтения, сортировать его нельзя."""
    d = ("<p/>" + swap.wrap("p0002-b9", "x") + swap.wrap("p0001-b3", "y")
         + swap.wrap("p0002-b1", "z"))
    assert swap.anchors(d) == ["p0002-b9", "p0001-b3", "p0002-b1"]


def test_swap_returns_what_it_removed_and_restore_puts_it_back():
    """Откат обязан вернуть документ ПОБАЙТОВО прежним."""
    before = doc()
    new, was = swap.swap(before, A, "<table><tr><td>1</td></tr></table>")
    assert was == "таблица картинкой"
    assert new != before
    assert swap.get(new, A) == "<table><tr><td>1</td></tr></table>"
    assert swap.restore(new, A, was) == before


def test_swap_leaves_the_neighbour_byte_for_byte():
    """Соседний блок не задет — на этом стоит «не трогая книгу»."""
    new, _ = swap.swap(doc(), A, "что угодно")
    assert swap.get(new, B) == "рисунок картинкой"
    assert new.count(swap.OPEN.format(B)) == 1
    assert new.count(swap.CLOSE.format(B)) == 1


def test_broken_markup_from_the_model_goes_in_as_is():
    """Разбора HTML тут нет нарочно: модель вернёт что вернёт.

    Незакрытый тег и голая `<` обязаны доехать побайтово — иначе первый же
    кривой ответ второго уровня разъехался бы по всей книге.
    """
    fragment = "<table><tr><td>a < b<td>2</table"
    new, _ = swap.swap(doc(), A, fragment)
    assert swap.get(new, A) == fragment
    assert swap.get(new, B) == "рисунок картинкой"


def test_missing_anchor_is_loud():
    try:
        swap.get(doc(), "p9999-b1")
    except swap.AnchorError as e:
        assert "открывающих 0" in str(e)
    else:
        raise AssertionError("замена на месте, которого нет, прошла молча")


def test_double_anchor_is_loud():
    """Столкновение якорей: сквозной `b17` на книге дал бы пятьсот одинаковых.

    «Возьму первую» тут значит переписать не тот блок и узнать об этом
    никогда.
    """
    d = doc() + swap.wrap(A, "он же на другой странице")
    try:
        swap.span(d, A)
    except swap.AnchorError as e:
        assert "открывающих 2" in str(e)
    else:
        raise AssertionError("две одинаковые метки приняты за одну")


def test_inverted_anchor_is_loud():
    d = "<p>" + swap.CLOSE.format(A) + "тело" + swap.OPEN.format(A) + "</p>"
    try:
        swap.span(d, A)
    except swap.AnchorError as e:
        assert "вывернут" in str(e)
    else:
        raise AssertionError("закрывающая метка раньше открывающей принята")


def test_crossed_anchors_are_loud():
    """Перекрёст: обе метки по одной, а границы зацеплены.

    Счёт «по одной» такое не ловит. `get(A)` отдавал тело с чужой открывающей
    меткой внутри, `swap(A, …)` стирал её вместе с телом, и беда всплывала на
    СЛЕДУЮЩЕЙ замене, когда книга уже наполовину переразмечена.
    """
    d = (swap.OPEN.format(A) + "1" + swap.OPEN.format(B) + "2"
         + swap.CLOSE.format(A) + "3" + swap.CLOSE.format(B))
    try:
        swap.span(d, A)
    except swap.AnchorError as e:
        assert A in str(e) and B in str(e), (
            f"жалоба не называет обоих участников перекрёста: {e}")
    else:
        raise AssertionError(
            "перекрёст меток принят: замена A уничтожила бы границу B, а "
            "вылезло бы это лишь на B")


def test_nested_anchors_are_not_a_crossing():
    """Вложение — не перекрёст, и путать их нельзя.

    Внутри тела A лежат ОБЕ метки B: границу соседа замена не рвёт, рвётся
    только сам сосед, и это видно сразу, а не через сотню страниц.
    """
    d = (swap.OPEN.format(A) + "до" + swap.wrap(B, "внутренний") + "после"
         + swap.CLOSE.format(A))
    assert swap.get(d, B) == "внутренний"
    assert swap.get(d, A) == "до" + swap.wrap(B, "внутренний") + "после"


def test_unterminated_mark_is_loud():
    """Оборванный комментарий не читается как «меток нет»."""
    try:
        swap.anchors("<p>текст<!--bs:p0001-b1 и всё")
    except swap.AnchorError as e:
        assert "не закрыта" in str(e)
    else:
        raise AssertionError("оборванная метка молча дала пустой список")
