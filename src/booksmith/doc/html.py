"""Продукт первого уровня: читаемый HTML из контуров.

Текст идёт разметкой, артефакты — картинками на своих местах, в порядке
чтения, который дала модель. Второй уровень заменит картинки разметкой по
одной, через `swap.py`.

ЧТО ЗДЕСЬ ЧЕГО НЕ КАСАЕТСЯ, И ЭТО ПРАВИЛО, А НЕ ВКУС.

Наблюдённое НЕ пишется в текст. Уверенность модели, её ярлык, ранг, срез
рамки листом — всё это живёт в `blocks.json` рядом и связано с блоком по
якорю. Прежде такие пометки (`⚠`, `≠`, `<mark>`, ссылка на скан) дописывались
прямо в разметку, то есть правили вывод модели на месте, и это стоило
конкретно: маркер дописывался в ячейки раньше, чем считалась подпись к
таблице, и рамка переставала узнавать собственную таблицу — 9 пропусков из 33.

Атрибуты `data-*` стоят на НАШЕЙ обёртке `<figure>`/`<p>`, а не внутри
содержимого модели. Обёртку писали мы, её и метим; байты модели неприкосновенны.

ПОЧЕМУ СЕЙЧАС КАРТИНКАМИ СТАНОВИТСЯ И ТЕКСТ. Распознавателя текста ещё нет:
`books detect` даёт контуры, а `Block.content` пуст у всех блоков. Блок, для
которого текста нет, выводится вырезкой и помечается `data-текст="не прочитан"`
— честно и сразу полезно: по такой странице глазом видно, верны ли контуры и
порядок чтения, ДО того как соглашения о них закрепит метрика. Когда появится
чтение текста, те же блоки поедут текстом, и ни строки здесь менять не придётся.
"""
import glob
import html as _html
import json
import os
import shlex
import time

from .. import policy
from ..models.base import Page
from ..run import knobs
from . import crop, swap

CSS = """
body{max-width:52em;margin:2em auto;padding:0 1em;
     font:16px/1.55 Georgia,'DejaVu Serif',serif}
figure{margin:1.2em 0;padding:0}
figure img{max-width:100%;height:auto;display:block;
           border:1px solid #ddd}
figcaption{font:12px/1.4 monospace;color:#777;margin-top:.3em}
p{margin:.7em 0}
[data-роль="служебное"]{opacity:.55}
[data-текст="не прочитан"] figcaption{color:#a60}
figure[data-внутри]{margin-left:2em;border-left:3px solid #e0c000;padding-left:.8em}
figure[data-внутри] figcaption{color:#a60}
hr.лист[data-без-текста]{border-top:2px solid #c00}
hr.лист[data-пусто]{border-top:2px dotted #c00}
hr.лист[data-пусто]::after{content:"модель не нашла на листе ничего";
    display:block;font:11px monospace;color:#c00;margin-top:.3em}
hr.лист[data-без-текста]:not([data-пусто])::after{content:"вся полоса ушла в картинки";
    display:block;font:11px monospace;color:#c00;margin-top:.3em}
hr.лист{border:0;border-top:1px dashed #ccc;margin:2.5em 0}
"""


def anchor_of(page_index: int, block_id: int) -> str:
    """Якорь блока. ПОСТРАНИЧНЫЙ: `block_id` считается заново на каждой стр."""
    return f"p{page_index:04d}-b{block_id}"


def _figure(anchor, b, role, rel, info, inside=None):
    cap = (f"{b.label} {b.score:.2f}" if b.score is not None else b.label)
    if inside:
        cap = f"деталь {inside} · " + cap
    if info.get("срезано листом"):
        cap += " · рамка вышла за лист"
    # Собираем атрибут отдельно: обратный слэш внутри f-строки — синтаксис
    # Python 3.12, а пакет заявляет 3.10.
    unread = "" if role == "артефакт" else ' data-текст="не прочитан"'
    within = f' data-внутри="{inside}"' if inside else ""
    return (f'<figure id="{anchor}" data-роль="{role}" '
            f'data-ярлык="{b.label}"{unread}{within}>'
            f'<img src="{_html.escape(rel)}" alt="{_html.escape(b.label)}" '
            f'width="{info["ширина"]}" height="{info["высота"]}">'
            f'<figcaption>{_html.escape(cap)}</figcaption></figure>')


