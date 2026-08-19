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
import collections
import glob
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


def _is_onnx_dir(path: str) -> bool:
    return os.path.isfile(os.path.join(path, "inference.onnx"))


def _concat_pages(pages_dir: str, dst: str) -> int:
    """Собрать книгу из уже записанных страниц, по порядку.

    Запасной путь: без сшивки таблиц через разрыв, но полный и честный —
    в отличие от склейки по страницам одного прогона.
    """
    files = []
    for root, _dirs, names in os.walk(pages_dir):
        for n in names:
            if n.endswith(".md"):
                files.append(os.path.join(root, n))
    files.sort()
    with open(dst, "w") as out:
        for f in files:
            out.write(open(f, encoding="utf-8", errors="replace").read())
            out.write("\n\n")
    return len(files)


def _done_pages(pages_dir: str) -> set[int]:
    if not os.path.isdir(pages_dir):
        return set()
    got = set()
    for n in os.listdir(pages_dir):
        stem = os.path.splitext(n)[0]
        if stem.isdigit():
            got.add(int(stem))
    return got


def _deep_update(base, extra):
    for k, v in extra.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_update(base[k], v)
        else:
            base[k] = v
    return base


def _pipeline_config(layout_dir):
    """Конфигурация пайплайна: детекция на ONNX Runtime и пачки страниц.

    Ключ `engine` внутри подмодуля имеет наивысший приоритет (paddlex
    resolve_child_engine), а выход совпадает с paddle побитово: замер на 82
    рамках дал IoU 1.0000 и расхождение координат 0.00 пикселя при втрое
    большей скорости.  Заодно из окружения уходит GPU-сборка paddle на
    3.69 ГБ.
    """
    from paddlex.inference import load_pipeline_config

    # Имя конфигурации зависит от версии пайплайна; у paddleocr 3.7 по
    # умолчанию v1.6.  Если однажды переименуют — откатываемся на v1.
    for name in ("PaddleOCR-VL-1.6", "PaddleOCR-VL"):
        try:
            cfg = load_pipeline_config(name)
            break
        except Exception:
            cfg = None
    if cfg is None:
        raise SystemExit("не нашлась конфигурация пайплайна PaddleOCR-VL")

    return _deep_update(cfg, {
        # Страницы подаются пачками, а не по одной: чем больше пачка, тем
        # больше блоков уходит к vLLM одновременно и тем плотнее он их
        # батчит.  Умолчание — 1, и карта простаивает между страницами.
        "batch_size": 4,
        "SubModules": {
            "LayoutDetection": {
                "module_name": "layout_detection",
                "model_name": os.environ.get("LAYOUT_MODEL_NAME",
                                             "PP-DocLayoutV2"),
                "model_dir": layout_dir,
                "engine": "onnxruntime",
                # Восьмёрка требовала 430 МБ единым буфером и не влезала
                # рядом с vLLM; четвёрка вдвое дешевле по памяти, а
                # детекция всё равно не узкое место.
                "batch_size": 4,
            }
        }
    })



