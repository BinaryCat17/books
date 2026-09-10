"""Knob registry: everything affecting a run is declared here and only here.

Three rules. `knob()` raises on an undeclared name instead of returning "": a
knob read past the registry misses the snapshot too, and the run turns
unrepeatable in silence. A default is stored as a string, as the environment
hands it over, or the snapshot writes `2.0` where the run saw `"2"`. A default
lives here alone; a second copy in the job builder would never reach the machine.

How many there are and who reads them is not written here: the registry counts
itself, and `tests/contract/test_snapshot.py` walks the tree for `knob("NAME")`
in python and `$NAME` in shell -- but only for names already declared here.
"""
from booksmith.core import job
from booksmith.core.errors import Refusal


class Knob:
    """One knob: name, default as a string, what for, and has it a consumer.

    `debt=True` is "declared, read by nobody" -- a deliberate debt, counted by
    `debts()`, checked against the tree, and carried into the snapshot.
    """
    __slots__ = ("name", "default", "what", "debt")

    def __init__(self, name, default, what, debt=False):
        self.name, self.default, self.what = name, default, what
        self.debt = bool(debt)


KNOBS = (
    Knob("PAGE_DPI", "144",
         "the resolution a page is RENDERED to for detection. The "
         "detector squeezes the raster to 800x800 itself (keep_ratio: "
         "false). THERE IS A DIFFERENCE, just not in the summary numbers: "
         "on bench/real-tables20/tables20.pdf (20 pages) at dpi "
         "100/140/144/148/200/300/450/580/600/620 the boxes are "
         "384/381/379/378/380/379/378/378/379/379 (band 378..384, 379 "
         "falling out four times), ink under boxes 99.3% everywhere and "
         "99.4% at 100 -- both numbers blind to dpi. The run repeats: two "
         "repeats at 300 dpi gave byte-identical blocks, so the band "
         "378..384 is dpi and not run noise. The LABEL tells them apart: "
         "paragraph_title 42/41/39/40/39/38/36/34/32/34 -- a monotone "
         "decline four times wider than the noise of neighbouring dpi "
         "(39..41 at 140/144/148); text meanwhile stands still "
         "(236..241), so boxes are LOST, not carried over. The cause is "
         "not the resolution but the FILTER: the adapter squeezes the "
         "raster with cv2.INTER_CUBIC (interp: 2 from the weights), at "
         "600 dpi that is a 7.6-fold vertical shrink, i.e. subsampling -- "
         "4.3% of the halftones reach the net against 16.6% with "
         "INTER_AREA. Swapping the interpolation for INTER_AREA at 600 "
         "dpi brings paragraph_title back 32 -> 40 without moving the "
         "total (379), and takes a table away (5 -> 4); at 144 dpi the "
         "same swap gives 382 boxes and 3 tables instead of 5. No dpi and "
         "no filter adds a table. On box coordinates it tells directly"),

    # Raising dpi buys nothing: 600 pays four times the raster for the same 379
    # boxes and loses eight headings, and the interpolation is the weights' own.

    # --- model and weights: without them a run cannot be repeated ---
    Knob("MODEL_NAME", "PaddleOCR-VL-1.6-0.9B",
         "model name for vLLM and for the client"),
    Knob("VL_MODEL_DIR", "", "VLM weights dir; run.sh sets it, vLLM reads"),
    Knob("LAYOUT_ADAPTER", "doclayout",
         "which detection adapter to call; the list is "
         "detect.py:ADAPTERS, four of them: doclayout (PaddleOCR "
         "PP-DocLayout*, 25 labels on V2/V3, 20 on plus-L), docling (IBM "
         "heron RT-DETRv2, 17), docling-egret (IBM egret D-FINE, 17), "
         "yolox (DocLayNet, 11). Different label dictionaries and "
         "different policies -- comparable only blind to the label"),
    Knob("YOLOX_WEIGHTS", "",
         "which YOLOX weights to take: yolox_l0.05.onnx (the default) or "
         "yolox_tiny.onnx"),
    Knob("LAYOUT_MODEL_NAME", "PP-DocLayoutV2", "layout model name"),
    Knob("LAYOUT_MODEL_DIR", "", "layout weights directory"),
    # A threshold for all classes at once, and a knob of its own, because in
    # paddlex a threshold dict holding one class silently gives the rest 0.5.
    Knob("LAYOUT_SCORE_THRESHOLD", "0.5",
         "detection threshold. On doclayout -- common to every class "
         "EXCEPT table (24 of the 25 classes on V2/V3, 19 of the 20 on "
         "plus-L), the default native to the weights. On docling, "
         "docling-egret and yolox -- one for ALL classes, table included, "
         "and the weights carry no native threshold at all"),
    Knob("LAYOUT_TABLE_THRESHOLD", "0.5",
         "the native table detection threshold; read by doclayout ONLY -- "
         "in the other three adapters a table goes by "
         "LAYOUT_SCORE_THRESHOLD"),

    # --- the docling vendor pipeline over heron and egret boxes --------------
    # `off` by default: every bench detector is measured raw, and the pipeline
    # costs 132 of the golden bench's artifacts found for 95 more merges.
    Knob("DOCLING_PIPELINE", "off",
         "the docling vendor pipeline over the boxes: off | post (its "
         "postprocessing) | full (that plus reading-order RULES, not a "
         "model). Read by the docling and docling-egret adapters; "
         "indigestible to the rest. The numbers beside this knob were "
         "taken on HERON -- egret has a price of its own, measured "
         "separately and different"),
    Knob("ASSEMBLY_ORDER", "ours",
         "what assembles the book when the model has NO reading rank of "
         "its own: ours (our rule, top to bottom and left to right) | "
         "docling (reading_order_rb -- 740 lines of vendor RULES, not a "
         "model; needs the docling package, +54 MB). Read by plus-L, "
         "heron, egret and yolox; PP-DocLayoutV2 and V3 have a rank of "
         "their OWN and this knob does not touch them at all. Measured on "
         "the 600 pages of the golden bench, THE SAME V2 boxes permuted "
         "three ways: our rule 2471 extra jumps, the model's own rank "
         "501, the docling rules 439. Ours is worse than both STEADILY -- "
         "over 16 sweep points the limits are 3.02..7.04 against "
         "0.23..1.73 and 0.28..1.57, not overlapping at all. And docling "
         "against the V2 rank the instrument does NOT tell apart: the "
         "pair is inverted, difference 0.13 against a ruler span of 4.02 "
         "-- which is why V2 keeps its own rank. The default is ours and "
         "not the best by number for exactly one reason: docling is a "
         "package, and `books detect --adapter yolox` must not fall on a "
         "fresh environment over a sorting rule"),

    # --- artifact crops: both values default to "as the model saw it" ---
    # Any other value would be ours and not measured; the bench will set it.
    Knob("CROP_DPI", "",
         "crop sharpness. Empty = the scan's OWN resolution (as much as "
         "the file holds and not a dot more), and if that cannot be "
         "determined -- as detection had it. Here stood 'empty = as "
         "PAGE_DPI', wrong on both counts; a knob's text rides into "
         "run.json, so the snapshot described it falsely. Read by "
         "core/raster.py, and through it by `books html`; `books read` and "
         "`books crop` do NOT read it -- there the model's window decides "
         "the resolution"),
    # Zero is a value: the pipeline cuts exactly along the box, and any margin
    # edits the model's box.
    Knob("CROP_MARGIN", "0",
         "margin around the box when cropping, in box fractions"),

    # --- book, rental and ledger: not about parsing, about repeatability ---
    Knob("HTML_MATH", "inline",
         "how formulas are drawn in the book: inline (MathJax INSIDE the "
         "book, +2.3 MB to the file) | local (as a neighbouring "
         "tex-svg.js) | cdn (pulled from the network on every open) | off "
         "(raw LaTeX). The default is `inline`, and it was paid for like "
         "this: with `local` the browser silently DOES NOT LOAD the "
         "neighbouring script when the book is opened over a network path "
         "(\\\\wsl.localhost\\... from Windows) -- Chromium cuts the local "
         "file off, the console says nothing, and the book looks built "
         "without formulas. An embedded script knows no such trouble. The "
         "measurement this knob was made for: «Технология огнеупоров» "
         "holds 2260 formulas among 6080 read blocks, and without "
         "rendering the reader sees "
         "\\[\\mathrm{Al}_{2}\\mathrm{O}_{3}\\] instead of a formula"),
    Knob("HTML_IMAGES", "inline",
         "how the book carries the cut-out artefacts: inline (data: links "
         "INSIDE the html; the file is self-contained and opens by any "
         "path) | linked (links to assets/blocks/*.png). The PNGs are put "
         "into assets/blocks in BOTH cases -- edits, measurements and the "
         "second level need them, not reading alone. The price of inline "
         "on «Технология огнеупоров»: 488 crops, 11.2 MB on disk -> "
         "14.9 MB in base64, the book 2.3 -> ~19 MB. The default is "
         "`inline` for the same reason as HTML_MATH: a book gets opened "
         "over a network path, and then neighbouring files fail to load "
         "in silence"),
    Knob("HTML_REPEATS", "hide",
         "what to do with a PROVEN repeat inside a page: hide (not shown "
         "to the reader; the markup stays, only the display is hidden) | "
         "show (show everything, hiding nothing). The proof is one: the "
         "same text belongs to a block that STAYS in the book; compared "
         "at the latex step, whose measurement is in `text.NORM_STEPS`. "
         "On «Технология огнеупоров» 728 of 1935 nested blocks are "
         "hidden, the share of false ones among them 11.7 % by the worst "
         "background. THE KNOB IS NOT HERE FOR BEAUTY: it is the only "
         "build operation that TAKES text off the reader's eyes, and it "
         "must have a switch -- the cost of an error is asymmetric here, "
         "a false hiding carries words away while a missed repeat leaves "
         "one line too many"),
    Knob("MIN_LINK_MBPS", "2.0",
         "the link threshold a machine is rejected by, Mbps, measured TO "
         "US. It separates a working machine from a broken one, not a "
         "fast one from a slow one: two orders of magnitude lie between "
         "them (7 against 0.06). THIS NUMBER IS NOT DERIVED FROM THE "
         "WORK, and that has to be known before blaming the market. A "
         "`vl-read` job of 20 pages weighs 872 KB: at 0.34 Mbps it "
         "travels in 20 s, at 0.062 (that same broken machine from the "
         "probe's docstring) in 112 s. So for the task ITSELF the "
         "threshold of 2.0 is tenfold excessive, and by it machines are "
         "rejected for good. Measured 3 September 2026: our own link over "
         "HTTP 4.6 Mbps, while a single ssh stream to the rented machine "
         "gave 0.34, and it went onto the eternal blacklist. Loosening "
         "the threshold knowingly is exactly what it was put in the "
         "registry for; loosening it, take the number FROM THE JOB SIZE "
         "and not from taste, and remember that below the threshold a "
         "machine returns its result slowly too"),
    # For a machine that has no git: the rented box has none, and without this
    # the one paid run would be the one with no record of the code that made it.
    Knob("BOOKSMITH_COMMIT", "",
         "the commit for a machine without git; empty = ask git in place"),
    Knob("BOOKSMITH_LEDGER", "",
         "where to write the run journal; empty = runs/ledger.jsonl. The "
         "machine blacklist lives beside the journal"),

    # --- synthetic bench ----------------------------------------------------
    # Seed and ageing profile decide which pages come out, hence the model's
    # answer: a clean page has no `table` box at all and an aged one grows one.
    Knob("SYNTH_SEED", "1", "seed of the synthetic bench"),
    Knob("SYNTH_AGING", "old",
         "bench ageing profile: clean|scan|old|decayed"),

    # --- SECOND LEVEL: reading block content --------------------------------
    # What we ask is the model's property, how we deliver it the transport's,
    # as in `read/__init__.py`; the knobs are split along that line.
    Knob("VLM_READER", "paddleocr-vl",
         "which READING adapter to call; the list is processing/read/driver.py:READERS. "
         "It decides which prompt asks about which label, and in what "
         "shape the answer arrives"),
    Knob("VLM_TRANSPORT", "http",
         "how the question is delivered; the list is processing/read/transports/openai_http.py:build. "
         "Rental is NOT a third transport: on a rented card the same http "
         "looks at 127.0.0.1, where run.sh raised vLLM"),
    # An empty default here drops the run instead of being passed on: a silent
    # `http://127.0.0.1:8118/v1` would call a refused connection a model silence.
    Knob("VLM_ENDPOINT", "",
         "address of an OpenAI-compatible service, /v1 included; no "
         "default"),
    # 4096 is the stock pipeline's, below the model's native 8192, and a knob
    # because our longest single text block is 8207 characters -- and truncation
    # here looks like looping, which only the `finish` field tells apart.
    Knob("VLM_MAX_TOKENS", "4096", "ceiling of an answer, in tokens"),
    Knob("VLM_TIMEOUT_S", "120", "how long to wait for one answer, s"),
    # A 200 is never retried whatever it carries: re-asking repairs the model.
    # The number is about broken links, of which a rented machine has plenty.
    Knob("VLM_RETRIES", "2",
         "how many times to repeat a DELIVERY REFUSAL (not an answer)"),
    # vLLM batches on its own, and a single stream leaves the card nearly idle.
    # Above one the order of answers is undetermined, so pages go by anchor.
    Knob("VLM_CONCURRENCY", "4",
         "how many requests to keep in flight at once"),

    # --- generation ---
    Knob("VLM_TEMPERATURE", "0", "VLM temperature; >0 makes the parse "
                                 "unrepeatable on purpose"),
    # Both are declared though at temperature 0 they change nothing: "top_p was
    # not set" and "top_p was not looked at" are different runs, and above 0 both
    # decide the answer with nowhere to recover them from.
    Knob("VLM_TOP_P", "1.0", "probability cutoff; 1.0 = cut nothing"),
    Knob("VLM_SEED", "0", "generation seed; decides at temperature > 0"),
    Knob("PASSES", "1",
         "how many reads; summing up is the runner's job, not the "
         "model's", debt=True),

    # --- observation, NOT intervention ---
    # What is observed goes to its own file and never touches the text: it lives
    # beside the block, tied to it by number.
    Knob("LOGPROBS", "1", "record token probabilities beside the page",
         debt=True),

    # --- shell ---
    Knob("PORT", "8118", "port of the vLLM service on the machine"),
    # A page counts as done by the artifact it was paid for, not by any trace
    # carrying its number: a page is written by two calls and the first can fail.
    Knob("RESUME", "1", "whether to continue an interrupted run"),
    # "0" and not "", as `run.sh` has it (`${X:-0}`), or the snapshot records ""
    # where the run saw "0". Off deliberately: flashinfer fails to build here.
    Knob("VLLM_USE_FLASHINFER_SAMPLER", "0", "flashinfer sampler in vLLM"),
)
KNOB = {k.name: k for k in KNOBS}


