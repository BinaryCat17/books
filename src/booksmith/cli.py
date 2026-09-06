"""Единая точка входа: books <команда>.

    books doctor                 проверить всё ДО того, как пойдут деньги
    books offers                 посмотреть рынок, ничего не арендуя
    books prepare книга.djvu     развернуть djvu в PDF, разрезав развороты
    books detect книга.pdf       ПЕРВЫЙ УРОВЕНЬ: контуры, местно и бесплатно
    books read книга.detect/     ВТОРОЙ УРОВЕНЬ: прочитать блоки моделью (платно)
    books html книга.detect/     собрать HTML: текст + артефакты картинками
    books apply книга.html/       поставить прочитанное в книгу; источник берётся
                                 из её слепка. Повтор бесплатен: что уже стоит,
                                 второй раз не ставится. --status — только отчёт
    books feed книга.detect/     что уехало бы в VLM: кроп или страница с дырами
    books synth                  синтетический стенд: страницы с точной истиной
    books annopage raw/annopage  золотой стенд: настоящие страницы с истиной
    books subset                 выжимка: артефакты бок о бок
    books score истина/ рамки/   метрики контуров; --selfcheck — батарея мутаций
    books text истина/ страницы/ метрика ЧТЕНИЯ: знаки и ячейки таблиц
    books fitness книга.pdf …    доедет ли смысл: по чернилам, без истины
    books overlay книга.pdf …    рамки поверх страниц, чтобы посмотреть глазами
    books ls | books down 12345 | books reap
    books ledger                 журнал прогонов и оценки по нему
    books replay --check выход/  полон ли слепок входа

СПИСОК ВЫШЕ СВЕРЕН С `sub.add_parser`, и это не педантизм: здесь недоставало
ШЕСТИ команд из двадцати — `fitness`, `subset`, `annopage`, `read`,
`apply` (тогда `swap`), `text`, — то есть весь второй уровень был невидим
тому, кто читает шапку.

ОБА УРОВНЯ НА МЕСТЕ. Здесь стояло «разбора целиком тут пока нет… что есть —
`books detect`, первая половина первого уровня»: верно до появления
`books read`. Прежний `books ocr` действительно звал модель через слой из
десятка заплаток поверх чужого пайплайна и собирал книгу эвристиками, и всё
это удалено вместе с замерами, которыми оправдывалось (они считались против
вывода другой модели, а не против известного текста). Нынешний второй уровень
устроен иначе: он ничего не правит, кладёт наблюдённое сбоку и проверяется
дома против подставного сервера — 27 проверок, ни одного цента.
"""
import argparse
import json
import re
import os
import sys

from . import config
from .models import paddleocr_vl
from .remote import ledger as ledger_mod
from .remote.spec import HostReq
from .remote.vast import Vast, log
from .run import knobs
from .run import replay as replay_mod


def _host_args(ap):
    ap.add_argument("--gpu", default="RTX_4090",
                    help="RTX_4090 / RTX_5090 / A100_PCIE ...")
    ap.add_argument("--max-dph", type=float, default=0.60, help="потолок $/час")
    ap.add_argument("--disk", type=int, default=60, help="диск инстанса, ГБ")
    ap.add_argument("--machine", type=int,
                    help="привязаться к machine_id с прогретым кешем")
    ap.add_argument("--image", help="переопределить docker-образ")


def cmd_offers(a):
    """Показать рынок так, как его видит ранжирование. Ничего не арендует."""
    host = HostReq(gpu=a.gpu, disk_gb=a.disk, max_dph=a.max_dph,
                   machine_id=a.machine)
    # Требование к CUDA приходит ОТ МОДЕЛИ, а не из слоя аренды: у `HostReq`
    # умолчания нет нарочно. Кто строит задание — тот и называет версию.
    host.cuda_min = paddleocr_vl.CUDA_MIN
    v = Vast()
    warm = ledger_mod.warm_machines(a.image or paddleocr_vl.BASE_IMAGE)
    v.pick(host, paddleocr_vl.IMAGE_GB, a.minutes, warm, show=8,
           payload_gb=paddleocr_vl.PAYLOAD_GB, warmup_s=paddleocr_vl.WARMUP_S)
    return 0


def cmd_prepare(a):
    """Развернуть djvu в PDF, разрезав развороты. Местно и бесплатно.

    Отдельной командой, а не только внутри разбора: развороты надо посмотреть
    глазами до того, как платить за карту. Две из трёх добавленных книг лежали
    разворотами, и распознаватель прочитал бы две страницы как одну.
    """
    from . import djvu
    print(djvu.to_pdf(a.file, dst=a.out, split=a.split))
    return 0


def cmd_detect(a):
    """Контуры первого уровня по страницам PDF. Ни VLM, ни аренды, ни денег."""
    import shlex
    from . import detect
    out = a.out or os.path.splitext(a.file)[0] + ".detect"
    detect.run(a.file, out, a.pages, log=log)
    # Экранируем: в raw/ пять файлов из девяти несут пробелы и скобки, и
    # подсказка, которую нельзя вставить в оболочку, — не подсказка.
    log(f"проверить полноту слепка: books replay --check {shlex.quote(out)}")
    return 0


# ------------------------------------------------ каталоги на входе команд
# `books detect` оставляет рядом ДВА разных каталога: `<выход>` со слепком
# `run.json` и `<выход>/pages` со страницами разметки. Половина команд просила
# первый (`html`, `feed`, `replay --check`), половина — второй (`score`,
# `text`, `fitness --detect`), а разницу оператор узнавал трассировкой из
# шести кадров: «MetricError: в bench/matematika/detect нет страниц
# разметки». Ниже обе формы принимаются обеими сторонами, а несуществующее
# падает ОДНОЙ строкой, которая называет, что именно ожидалось.


def _page_files(d):
    """(сколько страниц разметки, а если ноль — то почему именно).

    Отбор тот же, что у `metrics._load`: имя на `.json` кроме `run.json`, и
    поля `blocks`/`index` внутри. Разойдись он — и команда приняла бы каталог,
    на котором метрика потом падает: внятное сообщение отодвинулось бы на шаг,
    а не появилось.

    В файл заглядываем в ОДИН, первый по имени, а не во все: 600 страниц
    золотого стенда читать ради выбора каталога дорого, а корень книги от
    каталога страниц отличается уже по первому файлу (`manifest.json` против
    `0000.json`).

    Причина возвращается второй величиной, потому что нули тут РАЗНЫЕ:
    «json-файлов нет вовсе» и «json есть, но это не страницы» — две разные
    ошибки оператора, и подать их одной строкой значило бы соврать той самой
    заменой одного нуля другим, от которой заведено правило проекта.
    """
    if not os.path.isdir(d):
        return 0, "не каталог"
    names = sorted(f for f in os.listdir(d)
                   if f.endswith(".json") and f != "run.json")
    if not names:
        return 0, "json-файлов нет вовсе"
    try:
        with open(os.path.join(d, names[0]), encoding="utf-8") as f:
            first = json.load(f)
    except (OSError, ValueError) as e:
        return 0, f"{names[0]} не читается как json ({type(e).__name__})"
    if not (isinstance(first, dict) and "blocks" in first
            and "index" in first):
        return 0, (f"json-файлов {len(names)}, но {names[0]} — не страница "
                   f"разметки: нет полей blocks/index")
    return len(names), ""


