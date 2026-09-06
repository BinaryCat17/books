"""`books read` -- second level: walk the book and fill in block content.

THE PRODUCT IS THE SAME `pages/*.json` AS DETECTION, and that decision carries
the file: same boxes, labels and order, with `content` and `kind` filled in.
Everything downstream then costs nothing, and it is code, not a promise:

    books html  -- <p> when a TEXT block has content, an image otherwise. An
                   artefact stays an image whatever its content (`if role ==
                   "artifact" or not b.content`), by design: a swap must be
                   reversible and journalled, and a rebuild knows nothing of
                   the journal. Read tables and formulas go in through
                   `books apply --from`, one at a time and undoable
    books text  -- `measure(truth_dir, pages_dir)` reads exactly this directory,
                   and so do books score, fitness, overlay and replay

A format of our own would have cost six adapters.

WHAT IS OBSERVED LIVES BESIDE. `content` carries THE MODEL'S BYTES and nothing
more; seconds, tokens, finish reason, kind guess and delivery refusal go to
`answers/*.json`, tied to the block by its anchor. The rule cost nine misses
out of thirty-three when marks were written into the text instead.

WHAT MUST FAIL ALOUD ON THIS PATH:

  * a label the reader routes nowhere (`Reader.cover`): a new weights class
    would ride the wrong prompt and be filed as reading;
  * an endpoint answering with ANOTHER model's name (`Transport.check`): the
    snapshot would name one model while another answered;
  * zero blocks to read -- an empty run must not look successful;
  * a detection directory with no `run.json`, or with another book's pages;
  * a PDF whose sha256 differs from the detection snapshot: boxes measured on
    one file, crops cut from another.

FIVE DIFFERENT ZEROS, COUNTED APART. Merged, they all print "read 0"
while meaning something different every time:

    not asked        -- route empty with a declared reason (figures)
    delivery failed  -- no answer at all: broken link, timeout, not 200
    model silent     -- an answer came, and it was empty
    hit the ceiling  -- `finish="length"`; torn OTSL looks whole
    read             -- the only case where `content` is non-empty
"""
import glob
import json
import os
import re
import shlex
import sys
import time
from concurrent.futures import ThreadPoolExecutor

from . import Ask, Reader, Transport
from .. import otsl, policy
from ..doc import crop
from ..models.base import Page
from ..run import knobs, stamp

# Reader registry, a list for the same reason the detector one is: while a
# model name is wired into an import, "would another be better" cannot even be
# asked. A new reader is a line here and one file beside the model.
READERS = ("paddleocr-vl",)


def log(*a):
    print(f"[{time.strftime('%H:%M:%S')}]", *a, flush=True)


def build_reader(policy_name: str) -> Reader:
    name = knobs.knob("VLM_READER")
    if name == "paddleocr-vl":
        from ..models.paddleocr_vl.reader import PaddleOcrVl
        return PaddleOcrVl(policy_name)
    raise SystemExit(
        f"VLM_READER={name!r}: I know only {READERS}. A silent fallback to "
        f"whichever comes first would make a typo in the reader's name count "
        f"as a successful run, with the snapshot naming the wrong model.")


def _sniff(text: str) -> str:
    """A GUESS at the kind of answer. Lives BESIDE and decides nothing.

    The PROMPT declares the kind (`read/__init__.py`), not the answer: sniffing
    it would be fixing the model -- a table returned as prose would slip into
    text, and a LABEL error on a correct box dissolve into "that is how the
    model reads". Where guess and declaration disagree, that is a named counter,
    and it is what shows the declaration itself needs changing.
    """
    if not text:
        return "empty"
    t = text.strip()
    if otsl.looks_like(t):
        return "otsl"
    if "<table" in t.lower() or "<td" in t.lower():
        return "html"
    # LATEX IS RECOGNISED WIDER than by three tells. Measured on the previous
    # edition: of eight plausible answers to a formula, six came out `text`
    # (`x^{2}+y^{2}=z^{2}`, `\\alpha + \\beta`, `\\sum_{i=1}^{n} a_i`,
    # `A_{ij} = B_{ij}`), and "kind not as promised" grew on every formula,
    # demanding a change to a CORRECT declaration. An instrument that lies
    # towards alarm is no better than one lying towards calm.
    if (t.startswith("$") or re.search(r"\\[A-Za-z]{2,}", t)
            or re.search(r"[_^]\{", t) or re.search(r"[A-Za-z0-9)\]]\^[A-Za-z0-9{]", t)):
        return "latex"
    return "text"


