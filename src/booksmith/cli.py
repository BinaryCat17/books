"""Single entry point: books <command>.

    books doctor                 check everything BEFORE the money starts
    books offers                 look at the market, renting nothing
    books prepare book.djvu      djvu -> PDF, spreads cut apart
    books detect book.pdf        LEVEL ONE: contours, local and free
    books hybrid book-dir/       a served hybrid model: boxes and text in one
                                 call, filed as a read run with its own boxes
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
    books serve layout           a detector of the tree's own behind the protocol
    books serve vlm              a vLLM behind describe and health, chat passed through
    books web serve              the backend: users, jobs and HTTP over the service
    books web user <name>        a user of the web, with a store of their own
    books ls | books down 12345 | books reap
    books ledger                 run journal and the estimate from it
    books replay --check out/    is the input snapshot complete
    books docs                   regenerate the documents rendered from the code

This list is `books --help`, and `tests/contract/test_docs.py` checks it
against the parser both ways. Every command with its flags: `docs/commands.md`.
"""
import argparse
import dataclasses
import os
import signal
import sys

from booksmith.core import config
from booksmith.processing.read.rented import paddleocr_vl
from .remote import ledger as ledger_mod
from .remote.spec import HostReq
from booksmith.core.log import log
from booksmith.core import knobs
from booksmith.core import replay as replay_mod
from booksmith.core import job
from booksmith.core.errors import Cancelled, Refusal
from booksmith.core import book
from booksmith import service


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
    # The CUDA requirement comes from the model, not from the rental layer:
    # `HostReq` has no default on purpose. Whoever builds the job names it.
    host.cuda_min = paddleocr_vl.CUDA_MIN
    from .remote.vast import Vast
    v = Vast()
    warm = ledger_mod.warm_machines(a.image or paddleocr_vl.BASE_IMAGE)
    v.pick(host, paddleocr_vl.IMAGE_GB, a.minutes, warm, show=8,
           payload_gb=paddleocr_vl.PAYLOAD_GB, warmup_s=paddleocr_vl.WARMUP_S)
    return 0


def cmd_prepare(a):
    """djvu -> PDF with the spreads cut apart. Local and free.

    Its own command, not merely a step inside the parse: spreads must be seen
    with the eye before paying for a card, or the recogniser reads two pages of
    a spread as one.
    """
    from booksmith.processing.extract import djvu
    print(djvu.to_pdf(a.file, dst=a.out, split=a.split))
    return 0


def _with(a, **kw):
    """A copy of the parsed arguments with fields replaced.

    Mutating the caller's Namespace would leave the change behind for a second
    command in the same process (the tests run several).
    """
    import copy
    out = copy.copy(a)
    for k, v in kw.items():
        setattr(out, k, v)
    return out


def cmd_detect(a):
    """Level-one contours over the PDF pages. No VLM, no rental, no money.

    Given a book directory the run lands under `detect/<label>/`, the label
    being the model's own name, so a second detector stands beside the first
    instead of overwriting it; given a bare PDF, beside the file. `--out` wins
    over both.
    """
    import shlex
    out = service.detect(service.admin(), a.file, knobs.passthrough(), a.pages, a.out,
                         a.model or "")
    # Quoted: five of the nine files in raw/ carry spaces and brackets, and a
    # hint you cannot paste into a shell is not a hint.
    log(f"snapshot completeness: books replay --check {shlex.quote(out)}")
    return 0


def cmd_hybrid(a):
    """Boxes and text in one call from a served hybrid model. Filed as a read
    run with its own boxes: `read/<label>/` under a book directory, else
    beside the file."""
    import shlex
    out = service.hybrid(service.admin(), a.file, knobs.passthrough(), a.pages, a.out,
                         a.model or "")
    log(f"snapshot completeness: books replay --check {shlex.quote(out)}")
    log(f"next: books html {out}   |   books bench all <book> --kind read")
    return 0


