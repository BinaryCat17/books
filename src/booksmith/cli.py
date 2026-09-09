"""Single entry point: books <command>.

    books doctor                 check everything BEFORE the money starts
    books offers                 look at the market, renting nothing
    books prepare book.djvu      djvu -> PDF, spreads cut apart
    books detect book.pdf        LEVEL ONE: contours, local and free
    books read book.detect/      LEVEL TWO: read the blocks with a model (paid)
    books html book.detect/      build the HTML: text + artefacts as pictures
    books crop book.detect/      what `books read` would send, cut by its own
                                 path; nothing sent, nothing paid
    books apply book-dir/        put the read markup into the book, source out
                                 of its snapshot; repeats are free, what stands
                                 is not placed twice. --status — report only
    books synth                  synthetic bench: pages with exact truth
    books annopage raw/annopage  golden bench: real pages, librarians' truth
    books subset                 distillate: artefacts side by side
    books score truth/ boxes/    contour metrics: boxes, labels, order
    books text truth/ pages/     READING metric: characters and table cells
    books fitness book.pdf …     will the meaning arrive: by ink, no truth
    books overlay book.pdf …     boxes over pages, to look with your own eyes
    books bench all <book>       every applicable metric on one run: one table
    books bench selfcheck <book> every metric's probes: can the numbers fall
    books bench report           every measured number, as METRICS.md
    books ls | books down 12345 | books reap
    books ledger                 run journal and the estimate from it
    books replay --check out/    is the input snapshot complete
    books docs                   regenerate the documents rendered from the code

This list is `books --help`, and `tests/contract/test_docs.py` checks it
against the parser both ways. Every command with its flags: `docs/commands.md`.
"""
import argparse
import json
import os
import sys

from booksmith.core import config
from booksmith.processing.read.rented import paddleocr_vl
from .remote import ledger as ledger_mod
from .remote.spec import HostReq
from .remote.vast import Vast
from booksmith.core.log import log
from booksmith.core import knobs
from booksmith.core import replay as replay_mod
from booksmith.core.errors import Refusal
from booksmith.core import raster
from booksmith.core import book
from booksmith.datasets import look as look_mod


def _host_args(ap):
    ap.add_argument("--gpu", default="RTX_4090",
                    help="RTX_4090 / RTX_5090 / A100_PCIE ...")
    ap.add_argument("--max-dph", type=float, default=0.60,
                    help="ceiling in $/hour")
    ap.add_argument("--disk", type=int, default=60, help="instance disk, GB")
    ap.add_argument("--machine", type=int,
                    help="pin to a machine_id with a warm cache")
    ap.add_argument("--image", help="override the docker image")


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
    from booksmith.processing.extract import djvu
    print(djvu.to_pdf(a.file, dst=a.out, split=a.split))
    return 0


def _with(a, **kw):
    """A copy of the parsed arguments with fields replaced. argparse gives a
    Namespace, and mutating the caller's would leave the change behind for a
    second command in the same process (the tests run several)."""
    import copy
    out = copy.copy(a)
    for k, v in kw.items():
        setattr(out, k, v)
    return out


def cmd_detect(a):
    """Level-one contours over the PDF pages. No VLM, no rental, no money.

    WHERE IT LANDS. Given a BOOK DIRECTORY, under `detect/<label>/`, where the
    label is the model's own name -- so a second detector measured on the same
    book stands beside the first instead of overwriting it, which is what
    putting every model's numbers in one table needs. Given a bare PDF, beside
    it as before, because a loose file has no book directory to put a run in.
    `--out` still wins over both: it is how a run is put somewhere for a look.
    """
    import shlex
    from booksmith.processing.layout import detect
    out = a.out
    if os.path.isfile(os.path.join(a.file, "manifest.json")):
        # A BOOK DIRECTORY RESOLVES TO ITS SCAN whatever `--out` says. The
        # first edition did this only when `--out` was absent, so `books
        # detect <book> --out <dir>` handed the directory itself to the
        # renderer and died on "one book's PDF is expected". `--out` decides
        # WHERE a run lands, never WHAT is read.
        bk = book.Book.open(a.file, "books detect")
        pdf = bk.pdf
        if pdf is None:
            raise Refusal(
                f"{bk.name}: the manifest names "
                f"{(bk.manifest.get('source') or {}).get('name')!r} and it is "
                f"not beside the manifest. The book directory is where the "
                f"scan lives; a run cannot be measured against a file that "
                f"is not there.")
        # THE LABEL BEFORE THE PAGES. Building the adapter costs a session
        # load and no pages, and asking it its name here means a run that
        # cannot be filed refuses BEFORE the work rather than after it.
        out = out or bk.run_dir("detect", detect._adapter().label())
        a = _with(a, file=pdf)
    out = out or os.path.splitext(a.file)[0] + ".detect"
    detect.run(a.file, out, a.pages, log=log)
    # Quoted: five of the nine files in raw/ carry spaces and brackets, and a
    # hint you cannot paste into a shell is not a hint.
    log(f"snapshot completeness: books replay --check {shlex.quote(out)}")
    return 0


# --------------------------------------------- the directories commands take
# `books detect` leaves TWO directories side by side: `<out>` with the snapshot
# `run.json`, and `<out>/pages` with the layout pages. Half the commands wanted
# the first (`html`, `crop`, `replay --check`), half the second (`score`,
# `text`, `fitness --detect`), and the operator learned which from a six-frame
# traceback. Below both forms are taken by both sides, and a missing path fails
# in ONE line naming what it expected.


