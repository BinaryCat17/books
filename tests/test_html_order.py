"""Сборщик книги и договор о порядке чтения.

Проверка узкая и заведена по замеру: у договора про поле `порядок чтения` ДВА
читателя — сторож метрики и сборщик книги, — и стерёгся только первый.
Скептик показал это порчей: вернул в `doc/html._ours` собственную, разошедшуюся
копию правила (без снятия регистра), и все шестьдесят проверок остались
зелёными. То есть половина договора держалась на честном слове.

Цена расхождения известна и уплачена соседним прибором: на `bench/hard36`
метрика печатала «порядок чтения согласовано 73%» там, где порядок не размечен
ни на одной из 36 страниц. Число из ничего рождается именно так — двумя
копиями одного сговора.
"""
from booksmith.doc import html as H
from booksmith.models import base as B


def test_book_builder_reads_the_order_rule_through_the_one_contract():
    """`doc/html` обязан звать `models.base.ours_order`, а не свою копию."""
    for v in ("наш, сверху вниз", "Наш, полосами", "НАШ, позиция в списке",
              "  наш  ", "model_rank", "", None, 0, "порядок порождения"):
        assert H._ours(v) == B.ours_order(v), (
            f"{v!r}: сборщик книги и контракт адаптера разошлись — "
            f"сборщик {H._ours(v)}, контракт {B.ours_order(v)}. Это та самая "
            f"вторая копия договора, из-за которой рождается процент из ничего")


def test_anchor_is_page_scoped():
    """Якорь ПОСТРАНИЧНЫЙ: `block_id` считается заново на каждой странице.

    Сквозной `b17` на книге в пятьсот страниц дал бы пятьсот одинаковых
    якорей, и замена второго уровня попала бы не туда.
    """
    assert H.anchor_of(42, 17) == "p0042-b17"
    assert H.anchor_of(0, 0) == "p0000-b0"
    assert H.anchor_of(1, 17) != H.anchor_of(2, 17)


# --- вырезка: сговор сборки книги с рамкой модели ---------------------------
#
# Проверки вырезки живут здесь, а не в своём файле, потому что сговор один:
# `doc/html` режет `doc/crop`-ом по рамке модели и печатает его величины в
# подпись блока. Каждая ниже закрывает беду, воспроизведённую на `bench/atlas`.

def _sheet():
    """Пустой лист 720x506 пунктов в памяти. Без bench: проверка обязана идти
    в любом дереве, а не только там, где стенд уже нарезан."""
    import pymupdf
    doc = pymupdf.open()
    doc.new_page(width=720, height=506)
    return doc


def test_clipping_is_measured_with_a_tolerance_not_exactly():
    """«Срезано листом» на резкости, не дающей двоично точного множителя.

    pymupdf держит координаты одинарной точностью и прогоняет их через float32
    ещё раз при пересечении. Замер на `bench/atlas`: при `PAGE_DPI` = 144
    множитель 72/144 = 0.5 точен и срезанных 0 из 28, при 150 — 28 из 28, и в
    книгу к 26 вырезкам из 26 дописывалось «рамка вышла за лист». Расхождение
    при этом до 1.7e-05 пункта, то есть беды нет вовсе.

    И ОБРАТНОЕ, без чего проверка ничего не стоит: настоящий срез обязан
    остаться видимым. Метрика, которая не умеет сработать, не доказана.
    """
    import os
    import tempfile
    from booksmith.doc import crop
    doc = _sheet()
    dpi = 150.0                       # 72/150 = 0.48 — двоично НЕ точно
    # Рамка В ПИКСЕЛЯХ, и числа взяты не круглые НАРОЧНО: при 100 и 300
    # пикселях пункты выходят целыми, точное сравнение расхождения не даёт, и
    # проверка была бы зелена на неисправном коде. 113 пикселей дают
    # 54.239999999999995 пункта — вот на таких она и падала.
    inside_px = [113, 74, 1332, 803]
    out_px = [113, 74, int((720 + 20) / 0.48), 803]      # вылезла на 20 пунктов
    with tempfile.TemporaryDirectory() as tmp:
        dst = os.path.join(tmp, "b.png")
        inside = crop.cut(doc, 0, inside_px, dpi, dst)
        assert inside["clipped_by_sheet"] is False, (
            "рамка целиком внутри листа объявлена срезанной — это float32 "
            "пересечения, а не дефект модели")
        out = crop.cut(doc, 0, out_px, dpi, dst)
        assert out["clipped_by_sheet"] is True, (
            "рамка, вылезшая за лист на 20 пунктов, срезанной НЕ названа — "
            "допуск съел настоящую беду")


