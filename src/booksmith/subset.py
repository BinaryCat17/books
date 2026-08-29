"""Выжимка стенда: страницы, где в ИСТИНЕ два артефакта одного класса рядом.

Зачем отдельный стенд. Замер на шести синтетических книгах показал слияние
одиннадцать раз; на настоящих страницах AnnoPage — 378 недоборов из 534, то
есть 71% всех промахов. Разница в том, сколько таких страниц в выборке: в
синтетике их тринадцать, в AnnoPage сто тридцать восемь. Мерить главный
дефект на выборке, где он почти не встречается, значит мерить его шумом.

Выжимка нужна и по деньгам: подать в арендованную модель 700 страниц ради
дефекта, который виден на 151, — это заплатить вшестеро за тот же ответ.

Истина переносится КАК ЕСТЬ, вместе с полем «вне замера»: страница не меняется
ни на пиксель, меняется только её номер.

ПЕРЕНОСЯТСЯ И ПРИЗНАКИ, А НЕ ТОЛЬКО РАМКИ. `порядок размечен`, `текст
размечен`, `вне замера` — это входы метрики наравне с координатами, и потеря
любого из них не роняет прогон, а МЕНЯЕТ ЧИСЛО МОЛЧА. Цена померена:
`bench/hard36` собран внешним скриптом, который донёс рамки и потерял ровно
`порядок размечен` (в `bench/hard` признак есть у 124 страниц из 130, в
hard36 — ни у одной из 36). `books score` читал его отсутствие как «порядок
размечен» и печатал «пар 211, согласовано 73%» — число из ничего, по
которому уже ранжировались детекторы. Поэтому здесь признаки переносятся
явно, их состояние считается поимённо и уезжает в манифест: выжимка обязана
уметь сказать, чего в ней нельзя мерить.
"""
import hashlib
import json
import os

import pymupdf

from . import policy


class SubsetError(RuntimeError):
    pass


def _side_pairs(blocks):
    """Пары блоков ОДНОГО ярлыка, стоящих бок о бок: вертикали перекрываются
    больше чем наполовину, по горизонтали не пересекаются вовсе."""
    out = []
    for i in range(len(blocks)):
        for j in range(i + 1, len(blocks)):
            if blocks[i]["label"] != blocks[j]["label"]:
                continue
            a, b = blocks[i]["box"], blocks[j]["box"]
            v = min(a[3], b[3]) - max(a[1], b[1])
            h = min(a[2], b[2]) - max(a[0], b[0])
            if v > 0.5 * min(a[3] - a[1], b[3] - b[1]) and h <= 0:
                out.append((i, j))
    return out


# Признаки истины, без которых метрика молча меняет ответ. Список ЯВНЫЙ:
# новый признак у стенда должен попасть сюда осознанно, а не быть потерянным
# по умолчанию.
TRAITS = ("порядок размечен", "текст размечен")


def _carry_meta(t: dict, extra: dict, where: str) -> dict:
    """Meta исходной страницы плюс наши пометки. Ничего не затирая.

    `t.setdefault("meta", {})` прежней редакции падал бы на странице с
    `"meta": null` (setdefault вернул бы None) и, что хуже, молча позволял
    нашим полям встать поверх одноимённых полей истины. Наши три поля —
    бухгалтерия выжимки, а не истина, и права затирать истину у них нет.
    """
    src = dict(t.get("meta") or {})
    clash = {k: (src[k], v) for k, v in extra.items()
             if k in src and src[k] != v}
    if clash:
        raise SubsetError(
            f"{where}: поля выжимки затёрли бы поля истины {clash}. Истина "
            f"переносится как есть; править её здесь нельзя.")
    meta = {**src, **extra}
    lost = [k for k in src if k not in meta]
    if lost:
        raise SubsetError(f"{where}: при переносе потеряны признаки {lost}")
    return meta


