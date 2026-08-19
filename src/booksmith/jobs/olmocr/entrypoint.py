#!/usr/bin/env python3
"""Исполняется НА арендованной машине: PDF -> markdown через olmOCR-2.

Почему здесь свой клиент, а не `python -m olmocr.pipeline`
---------------------------------------------------------
Пакет olmocr закрепляет vllm==0.11.2 и transformers==4.57.3 (pyproject,
extra "gpu") — то есть тянет собственное дерево torch под cu128.  У нас в
репозитории уже есть закреплённое дерево под cu130 с vllm 0.27.1, на котором
считается paddleocr, и сравнивать две модели надо на одном движке: иначе
разница в результате окажется разницей в версии vLLM.  Держать два
несовместимых дерева ради полусотни строк пайплайна — плохая сделка.

Сам протокол переписан ДОСЛОВНО по исходникам olmocr (github.com/allenai/olmocr,
v0.4.27), и каждая его часть отмечена ниже ссылкой на место в оригинале:
  * промпт          olmocr/prompts/prompts.py::build_no_anchoring_v4_yaml_prompt
  * запрос          olmocr/pipeline.py::build_page_query
  * температуры     olmocr/pipeline.py::TEMPERATURE_BY_ATTEMPT
  * разбор ответа   olmocr/train/front_matter.py::FrontMatterParser
  * отрисовка       olmocr/data/renderpdf.py::render_pdf_to_base64png
Всё, что от оригинала отличается, помечено в комментарии словом «отличие».

Порядок работы — тот же, что у paddleocr, чтобы результаты можно было класть
рядом и сравнивать:
  outputs/pages/NNNN.md, NNNN.json   пишутся по мере счёта
  outputs/progress.json              обновляется после каждой страницы
  outputs/book/book.md               склейка по порядку, в конце
"""
import argparse
import base64
import concurrent.futures as futures
import io
import json
import multiprocessing
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.request

# Промпт olmOCR-2 дословно.  Он важен целиком, а не по смыслу: модель на нём
# дообучена, и «улучшение» формулировки — это выход за пределы обучающего
# распределения.  Отсюда же берётся ответ на вопрос про таблицы: olmOCR-2
# просят отдавать их в HTML, а не в markdown, — значит, ячейки считаются тем
# же способом, что и у PaddleOCR-VL.
#
# Текстового слоя PDF модель НЕ получает: document anchoring остался в первой
# версии olmOCR, а у второй ключ --target_anchor_text_len помечен в самом
# olmocr как "not used for new models".  Работает по картинке.
PROMPT = (
    "Attached is one page of a document that you must process. "
    "Just return the plain text representation of this document as if you were reading it naturally. "
    "Convert equations to LateX and tables to HTML.\n"
    "If there are any figures or charts, label them with the following markdown syntax "
    "![Alt text describing the contents of the figure](page_startx_starty_width_height.png)\n"
    "Return your output as markdown, with a front matter section on top specifying values for the "
    "primary_language, is_rotation_valid, rotation_correction, is_table, and is_diagram parameters."
)

# olmocr/pipeline.py: первая попытка идёт на 0.1, дальше температура растёт.
# Смысл в том, что повтор на той же температуре дал бы тот же ответ, а
# повторяют здесь как раз потому, что ответ не разобрался.
TEMPERATURE_BY_ATTEMPT = [0.1, 0.1, 0.2, 0.3, 0.5, 0.8, 0.9, 1.0]
MAX_TOKENS = 8000            # olmocr/pipeline.py::build_page_query
MODEL_MAX_CONTEXT = 16384    # olmocr/pipeline.py::try_single_page
TARGET_LONGEST_DIM = 1288    # olmocr: --target_longest_image_dim, умолчание

_print_lock = threading.Lock()


def _log(msg):
    with _print_lock:
        print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


