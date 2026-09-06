"""`books read` — второй уровень: пройти книгу и заполнить содержимое блоков.

ПРОДУКТ — ТОТ ЖЕ `pages/*.json`, ЧТО У ДЕТЕКЦИИ, и это главное решение здесь.
Не новый формат, а тот же самый: те же рамки, те же ярлыки, тот же порядок,
только `content` и `kind` заполнены. Отсюда всё остальное достаётся даром и
проверено по коду, а не обещано:

    books html  — печатает <p> при непустом `content` У ТЕКСТОВОГО блока,
                  картинку иначе. Здесь стояло, что это верно для всех
                  блоков, — неверно: артефакт рисуется картинкой независимо
                  от содержимого (`if role == "артефакт" or not b.content`),
                  и это ВЕРНО по замыслу. Замена артефакта обязана быть
                  обратимой и записанной в журнал, а пересборка книги журнала
                  не знает. Прочитанные таблицы и формулы ставит
                  `books apply --from`, по одной и с откатом
    books text  — `measure(truth_dir, pages_dir)` читает ровно такой каталог
    books score, books fitness, books overlay, books replay — тоже

Всякий свой формат стоил бы шести переходников. Их здесь нет.

НАБЛЮДЁННОЕ ЖИВЁТ СБОКУ. `content` несёт БАЙТЫ МОДЕЛИ и ничего больше.
Секунды, токены, причина остановки, догадка о виде, отказ доставки — всё в
`answers/*.json` рядом, связано с блоком по якорю. Правило проекта, и оно уже
стоило девяти пропусков из тридцати трёх, когда пометки дописывались в текст.

ЧТО ЗДЕСЬ ОБЯЗАНО ПАДАТЬ ВСЛУХ, А НЕ МОЛЧАТЬ:

  * ярлык, которому чтец не назначил маршрута (`Reader.cover`) — иначе класс
    новых весов поехал бы не тем промтом и записался чтением;
  * адрес, отвечающий ЧУЖИМ именем модели (`Transport.check`) — иначе слепок
    назовёт одну модель при ответах другой;
  * ноль блоков к чтению — пустой прогон не должен выглядеть успешным;
  * каталог детекции без `run.json` или с чужими страницами;
  * PDF, чей sha256 разошёлся со слепком детекции: рамки считаны по одному
    файлу, а режем из другого.

ПЯТЬ РАЗНЫХ НУЛЕЙ, И ОНИ СЧИТАЮТСЯ ПОРОЗНЬ. Слить их значит напечатать
«прочитано 0» там, где смысл каждый раз другой:

    не спрошено       — маршрут пуст с объявленной причиной (рисунки)
    отказ доставки    — ответа не было вовсе: обрыв, таймаут, код не 200
    модель промолчала — ответ пришёл, а в нём пусто
    оборвано потолком — `finish="length"`; порванный OTSL выглядит целым
    прочитано         — единственный случай, когда `content` непуст
"""
import glob
import json
import os
import re
import shlex
import sys
import time
from concurrent.futures import ThreadPoolExecutor

from . import Ask, Reader, Transport
from .. import otsl, policy
from ..doc import crop
from ..models.base import Page
from ..run import knobs, stamp

# Реестр чтецов. Объявлен списком по той же причине, что и реестр детекторов:
# пока имя модели зашито в импорт, вопрос «а не лучше ли другая» нельзя даже
# поставить. Новый чтец — строка здесь и один файл рядом с моделью.
READERS = ("paddleocr-vl",)


def log(*a):
    print(f"[{time.strftime('%H:%M:%S')}]", *a, flush=True)


def build_reader(policy_name: str) -> Reader:
    name = knobs.knob("VLM_READER")
    if name == "paddleocr-vl":
        from ..models.paddleocr_vl.reader import PaddleOcrVl
        return PaddleOcrVl(policy_name)
    raise SystemExit(
        f"VLM_READER={name!r}: знаю только {READERS}. Молчаливый откат на "
        f"первый попавшийся означал бы, что опечатка в имени чтеца считается "
        f"успешным прогоном, а слепок назовёт не ту модель.")