# --------------------------------------------- the directories commands take
# `books detect` leaves two directories side by side: `<out>` with the snapshot
# `run.json`, and `<out>/pages` with the layout pages. Both forms are taken by
# both sides below, and a missing path fails in one line naming what it wanted.


def cmd_html(a):
    """Level one's product: text as markup, artefacts as pictures."""
    out = service.html(service.admin(), a.dir, knobs.passthrough(), a.out)
    log(f"built into {out}")
    return 0


def cmd_apply(a):
    """Level two in place: markup instead of the picture, and back again.

    Not one call to a model here: this layer only places a ready fragment, and
    what generated it — `books read`, or a hand — is not its business.
    """
    from booksmith.processing.assemble import apply as ap
    # Not the detection-run resolver: that one looks for the detection
    # `run.json` and points at a directory with `pages/`, while this command
    # wants the build directory, the one with `book.html`.
    d = os.path.abspath(a.dir)
    try:
        if a.from_read:
            if a.anchor or a.undo:
                raise ap.SwapError(
                    "--from together with --anchor or --undo: these are "
                    "different jobs. --from places EVERYTHING read, "
                    "--anchor one block.")
            ap.from_read(d, a.from_read)
            return 0
        if a.status:
            ap.status(d)
            return 0
        if a.undo and not a.anchor:
            raise ap.SwapError(
                "--undo without --anchor: name the block to roll back. "
                "Unnamed, the command would roll back who knows what; the "
                "list of replaced ones is `books apply <dir> --status`.")
        if a.undo:
            ap.undo(d, a.anchor)
        elif a.anchor:
            if not a.file:
                raise ap.SwapError("nothing to place: give --file with the "
                                   "block markup, or --undo")
            with open(a.file, encoding="utf-8") as f:
                ap.put(d, a.anchor, f.read(), kind=a.kind,
                       source=a.source or os.path.basename(a.file))
        else:
            # No keys means do the work, not a report: the book remembers which
            # read it was built from, and `books apply book` is what a person
            # types first. Safe only through idempotence -- a repeat places
            # nothing and does not grow the undo stack.
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
            ap.from_read(d, src)
    except ap.SwapError as e:
        log(str(e))
        return 1
    return 0


def cmd_read_rented(a, policy_name, out):
    """The same work on a rented card: same code, same count, other place.

    A branch of `books read` and not a command of its own, so that reading on a
    rented card has exactly one way in.
    """
    from booksmith.processing.read.rented import paddleocr_vl as vl
    from .remote import runner

    spec = vl.spec(book.pdf_of(a.dir), a.dir, pages=a.pages, policy=policy_name,
                   budget_usd=a.budget, timeout_minutes=a.timeout)
    log(f"job {spec.name}: input {len(spec.inputs)} paths, ceiling "
        f"${spec.budget_usd:.2f} and {spec.timeout_minutes:.0f} min, card "
        f"{spec.host.gpu}, CUDA from {spec.host.cuda_min}")
    # The money ceiling is unreachable while it exceeds the hourly price:
    # `Budget` takes the smaller of the two, so at a price ceiling of
    # $0.60/hour a $0.60 limit is exactly one hour and time always cuts.
    # Whoever pays is told, not whoever later reads the journal.
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
    """Level two: read the content of the blocks with a model.

    The only command spending money outside the rental, and so the only one
    asking the endpoint its name before the first request, dropping the run on a
    mismatch. The product is detection's own `pages/*.json` with `content` and
    `kind` filled in, so every command downstream eats it unchanged.
    """
    from booksmith.processing.read import driver as vread

    out = a.out or (os.path.abspath(a.dir).rstrip("/") + ".read")
    if a.rent:
        # The label dictionary comes from the detection snapshot, not typed
        # by hand: `run.json` already carries `policy.vocabulary`, and a typed
        # default diverges silently -- `DocLayNet` (11 labels) is a strict
        # subset of `Docling-egret` (17), so that pair would pass without a word.
        policy_name = vread.policy_for(a.dir, a.policy, what="the paid run").name
        os.makedirs(out, exist_ok=True)
        return cmd_read_rented(a, policy_name, out)

    service.read(service.admin(), a.dir, knobs.passthrough(), out, a.pages or "",
                 a.policy or "", a.model or "")
    log(f"next: books html {out}   |   books text <truth> {out}/pages")
    return 0


