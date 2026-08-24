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
#
# `-raw_tex`.  При включённом расширении pandoc, увидев `\cmd{`, читает вперёд
# до баланса скобок — через абзацы, картинки и таблицы — и отдаёт всё куском
# raw latex, который писатель html молча выбрасывает.  Одной незакрытой скобки
# в ячейке хватает, чтобы съесть половину книги.  Контропыт на восьми строках:
# с `raw_tex` доезжает 1 абзац из 4, без него — все 4, таблица и картинка.
# Замерено на «Справочнике» (после Э2): таблиц 184 -> 470, тегов картинок
# 237 -> 1434.  Своей математики у нас нет: `_plain_math` переводит её в текст
# до pandoc, так что терять нечего.
#
# `-superscript-subscript`.  Расширение делает `^` и `~` разметкой.  У нас это
# знаки из формул и OCR, а не разметка: получаются ложные `<sup>`, а главное —
# открытый `^…` слипается с соседним `<mark>` и рвёт вложенность тегов.
#
# `-native_divs`.  Самое дорогое.  При включённом расширении pandoc разбирает
# каждый `<div>` в свой Div и перебирает содержимое как markdown; на книге с
# полутора тысячами `<div style="text-align: center;">` расход растёт
# сверхлинейно.  Замер на «Биохимии» (2.5 МБ разметки, 1590 div):
# с `native_divs` — пик RSS 4.7 ГБ и 129 с, без него — 279 МБ и 6.5 с.
# Именно это, а не только WeasyPrint, роняло машину: шесть книг подряд стоят
# 10.9 ГБ, а машины всего 7.9.
#
# Видимый текст при этом СОВПАДАЕТ знак в знак (проверено на курсе физики:
# 82 062 слова с обеих сторон).  Отличается только обвязка, и в лучшую
# сторону: с `native_divs` pandoc заворачивает содержимое div в абзац и
# закрывает его НЕ ТАМ — `<p>подпись</div>`, 166 таких мест на одной книге.
# Отсюда и битый XHTML в epub: файлов, не разбирающихся как XML, было
# 147 из 223 по шести книгам, стало 6 из 263.
READ = ("markdown+raw_html-tex_math_dollars"
        "-tex_math_single_backslash-tex_math_double_backslash"
        "-markdown_in_html_blocks"
        "-raw_tex-superscript-subscript-native_divs")

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



def _unbrace(cell):
    r"""Снять с ячейки массива ТОЛЬКО парную обёртку `{…}`.

    Прежде здесь стояло `c.strip(" {}")`, и на ячейке `\mathrm{Fe}` оно
    срывало закрывающую скобку: получалось `\mathrm{Fe` — незакрытая команда,
    которую pandoc с `raw_tex` дочитывал до следующей `}` через полкниги.
    Снимаем скобки, только если первая закрывается именно последней.
    """
    c = cell.strip()
    while len(c) >= 2 and c[0] == "{" and c[-1] == "}":
        depth = 0
        for i, ch in enumerate(c):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    break
        if i != len(c) - 1:
            break          # первая скобка закрылась раньше конца — не обёртка
        c = c[1:-1].strip()
    return c


# Тег `<mark>` целиком, с уважением к кавычкам в атрибутах: Э3 кладёт в
# `title` варианты свидетелей, и `[^>]*` на них однажды остановится не там.
MARK_TAG = re.compile(r"</?mark\b(?:\"[^\"]*\"|'[^']*'|[^>\"'])*>")
# Нечётная серия обратных слэшей перед тегом.  Чётная — правильный текст:
# `\\` в markdown это литеральный слэш, и трогать его нельзя.
MARK_SLASH = re.compile(
    r"(?<!\\)((?:\\\\)*)\\(</?mark\b(?:\"[^\"]*\"|'[^']*'|[^>\"'])*>)")
BLANK = re.compile(r"(\n[ \t]*\n)")


