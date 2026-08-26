"""Проверить вето на разрез разворота: сколько раз сработало и справедливо ли.

ЗАЧЕМ ЭТОТ ФАЙЛ СУЩЕСТВУЕТ.  Первая редакция вето в `djvu.py` объявляла
«порог 0.5% ловит 84% контрольных при отказе на 1–2% настоящих корешков» — и
скрипт, которым это считали, в дерево не попал.  Через день утверждение стало
непроверяемым, а прогон по живой книге дал другое: 11 отказов из 189 (5.8%),
и все одиннадцать ложные.  Замер без способа его повторить — это мнение,
набранное моноширинным шрифтом.

ЧТО МЕРИТ.  По каждому развороту: сработало ли вето, и если да — из-за чего.
Чернота, идущая через корешок, делится на два разряда, и это различение и
есть суть:

    сквозная  — чёрный прогон тянется через четверть ширины разворота и
                дальше.  Так выглядит линейка таблицы, пересекающей корешок:
                она идёт через обе страницы.  Вето по ней и должно
                срабатывать.
    короткая  — прогон в десяток-другой пикселей.  Так выглядит ТЕНЬ
                ПЕРЕПЛЁТА: у сканов разворота верхние строки корешка чернее
                всего.  Вето по ней — ложная тревога, и притом обидная: тень
                переплёта есть улика корешка, то есть прямо противоположна
                тому, что вето ищет.

Обе величины печатаются отдельно.  «Линеек нет» и «чернота была и вся
оказалась короткой» — разные ответы, и сводить их в одно число значит терять
ровно тот разряд ошибки, ради которого промер и написан.

ЗАПУСК::

    python tools/spread_probe.py --selfcheck            # без книг, секунды
    python tools/spread_probe.py raw/*.djvu
    python tools/spread_probe.py --pages 17,20,23 raw/книга.djvu

Третий вид — посмотреть поимённо, что нашлось на подозрительных листах.  Им и
проверяется, что признак различает: подставьте лист с таблицей во весь
разворот и лист с одной тенью переплёта — разряды должны выйти разные.

ЧЕГО ПРОМЕР НЕ ПРОВЕРЯЕТ, И ЭТО НАДО ЗНАТЬ.  Отрицательная сторона измерена
на живой книге: 11 бывших ложных вето сняты.  Положительная — что настоящая
линейка через корешок вето ВЫЗЫВАЕТ — на живых сканах не проверена: такого
разворота в трёх наших книгах не нашлось размеченным.  Проверена она пока
только синтетикой, `--selfcheck`.  Значит цена ошибки прежняя и
несимметричная: лишний отказ отдаёт распознавателю двухколоночный разворот,
страницы целы; разрез по таблице уничтожает числа безвозвратно.
"""
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "src"))
from booksmith import djvu  # noqa: E402


def unpack(src, tmp):
    """djvu -> pdf во временный каталог, минуя проверку свежести в to_pdf."""
    out = os.path.join(tmp, "probe.pdf")
    subprocess.run([djvu._tool("ddjvu"), "-format=pdf", "-quality=85",
                    src, out], check=True, capture_output=True)
    return out


def cut_column(pix):
    """Тот же выбор столбца, что делает `_gutter`, — чтобы мерить то самое."""
    data = pix.samples
    lo = int(pix.width * (0.5 - djvu.GUTTER_BAND / 2))
    hi = int(pix.width * (0.5 + djvu.GUTTER_BAND / 2))
    best, best_ink = None, None
    for x in range(lo, max(hi, lo + 1)):
        ink = sum(255 - data[y * pix.stride + x] for y in range(pix.height))
        if best_ink is None or ink < best_ink:
            best, best_ink = x, ink
    return best


def probe(src, only=None):
    """Промер одной книги. Возвращает (разворотов, вето, сквозных, коротких,
    подробности)."""
    import pymupdf
    with tempfile.TemporaryDirectory() as tmp:
        doc = pymupdf.open(unpack(src, tmp))
        spreads = vetoed = through_total = short_total = 0
        detail = []
        for page in doc:
            r = page.rect
            if r.width <= r.height * djvu.MIN_SPREAD_RATIO:
                continue
            sheet = page.number + 1
            if only and sheet not in only:
                continue
            spreads += 1
            pix = page.get_pixmap(dpi=djvu.PROBE_DPI,
                                  colorspace=pymupdf.csGRAY, clip=r)
            if pix.width < 8:
                continue
            through, short = djvu.dark_rows(pix, cut_column(pix))
            through_total += len(through)
            short_total += len(short)
            share = len(through) / max(1, pix.height)
            is_veto = share > djvu.RULE_MAX
            vetoed += is_veto
            if is_veto or only:
                detail.append((sheet, pix.height, through, short, share,
                               is_veto))
        doc.close()
    return spreads, vetoed, through_total, short_total, detail


# (имя случая, что нарисовать поверх двух колонок «текста», ждём ли вето)
CASES = (
    ("чистый корешок", None, False),
    ("тень переплёта сверху", "shadow-top", False),
    ("тень переплёта на всю высоту", "shadow-full", False),
    ("линейка через весь разворот", "rule-full", True),
    ("линейка через треть", "rule-third", True),
    ("таблица во весь разворот", "table", True),
    # Сканы серые, а не чёрные: без этого случая порог черноты RULE_INK можно
    # задрать до 250 — и ни один нарисованный чистым чёрным случай этого не
    # заметит. Мутация должна ловиться, иначе порог не проверен.
    ("выцветшая линейка через разворот", "rule-grey", True),
    # Бумага у сканов желтоватая. Без этого случая тот же порог можно опустить
    # до пяти, и всё поле листа станет «чернилами».
    ("жёлтая бумага, чистый корешок", "paper-grey", False),
)


