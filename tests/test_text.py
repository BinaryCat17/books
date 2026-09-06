"""Прибор ЧТЕНИЯ: последняя строка отчёта и разбор нулей.

ПОЧЕМУ ЭТОТ ФАЙЛ ПОЯВИЛСЯ. `text.report` не звался НИ ОДНОЙ проверкой и ни
одной пробой батареи — а это ровно та функция, которую читает человек. Цена
неохраняемости выяснилась в тот же день двумя способами сразу:

  * запись артефакта не несёт `WER` (в формуле слов не считают), а строка
    «худший блок» его печатала — одна неверная буква в одной формуле роняла
    `books text` целиком, `KeyError: 'WER'`. На платном прогоне это значит:
    деньги потрачены, ответы записаны, отчёта нет;
  * знаменатель последней строки считался по текстовым блокам, а числитель —
    по текстовым И артефактным, и на книге с формулами выходило «CER 0 на всех
    130 посчитанных из 104». Сторож «сверять было НЕЧЕГО» при этом не
    срабатывал никогда: молчащая модель снова получала «блоков с ошибкой нет».

Батарея порчи такое поймать не может по построению — она смотрит на ЧИСЛА, а
это про печать. Значит проверка.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from booksmith import text                                  # noqa: E402


def _pages(blocks, side=None):
    """Одна страница истины/ответа в схеме `Page`."""
    return {0: {"index": 0, "width": 100, "height": 100, "dpi": 144.0,
                "blocks": blocks,
                "meta": {"artifact_truth": side} if side else {}}}


def _text_block(i, content):
    return {"block_id": i, "box": [0, i * 10, 90, i * 10 + 8], "label": "text",
            "content": content, "kind": "text" if content else "none"}


def _formula_block(i, content):
    return {"block_id": i, "box": [0, i * 10, 90, i * 10 + 8],
            "label": "display_formula", "content": content,
            "kind": "latex" if content else "none"}


def _say(truth, answer):
    """Отчёт строками. Именно то, что увидит человек."""
    out = []
    text.report(text.measure_pages(truth, answer), log=out.append)
    return "\n".join(out)


# ------------------------------------------------------ последняя строка ---

def test_silence_is_not_reported_as_perfect_reading():
    """Модель промолчала на всех — и это НЕ «CER 0 на всех N»."""
    T = _pages([_text_block(0, "первый"), _text_block(1, "второй")])
    P = _pages([_text_block(0, None), _text_block(1, None)])
    s = _say(T, P)
    assert "сверять было НЕЧЕГО" in s
    # Утверждения «CER 0 на всех» быть не должно. Ищем именно УТВЕРЖДЕНИЕ:
    # сама поправляющая строка кончается цитатой «это НЕ „CER 0 на всех“», и
    # простое вхождение подстроки красит проверку на верном выводе.
    assert "блоков с ошибкой знаков нет" not in s


def test_perfect_reading_counts_only_text_in_the_text_line():
    """Знаменатель последней строки — текстовые блоки, и только они.

    Замер до починки: книга с 104 текстовыми блоками и 26 формулами печатала
    «CER 0 на всех 130 посчитанных из 104» — числитель по обоим разрядам,
    знаменатель по одному.
    """
    T = _pages([_text_block(0, "проза"), _formula_block(1, None)],
               side={"1": {"text": "x = 1"}})
    P = _pages([_text_block(0, "проза"), _formula_block(1, "x = 1")])
    s = _say(T, P)
    assert "блоков с ошибкой знаков нет: CER 0 на всех 1 посчитанных из 1" in s
    assert "блоков с ошибкой артефактов нет: CER 0 на всех 1 посчитанных из 1" in s


def test_one_wrong_letter_in_a_formula_does_not_crash():
    """Ошибка в формуле печатается, а не роняет прибор.

    Запись артефакта не несёт `WER`, и строка «худший блок» его печатала.
    """
    T = _pages([_text_block(0, "проза"), _formula_block(1, None)],
               side={"1": {"text": "x = 1"}})
    P = _pages([_text_block(0, "проза"), _formula_block(1, "z = 1")])
    s = _say(T, P)                      # не бросает — это и есть проверка
    assert "худший блок артефактов" in s
    assert "WER" not in s.split("худший блок артефактов")[1].split("\n")[0]


def test_silent_formulas_are_not_a_measured_one():
    """Молчание на ВСЕХ формулах — «сверять нечего», а не «CER 1.0»."""
    T = _pages([_text_block(0, "проза"), _formula_block(1, None)],
               side={"1": {"text": "x = 1"}})
    P = _pages([_text_block(0, "проза"), _formula_block(1, None)])
    s = _say(T, P)
    assert "ОТВЕТА НЕТ НИ НА ОДИН" in s
    assert "CER 1.0000" not in s


# ---------------------------------------------------------- разряды ------

def test_artefact_with_truth_is_not_a_bait():
    """У формулы истина ЕСТЬ: прочитать её — работа, а не выдумка."""
    T = _pages([_formula_block(0, None)], side={"0": {"text": "x = 1"}})
    P = _pages([_formula_block(0, "x = 1")])
    r = text.measure_pages(T, P)
    assert r["artifacts_with_truth"]["block_count"] == 1
    assert r["artifacts_with_truth"]["CER"] == 0.0
    assert r["baits"]["artifacts"] == 0


def test_artefact_without_truth_stays_a_bait():
    """А у рисунка истины нет: всякий текст в ответе — выдумка."""
    T = _pages([{"block_id": 0, "box": [0, 0, 90, 8], "label": "image",
                 "content": None, "kind": "none"}])
    P = _pages([{"block_id": 0, "box": [0, 0, 90, 8], "label": "image",
                 "content": "сочинил", "kind": "text"}])
    r = text.measure_pages(T, P)
    assert r["baits"]["artifacts"] == 1 and r["baits"]["read"] == 1
    assert r["artifacts_with_truth"]["block_count"] == 0


def test_invention_on_declared_emptiness_is_counted():
    """Истина артефакта — пустая строка, а модель написала: своя величина.

    В CER это не видно вовсе (делить не на что), и без счётчика выдумка на
    объявленной пустоте пропадала бы молча.
    """
    T = _pages([_formula_block(0, None)], side={"0": {"text": ""}})
    P = _pages([_formula_block(0, "сочинил четырнадцать")])
    r = text.measure_pages(T, P)
    assert r["artifacts_with_truth"]["invented_on_empty_truth"] == 1


def test_two_truths_on_one_artefact_are_loud():
    """И сетка, и знаки у одного блока — отказ вслух, а не тихий выбор."""
    T = _pages([_formula_block(0, None)],
               side={"0": {"text": "x = 1", "table": [["а", "б"]]}})
    P = _pages([_formula_block(0, "x = 1")])
    try:
        text.measure_pages(T, P)
    except text.TextError as e:
        assert "И сетка" in str(e) or "сетка" in str(e)
    else:
        raise AssertionError("две истины на одном блоке прошли молча")


# ------------------------------------------------------------- таблицы ---

def test_table_in_otsl_scores_like_the_same_table_in_html():
    """Один и тот же верный ответ двумя видами — одни и те же числа."""
    grid = [["А", "Б"], ["1", "2"]]
    T = _pages([{"block_id": 0, "box": [0, 0, 90, 8], "label": "table",
                 "content": None, "kind": "none"}],
               side={"0": {"table": grid}})
    as_html = ("<table><tr><td>А</td><td>Б</td></tr>"
               "<tr><td>1</td><td>2</td></tr></table>")
    as_otsl = "<fcel>А<fcel>Б<nl><fcel>1<fcel>2<nl>"
    got = []
    for body, kind in ((as_html, "html"), (as_otsl, "otsl")):
        P = _pages([{"block_id": 0, "box": [0, 0, 90, 8], "label": "table",
                     "content": body, "kind": kind}])
        b = text.measure_pages(T, P)["tables"]
        got.append((b["cells_matched"], b["given_as_text"], b["cer_cells"]))
    assert got[0] == got[1] == (4, 0, 0.0), got


def test_a_cell_with_angle_brackets_survives_the_round_trip():
    """Ячейка с `<` и `&` возвращается из HTML ТОЙ ЖЕ. Иначе прибор врёт.

    ЧЕМ ЭТО ОПЛАЧЕНО. `_grid_html` не экранировал, и круговой ход
    «сетка -> HTML -> сетка» терял содержимое: `a<b&c` приезжал обратно как
    `a`, потому что разборщик считал `<b&c` открывающим тегом. Батарея порчи
    делает порчу НАД СЕТКОЙ и подаёт метрике эту строку — значит ячейка
    усекалась ДО внесения порчи, и число относилось не к той строке, о
    которой батарея отчитывалась. Соседний `otsl.to_html` экранирует с
    первого дня; здесь жила вторая, разошедшаяся копия того же цикла.

    ЗАМЕР, КОТОРЫМ ЭТО ОБОСНОВЫВАЛОСЬ, БЫЛ НЕВЕРЕН. Здесь стояло «ни одна
    ячейка из 6812 прочитанных настоящей моделью блоков не содержала ни `<`,
    ни `&`; первая книга по химии это изменит». На деле книга в корпусе и
    ЕСТЬ книга по химии, и в ней 24 такие ячейки из 5726 (`< 3`, `<1,0`,
    `<28 …`). Ноль вышел потому, что ячейки я доставал регэкспом
    `<fcel>([^<]*)` — прибором с тем же дефектом, который чинил: он
    обрывается на `<`. Круговой довод.

    Правка от этого не отменяется, но её цена другая: ни одна из 24 ячеек
    НЕ портилась, потому что браузер считает `<` литералом, когда следом не
    буква. Опасно `<` перед буквой — такого в корпусе нет, и проверка стоит
    здесь ради первой же таблицы, где оно появится.
    """
    было = {(0, 0): "a<b & c", (0, 1): "простая",
            (1, 0): '"кавычки"', (1, 1): "5 > 3"}
    стало = text._html_grid(text._grid_html(было))
    assert стало == было, (
        f"круговой ход сетки потерял содержимое:\n  было  {было}\n"
        f"  стало {стало}\nЯчейка обязана экранироваться — иначе батарея "
        f"мерит не ту строку, о которой отчитывается")
