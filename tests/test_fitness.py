"""Прибор ГОДНОСТИ: чем его можно выиграть, не найдя ничего.

ПОЧЕМУ ЭТОТ ФАЙЛ ПОЯВИЛСЯ. `books fitness` — один из трёх приборов проекта, и
его выводом уже выбран детектор и оценён вендорский конвейер docling. При этом
`grep fitness tests/` не находил НИ ОДНОЙ строки: прибор, которым выбирают
модель, не был проверен ничем, кроме собственной батареи, а батарея портила
только вывод модели — ни истину, ни свои пороги.

Что здесь закреплено, всё — воспроизведённые дефекты, а не гипотезы:

  * рамка, уехавшая за левый верхний угол, накрывала две трети листа
    (отрицательный конец среза numpy отсчитывается ОТ КОНЦА);
  * пиксель, накрытый и артефактной рамкой, и текстовой, считался ДВАЖДЫ, и
    задвоенная разметка переписывала дорогую беду «потеряно» в дешёвую
    «уехал текстом». Полный проход: `bench/annopage` 90 -> 86, `bench/hard`
    44 -> 42 — шесть записей, но РАЗНЫХ объектов четыре (hard собран из тех
    же книг), и настоящая беда среди них одна: стр. 94 `table`, 14% чернил
    под открытым небом. Семь МАЛЫХ стендов дали ноль, и по этому нулю дефект
    был объявлен неопасным — ровно то, чего выборка не находит;
  * пустой растр печатался как «вне всех рамок 100.0% — это то, что исчезнет
    из HTML», то есть ноль от непонимания под видом замера;
  * «истина не подана» печаталось и тогда, когда истина подана, а артефактов в
    ней нет: два разных нуля одной строкой;
  * из ПЯТИ порогов отчёт объявлял один, батарея проверяла два, а dpi —
    единицу измерения всего здесь считаемого — не объявлял никто;
  * строка о слепоте к слиянию стояла ПОСЛЕ возвратов по истине, то есть в
    режиме без истины — которым и меряют настоящие сканы — не печаталась;
  * память растра не экономила ничего ровно на том стенде, ради которого
    заведена, и дважды подряд: потолком в страницах с полной очисткой, потом
    потолком в байтах с вытеснением старейшего.

Отчёт проверяется отдельно от чисел нарочно: батарея порчи смотрит на ЧИСЛА и
про печать сказать не может ничего по построению.

ЗАМЕР ЗДЕСЬ НА НАСТОЯЩИХ ФОРМАХ СТРАНИЦ, и это не педантизм. Проверка памяти,
писанная на игрушечных 64x64, была зелёной на коде, который не экономил
ничего: потолок в байтах на таких страницах не связывает никогда, и стенд
прятал ровно тот дефект, ради которого заведён.
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import numpy as np                                          # noqa: E402
import pymupdf                                              # noqa: E402

import support                                              # noqa: E402
from booksmith import fitness                               # noqa: E402


# --- чем меряем ------------------------------------------------------------
# Страница строится тут же и целиком: 200x200 точек, чернила — прямоугольник
# с известными краями. Ни ONNX, ни весов, ни стенда на диске; вся проверка
# укладывается в сотые доли секунды, и каждое ожидаемое число выводится из
# геометрии, а не списывается с прогона.

def _book(rects, out):
    doc = pymupdf.open()
    pg = doc.new_page(width=200, height=200)
    for r in rects:
        pg.draw_rect(pymupdf.Rect(*r), color=(0, 0, 0), fill=(0, 0, 0))
    pdf = os.path.join(out, "p.pdf")
    doc.save(pdf)
    doc.close()
    return pdf


def _pages(blocks, out, name):
    d = os.path.join(out, name)
    os.makedirs(d, exist_ok=True)
    p = {"index": 0, "width": 200, "height": 200, "dpi": 72.0,
         "blocks": [{"block_id": j, "box": list(b), "label": lab, "score": None,
                     "order": j, "content": None, "kind": "none"}
                    for j, (b, lab) in enumerate(blocks)]}
    import json
    with open(os.path.join(d, "0000.json"), "w", encoding="utf-8") as f:
        json.dump(p, f, ensure_ascii=False)
    return d


def _said(res):
    out = []
    fitness.report(res, log=out.append)
    return "\n".join(out)


# --- нарезка рамок ---------------------------------------------------------

def test_box_off_the_sheet_covers_nothing():
    """Рамка целиком за листом не накрывает ни пикселя.

    Прежняя нарезка `m[max(0, int(y0)):int(y1) + 1]` при отрицательном `y1`
    отсчитывала конец ОТ КОНЦА массива: рамка [-40, -40, -20, -20] накрывала
    6561 пиксель из 10000. Метрику можно было выиграть мусором.
    """
    assert int(fitness._mask((100, 100), [[-40, -40, -20, -20]]).sum()) == 0
    assert fitness._clip((100, 100), [-40, -40, -20, -20]) is None


def test_box_hanging_over_the_edge_is_cut_by_the_sheet():
    """А наполовину свесившаяся — накрывает ровно свою часть листа."""
    m = fitness._mask((100, 100), [[-10, -10, 9, 9]])
    assert int(m.sum()) == 100, int(m.sum())          # 10x10 в углу
    m = fitness._mask((100, 100), [[90, 90, 500, 500]])
    assert int(m.sum()) == 100, int(m.sum())


# --- два счёта одного пикселя ----------------------------------------------

def test_pixel_under_two_boxes_counts_once():
    """Объект, у которого половина чернил не накрыта ничем, не «уехал текстом».

    Задвоенная разметка (одна и та же область отдана артефактом и текстом) —
    не выдумка: у сырого docling-heron 4435 задвоенных пар. Прежняя формула
    `t_kept + kept` считала общий пиксель дважды, сумма переваливала за
    порог, и объект получал диагноз «не потерян, чинится ярлыком».
    """
    with tempfile.TemporaryDirectory() as tmp:
        pdf = _book([(20, 20, 120, 120)], tmp)
        truth = _pages([((20, 20, 120, 120), "table")], tmp, "truth")
        # рамка артефакта и текстовая — ОДНА И ТА ЖЕ левая половина объекта
        det = _pages([((20, 20, 70, 120), "table"),
                      ((20, 20, 70, 120), "text")], tmp, "det")
        r = fitness.measure(pdf, det, truth)
        assert r["torn"] == 1, r
        assert r["left_as_text"] == 0, r
        # ...а когда текстовая рамка и правда держит остаток — диагноз верен
        det2 = _pages([((20, 20, 70, 120), "table"),
                       ((60, 20, 120, 120), "text")], tmp, "det2")
        assert fitness.measure(pdf, det2, truth)["left_as_text"] == 1


# --- нули ------------------------------------------------------------------

def test_blank_page_is_not_a_total_loss():
    """Пустой растр — «мерить нечего», а не «потеряна вся книга»."""
    with tempfile.TemporaryDirectory() as tmp:
        pdf = _book([], tmp)
        det = _pages([((10, 10, 50, 50), "table")], tmp, "det")
        said = _said(fitness.measure(pdf, det))
        assert "нечего мерить" in said, said
        assert "исчезнет из HTML" not in said, said


def test_truth_without_artefacts_is_not_a_missing_truth():
    """Истина подана, артефактов в ней нет — это ДРУГОЙ ноль."""
    with tempfile.TemporaryDirectory() as tmp:
        pdf = _book([(20, 20, 120, 120)], tmp)
        det = _pages([((20, 20, 120, 120), "text")], tmp, "det")
        truth = _pages([((20, 20, 120, 120), "text")], tmp, "truth")
        with_truth = _said(fitness.measure(pdf, det, truth))
        without = _said(fitness.measure(pdf, det))
        assert "истина подана" in with_truth, with_truth
        assert "истина не подана" in without, without
        assert with_truth != without


def test_object_without_ink_is_a_bench_defect_not_a_score():
    """Объект истины без чернил не считан ни в «цел», ни в «порван»."""
    with tempfile.TemporaryDirectory() as tmp:
        pdf = _book([(20, 20, 120, 120)], tmp)
        det = _pages([((20, 20, 120, 120), "table")], tmp, "det")
        truth = _pages([((20, 20, 120, 120), "table"),
                        ((150, 150, 190, 190), "table")], tmp, "truth")
        r = fitness.measure(pdf, det, truth)
        assert r["objects"] == 1 and r["empty_objects"] == 1, r
        assert r["intact"] + r["almost_intact"] + r["bitten"] + r["torn"] == 1, r
        assert "дефект стенда" in _said(r)


def test_page_the_model_did_not_mark_is_loud():
    """Молчание модели — отказ, а не «чернил не потеряно»."""
    with tempfile.TemporaryDirectory() as tmp:
        pdf = _book([(20, 20, 120, 120)], tmp)
        truth = _pages([((20, 20, 120, 120), "table")], tmp, "truth")
        det = os.path.join(tmp, "det")
        os.makedirs(det)
        import json
        with open(os.path.join(det, "0001.json"), "w", encoding="utf-8") as f:
            json.dump({"index": 1, "width": 200, "height": 200, "dpi": 72.0,
                       "blocks": []}, f)
        try:
            fitness.measure(pdf, det, truth)
        except Exception as e:
            assert "не разметила страницу" in str(e), e
        else:
            assert False, "молчание модели прошло молча"


# --- линейка ---------------------------------------------------------------

def test_report_declares_the_whole_ruler():
    """Все четыре порога и dpi — в отчёте, а не только «цел».

    Величина без объявленной линейки уже стоила проекту невоспроизводимого
    «лишних прыжков 7.0 -> 1.3». Здесь единица измерения — пиксель растра,
    то есть число зависит от `PAGE_DPI`: те же рамки на bench/real/tables20.pdf
    дают «чернил под артефактом» 24.83% при 144 dpi и 25.99% при 600.
    """
    with tempfile.TemporaryDirectory() as tmp:
        pdf = _book([(20, 20, 120, 120)], tmp)
        det = _pages([((20, 20, 120, 120), "table")], tmp, "det")
        said = _said(fitness.measure(pdf, det))
        assert "72 dpi" in said, said
        # ПОРОГОВ ПЯТЬ, И СРАВНЕНИЕ ТОЧНОЕ. Здесь спрашивались четыре из пяти
        # (`EDGE` печатался только при потерях, и выкинуть его строку можно
        # было, не покраснев), да ещё и подстрокой: `BITTEN = 0.8` проходило
        # по «0.80» случайно, а `INK = 160` прошло бы и по «1600».
        import re
        nums = re.findall(r"\d+(?:\.\d+)?", said)
        for v in (fitness.INK, fitness.WHOLE, fitness.ALMOST, fitness.BITTEN):
            want = f"{v:.2f}" if isinstance(v, float) else str(v)
            assert want in nums, (want, nums)
        assert f"{fitness.EDGE * 100:.0f}" in nums, (fitness.EDGE, nums)
        assert "полоса у края" in said, said


def test_report_says_out_loud_that_it_is_blind_to_merging():
    """Прибор обязан сам называть, чего не видит, и звать соседа по имени.

    И называть ОБЯЗАТЕЛЬНО без истины тоже: строка стояла после обоих
    `return` по истине, а `books fitness книга.pdf --detect …` — ровно тот
    режим, которым меряют настоящие сканы, и им прибор про слепоту молчал.
    """
    with tempfile.TemporaryDirectory() as tmp:
        pdf = _book([(20, 20, 120, 120)], tmp)
        det = _pages([((20, 20, 120, 120), "table")], tmp, "det")
        truth = _pages([((20, 20, 120, 120), "table")], tmp, "truth")
        for res in (fitness.measure(pdf, det, truth), fitness.measure(pdf, det),
                    fitness.measure(_book([], tmp), det)):
            said = _said(res)
            assert "слияние" in said.lower() and "books score" in said, said


def test_the_number_that_grows_when_boxes_merge():
    """«Приехал не в одиночку» — единственное число, растущее от слияния.

    Все прочие от слияния улучшаются (bench/hard36: цел 365 -> 385, порван
    28 -> 13, чернил объектов 94.8% -> 96.1%), и по одним им слияние выглядит
    выгодным. Это росло там же 309 -> 385.
    """
    with tempfile.TemporaryDirectory() as tmp:
        pdf = _book([(20, 20, 80, 80), (110, 20, 170, 80)], tmp)
        truth = _pages([((20, 20, 80, 80), "table"),
                        ((110, 20, 170, 80), "table")], tmp, "truth")
        apart = _pages([((20, 20, 80, 80), "table"),
                        ((110, 20, 170, 80), "table")], tmp, "apart")
        one = _pages([((20, 20, 170, 80), "table")], tmp, "one")
        a = fitness.measure(pdf, apart, truth)
        b = fitness.measure(pdf, one, truth)
        assert a["intact"] == b["intact"] == 2, (a, b)          # слепые числа молчат
        assert a["in_one_box"] == b["in_one_box"] == 2
        assert a["arrived_with_company"] == 0, a         # а это — говорит
        assert b["arrived_with_company"] == 2, b
        assert a["boxes_with_many_objects"] == 0
        assert b["boxes_with_many_objects"] == 1
        assert "не в одиночку 2" in _said(b)


def test_the_ink_threshold_has_one_meaning_in_both_homes():
    """`fitness.INK` и `synth.INK` — одно число в двух домах.

    Стенд меряет свою истину этим порогом, метрика — вывод модели. Разойдись
    копии, и «доехало 94.8% чернил» считалось бы не про те чернила, которыми
    размечена истина. Свести импортом можно (cv2 в `synth` грузится ВНУТРИ
    функций, `import booksmith.synth` стоит 2 мс), но метрика не должна
    зависеть от того, кто рисует стенд, — поэтому договор держит проверка.
    """
    from booksmith import synth
    assert fitness.INK == synth.INK, (fitness.INK, synth.INK)


def test_merging_two_objects_into_one_box_does_not_lower_the_numbers():
    """Слепота, закреплённая замером: слияние прибор считает УЛУЧШЕНИЕМ.

    Проверка не о том, что так правильно, а о том, что так есть. Разойдись
    это с текстом отчёта — соврёт либо отчёт, либо прибор.
    """
    with tempfile.TemporaryDirectory() as tmp:
        pdf = _book([(20, 20, 80, 80), (110, 20, 170, 80)], tmp)
        truth = _pages([((20, 20, 80, 80), "table"),
                        ((110, 20, 170, 80), "table")], tmp, "truth")
        # обе таблицы обведены порознь, но у правой срезан край
        apart = _pages([((20, 20, 80, 80), "table"),
                        ((110, 20, 150, 80), "table")], tmp, "apart")
        one = _pages([((20, 20, 170, 80), "table")], tmp, "one")
        a = fitness.measure(pdf, apart, truth)
        b = fitness.measure(pdf, one, truth)
        assert a["intact"] == 1 and a["torn"] == 1, a
        assert b["intact"] == 2 and b["torn"] == 0, b
        assert b["in_one_box"] > a["in_one_box"]


# --- память растра ---------------------------------------------------------

# Страница ЗОЛОТОГО СТЕНДА, а не игрушечная: 1700x2200 — это 3.57 МиБ булевой
# маской и 457 КиБ упакованной, ровно порядок настоящей (средняя страница
# bench/annopage при 144 dpi — 5.00 МиБ и 640 КиБ). На игрушечных 64x64
# потолок в байтах не связывает НИКОГДА, и проверка, писанная на них, прятала
# ровно тот дефект, ради которого заведена.
_PAGE = (2200, 1700)


def _memory_probe(pages, cap, passes):
    """Сколько рендеров стоят `passes` последовательных проходов по книге."""
    rendered = {"n": 0}
    real, cap0 = fitness._ink, fitness._INK_CACHE_MAX_BYTES

    def spy(page, dpi):
        rendered["n"] += 1
        return np.zeros(_PAGE, bool)

    class Doc:
        def __getitem__(self, i):
            return None

    fitness._ink = spy
    fitness._INK_CACHE_MAX_BYTES = cap
    fitness._INK_CACHE.clear()
    fitness._INK_CACHE_BYTES = 0
    try:
        for _ in range(passes):
            for i in range(pages):
                fitness._ink_of("книга.pdf", Doc(), i, 144)
        return rendered["n"]
    finally:
        fitness._ink = real
        fitness._INK_CACHE_MAX_BYTES = cap0
        fitness._INK_CACHE.clear()
        fitness._INK_CACHE_BYTES = 0


def test_ink_memory_does_not_thrash_on_a_book_bigger_than_the_cap():
    """Книга больше потолка считается наполовину из памяти, а не заново целиком.

    Вытеснение при ПОСЛЕДОВАТЕЛЬНОМ обходе промахивается по построению: всё,
    что вытеснено к концу прохода, нужно в начале следующего. Обе прежние
    редакции — потолок в 64 страницы с полной очисткой и потолок в байтах с
    вытеснением старейшего — давали ровно столько рендеров, сколько без памяти
    вовсе. Симуляция на НАСТОЯЩЕМ следе обращений (23 прохода, снятые с самой
    батареи, с их порогами чернил) и настоящих формах страниц золотого стенда,
    600 страниц, потолок 512 МиБ: без памяти 13800 рендеров, вытеснением 2400,
    удержанием набранного 1800 — оно же идеал (три прохода: пороги 160, 0 и
    256 дают три разные маски).
    """
    page = (_PAGE[0] * _PAGE[1] + 7) // 8
    held, pages, passes = 4, 10, 3
    n = _memory_probe(pages, held * page, passes)
    # первый проход платит за всё, дальше платит только то, что не влезло
    assert n == pages + (passes - 1) * (pages - held), n
    assert n < pages * passes, "память не сэкономила ничего — это промашка"
    assert n > pages, "стенд подобран так, что потолок не связывает"


def test_ink_memory_pays_nothing_twice_when_the_book_fits():
    """Книга по размеру — каждая страница рендерится ровно один раз."""
    page = (_PAGE[0] * _PAGE[1] + 7) // 8
    assert _memory_probe(10, 10 * page, 5) == 10


def test_ink_memory_makes_room_for_the_next_book():
    """Прошлая книга уступает место следующей, а своя — не уступает.

    `_INK_CACHE` — глобаль модуля, и процесс, меряющий больше одной книги
    (восемь стендов подряд — обычное дело и для человека, и для проверок),
    получал вот что: книга А забивает потолок, книге Б не достаётся НИ БАЙТА.
    Симуляция на настоящем следе обращений и настоящих формах страниц,
    потолок 512 МиБ, две книги по 600 страниц: удержанием набранного 15600
    рендеров, вытеснением подряд 4200, выселением ЧУЖИХ книг 3600 — идеал.
    Внутри книги вытеснять по-прежнему нельзя: обход последовательный, и
    вытесненное нужно на следующем проходе (одна книга: 1800 против 2400).
    """
    page = (_PAGE[0] * _PAGE[1] + 7) // 8
    real, cap0 = fitness._ink, fitness._INK_CACHE_MAX_BYTES
    rendered = {"n": 0}

    def spy(pg, dpi):
        rendered["n"] += 1
        return np.zeros(_PAGE, bool)

    class Doc:
        def __getitem__(self, i):
            return None

    fitness._ink = spy
    fitness._INK_CACHE_MAX_BYTES = 4 * page      # места ровно на одну книгу
    fitness._INK_CACHE.clear()
    fitness._INK_CACHE_BYTES = 0
    try:
        for book in ("А.pdf", "Б.pdf"):
            for _ in range(3):
                for i in range(4):
                    fitness._ink_of(book, Doc(), i, 144)
        # каждая книга отрендерена по разу: вторая вытеснила первую, но
        # ВНУТРИ книги ни одна страница не считана дважды
        assert rendered["n"] == 8, rendered["n"]
    finally:
        fitness._ink = real
        fitness._INK_CACHE_MAX_BYTES = cap0
        fitness._INK_CACHE.clear()
        fitness._INK_CACHE_BYTES = 0


def test_the_cap_holds_the_bench_it_was_raised_for():
    """Потолок обязан вмещать золотой стенд ЦЕЛИКОМ — иначе он ничего не даёт.

    Число потолка выведено из этого стенда замером, и связь обязана быть
    проверяемой: здесь стояло «460 МБ булевыми и 58 МБ упакованными, влезают
    целиком», мимо в шесть с половиной раз, и не влезали.
    """
    # ЧИТАЕТСЯ `truth/`, А НЕ `detect/pages`. Второй лежит под `.gitignore`
    # (`bench/*/detect/pages/`), и на свежем клоне проверка молча пропускалась
    # — а под мутацией пропуск считается НЕ покрасневшей проверкой, так что
    # мутация «потолок опущен ниже золотого стенда» печаталась НЕ ПОЙМАНА и
    # `--selfcheck` возвращал 1. Формы страниц лежат и в `truth/`: те же 600
    # файлов, в git, сумма ровно та же.
    import json
    d = os.path.join(os.path.dirname(HERE), "bench", "annopage", "truth")
    if not os.path.isdir(d):
        support.skip("нет bench/annopage/truth: золотой стенд не собран")
    packed = 0
    for name in sorted(os.listdir(d)):
        if not name.endswith(".json") or name == "run.json":
            continue
        with open(os.path.join(d, name), encoding="utf-8") as f:
            p = json.load(f)
        packed += (p["height"] * p["width"] + 7) // 8
    assert packed <= fitness._INK_CACHE_MAX_BYTES, (
        f"стенд {packed / 2 ** 20:.0f} МиБ упакованным не влезает в потолок "
        f"{fitness._INK_CACHE_MAX_BYTES / 2 ** 20:.0f} МиБ")


def test_ink_threshold_is_part_of_the_memory_key():
    """Сдвинули порог — маску считать заново, иначе живой порог мёртв на вид."""
    rendered = {"n": 0}
    real = fitness._ink

    def spy(page, dpi):
        rendered["n"] += 1
        return np.zeros((8, 8), bool)

    class Doc:
        def __getitem__(self, i):
            return None

    fitness._ink = spy
    old = fitness.INK
    try:
        fitness._INK_CACHE.clear()
        fitness._INK_CACHE_BYTES = 0
        fitness._ink_of("книга.pdf", Doc(), 0, 144)
        fitness._ink_of("книга.pdf", Doc(), 0, 144)
        assert rendered["n"] == 1
        fitness.INK = old + 1
        fitness._ink_of("книга.pdf", Doc(), 0, 144)
        assert rendered["n"] == 2, rendered["n"]
    finally:
        fitness.INK = old
        fitness._ink = real
        fitness._INK_CACHE.clear()
        fitness._INK_CACHE_BYTES = 0


# --- батарея ---------------------------------------------------------------

def test_battery_counts_what_it_could_not_measure():
    """«Непойманных 0» при пяти непомеренных пробах — это слово, а не число.

    Без истины большинство проб мерить нечем, и итог обязан назвать сколько
    именно: иначе батарея выглядит зелёной, померив меньше половины.

    Проверяется АРИФМЕТИКА итога, а не литерал: сколько проб названо «нет
    данных», столько и обязано стоять в «нечем мерить», и померенных без
    истины обязано быть заметно меньше. Литерал «нечем мерить 0» тут врал бы
    сам: на книге из одной таблицы разряды «почти цел» и «надкушен» пусты, и
    двум пробам порогов мерить нечем честно.
    """
    def counts(*a):
        out = []
        bad = fitness.mutations(*a, log=out.append)
        tail = out[-1]
        got = dict(zip(("probes", "measured", "unmeasurable"),
                       (int(w) for w in tail.replace(",", " ").split()
                        if w.isdigit())))
        return bad, out, tail, got

    with tempfile.TemporaryDirectory() as tmp:
        pdf = _book([(20, 20, 120, 120)], tmp)
        det = _pages([((20, 20, 120, 120), "table")], tmp, "det")
        truth = _pages([((20, 20, 120, 120), "table")], tmp, "truth")
        # Считаются строки ПРОБ, а не весь вывод: итог сам поминает «нет
        # данных», отсылая к ним, и, посчитанный вместе с ними, давал бы на
        # одну молчащую пробу больше, чем было.
        bad, out, tail, got = counts(pdf, det, truth)
        assert bad == 0, tail
        silent = sum("нет данных" in l for l in out[:-1])
        assert got["probes"] == got["measured"] + got["unmeasurable"], tail
        assert got["unmeasurable"] == silent, (tail, silent)
        bad2, out2, tail2, got2 = counts(pdf, det)
        assert bad2 == 0, tail2
        assert sum("нет данных" in l for l in out2[:-1]) == got2["unmeasurable"], tail2
        # без истины мерить нечем ГОРАЗДО большему числу проб, и это видно
        assert got2["measured"] < got["measured"] / 2, (tail, tail2)


def test_battery_corrupts_all_three_sides():
    """Вывод модели, ИСТИНА и СВОИ пороги — каждый порознь.

    Двинутые разом, они прячут инертный: метрика, безразличная к истине,
    меряет один свой вход, а мёртвый порог печатается наравне с живым.
    """
    with tempfile.TemporaryDirectory() as tmp:
        pdf = _book([(20, 20, 120, 120)], tmp)
        det = _pages([((20, 20, 120, 120), "table")], tmp, "det")
        truth = _pages([((20, 20, 120, 120), "table")], tmp, "truth")
        out = []
        fitness.mutations(pdf, det, truth, log=out.append)
        said = "\n".join(out)
        assert "истина сдвинута" in said, said        # третья сторона
        assert "порог чернил" in said, said           # вторая
        assert "уехали за левый верхний угол" in said, said
        assert "слиты в одну" in said, said
        assert "отдана ещё и текстовой" in said, said
