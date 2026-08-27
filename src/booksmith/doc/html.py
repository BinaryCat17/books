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
hr.лист[data-без-текста]::after{content:"вся полоса ушла в картинки";
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
    # Две беды, каждая из которых МОЛЧА портит книгу, и обе обязаны быть
    # величиной, а не обнаружиться при чтении готового HTML.
    #
    #  * `съедено текстом` — текстовый блок целиком внутри артефактной рамки.
    #    Такой текст в HTML не попадает ВООБЩЕ: он остаётся только внутри
    #    картинки. На стенде из 93 страниц это случилось на двух, но там
    #    страница ушла в один <figure> целиком — 9 абзацев прозы исчезли.
    #  * `вложенных артефактов` — две артефактные рамки, одна внутри другой.
    #    Сырой вывод хранится без подавления, и обе доезжают до сборки: те же
    #    чернила выходят в книгу ДВАЖДЫ, двумя <figure>. Кому отдавать блок —
    #    решение, которое пока не объявлено, и потому его надо видеть числом.
    # ПОПРАВКА к первому счётчику, и она про правило «ноль от проверки и ноль
    # от непонимания».
    # Счётчик `съедено` считает текстовые блоки МОДЕЛИ, попавшие внутрь её же
    # артефактной рамки. На самой дорогой беде стенда он даёт ноль — и ноль
    # этот значит не «всё цело», а «модель не отдала на этой странице НИ
    # ОДНОГО текстового блока»: вся полоса ушла в одну рамку `table`, и в
    # книгу страница вышла единственным <figure> без единой строки. Поэтому
    # рядом стоят два числа, которые эту беду видят без всякой истины:
    # страниц без текста вовсе и наибольшая доля листа в одной рамке.
    eaten = nested = no_text = 0
    biggest = (0.0, None)
    for fp in files:
        with open(fp, encoding="utf-8") as f:
            page = Page.from_json(json.load(f))
        arts = [b for b in page.blocks if policy.role(b.label) == "артефакт"]
        sheet = float(page.width) * float(page.height)
        share = _union_share([b.box for b in arts], sheet)
        blank = not any(policy.role(b.label) == "текст" for b in page.blocks)
        no_text += blank
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
            + (' data-без-текста="да"' if blank else '') + '>')
        for b in page.blocks:
            a = anchor_of(page.index, b.block_id)
            role = policy.role(b.label)
            inside = [o for o in arts
                      if o.block_id != b.block_id and _covered(b.box, o.box)]
            if role != "артефакт" and inside:
                eaten += 1
            counts[role] += 1
            outer = nested_in.get(b.block_id)
            outer_a = anchor_of(page.index, outer) if outer is not None else None
            if role == "артефакт" or not b.content:
                rel = f"blocks/{a}.png"
                info = crop.cut(doc, page.index, b.box, page_dpi,
                                os.path.join(out_dir, rel))
                cut_n += 1
                clipped += bool(info["срезано листом"])
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
                       "ранг модели": b.order, "роль": role,
                       "рамка": list(b.box), "вырезка": info or None,
                       "внутри артефактов": [anchor_of(page.index, o.block_id)
                                             for o in inside] or None,
                       "внутри": outer_a,
                       "содержит": [anchor_of(page.index, k)
                                    for k, v in nested_in.items()
                                    if v == b.block_id] or None}
    doc.close()

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
    from .. import detect as _detect        # _sha256, _commit, _packages
    said = (snap.get("исходник") or {}).get("sha256")
    now = _detect._sha256(pdf)
    if said and said != now:
        raise ValueError(
            f"{pdf} изменился после детекции: слепок клялся sha256 "
            f"{said[:12]}, сейчас {now[:12]}. Вырезки шли бы из одного файла, "
            f"а рамки — из другого.")
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
        "исходник": {**snap["исходник"], "sha256": _detect._sha256(pdf),
                     "sha256 по слепку детекции": snap["исходник"].get("sha256")},
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
    log(f"текста съедено артефактной рамкой {eaten} "
        f"(эти абзацы в HTML не попали вовсе), "
        f"вложенных артефактов {nested} (подчинены внешней и помечены "
        f"data-внутри; ни один не выброшен)")
    log(f"страниц без единого текстового блока {no_text} "
        f"(вся полоса ушла в картинки), наибольшая доля листа в одной "
        f"рамке {biggest[0]*100:.0f}%"
        + (f" на стр. {biggest[1]}" if biggest[1] is not None else ""))
    log(f"якорей в документе {len(swap.anchors(page_html))}, "
        f"наблюдений сбоку {len(side)}")
    log(f"{out_html} ({os.path.getsize(out_html)/1024:.0f} КБ), "
        f"вырезки в {blockdir}")
    return {"страниц": len(files), "по разрядам": counts, "вырезок": cut_n,
            "срезано листом": clipped, "html": out_html,
            "вырезка": crop.params(), "политика": policy.snapshot()}
