"""`books detect` — контуры первого уровня, местно и бесплатно.

Что делает: рендерит страницы PDF при `PAGE_DPI`, гоняет по ним детектор
макета и кладёт рядом `Page` в json — рамки, ярлыки, порядок чтения. Ни VLM,
ни аренды, ни единого цента. Страница считается пару секунд на процессоре.

Зачем это раньше всего остального. Метрику контуров нельзя проверить на
выдуманных данных: мутации показывают, что число шевелится, но не показывают,
что оно меряет то самое. Нужен вывод НАСТОЯЩЕЙ модели на НАСТОЯЩИХ страницах
— и вот он, без денег и без ожидания.

Слепок пишется полным. `books replay --check` на каталоге этой команды обязан
возвращать 0: у детектора нет ни промтов, ни параметров порождения, ни весов
VLM — и это ЗНАЧЕНИЯ (`null`), а не пропуски. Разница принципиальная:
«промтов нет вовсе» и «промты не смотрели» — разные прогоны.

ЧТО ЗДЕСЬ ОБЯЗАНО ПАДАТЬ, А НЕ МОЛЧАТЬ. Пустой набор страниц, пустой вывод
модели, чужие страницы в каталоге от прошлого прогона. Каждый из трёх
случаев прежде давал код 0 и полный слепок, то есть выглядел успехом.
"""
import hashlib
import json
import os
import shlex
import subprocess
import sys
import time

from . import policy
from .models.doclayout import DocLayout
from .run import knobs

# Политика «текст / артефакт / служебное» живёт в одном месте — `policy.py`,
# и оттуда же её берёт сборщик HTML. Два списка разошлись бы: они уже
# расходились в этом проекте (реестр ручек против сборщика задания, 13 имён
# из 17).
ARTEFACT = policy.artefacts()


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _commit():
    """Коммит кода, которым считали. Грязное дерево помечается ЯВНО.

    Помечается, а не молчит: прогон на незакоммиченных правках повторить
    нельзя, и знать об этом надо в момент чтения слепка, а не потом.
    """
    # Спрашиваем git в КАТАЛОГЕ ИСХОДНИКОВ, а не в рабочем каталоге процесса.
    # `books detect` можно позвать откуда угодно — из чужого репозитория, из
    # каталога вовсе без git, — и слепок записал бы чужой коммит или None при
    # живом репозитории. Обе беды молчаливые.
    root = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))
    try:
        h = subprocess.run(["git", "-C", root, "rev-parse", "HEAD"],
                           capture_output=True, text=True, timeout=10)
        if h.returncode != 0:
            return None
        sha = h.stdout.strip()
        d = subprocess.run(["git", "-C", root, "status", "--porcelain"],
                           capture_output=True, text=True, timeout=10)
        return sha + ("+грязное дерево" if d.stdout.strip() else "")
    except (OSError, subprocess.SubprocessError):
        return None


def _packages():
    out = {}
    for name in ("onnxruntime", "numpy", "cv2", "pymupdf", "yaml"):
        try:
            out[name] = __import__(name).__version__
        except Exception:                      # noqa: BLE001
            out[name] = None                   # значение, а не пропуск
    out["python"] = sys.version.split()[0]
    return out


def parse_pages(spec, total):
    """`--pages 1,4,7-9` -> набор номеров, считая с единицы.

    Пустое значение — вся книга. Номер за пределами книги — ошибка вслух.
    Заданный, но ПУСТОЙ набор (`3-1`) — тоже ошибка: прежде он давал ноль
    страниц, код возврата 0 и полный слепок, то есть пустой прогон выглядел
    успешным. Ноль от непонимания.
    """
    if not spec:
        return list(range(total))
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
    bad = [p for p in want if not 1 <= p <= total]
    if bad:
        raise SystemExit(f"в книге {total} страниц, а запрошены {bad}")
    if not want:
        raise SystemExit(f"набор страниц «{spec}» пуст — считать нечего")
    return [p - 1 for p in sorted(set(want))]