def test_degenerate_and_inverted_boxes_are_named_by_their_own_trouble():
    """Вырожденная и перевёрнутая рамка — не «мимо листа».

    Обе давали пустое пересечение и получали чужой диагноз «не пересекается с
    листом» при рамке посреди бумаги; читающий шёл искать съехавшие координаты.
    """
    import os
    import tempfile
    from booksmith.doc import crop
    doc = _sheet()
    with tempfile.TemporaryDirectory() as tmp:
        dst = os.path.join(tmp, "b.png")
        for box, word in (([200.0, 200.0, 200.0, 300.0], "ВЫРОЖДЕНА"),
                          ([300.0, 200.0, 200.0, 300.0], "ПЕРЕВЁРНУТА")):
            try:
                crop.cut(doc, 0, box, 144.0, dst)
            except ValueError as e:
                assert word in str(e), (
                    f"рамка {box} названа не своей бедой: {str(e)[:90]!r}")
            else:
                raise AssertionError(f"рамка {box} вырезана молча")
        # А настоящая «мимо листа» обязана остаться собой.
        try:
            crop.cut(doc, 0, [5000.0, 5000.0, 5100.0, 5100.0], 144.0, dst)
        except ValueError as e:
            assert "не пересекается с листом" in str(e)
        else:
            raise AssertionError("рамка за пределами листа вырезана молча")


def test_negative_margin_is_refused_out_loud():
    """Отрицательное `CROP_MARGIN` РЕЖЕТ рамку модели, а не даёт поля.

    Замер до починки: `CROP_MARGIN=-0.1` на рамке (96, 96, 192, 144) пунктов
    отдавал вырезку (105.6, 100.8, 182.4, 139.2) — десятая доля съедена с
    каждой стороны, — и обе величины среза стояли False. Правка рамки модели
    запрещена правилом проекта, поэтому падение, а не тихий зажим в ноль.
    """
    import os
    from booksmith.doc import crop
    was = os.environ.get("CROP_MARGIN")
    os.environ["CROP_MARGIN"] = "-0.1"
    try:
        crop.params(144.0)
    except ValueError as e:
        assert "CROP_MARGIN" in str(e)
    else:
        raise AssertionError("отрицательное поле принято молча")
    finally:
        if was is None:
            del os.environ["CROP_MARGIN"]
        else:
            os.environ["CROP_MARGIN"] = was


