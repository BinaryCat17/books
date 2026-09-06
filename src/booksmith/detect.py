"""`books detect` — контуры первого уровня, местно и бесплатно.

Что делает: рендерит страницы PDF при `PAGE_DPI`, гоняет по ним детектор
макета и кладёт рядом `Page` в json — рамки, ярлыки, порядок чтения. Ни VLM,
ни аренды, ни единого цента. Страница считается пару секунд на процессоре.

Зачем это раньше всего остального. Метрику контуров нельзя проверить на
выдуманных данных: мутации показывают, что число шевелится, но не показывают,
что оно меряет то самое. Нужен вывод НАСТОЯЩЕЙ модели на НАСТОЯЩИХ страницах
— и вот он, без денег и без ожидания.

Слепок пишется полным. `books replay --check` на каталоге этой команды обязан
возвращать 0: у детектора нет ни промтов, ни параметров порождения, ни весов
VLM — и это ЗНАЧЕНИЯ (`null`), а не пропуски. Разница принципиальная:
«промтов нет вовсе» и «промты не смотрели» — разные прогоны.

Полный — не значит действующий, и это отдельная беда. Ручки в слепке
РАЗДЕЛЕНЫ по тому, кто их читает: активный адаптер, сама команда, никто. До
разделения прогон heron клялся `LAYOUT_MODEL_NAME=PP-DocLayoutV2`, ручкой,
которой этот адаптер не читает вовсе, — и проверка полноты это одобряла.

ЧТО ЗДЕСЬ ОБЯЗАНО ПАДАТЬ, А НЕ МОЛЧАТЬ. Пустой набор страниц, пустой вывод
модели, чужие страницы в каталоге от прошлого прогона, НАПИСАНИЕ ЯРЛЫКА
БЛОКА, КОТОРОГО НЕТ В СЛОВАРЕ ПОЛИТИКИ. Каждый из четырёх случаев прежде
давал код 0 и полный слепок, то есть выглядел успехом.
"""
import json
import os
import shlex
import sys
import time

from . import policy
from .models.doclayout import DocLayout
from .run import knobs, stamp

# Политика «текст / артефакт / служебное» живёт в одном месте — `policy.py`,
# и оттуда же её берёт сборщик HTML. Два списка разошлись бы: они уже
# расходились в этом проекте (реестр ручек против сборщика задания, 13 имён
# из 17).
# Артефактные ярлыки БЕРУТСЯ ИЗ АКТИВНОЙ ПОЛИТИКИ (в `run`), а не из
# объединения всех. Объединение печатало в отчёте `picture` при прогоне
# модели, у которой такого класса нет вовсе, — вечный ноль, который читается
# как «модель их не нашла».
# По ТОМУ ЖЕ ОДНОМУ словарю сверяется и написание ярлыка каждого блока —
# `_check_labels` ниже. Проверка словаря ВЕСОВ (`policy.check`) этого не
# делает и делать не может: она смотрит, что модель умеет назвать, а не что
# в блоке написано, а между ними лежит перевод туда и обратно.


# Три величины слепка — хэш файла, коммит, версии пакетов — переехали в
# `run/stamp.py`: пишущих слепок стало трое (эта команда, `doc/html.py` и
# `read/run.py`), а второй экземпляр — то самое расхождение, за которое проект
# уже платил (13 имён из 17 в реестре ручек против сборщика задания).
# Здесь стояло, что на арендованной машине этот файл «не поднимется вовсе, он
# тянет onnxruntime и opencv»; замер опроверг: импорты ленивые, внутри функций
# `models/doclayout.py`, а на машине эти пакеты есть.
_sha256 = stamp.sha256


# Реестр адаптеров. Пока он был один, вопрос «а не лучше ли другая модель»
# нельзя было даже поставить: имя модели было зашито в импорт. Адаптеры
# отличаются не весами, а СЛОВАРЁМ и препроцессом, поэтому выбор объявлен
# ручкой и уезжает в слепок.
ADAPTERS = ("doclayout", "docling", "docling-egret", "yolox")