def cmd_crop(a):
    """What `books read` would send, cut by its own path. Nothing sent, free.

    The driver runs in preview: the same crop rule, the same dpi, the same
    prompts and generation parameters, written to `crops/` and `would_ask.json`.
    A preview cutting by knobs of its own shows pictures the model never sees.
    """
    t = service.crop(service.admin(), a.dir, knobs.passthrough(), a.out,
                     a.pages or "", a.policy or "")
    out = t["out"]
    log(f"would ask {t.get('would_ask', 0)} of {t['block_count']} blocks; not "
        f"asked {t['not_asked']}, crop failed {t['crop_failed']}")
    # The troubles are printed, not left in the file: a preview is looked at to
    # decide whether to pay, and "crop failed 2" with no anchor decides nothing.
    if t["crop_failed"]:
        log(f"  THE CROP FAILED on {t['crop_failed']} blocks -- they would go "
            f"UNREAD in the paid run: {'; '.join(t['crop_failures'][:3])}"
            f"{'...' if t['crop_failed'] > 3 else ''}")
    if not t.get("would_ask"):
        # The same rule the paid run states: zero asked is not a success, and
        # this is the command that exists to find that out before the money.
        log("NOT ONE BLOCK WOULD BE ASKED -- not a success, an empty run. "
            "Look at `not_asked` in would_ask.json for the reason of each.")
    log(f"{os.path.join(out, 'would_ask.json')}; crops in {os.path.join(out, 'crops')}")
    return 0


def cmd_overlay(a):
    """Boxes over the pages: truth solid, the model's guess dashed."""
    service.overlay(service.admin(), a.pdf, a.truth, a.detect, a.out, a.pages or "")
    return 0


def cmd_score(a):
    """Contour metrics: truth against the model output.

    Whether the numbers can fall is `books bench selfcheck`, which runs every
    applicable metric's probes on a bench and a run.
    """
    from booksmith.core import policy
    from booksmith.datasets.metrics import contour as metrics
    truth = book.pages_dir(a.truth, "truth")
    det = book.pages_dir(a.detect, "model boxes")
    # Each side under its own policy: the run's out of the snapshot beside
    # its pages, truth's the union of the tree's vocabularies.
    metrics.report(metrics.compare(truth, det, policy.UNION, book.policy_beside(det)))
    return 0


def text_norm_default():
    """The normalisation default comes from the module, not typed here twice.

    A second copy of the value never reaches the consumer until somebody
    remembers this file.
    """
    from booksmith.datasets.metrics import text
    return text.NORM


def cmd_text(a):
    """The reading metric: the truth of characters against what the model read.

    Its own command, not a column in `books score`: that one measures geometry
    and labels, this one characters. One number for two questions is how an
    instrument here has already lied.
    """
    from booksmith.datasets.metrics import text
    truth = book.pages_dir(a.truth, "truth")
    pages = book.pages_dir(a.pages, "what was read")
    text.report(text.measure(truth, pages, norm=a.norm))
    return 0


def cmd_fitness(a):
    """Fitness of the output: will the meaning reach level two. By ink."""
    from booksmith.processing.assess import ink as fitness
    det = book.pages_dir(a.detect, "--detect")
    truth = book.pages_dir(a.truth, "--truth") if a.truth else ""
    fitness.report(fitness.measure(a.pdf, det, truth))
    return 0


