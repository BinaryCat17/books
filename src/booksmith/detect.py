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
        f"page {page.index}: block labels {bad} are not from the policy "
        f"vocabulary {pol} (adapter {adapter}; the vocabulary knows "
        f"{len(known)} spellings: {sorted(known)}). Counting cannot go on: "
        f"artefact labels come from that same vocabulary, and a block with a "
        f"foreign spelling would give 'artefacts 0' -- a zero from not "
        f"understanding, dressed as a measurement. Fix the label translation "
        f"in the adapter, or policy.POLICIES itself, but not this check.")


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
    raise SystemExit(f"LAYOUT_ADAPTER={which!r}: I know only {ADAPTERS}")


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
            f"adapter {det.name} did not declare which knobs it reads "
            f"(models/base.py, knobs_read). An empty tuple is a lawful "
            f"answer, silence is not: a silent adapter would take the "
            f"snapshot back to what this declaration exists against."
            ) from None
    unknown = [n for n in mine if n not in knobs.KNOB]
    if unknown:
        raise SystemExit(
            f"adapter {det.name} declared knobs the registry does not hold: "
            f"{unknown}. Either a typo, or the environment is read past "
            f"run/knobs.py -- both troubles are silent.")
    roles = {}
    for n in knobs.names():
        if n in mine:
            roles[n] = f"adapter {det.name}"
        elif n in COMMAND_KNOBS:
            roles[n] = "the books detect command"
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
                    f"in --pages {spec} the range {part} was not parsed. "
                    f"Expected 7-9, counting from one.")
            if not rng:
                raise SystemExit(
                    f"range {part} is empty: the end is before the start")
            want.extend(rng)
        else:
            try:
                want.append(int(part))
            except ValueError:
                # Out loud and with a sample, not a stack trace: this flag is
                # typed by hand, and a typo in it is routine.
                raise SystemExit(
                    f"in --pages {spec} the piece {part} is not a page "
                    f"number. Expected 1,4,7-9 or 1 4 7-9, from one.")
    bad = [p for p in want if not 1 <= p <= total]
    if bad:
        raise SystemExit(f"the book has {total} pages, {bad} were asked")
    if not want:
        raise SystemExit(f"the page set {spec} is empty -- nothing to count")
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
        log(f"WARNING: PAGE_DPI={dpi_raw} truncated to {dpi_used} -- the "
            f"raster is drawn at a whole number of dots per inch")

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
        raise SystemExit(f"no file {pdf}")
    if os.path.isdir(pdf):
        raise SystemExit(f"{pdf} is a directory, one book's PDF is expected")

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
        log(f"WARNING: the threshold set is not the native one -- {line}")

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
    log(f"knobs set from outside {len(given)}"
        + (f": {', '.join(given)}" if given else ""))
    if dead:
        log(f"WARNING: of those, {len(dead)} are read neither by adapter "
            f"{det.name} nor by the command itself: {', '.join(dead)} -- the "
            f"value set does NOT affect this run, and the snapshot marks it "
            f"for_this_run: false")
    log(f"detector {det.name}: "
        f"{det.fingerprint().get('model')} from {det.dir}")
    # About the input we ask the FINGERPRINT, not one adapter's fields: the
    # second adapter had none, and a hard `det.keep_ratio` dropped the run on
    # the first foreign model. Every adapter must have a fingerprint -- that is
    # the contract.
    fp_in = (det.fingerprint().get("input") or {})
    log(f"model input {fp_in.get('width')}x{fp_in.get('height')} (WxH): "
        + ", ".join(f"{k}={v}" for k, v in fp_in.items()
                    if k not in ("width", "height")))
    log(f"vocabulary {pol}, "
        f"classes {len(det.labels)}, "
        f"native threshold {det.fingerprint().get('native_threshold')}")

    # Opening speaks IN A LINE too: the three troubles the check above misses
    # used to come out as tracebacks -- an empty file (`EmptyFileError`), a
    # non-PDF under a pdf name (`FileDataError`), a book with no pages. All
    # three checked; the exception classes are foreign and deliberately not
    # named -- pymupdf has its own list, and it has changed.
    try:
        doc = pymupdf.open(pdf)
        pages_total = doc.page_count
    except Exception as e:                   # noqa: BLE001 -- foreign tree
        raise SystemExit(
            f"{pdf} does not open as a PDF: {type(e).__name__}: {e}") from None
    if not pages_total:
        raise SystemExit(
            f"{pdf} opened, but has zero pages -- nothing to count")
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
        log(f"pages of the previous run removed: {len(stale)}")

    log(f"{os.path.basename(pdf)}: pages in the file {doc.page_count}, "
        f"counting {len(idxs)} at {dpi_used} dpi")

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
                log(f"  {n}/{len(idxs)} pages, boxes {sum(counts.values())}")
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
    box_stage = (f"after the docling pipeline {mode}" if had_pipeline
                  else "the model's own, there was no pipeline over boxes")
    log(f"boxes {total} on {len(idxs)} pages "
        f"({total/len(idxs):.1f} per page), artefacts {artefacts}, "
        f"rank ties {ties}, {took:.1f} s ({took/len(idxs):.2f} s/page)"
        + (f" -- every box number is AFTER the docling pipeline {mode}"
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
        log(f"WARNING: on {mute_pages} pages of {len(idxs)} adapter "
            f"{det.name} did not say 'boxes accepted' -- how many the model "
            f"itself gave cannot be checked; the sums below are incomplete "
            f"by those pages")
    if had_pipeline:
        took = pipe["before"] - pipe["after"]
        share = 100.0 * took / pipe["before"] if pipe["before"] else 0.0
        log(f"docling pipeline {mode}: the model gave {pipe['before']} "
            f"boxes, it removed {took} ({share:.1f}%), {pipe['after']} went "
            f"into the book, {pipe['children']} into children, "
            f"{pipe['reordered']} permuted, "
            f"{pipe['page_count']} pages of {len(idxs)} through it")
        # The removals are NOT broken down by label, and silence about that
        # is not allowed: "table accepted 0" with the knob on would read as
        # "the model found none" when it may mean "it did, the pipeline
        # removed it".
        log(f"    what the pipeline removed is NOT broken down by label: "
            f"the adapter gives 'boxes before' as a total only "
            f"({pipe['before']}), never by class "
            f"(models/docling_heron.py, pipe_meta)")
        if pipe["missing_numbers"]:
            log(f"WARNING: the pipeline gave no numbers "
                f"{sorted(pipe['missing_numbers'])} -- the sums above are "
                f"incomplete by as much")
        if pipe["page_count"] != len(idxs):
            log(f"WARNING: {pipe['page_count']} pages of {len(idxs)} went "
                f"through the pipeline -- the stage numbers are summed over "
                f"different samples")
        if pipe["after"] != total:
            log(f"WARNING: the pipeline reported {pipe['after']} boxes "
                f"after itself, and the pages hold {total}: a difference of "
                f"{abs(pipe['after'] - total)}")
        if not mute_pages and pipe["before"] != model_boxes:
            log(f"WARNING: the pipeline took {pipe['before']} boxes and "
                f"the model gave {model_boxes}: a difference of "
                f"{abs(pipe['before'] - model_boxes)} boxes lost between the "
                f"stages")
    else:
        # A zero from a check, not the silence of a step: it says there WAS
        # no pipeline, and says it with the number of pages it was not on.
        log(f"the vendor pipeline did not touch the boxes: 0 pages of "
            f"{len(idxs)} through it, 'accepted' below is the model's own")
        if not mute_pages and model_boxes != total:
            log(f"WARNING: the model gave {model_boxes} boxes and the "
                f"pages hold {total} with no pipeline at all: someone "
                f"unnamed is correcting the boxes")

    # A quantity, not "verified": how many label spellings met, out of how
    # many known. Foreign ones are always zero -- not because they do not
    # happen, but because such a run never gets this far (`_check_labels` drops
    # it on that very page).
    log(f"label spellings checked against vocabulary {pol}: "
        f"{len(spellings)} of {len(known)} known, foreign 0 -- else the run "
        f"would have fallen")

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
        log(f"    by class, TWO STAGES: 'accepted' is {box_stage}; 'best "
            f"rejected' is the model's threshold BEFORE it. Do not add them.")
    else:
        log(f"    by class, both numbers from the model ({box_stage}): "
            f"'accepted' is boxes above the threshold, 'best rejected' the "
            f"best one below it")
    mark = " (after the pipeline)" if had_pipeline else ""
    answer_mark = ", BEFORE the pipeline" if had_pipeline else ""
    for lab in shown:
        line = f"    {lab:18s} accepted{mark} {counts.get(lab, 0):5d}"
        if lab in rej_best:
            line += (f", best rejected {rej_best[lab]:.3f} "
                     f"(p. {rej_pages[lab]}{answer_mark})")
        log(line)
    rest = {l: v for l, v in rej_best.items() if l not in shown}
    if rest:
        top = max(rest.items(), key=lambda kv: kv[1])
        log(f"    other classes rejected {len(rest)}, "
            f"highest of all {top[0]} {top[1]:.3f}"
            + (" (all by the model's threshold, BEFORE the pipeline)"
               if had_pipeline else ""))

    if total == 0:
        raise RuntimeError(
            f"not one box on {len(idxs)} pages -- a refusal, not an empty "
            f"book. Threshold LAYOUT_SCORE_THRESHOLD="
            f"{knobs.knob('LAYOUT_SCORE_THRESHOLD')}, weights {det.dir}. "
            f"Best rejected: {rej_best or 'nothing was rejected at all'}")

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
                         "by the model threshold, BEFORE the vendor pipeline",
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
                             ("the adapter gives 'boxes before' as one "
                              "number per page; by class there are none -- "
                              "see pipe_meta in models/docling_heron.py"),
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
    log(f"snapshot: {os.path.join(outdir, 'run.json')}")
    return outdir
