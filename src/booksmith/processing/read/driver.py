"""`books read` -- level two: walk the book and fill in block content.

The product is the same `pages/*.json` as detection -- same boxes, labels and
order, with `content` and `kind` filled in -- so html, text, score, fitness,
overlay and replay read it unchanged. `content` carries the model's bytes and
nothing more: seconds, tokens, finish reason, kind guess and delivery refusal go
to `answers/*.json`, tied to the block by its anchor.

The zeros are counted apart -- not asked, delivery failed, model silent, hit the
ceiling, read -- because merged they all print "read 0".
"""
import glob
import json
import os
import re
import shlex
import sys
import time
from concurrent.futures import ThreadPoolExecutor

from booksmith.processing.read import Ask, Reader, Transport
from booksmith.core import otsl, policy
from booksmith.core import raster as crop
from booksmith.core.page import Page
from booksmith.core import book, job, knobs, page, stamp
from booksmith.core.log import log
from booksmith.core.errors import Refusal

# The known readers; a new one is a line here and one file beside the model.
READERS = ("paddleocr-vl",)




def build_reader(policy_name: str) -> Reader:
    name = knobs.knob("VLM_READER")
    if name == "paddleocr-vl":
        from booksmith.processing.read.readers.paddleocr_vl import PaddleOcrVl
        return PaddleOcrVl(policy_name)
    raise Refusal(
        f"VLM_READER={name!r}: I know only {READERS}. A silent fallback to "
        f"whichever comes first would make a typo in the reader's name count "
        f"as a successful run, with the snapshot naming the wrong model.")


def _sniff(text: str) -> str:
    """A guess at the kind of answer. Lives beside it and decides nothing.

    The prompt declares the kind, not the answer; where guess and declaration
    disagree that is a counter (`kind_not_as_promised`), which is the sign the
    declaration wants changing -- never a fix applied to the answer.
    """
    if not text:
        return "empty"
    t = text.strip()
    if otsl.looks_like(t):
        return "otsl"
    if "<table" in t.lower() or "<td" in t.lower():
        return "html"
    # Wide on purpose: a narrow net drops plausible formulas into "text".
    if (t.startswith("$") or re.search(r"\\[A-Za-z]{2,}", t)
            or re.search(r"[_^]\{", t) or re.search(r"[A-Za-z0-9)\]]\^[A-Za-z0-9{]", t)):
        return "latex"
    return "text"


def crop_dpi_for(box, page_dpi: float, native: float | None,
                 window, sheet=None) -> tuple[float, str]:
    """What resolution to cut this block at, and why that one.

    A rule, not a number: as much as the scan has (`native`), no more than the
    model eats (`window`), and never above the scan's own grid -- a block below
    the model's lower bound becomes the number `below_model_min` instead.
    """
    base = float(native or page_dpi)
    if not window:
        return base, "native_scan_dpi_no_model_bounds"
    lo, hi = window
    # Size by the intersection with the sheet -- that is what `crop.cut` cuts.
    x0, y0, x1, y1 = box
    if sheet is not None:
        sx0, sy0, sx1, sy1 = sheet
        x0, y0 = max(x0, sx0), max(y0, sy0)
        x1, y1 = min(x1, sx1), min(y1, sy1)
    w = (x1 - x0) / page_dpi                  # inches
    h = (y1 - y0) / page_dpi
    if w <= 0 or h <= 0:
        return base, "native_scan_dpi"
    at_base = w * base * h * base
    if at_base > hi:
        # Down to the model's upper bound: it discards the excess itself.
        return (hi / (w * h)) ** 0.5, "downscaled_to_model_max"
    if at_base < lo:
        return base, "below_model_min"
    return base, "native_scan_dpi"


def _gen_params() -> dict:
    """Generation parameters. They ride into the snapshot whole, as
    `generation`."""
    return {"temperature": knobs.number("VLM_TEMPERATURE"),
            "max_tokens": knobs.number("VLM_MAX_TOKENS", kind=int),
            "top_p": knobs.number("VLM_TOP_P"),
            "seed": knobs.number("VLM_SEED", kind=int, negative=True)}


