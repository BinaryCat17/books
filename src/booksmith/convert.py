"""Разбор -> EPUB и FB2, рядом с книгой.

Обе конвертации идут через pandoc, но по-разному, и это не прихоть.

EPUB собирается напрямую: он основан на XHTML, и наши таблицы, которые лежат в
markdown сырым HTML, доезжают как есть.

FB2 — только в два шага, через настоящий HTML.  Его писатель в pandoc сырой
HTML выбрасывает молча: прямая конвертация даёт 0 таблиц и 0 картинок из
40 и 684, а файл при этом собирается и выглядит целым.  Промежуточный HTML
заставляет pandoc разобрать таблицы в свои внутренние и уже их записать.

Математику отключаем на чтении: в книге есть таблица, которую модель выдала
массивом LaTeX, и pandoc спотыкается на `\\begin{array}` посреди markdown.
"""
import os
import re
import shutil
import subprocess
import tempfile

from . import layout

# `-markdown_in_html_blocks` обязателен, и вот почему.  Таблицы у нас лежат в
# markdown сырым HTML, и pandoc по умолчанию разбирает их СОДЕРЖИМОЕ как
# markdown.  Ячейка, начинающаяся с `(a) .004"`, становится нумерованным
# списком: `<td><ol><li>` открывается внутри ячейки, проглатывает остаток
# таблицы и закрывается уже после `</table>`.  Разметка ломается, и писатель
# fb2 такую таблицу выбрасывает молча — так пропадали 2 таблицы из 41 и 2
# пометки внутри них.  Отключение одного лишь `fancy_lists` не спасает:
# список делают и другие образцы.
READ = ("markdown+raw_html-tex_math_dollars"
        "-tex_math_single_backslash-tex_math_double_backslash"
        "-markdown_in_html_blocks")

CSS = """
body { max-width: 46em; margin: 2em auto; padding: 0 1em;
       font: 16px/1.55 Georgia, 'DejaVu Serif', serif; color: #1a1a1a; }
h1, h2, h3 { font-family: system-ui, sans-serif; line-height: 1.25; }
h2 { margin-top: 2.2em; border-bottom: 1px solid #ddd; padding-bottom: .2em; }
img { max-width: 100%; height: auto; display: block; margin: 1em auto; }
table { border-collapse: collapse; margin: 1.2em auto; font-size: .95em; }
td, th { border: 1px solid #bbb; padding: .35em .6em; vertical-align: top; }
/* Пометки достоверности видны глазом, а не только машине. */
mark { background: #fff3cd; padding: 0 .15em; }
td:has-text, td { }
@media print { body { max-width: none; margin: 0; font-size: 11pt; }
                h2 { page-break-before: auto; } table, img { page-break-inside: avoid; } }
"""



def _plain_math(md: str) -> str:
    """Перевести простой LaTeX в читаемый текст.

    Математики в книге 172 куска, и она почти вся тривиальна: 82 знака
    градуса, 23 штриха, немного \\mathrm.  Настоящая формула одна — массив,
    и именно на нём pandoc падает с ошибкой, унося за собой ВСЮ математику:
    приходилось отключать её разбор целиком, и читатель видел `$ 90^{\\circ} $`
    вместо «90°».

    Поэтому переводим сами.  Правится только то, что идёт в html, epub, pdf и
    fb2; в `book.md` LaTeX остаётся — модели-пересказчику он понятнее текста.
    """
    def army(m):
        # Массив -> строки через перевод строки, без обвязки.
        body = m.group(1)
        rows = [r for r in body.split(r"\\") if r.strip()]
        out = []
        for r in rows:
            cells = [c.strip(" {}") for c in r.split("&") if c.strip(" {}")]
            if cells:
                out.append("  ".join(cells))
        return " ".join(out)

    # Та же граница, что и у долларов, и по той же причине: непарный
    # `\begin{array}` с `re.S` проглатывал всё до следующего `\end` через весь
    # документ.  Замер на «Технологии огнеупоров»: 17 картинок из 115.
    md = re.sub(r"\\begin\{array\}\{[^}]*\}"
                r"((?:(?!\\end\{array\})(?!\n[ \t]*\n).)*)"
                r"\\end\{array\}", army, md, flags=re.S)
    reps = [
        (r"\^\{\\circ\}", "°"), (r"\^\{\\prime\\prime\}", "″"),
        (r"\^\{\\prime\}", "′"), (r"\\mathrm\{~?([^{}]*?)~?\}", r"\1"),
        (r"\\mathbf\{([^{}]*?)\}", r"\1"), (r"\\mathit\{([^{}]*?)\}", r"\1"),
        (r"\\frac\{([^{}]*)\}\{([^{}]*)\}", r"(\1)/(\2)"),
        (r"\\quad|\\,|\\;", " "), (r"\\pm", "±"), (r"\\times", "×"),
        (r"\\prime", "′"), (r"\\circ", "°"), (r"''", "″"), (r"~", " "),
    ]
    for a, b in reps:
        md = re.sub(a, b, md)
    # Снимаем обёртку $…$ и $$…$$, схлопываем пробелы внутри.
    #
    # Раньше здесь стоял один шаблон `\${1,2}(.*?)\${1,2}` с `re.S`, и он
    # СЪЕДАЛ КНИГУ.  Знак доллара в разборе иногда остаётся непарным, и тогда
    # закрывающий доллар одной формулы склеивался с открывающим следующей, а
    # `re.S` позволял этому куску перепрыгивать через пустые строки.  Всё
    # между ними — абзацы, картинки, разрывы — схлопывалось в одну строку.
    #
    # Замер на четырёх русских книгах: у «Технологии огнеупоров» пропадали три
    # картинки из 115 и 22 632 знака, у «Справочника по литью» — 35 160.  На
    # английских книгах не срабатывало: там долларов 352 против 6762, и все
    # парные.  Догадка про эту беду была записана в план как «не выстрелило,
    # но выстрелит»; выстрелило.
    #
    # Теперь формула не может пересечь пустую строку, а строчная — вообще
    # перевод строки.  Непарный доллар остаётся в тексте как есть: лишний
    # знак виден и безобиден, а съеденный абзац — нет.
    def unwrap(m):
        return re.sub(r"\s+", " ", m.group(1)).strip()

    md = re.sub(r"\$\$((?:(?!\$\$)(?!\n[ \t]*\n).)*)\$\$", unwrap, md, flags=re.S)
    md = re.sub(r"\$([^$\n]+)\$", unwrap, md)
    return md