def cmd_subset(a):
    """Bench distillate: pages where two artefacts of one label stand side by side."""
    from booksmith.datasets.make import subset
    books = [x.strip() for x in (a.books or
             "spravochnik,slovar,matematika,atlas,katalog,zhurnal,annopage"
             ).split(",") if x.strip()]
    subset.build(books, a.out or "bench/hard")
    return 0


def cmd_annopage(a):
    """The golden bench from AnnoPage: real pages, librarians' truth."""
    from booksmith.datasets.make import annopage
    out = a.out or "bench/annopage"
    log(f"AnnoPage from {a.root}, split {a.split}")
    annopage.build(a.root, out, split=a.split, limit=a.limit,
                   truth_only=a.truth_only)
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
                knobs.knob("SYNTH_AGING"), book=a.book)
    log(f"next: books detect {shlex_quote(out)}/{a.book}.pdf "
        f"--out {shlex_quote(out)}/detect")
    return 0


def shlex_quote(s):
    import shlex
    return shlex.quote(s)


def cmd_bench_selfcheck(a):
    """Every applicable metric's probes on one bench and run: can they fall.

    A number is not to be trusted until it has been shown able to fall, so each
    probe spoils the input on purpose and says what must happen to the number.
    Returns 1 if any probe went uncaught; a probe with nothing to grip answers
    "no data" and is counted apart, or zero uncaught over probes that measured
    nothing would read as health.
    """
    which = [n.strip() for n in a.only.split(",") if n.strip()] if a.only else None
    t = service.selfcheck(service.admin(), a.bench, a.run, a.kind, which)
    return 1 if t["uncaught"] else 0


def cmd_bench_all(a):
    """Every applicable metric on one bench and one run: one table, one JSON.

    The one command that writes the numbers down: a comparison between detectors
    typed into prose by hand drifts from the runs it claims to describe.
    """
    which = [n.strip() for n in a.only.split(",") if n.strip()] if a.only else None
    service.bench(service.admin(), a.bench, knobs.passthrough(), a.run, a.kind, which, a.json,
                  pages=a.pages)
    return 0


def cmd_bench_report(a):
    """Every measured number as one generated document, at the repo root.

    A figure stated twice is free to drift; rendered from the record that
    produced it, it cannot.
    """
    service.report(service.admin(), a.out)
    return 0


def cmd_docs(_a):
    """Commands, knobs and metrics as documents, from the code that declares them."""
    from booksmith.datasets import docsgen
    for rel in docsgen.write_all(build_parser(), config.INSTALL):
        log(f"wrote {rel}")
    return 0


def cmd_ls(_a):
    from .remote.vast import Vast
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
    from .remote.vast import Vast
    return 0 if Vast().destroy(a.id) else 1


def cmd_serve_layout(a):
    """A detector of the tree's own behind the model protocol, until stopped.
    A key, when the environment sets `BOOKSMITH_SERVE_KEY`, is demanded on
    every route; it is a secret, not a knob, and reaches no snapshot."""
    from booksmith.serving import layout as serving
    return serving.main(a.host, a.port, key=config.env("BOOKSMITH_SERVE_KEY"))


def cmd_serve_vlm(a):
    """A vLLM behind describe and health, raised here over `VL_MODEL_DIR`
    unless `--upstream` names one already up; the chat route passes through."""
    from booksmith.serving import vlm as serving
    return serving.main(a.host, a.port, a.upstream or "",
                        key=config.env("BOOKSMITH_SERVE_KEY"), log_dir=a.log_dir)


def cmd_web_serve(a):
    """The backend, until stopped: users, jobs and HTTP over the service."""
    from booksmith.web import app as web_app
    return web_app.serve(a.host, a.port)


def cmd_web_user_add(a):
    """A user of the web with a store of their own. The password comes from
    `BOOKSMITH_PASSWORD` or a prompt, never from the command line, where
    every shell keeps a history."""
    import getpass
    from booksmith.web import auth as web_auth
    from booksmith.web.db import Db
    from booksmith.web.settings import Settings
    s = Settings.from_env()
    password = os.environ.get("BOOKSMITH_PASSWORD") or getpass.getpass("password: ")
    db = Db(s.db_path)
    try:
        user_id = web_auth.add_user(db, a.name, password, a.role)
        store = s.store_of(user_id, a.role)
    finally:
        db.close()
    log(f"user {a.name} ({a.role}), id {user_id}, store {store}")
    return 0


