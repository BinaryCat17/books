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
    показывал бы одно, а число говорило другое.

    СОПОСТАВЛЯЕМ АРТЕФАКТ С АРТЕФАКТОМ, а не всё подряд. `books score` ищет
    артефакт истины только среди АРТЕФАКТНЫХ рамок модели (проход А), а слепой
    к ярлыку проход у него служит порядку чтения и тексту, а не итоговой доле.
    Слепое сопоставление здесь рисовало таблицу, накрытую рамкой `text`, тонким
    серым «совпало», считало её совпавшей в итоговой строке и не заносило
    страницу в расхождения — ровно там, где число звало её потерянной: 51
    артефакт на девяти стендах (33 на annopage, 14 на hard, 2 на matematika, по
    одному на atlas и hard36), из них 31 таблица, съеденная текстовой рамкой
    (table->text 17, table->content 13, table->reference 1).

    Сторона считается тем же `label in arte`, что и в `compare_pages`, а не
    через `policy.role`: ярлык, политикой не описанный, обязан вести себя тут
    ТАК ЖЕ, как в score, иначе лист и число опять разойдутся — теперь на
    исключении.
    """
    from .metrics import _pick, _area
    from . import policy
    arte = set(policy.artefacts())
    pairs, lost, extra = [], [], []
    for side in (True, False):
        t = [b for b in truth if (b["label"] in arte) == side]
        m = [x for x in model if (x["label"] in arte) == side]
        # Порядок жадности взят у той же стороны `books score`: артефакты — в
        # порядке разметки, как в проходе А, остальное — от крупных к мелким,
        # как в проходе Б. При одном правиле совпадения, но другом порядке
        # пары расходились бы на спорных местах.
        if not side:
            t = sorted(t, key=lambda z: -_area(z["box"]))
        used = set()
        for b in t:
            j = _pick(b, m, used)
            if j is None:
                lost.append(b)
                continue
            used.add(j)
            pairs.append((b, m[j]))
        extra += [x for j, x in enumerate(m) if j not in used]
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

    ЧЕГО ИСТИНА НЕ РАЗМЕЧАЕТ, ТО НЕ «ЛИШНЕЕ». Истина объявляет это сама —
    полем meta «текст размечен»; нет поля — считаем, что размечает. Рамки
    неразмечаемых разрядов рисуются синим волоском без подписи (синий здесь
    значит то же, что и у одиночной разметки: сравнивать не с чем) и идут
    отдельной величиной, а не в «лишних».

    ПРО ЭТО ГОВОРИТСЯ ВСЕГДА, а не только когда такие рамки нашлись. «Вне
    разметки 0» бывает двух видов: истина текст размечает и лишнего нет —
    и истина текста не размечает, а модель его не выдала. Молчание здесь
    выдавало бы второе за первое, то есть ноль от непонимания за ноль от
    проверки.
    """
    from . import policy

    def role(label: str) -> str:
        # Неизвестный политике ярлык не прячем: пусть остаётся кричащим.
        try:
            return policy.role(label)
        except policy.UnknownLabel:
            return "артефакт"

    def die(msg: str):
        """Закрыть документ и упасть СВОИМ сообщением.

        Сообщение собирается на стороне вызова — то есть ДО того, как сюда
        зашли и закрыли документ. Прежде каждая защита писала `doc.close()`
        строкой выше, чем `raise OverlayError(... doc.page_count ...)`, а
        pymupdf 1.28.2 обращение к закрытому документу роняет: `page_count`
        даёт ValueError «document closed», `page.rotation` — AssertionError
        «page is None». Наружу вылетало это, а не объяснение, и вылетало
        голым следом стека: в cli.py `overlay.build` ничем не обёрнут.
        Проверено на всех четырёх защитах, где после close читался документ.
        """
        doc.close()
        raise OverlayError(msg)

    note = _same_book(pdf, marks)
    sets = [(_pages(d), tag) for d, tag in marks]
    doc = pymupdf.open(pdf)
    if not os.path.exists(FONT):
        die(f"нет шрифта {FONT}: подписи выйдут пустыми")
    if only is not None:
        bad = [i for i in only if not 0 <= i < doc.page_count]
        if bad:
            die(f"в {pdf} нет страниц {bad}: всего {doc.page_count}")
    for pages, tag in sets:
        lost = sorted(i for i in pages if not 0 <= i < doc.page_count)
        if lost:
            die(f"у разметки «{tag}» есть страницы {lost[:5]}, которых нет в "
                f"{pdf} ({doc.page_count} страниц): они исчезли бы без счёта.")

    counts = {"совпало": 0, "не нашла": 0, "лишних": 0, "вне разметки": 0,
              "страниц без разметки текста": 0, "сличено страниц": 0,
              "страницы": []}
    drawn = 0
    for i, page in enumerate(doc):
        if only is not None and i not in only:
            continue
        if page.rotation:
            die(f"страница {i} повёрнута атрибутом PDF ({page.rotation}°): "
                f"рамки лягут поперёк. Разверни PDF до наложения.")
        page.insert_font(fontname="L", fontfile=FONT)
        p0 = sets[0][0].get(i)
        if p0 is None:
            continue
        k = page.rect.width / p0["width"]
        kh = page.rect.height / p0["height"]
        if abs(k - kh) > 1e-3:
            die(f"страница {i}: растр разметки {p0['width']}x{p0['height']} "
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
        # Масштаб у КАЖДОЙ разметки свой. Прежде брался коэффициент первой и
        # молча применялся ко второй: если растр вывода модели отличается от
        # растра истины хоть на пиксель, рамки ложатся смещёнными, а лист
        # выглядит убедительно.
        if (p1["width"], p1["height"]) != (p0["width"], p0["height"]):
            die(f"страница {i}: растр истины {p0['width']}x{p0['height']}, "
                f"растр модели {p1['width']}x{p1['height']} — рамки лягут "
                f"в разных системах координат.")
        pairs, lost, extra = _pair(p0["blocks"], p1["blocks"])
        # Признак берётся у ИСТИНЫ и у каждой страницы свой; нет поля —
        # размечает, и всё остаётся как было. Своё на каждой странице он не
        # от педантизма: на стенде hard36 текст размечен на одной странице
        # из тридцати шести, и признак «на весь стенд» соврал бы про обе
        # половины сразу.
        marked = bool((p0.get("meta") or {}).get("текст размечен", True))
        counts["сличено страниц"] += 1
        counts["страниц без разметки текста"] += 0 if marked else 1
        loud, quiet = [], []
        for x in extra:
            (loud if marked or role(x["label"]) == "артефакт"
             else quiet).append(x)
        counts["совпало"] += len(pairs)
        counts["не нашла"] += len(lost)
        counts["лишних"] += len(loud)
        counts["вне разметки"] += len(quiet)
        if lost or loud:
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
        for x in quiet:
            # Тонко, синим и без подписи. Совсем не рисовать нельзя: лист
            # тогда молчал бы о том, что модель вообще что-то нашла, — и это
            # был бы ноль от непонимания, выданный за чистую страницу.
            _rect(page, x["box"], k, ОДНА, 0.5, dashes="[1 2] 0")
            drawn += 1
        for x in loud:
            _rect(page, x["box"], k, ЛИШНЯЯ, 1.6, dashes="[3 3] 0")
            s = f" {x['score']:.2f}" if x.get("score") is not None else ""
            _label(page, x["box"], k, ЛИШНЯЯ, f"ЛИШНЯЯ  {x['label']}{s}",
                   above=False)
            drawn += 1

    if not drawn:
        die(f"ни одна страница разметки не легла на {pdf}: в PDF "
            f"{doc.page_count} страниц, а индексы разметки другие")
    n = doc.page_count
    doc.save(out, garbage=3, deflate=True)
    doc.close()
    log(note)
    log(f"{out}: листов {n}, совпало {counts['совпало']}, "
        f"НЕ НАШЛА {counts['не нашла']}, ЛИШНИХ {counts['лишних']}; "
        f"расхождения на {len(counts['страницы'])} страницах")
    # Величина, а не молчание, и говорится всегда, когда есть неразмечающие
    # страницы: «ЛИШНИХ 508» без этой строки читалось бы как «весь лист
    # сверен», хотя текст на этих страницах не сверялся вовсе.
    if counts["страниц без разметки текста"]:
        log(f"  текста истина НЕ размечает на "
            f"{counts['страниц без разметки текста']} страницах из "
            f"{counts['сличено страниц']} (meta «текст размечен»: false): "
            f"{counts['вне разметки']} рамок модели этих разрядов "
            f"нарисованы волоском и в «лишних» НЕ считаны — это не ноль "
            f"лишних, это «сверять было нечем»")
    return counts
