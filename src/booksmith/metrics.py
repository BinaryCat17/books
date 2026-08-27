"""Метрики контуров: насколько верно модель обвела таблицы, рисунки, графики.

Три числа, и они РАЗДЕЛЬНЫЕ. Одно сводное лечится подгонкой одной беды за
счёт другой и потому ничего не говорит:

1. **локализация** — слепая к ярлыку: нашлась ли рамка там, где артефакт;
2. **путаница ярлыков** — на найденных: назвала ли модель таблицу таблицей;
3. **порядок чтения** — на найденных: тот ли номер получил блок.

К ним — ИМЕННЫЕ счётчики бед. Без них «нашлось 0 из 3» читается как «модель
их не видит», а модель видит и склеивает в одну рамку: беда другая и цена
другая. Каждый недобор обязан быть назван по имени, иначе отчёт врёт
умолчанием.

ЧТО ЗДЕСЬ УЖЕ БЫЛО СЛОМАНО, И ПОЧЕМУ ОБ ЭТОМ НАПИСАНО В ШАПКЕ.

* **Затвор по IoU был мёртв по построению.** При двустороннем покрытии `c`
  площади ограничены сверху, и IoU не может быть ниже `c/(2-c)`: при c=0.75
  это 0.6. Порог `IOU_MATCH = 0.5` не срабатывал НИКОГДА. Перебор от 0.01 до
  0.8 давал одно и то же «найдено 36» — то есть прогон выглядел проверенным
  на чувствительность к порогу, а порог не был подключён. Теперь затвор один
  и назван: двустороннее покрытие. IoU остался только тем, чем он полезен, —
  ранжированием кандидатов.

* **Пустой список кандидатов проходил порог.** `max(cand, default=(0.0, -1))`
  при пустом `cand` давал `(0.0, -1)`, и `mb[-1]` сшивал истину с ПОСЛЕДНЕЙ
  рамкой страницы, к ней не относящейся. Ровно эту ветку включала мутация
  «пороги обнулены»: она печатала 100% и рапортовала «выросло», хотя выросло
  от ошибки индекса, а не от снятия порога. На стенде `ветхий`, где у одной
  страницы артефактных рамок нет вовсе, та же строка роняла всю батарею
  IndexError на шестой пробе из девяти — и отчёт обрывался, не дойдя до
  остальных. Проба, обязанная уметь провалиться, не умела ни провалиться, ни
  доработать до конца.

ПРО СПОСОБНОСТЬ ПРОВАЛИТЬСЯ. `mutations()` кормит метрику заведомо порченым
входом и требует, чтобы число просело. Порча трёхсторонняя: вывод модели,
ИСТИНА (метрика, безразличная к истине, меряет один свой вход) и СВОИ
пороги — каждый порознь, потому что двинутые разом они прячут инертный.
"""
import hashlib
import json
import os

from . import policy

# Затвор совпадения. ОДИН, и он назван: рамка модели обязана накрыть истину
# (не срез) и сама лежать внутри неё (не разлив). Проверено на стенде: таблица
# через корешок разорвана надвое, левая половина давала IoU 0.51 и проходила
# как «найдено», хотя половины таблицы в ней нет.
COVER_MATCH = 0.75
# Ниже этой доли перекрытия рамки считаются вовсе не пересекающимися: доля
# нужна, чтобы касание углом не считалось «моделью видит».
TOUCH = 0.10
# Допуск по КРАЮ, в пикселях растра. Доля площади на мелком блоке врёт: у
# колонцифры 24x12 модель отдала [485,83,514,100] против истины
# [488,86,512,98] — расхождение по три пикселя на сторону, на глаз то же
# место, а покрытие 0.58 при пороге 0.75, и в отчёте стояло «найдено 0 из 11».
# Поэтому совпадением считается ЛИБО двустороннее покрытие, ЛИБО совпадение
# всех четырёх краёв в пределах допуска.
TOL_PX = 6.0
# ЕДИНИЦЫ: пиксели растра, в которых записаны и истина, и вывод модели, то
# есть при PAGE_DPI. Поднимут PAGE_DPI вдвое — допуск станет вдвое строже, и
# число сдвинется без единой правки метрики. Доля страницы была бы честнее,
# но на мелких блоках доля и подвела; здесь выбрано «строго и заметно».


