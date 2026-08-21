"""Разбор -> EPUB и FB2, рядом с book.md.

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

READ = ("markdown+raw_html-tex_math_dollars"
        "-tex_math_single_backslash-tex_math_double_backslash")

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
    """Сверяем, что доехало, с тем, что было — числом, а не словом «готово»."""
    parts = []
    for k, want in src.items():
        have = got.get(k, 0)
        parts.append(f"{k} {have}/{want}" + ("" if have >= want else " !"))
    _log(f"  {name}: " + ", ".join(parts))


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
    """Собрать книгу в EPUB и FB2 рядом с book.md."""
    if not shutil.which("pandoc"):
        _log("нет pandoc — поставьте его: apt install pandoc")
        return 1

    book_dir = os.path.join(os.path.abspath(outdir), "book")
    src = os.path.join(book_dir, "book.md")
    if not os.path.exists(src):
        _log(f"нет {src} — сначала разберите книгу")
        return 1

    text = open(src, encoding="utf-8").read()
    want = _counts(text)
    _log(f"исходник: {os.path.relpath(src)}, "
         + ", ".join(f"{k} {v}" for k, v in want.items()))

    title = title or os.path.basename(os.path.abspath(outdir)).replace("-", " ")
    meta = ["-M", f"title={title}"]
    rc = 0

    if "epub" in formats:
        dst = os.path.join(book_dir, "book.epub")
        try:
            # Резать по заголовкам ВТОРОГО уровня.  По умолчанию pandoc
            # режет по первому, а их в разборе почти нет: вся книга уезжала в
            # один ch001.xhtml на 1.5 МБ с 577 картинками и всеми сорока
            # таблицами, и читалки на таком спотыкаются.
            split = ("--split-level=2" if _pandoc_ge3()
                     else "--epub-chapter-level=2")
            _pandoc(["book.md", "-f", READ, "-t", "epub3", "--resource-path=.",
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
            _report(f"{os.path.relpath(dst)} "
                    f"({os.path.getsize(dst) // 1024 // 1024} МБ)", want, got)
        except Exception as exc:
            _log(f"  epub не собрался: {exc}")
            rc = 1

    html_path = os.path.join(book_dir, "book.html")
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
            _pandoc(["book.md", "-f", READ, "-t", "html5", "--standalone",
                     "--toc", "--toc-depth=3", "--resource-path=.",
                     "-H", head, *meta, "-o", html_path], cwd=book_dir)
            os.unlink(head)
            got = _counts(open(html_path, encoding="utf-8",
                               errors="replace").read())
            _report(f"{os.path.relpath(html_path)} "
                    f"({os.path.getsize(html_path) // 1024} КБ + imgs/)",
                    want, got)
        except Exception as exc:
            _log(f"  html не собрался: {exc}")
            rc = 1

    if "pdf" in formats:
        dst = os.path.join(book_dir, "book.pdf")
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
        dst = os.path.join(book_dir, "book.fb2")
        try:
            with tempfile.TemporaryDirectory() as tmp:
                mid = os.path.join(tmp, "mid.html")
                _pandoc(["book.md", "-f", READ, "-t", "html5",
                         "--resource-path=.", "-o", mid], cwd=book_dir)
                _pandoc([mid, "-f", "html", "-t", "fb2",
                         f"--resource-path={book_dir}", *meta, "-o", dst])
            got = _counts(open(dst, encoding="utf-8", errors="replace").read())
            _report(f"{os.path.relpath(dst)} "
                    f"({os.path.getsize(dst) // 1024 // 1024} МБ)", want, got)
        except Exception as exc:
            _log(f"  fb2 не собрался: {exc}")
            rc = 1

    return rc
