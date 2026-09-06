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
    log(f"snapshot completeness: books replay --check {shlex.quote(out)}")
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
        return 0, "not a directory"
    names = sorted(f for f in os.listdir(d)
                   if f.endswith(".json") and f != "run.json")
    if not names:
        return 0, "no json files at all"
    try:
        with open(os.path.join(d, names[0]), encoding="utf-8") as f:
            first = json.load(f)
    except (OSError, ValueError) as e:
        return 0, f"{names[0]} does not read as json ({type(e).__name__})"
    if not (isinstance(first, dict) and "blocks" in first
            and "index" in first):
        return 0, (f"json files {len(names)}, but {names[0]} is not a layout "
                   f"page: no blocks/index fields")
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
            f"{what}: no path {path}. Expected a `books detect` run "
            f"directory (pages/ and run.json in it) or the directory of "
            f"layout pages itself (*.json).")
    sub = os.path.join(path, "pages")
    (here, why_here), (there, why_sub) = _page_files(path), _page_files(sub)
    if there and not here:
        # A value, not silence: a substituted directory must show in the
        # journal, or "measured the wrong thing" reads like "measured".
        log(f"{what}: given a run directory, taking the pages from {sub} — "
            f"there are {there}")
        return sub
    if here:
        return path
    raise SystemExit(
        f"{what}: no layout pages found. In {path} — {why_here}; in {sub} — "
        f"{why_sub}. Expected a `books detect` run directory (pages/ and "
        f"run.json in it) or the page directory itself. There is nothing to "
        f"count — and that is not a zero of losses.")


def _run_dir(path, what):
    """The RUN directory: the one holding `run.json`. Takes `<out>/pages` too.

    The other side of the same trouble: `books feed bench/…/detect/pages` died
    with `FileNotFoundError` on `pages/run.json`, never saying it wanted the
    parent.
    """
    if not os.path.exists(path):
        raise SystemExit(
            f"{what}: no path {path}. Expected a `books detect` run "
            f"directory — the one holding run.json.")
    if os.path.exists(os.path.join(path, "run.json")):
        return path
    up = os.path.dirname(os.path.abspath(path.rstrip("/")))
    if _page_files(path)[0] and os.path.exists(os.path.join(up, "run.json")):
        log(f"{what}: given a page directory, taking the snapshot from {up}")
        return up
    raise SystemExit(
        f"{what}: no run.json in {path}. Expected a `books detect` run "
        f"directory (pages/ and run.json in it), not a page directory and "
        f"not a book root.")


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
            f"the snapshot {a.dir}/run.json names no label dictionary and "
            f"--policy is not given. Asking by a guessed dictionary means "
            f"leading a table with the text prompt and filing prose as "
            f"reading.")
    if a.policy and known and a.policy != known:
        raise SystemExit(
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
    log(f"snapshot: {p}")
    log(f"next: books html {out}   |   books text <truth> {out}/pages")
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
    log(f"feed {p['feed_mode']}, crop {p['crop_dpi']:.0f} dpi, "
        f"page {p['page_dpi']:.0f} dpi, "
        f"hole fill {p['hole_fill']}")
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
    log(f"pages {len(res)}, VLM requests {asked} "
        f"({asked/max(len(res),1):.1f} per page), artefacts past the VLM "
        f"{arts}")
    log(f"{path}; feed pictures in {out}")
    return 0


def cmd_overlay(a):
    """Boxes over the pages: truth solid, the model's guess dashed."""
    from . import detect, overlay
    marks = [(_pages_dir(a.truth, "--truth"), "T")] if a.truth else []
    if a.detect:
        marks.append((_pages_dir(a.detect, "--detect"), "M"))
    if not marks:
        raise SystemExit("nothing to draw: give --truth and/or --detect")
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
    truth = _pages_dir(a.truth, "truth")
    det = _pages_dir(a.detect, "model boxes")
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
    truth = _pages_dir(a.truth, "truth")
    pages = _pages_dir(a.pages, "what was read")
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
    log(f"AnnoPage from {a.root}, split {a.split}")
    annopage.build(a.root, out, split=a.split, limit=a.limit,
                   truth_only=a.truth_only, log=log)
    log(f"next: books detect {shlex_quote(out)}/annopage.pdf "
        f"--out {shlex_quote(out)}/detect")
    return 0


def cmd_synth(a):
    """Build a synthetic book with exact truth. Local and free."""
    from . import synth
    from .run import knobs
    out = a.out or f"bench/{a.book}"
    cases = a.cases.split(",") if a.cases else None
    from .books import load
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
        log(f"  [ – ] .env in the root — none; it is needed only for "
            f"VLM_API_KEY when reading over a network endpoint. Sample: "
            f".env.example")

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
            f"{'present, %d chars' % len(key) if key else 'not set'}")
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
    from .run import knobs

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
    except Exception as e:                               # noqa: BLE001
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
    ok = sum(1 for r in rows if r.get("ok"))
    spent = sum(r.get("cost_usd") or 0 for r in rows)
    log(f"{len(rows)} runs, successful {ok}, spent ${spent:.3f}")
    for r in rows[-10:]:
        # NOT MEASURED AND ZERO ARE DIFFERENT THINGS. `else 0` stood here, and
        # a run whose `setup_s` is zero (delivery cut short by a signal) printed
        # as "0 Mbps" — "the link is dead" instead of "no measurement". Six
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
            f"{'ok ' if r.get('ok') else 'fail'}  "
            f"start {r.get('setup_s',0)/60:4.1f}m "
            f"({' not measured' if mb is None else f'{mb:4.0f} Mbps'})  "
            f"count {r.get('run_s',0)/60:5.1f}m  ${r.get('cost_usd',0):.3f}  "
            f"machine {r.get('machine_id')}")
    log(f"estimate from the journal: {ledger_mod.fit()}")
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

    p = sub.add_parser("feed",
                       help="what would go to the VLM, without asking it")
    p.add_argument("dir", help="the directory books detect wrote to")
    p.add_argument("--out", help="where to put the feed pictures")
    p.set_defaults(fn=cmd_feed)

    p = sub.add_parser("fitness",
                       help="is the output fit to run OCR through")
    p.add_argument("pdf", help="the pages to count ink over")
    p.add_argument("--detect", required=True, help="model output directory")
    p.add_argument("--truth", default="", help="truth; without it only what "
                   "lies outside every box is counted")
    p.add_argument("--selfcheck", action="store_true",
                   help="damage battery: can the number fall")
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
    p.add_argument("--selfcheck", action="store_true",
                   help="mutation battery: can the number fall (1 if not)")
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
    p.add_argument("--selfcheck", action="store_true",
                   help="damage battery: can the number fall (1 if not)")
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
    p.add_argument("--selfcheck", action="store_true",
                   help="can the check itself fail (1 if not)")
    p.add_argument("--check", action="store_true",
                   help="print what is missing and return 1 if there is any")
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
