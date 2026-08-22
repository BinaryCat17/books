"""Где что лежит в каталоге разбора и как книга называется.

Раскладку знает только этот модуль.  До него имя `book.md` было зашито в
восьми файлах в двадцати девяти местах, а проходы лежали каталогами-соседями
с приставкой `-passN`, и связь между ними держалась на совпадении имён.
Каталог `processed/book-new` при этом нигде не сообщал, что он про станки:
`run.json` записывал модель, число страниц и скорость — и ни слова об
исходнике.

Нынешняя раскладка::

    processed/<имя>/
      <книга>.md            готовый текст — с ним и работают
      <книга>.toc.md        оглавление с номерами строк
      <книга>.html .epub .fb2
      imgs/                 картинки, на которые ссылается текст
      report.md             отчёт о разборе, пишется кодом
      run.json              исходник, страниц, проходов, сколько стоило
      passes/
        1/  pages/ book/ job.log run.json      основа разбора
        2/  pages/ book/ job.log               свидетель
        3/  …

Наверху только готовое.  Всё черновое — постраничный вывод распознавателя,
служебные журналы, слепки — лежит в `passes/`, и по имени каталога видно, что
это черновик, а не книга.

Картинки при сборке ПЕРЕЕЗЖАЮТ из первого прохода наверх, а не копируются:
книга ими владеет, ссылки в тексте (`imgs/…`) от переезда не меняются, и 81 МБ
не лежит на диске дважды.

Про имя.  Оно берётся из имени исходного pdf и хранится в `run.json`, а не
выводится из имени каталога: каталог оператор называет наспех (`book-new`), а
книга должна называться книгой.  Пробелы заменяются подчёркиваниями — иначе
каждое обращение из оболочки требует кавычек.

Старая раскладка (`book/book.md` + `pages/` в корне) продолжает читаться: в
ней лежит каждый отдельный проход, и `books restructure` на проходе — законный
способ посмотреть, что дал именно он.
"""
import glob
import json
import os
import re

PASSES = "passes"
DRAFT = "book.md"          # как книжный файл зовётся внутри прохода


def clean_stem(name):
    """Имя книги из имени файла: `Фейнман. 1.pdf` -> `Фейнман._1`.

    Убираем только то, что мешает: расширение, пробелы (иначе каждый вызов из
    оболочки требует кавычек), разделители пути и управляющие знаки.  Буквы,
    точки и подчёркивания оставляем как есть — имя должно оставаться узнаваемым
    в списке файлов, а не превращаться в транслитерированный огрызок.
    """
    stem = os.path.splitext(os.path.basename(str(name)))[0]
    stem = re.sub(r"[\s]+", "_", stem.strip())
    stem = re.sub(r"[/\\\x00-\x1f]+", "_", stem)
    stem = stem.strip("._") or "book"
    return stem[:120]


def facts(outdir):
    """Прочитать `run.json` из корня разбора; пусто, если его нет."""
    p = os.path.join(outdir, "run.json")
    try:
        with open(p, encoding="utf-8") as fh:
            d = json.load(fh)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def remember(outdir, **kw):
    """Дописать сведения в `run.json`, не потеряв того, что уже записано."""
    d = facts(outdir)
    d.update({k: v for k, v in kw.items() if v is not None})
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, "run.json"), "w", encoding="utf-8") as fh:
        json.dump(d, fh, ensure_ascii=False, indent=1, sort_keys=True)
    return d


def stem(outdir):
    """Как зовут книгу в этом каталоге.

    Порядок опор — от надёжного к запасному: запись в `run.json`; единственный
    `*.md` в корне (кроме отчёта и оглавления); имя каталога.  Последнее — не
    украшение: каталог, собранный до этой раскладки, иначе не открыть вовсе.
    """
    s = facts(outdir).get("stem")
    if s:
        return s
    tops = [os.path.basename(p)[:-3] for p in glob.glob(os.path.join(outdir, "*.md"))]
    tops = [t for t in tops if t not in ("report", "README")
            and not t.endswith(".toc")]
    if len(tops) == 1:
        return tops[0]
    return clean_stem(os.path.basename(os.path.abspath(outdir)))


def pass_dirs(outdir):
    """Каталоги проходов по порядку номеров; пусто, если их нет."""
    root = os.path.join(outdir, PASSES)
    if not os.path.isdir(root):
        return []
    got = []
    for n in os.listdir(root):
        d = os.path.join(root, n)
        if n.isdigit() and os.path.isdir(d):
            got.append((int(n), d))
    return [d for _, d in sorted(got)]


def pass_dir(outdir, n):
    return os.path.join(outdir, PASSES, str(n))


def assembled(outdir):
    """Собран ли каталог по нынешней раскладке (есть `passes/`)."""
    return bool(pass_dirs(outdir))


class Paths:
    """Пути одного разбора — и в нынешней раскладке, и в старой.

    Старая нужна не ради совместимости с историей, а потому, что каждый
    отдельный проход устроен именно так: `book/book.md` плюс `pages/`.  То
    есть `books restructure passes/1` обязан работать.
    """

    def __init__(self, outdir):
        self.outdir = os.path.abspath(outdir)
        self.passes = pass_dirs(self.outdir)
        self.new = bool(self.passes)
        if self.new:
            self.stem = stem(self.outdir)
            self.book = os.path.join(self.outdir, self.stem + ".md")
            self.toc = os.path.join(self.outdir, self.stem + ".toc.md")
            self.imgs = os.path.join(self.outdir, "imgs")
            self.pages = os.path.join(self.passes[0], "pages")
        else:
            self.stem = "book"
            self.book = os.path.join(self.outdir, "book", DRAFT)
            self.toc = os.path.join(self.outdir, "book", "toc.md")
            self.imgs = os.path.join(self.outdir, "book", "imgs")
            self.pages = os.path.join(self.outdir, "pages")
        self.report = os.path.join(os.path.dirname(self.book), "report.md")
        self.snapshot = self.book + ".before-restructure"

    def __repr__(self):
        kind = "новая" if self.new else "старая"
        return f"<Paths {kind} {os.path.relpath(self.outdir)} книга={self.stem}>"


def draft_of(pass_root):
    """Книжный файл внутри прохода — черновик, собранный распознавателем."""
    return os.path.join(pass_root, "book", DRAFT)