def cmd_html(a):
    """Level one's product: text as markup, artefacts as pictures."""
    from booksmith.processing.assemble import html as html_mod
    d = book.run_dir(a.dir, "books html")
    out = a.out or book.home_for(d)
    # FOREIGN WORK IS NOT OVERWRITTEN: the tell of ours is the snapshot the
    # builder writes, and a non-empty directory without it means refusal out
    # loud. THE TELL IS ASKED OF THE BUILDER, NOT TYPED HERE: the snapshot
    # moved into `assets/`, and this check, looking for `run.json` in the ROOT,
    # began refusing directories this same command had made a minute earlier —
    # refusing with a LIE, "probably a book of the old pipeline", of which none
    # remain, and refusing the advice the build itself prints along with them.
    if (not a.out and os.path.isdir(out) and os.listdir(out)
            and not html_mod.is_our_dir(out)):
        raise Refusal(
            f"{out} already holds something not ours: neither "
            f"`{html_mod.ASSETS}/run.json` nor `run.json` in the root — so "
            f"the directory was not built by `books html`. Overwriting it "
            f"silently is not allowed: give --out or remove it by hand.")
    html_mod.build(d, out, log=log)
    return 0


def cmd_apply(a):
    """Level two in place: markup instead of the picture, and back again.

    Not one call to a model here: this layer only places a ready fragment, and
    what generated it — `books read`, or a hand — is not its business.
    """
    from booksmith.processing.assemble import apply as ap
    # NOT `_run_dir`: that one looks for the DETECTION `run.json` and on
    # refusal points at a directory with `pages/`, while this command wants the
    # BUILD directory, the one with `book.html`. The old check refused the
    # right directory and advised the wrong one.
    d = os.path.abspath(a.dir)
    try:
        if a.from_read:
            if a.anchor or a.undo:
                raise ap.SwapError(
                    "--from together with --anchor or --undo: these are "
                    "different jobs. --from places EVERYTHING read, "
                    "--anchor one block.")
            ap.from_read(d, a.from_read, log=log)
            return 0
        if a.status:
            ap.status(d, log=log)
            return 0
        if a.undo and not a.anchor:
            raise ap.SwapError(
                "--undo without --anchor: name the block to roll back. "
                "Unnamed, the command would roll back who knows what; the "
                "list of replaced ones is `books apply <dir> --status`.")
        if a.undo:
            ap.undo(d, a.anchor, log=log)
        elif a.anchor:
            if not a.file:
                raise ap.SwapError("nothing to place: give --file with the "
                                   "block markup, or --undo")
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
                    f"{d}: I do not know what to place. "
                    f"`{ap.ASSETS}/run.json` holds no path to a reading "
                    f"directory, or it is gone from disk — name it "
                    f"yourself: `books apply {os.path.basename(d)} --from "
                    f"<books read dir>`. What is already replaced is shown "
                    f"by `--status`.")
            log(f"source taken from the book's snapshot: {src}")
            ap.from_read(d, src, log=log)
    except ap.SwapError as e:
        log(str(e))
        return 1
    return 0


def cmd_read_rented(a, policy_name, out):
    """The same work on a RENTED card. A branch, not a command of its own:
    same code, same count, only the place changes.

    WHY IT EXISTS. `read/rented/paddleocr_vl.spec()` and `remote.run_job()`
    were
    called by NOT ONE command — grep over the whole tree found definitions and
    prose only. "Read on a rented card" could be started by nothing, and that
    surfaced from the direct question "with which command?", not from reading
    the code.
    """
    from booksmith.processing.read.rented import paddleocr_vl as vl
    from .remote import runner

    spec = vl.spec(book.pdf_of(a.dir), a.dir, pages=a.pages, policy=policy_name,
                   budget_usd=a.budget, timeout_minutes=a.timeout)
    log(f"job {spec.name}: input {len(spec.inputs)} paths, ceiling "
        f"${spec.budget_usd:.2f} and {spec.timeout_minutes:.0f} min, card "
        f"{spec.host.gpu}, CUDA from {spec.host.cuda_min}")
    # THE MONEY CEILING IS UNREACHABLE WHILE IT EXCEEDS THE HOURLY PRICE.
    # `Budget` takes the smaller of the two, so at a price ceiling of
    # $0.60/hour a $0.60 limit means exactly one hour: time always cuts, money
    # never. Whoever pays is told, not whoever later reads the journal.
    by_money_h = a.budget / max(spec.host.max_dph, 1e-9)
    if by_money_h * 60 >= a.timeout:
        log(f"  WARNING: at a price of up to ${spec.host.max_dph:.2f}/hour "
            f"the ceiling ${a.budget:.2f} is {by_money_h:.1f} h, i.e. more "
            f"than the {a.timeout:.0f} min timeout. TIME will be the cutter; "
            f"the real top spend is "
            f"${spec.host.max_dph * a.timeout / 60:.2f}")
    if a.dry_run:
        log("--dry-run: renting nothing, the job is built and checked")
        return 0
    rc = runner.run_job(spec, out, ssh_key=config.ssh_key(a.key),
                        dry_run=False)
    log(f"the job returned {rc}; the result is in {out}")
    if rc == 0:
        log(f"next: books text <truth> {out}/pages   |   books html {out}")
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
    from booksmith.processing.read.transports import openai_http as vhttp
    from booksmith.processing.read import driver as vread

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
        raise Refusal(
            f"the snapshot {a.dir}/run.json names no label dictionary and "
            f"--policy is not given. Asking by a guessed dictionary means "
            f"leading a table with the text prompt and filing prose as "
            f"reading.")
    if a.policy and known and a.policy != known:
        raise Refusal(
            f"--policy {a.policy!r} against the detection dictionary "
            f"{known!r}. Matching labels would pass without a word, and the "
            f"snapshot would file two incompatible claims side by side. Drop "
            f"--policy, or recompute detection with the detector whose "
            f"dictionary you mean to read by.")
    os.makedirs(out, exist_ok=True)
    if a.rent:
        return cmd_read_rented(a, policy_name, out)

    reader = vread.build_reader(policy_name)
    transport = vhttp.build()

    # WHAT THE ENDPOINT ANSWERS WITH — before the first crop and first cent.
    who = transport.check()
    log(f"endpoint {who['endpoint']}: answers {who['models_on_server']}, "
        f"we ask {who['asking_for']} — matched")

    pages = None
    if a.pages:
        from booksmith.processing.layout.detect import parse_pages
        with raster.open_pdf(book.pdf_of(a.dir)) as d:
            pages = set(parse_pages(a.pages, d.page_count))

    t = vread.read_book(a.dir, out, reader, transport,
                        resume=not a.no_resume, pages_want=pages, log=log)
    vread.report(t, log=log)
    p = vread.snapshot(a.dir, out, reader, transport, t,
                       {"detect": a.dir, "out": out, "pages": a.pages,
                        "policy": policy_name})
    log(f"snapshot: {p}")
    log(f"next: books html {out}   |   books text <truth> {out}/pages")
    return 0