class MetricError(RuntimeError):
    pass


def _load(d):
    if not os.path.isdir(d):
        raise MetricError(f"нет каталога {d}")
    out = {}
    for name in sorted(os.listdir(d)):
        if name.endswith(".json") and name != "run.json":
            with open(os.path.join(d, name), encoding="utf-8") as f:
                p = json.load(f)
            if "blocks" not in p or "index" not in p:
                raise MetricError(f"{name}: не похоже на страницу разметки")
            out[int(p["index"])] = p
    if not out:
        raise MetricError(f"в {d} нет страниц разметки")
    return out


def _same_book(truth_dir: str, detect_dir: str) -> str:
    """Про один ли PDF истина и вывод модели.

    Без этой сверки `books score` спокойно считает истину одной книги против
    рамок другой и печатает осмысленное число. Оба слепка хранят sha256
    исходного PDF — сверяем их, а не имена каталогов.
    """
    man = os.path.join(os.path.dirname(truth_dir.rstrip("/")), "manifest.json")
    run = os.path.join(os.path.dirname(detect_dir.rstrip("/")), "run.json")
    if not (os.path.exists(man) and os.path.exists(run)):
        return "sha256 не сверен: нет manifest.json или run.json рядом"
    with open(man, encoding="utf-8") as f:
        a = json.load(f).get("sha256 pdf")
    with open(run, encoding="utf-8") as f:
        b = (json.load(f).get("исходник") or {}).get("sha256")
    if not (a and b):
        return "sha256 не сверен: поля нет в слепке"
    if a != b:
        raise MetricError(
            f"истина и вывод модели про РАЗНЫЕ книги: sha256 {a[:12]} против "
            f"{b[:12]}. Число тут вышло бы осмысленным на вид и бессмысленным "
            f"по существу.")
    return f"sha256 сверен: {a[:12]}"


def _inter(a, b):
    x0, y0 = max(a[0], b[0]), max(a[1], b[1])
    x1, y1 = min(a[2], b[2]), min(a[3], b[3])
    return max(0.0, x1 - x0) * max(0.0, y1 - y0)


def _area(a):
    return max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])


def iou(a, b):
    i = _inter(a, b)
    u = _area(a) + _area(b) - i
    return 0.0 if u <= 0 else i / u


def cover(a, b):
    """Какая доля `a` накрыта `b`. Двусторонняя пара cover(t,m)/cover(m,t)
    отличает срез (первая мала) от разлива (мала вторая)."""
    s = _area(a)
    return 0.0 if s <= 0 else _inter(a, b) / s


def _pad(b, d):
    return (b[0] - d, b[1] - d, b[2] + d, b[3] + d)


def matches(t_box, m_box) -> bool:
    """Совпадение: двустороннее покрытие, считанное С ДОПУСКОМ ПО КРАЮ.

    Допуск входит в покрытие, а не стоит отдельной веткой «все четыре края в
    пределах TOL_PX». Отдельная ветка давала ОБРЫВ: пара, у которой края
    расходились на 4-5 пикселей, проходила по допуску, а от сдвига ещё на три
    выпадала сразу в покрытие — и на книге формул сдвиг вывода модели на ТРИ
    пикселя ронял долю с 70% до 59%. Метрика, дрожащая от пиксельного
    дрожания, объявит дефектом любой прогон.
    """
    return (cover(t_box, _pad(m_box, TOL_PX)) >= COVER_MATCH
            and cover(m_box, _pad(t_box, TOL_PX)) >= COVER_MATCH)


def _pick(b, boxes, used):
    """Лучший непойманный кандидат к блоку `b`, или None.

    Пустой список кандидатов ОБЯЗАН давать None. Прежняя редакция отдавала
    `(0.0, -1)` и брала `boxes[-1]`.
    """
    cand = [(iou(b["box"], x["box"]), j) for j, x in enumerate(boxes)
            if j not in used and matches(b["box"], x["box"])]
    if not cand:
        return None
    return max(cand)[1]


