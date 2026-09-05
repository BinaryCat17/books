"""Второй уровень: чтение блоков моделью — весь путь, без единого цента.

Проверяется НАША половина: маршруты промтов, доставка, разбор ответа, сборка
страниц, пять разных нулей и слепок. Модель подменяется `fake_vlm.FakeVlm` —
OpenAI-совместимым адресом, отвечающим по указке; он не читает картинку и не
притворяется, что читает.

ПОЧЕМУ ЭТО НАПИСАНО ДО ПЕРВОГО ПЛАТНОГО ПРОГОНА. Порядок работ в проекте
обратный привычному: сперва стенд и прибор, потом модель. Прежний второй
уровень отлаживался на арендованной карте — тринадцать запусков, $0.52, из них
полезных два, и все ловушки оказались нашими, ни одной модельной.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from fake_vlm import FakeVlm                                # noqa: E402

from booksmith import otsl                                  # noqa: E402
from booksmith.models.base import Block, Page               # noqa: E402
from booksmith.read import Ask, Route                       # noqa: E402
from booksmith.read import http as vhttp                    # noqa: E402
from booksmith.read import run as vrun                      # noqa: E402
from booksmith.models.paddleocr_vl.reader import PaddleOcrVl  # noqa: E402


# ------------------------------------------------------------ маршруты ---

def test_every_label_of_every_dictionary_has_a_route():
    """Ярлык без маршрута роняет прогон ДО первого цента.

    Умолчания «чего не знаю — спрошу OCR:» нет нарочно: словарь ярлыков СВОЙ
    у каждого детектора, и двадцать шестой класс новых весов уехал бы не тем
    промтом, а его ответ записался бы чтением.
    """
    from booksmith import policy
    for name, d in policy.POLICIES.items():
        PaddleOcrVl(name).cover(d.keys())          # бросит, если дыра


def test_unknown_label_is_loud():
    r = PaddleOcrVl("PP-DocLayoutV2")
    try:
        r.cover(["table", "чего-такого-нет"])
    except ValueError as e:
        assert "чего-такого-нет" in str(e)
    else:
        raise AssertionError("ярлык без маршрута прошёл молча")


def test_kind_comes_from_the_prompt_not_from_the_answer():
    """Вид объявляет ПРОМТ. Спросили таблицу — вид `otsl`, что бы ни пришло."""
    r = PaddleOcrVl("PP-DocLayoutV2").routes()
    assert r["table"].kind == "otsl" and r["table"].prompt == "Table Recognition:"
    assert r["display_formula"].kind == "latex"
    assert r["text"].kind == "text" and r["text"].prompt == "OCR:"


def test_silence_carries_a_reason():
    """«Не спрашиваем» — значение с причиной, а не забытый ярлык."""
    r = PaddleOcrVl("PP-DocLayoutV2").routes()
    for lab in ("image", "header_image", "footer_image"):
        assert not r[lab].asked()
        assert r[lab].why, f"{lab} молчит без причины"


def test_route_with_unknown_kind_is_loud():
    try:
        Route("OCR:", "маркдаун").check("text")
    except ValueError as e:
        assert "не объявлен" in str(e)
    else:
        raise AssertionError("вид мимо KINDS прошёл молча")


def test_declared_kinds_agree_with_the_book():
    """Виды чтеца — те же имена, что принимает `books apply`."""
    from booksmith.doc.apply import KINDS
    for name in ("PP-DocLayoutV2", "Docling", "DocLayNet"):
        for rt in PaddleOcrVl(name).routes().values():
            if rt.asked():
                assert rt.kind in KINDS, f"вид {rt.kind} книге неизвестен"


# ------------------------------------------------------------ транспорт ---

def _t(url, model="PaddleOCR-VL-1.6-0.9B"):
    os.environ["VLM_ENDPOINT"] = url
    os.environ["MODEL_NAME"] = model
    return vhttp.Http()


def test_transport_asks_who_is_answering():
    """Проверка спрашивает не «жив ли», а «как тебя зовут».

    Оплачено первым уровнем: `curl /v1/models` отвечала СИРОТА прошлого
    прогона, державшая 60% видеопамяти, и скрипт считал, что поднял сервер сам.
    """
    with FakeVlm({"text": "ок"}) as s:
        out = _t(s.url).check()
        assert out["совпало"] and out["модели на сервере"] == [s.model]


def test_wrong_model_name_stops_the_run():
    with FakeVlm({"text": "ок"}, model="совсем-другая") as s:
        try:
            _t(s.url).check()
        except RuntimeError as e:
            assert "совсем-другая" in str(e)
        else:
            raise AssertionError("чужое имя модели прошло молча")


def test_delivery_refusal_is_a_value_not_a_throw(tmp_png=None):
    """Отказ доставки возвращается значением: прогон на пятистах блоках не
    должен умирать от одного обрыва связи."""
    png = _png()
    with FakeVlm({"http": 500}) as s:
        t = _t(s.url)
        os.environ["VLM_RETRIES"] = "0"
        said = vhttp.Http().send(Ask("p0-b0", png, "OCR:", "text", "text"))
        assert said.error and said.text is None
        assert not said.answered()
    os.environ.pop("VLM_RETRIES", None)


def test_answer_200_is_never_repeated():
    """Переспрос после ответа запрещён правилом и выражен кодом.

    Ответ 200 с пустотой — это ОТВЕТ, и второй вопрос по нему был бы починкой
    модели. Считаем обращения к службе: их обязано быть ровно одно.
    """
    png = _png()
    os.environ["VLM_RETRIES"] = "3"
    with FakeVlm({"text": ""}) as s:
        _t(s.url).send(Ask("p0-b0", png, "OCR:", "text", "text"))
        assert len(s.seen) == 1, f"на один ответ ушло {len(s.seen)} обращений"
    os.environ.pop("VLM_RETRIES", None)


def test_delivery_refusal_is_repeated():
    """А вот отказ доставки повторяется: ответа не было вовсе."""
    png = _png()
    os.environ["VLM_RETRIES"] = "2"
    with FakeVlm({"http": 503}) as s:
        _t(s.url).send(Ask("p0-b0", png, "OCR:", "text", "text"))
        assert len(s.seen) == 3, f"обращений {len(s.seen)}, ждали 3"
    os.environ.pop("VLM_RETRIES", None)


def test_empty_crop_is_loud():
    """Пустая вырезка не уезжает в модель.

    На пустом белом листе эта модель выдаёт полноценные таблицы — пять разных
    за пять попыток. Послать пустоту значит получить выдумку и записать её
    чтением.
    """
    import tempfile
    p = os.path.join(tempfile.mkdtemp(), "пусто.png")
    open(p, "wb").close()
    try:
        vhttp._data_uri(p)
    except ValueError as e:
        assert "пуста" in str(e)
    else:
        raise AssertionError("пустая вырезка уехала бы в модель")


def test_the_very_crop_reaches_the_model():
    """До модели доехала ТА вырезка, а не соседняя.

    Оплачено первым уровнем: переменная цикла затёрла коэффициент масштаба, и
    36 страниц из 36 записались неразобранными при безупречном ответе модели.
    """
    png = _png()
    n = os.path.getsize(png)
    with FakeVlm({"text": "ок"}) as s:
        _t(s.url).send(Ask("p0-b0", png, "Table Recognition:", "otsl", "table"))
        assert s.seen[0]["байт"] == n
        assert s.seen[0]["промт"] == "Table Recognition:"


# ------------------------------------------------------------- разбор ---

def test_otsl_grid_matches_html_grid_cell_for_cell():
    """Сетка из OTSL и та же сетка из HTML совпадают по адресам.

    Ради чего эта проверка. Прибор чтения разбирал таблицу ТОЛЬКО из HTML, и
    безупречный ответ PaddleOCR-VL — а она отдаёт OTSL — получал «совпало по
    адресу 0 (0%)» и клеймо «отдана текстом»: обвинение модели в дефекте
    нашего разбора.
    """
    # Сверяется НЕ разбор OTSL сам по себе, а ТА функция, которой прибор
    # достаёт сетку из ответа модели. Первая редакция этой проверки звала
    # `otsl.grid` и `_html_grid` порознь — и мутация «прибор снова слепнет на
    # OTSL» прошла мимо неё: сломанный `_answer_grid` проверку не касался
    # вовсе. Батарея это и поймала.
    from booksmith import text as booktext
    want = {(0, 0): "А", (0, 1): "Б", (1, 0): "1", (1, 1): "2"}
    g1 = booktext._answer_grid("<fcel>А<fcel>Б<nl><fcel>1<fcel>2<nl>", "otsl")
    g2 = booktext._answer_grid("<table><tr><td>А</td><td>Б</td></tr>"
                               "<tr><td>1</td><td>2</td></tr></table>", "html")
    # И вид, объявленный промтом, не запирает разбор: модель, спрошенная про
    # таблицу и ответившая HTML, ТАБЛИЦУ ПРОЧЛА, и мерить надо чтение.
    g3 = booktext._answer_grid("<fcel>А<fcel>Б<nl><fcel>1<fcel>2<nl>", "html")
    assert g1 == g2 == g3 == want


def test_otsl_span_occupies_all_its_addresses():
    """Сквозная клетка занимает все адреса — как colspan у HTML-разбора."""
    g = otsl.grid("<ched>шапка<lcel><nl><fcel>1<fcel>2<nl>")
    assert g[(0, 0)] == g[(0, 1)] == "шапка"


def test_torn_otsl_is_counted_not_repaired():
    """Рваный OTSL остаётся рваным и считается числом.

    Вендорский `otsl_pad_to_sqr_v2` поступает наоборот — молча дополняет и
    укорачивает, — и порванная по потолку таблица возвращается у него
    правдоподобной.
    """
    _, t = otsl.parse("<fcel>a<fcel>b<nl><fcel>c<nl>")
    assert t["строк разной длины"] == 1
    _, t2 = otsl.parse("<lcel>x<nl>")
    assert t2["продолжений в никуда"] == 1


def test_not_otsl_is_none_not_empty():
    """«Это не OTSL» и «таблица пуста» — разные ответы."""
    assert otsl.grid("<table><tr><td>x</td></tr></table>") is None
    assert otsl.grid("просто проза") is None
    assert otsl.grid("") is None


def test_sniffed_kind_never_overrides_the_declared_one():
    """Догадка о виде лежит СБОКУ и ничего не решает."""
    assert vrun._sniff("<fcel>a<nl>") == "otsl"
    assert vrun._sniff("проза") == "text"
    assert vrun._sniff("") == "пусто"


# --------------------------------------------------------- проход книги ---

def _png():
    """Настоящая маленькая картинка: транспорт читает байты, а не путь."""
    import tempfile
    import pymupdf
    d = os.path.join(tempfile.mkdtemp(), "к.png")
    doc = pymupdf.open()
    pg = doc.new_page(width=60, height=30)
    pg.insert_text((5, 20), "abc")
    pg.get_pixmap(dpi=72).save(d)
    doc.close()
    return d


def _book(tmp):
    """Крошечная книга и каталог детекции к ней: два блока, текст и таблица."""
    import pymupdf
    from booksmith.run import stamp
    pdf = os.path.join(tmp, "к.pdf")
    doc = pymupdf.open()
    pg = doc.new_page(width=200, height=200)
    pg.insert_text((20, 40), "строка прозы")
    pg.insert_text((20, 120), "таблица")
    doc.save(pdf, garbage=3, deflate=True)
    doc.close()

    os.makedirs(os.path.join(tmp, "detect", "pages"), exist_ok=True)
    page = Page(index=0, width=400, height=400, dpi=144.0, blocks=[
        Block(block_id=0, box=(30, 40, 300, 100), label="text", score=0.9,
              order=1),
        Block(block_id=1, box=(30, 200, 300, 300), label="table", score=0.8,
              order=2),
        Block(block_id=2, box=(30, 320, 300, 380), label="image", score=0.7,
              order=3),
    ])
    with open(os.path.join(tmp, "detect", "pages", "0000.json"), "w",
              encoding="utf-8") as f:
        json.dump(page.to_json(), f, ensure_ascii=False)
    with open(os.path.join(tmp, "detect", "run.json"), "w",
              encoding="utf-8") as f:
        json.dump({"исходник": {"путь": pdf, "sha256": stamp.sha256(pdf)},
                   "растр": {"dpi": 144.0},
                   "коммит": None, "адаптер": {"имя": "поддельный"},
                   "веса": {"layout": None}}, f, ensure_ascii=False)
    return pdf


def _run(tmp, plan, **kw):
    out = os.path.join(tmp, "read")
    with FakeVlm(plan) as s:
        os.environ["VLM_ENDPOINT"] = s.url
        os.environ["MODEL_NAME"] = s.model
        r = PaddleOcrVl("PP-DocLayoutV2")
        t = vrun.read_book(os.path.join(tmp, "detect"), out, r, vhttp.Http(),
                           log=lambda *a: None, **kw)
    return out, t


def test_read_fills_content_in_the_same_page_schema():
    """Продукт чтения — тот же `pages/*.json`, что у детекции."""
    import tempfile
    tmp = tempfile.mkdtemp()
    _book(tmp)
    out, t = _run(tmp, {"OCR:": {"text": "строка прозы"},
                        "Table Recognition:": {"text": "<fcel>А<fcel>Б<nl>"}})
    with open(os.path.join(out, "pages", "0000.json"), encoding="utf-8") as f:
        p = Page.from_json(json.load(f))
    by = {b.block_id: b for b in p.blocks}
    assert by[0].content == "строка прозы" and by[0].kind == "text"
    assert by[1].content == "<fcel>А<fcel>Б<nl>" and by[1].kind == "otsl"
    # Рисунок не спрашивали вовсе — и это НЕ молчание модели.
    assert by[2].content is None and by[2].kind == "none"
    assert t["не спрошено"] == 1 and t["прочитано"] == 2


def test_five_zeroes_are_counted_apart():
    """Не спрошено / отказ доставки / промолчала / оборвано / прочитано."""
    import tempfile
    tmp = tempfile.mkdtemp()
    _book(tmp)
    out, t = _run(tmp, {"OCR:": {"text": ""},                       # молчание
                        "Table Recognition:": {"text": "<fcel>x<nl>",
                                               "finish": "length"}})
    assert t["не спрошено"] == 1, t
    assert t["модель промолчала"] == 1, t
    assert t["оборвано потолком"] == 1, t
    assert t["прочитано"] == 1, t
    assert t["отказ доставки"] == 0, t


def test_delivery_refusal_does_not_look_like_silence():
    """Отказ связи не записывается молчанием модели: разные беды."""
    import tempfile
    tmp = tempfile.mkdtemp()
    _book(tmp)
    os.environ["VLM_RETRIES"] = "0"
    out, t = _run(tmp, {"http": 500})
    assert t["отказ доставки"] == 2 and t["модель промолчала"] == 0, t
    os.environ.pop("VLM_RETRIES", None)


def test_model_bytes_are_untouched():
    """Байты модели доезжают до страницы побайтово, включая мусор."""
    import tempfile
    tmp = tempfile.mkdtemp()
    _book(tmp)
    грязь = "  <b>не закрыт &amp;\n\tпробелы  "
    out, _ = _run(tmp, {"OCR:": {"text": грязь},
                        "Table Recognition:": {"text": "<fcel>a<nl>"}})
    with open(os.path.join(out, "pages", "0000.json"), encoding="utf-8") as f:
        p = Page.from_json(json.load(f))
    assert p.blocks[0].content == грязь


def test_observed_lives_beside_not_inside():
    """Секунды, токены, догадка о виде — в answers/, а не в тексте блока."""
    import tempfile
    tmp = tempfile.mkdtemp()
    _book(tmp)
    out, _ = _run(tmp, {"OCR:": {"text": "проза"},
                        "Table Recognition:": {"text": "<fcel>a<nl>"}})
    with open(os.path.join(out, "answers", "p0000.json"), encoding="utf-8") as f:
        a = {x["якорь"]: x for x in json.load(f)["ответы"]}
    assert a["p0000-b0"]["наблюдённое"]["догадка о виде"] == "text"
    assert a["p0000-b1"]["наблюдённое"]["догадка о виде"] == "otsl"
    assert "секунд" in a["p0000-b0"]
    # А в самом тексте — ни одной нашей пометки.
    with open(os.path.join(out, "pages", "0000.json"), encoding="utf-8") as f:
        p = Page.from_json(json.load(f))
    assert p.blocks[0].content == "проза"


def test_swapped_pdf_stops_the_run():
    """Книга, подменённая после детекции, роняет чтение вслух."""
    import tempfile
    tmp = tempfile.mkdtemp()
    pdf = _book(tmp)
    with open(pdf, "ab") as f:
        f.write(b"% extra byte\n")   # байт мимо ASCII в b"" не кладут
    try:
        _run(tmp, {"OCR:": {"text": "x"}})
    except SystemExit as e:
        assert "sha256" in str(e)
    else:
        raise AssertionError("чтение пошло по подменённой книге")


def test_resume_does_not_ask_twice():
    """Возобновление не платит второй раз за уже прочитанный блок."""
    import tempfile
    tmp = tempfile.mkdtemp()
    _book(tmp)
    plan = {"OCR:": {"text": "проза"},
            "Table Recognition:": {"text": "<fcel>a<nl>"}}
    out, t1 = _run(tmp, plan)
    assert t1["взято из прошлого прогона"] == 0
    with FakeVlm(plan) as s:
        os.environ["VLM_ENDPOINT"] = s.url
        t2 = vrun.read_book(os.path.join(tmp, "detect"), out,
                            PaddleOcrVl("PP-DocLayoutV2"), vhttp.Http(),
                            resume=True, log=lambda *a: None)
        assert len(s.seen) == 0, f"переспрошено {len(s.seen)} блоков"
    assert t2["взято из прошлого прогона"] == 2


def test_empty_run_is_not_a_success():
    """Ноль спрошенных блоков — не успех, а пустой прогон."""
    import tempfile
    tmp = tempfile.mkdtemp()
    _book(tmp)
    try:
        _run(tmp, {"OCR:": {"text": "x"}}, pages_want={999})
    except SystemExit as e:
        assert "пуст" in str(e)
    else:
        raise AssertionError("пустой набор страниц прошёл молча")


def test_snapshot_carries_prompts_and_our_parser():
    """Слепок несёт промты, порождение и хэш НАШЕГО разбора OTSL.

    Промты — единственное, чем здесь управляют ответом; поле «промты» было
    пусто у всех прогонов проекта, и это первое, что его заполняет. Разбор
    OTSL хэшируется отдельно: он решает числа не меньше модели, и два прогона
    с разным разбором обязаны различаться слепком.
    """
    import tempfile
    tmp = tempfile.mkdtemp()
    _book(tmp)
    out, t = _run(tmp, {"OCR:": {"text": "проза"},
                        "Table Recognition:": {"text": "<fcel>a<nl>"}})
    with FakeVlm({"text": "x"}) as s:
        os.environ["VLM_ENDPOINT"] = s.url
        p = vrun.snapshot(os.path.join(tmp, "detect"), out,
                          PaddleOcrVl("PP-DocLayoutV2"), vhttp.Http(), t,
                          {"detect": "detect", "out": out})
    with open(p, encoding="utf-8") as f:
        snap = json.load(f)
    assert snap["промты"]["table"] == "Table Recognition:"
    assert snap["порождение"]["max_tokens"] == 4096
    assert len(snap["адаптер"]["sha256 разбора otsl"]) == 64
    assert snap["отпечаток"]["веса"]["каталог"] is None
    # Ключ НЕ уезжает в слепок: его кладут в git.
    assert snap["отпечаток транспорта"]["ключ"] == "нет"
