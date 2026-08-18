#!/usr/bin/env python3
"""Исполняется НА арендованной машине: PDF -> markdown + картинки.

Главное отличие от прошлой версии: страницы пишутся на диск сразу, по одной.
Раньше `predict` прогонялся целиком в список, и до самого конца в выходном
каталоге не появлялось ничего — падение на 400-й странице из 539 теряло всё,
а по числу файлов нельзя было даже понять, идёт ли работа.

Порядок такой:
  outputs/pages/NNNN.md, NNNN.json   пишутся по мере счёта
  outputs/progress.json              обновляется после каждой страницы
  outputs/book.md                    склейка через restructure_pages, в конце
"""
import argparse
import json
import os
import sys
import time


def _log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def _slice_pdf(pdf: str, first: int, last: int, out: str) -> str | None:
    """Вырезать диапазон страниц, чтобы можно было продолжить с места обрыва.

    pymupdf в образе может не быть — тогда просто считаем всё заново.
    """
    try:
        import pymupdf
    except ImportError:
        return None
    src = pymupdf.open(pdf)
    dst = pymupdf.open()
    dst.insert_pdf(src, from_page=first, to_page=min(last, src.page_count - 1))
    dst.save(out)
    dst.close()
    src.close()
    return out


def _done_pages(pages_dir: str) -> set[int]:
    if not os.path.isdir(pages_dir):
        return set()
    got = set()
    for n in os.listdir(pages_dir):
        stem = os.path.splitext(n)[0]
        if stem.isdigit():
            got.add(int(stem))
    return got


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--model", default="PaddleOCR-VL-1.6-0.9B")
    ap.add_argument("--server", default="",
                    help="URL сервиса vLLM; пусто — считать в процессе")
    ap.add_argument("--device", default="gpu:0",
                    help="без этого пайплайн уезжает целиком на CPU: "
                         "видеокарта на нуле, одно ядро в потолке")
    ap.add_argument("--resume", action="store_true",
                    help="продолжить с первой несчитанной страницы")
    a = ap.parse_args()

    out = a.out
    pages_dir = os.path.join(out, "pages")
    os.makedirs(pages_dir, exist_ok=True)

    pdf = a.pdf
    offset = 0
    if a.resume:
        done = _done_pages(pages_dir)
        if done:
            first = max(done)          # последнюю пересчитываем: могла оборваться
            sliced = _slice_pdf(pdf, first, 10 ** 6,
                                os.path.join(out, "_resume.pdf"))
            if sliced:
                pdf, offset = sliced, first
                _log(f"продолжаю со страницы {first+1} ({len(done)} уже готовы)")
            else:
                _log("pymupdf недоступен — продолжить с середины нечем, считаю всё")

    from paddleocr import PaddleOCRVL

    kwargs = {"device": a.device}
    if a.server:
        kwargs.update(vl_rec_server_url=a.server, vl_rec_api_model_name=a.model)
        _log(f"VLM через сервис {a.server}")
    else:
        _log(f"VLM в процессе, устройство {a.device}")

    t0 = time.time()
    try:
        pipeline = PaddleOCRVL(**kwargs)
    except TypeError:                    # старая сигнатура без device=
        kwargs.pop("device")
        _log("пайплайн не принимает device=, беру как есть")
        pipeline = PaddleOCRVL(**kwargs)
    _log(f"пайплайн готов за {time.time()-t0:.0f}с")

    t1 = time.time()
    pages, n = [], 0
    for res in pipeline.predict(pdf):
        idx = offset + n
        n += 1
        pages.append(res)
        stem = f"{idx:04d}"
        try:
            res.save_to_markdown(save_path=os.path.join(pages_dir, stem + ".md"))
        except Exception as e:
            _log(f"  страница {idx}: markdown не сохранился: {e}")
        try:
            res.save_to_json(save_path=os.path.join(pages_dir, stem + ".json"))
        except Exception as e:
            _log(f"  страница {idx}: json не сохранился: {e}")

        dt = time.time() - t1
        with open(os.path.join(out, "progress.json"), "w") as f:
            json.dump({"pages_done": idx + 1, "this_run": n,
                       "seconds": round(dt, 1),
                       "pages_per_sec": round(n / max(dt, 1e-6), 3),
                       "server": bool(a.server)}, f, indent=1)
        if n % 5 == 0 or n == 1:
            _log(f"  {idx+1} страниц, {n/max(dt,1e-6):.2f} стр/с")

    dt = time.time() - t1
    _log(f"посчитано {n} страниц за {dt:.0f}с ({n/max(dt,1e-6):.2f} стр/с)")

    # Склейка таблиц и абзацев через разрыв страницы — то, что для
    # pymupdf-конвейера писалось руками.
    try:
        joined = pipeline.restructure_pages(pages, merge_tables=True,
                                            concatenate_pages=True)
        _log("restructure_pages: таблицы склеены, страницы сшиты")
    except (AttributeError, TypeError) as e:
        _log(f"restructure_pages недоступен ({e}) — оставляю постранично")
        joined = pages

    book_dir = os.path.join(out, "book")
    os.makedirs(book_dir, exist_ok=True)
    for res in joined:
        try:
            res.save_to_markdown(save_path=book_dir)
        except Exception as e:
            _log(f"  склейка: {e}")

    with open(os.path.join(out, "run.json"), "w") as f:
        json.dump({"pages": offset + n, "seconds": round(dt, 1),
                   "pages_per_sec": round(n / max(dt, 1e-6), 3),
                   "server": bool(a.server), "model": a.model,
                   "device": a.device}, f, indent=1)
    _log(f"готово: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