def cmd_crop(a):
    """What `books read` would send, cut by `books read`'s own path, and
    nothing sent. Free.

    The driver runs in preview: the same crop rule, the same dpi, the same
    prompts and generation parameters, written to `crops/` and
    `would_ask.json`. The preview that stood here before (`books feed`) cut
    with knobs of its own that the paid path never read, and showed pictures
    the model never saw.
    """
    from booksmith.processing.read import driver as vread
    d = book.run_dir(a.dir, "books crop")
    out = a.out or (os.path.abspath(d).rstrip("/") + ".crop")
    # THE SAME TWO LINES AS `books read`, and for the same reason. This asked
    # the snapshot alone and refused when it named no dictionary -- so
    # `bench/annopage/detect`, a run `books read --policy PP-DocLayoutV2`
    # reads perfectly well, could not be previewed at all. The free command
    # must accept every input the paid one does, or it is a preview of
    # something else.
    policy_name = vread.policy_for(d, a.policy)
    os.makedirs(out, exist_ok=True)
    reader = vread.build_reader(policy_name)
    pages = None
    if a.pages:
        from booksmith.processing.layout.detect import parse_pages
        with raster.open_pdf(book.pdf_of(d)) as doc:
            pages = set(parse_pages(a.pages, doc.page_count))
    t = vread.read_book(d, out, reader, None, resume=False, pages_want=pages,
                        log=log, preview=True)
    log(f"would ask {t.get('would_ask', 0)} of {t['block_count']} blocks; not "
        f"asked {t['not_asked']}, crop failed {t['crop_failed']}")
    # THE THREE TROUBLES ARE PRINTED, not left in the file. A preview is
    # looked at to decide whether to pay; "crop failed 2" with no anchor and
    # no reason decides nothing.
    if t["crop_failed"]:
        log(f"  THE CROP FAILED on {t['crop_failed']} blocks -- they would go "
            f"UNREAD in the paid run: {'; '.join(t['crop_failures'][:3])}"
            f"{'...' if t['crop_failed'] > 3 else ''}")
    if not t.get("would_ask"):
        # The same rule the paid run states: zero asked is not a success.
        # Here it matters more, because this is the command that exists to
        # find that out BEFORE the money.
        log("NOT ONE BLOCK WOULD BE ASKED -- not a success, an empty run. "
            "Look at `not_asked` in would_ask.json for the reason of each.")
    log(f"{os.path.join(out, 'would_ask.json')}; crops in {os.path.join(out, 'crops')}")
    return 0


def cmd_overlay(a):
    """Boxes over the pages: truth solid, the model's guess dashed."""
    from booksmith.processing.layout import detect
    from booksmith.datasets import look as overlay
    marks = [(book.pages_dir(a.truth, "--truth"), "T")] if a.truth else []
    if a.detect:
        marks.append((book.pages_dir(a.detect, "--detect"), "M"))
    if not marks:
        raise Refusal("nothing to draw: give --truth and/or --detect")
    out = a.out or look_mod.look_at(a.pdf, a.detect)
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
        doc = raster.open_pdf(a.pdf)
        total = doc.page_count
        doc.close()
        only = detect.parse_pages(a.pages, total)
    # The default now lands in `<book>/look/`, which need not exist yet --
    # `look.build` opens the file and does not make the directory.
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    overlay.build(a.pdf, out, marks, only=only, log=log)
    return 0


def cmd_score(a):
    """Contour metrics: truth against the model output.

    Whether the numbers can fall is `books bench selfcheck`, which runs every
    applicable metric's probes on a bench and a run.
    """
    from booksmith.datasets.metrics import contour as metrics
    truth = book.pages_dir(a.truth, "truth")
    det = book.pages_dir(a.detect, "model boxes")
    metrics.report(metrics.compare(truth, det), log=log)
    return 0


def text_norm_default():
    """The normalisation default comes FROM THE MODULE, not typed here twice.

    A second copy is what the knob registry's header warns of: a changed value
    never reaches the consumer until somebody remembers this file.
    """
    from booksmith.datasets.metrics import text
    return text.NORM