# ---------------------------------------------------------------- отрисовка
#
# Отрисовка вынесена в отдельные ПРОЦЕССЫ, и это не украшение.  Замер на
# bench/tables20.pdf: страницы там — сканы, вклеенные в PDF как JPEG 2000
# (фильтр JPXDecode, 4222x6112), и распаковка одной такой картинки стоит
# 1.7 с у pdfium и 5.6 с у mupdf.  Двадцать страниц подряд — это 34 или 112
# секунд ЧИСТОГО процессора, тогда как весь прогон paddleocr на тех же
# страницах занял 24 секунды.  Отрисовка в один поток была бы здесь узким
# местом, а не карта.
#
# Процессы, а не потоки: pdfium не потокобезопасен, а GIL всё равно не даёт
# разложить распаковку по ядрам.  Метод запуска — spawn: при fork дочерний
# процесс унаследовал бы уже проинициализированную библиотеку, а это ровно
# тот случай, когда «работает, пока однажды не упадёт».
_DOC = None


def _render_init(pdf_path: str) -> None:
    """Открыть документ один раз на процесс, а не на страницу."""
    global _DOC
    import pypdfium2
    _DOC = pypdfium2.PdfDocument(pdf_path)


def _render_worker(page_idx: int, rotation: int) -> str:
    """Страница -> PNG в base64, как это делает olmocr.

    Отличие: у них это `pdftoppm -r <dpi>` из poppler, у нас pdfium.  Причина
    не в удобстве: poppler в образе нет, а ставить его apt-ом при каждом
    старте — те же полминуты, ради экономии которых образ и сделан пустым
    (см. infra/base/Dockerfile).  Масштаб при этом ровно тот же, что у
    olmocr: длинная сторона страницы приводится к 1288 пикселям.

    Дробный масштаб важен: если округлять до целого dpi, страница 506x733 pt
    даёт 1293 пикселя вместо 1288 — мелочь, но модель обучена на 1288, и
    расходиться с ней по входу без нужды незачем.
    """
    from PIL import Image

    page = _DOC[page_idx]
    scale = TARGET_LONGEST_DIM / max(page.get_size())
    img = page.render(scale=scale).to_pil()

    if rotation:
        # Поворот делаем ровно теми же средствами, что olmocr
        # (PIL Image.Transpose.ROTATE_*): направление отсчёта у PIL своё, и
        # «повернуть на 90» в другой библиотеке — это поворот в другую
        # сторону, то есть страница уедет боком дважды.
        img = img.transpose({90: Image.Transpose.ROTATE_90,
                             180: Image.Transpose.ROTATE_180,
                             270: Image.Transpose.ROTATE_270}[rotation])

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _ask(server: str, model: str, image_b64: str, temperature: float,
         timeout: float) -> dict:
    """Один запрос к vLLM.  Тело — как в olmocr/pipeline.py::build_page_query.

    Системного сообщения нет намеренно: шаблон чата Qwen2.5-VL подставляет
    своё ("You are a helpful assistant."), и olmocr полагается именно на это.
    Порядок частей тоже значим — сначала текст, потом картинка.

    Ходим через urllib, а не requests: лишняя зависимость в закреплённом
    дереве стоит дороже, чем десять строк здесь.
    """
    body = {
        "model": model,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": PROMPT},
                {"type": "image_url",
                 "image_url": {"url": f"data:image/png;base64,{image_b64}"}},
            ],
        }],
        "max_tokens": MAX_TOKENS,
        "temperature": temperature,
    }
    req = urllib.request.Request(
        server.rstrip("/") + "/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


_FM_KEYS = ("primary_language", "is_rotation_valid", "rotation_correction",
            "is_table", "is_diagram")


def _parse_front_matter(text: str) -> tuple[dict, str]:
    """Ответ модели -> (front matter, markdown).

    Разбор границ — как в olmocr/train/front_matter.py: блок начинается с
    "---\\n" и заканчивается первым "\\n---".  Значения разбираются вручную,
    а не через yaml.safe_load: набор ключей известен и фиксирован, а yaml на
    строке вроде `primary_language: no` возвращает False вместо "no" — то
    есть язык превращается в булево значение.  В olmocr это лечится
    отдельной веткой в _parse_front_matter; проще не создавать проблему.
    """
    if not text.startswith("---\n"):
        return {}, text.strip()
    end = text.find("\n---", 4)
    if end == -1:
        return {}, text.strip()
    head, body = text[4:end], text[end + 4:].strip()

    fm: dict = {}
    for line in head.splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        k, v = k.strip(), v.strip()
        if k not in _FM_KEYS:
            continue
        if k in ("is_rotation_valid", "is_table", "is_diagram"):
            fm[k] = v.lower() in ("true", "yes")
        elif k == "rotation_correction":
            fm[k] = int(v) if v.lstrip("-").isdigit() else 0
        else:
            fm[k] = None if v in ("null", "none", "") else v
    return fm, body


_text_lock = threading.Lock()


def _page_text_layer(doc, page_idx: int) -> str:
    """Запасной путь: текстовый слой самого PDF.

    В olmocr это `pdftotext` через get_anchor_text — тот же смысл: страница,
    которую модель так и не разобрала, не должна пропасть из книги совсем.

    Замок нужен: документ здесь один на все потоки, а pdfium не
    потокобезопасен.  Путь редкий, на скорость это не влияет.
    """
    try:
        with _text_lock:
            return doc[page_idx].get_textpage().get_text_bounded().strip()
    except Exception:
        return ""


def _one_page(doc, pool, idx: int, args) -> dict:
    """Посчитать одну страницу, с повторами по правилам olmocr."""
    rotation = 0
    for attempt in range(args.attempts):
        temperature = TEMPERATURE_BY_ATTEMPT[
            min(attempt, len(TEMPERATURE_BY_ATTEMPT) - 1)]
        try:
            img = pool.submit(_render_worker, idx, rotation).result()
            resp = _ask(args.server, args.model, img, temperature, args.timeout)
        except (urllib.error.URLError, OSError, TimeoutError) as e:
            _log(f"  страница {idx+1}: сеть/сервер — {type(e).__name__}: {e}")
            time.sleep(min(2 ** attempt, 30))
            continue
        except Exception as e:                      # noqa: BLE001
            _log(f"  страница {idx+1}: запрос не удался — {type(e).__name__}: {e}")
            continue

        try:
            choice = resp["choices"][0]
            usage = resp.get("usage") or {}
            fm, body = _parse_front_matter(choice["message"]["content"])
        except Exception as e:                      # noqa: BLE001
            _log(f"  страница {idx+1}: ответ не разобрался ({e}), повтор")
            continue

        # Обрыв по длине — не результат: модель не дописала таблицу.  olmocr
        # в этом месте помечает страницу невалидной и повторяет.
        if choice.get("finish_reason") != "stop":
            _log(f"  страница {idx+1}: обрыв ({choice.get('finish_reason')}), повтор")
            continue
        if usage.get("total_tokens", 0) > MODEL_MAX_CONTEXT:
            _log(f"  страница {idx+1}: вылезли за контекст, повтор")
            continue

        # Модель сама сообщает, что страница лежит боком.  Один повтор с
        # поворотом — и дальше как обычно.
        want = int(fm.get("rotation_correction") or 0)
        if not fm.get("is_rotation_valid", True) and want in (90, 180, 270) \
                and rotation == 0:
            _log(f"  страница {idx+1}: модель просит повернуть на {want}°")
            rotation = want
            continue

        return {"page": idx, "text": body, "attempts": attempt + 1,
                "rotation_applied": rotation, "fallback": False,
                "input_tokens": usage.get("prompt_tokens", 0),
                "output_tokens": usage.get("completion_tokens", 0),
                **{k: fm.get(k) for k in _FM_KEYS}}

    _log(f"  страница {idx+1}: {args.attempts} попыток без результата — "
         f"беру текстовый слой PDF")
    return {"page": idx, "text": _page_text_layer(doc, idx),
            "attempts": args.attempts, "rotation_applied": 0, "fallback": True,
            "input_tokens": 0, "output_tokens": 0,
            **{k: None for k in _FM_KEYS}}


def _done_pages(pages_dir: str) -> set[int]:
    if not os.path.isdir(pages_dir):
        return set()
    got = set()
    for n in os.listdir(pages_dir):
        stem, ext = os.path.splitext(n)
        if ext == ".json" and stem.isdigit():
            got.add(int(stem))
    return got


def _concat_pages(pages_dir: str, dst: str) -> int:
    """Собрать книгу из уже записанных страниц, по порядку.

    Сшивки таблиц через разрыв страницы, какая есть у paddleocr в
    restructure_pages, здесь нет: olmOCR отдаёт страницу целиком одним куском
    текста, и разрезанную пополам таблицу пришлось бы искать эвристикой.
    Честнее оставить как есть и сказать об этом, чем склеить наугад.
    """
    files = sorted(f for f in os.listdir(pages_dir) if f.endswith(".md"))
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with open(dst, "w", encoding="utf-8") as out:
        for f in files:
            out.write(open(os.path.join(pages_dir, f),
                           encoding="utf-8", errors="replace").read())
            out.write("\n\n")
    return len(files)


def _count_tables(path: str) -> tuple[int, int]:
    """Таблицы и ячейки — тем же счётом, что и у paddleocr.

    olmOCR-2 просят отдавать таблицы в HTML, и она это делает, поэтому
    знаменатель общий.  Единственное расхождение: она размечает шапку через
    <th>, а PaddleOCR-VL кладёт в шапку тот же <td>.  Поэтому ячейки
    считаются как <td> + <th>, иначе у olmOCR пропадала бы ровно одна строка
    каждой таблицы.
    """
    try:
        text = open(path, encoding="utf-8", errors="replace").read()
    except OSError:
        return 0, 0
    tables = len(re.findall(r"<table[\s>]", text, re.I))
    cells = len(re.findall(r"<t[dh][\s>]", text, re.I))
    return tables, cells


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--model", default="olmocr",
                    help="имя модели в vLLM (--served-model-name)")
    ap.add_argument("--model-repo", default="", help="только для журнала")
    ap.add_argument("--server", required=True, help="URL vLLM, вместе с /v1")
    ap.add_argument("--attempts", type=int,
                    default=int(os.environ.get("OLMOCR_ATTEMPTS") or 4),
                    help="повторов на страницу; у olmocr восемь, но там "
                         "миллионы документов и цена ошибки другая")
    ap.add_argument("--concurrency", type=int,
                    default=int(os.environ.get("OLMOCR_CONCURRENCY") or 8),
                    help="страниц в полёте одновременно: 7B без пачки "
                         "упирается в скорость генерации, а не в карту")
    ap.add_argument("--timeout", type=float, default=600.0,
                    help="потолок на один запрос к vLLM")
    ap.add_argument("--resume", action="store_true",
                    help="пропустить страницы, посчитанные прошлым прогоном")
    a = ap.parse_args()

    out = a.out
    pages_dir = os.path.join(out, "pages")
    os.makedirs(pages_dir, exist_ok=True)

    import pypdfium2
    doc = pypdfium2.PdfDocument(a.pdf)
    total = len(doc)

    todo = list(range(total))
    if a.resume:
        done = _done_pages(pages_dir)
        if done:
            todo = [i for i in todo if i not in done]
            _log(f"продолжаю: {len(done)} страниц уже готовы, осталось {len(todo)}")

    # Отрисовщиков столько же, сколько страниц в полёте, но не больше числа
    # ядер: рисовать впрок незачем — картинка ждала бы своей очереди к карте,
    # занимая память, а ядер на арендованных хостах бывает и четыре.
    renderers = max(1, min(a.concurrency, os.cpu_count() or 1))
    _log(f"{os.path.basename(a.pdf)}: {total} страниц, модель {a.model_repo or a.model}, "
         f"{a.concurrency} в полёте, {renderers} отрисовщиков, "
         f"до {a.attempts} попыток на страницу")

    t0 = time.time()
    n = 0
    stats = {"fallback": 0, "input_tokens": 0, "output_tokens": 0, "attempts": 0}
    # Страницы уходят на карту пачкой, но на диск ложатся по мере готовности:
    # падение на пятнадцатой из двадцати должно оставить четырнадцать, а не
    # ноль.  Каталог outputs синхронизируется к оператору ПО ХОДУ работы.
    render_pool = futures.ProcessPoolExecutor(
        max_workers=renderers, initializer=_render_init, initargs=(a.pdf,),
        mp_context=multiprocessing.get_context("spawn"))
    with render_pool, futures.ThreadPoolExecutor(max_workers=a.concurrency) as pool:
        tasks = {pool.submit(_one_page, doc, render_pool, i, a): i for i in todo}
        for fut in futures.as_completed(tasks):
            idx = tasks[fut]
            try:
                res = fut.result()
            except Exception as e:                  # noqa: BLE001
                _log(f"  страница {idx+1}: сорвалась целиком — {type(e).__name__}: {e}")
                continue
            n += 1
            stem = f"{idx:04d}"
            text = res.pop("text") or ""
            with open(os.path.join(pages_dir, stem + ".md"), "w",
                      encoding="utf-8") as f:
                f.write(text + "\n")
            with open(os.path.join(pages_dir, stem + ".json"), "w",
                      encoding="utf-8") as f:
                json.dump(res, f, ensure_ascii=False, indent=1)

            stats["fallback"] += int(res["fallback"])
            stats["input_tokens"] += res["input_tokens"]
            stats["output_tokens"] += res["output_tokens"]
            stats["attempts"] += res["attempts"]

            dt = time.time() - t0
            with open(os.path.join(out, "progress.json"), "w") as f:
                json.dump({"pages_done": len(_done_pages(pages_dir)),
                           "this_run": n, "seconds": round(dt, 1),
                           "pages_per_sec": round(n / max(dt, 1e-6), 3),
                           "server": True}, f, indent=1)
            if n % 5 == 0 or n == 1:
                _log(f"  {n} из {len(todo)}, {n/max(dt,1e-6):.2f} стр/с")

    dt = time.time() - t0
    _log(f"посчитано {n} страниц за {dt:.0f}с ({n/max(dt,1e-6):.2f} стр/с)")

    book = os.path.join(out, "book", "book.md")
    _concat_pages(pages_dir, book)
    tables, cells = _count_tables(book)
    _log(f"в книге {tables} таблиц и {cells} ячеек (<table>, <td>+<th>)")
    if stats["fallback"]:
        _log(f"ВНИМАНИЕ: {stats['fallback']} страниц ушли на текстовый слой PDF")

    with open(os.path.join(out, "run.json"), "w") as f:
        json.dump({"pages": len(_done_pages(pages_dir)),
                   "seconds": round(dt, 1),
                   "pages_per_sec": round(n / max(dt, 1e-6), 3),
                   "server": True, "model": a.model_repo or a.model,
                   "concurrency": a.concurrency,
                   "tables": tables, "cells": cells,
                   "fallback_pages": stats["fallback"],
                   "input_tokens": stats["input_tokens"],
                   "output_tokens": stats["output_tokens"],
                   "avg_attempts": round(stats["attempts"] / max(n, 1), 2)},
                  f, indent=1)
    _log(f"готово: {out}")
    # Ненулевой код возврата — раннеру, чтобы прогон попал в журнал как сбой.
    # Два случая.  Пусто — понятно.  Второй тоньше: если ВСЁ, что считалось
    # этим прогоном, ушло на текстовый слой, значит модель не ответила ни
    # разу (упал vLLM, кончилась память) — и молчаливый нулевой код тут
    # хуже всего, потому что книга при этом на месте и выглядит целой.
    if not len(_done_pages(pages_dir)):
        return 1
    if n and stats["fallback"] == n:
        _log("ни одна страница не разобрана моделью — считаю прогон сбоем")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