def knob(name):
    """A knob's value: from the job's settings, else the registry default.

    Read at use, inside the job: an adapter, reader or transport built outside
    `Job.active()` or kept across jobs carries another job's values.
    """
    try:
        k = KNOB[name]
    except KeyError:
        raise KeyError(f"knob {name} is not declared in KNOBS: declare it "
                       f"there instead of reading the environment past "
                       f"the registry") from None
    v = job.current().settings.get(k.name)
    return k.default if v is None else v


def number(name, *, kind=float, negative=False):
    """A knob's value as a number, refusing what a number should not be.

    `nan` and `inf` are refused: `nan` compares False with everything, so a
    mistyped knob would make every guard around it quietly stop holding.

    """
    raw = knob(name)
    try:
        v = kind(raw)
    except (TypeError, ValueError):
        raise Refusal(
            f"{name}={raw!r} is not a number: {kind.__name__} expected. A "
            f"knob that decides a run may not be a typo") from None
    f = float(v)
    if f != f or f in (float("inf"), float("-inf")):
        raise Refusal(
            f"{name}={raw!r}: not a finite number. `nan` compares False with "
            f"everything, so every guard around this knob would quietly stop "
            f"holding -- and the run would finish and say nothing")
    if f < 0 and not negative:
        raise Refusal(f"{name}={raw!r}: negative, and this knob is not")
    return v