def _trait_state(meta: dict, key: str) -> str:
    """Три ответа, а не два: «да», «нет», «не сказано». Последнее — не то же
    самое, что «нет»: страница, где признака НЕТ ВОВСЕ, ничего не утверждает,
    и метрика по ней обязана молчать, а не считать."""
    if key not in meta:
        return "не сказано"
    return "да" if meta[key] else "нет"


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build(books, out_dir: str, root: str = "bench", log=print) -> dict:
    """Собрать выжимку из перечисленных книг стенда."""
    arte = set(policy.artefacts())
    os.makedirs(out_dir, exist_ok=True)
    tdir = os.path.join(out_dir, "truth")
    os.makedirs(tdir, exist_ok=True)
    for old in os.listdir(tdir):
        os.unlink(os.path.join(tdir, old))

    doc = pymupdf.open()
    kept, per_book, pairs_total = [], {}, 0
    traits = {k: {"да": 0, "нет": 0, "не сказано": 0} for k in TRAITS}
    for bk in books:
        pdf = os.path.join(root, bk, f"{bk}.pdf")
        if not os.path.exists(pdf):
            raise SubsetError(f"нет {pdf}")
        src = pymupdf.open(pdf)
        for name in sorted(os.listdir(os.path.join(root, bk, "truth"))):
            if not name.endswith(".json"):
                continue
            with open(os.path.join(root, bk, "truth", name),
                      encoding="utf-8") as f:
                t = json.load(f)
            ab = [b for b in t["blocks"] if b["label"] in arte]
            pr = _side_pairs(ab)
            if not pr:
                continue
            i = t["index"]
            if not 0 <= i < src.page_count:
                raise SubsetError(f"{bk}: страницы {i} нет в {pdf}")
            doc.insert_pdf(src, from_page=i, to_page=i)
            t["index"] = len(kept)
            t["meta"] = _carry_meta(t, {"из книги": bk,
                                        "страница в книге": i,
                                        "пар бок о бок": len(pr)},
                                    f"{bk}/{name}")
            for key in TRAITS:
                traits[key][_trait_state(t["meta"], key)] += 1
            with open(os.path.join(tdir, f"{len(kept):04d}.json"), "w",
                      encoding="utf-8") as f:
                json.dump(t, f, ensure_ascii=False)
            kept.append((bk, i))
            per_book[bk] = per_book.get(bk, 0) + 1
            pairs_total += len(pr)
        src.close()
    if not kept:
        raise SubsetError("ни одной страницы не отобрано")
    pdf = os.path.join(out_dir, "hard.pdf")
    doc.save(pdf, garbage=3, deflate=True)
    doc.close()
    man = {"книга": "hard", "о книге": "выжимка: два артефакта одного ярлыка "
                                       "бок о бок в истине",
           "страниц": len(kept), "пар бок о бок": pairs_total,
           "по книгам": per_book, "страницы": [{"книга": b, "стр": i}
                                               for b, i in kept],
           # Состояние признаков — часть паспорта выжимки. По нему видно, что
           # на ней МОЖНО померить, ещё до первого запуска `books score`.
           "признаки истины": traits,
           "pdf": os.path.basename(pdf), "sha256 pdf": _sha256(pdf)}
    with open(os.path.join(out_dir, "manifest.json"), "w",
              encoding="utf-8") as f:
        json.dump(man, f, ensure_ascii=False, indent=1)
    log(f"страниц {len(kept)} ({per_book}), пар бок о бок {pairs_total}")
    # ВЕЛИЧИНА, А НЕ СЛОВО «перенесено». Строка ниже — единственное место, где
    # видно, что выжимка донесла признаки; молчание тут уже стоило нам 73%,
    # напечатанных из ничего.
    for key, st in traits.items():
        log(f"признак «{key}»: да {st['да']}, нет {st['нет']}, "
            f"НЕ СКАЗАН {st['не сказано']} из {len(kept)} страниц"
            + (f" — на этих {st['не сказано']} метрика по нему считаться НЕ "
               f"БУДЕТ и обязана печатать «НЕ СВЕРЯЕТСЯ»"
               if st["не сказано"] else ""))
    log(f"{pdf} ({os.path.getsize(pdf)/1e6:.0f} МБ), истина в {tdir}")
    return man
