"""Счёт на арендованной машине: рамки макета от dots.ocr, страница за страницей.

ЧТО ЗДЕСЬ ОБЯЗАНО ПАДАТЬ, А НЕ МОЛЧАТЬ. Пустой ответ модели, ответ, из
которого не разбирается JSON, координаты вне листа, категория вне словаря.
Каждый такой случай прежде дал бы «страница без рамок» — то есть выглядел бы
дефектом модели, будучи нашим.

РЕЗУЛЬТАТ ПИШЕТСЯ ПОСТРАНИЧНО, а не в конце: падение на 90-й странице из 130
должно оставлять 90 страниц. Каталог `outputs` синхронизируется к нам по ходу
работы, поэтому уже посчитанное доедет, даже если машина погибнет.

ДРЕЙФ. При `--repeats N` те же страницы считаются N раз, и каждый проход
пишется в свой каталог. Сравнение делается ДОМА, а не здесь: считать разницу
на карте значило бы платить за арифметику по цене видеопамяти.
"""
import argparse
import json
import os
import re
import sys
import time

PROMPT = (
    "Please output the layout information from this PDF image, including each "
    "layout's bbox and its category. The bbox should be in the format "
    "[x1, y1, x2, y2]. The layout categories for the PDF document include "
    "['Caption', 'Footnote', 'Formula', 'List-item', 'Page-footer', "
    "'Page-header', 'Picture', 'Section-header', 'Table', 'Text', 'Title']. "
    "Do not output the corresponding text. The layout result should be in "
    "JSON format.")
LABELS = {"Caption", "Footnote", "Formula", "List-item", "Page-footer",
          "Page-header", "Picture", "Section-header", "Table", "Text", "Title"}
DPI = 144.0


def log(*a):
    print(f"[{time.strftime('%H:%M:%S')}]", *a, flush=True)


def parse_pages(spec, n):
    """`--pages 1,4,7-9` -> индексы страниц, считая ВХОД С ЕДИНИЦЫ.

    Нумерация та же, что у `--pages` в `books detect` (`parse_pages` в
    `src/booksmith/detect.py`). Прежде здесь был свой счёт, с нуля: одна и та
    же строка `1,4,7-9` означала в двух командах проекта разные страницы
    (`[1,4,7,8,9]` здесь против `[0,3,6,7,8]` там), а `--pages 130` на книге
    в 130 страниц отсюда отказывал. Расхождение молчаливое: просят не ту
    страницу и получают полный правдоподобный ответ, не отличимый от верного.

    Индекс, который уходит в имя файла и в поле `index`, как был с нуля, так
    и остаётся: истина стендов лежит в `0000.json`, и перевод делается только
    здесь, на границе аргумента.

    Разбор ПОВТОРЁН, а не позаимствован: на арендованную машину уезжают
    четыре файла (`inputs` в `spec()` соседнего `__init__.py`), пакета
    booksmith там нет. СТОРОЖА У ЭТИХ ДВУХ КОПИЙ НЕТ: батарея
    `books score --selfcheck` меряет контуры, сверке двух разборов там не
    место, а иного места для проб в дереве пока не заведено. Значит,
    расхождение поймает только человек: правка здесь обязана повторяться в
    `detect.parse_pages`, и наоборот. Сверка ручная — обе функции на входах
    «1», «1,4,7-9», «130», «2-4» обязаны дать одно и то же, а на «0»,
    «0-9», «3-1» отказать обе.

    Ноль как номер — отказ вслух, а не тихий сдвиг на страницу: так падает
    старая привычка `--pages 0-9`. Пустой диапазон (`3-1`) — тоже отказ: он
    дал бы ноль страниц при коде возврата 0, то есть пустая аренда выглядела
    бы успешной.
    """
    if not spec or spec == "-":
        log(f"страницы: вся книга, {n} шт.")
        return list(range(n))
    want = []
    for part in str(spec).split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part[1:]:
            a, b = part.split("-", 1)
            rng = range(int(a), int(b) + 1)
            if not rng:
                raise SystemExit(
                    f"диапазон «{part}» пуст: конец раньше начала")
            want.extend(rng)
        else:
            want.append(int(part))
    if 0 in want:
        raise SystemExit(
            f"«{spec}»: страницы считаются С ЕДИНИЦЫ, как в `books detect` — "
            f"первая страница книги это 1, нулевой нет. Прежде здесь был счёт "
            f"с нуля, и та же строка означала другие страницы.")
    bad = [p for p in want if not 1 <= p <= n]
    if bad:
        raise SystemExit(f"в книге {n} страниц, а запрошены {bad}")
    if not want:
        raise SystemExit(f"набор страниц «{spec}» пуст — считать нечего")
    idxs = [p - 1 for p in sorted(set(want))]
    # В журнал — величину, а не «понял»: что именно вышло из строки, видно ДО
    # того, как карта начнёт тикать.
    log(f"страницы «{spec}» поняты с единицы: {len(idxs)} шт., "
        f"с {idxs[0]+1}-й по {idxs[-1]+1}-ю (индексы {idxs[0]}..{idxs[-1]})")
    return idxs


