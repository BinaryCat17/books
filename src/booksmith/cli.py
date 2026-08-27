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


def cmd_html(a):
    """Продукт первого уровня: текст разметкой, артефакты картинками."""
    from .doc import html as html_mod
    out = a.out or os.path.join(a.dir, "html")
    html_mod.build(a.dir, out, log=log)
    return 0


def cmd_feed(a):
    """Приготовить то, что уехало бы в VLM. Ни одного обращения к модели."""
    import glob
    import json as _json
    import pymupdf
    from .doc import feed
    from .models.base import Page

    with open(os.path.join(a.dir, "run.json"), encoding="utf-8") as f:
        snap = _json.load(f)
    doc = pymupdf.open(snap["исходник"]["путь"])
    out = a.out or os.path.join(a.dir, "feed")
    page_dpi = float(snap["растр"]["dpi"])
    p = feed.params()
    log(f"подача {p['подача']}, вырезка {p['dpi вырезки']:.0f} dpi, "
        f"страница {p['dpi страницы']:.0f} dpi, "
        f"заливка дыр {p['заливка дыр']}")
    res, asked, arts = [], 0, 0
    for fp in sorted(glob.glob(os.path.join(a.dir, "pages", "*.json"))):
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
    marks = [(a.truth, "И")] if a.truth else []
    if a.detect:
        marks.append((a.detect, "М"))
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
    if a.selfcheck:
        return 1 if metrics.mutations(a.truth, a.detect, log=log) else 0
    metrics.report(metrics.compare(a.truth, a.detect), log=log)
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

    # Отдельным блоком и НЕ через `check`: детекция ставится необязательным
    # набором (`pip install -e ".[detect]"`), и тому, кто только арендует, она
    # не нужна. Валить приёмку из-за неё — ложная тревога, а ложная тревога
    # учит не смотреть на приёмку вовсе. Но и молчать нельзя: `books detect` —
    # первая работающая команда разбора, и её беда должна быть видна здесь, а
    # не в середине книги.
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
    else:
        from .models import doclayout
        d = doclayout.weights_dir()
        have = os.path.exists(os.path.join(d, "inference.onnx"))
        log(f"  [{'ок  ' if have else ' – '}] веса {d}"
            + ("" if have else " — нет; задайте LAYOUT_MODEL_DIR или "
                              "положите веса paddlex"))

    log("всё в порядке" if ok else "есть проблемы — см. выше")
    return 0 if ok else 1


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

    p = sub.add_parser("score", help="метрики контуров против истины стенда")
    p.add_argument("truth", help="каталог истины (bench/synth/truth)")
    p.add_argument("detect", help="каталог вывода модели (…/detect/pages)")
    p.add_argument("--selfcheck", action="store_true",
                   help="батарея мутаций: умеет ли число падать (код 1, если нет)")
    p.set_defaults(fn=cmd_score)

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
    return a.fn(a) or 0


if __name__ == "__main__":
    sys.exit(main())
