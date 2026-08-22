#!/usr/bin/env python3
"""Исполняется НА арендованной машине: PDF -> markdown + картинки.

Главное отличие от прошлой версии: страницы пишутся на диск сразу, по одной.
Раньше `predict` прогонялся целиком в список, и до самого конца в выходном
каталоге не появлялось ничего — падение на 400-й странице из 539 теряло всё,
а по числу файлов нельзя было даже понять, идёт ли работа.

Порядок такой:
  outputs/pages/NNNN.md, NNNN.json   пишутся по мере счёта
  outputs/progress.json              обновляется после каждой страницы
  outputs/book.md                    склейка через restructure_pages, в конце
"""
import argparse
import collections
import glob
import html
import json
import os
import re
import sys
import time


def _log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def _slice_pdf(pdf: str, first: int, last: int, out: str) -> str | None:
    """Вырезать диапазон страниц, чтобы можно было продолжить с места обрыва.

    pymupdf в образе может не быть — тогда просто считаем всё заново.
    """
    try:
        import pymupdf
    except ImportError:
        return None
    src = pymupdf.open(pdf)
    dst = pymupdf.open()
    dst.insert_pdf(src, from_page=first, to_page=min(last, src.page_count - 1))
    dst.save(out)
    dst.close()
    src.close()
    return out


def _is_onnx_dir(path: str) -> bool:
    return os.path.isfile(os.path.join(path, "inference.onnx"))


def _concat_pages(pages_dir: str, dst: str) -> int:
    """Собрать книгу из уже записанных страниц, по порядку.

    Запасной путь: без сшивки таблиц через разрыв, но полный и честный —
    в отличие от склейки по страницам одного прогона.
    """
    files = []
    for root, _dirs, names in os.walk(pages_dir):
        for n in names:
            if n.endswith(".md"):
                files.append(os.path.join(root, n))
    files.sort()
    with open(dst, "w") as out:
        for f in files:
            out.write(open(f, encoding="utf-8", errors="replace").read())
            out.write("\n\n")
    return len(files)


def _done_pages(pages_dir: str) -> set[int]:
    if not os.path.isdir(pages_dir):
        return set()
    got = set()
    for n in os.listdir(pages_dir):
        stem = os.path.splitext(n)[0]
        if stem.isdigit():
            got.add(int(stem))
    return got


def _deep_update(base, extra):
    for k, v in extra.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_update(base[k], v)
        else:
            base[k] = v
    return base


def _prefer_tables_over_text():
    """В паре {таблица, текст} побеждает таблица, а не рамка побольше.

    Это правка чужого кода на месте, и вот чем она оправдана.  Детектор
    предлагает для блока несколько классов сразу, и у таблиц без линеек
    текстовый кандидат почти всегда увереннее: на странице 307 три блока
    "RECOMMENDED STANDARDS" получили table 0.70 против text 0.78.  Понижение
    порога делает рамку table доступной — но дальше её убивает
    `filter_overlap_boxes` из paddlex.  Там при перекрытии больше 0.7 есть
    защиты для пар вроде {table, image}, а пара {table, text} проваливается
    мимо них, и побеждает рамка с большей площадью.  Текстовая накрывает
    блок целиком и потому больше почти всегда.

    Замер на двадцати страницах: детектор даёт 20 рамок table, штатный
    фильтр оставляет 10, в markdown доезжает 9.

    Меняется ровно одна ветка: если в паре есть таблица, а вторая рамка не
    из {image, seal, chart}, выбывает вторая — независимо от площади.
    Побочный эффект тут желанный: убрав текстовую рамку, мы иногда спасаем и
    те рамки, которые она давила сама.  Всё остальное — включая разбор таблицы с
    таблицей по площади — остаётся как в paddlex.  Первая версия правки была
    хитрее: она возвращала все съеденные рамки скопом, а потом пыталась
    отсеять дубли по перекрытию.  Обе половины ошиблись — без отсева
    страница 307 дала пять таблиц вместо трёх (две обрубки), с отсевом две
    соседние таблицы слиплись в одну.  Поэтому правка минимальная.

    Текст при этом не теряется: область всё равно уезжает в VLM, просто с
    табличной подсказкой.
    """
    from copy import deepcopy

    from paddlex.inference.pipelines.paddleocr_vl import pipeline as _p
    from paddlex.inference.pipelines.paddleocr_vl.uilts import (
        calculate_polygon_overlap_ratio,
    )

    # Такой же фильтр стоит ВТОРЫМ экземпляром внутри самого предиктора
    # (layout_analysis/processors.py: filter_boxes), и отрабатывает он РАНЬШЕ.
    # То есть к нашей правке табличная рамка, перекрытая текстовой большей
    # площади, уже удалена, и спасать нечего.  Гасим внутренний: наша
    # подмена — его полная переделка с одной изменённой веткой, так что
    # ничего, кроме дублирования, не теряется.
    # По умолчанию внутренний фильтр ОСТАВЛЯЕМ.  Разбор кода предположил, что
    # он съедает нашу правку, отработав раньше; замер этого не подтвердил:
    # на двадцати страницах отключение не дало ни одной лишней строки
    # значений (25 из 29 и с ним, и без него).  Раз пользы нет, а отклонение
    # от поведения библиотеки есть — не отклоняемся.  Выключатель оставлен,
    # чтобы можно было перемерить на другой книге.
    if os.environ.get("KEEP_INNER_FILTER", "1") == "1":
        _log("внутренний фильтр рамок ОСТАВЛЕН включённым (для сравнения)")
    else:
        try:
            from paddlex.inference.models.layout_analysis import (
                processors as _pr,
            )

            _pr.filter_boxes = lambda src_boxes, mode: [
                b for b in src_boxes if b.get("label") != "reference"]
            _log("внутренний фильтр рамок отключён — работает наш")
        except Exception as exc:
            _log(f"внутренний фильтр рамок оставлен как есть: {exc}")

    orig = _p.filter_overlap_boxes
    hard = ("table", "image", "seal", "chart")

    def patched(layout_det_res, layout_shape_mode):
        res = deepcopy(layout_det_res)
        boxes = [b for b in res["boxes"] if b["label"] != "reference"]

        def wh(b):
            c = b["coordinate"]
            return c[2] - c[0], c[3] - c[1]

        def overlap_small(a, b):
            x0 = max(a[0], b[0]); y0 = max(a[1], b[1])
            x1 = min(a[2], b[2]); y1 = min(a[3], b[3])
            i = max(0.0, x1 - x0) * max(0.0, y1 - y0)
            sa = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
            sb = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
            small = min(sa, sb)
            return (i / small if small else 0.0), sa, sb

        dropped = set()
        for i in range(len(boxes)):
            w, h = wh(boxes[i])
            if w < 6 or h < 6:
                dropped.add(i)
            for j in range(i + 1, len(boxes)):
                if i in dropped or j in dropped:
                    continue
                ratio, ai, aj = overlap_small(boxes[i]["coordinate"],
                                              boxes[j]["coordinate"])
                li, lj = boxes[i]["label"], boxes[j]["label"]
                if "inline_formula" in (li, lj):
                    if ratio > 0.5:
                        if li == "inline_formula":
                            dropped.add(i)
                        if lj == "inline_formula":
                            dropped.add(j)
                        continue
                if ratio <= 0.7:
                    continue
                # Уточнение по многоугольникам — как в paddlex.  Режим по
                # умолчанию "auto", а вовсе не "rect": первая версия этой
                # правки отдавала всё неправильному режиму штатной функции и
                # была молчаливой пустышкой — лог печатался, поведение не
                # менялось.  Рамки у нас прямоугольные, ключа polygon_points
                # в них нет, но полагаться на это незачем.
                if layout_shape_mode != "rect" and "polygon_points" in boxes[i]:
                    if calculate_polygon_overlap_ratio(
                            boxes[i]["polygon_points"],
                            boxes[j]["polygon_points"], "small") < 0.7:
                        continue
                labels = {li, lj}
                if labels & set(hard) and len(labels) > 1:
                    if "table" not in labels or labels <= set(hard):
                        continue          # как в paddlex: обе рамки живут
                    # Ровно наша правка: таблица против любой рамки, кроме
                    # image/seal/chart — то есть против text, figure_title,
                    # algorithm и прочих.  Площадь больше не решает.
                    dropped.add(j if li == "table" else i)
                    continue
                dropped.add(j if ai >= aj else i)

        res["boxes"] = [b for k, b in enumerate(boxes) if k not in dropped]
        return res

    _p.filter_overlap_boxes = patched


