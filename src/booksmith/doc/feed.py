"""Что именно уезжает в VLM: кроп по рамке или страница с дырами.

Две подачи, и обе — ГИПОТЕЗЫ. Ни одна не проверена: VLM в этом проекте не
запускалась после чистого листа ни разу. Поэтому они объявлены ручкой
`VLM_INPUT`, а не выбраны, и сравнит их стенд числом.

    crop         по одному запросу на текстовый блок. Так работает пайплайн
                 PaddleOCR-VL штатно: замер прежнего прогона — 409 запросов
                 на 25 страниц, шестнадцать на страницу.
    masked_page  один запрос на страницу; артефакты замазаны. В шестнадцать
                 раз меньше вызовов, и модель видит связный текст целиком —
                 переносы, колонки, продолжение абзаца через рисунок.

В ОБЕИХ артефакты в VLM не уезжают вовсе. Это и есть первый уровень: текст
читаем, таблицы и рисунки вырезаем картинками и не парсим. Попытка заглянуть
внутрь рисунка проверена и отвергнута — школьная панграмма `The quick brown
fox`, выдуманная по штриховому чертежу, +2100 слов мусора на 20 страницах.

ЧТО ИЗВЕСТНО ПРОТИВ `masked_page`, И ЭТО НАДО ЗНАТЬ ДО ЗАМЕРА.

* **Пустое место не молчит.** Проба «пустой белый лист»: модель выдала пять
  разных китайских канцелярских таблиц за пять попыток. Замазанный
  прямоугольник — тот же пустой лист в миниатюре, и на его месте может
  явиться сочинённая таблица. Поэтому чем замазывать — ручка `MASK_FILL`, а
  не константа: белое здесь наименее нейтрально из всего, что можно выбрать.
* **Контекст портит чтение.** Убрали третий столбец — модель прочла второй
  верно; с полной страницей читала неверно. На этом корпусе изоляция помогла.
* **Потолок ответа.** Пайплайн опускает `max_new_tokens` до 4096, а самый
  длинный ОДИН текстовый блок в наших книгах — 8207 знаков. Страница целиком
  больше, и обрыв у этой модели выглядит как зацикливание.

Здесь, в `doc/`, а не в `models/`, потому что вся работа — геометрия рамок и
растр, тот же код, что у вырезки. В модель это уедет байтами картинки.
"""
import json
import os

from .. import policy
from ..run import knobs
from . import crop
# Якорь блока собирается ОДНИМ правилом на весь проект. Здесь стояла его
# вторая копия (`f"p{page.index:04d}-b{b.block_id}"`), и разошлась бы она с
# `html.anchor_of` при первой же смене схемы имён — молча: feed.json назвал бы
# куски одними именами, книга и blocks.json другими, а связать подачу с
# блоком стало бы нечем. Ровно этой болезнью — двумя копиями одного
# сговора — рождаются проценты из ничего (см. tests/test_html_order.py).
from .html import anchor_of

FILLS = {"white": (1.0, 1.0, 1.0), "black": (0.0, 0.0, 0.0),
         "gray": (0.5, 0.5, 0.5)}
MODES = ("crop", "masked_page")


def params(page_dpi: float | None = None) -> dict:
    """Действующая подача. Уезжает в слепок целиком.

    `page_dpi` — резкость ДЕТЕКЦИИ (`растр.dpi` слепка). Пустые `CROP_DPI` и
    `FEED_DPI` значат «как видела модель», и раскрывать их окружением текущего
    процесса значит называть «как видела модель» то, чего модель не видела.
    Без аргумента ответ несёт поле «dpi откуда» со словом «текущего процесса»
    — угадано, а не сверено.
    """
    mode = knobs.knob("VLM_INPUT")
    if mode not in MODES:
        raise ValueError(f"VLM_INPUT={mode!r}: знаю только {MODES}")
    fill = knobs.knob("MASK_FILL")
    if fill not in FILLS:
        raise ValueError(f"MASK_FILL={fill!r}: знаю только {tuple(FILLS)}")
    # Из crop берём ТОЛЬКО то, что относится к режиму `crop`. Прежняя редакция
    # раскрывала crop.params() целиком, и CROP_DPI молча задавал разрешение
    # ЦЕЛОЙ страницы, уезжающей в VLM: поднимаешь резкость вырезки таблицы —
    # вчетверо растёт картинка подачи, другое число визуальных токенов, другая
    # цена, и сравнение подач мерит уже не то.
    c = crop.params(page_dpi)
    feed_dpi = knobs.knob("FEED_DPI")
    if feed_dpi:
        page_out, src = float(feed_dpi), "FEED_DPI"
    elif page_dpi is not None:
        page_out, src = float(page_dpi), "как у детекции"
    else:
        page_out, src = float(knobs.knob("PAGE_DPI")), "PAGE_DPI текущего процесса"
    return {"feed_mode": mode, "hole_fill": fill,
            "crop_dpi": c["dpi"], "crop_dpi_source": c["dpi_source"],
            "crop_margin": c["margin"],
            "page_dpi": page_out, "page_dpi_source": src}


