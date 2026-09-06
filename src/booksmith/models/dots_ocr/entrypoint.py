"""Counting on the rented machine: dots.ocr layout boxes, page by page.

WHAT HERE MUST FALL RATHER THAN KEEP QUIET. An empty answer from the model, an
answer no JSON parses out of, coordinates off the sheet, a category outside
the vocabulary. Each would once have given "a page without boxes" -- looking
like a defect of the model while being ours.

THE RESULT IS WRITTEN PAGE BY PAGE, not at the end: a fall on page 90 of 130
must leave 90 pages. The `outputs` directory syncs to us as the work goes, so
what is already counted arrives even if the machine dies.

DRIFT. With `--repeats N` the same pages are counted N times, each pass into
its own directory. The comparison is made AT HOME, not here: counting the
difference on the card would pay video-memory prices for arithmetic.
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
    """`--pages 1,4,7-9` -> page indices, COUNTING THE INPUT FROM ONE.

    The numbering is the one `--pages` has in `books detect` (`parse_pages` in
    `src/booksmith/detect.py`). There used to be a count of its own here, from
    zero: the same string `1,4,7-9` meant different pages in two commands of
    the project (`[1,4,7,8,9]` here against `[0,3,6,7,8]` there), and
    `--pages 130` on a 130-page book was refused from here. A silent
    divergence: the wrong page is asked for, and a full plausible answer comes
    back, indistinguishable from the right one.

    The index that goes into the file name and into the `index` field stays
    zero-based as it was: the bench truth lies in `0000.json`, and the
    translation is done only here, at the edge of the argument.

    THE PARSING IS REPEATED, not borrowed: four files ride to the rented
    machine (`inputs` in `spec()` of the neighbouring `__init__.py`), the
    booksmith package not among them. `tests/test_parse_pages.py` holds the
    two copies together -- it loads THIS file by path and puts both through
    thirteen inputs -- so an edit here must be repeated in `detect.parse_pages`
    and back. The dash is the one lawful difference: it means the whole book
    HERE only (`run.sh` passes `${4:--}`), and the check holds that both ways.
    Before it there was no guard, and the copies did diverge; on which inputs
    stands at the space below.

    A zero as a number is a refusal out loud, not a quiet shift by one page:
    that is how the old habit `--pages 0-9` falls. An empty range (`3-1`) is a
    refusal too: it would give zero pages at exit code 0, so an empty rental
    would look like a success.
    """
    if not spec or spec == "-":
        log(f"страницы: вся книга, {n} шт.")
        return list(range(n))
    want = []
    # A SPACE SEPARATES JUST LIKE A COMMA, as in `detect.parse_pages`. It did
    # not here, and the copies diverged on four inputs of thirteen: "1 3" and
    # "1 4 7-9" gave pages there and a bare
    # `ValueError: invalid literal for int()` here, while "x" and "7-x" were
    # refused there with a sample and here by the same traceback. This is
    # parsed ON THE RENTED CARD, after the weights are unrolled: for money.
    for part in str(spec).replace(" ", ",").split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part[1:]:
            a, b = part.split("-", 1)
            try:
                rng = range(int(a), int(b) + 1)
            except ValueError:
                raise SystemExit(
                    f"в «--pages {spec}» диапазон «{part}» не разобран. "
                    f"Ожидается «7-9», счёт с единицы.")
            if not rng:
                raise SystemExit(
                    f"диапазон «{part}» пуст: конец раньше начала")
            want.extend(rng)
        else:
            try:
                want.append(int(part))
            except ValueError:
                raise SystemExit(
                    f"в «--pages {spec}» кусок «{part}» — не номер страницы. "
                    f"Ожидается «1,4,7-9» или «1 4 7-9», счёт с единицы.")
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
    # Into the log a quantity, not "understood": what came out of the string
    # is visible BEFORE the card starts ticking.
    log(f"страницы «{spec}» поняты с единицы: {len(idxs)} шт., "
        f"с {idxs[0]+1}-й по {idxs[-1]+1}-ю (индексы {idxs[0]}..{idxs[-1]})")
    return idxs


def extract(text):
    """Parse the model's answer into a list of boxes.

    An unparsable answer is an error out loud. AN EMPTY LIST is not counted an
    error: a page without boxes can be genuine, and falling on it would mean
    judging for the model. `main` counts such pages apart from the unparsed,
    and `tally` prints both.
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
    """The pass in QUANTITIES: how many boxes the model gave at all.

    Without a box count the log lied with success. An empty list is a lawful
    answer of the model ("there are no boxes on this page"), so `extract` does
    not fall on it and the page does NOT go among the unparsed. Measured on a
    stand-in output -- 130 pages, `[]` on each -- the old log printed "130
    pages, unparsed 0" and exit code 0, so a zero catch over a whole rental
    was indistinguishable from a full success.

    The zero of an empty page and the zero of an unparsed one are DIFFERENT
    zeroes, hence counted apart; and where there is nothing to divide by it
    prints "no data" instead of 0.0 boxes per page.
    """
    ok = pages - bad
    s = (f"{pages} страниц, рамок {boxes}, пустых страниц {empty}, "
         f"неразобранных {bad}, "
         + (f"рамок на разобранную {boxes/ok:.1f}" if ok
            else "рамок на разобранную нет данных"))
    if pages and not boxes:
        # There is nothing here to judge by whether this is a refusal or a
        # genuinely empty selection: `--pages 5` on a blank sheet gives a
        # lawful zero. So the quantity shouts and the decision stays at home.
        s = "НИ ОДНОЙ РАМКИ за весь проход. " + s
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("--pages", default="-")
    # THE INPUT CEILING. Golden-bench pages run to 4.9 megapixels, and the
    # vision encoder gave OutOfMemory on 5.42 GiB in a single softmax. Not
    # repairing the model: EVERY detector of the bench shrinks its input
    # (800x800, 640x640, 1024x768), only for a generative model the ceiling is
    # set by a pixel count. The value goes into each page's
    # `meta.input_pixel_ceiling`: this job writes no run snapshot, and
    # `DOTS_MAX_PIXELS` is read past the knob registry (`dots_ocr/__init__.py`
    # says so of both its knobs).
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
    # A DIRECTORY NAME WITHOUT A DOT. Loading by the repository name is
    # impossible: the dot in "dots.ocr" becomes a package separator in the
    # remote-code loader, and the relative import inside the model falls.
    # provision.sh puts the weights here; a missing directory is a refusal out
    # loud, not a quiet attempt to download by name.
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

    # THE PROCESSOR'S EXTRA KEYS. It lays down more than `generate` takes --
    # for dots.ocr `mm_token_type_ids`, and the run fell on the very first
    # page with a ValueError: `generate` checks what it is handed against its
    # own list and falls listing the extras. Selecting by the `forward`
    # SIGNATURE IS IMPOSSIBLE: dots.ocr takes **kwargs there, the filter
    # switches itself off, and the run falls exactly the same way -- that has
    # cost two rentals already. So we read the names out of the error itself,
    # remember and repeat. What is dropped is printed as a quantity: dropping
    # a stranger's key in silence means feeding the model the wrong thing.
    drop = set()

    # The fallback: if `generate` still complains after the dropping, we
    # leave ONLY what generation is impossible without. The list is short and
    # known for the Qwen2-VL family of vision models dots.ocr is built on.
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
            # We shrink OURSELVES, not relying on the processor: the model's
            # boxes will come in the coordinates of the picture we sent, and
            # the way back must be ours and explicit, not guessed.
            # THE NAME `scale`, NOT `k`. The loop variable of
            # `for k, item in enumerate(...)` below overwrote the scale
            # factor, and the very first box gave a division by zero: 36 pages
            # of 36 written down as "unparsed" while the model answered
            # flawlessly.
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
            inputs = {k: v.to("cuda") for k, v in inputs.items()}
            if n == 1 and r == 0:
                # What the processor gave at all -- as a quantity, once.
                # Without it, working out a stranger's refusal costs a fresh
                # rental.
                log(f"  процессор отдал ключи: {sorted(inputs)}")
            oom = False
            try:
                # Greedy decoding, no sampling: otherwise our own drift would
                # be added to the kernels', with nothing to separate them by.
                with torch.inference_mode():
                    out = generate(inputs, max_new_tokens=4096,
                                   do_sample=False, temperature=None,
                                   top_p=None, top_k=None)
            except torch.OutOfMemoryError:
                # One page must not kill the run: the rest are counted and
                # have arrived. The skip is written INTO THE PAGE as a
                # quantity, not as a silent zero of boxes.
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
                        # The reading order of this model is the ORDER OF
                        # GENERATION, written down as a value, not passed off
                        # as a rank.
                        "order": k, "content": None, "kind": "none"})
            except Exception as e:
                err = f"{type(e).__name__}: {e}"
                bad += 1
            else:
                # Parsed -- so we count HOW MANY boxes the model gave. An
                # empty page here is not an error, and not a success either.
                seen += len(blocks)
                if not blocks:
                    empty += 1

            with open(os.path.join(pdir, f"{i:04d}.json"), "w",
                      encoding="utf-8") as f:
                json.dump({"index": i, "width": w, "height": h, "dpi": DPI,
                           "blocks": blocks, "raw": {"answer": ans},
                           "meta": {"detector": "dots.ocr",
                                    "pass_no": r, "prompt": "layout_only_en",
                                    "reading_order": "generation_order",
                                    "input_pixel_ceiling": a.max_pixels,
                                    "downscale": round(scale, 4),
                                    "out_of_vram": oom,
                                    "parse_error": err}}, f,
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