def _union_share(boxes, sheet):
    """Доля листа под артефактами — по ОБЪЕДИНЕНИЮ, а не суммой площадей:
    вложенные рамки иначе считались бы дважды."""
    from .feed import _union_area
    if not boxes or sheet <= 0:
        return 0.0
    return min(1.0, _union_area([[float(v) for v in b] for b in boxes]) / sheet)


def _nesting(arts) -> dict:
    """Кто внутри кого. Возвращает {block_id внутренней: block_id внешней}.

    НИЧЕГО НЕ ВЫБРАСЫВАЕТ — только называет отношение. Внешней считается
    большая по площади; при равных площадях (а так бывает: `image` и `table`
    приезжают на ОДНОМ прямоугольнике) внешней зовётся та, что у модели
    раньше по её собственному рангу. Ранг взят потому, что он ЕЁ, а не наш.
    """
    def area(b):
        return max(0.0, b.box[2] - b.box[0]) * max(0.0, b.box[3] - b.box[1])

    inner = {}
    for b in arts:
        for o in arts:
            if o.block_id == b.block_id or not _covered(b.box, o.box):
                continue
            ab, ao = area(b), area(o)
            if ab > ao * 1.02:
                continue
            if abs(ab - ao) <= ao * 0.02 and (o.order, o.block_id) >= (b.order, b.block_id):
                continue
            inner[b.block_id] = o.block_id
            break
    # Цепочку рвём: внешняя, сама лежащая внутри третьей, остаётся внешней для
    # своей внутренней — иначе подпись «деталь» указывала бы в пустоту.
    return inner


def _covered(inner, outer, part=0.9):
    """Доля `inner`, накрытая `outer`. Ровно то, что решает, исчезнет ли блок
    внутри чужой картинки."""
    x0, y0 = max(inner[0], outer[0]), max(inner[1], outer[1])
    x1, y1 = min(inner[2], outer[2]), min(inner[3], outer[3])
    i = max(0.0, x1 - x0) * max(0.0, y1 - y0)
    a = max(0.0, inner[2] - inner[0]) * max(0.0, inner[3] - inner[1])
    return a > 0 and i / a >= part


def _twice_area(boxes):
    """Площадь, накрытая ДВУМЯ рамками и более. Развёртка по вертикали, как
    `_union_area`; тройное накрытие не считается трижды.

    Ровно эти чернила уезжают в книгу дважды: и своей вырезкой, и внутри
    чужой. Касание (`x1` одной равен `x0` другой) не пересечение и даёт 0.
    """
    if len(boxes) < 2:
        return 0.0
    xs = sorted({v for b in boxes for v in (b[0], b[2])})
    total = 0.0
    for a, c in zip(xs, xs[1:]):
        if c <= a:
            continue
        ev = []
        for b in boxes:
            if b[0] <= a and b[2] >= c and b[3] > b[1]:
                ev.append((b[1], 1))
                ev.append((b[3], -1))
        ev.sort()
        cov, depth, prev = 0.0, 0, None
        for y, d in ev:
            if depth >= 2:
                cov += y - prev
            depth += d
            prev = y
        total += cov * (c - a)
    return total


def _order_src(page) -> str:
    """Откуда у блоков этой страницы взялся `order` — словами адаптера.

    Три состояния, и путать их нельзя. Поля НЕТ вовсе — слепок молчит (так во
    всех девяти каталогах стенда, сделанных до появления поля); поле есть, а в
    нём `null` — адаптер сказал «не знаю»; строка — он назвал источник.
    Умолчание «ранг модели» при отсутствии поля живёт в стороже метрики
    (`metrics._has_order`) и здесь НЕ повторяется: выдать неизвестное за
    модельное — ровно та подмена, из-за которой этот участок и чинится.
    """
    m = page.meta or {}
    if "порядок чтения" not in m:
        return "не сказано"
    v = m["порядок чтения"]
    if v is None:
        return "поле есть, значение null"
    return v if isinstance(v, str) else f"не строка: {v!r}"