def extract(text):
    """Разобрать ответ модели в список рамок.

    Неразбираемый ответ — ошибка вслух. ПУСТОЙ СПИСОК ошибкой не считается:
    страница без рамок бывает настоящей, и падать на ней значило бы судить
    за модель. Считает такие страницы `tally`, порознь от неразобранных.
    """
    t = text.strip()
    m = re.search(r"```(?:json)?\s*(.+?)```", t, re.S)
    if m:
        t = m.group(1).strip()
    i, j = t.find("["), t.rfind("]")
    if i < 0 or j <= i:
        raise ValueError(f"в ответе нет списка JSON: {t[:200]!r}")
    data = json.loads(t[i:j + 1])
    if not isinstance(data, list):
        raise ValueError(f"разобрался не список, а {type(data).__name__}")
    return data


def tally(pages, boxes, empty, bad):
    """Итог прохода ВЕЛИЧИНАМИ: сколько рамок модель вообще отдала.

    Без числа рамок журнал врал успехом. Пустой список — законный ответ
    модели («на странице нет рамок»), поэтому `extract` на нём не падает и
    страница НЕ попадает в неразобранные. Замер на подставном выводе: 130
    страниц, на каждой `[]`, — прежний журнал печатал «130 страниц,
    неразобранных 0» и код возврата 0, то есть нулевой улов за целую
    аренду был неотличим от полного успеха.

    Ноль пустой страницы и ноль неразобранной — РАЗНЫЕ нули, поэтому
    считаются порознь; а где делить не на что, печатается «нет данных», а
    не 0.0 рамок на страницу.
    """
    ok = pages - bad
    s = (f"{pages} страниц, рамок {boxes}, пустых страниц {empty}, "
         f"неразобранных {bad}, "
         + (f"рамок на разобранную {boxes/ok:.1f}" if ok
            else "рамок на разобранную нет данных"))
    if pages and not boxes:
        # Судить, отказ это или вправду пустая подборка страниц, отсюда
        # нечем: `--pages 5` на чистом листе даёт законный ноль. Поэтому
        # величина кричит, а решение остаётся дому.
        s = "НИ ОДНОЙ РАМКИ за весь проход. " + s
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("--pages", default="-")
    # ПОТОЛОК ПОДАЧИ. Страницы золотого стенда — до 4.9 мегапикселя, и
    # кодировщик зрения дал OutOfMemory на 5.42 ГиБ в одном софтмаксе. Это
    # не починка модели: ВСЕ детекторы стенда ужимают вход (800x800, 640x640,
    # 1024x768), просто у порождающей модели потолок задаётся числом
    # пикселей. Величина объявлена и уезжает в слепок прогона.
    ap.add_argument("--max-pixels", type=int,
                    default=int(os.environ.get("DOTS_MAX_PIXELS",
                                               1280 * 28 * 28)))
    a = ap.parse_args()

    import pymupdf
    import torch
    from PIL import Image
    from transformers import AutoModelForCausalLM, AutoProcessor

    log("гружу модель")
    t0 = time.time()
    # ИМЯ КАТАЛОГА БЕЗ ТОЧКИ. Грузить по имени репозитория нельзя: точка в
    # «dots.ocr» становится разделителем пакетов в загрузчике удалённого кода,
    # и относительный импорт внутри модели падает. Веса кладёт сюда
    # provision.sh; отсутствие каталога — отказ вслух, а не тихая попытка
    # скачать по имени.
    name = os.environ.get("DOTS_DIR", "/models/DotsOCR")
    if not os.path.isdir(name):
        raise SystemExit(
            f"нет каталога весов {name}: provision.sh должен был положить их "
            f"туда. Грузить по имени репозитория нельзя — точка в имени ломает "
            f"импорт удалённого кода.")
    model = AutoModelForCausalLM.from_pretrained(
        name, trust_remote_code=True, torch_dtype=torch.bfloat16,
        attn_implementation="sdpa", device_map="cuda")
    proc = AutoProcessor.from_pretrained(
        name, trust_remote_code=True,
        min_pixels=256 * 28 * 28, max_pixels=a.max_pixels)
    log(f"потолок подачи {a.max_pixels} пикселей "
        f"({a.max_pixels/1e6:.2f} Мпикс)")
    model.eval()
    log(f"модель поднята за {time.time()-t0:.0f} с")

    # ЛИШНИЕ КЛЮЧИ ПРОЦЕССОРА. `generate` сверяет переданное со своим
    # списком и падает ValueError, перечисляя лишнее. Отбирать по сигнатуре
    # `forward` НЕЛЬЗЯ: у dots.ocr она берёт **kwargs, фильтр выключается, и
    # прогон падает ровно так же — это уже стоило двух аренд. Поэтому читаем
    # имена из самой ошибки, запоминаем и повторяем. Отброшенное печатается
    # величиной: молча выкинуть чужой ключ значит кормить модель не тем.
    drop = set()

    # Запасной путь: если и после отбрасывания `generate` ругается, оставляем
    # ТОЛЬКО то, без чего порождение невозможно. Список короткий и известный
    # для зрительных моделей семейства Qwen2-VL, на котором собран dots.ocr.
    CORE = ("input_ids", "attention_mask", "pixel_values", "image_grid_thw")

    def generate(inputs, **kw):
        left = {k: v for k, v in inputs.items() if k not in drop}
        try:
            return model.generate(**left, **kw)
        except ValueError as e:
            m = re.search(r"not used by the model: \[(.*?)\]", str(e))
            if not m:
                raise
            bad = {t.strip().strip("'\"") for t in m.group(1).split(",")
                   if t.strip()}
            bad &= set(left)
            if not bad:
                raise
            drop.update(bad)
            log(f"  generate не принимает {sorted(bad)} — отбрасываю и повторяю")
            try:
                return model.generate(
                    **{k: v for k, v in left.items() if k not in drop}, **kw)
            except ValueError as e2:
                core = {k: v for k, v in inputs.items() if k in CORE}
                log(f"  и после этого ValueError ({e2}); оставляю только "
                    f"{sorted(core)}")
                if not core:
                    raise
                return model.generate(**core, **kw)

    doc = pymupdf.open(a.pdf)
    idxs = parse_pages(a.pages, doc.page_count)
    log(f"страниц в файле {doc.page_count}, считаю {len(idxs)}, "
        f"проходов {a.repeats}")

    tmp = os.path.join(a.out, "_page.png")
    for r in range(a.repeats):
        pdir = os.path.join(a.out, f"pass{r}", "pages")
        os.makedirs(pdir, exist_ok=True)
        bad = seen = empty = 0
        t_pass = time.time()
        for n, i in enumerate(idxs, 1):
            page = doc[i]
            page.get_pixmap(dpi=int(DPI)).save(tmp)
            im = Image.open(tmp).convert("RGB")
            w, h = im.size
            # Ужимаем САМИ, не полагаясь на процессор: рамки модели придут в
            # координатах поданной картинки, и обратный перевод должен быть
            # нашим и явным, а не угаданным.
            # ИМЯ scale, А НЕ k. Переменная цикла `for k, item in
            # enumerate(...)` ниже затирала коэффициент масштаба, и на первой
            # же рамке выходило деление на ноль: 36 страниц из 36 записались
            # как «неразобранные», хотя модель ответила безупречно.
            scale = 1.0
            if w * h > a.max_pixels:
                scale = (a.max_pixels / (w * h)) ** 0.5
                im = im.resize((max(1, int(w * scale)),
                                max(1, int(h * scale))))
                im.save(tmp)
            msg = [{"role": "user", "content": [
                {"type": "image", "image": tmp},
                {"type": "text", "text": PROMPT}]}]
            text = proc.apply_chat_template(msg, tokenize=False,
                                            add_generation_prompt=True)
            inputs = proc(text=[text], images=[im], return_tensors="pt")
            # Процессор кладёт больше ключей, чем принимает `generate`: у
            # dots.ocr это `mm_token_type_ids`, и прогон падал на первой же
            # странице ValueError. Отбираем ПО СИГНАТУРЕ самой модели, а не по
            # списку, набранному на глаз: список разойдётся с моделью на
            # следующей же её версии. Отброшенное печатается величиной — молча
            # выкинуть чужой ключ значит кормить модель не тем.
            inputs = {k: v.to("cuda") for k, v in inputs.items()}
            if n == 1 and r == 0:
                # Что вообще отдал процессор — величиной, один раз. Без этого
                # разбор чужого отказа стоит новой аренды.
                log(f"  процессор отдал ключи: {sorted(inputs)}")
            oom = False
            try:
                # Жадное декодирование, без семплирования: иначе к дрейфу
                # ядер добавился бы наш собственный, и разделить их было бы
                # нечем.
                with torch.inference_mode():
                    out = generate(inputs, max_new_tokens=4096,
                                   do_sample=False, temperature=None,
                                   top_p=None, top_k=None)
            except torch.OutOfMemoryError:
                # Одна страница не должна убивать прогон: остальные посчитаны
                # и уже доехали. Пропуск пишется В СТРАНИЦУ величиной, а не
                # молчаливым нулём рамок.
                torch.cuda.empty_cache()
                oom = True
                out = None
                log(f"  стр. {i}: не хватило видеопамяти, пропускаю")
            ans = "" if oom else proc.batch_decode(
                out[:, inputs["input_ids"].shape[1]:],
                skip_special_tokens=True)[0]

            blocks, err = [], None
            try:
                if oom:
                    raise RuntimeError("страница пропущена: не хватило "
                                       "видеопамяти")
                for k, item in enumerate(extract(ans)):
                    cat = item.get("category")
                    box = item.get("bbox")
                    if cat not in LABELS:
                        raise ValueError(f"категория {cat!r} вне словаря")
                    if not (isinstance(box, list) and len(box) == 4):
                        raise ValueError(f"рамка не из четырёх чисел: {box!r}")
                    x0, y0, x1, y1 = (float(v) / scale for v in box)
                    blocks.append({
                        "block_id": k, "box": [x0, y0, x1, y1],
                        "label": cat, "score": None,
                        # Порядок чтения у этой модели — ПОРЯДОК ПОРОЖДЕНИЯ, и
                        # это записано значением, а не выдано за ранг.
                        "order": k, "content": None, "kind": "none"})
            except Exception as e:
                err = f"{type(e).__name__}: {e}"
                bad += 1
            else:
                # Разбор удался — считаем, СКОЛЬКО рамок отдала модель.
                # Пустая страница здесь не ошибка, но и не успех.
                seen += len(blocks)
                if not blocks:
                    empty += 1

            with open(os.path.join(pdir, f"{i:04d}.json"), "w",
                      encoding="utf-8") as f:
                json.dump({"index": i, "width": w, "height": h, "dpi": DPI,
                           "blocks": blocks, "raw": {"ответ": ans},
                           "meta": {"распознаватель": "dots.ocr",
                                    "проход": r, "промт": "layout_only_en",
                                    "порядок чтения": "порядок порождения",
                                    "потолок подачи": a.max_pixels,
                                    "ужато": round(scale, 4),
                                    "нехватка видеопамяти": oom,
                                    "ошибка разбора": err}}, f,
                          ensure_ascii=False)
            if n % 10 == 0 or n == len(idxs):
                log(f"  проход {r}: {n}/{len(idxs)}, рамок {seen}, "
                    f"пустых {empty}, неразобранных {bad}, "
                    f"{time.time()-t_pass:.0f} с")
        log(f"проход {r} кончился: {tally(len(idxs), seen, empty, bad)}, "
            f"{time.time()-t_pass:.0f} с "
            f"({(time.time()-t_pass)/max(1,len(idxs)):.2f} с/страница)")
        if bad == len(idxs):
            log("НИ ОДНА страница не разобралась — это отказ, а не пустая книга")
            return 3
    doc.close()
    if os.path.exists(tmp):
        os.unlink(tmp)
    return 0


if __name__ == "__main__":
    sys.exit(main())