def cmd_text(a):
    """The reading metric: the truth of characters against what the model read.

    Its own command, not a column in `books score`: that one measures GEOMETRY
    and labels, this one CHARACTERS. One number for two questions is how an
    instrument here already lied — "reading order agreed 73%" on a bench where
    order is not annotated at all.
    """
    from booksmith.datasets.metrics import text
    truth = book.pages_dir(a.truth, "truth")
    pages = book.pages_dir(a.pages, "what was read")
    text.report(text.measure(truth, pages, norm=a.norm), log=log)
    return 0


def cmd_fitness(a):
    """Fitness of the output: will the meaning reach level two. By ink."""
    from booksmith.processing.assess import ink as fitness
    det = book.pages_dir(a.detect, "--detect")
    truth = book.pages_dir(a.truth, "--truth") if a.truth else ""
    fitness.report(fitness.measure(a.pdf, det, truth), log=log)
    return 0


def cmd_subset(a):
    """Bench distillate: pages where two artefacts of one label stand side by side."""
    from booksmith.datasets.make import subset
    books = [x.strip() for x in (a.books or
             "spravochnik,slovar,matematika,atlas,katalog,zhurnal,annopage"
             ).split(",") if x.strip()]
    subset.build(books, a.out or "bench/hard", log=log)
    return 0


def cmd_annopage(a):
    """The golden bench from AnnoPage: real pages, librarians' truth."""
    from booksmith.datasets.make import annopage
    out = a.out or "bench/annopage"
    log(f"AnnoPage from {a.root}, split {a.split}")
    annopage.build(a.root, out, split=a.split, limit=a.limit,
                   truth_only=a.truth_only, log=log)
    log(f"next: books detect {shlex_quote(out)}/annopage.pdf "
        f"--out {shlex_quote(out)}/detect")
    return 0


def cmd_synth(a):
    """Build a synthetic book with exact truth. Local and free."""
    from booksmith.datasets.make import synth
    from booksmith.core import knobs
    out = a.out or f"bench/{a.book}"
    cases = a.cases.split(",") if a.cases else None
    from booksmith.datasets.make.synth.books import load
    log(f"book {a.book}: cases {len(cases or load(a.book).CASES)}, "
        f"ageing {knobs.knob('SYNTH_AGING')}, "
        f"seed {knobs.knob('SYNTH_SEED')}")
    synth.build(out, cases, knobs.number("SYNTH_SEED", kind=int),
                knobs.knob("SYNTH_AGING"), book=a.book, log=log)
    log(f"next: books detect {shlex_quote(out)}/{a.book}.pdf "
        f"--out {shlex_quote(out)}/detect")
    return 0


def shlex_quote(s):
    import shlex
    return shlex.quote(s)


def _open_book(path, kind, label):
    """The book at `path` and one of its runs, as `bench all` opens them.

    A BENCH IS A BOOK WITH `truth/`, AND A PROCESSED BOOK IS THE OTHER HALF.
    Asked here rather than by catching `Unmeasurable` from `open`: a caught
    refusal cannot tell "there is no truth here, which is fine" from "this path
    is wrong", and the second must still reach the user.
    """
    from booksmith.datasets.bench import Bench
    root = path.rstrip("/")
    if not os.path.isdir(root):
        # SAID BEFORE EITHER DOOR IS TRIED: both openers answer a path that is
        # not there by describing what they wanted to find in it, which sends
        # the reader looking for a file in a directory that does not exist.
        raise Refusal(f"{path} is not a directory. This takes a book: "
                      f"bench/<name> or processed/<name>.")
    has_truth = (os.path.isdir(os.path.join(root, "truth"))
                 or os.path.basename(root) == "truth")
    b = Bench.open(root) if has_truth else Bench.no_truth(root)
    return b, b.run(label, kind)


def cmd_bench_selfcheck(a):
    """Every applicable metric's probes on one bench and run: can they fall.

    A number is not to be trusted until it has been shown able to fall, so each
    probe spoils the input on purpose and says what must happen to the number.
    Returns 1 if any probe went uncaught. A probe with nothing to grip on this
    book answers "no data" and is counted apart: a battery reporting zero
    uncaught over probes that measured nothing is what this guards against.
    """
    from booksmith.datasets.metrics import BY_NAME, METRICS
    from booksmith.datasets.metrics import base
    b, run = _open_book(a.bench, a.kind, a.run)
    # THE TRUTH IS PARSED ONLY IF THERE IS ANY, as `table.rows` does it: a book
    # with no `truth/` is a legal thing to probe, since the ink and column-jump
    # metrics need none, and asking for its truth pages raises before
    # applicability is ever consulted.
    pages = b.pages() if b.truth_dir else {}
    fit = base.applicable(METRICS, b, run, pages, run.pages())
    if a.only:
        which = [n.strip() for n in a.only.split(",") if n.strip()]
        unknown = [n for n in which if n not in BY_NAME]
        if unknown:
            raise Refusal(f"no metric named {', '.join(unknown)}; there are "
                          f"{', '.join(BY_NAME)}")
        off = [n for n in which if BY_NAME[n] not in fit]
        if off:
            raise Refusal(f"{', '.join(off)} cannot be measured on {b.name} "
                          f"with run {run.label}, so its probes say nothing")
        fit = [BY_NAME[n] for n in which]
    total = uncaught = mute = 0
    for metric in fit:
        seen, silent, bad = base.run_probes(metric.probes(b, run), log=log)
        log(f"{metric.name}: probes {seen}, measured {seen - silent}, "
            f"nothing to measure with {silent}, uncaught {bad}")
        total, uncaught, mute = total + seen, uncaught + bad, mute + silent
    left = sorted(m.name for m in METRICS if m not in fit)
    log(f"{b.name} {run.label}: metrics {len(fit)}, probes {total}, "
        f"nothing to measure with {mute}, UNCAUGHT {uncaught}"
        + (f"; not probed here: {', '.join(left)}" if left else ""))
    return 1 if uncaught else 0


