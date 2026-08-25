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
RULE_MAX = 0.005            # больше этой доли сплошных строк — резать нельзя
RULE_BAND = 0.012           # полоса вокруг реза, в долях ширины разворота
RULE_INK = 96               # насколько тёмен пиксель, чтобы счесть его чернотой


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
    """Где резать разворот — и резать ли вообще.

    Возвращает `None`, если резать нельзя: на месте предполагаемого корешка
    лежит содержимое, и разрез уничтожит его.

    ЧЕГО ЗДЕСЬ НЕ БЫЛО И ЧТО ЭТО СТОИЛО.  Докстринг модуля обещал откат на
    середину, «если чернил всюду поровну», — а в коде не было НИ ОДНОГО
    сравнения с порогом: `argmin` возвращал столбец с наименьшими чернилами
    всегда, то есть при широкой таблице во весь разворот резал её по самому
    разреженному столбцу.  Замер по рамкам блоков: **439 страниц из 1138
    разрезанных (38.6%) имеют блок вплотную к резу** (ближе 1% ширины) против
    **0 из 3740** краёв на трёх нерезаных книгах; таблица вплотную — 165
    страниц.  Три книги в djvu — это 1693 страницы из 3268, половина
    библиотеки.

    ДВА ПРИЗНАКА, И ОНИ РАЗНЫЕ.  Мало чернил — не значит «здесь корешок»: у
    таблицы между колонками тоже белые просветы, и порог по чернилам ловит
    лишь 31% контрольных страниц.  Работает СКВОЗНАЯ ГОРИЗОНТАЛЬНАЯ ЛИНЕЙКА:
    доля строк, где через выбранный столбец (± полоса) идёт сплошная чернота.
    У настоящих корешков она почти нулевая (медиана 0.17%, 99-й процентиль
    0.67%), у страниц, занятых таблицей во всю ширину, — медиана 0.83%.
    Порог 0.5% ловит 84% контрольных при отказе на 1–2% настоящих корешков.

    Цена ошибки НЕСИММЕТРИЧНА, и порог выбран под неё: лишний отказ отдаёт
    распознавателю двухколоночный разворот — беда поправимая, страницы целы;
    разрез по таблице уничтожает числа безвозвратно.
    """
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
    if best is None:
        return rect.x0 + rect.width / 2
    if _ruled_through(pix, best) > RULE_MAX:
        return None
    return rect.x0 + rect.width * (best + 0.5) / pix.width


def _ruled_through(pix, x):
    """Доля строк, где через столбец `x` идёт сплошная чернота.

    Полоса, а не один столбец: рез не обязан попадать в линейку пиксель в
    пиксель, а линейка таблицы толще одного пикселя на 36 dpi.
    """
    half = max(1, int(pix.width * RULE_BAND / 2))
    lo, hi = max(0, x - half), min(pix.width, x + half + 1)
    data, dark = pix.samples, 0
    for y in range(pix.height):
        row = y * pix.stride
        if all(255 - data[row + i] >= RULE_INK for i in range(lo, hi)):
            dark += 1
    return dark / max(1, pix.height)


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
    spared = []
    for page in doc:
        r = page.rect
        halves = [r]
        if cut and r.width > r.height * MIN_SPREAD_RATIO:
            x = _gutter(page, r)
            if x is None:
                # На месте корешка лежит содержимое: разворот занят таблицей
                # во всю ширину.  Отдаём его распознавателю целым — он
                # прочтёт две колонки хуже, чем две страницы, но прочтёт;
                # разрезанная таблица не восстанавливается ничем.
                spared.append(page.number + 1)
            else:
                halves = [pymupdf.Rect(r.x0, r.y0, x, r.y1),
                          pymupdf.Rect(x, r.y0, r.x1, r.y1)]
        for h in halves:
            np = out.new_page(width=h.width, height=h.height)
            np.show_pdf_page(np.rect, doc, page.number, clip=h)
            made += 1
    out.save(dst, garbage=3, deflate=True)
    out.close()
    doc.close()
    os.unlink(raw)
    if spared:
        # Число, а не «готово»: по нему видно, разумно ли вето сработало.
        # Много отказов на книге сплошной прозы — признак сбитого порога.
        log(f"не разрезано (содержимое на линии реза): {len(spared)} "
            f"из {wide}, листы {spared[:12]}"
            + (" …" if len(spared) > 12 else ""))
    log(f"развёрнут: {os.path.basename(dst)}, страниц {made} "
        f"({os.path.getsize(dst) / 1e6:.0f} МБ)")
    return dst


def ensure_pdf(path, log=print):
    """PDF как есть; djvu — развернуть. Всё остальное — пусть падает дальше."""
    if path.lower().endswith(".djvu"):
        return to_pdf(path, log=log)
    return path