def crop_dpi_for(box, page_dpi: float, native: float | None,
                 window, sheet=None) -> tuple[float, str]:
    """What resolution to cut THIS block at, and why that one.

    A RULE, NOT A NUMBER. As much as the scan HAS (`native`), no more than the
    model eats (`window`, its own bounds). None of the three is ours: sharpness
    comes from the scan, bounds from the model, box size from the detector.

    Not more: above its own grid what gets added is the rasteriser's guess, not
    ink, and the model shrinks the crop back anyway -- paying twice to compress
    an invention. Not less: on `bench/slovar` at detection resolution 555 crops
    of 566 fall below the model's lower bound, so nine times in ten it stretched
    our ink itself.

    AND NEVER ABOVE THE GRID even when the block is smaller than the lower
    bound: that would be inventing dots and calling it reading. The case
    becomes a number (`below_model_min`) for the bench to explain.
    """
    base = float(native or page_dpi)
    if not window:
        return base, "native_scan_dpi_no_model_bounds"
    lo, hi = window
    # COUNT BY WHAT WILL ACTUALLY BE CUT. A model box can hang off the sheet and
    # `crop.cut` cuts the INTERSECTION; sizing by the full box clamps the crop to
    # a size that is not on paper, and a badly overhanging box then gets LESS
    # resolution than the model's window allows. On the bench that is 28 boxes of
    # 33 640, overhangs no larger than 4.8 pixels -- real data has not caught it
    # yet, but the rule must measure the rectangle it cuts, or two numbers drift
    # apart in silence.
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
        raise SystemExit(
            f"no run.json in {detect_dir}: this is not a `books detect` "
            f"directory. Reading without the detection snapshot knows neither "
            f"the book nor the dpi the boxes were measured at, and would cut "
            f"the crops at the wrong coordinates.")
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def read_book(detect_dir: str, out_dir: str, reader: Reader,
              transport: Transport, resume: bool = True,
              pages_want=None, log=log, pdf: str | None = None) -> dict:
    """Walk the book and fill in block content. Returns quantities.

    `pdf` is where the book lies NOW. The detection snapshot keeps the path it
    was read at, and on a rented machine that path does not exist: the working
    directory is its own and the file arrives as `input.pdf`. So the path may be
    given; the sha256 CHECK stays mandatory whatever it is, being about which
    book this is, not where it lies.
    """
    import pymupdf

    facts = _detect_facts(detect_dir)
    pdf = pdf or facts["source"]["path"]
    if not os.path.exists(pdf):
        raise SystemExit(f"no source {pdf}, the one the detection snapshot names")
    got = stamp.sha256(pdf)
    if got != facts["source"]["sha256"]:
        raise SystemExit(
            f"{pdf}: sha256 {got[:12]} against "
            f"{facts['source']['sha256'][:12]} in the detection snapshot. The "
            f"boxes were measured on ANOTHER file; the crops would be cut at "
            f"the wrong coordinates and the answer would look like reading.")
    page_dpi = float(facts["raster"]["dpi"])

    files = sorted(glob.glob(os.path.join(detect_dir, "pages", "*.json")))
    if not files:
        raise SystemExit(f"no pages in {detect_dir}: run books detect first")

    # ANOTHER BOOK'S PAGES. The `out` directory is assembled by hand and reused;
    # `0007.json` from a different book would survive the run and ride into
    # `books html`, `books text` and `books score` as part of this one. The
    # header promised a failure on that, and there was none.
    _pages_dir = os.path.join(out_dir, "pages")
    if os.path.isdir(_pages_dir):
        mine_ = {os.path.basename(f) for f in files}
        alien = sorted(set(os.listdir(_pages_dir)) - mine_)
        if alien:
            raise SystemExit(
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
        raise SystemExit("not one page to read: the --pages set is empty")
    reader.cover(labels)

    params = _gen_params()
    window = reader.pixels()
    # WHAT WE READ WITH LAST TIME. Resuming must compare this, not merely that a
    # file exists. Measured before the comparison: change the model, the token
    # ceiling or the prompts and not one block was re-asked, while `run.json`
    # declared the NEW values in force -- a snapshot "complete and not in
    # effect", the disease this header is written against. And the only record of
    # what was paid for (seconds, tokens) was overwritten by the second, free
    # run.
    setup = {"reader": reader.fingerprint(), "generation": params,
             "transport": {k: v for k, v in transport.fingerprint().items()
                           # the address moves from run to run (stand-in server
                           # port, a loopback on the box) and does not decide
                           # the model's answer; the model name does.
                           if k in ("transport", "model_asked")}}
    setup_path = os.path.join(out_dir, "read_with.json")
    same_setup = True
    if resume and os.path.exists(setup_path):
        with open(setup_path, encoding="utf-8") as f:
            was = json.load(f)
        same_setup = was == setup
        if not same_setup:
            diff = [k for k in setup if was.get(k) != setup[k]]
            log(f"READ WITH SOMETHING ELSE: {diff} differ -- resuming is not "
                f"allowed, asking everything again. Otherwise the snapshot "
                f"would declare new values in force over old answers.")
    with open(setup_path, "w", encoding="utf-8") as f:
        json.dump(setup, f, ensure_ascii=False, indent=1)
    doc = pymupdf.open(pdf)
    # OWN RESOLUTION PER PAGE, not the first page's for the whole book.
    #
    # The sheet is NOT one and the same: "Фейнмановские лекции" carry 255
    # distinct sheet sizes over 260 pages, "Технология огнеупоров" 178 over 378.
    #
    # Per page costs nothing: the answer is memoised here, one `get_images` per
    # page rather than per block. The 15 601 calls against 600 pages that made
    # this "saving" negative were `crop.cut` asking `native_dpi` on every block
    # and dropping the answer; it stopped asking once `dpi` is passed, which on
    # this path it always is.
    #
    # The price of the error is measured. Feynman pages 0-2 are vector (the
    # title) and 257 of 260 carry a 300 dpi raster; the first page's resolution
    # is `None`, so the whole book was cut at 144: 15.1 million pixels instead
    # of 59.0, 2.69 million of ink instead of 9.38 (3.89x and 3.49x), 125 crops
    # of 177 below the model's lower bound instead of 79. One book in nine, and
    # the one showing that "by the first page" rested on a coincidence.
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
             # THE SIXTH ZERO, nameless until now. The transport can return an
             # answer under SOMEONE ELSE'S anchor (shuffled order, a gateway
             # that rewrote the request), and the block was then left without
             # any record: none of the five counters moved, `answers/` empty,
             # `content` empty, the answer paid for. Measured: three answers
             # with foreign anchors gave "sum of outcomes 0 with 3 blocks".
             "answer_wrong_anchor": 0, "asked_no_answer": 0,
             "crop_failed": 0, "crop_dpi_reason_counts": {},
             "native_book_dpi": native,
             "model_window": list(window) if window else None,
             "chars": 0, "compute_seconds": 0.0, "tokens": 0}
    bad_crops = []
    by_kind = {}
    worst = []

    for fp, pg in pages:
        tag = f"p{pg.index:04d}"
        ans_path = os.path.join(out_dir, "answers", f"{tag}.json")
        old = {}
        if resume and os.path.exists(ans_path) and same_setup:
            with open(ans_path, encoding="utf-8") as f:
                old = {a["anchor"]: a for a in json.load(f).get("answers", [])}

        asks, silent, nocrop, cut_info = [], {}, {}, {}
        for b in pg.blocks:
            tally["block_count"] += 1
            anchor = f"{tag}-b{b.block_id}"
            rt = routes[b.label]
            if not rt.asked():
                tally["not_asked"] += 1
                silent[anchor] = rt.why
                continue
            if anchor in old and old[anchor].get("text") is not None:
                tally["reused_from_previous_run"] += 1
                continue
            rel = os.path.join(crops_dir, f"{anchor}.png")
            # The sheet in pixels of THE SAME raster the boxes live in.
            _r = doc[pg.index].rect
            sheet = (0.0, 0.0, _r.width * page_dpi / 72.0,
                     _r.height * page_dpi / 72.0)
            cdpi, why = crop_dpi_for(b.box, page_dpi, _native(pg.index),
                                     window, sheet=sheet)
            cut_dpi[anchor] = (cdpi, why)
            tally["crop_dpi_reason_counts"][why] = (
                tally["crop_dpi_reason_counts"].get(why, 0) + 1)
            try:
                # THE RETURN IS NOT THROWN AWAY. `crop.cut` reports width,
                # height, `clipped_by_sheet` and the HONEST dpi (cut at, not
                # asked for), and this pass used to lose them: about a crop that
                # went to the model bitten off by the sheet edge, `answers/`
                # said nothing. Measured: clipped by sheet 28 of 15 601 bench
                # boxes (0.18%), but 8 of 177 on a real scan -- 4.5%.
                cut_info[anchor] = crop.cut(doc, pg.index, b.box, page_dpi,
                                            rel, dpi=cdpi)
            except (ValueError, IndexError, RuntimeError) as e:
                # THE MODEL'S BOX IS NOT REPAIRED, nor is the book abandoned over
                # it. A degenerate box, a box off the sheet, a page beyond the
                # PDF are defects of the model or of a foreign directory, and
                # each used to drop the run with a bare traceback MID-BOOK:
                # everything already read left without a snapshot, money spent
                # and nothing to show. Now it is a QUANTITY with a counter and
                # the run goes on.
                tally["crop_failed"] += 1
                bad_crops.append(f"{anchor}: {type(e).__name__}: {e}")
                nocrop[anchor] = f"{type(e).__name__}: {e}"
                continue
            asks.append(Ask(anchor=anchor, image=rel, prompt=rt.prompt,
                            kind=rt.kind, label=b.label, params=dict(params)))

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

        # Assemble the page. Block order is the ORIGINAL one, not the order the
        # answers came in: with VLM_CONCURRENCY > 1 they arrive shuffled, and
        # filing by arrival would silently reorder the book.
        answers = []
        for b in pg.blocks:
            anchor = f"{tag}-b{b.block_id}"
            rt = routes[b.label]
            if anchor in silent:
                b.content, b.kind = None, "none"
                answers.append({"anchor": anchor, "not_asked": silent[anchor]})
                continue
            if anchor in nocrop:
                # The block was NOT asked: there was nothing to cut. This is not
                # "asked and no answer" -- one trouble would count as two.
                b.content, b.kind = None, "none"
                answers.append({"anchor": anchor,
                                "crop_failed": nocrop[anchor]})
                continue
            if anchor in old and old[anchor].get("text") is not None:
                rec = old[anchor]
            else:
                s = said.get(anchor)
                if s is None:
                    # Asked, and no answer under this anchor. Silence is not
                    # allowed: the block would leave the book and `answers/`
                    # without a single record.
                    tally["asked_no_answer"] += 1
                    b.content, b.kind = None, "none"
                    answers.append({"anchor": anchor,
                                    "trouble": "asked, and no answer came "
                                               "under this anchor"})
                    continue
                rec = s.to_json()
                rec["label"] = b.label
                if anchor in cut_dpi:
                    # dpi comes FROM THE CROP, not from the rule: `crop.cut`
                    # renders at `int(dpi)` while the rule gives a fraction,
                    # and the recorded `round` disagreed with the deed on 328
                    # boxes of 379. The disagreement is worth one dpi (0.13% of
                    # width) -- but the number in the journal must be the one it
                    # was cut at.
                    info = cut_info.get(anchor) or {}
                    rec["observed"]["crop_dpi"] = info.get(
                        "dpi", cut_dpi[anchor][0])
                    rec["observed"]["crop_dpi_by_rule"] = round(
                        cut_dpi[anchor][0], 2)
                    rec["observed"]["crop_dpi_reason"] = cut_dpi[anchor][1]
                    rec["observed"]["crop"] = info or None
                rec["observed"]["kind_sniffed"] = _sniff(s.text or "")
                # OTSL TORNNESS IS COUNTED BESIDE the answer. `otsl.parse`
                # already counted rows of unequal length, continuations to
                # nowhere and text outside the tags, and threw it all away: no
                # run could print the numbers that tell a table torn at the
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
                # THE MODEL'S BYTES, unedited. The kind is the prompt's.
                b.content, b.kind = txt, rt.kind
                by_kind[rt.kind] = by_kind.get(rt.kind, 0) + 1
                if rec["observed"].get("kind_sniffed") not in (rt.kind, None):
                    tally["kind_not_as_promised"] += 1
            if rec.get("outcome") == "length":
                tally["hit_ceiling"] += 1
                worst.append(anchor)
            # ONLY REAL QUESTIONS COUNT. Blocks taken from a previous run landed
            # here too: a second `books read` printed "asked 567" with ZERO
            # calls to the service, and "seconds per block" divided by that same
            # number. Two quantities under one name, drifting apart by
            # construction.
            if anchor in asked_now:
                tally["asked"] += 1

        pg.meta = dict(pg.meta or {})
        pg.meta["reading"] = {"reader": reader.name, "transport": transport.name,
                             "asked": len(asks)}
        with open(os.path.join(out_dir, "pages", os.path.basename(fp)),
                  "w", encoding="utf-8") as f:
            json.dump(pg.to_json(), f, ensure_ascii=False, indent=1)
        with open(ans_path, "w", encoding="utf-8") as f:
            json.dump({"page": pg.index, "answers": answers}, f,
                      ensure_ascii=False, indent=1)
        log(f"p. {pg.index}: asked {len(asks)}, read "
            f"{sum(1 for a in answers if a.get('text'))}, "
            f"silences {sum(1 for a in answers if a.get('text') == '')}, "
            f"refusals {sum(1 for a in answers if a.get('error'))}")
    doc.close()

    tally["by_kind"] = by_kind
    tally["truncated_anchors"] = worst[:20]
    tally["crop_failures"] = bad_crops[:20]
    return tally