def _sniff(text: str) -> str:
    """ДОГАДКА о виде ответа. Живёт СБОКУ и ничего не решает.

    Вид содержимого объявляет ПРОМТ (см. `read/__init__.py`), а не ответ:
    нюхать его значило бы чинить модель — таблица, отданная прозой, молча
    переехала бы в разряд текста, и ошибка ЯРЛЫКА при верной рамке
    растворилась бы в «модель так читает». Поэтому догадка не подменяет
    объявленное, а лишь ложится рядом; её расхождение с объявленным — именной
    счётчик, по которому и станет видно, что пора менять объявление.
    """
    if not text:
        return "пусто"
    t = text.strip()
    if otsl.looks_like(t):
        return "otsl"
    if "<table" in t.lower() or "<td" in t.lower():
        return "html"
    # ЛАТЕХ УЗНАЁТСЯ ШИРЕ, чем по трём приметам. Замер прежней редакции: из
    # восьми правдоподобных ответов модели на формулу шесть объявлялись
    # «text» (`x^{2}+y^{2}=z^{2}`, `\\alpha + \\beta`, `\\sum_{i=1}^{n} a_i`,
    # `A_{ij} = B_{ij}`), и счётчик «вид не тот, что обещан» рос на каждой
    # формуле, требуя поменять ВЕРНОЕ объявление. Прибор, врущий в сторону
    # тревоги, ничем не лучше врущего в сторону покоя.
    if (t.startswith("$") or re.search(r"\\[A-Za-z]{2,}", t)
            or re.search(r"[_^]\{", t) or re.search(r"[A-Za-z0-9)\]]\^[A-Za-z0-9{]", t)):
        return "latex"
    return "text"


def crop_dpi_for(box, page_dpi: float, native: float | None,
                 window, sheet=None) -> tuple[float, str]:
    """Какой резкостью резать ИМЕННО ЭТОТ блок, и почему именно такой.

    ПРАВИЛО, А НЕ ЧИСЛО. Столько, сколько в скане ЕСТЬ (`native`), но не
    больше, чем модель съест (`window` — её собственные границы). Ни одна из
    трёх величин не выбрана нами: резкость приходит от скана, границы от
    модели, размер рамки от детектора.

    Почему не «побольше»: выше своей решётки прибавляются не чернила, а
    догадка растеризатора, и модель всё равно ужмёт вырезку обратно — мы
    платили бы вдвое за то, чтобы сжать выдуманное. Почему не «поменьше»:
    замер на `bench/slovar` при резкости детекции — 555 вырезок из 566 ниже
    нижней границы модели, то есть в девяти случаях из десяти она растягивала
    наши чернила сама.

    ВВЕРХ ВЫШЕ СВОЕЙ РЕШЁТКИ НЕ ПОДНИМАЕМСЯ НИКОГДА, даже когда блок мельче
    нижней границы. Поднять значило бы выдумать точки и назвать это чтением;
    вместо этого случай считается числом («мельче окна модели»), и пусть его
    объяснит стенд.
    """
    base = float(native or page_dpi)
    if not window:
        return base, "своя резкость скана (границ модели нет)"
    lo, hi = window
    # СЧИТАЕМ ПО ТОМУ, ЧТО ВПРАВДУ ВЫРЕЖЕТСЯ. Рамка модели может вылезти за
    # лист, а `crop.cut` режет ПЕРЕСЕЧЕНИЕ с ним; считая резкость по полной
    # рамке, мы зажимали бы её под размер, которого на бумаге нет, и сильно
    # вылезшая рамка получала бы резкость НИЖЕ той, что позволяет окно модели.
    # На стенде таких рамок 28 из 33 640 и вылеты не больше 4.8 пикселя, так
    # что настоящими данными это пока не поймано — но правило должно считать по
    # тому же прямоугольнику, по которому режет, иначе два числа разойдутся
    # молча и без предупреждения.
    x0, y0, x1, y1 = box
    if sheet is not None:
        sx0, sy0, sx1, sy1 = sheet
        x0, y0 = max(x0, sx0), max(y0, sy0)
        x1, y1 = min(x1, sx1), min(y1, sy1)
    w = (x1 - x0) / page_dpi                  # дюймы
    h = (y1 - y0) / page_dpi
    if w <= 0 or h <= 0:
        return base, "native_scan_dpi"
    at_base = w * base * h * base
    if at_base > hi:
        # Ужать до верхней границы модели: всё, что сверх, она выбросит сама.
        return (hi / (w * h)) ** 0.5, "downscaled_to_model_max"
    if at_base < lo:
        return base, "below_model_min"
    return base, "native_scan_dpi"