def _diagnose(t, mine, others_truth, arte):
    """Назвать беду по имени. Порядок ветвей — от определённой к общей."""
    touching = [m for m in mine if cover(t["box"], m["box"]) >= TOUCH
                or cover(m["box"], t["box"]) >= TOUCH]
    if not touching:
        return "не увидел"
    best = max(touching, key=lambda m: iou(t["box"], m["box"]))
    ct, cm = cover(t["box"], best["box"]), cover(best["box"], t["box"])
    eaten = [o for o in others_truth
             if o is not t and cover(o["box"], best["box"]) >= 0.6]
    if eaten and ct >= 0.6:
        return "слияние"
    # Дробление — только АРТЕФАКТНЫМИ рамками. Прежняя редакция набирала его
    # из текстовых, и «модель не увидела таблицу, но покрыла её текстом»
    # получало имя самой дешёвой беды вместо самой дорогой.
    inside = [m for m in touching if m["label"] in arte
              and cover(m["box"], t["box"]) >= 0.7]
    if len(inside) >= 2:
        return "дробление"
    if policy.role(best["label"]) == "текст" and ct >= 0.6:
        return "съеден текстом"
    if ct < 0.85 and cm >= 0.85:
        return "срез"
    if cm < 0.6:
        return "разлив"
    return "рядом, но не совпал"


def compare(truth_dir: str, detect_dir: str) -> dict:
    """Сверить вывод модели с истиной. Возвращает числа и именные счётчики."""
    note = _same_book(truth_dir, detect_dir)
    res = compare_pages(_load(truth_dir), _load(detect_dir))
    res["книга"] = note
    return res


def compare_pages(T: dict, M: dict) -> dict:
    missing = sorted(set(T) - set(M))
    if missing:
        raise MetricError(
            f"модель не разметила страницы {missing[:5]}: сверять нечего. "
            f"Пустой отчёт тут выглядел бы как «совпало ноль», а это другое.")

    arte = set(policy.artefacts())
    per_case, conf, ranks = {}, {}, []
    tot = {"артефактов": 0, "найдено": 0}
    txt = {"блоков": 0, "найдено": 0}
    # Полнота по КАЖДОМУ ярлыку истины. Без неё отчёт молчал о трёх четвертях
    # блоков: «текста 94%» — одно число на тринадцать разных ярлыков, и
    # `header` при нуле находок в нём неотличим от `text` при полной.
    per_label = {}
    beds = {}
    for i, t in sorted(T.items()):
        m = M[i]
        case = t.get("meta", {}).get("случай", str(i))
        tb = [b for b in t["blocks"] if b["label"] in arte]
        mb = [b for b in m["blocks"] if b["label"] in arte]
        mall = m["blocks"]
        used, pairs = set(), []
        for b in tb:
            j = _pick(b, mb, used)
            if j is None:
                pairs.append((b, None))
            else:
                used.add(j)
                pairs.append((b, mb[j]))
        found = sum(1 for _, x in pairs if x is not None)
        c = per_case.setdefault(case, {"артефактов": 0, "найдено": 0,
                                       "беды": {}})
        c["артефактов"] += len(tb)
        c["найдено"] += found
        tot["артефактов"] += len(tb)
        tot["найдено"] += found

        def bed(name, n=1):
            c["беды"][name] = c["беды"].get(name, 0) + n
            beds[name] = beds.get(name, 0) + n

        for b, x in pairs:
            if x is None:
                bed(f"{_diagnose(b, mall, tb, arte)} ({b['label']})")
        # Артефактные рамки модели без пары в истине. Вложенный дубль —
        # отдельная беда: сырой вывод хранится без подавления, и рамка внутри
        # уже засчитанной это НЕ выдумка модели на пустом месте.
        for j, x in enumerate(mb):
            if j in used:
                continue
            if any(cover(x["box"], b["box"]) >= 0.9 for b in tb):
                bed("вложенный дубль")
            else:
                bed("лишняя рамка")

        # Проход Б: сличение ВСЕХ блоков, слепое к ярлыку. Порядок чтения по
        # одним артефактам не считается: их на странице бывает один, и число
        # выходило из пяти пар на весь стенд.
        page_ranks, taken = [], set()
        for b in sorted(t["blocks"], key=lambda z: -_area(z["box"])):
            j = _pick(b, mall, taken)
            if j is None:
                continue
            taken.add(j)
            x = mall[j]
            conf[(b["label"], x["label"])] = conf.get((b["label"], x["label"]), 0) + 1
            page_ranks.append((b["order"], x["order"]))
            if b["label"] not in arte:
                txt["найдено"] += 1
            per_label.setdefault(b["label"], [0, 0])[0] += 1
        for b in t["blocks"]:
            per_label.setdefault(b["label"], [0, 0])[1] += 1
        txt["блоков"] += len([b for b in t["blocks"] if b["label"] not in arte])
        # Порядок чтения сверяется ВНУТРИ страницы: ранг модели — номер строки
        # в её выводе по этой странице, у следующей он начинается с другого
        # числа. Сложенные в один список, они дали 33% согласия — «хуже
        # монетки», то есть признак не модели, а сравнения через страницу.
        ranks.append(page_ranks)

    tot["доля"] = (tot["найдено"] / tot["артефактов"]) if tot["артефактов"] else 0.0
    txt["доля"] = (txt["найдено"] / txt["блоков"]) if txt["блоков"] else 0.0
    return {"итого": tot, "текст и служебное": txt, "по случаям": per_case,
            "по ярлыкам": {k: {"истина": v[1], "найдено": v[0],
                               "разряд": policy.role(k)}
                           for k, v in sorted(per_label.items())},
            "беды": dict(sorted(beds.items())),
            "путаница ярлыков": {f"{a}->{b}": n for (a, b), n in sorted(conf.items())},
            "порядок": _order(ranks)}


