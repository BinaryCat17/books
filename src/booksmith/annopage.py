"""AnnoPage: ЗОЛОТОЙ СТЕНД из настоящих страниц с истиной от библиотекарей.

Чего не мог дать синтетический стенд. Он нарисован шрифтом, а не отпечатан
высокой печатью, и про чтение знаков не говорит ничего — это записано в его
собственной шапке. AnnoPage — 7550 страниц исторических документов 1485 года
и позже, преимущественно чешских и немецких, размеченных экспертами-
библиотекарями по чешской методике обработки изобразительных документов.
Zenodo, DOI 10.5281/zenodo.12788419, CC BY 4.0.

ЧТО ЗДЕСЬ РАЗМЕЧЕНО, А ЧТО НЕТ. Размечены ТОЛЬКО нетекстовые объекты, 25
категорий. Текстовых блоков в истине нет вовсе — значит по этому стенду
меряется локализация артефактов и ничего больше. Строка отчёта «текст и
служебное» на нём обязана говорить «нет данных», а не «ноль»: это разные нули.

ТРИ РАЗРЯДА КАТЕГОРИЙ, И ГРАНИЦА МЕЖДУ НИМИ — НАШЕ РЕШЕНИЕ, ОБЪЯВЛЕННОЕ ЯВНО.

* `ПРЯМО` — у нашей модели есть ярлык ровно про это. Только эти объекты
  входят в замер.
* `СПОРНО` — соответствие правдоподобно, но не однозначно (карта, реклама,
  ноты, рукописная пометка). Свести их к `image` значило бы решить за модель
  спорный случай и записать себе лишние находки.
* `НЕВЫРАЗИМО` — книжный декор: буквица, виньетка, фриз, экслибрис, шмуцтитул,
  наборное украшение. В словаре PP-DocLayoutV2 нет ничего про это, и промах
  тут был бы промахом СЛОВАРЯ, а не модели.

Спорное и невыразимое не выбрасывается молча: их число печатается рядом с
итогом, чтобы «нашли 40%» нельзя было прочесть как «40% страницы разобрано».
"""
import hashlib
import json
import os

# --- прямое соответствие: только это идёт в замер -------------------------
DIRECT = {
    "Table": "table",
    "Graph": "chart",
    "Diagram": "chart",
    "Image": "image",
    "Photograph": "image",
    "Geometric drawing": "image",
    "Other technical drawing": "image",
    "Floor plan": "image",
    "Mathematical expression and equation": "display_formula",
    "Chemical formula and equation": "display_formula",
    "Stamp": "seal",
}
# --- соответствие правдоподобно, но спорно: в замер НЕ идёт ---------------
DOUBTFUL = ("Map", "Advertisement", "Musical notation", "Handwritten note",
            "Caricature and comics", "Barcode and QR code")
# --- нашей моделью невыразимо вовсе ---------------------------------------
INEXPRESSIBLE = ("Initial", "Vignette", "Frieze", "Exlibris", "Signet",
                 "Decorative inscription", "Other book decor",
                 "Symbol, logo, coat of arms")


class AnnoPageError(RuntimeError):
    pass


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _classes(root):
    p = os.path.join(root, "classes.txt")
    if not os.path.exists(p):
        raise AnnoPageError(f"нет {p}: это не корень AnnoPage")
    names = [l.strip() for l in open(p, encoding="utf-8") if l.strip()]
    known = set(DIRECT) | set(DOUBTFUL) | set(INEXPRESSIBLE)
    unknown = [n for n in names if n not in known]
    if unknown:
        raise AnnoPageError(
            f"в датасете есть категории, о которых мы не высказались: "
            f"{unknown}. Умолчания нет нарочно — молчаливое «невыразимо» "
            f"превратилось бы в вечный недобор без объяснения.")
    return names