def test_native_dpi_divides_by_the_placement_not_by_the_sheet():
    """Собственная резкость считается по ШИРИНЕ РАЗМЕЩЕНИЯ картинки.

    Скан разворота ШИРЕ листа: `books prepare` режет его пополам и кладёт обе
    половины через `show_pdf_page`, так что растр в 2867 px лежит на 688 пт при
    листе в 278 пт. Деление на лист завышало решётку ровно во столько раз, во
    сколько растр шире, — до 2.47 раза на четырёх книгах из шести. Сверено с
    заголовком самого djvu (`djvudump`): у трёх книг из трёх формат объявляет
    300 / 600 / 300 dpi, и новая формула совпадает с ним, а старая — нет.

    Правка была не покрыта ничем: в `tests/` про `native_dpi` не было ни слова.
    """
    import pymupdf
    from booksmith.doc import crop

    # Лист 200x100 пт, растр 1000 px лежит на 400 пт — вдвое шире листа.
    doc = pymupdf.open()
    page = doc.new_page(width=200, height=100)
    src = pymupdf.open()
    sp = src.new_page(width=400, height=100)
    sp.insert_text((10, 50), "x")
    pix = sp.get_pixmap(dpi=180)          # 1000 px на 400 пт = 180 dpi
    img = pymupdf.open("png", pix.tobytes("png"))
    page.insert_image(pymupdf.Rect(0, 0, 400, 100), stream=img.convert_to_pdf()
                      if False else pix.tobytes("png"))
    got = crop.native_dpi(page)
    doc.close(); src.close(); img.close()
    assert got is not None, "растр на весь лист, а резкость не определилась"
    # По размещению: 1000 px / 400 пт = 180 dpi. По ЛИСТУ вышло бы 360.
    assert abs(got - 180.0) < 1.0, (
        f"резкость {got:.1f} — считана по ширине ЛИСТА, а не размещения; "
        f"деление на лист даёт 360 и завышает вдвое")


def test_native_dpi_says_nothing_when_there_is_nothing_to_say():
    """Вектор и марка в углу — `None`, а не число наугад."""
    import pymupdf
    from booksmith.doc import crop

    doc = pymupdf.open()
    page = doc.new_page(width=200, height=100)
    page.insert_text((10, 50), "только текст")
    assert crop.native_dpi(page) is None, "вектор объявил решётку"

    # Марка в углу: подробная, но занимает пятую часть ширины.
    small = pymupdf.open()
    sp = small.new_page(width=40, height=20)
    sp.insert_text((2, 15), "m")
    page.insert_image(pymupdf.Rect(0, 0, 40, 20),
                      stream=sp.get_pixmap(dpi=600).tobytes("png"))
    got = crop.native_dpi(page)
    doc.close(); small.close()
    assert got is None, (
        f"марка в углу объявлена резкостью страницы ({got}) — по ней резался "
        f"бы весь лист")


def test_crop_dpi_counts_what_will_actually_be_cut():
    """Резкость считается по ПЕРЕСЕЧЕНИЮ рамки с листом, а не по рамке.

    `crop.cut` режет пересечение — рамка модели вправе вылезти за бумагу. Считая
    зажим под окно модели по ПОЛНОЙ рамке, мы прижимали бы резкость под размер,
    которого на листе нет: рамка, вылезшая вдвое, получала 83.7 dpi вместо
    118.4, то есть окно модели не добиралось. На стенде таких рамок 28 из
    33 640 и вылеты не больше 4.8 пикселя — настоящими данными это не поймано,
    но два числа обязаны считаться по одному прямоугольнику.
    """
    from booksmith.read.run import crop_dpi_for
    W = (112896, 1003520)
    sheet = (0.0, 0.0, 1012.0, 1466.0)
    out = (0, 0, 2024, 1466)                   # вдвое шире листа
    without, _ = crop_dpi_for(out, 144.0, 601.0, W)
    with_sheet, why = crop_dpi_for(out, 144.0, 601.0, W, sheet=sheet)
    assert with_sheet > without + 1, (
        f"по листу {with_sheet:.1f}, по полной рамке {without:.1f} — резкость "
        f"считается по тому, чего на бумаге нет")
    # А та же рамка ЦЕЛИКОМ на листе не должна меняться от появления листа.
    inside = (0, 0, 540, 700)
    a, _ = crop_dpi_for(inside, 144.0, 601.0, W)
    b, _ = crop_dpi_for(inside, 144.0, 601.0, W, sheet=sheet)
    assert abs(a - b) < 1e-9, "лист изменил резкость рамки, лежащей внутри него"