def _pages_dir(path, what):
    """Каталог СТРАНИЦ: из каталога прогона или из него самого.

    Возвращается именно `<выход>/pages`, а не `<выход>`: `metrics._same_book`
    ищет `run.json` В РОДИТЕЛЕ поданного каталога, и подмена родителя молча
    отключила бы сверку sha256 истины и вывода — ту самую, что ловит счёт
    истины одной книги против рамок другой.
    """
    if not os.path.exists(path):
        raise SystemExit(
            f"{what}: нет пути {path}. Ожидается каталог прогона "
            f"`books detect` (в нём pages/ и run.json) или сам каталог "
            f"страниц разметки (*.json).")
    sub = os.path.join(path, "pages")
    (here, why_here), (there, why_sub) = _page_files(path), _page_files(sub)
    if there and not here:
        # Величина, а не молчание: подменённый каталог обязан быть виден в
        # журнале, иначе «померено не то» не отличить от «померено».
        log(f"{what}: подан каталог прогона, страницы беру из {sub} — их "
            f"{there}")
        return sub
    if here:
        return path
    raise SystemExit(
        f"{what}: страниц разметки не нашлось. В {path} — {why_here}; "
        f"в {sub} — {why_sub}. Ожидается каталог прогона `books detect` "
        f"(в нём pages/ и run.json) или сам каталог страниц. Считать "
        f"нечего — и это не ноль потерь.")


def _run_dir(path, what):
    """Каталог ПРОГОНА: тот, где лежит `run.json`. Принимает и `<выход>/pages`.

    Обратная сторона той же беды: `books feed bench/…/detect/pages` падал
    `FileNotFoundError` на `pages/run.json`, ни слова не сказав, что нужен
    родитель.
    """
    if not os.path.exists(path):
        raise SystemExit(
            f"{what}: нет пути {path}. Ожидается каталог прогона "
            f"`books detect` — тот, где лежит run.json.")
    if os.path.exists(os.path.join(path, "run.json")):
        return path
    up = os.path.dirname(os.path.abspath(path.rstrip("/")))
    if _page_files(path)[0] and os.path.exists(os.path.join(up, "run.json")):
        log(f"{what}: подан каталог страниц, слепок беру из {up}")
        return up
    raise SystemExit(
        f"{what}: в {path} нет run.json. Ожидается каталог прогона "
        f"`books detect` (в нём pages/ и run.json), а не каталог страниц и "
        f"не корень книги.")


def book_home(detect_dir: str) -> str:
    """Куда книга ложится ПО УМОЛЧАНИЮ. В постоянное место, а не рядом с прогоном.

    Прежде умолчанием было `<каталог прогона>/html`, и это верно ровно до
    первого прогона во временном каталоге: книга собиралась, читалась глазами
    и исчезала вместе с ним. Замер этого вечера: обе книги — 378 и 539
    страниц, $0.47 аренды — легли в `/tmp`, и перекладывать пришлось руками.

    Имя берётся из ИСХОДНИКА, а не набирается: книга должна находиться по
    имени файла, с которого снята. Небезопасные для пути знаки заменяются,
    длина режется — но не молча, а с сохранением узнаваемости.
    """
    with open(os.path.join(detect_dir, "run.json"), encoding="utf-8") as f:
        snap = json.load(f)
    stem = os.path.splitext(os.path.basename(snap["source"]["path"]))[0]
    safe = re.sub(r"[^\w.,()-]+", "-", stem, flags=re.UNICODE).strip("-")[:80]
    return os.path.join(config.ROOT, "processed", safe or "book")


def cmd_html(a):
    """Продукт первого уровня: текст разметкой, артефакты картинками."""
    from .doc import html as html_mod
    d = _run_dir(a.dir, "books html")
    out = a.out or book_home(d)
    # ЧУЖОЕ НЕ ЗАТИРАЕМ. В `processed/` лежат книги ПРЕЖНЕГО конвейера, и
    # совпадение имён там вероятно: та же книга, разобранная иначе. Признак
    # своего — `run.json`, который пишет сам сборщик; нет его при непустом
    # каталоге — отказ вслух, а не молчаливая замена чужой работы.
    # ПРИЗНАК СВОЕГО СПРАШИВАЕМ У СБОРЩИКА, А НЕ НАБИРАЕМ ЗДЕСЬ. Слепок
    # переехал в `assets/`, и эта проверка, искавшая `run.json` в КОРНЕ,
    # начала отказывать каталогу, сделанному этой же командой минуту назад, —
    # причём отказывать ЛОЖЬЮ: «это, скорее всего, книга прежнего
    # конвейера», которых в проекте больше нет ни одной. Под тот же отказ
    # попадал и совет, который печатает сама сборка («книга пересобирается
    # без него — books html <книга>/assets/source»).
    #
    # `наш_каталог` живёт в `doc/html.py` рядом с тем, кто слепок пишет.
    if (not a.out and os.path.isdir(out) and os.listdir(out)
            and not html_mod.is_our_dir(out)):
        raise SystemExit(
            f"в {out} уже лежит что-то не наше: нет ни "
            f"`{html_mod.ASSETS}/run.json`, ни `run.json` в корне — значит "
            f"каталог собран не `books html`. Затирать его молча нельзя: "
            f"задайте --out либо уберите каталог руками.")
    html_mod.build(d, out, log=log)
    return 0


