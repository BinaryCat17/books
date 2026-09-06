"""`books detect` -- first-level contours, locally and for free.

Renders the PDF pages at `PAGE_DPI`, runs a layout detector over them and puts
a `Page` in json beside each: boxes, labels, reading order. No VLM, no rental,
not a cent, a couple of seconds a page on the CPU.

Why before everything else. Contour metrics cannot be checked on invented data:
mutations show that the number moves, not that it measures the thing. What is
needed is a REAL model's output on REAL pages -- here, without money or
waiting.

The snapshot is written FULL. `books replay --check` over this command's
directory must return 0: the detector has no prompts, no generation parameters,
no VLM weights -- and those are VALUES (`null`), not gaps. "There are no
prompts at all" and "nobody looked at the prompts" are different runs.

Full is not the same as acting, and that is a separate trouble. Knobs in the
snapshot are SPLIT by who reads them: the active adapter, the command itself,
nobody. What the split cost to learn is in `_knob_roles`.

WHAT MUST BE LOUD HERE, NOT SILENT. An empty page set, empty model output,
foreign pages left in the directory by an earlier run, A BLOCK LABEL SPELLED
THE WAY THE POLICY VOCABULARY DOES NOT KNOW. Each of the four used to give exit
code 0 and a full snapshot: it looked like success.
"""
import json
import os
import shlex
import sys
import time

from . import policy
from .models.doclayout import DocLayout
from .run import knobs, stamp

# The "text / artefact / service" policy lives in one place, `policy.py`, and
# the HTML builder takes it from there too. Two lists would drift; they have
# drifted here already (the knob registry against the task builder, 13 names of
# 17).
# Artefact labels are TAKEN FROM THE ACTIVE POLICY (in `run`), not the union of
# all. The union printed `picture` in the report while running a model with no
# such class -- an eternal zero reading as "the model did not find them".
# The SAME single vocabulary also checks every block's label spelling, which
# the WEIGHTS check cannot -- `_check_labels` below says why.


# The three snapshot quantities -- file hash, commit, package versions -- moved
# to `run/stamp.py`: three places write a snapshot now (this command,
# `doc/html.py` and `read/run.py`), and a second copy is the drift this project
# has already paid for.
_sha256 = stamp.sha256


# The adapter registry. While there was one, "would another model be better"
# could not be asked: the name was baked into the import. Adapters differ not
# in weights but in VOCABULARY and preprocessing, so the choice is a declared
# knob and travels into the snapshot.
ADAPTERS = ("doclayout", "docling", "docling-egret", "yolox")


def _check_labels(page, pol, known, adapter):
    """EVERY BLOCK's label spelling, against the named vocabulary, out loud.

    WHAT NOBODY CHECKED. `policy.check(det.labels)` verifies the WEIGHTS
    vocabulary: what the model can name. What arrives here is what the block
    SAYS, and between the two lies a translation -- the docling adapter turns a
    label into the vendor's vocabulary and back, and the vendor pipeline
    renames labels itself (`TITLE -> SECTION_HEADER` in its postprocessing).
    Not one guard stood on that path: a swapped reverse translation in egret
    passed six pages in silence. `policy.role()` never fails either, because
    `policy.ROLE` is the union of all five vocabularies, where `table` and
    `Table` lie side by side.

    THE PRICE OF SILENCE IS NOT A CRASH BUT A ZERO. Artefact labels come from
    ONE vocabulary (`arte` in `run`), and a foreign-spelled block matches none:
    "artefacts 0" reads as "the model did not find them" when it means "we did
    not recognise its words" -- the zero from misunderstanding.

    Checked ON EVERY PAGE, not once: the vendor pipeline renames labels and
    does not see every page alike -- a foreign spelling can turn up on page
    four hundred and never before.
    """
    bad = sorted({b.label for b in page.blocks if b.label not in known})
    if not bad:
        return
    raise RuntimeError(
        f"страница {page.index}: ярлыки блоков {bad} не из словаря политики "
        f"«{pol}» (адаптер {adapter}; словарь знает {len(known)} написаний: "
        f"{sorted(known)}). Считать дальше нельзя: артефактные ярлыки берутся "
        f"из этого же словаря, и блок с чужим написанием дал бы «артефактов "
        f"0» — ноль от непонимания под видом замера. Чинить надо перевод "
        f"ярлыка в адаптере или сам словарь policy.POLICIES, но не эту "
        f"проверку.")


