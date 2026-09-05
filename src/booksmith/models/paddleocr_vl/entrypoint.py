"""Чтение блоков на арендованной карте. Исполняется НА боксе.

ЗДЕСЬ НЕТ НИ ОДНОГО ПОВТОРЁННОГО ПРАВИЛА, и это главное отличие от соседнего
`dots_ocr/entrypoint.py`. Тот несёт свою копию разбора страниц и сам про себя
пишет: «СТОРОЖА У ЭТИХ ДВУХ КОПИЙ НЕТ… расхождение поймает только человек».
Проект уже платил за такое расхождение — реестр ручек против сборщика
задания, 13 имён из 17, — и повторять его во второй раз незачем.

Вместо копии на машину едет САМ ПАКЕТ: `spec()` кладёт `src/booksmith`
входным файлом (1.1 МБ, против 6.2 ГБ весов — величина, которой можно
пренебречь), а этот файл только подставляет пути и зовёт `booksmith.read.run`.
То есть дома и на карте исполняется ОДИН И ТОТ ЖЕ код, вплоть до байта, и
проверен он дома против подставного сервера — бесплатно и заранее
(`tests/test_read.py`, 27 проверок).

ЧТО ЗДЕСЬ СВОЁ, А НЕ ОБЩЕЕ. Ровно три вещи, и все три — про то, что машина
чужая: путь к книге (она приезжает как `input.pdf`, а слепок детекции помнит
домашний путь), адрес поднятого vLLM и место результата. Всё остальное —
общее.

ЧТО ОБЯЗАНО ПАДАТЬ ЗДЕСЬ, А НЕ НА ПОЛПУТИ. Отсутствие пакета, отсутствие
каталога детекции, адрес, отвечающий чужим именем модели. Каждое из трёх
стоит денег ровно столько, сколько тикает карта, поэтому проверяется до
первой вырезки.
"""
import argparse
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))


def log(*a):
    print(f"[{time.strftime('%H:%M:%S')}]", *a, flush=True)


def main(argv=None):
    ap = argparse.ArgumentParser(description="второй уровень на боксе")
    ap.add_argument("--pkg", default=HERE,
                    help="каталог, где лежит пакет booksmith (уезжает с заданием)")
    ap.add_argument("--detect", required=True, help="каталог books detect")
    ap.add_argument("--pdf", required=True, help="книга, как она легла на бокс")
    ap.add_argument("--out", required=True)
    ap.add_argument("--server", required=True, help="адрес vLLM вместе с /v1")
    ap.add_argument("--model", default="")
    ap.add_argument("--pages", default="")
    ap.add_argument("--policy", default="PP-DocLayoutV2")
    # `run.sh` подставляет этот ключ при `RESUME=0`, а `RESUME` — объявленная
    # ручка реестра, которую пробрасывает `knobs.passthrough()`. Прежде ключа
    # здесь не было вовсе, и оператор, задавший `RESUME=0`, получал
    # `error: unrecognized arguments: --no-resume`, код 2 — ПОСЛЕ аренды,
    # разворачивания и подъёма vLLM. Вторая половина той же беды: `resume` не
    # передавался в `read_book` вовсе, то есть при `RESUME=1` ручка тоже
    # ничего не решала. Третьего поведения у неё не было.
    ap.add_argument("--no-resume", action="store_true",
                    help="спрашивать заново даже то, что уже прочитано")
    a = ap.parse_args(argv)

    # Пакет ищем ЯВНО и падаем вслух: без него дальше пошли бы `ImportError`
    # из середины прохода, то есть уже за деньги и на полпути.
    if a.pkg not in sys.path:
        sys.path.insert(0, a.pkg)
    try:
        from booksmith.read import http as vhttp
        from booksmith.read import run as vread
    except ImportError as e:
        raise SystemExit(
            f"пакет booksmith не поднимается из {a.pkg}: {e}. На машину он "
            f"едет входным файлом задания (`spec()` рядом); без него считать "
            f"нечем, и лучше сказать это сейчас, чем на середине книги.")

    if not os.path.isdir(os.path.join(a.detect, "pages")):
        raise SystemExit(f"в {a.detect} нет pages/ — каталог детекции не приехал")

    # Адрес и имя модели — через окружение, потому что их читает транспорт из
    # реестра ручек. Мимо реестра здесь не ходит ничто: ручка, прочитанная в
    # обход, не попадёт в слепок, и прогон станет неповторимым молча.
    os.environ["VLM_ENDPOINT"] = a.server
    if a.model:
        os.environ["MODEL_NAME"] = a.model

    reader = vread.build_reader(a.policy)
    transport = vhttp.build()
    who = transport.check()
    log(f"адрес {who['адрес']}: отвечает {who['модели на сервере']}, "
        f"спрашиваем {who['спрашиваем']} — совпало")

    pages = None
    if a.pages and a.pages != "-":
        import pymupdf
        from booksmith.detect import parse_pages
        with pymupdf.open(a.pdf) as d:
            pages = set(parse_pages(a.pages, d.page_count))

    t = vread.read_book(a.detect, a.out, reader, transport,
                        resume=not a.no_resume,
                        pages_want=pages, log=log, pdf=a.pdf)
    vread.report(t, log=log)
    vread.snapshot(a.detect, a.out, reader, transport, t,
                   {"detect": a.detect, "out": a.out, "pages": a.pages,
                    "на боксе": True})
    # Число, а не «готово»: по нему видно, за что заплачено.
    log(f"итог: прочитано {t['прочитано']} из {t['спрошено']} спрошенных, "
        f"знаков {t['знаков']}, счёта {t['секунд счёта']:.0f} с")
    return 0


if __name__ == "__main__":
    sys.exit(main())
