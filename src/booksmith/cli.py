"""Единая точка входа: books <команда>.

    books doctor                 проверить всё ДО того, как пойдут деньги
    books offers                 посмотреть рынок, ничего не арендуя
    books prepare книга.djvu     развернуть djvu в PDF, разрезав развороты
    books detect книга.pdf       контуры первого уровня, местно и бесплатно
    books html книга.detect/     собрать HTML: текст + артефакты картинками
    books feed книга.detect/     что уехало бы в VLM: кроп или страница с дырами
    books synth                  синтетический стенд: страницы с точной истиной
    books score истина/ рамки/   метрики контуров; --selfcheck — батарея мутаций
    books overlay книга.pdf …    рамки поверх страниц, чтобы посмотреть глазами
    books ls | books down 12345 | books reap
    books ledger                 журнал прогонов и оценки по нему
    books replay --check выход/  полон ли слепок входа

РАЗБОРА ЦЕЛИКОМ ЗДЕСЬ ПОКА НЕТ, и это не упущение. Прежний `books ocr` звал
модель через слой из десятка заплаток поверх чужого пайплайна и собирал книгу
эвристиками; всё это удалено вместе с замерами, которыми оправдывалось, —
они считались против вывода другой модели, а не против известного текста.

Что есть — `books detect`: первая половина первого уровня, контуры без единой
заплатки. Она местная и бесплатная нарочно: метрику контуров надо проверять
на выводе настоящей модели, а не на выдуманных данных, и упереться в это
раньше, чем в деньги.
"""
import argparse
import json
import os
import sys

from . import config
from .models import paddleocr_vl
from .remote import ledger as ledger_mod
from .remote.spec import HostReq
from .remote.vast import Vast, log
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


def cmd_html(a):
    """Продукт первого уровня: текст разметкой, артефакты картинками."""
    from .doc import html as html_mod
    d = _run_dir(a.dir, "books html")
    out = a.out or os.path.join(d, "html")
    html_mod.build(d, out, log=log)
    return 0


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
    doc = pymupdf.open(snap["исходник"]["путь"])
    out = a.out or os.path.join(d, "feed")
    page_dpi = float(snap["растр"]["dpi"])
    p = feed.params()
    log(f"подача {p['подача']}, вырезка {p['dpi вырезки']:.0f} dpi, "
        f"страница {p['dpi страницы']:.0f} dpi, "
        f"заливка дыр {p['заливка дыр']}")
    res, asked, arts = [], 0, 0
    for fp in sorted(glob.glob(os.path.join(d, "pages", "*.json"))):
        with open(fp, encoding="utf-8") as f:
            page = Page.from_json(_json.load(f))
        r = feed.prepare(doc, page, out, page_dpi, log=log)
        asked += r["запросов"]
        arts += r.get("артефактов замазано", r.get("артефактов не послано", 0))
        res.append(r)
    doc.close()
    path = feed.dump({"ручки": p, "страницы": res}, out)
    # Число, а не «готово»: по нему и выбирают подачу.
    log(f"страниц {len(res)}, запросов в VLM {asked} "
        f"({asked/max(len(res),1):.1f} на страницу), артефактов мимо VLM {arts}")
    log(f"{path}; картинки подачи в {out}")
    return 0


def cmd_overlay(a):
    """Рамки поверх страниц: истина сплошной, догадка модели пунктиром."""
    from . import overlay
    marks = [(_pages_dir(a.truth, "--truth"), "И")] if a.truth else []
    if a.detect:
        marks.append((_pages_dir(a.detect, "--detect"), "М"))
    if not marks:
        raise SystemExit("нечего рисовать: задайте --truth и/или --detect")
    out = a.out or os.path.splitext(a.pdf)[0] + ".overlay.pdf"
    only = None
    if a.pages:
        only = [int(x) for x in a.pages.replace(",", " ").split()]
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
    # Не через `check`: `.env` держит только GHCR-креды для сборки образа в
    # CI, локальному прогону он не нужен, а ключ vast живёт отдельно в
    # ~/.config/vastai. Проваливать приёмку из-за него — ложная тревога, а
    # ложная тревога учит не смотреть на приёмку вовсе.
    if not os.path.exists(config.ENV_FILE):
        log(f"  [ – ] .env в корне — нет, и это не беда: он нужен только "
            f"сборке образа (GHCR). Образец: .env.example")

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
    det_line = _doctor_detect()
    pipe_line = _doctor_docling()

    log(("окружение аренды в порядке" if ok else "есть проблемы — см. выше")
        + f"; детекция: {det_line}; конвейер docling: {pipe_line}")
    return 0 if ok else 1


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
    for mod, why in (("onnxruntime", "счёт детектора"), ("cv2", "растр"),
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
        mb = ((r.get("image_gb") or 0) * 8 * 1024 / r["setup_s"]
              if r.get("setup_s") else 0)
        log(f"  {r.get('started_iso','')}  {r.get('job','')[:22]:22s} "
            f"{'ok ' if r.get('ok') else 'сбой'}  "
            f"старт {r.get('setup_s',0)/60:4.1f}м ({mb:4.0f} Мбит/с)  "
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
    p.add_argument("--out", help="куда положить book.html и blocks/")
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
    p.add_argument("--pages", help="только эти страницы, через запятую")
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