def _adapter():
    which = knobs.knob("LAYOUT_ADAPTER")
    if which == "doclayout":
        return DocLayout()
    if which == "docling":
        from .models.docling_heron import DoclingHeron
        return DoclingHeron()
    if which == "docling-egret":
        from .models.docling_heron import DoclingEgret
        return DoclingEgret()
    if which == "yolox":
        from .models.yolox_layout import YoloXLayout
        return YoloXLayout()
    raise SystemExit(f"LAYOUT_ADAPTER={which!r}: знаю только {ADAPTERS}")


# Knobs THIS command reads, not the adapter. A third rank, and no ornament:
# marking `PAGE_DPI` "does not concern this run" would be a lie of the same
# kind as naming a foreign model, the other way round.
# `LAYOUT_SCORE_THRESHOLD` is read here too (in the "not one box" refusal) but
# only to print someone else's number: the adapter makes it act and declares
# it, and two owners of one knob are two lists that drift.
COMMAND_KNOBS = ("PAGE_DPI", "LAYOUT_ADAPTER")


def _knob_roles(det):
    """Who reads each registry knob IN THIS RUN: the adapter, the command, nobody.

    Before this split, a `LAYOUT_ADAPTER=docling` snapshot confidently wrote
    `LAYOUT_MODEL_NAME=PP-DocLayoutV2` -- a model it never raised: heron's
    weights directory is hard-wired and only `doclayout.py` reads that knob.
    Completeness does not save you here, it hurts: `books replay --check`
    returned 0 of 41, so the check confirmed a snapshot naming a foreign value.

    A typo in an adapter's declaration is caught here too, out loud: a name
    outside the registry would mean the knob list had drifted from it in
    silence -- the very trouble the registry exists against.
    """
    try:
        mine = tuple(det.knobs_read())
    except NotImplementedError:
        raise SystemExit(
            f"адаптер {det.name} не объявил, какие ручки читает "
            f"(models/base.py, knobs_read). Пустой кортеж — законный ответ, "
            f"молчание — нет: молчащий адаптер вернул бы слепок к тому, "
            f"ради чего это объявление и заведено.") from None
    unknown = [n for n in mine if n not in knobs.KNOB]
    if unknown:
        raise SystemExit(
            f"адаптер {det.name} объявил ручки, которых нет в реестре: "
            f"{unknown}. Либо опечатка, либо чтение окружения мимо "
            f"run/knobs.py — обе беды молчаливые.")
    roles = {}
    for n in knobs.names():
        if n in mine:
            roles[n] = f"адаптер {det.name}"
        elif n in COMMAND_KNOBS:
            roles[n] = "команда books detect"
        else:
            roles[n] = None
    return roles


# The shape of the knob snapshot moved into the registry
# (`run/knobs.snapshot_with_readers`): two takers now, detection and reading,
# and the second version had already come out a different shape, rejected by
# `books replay --check`.
_knobs_snapshot = knobs.snapshot_with_readers


_commit = stamp.commit


def _packages():
    return stamp.packages(stamp.DETECT_PACKAGES)