def cmd_bench_all(a):
    """Every applicable metric on one bench and one run: one table, one JSON.

    The numbers used to land on stdout only, three commands with three
    argument shapes, and every comparison between detectors was typed into
    prose by hand -- four times, the prose records, wrongly. This is the
    first command that writes them down.
    """
    from booksmith.datasets import table
    root = a.bench.rstrip("/")
    b, run = _open_book(root, a.kind, a.run)
    which = [n.strip() for n in a.only.split(",") if n.strip()] if a.only else None
    recs = table.rows(b, run, which, log=log)
    table.render(recs, log=log)
    path = a.json or table.results_path(b, run, which)
    table.write_json(recs, path, log=log, kind=run.kind)
    return 0


def cmd_bench_report(a):
    """Every measured number as one generated document, at the repo root.

    The measurements lived as prose in five documents, and a figure stated
    twice is free to drift; rendered from the record that produced it, it
    cannot.
    """
    from booksmith.datasets import report
    report.write(a.out or report.OUT, log=log)
    return 0


def cmd_docs(_a):
    """Commands, knobs and metrics as documents, from the code that declares them."""
    from booksmith.datasets import docsgen
    for rel in docsgen.write_all(build_parser(), config.ROOT):
        log(f"wrote {rel}")
    return 0


