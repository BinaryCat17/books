"""Single entry point: books <command>.

    books doctor                 check everything BEFORE the money starts
    books offers                 look at the market, renting nothing
    books prepare book.djvu      djvu -> PDF, spreads cut apart
    books detect book.pdf        LEVEL ONE: contours, local and free
    books read book.detect/      LEVEL TWO: read the blocks with a model (paid)
    books html book.detect/      build the HTML: text + artefacts as pictures
    books apply book-dir/        put the read markup into the book, source out
                                 of its snapshot; repeats are free, what stands
                                 is not placed twice. --status — report only
    books feed book.detect/      what would go to the VLM: crop or holed page
    books synth                  synthetic bench: pages with exact truth
    books annopage raw/annopage  golden bench: real pages, librarians' truth
    books subset                 distillate: artefacts side by side
    books score truth/ boxes/    contour metrics; --selfcheck — mutation battery
    books text truth/ pages/     READING metric: characters and table cells
    books fitness book.pdf …     will the meaning arrive: by ink, no truth
    books overlay book.pdf …     boxes over pages, to look with your own eyes
    books ls | books down 12345 | books reap
    books ledger                 run journal and the estimate from it
    books replay --check out/    is the input snapshot complete

THE LIST IS CHECKED AGAINST `sub.add_parser`: six commands of twenty were
missing — `fitness`, `subset`, `annopage`, `read`, `apply` (then `swap`),
`text` — the whole of level two, invisible to whoever reads the header.

Level two repairs nothing, keeps what it observed beside the block, and is
checked at home against a stand-in server: 27 checks, not one cent.
"""
import argparse
import json
import re
import os
import sys

from . import config
from .models import paddleocr_vl
from .remote import ledger as ledger_mod
from .remote.spec import HostReq
from .remote.vast import Vast, log
from .run import knobs
from .run import replay as replay_mod


def _host_args(ap):
    ap.add_argument("--gpu", default="RTX_4090",
                    help="RTX_4090 / RTX_5090 / A100_PCIE ...")
    ap.add_argument("--max-dph", type=float, default=0.60, help="потолок $/час")
    ap.add_argument("--disk", type=int, default=60, help="диск инстанса, ГБ")
    ap.add_argument("--machine", type=int,
                    help="привязаться к machine_id с прогретым кешем")
    ap.add_argument("--image", help="переопределить docker-образ")


def cmd_offers(a):
    """Show the market as the ranking sees it. Rents nothing."""
    host = HostReq(gpu=a.gpu, disk_gb=a.disk, max_dph=a.max_dph,
                   machine_id=a.machine)
    # The CUDA requirement comes FROM THE MODEL, not from the rental layer:
    # `HostReq` has no default on purpose. Whoever builds the job names it.
    host.cuda_min = paddleocr_vl.CUDA_MIN
    v = Vast()
    warm = ledger_mod.warm_machines(a.image or paddleocr_vl.BASE_IMAGE)
    v.pick(host, paddleocr_vl.IMAGE_GB, a.minutes, warm, show=8,
           payload_gb=paddleocr_vl.PAYLOAD_GB, warmup_s=paddleocr_vl.WARMUP_S)
    return 0


def cmd_prepare(a):
    """djvu -> PDF with the spreads cut apart. Local and free.

    Its own command, not merely a step inside the parse: spreads must be seen
    with the eye before paying for a card. Two of the three books added lay as
    spreads, and the recogniser would read two pages as one.
    """
    from . import djvu
    print(djvu.to_pdf(a.file, dst=a.out, split=a.split))
    return 0


def cmd_detect(a):
    """Level-one contours over the PDF pages. No VLM, no rental, no money."""
    import shlex
    from . import detect
    out = a.out or os.path.splitext(a.file)[0] + ".detect"
    detect.run(a.file, out, a.pages, log=log)
    # Quoted: five of the nine files in raw/ carry spaces and brackets, and a
    # hint you cannot paste into a shell is not a hint.
    log(f"проверить полноту слепка: books replay --check {shlex.quote(out)}")
    return 0


# --------------------------------------------- the directories commands take
# `books detect` leaves TWO directories side by side: `<out>` with the snapshot
# `run.json`, and `<out>/pages` with the layout pages. Half the commands wanted
# the first (`html`, `feed`, `replay --check`), half the second (`score`,
# `text`, `fitness --detect`), and the operator learned which from a six-frame
# traceback. Below both forms are taken by both sides, and a missing path fails
# in ONE line naming what it expected.


def _page_files(d):
    """(how many layout pages, and if zero — why exactly).

    The selection is `metrics._load`'s: `.json` except `run.json`, `blocks`
    and `index` inside. Let them diverge and this accepts a directory the
    metric then dies on, moving the clear message one step away.

    ONE file is opened, the first by name: reading the 600 golden pages to
    choose a directory is expensive, and a book root differs from a page
    directory by the first file already (`manifest.json` against `0000.json`).

    The reason comes back as a second value because the zeroes DIFFER: "no json
    at all" and "json, but not pages" are two different mistakes, and one line
    for both swaps one zero for the other.
    """
    if not os.path.isdir(d):
        return 0, "не каталог"
    names = sorted(f for f in os.listdir(d)
                   if f.endswith(".json") and f != "run.json")
    if not names:
        return 0, "json-файлов нет вовсе"
    try:
        with open(os.path.join(d, names[0]), encoding="utf-8") as f:
            first = json.load(f)
    except (OSError, ValueError) as e:
        return 0, f"{names[0]} не читается как json ({type(e).__name__})"
    if not (isinstance(first, dict) and "blocks" in first
            and "index" in first):
        return 0, (f"json-файлов {len(names)}, но {names[0]} — не страница "
                   f"разметки: нет полей blocks/index")
    return len(names), ""