def _detect_facts(detect_dir: str) -> dict:
    p = os.path.join(detect_dir, "run.json")
    if not os.path.exists(p):
        raise Refusal(
            f"no run.json in {detect_dir}: this is not a `books detect` "
            f"directory. Reading without the detection snapshot knows neither "
            f"the book nor the dpi the boxes were measured at, and would cut "
            f"the crops at the wrong coordinates.")
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def read_identity(reader: Reader, transport) -> tuple[str, dict]:
    """(identity, the knob block it came from). One source for the guard and for
    the snapshot, so the number that refuses a run and the number recorded in it
    cannot differ."""
    roles = {**{n: "reading adapter" for n in reader.knobs_read()},
             **{n: "transport" for n in (transport.knobs_read()
                                         if transport is not None else ())}}
    block = _knobs_snapshot(roles)
    return stamp.identity(reader.fingerprint(),
                          stamp.knob_values({"knobs": block})), block


def read_book(detect_dir: str, out_dir: str, reader: Reader,
              transport: Transport, resume: bool = True,
              pages_want=None, pdf: str | None = None,
              preview: bool = False) -> dict:
    """Walk the book and fill in block content. Returns quantities.

    `preview` cuts every crop and builds every question as the paid run does,
    sends none, writes the list to `would_ask.json`, and cannot resume: the
    answers a resume reuses live in a directory a preview may not write to.
    `pdf` is where the book lies now; its sha256 is checked whatever the path.
    """

    if preview and resume:
        raise Refusal(
            "a preview cannot resume: the answers a resuming `books read` "
            "would reuse live in ITS directory, and a preview may not write "
            "there. Pass resume=False and read `would_ask.json` as a fresh "
            "run -- on a book already half read, that is more questions than "
            "the next paid run would ask.")
    if not preview:
        # Would this overwrite another experiment, asked before the first cent.
        ident, _ = read_identity(reader, transport)
        book.guard_identity(out_dir, ident,
                            "" if pages_want is None else "a page selection",
                            f"this {reader.label()} reading")
    facts = _detect_facts(detect_dir)
    pdf = pdf or facts["source"]["path"]
    if not os.path.exists(pdf):
        raise Refusal(f"no source {pdf}, the one the detection snapshot names")
    got = stamp.sha256(pdf)
    if got != facts["source"]["sha256"]:
        raise Refusal(
            f"{pdf}: sha256 {got[:12]} against "
            f"{facts['source']['sha256'][:12]} in the detection snapshot. The "
            f"boxes were measured on ANOTHER file; the crops would be cut at "
            f"the wrong coordinates and the answer would look like reading.")
    page_dpi = float(facts["raster"]["dpi"])

    files = sorted(glob.glob(os.path.join(detect_dir, "pages", "*.json")))
    if not files:
        raise Refusal(f"no pages in {detect_dir}: run books detect first")

    _pages_dir = os.path.join(out_dir, "pages")
    if preview:
        # A preview may not overwrite the crops a paid run's answers/ describes.
        for tell in ("answers", "pages", "read_with.json", "run.json"):
            if os.path.exists(os.path.join(out_dir, tell)):
                raise Refusal(
                    f"{out_dir} holds `{tell}`: this is a `books read` "
                    f"directory, not a place for a preview. The crops there "
                    f"are what was PAID for -- `answers/` describes them by "
                    f"name, dpi and size -- and a preview would overwrite "
                    f"them with crops nothing was asked about. Give --out "
                    f"somewhere else.")
    else:
        # A page the detection does not have would ride into the book as one of
        # its own, and into the measurement with it.
        if os.path.isdir(_pages_dir):
            mine_ = {os.path.basename(f) for f in files}
            alien = sorted(set(os.listdir(_pages_dir)) - mine_)
            if alien:
                raise Refusal(
                    f"{_pages_dir} holds pages the detection does not have: "
                    f"{alien[:5]}{'...' if len(alien) > 5 else ''} "
                    f"({len(alien)} of them). This is a directory from another "
                    f"book or another page set; they would travel into the book "
                    f"and into the measurement as part of this one. Remove them "
                    f"or choose an empty --out.")
        os.makedirs(_pages_dir, exist_ok=True)
        os.makedirs(os.path.join(out_dir, "answers"), exist_ok=True)
    crops_dir = os.path.join(out_dir, "crops")
    os.makedirs(crops_dir, exist_ok=True)

    routes = reader.routes()
    would, not_asked, failed = [], [], []
    # Route completeness BEFORE the first cent and the first crop.
    labels = set()
    pages = []
    for fp in files:
        with open(fp, encoding="utf-8") as f:
            pg = Page.from_json(json.load(f))
        if pages_want is not None and pg.index not in pages_want:
            continue
        pages.append((fp, pg))
        labels |= {b.label for b in pg.blocks}
    if not pages:
        raise Refusal("not one page to read: the --pages set is empty")
    reader.cover(labels)

    params = _gen_params()
    window = reader.pixels()
    same_setup = True
    # Resuming compares what we read with, not merely that a file exists.
    # A preview writes none of it: it has no transport that ever answered.
    if not preview:
        setup = {"reader": reader.fingerprint(), "generation": params,
                 "transport": {k: v for k, v in transport.fingerprint().items()
                               # the address does not decide the answer, the
                               # model name does
                               if k in ("transport", "model_asked")},
                 # The boxes the answers are about: a resume over another
                 # detection's answers would reuse them by anchor alone.
                 "detection": facts.get("identity")}
        setup_path = os.path.join(out_dir, "read_with.json")
        if resume and os.path.exists(setup_path):
            with open(setup_path, encoding="utf-8") as f:
                was = json.load(f)
            same_setup = was == setup
            if not same_setup:
                diff = [k for k in setup if was.get(k) != setup[k]]
                log(f"READ WITH SOMETHING ELSE: {diff} differ -- resuming is "
                    f"not allowed, asking everything again. Otherwise the "
                    f"snapshot would declare new values in force over old "
                    f"answers.")
        page.write_json(setup_path, setup, indent=1)
    doc = crop.open_pdf(pdf)
    # Own resolution per page, memoised: sheet sizes differ inside one book.
    native_of = {}

    def _native(i):
        if i not in native_of:
            native_of[i] = crop.native_dpi(doc[i])
        return native_of[i]

    native = _native(0)
    cut_dpi = {}
    tally = {"page_count": len(pages), "block_count": 0, "asked": 0,
             "not_asked": 0, "read": 0, "model_silent": 0,
             "delivery_failed": 0, "hit_ceiling": 0,
             "kind_not_as_promised": 0, "reused_from_previous_run": 0,
             # without it an answer under a foreign anchor leaves no record
             "answer_wrong_anchor": 0, "asked_no_answer": 0,
             "crop_failed": 0, "crop_dpi_reason_counts": {},
             "native_book_dpi": native,
             "model_window": list(window) if window else None,
             "chars": 0, "compute_seconds": 0.0, "tokens": 0}
    bad_crops = []
    by_kind = {}
    worst = []

    for n, (fp, pg) in enumerate(pages, 1):
        job.current().check()
        tag = f"p{pg.index:04d}"
        ans_path = os.path.join(out_dir, "answers", f"{tag}.json")
        old = {}
        if resume and os.path.exists(ans_path) and same_setup:
            with open(ans_path, encoding="utf-8") as f:
                old = {a["anchor"]: a for a in json.load(f).get("answers", [])}

        asks, silent, nocrop, cut_info = [], {}, {}, {}
        for b in pg.blocks:
            tally["block_count"] += 1
            anchor = page.anchor(pg.index, b.block_id)
            rt = routes[b.label]
            if not rt.asked():
                tally["not_asked"] += 1
                silent[anchor] = rt.why
                continue
            if anchor in old and old[anchor].get("text") is not None:
                tally["reused_from_previous_run"] += 1
                continue
            rel = os.path.join(crops_dir, f"{anchor}.png")
            # The sheet in pixels of the same raster the boxes live in.
            _r = doc[pg.index].rect
            sheet = (0.0, 0.0, _r.width * page_dpi / 72.0,
                     _r.height * page_dpi / 72.0)
            cdpi, why = crop_dpi_for(b.box, page_dpi, _native(pg.index),
                                     window, sheet=sheet)
            cut_dpi[anchor] = (cdpi, why)
            tally["crop_dpi_reason_counts"][why] = (
                tally["crop_dpi_reason_counts"].get(why, 0) + 1)
            try:
                # crop.cut reports the dpi it cut at and clipped_by_sheet, and
                # `answers/` keeps both: a crop bitten off by the sheet edge is
                # a fact about what the model was sent.
                cut_info[anchor] = crop.cut(doc, pg.index, b.box, page_dpi,
                                            rel, dpi=cdpi)
            except (ValueError, IndexError, RuntimeError) as e:
                # A degenerate or off-sheet box is the model's defect, and it
                # becomes a quantity: the run does not die mid-book over it.
                tally["crop_failed"] += 1
                bad_crops.append(f"{anchor}: {type(e).__name__}: {e}")
                nocrop[anchor] = f"{type(e).__name__}: {e}"
                continue
            asks.append(Ask(anchor=anchor, image=rel, prompt=rt.prompt,
                            kind=rt.kind, label=b.label, params=dict(params)))

        if preview:
            for a in asks:
                info = cut_info.get(a.anchor) or {}
                would.append({"anchor": a.anchor, "label": a.label,
                              "image": os.path.relpath(a.image, out_dir),
                              "prompt": a.prompt, "kind": a.kind,
                              # The dpi it was cut at, with the rule's fraction
                              # beside it, not instead: `crop.cut` renders at
                              # `int(dpi)`. The same two keys the paid run writes.
                              "crop_dpi": info.get("dpi", cut_dpi[a.anchor][0]),
                              "crop_dpi_by_rule": round(cut_dpi[a.anchor][0], 2),
                              "crop_dpi_reason": cut_dpi[a.anchor][1],
                              **{k: info[k] for k in ("width", "height",
                                                      "clipped_by_sheet")
                                 if k in info}})
            # Every block gets a record here as in a paid run: a preview must
            # say what it would skip, not only what it would ask.
            for anchor, why in sorted(silent.items()):
                not_asked.append({"anchor": anchor, "not_asked": why})
            for anchor, why in sorted(nocrop.items()):
                failed.append({"anchor": anchor, "crop_failed": why})
            tally["would_ask"] = tally.get("would_ask", 0) + len(asks)
            log(f"page {pg.index}: would ask {len(asks)}, not asked "
                f"{len(silent)}, crop failed {len(nocrop)}")
            continue
        asked_now = {a.anchor for a in asks}
        said = {}
        if asks:
            n = max(1, knobs.number("VLM_CONCURRENCY", kind=int))
            want = {a.anchor for a in asks}
            with ThreadPoolExecutor(max_workers=n) as pool:
                for s in pool.map(transport.send, asks):
                    if s.anchor not in want:
                        tally["answer_wrong_anchor"] += 1
                        continue
                    said[s.anchor] = s

        # Block order is the original one: under concurrency answers arrive
        # shuffled, and filing by arrival would reorder the book.
        answers = []
        for b in pg.blocks:
            anchor = page.anchor(pg.index, b.block_id)
            rt = routes[b.label]
            if anchor in silent:
                b.content, b.kind = None, "none"
                answers.append({"anchor": anchor, "not_asked": silent[anchor]})
                continue
            if anchor in nocrop:
                # Not asked -- there was nothing to cut; not "asked, no answer".
                b.content, b.kind = None, "none"
                answers.append({"anchor": anchor,
                                "crop_failed": nocrop[anchor]})
                continue
            if anchor in old and old[anchor].get("text") is not None:
                rec = old[anchor]
            else:
                s = said.get(anchor)
                if s is None:
                    # Asked, and nothing came under this anchor: every block
                    # leaves a record in `answers/`.
                    tally["asked_no_answer"] += 1
                    b.content, b.kind = None, "none"
                    answers.append({"anchor": anchor,
                                    "trouble": "asked, and no answer came "
                                               "under this anchor"})
                    continue
                rec = s.to_json()
                rec["label"] = b.label
                if anchor in cut_dpi:
                    # The journal's dpi is the one it was cut at; the rule's
                    # fraction stands beside it under its own name.
                    info = cut_info.get(anchor) or {}
                    rec["observed"]["crop_dpi"] = info.get(
                        "dpi", cut_dpi[anchor][0])
                    rec["observed"]["crop_dpi_by_rule"] = round(
                        cut_dpi[anchor][0], 2)
                    rec["observed"]["crop_dpi_reason"] = cut_dpi[anchor][1]
                    rec["observed"]["crop"] = info or None
                rec["observed"]["kind_sniffed"] = _sniff(s.text or "")
                # OTSL tornness beside the answer: it tells a table torn at the
                # ceiling from a whole one.
                if rt.kind == "otsl" and s.text:
                    g, t = otsl.parse(s.text)
                    rec["observed"]["otsl_grid"] = t
                tally["compute_seconds"] += s.took_s
                tally["tokens"] += s.tokens or 0
            answers.append(rec)

            txt = rec.get("text")
            if rec.get("error"):
                tally["delivery_failed"] += 1
                b.content, b.kind = None, "none"
            elif txt is None or not txt.strip():
                tally["model_silent"] += 1
                b.content, b.kind = None, "none"
            else:
                tally["read"] += 1
                tally["chars"] += len(txt)
                # The model's bytes, unedited; the kind is the prompt's.
                b.content, b.kind = txt, rt.kind
                by_kind[rt.kind] = by_kind.get(rt.kind, 0) + 1
                if rec["observed"].get("kind_sniffed") not in (rt.kind, None):
                    tally["kind_not_as_promised"] += 1
            if rec.get("outcome") == "length":
                tally["hit_ceiling"] += 1
                worst.append(anchor)
            # Only questions actually sent count as asked; a reused answer is
            # not one, and seconds per block divides by this number.
            if anchor in asked_now:
                tally["asked"] += 1

        pg.meta = dict(pg.meta or {})
        pg.meta["reading"] = {"reader": reader.name, "transport": transport.name,
                             "asked": len(asks)}
        page.write_json(os.path.join(out_dir, "pages", os.path.basename(fp)),
                        pg.to_json(), indent=1)
        page.write_json(ans_path, {"page": pg.index, "answers": answers}, indent=1)
        got = sum(1 for a in answers if a.get('text'))
        log(f"p. {pg.index}: asked {len(asks)}, read {got}, "
            f"silences {sum(1 for a in answers if a.get('text') == '')}, "
            f"refusals {sum(1 for a in answers if a.get('error'))}",
            page=pg.index, n=n, of=len(pages), asked=len(asks), read=got)
    doc.close()

    tally["by_kind"] = by_kind
    tally["truncated_anchors"] = worst[:20]
    tally["crop_failures"] = bad_crops[:20]
    if preview:
        with open(os.path.join(out_dir, "would_ask.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"detect": os.path.abspath(detect_dir),
                       "reader": reader.name, "policy": reader.policy_name,
                       "generation": params, "asks": would,
                       "not_asked": not_asked, "crop_failed": failed},
                      f, ensure_ascii=False, indent=1)
        tally["preview"] = True
    return tally