def _fix_marks(md: str) -> tuple[str, dict]:
    r"""Починить пометки достоверности, разрезанные разметкой.

    Пометки ставит свод, ничего не зная о markdown, и попадает в четыре беды.

    (а) Закрывающий тег съеден слэшем: `<mark …> $\</mark>Phi` — markdown
        читает `\<` как экранированный знак «меньше», тег становится текстом,
        пометка не закрывается, и дальше едет открытый `<mark>`.
    (б) Открывающий тег съеден так же: `$t_{\<mark …>lambda</mark>}$` — свод
        разрезал команду `\lambda` пополам.
    (в) Пометка пересекает границу абзаца: pandoc закрывает абзац раньше тега
        и падает с `TagClose "p"`, унося ВЕСЬ fb2.
    (г) Перехлёст с `superscript` — снимается отключением расширения в READ.

    Лечим (а) и (б) переносом непарного слэша ЧЕРЕЗ тег вправо: слэш снова
    прирастает к имени команды (`\Phi`, `\lambda`), а помеченный кусок
    сдвигается на один знак — цена, которой не видно.  Чётность серии
    обязательна: `\\</mark>` остаётся как есть.

    (в) лечим не выбрасыванием, а перевыставлением: пометка закрывается в
    конце абзаца и открывается тем же тегом в начале следующего.  Помеченный
    кусок сохраняется целиком, вложенность тегов становится законной.
    """
    stat = {"слэш снят с тега": len(MARK_SLASH.findall(md)),
            "пометка перевыставлена через абзац": 0,
            "лишний закрывающий выброшен": 0}
    md = MARK_SLASH.sub(r"\1\2\\", md)

    out, pending = [], None
    for part in BLANK.split(md):
        if BLANK.fullmatch(part):
            out.append(part)
            continue
        buf, pos = [], 0
        if pending:
            buf.append(pending)
        for m in MARK_TAG.finditer(part):
            buf.append(part[pos:m.start()])
            pos = m.end()
            if m.group(0).startswith("</"):
                if pending:
                    buf.append("</mark>")
                    pending = None
                else:
                    # лишний закрывающий без пары — выбрасываем: иначе он
                    # доедет до читателя видимым мусором
                    stat["лишний закрывающий выброшен"] += 1
            else:
                if pending:
                    buf.append("</mark>")   # вложенности у нас не бывает
                buf.append(m.group(0))
                pending = m.group(0)
        buf.append(part[pos:])
        if pending:
            buf.append("</mark>")
            stat["пометка перевыставлена через абзац"] += 1
        out.append("".join(buf))
    return "".join(out), stat


# `\cmd{`, у которой в пределах абзаца нет закрывающей скобки.
CMD_OPEN = re.compile(r"\\[A-Za-z]+\{|[{}]")
# Дописываем скобку только в абзаце, где есть команда со скобкой: одинокая
# `{` в прозе — это просто знак, и дописанная к ней `}` была бы мусором.
HAS_CMD = re.compile(r"\\[A-Za-z]+\{")


def _close_commands(md: str) -> tuple[str, int]:
    r"""Дописать недостающие `}` в конце абзаца — и вернуть, сколько дописано.

    Незакрытая `\mathrm{Fe` приезжает из распознавания и из ячеек массива.
    С `raw_tex` она съедала книгу; без него она хотя бы видна, но читатель
    видит `\mathrm{Fe` вместо «Fe».  Закрыв скобку, мы отдаём кусок правилам
    ниже (`\mathrm{…}` -> `…`), и он превращается в текст.

    Граница — абзац, и по той же причине, что у долларов: беда, которой
    позволено ходить через пустую строку, съедает книгу целиком.
    """
    fixed = 0
    out = []
    for part in BLANK.split(md):
        if BLANK.fullmatch(part) or not HAS_CMD.search(part):
            out.append(part)
            continue
        depth = 0
        for m in CMD_OPEN.finditer(part):
            depth += 1 if m.group(0).endswith("{") else -1
            if depth < 0:
                depth = 0        # лишняя `}` безобидна: она просто текст
        if depth > 0:
            part = part + "}" * depth
            fixed += depth
        out.append(part)
    return "".join(out), fixed


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
            cells = [x for x in (_unbrace(c) for c in r.split("&")) if x]
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


def _prepare(md: str) -> tuple[str, dict]:
    r"""Всё, что делаем с текстом до pandoc, и числа об этом.

    Порядок обязателен.  Сперва закрываем висячие скобки: только тогда
    `_plain_math` увидит `\mathrm{Fe}` целиком и переведёт его в «Fe».
    Пометки чиним последними — закрытие скобок и перевод формул сдвигают
    текст, и чинить границы тегов до этого бессмысленно.
    """
    md, braces = _close_commands(md)
    md = _plain_math(md)
    md, stat = _fix_marks(md)
    stat["дописано скобок"] = braces
    return md, stat


def _log(msg):
    print(msg, flush=True)


def _srcs(text):
    """Пути картинок, на которые ссылается разметка."""
    return re.findall(r"<img\b[^>]*?src=[\"']([^\"']+)[\"']", text, re.I)