def _pages_dir(path, what):
    """The PAGE directory: out of the run directory, or itself.

    `<out>/pages` comes back, not `<out>`: `metrics._same_book` looks for
    `run.json` IN THE PARENT of the directory given, so substituting the parent
    silently switches off the sha256 check of truth against output — the one
    catching one book's truth scored against another book's boxes.
    """
    if not os.path.exists(path):
        raise SystemExit(
            f"{what}: нет пути {path}. Ожидается каталог прогона "
            f"`books detect` (в нём pages/ и run.json) или сам каталог "
            f"страниц разметки (*.json).")
    sub = os.path.join(path, "pages")
    (here, why_here), (there, why_sub) = _page_files(path), _page_files(sub)
    if there and not here:
        # A value, not silence: a substituted directory must show in the
        # journal, or "measured the wrong thing" reads like "measured".
        log(f"{what}: подан каталог прогона, страницы беру из {sub} — их "
            f"{there}")
        return sub
    if here:
        return path
    raise SystemExit(
        f"{what}: страниц разметки не нашлось. В {path} — {why_here}; "
        f"в {sub} — {why_sub}. Ожидается каталог прогона `books detect` "
        f"(в нём pages/ и run.json) или сам каталог страниц. Считать "
        f"нечего — и это не ноль потерь.")


def _run_dir(path, what):
    """The RUN directory: the one holding `run.json`. Takes `<out>/pages` too.

    The other side of the same trouble: `books feed bench/…/detect/pages` died
    with `FileNotFoundError` on `pages/run.json`, never saying it wanted the
    parent.
    """
    if not os.path.exists(path):
        raise SystemExit(
            f"{what}: нет пути {path}. Ожидается каталог прогона "
            f"`books detect` — тот, где лежит run.json.")
    if os.path.exists(os.path.join(path, "run.json")):
        return path
    up = os.path.dirname(os.path.abspath(path.rstrip("/")))
    if _page_files(path)[0] and os.path.exists(os.path.join(up, "run.json")):
        log(f"{what}: подан каталог страниц, слепок беру из {up}")
        return up
    raise SystemExit(
        f"{what}: в {path} нет run.json. Ожидается каталог прогона "
        f"`books detect` (в нём pages/ и run.json), а не каталог страниц и "
        f"не корень книги.")


def book_home(detect_dir: str) -> str:
    """Where the book lands BY DEFAULT: somewhere permanent, not beside the run.

    The default was `<run directory>/html`, true up to the first run in a
    temporary directory: the book was built, read with the eye, and vanished
    with it. Measured that evening: both books — 378 and 539 pages, $0.47 of
    rental — landed in `/tmp` and had to be moved by hand.

    The name comes from the SOURCE: a book must be findable by the file it was
    made from. Unsafe characters are replaced and the length cut, recognisably.
    """
    with open(os.path.join(detect_dir, "run.json"), encoding="utf-8") as f:
        snap = json.load(f)
    stem = os.path.splitext(os.path.basename(snap["source"]["path"]))[0]
    safe = re.sub(r"[^\w.,()-]+", "-", stem, flags=re.UNICODE).strip("-")[:80]
    return os.path.join(config.ROOT, "processed", safe or "book")


def cmd_html(a):
    """Level one's product: text as markup, artefacts as pictures."""
    from .doc import html as html_mod
    d = _run_dir(a.dir, "books html")
    out = a.out or book_home(d)
    # FOREIGN WORK IS NOT OVERWRITTEN: the tell of ours is the snapshot the
    # builder writes, and a non-empty directory without it means refusal out
    # loud. THE TELL IS ASKED OF THE BUILDER, NOT TYPED HERE: the snapshot
    # moved into `assets/`, and this check, looking for `run.json` in the ROOT,
    # began refusing directories this same command had made a minute earlier —
    # refusing with a LIE, "probably a book of the old pipeline", of which none
    # remain, and refusing the advice the build itself prints along with them.
    if (not a.out and os.path.isdir(out) and os.listdir(out)
            and not html_mod.is_our_dir(out)):
        raise SystemExit(
            f"в {out} уже лежит что-то не наше: нет ни "
            f"`{html_mod.ASSETS}/run.json`, ни `run.json` в корне — значит "
            f"каталог собран не `books html`. Затирать его молча нельзя: "
            f"задайте --out либо уберите каталог руками.")
    html_mod.build(d, out, log=log)
    return 0


def cmd_apply(a):
    """Level two in place: markup instead of the picture, and back again.

    Not one call to a model here: this layer only places a ready fragment, and
    what generated it — `books read`, or a hand — is not its business.
    """
    from .doc import apply as ap
    # NOT `_run_dir`: that one looks for the DETECTION `run.json` and on
    # refusal points at a directory with `pages/`, while this command wants the
    # BUILD directory, the one with `book.html`. The old check refused the
    # right directory and advised the wrong one.
    d = os.path.abspath(a.dir)
    try:
        if a.from_read:
            if a.anchor or a.undo:
                raise ap.SwapError(
                    "--from вместе с --anchor или --undo: это разные работы. "
                    "--from ставит ВСЁ прочитанное, --anchor — один блок.")
            ap.from_read(d, a.from_read, log=log)
            return 0
        if a.status:
            ap.status(d, log=log)
            return 0
        if a.undo and not a.anchor:
            raise ap.SwapError(
                "--undo без --anchor: назови блок, который откатывать. "
                "Без имени команда откатила бы неизвестно что; список "
                "заменённых даёт `books apply <каталог> --status`.")
        if a.undo:
            ap.undo(d, a.anchor, log=log)
        elif a.anchor:
            if not a.file:
                raise ap.SwapError("нечего ставить: дай --file с разметкой "
                                   "блока либо --undo")
            with open(a.file, encoding="utf-8") as f:
                ap.put(d, a.anchor, f.read(), kind=a.kind,
                       source=a.source or os.path.basename(a.file), log=log)
        else:
            # NO KEYS — DO THE WORK, not a report: the book remembers which
            # read it was built from, and `books apply book` is what a person
            # types first. Safe only with idempotence: a repeat places nothing
            # and does not grow the undo stack. Before it, a second `--from` on
            # the same book said "placed 412" with the content unchanged and
            # doubled the journal (412 swaps -> 824). The report lives on under
            # `--status`, and the work prints it too.
            src = ap.source_of(d)
            if not src:
                raise ap.SwapError(
                    f"{d}: не знаю, что ставить. В `{ap.ASSETS}/run.json` нет "
                    f"пути каталога чтения либо его больше нет на диске — "
                    f"назови его сам: `books apply {os.path.basename(d)} "
                    f"--from <каталог books read>`. Что уже заменено, "
                    f"покажет `--status`.")
            log(f"источник взят из слепка книги: {src}")
            ap.from_read(d, src, log=log)
    except ap.SwapError as e:
        log(str(e))
        return 1
    return 0


