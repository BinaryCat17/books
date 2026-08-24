# -*- coding: utf-8 -*-
"""`_done_pages`: готова та страница, у которой есть `.md`.

Подставка, а не книга: беда воспроизводится десятью файлами, и держать под
неё оплаченный разбор незачем.  Страница пишется двумя вызовами
(`save_to_markdown`, потом `save_to_json`), каждый в своём `try`; первый
может упасть, и тогда на диске лежит `0005.json` без текста.

Прежний счёт брал любой файл с числовым именем.  Что из этого выходило:

    было:  готовых 10, первая дыра 9    (то есть дыры «нет», считаем с конца)
    стало: готовых  9, первая дыра 5    (дыра найдена, считаем с неё)

Разница не в счёте, а в деньгах и в книге: при `--resume` страница 5 не
пересчитывалась НИКОГДА, `run.json` показывал полное число страниц, а в
книге на её месте была тишина.
"""
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.environ.get("BOOKSMITH_SRC") or os.path.join(HERE, "..", "src")
sys.path.insert(0, os.path.abspath(SRC))


def подставка(куда, страниц=10, без_md=(5,)):
    """Каталог страниц, где у части страниц есть json, но нет md."""
    os.makedirs(куда, exist_ok=True)
    for i in range(страниц):
        open(os.path.join(куда, f"{i:04d}.json"), "w").write("{}")
        if i not in без_md:
            open(os.path.join(куда, f"{i:04d}.md"), "w").write(f"страница {i}\n")
    return куда


def как_было(pages_dir):
    """Прежний счёт: любой файл с числовым именем."""
    got = set()
    for n in os.listdir(pages_dir):
        stem = os.path.splitext(n)[0]
        if stem.isdigit():
            got.add(int(stem))
    return got


def первая_дыра(done):
    """Та же арифметика, что в `main()` при `--resume`."""
    if not done:
        return 0
    return next((i for i in range(max(done) + 1) if i not in done), max(done))


def main():
    from booksmith.jobs.paddleocr.entrypoint import _done_pages

    tmp = tempfile.mkdtemp(prefix="e7-done-")
    try:
        pages = подставка(os.path.join(tmp, "pages"))
        файлов = sorted(os.listdir(pages))
        print(f"подставка: {len(файлов)} файлов, 10 страниц, "
              f"у страницы 0005 есть json и НЕТ md")

        было = как_было(pages)
        стало = _done_pages(pages)
        print(f"  было:  готовых {len(было):2d}, первая дыра {первая_дыра(было)}")
        print(f"  стало: готовых {len(стало):2d}, первая дыра {первая_дыра(стало)}")

        беды = []
        if (len(было), первая_дыра(было)) != (10, 9):
            беды.append(f"прежний счёт дал {(len(было), первая_дыра(было))}, "
                        f"а на этой подставке он давал (10, 9)")
        if (len(стало), первая_дыра(стало)) != (9, 5):
            беды.append(f"новый счёт дал {(len(стало), первая_дыра(стало))}, "
                        f"ждали (9, 5)")

        # Мутации: на чём проверка обязана падать.
        print("\nмутации:")
        случаи = [
            ("страница без md в середине", (5,), (9, 5)),
            ("две страницы без md", (3, 7), (8, 3)),
            # Дыры «впереди» нет — считаем с последней готовой (8) и
            # пересчитываем её заново. Лишняя страница карты дешевле
            # пропущенной главы.
            ("последняя страница без md", (9,), (9, 8)),
            ("все страницы целы", (), (10, 9)),
        ]
        for имя, без, ждём in случаи:
            d = подставка(os.path.join(tmp, "m" + "_".join(map(str, без)) or "m"),
                          без_md=без)
            got = _done_pages(d)
            вышло = (len(got), первая_дыра(got))
            ok = вышло == ждём
            print(f"  {'ок  ' if ok else 'МИМО'}  {имя:28s} готовых/дыра "
                  f"{вышло}, ждали {ждём}")
            if not ok:
                беды.append(f"{имя}: {вышло} вместо {ждём}")

        # И главное: старый счёт на той же подставке дыру НЕ находит.
        d = подставка(os.path.join(tmp, "старый"), без_md=(3, 7))
        с = как_было(d)
        if первая_дыра(с) != 9:
            беды.append("прежний счёт вдруг нашёл дыру — подставка не та")
        else:
            print(f"  ок    прежний счёт на той же подставке дыру НЕ находит: "
                  f"готовых {len(с)}, «первая дыра» {первая_дыра(с)}")
        for b in беды:
            print("  !!", b)
        return 1 if беды else 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
