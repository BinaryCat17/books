"""Прибор, которым в проекте смотрят ГЛАЗАМИ, — и у него не было ни одной
проверки.

Ни `overlay` в `tests/`, ни одной из 158 проверок, ни одной из 134 мутаций.
Цена особая: `books score` врёт числом, и число можно перепроверить другим
числом; `books overlay` врёт КАРТИНКОЙ, а картинку перепроверяют глазами — и
человек уходит уверенный, что видел сам. В этой сессии глазами смотрели
четырежды, и дважды это опрокидывало утверждение, которое держалось числами.

Закреплены четыре дефекта, все найдены аудитом и все воспроизведены:

    --pages считался с НУЛЯ      у `books detect` — с единицы, и диапазонов
                                 `40-42` этот разбор не знал вовсе (падал
                                 голым ValueError). Смотришь не тот лист и не
                                 узнаёшь об этом, а глазами смотрят именно
                                 так: продетектировал пару страниц и глянул

    страница, которой нет у       убрал у модели 3 страницы из 13 — «НЕ НАШЛА
    одной разметки, пропускалась   6» не дрогнуло, а «расхождений» стало
    молча                          МЕНЬШЕ (10 -> 7): модель на вид улучшилась
                                   оттого, что часть её ответа пропала.
                                   `books score` на том же входе отказывается
                                   считать вслух

    одна разметка -> три нуля     «совпало 0, НЕ НАШЛА 0, ЛИШНИХ 0;
                                   расхождения на 0 страницах» при
                                   нарисованных рамках. Ноль от непонимания в
                                   ИТОГОВОЙ строке

    «листов 600» при одном        печаталось `doc.page_count`; три разные
    нарисованном                   величины (страницы книги, листы, рамки)
                                   ходили под одним словом
"""
import json
import os
import tempfile

import support

from booksmith import overlay


def _stand(d, pages=3, model_skip=()):
    """Книга на три листа, истина на всех, вывод модели — кроме `model_skip`."""
    import pymupdf
    pdf = os.path.join(d, "b.pdf")
    doc = pymupdf.open()
    for _ in range(pages):
        doc.new_page(width=200, height=300)
    doc.save(pdf)
    doc.close()
    for name, skip in (("truth", ()), ("model", model_skip)):
        pd = os.path.join(d, name, "pages")
        os.makedirs(pd)
        for i in range(pages):
            if i in skip:
                continue
            with open(os.path.join(pd, f"{i:04d}.json"), "w",
                      encoding="utf-8") as f:
                json.dump({"index": i, "width": 400, "height": 600,
                           "blocks": [{"block_id": 0, "box": [10, 10, 90, 90],
                                       "label": "text", "score": None,
                                       "order": 0, "content": None,
                                       "kind": "none"}]}, f)
    return pdf


def _say(pdf, marks, only=None):
    said = []
    overlay.build(pdf, pdf + ".ov.pdf", marks, only=only, log=said.append)
    return "\n".join(said)


def _drawn_sheets(out_pdf):
    """Какие листы выхода вправду что-то несут. Считано ГЛАЗАМИ ПРИБОРА."""
    import pymupdf
    doc = pymupdf.open(out_pdf)
    got = [i for i, pg in enumerate(doc) if pg.get_drawings()]
    doc.close()
    return got


def test_pages_are_counted_from_one_like_detect():
    """`--pages` здесь считается ТАК ЖЕ, как у `books detect`.

    Разбор один на оба, а не второй экземпляр: `books detect --pages 2` даёт
    лист 0001, и `books overlay --pages 2` обязан нарисовать его же. Прежде
    рисовался 0002 — и молча.

    ЗОВЁМ ЧЕРЕЗ CLI, А НЕ РАЗБОРЩИК НАПРЯМУЮ, и это существо проверки.
    Первая её редакция утверждала `detect.parse_pages("2", 3) == [1]` и потом
    сама передавала этот набор в `build` — то есть меряла, что разборщик
    считает с единицы (это было верно и до починки), и НЕ меряла, что
    `cmd_overlay` его зовёт. Замер скептика: откат `cli.py` целиком и точечная
    мутация прямо на исправленную строку давали НОЛЬ красных проверок.
    Дыра ровно того класса, что чинилась рядом.
    """
    from booksmith import cli
    with tempfile.TemporaryDirectory() as d:
        pdf = _stand(d)
        t = os.path.join(d, "truth", "pages")
        for spec, want in (("2", [1]), ("1-3", [0, 1, 2]),
                           ("1 3", [0, 2])):
            out = os.path.join(d, f"p{spec.replace(' ', '_')}.pdf")
            said = []
            было = cli.log
            cli.log = said.append          # `log` в cli — импортированное имя
            try:
                assert cli.main(["overlay", pdf, "--truth", t,
                                 "--pages", spec, "--out", out]) == 0
            finally:
                cli.log = было
            # В выходе лежат ТОЛЬКО запрошенные листы (иначе `--pages 102` на
            # золотом стенде давал бы 494 МБ), поэтому счёт сверяем двумя
            # величинами: сколько листов вышло и КАКАЯ страница книги стала
            # первой. Вторую прибор обязан назвать сам — молчаливый сдвиг
            # номеров был бы той же бедой, что и сдвиг `--pages` на единицу.
            got = _drawn_sheets(out)
            assert got == list(range(len(want))), (
                f"--pages {spec!r}: в выходе листы {got}, ожидались "
                f"{list(range(len(want)))} подряд с первого")
            s = "\n".join(said)
            assert f"листов нарисовано {len(want)} из 3" in s, s
            if len(want) < 3:
                assert f"это страница {want[0] + 1} книги" in s, (
                    f"--pages {spec!r}: прибор не сказал, какая страница "
                    f"книги стала первой в файле. `books detect` на том же "
                    f"вводе взял бы {want} — смотришь не тот лист и не "
                    f"узнаёшь об этом.\n{s}")