def cmd_reap(_a):
    from .remote.vast import Vast
    Vast().reap()
    return 0


def cmd_doctor(_a):
    """Check everything that can wreck a run before the money starts."""
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
    # over a network endpoint, and the vast key lives apart in ~/.config/vastai.
    # Failing acceptance over it is a false alarm, and a false alarm teaches
    # people not to look at acceptance at all. Its only live tenant is
    # `VLM_API_KEY`, which can be exported instead.
    if not os.path.exists(config.ENV_FILE):
        log("  [ – ] .env in the root — none; it is needed only for "
            "VLM_API_KEY when reading over a network endpoint. Sample: "
            ".env.example")

    try:
        from .remote.vast import Vast
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

    # Separate blocks, and not through `check` either: detection and the vendor
    # pipeline install as optional sets, and whoever only rents needs neither.
    # Silence is no better, so both end as a value in the last line -- a bare
    # "all in order" stays "in order" with the active adapter having no weights.
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

    The key lives outside the knob registry on purpose: everything declared
    there lands in `run.json` as a value, and the snapshot goes into git. The
    price is a name no registry walk sees, so it is spoken at least here.
    """
    ep = knobs.knob("VLM_ENDPOINT")
    key = config.env("VLM_API_KEY")
    log("reading blocks (books read, level two):")
    if ep:
        log(f"  [ok  ] VLM_ENDPOINT={ep}, key VLM_API_KEY "
            f"{f'present, {len(key)} chars' if key else 'not set'}")
        # Asked, not assumed: a shim describes itself, a bare vLLM does not,
        # and both are lawful; what is said is which, as a value.
        from booksmith.core import served
        try:
            d = served.Describe.from_json(served.fetch(
                served.root_of(ep) + served.DESCRIBE, timeout=10,
                headers=served.bearer(key)))
            log(f"  [ok  ] describes itself: {d.kind} {d.label}, chat route "
                f"as {(d.openai or {}).get('model')!r}")
            return f"endpoint set, describes itself as {d.label}"
        except served.Unreachable as e:
            log(f"  [ – ] no describe at {served.root_of(ep)}: {e.why[:60]} -- "
                f"a bare vLLM, taken by /models at run time")
        except Refusal as e:
            log(f"  [no  ] describes itself wrongly: {e}")
        return f"endpoint set, key {'present' if key else 'none'}"
    log("  [—   ] VLM_ENDPOINT not set: `books read` will refuse out loud "
        "rather than knock at nothing. There is no default on purpose. On a "
        "rented card run.sh sets the endpoint and no key is needed there — "
        "vLLM is raised on the loopback")
    return "endpoint not set (rental does not need one)"


def _doctor_detect():
    """What can count contours today: packages and weights of every adapter.

    The adapter list comes from `detect.py:ADAPTERS`, since a second list
    drifts, and each adapter is raised rather than tested by a weights path --
    the four name their weights differently, and a list of names here would
    drift too. Nothing found fails acceptance: it says as a value what is
    absent and what turns it on, and what the check itself cost.
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
        # A zero from checking and a zero from not understanding are different
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
    have, t0 = [], time.time()
    for which in detect.ADAPTERS:
        t = time.time()
        if which == "served" and not knobs.knob("LAYOUT_ENDPOINT"):
            log(f"  [ – ] {which:14s} LAYOUT_ENDPOINT not set: no model to "
                f"describe, and nothing is raised for one")
            continue
        try:
            with dataclasses.replace(job.current(),
                                     settings={**knobs.passthrough(),
                                               "LAYOUT_ADAPTER": which}).active():
                det = detect._adapter()
        except (Exception, SystemExit) as e:
            # `SystemExit` is caught on purpose: at `DOCLING_PIPELINE=full`
            # with no vendor package the docling adapter leaves by exactly
            # that, and one adapter of four must not end the check. "No
            # weights" and "weights present, adapter would not rise" are
            # different troubles: a download cures only the first.
            kind = ("no weights" if type(e).__name__ == "WeightsMissing"
                    else f"DID NOT RISE ({type(e).__name__})")
            log(f"  [ – ] {which:14s} {kind}: {e}")
            continue
        w = getattr(det, "onnx", "") or ""
        mb = os.path.getsize(w) / 2 ** 20 if os.path.exists(w) else 0.0
        have.append(which)
        log(f"  [ok  ] {which:14s} {det.name}, labels "
            f"{len(det.labels)}, weights {mb:.0f} MB, rose in "
            f"{time.time() - t:.1f} s — {det.where()}")
        det = None                        # not holding 4 graphs at once
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

    The presence of the modules is checked, not their import: `docling.utils.
    layout_postprocessor` takes 8.3 s to rise, and acceptance would pay it every
    time. `rtree` is imported for real, at 0.2 s -- it pulls the system
    libspatialindex, so a wheel in place does not yet mean it imports.
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
    # The version comes from the distribution, not `docling.__version__`: one
    # package, two deliveries (`docling-slim` and full), and pyproject pins the
    # version to the point, a vendor rule change moving our boxes otherwise.
    # With no distribution at all, "not declared" is not a version.
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
        log(f"journal empty ({ledger_mod.file()})")
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

    One base class and not a tuple of classes looked up by module path: a
    renamed module empties such a tuple in silence, and a traceback from a
    failed instrument would then read as one from our own bug.
    """
    from booksmith.core.errors import Unmeasurable
    return (Unmeasurable,)


class _Parser(argparse.ArgumentParser):
    """Usage errors leave with 64, because 2 is taken: it means "could not
    count", and a typo in a flag must not read as a broken instrument."""

    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(64, f"{self.prog}: {message}\n")


