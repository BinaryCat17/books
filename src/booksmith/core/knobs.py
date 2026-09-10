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

    def __init__(self, name: str, default: str, what: str, debt: bool = False) -> None:
        self.name, self.default, self.what = name, default, what
        self.debt = bool(debt)


KNOBS = (
    Knob("PAGE_DPI", "144",
         "the resolution a page is rendered to for detection; the detector squeezes the raster to its own input size, so the dpi decides little and the squeeze's filter more"),


    # --- model and weights: without them a run cannot be repeated ---
    Knob("MODEL_NAME", "PaddleOCR-VL-1.6-0.9B",
         "model name for vLLM and for the client"),
    Knob("VL_MODEL_DIR", "", "VLM weights dir; run.sh sets it, vLLM reads"),
    Knob("LAYOUT_ADAPTER", "doclayout",
         "which detection adapter to call, one of `detect.py:ADAPTERS`; each has its own label dictionary and policy, so two are comparable only blind to the label"),
    # An empty default drops the run instead of being passed on, as with
    # VLM_ENDPOINT: a silent localhost would call a refused connection silence.
    Knob("LAYOUT_ENDPOINT", "",
         "address of a served layout or hybrid model, the root its /booksmith routes hang from; read by the served adapter alone, and no default"),
    Knob("YOLOX_WEIGHTS", "",
         "which YOLOX weights to take: yolox_l0.05.onnx (the default) or "
         "yolox_tiny.onnx"),
    Knob("LAYOUT_MODEL_NAME", "PP-DocLayoutV2", "layout model name"),
    Knob("LAYOUT_MODEL_DIR", "", "layout weights directory"),
    # A threshold for all classes at once, and a knob of its own, because in
    # paddlex a threshold dict holding one class silently gives the rest 0.5.
    Knob("LAYOUT_SCORE_THRESHOLD", "0.5",
         "the detection threshold: on doclayout the one native to the weights for every class but table, on docling, docling-egret and yolox one for all classes, table included, since those weights carry none of their own"),
    Knob("LAYOUT_TABLE_THRESHOLD", "0.5",
         "the native table detection threshold; read by doclayout ONLY -- "
         "in the other three adapters a table goes by "
         "LAYOUT_SCORE_THRESHOLD"),

    # --- the docling vendor pipeline over heron and egret boxes --------------
    # `off` by default: every bench detector is measured raw.
    Knob("DOCLING_PIPELINE", "off",
         "the docling vendor pipeline over the boxes: off, post (its postprocessing) or full (that plus its reading-order rules, which are not a model); read by the docling and docling-egret adapters only"),
    Knob("ASSEMBLY_ORDER", "ours",
         "what assembles the book when the model has no reading rank of its own: ours (top to bottom, left to right) or docling (the vendor's rules, needing the docling package); PP-DocLayoutV2 and V3 carry a rank and ignore it, and ours is the default so that a detect run on a fresh environment never falls over a sorting rule"),

    # --- artifact crops: both values default to "as the model saw it" ---
    # Any other value would be ours and not measured; the bench will set it.
    Knob("CROP_DPI", "",
         "crop sharpness for `books html`: empty is the scan's own resolution, or detection's when that cannot be told; `books read` and `books crop` do not read it, the model's window deciding there"),
    # Zero is a value: the pipeline cuts exactly along the box, and any margin
    # edits the model's box.
    Knob("CROP_MARGIN", "0",
         "margin around the box when cropping, in box fractions"),

    # --- book, rental and ledger: not about parsing, about repeatability ---
    Knob("HTML_MATH", "inline",
         "how formulas are drawn in the book: inline (MathJax inside the file), local (a neighbouring script, which a browser silently refuses to load over a network path), cdn (fetched on every open) or off (raw LaTeX)"),
    Knob("HTML_IMAGES", "inline",
         "how the book carries the cut-out artefacts: inline (data links inside the html, so the file opens by any path) or linked (assets/blocks/*.png, which a browser silently refuses over a network path); the PNGs are written in both cases"),
    Knob("HTML_REPEATS", "hide",
         "what to do with a proven repeat inside a page: hide (kept in the markup, not displayed) or show; the one build operation that takes text off the reader's eyes, so it has a switch"),
    Knob("MIN_LINK_MBPS", "2.0",
         "the link threshold in Mbps, measured to us, below which a machine is rejected, and blacklisted only when a faster witness makes the link the machine's own; it tells a broken machine from a working one, not a slow from a fast, and is not derived from the job's size"),
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
    # The stock pipeline's ceiling, below the model's native one, and a knob
    # because a long text block exceeds it -- and truncation here looks like
    # looping, which only the `finish` field tells apart.
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
    Knob("VLM_TOP_P", "1.0", "probability cutoff; one cuts nothing"),
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


def knob(name: str) -> str:
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


def number(name: str, *, kind: type = float, negative: bool = False) -> float:
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


def snapshot() -> dict:
    """Every knob at once: what stood, what the default was, was it set.

    "Debt" and the "read by" field `detect.py` adds are different questions: read
    by is about this run, debt about the whole tree.

    """
    given = job.current().settings
    return {k.name: {"value": knob(k.name), "default": k.default,
                     "set_externally": k.name in given, "what": k.what,
                     "debt": k.debt}
            for k in KNOBS}


def snapshot_with_readers(roles: dict) -> dict:
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


def debts() -> tuple[str, ...]:
    """Knobs declared debt: no consumer, and none due yet."""
    return tuple(k.name for k in KNOBS if k.debt)


def names() -> tuple[str, ...]:
    return tuple(k.name for k in KNOBS)


def passthrough() -> dict:
    """What to pass to the rented machine: only what the operator set.

    Defaults are not substituted -- they live in this file alone -- and the list
    comes from the registry, so it cannot fall behind it.
    """
    given = job.current().settings
    return {n: given[n] for n in names() if n in given}