def test_crop_dpi_never_comes_from_the_environment_silently():
    """Пустой `CROP_DPI` не значит «как в ЭТОМ процессе», и говорит откуда.

    Умолчание менялось дважды, и оба раза замером. Сперва оно было «`PAGE_DPI`
    текущего процесса» — детекция `bench/atlas` при `PAGE_DPI=150` и сборка
    при умолчании печатали «вырезок 26 при 144 dpi», хотя координаты
    пересчитывались из 150. Потом стало «как у детекции», и это тоже оказалось
    мало: на настоящем скане в 200 dpi резать при 144 значит выбросить 48%
    чернил, которые в файле есть (замер в `crop.params`).

    Сегодня умолчание — СОБСТВЕННАЯ резкость скана, а стережёт эта проверка
    то, что стерегла всегда: величина обязана называть свой источник, и
    молчаливое окружение источником быть не смеет.
    """
    from booksmith.doc import crop
    # своя резкость известна — она и берётся, детекция ни при чём
    p = crop.params(150.0, page_native=300.0)
    assert p["dpi"] == 300.0 and p["dpi_source"] == "native_scan_dpi", p
    # своей нет — детекция, и об этом сказано словами
    p2 = crop.params(150.0)
    assert p2["dpi"] == 150.0 and "как у детекции" in p2["dpi_source"], p2
    # нет ни того ни другого — окружение, и это НАЗВАНО угаданным
    assert crop.params()["dpi_source"] == "PAGE_DPI текущего процесса", (
        "резкость угадана по окружению, и об этом не сказано ни слова")


def test_crop_dpi_takes_the_ink_that_exists_and_invents_none():
    """Резкость вырезки — правило, а не число: сколько есть, но не больше окна.

    Ни одна из трёх величин не наша: резкость приходит от скана, границы от
    модели (`Reader.pixels`), размер рамки от детектора. Вверх выше своей
    решётки не поднимаемся НИКОГДА — это выдумывало бы точки и звало их
    чтением.
    """
    from booksmith.read.run import crop_dpi_for
    W = (112896, 1003520)
    # блок мельче нижней границы: остаёмся на своей решётке и говорим об этом
    d, why = crop_dpi_for((0, 0, 273, 47), 144.0, 144.0, W)
    assert d == 144.0 and "below_model_min" == why, (d, why)
    # тот же блок в книге из djvu (текстовый слой 601 dpi) — берём всё
    d, why = crop_dpi_for((0, 0, 273, 47), 144.0, 601.0, W)
    assert d == 601.0 and why == "native_scan_dpi", (d, why)
    # крупная таблица там же вышла бы за верхнюю границу — ужимаем ровно к ней
    d, why = crop_dpi_for((0, 0, 540, 700), 144.0, 601.0, W)
    px = (540 / 144 * d) * (700 / 144 * d)
    assert abs(px - W[1]) < 1 and why == "downscaled_to_model_max", (d, why, px)
    # границ модель не объявила — режем своей резкостью и ничего не правим
    d, why = crop_dpi_for((0, 0, 540, 700), 144.0, 601.0, None)
    assert d == 601.0 and "границ модели нет" in why, (d, why)


def test_nesting_survives_blocks_without_a_model_rank():
    """`Block.order = None` контракт разрешает ПРЯМО — сборка не смеет падать.

    Ранга не даёт ни один адаптер из трёх (yolox и оба docling), а у
    четвёртого он пуст ровно у того, что первый уровень вырезает картинками
    (100% у `image`, `figure_title`, `table` — см. `models/base.Block`). Пара
    «ранг есть / ранга нет» на одном прямоугольнике роняла ВСЮ книгу:
    `TypeError: '>=' not supported between instances of 'NoneType' and 'int'`.
    """
    from booksmith.models.base import Block
    box = (0.0, 0.0, 100.0, 100.0)
    pairs = ((3, None), (None, 3), (None, None), (1, 2))
    for o1, o2 in pairs:
        arts = [Block(block_id=1, box=box, label="table", order=o1),
                Block(block_id=2, box=box, label="image", order=o2)]
        inner = H._nesting(arts)
        assert len(inner) == 1, (
            f"ранги {o1!r}/{o2!r}: вложенность посчитана как {inner}, а рамки "
            f"совпадают — одна обязана уйти внутрь другой")
    # Ранг решает, КТО внешний, и решает он ЕЁ порядком, а не нашим id.
    arts = [Block(block_id=1, box=box, label="table", order=9),
            Block(block_id=2, box=box, label="image", order=1)]
    assert H._nesting(arts) == {1: 2}, (
        "внешней названа не та, что раньше по рангу модели")