def snapshot():
    """Every knob at once: what stood, what the default was, was it set.

    "Debt" and the "read by" field `detect.py` adds are different questions: read
    by is about this run, debt about the whole tree.

    """
    given = job.current().settings
    return {k.name: {"value": knob(k.name), "default": k.default,
                     "set_externally": k.name in given, "what": k.what,
                     "debt": k.debt}
            for k in KNOBS}


def snapshot_with_readers(roles):
    """The knob snapshot, each knob saying who reads it in this run.

    Here because two commands snapshot and both must write the one shape `books
    replay --check` reads. No knob is dropped; the mark rides beside the value.

    """
    snap = snapshot()
    for name, rec in snap.items():
        who = roles.get(name)
        rec["read_by"] = who or "NOBODY IN THIS RUN"
        rec["for_this_run"] = who is not None
    return snap


def debts():
    """Knobs declared debt: no consumer, and none due yet."""
    return tuple(k.name for k in KNOBS if k.debt)


def names():
    return tuple(k.name for k in KNOBS)


def passthrough():
    """What to pass to the rented machine: only what the operator set.

    Defaults are not substituted -- they live in this file alone -- and the list
    comes from the registry, so it cannot fall behind it.
    """
    given = job.current().settings
    return {n: given[n] for n in names() if n in given}