def _order(by_page) -> dict:
    """Доля согласованных пар по порядку чтения, страница за страницей."""
    ok = bad = 0
    for pairs in by_page:
        n = len(pairs)
        for i in range(n):
            for j in range(i + 1, n):
                a = pairs[i][0] - pairs[j][0]
                b = pairs[i][1] - pairs[j][1]
                if a == 0 or b == 0:
                    continue
                ok += (a > 0) == (b > 0)
                bad += (a > 0) != (b > 0)
    return {"пар": ok + bad, "согласовано": ok / (ok + bad) if ok + bad else None}


def label_errors(res: dict) -> int:
    return sum(n for k, n in res["путаница ярлыков"].items()
               if k.split("->")[0] != k.split("->")[1])


def report(res: dict, log=print) -> None:
    if res.get("книга"):
        log(res["книга"])
    t, x = res["итого"], res["текст и служебное"]
    log(f"артефактов {t['артефактов']}, найдено {t['найдено']} "
        f"({t['доля']*100:.0f}%)")
    for why, n in res["беды"].items():
        log(f"  {why}: {n}")
    # Текст и служебное — три четверти блоков истины. Без этой строки они не
    # входили НИ В ОДНО печатаемое число, то есть стенд молчал о 337 блоках
    # из 382 и выглядел при этом полным.
    log(f"текст и служебное: блоков {x['блоков']}, найдено {x['найдено']} "
        f"({x['доля']*100:.0f}%)")
    miss = {k: v for k, v in res["по ярлыкам"].items()
            if v["найдено"] < v["истина"]}
    if miss:
        log("  недобор по ярлыкам: " + ", ".join(
            f"{k} {v['найдено']}/{v['истина']}" for k, v in miss.items()))
    o = res["порядок"]
    log(f"порядок чтения: пар {o['пар']}, согласовано "
        + ("—" if o["согласовано"] is None else f"{o['согласовано']*100:.0f}%"))
    bad = {k: v for k, v in res["путаница ярлыков"].items()
           if k.split("->")[0] != k.split("->")[1]}
    log(f"путаница ярлыков: {label_errors(res)} из "
        f"{sum(res['путаница ярлыков'].values())} пар"
        + (f" — {bad}" if bad else ""))
    for case, c in sorted(res["по случаям"].items(),
                          key=lambda kv: (kv[1]["найдено"] - kv[1]["артефактов"])):
        if c["найдено"] < c["артефактов"] or c["беды"]:
            log(f"  {case:24s} {c['найдено']}/{c['артефактов']}  "
                + ", ".join(f"{k} {v}" for k, v in sorted(c["беды"].items())))