def cmd_apply(a):
    """Второй уровень на месте: поставить разметку вместо картинки, и откатить.

    Обращений к модели здесь нет ни одного — слой умеет только поставить
    готовый кусок. Кто его породил, решает адаптер, и до его появления замену
    можно проверить руками, не потратив ни цента.
    """
    from .doc import apply as ap
    # НЕ `_run_dir`: тот ищет `run.json` каталога ДЕТЕКЦИИ и в отказе зовёт в
    # каталог с `pages/`, а этой команде нужен каталог СБОРКИ — с `book.html`.
    # `apply.py` про `run.json` не знает вовсе. Прежняя проверка отказывала
    # правильному каталогу и советовала не тот.
    d = os.path.abspath(a.dir)
    try:
        if a.from_read:
            if a.anchor or a.undo:
                raise ap.SwapError(
                    "--from вместе с --anchor или --undo: это разные работы. "
                    "--from ставит ВСЁ прочитанное, --anchor — один блок.")
            ap.from_read(d, a.from_read, log=log)
            return 0
        if a.status:
            ap.status(d, log=log)
            return 0
        if a.undo and not a.anchor:
            raise ap.SwapError(
                "--undo без --anchor: назови блок, который откатывать. "
                "Без имени команда откатила бы неизвестно что; список "
                "заменённых даёт `books apply <каталог> --status`.")
        if a.undo:
            ap.undo(d, a.anchor, log=log)
        elif a.anchor:
            if not a.file:
                raise ap.SwapError("нечего ставить: дай --file с разметкой "
                                   "блока либо --undo")
            with open(a.file, encoding="utf-8") as f:
                ap.put(d, a.anchor, f.read(), kind=a.kind,
                       source=a.source or os.path.basename(a.file), log=log)
        else:
            # БЕЗ КЛЮЧЕЙ — ДЕЛАЕМ РАБОТУ, а не отчёт. Книга помнит, из какого
            # чтения собрана (`assets/run.json`), и спрашивать это вторично
            # незачем: `books apply книга` — то, что человек набирает первым.
            #
            # Безопасно это стало только вместе с идемпотентностью: повтор
            # ничего не ставит и стопку отката не растит. До неё второй
            # `--from` на той же книге давал «поставлено 412» при неизменном
            # содержимом и удваивал журнал (412 замен -> 824).
            #
            # Отчёт никуда не делся — он под `--status`, и его же печатает
            # сама работа: «уже стояло N».
            src = ap.source_of(d)
            if not src:
                raise ap.SwapError(
                    f"{d}: не знаю, что ставить. В `{ap.ASSETS}/run.json` нет "
                    f"пути каталога чтения либо его больше нет на диске — "
                    f"назови его сам: `books apply {os.path.basename(d)} "
                    f"--from <каталог books read>`. Что уже заменено, "
                    f"покажет `--status`.")
            log(f"источник взят из слепка книги: {src}")
            ap.from_read(d, src, log=log)
    except ap.SwapError as e:
        log(str(e))
        return 1
    return 0


def cmd_read_rented(a, policy_name, out):
    """Та же работа на АРЕНДОВАННОЙ карте. Отдельная ветка, а не отдельная
    команда: считает то же самое и тем же кодом, меняется только место.

    ЗАЧЕМ ЭТА ВЕТКА ВООБЩЕ ПОЯВИЛАСЬ. `models/paddleocr_vl.spec()` и
    `remote.run_job()` не звала НИ ОДНА команда проекта — проверено grep-ом по
    всему дереву: только определения и проза в комментариях. То есть «читать
    на арендованной карте» нельзя было запустить ничем, и это выяснилось не
    чтением кода, а прямым вопросом «а какой командой?».
    """
    from .models import paddleocr_vl as vl
    from .remote import runner

    spec = vl.spec(_pdf_of(a.dir), a.dir, pages=a.pages, policy=policy_name,
                   budget_usd=a.budget, timeout_minutes=a.timeout)
    log(f"задание {spec.name}: вход {len(spec.inputs)} путей, потолок "
        f"${spec.budget_usd:.2f} и {spec.timeout_minutes:.0f} мин, карта "
        f"{spec.host.gpu}, CUDA от {spec.host.cuda_min}")
    # ПОТОЛОК ПО ДЕНЬГАМ НЕДОСТИЖИМ, ПОКА ОН БОЛЬШЕ ЧАСОВОЙ ЦЕНЫ. `Budget`
    # берёт минимум из двух, и при потолке цены $0.60/час рубеж в $0.60
    # означает ровно час — то есть режет всегда время, а деньги не режут
    # никогда. Сказать об этом обязан тот, кто платит, а не тот, кто потом
    # разбирает журнал.
    by_money_h = a.budget / max(spec.host.max_dph, 1e-9)
    if by_money_h * 60 >= a.timeout:
        log(f"  ВНИМАНИЕ: при цене до ${spec.host.max_dph:.2f}/час потолок "
            f"${a.budget:.2f} — это {by_money_h:.1f} ч, то есть больше "
            f"{a.timeout:.0f} мин таймаута. Резать будет ВРЕМЯ; настоящая "
            f"верхняя трата — ${spec.host.max_dph * a.timeout / 60:.2f}")
    if a.dry_run:
        log("--dry-run: ничего не арендую, задание собрано и проверено")
        return 0
    rc = runner.run_job(spec, out, ssh_key=config.ssh_key(a.key),
                        dry_run=False)
    log(f"задача вернула {rc}; результат в {out}")
    if rc == 0:
        log(f"дальше: books text <истина> {out}/pages   |   books html {out}")
    return rc


def cmd_read(a):
    """ВТОРОЙ УРОВЕНЬ: прочитать содержимое блоков моделью.

    Единственная команда проекта, которая тратит деньги за пределами аренды, —
    и потому единственная, которая ДО первого запроса спрашивает у адреса, как
    его зовут, и роняет прогон при несовпадении.

    Продукт — тот же `pages/*.json`, что у детекции, только с заполненными
    `content`/`kind`. Значит `books html`, `books text`, `books score`,
    `books fitness` и `books overlay` едят его без единой правки.
    """
    from .read import http as vhttp
    from .read import run as vread

    out = a.out or (os.path.abspath(a.dir).rstrip("/") + ".read")
    # СЛОВАРЬ ЯРЛЫКОВ БЕРЁТСЯ ИЗ СЛЕПКА ДЕТЕКЦИИ, а не вбивается руками.
    # `run.json` детекции уже несёт `политика.словарь`; вбитое умолчание
    # расходилось с ним молча, и ловилось лишь СЛУЧАЙНО — по ярлыку, которого
    # нет в чужом словаре. Замер: `DocLayNet` (11 ярлыков) — строгое
    # подмножество `Docling-egret` (17), и эта пара прошла бы без единого
    # слова, а слепок положил бы рядом два несовместимых утверждения.
    known = json.load(open(os.path.join(a.dir, "run.json"), encoding="utf-8")
                      ).get("policy", {}).get("vocabulary")
    policy_name = a.policy or known
    if not policy_name:
        raise SystemExit(
            f"в слепке {a.dir}/run.json не назван словарь ярлыков, и --policy "
            f"не задан. Спрашивать по угаданному словарю значит вести таблицу "
            f"промтом текста и записать прозу чтением.")
    if a.policy and known and a.policy != known:
        raise SystemExit(
            f"--policy {a.policy!r} против словаря детекции {known!r}. "
            f"Совпадающие ярлыки прошли бы молча, а слепок положил бы рядом "
            f"два несовместимых утверждения. Убери --policy или пересчитай "
            f"детекцию тем детектором, чьим словарём собрался читать.")
    os.makedirs(out, exist_ok=True)
    if a.rent:
        return cmd_read_rented(a, policy_name, out)

    reader = vread.build_reader(policy_name)
    transport = vhttp.build()

    # ЧЕМ ОТВЕЧАЕТ АДРЕС — до первой вырезки и до первого цента.
    who = transport.check()
    log(f"адрес {who['endpoint']}: отвечает {who['models_on_server']}, "
        f"спрашиваем {who['asking_for']} — совпало")

    pages = None
    if a.pages:
        from .detect import parse_pages
        import pymupdf
        with pymupdf.open(_pdf_of(a.dir)) as d:
            pages = set(parse_pages(a.pages, d.page_count))

    t = vread.read_book(a.dir, out, reader, transport,
                        resume=not a.no_resume, pages_want=pages, log=log)
    vread.report(t, log=log)
    p = vread.snapshot(a.dir, out, reader, transport, t,
                       {"detect": a.dir, "out": out, "pages": a.pages,
                        "policy": policy_name})
    log(f"слепок: {p}")
    log(f"дальше: books html {out}   |   books text <истина> {out}/pages")
    return 0