def _union_rects(holes):
    """Слить пересекающиеся дыры в связные группы (описанными рамками).

    СЛИВАЕТ ДО УПОРА, А НЕ ЗА ОДИН ПРОХОД, и это не придирка. Слитая рамка
    берётся ОПИСАННОЙ, то есть растёт, — и может накрыть ту, которую этот же
    проход уже отложил как непересекающуюся. Замер на построенном входе:
    `[[0,20,4,30], [0,0,10,10], [5,5,8,80]]` — прежний код печатал «дыр 2»
    (`[0,20,4,30]` и `[0,0,10,80]`), хотя вторая целиком накрывает первую и
    группа тут одна. По числу дыр выбирают подачу, и завышенное число делает
    `masked_page` дороже на бумаге, чем она есть.

    На девяти каталогах `bench/*/detect` (762 страницы с артефактами) старый и
    новый счёт совпали до единицы — 1701 дыра тем и другим. То есть в дереве
    беда пока не всплывала; чинится она потому, что вход выбирает не она.
    """
    out = []
    for h in holes:
        cur = list(h)
        rest = list(out)
        grew = True
        while grew:
            grew = False
            keep = []
            for o in rest:
                if (cur[0] < o[2] and o[0] < cur[2]
                        and cur[1] < o[3] and o[1] < cur[3]):
                    cur = [min(cur[0], o[0]), min(cur[1], o[1]),
                           max(cur[2], o[2]), max(cur[3], o[3])]
                    grew = True
                else:
                    keep.append(o)
            rest = keep
        out = rest + [cur]
    return out


def _union_area(holes):
    """Площадь объединения прямоугольников: развёртка по вертикали."""
    if not holes:
        return 0
    xs = sorted({v for h in holes for v in (h[0], h[2])})
    total = 0
    for a, b in zip(xs, xs[1:]):
        spans = sorted((h[1], h[3]) for h in holes if h[0] <= a and h[2] >= b)
        cov, end = 0, None
        for y0, y1 in spans:
            if end is None or y0 > end:
                cov += y1 - y0
                end = y1
            elif y1 > end:
                cov += y1 - end
                end = y1
        total += cov * (b - a)
    return total


def masked_page(doc, page_index: int, boxes, page_dpi: float, dst: str,
                dpi: float | None = None, fill: str | None = None) -> dict:
    """Страница целиком, артефакты замазаны. Возвращает величины подачи.

    Замазываем ПОСЛЕ отрисовки, прямо по растру: рисовать поверх PDF значит
    менять исходник, а он должен остаться нетронутым — из него же режутся
    вырезки для второго уровня.
    """
    import pymupdf

    p = params(page_dpi)
    dpi = p["page_dpi"] if dpi is None else dpi
    fill = p["hole_fill"] if fill is None else fill

    page = doc[page_index]
    pix = page.get_pixmap(dpi=int(dpi))
    # Рамки приходят в пикселях растра детекции; переводим в пиксели ЭТОГО
    # растра. Без пересчёта дыры уехали бы, а страница выглядела бы целой.
    k = dpi / page_dpi
    holes = []
    for b in boxes:
        r = pymupdf.IRect(int(b[0] * k), int(b[1] * k),
                          int(b[2] * k), int(b[3] * k))
        r = r & pymupdf.IRect(0, 0, pix.width, pix.height)
        if r.is_empty:
            continue
        pix.set_rect(r, tuple(int(c * 255) for c in FILLS[fill]))
        holes.append([r.x0, r.y0, r.x1, r.y1])
    # Площадь по ОБЪЕДИНЕНИЮ, а не суммой. Модель отдаёт `chart` и `image` на
    # одном прямоугольнике со связанным рангом — это её задокументированное
    # поведение, — и сумма площадей на такой странице ровно вдвое завышала
    # «долю страницы замазана», а «дыр 2» стояло при одной дыре. По этим
    # числам и выбирают подачу.
    area = _union_area(holes)
    merged = _union_rects(holes)
    os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)
    pix.save(dst)
    return {"file": os.path.basename(dst), "dpi": int(dpi),
            "width": pix.width, "height": pix.height,
            "holes_count": len(merged), "model_boxes": len(holes), "fill": fill,
            "page_share_masked": round(area / (pix.width * pix.height), 4),
            "holes": holes}


def prepare(doc, page, out_dir: str, page_dpi: float, log=print) -> dict:
    """Приготовить то, что уехало бы в VLM, и НИЧЕГО не считать.

    Ни одного обращения к модели: местно, бесплатно, чтобы посмотреть глазами
    и сравнить подачи ДО того, как пойдут деньги.
    """
    p = params(page_dpi)
    os.makedirs(out_dir, exist_ok=True)
    tag = f"p{page.index:04d}"           # имя файла СТРАНИЦЫ, а не якорь блока
    art = [b for b in page.blocks if policy.role(b.label) == "artifact"]
    txt = [b for b in page.blocks if policy.role(b.label) != "artifact"]

    if p["feed_mode"] == "crop":
        items = []
        for b in txt:
            a = anchor_of(page.index, b.block_id)
            rel = f"{a}.png"
            info = crop.cut(doc, page.index, b.box, page_dpi,
                            os.path.join(out_dir, rel))
            items.append({"anchor": a, "label": b.label, **info})
        return {"feed_mode": "crop", "requests": len(items),
                "artifacts_not_sent": len(art), "chunks": items}

    rel = f"{tag}.png"
    info = masked_page(doc, page.index, [b.box for b in art], page_dpi,
                       os.path.join(out_dir, rel))
    return {"feed_mode": "masked_page", "requests": 1,
            "artifacts_masked": len(art),
            "text_blocks_on_page": len(txt),
            # Куда потом вернуть плейсхолдеры. Модель об этом не скажет:
            # промпт у неё два слова, без системного сообщения, попросить
            # метку нечем. Значит, геометрию дыр обязаны помнить мы.
            "page": info}


def dump(result: dict, out_dir: str) -> str:
    path = os.path.join(out_dir, "feed.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    return path