# --------------------------------------------------------------- мутации
# Число, которое не умеет упасть, ничего не меряет. Батарея кормит метрику
# заведомо порченым входом и требует, чтобы число просело.
#
# ПОРЧА ТРЁХСТОРОННЯЯ, и это не педантизм:
#  * вывод модели — очевидная сторона;
#  * ИСТИНА — метрика, безразличная к истине, меряет один свой вход и всегда
#    будет «права»;
#  * СВОИ пороги, каждый ПОРОЗНЬ. Прежняя редакция двигала оба разом, и
#    инертный порог был неотличим от рабочего: `IOU_MATCH` не срабатывал
#    никогда, а батарея девять пробегов подряд рапортовала «упало».

def _map_boxes(M, fn):
    return {i: {**p, "blocks": [{**b, "box": list(fn(b["box"]))}
                                for b in p["blocks"]]} for i, p in M.items()}


def _shift(M, dx, dy):
    return _map_boxes(M, lambda b: (b[0] + dx, b[1] + dy, b[2] + dx, b[3] + dy))


def _shift_rel(M, frac):
    """Сдвиг НА ДОЛЮ размера рамки, а не на постоянные сорок пикселей.

    Постоянный сдвиг ничего не проверяет на крупных артефактах: рамка
    900x400, сдвинутая на 40, накрывает истину на 96% и проходит порог. На
    книге, где артефакты крупные, проба «сдвиг на 40» рапортовала «НЕ УПАЛО»
    — и была права: упасть было не с чего.
    """
    def g(b):
        d = frac * max(4.0, min(b[2] - b[0], b[3] - b[1]))
        return (b[0] + d, b[1] + d, b[2] + d, b[3] + d)
    return _map_boxes(M, g)


def _grow(M, f):
    def g(b):
        cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
        w, h = (b[2] - b[0]) * f / 2, (b[3] - b[1]) * f / 2
        return (cx - w, cy - h, cx + w, cy + h)
    return _map_boxes(M, g)


def _only(M, keep):
    return {i: {**p, "blocks": [b for b in p["blocks"] if keep(b)]}
            for i, p in M.items()}


def _relabel(M, fn):
    return {i: {**p, "blocks": [{**b, "label": fn(b["label"])} for b in p["blocks"]]}
            for i, p in M.items()}


def _reverse_order(M):
    out = {}
    for i, p in M.items():
        n = len(p["blocks"])
        out[i] = {**p, "blocks": [{**b, "order": n - 1 - j}
                                  for j, b in enumerate(p["blocks"])]}
    return out


def _duplicate(M):
    """Каждую рамку продублировать. Доля найденного расти НЕ должна."""
    return {i: {**p, "blocks": [c for b in p["blocks"] for c in (b, dict(b))]}
            for i, p in M.items()}


def _shuffle_pages(M):
    """Разметку сдвинуть на страницу вперёд по кругу: сверка идёт по индексу
    страницы, и подмена соседней обязана всё уронить."""
    keys = sorted(M)
    return {k: {**M[keys[(n + 1) % len(keys)]], "index": k}
            for n, k in enumerate(keys)}


def _merge_all(M, arte):
    """Все артефактные рамки страницы слить в одну описанную."""
    out = {}
    for i, p in M.items():
        a = [b for b in p["blocks"] if b["label"] in arte]
        rest = [b for b in p["blocks"] if b["label"] not in arte]
        if len(a) >= 2:
            box = [min(b["box"][0] for b in a), min(b["box"][1] for b in a),
                   max(b["box"][2] for b in a), max(b["box"][3] for b in a)]
            a = [{**a[0], "box": box}]
        out[i] = {**p, "blocks": rest + a}
    return out