def test_the_anchor_rule_has_exactly_one_home():
    """Имя блока собирает `doc/html.anchor_of`, и никто больше.

    Своих копий этого правила было ДВЕ — в `doc/feed` и в `doc/apply`, — и
    разошлись бы они молча: feed.json звал бы куски одними именами, книга и
    blocks.json другими, а `books apply` отвечал бы «якоря нет в книге» на
    каждый блок чтения. Проверяем тождеством объекта, а не совпадением строк:
    совпадение строк держится ровно до первой правки одной из копий.
    """
    from booksmith.doc import apply as ap
    from booksmith.doc import feed
    assert feed.anchor_of is H.anchor_of, "doc/feed завёл свой якорь"
    assert ap.anchor_of is H.anchor_of, "doc/apply завёл свой якорь"


def test_three_kinds_of_bad_sheet_get_three_different_marks():
    """Лист-отказ бывает ТРЁХ видов, и путать их нельзя.

    Прежде пометки было две, и третий вид печатался чужой: `blank` значил
    «блоки есть, текста среди них нет», поэтому лист с одной колонцифрой
    (`footer`, разряд «служебное») получал красное «вся полоса ушла в
    картинки» при `data-image-share="0.00"` — элемент противоречил сам
    себе. Замер: `bench/atlas` стр. 0.
    """
    import json
    import os
    import tempfile

    import pymupdf
    from booksmith.models.base import Block, Page

    def page(i, blocks):
        return Page(index=i, width=1000, height=1400, dpi=144.0,
                    blocks=blocks, meta={"reading_order": "model_rank"})

    art = Block(block_id=0, box=(50.0, 50.0, 950.0, 1350.0), label="table",
                score=0.9, order=0)
    with tempfile.TemporaryDirectory() as tmp:
        pdf = os.path.join(tmp, "проба.pdf")
        doc = pymupdf.open()
        for _ in range(4):
            doc.new_page(width=500, height=700)
        doc.save(pdf)
        doc.close()

        det = os.path.join(tmp, "detect")
        os.makedirs(os.path.join(det, "pages"))
        pages = [
            page(0, [Block(block_id=0, box=(200.0, 1300.0, 300.0, 1340.0),
                           label="footer", score=0.8, order=0)]),
            page(1, [art]),
            page(2, []),
            page(3, [Block(block_id=0, box=(50.0, 50.0, 950.0, 600.0),
                           label="text", score=0.9, order=0, content="строки"),
                     Block(block_id=1, box=(50.0, 700.0, 950.0, 1300.0),
                           label="table", score=0.9, order=1)]),
        ]
        for p in pages:
            with open(os.path.join(det, "pages", f"{p.index:04d}.json"),
                      "w", encoding="utf-8") as f:
                json.dump(p.to_json(), f, ensure_ascii=False)
        from booksmith import detect as _detect
        with open(os.path.join(det, "run.json"), "w", encoding="utf-8") as f:
            json.dump({"source": {"path": pdf,
                                    "sha256": _detect._sha256(pdf)},
                       "raster": {"dpi": 144},
                       "weights": {"layout": None}}, f, ensure_ascii=False)

        out = os.path.join(tmp, "html")
        H.build(det, out, log=lambda *_: None)
        book = open(os.path.join(out, "book.html"), encoding="utf-8").read()

    import re
    marks = dict(re.findall(r'<hr class="sheet" data-sheet="(\d+)"([^>]*)>', book))
    assert 'data-furniture-only' in marks["0"], (
        f"лист из одного служебного помечен как {marks['0']!r} — а картинок "
        f"на нём нет вовсе")
    assert 'data-no-text' not in marks["0"], (
        "лист без единой картинки назван ушедшим в картинки: "
        f"{marks['0']!r}")
    assert ('data-no-text' in marks["1"]
            and 'data-furniture-only' not in marks["1"]), marks["1"]
    assert 'data-empty' in marks["2"], marks["2"]
    assert marks["3"].strip().endswith('"'), (
        f"здоровый лист получил пометку отказа: {marks['3']!r}")
    # И у каждой пометки своя надпись — иначе разведены они только на словах.
    for word in ("вся полоса ушла в картинки", "модель не нашла на листе ничего",
                 "на листе только служебное"):
        assert word in book, f"надписи «{word}» в книге нет"


