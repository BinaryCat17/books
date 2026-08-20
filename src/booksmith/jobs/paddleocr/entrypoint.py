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
                vkw = dict(kw, layout_merge_bboxes_mode="union", layout_nms=False)
                for view, back in _views(img):
                    for r in orig(self, [view], **vkw):
                        for b in r["boxes"]:
                            if b["label"] != "table" or b["score"] < thr:
                                continue
                            c = back(b["coordinate"])
                            c = [max(0, min(w, c[0])), max(0, min(h, c[1])),
                                 max(0, min(w, c[2])), max(0, min(h, c[3]))]
                            if c[2] - c[0] < 40 or c[3] - c[1] < 25:
                                continue
                            extra.append({"cls_id": b["cls_id"], "label": "table",
                                          "score": b["score"], "coordinate": c})
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
                _log(f"ворота переспроса пропущены: {exc}")
                break
        if n:
            _log(f"переспрос: блоков text отправлено как таблицы {n}")
        return out

    _C.__call__ = patched


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
            dst = re.sub(r"<table\b.*?</table>", one, src, flags=re.I | re.S)
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

    def suspicious(txt):
        plain = html.unescape(tag_re.sub("", txt)).strip()
        if not plain:
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
            out = cell_re.sub(cell, src_md)

            # Проза: заворачиваем сам сомнительный кусок, но не трогаем то,
            # что уже внутри таблицы — там пометка своя, на всю ячейку.
            safe = [(m.start(), m.end()) for m in table_re.finditer(out)]
            edits = []
            for resp, spans in _LOW.items():
                base = out.find(resp)
                if base < 0:
                    continue
                if any(a <= base < b for a, b in safe):
                    continue
                for a, b, _ in spans:
                    edits.append((base + a, base + b))
            for a, b in sorted(set(edits), reverse=True):
                if out[a:b].strip():
                    out = (out[:a] + f'<mark title="модель не уверена">'
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
            d = json.load(open(f))
        except Exception:
            continue
        for r in d.get("parsing_res_list") or []:
            if r.get("block_label") == "header":
                t = (r.get("block_content") or "").strip()
                if t:
                    seen[t] += 1

    limit = max(3, npages // 3)
    running = {t for t, c in seen.items() if c >= limit}
    if not running:
        return []

    # Блок может занимать несколько строк — сравниваем построчно.
    lines = {ln.strip() for t in running for ln in t.splitlines() if ln.strip()}
    for target in targets:
        for f in glob.glob(os.path.join(target, "*.md")):
            try:
                src = open(f).read().splitlines(keepends=True)
            except Exception:
                continue
            kept = [ln for ln in src if ln.strip() not in lines]
            if len(kept) != len(src):
                open(f, "w").writelines(kept)
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
    offset = 0
    if a.resume:
        done = _done_pages(pages_dir)
        if done:
            first = max(done)          # последнюю пересчитываем: могла оборваться
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
    if os.environ.get("REASK", "1") == "1":
        _reask_text_as_table()
        _log("блоки text, похожие на таблицу, идут на переспрос")
    if os.environ.get("LOGPROBS", "1") == "1" and a.server:
        _capture_logprobs(thr=float(os.environ.get("LOGPROB_THR", "-1.0")))
        _log("вероятности токенов будут запрошены у vLLM")
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
        except (AttributeError, TypeError) as e:
            _log(f"restructure_pages недоступен ({e}) — сшиваю из файлов")
            joined = None
        if joined is None:
            _concat_pages(pages_dir, os.path.join(book_dir, "book.md"))
        else:
            for res in joined:
                try:
                    res.save_to_markdown(save_path=book_dir)
                except Exception as e:
                    _log(f"  склейка: {e}")

    if _LOW:
        with open(os.path.join(out, "logprobs.json"), "w") as f:
            json.dump({k: v for k, v in list(_LOW.items())[:400]}, f,
                      ensure_ascii=False, indent=1)
        n_cell, n_span = _mark_uncertain(pages_dir, book_dir)
        _log(f"ответов с неуверенными местами {len(_LOW)}: "
             f"помечено ячеек {n_cell}, кусков прозы {n_span}")

    unwrapped = _unwrap_degenerate_tables(pages_dir, book_dir)
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