def _split_all(M, arte):
    """Каждую артефактную рамку разрезать пополам по вертикали."""
    out = {}
    for i, p in M.items():
        bs = []
        for b in p["blocks"]:
            if b["label"] not in arte:
                bs.append(b)
                continue
            x0, y0, x1, y1 = b["box"]
            mid = (x0 + x1) / 2
            bs.append({**b, "box": [x0, y0, mid, y1]})
            bs.append({**b, "box": [mid, y0, x1, y1]})
        out[i] = {**p, "blocks": bs}
    return out


def _beds(res, prefix):
    return sum(n for k, n in res["беды"].items() if k.startswith(prefix))


def _multi(T, arte):
    """Есть ли страница, где артефактов истины больше одного: без такой
    страницы пробу на слияние ставить не на чем."""
    return any(sum(1 for b in p["blocks"] if b["label"] in arte) > 1
               for p in T.values())


def _found_label(T, M, label):
    """Нашлась ли хоть одна пара по этому ярлыку: иначе переименование его
    ничего не двинет, и «не выросло» скажет о книге, а не о метрике."""
    res = compare_pages(T, M)
    return any(k.startswith(f"{label}->") and n
               for k, n in res["путаница ярлыков"].items())


def _ceiling(T, M, arte):
    """Потолок доли: сколько артефактов истины вообще имеют кандидата у
    модели. Когда доля уже на потолке, ослабление порогов поднять её не
    может, и «не выросло» — свойство книги, а не метрики."""
    tot = hit = 0
    for i, t in T.items():
        mb = [b for b in M[i]["blocks"] if b["label"] in arte]
        tb = [b for b in t["blocks"] if b["label"] in arte]
        tot += len(tb)
        hit += min(len(tb), len(mb))
    return (hit / tot) if tot else 1.0


