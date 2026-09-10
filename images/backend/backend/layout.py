"""`books detect` -- first-level contours, locally and for free"""

import os
import shlex
import sys
import tempfile
import time
from backend.served import Served
from backend import store as book
from backend import knobs
from backend import identity as stamp
from backend.errors import Refusal
from backend import raster
from backend.log import log
from backend.page import write_json
from backend import job

_sha256 = stamp.sha256
ADAPTERS = ("served",)


def _check_labels(page, pol, known, adapter):
    bad = sorted({b.label for b in page.blocks if b.label not in known})
    if not bad:
        return
    raise Refusal(
        f"page {page.index}: block labels {bad} are not from the policy {pol} (adapter {adapter}; the vocabulary knows {len(known)} spellings: {sorted(known)}). Counting cannot go on: artefact labels come from that same vocabulary, and a block with a foreign spelling would give 'artefacts 0' -- a zero from not understanding, dressed as a measurement. Fix the label translation in the adapter, or the mapping itself, but not this check."
    )


def _adapter():
    return Served()


COMMAND_KNOBS = ("PAGE_DPI",)


def _knob_roles(det):
    try:
        mine = tuple(det.knobs_read())
    except NotImplementedError:
        raise Refusal(
            f"adapter {det.name} did not declare which knobs it reads (layout/base.py, knobs_read). An empty tuple is a lawful answer, silence is not: a silent adapter would take the snapshot back to what this declaration exists against."
        ) from None
    unknown = [n for n in mine if n not in knobs.KNOB]
    if unknown:
        raise Refusal(
            f"adapter {det.name} declared knobs the registry does not hold: {unknown}. Either a typo, or the environment is read past core/knobs.py -- both troubles are silent."
        )
    roles = {}
    for n in knobs.names():
        if n in mine:
            roles[n] = f"adapter {det.name}"
        elif n in COMMAND_KNOBS:
            roles[n] = "the books detect command"
        else:
            roles[n] = None
    return roles


_knobs_snapshot = knobs.snapshot_with_readers


def _identity(det, roles):
    return stamp.identity(
        det.fingerprint(),
        stamp.knob_values({"knobs": _knobs_snapshot(roles), "served": det.served()}),
    )


_commit = stamp.commit


def _packages():
    return stamp.packages(stamp.DETECT_PACKAGES)


def parse_pages(spec, total):
    if not spec:
        return list(range(total))
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
                    f"in --pages {spec} the range {part} was not parsed. Expected 7-9, counting from one."
                )
            if not rng:
                raise Refusal(f"range {part} is empty: the end is before the start")
            want.extend(rng)
        else:
            try:
                want.append(int(part))
            except ValueError:
                raise Refusal(
                    f"in --pages {spec} the piece {part} is not a page number. Expected 1,4,7-9 or 1 4 7-9, from one."
                )
    bad = [p for p in want if not 1 <= p <= total]
    if bad:
        raise Refusal(f"the book has {total} pages, {bad} were asked")
    if not want:
        raise Refusal(f"the page set {spec} is empty -- nothing to count")
    return [p - 1 for p in sorted(set(want))]