def cmd_ls(_a):
    v = Vast()
    rows = v.v.show_instances()
    log(f"balance: ${v.balance():.3f}")
    if not rows:
        log("no instances — no money going out")
        return 0
    for i in rows:
        log(f"  {i['id']}  {i.get('actual_status')}  {i.get('label')}  "
            f"${float(i.get('dph_total') or 0):.3f}/hour  "
            f"machine {i.get('machine_id')}  {i.get('gpu_name')}")
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
        log(f"  [{'ok  ' if good else 'no  '}] {name}"
            + ("" if good else f" — {hint}"))
        ok = ok and good

    log("environment check:")
    check("rsync locally", shutil.which("rsync") is not None,
          "needed for the incremental pull: apt install rsync")
    check("ssh locally", shutil.which("ssh") is not None,
          "apt install openssh-client")
    key = config.ssh_key()
    check(f"ssh key {config.DEFAULT_SSH_KEY}", key is not None,
          "ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519_vast -N ''")
    check("public half of the key", bool(key) and os.path.exists(key + ".pub"),
          "without it the key cannot be attached to an instance")
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
        log("  [ – ] .env in the root — none; it is needed only for "
            "VLM_API_KEY when reading over a network endpoint. Sample: "
            ".env.example")

    try:
        v = Vast()
        bal = v.balance()
        check(f"vast.ai key (balance ${bal:.3f})", True)
        check("balance enough for at least one run", bal > 0.20,
              "top up: console.vast.ai/billing")
        rows = v.v.show_instances()
        check(f"no forgotten instances (now {len(rows)})", not rows,
              "books ls, then books reap")
    except Exception as e:
        check("vast.ai key", False, f"vastai set api-key <KEY> ({e})")

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

    log(("the rental environment is in order" if ok
         else "there are troubles — see above")
        + f"; reading: {read_line}; detection: {det_line}; "
        + f"docling pipeline: {pipe_line}")
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
    log("reading blocks (books read, level two):")
    if ep:
        log(f"  [ok  ] VLM_ENDPOINT={ep}, key VLM_API_KEY "
            f"{f'present, {len(key)} chars' if key else 'not set'}")
        return f"endpoint set, key {'present' if key else 'none'}"
    log("  [—   ] VLM_ENDPOINT not set: `books read` will refuse out loud "
        "rather than knock at nothing. There is no default on purpose. On a "
        "rented card run.sh sets the endpoint and no key is needed there — "
        "vLLM is raised on the loopback")
    return "endpoint not set (rental does not need one)"


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
    log("layout detection (books detect, optional set):")
    missing = []
    for mod, why in (("onnxruntime", "the detector's arithmetic"),
                     ("cv2", "raster"),
                     ("yaml", "reading inference.yml")):
        try:
            __import__(mod)
        except ImportError:
            missing.append(f"{mod} ({why})")
    if missing:
        log(f"  [ – ] packages missing: {', '.join(missing)} — "
            f'install: pip install -e ".[detect]"')
        # A zero from checking and a zero from not understanding are DIFFERENT
        # lines: without these packages no adapter rises at all, so there is
        # nothing to call "no weights".
        log("  [ – ] adapter weights NOT CHECKED for a single one: there is "
            "nothing to raise them with. That is not «no weights», it is "
            "«we did not look».")
        return ("NOT CHECKED — the detect set is missing packages "
                f"({len(missing)} of 3)")

    from booksmith.processing.layout import detect
    from booksmith.core import knobs
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
            except (Exception, SystemExit) as e:
                # `SystemExit` is caught ON PURPOSE: at
                # `DOCLING_PIPELINE=full` with no vendor package the docling
                # adapter leaves by exactly that, and acceptance catching only
                # `Exception` died on the second adapter of four, saying
                # nothing of it, the two remaining, or the pipeline (rc=1,
                # measured). "No weights" and "weights present, adapter would
                # not rise" are different troubles: a download cures the first,
                # the second breaks the run with a full weights directory.
                kind = ("no weights" if type(e).__name__ == "WeightsMissing"
                        else f"DID NOT RISE ({type(e).__name__})")
                log(f"  [ – ] {which:14s} {kind}: {e}")
                continue
            w = getattr(det, "onnx", "") or ""
            mb = os.path.getsize(w) / 2 ** 20 if os.path.exists(w) else 0.0
            have.append(which)
            log(f"  [ok  ] {which:14s} {det.name}, labels "
                f"{len(det.labels)}, weights {mb:.0f} MB, rose in "
                f"{time.time() - t:.1f} s — {det.dir}")
            det = None                        # not holding 4 graphs at once
    finally:
        if saved is None:
            os.environ.pop("LAYOUT_ADAPTER", None)
        else:
            os.environ["LAYOUT_ADAPTER"] = saved
    log(f"  adapters risen {len(have)} of {len(detect.ADAPTERS)}"
        f" ({', '.join(have) if have else 'none at all'}), the check took "
        f"{time.time() - t0:.0f} s; the book is now counted by "
        f"LAYOUT_ADAPTER={active}")
    line = f"adapters risen {len(have)} of {len(detect.ADAPTERS)}"
    if active not in detect.ADAPTERS:
        log(f"  WARNING: LAYOUT_ADAPTER={active!r} — no such adapter; I "
            f"know {', '.join(detect.ADAPTERS)}")
        line += f", but LAYOUT_ADAPTER={active!r} is not from that list"
    elif active not in have:
        log(f"  WARNING: the active adapter {active} did not rise (reason "
            f"one line above) — `books detect` will fall without counting a "
            f"page")
        line += f", the active {active} DID NOT RISE"
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
    from booksmith.core import knobs

    mode = knobs.knob("DOCLING_PIPELINE")
    log(f"docling pipeline (knob DOCLING_PIPELINE={mode}, "
        f"optional set):")
    gone = []
    try:
        if iu.find_spec("docling.utils.layout_postprocessor") is None:
            gone.append("docling.utils.layout_postprocessor")
    except (ImportError, ValueError):
        gone.append("docling.utils.layout_postprocessor")
    try:
        __import__("rtree")
    except Exception as e:
        gone.append(f"rtree ({type(e).__name__})")
    vers = {}
    for dist in ("docling-slim", "docling", "rtree"):
        try:
            vers[dist] = md.version(dist)
        except md.PackageNotFoundError:
            vers[dist] = None
    if gone:
        log(f"  [ – ] missing: {', '.join(gone)} — install: "
            f'pip install -e ".[docling]". At DOCLING_PIPELINE=post|full '
            f"the run falls out loud, at off (the default) it is not needed "
            f"at all")
        return (f"{len(gone)} of 2 packages missing"
                + (f", and the knob is at {mode}" if mode != "off" else ""))
    # The version comes from the DISTRIBUTION, not `docling.__version__`: one
    # package, two deliveries (`docling-slim` and full), and pyproject pins the
    # version to the point — a vendor rule change would move our boxes
    # silently. With no distribution at all (sources on the path) it says so:
    # "not declared" is not a version.
    ver = (vers["docling-slim"] or vers["docling"]
           or "version not declared (no distribution, module from elsewhere)")
    kind = ("slim" if vers["docling-slim"] else
            "full delivery" if vers["docling"] else "delivery unknown")
    log(f"  [ok  ] docling {ver} ({kind}), rtree {vers['rtree']}; "
        f"turned on by DOCLING_PIPELINE=post|full over the docling and "
        f"docling-egret adapters, now {mode}")
    return f"{ver} + rtree {vers['rtree']}, knob at {mode}"


def cmd_ledger(_a):
    rows = ledger_mod.read()
    if not rows:
        log(f"journal empty ({ledger_mod.LEDGER})")
        return 0
    t = ledger_mod.totals(rows)
    log(f"{t['runs']} runs, successful {t['ok']}, spent ${t['spent_usd']:.3f}")
    for r in rows[-10:]:
        mb = ledger_mod.observed_mbps(r)
        log(f"  {r.get('started_iso','')}  {r.get('job','')[:22]:22s} "
            f"{'ok ' if r.get('ok') else 'fail'}  "
            f"start {r.get('setup_s',0)/60:4.1f}m "
            f"({' not measured' if mb is None else f'{mb:4.0f} Mbps'})  "
            f"count {r.get('run_s',0)/60:5.1f}m  ${r.get('cost_usd',0):.3f}  "
            f"machine {r.get('machine_id')}")
    log(f"estimate from the journal: {ledger_mod.fit()}")
    return 0


def _tool_errors():
    """The "instrument could not count" family: exit code 2.

    Once a tuple of five classes named by module path -- three `WeightsMissing`
    and two metric errors -- so that a traceback from a failed instrument and
    one from our own bug stayed apart. The family is one base class now, and
    the package move that renamed every module path would have emptied the
    tuple in silence: `sys.modules.get(old_name)` finds nothing and the
    mapping dies without an error. A base class cannot go stale that way.
    """
    from booksmith.core.errors import Unmeasurable
    return (Unmeasurable,)