def _ours(v) -> bool:
    """Наш ли это порядок — по строке, которую вернул `_order_src`.

    Признак один и общий с метрикой: слово «наш» в начале. Сторож метрики
    (`metrics._has_order`) сверяет его СО СТРОЧНОЙ и потому не видит «НАШ» с
    заглавной — так написано в `doclayout.fingerprint`, но в meta СТРАНИЦЫ
    адаптеры пишут строчную. Здесь регистр снят: строка журнала обязана
    назвать наш порядок нашим при любом написании, а не молча зачесть его
    модели. Неизвестное («не сказано», `null`) наш порядок не подтверждает и
    не опровергает: в число наших оно не идёт, но и модельным не зовётся.
    """
    return isinstance(v, str) and v.strip().lower().startswith("наш")


def build(detect_dir: str, out_dir: str, log=print) -> dict:
    """Собрать HTML из каталога `books detect`. Возвращает величины сборки."""
    import pymupdf

    detect_dir = os.path.abspath(detect_dir)
    out_dir = os.path.abspath(out_dir)
    with open(os.path.join(detect_dir, "run.json"), encoding="utf-8") as f:
        snap = json.load(f)
    pdf = snap["исходник"]["путь"]
    page_dpi = float(snap["растр"]["dpi"])
    if not os.path.exists(pdf):
        raise SystemExit(
            f"исходник разбора не на месте: {pdf}\n"
            f"HTML собирается из PDF, а не из растра детекции — вырезка "
            f"плотной таблицы при {page_dpi:.0f} dpi нечитаема.")

    # СВЕРКА ИСХОДНИКА СТОИТ ЗДЕСЬ, а не в конце, и это цена опыта. Прежде
    # sha256 считался после всей работы: 568 вырезок `slovar` уже нарезаны,
    # book.html и blocks.json уже на диске, — и только тогда летел ValueError.
    # Подмена PDF по тому же пути (djvu пересобран другим разрезом разворотов,
    # другая книга с тем же именем) давала ровно худший исход: на диске книга
    # из ЧУЖОГО файла, БЕЗ слепка — run.json пишется ниже и до него не
    # доходило, — а оператору трассировка вместо объяснения. Теперь падаем до
    # первой вырезки и тем же способом, что две беды выше: SystemExit с
    # текстом.
    from .. import detect as _detect        # _sha256, _commit, _packages
    said = (snap.get("исходник") or {}).get("sha256")
    now = _detect._sha256(pdf)
    if said and said != now:
        raise SystemExit(
            f"{pdf} изменился после детекции: слепок клялся sha256 "
            f"{said[:12]}, сейчас {now[:12]}. Вырезки шли бы из одного файла, "
            f"а рамки — из другого. Пересчитайте books detect либо верните "
            f"тот PDF, по которому считались рамки.")
    # Величина, а не «сошлось», — и два разных нуля рядом. Слепок детекции
    # без поля sha256 (таковы все девять каталогов стенда, сделанных до его
    # появления) — это НЕ «сверено и совпало», а «сверять не с чем», и так и
    # написано.
    log(f"исходник {os.path.basename(pdf)} sha256 {now[:12]}"
        + (" — сошёлся со слепком детекции" if said
           else " — слепок детекции sha256 не назвал, сверять не с чем"))

    files = sorted(glob.glob(os.path.join(detect_dir, "pages", "*.json")))
    if not files:
        raise SystemExit(f"в {detect_dir} нет страниц — сначала books detect")

    doc = pymupdf.open(pdf)
    blockdir = os.path.join(out_dir, "blocks")
    os.makedirs(blockdir, exist_ok=True)
    for old in glob.glob(os.path.join(blockdir, "*.png")):
        os.unlink(old)

    body, side = [], {}
    counts = {r: 0 for r in policy.ROLES}
    cut_n = clipped = 0
    # Три беды, каждая из которых МОЛЧА портит книгу, и все три обязаны быть
    # величиной, а не обнаружиться при чтении готового HTML.
    #
    #  * ЧЕРНИЛА ДВАЖДЫ — доля листа под двумя вырезками и более. Рамкам
    #    модели пересекаться не запрещено, а режем мы по каждой: где рамки
    #    налезли, те же строки уезжают в книгу двумя картинками.
    #    Здесь стоял счётчик `съедено текстом`, и журнал утверждал, что такие
    #    абзацы «в HTML не попали вовсе». Это неправда: в цикле ниже блок
    #    выводится независимо от того, лежит ли он внутри чужой рамки, — на
    #    стенде hard36 792 блока дали 792 якоря и 792 вырезки, не пропал ни
    #    один. Беда обратна потере, и мерить её надо площадью, а не счётом
    #    блоков: на стенде `slovar` рамки `reference` и `reference_content`
    #    налезают друг на друга 166 раз (одна `reference` накрывает до 20
    #    соседних), колонка выходит в книгу дважды — 23.45% всей бумаги, — а
    #    прежние два счётчика печатали там 0 и 0, потому что оба смотрят
    #    только на артефактные рамки.
    #  * `вложенных артефактов` — две артефактные рамки, одна внутри другой.
    #    Сырой вывод хранится без подавления, и обе доезжают до сборки. Кому
    #    отдавать блок — решение, которое пока не объявлено, и потому его
    #    надо видеть числом отдельно от общей площади.
    #  * СТРАНИЦА БЕЗ ТЕКСТА — самая дорогая беда стенда: вся полоса ушла в
    #    одну рамку `table`, и в книгу страница вышла единственным <figure>
    #    без единой строки. Ни двойные чернила, ни вложенность её не видят
    #    (рамка там одна, пересекаться не с чем), поэтому рядом стоят два
    #    своих числа: страниц без текста вовсе и наибольшая доля листа в
    #    одной рамке.
    dup_text = nested = no_text = no_blocks = 0
    # ЧЕЙ ПОРЯДОК СОБРАН — главное свойство книги и до сих пор нигде не
    # названное. `Block.order` у трёх адаптеров из четырёх не ранг модели, а
    # наша сортировка сверху вниз и слева направо; адаптер честно говорит об
    # этом в meta страницы полем «порядок чтения». Считаем страницы по этому
    # полю, а не по одному значению на книгу: страницы приходят из одного
    # прогона, но каталог собирается руками и может оказаться смешанным.
    order_src_n = {}
    ink2 = sheet_pt_all = 0.0
    worst2 = (0.0, None)
    biggest = (0.0, None)
    for fp in files:
        with open(fp, encoding="utf-8") as f:
            page = Page.from_json(json.load(f))
        order_src = _order_src(page)
        order_src_n[order_src] = order_src_n.get(order_src, 0) + 1
        arts = [b for b in page.blocks if policy.role(b.label) == "артефакт"]
        sheet = float(page.width) * float(page.height)
        share = _union_share([b.box for b in arts], sheet)
        # ПУСТАЯ страница — не «ушла в картинки». Прежде лист, на котором
        # модель не нашла ВООБЩЕ ничего, помечался тем же красным «вся полоса
        # ушла в картинки», что и лист, целиком съеденный одной рамкой. Это
        # два разных отказа, и путать их нельзя: первый — «модель ничего не
        # увидела», второй — «увидела одно на всё».
        blank = (bool(page.blocks)
                 and not any(policy.role(b.label) == "текст"
                             for b in page.blocks))
        empty = not page.blocks
        no_text += blank
        no_blocks += empty
        for b in arts:
            one = ((b.box[2] - b.box[0]) * (b.box[3] - b.box[1])) / sheet
            if one > biggest[0]:
                biggest = (one, page.index)
        # ПРАВИЛО 1: вложенная рамка подчиняется внешней, но не пропадает.
        nested_in = _nesting(arts)
        nested += len(nested_in)
        # ПРАВИЛО 2: полоса, ушедшая в картинки целиком, помечена на листе.
        body.append(
            f'<hr class="лист" data-стр="{page.index}" '
            f'data-доля-в-картинках="{share:.2f}"'
            + (' data-без-текста="да"' if blank else '')
            + (' data-пусто="да"' if empty else '') + '>')
        cuts = []
        for b in page.blocks:
            a = anchor_of(page.index, b.block_id)
            role = policy.role(b.label)
            inside = [o for o in arts
                      if o.block_id != b.block_id and _covered(b.box, o.box)]
            if role != "артефакт" and inside:
                dup_text += 1
            counts[role] += 1
            outer = nested_in.get(b.block_id)
            outer_a = anchor_of(page.index, outer) if outer is not None else None
            if role == "артефакт" or not b.content:
                rel = f"blocks/{a}.png"
                info = crop.cut(doc, page.index, b.box, page_dpi,
                                os.path.join(out_dir, rel))
                cut_n += 1
                clipped += bool(info["срезано листом"])
                cuts.append([float(v) for v in info["рамка в пунктах"]])
                body.append(swap.wrap(
                    a, _figure(a, b, role, rel, info, inside=outer_a)))
            else:
                info = {}
                body.append(swap.wrap(
                    a, f'<p id="{a}" data-роль="{role}" '
                       f'data-ярлык="{b.label}">'
                       f'{_html.escape(b.content)}</p>'))
            # Наблюдённое — сбоку, по якорю. В текст не лезет ничего.
            side[a] = {"страница": page.index, "блок": b.block_id,
                       "ярлык": b.label, "уверенность": b.score,
                       # Поле звалось «ранг модели» и врало на трёх адаптерах
                       # из четырёх: там это НАША позиция в списке. Ровно эта
                       # болезнь — своё, названное чужим, — печатала метрике
                       # порядка проценты из ничего (86% у YOLOX, который
                       # ранга не даёт вовсе). Имя стало нейтральным, а рядом
                       # лежит источник — то самое значение meta страницы.
                       "порядок": b.order, "порядок откуда": order_src,
                       "роль": role,
                       "рамка": list(b.box), "вырезка": info or None,
                       "внутри артефактов": [anchor_of(page.index, o.block_id)
                                             for o in inside] or None,
                       "внутри": outer_a,
                       "содержит": [anchor_of(page.index, k)
                                    for k, v in nested_in.items()
                                    if v == b.block_id] or None}
        # Считаем по рамкам, которые РЕАЛЬНО порезаны, и в пунктах листа, а
        # не по `b.box`: у вырезки своё поле (`CROP_MARGIN`) и свой срез
        # краем листа, и уезжает в книгу именно она.
        # ЧЕГО ЭТО ЧИСЛО НЕ ВИДИТ, и это надо знать заранее: оно про вырезки,
        # а не про чернила вообще. Сейчас режется всё подряд, потому что
        # текста ещё никто не читает, и на `slovar` все 166 налезаний — текст
        # на тексте (`reference` поверх `reference_content`, оба «текст» по
        # политике). Когда появится чтение, такие блоки поедут строками,
        # вырезок для них не будет и число упадёт до нуля — но слова
        # останутся задвоенными, уже двумя <p>. Тот ноль будет от
        # непонимания, и к нему понадобится своя величина, по всем блокам, а
        # не по вырезкам.
        r = doc[page.index].rect
        sheet_pt = float(r.width) * float(r.height)
        twice = min(_twice_area(cuts), sheet_pt)
        ink2 += twice
        sheet_pt_all += sheet_pt
        if sheet_pt > 0 and twice / sheet_pt > worst2[0]:
            worst2 = (twice / sheet_pt, page.index)
    doc.close()

    # ВТОРАЯ СВЕРКА, ПОСЛЕ РАБОТЫ. Первая (до вырезок) отвечает на вопрос
    # «тот ли это файл, по которому считались рамки»; эта — на другой: «не
    # подменили ли его, ПОКА мы резали». Замер, ради которого она здесь:
    # копия каталога `slovar/detect`, подмена PDF через 1.5 с после старта —
    # сборка доходила до конца без единой жалобы, 568 вырезок резались из
    # двух разных файлов, слепок клялся хэшем первого, а `replay --check`
    # печатал «41 из 41» и возвращал 0. То есть слепок объявлял прогон
    # повторимым, будучи лживым, — ровно то, чего первая сверка не ловит по
    # построению: она смотрит на файл до того, как его читали.
    #
    # Файл читается второй раз намеренно. Цена — один проход по PDF
    # (`slovar`, 34 МБ: 0.06 с против 12 с сборки); плата за её отсутствие —
    # книга, про которую нельзя сказать, из чего она сделана.
    after = _detect._sha256(pdf)
    if after != now:
        raise SystemExit(
            f"{pdf} подменён ВО ВРЕМЯ сборки: при старте sha256 {now[:12]}, "
            f"сейчас {after[:12]}. Часть вырезок нарезана из одного файла, "
            f"часть из другого, и какая именно — неизвестно. Книга не "
            f"записана; повторите books html целиком.")

    page_html = ("<!doctype html>\n<html lang=\"ru\"><head>"
                 "<meta charset=\"utf-8\">"
                 f"<title>{_html.escape(os.path.basename(pdf))}</title>"
                 f"<style>{CSS}</style></head>\n<body>\n"
                 + "\n".join(body) + "\n</body></html>\n")
    os.makedirs(out_dir, exist_ok=True)
    out_html = os.path.join(out_dir, "book.html")
    with open(out_html, "w", encoding="utf-8") as f:
        f.write(page_html)
    with open(os.path.join(out_dir, "blocks.json"), "w", encoding="utf-8") as f:
        json.dump(side, f, ensure_ascii=False, indent=1)

    # Свой слепок, а не «наследуем детекцию». У сборки есть собственные
    # ручки (`CROP_DPI`, `CROP_MARGIN`) и собственная политика, и без них
    # нельзя ответить, какой резкостью вырезаны эти картинки. Планка одна:
    # `books replay --check` обязан вернуть 0 и здесь.
    here = os.path.dirname(os.path.abspath(__file__))
    snap_out = {
        "когда": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "ручки": knobs.snapshot(),
        "растр": dict(snap["растр"]),
        "аргументы": {"detect": detect_dir, "out": out_dir},
        "коммит": _detect._commit(),
        # sha256 ПЕРЕСЧИТАН, а не переписан из слепка детекции. Прежняя
        # редакция копировала чужое значение: PDF по тому же пути можно
        # пересобрать (другой разрез разворотов, другая версия pymupdf, просто
        # другая книга с тем же именем) — вырезки резались бы из нового файла,
        # слепок клялся бы старым, а `replay --check` печатал бы «полон» и
        # возвращал 0. Слепок объявлял бы прогон повторимым, будучи лживым.
        # Число то же самое, что сверено ДО первой вырезки, и файл читается
        # один раз вместо трёх: прежде sha256 считался дважды подряд здесь и
        # один раз для сверки.
        "исходник": {**snap["исходник"], "sha256": now,
                     "sha256 по слепку детекции": said,
                     # Обе величины, а не одна: «совпало до и после» — это
                     # утверждение о ЦЕЛОМ прогоне, а одно число до работы
                     # утверждает лишь про её начало.
                     "sha256 после сборки": after},
        # Что решает вид этой сборки: три модуля и слепок детекции целиком.
        "адаптер": {
            "имя": "doc.html",
            "sha256": _detect._sha256(os.path.join(here, "html.py")),
            "sha256 вырезки": _detect._sha256(os.path.join(here, "crop.py")),
            "sha256 замены": _detect._sha256(os.path.join(here, "swap.py")),
            "sha256 слепка детекции": _detect._sha256(
                os.path.join(detect_dir, "run.json"))},
        "политика": policy.snapshot(),
        "вырезка": crop.params(),
        # У сборки нет ни промтов, ни порождения, ни весов — это ЗНАЧЕНИЯ.
        "промты": {},
        "порождение": {"temperature": None, "max_tokens": None,
                       "top_p": None, "seed": None},
        "пакеты": _detect._packages(),
        "веса": {"vl": None, "layout": snap["веса"]["layout"]},
        "итог": {"страниц": len(files), "по разрядам": counts,
                 "вырезок": cut_n, "срезано листом": clipped,
                 "чернил дважды, доля листов": (
                     round(ink2 / sheet_pt_all, 4)
                     if sheet_pt_all > 0 else None),
                 "худший лист по двойным чернилам": (
                     {"стр": worst2[1], "доля": round(worst2[0], 4)}
                     if worst2[1] is not None else None),
                 "текста внутри артефактных рамок": dup_text,
                 "вложенных артефактов": nested,
                 "порядок блоков": {
                     "по meta страниц": dict(sorted(order_src_n.items())),
                     "страниц с нашим порядком": sum(
                         n for v, n in order_src_n.items() if _ours(v))},
                 "якорей": len(swap.anchors(page_html))},
        "повтор": " ".join(shlex.quote(a) for a in
                           ["books", "html", detect_dir, "--out", out_dir]),
    }
    with open(os.path.join(out_dir, "run.json"), "w", encoding="utf-8") as f:
        json.dump(snap_out, f, ensure_ascii=False, indent=1)

    # Число, а не «готово»: по разрядам видно, во что превратилась книга.
    log(f"страниц {len(files)}, блоков {sum(counts.values())} "
        f"(текст {counts['текст']}, артефакты {counts['артефакт']}, "
        f"служебное {counts['служебное']})")
    log(f"вырезок {cut_n} при {crop.params()['dpi']:.0f} dpi, "
        f"поле {crop.params()['поле']}, срезано листом {clipped}")
    # Ноль от проверки и ноль от непонимания: «0.00%» здесь значит «сверили
    # все вырезки, пересечений нет», а нулевой знаменатель — «сверять нечем»,
    # и так и написано.
    if sheet_pt_all > 0:
        log(f"чернил дважды {ink2 / sheet_pt_all * 100:.2f}% площади листов"
            + (f", худший лист стр. {worst2[1]}: {worst2[0] * 100:.0f}%"
               if worst2[1] is not None
               else " — ни на одном листе вырезки не пересеклись"))
    else:
        log("чернил дважды: нет данных — площадь листов нулевая")
    log(f"текстовых блоков внутри артефактной рамки {dup_text} "
        f"(они в HTML ЕСТЬ, но их чернила уехали ещё и в картинку "
        f"артефакта), вложенных артефактов {nested} (подчинены внешней и "
        f"помечены data-внутри; ни один не выброшен)")
    log(f"страниц, где модель не нашла НИЧЕГО: {no_blocks}")
    log(f"страниц без единого текстового блока {no_text} "
        f"(вся полоса ушла в картинки), наибольшая доля листа в одной "
        f"рамке {biggest[0]*100:.0f}%"
        + (f" на стр. {biggest[1]}" if biggest[1] is not None else ""))
    # ЧЕЙ ПОРЯДОК — величиной. Без этой строки книга собиралась молча, и
    # «текст идёт в порядке чтения, который дала модель» (шапка файла) было
    # утверждением, которое никто не проверял: у yolox и обоих docling порядок
    # НАШ, и на глаз это неотличимо.
    ours = sum(n for v, n in order_src_n.items() if _ours(v))
    if len(order_src_n) == 1:
        v, n = next(iter(order_src_n.items()))
        log(f"порядок блоков: «{v}» на всех {n} стр.; "
            f"наш, а не модели, на {ours} стр."
            + (" (meta страниц о порядке молчит — чей он, слепок детекции "
               "не говорит; «наш» здесь не посчитан, а не опровергнут)"
               if v == "не сказано" else ""))
    else:
        log("порядок блоков РАЗНЫЙ по страницам: "
            + ", ".join(f"«{v}» — {n} стр."
                        for v, n in sorted(order_src_n.items(),
                                           key=lambda kv: (-kv[1], kv[0])))
            + f"; наш, а не модели, на {ours} стр. из {len(files)}")
    log(f"якорей в документе {len(swap.anchors(page_html))}, "
        f"наблюдений сбоку {len(side)}")
    log(f"{out_html} ({os.path.getsize(out_html)/1024:.0f} КБ), "
        f"вырезки в {blockdir}")
    return {"страниц": len(files), "по разрядам": counts, "вырезок": cut_n,
            "срезано листом": clipped, "html": out_html,
            # Чей порядок — величина того же ранга, что число вырезок: без неё
            # вызывающий не может сказать, что именно он собрал.
            "порядок блоков": {
                "по meta страниц": dict(sorted(order_src_n.items())),
                "страниц с нашим порядком": ours},
            "вырезка": crop.params(), "политика": policy.snapshot()}
