"""`books detect` -- first-level contours, locally and for free.

In: a book PDF and a page selection. Out: `pages/NNNN.json` with boxes, labels
and reading order, plus a full `run.json`. No VLM, no rental, a couple of
seconds a page on the CPU.

`books replay --check` here must return 0: what the detector has none of is a
value (`null`), not a gap, and the knobs are split by who reads them -- adapter,
command, nobody. An empty page set, empty output, foreign pages from an earlier
run and a label outside the policy vocabulary all refuse out loud.
"""
import os
import shlex
import sys
import time

from booksmith.processing.layout.adapters.doclayout import DocLayout
from booksmith.core import book
from booksmith.core import knobs, stamp
from booksmith.core.errors import Refusal
from booksmith.core import raster
from booksmith.core.log import log
from booksmith.core.page import write_json
from booksmith.core import job

# The "text / artefact / service" policy lives only in `policy.py`; two lists drift.
# Artefact labels come from the active policy, not the union: an unnameable class
# would read as an eternal zero. The same vocabulary checks block spellings.


# The three snapshot quantities live in `core/stamp.py`: three commands write one.
_sha256 = stamp.sha256


# The adapter registry: adapters differ in vocabulary and preprocessing, so the
# choice is a declared knob and travels into the snapshot.
ADAPTERS = ("doclayout", "docling", "docling-egret", "yolox", "served")


def _check_labels(page, pol, known, adapter):
    """Every block's label spelling against the model's vocabulary, out loud,
    on every page: `Policy.check(det.labels)` verifies what the weights can
    name, and a translation stands between that and what a block says.
    """
    bad = sorted({b.label for b in page.blocks if b.label not in known})
    if not bad:
        return
    raise Refusal(
        f"page {page.index}: block labels {bad} are not from the policy "
        f"{pol} (adapter {adapter}; the vocabulary knows "
        f"{len(known)} spellings: {sorted(known)}). Counting cannot go on: "
        f"artefact labels come from that same vocabulary, and a block with a "
        f"foreign spelling would give 'artefacts 0' -- a zero from not "
        f"understanding, dressed as a measurement. Fix the label translation "
        f"in the adapter, or the mapping itself, but not this check.")


def _adapter():
    which = knobs.knob("LAYOUT_ADAPTER")
    if which == "doclayout":
        return DocLayout()
    if which == "docling":
        from booksmith.processing.layout.adapters.docling import DoclingHeron
        return DoclingHeron()
    if which == "docling-egret":
        from booksmith.processing.layout.adapters.docling import DoclingEgret
        return DoclingEgret()
    if which == "yolox":
        from booksmith.processing.layout.adapters.yolox import YoloXLayout
        return YoloXLayout()
    if which == "served":
        from booksmith.processing.layout.adapters.served import Served
        return Served()
    raise Refusal(f"LAYOUT_ADAPTER={which!r}: I know only {ADAPTERS}")


# Knobs this command reads, not the adapter's.
# `LAYOUT_SCORE_THRESHOLD` is read here only to print it; the adapter declares it.
COMMAND_KNOBS = ("PAGE_DPI", "LAYOUT_ADAPTER")


def _knob_roles(det):
    """Who reads each registry knob in this run: the adapter, the command or
    nobody -- a complete snapshot that marks a knob nobody read confidently
    names a foreign value. A name outside the registry is a refusal.
    """
    try:
        mine = tuple(det.knobs_read())
    except NotImplementedError:
        raise Refusal(
            f"adapter {det.name} did not declare which knobs it reads "
            f"(layout/base.py, knobs_read). An empty tuple is a lawful "
            f"answer, silence is not: a silent adapter would take the "
            f"snapshot back to what this declaration exists against."
            ) from None
    unknown = [n for n in mine if n not in knobs.KNOB]
    if unknown:
        raise Refusal(
            f"adapter {det.name} declared knobs the registry does not hold: "
            f"{unknown}. Either a typo, or the environment is read past "
            f"core/knobs.py -- both troubles are silent.")
    roles = {}
    for n in knobs.names():
        if n in mine:
            roles[n] = f"adapter {det.name}"
        elif n in COMMAND_KNOBS:
            roles[n] = "the books detect command"
        else:
            roles[n] = None
    return roles