def build(root: str, out_dir: str, split: str = "test", limit: int = 0,
          truth_only: bool = False, log=print) -> dict:
    """Сложить книгу-стенд из AnnoPage: PDF плюс истина в нашем формате.

    Страница получает размер, при котором рендер на PAGE_DPI=144 отдаёт РОВНО
    исходный растр: тогда координаты истины и рамки модели живут в одной
    системе, и приводить ничего не надо.
    """
    import cv2
    import pymupdf

    names = _classes(root)
    ldir = os.path.join(root, "labels", split)
    idir = os.path.join(root, "images", split)
    if not (os.path.isdir(ldir) and os.path.isdir(idir)):
        raise AnnoPageError(f"нет {ldir} или {idir}")

    stems = sorted(f[:-4] for f in os.listdir(ldir) if f.endswith(".txt"))
    os.makedirs(out_dir, exist_ok=True)
    tdir = os.path.join(out_dir, "truth")
    os.makedirs(tdir, exist_ok=True)
    for old in os.listdir(tdir):
        os.unlink(os.path.join(tdir, old))

    # 1860 разметок ссылаются на страницы ЧУЖИХ датасетов, которых в архиве
    # нет. Это не потеря, а объявленное свойство ВЫБОРКИ, поэтому и считается
    # оно до главного цикла и по всей выборке. Внутри цикла счёт обрывался
    # вместе с ним на --limit: `--split train --limit 5` печатал «без картинки
    # 178» при честных 1860, а на выборке, где пропуски идут дальше предела, —
    # ровный 0, то есть «не дошли» под видом «нет пропусков». Предпроход
    # дешёвый: 0.1 с на 6950 разметок, только os.path.exists, растры не
    # читаются.
    images = {}
    for stem in stems:
        for ext in (".jpg", ".jpeg", ".png", ".tif", ".tiff"):
            p = os.path.join(idir, stem + ext)
            if os.path.exists(p):
                images[stem] = p
                break
    skipped_no_image = len(stems) - len(images)

    doc = pymupdf.open()
    pages, counts = [], {"прямо": {}, "спорно": {}, "невыразимо": {}}
    used = 0
    for stem in stems:
        img_path = images.get(stem)
        if img_path is None:
            continue
        if limit and used >= limit:
            break
        im = cv2.imread(img_path)
        if im is None:
            raise AnnoPageError(f"не читается {img_path}")
        h, w = im.shape[:2]

        blocks, outside = [], []
        drop = {"спорно": 0, "невыразимо": 0}
        with open(os.path.join(ldir, stem + ".txt"), encoding="utf-8") as f:
            for line in f:
                q = line.split()
                if len(q) < 5:
                    continue
                cat = names[int(q[0])]
                cx, cy, bw, bh = (float(v) for v in q[1:5])
                box = [(cx - bw / 2) * w, (cy - bh / 2) * h,
                       (cx + bw / 2) * w, (cy + bh / 2) * h]
                if cat in DIRECT:
                    lab = DIRECT[cat]
                    counts["прямо"][cat] = counts["прямо"].get(cat, 0) + 1
                    blocks.append({"block_id": len(blocks),
                                   "box": [round(v, 1) for v in box],
                                   "label": lab, "score": None,
                                   "order": len(blocks), "content": None,
                                   "kind": "none", "исходная категория": cat})
                else:
                    kind = "спорно" if cat in DOUBTFUL else "невыразимо"
                    counts[kind][cat] = counts[kind].get(cat, 0) + 1
                    drop[kind] += 1
                    # Рамка ОСТАЁТСЯ в истине отдельным списком. Выбросив её
                    # совсем, мы объявляли бы лишней всякую рамку модели,
                    # попавшую на рекламу или буквицу, — а модель там не
                    # виновата: это мы не смогли выразить категорию.
                    outside.append({"box": [round(v, 1) for v in box],
                                    "категория": cat, "разряд": kind})

        if not truth_only:
            page = doc.new_page(width=w * 0.5, height=h * 0.5)  # 144dpi -> w,h
            with open(img_path, "rb") as f:
                page.insert_image(page.rect, stream=f.read())
        with open(os.path.join(tdir, f"{used:04d}.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"index": used, "width": w, "height": h, "dpi": 144.0,
                       "blocks": blocks, "raw": None,
                       "meta": {"случай": stem[:8], "книга": "annopage",
                                "файл": os.path.basename(img_path),
                                "объектов вне замера": drop,
                                "вне замера": outside,
                                # Текстовых блоков в истине НЕТ ВОВСЕ.
                                "текст размечен": False,
                                # И ПОРЯДКА ЧТЕНИЯ ТОЖЕ НЕТ. `order` ниже —
                                # это номер строки в файле разметки, а он
                                # сгруппирован по классам: на стр. 51 порядок
                                # 0,1,2,3 стоит при y0 = 1560, 3004, 673,
                                # 4129. Сверять с ним чей-либо порядок чтения
                                # значит мерить чужую величину; метрика этот
                                # признак читает и печатает прочерк.
                                "порядок размечен": False}}, f,
                      ensure_ascii=False)
        pages.append({"страница": used, "размер": [w, h], "файл": stem,
                      "блоков": len(blocks), "вне замера": drop})
        used += 1
        if used % 50 == 0:
            log(f"  {used} страниц")

    if not pages:
        raise AnnoPageError("ни одной страницы не собрано")
    pdf = os.path.join(out_dir, "annopage.pdf")
    if truth_only:
        doc.close()
        if not os.path.exists(pdf):
            raise AnnoPageError(f"нет {pdf}: с --truth-only он должен уже быть")
        # Сверяем ЧИСЛО И РАЗМЕР страниц: переписать истину под чужой pdf —
        # ровно та беда, от которой в `books score` стоит проверка sha256, и
        # тут она обходилась бы с чёрного хода.
        import pymupdf as _pm
        chk = _pm.open(pdf)
        if chk.page_count != len(pages):
            n = chk.page_count
            chk.close()
            raise AnnoPageError(
                f"в {pdf} страниц {n}, а истина переписана на {len(pages)}: "
                f"это разные выборки.")
        for rec in pages:
            r = chk[rec["страница"]].rect
            w, h = rec["размер"]
            if abs(r.width - w * 0.5) > 0.6 or abs(r.height - h * 0.5) > 0.6:
                chk.close()
                raise AnnoPageError(
                    f"стр. {rec['страница']}: лист {r.width:.0f}x{r.height:.0f} "
                    f"пт не соответствует растру {w}x{h} — истина не про этот "
                    f"pdf.")
        chk.close()
    else:
        doc.save(pdf, garbage=3, deflate=True)
        doc.close()

    n_direct = sum(counts["прямо"].values())
    man = {"книга": "annopage",
           "о книге": "AnnoPage: исторические страницы 1485 г. и позже, "
                      "разметка библиотекарями, только НЕТЕКСТОВЫЕ объекты",
           "источник": "Zenodo 10.5281/zenodo.12788419, CC BY 4.0",
           "выборка": split, "страниц": len(pages),
           "текст размечен": False,
           "объектов в замере": n_direct,
           "объектов вне замера": {
               "спорно": sum(counts["спорно"].values()),
               "невыразимо": sum(counts["невыразимо"].values())},
           "по категориям": counts,
           "свод категорий": DIRECT,
           "разметок без картинки": skipped_no_image,
           "pdf": os.path.basename(pdf), "sha256 pdf": _sha256(pdf)}
    with open(os.path.join(out_dir, "manifest.json"), "w",
              encoding="utf-8") as f:
        json.dump(man, f, ensure_ascii=False, indent=1)
    log(f"страниц {len(pages)}, в замер идёт {n_direct} объектов; "
        f"вне замера: спорных {man['объектов вне замера']['спорно']}, "
        f"невыразимых {man['объектов вне замера']['невыразимо']}")
    log(f"разметок без картинки пропущено {skipped_no_image}")
    log(f"{pdf} ({os.path.getsize(pdf)/1e6:.0f} МБ), истина в {tdir}")
    return man