def _strip_running_headers(pages_dir, *targets):
    """Убрать колонтитулы — по повторяемости, а не по метке.

    Название главы и колонтитул несут одну и ту же метку `header`, поэтому
    отличить их можно только по одному признаку: колонтитул стоит на многих
    страницах, название главы — на одной.  Порог с запасом: не меньше трёх
    страниц и не меньше трети книги.

    Возвращает то, что убрано, — чтобы это было видно в логе, а не молча.
    """
    seen = collections.Counter()
    npages = 0
    for f in sorted(glob.glob(os.path.join(pages_dir, "*.json"))):
        npages += 1
        try:
            d = json.load(open(f))
        except Exception:
            continue
        for r in d.get("parsing_res_list") or []:
            if r.get("block_label") == "header":
                t = (r.get("block_content") or "").strip()
                if t:
                    seen[t] += 1

    limit = max(3, npages // 3)
    running = {t for t, c in seen.items() if c >= limit}
    if not running:
        return []

    # Блок может занимать несколько строк — сравниваем построчно.
    lines = {ln.strip() for t in running for ln in t.splitlines() if ln.strip()}
    for target in targets:
        for f in glob.glob(os.path.join(target, "*.md")):
            try:
                src = open(f).read().splitlines(keepends=True)
            except Exception:
                continue
            kept = [ln for ln in src if ln.strip() not in lines]
            if len(kept) != len(src):
                open(f, "w").writelines(kept)
    return sorted(running)


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

    # Детекцию макета уводим на ONNX Runtime, если в образе лежат ONNX-веса.
    # Ключ `engine` внутри подмодуля имеет наивысший приоритет (paddlex
    # resolve_child_engine), а сам выход побитово тот же: замер на 82 рамках
    # дал IoU 1.0000 и расхождение координат 0.00 пикселя при втрое большей
    # скорости. Заодно из образа уходит GPU-сборка paddle на 3.69 ГБ.
    layout_dir = os.environ.get("LAYOUT_MODEL_DIR", "")
    if layout_dir and _is_onnx_dir(layout_dir):
        # paddlex_config словарём НЕ сливается с конфигурацией по умолчанию:
        # в paddleocr/_pipelines/base.py это буквально `config =
        # self._paddlex_config`, то есть подмена целиком.  Передать один
        # подмодуль нельзя — пайплайн остаётся без `pipeline_name` и падает
        # с KeyError.  Поэтому берём конфигурацию сами и сливаем в неё.
        kwargs["paddlex_config"] = _pipeline_config(layout_dir)
        _log(f"детекция макета: ONNX Runtime, веса из {layout_dir}")
    elif layout_dir:
        _log(f"в {layout_dir} нет inference.onnx — детекция остаётся на paddle")
    # Умолчание paddlex выбрасывает из markdown семь меток, и среди них
    # `header` — а в книгах это не только колонтитул, но и название главы.
    # Замер на 25 страницах: в `header` попало семь блоков, и все семь —
    # настоящий текст ("Chapter 28", "THE VERTICAL MILLING MACHINE", ...),
    # ни одного колонтитула.  Их отбрасывание — потеря содержания.
    #
    # Колонтитулы всё равно надо убирать, но по факту, а не по метке: они
    # повторяются из страницы в страницу, и это видно после прогона
    # (см. _strip_running_headers).  `number` остаётся в списке — это
    # номера страниц, все 24 из 25.
    # Конвейер вместо последовательности.  Замер: 25 страниц за 98 с при
    # 409 запросах к vLLM (по одному на распознанный блок, 16 на страницу),
    # причём карта между ними простаивала — в статистике vLLM `Running: 0
    # reqs` и KV-кеш 0.0%.  Узкое место не карта, а то, что чтение страницы,
    # детекция макета и VLM шли строго по очереди.
    #
    # use_queues ставит между ними очереди и отдельные потоки, так что
    # детекция следующей страницы идёт, пока считается текущая.
    # Порог детекции таблиц — отдельной ручкой, потому что именно он решает
    # судьбу таблиц без линеек.  RT-DETR предлагает для одной области
    # несколько кандидатов с разными классами; на странице 307 книги три
    # одинаковых блока "RECOMMENDED STANDARDS" получили table 0.70, text 0.78
    # и text 0.61 — то есть таблица проиграла тексту по уверенности, а не
    # осталась незамеченной.  В PP-DocLayoutV2 table — класс 21.
    thr = os.environ.get("LAYOUT_TABLE_THRESHOLD", "")
    if thr:
        kwargs["layout_threshold"] = {21: float(thr)}
        _log(f"порог таблиц опущен до {thr}")

    kwargs["use_queues"] = True
    kwargs["markdown_ignore_labels"] = [
        "number", "header_image", "footer", "footer_image", "aside_text",
    ]

    if a.server:
        # Одного адреса мало: без backend пайплайн всё равно строит локальную
        # модель и падает на gpu:0, потому что paddle у нас CPU-сборки.
        # Переключатель — SubModules.VLRecognition.genai_config.backend,
        # снаружи это vl_rec_backend (см. paddleocr/_pipelines/paddleocr_vl.py).
        kwargs.update(vl_rec_backend="vllm-server",
                      vl_rec_server_url=a.server,
                      vl_rec_api_model_name=a.model)
        _log(f"VLM через сервис {a.server} (backend vllm-server)")
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
    #
    # ВАЖНО: `pages` содержит только страницы ЭТОГО прогона.  При возобновлении
    # склеивать по ним нельзя — получилась бы книга из одного хвоста, и молча.
    book_dir = os.path.join(out, "book")
    os.makedirs(book_dir, exist_ok=True)
    if offset:
        _log(f"прогон был возобновлён с {offset+1}-й страницы — "
             f"сшиваю книгу из файлов, без restructure_pages")
        _concat_pages(pages_dir, os.path.join(book_dir, "book.md"))
    else:
        try:
            joined = pipeline.restructure_pages(pages, merge_tables=True,
                                                concatenate_pages=True)
            _log("restructure_pages: таблицы склеены, страницы сшиты")
        except (AttributeError, TypeError) as e:
            _log(f"restructure_pages недоступен ({e}) — сшиваю из файлов")
            joined = None
        if joined is None:
            _concat_pages(pages_dir, os.path.join(book_dir, "book.md"))
        else:
            for res in joined:
                try:
                    res.save_to_markdown(save_path=book_dir)
                except Exception as e:
                    _log(f"  склейка: {e}")

    dropped = _strip_running_headers(pages_dir, pages_dir, book_dir)
    if dropped:
        _log(f"убраны колонтитулы ({len(dropped)}): "
             + "; ".join(x.replace(chr(10), " ")[:40] for x in dropped[:5]))

    with open(os.path.join(out, "run.json"), "w") as f:
        json.dump({"pages": offset + n, "seconds": round(dt, 1),
                   "pages_per_sec": round(n / max(dt, 1e-6), 3),
                   "server": bool(a.server), "model": a.model,
                   "device": a.device}, f, indent=1)
    _log(f"готово: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