def report(t: dict) -> None:
    """Quantities, not "done". The five zeros are printed apart."""
    log(f"pages {t['page_count']}, blocks {t['block_count']}: asked "
        f"{t['asked']}, not asked {t['not_asked']}")
    if t["reused_from_previous_run"]:
        log(f"  taken from a previous run {t['reused_from_previous_run']} "
            f"-- the model did NOT read these blocks now")
    log(f"read {t['read']}, chars {t['chars']}, by kind "
        f"{t['by_kind'] or '--'}")
    log(f"crop sharpness: the book's own "
        f"{t['native_book_dpi'] and round(t['native_book_dpi']) or '--'} dpi, "
        f"model window {t['model_window'] or 'not declared'}; "
        f"{t['crop_dpi_reason_counts'] or '--'}")
    # Printed always, zeros included: a line that vanishes at zero reads as
    # "this never happens".
    log(f"  model silent {t['model_silent']}, delivery failed "
        f"{t['delivery_failed']}, hit the ceiling {t['hit_ceiling']}, "
        f"answer past the anchor {t['answer_wrong_anchor']}, asked with no "
        f"answer {t['asked_no_answer']}")
    if t["crop_failed"]:
        log(f"  THE CROP FAILED on {t['crop_failed']} blocks -- the model's "
            f"box is degenerate or lies off the sheet. That is its defect, "
            f"not ours; the block stayed unread: "
            f"{'; '.join(t['crop_failures'][:3])}")
    if t["hit_ceiling"]:
        log(f"  CUT AT THE CEILING: {', '.join(t['truncated_anchors'])}"
            f"{'...' if t['hit_ceiling'] > 20 else ''} -- on a table this does "
            f"NOT look broken: the vendor's otsl_pad_to_sqr_v2 silently "
            f"shortens long rows, and a torn table comes back plausible. "
            f"Raise VLM_MAX_TOKENS or crop smaller")
    if t["kind_not_as_promised"]:
        log(f"  the answer's kind differs from the declared one on "
            f"{t['kind_not_as_promised']} blocks -- NOT a defect of the model "
            f"but a reason to revisit the declaration in the reader; the "
            f"guess lies beside it, in answers/")
    if not t["asked"]:
        log("ZERO BLOCKS ASKED -- not a success, an empty run")
    if t["compute_seconds"]:
        log(f"compute {t['compute_seconds']:.1f} s, tokens {t['tokens']}, "
            f"{t['compute_seconds'] / max(1, t['asked']):.2f} s per block")