def _pdf_of(detect_dir):
    with open(os.path.join(detect_dir, "run.json"), encoding="utf-8") as f:
        return json.load(f)["source"]["path"]


def cmd_feed(a):
    """Приготовить то, что уехало бы в VLM. Ни одного обращения к модели."""
    import glob
    import json as _json
    import pymupdf
    from .doc import feed
    from .models.base import Page

    d = _run_dir(a.dir, "books feed")
    with open(os.path.join(d, "run.json"), encoding="utf-8") as f:
        snap = _json.load(f)
    doc = pymupdf.open(snap["source"]["path"])
    out = a.out or os.path.join(d, "feed")
    page_dpi = float(snap["raster"]["dpi"])
    p = feed.params(page_dpi)
    log(f"подача {p['feed_mode']}, вырезка {p['crop_dpi']:.0f} dpi, "
        f"страница {p['page_dpi']:.0f} dpi, "
        f"заливка дыр {p['hole_fill']}")
    res, asked, arts = [], 0, 0
    for fp in sorted(glob.glob(os.path.join(d, "pages", "*.json"))):
        with open(fp, encoding="utf-8") as f:
            page = Page.from_json(_json.load(f))
        r = feed.prepare(doc, page, out, page_dpi, log=log)
        asked += r["requests"]
        arts += r.get("artifacts_masked", r.get("artifacts_not_sent", 0))
        res.append(r)
    doc.close()
    path = feed.dump({"knobs": p, "pages": res}, out)
    # Число, а не «готово»: по нему и выбирают подачу.
    log(f"страниц {len(res)}, запросов в VLM {asked} "
        f"({asked/max(len(res),1):.1f} на страницу), артефактов мимо VLM {arts}")
    log(f"{path}; картинки подачи в {out}")
    return 0


def cmd_overlay(a):
    """Рамки поверх страниц: истина сплошной, догадка модели пунктиром."""
    from . import detect, overlay
    marks = [(_pages_dir(a.truth, "--truth"), "И")] if a.truth else []
    if a.detect:
        marks.append((_pages_dir(a.detect, "--detect"), "М"))
    if not marks:
        raise SystemExit("нечего рисовать: задайте --truth и/или --detect")
    out = a.out or os.path.splitext(a.pdf)[0] + ".overlay.pdf"
    only = None
    if a.pages:
        # РАЗБОР ТОТ ЖЕ САМЫЙ, что у `books detect`, а не второй экземпляр.
        # Здесь стоял свой: `[int(x) for x in a.pages.replace(",", " ")…]`, и
        # он расходился с `detect.parse_pages` ТРЕМЯ способами сразу.
        # (1) Счёт. `detect` считает с ЕДИНИЦЫ, а это клало число прямо в
        #     индекс: `books detect --pages 40` даёт лист 0039, а `books
        #     overlay --pages 40` рисовал 0040. Смотришь не тот лист и не
        #     узнаёшь об этом — а глазами в этом проекте смотрят именно так:
        #     продетектировал пару страниц и глянул на них.
        # (2) Диапазоны. `--pages 40-42` у `detect` работает, здесь падало
        #     голым следом стека: ValueError: invalid literal for int().
        # (3) Границы. Номер за пределами книги `detect` объявляет вслух, а
        #     здесь пустой набор давал молчаливое «расхождения на 0
        #     страницах» — ноль от непонимания в итоговой строке.
        import pymupdf
        doc = pymupdf.open(a.pdf)
        total = doc.page_count
        doc.close()
        only = detect.parse_pages(a.pages, total)
    overlay.build(a.pdf, out, marks, only=only, log=log)
    return 0


def cmd_score(a):
    """Метрики контуров: истина против вывода модели."""
    from . import metrics
    truth = _pages_dir(a.truth, "истина")
    det = _pages_dir(a.detect, "рамки модели")
    if a.selfcheck:
        return 1 if metrics.mutations(truth, det, log=log) else 0
    metrics.report(metrics.compare(truth, det), log=log)
    return 0


def text_norm_default():
    """Умолчание нормализации — ИЗ МОДУЛЯ, а не набранное здесь второй раз.

    Второй экземпляр умолчания — ровно то, о чём предупреждает шапка реестра
    ручек: смена значения в коде не доезжает до потребителя, пока кто-нибудь
    не вспомнит про этот файл.
    """
    from . import text
    return text.NORM


def cmd_text(a):
    """Метрика чтения: истина знаков против того, что прочла модель.

    Отдельной командой, а не столбцом в `books score`: та мерит ГЕОМЕТРИЮ и
    ярлыки, эта — ЗНАКИ. Слить их значило бы получить одно число на два
    вопроса, а прибор проекта уже один раз так соврал — «порядок чтения
    согласовано 73%» на стенде, где порядок не размечен вовсе.
    """
    from . import text
    truth = _pages_dir(a.truth, "истина")
    pages = _pages_dir(a.pages, "прочитанное")
    if a.selfcheck:
        return 1 if text.mutations(truth, pages, log=log) else 0
    text.report(text.measure(truth, pages, norm=a.norm), log=log)
    return 0


def cmd_fitness(a):
    """Годность вывода: доедет ли смысл до второго уровня, по чернилам."""
    from . import fitness
    det = _pages_dir(a.detect, "--detect")
    truth = _pages_dir(a.truth, "--truth") if a.truth else ""
    if a.selfcheck:
        return 1 if fitness.mutations(a.pdf, det, truth, log=log) else 0
    fitness.report(fitness.measure(a.pdf, det, truth), log=log)
    return 0


def cmd_subset(a):
    """Выжимка стенда: страницы, где два артефакта одного ярлыка стоят рядом."""
    from . import subset
    books = [x.strip() for x in (a.books or
             "spravochnik,slovar,matematika,atlas,katalog,zhurnal,annopage"
             ).split(",") if x.strip()]
    subset.build(books, a.out or "bench/hard", log=log)
    return 0