def _counts(text):
    return {
        "таблиц": len(re.findall(r"<table", text, re.I)),
        "ячеек": len(re.findall(r"<td\b", text, re.I)),
        "картинок": len(re.findall(r"<img |<binary ", text, re.I)),
        "⚠": text.count("⚠"),
        "≠": text.count("≠"),
    }


def _tables(text):
    """Отпечаток каждой таблицы: первые 60 знаков её текста.

    Нужен, чтобы сказать не «таблиц 184 из 470», а КАКИХ именно не хватает и
    подряд ли они. Разрыв подряд — это одна проглоченная область, а не 286
    независимых бед, и чинится он одной правкой.
    """
    out = []
    for m in re.finditer(r"<table\b.*?(?:</table>|\Z)", text, re.I | re.S):
        body = re.sub(r"<[^>]*>", " ", m.group(0))
        body = re.sub(r"[\s\u00a0]+", " ", body).strip()
        out.append((m.start(), body[:60]))
    return out


def _gap(src_text, got_text):
    """Самый длинный кусок таблиц, который есть в исходнике и пропал в выводе.

    Возвращает (сколько, номер строки первой пропавшей, её отпечаток).
    """
    import difflib
    a = _tables(src_text)
    b = [t for _, t in _tables(got_text)]
    sm = difflib.SequenceMatcher(None, [t for _, t in a], b, autojunk=False)
    best = (0, None, "")
    for tag, i1, i2, _j1, _j2 in sm.get_opcodes():
        if tag == "delete" and i2 - i1 > best[0]:
            pos = a[i1][0]
            best = (i2 - i1, src_text.count("\n", 0, pos) + 1, a[i1][1])
    return best


def _report(name, src, got, gap=None):
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
    if got.get("таблиц", 0) < src.get("таблиц", 0) and gap is not None:
        n, line, head = gap
        if n:
            _log(f"    пропало подряд {n} таблиц, начиная со строки {line}"
                 f" книги: «{head}…»")
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
    # Собираем из копии с переведённым LaTeX: сам текст остаётся с
    # формулами, они полезнее модели-пересказчику.  Копия лежит рядом,
    # чтобы ссылки на imgs/ разрешались.
    prepared, repairs = _prepare(text)
    # Сверяемся с ПОДГОТОВЛЕННЫМ текстом, а не с книгой: `_prepare` чинит
    # пометки и может изменить их число, и сверка обязана мерить то, что
    # мы отдали pandoc, иначе она ловит собственную починку как потерю.
    want = _counts(prepared)
    # Картинок в «Справочнике» 1434 тега на 620 файлов — одна вырезка стоит
    # в тексте по нескольку раз.  epub кладёт файл ОДИН раз, поэтому его
    # сверять надо по уникальным путям, иначе она кричит всегда и на всём.
    want_files = len(set(_srcs(prepared)))
    build = os.path.join(book_dir, "_build.md")
    open(build, "w", encoding="utf-8").write(prepared)
    SRC = "_build.md"
    _log(f"исходник: {os.path.relpath(src)}, "
         + ", ".join(f"{k} {v}" for k, v in want.items())
         + f", файлов картинок {want_files}")
    if any(repairs.values()):
        _log("  перед сборкой: "
             + ", ".join(f"{k} {v}" for k, v in repairs.items() if v))

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
            want_epub = dict(want, картинок=want_files)
            if not _report(f"{os.path.relpath(dst)} "
                           f"({os.path.getsize(dst) // 1024 // 1024} МБ)",
                           want_epub, got, _gap(prepared, inside)):
                rc = 1
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
            body = open(html_path, encoding="utf-8", errors="replace").read()
            got = _counts(body)
            if not _report(f"{os.path.relpath(html_path)} "
                           f"({os.path.getsize(html_path) // 1024} КБ + imgs/)",
                           want, got, _gap(prepared, body)):
                rc = 1
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
            body = open(dst, encoding="utf-8", errors="replace").read()
            got = _counts(body)
            # fb2 кладёт картинку как `<binary>` — по одной на файл, а
            # ссылок `<image>` столько же, сколько было тегов.  Считаем
            # `_counts` обе формы разом, поэтому сверяем с числом тегов.
            if not _report(f"{os.path.relpath(dst)} "
                           f"({os.path.getsize(dst) // 1024 // 1024} МБ)",
                           want, got, _gap(prepared, body)):
                rc = 1
        except Exception as exc:
            _log(f"  fb2 не собрался: {exc}")
            rc = 1

    try:
        os.unlink(build)
    except OSError:
        pass
    return rc