def run(pdf, outdir, pages_spec=None, det=None, hybrid=False):
    dpi_raw = knobs.knob("PAGE_DPI")
    dpi = float(dpi_raw)
    dpi_used = int(dpi)
    if dpi_used != dpi:
        log(
            f"WARNING: PAGE_DPI={dpi_raw} truncated to {dpi_used} -- the raster is drawn at a whole number of dots per inch"
        )
    pdf = os.path.abspath(pdf)
    outdir = os.path.abspath(outdir)
    pagedir = os.path.join(outdir, "pages")
    if not os.path.exists(pdf):
        raise Refusal(f"no file {pdf}")
    if os.path.isdir(pdf):
        raise Refusal(f"{pdf} is a directory, one book's PDF is expected")
    det = det if det is not None else _adapter()
    spoken = det.served()
    if hybrid and (not (spoken and spoken.get("kind") == "hybrid")):
        raise Refusal(
            f"a hybrid run needs a served hybrid model, and {det.where()} is "
            + (f"a {spoken.get('kind')} model" if spoken else f"the in-process adapter {det.name}")
            + ". Boxes and text in one call come from a model that declared both; `books detect` runs the rest."
        )
    book.guard_identity(
        outdir, _identity(det, _knob_roles(det)), pages_spec or "", f"this {det.label()} run"
    )
    pol = det.policy()
    pol.check(det.labels)
    arte = pol.artefacts()
    known = set(pol.labels)
    for line in det.threshold_drift():
        log(f"WARNING: the threshold set is not the native one -- {line}")
    roles = _knob_roles(det)
    given = list(knobs.passthrough())
    dead = [n for n in given if roles[n] is None]
    log(f"knobs set from outside {len(given)}" + (f": {', '.join(given)}" if given else ""))
    if dead:
        log(
            f"WARNING: of those, {len(dead)} are read neither by adapter {det.name} nor by the command itself: {', '.join(dead)} -- the value set does NOT affect this run, and the snapshot marks it for_this_run: false"
        )
    log(f"detector {det.name}: {det.fingerprint().get('model')} from {det.where()}")
    fp_in = det.fingerprint().get("input") or {}
    log(
        f"model input {fp_in.get('width')}x{fp_in.get('height')} (WxH): "
        + ", ".join((f"{k}={v}" for k, v in fp_in.items() if k not in ("width", "height")))
    )
    log(
        f"vocabulary {pol.name or 'the model declared'}, labels {len(det.labels)}, native threshold {det.fingerprint().get('native_threshold')}"
    )
    try:
        doc = raster.open_pdf(pdf)
        pages_total = doc.page_count
    except Exception as e:
        raise Refusal(f"{pdf} does not open as a PDF: {type(e).__name__}: {e}") from None
    if not pages_total:
        raise Refusal(f"{pdf} opened, but has zero pages -- nothing to count")
    idxs = parse_pages(pages_spec, pages_total)
    os.makedirs(pagedir, exist_ok=True)
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
        log(
            "the previous run.json removed BEFORE its pages: a run that dies here leaves no identity, not a stale one"
        )
    log(
        f"{os.path.basename(pdf)}: pages in the file {doc.page_count}, counting {len(idxs)} at {dpi_used} dpi"
    )
    t0 = time.time()
    fd, tmp = tempfile.mkstemp(prefix=".page.", suffix=".png", dir=outdir)
    os.close(fd)
    counts, rej_best, rej_pages = ({}, {}, {})
    artefacts = ties = 0
    spellings = set()
    model_boxes = mute_pages = 0
    pipe = {
        "page_count": 0,
        "before": 0,
        "after": 0,
        "children": 0,
        "reordered": 0,
        "modes": set(),
        "missing_numbers": set(),
    }
    try:
        for n, i in enumerate(idxs, 1):
            job.current().check()
            raster.render(doc[i], dpi_used).save(tmp)
            page = det.read(tmp, i, float(dpi_used))
            _check_labels(page, pol.name or "the model declared", known, det.name)
            spellings.update(b.label for b in page.blocks)
            mk = page.meta.get("boxes_accepted")
            if mk is None:
                mute_pages += 1
            else:
                model_boxes += int(mk)
            pm = page.meta.get("docling_pipeline")
            if pm:
                pipe["page_count"] += 1
                pipe["modes"].add(pm.get("mode"))
                for key, margin in (
                    ("boxes_before", "before"),
                    ("boxes_after", "after"),
                    ("moved_to_children", "children"),
                    ("boxes_reordered", "reordered"),
                ):
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
                    rej_pages[lab] = i
            for b in page.blocks:
                counts[b.label] = counts.get(b.label, 0) + 1
                artefacts += b.label in arte
            if n % 10 == 0 or n == len(idxs):
                log(
                    f"  {n}/{len(idxs)} pages, boxes {sum(counts.values())}",
                    page=i,
                    n=n,
                    of=len(idxs),
                    boxes=sum(counts.values()),
                )
    finally:
        doc.close()
        if os.path.exists(tmp):
            os.unlink(tmp)
    took = time.time() - t0
    total = sum(counts.values())
    mode = "/".join(sorted(str(m) for m in pipe["modes"]))
    had_pipeline = bool(pipe["page_count"])
    box_stage = (
        f"after the docling pipeline {mode}"
        if had_pipeline
        else "the model's own, there was no pipeline over boxes"
    )
    log(
        f"boxes {total} on {len(idxs)} pages ({total / len(idxs):.1f} per page), artefacts {artefacts}, rank ties {ties}, {took:.1f} s ({took / len(idxs):.2f} s/page)"
        + (f" -- every box number is AFTER the docling pipeline {mode}" if had_pipeline else "")
    )
    if mute_pages:
        log(
            f"WARNING: on {mute_pages} pages of {len(idxs)} adapter {det.name} did not say 'boxes accepted' -- how many the model itself gave cannot be checked; the sums below are incomplete by those pages"
        )
    if had_pipeline:
        removed = pipe["before"] - pipe["after"]
        share = 100.0 * removed / pipe["before"] if pipe["before"] else 0.0
        log(
            f"docling pipeline {mode}: the model gave {pipe['before']} boxes, it removed {removed} ({share:.1f}%), {pipe['after']} went into the book, {pipe['children']} into children, {pipe['reordered']} permuted, {pipe['page_count']} pages of {len(idxs)} through it"
        )
        log(
            f"    what the pipeline removed is NOT broken down by label: the adapter gives 'boxes before' as a total only ({pipe['before']}), never by class (layout/adapters/docling.py, pipe_meta)"
        )
        if pipe["missing_numbers"]:
            log(
                f"WARNING: the pipeline gave no numbers {sorted(pipe['missing_numbers'])} -- the sums above are incomplete by as much"
            )
        if pipe["page_count"] != len(idxs):
            log(
                f"WARNING: {pipe['page_count']} pages of {len(idxs)} went through the pipeline -- the stage numbers are summed over different samples"
            )
        if pipe["after"] != total:
            log(
                f"WARNING: the pipeline reported {pipe['after']} boxes after itself, and the pages hold {total}: a difference of {abs(pipe['after'] - total)}"
            )
        if not mute_pages and pipe["before"] != model_boxes:
            log(
                f"WARNING: the pipeline took {pipe['before']} boxes and the model gave {model_boxes}: a difference of {abs(pipe['before'] - model_boxes)} boxes lost between the stages"
            )
    else:
        log(
            f"the vendor pipeline did not touch the boxes: 0 pages of {len(idxs)} through it, 'accepted' below is the model's own"
        )
        if not mute_pages and model_boxes != total:
            log(
                f"WARNING: the model gave {model_boxes} boxes and the pages hold {total} with no pipeline at all: someone unnamed is correcting the boxes"
            )
    log(
        f"label spellings checked against vocabulary {pol.name or 'the model declared'}: {len(spellings)} of {len(known)} known, foreign 0 -- else the run would have fallen"
    )
    shown = sorted(set(counts) | set(arte), key=lambda l: (-counts.get(l, 0), l))
    if had_pipeline:
        log(
            f"    by class, TWO STAGES: 'accepted' is {box_stage}; 'best rejected' is the model's threshold BEFORE it. Do not add them."
        )
    else:
        log(
            f"    by class, both numbers from the model ({box_stage}): 'accepted' is boxes above the threshold, 'best rejected' the best one below it"
        )
    mark = " (after the pipeline)" if had_pipeline else ""
    answer_mark = ", BEFORE the pipeline" if had_pipeline else ""
    for lab in shown:
        line = f"    {lab:18s} accepted{mark} {counts.get(lab, 0):5d}"
        if lab in rej_best:
            line += f", best rejected {rej_best[lab]:.3f} (p. {rej_pages[lab]}{answer_mark})"
        log(line)
    rest = {l: v for l, v in rej_best.items() if l not in shown}
    if rest:
        top = max(rest.items(), key=lambda kv: kv[1])
        log(
            f"    other classes rejected {len(rest)}, highest of all {top[0]} {top[1]:.3f}"
            + (" (all by the model's threshold, BEFORE the pipeline)" if had_pipeline else "")
        )
    if total == 0:
        raise Refusal(
            f"not one box on {len(idxs)} pages -- a refusal, not an empty book. Threshold LAYOUT_SCORE_THRESHOLD={knobs.knob('LAYOUT_SCORE_THRESHOLD')}, weights {det.where()}. Best rejected: {rej_best or 'nothing was rejected at all'}"
        )
    fp = det.fingerprint()
    knob_block = _knobs_snapshot(roles)
    gen_null = {"temperature": None, "max_tokens": None, "top_p": None, "seed": None}
    own = (
        {"layout": "own", "detection": None, "kinds": list(spoken.get("kinds") or [])}
        if hybrid
        else {}
    )
    snap = {
        "when": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "knobs": knob_block,
        "run_knobs": {
            "read_by_active_adapter": [
                n for n in knobs.names() if roles[n] and n not in COMMAND_KNOBS
            ],
            "read_by_detect_command": [n for n in knobs.names() if roles[n] and n in COMMAND_KNOBS],
            "not_for_this_run": [n for n in knobs.names() if roles[n] is None],
            "set_externally": given,
            "set_externally_unread": dead,
        },
        "raster": {"scale": dpi_used / 72.0, "dpi": float(dpi_used), "page_dpi_as_given": dpi_raw},
        "args": {"pdf": pdf, "pages": pages_spec, "out": outdir},
        "commit": _commit(),
        "identity": stamp.identity(fp, stamp.knob_values({"knobs": knob_block, "served": spoken})),
        "served": spoken,
        **own,
        "label": det.label(),
        "source": {"path": pdf, "sha256": _sha256(pdf)},
        "adapter": {
            "name": det.name,
            "module": type(det).__module__,
            "sha256": _sha256(sys.modules[type(det).__module__].__file__),
            "sha256_command": _sha256(os.path.abspath(__file__)),
        },
        "policy": pol.snapshot(),
        "prompts": fp.get("prompts") or {} if hybrid else {},
        "generation": {**gen_null, **(fp.get("generation") or {})} if hybrid else gen_null,
        "packages": _packages(),
        "weights": {"vl": fp["sha256_weights"] if hybrid else None, "layout": fp["sha256_weights"]},
        "fingerprint": fp,
        "summary": {
            "page_count": len(idxs),
            "box_count": total,
            "artifacts": artefacts,
            "rank_ties": ties,
            "seconds": round(took, 2),
            "by_label": counts,
            "best_rejected": rej_best,
            "pages_with_rejected": rej_pages,
            "stages": {
                "box_counts_stage": box_stage,
                "best_rejected_stage": "by the model threshold, BEFORE the vendor pipeline",
                "boxes_from_model": None if mute_pages else model_boxes,
                "pages_without_boxes_accepted": mute_pages,
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
                    "removed_by_label": None,
                    "why_removed_by_label_empty": "the adapter gives 'boxes before' as one number per page; by class there are none -- see pipe_meta in layout/adapters/docling.py",
                    "numbers_never_given": sorted(pipe["missing_numbers"]),
                },
            },
        },
        "repeat_command": " ".join(
            shlex.quote(a)
            for a in ["books", "hybrid" if hybrid else "detect", pdf, "--out", outdir]
            + (["--pages", str(pages_spec)] if pages_spec else [])
        ),
    }
    write_json(os.path.join(outdir, "run.json"), snap, indent=1)
    log(f"snapshot: {os.path.join(outdir, 'run.json')}")
    return outdir
