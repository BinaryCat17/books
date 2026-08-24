# -*- coding: utf-8 -*-
"""Общий каркас приёмки Э6.

Одно дерево исходников на запуск, задаётся `BOOKSMITH_SRC`.  Так один и тот
же набор гоняется по всем правкам, а не только по своей: `BOOKSMITH_SRC=
~/booksmith-work/e4/src ./run_all.sh`.  Проверка, для которой в дереве нет
функции, ГРОМКО пропускается — молчаливый пропуск и есть фон.

Стенд — не выдумка, а вырезка: 12 настоящих страниц настоящей книги во всех
трёх проходах, собранная `tools/make_stand.py`.  Провенанс каждой вырезки —
в `stand/<книга>/ИСТОЧНИК.txt`.
"""
import os, re, shutil, subprocess, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
# Корпус лежит РЯДОМ с проверками (`tests/stand`, `tests/fixtures`), а не
# этажом выше: в репозитории корень занят самим проектом, и сваливать туда
# 2 МБ стенда незачем.  Запасной путь — этажом выше: так корпус лежал в
# каталоге этапа, откуда проверки пришли, и ссылки на него остались в отчётах.
E6 = HERE if os.path.isdir(os.path.join(HERE, "stand")) \
    else os.path.dirname(HERE)
SRC = os.path.abspath(os.environ.get("BOOKSMITH_SRC", "/home/smirn/books/src"))
STAND = os.path.join(E6, "stand")
FIX = os.path.join(E6, "fixtures")
BOOKS = "/home/smirn/books/processed"
STANDS = ("chugun", "feynman-1", "ogneupory")
# Настоящие книги гоняем только по требованию: минуты против секунд.
SLOW = os.environ.get("E6_SLOW") == "1"

sys.path.insert(0, SRC)


def mod(name):
    """Модуль пакета из выбранного дерева."""
    import importlib
    return importlib.import_module("booksmith." + name)


def need(obj, attr):
    """Есть ли в этом дереве нужное; иначе проверку пропустить ГРОМКО."""
    if not hasattr(obj, attr):
        raise unittest.SkipTest(
            f"в {os.path.relpath(SRC, os.path.expanduser('~'))} нет "
            f"{getattr(obj, '__name__', obj)}.{attr} — проверка НЕ выполнена")
    return getattr(obj, attr)


# `<[^<>]*>`, а не `<[^>]+>`.  Жадный класс ест не тег, а всё от голой угловой
# скобки до ближайшего `>`: в книгах она приходит из математики (`$1 < K$`), и
# линейка занижала счёт слов на 9.0% у «Огнеупоров» (84 069 против 92 405).
# Прибор, которым меряют инвариант «слов не убыло», не имеет права шататься от
# того, сколько в тексте формул.  Ту же правку `structure.py` уже получил.
TAG = re.compile(r"<[^<>]*>")
WORD = re.compile(r"[^\W_]+", re.UNICODE)


def counts(text):
    """Величины, которые ни одна правка не имеет права уменьшить.

    Слова считаются ПОСЛЕ снятия тегов и по одному определению на весь набор:
    смешение определений слова уже трижды портило выводы в этом проекте.
    """
    bare = TAG.sub(" ", text)
    return {
        "таблиц": len(re.findall(r"<table\b", text, re.I)),
        "ячеек": len(re.findall(r"<t[dh]\b", text, re.I)),
        "тегов картинок": len(re.findall(r"<img\b", text, re.I)),
        "слов": len(WORD.findall(bare)),
        "знаков без тегов": len(re.sub(r"\s+", " ", bare)),
        "⚠": text.count("⚠"),
        "≠": text.count("≠"),
        "пометок mark": len(re.findall(r"<mark\b", text)),
    }


def less(before, after, slack=()):
    """Что убыло: список строк «величина было -> стало»."""
    return [f"{k}: {before[k]} -> {after[k]}" for k in before
            if k not in slack and after.get(k, 0) < before[k]]


def stand_copy(book, into=None):
    """Свежая копия стенда во временном каталоге (репозиторий не трогаем)."""
    d = into or tempfile.mkdtemp(prefix="e6-")
    dst = os.path.join(d, book)
    shutil.copytree(os.path.join(STAND, book), dst)
    # Картинки читаем НА МЕСТЕ, ссылкой: копировать сотни мегабайт нельзя.
    real = os.path.join(BOOKS, book, "imgs")
    if os.path.isdir(real):
        os.symlink(real, os.path.join(dst, "imgs"))
    return dst


def quiet(fn, *a, **kw):
    """Выполнить, спрятав печать; вернуть (результат, что напечатано)."""
    import contextlib, io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        r = fn(*a, **kw)
    return r, buf.getvalue()


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


DATA = os.path.join(E6, "data")


def digest(path):
    import hashlib
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def book_files(outdir):
    """Книга, оглавление, отчёт — то, что обязано быть побайтово устойчивым."""
    lay = mod("layout")
    p = lay.Paths(outdir)
    return [x for x in (p.book, p.toc, p.report) if os.path.exists(x)]


def real_books():
    """Настоящие книги — КОПИЯ текста в e6/data, а не сам репозиторий.

    Медленный слой пишет (`restructure` переписывает книгу на месте), поэтому
    он не смеет работать в `/home/smirn/books/processed`.  Копию делает
    `tools/copy_text.py`: 157 МБ, 3 с.
    """
    if not os.path.isdir(DATA):
        return []
    return [os.path.join(DATA, b) for b in sorted(os.listdir(DATA))
            if os.path.isdir(os.path.join(DATA, b, "passes"))]