def _gen_params() -> dict:
    """Параметры порождения. Уезжают в слепок целиком, полем «порождение»."""
    return {"temperature": float(knobs.knob("VLM_TEMPERATURE")),
            "max_tokens": int(knobs.knob("VLM_MAX_TOKENS")),
            "top_p": float(knobs.knob("VLM_TOP_P")),
            "seed": int(knobs.knob("VLM_SEED"))}


def _detect_facts(detect_dir: str) -> dict:
    p = os.path.join(detect_dir, "run.json")
    if not os.path.exists(p):
        raise SystemExit(
            f"в {detect_dir} нет run.json — это не каталог `books detect`. "
            f"Чтение без слепка детекции не знает ни книги, ни dpi, которым "
            f"считаны рамки, и порезало бы вырезки не по тем координатам.")
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def read_book(detect_dir: str, out_dir: str, reader: Reader,
              transport: Transport, resume: bool = True,
              pages_want=None, log=log, pdf: str | None = None) -> dict:
    """Пройти книгу и заполнить содержимое блоков. Возвращает величины.

    `pdf` — где книга лежит СЕЙЧАС. Слепок детекции хранит путь, по которому
    её читали, и на арендованной машине этого пути нет: каталог там свой, а
    файл приезжает под именем `input.pdf`. Поэтому путь можно назвать, а вот
    СВЕРКА sha256 остаётся обязательной при любом пути — она про то, та ли это
    книга, а не про то, где она лежит.
    """
    import pymupdf

    facts = _detect_facts(detect_dir)
    pdf = pdf or facts["source"]["path"]
    if not os.path.exists(pdf):
        raise SystemExit(f"нет исходника {pdf}, названного слепком детекции")
    got = stamp.sha256(pdf)
    if got != facts["source"]["sha256"]:
        raise SystemExit(
            f"{pdf}: sha256 {got[:12]} против {facts['source']['sha256'][:12]} "
            f"в слепке детекции. Рамки считаны по ДРУГОМУ файлу; вырезки "
            f"поехали бы не по тем координатам, а ответ выглядел бы чтением.")
    page_dpi = float(facts["raster"]["dpi"])

    files = sorted(glob.glob(os.path.join(detect_dir, "pages", "*.json")))
    if not files:
        raise SystemExit(f"в {detect_dir} нет страниц — сначала books detect")

    # ЧУЖИЕ СТРАНИЦЫ ОТ ПРОШЛОЙ КНИГИ. Каталог `out` собирается руками и
    # переиспользуется; страница `0007.json` от другой книги пережила бы
    # прогон и уехала в `books html`, `books text` и `books score` как часть
    # этой. Шапка обещала падать на таком, и не падала.
    _pages_dir = os.path.join(out_dir, "pages")
    if os.path.isdir(_pages_dir):
        mine_ = {os.path.basename(f) for f in files}
        alien = sorted(set(os.listdir(_pages_dir)) - mine_)
        if alien:
            raise SystemExit(
                f"в {_pages_dir} лежат страницы, которых нет в детекции: "
                f"{alien[:5]}{'…' if len(alien) > 5 else ''} ({len(alien)} шт.). "
                f"Это каталог от другой книги или другого набора страниц; "
                f"они уехали бы в книгу и в замер как часть этой. Убери их или "
                f"выбери пустой --out.")
    os.makedirs(_pages_dir, exist_ok=True)
    os.makedirs(os.path.join(out_dir, "answers"), exist_ok=True)
    crops_dir = os.path.join(out_dir, "crops")
    os.makedirs(crops_dir, exist_ok=True)

    routes = reader.routes()
    # Полнота маршрутов — ДО первого цента и до первой вырезки.
    labels = set()
    pages = []
    for fp in files:
        with open(fp, encoding="utf-8") as f:
            pg = Page.from_json(json.load(f))
        if pages_want is not None and pg.index not in pages_want:
            continue
        pages.append((fp, pg))
        labels |= {b.label for b in pg.blocks}
    if not pages:
        raise SystemExit("ни одной страницы к чтению — набор --pages пуст")
    reader.cover(labels)

    params = _gen_params()
    window = reader.pixels()
    # ЧЕМ ЧИТАЛИ В ПРОШЛЫЙ РАЗ. Возобновление обязано сверять это, а не только
    # наличие файла. Замер до сверки: сменить модель, потолок токенов или
    # промты — и ни один блок не переспрашивался, а `run.json` объявлял НОВЫЕ
    # величины действующими. То есть слепок «полон и недействующий» — ровно та
    # болезнь, которой посвящены шапки этого файла и `read/__init__.py`.
    # Вдобавок единственная запись о том, за что заплачено (секунды, токены),
    # затиралась вторым, бесплатным запуском.
    setup = {"reader": reader.fingerprint(), "generation": params,
             "transport": {k: v for k, v in transport.fingerprint().items()
                           # адрес меняется от прогона к прогону (порт
                           # подставного сервера, петля на боксе) и ответ
                           # модели не решает; имя модели — решает.
                           if k in ("transport", "model_asked")}}
    setup_path = os.path.join(out_dir, "чем читали.json")
    same_setup = True
    if resume and os.path.exists(setup_path):
        with open(setup_path, encoding="utf-8") as f:
            was = json.load(f)
        same_setup = was == setup
        if not same_setup:
            diff = [k for k in setup if was.get(k) != setup[k]]
            log(f"ЧИТАЛИ ДРУГИМ: разошлось {diff} — возобновлять нельзя, "
                f"спрашиваю всё заново. Иначе слепок объявил бы новые величины "
                f"действующими при старых ответах.")
    with open(setup_path, "w", encoding="utf-8") as f:
        json.dump(setup, f, ensure_ascii=False, indent=1)
    doc = pymupdf.open(pdf)
    # СОБСТВЕННАЯ РЕЗКОСТЬ — ПО КАЖДОЙ СТРАНИЦЕ, а не по первой на всю книгу.
    #
    # Здесь стояло «по первой, и её довольно: лист у книги один и тот же», а
    # рядом довод «считать по каждой значило бы звать `get_images` на шестистах
    # страницах». Оба неверны, и оба опровергнуты замером.
    #
    # Лист НЕ один и тот же: у «Фейнмановских лекций» 255 разных размеров листа
    # на 260 страниц, у «Технологии огнеупоров» — 178 на 378.
    #
    # Считать по каждой ничего не стоит, потому что это УЖЕ делается: `crop.cut`
    # зовёт `native_dpi(doc[page_index])` на КАЖДОМ блоке и ответ выбрасывает —
    # на стенде это 15 601 вызов вместо шестисот. Экономия была не только
    # ложной, но и отрицательной.
    #
    # Цена ошибки замерена. У «Фейнмана» страницы 0-2 векторные (титул), а
    # 257 из 260 несут растр 300 dpi. Резкость первой страницы — `None`, и вся
    # книга резалась при 144: пикселей 15.1 млн вместо 59.0 млн, чернил 2.69
    # млн вместо 9.38 млн (3.89x и 3.49x), а вырезок мельче нижней границы
    # модели 125 из 177 вместо 79. Книга такая одна из девяти — но именно она
    # и показывает, что правило «по первой» держалось на совпадении.
    native_of = {}

    def _native(i):
        if i not in native_of:
            native_of[i] = crop.native_dpi(doc[i])
        return native_of[i]

    native = _native(0)
    cut_dpi = {}
    tally = {"page_count": len(pages), "block_count": 0, "asked": 0,
             "not_asked": 0, "read": 0, "model_silent": 0,
             "delivery_failed": 0, "hit_ceiling": 0,
             "kind_not_as_promised": 0, "reused_from_previous_run": 0,
             # ШЕСТОЙ НОЛЬ, и у него до сих пор не было имени. Транспорт может
             # вернуть ответ с ЧУЖИМ якорем (спутанный порядок, шлюз,
             # переписавший запрос), и тогда блок оставался без записи вовсе:
             # ни один из пяти счётчиков не шевелился, `answers/` был пуст,
             # `content` пуст, а деньги за ответ уплачены. Замер: три ответа с
             # чужими якорями дали «сумма исходов 0 при блоках 3».
             "answer_wrong_anchor": 0, "asked_no_answer": 0,
             "crop_failed": 0, "crop_dpi_reason_counts": {},
             "native_book_dpi": native,
             "model_window": list(window) if window else None,
             "chars": 0, "compute_seconds": 0.0, "tokens": 0}
    bad_crops = []
    by_kind = {}
    worst = []

    for fp, pg in pages:
        tag = f"p{pg.index:04d}"
        ans_path = os.path.join(out_dir, "answers", f"{tag}.json")
        old = {}
        if resume and os.path.exists(ans_path) and same_setup:
            with open(ans_path, encoding="utf-8") as f:
                old = {a["anchor"]: a for a in json.load(f).get("answers", [])}

        asks, silent, nocrop, cut_info = [], {}, {}, {}
        for b in pg.blocks:
            tally["block_count"] += 1
            anchor = f"{tag}-b{b.block_id}"
            rt = routes[b.label]
            if not rt.asked():
                tally["not_asked"] += 1
                silent[anchor] = rt.why
                continue
            if anchor in old and old[anchor].get("text") is not None:
                tally["reused_from_previous_run"] += 1
                continue
            rel = os.path.join(crops_dir, f"{anchor}.png")
            # Лист в пикселях ТОГО ЖЕ растра, в котором лежат рамки.
            _r = doc[pg.index].rect
            sheet = (0.0, 0.0, _r.width * page_dpi / 72.0,
                     _r.height * page_dpi / 72.0)
            cdpi, why = crop_dpi_for(b.box, page_dpi, _native(pg.index),
                                     window, sheet=sheet)
            cut_dpi[anchor] = (cdpi, why)
            tally["crop_dpi_reason_counts"][why] = (
                tally["crop_dpi_reason_counts"].get(why, 0) + 1)
            try:
                # ВОЗВРАТ НЕ ВЫБРАСЫВАЕТСЯ. `crop.cut` считает ширину, высоту,
                # «срезано листом» и ЧЕСТНЫЙ dpi (тот, которым резали, а не тот,
                # который просили), а этот проход их терял: про вырезку,
                # уехавшую в модель обкусанной краем листа, в `answers/` не было
                # ни слова. Замер: срезано листом 28 из 15 601 рамки стенда
                # (0.18%), но на настоящем скане 8 из 177 — 4.5%.
                cut_info[anchor] = crop.cut(doc, pg.index, b.box, page_dpi,
                                            rel, dpi=cdpi)
            except (ValueError, IndexError, RuntimeError) as e:
                # РАМКУ МОДЕЛИ НЕ ЧИНИМ, но и книгу из-за неё не бросаем.
                # Вырожденная рамка, рамка за листом, страница за пределами
                # PDF — дефекты модели или чужого каталога, и прежде каждый из
                # них ронял прогон голой трассой НА СЕРЕДИНЕ книги: всё уже
                # прочитанное оставалось без слепка, то есть деньги уплачены, а
                # предъявить нечего. Теперь это ВЕЛИЧИНА со своим счётчиком, и
                # прогон идёт дальше.
                tally["crop_failed"] += 1
                bad_crops.append(f"{anchor}: {type(e).__name__}: {e}")
                nocrop[anchor] = f"{type(e).__name__}: {e}"
                continue
            asks.append(Ask(anchor=anchor, image=rel, prompt=rt.prompt,
                            kind=rt.kind, label=b.label, params=dict(params)))

        asked_now = {a.anchor for a in asks}
        said = {}
        if asks:
            n = max(1, int(knobs.knob("VLM_CONCURRENCY")))
            want = {a.anchor for a in asks}
            with ThreadPoolExecutor(max_workers=n) as pool:
                for s in pool.map(transport.send, asks):
                    if s.anchor not in want:
                        tally["answer_wrong_anchor"] += 1
                        continue
                    said[s.anchor] = s

        # Собираем страницу. Порядок блоков — исходный, а не порядок ответов:
        # при VLM_CONCURRENCY > 1 ответы приходят вразнобой, и складывать по
        # приходу значило бы молча переставить книгу.
        answers = []
        for b in pg.blocks:
            anchor = f"{tag}-b{b.block_id}"
            rt = routes[b.label]
            if anchor in silent:
                b.content, b.kind = None, "none"
                answers.append({"anchor": anchor, "not_asked": silent[anchor]})
                continue
            if anchor in nocrop:
                # Блок НЕ спрашивали: вырезать было нечего. Это не «спросили, а
                # ответа нет» — иначе одна беда считалась бы двумя.
                b.content, b.kind = None, "none"
                answers.append({"anchor": anchor,
                                "crop_failed": nocrop[anchor]})
                continue
            if anchor in old and old[anchor].get("text") is not None:
                rec = old[anchor]
            else:
                s = said.get(anchor)
                if s is None:
                    # Спрашивали, а ответа под этим якорем нет. Молчать нельзя:
                    # блок ушёл бы из книги и из `answers/` без единой записи.
                    tally["asked_no_answer"] += 1
                    b.content, b.kind = None, "none"
                    answers.append({"anchor": anchor,
                                    "trouble": "спросили, ответа под этим якорем "
                                            "не пришло"})
                    continue
                rec = s.to_json()
                rec["label"] = b.label          # чей это блок — видно в ответе
                if anchor in cut_dpi:
                    # dpi берётся ИЗ ВЫРЕЗКИ, а не из правила: `crop.cut`
                    # рендерит при `int(dpi)`, а правило даёт дробное, и
                    # запись `round` расходилась с делом у 328 рамок из 379.
                    # Расхождение стоит одного dpi (0.13% ширины) — но число в
                    # журнале обязано быть тем, которым резали.
                    info = cut_info.get(anchor) or {}
                    rec["observed"]["crop_dpi"] = info.get(
                        "dpi", cut_dpi[anchor][0])
                    rec["observed"]["crop_dpi_by_rule"] = round(
                        cut_dpi[anchor][0], 2)
                    rec["observed"]["crop_dpi_reason"] = cut_dpi[anchor][1]
                    rec["observed"]["crop"] = info or None
                rec["observed"]["kind_sniffed"] = _sniff(s.text or "")
                # СЧЁТ РВАНОСТИ OTSL — сбоку, у ответа. Прежде `otsl.parse`
                # считал строки разной длины, продолжения в никуда и текст
                # мимо тегов, и всё это выбрасывалось: ни один прогон не мог
                # напечатать числа, ради которых отличают порванную по потолку
                # таблицу от целой. Теперь они лежат рядом с ответом.
                if rt.kind == "otsl" and s.text:
                    g, t = otsl.parse(s.text)
                    rec["observed"]["otsl_grid"] = t
                tally["compute_seconds"] += s.took_s
                tally["tokens"] += s.tokens or 0
            answers.append(rec)

            txt = rec.get("text")
            if rec.get("error"):
                tally["delivery_failed"] += 1
                b.content, b.kind = None, "none"
            elif txt is None or not txt.strip():
                tally["model_silent"] += 1
                b.content, b.kind = None, "none"
            else:
                tally["read"] += 1
                tally["chars"] += len(txt)
                # БАЙТЫ МОДЕЛИ, без единой правки. Вид — объявленный промтом.
                b.content, b.kind = txt, rt.kind
                by_kind[rt.kind] = by_kind.get(rt.kind, 0) + 1
                if rec["observed"].get("kind_sniffed") not in (rt.kind, None):
                    tally["kind_not_as_promised"] += 1
            if rec.get("outcome") == "length":
                tally["hit_ceiling"] += 1
                worst.append(anchor)
            # СЧИТАЕМ ТОЛЬКО НАСТОЯЩИЕ ВОПРОСЫ. Прежде сюда попадали и блоки,
            # взятые из прошлого прогона: `books read` вторым разом печатал
            # «спрошено 567» при НУЛЕ обращений к службе, и на это же число
            # делились «секунды на блок». Две величины с одним именем
            # расходились по построению.
            if anchor in asked_now:
                tally["asked"] += 1

        pg.meta = dict(pg.meta or {})
        pg.meta["reading"] = {"reader": reader.name, "transport": transport.name,
                             "asked": len(asks)}
        with open(os.path.join(out_dir, "pages", os.path.basename(fp)),
                  "w", encoding="utf-8") as f:
            json.dump(pg.to_json(), f, ensure_ascii=False, indent=1)
        with open(ans_path, "w", encoding="utf-8") as f:
            json.dump({"page": pg.index, "answers": answers}, f,
                      ensure_ascii=False, indent=1)
        log(f"стр. {pg.index}: спрошено {len(asks)}, прочитано "
            f"{sum(1 for a in answers if a.get('text'))}, "
            f"молчаний {sum(1 for a in answers if a.get('text') == '')}, "
            f"отказов {sum(1 for a in answers if a.get('error'))}")
    doc.close()

    tally["by_kind"] = by_kind
    tally["truncated_anchors"] = worst[:20]
    tally["crop_failures"] = bad_crops[:20]
    return tally