def parse_pages(spec, total):
    """`--pages 1,4,7-9` -> a set of numbers, counting from one.

    Empty value means the whole book. A number outside the book is an error
    out loud. A set given but EMPTY (`3-1`) is an error too: it used to give
    zero pages, exit code 0 and a full snapshot, so an empty run looked like
    success. A zero from misunderstanding.
    """
    if not spec:
        return list(range(total))
    # A SPACE SEPARATES JUST LIKE A COMMA. `--pages "1 3"` used to fall with a
    # bare `ValueError: invalid literal for int()`, caught only in `detect` --
    # `overlay` had its own parser that took spaces. Merging the parsers gave
    # the refusal to both: the rule "complain out loud" was broken in two
    # commands, not one. Both spellings have to be understood.
    want = []
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
                # Out loud and with a sample, not a stack trace: this flag is
                # typed by hand, and a typo in it is routine.
                raise SystemExit(
                    f"в «--pages {spec}» кусок «{part}» — не номер страницы. "
                    f"Ожидается «1,4,7-9» или «1 4 7-9», счёт с единицы.")
    bad = [p for p in want if not 1 <= p <= total]
    if bad:
        raise SystemExit(f"в книге {total} страниц, а запрошены {bad}")
    if not want:
        raise SystemExit(f"набор страниц «{spec}» пуст — считать нечего")
    return [p - 1 for p in sorted(set(want))]