def run(pdf, outdir, pages_spec=None, log=print):
    """Прогнать детектор по страницам PDF. Возвращает путь к каталогу."""
    import pymupdf

    dpi_raw = knobs.knob("PAGE_DPI")
    dpi = float(dpi_raw)
    # Рендерим целым числом, и в слепок пишем ЕГО, а не исходное дробное:
    # `get_pixmap` дробное усекает, и слепок при `PAGE_DPI=143.5` соврал бы.
    dpi_used = int(dpi)
    if dpi_used != dpi:
        log(f"ВНИМАНИЕ: PAGE_DPI={dpi_raw} усечён до {dpi_used} — "
            f"растр рисуется целым числом точек на дюйм")

    pdf = os.path.abspath(pdf)
    outdir = os.path.abspath(outdir)
    pagedir = os.path.join(outdir, "pages")

    det = DocLayout()
    # Политика обязана покрывать словарь весов ЦЕЛИКОМ и не называть лишнего.
    # Проверяется при каждом прогоне: словарь приезжает из весов, и смена
    # весов — самый вероятный способ завести двадцать шестой класс.
    policy.check(det.labels)
    for line in det.threshold_drift():
        # Громко: молчаливое расхождение означает, что прогон поехал на нашем
        # числе вместо модельного.
        log(f"ВНИМАНИЕ: порог задан не родной — {line}")
    log(f"детектор {det.name}: {knobs.knob('LAYOUT_MODEL_NAME')} из {det.dir}")
    log(f"вход модели {det.target_w}x{det.target_h} (ШxВ), "
        f"keep_ratio={det.keep_ratio}, родной порог {det.native_threshold}")

    doc = pymupdf.open(pdf)
    idxs = parse_pages(pages_spec, doc.page_count)

    # Чужие страницы в каталоге — не мелочь. Прошлый прогон мог идти при
    # другом пороге, другом dpi, других весах; смешавшись, они дадут метрике
    # выборку из двух разных прогонов, и `run.json` про это не скажет.
    # Ровно тот урок, что записан в реестре про `RESUME`.
    os.makedirs(pagedir, exist_ok=True)
    stale = [f for f in os.listdir(pagedir) if f.endswith(".json")]
    if stale:
        for f in stale:
            os.unlink(os.path.join(pagedir, f))
        log(f"убрано страниц прошлого прогона: {len(stale)}")

    log(f"{os.path.basename(pdf)}: страниц в файле {doc.page_count}, "
        f"считаю {len(idxs)} при {dpi_used} dpi")

    t0 = time.time()
    tmp = os.path.join(outdir, f".page.{os.getpid()}.png")
    counts, rej_best, rej_pages = {}, {}, {}
    artefacts = ties = 0
    try:
        for n, i in enumerate(idxs, 1):
            doc[i].get_pixmap(dpi=dpi_used).save(tmp)
            page = det.read(tmp, i, float(dpi_used))
            with open(os.path.join(pagedir, f"{i:04d}.json"), "w",
                      encoding="utf-8") as f:
                json.dump(page.to_json(), f, ensure_ascii=False)
            ties += page.meta["связок рангов"]
            for lab, s in page.meta["лучший отвергнутый по классам"].items():
                if s > rej_best.get(lab, 0.0):
                    rej_best[lab] = s
                    rej_pages[lab] = i          # ГДЕ он был лучше всего
                # «На скольких страницах отвергнуто» отсюда убрано: сырой
                # вывод несёт три сотни строк на страницу и накрывает почти
                # все классы почти всегда, так что это число было равно числу
                # страниц при любом пороге. Оно не умело упасть, а читалось
                # как замер.
            for b in page.blocks:
                counts[b.label] = counts.get(b.label, 0) + 1
                artefacts += b.label in ARTEFACT
            if n % 10 == 0 or n == len(idxs):
                log(f"  {n}/{len(idxs)} страниц, рамок {sum(counts.values())}")
    finally:
        doc.close()
        if os.path.exists(tmp):
            os.unlink(tmp)

    took = time.time() - t0
    total = sum(counts.values())
    log(f"рамок {total} на {len(idxs)} страницах "
        f"({total/len(idxs):.1f} на страницу), артефактов {artefacts}, "
        f"связок рангов {ties}, {took:.1f} с ({took/len(idxs):.2f} с/страница)")

    # По классам — принято И лучшее отвергнутое. Без второго числа «table 0»
    # читается как «таблиц нет», а означать может «таблица была на 0.03 ниже
    # порога». Это разные беды: первая к модели, вторая к ручке. Замер на
    # bench/real/tables20.pdf: при родном пороге таблица находится на 4 страницах
    # из 20, притом что страницы отобраны именно по таблицам.
    # Показываем то, что нашлось, и ВСЕ артефактные ярлыки — даже с нулём.
    # Остальные отвергнутые сводим в строку: двадцать пять классов подряд
    # топят единственное число, ради которого отчёт и написан.
    shown = sorted(set(counts) | set(ARTEFACT),
                   key=lambda l: (-counts.get(l, 0), l))
    for lab in shown:
        line = f"    {lab:18s} принято {counts.get(lab, 0):5d}"
        if lab in rej_best:
            line += (f", лучший отвергнутый {rej_best[lab]:.3f} "
                     f"(стр. {rej_pages[lab]})")
        log(line)
    rest = {l: v for l, v in rej_best.items() if l not in shown}
    if rest:
        top = max(rest.items(), key=lambda kv: kv[1])
        log(f"    прочих классов отвергнуто {len(rest)}, "
            f"выше всех {top[0]} {top[1]:.3f}")

    if total == 0:
        raise RuntimeError(
            f"ни одной рамки на {len(idxs)} страницах — это отказ, а не "
            f"пустая книга. Порог LAYOUT_SCORE_THRESHOLD="
            f"{knobs.knob('LAYOUT_SCORE_THRESHOLD')}, веса {det.dir}. "
            f"Лучшее отвергнутое: {rej_best or 'ничего не отвергнуто вовсе'}")

    here = os.path.dirname(os.path.abspath(__file__))
    fp = det.fingerprint()
    snap = {
        # Дата рядом с числом: замер без неё не сказать, к чему применён.
        "когда": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "ручки": knobs.snapshot(),
        "растр": {"scale": dpi_used / 72.0, "dpi": float(dpi_used),
                  "PAGE_DPI как задан": dpi_raw},
        "аргументы": {"pdf": pdf, "pages": pages_spec, "out": outdir},
        "коммит": _commit(),
        "исходник": {"путь": pdf, "sha256": _sha256(pdf)},
        # Хэшируются ОБА файла, решающих результат. Прежде считался только
        # адаптер, а политика артефактов и разбор страниц живут здесь.
        "адаптер": {"имя": det.name,
                    "sha256": _sha256(os.path.join(here, "models",
                                                   "doclayout.py")),
                    "sha256 команды": _sha256(os.path.join(here,
                                                           "detect.py"))},
        "политика": policy.snapshot(),
        "промты": {},
        "порождение": {"temperature": None, "max_tokens": None,
                       "top_p": None, "seed": None},
        "пакеты": _packages(),
        "веса": {"vl": None, "layout": fp["sha256 весов"]},
        "отпечаток": fp,
        "итог": {"страниц": len(idxs), "рамок": total,
                 "артефактов": artefacts, "связок рангов": ties,
                 "секунд": round(took, 2), "по ярлыкам": counts,
                 "лучший отвергнутый": rej_best,
                 "страниц с отвергнутыми": rej_pages},
        # Строка обязана быть исполнимой: в raw/ пять файлов из девяти несут
        # пробелы и скобки, и неэкранированная строка повтора — не строка
        # повтора, а её описание.
        "повтор": " ".join(shlex.quote(a) for a in
                           ["books", "detect", pdf, "--out", outdir]
                           + (["--pages", str(pages_spec)] if pages_spec else [])),
    }
    with open(os.path.join(outdir, "run.json"), "w", encoding="utf-8") as f:
        json.dump(snap, f, ensure_ascii=False, indent=1)
    log(f"слепок: {os.path.join(outdir, 'run.json')}")
    return outdir
