"""AnnoPage: ЗОЛОТОЙ СТЕНД из настоящих страниц с истиной от библиотекарей.

Чего не мог дать синтетический стенд. Он нарисован шрифтом, а не отпечатан
высокой печатью, и про чтение знаков не говорит ничего — это записано в его
собственной шапке. AnnoPage — **7550 файлов разметки** к **5690**
опубликованным страницам исторических документов, размеченным экспертами по
25 нетекстовым категориям. Здесь стояло «7550 страниц», и это неверно:
разница в 1860 — разметки, ссылающиеся на страницы ЧУЖИХ датасетов, которых в
архиве нет (ровно столько строк в `images.txt`), и они же дают счётчик
«разметок без картинки». Zenodo, DOI 10.5281/zenodo.12788419, CC BY 4.0.

ЧЕГО ПРО ЭТОТ АРХИВ СКАЗАТЬ НЕЧЕМ, И ЭТО НЕ ТО ЖЕ, ЧТО «НЕВЕРНО». Здесь
стояло ещё «1485 года и позже, преимущественно чешских и немецких, по чешской
методике обработки изобразительных документов». В самом архиве этого нет:
`README.md` говорит только «mostly from czech written documents», ни даты, ни
немецких, ни методики, ни DOI внутри ZIP нет вовсе (перечислен исчерпывающе:
13252 записи). Сведения могли быть взяты со страницы Zenodo или из статьи
авторов — проверить нечем, и потому они убраны отсюда, а не объявлены
выдумкой.

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
import shutil

from .run import knobs

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


def _yaml_names(root):
    """Карта «индекс -> имя» из `dataset.yaml`. `None`, если файла нет.

    Разбирается пятью строками, а не библиотекой: нужен один плоский раздел
    `names:` вида «  0: Имя», и тащить `yaml` в модуль ради него незачем.
    Двоеточие делим ПЕРВОЕ — в именах категорий бывают запятые, и когда-нибудь
    может встретиться двоеточие.
    """
    p = os.path.join(root, "dataset.yaml")
    if not os.path.exists(p):
        return None
    out, inside = {}, False
    for line in open(p, encoding="utf-8"):
        if line.startswith("names:"):
            inside = True
            continue
        if inside:
            if line.strip() and not line[0].isspace():
                break                          # раздел кончился
            if ":" not in line:
                continue
            k, v = line.split(":", 1)
            k = k.strip()
            if k.isdigit():
                out[int(k)] = v.strip()
    return out or None


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
    # ПОРЯДОК СТРОК СВЕРЯЕТСЯ СО ВТОРЫМ ИСТОЧНИКОМ, а не принимается на веру.
    # Метка в разметке — это ИНДЕКС, имя ему даёт строка N файла `classes.txt`,
    # и до сих пор проверялось только МНОЖЕСТВО имён. Цена промера: поменять в
    # `classes.txt` местами `Table` и `Vignette` — сборка проходит молча, а в
    # замере объектов становится 1121 вместо 1232 и таблиц 13 вместо 124. То
    # есть весь золотой стенд уезжает, и ни одна проверка этого не говорит.
    # Второй источник лежит в том же архиве и до сих пор не читался ни разу.
    # (Сегодня они СОВПАДАЮТ, 25 из 25, — истина стенда цела; сторож ставится
    # не по следам аварии, а чтобы её не было.)
    ymap = _yaml_names(root)
    if ymap is not None:
        wrong = [(i, n, ymap.get(i)) for i, n in enumerate(names)
                 if ymap.get(i) != n]
        if wrong or len(ymap) != len(names):
            raise AnnoPageError(
                f"classes.txt и dataset.yaml расходятся: имён {len(names)} "
                f"против {len(ymap)}, первое расхождение "
                f"{wrong[0] if wrong else '—'} (индекс, classes.txt, "
                f"dataset.yaml). Метка в разметке — это ИНДЕКС, и при "
                f"расхождении вся истина стенда собралась бы под чужими "
                f"ярлыками молча.")
    return names


def build(root: str, out_dir: str, split: str = "test", limit: int = 0,
          truth_only: bool = False, log=print) -> dict:
    """Сложить книгу-стенд из AnnoPage: PDF плюс истина в нашем формате.

    Страница получает размер, при котором рендер на `PAGE_DPI` отдаёт РОВНО
    исходный растр: тогда координаты истины и рамки модели живут в одной
    системе, и приводить ничего не надо. Ручка читается, а не подразумевается
    — здесь стояло «на PAGE_DPI=144», и число было зашито в код рядом.
    """
    import cv2
    import pymupdf

    # МАСШТАБ БЕРЁТСЯ ИЗ ОБЪЯВЛЕННОЙ РУЧКИ, а не из зашитого 0.5. Смысл его
    # один: лист должен быть такого размера в пунктах, чтобы рендер при
    # `PAGE_DPI` отдал РОВНО исходный растр — тогда координаты истины и рамки
    # модели живут в одной системе и приводить ничего не надо. Прежде здесь
    # стояло 0.5 = 72/144, верное ровно при умолчании: подними кто-нибудь
    # `PAGE_DPI` до 300 — и стенд собрался бы про растр вчетверо мельче
    # объявленного, а истина продолжала бы писать «dpi: 144.0». Ловила это
    # сверка размеров в `metrics`, то есть ЧУЖОЙ файл и не всегда; сам
    # сборщик молчал. Ручку читаем через реестр, иначе прогон не попадёт в
    # слепок.
    dpi = float(knobs.knob("PAGE_DPI"))
    if dpi <= 0:
        raise AnnoPageError(f"PAGE_DPI = {dpi}: масштаб листа неположителен")
    scale = 72.0 / dpi

    names = _classes(root)
    ldir = os.path.join(root, "labels", split)
    idir = os.path.join(root, "images", split)
    if not (os.path.isdir(ldir) and os.path.isdir(idir)):
        raise AnnoPageError(f"нет {ldir} или {idir}")

    stems = sorted(f[:-4] for f in os.listdir(ldir) if f.endswith(".txt"))
    os.makedirs(out_dir, exist_ok=True)
    tdir = os.path.join(out_dir, "truth")
    # ИСТИНА ПИШЕТСЯ В СТОРОНУ И ПОДМЕНЯЕТСЯ ТОЛЬКО ПОСЛЕ СТОРОЖЕЙ. Прежде
    # `truth/` чистился ЗДЕСЬ, а сторожа `--truth-only` (число страниц, размер
    # листа) стояли на сотню строк ниже, после главного цикла. То есть сторож
    # говорил правду и говорил ПОЗДНО: опыт на копии стенда — `build(...,
    # limit=5, truth_only=True)` уронил сборку словами «страниц 600, а истина
    # переписана на 5: это разные выборки», и к этому мигу от 600 годных
    # файлов истины оставалось ПЯТЬ. 595 уничтожены отказом, который затевался
    # ради их защиты. Восстановить их можно было только `git checkout`, и
    # только потому, что этот стенд отслеживается; в свежем каталоге —
    # нечем.
    work = tdir + ".новая"
    if os.path.isdir(work):
        shutil.rmtree(work)
    os.makedirs(work)

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
    pages, counts = [], {"direct": {}, "doubtful": {}, "inexpressible": {}}
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
        drop = {"doubtful": 0, "inexpressible": 0}
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
                    counts["direct"][cat] = counts["direct"].get(cat, 0) + 1
                    blocks.append({"block_id": len(blocks),
                                   "box": [round(v, 1) for v in box],
                                   "label": lab, "score": None,
                                   "order": len(blocks), "content": None,
                                   "kind": "none", "source_category": cat})
                else:
                    kind = "doubtful" if cat in DOUBTFUL else "inexpressible"
                    counts[kind][cat] = counts[kind].get(cat, 0) + 1
                    drop[kind] += 1
                    # Рамка ОСТАЁТСЯ в истине отдельным списком. Выбросив её
                    # совсем, мы объявляли бы лишней всякую рамку модели,
                    # попавшую на рекламу или буквицу, — а модель там не
                    # виновата: это мы не смогли выразить категорию.
                    outside.append({"box": [round(v, 1) for v in box],
                                    "category": cat, "bucket": kind})

        if not truth_only:
            page = doc.new_page(width=w * scale, height=h * scale)
            with open(img_path, "rb") as f:
                page.insert_image(page.rect, stream=f.read())
        with open(os.path.join(work, f"{used:04d}.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"index": used, "width": w, "height": h, "dpi": dpi,
                       "blocks": blocks, "raw": None,
                       "meta": {"case": stem[:8], "book": "annopage",
                                "file": os.path.basename(img_path),
                                "objects_out_of_scope": drop,
                                "out_of_scope": outside,
                                # Текстовых блоков в истине НЕТ ВОВСЕ.
                                "text_marked": False,
                                # И ПОРЯДКА ЧТЕНИЯ ТОЖЕ НЕТ. `order` ниже —
                                # это номер строки в файле разметки, а он
                                # сгруппирован по классам: на стр. 51 порядок
                                # 0,1,2,3 стоит при y0 = 1560, 3004, 673,
                                # 4129. Сверять с ним чей-либо порядок чтения
                                # значит мерить чужую величину; метрика этот
                                # признак читает и печатает прочерк.
                                "order_marked": False}}, f,
                      ensure_ascii=False)
        pages.append({"page": used, "size": [w, h], "file": stem,
                      "block_count": len(blocks), "out_of_scope": drop})
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
            r = chk[rec["page"]].rect
            w, h = rec["size"]
            if abs(r.width - w * scale) > 0.6 or abs(r.height - h * scale) > 0.6:
                chk.close()
                raise AnnoPageError(
                    f"стр. {rec['page']}: лист {r.width:.0f}x{r.height:.0f} "
                    f"пт не соответствует растру {w}x{h} — истина не про этот "
                    f"pdf.")
        chk.close()
    else:
        doc.save(pdf, garbage=3, deflate=True)
        doc.close()

    # Сторожа позади — можно подменять. Порядок: старое в сторону, новое на
    # место, старое снести. Оборвись работа посередине, на месте останется
    # либо прежняя истина, либо новая, но не пустота.
    keep = tdir + ".прежняя"
    if os.path.isdir(keep):
        shutil.rmtree(keep)
    if os.path.isdir(tdir):
        os.rename(tdir, keep)
    os.rename(work, tdir)
    if os.path.isdir(keep):
        shutil.rmtree(keep)

    n_direct = sum(counts["direct"].values())
    man = {"book": "annopage",
           "about": "AnnoPage: 7550 разметок к 5690 страницам, "
                      "разметка библиотекарями, только НЕТЕКСТОВЫЕ объекты",
           "origin": "Zenodo 10.5281/zenodo.12788419, CC BY 4.0",
           "split": split, "page_count": len(pages), "PAGE_DPI": dpi,
           "text_marked": False,
           "objects_in_scope": n_direct,
           "objects_out_of_scope": {
               "doubtful": sum(counts["doubtful"].values()),
               "inexpressible": sum(counts["inexpressible"].values())},
           "by_category": counts,
           "category_map": DIRECT,
           "annotations_without_image": skipped_no_image,
           "pdf": os.path.basename(pdf), "sha256 pdf": _sha256(pdf)}
    with open(os.path.join(out_dir, "manifest.json"), "w",
              encoding="utf-8") as f:
        json.dump(man, f, ensure_ascii=False, indent=1)
    log(f"страниц {len(pages)}, в замер идёт {n_direct} объектов; "
        f"вне замера: спорных {man['objects_out_of_scope']['doubtful']}, "
        f"невыразимых {man['objects_out_of_scope']['inexpressible']}")
    log(f"разметок без картинки пропущено {skipped_no_image}")
    log(f"{pdf} ({os.path.getsize(pdf)/1e6:.0f} МБ), истина в {tdir}")
    return man