def cmd_read_rented(a, policy_name, out):
    """The same work on a RENTED card. A branch, not a command of its own:
    same code, same count, only the place changes.

    WHY IT EXISTS. `models/paddleocr_vl.spec()` and `remote.run_job()` were
    called by NOT ONE command — grep over the whole tree found definitions and
    prose only. "Read on a rented card" could be started by nothing, and that
    surfaced from the direct question "with which command?", not from reading
    the code.
    """
    from .models import paddleocr_vl as vl
    from .remote import runner

    spec = vl.spec(_pdf_of(a.dir), a.dir, pages=a.pages, policy=policy_name,
                   budget_usd=a.budget, timeout_minutes=a.timeout)
    log(f"задание {spec.name}: вход {len(spec.inputs)} путей, потолок "
        f"${spec.budget_usd:.2f} и {spec.timeout_minutes:.0f} мин, карта "
        f"{spec.host.gpu}, CUDA от {spec.host.cuda_min}")
    # THE MONEY CEILING IS UNREACHABLE WHILE IT EXCEEDS THE HOURLY PRICE.
    # `Budget` takes the smaller of the two, so at a price ceiling of
    # $0.60/hour a $0.60 limit means exactly one hour: time always cuts, money
    # never. Whoever pays is told, not whoever later reads the journal.
    by_money_h = a.budget / max(spec.host.max_dph, 1e-9)
    if by_money_h * 60 >= a.timeout:
        log(f"  ВНИМАНИЕ: при цене до ${spec.host.max_dph:.2f}/час потолок "
            f"${a.budget:.2f} — это {by_money_h:.1f} ч, то есть больше "
            f"{a.timeout:.0f} мин таймаута. Резать будет ВРЕМЯ; настоящая "
            f"верхняя трата — ${spec.host.max_dph * a.timeout / 60:.2f}")
    if a.dry_run:
        log("--dry-run: ничего не арендую, задание собрано и проверено")
        return 0
    rc = runner.run_job(spec, out, ssh_key=config.ssh_key(a.key),
                        dry_run=False)
    log(f"задача вернула {rc}; результат в {out}")
    if rc == 0:
        log(f"дальше: books text <истина> {out}/pages   |   books html {out}")
    return rc


def cmd_read(a):
    """LEVEL TWO: read the content of the blocks with a model.

    The only command spending money outside the rental, and therefore the only
    one asking the endpoint its name BEFORE the first request, dropping the run
    on a mismatch.

    The product is detection's own `pages/*.json` with `content` and `kind`
    filled in, so `books html`, `text`, `score`, `fitness` and `overlay` eat it
    unchanged.
    """
    from .read import http as vhttp
    from .read import run as vread

    out = a.out or (os.path.abspath(a.dir).rstrip("/") + ".read")
    # THE LABEL DICTIONARY COMES FROM THE DETECTION SNAPSHOT, not typed by
    # hand: `run.json` already carries `policy.vocabulary`. A typed default
    # diverged silently, caught only BY CHANCE on a label the other dictionary
    # lacks. Measured: `DocLayNet` (11 labels) is a strict subset of
    # `Docling-egret` (17), so that pair passes without a word while the
    # snapshot files two incompatible claims side by side.
    known = json.load(open(os.path.join(a.dir, "run.json"), encoding="utf-8")
                      ).get("policy", {}).get("vocabulary")
    policy_name = a.policy or known
    if not policy_name:
        raise SystemExit(
            f"в слепке {a.dir}/run.json не назван словарь ярлыков, и --policy "
            f"не задан. Спрашивать по угаданному словарю значит вести таблицу "
            f"промтом текста и записать прозу чтением.")
    if a.policy and known and a.policy != known:
        raise SystemExit(
            f"--policy {a.policy!r} против словаря детекции {known!r}. "
            f"Совпадающие ярлыки прошли бы молча, а слепок положил бы рядом "
            f"два несовместимых утверждения. Убери --policy или пересчитай "
            f"детекцию тем детектором, чьим словарём собрался читать.")
    os.makedirs(out, exist_ok=True)
    if a.rent:
        return cmd_read_rented(a, policy_name, out)

    reader = vread.build_reader(policy_name)
    transport = vhttp.build()

    # WHAT THE ENDPOINT ANSWERS WITH — before the first crop and first cent.
    who = transport.check()
    log(f"адрес {who['endpoint']}: отвечает {who['models_on_server']}, "
        f"спрашиваем {who['asking_for']} — совпало")

    pages = None
    if a.pages:
        from .detect import parse_pages
        import pymupdf
        with pymupdf.open(_pdf_of(a.dir)) as d:
            pages = set(parse_pages(a.pages, d.page_count))

    t = vread.read_book(a.dir, out, reader, transport,
                        resume=not a.no_resume, pages_want=pages, log=log)
    vread.report(t, log=log)
    p = vread.snapshot(a.dir, out, reader, transport, t,
                       {"detect": a.dir, "out": out, "pages": a.pages,
                        "policy": policy_name})
    log(f"слепок: {p}")
    log(f"дальше: books html {out}   |   books text <истина> {out}/pages")
    return 0


def _pdf_of(detect_dir):
    with open(os.path.join(detect_dir, "run.json"), encoding="utf-8") as f:
        return json.load(f)["source"]["path"]