def mutations(truth_dir: str, detect_dir: str, log=print) -> int:
    """Прогнать батарею. Возвращает число НЕ пойманных порч (0 — метрика жива)."""
    global COVER_MATCH, TOUCH, TOL_PX
    T, M = _load(truth_dir), _load(detect_dir)
    arte = set(policy.artefacts())
    base = compare_pages(T, M)
    b_found = base["итого"]["доля"]
    b_text = base["текст и служебное"]["доля"]
    b_ord = base["порядок"]["согласовано"]
    b_lab = label_errors(base)
    b_merge, b_split = _beds(base, "слияние"), _beds(base, "дробление")
    log(f"исходно: артефактов {b_found*100:.0f}%, текста {b_text*100:.0f}%, "
        f"порядок {b_ord*100:.0f}%, ошибок ярлыка {b_lab}, "
        f"слияний {b_merge}, дроблений {b_split}")

    def R(mm=None, tt=None):
        return compare_pages(tt or T, mm or M)

    def found(mm=None, tt=None):
        return R(mm, tt)["итого"]["доля"]

    # Проба, которой не за что зацепиться на этой книге, — НЕ провал, а
    # «нет данных». Ноль от проверки и ноль от непонимания — разные нули:
    # «слияний не стало больше» на книге, где артефакты по одному на
    # страницу и слить нечего, ничего не говорит о метрике. Такие пробы
    # возвращают None и печатаются отдельной пометкой.
    probes = [
        # --- порча вывода модели
        ("сдвиг рамок на треть их размера", "упало",
         lambda: found(_shift_rel(M, 0.34)) < b_found),
        ("рамки раздуты в 1.5 раза (разлив)", "упало",
         lambda: found(_grow(M, 1.5)) < b_found),
        ("рамки сжаты в 0.6 раза (срез)", "упало",
         lambda: found(_grow(M, 0.6)) < b_found),
        ("артефакты выкинуты вовсе", "ноль",
         lambda: found(_only(M, lambda b: b["label"] not in arte)) == 0.0),
        ("артефакты названы текстом", "ноль",
         lambda: found(_relabel(M, lambda l: "text" if l in arte else l)) == 0.0),
        ("рамки продублированы", "не выросло",
         lambda: found(_duplicate(M)) <= b_found),
        ("разметка сдвинута на страницу", "упало",
         lambda: found(_shuffle_pages(M)) < b_found),
        ("порядок чтения перевёрнут", "упало",
         lambda: R(_reverse_order(M))["порядок"]["согласовано"] < b_ord),
        # --- порча, целящая в ИМЕННЫЕ счётчики
        ("артефакты страницы слиты в один", "слияний больше",
         lambda: None if not _multi(T, arte)
                 else _beds(R(_merge_all(M, arte)), "слияние") > b_merge),
        ("каждый артефакт разрезан пополам", "дроблений больше",
         lambda: _beds(R(_split_all(M, arte)), "дробление") > b_split),
        # --- порча, целящая в ПУТАНИЦУ ЯРЛЫКОВ (вторая из трёх величин)
        ("таблицы названы графиками", "ошибок ярлыка больше",
         lambda: None if not _found_label(T, M, "table")
                 else label_errors(R(_relabel(
                     M, lambda l: "chart" if l == "table" else l))) > b_lab),
        ("таблицы названы графиками", "локализация НЕ изменилась",
         lambda: found(_relabel(M, lambda l: "chart" if l == "table" else l)) == b_found),
        # --- порча ИСТИНЫ: метрика обязана смотреть на оба входа
        ("истина сдвинута на треть размера рамки", "упало",
         lambda: found(tt=_shift_rel(T, 0.34)) < b_found),
        ("истина раздута в 1.5 раза", "упало",
         lambda: found(tt=_grow(T, 1.5)) < b_found),
        ("текст и служебное выкинуты из истины", "текста ноль",
         lambda: R(tt=_only(T, lambda b: b["label"] in arte))
                 ["текст и служебное"]["доля"] == 0.0),
    ]
    bad = 0
    for name, want, probe in probes:
        ok = probe()
        mark = "нет данных" if ok is None else ("ok " if ok else "НЕТ")
        log(f"  {mark:>10}  {name}: {want}")
        bad += ok is False

    # --- порча СВОИХ порогов, каждого ПОРОЗНЬ
    keep_c, keep_t, keep_p = COVER_MATCH, TOUCH, TOL_PX
    try:
        TOL_PX = 0.0
        COVER_MATCH = 0.0
        loose = compare_pages(T, M)["итого"]["доля"]
        COVER_MATCH = 0.99
        tight = compare_pages(T, M)["итого"]["доля"]
        COVER_MATCH = keep_c
        TOL_PX = 1e6
        wide = compare_pages(T, M)["итого"]["доля"]
        TOL_PX = keep_p
        TOUCH = 1.01
        blind = _beds(compare_pages(T, M), "не увидел")
    finally:
        COVER_MATCH, TOUCH, TOL_PX = keep_c, keep_t, keep_p
    base_blind = _beds(base, "не увидел")
    for name, ok, why in (
            (f"COVER_MATCH=0 ({loose*100:.0f}% против {b_found*100:.0f}%)",
             None if b_found >= _ceiling(T, M, arte) else loose > b_found,
             "выросло"),
            (f"COVER_MATCH=0.99 ({tight*100:.0f}% против {b_found*100:.0f}%)",
             tight < b_found, "упало"),
            (f"TOL_PX=10^6 ({wide*100:.0f}% против {b_found*100:.0f}%)",
             None if b_found >= _ceiling(T, M, arte) else wide > b_found,
             "выросло"),
            (f"TOUCH=1.01 (не увидел {blind} против {base_blind})",
             blind > base_blind, "бед «не увидел» больше")):
        mark = "нет данных" if ok is None else ("ok " if ok else "НЕТ")
        log(f"  {mark:>10}  {name}: {why}")
        bad += ok is False

    # --- малая порча ловиться НЕ должна
    tiny = found(_shift(M, 3, 3))
    ok = tiny == b_found
    log(f"  {'ok ' if ok else 'НЕТ'}  сдвиг на 3 пикселя: не шелохнулось "
        f"({tiny*100:.0f}% против {b_found*100:.0f}%)")
    bad += not ok

    log("чего эта батарея НЕ ловит: неверную ИСТИНУ (против неё только глаза "
        "и `books overlay`); неверный перевод координат моделью (истина и "
        "вывод сверяются друг с другом, а не с растром); подмену книги при "
        "отсутствии слепка рядом; ошибку ярлыка ВНУТРИ разряда, если она "
        "одинакова у истины и модели.")
    log(f"не пойманных порч: {bad}")
    return bad