# The knob snapshot's shape lives in the registry: detection and reading share it.
_knobs_snapshot = knobs.snapshot_with_readers


def _identity(det, roles):
    """What makes this run this experiment: the fingerprint, the knobs this
    process read and, for a served model, the knobs read on its side, out of
    the same describe the snapshot records -- so the guard and the snapshot
    cannot disagree, and a served run equals an in-process one."""
    return stamp.identity(det.fingerprint(), stamp.knob_values(
        {"knobs": _knobs_snapshot(roles), "served": det.served()}))


_commit = stamp.commit


def _packages():
    return stamp.packages(stamp.DETECT_PACKAGES)


def parse_pages(spec, total):
    """`--pages 1,4,7-9` -> zero-based indices, counting the input from one.
    Empty means the whole book; a page outside it, or a set that comes out
    empty (`3-1`), is a refusal rather than a run over nothing.
    """
    if not spec:
        return list(range(total))
    # A space separates just like a comma; `detect` and `overlay` share this parser.
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
                raise Refusal(
                    f"in --pages {spec} the range {part} was not parsed. "
                    f"Expected 7-9, counting from one.")
            if not rng:
                raise Refusal(
                    f"range {part} is empty: the end is before the start")
            want.extend(rng)
        else:
            try:
                want.append(int(part))
            except ValueError:
                # Out loud and with a sample, not a stack trace: typed by hand.
                raise Refusal(
                    f"in --pages {spec} the piece {part} is not a page "
                    f"number. Expected 1,4,7-9 or 1 4 7-9, from one.")
    bad = [p for p in want if not 1 <= p <= total]
    if bad:
        raise Refusal(f"the book has {total} pages, {bad} were asked")
    if not want:
        raise Refusal(f"the page set {spec} is empty -- nothing to count")
    return [p - 1 for p in sorted(set(want))]