def cmd_feed(a):
    """Prepare what would go to the VLM. Not one call to the model."""
    import glob
    import json as _json
    import pymupdf
    from .doc import feed
    from .models.base import Page

    d = _run_dir(a.dir, "books feed")
    with open(os.path.join(d, "run.json"), encoding="utf-8") as f:
        snap = _json.load(f)
    doc = pymupdf.open(snap["source"]["path"])
    out = a.out or os.path.join(d, "feed")
    page_dpi = float(snap["raster"]["dpi"])
    p = feed.params(page_dpi)
    log(f"подача {p['feed_mode']}, вырезка {p['crop_dpi']:.0f} dpi, "
        f"страница {p['page_dpi']:.0f} dpi, "
        f"заливка дыр {p['hole_fill']}")
    res, asked, arts = [], 0, 0
    for fp in sorted(glob.glob(os.path.join(d, "pages", "*.json"))):
        with open(fp, encoding="utf-8") as f:
            page = Page.from_json(_json.load(f))
        r = feed.prepare(doc, page, out, page_dpi, log=log)
        asked += r["requests"]
        arts += r.get("artifacts_masked", r.get("artifacts_not_sent", 0))
        res.append(r)
    doc.close()
    path = feed.dump({"knobs": p, "pages": res}, out)
    # A number, not "done": the feed is chosen by it.
    log(f"страниц {len(res)}, запросов в VLM {asked} "
        f"({asked/max(len(res),1):.1f} на страницу), артефактов мимо VLM {arts}")
    log(f"{path}; картинки подачи в {out}")
    return 0


def cmd_overlay(a):
    """Boxes over the pages: truth solid, the model's guess dashed."""
    from . import detect, overlay
    marks = [(_pages_dir(a.truth, "--truth"), "И")] if a.truth else []
    if a.detect:
        marks.append((_pages_dir(a.detect, "--detect"), "М"))
    if not marks:
        raise SystemExit("нечего рисовать: задайте --truth и/или --detect")
    out = a.out or os.path.splitext(a.pdf)[0] + ".overlay.pdf"
    only = None
    if a.pages:
        # THE VERY SAME PARSE as `books detect`, not a second copy. The copy
        # that stood here diverged from `detect.parse_pages` THREE ways at once.
        # (1) Counting. `detect` counts FROM ONE; this put the number straight
        #     into the index, so `--pages 40` drew sheet 0040 where `detect`
        #     gives 0039. You look at the wrong sheet and never learn it — and
        #     that is exactly how eyes are used here.
        # (2) Ranges. `--pages 40-42` works in `detect`; here it died on a bare
        #     ValueError: invalid literal for int().
        # (3) Bounds. A number past the end of the book `detect` declares out
        #     loud; here an empty set gave a silent "differences on 0 pages" —
        #     a zero from not understanding, in the final line.
        import pymupdf
        doc = pymupdf.open(a.pdf)
        total = doc.page_count
        doc.close()
        only = detect.parse_pages(a.pages, total)
    overlay.build(a.pdf, out, marks, only=only, log=log)
    return 0


def cmd_score(a):
    """Contour metrics: truth against the model output."""
    from . import metrics
    truth = _pages_dir(a.truth, "истина")
    det = _pages_dir(a.detect, "рамки модели")
    if a.selfcheck:
        return 1 if metrics.mutations(truth, det, log=log) else 0
    metrics.report(metrics.compare(truth, det), log=log)
    return 0


def text_norm_default():
    """The normalisation default comes FROM THE MODULE, not typed here twice.

    A second copy is what the knob registry's header warns of: a changed value
    never reaches the consumer until somebody remembers this file.
    """
    from . import text
    return text.NORM


def cmd_text(a):
    """The reading metric: the truth of characters against what the model read.

    Its own command, not a column in `books score`: that one measures GEOMETRY
    and labels, this one CHARACTERS. One number for two questions is how an
    instrument here already lied — "reading order agreed 73%" on a bench where
    order is not annotated at all.
    """
    from . import text
    truth = _pages_dir(a.truth, "истина")
    pages = _pages_dir(a.pages, "прочитанное")
    if a.selfcheck:
        return 1 if text.mutations(truth, pages, log=log) else 0
    text.report(text.measure(truth, pages, norm=a.norm), log=log)
    return 0


def cmd_fitness(a):
    """Fitness of the output: will the meaning reach level two. By ink."""
    from . import fitness
    det = _pages_dir(a.detect, "--detect")
    truth = _pages_dir(a.truth, "--truth") if a.truth else ""
    if a.selfcheck:
        return 1 if fitness.mutations(a.pdf, det, truth, log=log) else 0
    fitness.report(fitness.measure(a.pdf, det, truth), log=log)
    return 0


def cmd_subset(a):
    """Bench distillate: pages where two artefacts of one label stand side by side."""
    from . import subset
    books = [x.strip() for x in (a.books or
             "spravochnik,slovar,matematika,atlas,katalog,zhurnal,annopage"
             ).split(",") if x.strip()]
    subset.build(books, a.out or "bench/hard", log=log)
    return 0


def cmd_annopage(a):
    """The golden bench from AnnoPage: real pages, librarians' truth."""
    from . import annopage
    out = a.out or "bench/annopage"
    log(f"AnnoPage из {a.root}, выборка {a.split}")
    annopage.build(a.root, out, split=a.split, limit=a.limit,
                   truth_only=a.truth_only, log=log)
    log(f"дальше: books detect {shlex_quote(out)}/annopage.pdf "
        f"--out {shlex_quote(out)}/detect")
    return 0


def cmd_synth(a):
    """Build a synthetic book with exact truth. Local and free."""
    from . import synth
    from .run import knobs
    out = a.out or f"bench/{a.book}"
    cases = a.cases.split(",") if a.cases else None
    from .books import load
    log(f"книга {a.book}: случаев {len(cases or load(a.book).CASES)}, "
        f"старение {knobs.knob('SYNTH_AGING')}, зерно {knobs.knob('SYNTH_SEED')}")
    synth.build(out, cases, int(knobs.knob("SYNTH_SEED")),
                knobs.knob("SYNTH_AGING"), book=a.book, log=log)
    log(f"дальше: books detect {shlex_quote(out)}/{a.book}.pdf "
        f"--out {shlex_quote(out)}/detect")
    return 0


