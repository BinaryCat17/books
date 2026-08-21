"""Свод нескольких проходов в одну книгу с пометками неустойчивости.

Основой берётся первый проход — жадный, лучший одиночный ответ.  Остальные
читались при ненулевой температуре и служат свидетелями: ячейка, прочитанная
всеми одинаково, надёжна; разошедшаяся — нет.

Пометки в итоге две, и они про разное:
  ⚠  модель сама не была уверена (по вероятностям токенов);
  ≠  чтения разошлись (модель гадала, но уверенно).
Первый признак ловит искажённый текст, второй — правдоподобную выдумку.
"""
import collections, glob, html, os, re, shutil, sys

TAG = re.compile(r"<[^>]+>")
CELL = re.compile(r"(<t[dh][^>]*>)(.*?)(</t[dh]>)", re.I | re.S)
TABLE = re.compile(r"<table\b.*?</table>", re.I | re.S)


def plain(c):
    return html.unescape(TAG.sub("", c)).replace("⚠", "").replace("≠", "").strip()


def cells_of(path):
    md = open(path, encoding="utf-8").read()
    out = collections.Counter()
    for t in TABLE.finditer(md):
        for _, body, _ in CELL.findall(t.group(0)):
            v = plain(body)
            if v:
                out[v] += 1
    return out


def merge(dirs, dst):
    base, others = dirs[0], dirs[1:]
    if os.path.isdir(dst):
        shutil.rmtree(dst)
    shutil.copytree(base, dst)
    pages = sorted(glob.glob(os.path.join(dst, "pages", "*.md")))
    marked = total = 0
    for f in pages:
        stem = os.path.basename(f)
        try:
            witness = [cells_of(os.path.join(o, "pages", stem))
                       for o in others]
        except FileNotFoundError:
            continue
        src = open(f, encoding="utf-8").read()
        if "<table" not in src.lower():
            continue
        seen = collections.Counter()

        def one(m):
            nonlocal marked, total
            v = plain(m.group(2))
            if not v:
                return m.group(0)
            total += 1
            seen[v] += 1
            k = seen[v]
            if all(w[v] >= k for w in witness):
                return m.group(0)          # подтверждена обоими свидетелями
            marked += 1
            return m.group(1) + m.group(2) + " ≠" + m.group(3)

        out = []
        prev = 0
        for t in TABLE.finditer(src):
            out.append(src[prev:t.start()])
            out.append(CELL.sub(one, t.group(0)))
            prev = t.end()
        out.append(src[prev:])
        with open(f, "w", encoding="utf-8") as fh:
            fh.write("".join(out))

    book = os.path.join(dst, "book", "book.md")
    os.makedirs(os.path.dirname(book), exist_ok=True)
    with open(book, "w", encoding="utf-8") as out:
        for f in pages:
            out.write(open(f, encoding="utf-8").read())
            out.write("\n\n")
    print(f"ячеек в таблицах {total}, помечено неустойчивыми {marked} "
          f"({marked/max(total,1):.0%})")
    print(f"книга собрана: {book}")