def test_a_page_out_of_the_book_is_loud():
    """Номер за пределами книги — жалоба вслух, а не пустой прогон.

    Прежде свой разбор `overlay` клал число прямо в индекс, а пустой набор
    давал молчаливое «расхождения на 0 страницах».
    """
    from booksmith import cli
    with tempfile.TemporaryDirectory() as d:
        pdf = _stand(d)
        t = os.path.join(d, "truth", "pages")
        try:
            cli.main(["overlay", pdf, "--truth", t, "--pages", "9",
                      "--out", os.path.join(d, "x.pdf")])
        except SystemExit as e:
            assert "3 страниц" in str(e), f"жалоба не про то: {e}"
            return
        raise AssertionError("страница за пределами книги принята молча")


def test_a_page_missing_from_one_markup_is_named():
    """Страница, которой нет у одной разметки, НАЗЫВАЕТСЯ, а не пропускается.

    Умеет провалиться: верните `continue` без счётчика — и лист выйдет
    полным на вид, а числа станут лучше оттого, что часть ответа пропала.
    """
    with tempfile.TemporaryDirectory() as d:
        pdf = _stand(d, model_skip=(1,))
        s = _say(pdf, [(os.path.join(d, "truth", "pages"), "И"),
                       (os.path.join(d, "model", "pages"), "М")])
        assert "У модели НЕТ 1 страниц" in s and "[1]" in s, s
        assert "листов нарисовано 2 из 3" in s, s


def test_a_page_missing_from_the_truth_is_named_too():
    """Зеркальная сторона: дыра в ИСТИНЕ называется так же, как дыра в модели.

    Скептик показал, что чинил я обе стороны, а проверял одну: подмена
    `counts["нет у истины"].append(i)` на `pass` не красила НИ ОДНОЙ из 163
    проверок. Сторож, у которого проверена половина, — половина сторожа.
    """
    with tempfile.TemporaryDirectory() as d:
        pdf = _stand(d)
        os.unlink(os.path.join(d, "truth", "pages", "0001.json"))
        s = _say(pdf, [(os.path.join(d, "truth", "pages"), "И"),
                       (os.path.join(d, "model", "pages"), "М")])
        assert "У истины НЕТ 1 страниц" in s and "[1]" in s, s


def test_one_markup_says_there_is_nothing_to_compare():
    """Одна разметка — «сличать НЕ С ЧЕМ», а не три нуля.

    Три нуля при нарисованных рамках читаются как «всё сошлось». Это тот же
    ноль от непонимания, что «глав 0» вместо «я их не узнал», только в
    итоговой строке.
    """
    with tempfile.TemporaryDirectory() as d:
        pdf = _stand(d)
        s = _say(pdf, [(os.path.join(d, "truth", "pages"), "И")])
        assert "НЕ С ЧЕМ" in s, s
        assert "совпало 0" not in s, f"итог всё ещё врёт нулями:\n{s}"


def test_the_summary_counts_sheets_not_pages_of_the_book():
    """Итог называет НАРИСОВАННЫЕ листы, и рамки — отдельно.

    Прежде печаталось `doc.page_count`: `--pages 102` на золотом стенде давало
    «листов 600» при одном нарисованном.
    """
    with tempfile.TemporaryDirectory() as d:
        pdf = _stand(d)
        s = _say(pdf, [(os.path.join(d, "truth", "pages"), "И")], only=[0])
        assert "листов нарисовано 1 из 3 в книге, рамок 1" in s, s