def shlex_quote(s):
    import shlex
    return shlex.quote(s)


def cmd_ls(_a):
    v = Vast()
    rows = v.v.show_instances()
    log(f"баланс: ${v.balance():.3f}")
    if not rows:
        log("инстансов нет — денег не тратится")
        return 0
    for i in rows:
        log(f"  {i['id']}  {i.get('actual_status')}  {i.get('label')}  "
            f"${float(i.get('dph_total') or 0):.3f}/час  "
            f"машина {i.get('machine_id')}  {i.get('gpu_name')}")
    return 0


def cmd_down(a):
    return 0 if Vast().destroy(a.id) else 1


def cmd_reap(_a):
    Vast().reap()
    return 0


def cmd_doctor(_a):
    """Check everything that can wreck a run BEFORE the money starts."""
    import shutil
    ok = True

    def check(name, good, hint=""):
        nonlocal ok
        log(f"  [{'ок  ' if good else 'нет '}] {name}"
            + ("" if good else f" — {hint}"))
        ok = ok and good

    log("проверка окружения:")
    check("rsync локально", shutil.which("rsync") is not None,
          "нужен для инкрементальной выкачки: apt install rsync")
    check("ssh локально", shutil.which("ssh") is not None,
          "apt install openssh-client")
    key = config.ssh_key()
    check(f"ssh-ключ {config.DEFAULT_SSH_KEY}", key is not None,
          "ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519_vast -N ''")
    check("публичная часть ключа", bool(key) and os.path.exists(key + ".pub"),
          "без неё ключ не привязать к инстансу")
    # Not through `check`: without `.env` everything works except paid reading
    # over a NETWORK endpoint, and the vast key lives apart in
    # ~/.config/vastai. Failing acceptance over it is a false alarm, and a
    # false alarm teaches people not to look at acceptance at all.
    #
    # It is NOT for the image build (GHCR), as stood here: those credentials
    # are read by nobody, not even CI (it logs in with `secrets.GITHUB_TOKEN`),
    # and `.env`'s only live tenant is `VLM_API_KEY`, asked for forty lines
    # below. That key can be exported instead — `config.env` looks at the
    # environment first — and a rented card's vLLM listens on the loopback and
    # asks for none.
    if not os.path.exists(config.ENV_FILE):
        log(f"  [ – ] .env в корне — нет; нужен он только для VLM_API_KEY при "
            f"чтении по сетевому адресу. Образец: .env.example")

    try:
        v = Vast()
        bal = v.balance()
        check(f"ключ vast.ai (баланс ${bal:.3f})", True)
        check("баланса хватит хотя бы на прогон", bal > 0.20,
              "пополни: console.vast.ai/billing")
        rows = v.v.show_instances()
        check(f"нет забытых инстансов (сейчас {len(rows)})", not rows,
              "books ls, затем books reap")
    except Exception as e:
        check("ключ vast.ai", False, f"vastai set api-key <КЛЮЧ> ({e})")

    # Separate blocks, and NOT through `check` either: detection and the vendor
    # pipeline install as optional sets, and whoever only rents needs neither.
    # Silence is no better — `books detect` is the first working parse command,
    # and its trouble must show here, not in the middle of a book. Both end AS
    # A VALUE in the last line: a bare "all in order" stood here, and it stayed
    # "in order" with the active adapter having no weights, which the command
    # knew nothing about.
    read_line = _doctor_read()
    det_line = _doctor_detect()
    pipe_line = _doctor_docling()

    log(("окружение аренды в порядке" if ok else "есть проблемы — см. выше")
        + f"; чтение: {read_line}; детекция: {det_line}; "
        + f"конвейер docling: {pipe_line}")
    return 0 if ok else 1


def _doctor_read():
    """Level two: the model endpoint and the key. Returns a line for the summary.

    The key lives OUTSIDE the knob registry on purpose: everything declared
    there lands in `run.json` as a value, and the snapshot goes into git. The
    price is a name invisible to `knobs.readers()` — the `VL_MODEL_DIR` disease
    in miniature — so it must be spoken at least here.
    """
    ep = knobs.knob("VLM_ENDPOINT")
    key = config.env("VLM_API_KEY")
    log("чтение блоков (books read, второй уровень):")
    if ep:
        log(f"  [ок  ] VLM_ENDPOINT={ep}, ключ VLM_API_KEY "
            f"{'есть, %d знаков' % len(key) if key else 'не задан'}")
        return f"адрес задан, ключ {'есть' if key else 'нет'}"
    log("  [—   ] VLM_ENDPOINT не задан: `books read` откажется работать "
        "вслух, а не постучится в никуда. Умолчания нет нарочно. На "
        "арендованной карте адрес ставит run.sh, ключ там не нужен — vLLM "
        "поднят на петле")
    return "адрес не задан (для аренды и не нужен)"