class _Parser(argparse.ArgumentParser):
    """argparse exits 2 on a usage error, and 2 is taken: it means "could not
    count". A typo in a flag must not read as a broken instrument."""

    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(64, f"{self.prog}: {message}\n")


def build_parser():
    ap = _Parser(
        prog="books", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("offers", help="look at the market, renting nothing")
    _host_args(p)
    p.add_argument("--minutes", type=float, default=20.0,
                   help="how many minutes to price a run for")
    p.set_defaults(fn=cmd_offers)

    p = sub.add_parser("prepare", help="unfold djvu into PDF")
    p.add_argument("file")
    p.add_argument("--out", help="where to put the PDF")
    p.add_argument("--split", default="auto", choices=("auto", "yes", "no"),
                   help="whether to cut the spreads")
    p.set_defaults(fn=cmd_prepare)

    p = sub.add_parser("detect", help="level-one contours, locally")
    p.add_argument("file", help="PDF (unfold djvu with books prepare)")
    p.add_argument("--out", help="where to put pages/ and run.json")
    p.add_argument("--pages", help="which pages: 1,4,7-9; all by default")
    p.set_defaults(fn=cmd_detect)

    p = sub.add_parser("html", help="build HTML from a books detect directory")
    p.add_argument("dir", help="the directory books detect wrote to")
    p.add_argument("--out", help="where to put book.html and assets/")
    p.set_defaults(fn=cmd_html)

    p = sub.add_parser("crop",
                       help="what `books read` would send, by its own path; "
                            "nothing sent, nothing paid")
    p.add_argument("dir", help="the directory books detect wrote to")
    p.add_argument("--out", help="where to put the crops (default: <dir>.crop)")
    p.add_argument("--pages", help="page numbers to cut, e.g. 1,4,7-9")
    p.add_argument("--policy", help="label dictionary, when the snapshot "
                   "names none (as `books read` takes it)")
    p.set_defaults(fn=cmd_crop)

    p = sub.add_parser("fitness",
                       help="is the output fit to run OCR through")
    p.add_argument("pdf", help="the pages to count ink over")
    p.add_argument("--detect", required=True, help="model output directory")
    p.add_argument("--truth", default="", help="truth; without it only what "
                   "lies outside every box is counted")
    p.set_defaults(fn=cmd_fitness)

    p = sub.add_parser("subset", help="distillate: artefacts side by side")
    p.add_argument("--books", help="which bench books, comma-separated")
    p.add_argument("--out", help="where to put hard.pdf and truth/")
    p.set_defaults(fn=cmd_subset)

    p = sub.add_parser("annopage", help="golden bench from the AnnoPage set")
    p.add_argument("root", help="root of the unpacked AnnoPage")
    p.add_argument("--split", default="test", help="test | train")
    p.add_argument("--limit", type=int, default=0, help="take only N pages")
    p.add_argument("--truth-only", action="store_true", dest="truth_only",
                   help="rewrite the truth only, leaving the built pdf alone")
    p.add_argument("--out", help="where to put annopage.pdf and truth/")
    p.set_defaults(fn=cmd_annopage)

    p = sub.add_parser("score", help="contour metrics against the bench truth")
    p.add_argument("truth", help="truth directory (bench/synth/truth)")
    p.add_argument("detect", help="model output directory (…/detect/pages)")
    p.set_defaults(fn=cmd_score)

    p = sub.add_parser("read",
                       help="LEVEL TWO: read the blocks with a model (paid)")
    p.add_argument("dir", help="books detect directory")
    p.add_argument("--out", default="",
                   help="where to put it; <dir>.read by default")
    p.add_argument("--pages", default="", help="which pages: 1,4,7-9")
    p.add_argument("--policy", default="",
                   help="the detector label dictionary; empty = take it from "
                        "the detection snapshot, and a mismatch with it is a "
                        "refusal out loud")
    p.add_argument("--no-resume", action="store_true",
                   help="ask again even for what has already been read")
    p.add_argument("--rent", action="store_true",
                   help="count on a RENTED card instead of VLM_ENDPOINT: "
                        "take a machine, raise vLLM, fetch the result")
    p.add_argument("--budget", type=float, default=0.60,
                   help="spending ceiling, $; reached — the machine dies")
    p.add_argument("--timeout", type=float, default=60.0,
                   help="time ceiling, min; reached — the same")
    p.add_argument("--dry-run", action="store_true",
                   help="build the job and check it, renting nothing")
    p.add_argument("--key", default="", help="path to the ssh key for vast.ai")
    p.set_defaults(fn=cmd_read)

    # THE COMMAND IS `apply`, and `swap` stood here. `swap` names the MECHANICS
    # ("exchange"), not the work, and hints not a word at the journal with undo
    # the command exists for; with no keys it changes nothing and prints a
    # report, so an order reads as an action and turns out to be a lookup.
    # `apply` matches the module that does it, and `--undo` reads as "undo what
    # was applied".
    p = sub.add_parser("apply",
                       help="level two: markup instead of a picture, and undo")
    p.add_argument("dir", help="build directory (books html --out)")
    p.add_argument("--anchor", help="block anchor, of the form p0042-b17")
    p.add_argument("--file", help="file holding the block markup")
    p.add_argument("--kind", default="html",
                   help="content kind: html | otsl | latex | text")
    p.add_argument("--source", default="",
                   help="what produced it; goes to the journal and the block")
    p.add_argument("--undo", action="store_true",
                   help="bring back what stood before the last swap")
    p.add_argument("--status", action="store_true",
                   help="report only: what is replaced, touching nothing")
    p.add_argument("--from", dest="from_read", default="",
                   help="a `books read` directory: place EVERYTHING read, "
                        "one block at a time and each with an undo")
    p.set_defaults(fn=cmd_apply)

    p = sub.add_parser("text",
                       help="reading metric: characters against bench truth")
    p.add_argument("truth", help="truth directory (bench/<book>/truth)")
    p.add_argument("pages", help="directory of what was read (…/detect/pages)")
    p.add_argument("--norm", default=text_norm_default(),
                   help="the normalisation boundary when comparing; "
                        "declared as a number and carried into the report")
    p.set_defaults(fn=cmd_text)

    p = sub.add_parser("overlay",
                       help="boxes over the pages, to look with your own eyes")
    p.add_argument("pdf", help="the pages to draw over")
    p.add_argument("--truth", help="truth directory (bench/synth/truth)")
    p.add_argument("--detect", help="model output directory (…/detect/pages)")
    p.add_argument("--out", help="where to put the pdf with the boxes")
    p.add_argument("--pages",
                   help="which pages: 1,4,7-9; counted from one, as in detect")
    p.set_defaults(fn=cmd_overlay)

    p = sub.add_parser("synth", help="synthetic bench with exact truth")
    p.add_argument("--book", default="spravochnik",
                   help="which bench book: spravochnik|slovar|matematika|"
                        "atlas|katalog|zhurnal")
    p.add_argument("--out", help="where to put <book>.pdf and truth/")
    p.add_argument("--cases",
                   help="which cases, comma-separated; all by default")
    p.set_defaults(fn=cmd_synth)

    p = sub.add_parser("bench", help="the benches: every metric on one run, side by side")
    bs = p.add_subparsers(dest="bench_cmd", required=True)
    q = bs.add_parser("all", help="every applicable metric on one bench and run, as one table and one JSON")
    q.add_argument("bench", help="the book directory, e.g. bench/slovar or "
                                 "processed/ogneupory-vl2. A bench brings "
                                 "truth/ and gets every metric; a book "
                                 "without it gets the truth-free ones")
    q.add_argument("--run", default="",
                   help="which run, by its model label. Omit it when "
                        "the book has exactly one of this kind; with several, "
                        "the command refuses and lists them")
    q.add_argument("--kind", default="detect", choices=("detect", "read"),
                   help="which level to measure: detect, the contours "
                        "(default), or read, the level-two reading")
    q.add_argument("--only", default="",
                   help="comma-separated metric names, instead of every applicable one")
    q.add_argument("--json", default="",
                   help="where to write the records (default: "
                        "results/<bench>-<run>.json, and "
                        "<bench>-<kind>-<run>.json for a level "
                        "that is not detect: a label is the "
                        "model's own name and two levels can "
                        "share one)")
    q.set_defaults(fn=cmd_bench_all)

    q = bs.add_parser("selfcheck",
                      help="every metric's probes on one bench and run: can "
                           "the numbers fall (1 if any is uncaught)")
    q.add_argument("bench", help="the book directory, as `bench all` takes it")
    q.add_argument("--run", default="",
                   help="which run, by its model label; omit it when the book "
                        "has exactly one of this kind")
    q.add_argument("--kind", default="detect", choices=("detect", "read"),
                   help="which level to probe")
    q.add_argument("--only", default="",
                   help="comma-separated metric names, instead of every "
                        "applicable one")
    q.set_defaults(fn=cmd_bench_selfcheck)

    q = bs.add_parser("report",
                      help="every measured number as one generated document")
    q.add_argument("--out", default="",
                   help="where to write it (default: METRICS.md at the root)")
    q.set_defaults(fn=cmd_bench_report)

    p = sub.add_parser("ls", help="what is rented right now")
    p.set_defaults(fn=cmd_ls)

    p = sub.add_parser("down", help="destroy an instance")
    p.add_argument("id", type=int)
    p.set_defaults(fn=cmd_down)

    p = sub.add_parser("reap", help="destroy everything our runs left behind")
    p.set_defaults(fn=cmd_reap)

    p = sub.add_parser("doctor",
                       help="check the environment before spending money")
    p.set_defaults(fn=cmd_doctor)

    p = sub.add_parser("ledger", help="run journal and the estimate from it")
    p.set_defaults(fn=cmd_ledger)

    p = sub.add_parser("replay", help="is the input snapshot complete")
    # nargs="+", not "*": a check whose whole point is its exit code silently
    # approved on an empty list — `books replay --check` with no directory
    # returned 0 and printed not a line.
    p.add_argument("outdir", nargs="+", help="parse directory")
    p.add_argument("--check", action="store_true",
                   help="print what is missing and return 1 if there is any")
    p.set_defaults(fn=replay_mod.cmd_replay)

    p = sub.add_parser("docs", help="regenerate the documents rendered from the code")
    p.set_defaults(fn=cmd_docs)
    return ap


def main(argv=None):
    a = build_parser().parse_args(argv)
    try:
        return a.fn(a) or 0
    except _tool_errors() as e:
        # Code 2 is "could not count", against 1 — "counted, and the number
        # failed". Merged, a silent instrument and a failed metric read alike;
        # the actions on them differ.
        log(f"{type(e).__name__}: {e}")
        return 2
    except Refusal as e:
        # ONE LINE, exit 1: the message names what to do. A refusal used to be
        # a `SystemExit` raised deep in a library, which printed the same line
        # and forced every caller in between to special-case a BaseException.
        log(str(e))
        return 1


if __name__ == "__main__":
    sys.exit(main())
