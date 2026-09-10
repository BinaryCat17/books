"""Counting on the rented machine: dots.ocr layout boxes, page by page.

In: a PDF and a page selection. Out: one `pass<r>/pages/NNNN.json` per page,
written as the work goes, so a fall on page 90 of 130 leaves 90 pages and the
`outputs` sync brings them home.

An empty answer, an answer no JSON parses out of, coordinates off the sheet or
a category outside the vocabulary fall out loud rather than pass for a page
without boxes. With `--repeats N` each pass gets its own directory; the
comparison is made at home, not at video-memory prices.
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
    """`--pages 1,4,7-9` -> zero-based indices, counting the input from one as
    `detect.parse_pages` does; `-` means the whole book, here only. A copy of
    that function, held to it by `tests/contract/test_parse_pages.py`.
    """
    if not spec or spec == "-":
        log(f"pages: the whole book, {n} of them")
        return list(range(n))
    want = []
    # A space separates just like a comma, as in `detect.parse_pages`.
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
                    f"in `--pages {spec}` the range {part!r} did not parse. "
                    f"Expected \"7-9\", counting from one.")
            if not rng:
                raise SystemExit(
                    f"the range {part!r} is empty: the end precedes the "
                    f"start")
            want.extend(rng)
        else:
            try:
                want.append(int(part))
            except ValueError:
                raise SystemExit(
                    f"in `--pages {spec}` the piece {part!r} is not a page "
                    f"number. Expected \"1,4,7-9\" or \"1 4 7-9\", counting "
                    f"from one.")
    if 0 in want:
        raise SystemExit(
            f"{spec!r}: pages count FROM ONE, as in `books detect` -- the "
            f"first page of the book is 1 and there is no page zero. This "
            f"counted from zero once, and the same string then meant other "
            f"pages.")
    bad = [p for p in want if not 1 <= p <= n]
    if bad:
        raise SystemExit(f"the book has {n} pages, and {bad} were asked for")
    if not want:
        raise SystemExit(f"the page set {spec!r} is empty: nothing to count")
    idxs = [p - 1 for p in sorted(set(want))]
    # A quantity, not "understood": the meaning is visible before the card ticks.
    log(f"pages {spec!r} understood from one: {len(idxs)} of them, "
        f"{idxs[0]+1} to {idxs[-1]+1} (indices {idxs[0]}..{idxs[-1]})")
    return idxs


def extract(text):
    """Parse the model's answer into a list of boxes. An unparsable answer is
    an error out loud; an empty list is not -- a page without boxes can be
    genuine, and `main` counts those apart from the unparsed.
    """
    t = text.strip()
    m = re.search(r"```(?:json)?\s*(.+?)```", t, re.S)
    if m:
        t = m.group(1).strip()
    i, j = t.find("["), t.rfind("]")
    if i < 0 or j <= i:
        raise ValueError(f"no JSON list in the answer: {t[:200]!r}")
    data = json.loads(t[i:j + 1])
    if not isinstance(data, list):
        raise ValueError(f"what parsed is not a list but a {type(data).__name__}")
    return data


def tally(pages, boxes, empty, bad):
    """The pass in quantities: how many boxes the model gave at all. The zero
    of an empty page and the zero of an unparsed one are different zeroes,
    counted apart; with nothing to divide by it says "no data".
    """
    ok = pages - bad
    s = (f"{pages} pages, boxes {boxes}, empty pages {empty}, "
         f"unparsed {bad}, "
         + (f"boxes per parsed page {boxes/ok:.1f}" if ok
            else "boxes per parsed page: no data"))
    if pages and not boxes:
        # A lawful zero and a refusal look alike here, so the decision stays at home.
        s = "NOT ONE BOX in the whole pass. " + s
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("--pages", default="-")
    # The input ceiling: the vision encoder runs out of memory on a 4.9-Mpixel page.
    ap.add_argument("--max-pixels", type=int,
                    default=int(os.environ.get("DOTS_MAX_PIXELS",
                                               1280 * 28 * 28)))
    a = ap.parse_args()

    import pymupdf
    import torch
    from PIL import Image
    from transformers import AutoModelForCausalLM, AutoProcessor

    log("loading the model")
    t0 = time.time()
    # A directory without a dot: the dot in "dots.ocr" breaks the remote-code import.
    name = os.environ.get("DOTS_DIR", "/models/DotsOCR")
    if not os.path.isdir(name):
        raise SystemExit(
            f"no weights directory {name}: provision.sh should have put "
            f"them there. Loading by repository name is impossible -- the dot "
            f"in the name breaks the remote-code import.")
    model = AutoModelForCausalLM.from_pretrained(
        name, trust_remote_code=True, torch_dtype=torch.bfloat16,
        attn_implementation="sdpa", device_map="cuda")
    proc = AutoProcessor.from_pretrained(
        name, trust_remote_code=True,
        min_pixels=256 * 28 * 28, max_pixels=a.max_pixels)
    log(f"input ceiling {a.max_pixels} pixels "
        f"({a.max_pixels/1e6:.2f} Mpixel)")
    model.eval()
    log(f"model up in {time.time()-t0:.0f} s")

    # `generate` refuses extra processor keys; the names come from its error, not the signature.
    drop = set()

    # Last resort: what generation is impossible without in the Qwen2-VL family.
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
            log(f"  generate does not take {sorted(bad)} -- dropping and retrying")
            try:
                return model.generate(
                    **{k: v for k, v in left.items() if k not in drop}, **kw)
            except ValueError as e2:
                core = {k: v for k, v in inputs.items() if k in CORE}
                log(f"  and a ValueError after that ({e2}); keeping only "
                    f"{sorted(core)}")
                if not core:
                    raise
                return model.generate(**core, **kw)

    doc = pymupdf.open(a.pdf)
    idxs = parse_pages(a.pages, doc.page_count)
    log(f"pages in the file {doc.page_count}, counting {len(idxs)}, "
        f"passes {a.repeats}")

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
            # We shrink ourselves: boxes come back in the sent picture's coordinates.
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
                # What the processor gave at all, once: a refusal is unreadable without it.
                log(f"  the processor returned the keys: {sorted(inputs)}")
            oom = False
            try:
                # Greedy decoding: sampling would add our drift to the kernels', inseparably.
                with torch.inference_mode():
                    out = generate(inputs, max_new_tokens=4096,
                                   do_sample=False, temperature=None,
                                   top_p=None, top_k=None)
            except torch.OutOfMemoryError:
                # One page must not kill the run; the skip is written into the page itself.
                torch.cuda.empty_cache()
                oom = True
                out = None
                log(f"  p. {i}: out of video memory, skipping")
            ans = "" if oom else proc.batch_decode(
                out[:, inputs["input_ids"].shape[1]:],
                skip_special_tokens=True)[0]

            blocks, err = [], None
            try:
                if oom:
                    raise RuntimeError("page skipped: out of video memory")
                for k, item in enumerate(extract(ans)):
                    cat = item.get("category")
                    box = item.get("bbox")
                    if cat not in LABELS:
                        raise ValueError(f"category {cat!r} is outside the vocabulary")
                    if not (isinstance(box, list) and len(box) == 4):
                        raise ValueError(f"a box is not four numbers: {box!r}")
                    x0, y0, x1, y1 = (float(v) / scale for v in box)
                    blocks.append({
                        "block_id": k, "box": [x0, y0, x1, y1],
                        "label": cat, "score": None,
                        # This model's reading order is the order of generation.
                        "order": k, "content": None, "kind": "none"})
            except Exception as e:
                err = f"{type(e).__name__}: {e}"
                bad += 1
            else:
                # An empty page here is neither an error nor a success.
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
                log(f"  pass {r}: {n}/{len(idxs)}, boxes {seen}, "
                    f"empty {empty}, unparsed {bad}, "
                    f"{time.time()-t_pass:.0f} s")
        log(f"pass {r} finished: {tally(len(idxs), seen, empty, bad)}, "
            f"{time.time()-t_pass:.0f} s "
            f"({(time.time()-t_pass)/max(1,len(idxs)):.2f} s/page)")
        if bad == len(idxs):
            log("NOT ONE page parsed -- this is a refusal, not an empty book")
            return 3
    doc.close()
    if os.path.exists(tmp):
        os.unlink(tmp)
    return 0


if __name__ == "__main__":
    sys.exit(main())