def test_what_was_not_checked_by_sha256_is_named():
    """Несверенная разметка НАЗЫВАЕТСЯ, а не молчит.

    Прежде печаталось «sha256 сверен для И» — и о том, что «М» не сверен
    вовсе, ни слова: половина сторожа читалась как весь сторож.
    """
    with tempfile.TemporaryDirectory() as d:
        pdf = _stand(d)
        with open(os.path.join(d, "truth", "manifest.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"sha256 pdf": overlay._sha256(pdf)}, f)
        s = _say(pdf, [(os.path.join(d, "truth", "pages"), "И"),
                       (os.path.join(d, "model", "pages"), "М")])
        assert "сверен для И" in s and "НЕ СВЕРЕН для М" in s, s


def test_the_sheet_shouts_at_exactly_what_the_number_calls_extra():
    """«ЛИШНИХ» на листе == «лишняя рамка» в `books score`. Один классификатор.

    ЗАЧЕМ. Прибор делил рамки на крикливые и тихие по одному признаку —
    артефактный ли ярлык, — и кричал оранжевым на всё подряд: на золотом
    стенде 508 рамок, из которых `books score` зовёт лишними 110, а 350 (69%)
    НАРОЧНО оправдывает («на объекте вне замера»). Человек смотрел и выносил
    приговор модели по числу, которое прибор рядом опровергает.

    Умеет провалиться: верните признак по ярлыку — и «ЛИШНИХ» станет больше
    «лишней рамки». Здесь это видно на трёх рамках вместо трёхсот пятидесяти,
    но правило то же, и правило ОДНО: `metrics.extra_kind` зовут оба.
    """
    import json as _j

    from booksmith import metrics

    with tempfile.TemporaryDirectory() as d:
        pdf = _stand(d, pages=1)
        # Истина: один артефакт в замере плюс один ВНЕ замера.
        t = {"index": 0, "width": 400, "height": 600,
             "blocks": [{"block_id": 0, "box": [10, 10, 90, 90],
                         "label": "table", "score": None, "order": 0,
                         "content": None, "kind": "none"}],
             "meta": {"вне замера": [{"box": [200, 200, 300, 300],
                                      "категория": "Vignette",
                                      "разряд": "невыразимо"}]}}
        # Модель: нашла таблицу, плюс рамка НА объекте вне замера, плюс
        # настоящая лишняя в пустоте.
        m = {"index": 0, "width": 400, "height": 600,
             "blocks": [{"block_id": 0, "box": [10, 10, 90, 90],
                         "label": "table", "score": 0.9, "order": 0,
                         "content": None, "kind": "none"},
                        {"block_id": 1, "box": [205, 205, 295, 295],
                         "label": "image", "score": 0.8, "order": 1,
                         "content": None, "kind": "none"},
                        {"block_id": 2, "box": [320, 400, 380, 460],
                         "label": "image", "score": 0.7, "order": 2,
                         "content": None, "kind": "none"}]}
        for name, page in (("truth", t), ("model", m)):
            with open(os.path.join(d, name, "pages", "0000.json"), "w",
                      encoding="utf-8") as f:
                _j.dump(page, f)
        counts = {}
        overlay.build(pdf, os.path.join(d, "o.pdf"),
                      [(os.path.join(d, "truth", "pages"), "И"),
                       (os.path.join(d, "model", "pages"), "М")],
                      log=lambda *a: None)
        c = metrics.compare(os.path.join(d, "truth", "pages"),
                            os.path.join(d, "model", "pages"))
        del counts
        beds = c["беды"] if "беды" in c else {}
        want = beds.get("лишняя рамка", 0)
        said = []
        got = overlay.build(pdf, os.path.join(d, "o2.pdf"),
                            [(os.path.join(d, "truth", "pages"), "И"),
                             (os.path.join(d, "model", "pages"), "М")],
                            log=said.append)["лишних"]
        assert want == 1, f"стенд собран не так: score зовёт лишними {want}"
        assert got == want, (
            f"лист кричит про {got} рамок, а число зовёт лишними {want}. "
            f"Прибор и метрика разошлись на одной и той же рамке — а лист "
            f"судят глазами и переспросить его нечем")


def test_a_changed_label_is_not_painted_like_an_extra_box():
    """Подпись «ярлык: A -> B» и «ЛИШНЯЯ» — РАЗНЫМ цветом.

    Прежде обе брали одну оранжевую константу, и подпись висела над СЕРОЙ
    рамкой: цвет подписи противоречил цвету рамки, к которой она относится.
    Замер глазами на `bench/slovar` стр. 2 (56 таких подписей из 56 пар): из
    двух настоящих «ЛИШНИХ» листа одна была невидима — стояла в трёх пунктах
    от одноимённо окрашенной подписи тем же кеглем.

    Умеет провалиться: сведите цвета обратно.
    """
    assert overlay.ЯРЛЫК != overlay.ЛИШНЯЯ, (
        "смена ярлыка красится как лишняя рамка — оранжевый перестаёт "
        "значить «модель нашла лишнее», и настоящая лишняя в нём тонет")
    assert overlay.ЯРЛЫК != overlay.СОВПАЛО, (
        "подпись слилась с рамкой, к которой относится")