def _check_labels(page, pol, known, adapter):
    """Написание ярлыка КАЖДОГО БЛОКА — по названному словарю, и вслух.

    ЧЕГО НЕ ПРОВЕРЯЛ НИКТО. `policy.check(det.labels)` сверяет словарь ВЕСОВ:
    то, что модель умеет назвать. Сюда же приходит то, что в блоке НАПИСАНО, а
    между этими двумя вещами лежит перевод: адаптер docling переводит ярлык в
    словарь вендора и обратно, а вендорский конвейер ярлыки ещё и
    переименовывает сам (`TITLE -> SECTION_HEADER` в его постобработке).
    Сторожа на этом пути не было ни одного: подмена обратного перевода у egret
    на шести страницах прошла молча. `policy.role()` тут тоже не спасает — он
    не падает никогда, потому что `policy.ROLE` это объединение всех пяти
    словарей, где рядом лежат и `table`, и `Table`.

    ЦЕНА МОЛЧАНИЯ — НЕ ПАДЕНИЕ, А НОЛЬ. Артефактные ярлыки берутся из ОДНОГО
    словаря (`arte` в `run`), и блок, написанный по-чужому, не совпадёт ни с
    одним из них: «артефактов 0» читается как «модель их не нашла», а значит
    «мы не узнали её слов». Ровно тот ноль от непонимания, что записан в
    правилах проекта.

    Проверяется НА КАЖДОЙ СТРАНИЦЕ, а не однажды: переименовать ярлык может
    вендорский конвейер, а он видит не всякую страницу одинаково — чужое
    написание способно появиться на четырёхсотой странице и ни разу до неё.
    """
    bad = sorted({b.label for b in page.blocks if b.label not in known})
    if not bad:
        return
    raise RuntimeError(
        f"страница {page.index}: ярлыки блоков {bad} не из словаря политики "
        f"«{pol}» (адаптер {adapter}; словарь знает {len(known)} написаний: "
        f"{sorted(known)}). Считать дальше нельзя: артефактные ярлыки берутся "
        f"из этого же словаря, и блок с чужим написанием дал бы «артефактов "
        f"0» — ноль от непонимания под видом замера. Чинить надо перевод "
        f"ярлыка в адаптере или сам словарь policy.POLICIES, но не эту "
        f"проверку.")


def _adapter():
    which = knobs.knob("LAYOUT_ADAPTER")
    if which == "doclayout":
        return DocLayout()
    if which == "docling":
        from .models.docling_heron import DoclingHeron
        return DoclingHeron()
    if which == "docling-egret":
        from .models.docling_heron import DoclingEgret
        return DoclingEgret()
    if which == "yolox":
        from .models.yolox_layout import YoloXLayout
        return YoloXLayout()
    raise SystemExit(f"LAYOUT_ADAPTER={which!r}: знаю только {ADAPTERS}")


# Ручки, которые читает САМА эта команда, а не адаптер. Разряд третий, и он
# не украшение: пометить `PAGE_DPI` как «к прогону не относится» было бы враньём
# ровно того же рода, что называть чужую модель, — только в другую сторону.
# `LAYOUT_SCORE_THRESHOLD` здесь тоже читается (в отказе «ни одной рамки»), но
# лишь чтобы напечатать чужое число: действующим его делает адаптер, он же его
# и объявляет, а два хозяина у одной ручки — два списка, которые разойдутся.
COMMAND_KNOBS = ("PAGE_DPI", "LAYOUT_ADAPTER")


def _knob_roles(det):
    """Кто читает каждую ручку реестра В ЭТОМ прогоне: адаптер, команда, никто.

    До этого разбора слепок прогона `LAYOUT_ADAPTER=docling` уверенно писал
    `LAYOUT_MODEL_NAME=PP-DocLayoutV2` — имя модели, которую он не поднимал:
    у heron каталог весов зашит, а ручку эту читает только `doclayout.py`.
    Полнота слепка тут не спасает, а вредит: `books replay --check` возвращал
    0 из 41, то есть проверка подтверждала слепок, называющий чужую величину.

    Опечатка в объявлении адаптера ловится здесь же и вслух: имя не из реестра
    означало бы, что список ручек разошёлся с реестром молча — та самая беда,
    от которой реестр и заведён.
    """
    try:
        mine = tuple(det.knobs_read())
    except NotImplementedError:
        raise SystemExit(
            f"адаптер {det.name} не объявил, какие ручки читает "
            f"(models/base.py, knobs_read). Пустой кортеж — законный ответ, "
            f"молчание — нет: молчащий адаптер вернул бы слепок к тому, "
            f"ради чего это объявление и заведено.") from None
    unknown = [n for n in mine if n not in knobs.KNOB]
    if unknown:
        raise SystemExit(
            f"адаптер {det.name} объявил ручки, которых нет в реестре: "
            f"{unknown}. Либо опечатка, либо чтение окружения мимо "
            f"run/knobs.py — обе беды молчаливые.")
    roles = {}
    for n in knobs.names():
        if n in mine:
            roles[n] = f"адаптер {det.name}"
        elif n in COMMAND_KNOBS:
            roles[n] = "команда books detect"
        else:
            roles[n] = None
    return roles