def report(t: dict, log=log) -> None:
    """Величины, а не «готово». Пять нулей печатаются порознь."""
    log(f"страниц {t['page_count']}, блоков {t['block_count']}: спрошено "
        f"{t['asked']}, не спрошено {t['not_asked']}")
    if t["reused_from_previous_run"]:
        log(f"  взято из прошлого прогона {t['reused_from_previous_run']} — "
            f"эти блоки модель СЕЙЧАС не читала")
    log(f"прочитано {t['read']}, знаков {t['chars']}, по видам "
        f"{t['by_kind'] or '—'}")
    log(f"резкость вырезки: своя у книги "
        f"{t['native_book_dpi'] and round(t['native_book_dpi']) or '—'} dpi, "
        f"окно модели {t['model_window'] or 'не объявлено'}; "
        f"{t['crop_dpi_reason_counts'] or '—'}")
    # Три беды печатаются ВСЕГДА, в том числе нулями: строка, исчезающая при
    # нуле, читается как «такого не бывает», а не как «в этот раз не было».
    log(f"  модель промолчала {t['model_silent']}, отказов доставки "
        f"{t['delivery_failed']}, оборвано потолком {t['hit_ceiling']}, "
        f"ответ мимо якоря {t['answer_wrong_anchor']}, спрошено без ответа "
        f"{t['asked_no_answer']}")
    if t["crop_failed"]:
        log(f"  ВЫРЕЗКА НЕ ВЫШЛА у {t['crop_failed']} блоков — рамка "
            f"модели вырождена или лежит вне листа. Это её дефект, а не наш; "
            f"блок остался непрочитанным: {'; '.join(t['crop_failures'][:3])}")
    if t["hit_ceiling"]:
        log(f"  ОБОРВАНО ПОТОЛКОМ: {', '.join(t['truncated_anchors'])}"
            f"{'…' if t['hit_ceiling'] > 20 else ''} — у таблицы это "
            f"НЕ выглядит поломкой: вендорский otsl_pad_to_sqr_v2 молча "
            f"укорачивает длинные строки, и порванная таблица возвращается "
            f"правдоподобной. Поднимать VLM_MAX_TOKENS или резать мельче")
    if t["kind_not_as_promised"]:
        log(f"  вид ответа разошёлся с объявленным у "
            f"{t['kind_not_as_promised']} блоков — это НЕ дефект модели, а "
            f"повод пересмотреть объявление в чтеце; догадка лежит сбоку, в "
            f"answers/")
    if not t["asked"]:
        log("СПРОШЕНО НОЛЬ БЛОКОВ — это не успех, а пустой прогон")
    if t["compute_seconds"]:
        log(f"счёта {t['compute_seconds']:.1f} с, токенов {t['tokens']}, "
            f"{t['compute_seconds'] / max(1, t['asked']):.2f} с на блок")


