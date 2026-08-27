"""Вырезать артефакт из страницы по рамке модели.

Режем ИЗ PDF, а не из растра, которым кормили детектор. Причина в числе:
детекция идёт при `PAGE_DPI` = 144, и плотная таблица без линеек даёт там
шесть-семь точек на высоту знака — второй уровень на такой вырезке провалится,
а спишут это на него. Из PDF можно взять любую резкость, не переспрашивая
детектор.

ДВЕ РУЧКИ, И ОБЕ ОБЪЯВЛЕНЫ В РЕЕСТРЕ.

`CROP_DPI` — резкость вырезки. Умолчание равно `PAGE_DPI`, то есть «как
видела модель»: любое другое число было бы выбрано нами, а не замерено. Назначит
его стенд.

`CROP_MARGIN` — поле вокруг рамки, в долях её размера. Умолчание 0, и это
не лень: пайплайн режет ровно по рамке (`layout_unclip_ratio` = [1.0, 1.0]),
а всякое ненулевое поле есть правка рамки модели — то самое, что правила
запрещают. Ноль здесь ЗНАЧЕНИЕ: мы не трогаем рамку. Если стенд покажет, что
поле нужно, оно вернётся числом и с замером.
"""
import os

from ..run import knobs


def params() -> dict:
    """Действующие величины вырезки. Уезжают в слепок целиком."""
    return {"dpi": float(knobs.knob("CROP_DPI") or knobs.knob("PAGE_DPI")),
            "поле": float(knobs.knob("CROP_MARGIN"))}


def box_to_points(box, page_dpi: float):
    """Рамка из пикселей растра при `page_dpi` — в пункты PDF (72 на дюйм)."""
    k = 72.0 / page_dpi
    return tuple(v * k for v in box)


def cut(doc, page_index: int, box, page_dpi: float, dst: str,
        dpi: float | None = None, margin: float | None = None) -> dict:
    """Вырезать рамку в файл. Возвращает, ЧТО именно вырезано.

    Возвращает не «готово», а величины: итоговый размер в точках, применённое
    поле, срез по краю страницы. Без них нельзя отличить «вырезали таблицу» от
    «вырезали её левую половину, потому что рамка вылезла за лист».
    """
    import pymupdf

    p = params()
    dpi = p["dpi"] if dpi is None else dpi
    margin = p["поле"] if margin is None else margin

    page = doc[page_index]
    x0, y0, x1, y1 = box_to_points(box, page_dpi)
    w, h = x1 - x0, y1 - y0
    if margin:
        x0, y0, x1, y1 = (x0 - w * margin, y0 - h * margin,
                          x1 + w * margin, y1 + h * margin)
    want = pymupdf.Rect(x0, y0, x1, y1)
    # Пересечение с листом. Рамка модели может выйти за край — это её дефект,
    # и он должен быть ВИДЕН числом, а не молча обрезан.
    #
    # Дефект модели и последствие НАШЕЙ ручки — разные числа. Прежняя редакция
    # мерила выход за лист уже РАСШИРЕННОЙ на CROP_MARGIN рамки, и стоило
    # назначить поле, как рамка, целиком лежащая внутри листа, объявлялась
    # срезанной — а к подписи блока в книге дописывалось «рамка вышла за лист».
    # Ложное обвинение модели тем чаще, чем крупнее поле.
    raw = pymupdf.Rect(*box_to_points(box, page_dpi))
    clipped = (raw & page.rect) != raw
    clip = want & page.rect
    margin_clipped = (abs(clip.width - want.width) > 0.01
                      or abs(clip.height - want.height) > 0.01)
    if clip.is_empty:
        raise ValueError(
            f"рамка {tuple(round(v,1) for v in box)} на стр. {page_index} "
            f"не пересекается с листом {tuple(round(v,1) for v in page.rect)}")

    os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)
    pix = page.get_pixmap(dpi=int(dpi), clip=clip)
    pix.save(dst)
    return {"файл": os.path.basename(dst), "dpi": int(dpi), "поле": margin,
            "ширина": pix.width, "высота": pix.height,
            "срезано листом": clipped,
            "поле срезано листом": margin_clipped,
            "рамка в пунктах": [round(v, 2) for v in (clip.x0, clip.y0,
                                                      clip.x1, clip.y1)]}
