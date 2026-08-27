"""`books overlay` — посмотреть глазами на то, что померено числом.

Зачем отдельная команда. Стенд, который проверяет себя числами, но которого
никто не видел, — не прибор. За одну сессию этот стенд соврал рамками шесть
раз, и ни разу число не выглядело больным: пустые рамки текста, половина
разворота за краем листа, «чертёж» из сорока семи параллельных линий, рамка
формулы шире формулы, строка вместо абзаца, одна рамка на колонтитул из двух.
Все шесть видно на листе и ни одной — в отчёте.

ПОКАЗЫВАЕМ РАСХОЖДЕНИЯ, А НЕ ВСЁ ПОДРЯД. Первая редакция рисовала обе
разметки целиком: на странице, где модель права, выходило две сотни почти
совпадающих прямоугольников с двумя подписями над каждым — и лист переставал
читаться ровно там, где читать было нечего. Теперь совпавшая пара рисуется
одной тонкой серой рамкой без подписи, а криком выделено только то, что
разошлось: чего модель не нашла и что она нашла лишнего. На хорошей странице
лист почти чист, на плохой видно ровно беду.

ЛЕГЕНДЫ НЕТ. Врисованная в угол, она ложилась поверх первых блоков страницы;
отдельным листом — лишний лист, который никто не смотрит. Цвета говорят сами:
серое тонкое — совпало, красное толстое — не нашла, оранжевый пунктир —
лишняя. Подпись стоит только там, где есть что сказать.

ПУНКТИР ЗАДАЁТСЯ СТРОКОЙ, а не кортежем. Первая редакция передавала
`dashes=(0, 3)`; pymupdf ждёт строку вида `"[3 3] 0"` и молча рисовал
СПЛОШНУЮ — то есть обе разметки выглядели одинаково, и отличить их было
нельзя вообще ничем.
"""
import json
import os

import pymupdf

# Шрифт подписей. Встроенный `helv` кириллицы не знает, и подписи рисовались
# пустотой: по какой из двух разметок рамка — было не отличить.
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

СОВПАЛО = (0.55, 0.55, 0.55)      # серым и тонко: смотреть тут не на что
НЕ_НАШЛА = (0.85, 0.10, 0.10)     # красным: есть в истине, нет у модели
ЛИШНЯЯ = (0.95, 0.55, 0.00)       # оранжевым: есть у модели, нет в истине
ОДНА = (0.15, 0.35, 0.85)         # синим: разметка одна, сравнивать не с чем


class OverlayError(RuntimeError):
    pass


def _sha256(path):
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _same_book(pdf: str, marks) -> str:
    """Про тот ли PDF разметка. Без сверки чужая истина ложится молча и
    выглядит бедой модели — а это беда каталога."""
    mine = _sha256(pdf)
    said = []
    for d, tag in marks:
        up = os.path.dirname(d.rstrip("/"))
        for name, path_in in (("manifest.json", ("sha256 pdf",)),
                              ("run.json", ("исходник", "sha256"))):
            path = os.path.join(up, name)
            if not os.path.exists(path):
                continue
            with open(path, encoding="utf-8") as f:
                j = json.load(f)
            for k in path_in:
                j = (j or {}).get(k) if isinstance(j, dict) else None
            if not j:
                continue
            if j != mine:
                raise OverlayError(
                    f"разметка «{tag}» ({d}) про ДРУГУЮ книгу: в её слепке "
                    f"sha256 {j[:12]}, а у {pdf} — {mine[:12]}. Нарисованные "
                    f"рамки выглядели бы дефектом модели.")
            said.append(tag)
    return (f"sha256 сверен для {', '.join(said)}" if said
            else "sha256 не сверен: слепка рядом с разметкой нет")


def _pages(d: str) -> dict:
    if not os.path.isdir(d):
        raise OverlayError(f"нет каталога разметки {d}")
    out = {}
    for name in sorted(os.listdir(d)):
        if not name.endswith(".json") or name == "run.json":
            continue
        with open(os.path.join(d, name), encoding="utf-8") as f:
            p = json.load(f)
        if "blocks" not in p or "index" not in p:
            raise OverlayError(f"{name}: не похоже на страницу разметки")
        out[int(p["index"])] = p
    if not out:
        raise OverlayError(f"в {d} нет ни одной страницы разметки")
    return out


def _pair(truth, model):
    """Сопоставить рамки одной страницы. Возвращает (пары, лишние_истины,
    лишние_модели). Совпадение — то же, чем меряет `books score`: иначе лист
    показывал бы одно, а число говорило другое."""
    from .metrics import matches, iou
    used, pairs, lost = set(), [], []
    for b in sorted(truth, key=lambda z: -(z["box"][2] - z["box"][0])
                    * (z["box"][3] - z["box"][1])):
        cand = [(iou(b["box"], x["box"]), j) for j, x in enumerate(model)
                if j not in used and matches(b["box"], x["box"])]
        if not cand:
            lost.append(b)
            continue
        j = max(cand)[1]
        used.add(j)
        pairs.append((b, model[j]))
    extra = [x for j, x in enumerate(model) if j not in used]
    return pairs, lost, extra