def _doctor_detect():
    """What can count contours today: packages and weights of ALL adapters.

    A check of PP-DocLayoutV2's weights alone stood here, and acceptance
    printed "all in order" knowing nothing of the other three.

    The adapter list comes from `detect.py:ADAPTERS`: a second list drifts
    silently, as the knob registry did against the job builder (13 names of 17)
    and against `ADAPTERS` itself (`LAYOUT_ADAPTER` described two adapters of
    four). The check RAISES the adapter rather than testing a weights path —
    the four name their weights differently (`inference.onnx`, `model.onnx`,
    `yolox_l0.05.onnx` by `YOLOX_WEIGHTS`), and a list of names here would be a
    third one drifting. It costs seconds of CPU, printed as a value so the
    price of acceptance is visible rather than implied.

    Nothing found here fails acceptance: a missing optional set is no disaster.
    It says as a value what is absent and what turns it on.
    """
    import time
    log("детекция макета (books detect, необязательный набор):")
    missing = []
    for mod, why in (("onnxruntime", "счёт детектора"), ("cv2", "raster"),
                     ("yaml", "чтение inference.yml")):
        try:
            __import__(mod)
        except ImportError:
            missing.append(f"{mod} ({why})")
    if missing:
        log(f"  [ – ] нет пакетов: {', '.join(missing)} — "
            f'поставьте: pip install -e ".[detect]"')
        # A zero from checking and a zero from not understanding are DIFFERENT
        # lines: without these packages no adapter rises at all, so there is
        # nothing to call "no weights".
        log("  [ – ] веса адаптеров НЕ ПРОВЕРЕНЫ ни у одного: поднимать их "
            "нечем. Это не «весов нет», это «не смотрели».")
        return ("НЕ ПРОВЕРЕНА — нет пакетов набора detect "
                f"({len(missing)} из 3)")

    from . import detect
    from .run import knobs
    active = knobs.knob("LAYOUT_ADAPTER")
    # The same `_adapter()` `books detect` calls, its name given through the
    # knob: parsing names here would be a fourth list.
    saved = os.environ.get("LAYOUT_ADAPTER")
    have, t0 = [], time.time()
    try:
        for which in detect.ADAPTERS:
            os.environ["LAYOUT_ADAPTER"] = which
            t = time.time()
            try:
                det = detect._adapter()
            except (Exception, SystemExit) as e:         # noqa: BLE001
                # `SystemExit` is caught ON PURPOSE: at
                # `DOCLING_PIPELINE=full` with no vendor package the docling
                # adapter leaves by exactly that, and acceptance catching only
                # `Exception` died on the second adapter of four, saying
                # nothing of it, the two remaining, or the pipeline (rc=1,
                # measured). "No weights" and "weights present, adapter would
                # not rise" are different troubles: a download cures the first,
                # the second breaks the run with a full weights directory.
                kind = ("весов нет" if type(e).__name__ == "WeightsMissing"
                        else f"НЕ ПОДНЯЛСЯ ({type(e).__name__})")
                log(f"  [ – ] {which:14s} {kind}: {e}")
                continue
            w = getattr(det, "onnx", "") or ""
            mb = os.path.getsize(w) / 2 ** 20 if os.path.exists(w) else 0.0
            have.append(which)
            log(f"  [ок  ] {which:14s} {det.name}, ярлыков "
                f"{len(det.labels)}, весов {mb:.0f} МБ, поднялся за "
                f"{time.time() - t:.1f} с — {det.dir}")
            det = None                        # not holding 4 graphs at once
    finally:
        if saved is None:
            os.environ.pop("LAYOUT_ADAPTER", None)
        else:
            os.environ["LAYOUT_ADAPTER"] = saved
    log(f"  адаптеров поднялось {len(have)} из {len(detect.ADAPTERS)}"
        f" ({', '.join(have) if have else 'ни одного'}), проверка заняла "
        f"{time.time() - t0:.0f} с; книгу сейчас считает LAYOUT_ADAPTER="
        f"{active}")
    line = f"адаптеров поднялось {len(have)} из {len(detect.ADAPTERS)}"
    if active not in detect.ADAPTERS:
        log(f"  ВНИМАНИЕ: LAYOUT_ADAPTER={active!r} — такого адаптера нет; "
            f"знаю {', '.join(detect.ADAPTERS)}")
        line += f", но LAYOUT_ADAPTER={active!r} не из этого списка"
    elif active not in have:
        log(f"  ВНИМАНИЕ: активный адаптер {active} не поднялся (причина "
            f"строкой выше) — `books detect` упадёт, не посчитав ни страницы")
        line += f", активный {active} НЕ ПОДНЯЛСЯ"
    return line


def _doctor_docling():
    """The vendor pipeline package: without it `DOCLING_PIPELINE` is a dead knob.

    The PRESENCE of the modules is checked, not their import: `docling.utils.
    layout_postprocessor` takes 8.3 s to rise, and acceptance would pay that
    every time. `rtree` IS imported for real — it pulls the system
    libspatialindex, and "the wheel is there" does not yet mean "it imports";
    that costs 0.2 s.
    """
    import importlib.metadata as md
    import importlib.util as iu
    from .run import knobs

    mode = knobs.knob("DOCLING_PIPELINE")
    log(f"конвейер docling (ручка DOCLING_PIPELINE={mode}, "
        f"необязательный набор):")
    gone = []
    try:
        if iu.find_spec("docling.utils.layout_postprocessor") is None:
            gone.append("docling.utils.layout_postprocessor")
    except (ImportError, ValueError):
        gone.append("docling.utils.layout_postprocessor")
    try:
        __import__("rtree")
    except Exception as e:                               # noqa: BLE001
        gone.append(f"rtree ({type(e).__name__})")
    vers = {}
    for dist in ("docling-slim", "docling", "rtree"):
        try:
            vers[dist] = md.version(dist)
        except md.PackageNotFoundError:
            vers[dist] = None
    if gone:
        log(f"  [ – ] нет: {', '.join(gone)} — поставьте: "
            f'pip install -e ".[docling]". При DOCLING_PIPELINE=post|full '
            f"прогон упадёт вслух, при off (умолчание) он не нужен вовсе")
        return (f"нет {len(gone)} из 2 пакетов"
                + (f", а ручка стоит в {mode}" if mode != "off" else ""))
    # The version comes from the DISTRIBUTION, not `docling.__version__`: one
    # package, two deliveries (`docling-slim` and full), and pyproject pins the
    # version to the point — a vendor rule change would move our boxes
    # silently. With no distribution at all (sources on the path) it says so:
    # "not declared" is not a version.
    ver = (vers["docling-slim"] or vers["docling"]
           or "версия не объявлена (дистрибутива нет, модуль откуда-то ещё)")
    kind = ("slim" if vers["docling-slim"] else
            "полная поставка" if vers["docling"] else "поставка неизвестна")
    log(f"  [ок  ] docling {ver} ({kind}), rtree {vers['rtree']}; "
        f"включается DOCLING_PIPELINE=post|full поверх адаптеров docling и "
        f"docling-egret, сейчас {mode}")
    return f"{ver} + rtree {vers['rtree']}, ручка в {mode}"