def test_the_book_is_alone_at_the_root_and_carries_itself():
    """В корне сборки РОВНО ОДИН файл, и он не ссылается наружу.

    ДВА ОБЕЩАНИЯ, И ОБА ПРОВЕРЯЮТСЯ ЗДЕСЬ.

    Первое — раскладка. Книгу открывают двойным щелчком из проводника, и
    корень, где рядом с ней лежат четыре json и двухмегабайтный js, заставляет
    читателя гадать, что из этого открыть. Кухня уезжает в `assets/`.

    Второе — самодостаточность, и она оплачена. При `HTML_MATH=local` MathJax
    лежал соседним файлом, и книга, открытая по сетевому пути
    (`\\\\wsl.localhost\\...` из Windows), показывала формулы СЫРЫМ LaTeX:
    Chromium молча не грузит локальный скрипт с UNC-пути, консоль пуста, а
    книга выглядит собранной. То же ждало бы картинки. Поэтому умолчание —
    вшивать: `HTML_MATH=inline`, `HTML_IMAGES=inline`.

    Вырезки при этом остаются файлами в `assets/blocks` ВСЕГДА: они нужны
    правкам, замерам и второму уровню, и второй экземпляр внутри книги их не
    отменяет.
    """
    import json
    import os
    import re
    import tempfile

    import pymupdf

    from booksmith import detect as _detect
    from booksmith.models.base import Block, Page

    with tempfile.TemporaryDirectory() as tmp:
        pdf = os.path.join(tmp, "проба.pdf")
        doc = pymupdf.open()
        doc.new_page(width=500, height=700)
        doc.save(pdf)
        doc.close()

        det = os.path.join(tmp, "detect")
        os.makedirs(os.path.join(det, "pages"))
        pg = Page(index=0, width=1000, height=1400, dpi=144.0, blocks=[
            Block(block_id=0, box=(50.0, 50.0, 950.0, 400.0), label="text",
                  score=0.9, order=0, content="строки"),
            Block(block_id=1, box=(50.0, 500.0, 950.0, 1300.0), label="table",
                  score=0.9, order=1)])
        with open(os.path.join(det, "pages", "0000.json"), "w",
                  encoding="utf-8") as f:
            json.dump(pg.to_json(), f, ensure_ascii=False)
        with open(os.path.join(det, "run.json"), "w", encoding="utf-8") as f:
            json.dump({"source": {"path": pdf,
                                    "sha256": _detect._sha256(pdf)},
                       "raster": {"dpi": 144},
                       "weights": {"layout": None}}, f, ensure_ascii=False)

        out = os.path.join(tmp, "html")
        H.build(det, out, log=lambda *_: None)

        в_корне = sorted(os.listdir(out))
        assert в_корне == ["assets", "book.html"], (
            f"в корне сборки {в_корне}, а ожидается только book.html и "
            f"assets/. Всё, кроме книги, — кухня")

        with open(os.path.join(out, "book.html"), encoding="utf-8") as f:
            s = f.read()
        # Ищем то, что книга ГРУЗИТ, а не любую ссылку: `src=` у картинок и
        # скриптов плюс таблицы стилей. Обычный `<a href="https://…">` не
        # ловим — их два, оба внутри диалога «О программе» самого MathJax,
        # и на чтение книги без сети они не влияют никак.
        грузит = [u for u in re.findall(r'\ssrc="([^"]+)"', s)
                  if not u.startswith("data:")]
        грузит += re.findall(r'<link[^>]+href="([^"]+)"', s)
        assert not грузит, (
            f"книга подгружает со стороны: {грузит[:5]}. По сетевому пути "
            f"(\\\\wsl.localhost\\...) браузер эти файлы молча не загрузит, и "
            f"книга откроется без формул и картинок, выглядя исправной")

        assert os.path.isdir(os.path.join(out, "assets", "blocks")), (
            "вырезок нет в assets/blocks. Они обязаны лежать файлами даже "
            "когда вшиты в книгу: их читают правки, замеры и второй уровень")