def _multiview_layout(overlap=0.12, merge=0.55, thr=0.30):
    """Один детектор, двенадцать взглядов на страницу, объединение рамок таблиц.

    Причина в устройстве самого детектора, а не в наших настройках.  В
    inference.yml весов PP-DocLayoutV2 стоит `Resize target_size [800, 800]`
    при `keep_ratio: false`, а вход ONNX-графа жёстко объявлен как
    [N, 3, 800, 800]; обе доступные модели перечислены в
    STATIC_SHAPE_MODEL_LIST, так что размер входа не настраивается в
    принципе.  Страница 1012x1466 сжимается по горизонтали в 0.79, а по
    вертикали в 0.55 — и межстрочный интервал, единственный признак, по
    которому строка таблицы без линеек отличается от строки абзаца, страдает
    сильнее всего.

    Отсюда лечение: показывать детектору меньше бумаги за раз.  Замер на
    bench/tables20.pdf, максимальная уверенность класса table:

        стр 4:  вся страница 0.055 -> четверть   0.489
        стр 9:  вся страница 0.176 -> четверть   0.612
        стр 6:  вся страница 0.197 -> зеркало-в  0.419
        стр 5:  вся страница 0.196 -> зеркало-г  0.348
        стр 15: вся страница 0.389 -> низ        0.809

    Ни один взгляд не выигрывает у остальных — они вытаскивают разные
    страницы, поэтому берётся объединение.  Отражения работают потому, что
    детектор судит о табличности по геометрии белого, а не по чтению текста:
    страница вверх ногами ему не мешает, а сдвиг пиксельной сетки
    перебрасывает пограничный случай через порог.

    Полный проход остаётся якорем: остальные взгляды только ДОБАВЛЯЮТ рамки
    класса table и не трогают ни текст, ни порядок чтения.  Замер на тех же
    20 страницах: 12 таблиц против 19, ложных срабатываний на четырёх пустых
    страницах — ноль, а рамки перестали быть обрезанными (страница 311: было
    86 пикселей ширины, стало 373) и межколоночными (страница 307: рамка в
    801 пиксель через обе колонки исчезла, вместо неё три по 377).
    """
    import numpy as np
    from paddlex.inference.models.layout_analysis.predictor import (
        LayoutAnalysisRunnerPredictor as _L,
    )

    orig = _L.__call__

    def _views(img):
        """(картинка, обратное отображение рамки в координаты страницы)."""
        h, w = img.shape[:2]
        s = max(w, h)
        pad = np.full((s, s, 3), 255, dtype=img.dtype)
        ox, oy = (s - w) // 2, (s - h) // 2
        pad[oy:oy + h, ox:ox + w] = img
        yield pad, lambda b: [b[0] - ox, b[1] - oy, b[2] - ox, b[3] - oy]
        yield img[:, ::-1], lambda b: [w - b[2], b[1], w - b[0], b[3]]
        yield img[::-1, :], lambda b: [b[0], h - b[3], b[2], h - b[1]]

        dx, dy = int(w * overlap), int(h * overlap)
        cuts = [(0, 0, w, h // 2 + dy), (0, h // 2 - dy, w, h),
                (0, 0, w // 2 + dx, h), (w // 2 - dx, 0, w, h)]
        for ny in (0, 1):
            for nx in (0, 1):
                cuts.append((max(0, nx * w // 2 - dx), max(0, ny * h // 2 - dy),
                             min(w, (nx + 1) * w // 2 + dx),
                             min(h, (ny + 1) * h // 2 + dy)))
        for x0, y0, x1, y1 in cuts:
            yield (img[y0:y1, x0:x1],
                   lambda b, x0=x0, y0=y0: [b[0] + x0, b[1] + y0,
                                            b[2] + x0, b[3] + y0])

    def _overlap_small(a, b):
        ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
        iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
        inter = ix * iy
        if inter <= 0:
            return 0.0
        sa = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
        sb = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
        small = min(sa, sb)
        return inter / small if small else 0.0

    def _key(box, mid):
        """Ключ порядка чтения: сначала колонка, потом высота."""
        c = box["coordinate"]
        return (0 if (c[0] + c[2]) / 2 < mid else 1, c[1])

    _k = _render_scale()

    def patched(self, input, **kw):
        # Пачку исчерпываем целиком до того, как звать предиктор снова:
        # sampler у него один на экземпляр, и вложенный вход в него посреди
        # внешней итерации портит его состояние.
        results = list(orig(self, input, **kw))
        for res in results:
            try:
                img = res["input_img"]
                boxes = res["boxes"]
                h, w = img.shape[:2]
                extra = []
                # На фрагменте отключаем уборку вложенных рамок.  Правило
                # paddlex: рамка, лежащая на 90% внутри рамки класса chart,
                # display_formula, doc_title, inline_formula или
                # paragraph_title, молча удаляется (is_contained, iou>=0.9).
                # На целой странице это разумно, а на куске заголовок занимает
                # бо́льшую долю площади и съедает таблицу целиком: первый
                # прогон дал 0 кандидатов там, где локальный замер без этого
                # правила давал 19 рамок.
                # И NMS: он гасит рамку ДРУГОГО класса при перекрытии 0.98,
                # а текстовая рамка поверх таблицы без линеек перекрывается
                # ровно настолько.  То есть кандидат гибнет внутри прохода, и
                # наша правка "таблица важнее текста" до него не доживает.
                # layout_nms=False здесь БЕСПОЛЕЗЕН: в paddlex стоит
                # `layout_nms or self.layout_nms`, а в конфиге True, то есть
                # False or True == True.  Флаг был инертен, и вывод «NMS ни
                # при чём», сделанный по такому замеру, ничего не проверял.
                # Гасим на самом предикторе, вернув значение после прохода.
                vkw = dict(kw, layout_merge_bboxes_mode="union")
                was_nms = getattr(self, "layout_nms", None)
                if os.environ.get("VIEW_NMS", "0") != "1":
                    self.layout_nms = False
                try:
                    for view, back in _views(img):
                        for r in orig(self, [view], **vkw):
                            for b in r["boxes"]:
                                if b["label"] != "table" or b["score"] < thr:
                                    continue
                                c = back(b["coordinate"])
                                c = [max(0, min(w, c[0])), max(0, min(h, c[1])),
                                     max(0, min(w, c[2])), max(0, min(h, c[3]))]
                                if c[2] - c[0] < 40 * _k or c[3] - c[1] < 25 * _k:
                                    continue
                                extra.append({"cls_id": b["cls_id"],
                                              "label": "table",
                                              "score": b["score"],
                                              "coordinate": c})
                finally:
                    # Значение возвращаем в любом случае: иначе первая же
                    # ошибка оставила бы NMS выключенным на весь прогон.
                    if was_nms is not None:
                        self.layout_nms = was_nms
                extra.sort(key=lambda b: -b["score"])

                added = 0
                for cand in extra:
                    hit = None
                    for b in boxes:
                        if b["label"] != "table":
                            continue
                        if _overlap_small(cand["coordinate"], b["coordinate"]) > merge:
                            hit = b
                            break
                    if hit is not None:
                        # Берём ту рамку, что больше по площади, но НЕ их
                        # объединение: объединение выдумывает геометрию,
                        # которой не предлагал ни один детектор, раздувает
                        # рамку на соседний текст и стоило 8 ячеек в прогоне
                        # tables-mv2.  Так лечится страница 311, где рамка
                        # шириной 86 пикселей уступает найденной в 373.
                        a, c = hit["coordinate"], cand["coordinate"]
                        if ((c[2]-c[0]) * (c[3]-c[1])) > ((a[2]-a[0]) * (a[3]-a[1])):
                            hit["coordinate"] = c
                        hit["score"] = max(hit["score"], cand["score"])
                        continue
                    # Место в списке — это порядок чтения, а он влияет и на
                    # markdown, и на склейку таблиц между страницами.  В конец
                    # добавлять нельзя: таблица уедет под низ страницы.
                    mid = w / 2
                    k = _key(cand, mid)
                    pos = len(boxes)
                    for i, b in enumerate(boxes):
                        if _key(b, mid) > k:
                            pos = i
                            break
                    cand["order"] = pos + 1
                    boxes.insert(pos, cand)
                    added += 1
                # Печатаем всегда, даже нули.  Одна из прошлых правок была
                # молчаливой пустышкой: лог о включении печатался, а сама
                # функция не делала ничего, и это стоило целого прогона.
                _log(f"взгляды: кандидатов {len(extra)}, новых рамок {added}")
            except Exception as exc:                      # noqa: BLE001
                # Детекция важнее прибавки: при любой поломке отдаём
                # штатный результат, а не роняем прогон целиком.
                _log(f"многовзглядовая детекция пропущена: {exc}")
        return iter(results)

    _L.__call__ = patched


# Эти блоки к колонкам не относятся и вёрстку не размечают: номер страницы
# лежит ровно посреди низа и своим телом закрывает межколонник.
_NOT_COLUMN = ("number", "header", "footer", "header_image", "footer_image")


def _column_gutter(boxes, w, need_side=2, min_gap=None):
    """Середина межколонника — или None, если двух колонок на странице нет.

    Ищется не по пустому просвету (его закрывает первый же случайный блок,
    и на нашей книге его закрывал номер страницы), а по кластерам левых краёв.
    В двухколонной вёрстке левые края собираются у двух значений; между
    правым краем левой колонки и левым краем правой и лежит межколонник.

    Признаётся он только если по обе стороны есть хотя бы по need_side
    блоков.  На одноколонной книге кластер один, и функция вернёт None —
    разрез не тронет ничего.
    """
    min_gap = int(6 * _render_scale()) if min_gap is None else min_gap
    cols = [b for b in boxes
            if b["label"] != "table" and b["label"] not in _NOT_COLUMN]
    if len(cols) < 2 * need_side:
        return None
    lefts = sorted(b["coordinate"][0] for b in cols)
    # самый большой разрыв в упорядоченных левых краях — граница кластеров
    gap, at = 0, None
    for a, b in zip(lefts, lefts[1:]):
        if b - a > gap:
            gap, at = b - a, (a + b) / 2
    if at is None or gap < w * 0.15:
        return None
    left = [b for b in cols if b["coordinate"][0] < at]
    right = [b for b in cols if b["coordinate"][0] >= at]
    if len(left) < need_side or len(right) < need_side:
        return None
    edge_l = max(b["coordinate"][2] for b in left)
    edge_r = min(b["coordinate"][0] for b in right)
    if edge_r - edge_l < min_gap:
        return None
    return int((edge_l + edge_r) // 2)


def _render_scale():
    """Во сколько раз страница крупнее базовых 144 dpi.

    Пиксельные пороги без этого множителя молча разъезжаются при смене
    разрешения — так уже случилось с воротами переспроса, где порог 12 px на
    288 dpi стал вдвое мягче и отправил на переспрос 103 блока вместо
    четырёх.  Те же грабли лежали ещё в четырёх местах.
    """
    try:
        return max(1.0, float(os.environ.get("PADDLE_PDX_PDF_RENDER_SCALE", 2.0)) / 2.0)
    except ValueError:
        return 1.0


def _split_cross_column_tables(min_gutter=12, margin=4, min_half=120):
    """Разрезать табличную рамку, легшую поперёк межколонника.

    Худший из оставшихся дефектов, и худший он именно для машины-читателя.
    На стр. 313 детектор выдал рамку шириной 801 px на странице в 1012, и две
    разные таблицы склеились в одну сетку на десять столбцов: «Engine Lathe»
    оказался в столбце значений.  Человек, взглянув на такую сетку, сразу
    увидит бессмыслицу; модель-пересказчик уверенно перескажет её как факт.

    Одного пересечения мало: бывает и настоящая таблица во всю ширину полосы.
    Поэтому проверяются чернила — если внутри рамки на месте межколонника
    идёт сквозной просвет, это две таблицы; если текст пересекает его, это
    одна, и её не трогаем.  Разрез делается здесь, а не в фильтре рамок,
    именно ради доступа к картинке.
    """
    from paddlex.inference.pipelines.components.common.crop_image_regions import (
        CropByBoxes as _C,
    )
    import numpy as np

    k = _render_scale()
    min_gutter = int(min_gutter * k)
    margin = int(margin * k)
    min_half = int(min_half * k)
    orig = _C.__call__

    def clear_corridor(img, box, mid, half=None):
        half = int(8 * k) if half is None else half
        # Пуст ли столбец шириной 2*half на месте межколонника внутри рамки.
        x0, y0, x1, y1 = [int(v) for v in box]
        a, b = max(x0, mid - half), min(x1, mid + half)
        if b - a < 3 or y1 - y0 < 3:
            return False
        strip = img[max(0, y0):y1, a:b]
        if strip.size == 0:
            return False
        g = strip if strip.ndim == 2 else strip.mean(2)
        return bool((g < max(128, g.mean() - 25)).sum() < 0.005 * g.size)

    def patched(self, img, boxes, layout_shape_mode="auto"):
        try:
            w = img.shape[1]
            mid = _column_gutter(boxes, w + 1)
            if mid is not None:
                out, cut, kept = [], 0, 0
                for b in boxes:
                    c = b["coordinate"]
                    wide = (b.get("label") == "table"
                            and c[0] < mid - min_gutter and c[2] > mid + min_gutter
                            and (mid - c[0]) > min_half and (c[2] - mid) > min_half)
                    if wide and clear_corridor(img, c, mid):
                        left, right = dict(b), dict(b)
                        # Многоугольник целой рамки половинкам не годится:
                        # CropByBoxes строит по нему маску и заливает всё вне
                        # её белым, так что правая половина ушла бы в VLM
                        # почти пустым листом.  Прямоугольника достаточно.
                        left.pop("polygon_points", None)
                        right.pop("polygon_points", None)
                        left["coordinate"] = [c[0], c[1], mid - margin, c[3]]
                        right["coordinate"] = [mid + margin, c[1], c[2], c[3]]
                        out += [left, right]
                        cut += 1
                    else:
                        if wide:
                            kept += 1
                        out.append(b)
                if cut or kept:
                    _log(f"межколонник x={mid}: разрезано рамок {cut}, "
                         f"оставлено сплошными {kept}")
                boxes = out
        except Exception as exc:
            _log(f"разрез по межколоннику пропущен: {exc}")
        return orig(self, img, boxes, layout_shape_mode)

    _C.__call__ = patched


def _looks_tabular(img, min_lines=2, max_lines=8, gap_per_line=0.7,
                   min_gaps=2, frac=0.6):
    """Похож ли кроп на таблицу по просветам между столбцами.

    Детектор макета судит о «табличности» по геометрии пробелов, но видит
    страницу сжатой до 800x800 — по вертикали втрое (см. docs/ocr-notes.md).
    Здесь тот же признак меряется на кропе в родном разрешении, где он цел.

    Это не приговор, а только отбор кандидатов на переспрос: замер на двадцати
    страницах показал, что ширины просветов у настоящих таблиц (22..110 px) и у
    обычных абзацев (20..35 px) перекрываются, чистого порога нет.  Поэтому
    правило намеренно щедрое, а решает дальше сама VLM — и её ошибка обратима
    (см. _unwrap_degenerate_tables).

    Просвет засчитывается, если он чист в большинстве строк, а не во всех:
    у здешних таблиц последняя строка — примечание вроде "(At end of 12 inch
    test bar)", растянутое на все столбцы, и оно закрывало бы любой просвет.

    Ширина просвета меряется в долях высоты строки, а не в пикселях.  Первая
    версия держала порог в 12 px и молча разъезжалась при смене разрешения:
    на 288 dpi просветы вдвое шире, порог стал вдвое мягче, и на переспрос
    ушло 103 блока вместо четырёх.  Разворот их вернул, но 99 вызовов VLM
    были потрачены впустую.
    """
    import cv2
    import numpy as np
    if img is None or img.size == 0 or img.shape[0] < 20 or img.shape[1] < 60:
        return False
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    ink = (g < max(128, int(g.mean()) - 25))
    rows = ink.any(1)
    lines, start = [], None
    for y, v in enumerate(rows):
        if v and start is None:
            start = y
        elif not v and start is not None:
            if y - start >= 4:
                lines.append((start, y))
            start = None
    if start is not None and len(rows) - start >= 4:
        lines.append((start, len(rows)))
    if not min_lines <= len(lines) <= max_lines:
        return False
    heights = sorted(b - a for a, b in lines)
    min_gap_px = max(6, int(gap_per_line * heights[len(heights) // 2]))
    nz = np.flatnonzero(ink.any(0))
    if nz.size == 0:
        return False
    # поля слева и справа есть у любого абзаца — считаем только внутренние
    blank = np.array([~ink[a:b, nz[0]:nz[-1] + 1].any(0) for a, b in lines])
    keep = blank.mean(0) >= frac
    found, run = 0, 0
    for v in keep:
        if v:
            run += 1
        else:
            if run >= min_gap_px:
                found += 1
            run = 0
    if run >= min_gap_px:
        found += 1
    return found >= min_gaps


def _reask_text_as_table():
    """Переспросить VLM по блокам `text`, похожим на таблицу.

    Главный вывод замеров: содержимое таблиц никогда не терялось.  Детектор
    ставит рамку правильно, но с ярлыком `text`, и VLM, получив промпт "OCR:",
    честно читает строки вместо того, чтобы построить сетку.  Ломается не
    детекция, а одно решение о разметке в самом конце.

    Поэтому здесь не добавляется ни одна новая модель: кандидату просто
    меняется ярлык, и дальше пайплайн сам отправляет тот же кроп в ту же VLM
    с промптом "Table Recognition:".

    Хук — сразу после нарезки кропов и до склейки соседних блоков: у merge_blocks
    в non_merge_labels есть "table", так что переименованный кандидат перестаёт
    приклеиваться к абзацу сверху.  Ярлык меняется на месте, поэтому и разметку
    страницы рисует уже как таблицу.
    """
    from paddlex.inference.pipelines.components.common.crop_image_regions import (
        CropByBoxes as _C,
    )
    orig = _C.__call__

    def patched(self, img, boxes, layout_shape_mode="auto"):
        out = orig(self, img, boxes, layout_shape_mode)
        n = 0
        for blk in out:
            if blk.get("label") != "text":
                continue
            try:
                if _looks_tabular(blk["img"]):
                    blk["label"] = "table"
                    n += 1
            except Exception as exc:
                # continue, а не break: одна кривая картинка выключала ворота
                # для всех оставшихся блоков страницы, а лог печатал
                # уменьшенное число и выглядел рабочим.
                _log(f"ворота переспроса, блок пропущен: {exc}")
                continue
        if n:
            _log(f"переспрос: блоков text отправлено как таблицы {n}")
        return out

    _C.__call__ = patched


def _link_table_crops(pdf, pages_dir, book_dir, scale=None):
    """Положить рядом с каждой таблицей ссылку на её же скан.

    Ради этого всё и делалось: сетку, вызывающую сомнение, дальше можно
    сверить с картинкой — глазом или мультимодальной моделью.  Молчаливую
    ошибку мы уже умеем помечать, а теперь её можно и проверить.

    Ссылка кладётся HTML-комментарием перед таблицей: в отрисованном виде он
    невидим, а модели, читающей исходный markdown, виден полностью.

    Рамки берутся из parsing_res_list, где у каждого блока есть и ярлык, и
    координаты; таблицы в разметке идут в том же порядке чтения.  Если числа
    не сходятся, ничего не трогаем и говорим об этом: подписать чужой скан
    хуже, чем не подписать никакого.
    """
    import pypdfium2 as pdfium

    scale = float(scale or os.environ.get("PADDLE_PDX_PDF_RENDER_SCALE", 2.0))
    imgs = os.path.join(book_dir, "imgs")
    os.makedirs(imgs, exist_ok=True)
    doc = pdfium.PdfDocument(pdf)
    tag_re = re.compile(r"<[^>]+>")
    cell_re = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.I | re.S)
    total = skipped = 0
    all_signs: dict = {}        # подпись таблицы -> имена вырезанных сканов

    def sign(table_html):
        """Подпись таблицы — её ячейки подряд, без разметки и пробелов.

        Сопоставлять по порядку нельзя: часть табличных рамок возвращает
        пустой OTSL и в разметку не попадает вовсе, счёт разъезжается.
        А ячейки у рамки и у готовой таблицы одни и те же, отличается только
        обвязка тегов.
        """
        # Маркер неуверенности снимается: _mark_uncertain дописывает его в
        # ячейки раньше, чем считается подпись, и без этого рамка перестаёт
        # узнавать собственную таблицу.
        cells = [re.sub(r"\s+", "",
                        html.unescape(tag_re.sub("", c)).replace("⚠", ""))
                 for c in cell_re.findall(table_html)]
        return "\x1f".join(c for c in cells if c)

    # Книжный файл обходится вместе с постраничными: раньше `book_dir`
    # служил только местом для imgs/, и главный результат ссылок не получал
    # вовсе, хотя лог рапортовал «проставлено N».
    book_md = [f for f in glob.glob(os.path.join(book_dir, "*.md"))]
    for jf in sorted(glob.glob(os.path.join(pages_dir, "*.json"))):
        mf = jf[:-5] + ".md"
        if not os.path.exists(mf):
            continue
        try:
            data = json.load(open(jf, encoding="utf-8"))
            blocks = [b for b in data.get("parsing_res_list", [])
                      if b.get("block_label") == "table"
                      and b.get("block_content")]
            if not blocks:
                continue
            by_sign = {}
            for b in blocks:
                by_sign.setdefault(sign(str(b["block_content"])), []).append(b)
            md = open(mf, encoding="utf-8").read()
            page_idx = int(data.get("page_index") or 0)
            img = None
            out, prev, miss = [], 0, 0
            for m in re.finditer(r"<table\b.*?</table>", md, re.I | re.S):
                same = by_sign.get(sign(m.group(0)))
                if not same:
                    miss += 1
                    continue
                b = same.pop(0)
                x0, y0, x1, y1 = [int(v) for v in b["block_bbox"]]
                name = f"tbl_p{page_idx:04d}_{x0}_{y0}_{x1}_{y1}.jpg"
                path = os.path.join(imgs, name)
                if not os.path.exists(path):
                    if img is None:
                        img = doc[page_idx].render(scale=scale).to_pil()
                    img.crop((x0, y0, x1, y1)).convert("RGB").save(
                        path, "JPEG", quality=88)
                # Тот же скан нужен и рядом со страницей: постраничные файлы
                # ссылаются на свой каталог imgs, а не на книжный, и без этой
                # копии ссылка вела в никуда — 26 страниц из 539.
                near = os.path.join(pages_dir, "imgs")
                os.makedirs(near, exist_ok=True)
                twin = os.path.join(near, name)
                if not os.path.exists(twin):
                    try:
                        os.link(path, twin)
                    except OSError:
                        import shutil as _sh
                        _sh.copyfile(path, twin)
                all_signs.setdefault(sign(m.group(0)), []).append(name)
                out.append(md[prev:m.start()])
                out.append(f"<!-- скан таблицы: imgs/{name} -->\n")
                prev = m.start()
                total += 1
            skipped += miss
            if out:
                # Не `if prev:` — таблица может начинаться с нулевого
                # смещения, и тогда правка терялась, а счётчик её уже учёл.
                out.append(md[prev:])
                with open(mf, "w", encoding="utf-8") as fh:
                    fh.write("".join(out))
        except Exception as exc:
            _log(f"ссылки на сканы таблиц, {os.path.basename(jf)}: {exc}")

    # Книжный файл — тот же обход, но по общей карте подписей: страницы уже
    # прошли, кропы вырезаны, остаётся вставить комментарии.
    for bf in book_md:
        try:
            md = open(bf, encoding="utf-8").read()
            if "<table" not in md.lower():
                continue
            pool = {k: list(v) for k, v in all_signs.items()}
            out, prev, added = [], 0, 0
            for m in re.finditer(r"<table\b.*?</table>", md, re.I | re.S):
                names = pool.get(sign(m.group(0)))
                if not names:
                    continue
                out.append(md[prev:m.start()])
                out.append(f"<!-- скан таблицы: imgs/{names.pop(0)} -->\n")
                prev = m.start()
                added += 1
            if out:
                out.append(md[prev:])
                with open(bf, "w", encoding="utf-8") as fh:
                    fh.write("".join(out))
                total += added
        except Exception as exc:
            _log(f"ссылки на сканы таблиц, {os.path.basename(bf)}: {exc}")

    return total, skipped


def _drop_orphan_crops(book_dir, *dirs):
    """Убрать сканы таблиц, на которые в разметке уже никто не ссылается.

    Развёрнутая обратно таблица уносит свой комментарий, а вырезанный скан
    остаётся лежать.  На двадцати страницах таких десять из тридцати трёх; на
    книге это сотни файлов, которые выглядят частью разбора и ею не являются.
    """
    used = set()
    for d in dict.fromkeys(dirs):
        for f in glob.glob(os.path.join(d, "*.md")):
            used.update(re.findall(r"скан таблицы: imgs/(\S+?) -->",
                                   open(f, encoding="utf-8").read()))
    gone = 0
    # Чистим оба каталога: близнец рядом со страницами — жёсткая ссылка, и
    # без его удаления место не освобождается вовсе, а осиротевший скан
    # остаётся лежать.
    for d in dict.fromkeys(dirs + (book_dir,)):
        for f in glob.glob(os.path.join(d, "imgs", "tbl_*.jpg")):
            if os.path.basename(f) not in used:
                os.remove(f)
                gone += 1
    return gone


def _fix_broken_img_tags(*dirs):
    """Переписать теги картинок начисто, взяв из них только src.

    paddleocr для картинок ВНУТРИ таблиц пишет `alt="Image""` — с лишней
    кавычкой.  Разметка от этого невалидна, и разборщик pandoc такой тег
    молча выбрасывает: две картинки из 686 не доезжали ни в html, ни в epub,
    ни в fb2.  Причину искали долго, потому что ссылки разрешались, файлы
    были на месте и все различались по содержимому — ломался не файл, а
    кавычка рядом с ним.

    Чиним не заплатой на кавычку, а переписыванием: две попытки поправить
    кавычки по отдельности сделали хуже, оставив то незакрытый атрибут, то
    мусор в alt.  Из тега нужен только src, остальное — украшение.
    """
    tag = re.compile(r'<img\b[^>]*?src\s*=\s*"([^"]+)"[^>]*?/?>', re.I)
    fixed = 0
    for d in dict.fromkeys(dirs):
        for f in glob.glob(os.path.join(d, "*.md")):
            src = open(f, encoding="utf-8").read()

            def one(m):
                canon = f'<img src="{m.group(1)}" alt="Image" />'
                return canon if m.group(0) != canon else m.group(0)

            dst = tag.sub(one, src)
            if dst != src:
                with open(f, "w", encoding="utf-8") as fh:
                    fh.write(dst)
                fixed += 1
    return fixed


def _unwrap_degenerate_tables(*dirs):
    """Развернуть обратно в текст таблицы, оказавшиеся не таблицами.

    Обратная сторона щедрых ворот: абзац, отправленный на переспрос, вернётся
    сеткой в один столбец или в одну строку.  Текст при этом цел — он лежит по
    ячейкам, — так что ошибка стоит только разметки и снимается разбором HTML.
    Настоящую таблицу (два столбца и две строки минимум) не трогаем.
    """
    rows_re = re.compile(r"<tr[^>]*>(.*?)</tr>", re.I | re.S)
    cell_re = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.I | re.S)
    tag_re = re.compile(r"<[^>]+>")
    n = 0

    def one(m):
        nonlocal n
        rows = [cell_re.findall(r) for r in rows_re.findall(m.group(0))]
        if not rows:
            return m.group(0)
        if len(rows) >= 2 and max(len(r) for r in rows) >= 2:
            return m.group(0)
        n += 1
        out = []
        for r in rows:
            line = " ".join(html.unescape(tag_re.sub("", c)).strip() for c in r)
            if line.strip():
                out.append(line.strip())
        return "\n\n".join(out)

    for d in dict.fromkeys(dirs):
        for f in glob.glob(os.path.join(d, "*.md")):
            src = open(f, encoding="utf-8").read()
            # Комментарий со ссылкой на скан снимается вместе с таблицей:
            # осиротевшая ссылка указывала бы на картинку, которой в тексте
            # больше нет.
            dst = re.sub(r"(?:<!-- скан таблицы: [^>]*-->\n)?<table\b.*?</table>",
                         one, src, flags=re.I | re.S)
            if dst != src:
                with open(f, "w", encoding="utf-8") as fh:
                    fh.write(dst)
    return n


# Ответ VLM -> куски текста, которые она выдала неуверенно.
# Заполняется _capture_logprobs, читается _mark_uncertain.
_LOW: dict = {}


def _capture_logprobs(thr=-1.0):
    """Просить у vLLM вероятность каждого токена и запоминать слабые места.

    Наш порок не в том, что модель ошибается, а в том, что она молчит об этом:
    на выцветшем скане (стр. 304) она дописала третий столбец по образцу первых
    двух и выдала `.0005` вместо `.0015` с тем же видом уверенности.  Модель,
    обученная предсказывать следующий токен, обязана что-то выдать и не умеет
    сказать «не разбираю».

    Но само знание у неё есть — в вероятностях.  Обученного заново детектора
    для этого не нужно: vLLM отдаёт logprob каждого токена, если попросить.

    Порог -1.0 в логарифме это примерно 37% вероятности: ниже — модель
    выбирала почти наугад.
    """
    from paddlex.inference.models.common.genai import GenAIClient
    from paddlex.inference.models.doc_vlm.predictor import (
        DocVLMGenAIClientPredictor as _P,
    )

    call = GenAIClient.create_chat_completion

    def patched_call(self, messages, *, return_future=False, **kw):
        kw.setdefault("logprobs", True)
        return call(self, messages, return_future=return_future, **kw)

    GenAIClient.create_chat_completion = patched_call

    collect = _P._doc_vlm_genai_collect_responses

    def patched_collect(self, futures):
        out = []
        for future in futures:
            res = future.result()
            ch = res.choices[0]
            text = ch.message.content
            out.append(text)
            try:
                toks = ch.logprobs.content or []
            except AttributeError:
                toks = []
            spans, pos = [], 0
            for t in toks:
                n = len(t.token)
                if t.logprob < thr:
                    spans.append((pos, pos + n, round(t.logprob, 2)))
                pos += n
            if spans:
                _LOW[text] = spans
        return out

    _P._doc_vlm_genai_collect_responses = patched_collect


# Ниже этих порогов пометка в прозе только шумит: ответ короче MARK_MIN_RESP
# нельзя привязать к месту на странице, а кусок короче MARK_MIN_SPAN ничего не
# говорит читателю.  Ячейки таблиц помечаются целиком и под пороги не подпадают.
MARK_MIN_RESP = 24
MARK_MIN_SPAN = 3
# Ячейка короче этого не ищется: короткая строка находится внутри почти
# любого слабого места чужого ответа.
MARK_MIN_CELL = 4


def _mark_uncertain(*dirs, mark="⚠"):
    """Пометить в разметке места, которые модель выдала неуверенно.

    Две пометки, потому что случаи разные.  В таблице помечается ячейка
    целиком: читателю (и модели, что будет пересказывать) важно «этому числу
    не верь», а не какая цифра сомнительна.  В прозе помечается сам кусок,
    завёрнутый в <mark> — так видно, где именно modель гадала, и разметка
    остаётся читаемой.

    Молчаливая ошибка становится видимой — это всё, чего мы тут добиваемся.
    Проверено на замере: в неуверенные места попали `RECOMMENDATION STANDARDS`
    вместо RECOMMENDED и `tarsock` вместо tailstock, то есть настоящие промахи,
    а не случайные ячейки.
    """
    cell_re = re.compile(r"(<t[dh][^>]*>)(.*?)(</t[dh]>)", re.I | re.S)
    table_re = re.compile(r"<table\b.*?</table>", re.I | re.S)
    tag_re = re.compile(r"<[^>]+>")
    n_cell = n_span = 0
    local: list = []          # ответы VLM, относящиеся к текущей странице

    def suspicious(txt):
        """Попал ли текст ячейки в неуверенное место ответа ЭТОЙ страницы.

        Две поправки против прежней версии, и обе по одной причине — ячейка
        помечалась чужой неуверенностью:

        Порог длины: `4` или `.001` найдётся внутри почти любого слабого
        места, и пометка теряет смысл.  В прозе такой порог уже стоял, в
        ячейках его забыли.

        А вот привязать поиск к своей странице, как сделано для прозы,
        нельзя: ответ по таблице приходит в OTSL (`<fcel>Tool Room<fcel>…`),
        а в разметку попадает уже как HTML.  Условие «ответ встречается на
        этой странице» для таблиц не выполняется никогда — проверено, оно
        обнулило пометку ячеек целиком: было 24, стало 0.
        """
        plain = html.unescape(tag_re.sub("", txt)).strip()
        if len(plain) < MARK_MIN_CELL:
            return False
        for src, spans in _LOW.items():
            i = src.find(plain)
            while i >= 0:
                for a, b, _ in spans:
                    if a < i + len(plain) and b > i:
                        return True
                i = src.find(plain, i + 1)
        return False

    def cell(m):
        nonlocal n_cell
        if suspicious(m.group(2)):
            n_cell += 1
            return m.group(1) + m.group(2) + f" {mark}" + m.group(3)
        return m.group(0)

    for d in dict.fromkeys(dirs):
        for f in glob.glob(os.path.join(d, "*.md")):
            src_md = open(f, encoding="utf-8").read()
            # Отбор ответов этой страницы делается ОДИН раз на файл.  Раньше
            # он шёл заново на каждую ячейку, и на книге это давало сотни
            # миллионов подстрочных поисков.
            local = [(src, spans) for src, spans in _LOW.items()
                     if src in src_md]
            out = cell_re.sub(cell, src_md)

            # Проза: заворачиваем сам сомнительный кусок, но не трогаем то,
            # что уже внутри таблицы — там пометка своя, на всю ячейку.
            safe = [(m.start(), m.end()) for m in table_re.finditer(out)]
            edits = []
            for resp, spans in _LOW.items():
                # Короткий ответ найти на странице однозначно нельзя: строка
                # вроде "4" встречается всюду, и пометка садится на случайное
                # совпадение.  На двадцати страницах такие ответы не
                # набирались, на пятистах их оказалось 173 — и 1365 пометок
                # из 1457 пришлись на одиночные символы.
                if len(resp) < MARK_MIN_RESP:
                    continue
                base = out.find(resp)
                if base < 0 or out.find(resp, base + 1) >= 0:
                    continue      # нет вовсе либо встречается дважды
                if any(a <= base < b for a, b in safe):
                    continue
                for a, b, _ in spans:
                    if b - a < MARK_MIN_SPAN:
                        continue  # одиночный символ помечать бессмысленно
                    edits.append((base + a, base + b))
            # Наложения надо слить ДО вставки: два соседних неуверенных
            # места, вставленные по отдельности, режут друг другу тег, и в
            # разметке остаётся `1mark title="..."` без угловой скобки.
            merged = []
            for a, b in sorted(set(edits)):
                if merged and a <= merged[-1][1]:
                    merged[-1] = (merged[-1][0], max(merged[-1][1], b))
                else:
                    merged.append((a, b))
            for a, b in reversed(merged):
                if out[a:b].strip() and "<" not in out[a:b]:
                    out = (out[:a] + '<mark title="модель не уверена">'
                           + out[a:b] + "</mark>" + out[b:])
                    n_span += 1

            if out != src_md:
                with open(f, "w", encoding="utf-8") as fh:
                    fh.write(out)
    return n_cell, n_span


def _probe_hallucination(server, model, pdf, page=2, scale=4.0,
                         box=(258, 2435, 1005, 2642), tries=5):
    """Читает ли модель картинку — или достраивает по языковому навыку.

    Повод: на стр. 304 модель выдала `.0005` там, где на скане `.0015`, и
    выдала уверенно.  Для сети в 0.9B это странно: у неё нет тех знаний о
    мире, которыми большая модель могла бы «додумать смысл числа».  Значит,
    достраивает она не смысл, а узор — две одинаковые ячейки слева.

    Проверяется четырьмя подачами одного и того же промпта:

    - как есть — то, что видит конвейер;
    - пустой лист того же размера — если ответ всё равно похож на таблицу,
      картинка не читается вовсе, и это чистый языковой навык;
    - только правая треть — исчезает узор `.0005 | .0005` слева, и если
      значение меняется, оно бралось из соседей, а не со скана;
    - левые две трети — если третье значение всё равно появится, оно
      выдумано целиком.
    """
    import base64, io
    from openai import OpenAI
    import pypdfium2 as pdfium
    from PIL import Image

    scale = float(os.environ.get("PROBE_SCALE", scale))
    k = scale / 4.0                      # рамка снята при scale=4
    box = tuple(int(v * k) for v in box)
    cli = OpenAI(base_url=server, api_key="null")
    crop = pdfium.PdfDocument(pdf)[page].render(scale=scale).to_pil().crop(box)
    _log(f"проба на масштабе {scale} ({int(scale*72)} dpi), кроп {crop.size}")
    w, h = crop.size
    cases = {
        "как есть": crop,
        "пустой лист": Image.new("RGB", (w, h), "white"),
        "только правая треть": crop.crop((int(w * 0.62), 0, w, h)),
        "левые две трети": crop.crop((0, 0, int(w * 0.70), h)),
    }

    def ask(im, temp):
        buf = io.BytesIO()
        im.convert("RGB").save(buf, "JPEG", quality=90)
        url = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
        r = cli.chat.completions.create(
            model=model, temperature=temp, max_tokens=512, logprobs=True,
            messages=[{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": url}},
                {"type": "text", "text": "Table Recognition:"}]}])
        ch = r.choices[0]
        toks = getattr(ch.logprobs, "content", None) or []
        worst = min((t.logprob for t in toks), default=0.0)
        return ch.message.content, worst

    _log("=== проба на выдумывание ===")
    for name, im in cases.items():
        txt, worst = ask(im, 0.0)
        _log(f"[{name}] жадно, худший logprob {worst:.2f}:")
        _log("    " + (txt or "").replace(chr(10), " ")[:300])
        seen = collections.Counter()
        for _ in range(tries):
            t, _w = ask(im, 0.6)
            seen[(t or "").replace(chr(10), " ")[:300]] += 1
        _log(f"    при температуре 0.6 из {tries} попыток различных ответов "
             f"{len(seen)}:")
        for t, n in seen.most_common(3):
            _log(f"      x{n}: {t[:220]}")


def _pipeline_config(layout_dir, table_threshold=0.05):
    """Конфигурация пайплайна: детекция на ONNX Runtime и пачки страниц.

    Ключ `engine` внутри подмодуля имеет наивысший приоритет (paddlex
    resolve_child_engine), а выход совпадает с paddle побитово: замер на 82
    рамках дал IoU 1.0000 и расхождение координат 0.00 пикселя при втрое
    большей скорости.  Заодно из окружения уходит GPU-сборка paddle на
    3.69 ГБ.
    """
    from paddlex.inference import load_pipeline_config

    # Имя конфигурации зависит от версии пайплайна; у paddleocr 3.7 по
    # умолчанию v1.6.  Если однажды переименуют — откатываемся на v1.
    for name in ("PaddleOCR-VL-1.6", "PaddleOCR-VL"):
        try:
            cfg = load_pipeline_config(name)
            break
        except Exception:
            cfg = None
    if cfg is None:
        raise SystemExit("не нашлась конфигурация пайплайна PaddleOCR-VL")

    # Порог детекции.  В конфигурации пайплайна он стоит числом 0.3, но
    # postprocess при словаре берёт для незаданных классов 0.5 — то есть
    # словарь с одним классом молча ухудшил бы все остальные.  Поэтому
    # задаём все 25 меток явно.
    thr = {i: 0.3 for i in range(25)}
    thr[21] = table_threshold          # table

    return _deep_update(cfg, {
        # Пачка страниц.  Умолчание пайплайна — 64, и оно не влезает: 64
        # страницы разом идут в детектор, арена ONNX Runtime раздувается до
        # 5.4 ГБ и вместе с 18 ГБ vLLM упирается в 23.5 ГБ карты — прогон
        # падает на "CUDA out of memory. Tried to allocate 76.00 MiB".
        # Замерено: с четвёркой те же 20 страниц считаются с запасом по
        # памяти на скорости 4 стр/с.  Это ограничение по памяти, а не по
        # скорости, и снимать его можно только вместе с долей vLLM.
        "batch_size": 4,
        "SubModules": {
            "LayoutDetection": {
                "module_name": "layout_detection",
                "model_name": os.environ.get("LAYOUT_MODEL_NAME",
                                             "PP-DocLayoutV2"),
                "model_dir": layout_dir,
                "engine": "onnxruntime",
                "threshold": thr,
                # Восьмёрка требовала 430 МБ единым буфером и не влезала
                # рядом с vLLM; четвёрка вдвое дешевле по памяти, а
                # детекция всё равно не узкое место.
                "batch_size": 4,
            }
        }
    })



def _strip_running_headers(pages_dir, *targets):
    """Убрать колонтитулы — по повторяемости, а не по метке.

    Название главы и колонтитул несут одну и ту же метку `header`, поэтому
    отличить их можно только по одному признаку: колонтитул стоит на многих
    страницах, название главы — на одной.  Порог с запасом: не меньше трёх
    страниц и не меньше трети книги.

    Возвращает то, что убрано, — чтобы это было видно в логе, а не молча.
    """
    seen = collections.Counter()
    npages = 0
    for f in sorted(glob.glob(os.path.join(pages_dir, "*.json"))):
        npages += 1
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        for r in d.get("parsing_res_list") or []:
            if r.get("block_label") == "header":
                t = (r.get("block_content") or "").strip()
                if t:
                    seen[t] += 1

    # Треть книги — порог, годный для брошюры и бессмысленный для тома: на
    # 539 страницах он равен 179, и колонтитул главы (30-40 страниц) не
    # пройдёт его никогда.  Берём меньшее из трети и двадцати повторов.
    limit = max(3, min(20, npages // 3))
    running = {t for t, c in seen.items() if c >= limit}
    if not running:
        return []

    # Блок может занимать несколько строк — сравниваем построчно.
    lines = {ln.strip() for t in running for ln in t.splitlines() if ln.strip()}
    for target in targets:
        for f in glob.glob(os.path.join(target, "*.md")):
            try:
                src = open(f, encoding="utf-8").read().splitlines(keepends=True)
            except Exception:
                continue
            kept = [ln for ln in src if ln.strip() not in lines]
            if len(kept) != len(src):
                open(f, "w", encoding="utf-8").writelines(kept)
    return sorted(running)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--model", default="PaddleOCR-VL-1.6-0.9B")
    ap.add_argument("--server", default="",
                    help="URL сервиса vLLM; пусто — считать в процессе")
    ap.add_argument("--device", default="gpu:0",
                    help="без этого пайплайн уезжает целиком на CPU: "
                         "видеокарта на нуле, одно ядро в потолке")
    ap.add_argument("--resume", action="store_true",
                    help="продолжить с первой несчитанной страницы")
    a = ap.parse_args()

    out = a.out
    pages_dir = os.path.join(out, "pages")
    os.makedirs(pages_dir, exist_ok=True)

    pdf = a.pdf
    full_pdf = pdf                  # исходник до подмены на срез возобновления
    offset = 0
    if a.resume:
        done = _done_pages(pages_dir)
        if done:
            # Первая дыра, а не максимум: если страница в середине не
            # записалась (save_to_markdown падает, ошибка проглатывается и
            # логируется), при max она не пересчитается НИКОГДА, а run.json
            # покажет полное число страниц, будто всё на месте.
            first = next((i for i in range(max(done) + 1) if i not in done),
                         max(done))
            if first < max(done):
                _log(f"в разборе дыра начиная со страницы {first+1} — "
                     f"считаю с неё, а не с конца")
            sliced = _slice_pdf(pdf, first, 10 ** 6,
                                os.path.join(out, "_resume.pdf"))
            if sliced:
                pdf, offset = sliced, first
                _log(f"продолжаю со страницы {first+1} ({len(done)} уже готовы)")
            else:
                _log("pymupdf недоступен — продолжить с середины нечем, считаю всё")

    from paddleocr import PaddleOCRVL

    kwargs = {"device": a.device}

    # Детекцию макета уводим на ONNX Runtime, если в образе лежат ONNX-веса.
    # Ключ `engine` внутри подмодуля имеет наивысший приоритет (paddlex
    # resolve_child_engine), а сам выход побитово тот же: замер на 82 рамках
    # дал IoU 1.0000 и расхождение координат 0.00 пикселя при втрое большей
    # скорости. Заодно из образа уходит GPU-сборка paddle на 3.69 ГБ.
    layout_dir = os.environ.get("LAYOUT_MODEL_DIR", "")
    if layout_dir and _is_onnx_dir(layout_dir):
        # paddlex_config словарём НЕ сливается с конфигурацией по умолчанию:
        # в paddleocr/_pipelines/base.py это буквально `config =
        # self._paddlex_config`, то есть подмена целиком.  Передать один
        # подмодуль нельзя — пайплайн остаётся без `pipeline_name` и падает
        # с KeyError.  Поэтому берём конфигурацию сами и сливаем в неё.
        kwargs["paddlex_config"] = _pipeline_config(
            layout_dir, float(os.environ.get("LAYOUT_TABLE_THRESHOLD") or 0.05))
        _log(f"детекция макета: {os.environ.get('LAYOUT_MODEL_NAME','PP-DocLayoutV2')}"
             f" на ONNX Runtime, порог таблиц "
             f"{os.environ.get('LAYOUT_TABLE_THRESHOLD') or 0.05}, веса из {layout_dir}")
    elif layout_dir:
        _log(f"в {layout_dir} нет inference.onnx — детекция остаётся на paddle")
    # Умолчание paddlex выбрасывает из markdown семь меток, и среди них
    # `header` — а в книгах это не только колонтитул, но и название главы.
    # Замер на 25 страницах: в `header` попало семь блоков, и все семь —
    # настоящий текст ("Chapter 28", "THE VERTICAL MILLING MACHINE", ...),
    # ни одного колонтитула.  Их отбрасывание — потеря содержания.
    #
    # Колонтитулы всё равно надо убирать, но по факту, а не по метке: они
    # повторяются из страницы в страницу, и это видно после прогона
    # (см. _strip_running_headers).  `number` остаётся в списке — это
    # номера страниц, все 24 из 25.
    # Конвейер вместо последовательности.  Замер: 25 страниц за 98 с при
    # 409 запросах к vLLM (по одному на распознанный блок, 16 на страницу),
    # причём карта между ними простаивала — в статистике vLLM `Running: 0
    # reqs` и KV-кеш 0.0%.  Узкое место не карта, а то, что чтение страницы,
    # детекция макета и VLM шли строго по очереди.
    #
    # use_queues ставит между ними очереди и отдельные потоки, так что
    # детекция следующей страницы идёт, пока считается текущая.
    # Порог детекции таблиц — отдельной ручкой, потому что именно он решает
    # судьбу таблиц без линеек.  RT-DETR предлагает для одной области
    # несколько кандидатов с разными классами; на странице 307 книги три
    # одинаковых блока "RECOMMENDED STANDARDS" получили table 0.70, text 0.78
    # и text 0.61 — то есть таблица проиграла тексту по уверенности, а не
    # осталась незамеченной.  В PP-DocLayoutV2 table — класс 21.
    kwargs["use_queues"] = True
    if os.environ.get("PREFER_TABLES", "1") == "1":
        _prefer_tables_over_text()
        _log("таблица важнее текстовой рамки при перекрытии")
    if os.environ.get("MULTIVIEW", "1") == "1":
        _multiview_layout()
        _log("детекция макета в двенадцать взглядов")
    if os.environ.get("SPLIT_COLUMNS", "1") == "1":
        _split_cross_column_tables()
        _log("таблицы поперёк межколонника будут разрезаны")
    if os.environ.get("REASK", "1") == "1":
        _reask_text_as_table()
        _log("блоки text, похожие на таблицу, идут на переспрос")
    if os.environ.get("LOGPROBS", "1") == "1" and a.server:
        _capture_logprobs(thr=float(os.environ.get("LOGPROB_THR", "-1.0")))
        _log("вероятности токенов будут запрошены у vLLM")
    # `content` (страница оглавления) в этот список НЕ входит, хотя соблазн
    # был: на book-new блок вышел в 8200 знаков, из них 49.8% — точки выносок,
    # с обрывом на полуслове.  Но это замер на одной книге, а список бьёт по
    # всем: у книги с коротким оглавлением или без выносок блок прочитается
    # нормально, и выбрасывать его значит терять содержание из-за чужой беды.
    # Решение принимается позже и по факту — `structure.py` сравнивает число
    # записей в оглавлении с числом глав в книге и трогает блок только тогда,
    # когда он явно не дочитан.
    kwargs["markdown_ignore_labels"] = [
        "number", "header_image", "footer", "footer_image", "aside_text",
    ]

    if a.server:
        # Одного адреса мало: без backend пайплайн всё равно строит локальную
        # модель и падает на gpu:0, потому что paddle у нас CPU-сборки.
        # Переключатель — SubModules.VLRecognition.genai_config.backend,
        # снаружи это vl_rec_backend (см. paddleocr/_pipelines/paddleocr_vl.py).
        kwargs.update(vl_rec_backend="vllm-server",
                      vl_rec_server_url=a.server,
                      vl_rec_api_model_name=a.model)
        _log(f"VLM через сервис {a.server} (backend vllm-server)")
    else:
        _log(f"VLM в процессе, устройство {a.device}")

    if os.environ.get("PROBE") == "1" and a.server:
        _probe_hallucination(a.server, a.model, pdf)
        return 0

    t0 = time.time()
    try:
        pipeline = PaddleOCRVL(**kwargs)
    except TypeError:                    # старая сигнатура без device=
        kwargs.pop("device")
        _log("пайплайн не принимает device=, беру как есть")
        pipeline = PaddleOCRVL(**kwargs)
    _log(f"пайплайн готов за {time.time()-t0:.0f}с")

    t1 = time.time()
    pages, n = [], 0
    # Ненулевая температура — для опыта на самосогласованность: тот же кроп
    # читается несколько раз, и разошедшиеся ячейки помечаются как ненадёжные.
    # По умолчанию 0, то есть жадный разбор, как и был.
    pkw = {}
    # Текст внутри рисунков: буквенные выноски A/B на схемах, размерные
    # подписи.  По умолчанию paddlex их не читает вовсе — блок `image`
    # вырезается картинкой, и внутрь никто не заглядывает.  А в тексте рядом
    # сказано «кнопка в точке A перемещается к B», и без выносок абзац
    # теряет смысл.  Сама картинка при этом сохраняется как была:
    # vis_image_labels в paddlex отдельный от image_labels.
    if os.environ.get("OCR_IN_IMAGES", "0") == "1":
        pkw["use_ocr_for_image_block"] = True
        _log("текст внутри рисунков будет прочитан")

    _temp = float(os.environ.get("VLM_TEMPERATURE", "0") or 0)
    if _temp > 0:
        pkw["temperature"] = _temp
        _log(f"температура VLM {_temp} — разбор будет невоспроизводимым нарочно")

    for res in pipeline.predict(pdf, **pkw):
        idx = offset + n
        n += 1
        pages.append(res)
        stem = f"{idx:04d}"
        try:
            res.save_to_markdown(save_path=os.path.join(pages_dir, stem + ".md"))
        except Exception as e:
            _log(f"  страница {idx}: markdown не сохранился: {e}")
        try:
            res.save_to_json(save_path=os.path.join(pages_dir, stem + ".json"))
        except Exception as e:
            _log(f"  страница {idx}: json не сохранился: {e}")

        # Отдав страницу на диск, отпускаем самое тяжёлое: отрисованную
        # страницу и её же копию из предобработки.  Список `pages` нужен
        # только для склейки таблиц через разрыв, а держал он всю книгу
        # целиком — на 539 страницах при 288 dpi это гигабайты на машине,
        # где 18 ГБ уже отданы vLLM.
        for key in ("layout_det_res", "doc_preprocessor_res"):
            try:
                sub = res[key]
                if isinstance(sub, dict):
                    sub.pop("input_img", None)
                elif hasattr(sub, "pop"):
                    sub.pop("input_img", None)
            except Exception:
                pass

        dt = time.time() - t1
        with open(os.path.join(out, "progress.json"), "w") as f:
            json.dump({"pages_done": idx + 1, "this_run": n,
                       "seconds": round(dt, 1),
                       "pages_per_sec": round(n / max(dt, 1e-6), 3),
                       "server": bool(a.server)}, f, indent=1)
        if n % 5 == 0 or n == 1:
            _log(f"  {idx+1} страниц, {n/max(dt,1e-6):.2f} стр/с")

    dt = time.time() - t1
    _log(f"посчитано {n} страниц за {dt:.0f}с ({n/max(dt,1e-6):.2f} стр/с)")

    # Склейка таблиц и абзацев через разрыв страницы — то, что для
    # pymupdf-конвейера писалось руками.
    #
    # ВАЖНО: `pages` содержит только страницы ЭТОГО прогона.  При возобновлении
    # склеивать по ним нельзя — получилась бы книга из одного хвоста, и молча.
    book_dir = os.path.join(out, "book")
    os.makedirs(book_dir, exist_ok=True)
    if offset:
        _log(f"прогон был возобновлён с {offset+1}-й страницы — "
             f"сшиваю книгу из файлов, без restructure_pages")
        _concat_pages(pages_dir, os.path.join(book_dir, "book.md"))
    else:
        try:
            joined = pipeline.restructure_pages(pages, merge_tables=True,
                                                concatenate_pages=True)
            _log("restructure_pages: таблицы склеены, страницы сшиты")
        except Exception as e:
            # Ловим шире: раньше сюда не попадали ни нехватка памяти, ни любая
            # другая беда внутри склейки, и прогон падал в самом конце, уже
            # посчитав всю книгу.
            _log(f"restructure_pages не отработал ({e}) — сшиваю из файлов")
            joined = None
        if joined is not None and not joined:
            # Пустой список, а не None: цикл ниже не делал ничего, book_dir
            # оставался пустым, а лог рапортовал «таблицы склеены».
            _log("restructure_pages вернул пусто — сшиваю из файлов")
            joined = None
        if joined is None:
            _concat_pages(pages_dir, os.path.join(book_dir, "book.md"))
        else:
            for res in joined:
                try:
                    res.save_to_markdown(save_path=book_dir)
                except Exception as e:
                    _log(f"  склейка: {e}")
            # paddlex называет файл по имени входного PDF, а мы заливаем его
            # как input.pdf — получался `input.md`, имя без смысла, да ещё и
            # второй книжный файл рядом с book.md.  Приводим к одному имени:
            # содержимое здесь лучше (таблицы склеены через разрыв страницы),
            # поэтому оно и становится book.md.
            for f in glob.glob(os.path.join(book_dir, "*.md")):
                if os.path.basename(f) != "book.md":
                    os.replace(f, os.path.join(book_dir, "book.md"))
                    _log(f"книга: {os.path.basename(f)} -> book.md")
                    break

    if _LOW:
        with open(os.path.join(out, "logprobs.json"), "w",
                  encoding="utf-8") as f:
            keep = list(_LOW.items())[:400]
            json.dump({"всего": len(_LOW), "сохранено": len(keep),
                       "места": dict(keep)}, f, ensure_ascii=False, indent=1)
        if len(_LOW) > 400:
            _log(f"в logprobs.json сохранены первые 400 мест из {len(_LOW)}")
        n_cell, n_span = _mark_uncertain(pages_dir, book_dir)
        _log(f"ответов с неуверенными местами {len(_LOW)}: "
             f"помечено ячеек {n_cell}, кусков прозы {n_span}")

    # Сканы режем из ПОЛНОЙ книги, а не из обрезка: при возобновлении `pdf`
    # подменён на срез, а page_index в старых json остались абсолютными, и
    # doc[page_index] вырезал бы кусок чужой страницы — молча, с правильным
    # именем файла.
    broken = _fix_broken_img_tags(pages_dir, book_dir)
    if broken:
        _log(f"переписано начисто тегов картинок в файлах: {broken}")

    linked, skipped = _link_table_crops(full_pdf, pages_dir, book_dir)
    if linked or skipped:
        _log(f"ссылок на сканы таблиц проставлено {linked}"
             + (f"; страниц пропущено из-за несовпадения счёта {skipped}"
                if skipped else ""))

    unwrapped = _unwrap_degenerate_tables(pages_dir, book_dir)
    orphans = _drop_orphan_crops(book_dir, pages_dir, book_dir)
    if orphans:
        _log(f"сканов таблиц без ссылки удалено {orphans}")
    if unwrapped:
        _log(f"переспрос не подтвердился, развёрнуто обратно в текст: {unwrapped}")

    dropped = _strip_running_headers(pages_dir, pages_dir, book_dir)
    if dropped:
        _log(f"убраны колонтитулы ({len(dropped)}): "
             + "; ".join(x.replace(chr(10), " ")[:40] for x in dropped[:5]))

    with open(os.path.join(out, "run.json"), "w") as f:
        json.dump({"pages": offset + n, "seconds": round(dt, 1),
                   "pages_per_sec": round(n / max(dt, 1e-6), 3),
                   "server": bool(a.server), "model": a.model,
                   "device": a.device}, f, indent=1)
    _log(f"готово: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