def cmd_annopage(a):
    """Золотой стенд из AnnoPage: настоящие страницы с истиной библиотекарей."""
    from . import annopage
    out = a.out or "bench/annopage"
    log(f"AnnoPage из {a.root}, выборка {a.split}")
    annopage.build(a.root, out, split=a.split, limit=a.limit,
                   truth_only=a.truth_only, log=log)
    log(f"дальше: books detect {shlex_quote(out)}/annopage.pdf "
        f"--out {shlex_quote(out)}/detect")
    return 0


def cmd_synth(a):
    """Сложить синтетическую книгу с точной истиной. Местно и бесплатно."""
    from . import synth
    from .run import knobs
    out = a.out or f"bench/{a.book}"
    cases = a.cases.split(",") if a.cases else None
    from .books import load
    log(f"книга {a.book}: случаев {len(cases or load(a.book).CASES)}, "
        f"старение {knobs.knob('SYNTH_AGING')}, зерно {knobs.knob('SYNTH_SEED')}")
    synth.build(out, cases, int(knobs.knob("SYNTH_SEED")),
                knobs.knob("SYNTH_AGING"), book=a.book, log=log)
    log(f"дальше: books detect {shlex_quote(out)}/{a.book}.pdf "
        f"--out {shlex_quote(out)}/detect")
    return 0


def shlex_quote(s):
    import shlex
    return shlex.quote(s)


def cmd_ls(_a):
    v = Vast()
    rows = v.v.show_instances()
    log(f"баланс: ${v.balance():.3f}")
    if not rows:
        log("инстансов нет — денег не тратится")
        return 0
    for i in rows:
        log(f"  {i['id']}  {i.get('actual_status')}  {i.get('label')}  "
            f"${float(i.get('dph_total') or 0):.3f}/час  "
            f"машина {i.get('machine_id')}  {i.get('gpu_name')}")
    return 0


def cmd_down(a):
    return 0 if Vast().destroy(a.id) else 1


def cmd_reap(_a):
    Vast().reap()
    return 0


def cmd_doctor(_a):
    """Проверить всё, что может сорвать прогон, ДО того как деньги пойдут."""
    import shutil
    ok = True

    def check(name, good, hint=""):
        nonlocal ok
        log(f"  [{'ок  ' if good else 'нет '}] {name}"
            + ("" if good else f" — {hint}"))
        ok = ok and good

    log("проверка окружения:")
    check("rsync локально", shutil.which("rsync") is not None,
          "нужен для инкрементальной выкачки: apt install rsync")
    check("ssh локально", shutil.which("ssh") is not None,
          "apt install openssh-client")
    key = config.ssh_key()
    check(f"ssh-ключ {config.DEFAULT_SSH_KEY}", key is not None,
          "ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519_vast -N ''")
    check("публичная часть ключа", bool(key) and os.path.exists(key + ".pub"),
          "без неё ключ не привязать к инстансу")
    # Не через `check`: без `.env` работает всё, кроме платного чтения по
    # СЕТЕВОМУ адресу, а ключ vast живёт отдельно в ~/.config/vastai.
    # Проваливать приёмку из-за него — ложная тревога, а ложная тревога учит
    # не смотреть на приёмку вовсе.
    #
    # Здесь стояло «он нужен только сборке образа (GHCR)», и это было неверно
    # дважды: GHCR-креды не читает никто, даже CI (он логинится через
    # `secrets.GITHUB_TOKEN`), а единственный живой жилец `.env` —
    # `VLM_API_KEY`, который сорока строками ниже спрашивает сам `doctor`.
    # Ключ можно и экспортировать в окружение: `config.env` смотрит туда
    # первым, а на арендованной карте vLLM слушает петлю и ключа не просит.
    if not os.path.exists(config.ENV_FILE):
        log(f"  [ – ] .env в корне — нет; нужен он только для VLM_API_KEY при "
            f"чтении по сетевому адресу. Образец: .env.example")

    try:
        v = Vast()
        bal = v.balance()
        check(f"ключ vast.ai (баланс ${bal:.3f})", True)
        check("баланса хватит хотя бы на прогон", bal > 0.20,
              "пополни: console.vast.ai/billing")
        rows = v.v.show_instances()
        check(f"нет забытых инстансов (сейчас {len(rows)})", not rows,
              "books ls, затем books reap")
    except Exception as e:
        check("ключ vast.ai", False, f"vastai set api-key <КЛЮЧ> ({e})")

    # Отдельными блоками и НЕ через `check`: детекция и вендорский конвейер
    # ставятся необязательными наборами, и тому, кто только арендует, они не
    # нужны. Валить приёмку из-за них — ложная тревога, а ложная тревога учит
    # не смотреть на приёмку вовсе. Но и молчать нельзя: `books detect` —
    # первая работающая команда разбора, и её беда должна быть видна здесь, а
    # не в середине книги.
    # Итог обеих проверок — ВЕЛИЧИНОЙ в последней строке. Прежде здесь стояло
    # голое «всё в порядке», и оно оставалось бы «в порядке» при активном
    # адаптере без весов: команда не знала про него вовсе.
    read_line = _doctor_read()
    det_line = _doctor_detect()
    pipe_line = _doctor_docling()

    log(("окружение аренды в порядке" if ok else "есть проблемы — см. выше")
        + f"; чтение: {read_line}; детекция: {det_line}; "
        + f"конвейер docling: {pipe_line}")
    return 0 if ok else 1


def _doctor_read():
    """Второй уровень: адрес модели и ключ. Возвращает строку для итога.

    Ключ живёт МИМО реестра ручек нарочно: всё объявленное в реестре попадает
    в `run.json` значением, а слепок кладут в git. Оборотная сторона —
    имя, невидимое `knobs.readers()`, то есть болезнь `VL_MODEL_DIR` в
    миниатюре; поэтому оно обязано звучать хотя бы здесь.
    """
    ep = knobs.knob("VLM_ENDPOINT")
    key = config.env("VLM_API_KEY")
    log("чтение блоков (books read, второй уровень):")
    if ep:
        log(f"  [ок  ] VLM_ENDPOINT={ep}, ключ VLM_API_KEY "
            f"{'есть, %d знаков' % len(key) if key else 'не задан'}")
        return f"адрес задан, ключ {'есть' if key else 'нет'}"
    log("  [—   ] VLM_ENDPOINT не задан: `books read` откажется работать "
        "вслух, а не постучится в никуда. Умолчания нет нарочно. На "
        "арендованной карте адрес ставит run.sh, ключ там не нужен — vLLM "
        "поднят на петле")
    return "адрес не задан (для аренды и не нужен)"