def cmd_ledger(_a):
    rows = ledger_mod.read()
    if not rows:
        log(f"журнал пуст ({ledger_mod.LEDGER})")
        return 0
    ok = sum(1 for r in rows if r.get("ok"))
    spent = sum(r.get("cost_usd") or 0 for r in rows)
    log(f"{len(rows)} прогонов, успешных {ok}, потрачено ${spent:.3f}")
    for r in rows[-10:]:
        # NOT MEASURED AND ZERO ARE DIFFERENT THINGS. `else 0` stood here, and
        # a run whose `setup_s` is zero (delivery cut short by a signal) printed
        # as "0 Мбит/с" — "the link is dead" instead of "no measurement". Six
        # such records in the printed ten, 29 over the whole journal, and all
        # six DO carry the image size (0.06 GB): the zero is in `setup_s` alone.
        # A negative `setup_s` means "not measured" too, not a negative speed.
        #
        # The formula lived as a SECOND copy: `ledger.Run.observed_mbps` did the
        # same arithmetic returning `None`, but `asdict` takes no properties, so
        # it never reached the journal. Of the two the dead copy held the right
        # semantics; it is gone and its semantics moved here.
        setup = r.get("setup_s")
        gb = r.get("image_gb")
        mb = (gb * 8 * 1024 / setup) if (setup or 0) > 0 and gb else None
        log(f"  {r.get('started_iso','')}  {r.get('job','')[:22]:22s} "
            f"{'ok ' if r.get('ok') else 'сбой'}  "
            f"старт {r.get('setup_s',0)/60:4.1f}м "
            f"({'  не мерили' if mb is None else f'{mb:4.0f} Мбит/с'})  "
            f"счёт {r.get('run_s',0)/60:5.1f}м  ${r.get('cost_usd',0):.3f}  "
            f"машина {r.get('machine_id')}")
    log(f"оценка по журналу: {ledger_mod.fit()}")
    return 0