def run(pdf, outdir, pages_spec=None, log=print):
    """Run the detector over the PDF pages. Returns the directory path."""
    import pymupdf

    dpi_raw = knobs.knob("PAGE_DPI")
    dpi = float(dpi_raw)
    # We render at an integer and write THAT into the snapshot, not the
    # fractional original: `get_pixmap` truncates, and at `PAGE_DPI=143.5` the
    # snapshot would lie.
    dpi_used = int(dpi)
    if dpi_used != dpi:
        log(f"ВНИМАНИЕ: PAGE_DPI={dpi_raw} усечён до {dpi_used} — "
            f"растр рисуется целым числом точек на дюйм")

    pdf = os.path.abspath(pdf)
    outdir = os.path.abspath(outdir)
    pagedir = os.path.join(outdir, "pages")

    # The input is checked BEFORE the detector comes up: otherwise a typo in
    # the file name made the operator wait for the weights, read the label
    # vocabulary and collect five frames of `pymupdf.FileNotFoundError`. Every
    # neighbouring command answers a bad path in one line. IT CATCHES ONLY
    # ABSENCE AND A DIRECTORY: an empty file, a non-PDF and a book with no
    # pages are caught below, at the open.
    if not os.path.exists(pdf):
        raise SystemExit(f"нет файла {pdf}")
    if os.path.isdir(pdf):
        raise SystemExit(f"{pdf} — каталог, а ожидается PDF одной книги")

    det = _adapter()
    # The policy must cover the weights vocabulary WHOLE and name nothing
    # extra. Checked every run: changing weights is the likeliest way to
    # acquire a twenty-sixth class. The MODEL'S VOCABULARY picks the policy,
    # not the weights' name -- a name can be confused, the class list comes
    # from the weights themselves.
    pol = getattr(det, "policy_name", None) or policy.for_labels(det.labels)
    det.policy_name = pol
    policy.check(det.labels, policy=pol)
    arte = tuple(sorted(l for l, r in policy.POLICIES[pol].items()
                        if r == "artifact"))
    # The same single vocabulary, for block label spelling too. The union
    # `policy.ROLE` is no good here for the reason it is a union.
    known = set(policy.POLICIES[pol])
    for line in det.threshold_drift():
        # Loudly: a silent divergence means the run went on our number
        # instead of the model's.
        log(f"ВНИМАНИЕ: порог задан не родной — {line}")

    # What the operator set, by value and by name; what this adapter cannot
    # digest, on its own line. Measured before it:
    # `LAYOUT_ADAPTER=docling LAYOUT_MODEL_NAME=PP-DocLayout_plus-L` gave 0
    # mentions of the knob in the log over 12 pages and a snapshot marking it
    # "set externally: true" beside a value heron never saw -- while the
    # operator is sure they configured something.
    roles = _knob_roles(det)
    given = [n for n in knobs.names() if n in os.environ]
    dead = [n for n in given if roles[n] is None]
    # The zero is printed TOO: a zero from a check ("we asked, nothing is
    # set"), not the silence of a step that may not have run.
    log(f"задано снаружи ручек {len(given)}"
        + (f": {', '.join(given)}" if given else ""))
    if dead:
        log(f"ВНИМАНИЕ: из них {len(dead)} не читает ни адаптер {det.name}, "
            f"ни сама команда: {', '.join(dead)} — заданное значение на этот "
            f"прогон НЕ влияет, в слепке оно помечено «к этому прогону "
            f"относится: false»")
    log(f"детектор {det.name}: "
        f"{det.fingerprint().get('model')} из {det.dir}")
    # About the input we ask the FINGERPRINT, not one adapter's fields: the
    # second adapter had none, and a hard `det.keep_ratio` dropped the run on
    # the first foreign model. Every adapter must have a fingerprint -- that is
    # the contract.
    fp_in = (det.fingerprint().get("input") or {})
    log(f"вход модели {fp_in.get('width')}x{fp_in.get('height')} (ШxВ): "
        + ", ".join(f"{k}={v}" for k, v in fp_in.items()
                    if k not in ("width", "height")))
    log(f"словарь {pol}, "
        f"классов {len(det.labels)}, "
        f"родной порог {det.fingerprint().get('native_threshold')}")

    # Opening speaks IN A LINE too: the three troubles the check above misses
    # used to come out as tracebacks -- an empty file (`EmptyFileError`), a
    # non-PDF under a pdf name (`FileDataError`), a book with no pages. All
    # three checked; the exception classes are foreign and deliberately not
    # named -- pymupdf has its own list, and it has changed.
    try:
        doc = pymupdf.open(pdf)
        pages_total = doc.page_count
    except Exception as e:                      # noqa: BLE001 — чужая иерархия
        raise SystemExit(
            f"{pdf} не открывается как PDF: {type(e).__name__}: {e}") from None
    if not pages_total:
        raise SystemExit(f"{pdf} открылся, но страниц в нём ноль — считать нечего")
    idxs = parse_pages(pages_spec, pages_total)

    # Foreign pages in the directory are no trifle: the earlier run may have
    # gone at another threshold, dpi or weights, and mixed in they give the
    # metric a sample from two runs while `run.json` says nothing. Exactly the
    # lesson the registry records for `RESUME`.
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
    spellings = set()
    # THERE ARE TWO STAGES, COUNTED APART. `counts` is gathered over blocks
    # that reached json, AFTER the vendor pipeline if it is on; `model_boxes`
    # is what the model gave above the threshold (its own number, put in `meta`
    # by the adapter). The difference is what the pipeline removed.
    model_boxes = mute_pages = 0
    pipe = {"page_count": 0, "before": 0, "after": 0, "children": 0, "reordered": 0,
            "modes": set(), "missing_numbers": set()}
    try:
        for n, i in enumerate(idxs, 1):
            doc[i].get_pixmap(dpi=dpi_used).save(tmp)
            page = det.read(tmp, i, float(dpi_used))
            # BEFORE writing to disk: a page with an unrecognised label
            # spelling must not enter the directory at all -- the metric would
            # pick it up.
            _check_labels(page, pol, known, det.name)
            spellings.update(b.label for b in page.blocks)
            mk = page.meta.get("boxes_accepted")
            if mk is None:
                mute_pages += 1          # the adapter did not say: not a zero
            else:
                model_boxes += int(mk)
            pm = page.meta.get("docling_pipeline")
            if pm:
                pipe["page_count"] += 1
                pipe["modes"].add(pm.get("mode"))
                for key, margin in (("boxes_before", "before"),
                                   ("boxes_after", "after"),
                                   ("moved_to_children", "children"),
                                   ("boxes_reordered", "reordered")):
                    v = pm.get(key)
                    if v is None:
                        pipe["missing_numbers"].add(key)
                    else:
                        pipe[margin] += int(v)
            with open(os.path.join(pagedir, f"{i:04d}.json"), "w",
                      encoding="utf-8") as f:
                json.dump(page.to_json(), f, ensure_ascii=False)
            ties += page.meta["rank_ties"]
            for lab, s in page.meta["best_rejected_by_class"].items():
                if s > rej_best.get(lab, 0.0):
                    rej_best[lab] = s
                    rej_pages[lab] = i          # WHERE it was best
                # "On how many pages rejected" was dropped from here: the raw
                # output carries three hundred rows a page and covers almost
                # every class almost always, so the number equalled the page
                # count at any threshold. It could not fall, and read as a
                # measurement.
            for b in page.blocks:
                counts[b.label] = counts.get(b.label, 0) + 1
                artefacts += b.label in arte
            if n % 10 == 0 or n == len(idxs):
                log(f"  {n}/{len(idxs)} страниц, рамок {sum(counts.values())}")
    finally:
        doc.close()
        if os.path.exists(tmp):
            os.unlink(tmp)

    took = time.time() - t0
    total = sum(counts.values())
    mode = "/".join(sorted(str(m) for m in pipe["modes"]))
    had_pipeline = bool(pipe["page_count"])
    # The stage note is set ONLY when the pipeline really ran: with it off
    # every number is the model's anyway, and an extra word would make earlier
    # runs incomparable by eye for nothing.
    box_stage = (f"после конвейера docling {mode}" if had_pipeline
                  else "у модели, конвейера над рамками не было")
    log(f"рамок {total} на {len(idxs)} страницах "
        f"({total/len(idxs):.1f} на страницу), артефактов {artefacts}, "
        f"связок рангов {ties}, {took:.1f} с ({took/len(idxs):.2f} с/страница)"
        + (f" — все числа рамок ПОСЛЕ конвейера docling {mode}"
           if had_pipeline else ""))

    # WHAT THE PIPELINE REMOVED IS A QUANTITY OF ITS OWN, NOT A CORRECTION TO
    # "ACCEPTED". Until it existed, "text accepted 130" with the knob on was
    # indistinguishable from "the model found 130", visible only through a
    # second run with the knob off. The measurement that exposed it
    # (bench/matematika, docling, off -> post): text 143 -> 130,
    # section_header 9 -> 7, formula 4 -> 3, while the "best rejected" of those
    # classes (0.480 / 0.425 / 0.476) matched to the digit, being removed by
    # the threshold BEFORE the pipeline.
    if mute_pages:
        log(f"ВНИМАНИЕ: на {mute_pages} страницах из {len(idxs)} адаптер "
            f"{det.name} не сказал «рамок принято» — сколько отдала сама "
            f"модель, сверить нечем; сложенное ниже неполно на эти страницы")
    if had_pipeline:
        took = pipe["before"] - pipe["after"]
        share = 100.0 * took / pipe["before"] if pipe["before"] else 0.0
        log(f"конвейер docling {mode}: модель отдала рамок {pipe['before']}, "
            f"он снял {took} ({share:.1f}%), в книгу пошло {pipe['after']}, "
            f"ушло в дети {pipe['children']}, переставлено {pipe['reordered']}, "
            f"страниц через него {pipe['page_count']} из {len(idxs)}")
        # The removals are NOT broken down by label, and silence about that
        # is not allowed: "table accepted 0" with the knob on would read as
        # "the model found none" when it may mean "it did, the pipeline
        # removed it".
        log(f"    снятое конвейером по ярлыкам НЕ разложено: адаптер отдаёт "
            f"«рамок до» только итогом ({pipe['before']}), по классам их нет "
            f"(models/docling_heron.py, pipe_meta)")
        if pipe["missing_numbers"]:
            log(f"ВНИМАНИЕ: конвейер не дал чисел {sorted(pipe['missing_numbers'])} "
                f"— сложенное выше на столько же неполно")
        if pipe["page_count"] != len(idxs):
            log(f"ВНИМАНИЕ: через конвейер прошли {pipe['page_count']} страниц "
                f"из {len(idxs)} — числа этапов сложены по разным выборкам")
        if pipe["after"] != total:
            log(f"ВНИМАНИЕ: конвейер отчитался о {pipe['after']} рамках после "
                f"себя, а в страницах их {total}: разница "
                f"{abs(pipe['after'] - total)}")
        if not mute_pages and pipe["before"] != model_boxes:
            log(f"ВНИМАНИЕ: конвейер принял {pipe['before']} рамок, а модель "
                f"отдала {model_boxes}: разница "
                f"{abs(pipe['before'] - model_boxes)} рамок потеряна между "
                f"этапами")
    else:
        # A zero from a check, not the silence of a step: it says there WAS
        # no pipeline, and says it with the number of pages it was not on.
        log(f"конвейер вендора рамок не касался: страниц через него 0 из "
            f"{len(idxs)}, «принято» ниже — рамки самой модели")
        if not mute_pages and model_boxes != total:
            log(f"ВНИМАНИЕ: модель отдала {model_boxes} рамок, а в страницах "
                f"их {total} при отсутствии конвейера: рамки правит кто-то "
                f"неназванный")

    # A quantity, not "verified": how many label spellings met, out of how
    # many known. Foreign ones are always zero -- not because they do not
    # happen, but because such a run never gets this far (`_check_labels` drops
    # it on that very page).
    log(f"написаний ярлыков сверено со словарём «{pol}»: {len(spellings)} "
        f"из {len(known)} известных, чужих 0 — иначе прогон бы упал")

    # By class -- accepted AND best rejected. Without the second number
    # "table 0" reads as "there are no tables" when it may mean "the table was
    # 0.03 below the threshold": the first trouble is the model's, the second a
    # knob's. Measured on bench/real/tables20.pdf: at the native threshold a
    # table is found on 4 pages of 20, and the pages were selected for tables.
    # We show what was found and ALL artefact labels, even at zero; the rest of
    # the rejected go into one line, because twenty-five classes in a row drown
    # the one number the report is written for.
    shown = sorted(set(counts) | set(arte),
                   key=lambda l: (-counts.get(l, 0), l))
    # THE STAGES ARE NAMED because there are two. Two numbers about one label
    # on one line, about different stages, the reader adds into one -- and gets
    # "the box was 0.02 below the threshold" where it was accepted by the model
    # and removed afterwards by the vendor.
    if had_pipeline:
        log(f"    по классам ДВА ЭТАПА: «принято» — {box_stage}; «лучший "
            f"отвергнутый» — порог модели ДО него. Складывать их нельзя.")
    else:
        log(f"    по классам, оба числа от модели ({box_stage}): «принято» "
            f"— рамки выше порога, «лучший отвергнутый» — лучшая ниже него")
    mark = " (после конвейера)" if had_pipeline else ""
    answer_mark = ", ДО конвейера" if had_pipeline else ""
    for lab in shown:
        line = f"    {lab:18s} принято{mark} {counts.get(lab, 0):5d}"
        if lab in rej_best:
            line += (f", лучший отвергнутый {rej_best[lab]:.3f} "
                     f"(стр. {rej_pages[lab]}{answer_mark})")
        log(line)
    rest = {l: v for l, v in rej_best.items() if l not in shown}
    if rest:
        top = max(rest.items(), key=lambda kv: kv[1])
        log(f"    прочих классов отвергнуто {len(rest)}, "
            f"выше всех {top[0]} {top[1]:.3f}"
            + (" (всё — порогом модели, ДО конвейера)" if had_pipeline
               else ""))

    if total == 0:
        raise RuntimeError(
            f"ни одной рамки на {len(idxs)} страницах — это отказ, а не "
            f"пустая книга. Порог LAYOUT_SCORE_THRESHOLD="
            f"{knobs.knob('LAYOUT_SCORE_THRESHOLD')}, веса {det.dir}. "
            f"Лучшее отвергнутое: {rej_best or 'ничего не отвергнуто вовсе'}")

    here = os.path.dirname(os.path.abspath(__file__))
    fp = det.fingerprint()
    snap = {
        # The date beside the number: without it a measurement cannot say
        # what it was applied to.
        "when": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "knobs": _knobs_snapshot(roles),
        # A summary in the same number as the log: nobody reads twenty
        # entries to answer "what was actually acting here".
        "run_knobs": {
            "read_by_active_adapter": [n for n in knobs.names()
                                        if roles[n] and n not in COMMAND_KNOBS],
            "read_by_detect_command": [n for n in knobs.names()
                                           if roles[n] and n in COMMAND_KNOBS],
            "not_for_this_run": [n for n in knobs.names()
                                             if roles[n] is None],
            "set_externally": given,
            "set_externally_unread": dead,
        },
        "raster": {"scale": dpi_used / 72.0, "dpi": float(dpi_used),
                  "page_dpi_as_given": dpi_raw},
        "args": {"pdf": pdf, "pages": pages_spec, "out": outdir},
        "commit": _commit(),
        "source": {"path": pdf, "sha256": _sha256(pdf)},
        # BOTH files that decide the result are hashed: only the adapter used
        # to be counted, while artefact policy and page parsing live here. And
        # the sha256 OF THE ACTIVE ADAPTER'S FILE, not always doclayout.py -- a
        # yolox run used to swear by a foreign module's hash, so an edit in
        # docling_heron.py or yolox_layout.py was invisible and two detectors
        # gave indistinguishable snapshots.
        "adapter": {"name": det.name,
                    "module": type(det).__module__,
                    "sha256": _sha256(sys.modules[type(det).__module__].__file__),
                    "sha256_command": _sha256(os.path.join(here,
                                                           "detect.py"))},
        "policy": policy.snapshot(getattr(det, "policy_name", None)),
        "prompts": {},
        "generation": {"temperature": None, "max_tokens": None,
                       "top_p": None, "seed": None},
        "packages": _packages(),
        "weights": {"vl": None, "layout": fp["sha256_weights"]},
        "fingerprint": fp,
        "summary": {"page_count": len(idxs), "box_count": total,
                 "artifacts": artefacts, "rank_ties": ties,
                 "seconds": round(took, 2), "by_label": counts,
                 "best_rejected": rej_best,
                 "pages_with_rejected": rej_pages,
                 # WHOSE STAGE THIS IS -- beside the numbers, not only in the
                 # log: without this record two runs' snapshots would differ by
                 # one line in the knob registry, and their summary numbers by
                 # a whole stage.
                 "stages": {
                     "box_counts_stage":
                         box_stage,
                     "best_rejected_stage":
                         "порогом модели, ДО конвейера вендора",
                     # An incomplete sum is NOT a quantity: a page the
                     # adapter kept quiet about makes it smaller by exactly
                     # what we do not know. So either a number, or `null`
                     # beside the count of silent pages.
                     "boxes_from_model":
                         None if mute_pages else model_boxes,
                     "pages_without_boxes_accepted":
                         mute_pages,
                     "vendor_pipeline": {
                         "stage_ran": had_pipeline,
                         "modes": sorted(str(m) for m in pipe["modes"]),
                         "pages_through_it": pipe["page_count"],
                         "pages_in_run": len(idxs),
                         "boxes_before": pipe["before"],
                         "boxes_after": pipe["after"],
                         "boxes_removed": pipe["before"] - pipe["after"],
                         "moved_to_children": pipe["children"],
                         "boxes_reordered": pipe["reordered"],
                         # A value, not a gap: removals are not broken down
                         # by label because the adapter gives "boxes before"
                         # only as a total.
                         "removed_by_label": None,
                         "why_removed_by_label_empty":
                             ("адаптер отдаёт «рамок до» одним числом на "
                              "страницу; по классам их нет — см. pipe_meta "
                              "в models/docling_heron.py"),
                         "numbers_never_given":
                             sorted(pipe["missing_numbers"]),
                     },
                 }},
        # The line must be runnable: 8 of the 9 files in raw/ carry spaces or
        # brackets, and an unquoted repeat line is not a repeat line but a
        # description of one.
        "repeat_command": " ".join(shlex.quote(a) for a in
                           ["books", "detect", pdf, "--out", outdir]
                           + (["--pages", str(pages_spec)] if pages_spec else [])),
    }
    with open(os.path.join(outdir, "run.json"), "w", encoding="utf-8") as f:
        json.dump(snap, f, ensure_ascii=False, indent=1)
    log(f"слепок: {os.path.join(outdir, 'run.json')}")
    return outdir