def _doctor_detect():
    """Чем сегодня можно считать контуры: пакеты и веса ВСЕХ адаптеров.

    Здесь стояла проверка ОДНИХ весов PP-DocLayoutV2, и приёмка печатала
    «всё в порядке», ничего не зная про три остальных адаптера. Смысл команды
    объявлен как «проверить всё ДО того, как пойдут деньги» — значит она
    обязана знать про всё, чем сегодня считают.

    Список адаптеров читается из `detect.py:ADAPTERS`, а НЕ набирается здесь:
    второй список разошёлся бы молча — этим в проекте уже болели реестр ручек
    против сборщика задания (13 имён из 17) и сам реестр против `ADAPTERS`
    (в описании `LAYOUT_ADAPTER` значилось два адаптера из четырёх).

    Проверка — попытка ПОДНЯТЬ адаптер, а не `os.path.exists` на файле весов:
    у четырёх адаптеров веса зовутся по-разному (`inference.onnx`,
    `model.onnx`, `yolox_l0.05.onnx` по ручке `YOLOX_WEIGHTS`), и список имён
    здесь был бы третьим списком, расходящимся молча. Платим за это
    секундами: граф поднимается на процессоре, и время печатается величиной,
    чтобы цена приёмки была видна, а не подразумевалась.

    Ничего из найденного здесь приёмку НЕ валит: отсутствие необязательного
    набора — не авария. Оно говорит величиной, чего нет и чем включается, и
    той же величиной возвращается в итоговую строку.
    """
    import time
    log("детекция макета (books detect, необязательный набор):")
    missing = []
    for mod, why in (("onnxruntime", "счёт детектора"), ("cv2", "raster"),
                     ("yaml", "чтение inference.yml")):
        try:
            __import__(mod)
        except ImportError:
            missing.append(f"{mod} ({why})")
    if missing:
        log(f"  [ – ] нет пакетов: {', '.join(missing)} — "
            f'поставьте: pip install -e ".[detect]"')
        # Ноль от проверки и ноль от непонимания — РАЗНЫЕ строки: без этих
        # пакетов адаптер не поднять ни один, и «весов нет» сказать не о чем.
        log("  [ – ] веса адаптеров НЕ ПРОВЕРЕНЫ ни у одного: поднимать их "
            "нечем. Это не «весов нет», это «не смотрели».")
        return ("НЕ ПРОВЕРЕНА — нет пакетов набора detect "
                f"({len(missing)} из 3)")

    from . import detect
    from .run import knobs
    active = knobs.knob("LAYOUT_ADAPTER")
    # Зовём тот же `_adapter()`, что и `books detect`, подставив ему имя
    # ручкой: свой разбор имён здесь был бы четвёртым списком.
    saved = os.environ.get("LAYOUT_ADAPTER")
    have, t0 = [], time.time()
    try:
        for which in detect.ADAPTERS:
            os.environ["LAYOUT_ADAPTER"] = which
            t = time.time()
            try:
                det = detect._adapter()
            except (Exception, SystemExit) as e:         # noqa: BLE001
                # `SystemExit` ловится НАРОЧНО: адаптер docling при
                # `DOCLING_PIPELINE=full` без пакета вендора выходит именно
                # им, и приёмка, поймавшая только `Exception`, умирала на
                # втором адаптере из четырёх, не сказав ни про него, ни про
                # два оставшихся, ни про конвейер (rc=1, замерено).
                # «Весов нет» и «веса есть, но адаптер не поднялся» — разные
                # беды: первая чинится скачиванием, вторая ломает прогон при
                # полном каталоге весов.
                kind = ("весов нет" if type(e).__name__ == "WeightsMissing"
                        else f"НЕ ПОДНЯЛСЯ ({type(e).__name__})")
                log(f"  [ – ] {which:14s} {kind}: {e}")
                continue
            w = getattr(det, "onnx", "") or ""
            mb = os.path.getsize(w) / 2 ** 20 if os.path.exists(w) else 0.0
            have.append(which)
            log(f"  [ок  ] {which:14s} {det.name}, ярлыков "
                f"{len(det.labels)}, весов {mb:.0f} МБ, поднялся за "
                f"{time.time() - t:.1f} с — {det.dir}")
            det = None                        # 4 графа разом машину не держим
    finally:
        if saved is None:
            os.environ.pop("LAYOUT_ADAPTER", None)
        else:
            os.environ["LAYOUT_ADAPTER"] = saved
    log(f"  адаптеров поднялось {len(have)} из {len(detect.ADAPTERS)}"
        f" ({', '.join(have) if have else 'ни одного'}), проверка заняла "
        f"{time.time() - t0:.0f} с; книгу сейчас считает LAYOUT_ADAPTER="
        f"{active}")
    line = f"адаптеров поднялось {len(have)} из {len(detect.ADAPTERS)}"
    if active not in detect.ADAPTERS:
        log(f"  ВНИМАНИЕ: LAYOUT_ADAPTER={active!r} — такого адаптера нет; "
            f"знаю {', '.join(detect.ADAPTERS)}")
        line += f", но LAYOUT_ADAPTER={active!r} не из этого списка"
    elif active not in have:
        log(f"  ВНИМАНИЕ: активный адаптер {active} не поднялся (причина "
            f"строкой выше) — `books detect` упадёт, не посчитав ни страницы")
        line += f", активный {active} НЕ ПОДНЯЛСЯ"
    return line


def _doctor_docling():
    """Пакет вендорского конвейера: без него ручка `DOCLING_PIPELINE` мертва.

    Проверяется НАЛИЧИЕ модулей, а не их импорт: `docling.utils.
    layout_postprocessor` поднимается 8.3 с, и класть их в приёмку значило бы
    платить за неё каждый раз. `rtree` при этом импортируется по-настоящему —
    он тянет системный libspatialindex, и «колесо на месте» ещё не значит
    «импортируется»; стоит это 0.2 с.
    """
    import importlib.metadata as md
    import importlib.util as iu
    from .run import knobs

    mode = knobs.knob("DOCLING_PIPELINE")
    log(f"конвейер docling (ручка DOCLING_PIPELINE={mode}, "
        f"необязательный набор):")
    gone = []
    try:
        if iu.find_spec("docling.utils.layout_postprocessor") is None:
            gone.append("docling.utils.layout_postprocessor")
    except (ImportError, ValueError):
        gone.append("docling.utils.layout_postprocessor")
    try:
        __import__("rtree")
    except Exception as e:                               # noqa: BLE001
        gone.append(f"rtree ({type(e).__name__})")
    vers = {}
    for dist in ("docling-slim", "docling", "rtree"):
        try:
            vers[dist] = md.version(dist)
        except md.PackageNotFoundError:
            vers[dist] = None
    if gone:
        log(f"  [ – ] нет: {', '.join(gone)} — поставьте: "
            f'pip install -e ".[docling]". При DOCLING_PIPELINE=post|full '
            f"прогон упадёт вслух, при off (умолчание) он не нужен вовсе")
        return (f"нет {len(gone)} из 2 пакетов"
                + (f", а ручка стоит в {mode}" if mode != "off" else ""))
    # Версия — из ДИСТРИБУТИВА, а не из `docling.__version__`: пакет один и
    # тот же, а поставок две (`docling-slim` и полная), и pyproject колотит
    # версию точкой — правка правил у вендора молча сменила бы наши рамки.
    # Если дистрибутива нет вовсе (исходники на пути), так и сказано: «не
    # объявлена» — это не то же, что «версия такая-то».
    ver = (vers["docling-slim"] or vers["docling"]
           or "версия не объявлена (дистрибутива нет, модуль откуда-то ещё)")
    kind = ("slim" if vers["docling-slim"] else
            "полная поставка" if vers["docling"] else "поставка неизвестна")
    log(f"  [ок  ] docling {ver} ({kind}), rtree {vers['rtree']}; "
        f"включается DOCLING_PIPELINE=post|full поверх адаптеров docling и "
        f"docling-egret, сейчас {mode}")
    return f"{ver} + rtree {vers['rtree']}, ручка в {mode}"