def run(pdf, outdir, pages_spec=None, det=None, hybrid=False):
    """Run the detector over the PDF pages. Returns the directory path.

    `det` is the adapter already built, or none and it is built here; a
    caller that needs the label before the pages passes it, so one run loads
    one session. `hybrid` files the pages as a read run with its own boxes:
    the model must be a served hybrid, and its blocks carry content and kind.
    """

    dpi_raw = knobs.knob("PAGE_DPI")
    dpi = float(dpi_raw)
    # The snapshot records the integer actually rendered: `get_pixmap` truncates.
    dpi_used = int(dpi)
    if dpi_used != dpi:
        log(f"WARNING: PAGE_DPI={dpi_raw} truncated to {dpi_used} -- the "
            f"raster is drawn at a whole number of dots per inch")

    pdf = os.path.abspath(pdf)
    outdir = os.path.abspath(outdir)
    pagedir = os.path.join(outdir, "pages")

    # Checked before the detector comes up; an empty file or a non-PDF falls at the open.
    if not os.path.exists(pdf):
        raise Refusal(f"no file {pdf}")
    if os.path.isdir(pdf):
        raise Refusal(f"{pdf} is a directory, one book's PDF is expected")

    det = det if det is not None else _adapter()
    spoken = det.served()
    if hybrid and not (spoken and spoken.get("kind") == "hybrid"):
        raise Refusal(
            f"a hybrid run needs a served hybrid model, and "
            f"{det.where()} is "
            + (f"a {spoken.get('kind')} model" if spoken else
               f"the in-process adapter {det.name}")
            + ". Boxes and text in one call come from a model that declared "
              "both; `books detect` runs the rest.")
    # Would this overwrite another experiment: asked before the pages, not after an hour.
    book.guard_identity(outdir, _identity(det, _knob_roles(det)),
                        pages_spec or "", f"this {det.label()} run")
    # The policy must cover the weights vocabulary whole and name nothing extra.
    # The vocabulary picks the policy, not the weights' name: a name can be
    # confused; a served model brings its own mapping onto the classes.
    pol = det.policy()
    pol.check(det.labels)
    arte = pol.artefacts()
    # The same single vocabulary for block spellings, never a union.
    known = set(pol.labels)
    for line in det.threshold_drift():
        # Loudly: a silent divergence means the run went on our number, not the model's.
        log(f"WARNING: the threshold set is not the native one -- {line}")

    # What the operator set, and on its own line what this adapter never reads.
    roles = _knob_roles(det)
    given = list(knobs.passthrough())
    dead = [n for n in given if roles[n] is None]
    # The zero is printed too: a zero from a check, not the silence of a skipped step.
    log(f"knobs set from outside {len(given)}"
        + (f": {', '.join(given)}" if given else ""))
    if dead:
        log(f"WARNING: of those, {len(dead)} are read neither by adapter "
            f"{det.name} nor by the command itself: {', '.join(dead)} -- the "
            f"value set does NOT affect this run, and the snapshot marks it "
            f"for_this_run: false")
    log(f"detector {det.name}: "
        f"{det.fingerprint().get('model')} from {det.where()}")
    # The input comes from the fingerprint, which every adapter has, not from its fields.
    fp_in = (det.fingerprint().get("input") or {})
    log(f"model input {fp_in.get('width')}x{fp_in.get('height')} (WxH): "
        + ", ".join(f"{k}={v}" for k, v in fp_in.items()
                    if k not in ("width", "height")))
    log(f"vocabulary {pol.name or 'the model declared'}, "
        f"labels {len(det.labels)}, "
        f"native threshold {det.fingerprint().get('native_threshold')}")

    # The exception classes are foreign and deliberately not named: pymupdf's list changes.
    try:
        doc = raster.open_pdf(pdf)
        pages_total = doc.page_count
    except Exception as e:
        raise Refusal(
            f"{pdf} does not open as a PDF: {type(e).__name__}: {e}") from None
    if not pages_total:
        raise Refusal(
            f"{pdf} opened, but has zero pages -- nothing to count")
    idxs = parse_pages(pages_spec, pages_total)

    # Pages of an earlier run, mixed in, give the metric a sample from two runs.
    os.makedirs(pagedir, exist_ok=True)
    # The snapshot goes before its pages: a run that dies between them leaves no
    # identity rather than a stale one beside new boxes, which lies to every check.
    snap = os.path.join(outdir, "run.json")
    had_snapshot = os.path.isfile(snap)
    if had_snapshot:
        os.unlink(snap)
    stale = [f for f in os.listdir(pagedir) if f.endswith(".json")]
    if stale:
        for f in stale:
            os.unlink(os.path.join(pagedir, f))
        log(f"pages of the previous run removed: {len(stale)}")
    if had_snapshot:
        log("the previous run.json removed BEFORE its pages: a run that dies "
            "here leaves no identity, not a stale one")

    log(f"{os.path.basename(pdf)}: pages in the file {doc.page_count}, "
        f"counting {len(idxs)} at {dpi_used} dpi")

    t0 = time.time()
    tmp = os.path.join(outdir, f".page.{os.getpid()}.png")
    counts, rej_best, rej_pages = {}, {}, {}
    artefacts = ties = 0
    spellings = set()
    # Two stages, counted apart: `counts` is what reached json, after the vendor
    # pipeline if it ran; `model_boxes` is what the model gave above the threshold.
    model_boxes = mute_pages = 0
    pipe = {"page_count": 0, "before": 0, "after": 0, "children": 0, "reordered": 0,
            "modes": set(), "missing_numbers": set()}
    try:
        for n, i in enumerate(idxs, 1):
            job.current().check()
            raster.render(doc[i], dpi_used).save(tmp)
            page = det.read(tmp, i, float(dpi_used))
            # Before the write: an unknown label spelling must not reach the directory.
            _check_labels(page, pol.name or "the model declared", known, det.name)
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
            write_json(os.path.join(pagedir, f"{i:04d}.json"), page.to_json())
            ties += page.meta["rank_ties"]
            for lab, s in page.meta["best_rejected_by_class"].items():
                if s > rej_best.get(lab, 0.0):
                    rej_best[lab] = s
                    rej_pages[lab] = i          # where it was best
            for b in page.blocks:
                counts[b.label] = counts.get(b.label, 0) + 1
                artefacts += b.label in arte
            if n % 10 == 0 or n == len(idxs):
                log(f"  {n}/{len(idxs)} pages, boxes {sum(counts.values())}",
                    page=i, n=n, of=len(idxs), boxes=sum(counts.values()))
    finally:
        doc.close()
        if os.path.exists(tmp):
            os.unlink(tmp)

    took = time.time() - t0
    total = sum(counts.values())
    mode = "/".join(sorted(str(m) for m in pipe["modes"]))
    had_pipeline = bool(pipe["page_count"])
    # Set only when the pipeline ran; with it off every number is the model's anyway.
    box_stage = (f"after the docling pipeline {mode}" if had_pipeline
                  else "the model's own, there was no pipeline over boxes")
    log(f"boxes {total} on {len(idxs)} pages "
        f"({total/len(idxs):.1f} per page), artefacts {artefacts}, "
        f"rank ties {ties}, {took:.1f} s ({took/len(idxs):.2f} s/page)"
        + (f" -- every box number is AFTER the docling pipeline {mode}"
           if had_pipeline else ""))

    # What the pipeline removed is a quantity of its own, not a correction to "accepted".
    if mute_pages:
        log(f"WARNING: on {mute_pages} pages of {len(idxs)} adapter "
            f"{det.name} did not say 'boxes accepted' -- how many the model "
            f"itself gave cannot be checked; the sums below are incomplete "
            f"by those pages")
    if had_pipeline:
        removed = pipe["before"] - pipe["after"]
        share = 100.0 * removed / pipe["before"] if pipe["before"] else 0.0
        log(f"docling pipeline {mode}: the model gave {pipe['before']} "
            f"boxes, it removed {removed} ({share:.1f}%), {pipe['after']} went "
            f"into the book, {pipe['children']} into children, "
            f"{pipe['reordered']} permuted, "
            f"{pipe['page_count']} pages of {len(idxs)} through it")
        # Said out loud: "table accepted 0" with the knob on may mean it was removed.
        log(f"    what the pipeline removed is NOT broken down by label: "
            f"the adapter gives 'boxes before' as a total only "
            f"({pipe['before']}), never by class "
            f"(layout/adapters/docling.py, pipe_meta)")
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
        # A zero from a check, not the silence of a step, with the page count beside it.
        log(f"the vendor pipeline did not touch the boxes: 0 pages of "
            f"{len(idxs)} through it, 'accepted' below is the model's own")
        if not mute_pages and model_boxes != total:
            log(f"WARNING: the model gave {model_boxes} boxes and the "
                f"pages hold {total} with no pipeline at all: someone "
                f"unnamed is correcting the boxes")

    # A quantity, not "verified"; foreign is always 0 because `_check_labels` drops it.
    log(f"label spellings checked against vocabulary "
        f"{pol.name or 'the model declared'}: "
        f"{len(spellings)} of {len(known)} known, foreign 0 -- else the run "
        f"would have fallen")

    # By class, accepted and best rejected: without the second, "table 0" reads as
    # "there are no tables" where it may mean "0.03 below the threshold".
    # Every artefact label is shown even at zero; the rest of the rejected go in one line.
    shown = sorted(set(counts) | set(arte),
                   key=lambda l: (-counts.get(l, 0), l))
    # The stages are named because there are two, and the two numbers must not be added.
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
        raise Refusal(
            f"not one box on {len(idxs)} pages -- a refusal, not an empty "
            f"book. Threshold LAYOUT_SCORE_THRESHOLD="
            f"{knobs.knob('LAYOUT_SCORE_THRESHOLD')}, weights {det.where()}. "
            f"Best rejected: {rej_best or 'nothing was rejected at all'}")

    fp = det.fingerprint()
    # The identity comes from the snapshot's own knobs block: a second walk is a second list.
    knob_block = _knobs_snapshot(roles)
    gen_null = {"temperature": None, "max_tokens": None, "top_p": None,
                "seed": None}
    # A hybrid's pages are a read run with its own boxes: no detect run stands
    # behind them, and its prompts and generation are the model's, out of the
    # fingerprint it declared.
    own = ({"layout": "own", "detection": None,
            "kinds": list(spoken.get("kinds") or [])} if hybrid else {})
    snap = {
        # The date beside the number: a measurement must say what it was applied to.
        "when": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "knobs": knob_block,
        # A summary in the same numbers as the log: what was actually acting here.
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
        # What makes this run this experiment: a resume told from a collision.
        "identity": stamp.identity(fp, stamp.knob_values(
            {"knobs": knob_block, "served": spoken})),
        # The describe a served model answered with, whole: its knobs are in
        # the identity above, its code and commit stand where the adapter's
        # source would for `books replay --check`.
        "served": spoken,
        **own,
        "label": det.label(),
        "source": {"path": pdf, "sha256": _sha256(pdf)},
        # Both files that decide the result are hashed, the adapter's being the active one.
        "adapter": {"name": det.name,
                    "module": type(det).__module__,
                    "sha256": _sha256(sys.modules[type(det).__module__].__file__),
                    # This file, asked of itself: a literal path breaks when the module moves.
                    "sha256_command": _sha256(os.path.abspath(__file__))},
        "policy": pol.snapshot(),
        "prompts": (fp.get("prompts") or {}) if hybrid else {},
        "generation": ({**gen_null, **(fp.get("generation") or {})}
                       if hybrid else gen_null),
        "packages": _packages(),
        "weights": {"vl": fp["sha256_weights"] if hybrid else None,
                    "layout": fp["sha256_weights"]},
        "fingerprint": fp,
        "summary": {"page_count": len(idxs), "box_count": total,
                 "artifacts": artefacts, "rank_ties": ties,
                 "seconds": round(took, 2), "by_label": counts,
                 "best_rejected": rej_best,
                 "pages_with_rejected": rej_pages,
                 # Whose stage this is, beside the numbers and not only in the log.
                 "stages": {
                     "box_counts_stage":
                         box_stage,
                     "best_rejected_stage":
                         "by the model threshold, BEFORE the vendor pipeline",
                     # An incomplete sum is not a quantity: `null` beside the silent pages.
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
                         # A value, not a gap: "boxes before" comes as a total only.
                         "removed_by_label": None,
                         "why_removed_by_label_empty":
                             ("the adapter gives 'boxes before' as one "
                              "number per page; by class there are none -- "
                              "see pipe_meta in layout/adapters/docling.py"),
                         "numbers_never_given":
                             sorted(pipe["missing_numbers"]),
                     },
                 }},
        # The line must be runnable: file names carry spaces, so every argument is quoted.
        "repeat_command": " ".join(shlex.quote(a) for a in
                           ["books", "hybrid" if hybrid else "detect", pdf,
                            "--out", outdir]
                           + (["--pages", str(pages_spec)] if pages_spec else [])),
    }
    write_json(os.path.join(outdir, "run.json"), snap, indent=1)
    log(f"snapshot: {os.path.join(outdir, 'run.json')}")
    return outdir