def report(t: dict, log=log) -> None:
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
    # The five troubles are printed ALWAYS, zeros included: a line that
    # disappears at zero reads as "this never happens" rather than "it did not
    # happen this time".
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
    """The repeat line. EXECUTABLE and COMPLETE.

    Without `--pages` and `--policy` it repeats a DIFFERENT run; `books detect`
    puts `--pages` into its own, and two commands disagreeing here is
    indefensible. Quoting is mandatory: five files of nine in `raw/` carry
    spaces and brackets, and an unquoted repeat line is not a repeat line but a
    description of one.
    """
    argv = ["books", "read", detect_dir, "--out", out_dir]
    if args.get("pages"):
        argv += ["--pages", str(args["pages"])]
    if args.get("policy"):
        argv += ["--policy", str(args["policy"])]
    return " ".join(shlex.quote(a) for a in argv)


def snapshot(detect_dir: str, out_dir: str, reader: Reader,
             transport: Transport, tally: dict, args: dict) -> str:
    """Input snapshot: the same fields as detection, and at last a non-empty
    `prompts`."""
    facts = _detect_facts(detect_dir)
    read_knobs = {**{n: "reading adapter" for n in reader.knobs_read()},
                  **{n: "transport" for n in transport.knobs_read()}}
    snap = {
        "when": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "knobs": _knobs_snapshot(read_knobs),
        "raster": facts["raster"],
        "args": args,
        "commit": stamp.commit(),
        # The same book as detection, hash checked BEFORE the work (read_book).
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
                    "sha256_command": stamp.sha256(
                        os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                     "run.py")),
                    # OTSL parsing is OUR code and decides the numbers no less
                    # than the model does. Without its hash two runs with
                    # different parsers would look identical.
                    "sha256_otsl_parser": stamp.sha256(
                        os.path.join(os.path.dirname(os.path.dirname(
                            os.path.abspath(__file__))), "otsl.py"))},
        "policy": policy.snapshot(getattr(reader, "policy_name", None)),
        "prompts": reader.fingerprint().get("prompts", {}),
        "generation": _gen_params(),
        "packages": stamp.packages(stamp.READ_PACKAGES),
        "weights": {"vl": reader.fingerprint().get("weights"),
                 "layout": facts.get("weights", {}).get("layout")},
        # THE FINGERPRINT IS THE READER'S, unwrapped. `run/replay.py` derives the
        # required shape from the active adapter's `fingerprint()` and looks for
        # its fields right here; nested under a "reader" key they gave six lines
        # of "no fingerprint/prompts" -- the snapshot declared INCOMPLETE while
        # everything was written. The transport gets its own field: it is no
        # model adapter, and mixing them declares two fingerprints one.
        "fingerprint": reader.fingerprint(),
        "transport_fingerprint": transport.fingerprint(),
        "summary": tally,
        "repeat_command": _repeat_line(detect_dir, out_dir, args),
    }
    p = os.path.join(out_dir, "run.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(snap, f, ensure_ascii=False, indent=1)
    return p


def _knobs_snapshot(read_by_adapter) -> dict:
    """Knobs marked with who reads them. Shape shared with detection.

    The split is not decoration: a snapshot with every knob in one heap is
    COMPLETE and not in effect. A heron run swore `LAYOUT_MODEL_NAME=
    PP-DocLayoutV2` -- a value that adapter does not read at all -- and `books
    replay --check` approved it.
    """
    # `CROP_DPI` IS ABSENT HERE, and not out of forgetfulness. The reading path
    # does not read it at all: each crop's resolution is decided by
    # `crop_dpi_for` (scan plus model window), and `crop.cut` is called with an
    # explicit `dpi=`. Checked: `CROP_DPI=72` and `CROP_DPI=1200` do not move a
    # `books read` crop by a pixel, while `books html` and `books feed` obey it.
    # Declaring it in force would repeat the disease above.
    mine = ("VLM_READER", "VLM_TRANSPORT", "VLM_CONCURRENCY",
            "VLM_TEMPERATURE", "VLM_MAX_TOKENS", "VLM_TOP_P", "VLM_SEED",
            "CROP_MARGIN", "PAGE_DPI")
    # THE "WHAT WE ASK / HOW WE DELIVER" SEAM LIVES IN THE SNAPSHOT TOO. Roles
    # used to be folded into one tuple with "reading adapter" on all of them --
    # so `VLM_ENDPOINT`, `VLM_RETRIES` and `VLM_TIMEOUT_S`, read by the
    # transport, were credited to the model. The seam the whole of
    # `read/__init__.py` exists for was erased in the snapshot.
    roles = dict(read_by_adapter)
    for n in mine:
        roles.setdefault(n, "the `books read` command itself")
    return knobs.snapshot_with_readers(roles)