# Форма слепка ручек переехала в реестр (`run/knobs.snapshot_with_readers`):
# снимающих стало двое — детекция и чтение, — и вторая редакция успела
# получиться другой формы, которую забраковал `books replay --check`.
_knobs_snapshot = knobs.snapshot_with_readers


_commit = stamp.commit


def _packages():
    return stamp.packages(stamp.DETECT_PACKAGES)


def parse_pages(spec, total):
    """`--pages 1,4,7-9` -> набор номеров, считая с единицы.

    Пустое значение — вся книга. Номер за пределами книги — ошибка вслух.
    Заданный, но ПУСТОЙ набор (`3-1`) — тоже ошибка: прежде он давал ноль
    страниц, код возврата 0 и полный слепок, то есть пустой прогон выглядел
    успешным. Ноль от непонимания.
    """
    if not spec:
        return list(range(total))
    # ПРОБЕЛ РАЗДЕЛЯЕТ ТАК ЖЕ, КАК ЗАПЯТАЯ. Прежде `--pages "1 3"` падало
    # голым `ValueError: invalid literal for int()`, и это ловилось только у
    # `detect` — у `overlay` был свой разбор, пробелы принимавший. Когда
    # разборы свели в один, отказ достался обоим: правило «жаловаться вслух»
    # нарушалось в двух командах вместо одной. Понимать надо обе записи.
    want = []
    for part in str(spec).replace(" ", ",").split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part[1:]:
            a, b = part.split("-", 1)
            try:
                rng = range(int(a), int(b) + 1)
            except ValueError:
                raise SystemExit(
                    f"в «--pages {spec}» диапазон «{part}» не разобран. "
                    f"Ожидается «7-9», счёт с единицы.")
            if not rng:
                raise SystemExit(
                    f"диапазон «{part}» пуст: конец раньше начала")
            want.extend(rng)
        else:
            try:
                want.append(int(part))
            except ValueError:
                # Вслух и с образцом, а не следом стека: этот ключ набирают
                # руками, и опечатка в нём — обычное дело.
                raise SystemExit(
                    f"в «--pages {spec}» кусок «{part}» — не номер страницы. "
                    f"Ожидается «1,4,7-9» или «1 4 7-9», счёт с единицы.")
    bad = [p for p in want if not 1 <= p <= total]
    if bad:
        raise SystemExit(f"в книге {total} страниц, а запрошены {bad}")
    if not want:
        raise SystemExit(f"набор страниц «{spec}» пуст — считать нечего")
    return [p - 1 for p in sorted(set(want))]