def _repeat_line(detect_dir: str, out_dir: str, args: dict) -> str:
    """The repeat line: executable and complete.

    Without `--pages` and `--policy` it repeats a different run. Quoting is
    mandatory -- source names carry spaces and brackets, and an unquoted line
    describes a command rather than being one.
    """
    argv = ["books", "read", detect_dir, "--out", out_dir]
    if args.get("pages"):
        argv += ["--pages", str(args["pages"])]
    if args.get("policy"):
        argv += ["--policy", str(args["policy"])]
    return " ".join(shlex.quote(a) for a in argv)


def snapshot(detect_dir: str, out_dir: str, reader: Reader,
             transport: Transport, tally: dict, args: dict) -> str:
    """Input snapshot: the same fields as detection, and a non-empty
    `prompts`."""
    facts = _detect_facts(detect_dir)
    # One source: the identity that refuses a run and the one recorded are one.
    ident, knob_block = read_identity(reader, transport)
    snap = {
        "when": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "knobs": knob_block,
        "raster": facts["raster"],
        "args": args,
        "commit": stamp.commit(),
        # VLM_SEED is in the identity on purpose: two seeds are two experiments.
        "identity": ident,
        "label": reader.label(),
        # The same book as detection, hash checked before the work (read_book).
        "source": facts["source"],
        "detection": {"dir": os.path.abspath(detect_dir),
                     "commit": facts.get("commit"),
                     "adapter": facts.get("adapter"),
                     "sha256_snapshot": stamp.sha256(
                         os.path.join(detect_dir, "run.json"))},
        "adapter": {"name": reader.name,
                    "module": type(reader).__module__,
                    "sha256": stamp.sha256(
                        sys.modules[type(reader).__module__].__file__),
                    "sha256_command": stamp.sha256(os.path.abspath(__file__)),
                    # Our OTSL parser decides the numbers too: without its hash
                    # two runs with different parsers look identical.
                    "sha256_otsl_parser": stamp.sha256(otsl.__file__)},
        "policy": policy.snapshot(getattr(reader, "policy_name", None)),
        "prompts": reader.fingerprint().get("prompts", {}),
        "generation": _gen_params(),
        "packages": stamp.packages(stamp.READ_PACKAGES),
        "weights": {"vl": reader.fingerprint().get("weights"),
                 "layout": facts.get("weights", {}).get("layout")},
        # Unwrapped, where `core/replay.py` looks for its fields; the transport
        # keeps a field of its own rather than being folded in here.
        "fingerprint": reader.fingerprint(),
        "transport_fingerprint": transport.fingerprint(),
        "summary": tally,
        "repeat_command": _repeat_line(detect_dir, out_dir, args),
    }
    p = os.path.join(out_dir, "run.json")
    page.write_json(p, snap, indent=1)
    return p