def cmd_ledger(_a):
    rows = ledger_mod.read()
    if not rows:
        log(f"журнал пуст ({ledger_mod.LEDGER})")
        return 0
    ok = sum(1 for r in rows if r.get("ok"))
    spent = sum(r.get("cost_usd") or 0 for r in rows)
    log(f"{len(rows)} прогонов, успешных {ok}, потрачено ${spent:.3f}")
    for r in rows[-10:]:
        # НЕ МЕРИЛИ И НОЛЬ — РАЗНЫЕ ВЕЩИ. Здесь стояло `else 0`, и прогон,
        # у которого `setup_s` нулевой (доставка не дошла до конца — прервано
        # сигналом), печатался как «   0 Мбит/с», то есть «канал мёртв»
        # вместо «замера нет». Таких записей в печатаемой десятке шесть, по всему журналу 29, и вес образа у
        # всех шести ЕСТЬ (0.06 ГБ) — ноль стоит только в `setup_s`; здесь
        # было сказано «нет ни того, ни другого», и это неверно. Соседний
        # комментарий про `download_mbps` предупреждает ровно об этом:
        # `None` значит НЕ МЕРИЛИ.
        #
        # Отрицательный `setup_s` — тоже «не мерили», а не отрицательная
        # скорость: мёртвое свойство отбивало его условием `<= 0`, и при
        # переносе семантики это едва не потерялось.
        #
        # Формула жила ВТОРЫМ экземпляром: в `ledger.Run.observed_mbps` та же
        # арифметика возвращала `None`, но свойство было недостижимо —
        # `asdict` свойств не берёт, и в журнал оно не попадало никогда. Из
        # двух копий верная семантика была у мёртвой. Копию убрали, семантику
        # перенесли сюда.
        setup = r.get("setup_s")
        gb = r.get("image_gb")
        mb = (gb * 8 * 1024 / setup) if (setup or 0) > 0 and gb else None
        log(f"  {r.get('started_iso','')}  {r.get('job','')[:22]:22s} "
            f"{'ok ' if r.get('ok') else 'сбой'}  "
            f"старт {r.get('setup_s',0)/60:4.1f}м "
            f"({'  не мерили' if mb is None else f'{mb:4.0f} Мбит/с'})  "
            f"счёт {r.get('run_s',0)/60:5.1f}м  ${r.get('cost_usd',0):.3f}  "
            f"машина {r.get('machine_id')}")
    log(f"оценка по журналу: {ledger_mod.fit()}")
    return 0