def _log(msg):
    print(msg, flush=True)


def _counts(text):
    return {
        "таблиц": len(re.findall(r"<table", text, re.I)),
        "картинок": len(re.findall(r"<img |<binary ", text, re.I)),
        "⚠": text.count("⚠"),
        "≠": text.count("≠"),
    }


def _report(name, src, got):
    """Сверяем, что доехало, с тем, что было — числом, а не словом «готово».

    Возвращает `True`, если всё доехало.  Прежде функция ничего не
    возвращала, восклицательный знак уходил в строку — и команда завершалась
    нулём при любой потере.  Проверка без последствий не проверка: она нашла
    у «Технологии огнеупоров» семь пропавших таблиц и пять картинок, и никто
    бы этого не заметил, потому что `books convert` отчитался успехом.
    """
    parts, ok = [], True
    for k, want in src.items():
        have = got.get(k, 0)
        if have < want:
            ok = False
        parts.append(f"{k} {have}/{want}" + ("" if have >= want else " !"))
    _log(f"  {name}: " + ", ".join(parts))
    return ok


def _pandoc_ge3():
    """У pandoc 3 ключ --split-level, у второго — --epub-chapter-level."""
    try:
        out = subprocess.run(["pandoc", "--version"], capture_output=True,
                             text=True).stdout
        return int(out.split()[1].split(".")[0]) >= 3
    except Exception:
        return False


def _pandoc(args, cwd=None):
    r = subprocess.run(["pandoc"] + args, cwd=cwd,
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"pandoc: {r.stderr.strip()[:300]}")
    return r.stderr