def _knobs_snapshot(read_by_adapter) -> dict:
    """Knobs marked with who reads them. Shape shared with detection.

    The split is not decoration: a snapshot with every knob in one heap is
    complete and not in effect, and `books replay --check` approves it.
    """
    # CROP_DPI is absent because this path does not read it: `crop_dpi_for`
    # decides each crop's resolution and `crop.cut` gets an explicit `dpi=`.
    mine = ("VLM_READER", "VLM_TRANSPORT", "VLM_CONCURRENCY",
            "VLM_TEMPERATURE", "VLM_MAX_TOKENS", "VLM_TOP_P", "VLM_SEED",
            "CROP_MARGIN", "PAGE_DPI")
    # The ask/deliver seam holds in the snapshot too: transport knobs are the
    # transport's, not the model's.
    roles = dict(read_by_adapter)
    for n in mine:
        roles.setdefault(n, "the `books read` command itself")
    return knobs.snapshot_with_readers(roles)


def policy_for(run_dir: str, wanted: str | None, what: str = "the preview") -> str:
    """The label dictionary `what` (the preview or the paid run) must use for
    this detect run: the snapshot's own vocabulary, and a `--policy` that
    disagrees with it is refused rather than asked by."""
    with open(os.path.join(run_dir, "run.json"), encoding="utf-8") as f:
        known = json.load(f).get("policy", {}).get("vocabulary")
    if not wanted and not known:
        raise Refusal(
            f"the snapshot {run_dir}/run.json names no label dictionary and "
            f"--policy is not given; {what} depends on which labels are asked "
            f"about, and a guessed dictionary files prose as reading.")
    if wanted and known and wanted != known:
        raise Refusal(
            f"--policy {wanted!r} against the detection dictionary {known!r}: "
            f"{what} would ask by one dictionary what detection boxed by "
            f"another. Drop --policy, or detect again with the detector whose "
            f"dictionary you mean.")
    return wanted or known