def test_the_builder_recognises_its_own_directory():
    """Признак «каталог собран нами» знает СБОРЩИК, а не вызывающий.

    ЧЕМ ЭТО ОПЛАЧЕНО. Сторож «чужое не затираем» в `cli.py` искал `run.json`
    в КОРНЕ каталога. Слепок переехал в `assets/`, и сторож стал отказывать
    каталогу, сделанному этой же командой минуту назад, — причём отказывать
    ЛОЖЬЮ: «это, скорее всего, книга прежнего конвейера», которых в проекте
    не осталось ни одной. Под тот же отказ попадал и совет, который печатает
    сама сборка: «книга пересобирается без него — `books html
    <книга>/assets/source`».

    Признак живёт рядом с тем, кто слепок ПИШЕТ. Набранная в другом файле
    строка разошлась бы молча — так и вышло.

    Старая раскладка признаётся своей ТОЖЕ: книги, собранные до переезда,
    наши, и объявлять их чужими неверно.
    """
    import os
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        assert not H.наш_каталог(tmp), "пустой каталог признан нашим"

        os.makedirs(os.path.join(tmp, H.ASSETS))
        open(os.path.join(tmp, H.ASSETS, "run.json"), "w").close()
        assert H.наш_каталог(tmp), (
            "каталог со слепком в кухне не признан своим — пересборка на "
            "месте откажет, и совет из журнала сборки станет невыполним")

    with tempfile.TemporaryDirectory() as tmp:
        open(os.path.join(tmp, "run.json"), "w").close()
        assert H.наш_каталог(tmp), (
            "книга ПРЕЖНЕЙ раскладки объявлена чужой — она наша, просто "
            "собрана до переезда слепка")