def run(pdf, outdir, pages_spec=None, log=print):
    """Прогнать детектор по страницам PDF. Возвращает путь к каталогу."""
    import pymupdf

    dpi_raw = knobs.knob("PAGE_DPI")
    dpi = float(dpi_raw)
    # Рендерим целым числом, и в слепок пишем ЕГО, а не исходное дробное:
    # `get_pixmap` дробное усекает, и слепок при `PAGE_DPI=143.5` соврал бы.
    dpi_used = int(dpi)
    if dpi_used != dpi:
        log(f"ВНИМАНИЕ: PAGE_DPI={dpi_raw} усечён до {dpi_used} — "
            f"растр рисуется целым числом точек на дюйм")

    pdf = os.path.abspath(pdf)
    outdir = os.path.abspath(outdir)
    pagedir = os.path.join(outdir, "pages")

    # Вход проверяем ДО подъёма детектора: иначе на опечатке в имени файла
    # оператор ждал загрузки весов, читал словарь ярлыков и получал пять
    # кадров `pymupdf.FileNotFoundError`. Все соседние команды (`books html`,
    # `books feed`, `books replay`) на дурном пути говорят одной строкой.
    # ЭТА ПРОВЕРКА ЛОВИТ ТОЛЬКО ОТСУТСТВИЕ И КАТАЛОГ. Пустой файл, не-PDF и
    # книга без страниц ею НЕ ловятся — они ловятся ниже, на открытии; здесь
    # прежде стояло «осталась единственной с трассировкой», и это объявляло
    # вылеченным то, что вылечено не было (проверено: EmptyFileError и
    # FileDataError вылезали трассировкой).
    if not os.path.exists(pdf):
        raise SystemExit(f"нет файла {pdf}")
    if os.path.isdir(pdf):
        raise SystemExit(f"{pdf} — каталог, а ожидается PDF одной книги")

    det = _adapter()
    # Политика обязана покрывать словарь весов ЦЕЛИКОМ и не называть лишнего.
    # Проверяется при каждом прогоне: словарь приезжает из весов, и смена
    # весов — самый вероятный способ завести двадцать шестой класс.
    # Политику выбирает СЛОВАРЬ МОДЕЛИ, а не имя весов: имя можно перепутать,
    # список классов приезжает из самих весов.
    pol = getattr(det, "policy_name", None) or policy.for_labels(det.labels)
    det.policy_name = pol
    policy.check(det.labels, policy=pol)
    arte = tuple(sorted(l for l, r in policy.POLICIES[pol].items()
                        if r == "artifact"))
    # Тот же один словарь — и для сверки написания ярлыка блока. Объединение
    # `policy.ROLE` тут не годится ровно потому, что оно объединение: в нём
    # рядом лежат `table` и `Table`, и чужое написание прошло бы насквозь.
    known = set(policy.POLICIES[pol])
    for line in det.threshold_drift():
        # Громко: молчаливое расхождение означает, что прогон поехал на нашем
        # числе вместо модельного.
        log(f"ВНИМАНИЕ: порог задан не родной — {line}")

    # Заданное оператором — величиной и поимённо, а несъедобное для этого
    # адаптера — отдельной строкой. Замер до этой строки:
    # `LAYOUT_ADAPTER=docling LAYOUT_MODEL_NAME=PP-DocLayout_plus-L` давал
    # 0 упоминаний ручки в журнале на 12 страницах и слепок, где у неё стояло
    # «задано снаружи: true» рядом со значением, которого heron не видел.
    # Оператор при этом уверен, что он что-то настроил.
    roles = _knob_roles(det)
    given = [n for n in knobs.names() if n in os.environ]
    dead = [n for n in given if roles[n] is None]
    # Ноль печатается ТОЖЕ: это ноль от проверки («спросили — ничего не
    # задано»), а не молчание шага, который могли и не выполнить.
    log(f"задано снаружи ручек {len(given)}"
        + (f": {', '.join(given)}" if given else ""))
    if dead:
        log(f"ВНИМАНИЕ: из них {len(dead)} не читает ни адаптер {det.name}, "
            f"ни сама команда: {', '.join(dead)} — заданное значение на этот "
            f"прогон НЕ влияет, в слепке оно помечено «к этому прогону "
            f"относится: false»")
    log(f"детектор {det.name}: "
        f"{det.fingerprint().get('model')} из {det.dir}")
    # Про вход спрашиваем ОТПЕЧАТОК, а не поля конкретного адаптера: у второго
    # адаптера их не оказалось, и жёсткое обращение к `det.keep_ratio` роняло
    # прогон на первой же чужой модели. Отпечаток обязан быть у каждого — это
    # и есть контракт.
    fp_in = (det.fingerprint().get("input") or {})
    log(f"вход модели {fp_in.get('width')}x{fp_in.get('height')} (ШxВ): "
        + ", ".join(f"{k}={v}" for k, v in fp_in.items()
                    if k not in ("width", "height")))
    log(f"словарь {pol}, "
        f"классов {len(det.labels)}, "
        f"родной порог {det.fingerprint().get('native_threshold')}")

    # Открытие тоже говорит СТРОКОЙ. Проверка существования выше ловит опечатку
    # в имени, а этот `try` — три другие беды, которые она пропускает и которые
    # прежде вылезали трассировкой: пустой файл (`EmptyFileError`), не-PDF под
    # именем pdf (`FileDataError`) и книга без единой страницы. Все три
    # проверены; классы исключений чужие и не перечисляются поимённо нарочно —
    # список у pymupdf свой, и он менялся.
    try:
        doc = pymupdf.open(pdf)
        pages_total = doc.page_count
    except Exception as e:                      # noqa: BLE001 — чужая иерархия
        raise SystemExit(
            f"{pdf} не открывается как PDF: {type(e).__name__}: {e}") from None
    if not pages_total:
        raise SystemExit(f"{pdf} открылся, но страниц в нём ноль — считать нечего")
    idxs = parse_pages(pages_spec, pages_total)

    # Чужие страницы в каталоге — не мелочь. Прошлый прогон мог идти при
    # другом пороге, другом dpi, других весах; смешавшись, они дадут метрике
    # выборку из двух разных прогонов, и `run.json` про это не скажет.
    # Ровно тот урок, что записан в реестре про `RESUME`.
    os.makedirs(pagedir, exist_ok=True)
    stale = [f for f in os.listdir(pagedir) if f.endswith(".json")]
    if stale:
        for f in stale:
            os.unlink(os.path.join(pagedir, f))
        log(f"убрано страниц прошлого прогона: {len(stale)}")

    log(f"{os.path.basename(pdf)}: страниц в файле {doc.page_count}, "
        f"считаю {len(idxs)} при {dpi_used} dpi")

    t0 = time.time()
    tmp = os.path.join(outdir, f".page.{os.getpid()}.png")
    counts, rej_best, rej_pages = {}, {}, {}
    artefacts = ties = 0
    spellings = set()
    # ЭТАПОВ ДВА, И СЧИТАЮТСЯ ОНИ ПОРОЗНЬ. `counts` набирается по блокам,
    # доехавшим до json, то есть ПОСЛЕ вендорского конвейера, если он включён;
    # `model_boxes` — сколько рамок отдала сама модель выше порога (её число,
    # адаптер кладёт его в `meta`), и снятое конвейером есть разность.
    model_boxes = mute_pages = 0
    pipe = {"page_count": 0, "before": 0, "after": 0, "children": 0, "reordered": 0,
            "modes": set(), "missing_numbers": set()}
    try:
        for n, i in enumerate(idxs, 1):
            doc[i].get_pixmap(dpi=dpi_used).save(tmp)
            page = det.read(tmp, i, float(dpi_used))
            # ДО записи на диск: страница с неузнанным написанием ярлыка не
            # должна попадать в каталог вовсе — иначе её подберёт метрика.
            _check_labels(page, pol, known, det.name)
            spellings.update(b.label for b in page.blocks)
            mk = page.meta.get("boxes_accepted")
            if mk is None:
                mute_pages += 1          # адаптер не сказал — это не ноль
            else:
                model_boxes += int(mk)
            pm = page.meta.get("docling_pipeline")
            if pm:
                pipe["page_count"] += 1
                pipe["modes"].add(pm.get("mode"))
                for key, margin in (("boxes_before", "before"),
                                   ("boxes_after", "after"),
                                   ("moved_to_children", "children"),
                                   ("boxes_reordered", "reordered")):
                    v = pm.get(key)
                    if v is None:
                        pipe["missing_numbers"].add(key)
                    else:
                        pipe[margin] += int(v)
            with open(os.path.join(pagedir, f"{i:04d}.json"), "w",
                      encoding="utf-8") as f:
                json.dump(page.to_json(), f, ensure_ascii=False)
            ties += page.meta["rank_ties"]
            for lab, s in page.meta["best_rejected_by_class"].items():
                if s > rej_best.get(lab, 0.0):
                    rej_best[lab] = s
                    rej_pages[lab] = i          # ГДЕ он был лучше всего
                # «На скольких страницах отвергнуто» отсюда убрано: сырой
                # вывод несёт три сотни строк на страницу и накрывает почти
                # все классы почти всегда, так что это число было равно числу
                # страниц при любом пороге. Оно не умело упасть, а читалось
                # как замер.
            for b in page.blocks:
                counts[b.label] = counts.get(b.label, 0) + 1
                artefacts += b.label in arte
            if n % 10 == 0 or n == len(idxs):
                log(f"  {n}/{len(idxs)} страниц, рамок {sum(counts.values())}")
    finally:
        doc.close()
        if os.path.exists(tmp):
            os.unlink(tmp)

    took = time.time() - t0
    total = sum(counts.values())
    mode = "/".join(sorted(str(m) for m in pipe["modes"]))
    had_pipeline = bool(pipe["page_count"])
    # Пометка про этап ставится ТОЛЬКО когда конвейер и вправду работал: при
    # выключенном все числа и так от модели, и лишнее слово в строке сделало
    # бы прежние прогоны несравнимыми глазами на ровном месте.
    box_stage = (f"после конвейера docling {mode}" if had_pipeline
                  else "у модели, конвейера над рамками не было")
    log(f"рамок {total} на {len(idxs)} страницах "
        f"({total/len(idxs):.1f} на страницу), артефактов {artefacts}, "
        f"связок рангов {ties}, {took:.1f} с ({took/len(idxs):.2f} с/страница)"
        + (f" — все числа рамок ПОСЛЕ конвейера docling {mode}"
           if had_pipeline else ""))

    # СНЯТОЕ КОНВЕЙЕРОМ — ОТДЕЛЬНАЯ ВЕЛИЧИНА, А НЕ ПОПРАВКА К «ПРИНЯТО».
    # Пока её не было, «text принято 130» при включённой ручке было
    # неотличимо от «модель нашла 130»: снятое вендором растворялось в том же
    # числе, и увидеть его можно было только вторым прогоном с выключенной
    # ручкой. Замер, которым это вскрыто (bench/matematika, docling,
    # off -> post): text 143 -> 130, section_header 9 -> 7, formula 4 -> 3, а
    # «лучший отвергнутый» тех же классов (0.480 / 0.425 / 0.476) совпал до
    # знака, потому что он снят порогом ДО конвейера.
    if mute_pages:
        log(f"ВНИМАНИЕ: на {mute_pages} страницах из {len(idxs)} адаптер "
            f"{det.name} не сказал «рамок принято» — сколько отдала сама "
            f"модель, сверить нечем; сложенное ниже неполно на эти страницы")
    if had_pipeline:
        took = pipe["before"] - pipe["after"]
        share = 100.0 * took / pipe["before"] if pipe["before"] else 0.0
        log(f"конвейер docling {mode}: модель отдала рамок {pipe['before']}, "
            f"он снял {took} ({share:.1f}%), в книгу пошло {pipe['after']}, "
            f"ушло в дети {pipe['children']}, переставлено {pipe['reordered']}, "
            f"страниц через него {pipe['page_count']} из {len(idxs)}")
        # По ярлыкам снятое НЕ разложено, и молчать об этом нельзя: иначе
        # «table принято 0» при включённой ручке читается как «модель не
        # нашла», хотя означать может «нашла, а конвейер снял».
        log(f"    снятое конвейером по ярлыкам НЕ разложено: адаптер отдаёт "
            f"«рамок до» только итогом ({pipe['before']}), по классам их нет "
            f"(models/docling_heron.py, pipe_meta)")
        if pipe["missing_numbers"]:
            log(f"ВНИМАНИЕ: конвейер не дал чисел {sorted(pipe['missing_numbers'])} "
                f"— сложенное выше на столько же неполно")
        if pipe["page_count"] != len(idxs):
            log(f"ВНИМАНИЕ: через конвейер прошли {pipe['page_count']} страниц "
                f"из {len(idxs)} — числа этапов сложены по разным выборкам")
        if pipe["after"] != total:
            log(f"ВНИМАНИЕ: конвейер отчитался о {pipe['after']} рамках после "
                f"себя, а в страницах их {total}: разница "
                f"{abs(pipe['after'] - total)}")
        if not mute_pages and pipe["before"] != model_boxes:
            log(f"ВНИМАНИЕ: конвейер принял {pipe['before']} рамок, а модель "
                f"отдала {model_boxes}: разница "
                f"{abs(pipe['before'] - model_boxes)} рамок потеряна между "
                f"этапами")
    else:
        # Ноль от проверки, а не молчание шага: сказано, что конвейера НЕ
        # БЫЛО, и сказано числом страниц, на которых его не было.
        log(f"конвейер вендора рамок не касался: страниц через него 0 из "
            f"{len(idxs)}, «принято» ниже — рамки самой модели")
        if not mute_pages and model_boxes != total:
            log(f"ВНИМАНИЕ: модель отдала {model_boxes} рамок, а в страницах "
                f"их {total} при отсутствии конвейера: рамки правит кто-то "
                f"неназванный")

    # Величина, а не «сверено»: сколько написаний ярлыка встретилось из
    # скольких известных. Чужих здесь ноль всегда — не потому, что их не
    # бывает, а потому, что прогон с чужим написанием сюда не доходит
    # (`_check_labels` роняет его на той же странице).
    log(f"написаний ярлыков сверено со словарём «{pol}»: {len(spellings)} "
        f"из {len(known)} известных, чужих 0 — иначе прогон бы упал")

    # По классам — принято И лучшее отвергнутое. Без второго числа «table 0»
    # читается как «таблиц нет», а означать может «таблица была на 0.03 ниже
    # порога». Это разные беды: первая к модели, вторая к ручке. Замер на
    # bench/real/tables20.pdf: при родном пороге таблица находится на 4 страницах
    # из 20, притом что страницы отобраны именно по таблицам.
    # Показываем то, что нашлось, и ВСЕ артефактные ярлыки — даже с нулём.
    # Остальные отвергнутые сводим в строку: двадцать пять классов подряд
    # топят единственное число, ради которого отчёт и написан.
    shown = sorted(set(counts) | set(arte),
                   key=lambda l: (-counts.get(l, 0), l))
    # ЭТАПЫ НАЗВАНЫ, потому что их два. «Принято» считается по блокам,
    # доехавшим до json (после конвейера, если он был), «лучший отвергнутый»
    # приходит из `meta` адаптера и снят порогом модели ДО конвейера. Два
    # числа об одном ярлыке в одной строке про разные этапы читатель
    # складывает в одно — и получает «рамка была на 0.02 ниже порога» там,
    # где она была принята моделью и снята потом вендором.
    if had_pipeline:
        log(f"    по классам ДВА ЭТАПА: «принято» — {box_stage}; «лучший "
            f"отвергнутый» — порог модели ДО него. Складывать их нельзя.")
    else:
        log(f"    по классам, оба числа от модели ({box_stage}): «принято» "
            f"— рамки выше порога, «лучший отвергнутый» — лучшая ниже него")
    mark = " (после конвейера)" if had_pipeline else ""
    answer_mark = ", ДО конвейера" if had_pipeline else ""
    for lab in shown:
        line = f"    {lab:18s} принято{mark} {counts.get(lab, 0):5d}"
        if lab in rej_best:
            line += (f", лучший отвергнутый {rej_best[lab]:.3f} "
                     f"(стр. {rej_pages[lab]}{answer_mark})")
        log(line)
    rest = {l: v for l, v in rej_best.items() if l not in shown}
    if rest:
        top = max(rest.items(), key=lambda kv: kv[1])
        log(f"    прочих классов отвергнуто {len(rest)}, "
            f"выше всех {top[0]} {top[1]:.3f}"
            + (" (всё — порогом модели, ДО конвейера)" if had_pipeline
               else ""))

    if total == 0:
        raise RuntimeError(
            f"ни одной рамки на {len(idxs)} страницах — это отказ, а не "
            f"пустая книга. Порог LAYOUT_SCORE_THRESHOLD="
            f"{knobs.knob('LAYOUT_SCORE_THRESHOLD')}, веса {det.dir}. "
            f"Лучшее отвергнутое: {rej_best or 'ничего не отвергнуто вовсе'}")

    here = os.path.dirname(os.path.abspath(__file__))
    fp = det.fingerprint()
    snap = {
        # Дата рядом с числом: замер без неё не сказать, к чему применён.
        "when": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "knobs": _knobs_snapshot(roles),
        # Сводка тем же числом, что и в журнале: читать двадцать записей ради
        # ответа «а что здесь вообще действовало» никто не станет.
        "run_knobs": {
            "read_by_active_adapter": [n for n in knobs.names()
                                        if roles[n] and n not in COMMAND_KNOBS],
            "read_by_detect_command": [n for n in knobs.names()
                                           if roles[n] and n in COMMAND_KNOBS],
            "not_for_this_run": [n for n in knobs.names()
                                             if roles[n] is None],
            "set_externally": given,
            "set_externally_unread": dead,
        },
        "raster": {"scale": dpi_used / 72.0, "dpi": float(dpi_used),
                  "page_dpi_as_given": dpi_raw},
        "args": {"pdf": pdf, "pages": pages_spec, "out": outdir},
        "commit": _commit(),
        "source": {"path": pdf, "sha256": _sha256(pdf)},
        # Хэшируются ОБА файла, решающих результат. Прежде считался только
        # адаптер, а политика артефактов и разбор страниц живут здесь.
        # sha256 ФАЙЛА АКТИВНОГО АДАПТЕРА, а не всегда doclayout.py. Прежде
        # прогон yolox клялся хэшем чужого модуля: правка в docling_heron.py
        # или yolox_layout.py была в слепке невидима, то есть два разных
        # детектора давали неотличимые слепки.
        "adapter": {"name": det.name,
                    "module": type(det).__module__,
                    "sha256": _sha256(sys.modules[type(det).__module__].__file__),
                    "sha256_command": _sha256(os.path.join(here,
                                                           "detect.py"))},
        "policy": policy.snapshot(getattr(det, "policy_name", None)),
        "prompts": {},
        "generation": {"temperature": None, "max_tokens": None,
                       "top_p": None, "seed": None},
        "packages": _packages(),
        "weights": {"vl": None, "layout": fp["sha256_weights"]},
        "fingerprint": fp,
        "summary": {"page_count": len(idxs), "box_count": total,
                 "artifacts": artefacts, "rank_ties": ties,
                 "seconds": round(took, 2), "by_label": counts,
                 "best_rejected": rej_best,
                 "pages_with_rejected": rej_pages,
                 # ЧЕЙ ЭТО ЭТАП — рядом с числами, а не только в журнале.
                 # «по ярлыкам» и «рамок» сняты ПОСЛЕ вендорского конвейера,
                 # «лучший отвергнутый» — порогом модели ДО него; без этой
                 # записи слепок двух прогонов различался бы одной строкой в
                 # реестре ручек, а числа в «итоге» — этапом.
                 "stages": {
                     "box_counts_stage":
                         box_stage,
                     "best_rejected_stage":
                         "порогом модели, ДО конвейера вендора",
                     # Неполная сумма — это НЕ величина: страница, о которой
                     # адаптер промолчал, делает её меньше настоящей ровно на
                     # столько, сколько мы не знаем. Поэтому либо число, либо
                     # `null` рядом со счётчиком промолчавших страниц.
                     "boxes_from_model":
                         None if mute_pages else model_boxes,
                     "pages_without_boxes_accepted":
                         mute_pages,
                     "vendor_pipeline": {
                         "stage_ran": had_pipeline,
                         "modes": sorted(str(m) for m in pipe["modes"]),
                         "pages_through_it": pipe["page_count"],
                         "pages_in_run": len(idxs),
                         "boxes_before": pipe["before"],
                         "boxes_after": pipe["after"],
                         "boxes_removed": pipe["before"] - pipe["after"],
                         "moved_to_children": pipe["children"],
                         "boxes_reordered": pipe["reordered"],
                         # Значение, а не пропуск: снятое по ярлыкам не
                         # разложено потому, что адаптер отдаёт «рамок до»
                         # только итогом.
                         "removed_by_label": None,
                         "why_removed_by_label_empty":
                             ("адаптер отдаёт «рамок до» одним числом на "
                              "страницу; по классам их нет — см. pipe_meta "
                              "в models/docling_heron.py"),
                         "numbers_never_given":
                             sorted(pipe["missing_numbers"]),
                     },
                 }},
        # Строка обязана быть исполнимой: в raw/ пять файлов из девяти несут
        # пробелы и скобки, и неэкранированная строка повтора — не строка
        # повтора, а её описание.
        "repeat_command": " ".join(shlex.quote(a) for a in
                           ["books", "detect", pdf, "--out", outdir]
                           + (["--pages", str(pages_spec)] if pages_spec else [])),
    }
    with open(os.path.join(outdir, "run.json"), "w", encoding="utf-8") as f:
        json.dump(snap, f, ensure_ascii=False, indent=1)
    log(f"слепок: {os.path.join(outdir, 'run.json')}")
    return outdir