def _tool_errors():
    """The "instrument could not count" classes — from ALREADY raised modules.

    Not imported at the top: `metrics` pulls numpy, `text` its own parser, and
    whoever only rents needs no `detect` set. So `sys.modules` is asked: a
    module that never rose could throw nothing. EXACTLY these classes, not
    `Exception` — a traceback from a failed instrument is trouble, one from our
    own bug is evidence, and hiding evidence is not allowed.
    """
    out = []
    for mod, name in (("booksmith.metrics", "MetricError"),
                      ("booksmith.text", "TextError"),
                      ("booksmith.models.doclayout", "WeightsMissing"),
                      ("booksmith.models.docling_heron", "WeightsMissing"),
                      ("booksmith.models.yolox_layout", "WeightsMissing")):
        cls = getattr(sys.modules.get(mod), name, None)
        if isinstance(cls, type) and issubclass(cls, BaseException):
            out.append(cls)
    return tuple(out)


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="books", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("offers", help="показать рынок, ничего не арендуя")
    _host_args(p)
    p.add_argument("--minutes", type=float, default=20.0,
                   help="на сколько минут считать стоимость прогона")
    p.set_defaults(fn=cmd_offers)

    p = sub.add_parser("prepare", help="развернуть djvu в PDF")
    p.add_argument("file")
    p.add_argument("--out", help="куда положить PDF")
    p.add_argument("--split", default="auto", choices=("auto", "yes", "no"),
                   help="резать ли развороты")
    p.set_defaults(fn=cmd_prepare)

    p = sub.add_parser("detect", help="контуры первого уровня, местно")
    p.add_argument("file", help="PDF (djvu разверните через books prepare)")
    p.add_argument("--out", help="куда положить pages/ и run.json")
    p.add_argument("--pages", help="какие страницы: 1,4,7-9; по умолчанию все")
    p.set_defaults(fn=cmd_detect)

    p = sub.add_parser("html", help="собрать HTML из каталога books detect")
    p.add_argument("dir", help="каталог, куда писал books detect")
    p.add_argument("--out", help="куда положить book.html и assets/")
    p.set_defaults(fn=cmd_html)

    p = sub.add_parser("feed", help="что уехало бы в VLM, без обращения к ней")
    p.add_argument("dir", help="каталог, куда писал books detect")
    p.add_argument("--out", help="куда положить картинки подачи")
    p.set_defaults(fn=cmd_feed)

    p = sub.add_parser("fitness",
                       help="годен ли вывод, чтобы гнать через него OCR")
    p.add_argument("pdf", help="страницы, по которым считать чернила")
    p.add_argument("--detect", required=True, help="каталог вывода модели")
    p.add_argument("--truth", default="", help="истина; без неё считается "
                   "только то, что вне всех рамок")
    p.add_argument("--selfcheck", action="store_true",
                   help="батарея порчи: умеет ли число упасть")
    p.set_defaults(fn=cmd_fitness)

    p = sub.add_parser("subset", help="выжимка: артефакты бок о бок")
    p.add_argument("--books", help="какие книги стенда, через запятую")
    p.add_argument("--out", help="куда положить hard.pdf и truth/")
    p.set_defaults(fn=cmd_subset)

    p = sub.add_parser("annopage", help="золотой стенд из датасета AnnoPage")
    p.add_argument("root", help="корень распакованного AnnoPage")
    p.add_argument("--split", default="test", help="test | train")
    p.add_argument("--limit", type=int, default=0, help="взять только N страниц")
    p.add_argument("--truth-only", action="store_true", dest="truth_only",
                   help="переписать только истину, не трогая уже собранный pdf")
    p.add_argument("--out", help="куда положить annopage.pdf и truth/")
    p.set_defaults(fn=cmd_annopage)

    p = sub.add_parser("score", help="метрики контуров против истины стенда")
    p.add_argument("truth", help="каталог истины (bench/synth/truth)")
    p.add_argument("detect", help="каталог вывода модели (…/detect/pages)")
    p.add_argument("--selfcheck", action="store_true",
                   help="батарея мутаций: умеет ли число падать (код 1, если нет)")
    p.set_defaults(fn=cmd_score)

    p = sub.add_parser("read",
                       help="ВТОРОЙ УРОВЕНЬ: прочитать блоки моделью (платно)")
    p.add_argument("dir", help="каталог books detect")
    p.add_argument("--out", default="", help="куда класть; по умолчанию <dir>.read")
    p.add_argument("--pages", default="", help="какие страницы: 1,4,7-9")
    p.add_argument("--policy", default="",
                   help="словарь ярлыков детектора; пусто = взять из слепка "
                        "детекции, а несовпадение с ним — отказ вслух")
    p.add_argument("--no-resume", action="store_true",
                   help="спрашивать заново даже то, что уже прочитано")
    p.add_argument("--rent", action="store_true",
                   help="считать на АРЕНДОВАННОЙ карте, а не по VLM_ENDPOINT: "
                        "снять машину, поднять vLLM, забрать результат")
    p.add_argument("--budget", type=float, default=0.60,
                   help="потолок траты, $; достигнут — машина уничтожается")
    p.add_argument("--timeout", type=float, default=60.0,
                   help="потолок времени, мин; достигнут — то же самое")
    p.add_argument("--dry-run", action="store_true",
                   help="собрать задание и проверить его, ничего не арендуя")
    p.add_argument("--key", default="", help="путь к ssh-ключу для vast.ai")
    p.set_defaults(fn=cmd_read)

    # THE COMMAND IS `apply`, and `swap` stood here. `swap` names the MECHANICS
    # ("exchange"), not the work, and hints not a word at the journal with undo
    # the command exists for; with no keys it changes nothing and prints a
    # report, so an order reads as an action and turns out to be a lookup.
    # `apply` matches the module that does it, and `--undo` reads as "undo what
    # was applied".
    p = sub.add_parser("apply",
                       help="второй уровень: разметка вместо картинки, и откат")
    p.add_argument("dir", help="каталог сборки (books html --out)")
    p.add_argument("--anchor", help="якорь блока, вида p0042-b17")
    p.add_argument("--file", help="файл с разметкой блока")
    p.add_argument("--kind", default="html",
                   help="вид содержимого: html | otsl | latex | text")
    p.add_argument("--source", default="",
                   help="чем порождено; уезжает в журнал и в атрибут блока")
    p.add_argument("--undo", action="store_true",
                   help="вернуть то, что стояло до последней замены")
    p.add_argument("--status", action="store_true",
                   help="только отчёт: что заменено, ничего не трогая")
    p.add_argument("--from", dest="from_read", default="",
                   help="каталог `books read`: поставить ВСЁ прочитанное, "
                        "по одному блоку и с откатом у каждого")
    p.set_defaults(fn=cmd_apply)

    p = sub.add_parser("text",
                       help="метрика чтения: знаки против истины стенда")
    p.add_argument("truth", help="каталог истины (bench/<книга>/truth)")
    p.add_argument("pages", help="каталог прочитанного (…/detect/pages)")
    p.add_argument("--norm", default=text_norm_default(),
                   help="граница нормализации при сличении; "
                        "объявляется числом и уезжает в отчёт")
    p.add_argument("--selfcheck", action="store_true",
                   help="батарея порчи: умеет ли число падать (код 1, если нет)")
    p.set_defaults(fn=cmd_text)

    p = sub.add_parser("overlay", help="рамки поверх страниц, чтобы посмотреть глазами")
    p.add_argument("pdf", help="страницы, поверх которых рисовать")
    p.add_argument("--truth", help="каталог истины (bench/synth/truth)")
    p.add_argument("--detect", help="каталог вывода модели (…/detect/pages)")
    p.add_argument("--out", help="куда положить pdf с рамками")
    p.add_argument("--pages",
                   help="какие страницы: 1,4,7-9; счёт с единицы, как у detect")
    p.set_defaults(fn=cmd_overlay)

    p = sub.add_parser("synth", help="синтетический стенд с точной истиной")
    p.add_argument("--book", default="spravochnik",
                   help="какая книга стенда: spravochnik|slovar|matematika|"
                        "atlas|katalog|zhurnal")
    p.add_argument("--out", help="куда положить <книга>.pdf и truth/")
    p.add_argument("--cases", help="какие случаи, через запятую; по умолчанию все")
    p.set_defaults(fn=cmd_synth)

    p = sub.add_parser("ls", help="что сейчас арендовано")
    p.set_defaults(fn=cmd_ls)

    p = sub.add_parser("down", help="уничтожить инстанс")
    p.add_argument("id", type=int)
    p.set_defaults(fn=cmd_down)

    p = sub.add_parser("reap", help="уничтожить всё, что оставили наши прогоны")
    p.set_defaults(fn=cmd_reap)

    p = sub.add_parser("doctor",
                       help="проверить окружение до того, как тратить деньги")
    p.set_defaults(fn=cmd_doctor)

    p = sub.add_parser("ledger", help="журнал прогонов и оценки по нему")
    p.set_defaults(fn=cmd_ledger)

    p = sub.add_parser("replay", help="полон ли слепок входа для повтора")
    # nargs="+", not "*": a check whose whole point is its exit code silently
    # approved on an empty list — `books replay --check` with no directory
    # returned 0 and printed not a line.
    p.add_argument("outdir", nargs="+", help="каталог разбора")
    p.add_argument("--selfcheck", action="store_true",
                   help="умеет ли сама проверка провалиться (код 1, если нет)")
    p.add_argument("--check", action="store_true",
                   help="печатать недостающее и вернуть 1, если оно есть")
    p.set_defaults(fn=replay_mod.cmd_replay)

    a = ap.parse_args(argv)
    try:
        return a.fn(a) or 0
    except _tool_errors() as e:
        # Code 2 is "could not count", against 1 — "counted, and the number
        # failed". Merged, a silent instrument and a failed metric read alike;
        # the actions on them differ.
        log(f"{type(e).__name__}: {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