def convert(outdir: str, formats=("html", "epub", "fb2"),
            title: str | None = None) -> int:
    """Собрать книгу в EPUB и FB2 рядом с её текстом."""
    if not shutil.which("pandoc"):
        _log("нет pandoc — поставьте его: apt install pandoc")
        return 1

    paths = layout.Paths(outdir)
    src = paths.book
    book_dir = os.path.dirname(src)
    stem = paths.stem
    if not os.path.exists(src):
        _log(f"нет {src} — сначала разберите книгу")
        return 1

    text = open(src, encoding="utf-8").read()
    want = _counts(text)
    # Собираем из копии с переведённым LaTeX: сам текст остаётся с
    # формулами, они полезнее модели-пересказчику.  Копия лежит рядом,
    # чтобы ссылки на imgs/ разрешались.
    build = os.path.join(book_dir, "_build.md")
    open(build, "w", encoding="utf-8").write(_plain_math(text))
    SRC = "_build.md"
    _log(f"исходник: {os.path.relpath(src)}, "
         + ", ".join(f"{k} {v}" for k, v in want.items()))

    # Заглавие — из имени исходника, а не из имени каталога: каталог оператор
    # называет наспех («book-new»), и это имя уезжало в метаданные epub.
    if not title:
        # Из имени исходника, а не из имени каталога: каталог оператор
        # называет наспех («book-new»), и это имя уезжало в метаданные epub.
        # Хвост режем только у имени файла — заданный оператором заголовок
        # трогать нельзя: скобка вокруг всего выражения превращала
        # `--title "Том 2. Механика"` в «Том 2».
        src_name = layout.facts(paths.outdir).get("source") or stem
        title = os.path.splitext(src_name)[0].replace("_", " ")
    meta = ["-M", f"title={title}"]
    rc = 0

    if "epub" in formats:
        dst = os.path.join(book_dir, stem + ".epub")
        try:
            # Резать по заголовкам ВТОРОГО уровня.  По умолчанию pandoc
            # режет по первому, а их в разборе почти нет: вся книга уезжала в
            # один ch001.xhtml на 1.5 МБ с 577 картинками и всеми сорока
            # таблицами, и читалки на таком спотыкаются.
            split = ("--split-level=2" if _pandoc_ge3()
                     else "--epub-chapter-level=2")
            _pandoc([SRC, "-f", READ, "-t", "epub3", "--resource-path=.",
                     "--toc", "--toc-depth=3", split, *meta, "-o", dst],
                    cwd=book_dir)
            import zipfile
            with zipfile.ZipFile(dst) as z:
                inside = "".join(
                    z.read(n).decode("utf-8", "replace")
                    for n in z.namelist() if n.endswith((".xhtml", ".html")))
                got = _counts(inside)
                got["картинок"] = sum(
                    1 for n in z.namelist() if n.lower().endswith(
                        (".jpg", ".jpeg", ".png")))
            rc = rc or (0 if _report(f"{os.path.relpath(dst)} "
                              f"({os.path.getsize(dst) // 1024 // 1024} МБ)",
                              want, got) else 1)
        except Exception as exc:
            _log(f"  epub не собрался: {exc}")
            rc = 1

    html_path = os.path.join(book_dir, stem + ".html")
    if {"html", "pdf"} & set(formats):
        # HTML собирается один раз и служит двум целям: он и сам хороший
        # способ читать (браузер кладёт таблицы лучше любой читалки), и
        # исходник для PDF.  Рисунки остаются файлами рядом, а не уезжают в
        # base64: иначе один файл раздуется до сотни мегабайт.
        try:
            with tempfile.NamedTemporaryFile("w", suffix=".html",
                                             delete=False) as h:
                h.write(f"<style>{CSS}</style>")
                head = h.name
            _pandoc([SRC, "-f", READ, "-t", "html5", "--standalone",
                     "--toc", "--toc-depth=3", "--resource-path=.",
                     "-H", head, *meta, "-o", html_path], cwd=book_dir)
            os.unlink(head)
            got = _counts(open(html_path, encoding="utf-8",
                               errors="replace").read())
            rc = rc or (0 if _report(f"{os.path.relpath(html_path)} "
                              f"({os.path.getsize(html_path) // 1024} КБ + imgs/)",
                              want, got) else 1)
        except Exception as exc:
            _log(f"  html не собрался: {exc}")
            rc = 1

    if "pdf" in formats:
        dst = os.path.join(book_dir, stem + ".pdf")
        try:
            from weasyprint import HTML
        except ImportError:
            _log("  pdf пропущен: нет weasyprint "
                 "(uv pip install --python .venv weasyprint)")
            rc = 1
        else:
            try:
                HTML(filename=html_path, base_url=book_dir).write_pdf(dst)
                _log(f"  {os.path.relpath(dst)} "
                     f"({os.path.getsize(dst) // 1024 // 1024} МБ)")
            except Exception as exc:
                _log(f"  pdf не собрался: {exc}")
                rc = 1

    if "fb2" in formats:
        dst = os.path.join(book_dir, stem + ".fb2")
        try:
            with tempfile.TemporaryDirectory() as tmp:
                mid = os.path.join(tmp, "mid.html")
                _pandoc([SRC, "-f", READ, "-t", "html5",
                         "--resource-path=.", "-o", mid], cwd=book_dir)
                _pandoc([mid, "-f", "html", "-t", "fb2",
                         f"--resource-path={book_dir}", *meta, "-o", dst])
            got = _counts(open(dst, encoding="utf-8", errors="replace").read())
            rc = rc or (0 if _report(f"{os.path.relpath(dst)} "
                              f"({os.path.getsize(dst) // 1024 // 1024} МБ)",
                              want, got) else 1)
        except Exception as exc:
            _log(f"  fb2 не собрался: {exc}")
            rc = 1

    try:
        os.unlink(build)
    except OSError:
        pass
    return rc