def selfcheck():
    """Умеет ли вето провалиться — на нарисованных листах, без книг.

    Половина случаев обязана вето вызвать, половина обязана не вызвать.
    Признак, который нельзя провалить, — не прибор: пометка `≠` в прежнем
    разборе стояла у 416 таблиц из 448 и не значила ничего именно потому, что
    её никто не проверял против известной порчи.

    Возврат 1 при любом расхождении: проверка нужна такая, чтобы могла
    кого-нибудь остановить.

    ЧТО ЭТА ПРОВЕРКА ЛОВИТ.  Прогон с нарочно сдвинутой ручкой (мутация)::

        RULE_RUN 0.25 -> 0.9         4 расхождения из 8
        RULE_RUN 0.25 -> 0.05        1
        RULE_MAX 0.005 -> 0.9        4
        RULE_INK 96 -> 250           1
        RULE_INK 96 -> 5             1
        RULE_BAND 0.012 -> 0.4       1
        GUTTER_BAND 0.20 -> 0.9      4
        MIN_SPREAD_RATIO 1.15 -> 9   0 — НЕ ловится

    Последняя не ловится честно: самопроверка зовёт `_gutter` напрямую и
    признака разворота не касается вовсе.  Это область другой проверки, и
    молчать об этом нельзя — непроверенное, выданное за проверенное, и есть
    тот фон, ради ухода от которого всё написано.
    """
    import pymupdf

    def sheet(kind):
        doc = pymupdf.open()
        pg = doc.new_page(width=800, height=500)
        if kind == "paper-grey":
            pg.draw_rect(pg.rect, color=None, fill=(0.88, 0.85, 0.78))
        for x0 in (60, 430):                      # две колонки «текста»
            for i in range(20):
                pg.draw_line(pymupdf.Point(x0, 60 + i * 20),
                             pymupdf.Point(x0 + 310, 60 + i * 20),
                             color=(0, 0, 0), width=3)
        black, grey = (0, 0, 0), (0.55, 0.55, 0.55)
        if kind == "shadow-top":
            # ШИРЕ полосы поиска (400 ± 40 pt), иначе `argmin` просто уйдёт от
            # тени в соседний чистый столбец, случай пройдёт по неверной
            # причине и мутацию порога не поймает. В книге тень именно такая:
            # накрывает весь корешок, и уйти от неё некуда.
            pg.draw_rect(pymupdf.Rect(340, 0, 460, 12), color=None, fill=black)
        elif kind == "shadow-full":
            pg.draw_rect(pymupdf.Rect(396, 0, 404, 500), color=None, fill=black)
        elif kind == "rule-full":
            pg.draw_line(pymupdf.Point(60, 250), pymupdf.Point(740, 250),
                         color=black, width=4)
        elif kind == "rule-third":
            pg.draw_line(pymupdf.Point(270, 250), pymupdf.Point(530, 250),
                         color=black, width=4)
        elif kind == "rule-grey":
            pg.draw_line(pymupdf.Point(60, 250), pymupdf.Point(740, 250),
                         color=grey, width=5)
        elif kind == "table":
            for i in range(8):
                pg.draw_line(pymupdf.Point(60, 100 + i * 40),
                             pymupdf.Point(740, 100 + i * 40),
                             color=black, width=4)
        return doc

    bad = 0
    print("самопроверка вето:")
    for name, kind, want in CASES:
        doc = sheet(kind)
        pg = doc[0]
        got = djvu._gutter(pg, pg.rect) is None
        doc.close()
        ok = got == want
        bad += not ok
        print(f"  {name:34s} вето {'ДА ' if got else 'нет'}  "
              f"ждали {'ДА ' if want else 'нет'}"
              f"{'' if ok else '   <-- НЕ СОШЛОСЬ'}")
    print(f"  расхождений {bad} из {len(CASES)}")
    return 1 if bad else 0


def main(argv):
    only, files, i = None, [], 0
    while i < len(argv):
        if argv[i] == "--selfcheck":
            i += 1
        elif argv[i] == "--pages":
            only = {int(x) for x in argv[i + 1].split(",")}
            i += 2
        else:
            files.append(argv[i])
            i += 1

    if "--selfcheck" in argv:
        return selfcheck()
    if not files:
        print(__doc__)
        return 2

    for src in files:
        spreads, vetoed, through, short, detail = probe(src, only)
        print(f"\n{os.path.basename(src)}")
        print(f"  разворотов {spreads}, вето {vetoed} "
              f"({vetoed / max(1, spreads):.1%})")
        print(f"  строк черноты через корешок: сквозных {through}, "
              f"коротких {short}")
        if short and not through:
            print("  — вся чернота оказалась короткой: без различения вето "
                  "сработало бы напрасно на каждом таком развороте")
        for sheet_no, h, thr, sh, share, v in detail[:20]:
            print(f"    лист {sheet_no}: проба {h} строк, сквозные {thr}, "
                  f"короткие {sh}, доля {share:.4f}"
                  f"{'  ВЕТО' if v else ''}")
        if len(detail) > 20:
            print(f"    … ещё {len(detail) - 20}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