def _repeat_line(detect_dir: str, out_dir: str, args: dict) -> str:
    """Строка повтора. ИСПОЛНИМАЯ и ПОЛНАЯ.

    Без `--pages` и `--policy` она повторяет ДРУГОЙ прогон: у `books detect`
    `--pages` в повторе есть, и расхождение двух команд тут ничем не оправдано.
    Экранирование обязательно: в `raw/` пять файлов из девяти несут пробелы и
    скобки, и неэкранированная строка повтора — не строка повтора, а её
    описание.
    """
    argv = ["books", "read", detect_dir, "--out", out_dir]
    if args.get("pages"):
        argv += ["--pages", str(args["pages"])]
    if args.get("policy"):
        argv += ["--policy", str(args["policy"])]
    return " ".join(shlex.quote(a) for a in argv)


def snapshot(detect_dir: str, out_dir: str, reader: Reader,
             transport: Transport, tally: dict, args: dict) -> str:
    """Слепок входа: те же поля, что у детекции, и наконец непустые «промты»."""
    facts = _detect_facts(detect_dir)
    read_knobs = {**{n: "адаптер чтения" for n in reader.knobs_read()},
                  **{n: "transport" for n in transport.knobs_read()}}
    snap = {
        "when": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "knobs": _knobs_snapshot(read_knobs),
        "raster": facts["raster"],
        "args": args,
        "commit": stamp.commit(),
        # Книга та же, что у детекции, и хэш сверен ДО работы (см. read_book).
        "source": facts["source"],
        "detection": {"dir": os.path.abspath(detect_dir),
                     "commit": facts.get("commit"),
                     "adapter": facts.get("adapter"),
                     "sha256_snapshot": stamp.sha256(
                         os.path.join(detect_dir, "run.json"))},
        "adapter": {"name": reader.name,
                    "module": type(reader).__module__,
                    "sha256": stamp.sha256(
                        sys.modules[type(reader).__module__].__file__),
                    "sha256_command": stamp.sha256(
                        os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                     "run.py")),
                    # Разбор OTSL — НАШ код, и он решает числа не меньше
                    # модели. Без его хэша два прогона с разным разбором
                    # выглядели бы одинаковыми.
                    "sha256_otsl_parser": stamp.sha256(
                        os.path.join(os.path.dirname(os.path.dirname(
                            os.path.abspath(__file__))), "otsl.py"))},
        "policy": policy.snapshot(getattr(reader, "policy_name", None)),
        "prompts": reader.fingerprint().get("prompts", {}),
        "generation": _gen_params(),
        "packages": stamp.packages(stamp.READ_PACKAGES),
        "weights": {"vl": reader.fingerprint().get("weights"),
                 "layout": facts.get("weights", {}).get("layout")},
        # ОТПЕЧАТОК — ЭТО ОТПЕЧАТОК ЧТЕЦА, без обёртки. `run/replay.py`
        # выводит требуемую форму разбором метода `fingerprint()` активного
        # адаптера и ищет её поля прямо здесь; вложенный «чтец» давал шесть
        # строк «нет отпечаток/промты», то есть слепок объявлялся НЕПОЛНЫМ,
        # хотя всё было записано. Транспорт — своим полем: он не адаптер
        # модели, и смешивать их значило бы объявить два отпечатка одним.
        "fingerprint": reader.fingerprint(),
        "transport_fingerprint": transport.fingerprint(),
        "summary": tally,
        # Строка обязана быть ИСПОЛНИМОЙ и полной: без `--pages` и `--policy`
        # она повторяет ДРУГОЙ прогон. У `books detect` `--pages` в повторе
        # есть, и расхождение двух команд тут ничем не оправдано.
        "repeat_command": _repeat_line(detect_dir, out_dir, args),
    }
    p = os.path.join(out_dir, "run.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(snap, f, ensure_ascii=False, indent=1)
    return p


def _knobs_snapshot(read_by_adapter) -> dict:
    """Ручки с пометкой, кто их читает. Форма — общая с детекцией.

    Разделение не украшение: слепок, где все ручки лежат в одной куче, ПОЛОН
    и недействующий. Прогон heron клялся `LAYOUT_MODEL_NAME=PP-DocLayoutV2` —
    величиной, которой этот адаптер не читает вовсе, — и `books replay
    --check` это одобрял.
    """
    # `CROP_DPI` ЗДЕСЬ НЕТ, и это не забывчивость. Путь чтения её не читает
    # вовсе: резкость каждой вырезки решает `crop_dpi_for` (скан плюс окно
    # модели), а `crop.cut` зовётся с явным `dpi=`. Проверено: `CROP_DPI=72` и
    # `CROP_DPI=1200` не меняют вырезку `books read` ни на пиксель, тогда как
    # `books html` и `books feed` слушаются. Объявить её действующей значило бы
    # повторить болезнь, против которой этот самый слепок и написан: прогон
    # heron клялся `LAYOUT_MODEL_NAME`, которого не читает.
    mine = ("VLM_READER", "VLM_TRANSPORT", "VLM_CONCURRENCY",
            "VLM_TEMPERATURE", "VLM_MAX_TOKENS", "VLM_TOP_P", "VLM_SEED",
            "CROP_MARGIN", "PAGE_DPI")
    # РАЗРЕЗ «ЧТО ПРОСИМ / КАК ДОСТАВЛЯЕМ» ЖИВ И В СЛЕПКЕ. Прежде роли
    # складывались в один кортеж и всем ставилось «адаптер чтения» — то есть
    # `VLM_ENDPOINT`, `VLM_RETRIES` и `VLM_TIMEOUT_S`, которые читает
    # транспорт, приписывались модели. Разрез, ради которого написан весь
    # `read/__init__.py`, в слепке стирался.
    roles = dict(read_by_adapter)
    for n in mine:
        roles.setdefault(n, "сама команда `books read`")
    return knobs.snapshot_with_readers(roles)