def _rect(page, box, k, color, width, dashes=None):
    page.draw_rect(pymupdf.Rect(box[0] * k, box[1] * k, box[2] * k, box[3] * k),
                   color=color, width=width, dashes=dashes)


def _label(page, box, k, color, text, above=True):
    x, y = box[0] * k + 1, box[1] * k - 2
    if not above:
        y = box[3] * k + 7
    page.insert_text((x, max(7.0, y)), text, fontname="L", fontsize=6.0,
                     color=color)


def build(pdf: str, out: str, marks: list[tuple[str, str]], only=None,
          log=print) -> dict:
    """Наложить разметку на страницы PDF, ПОКАЗЫВАЯ РАСХОЖДЕНИЯ.

    `marks` — список пар (каталог, метка). Две разметки сличаются; одна
    рисуется целиком, потому что сличать не с чем.
    """
    note = _same_book(pdf, marks)
    sets = [(_pages(d), tag) for d, tag in marks]
    doc = pymupdf.open(pdf)
    if not os.path.exists(FONT):
        doc.close()
        raise OverlayError(f"нет шрифта {FONT}: подписи выйдут пустыми")
    if only is not None:
        bad = [i for i in only if not 0 <= i < doc.page_count]
        if bad:
            doc.close()
            raise OverlayError(
                f"в {pdf} нет страниц {bad}: всего {doc.page_count}")
    for pages, tag in sets:
        lost = sorted(i for i in pages if not 0 <= i < doc.page_count)
        if lost:
            doc.close()
            raise OverlayError(
                f"у разметки «{tag}» есть страницы {lost[:5]}, которых нет в "
                f"{pdf} ({doc.page_count} страниц): они исчезли бы без счёта.")

    counts = {"совпало": 0, "не нашла": 0, "лишних": 0, "страницы": []}
    drawn = 0
    for i, page in enumerate(doc):
        if only is not None and i not in only:
            continue
        if page.rotation:
            doc.close()
            raise OverlayError(
                f"страница {i} повёрнута атрибутом PDF ({page.rotation}°): "
                f"рамки лягут поперёк. Разверни PDF до наложения.")
        page.insert_font(fontname="L", fontfile=FONT)
        p0 = sets[0][0].get(i)
        if p0 is None:
            continue
        k = page.rect.width / p0["width"]
        kh = page.rect.height / p0["height"]
        if abs(k - kh) > 1e-3:
            doc.close()
            raise OverlayError(
                f"страница {i}: растр разметки {p0['width']}x{p0['height']} "
                f"не той пропорции, что лист — рамки лягут растянутыми.")
        if len(sets) == 1:
            for b in p0["blocks"]:
                _rect(page, b["box"], k, ОДНА, 1.1)
                _label(page, b["box"], k, ОДНА, f"{b['label']}")
                drawn += 1
            continue
        p1 = sets[1][0].get(i)
        if p1 is None:
            continue
        pairs, lost, extra = _pair(p0["blocks"], p1["blocks"])
        counts["совпало"] += len(pairs)
        counts["не нашла"] += len(lost)
        counts["лишних"] += len(extra)
        if lost or extra:
            counts["страницы"].append(i)
        for b, x in pairs:
            # Совпавшую пару рисуем ОДНОЙ тонкой рамкой и без подписи: две
            # почти совпадающие рамки с двумя подписями над каждой и делали
            # лист нечитаемым. Ярлык, если он разошёлся, — единственное, что
            # тут стоит сказать.
            _rect(page, x["box"], k, СОВПАЛО, 0.7)
            if b["label"] != x["label"]:
                _label(page, x["box"], k, ЛИШНЯЯ,
                       f"ярлык: {b['label']} -> {x['label']}")
            drawn += 1
        for b in lost:
            _rect(page, b["box"], k, НЕ_НАШЛА, 1.6)
            _label(page, b["box"], k, НЕ_НАШЛА, f"НЕ НАШЛА  {b['label']}")
            drawn += 1
        for x in extra:
            _rect(page, x["box"], k, ЛИШНЯЯ, 1.6, dashes="[3 3] 0")
            s = f" {x['score']:.2f}" if x.get("score") is not None else ""
            _label(page, x["box"], k, ЛИШНЯЯ, f"ЛИШНЯЯ  {x['label']}{s}",
                   above=False)
            drawn += 1

    if not drawn:
        doc.close()
        raise OverlayError(
            f"ни одна страница разметки не легла на {pdf}: в PDF "
            f"{doc.page_count} страниц, а индексы разметки другие")
    n = doc.page_count
    doc.save(out, garbage=3, deflate=True)
    doc.close()
    log(note)
    log(f"{out}: листов {n}, совпало {counts['совпало']}, "
        f"НЕ НАШЛА {counts['не нашла']}, ЛИШНИХ {counts['лишних']}; "
        f"расхождения на {len(counts['страницы'])} страницах")
    return counts