def _model_arg(p):
    p.add_argument("--model", default="",
                   help="an entry of the admin's models.json: its endpoint "
                        "fills the knob the run reads, its key rides as a "
                        "secret")


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
    _model_arg(p)
    p.set_defaults(fn=cmd_detect)

    p = sub.add_parser("hybrid",
                       help="boxes and text in one call from a served hybrid "
                            "model, filed as a read run")
    p.add_argument("file", help="book directory or PDF")
    p.add_argument("--out", help="where to put pages/ and run.json")
    p.add_argument("--pages", help="which pages: 1,4,7-9; all by default")
    _model_arg(p)
    p.set_defaults(fn=cmd_hybrid)

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
    _model_arg(p)
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
    q.add_argument("--pages", default="",
                   help="measure these pages only, counted from 1 as "
                        "`books detect` counts them; the records go to a "
                        "file of their own name, never the book's")
    q.add_argument("--json", default="",
                   help="where to write the records (default: "
                        "results/<bench>-<run>.json, "
                        "<bench>-<kind>-<run>.json for a level "
                        "that is not detect: a label is the "
                        "model's own name and two levels can "
                        "share one; and processed-<book>-... for a "
                        "book under processed/)")
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
                      help="every measured number as one generated document, "
                           "out of the data home's results/; with BOOKSMITH_HOME "
                           "set that is not the repository's METRICS.md")
    q.add_argument("--out", default="",
                   help="where to write it (default: METRICS.md in the data home)")
    q.set_defaults(fn=cmd_bench_report)

    p = sub.add_parser("ls", help="what is rented right now")
    p.set_defaults(fn=cmd_ls)

    p = sub.add_parser("down", help="destroy an instance")
    p.add_argument("id", type=int)
    p.set_defaults(fn=cmd_down)

    p = sub.add_parser("reap", help="destroy everything our runs left behind")
    p.set_defaults(fn=cmd_reap)

    p = sub.add_parser("web", help="the backend: users, jobs and HTTP over the service")
    ws = p.add_subparsers(dest="what", required=True)
    q = ws.add_parser("serve", help="run the backend until stopped")
    q.add_argument("--host", default="127.0.0.1")
    q.add_argument("--port", type=int, default=8080)
    q.set_defaults(fn=cmd_web_serve)
    q = ws.add_parser("user", help="a user of the web, with a store of their own; "
                                   "the password from BOOKSMITH_PASSWORD or a prompt")
    q.add_argument("name")
    q.add_argument("--role", default="user", choices=("admin", "user"))
    q.set_defaults(fn=cmd_web_user_add)

    p = sub.add_parser("serve", help="a model of the tree's own behind the model protocol")
    ss = p.add_subparsers(dest="what", required=True)
    q = ss.add_parser("layout", help="the detector LAYOUT_ADAPTER names, behind "
                                     "describe, health and layout")
    q.add_argument("--host", default="127.0.0.1")
    q.add_argument("--port", type=int, default=8000)
    q.set_defaults(fn=cmd_serve_layout)
    q = ss.add_parser("vlm", help="a vLLM behind describe and health, the chat "
                                  "route passed through")
    q.add_argument("--host", default="127.0.0.1")
    q.add_argument("--port", type=int, default=8000)
    q.add_argument("--upstream", default="",
                   help="a vLLM already up, its root without /v1; empty raises one "
                        "here over VL_MODEL_DIR")
    q.add_argument("--log-dir", default=".", help="where vllm.log goes")
    q.set_defaults(fn=cmd_serve_vlm)

    p = sub.add_parser("doctor",
                       help="check the environment before spending money")
    p.set_defaults(fn=cmd_doctor)

    p = sub.add_parser("ledger", help="run journal and the estimate from it")
    p.set_defaults(fn=cmd_ledger)

    p = sub.add_parser("replay", help="is the input snapshot complete")
    # nargs="+", not "*": a check whose whole point is its exit code would
    # silently approve on an empty list.
    p.add_argument("outdir", nargs="+", help="parse directory")
    p.add_argument("--check", action="store_true",
                   help="print what is missing and return 1 if there is any")
    p.set_defaults(fn=replay_mod.cmd_replay)

    p = sub.add_parser("docs", help="regenerate the documents rendered from the code")
    p.set_defaults(fn=cmd_docs)
    return ap