def _tool_errors():
    """Классы «прибор не смог посчитать» — из УЖЕ поднятых модулей.

    Наверху их не импортировать: `metrics` тянет numpy, `text` — свой разбор,
    а тому, кто только арендует машину, набор `detect` не нужен. Поэтому
    спрашиваем `sys.modules`: модуль, который не поднимался, и ошибку бросить
    не мог. Ловим ИМЕННО эти классы, а не `Exception`: трассировка от
    несорванного прибора — беда, а трассировка от нашей ошибки в коде —
    улика, и прятать её нельзя.
    """
    out = []
    for mod, name in (("booksmith.metrics", "MetricError"),
                      ("booksmith.text", "TextError"),
                      ("booksmith.models.doclayout", "WeightsMissing"),
                      ("booksmith.models.docling_heron", "WeightsMissing"),
                      ("booksmith.models.yolox_layout", "WeightsMissing")):
        cls = getattr(sys.modules.get(mod), name, None)
        if isinstance(cls, type) and issubclass(cls, BaseException):
            out.append(cls)
    return tuple(out)


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="books", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("offers", help="показать рынок, ничего не арендуя")
    _host_args(p)
    p.add_argument("--minutes", type=float, default=20.0,
                   help="на сколько минут считать стоимость прогона")
    p.set_defaults(fn=cmd_offers)

    p = sub.add_parser("prepare", help="развернуть djvu в PDF")
    p.add_argument("file")
    p.add_argument("--out", help="куда положить PDF")
    p.add_argument("--split", default="auto", choices=("auto", "yes", "no"),
                   help="резать ли развороты")
    p.set_defaults(fn=cmd_prepare)

    p = sub.add_parser("detect", help="контуры первого уровня, местно")
    p.add_argument("file", help="PDF (djvu разверните через books prepare)")
    p.add_argument("--out", help="куда положить pages/ и run.json")
    p.add_argument("--pages", help="какие страницы: 1,4,7-9; по умолчанию все")
    p.set_defaults(fn=cmd_detect)

    p = sub.add_parser("html", help="собрать HTML из каталога books detect")
    p.add_argument("dir", help="каталог, куда писал books detect")
    p.add_argument("--out", help="куда положить book.html и assets/")
    p.set_defaults(fn=cmd_html)

    p = sub.add_parser("feed", help="что уехало бы в VLM, без обращения к ней")
    p.add_argument("dir", help="каталог, куда писал books detect")
    p.add_argument("--out", help="куда положить картинки подачи")
    p.set_defaults(fn=cmd_feed)

    p = sub.add_parser("fitness",
                       help="годен ли вывод, чтобы гнать через него OCR")
    p.add_argument("pdf", help="страницы, по которым считать чернила")
    p.add_argument("--detect", required=True, help="каталог вывода модели")
    p.add_argument("--truth", default="", help="истина; без неё считается "
                   "только то, что вне всех рамок")
    p.add_argument("--selfcheck", action="store_true",
                   help="батарея порчи: умеет ли число упасть")
    p.set_defaults(fn=cmd_fitness)

    p = sub.add_parser("subset", help="выжимка: артефакты бок о бок")
    p.add_argument("--books", help="какие книги стенда, через запятую")
    p.add_argument("--out", help="куда положить hard.pdf и truth/")
    p.set_defaults(fn=cmd_subset)

    p = sub.add_parser("annopage", help="золотой стенд из датасета AnnoPage")
    p.add_argument("root", help="корень распакованного AnnoPage")
    p.add_argument("--split", default="test", help="test | train")
    p.add_argument("--limit", type=int, default=0, help="взять только N страниц")
    p.add_argument("--truth-only", action="store_true", dest="truth_only",
                   help="переписать только истину, не трогая уже собранный pdf")
    p.add_argument("--out", help="куда положить annopage.pdf и truth/")
    p.set_defaults(fn=cmd_annopage)

    p = sub.add_parser("score", help="метрики контуров против истины стенда")
    p.add_argument("truth", help="каталог истины (bench/synth/truth)")
    p.add_argument("detect", help="каталог вывода модели (…/detect/pages)")
    p.add_argument("--selfcheck", action="store_true",
                   help="батарея мутаций: умеет ли число падать (код 1, если нет)")
    p.set_defaults(fn=cmd_score)

    p = sub.add_parser("read",
                       help="ВТОРОЙ УРОВЕНЬ: прочитать блоки моделью (платно)")
    p.add_argument("dir", help="каталог books detect")
    p.add_argument("--out", default="", help="куда класть; по умолчанию <dir>.read")
    p.add_argument("--pages", default="", help="какие страницы: 1,4,7-9")
    p.add_argument("--policy", default="",
                   help="словарь ярлыков детектора; пусто = взять из слепка "
                        "детекции, а несовпадение с ним — отказ вслух")
    p.add_argument("--no-resume", action="store_true",
                   help="спрашивать заново даже то, что уже прочитано")
    p.add_argument("--rent", action="store_true",
                   help="считать на АРЕНДОВАННОЙ карте, а не по VLM_ENDPOINT: "
                        "снять машину, поднять vLLM, забрать результат")
    p.add_argument("--budget", type=float, default=0.60,
                   help="потолок траты, $; достигнут — машина уничтожается")
    p.add_argument("--timeout", type=float, default=60.0,
                   help="потолок времени, мин; достигнут — то же самое")
    p.add_argument("--dry-run", action="store_true",
                   help="собрать задание и проверить его, ничего не арендуя")
    p.add_argument("--key", default="", help="путь к ssh-ключу для vast.ai")
    p.set_defaults(fn=cmd_read)

    # ИМЯ КОМАНДЫ — `apply`, и здесь стояло `swap`. Два довода, оба про
    # читателя справки. Первое: `swap` называет МЕХАНИКУ («поменять местами»),
    # а не работу — «применить прочитанное к книге», — и ни словом не намекает
    # на журнал с откатом, ради которого команда и существует. Второе: без
    # ключей она ничего не меняет, а печатает отчёт, и приказ «swap» тут
    # читается как действие, а получается справка. `apply` совпадает с именем
    # модуля, который её и делает (`doc/apply.py`), а `--undo` читается как
    # «отменить применённое».
    p = sub.add_parser("apply",
                       help="второй уровень: разметка вместо картинки, и откат")
    p.add_argument("dir", help="каталог сборки (books html --out)")
    p.add_argument("--anchor", help="якорь блока, вида p0042-b17")
    p.add_argument("--file", help="файл с разметкой блока")
    p.add_argument("--kind", default="html",
                   help="вид содержимого: html | otsl | latex | text")
    p.add_argument("--source", default="",
                   help="чем порождено; уезжает в журнал и в атрибут блока")
    p.add_argument("--undo", action="store_true",
                   help="вернуть то, что стояло до последней замены")
    p.add_argument("--status", action="store_true",
                   help="только отчёт: что заменено, ничего не трогая")
    p.add_argument("--from", dest="from_read", default="",
                   help="каталог `books read`: поставить ВСЁ прочитанное, "
                        "по одному блоку и с откатом у каждого")
    p.set_defaults(fn=cmd_apply)

    p = sub.add_parser("text",
                       help="метрика чтения: знаки против истины стенда")
    p.add_argument("truth", help="каталог истины (bench/<книга>/truth)")
    p.add_argument("pages", help="каталог прочитанного (…/detect/pages)")
    p.add_argument("--norm", default=text_norm_default(),
                   help="граница нормализации при сличении; "
                        "объявляется числом и уезжает в отчёт")
    p.add_argument("--selfcheck", action="store_true",
                   help="батарея порчи: умеет ли число падать (код 1, если нет)")
    p.set_defaults(fn=cmd_text)

    p = sub.add_parser("overlay", help="рамки поверх страниц, чтобы посмотреть глазами")
    p.add_argument("pdf", help="страницы, поверх которых рисовать")
    p.add_argument("--truth", help="каталог истины (bench/synth/truth)")
    p.add_argument("--detect", help="каталог вывода модели (…/detect/pages)")
    p.add_argument("--out", help="куда положить pdf с рамками")
    p.add_argument("--pages",
                   help="какие страницы: 1,4,7-9; счёт с единицы, как у detect")
    p.set_defaults(fn=cmd_overlay)

    p = sub.add_parser("synth", help="синтетический стенд с точной истиной")
    p.add_argument("--book", default="spravochnik",
                   help="какая книга стенда: spravochnik|slovar|matematika|"
                        "atlas|katalog|zhurnal")
    p.add_argument("--out", help="куда положить <книга>.pdf и truth/")
    p.add_argument("--cases", help="какие случаи, через запятую; по умолчанию все")
    p.set_defaults(fn=cmd_synth)

    p = sub.add_parser("ls", help="что сейчас арендовано")
    p.set_defaults(fn=cmd_ls)

    p = sub.add_parser("down", help="уничтожить инстанс")
    p.add_argument("id", type=int)
    p.set_defaults(fn=cmd_down)

    p = sub.add_parser("reap", help="уничтожить всё, что оставили наши прогоны")
    p.set_defaults(fn=cmd_reap)

    p = sub.add_parser("doctor",
                       help="проверить окружение до того, как тратить деньги")
    p.set_defaults(fn=cmd_doctor)

    p = sub.add_parser("ledger", help="журнал прогонов и оценки по нему")
    p.set_defaults(fn=cmd_ledger)

    p = sub.add_parser("replay", help="полон ли слепок входа для повтора")
    # nargs="+", а не "*": проверка, весь смысл которой в коде возврата,
    # при пустом списке молча одобряла бы — `books replay --check` без
    # каталога возвращал 0 и не печатал ни строки.
    p.add_argument("outdir", nargs="+", help="каталог разбора")
    p.add_argument("--selfcheck", action="store_true",
                   help="умеет ли сама проверка провалиться (код 1, если нет)")
    p.add_argument("--check", action="store_true",
                   help="печатать недостающее и вернуть 1, если оно есть")
    p.set_defaults(fn=replay_mod.cmd_replay)

    a = ap.parse_args(argv)
    try:
        return a.fn(a) or 0
    except _tool_errors() as e:
        # Код 2 — «посчитать не смог», в отличие от 1 — «посчитал, и число
        # провалилось». Слить их значило бы, что молчащий прибор и провал
        # метрики читаются одинаково; на них разные действия.
        log(f"{type(e).__name__}: {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
