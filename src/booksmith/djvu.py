"""DjVu на входе: развернуть в PDF и разрезать развороты.

Конвейер умеет читать только PDF, и это правильно: распознаватель рендерит
страницы сам, а формат исходника его не касается.  Значит djvu надо развернуть
до прогона — местно, бесплатно и проверяемо глазами, а не на арендованной
карте, где ошибка стоит денег.

ГЛАВНОЕ, ЧЕГО ЗДЕСЬ НЕЛЬЗЯ ПРОПУСТИТЬ: **сканы книг в djvu часто лежат
разворотами.**  Из трёх добавленных книг две именно такие: в файле 189 и 381
«страница», а книжных — 378 и 762.  Отдать такой файл распознавателю значит
велеть ему прочитать две страницы как одну: детектор макета увидит две колонки
там, где их нет, порядок чтения перепутается, а колонцифры двух разных страниц
окажутся в одном блоке.  Проверить это дёшево (посмотреть на страницу), а не
проверить — дорого: беда выглядит как «модель плохо читает».

Признак разворота — ширина больше высоты.  Он грубый, но здесь достаточный:
книжная страница почти всегда выше, чем шире, а разворот почти всегда шире, чем
выше.  Решение принимается ПО КНИГЕ, а не по странице: если разворотов
большинство, режем все альбомные, а редкие портретные (обложка, вклейки)
оставляем целыми.  Наоборот тоже верно — в книге одиночных страниц случайная
альбомная страница это таблица на всю ширину, и резать её нельзя.

Линия реза ищется по чернилам, а не берётся посередине: у сканов разворот
редко приходится ровно на половину.  Берём столбец с наименьшим количеством
чернил в средней пятой части листа.  Если чернил там всюду поровну (разворот
без поля между страницами), падаем обратно на середину — хуже не станет.
"""
import os
import re
import shutil
import subprocess

MIN_SPREAD_RATIO = 1.15     # шире высоты во столько раз — считаем разворотом
GUTTER_BAND = 0.20          # где искать линию реза: середина ± десятая часть
PROBE_DPI = 36              # чернила считаем по уменьшенной странице: хватает


class NoDjvuTools(SystemExit):
    pass


def _tool(name):
    p = shutil.which(name)
    if not p:
        raise NoDjvuTools(
            f"нет {name} — без него djvu не развернуть. Поставьте djvulibre:\n"
            f"    sudo apt install djvulibre-bin\n"
            f"Если sudo недоступен, её можно распаковать без установки:\n"
            f"    apt-get download djvulibre-bin libdjvulibre21 libjpeg-turbo8\n"
            f"    dpkg -x <каждый>.deb ~/.local/djvu")
    return p


def pages(path):
    """Сколько страниц в файле djvu (страниц файла, не книги)."""
    out = subprocess.run([_tool("djvused"), "-e", "n", path],
                         capture_output=True, text=True, timeout=120)
    m = re.search(r"\d+", out.stdout)
    if not m:
        raise SystemExit(f"не смог прочитать число страниц: {path}\n{out.stderr}")
    return int(m.group(0))


def _gutter(page, rect):
    """Столбец с наименьшим количеством чернил в середине разворота."""
    import pymupdf
    pix = page.get_pixmap(dpi=PROBE_DPI, colorspace=pymupdf.csGRAY, clip=rect)
    if pix.width < 8:
        return rect.x0 + rect.width / 2
    data = pix.samples
    lo = int(pix.width * (0.5 - GUTTER_BAND / 2))
    hi = int(pix.width * (0.5 + GUTTER_BAND / 2))
    best, best_ink = None, None
    for x in range(lo, max(hi, lo + 1)):
        ink = 0
        for y in range(pix.height):
            ink += 255 - data[y * pix.stride + x]
        if best_ink is None or ink < best_ink:
            best, best_ink = x, ink
    return rect.x0 + rect.width * (best + 0.5) / pix.width


def to_pdf(src, dst=None, split="auto", log=print):
    """Развернуть djvu в PDF, разрезав развороты.

    `split`: `auto` — решать по книге, `yes` — резать все альбомные, `no` — не
    резать вовсе.  Возвращает путь к готовому PDF.

    Готовый файл не переделываем: развёртка идёт минуты, а вызывают её и `books
    ocr`, и рука.  Свежесть проверяем по времени изменения — исходник обычно
    не меняется вовсе, но молча отдать вчерашний PDF от другого файла нельзя.
    """
    import pymupdf

    src = os.path.abspath(src)
    if dst is None:
        dst = os.path.splitext(src)[0] + ".pdf"
    if (os.path.exists(dst)
            and os.path.getmtime(dst) >= os.path.getmtime(src)):
        n = pymupdf.open(dst).page_count
        log(f"уже развёрнут: {os.path.basename(dst)} ({n} стр.)")
        return dst

    n_src = pages(src)
    log(f"{os.path.basename(src)}: страниц в файле {n_src}")

    raw = dst + ".raw.pdf"
    subprocess.run([_tool("ddjvu"), "-format=pdf", "-quality=90", src, raw],
                   check=True, timeout=3600)
    doc = pymupdf.open(raw)

    wide = sum(1 for p in doc if p.rect.width > p.rect.height * MIN_SPREAD_RATIO)
    if split == "auto":
        cut = wide * 2 > doc.page_count
        log(f"альбомных страниц {wide} из {doc.page_count} — "
            + ("это развороты, режу" if cut else "разворотов нет, не режу"))
    else:
        cut = split == "yes"

    out = pymupdf.open()
    made = 0
    for page in doc:
        r = page.rect
        if cut and r.width > r.height * MIN_SPREAD_RATIO:
            x = _gutter(page, r)
            halves = [pymupdf.Rect(r.x0, r.y0, x, r.y1),
                      pymupdf.Rect(x, r.y0, r.x1, r.y1)]
        else:
            halves = [r]
        for h in halves:
            np = out.new_page(width=h.width, height=h.height)
            np.show_pdf_page(np.rect, doc, page.number, clip=h)
            made += 1
    out.save(dst, garbage=3, deflate=True)
    out.close()
    doc.close()
    os.unlink(raw)
    log(f"развёрнут: {os.path.basename(dst)}, страниц {made} "
        f"({os.path.getsize(dst) / 1e6:.0f} МБ)")
    return dst


def ensure_pdf(path, log=print):
    """PDF как есть; djvu — развернуть. Всё остальное — пусть падает дальше."""
    if path.lower().endswith(".djvu"):
        return to_pdf(path, log=log)
    return path