def test_the_book_carries_blocks_in_the_order_it_walked_them():
    """Порядок книги СВЕРЯЕТСЯ со списком блоков, а не подразумевается.

    ДЫРА, КОТОРУЮ ЭТО ЗАКРЫВАЕТ. Сборщик обходит `page.blocks` как есть, и
    книга наследует их порядок — ранг модели либо наше правило. Проверялось
    это НИЧЕМ: скептик перевернул обход одной строкой (`reversed`), и полная
    батарея осталась зелёной — 201 проверка, 0 провалов. Книга читалась бы
    задом наперёд. Все три прибора мерят СТРАНИЦЫ детекции, а не собранный
    документ, и потому молчат по построению.

    СТОРОЖ ЛЕГКО СДЕЛАТЬ ТАВТОЛОГИЧНЫМ, и первая редакция такой и была:
    ожидание копилось внутри того же цикла, который оно стережёт, — перевернёшь
    обход, перевернётся и ожидание. Три порчи (reversed, сдвиг на один, потеря
    последнего) не поймались ни одна. Поэтому здесь проверяется не только то,
    что сторож есть, но и что ожидание выводится из `page.blocks` НЕЗАВИСИМО.
    """
    import ast
    import json
    import os
    import tempfile

    import pymupdf
    import support

    from booksmith import detect as _detect
    from booksmith.doc import swap
    from booksmith.models.base import Block, Page

    with tempfile.TemporaryDirectory() as tmp:
        pdf = os.path.join(tmp, "проба.pdf")
        doc = pymupdf.open()
        doc.new_page(width=500, height=700)
        doc.save(pdf)
        doc.close()

        det = os.path.join(tmp, "detect")
        os.makedirs(os.path.join(det, "pages"))
        # Порядок НЕсимметричный: при перевороте он обязан не совпасть сам с
        # собой. На двух блоках переворот заметен, на одном — нет.
        pg = Page(index=0, width=1000, height=1400, dpi=144.0, blocks=[
            Block(block_id=0, box=(50.0, 50.0, 950.0, 300.0), label="text",
                  score=0.9, order=0, content="первый"),
            Block(block_id=1, box=(50.0, 400.0, 950.0, 700.0), label="text",
                  score=0.9, order=1, content="второй"),
            Block(block_id=2, box=(50.0, 800.0, 950.0, 1300.0), label="table",
                  score=0.9, order=2)])
        with open(os.path.join(det, "pages", "0000.json"), "w",
                  encoding="utf-8") as f:
            json.dump(pg.to_json(), f, ensure_ascii=False)
        with open(os.path.join(det, "run.json"), "w", encoding="utf-8") as f:
            json.dump({"source": {"path": pdf,
                                    "sha256": _detect._sha256(pdf)},
                       "raster": {"dpi": 144},
                       "weights": {"layout": None}}, f, ensure_ascii=False)

        out = os.path.join(tmp, "html")
        H.build(det, out, log=lambda *_: None)
        with open(os.path.join(out, "book.html"), encoding="utf-8") as f:
            книга = f.read()

        ждали = [H.anchor_of(0, i) for i in range(3)]
        assert swap.anchors(книга) == ждали, (
            f"книга сложена не в порядке блоков: {swap.anchors(книга)} против "
            f"{ждали}. Порядок книги — это порядок чтения")

    # ОЖИДАНИЕ НЕ СМЕЕТ ВЫВОДИТЬСЯ ИЗ ОБХОДА. Разбором исходника: исполнением
    # тавтологию не поймать — сторож, выведенный из обхода, на здоровом коде
    # ведёт себя ровно так же, как честный.
    t = support.tree("doc/html.py")
    fn = next(n for n in ast.walk(t)
              if isinstance(n, ast.FunctionDef) and n.name == "build")
    циклы = [n for n in ast.walk(fn) if isinstance(n, ast.For)]
    for c in циклы:
        внутри = [n for n in ast.walk(c)
                  if isinstance(n, ast.Call)
                  and isinstance(n.func, ast.Attribute)
                  and isinstance(n.func.value, ast.Name)
                  and n.func.value.id == "ждём"
                  and n.func.attr == "append"]
        assert not внутри, (
            f"ожидание порядка копится ВНУТРИ цикла (строка {внутри[0].lineno}"
            f") — сторож стал тавтологичным: перевернёшь обход, перевернётся "
            f"и ожидание. Так уже было, и три порчи не поймались ни одна")

    # И САМ СТОРОЖ ОБЯЗАН БЫТЬ НА МЕСТЕ. Проверка выше сравнивает порядок
    # своими руками, поэтому снятие сторожа ИЗ СБОРЩИКА она не заметит:
    # книга-то соберётся верно. А сторож нужен не ей, а настоящему прогону —
    # там сравнивать некому. Проверено порчей: `if вышло != ждём` -> `if
    # False` не роняет ни одной проверки.
    сверок = [n for n in ast.walk(fn)
              if isinstance(n, ast.Compare)
              and isinstance(n.left, ast.Name) and n.left.id == "вышло"
              and any(isinstance(o, ast.NotEq) for o in n.ops)]
    assert сверок, (
        "в `build` не осталось сверки `вышло != ждём` — сборщик перестал "
        "проверять, в том ли порядке сложилась книга. Настоящему прогону "
        "сравнивать нечем: приборы мерят страницы детекции, а не документ")