def main(argv=None):
    a = build_parser().parse_args(argv)
    stop = job.current().stop
    stop.clear()

    def handler(_signum, _frame):
        # A signal asks the job to stop and raises nothing: every wait in the
        # library asks the job and unwinds at its next check, so a stop cannot
        # land inside a renter's retry or a teardown, which run to their end
        # however often the key is pressed.
        stop.set()
    was = {}
    for s in (signal.SIGINT, signal.SIGTERM):
        try:
            was[s] = signal.signal(s, handler)
        except ValueError:
            pass                           # not the main thread: no signals here
    try:
        # Secrets ride on the job, never in its settings: the transport reads
        # the key from here, and a job the web builds carries its own.
        with dataclasses.replace(job.current(), secrets=config.secrets()).active():
            return a.fn(a) or 0
    except Cancelled as e:
        log(f"stopped: {e}")
        return 130
    except _tool_errors() as e:
        # Code 2 is "could not count", against 1 — "counted, and the number
        # failed": merged, a silent instrument and a failed metric read alike.
        log(f"{type(e).__name__}: {e}")
        return 2
    except Refusal as e:
        # One line, exit 1: the message names what to do, and a `Refusal` is an
        # ordinary exception, so no caller in between special-cases it.
        log(str(e))
        return 1
    finally:
        for sig, h in was.items():
            signal.signal(sig, h)


if __name__ == "__main__":
    sys.exit(main())
