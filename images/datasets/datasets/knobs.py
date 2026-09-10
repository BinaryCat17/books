"""Knob registry: everything affecting a run is declared here and only here"""

from datasets import job
from datasets.errors import Refusal


class Knob:
    __slots__ = ("name", "default", "what", "debt")

    def __init__(self, name: str, default: str, what: str, debt: bool = False) -> None:
        self.name, self.default, self.what = (name, default, what)
        self.debt = bool(debt)


KNOBS = (
    Knob(
        "PAGE_DPI",
        "144",
        "the resolution a page is rendered to for detection; the detector squeezes the raster to its own input size, so the dpi decides little and the squeeze's filter more",
    ),
    Knob("MODEL_NAME", "PaddleOCR-VL-1.6-0.9B", "model name for vLLM and for the client"),
    Knob("VL_MODEL_DIR", "", "VLM weights dir; run.sh sets it, vLLM reads"),
    Knob(
        "LAYOUT_ADAPTER",
        "doclayout",
        "which detection adapter to call, one of `detect.py:ADAPTERS`; each has its own label dictionary and policy, so two are comparable only blind to the label",
    ),
    Knob(
        "LAYOUT_ENDPOINT",
        "",
        "address of a served layout or hybrid model, the root its /datasets routes hang from; read by the served adapter, and by the doctor to know whether there is one to ask; no default",
    ),
    Knob(
        "YOLOX_WEIGHTS",
        "",
        "which YOLOX weights to take: yolox_l0.05.onnx (the default) or yolox_tiny.onnx",
    ),
    Knob("LAYOUT_MODEL_NAME", "PP-DocLayoutV2", "layout model name"),
    Knob("LAYOUT_MODEL_DIR", "", "layout weights directory"),
    Knob(
        "LAYOUT_SCORE_THRESHOLD",
        "0.5",
        "the detection threshold: on doclayout the one native to the weights for every class but table, on docling, docling-egret and yolox one for all classes, table included, since those weights carry none of their own",
    ),
    Knob(
        "LAYOUT_TABLE_THRESHOLD",
        "0.5",
        "the native table detection threshold; read by doclayout ONLY -- in the other three adapters a table goes by LAYOUT_SCORE_THRESHOLD",
    ),
    Knob(
        "DOCLING_PIPELINE",
        "off",
        "the docling vendor pipeline over the boxes: off, post (its postprocessing) or full (that plus its reading-order rules, which are not a model); read by the docling and docling-egret adapters only",
    ),
    Knob(
        "ASSEMBLY_ORDER",
        "ours",
        "what assembles the book when the model has no reading rank of its own: ours (top to bottom, left to right) or docling (the vendor's rules, needing the docling package); PP-DocLayoutV2 and V3 carry a rank and ignore it, and ours is the default so that a detect run on a fresh environment never falls over a sorting rule",
    ),
    Knob(
        "CROP_DPI",
        "",
        "crop sharpness for `books html`: empty is the scan's own resolution, or detection's when that cannot be told; `books read` and `books crop` do not read it, the model's window deciding there",
    ),
    Knob("CROP_MARGIN", "0", "margin around the box when cropping, in box fractions"),
    Knob(
        "HTML_MATH",
        "inline",
        "how formulas are drawn in the book: inline (MathJax inside the file), local (a neighbouring script, which a browser silently refuses to load over a network path), cdn (fetched on every open) or off (raw LaTeX)",
    ),
    Knob(
        "HTML_IMAGES",
        "inline",
        "how the book carries the cut-out artefacts: inline (data links inside the html, so the file opens by any path) or linked (assets/blocks/*.png, which a browser silently refuses over a network path); the PNGs are written in both cases",
    ),
    Knob(
        "HTML_REPEATS",
        "hide",
        "what to do with a proven repeat inside a page: hide (kept in the markup, not displayed) or show; the one build operation that takes text off the reader's eyes, so it has a switch",
    ),
    Knob(
        "MIN_LINK_MBPS",
        "2.0",
        "the link threshold in Mbps, measured to us, below which a machine is rejected, and blacklisted only when a faster witness makes the link the machine's own; it tells a broken machine from a working one, not a slow from a fast, and is not derived from the job's size",
    ),
    Knob("BOOKSMITH_COMMIT", "", "the commit for a machine without git; empty = ask git in place"),
    Knob(
        "BOOKSMITH_LEDGER",
        "",
        "where to write the run journal; empty = runs/ledger.jsonl. The machine blacklist lives beside the journal",
    ),
    Knob("SYNTH_SEED", "1", "seed of the synthetic bench"),
    Knob("SYNTH_AGING", "old", "bench ageing profile: clean|scan|old|decayed"),
    Knob(
        "VLM_READER",
        "paddleocr-vl",
        "which READING adapter to call; the list is processing/read/driver.py:READERS. It decides which prompt asks about which label, and in what shape the answer arrives",
    ),
    Knob(
        "VLM_TRANSPORT",
        "http",
        "how the question is delivered; the list is processing/read/transports/openai_http.py:build. Rental is NOT a third transport: on a rented card the same http looks at 127.0.0.1, where run.sh raised vLLM",
    ),
    Knob("VLM_ENDPOINT", "", "address of an OpenAI-compatible service, /v1 included; no default"),
    Knob("VLM_MAX_TOKENS", "4096", "ceiling of an answer, in tokens"),
    Knob("VLM_TIMEOUT_S", "120", "how long to wait for one answer, s"),
    Knob("VLM_RETRIES", "2", "how many times to repeat a DELIVERY REFUSAL (not an answer)"),
    Knob("VLM_CONCURRENCY", "4", "how many requests to keep in flight at once"),
    Knob("VLM_TEMPERATURE", "0", "VLM temperature; >0 makes the parse unrepeatable on purpose"),
    Knob("VLM_TOP_P", "1.0", "probability cutoff; one cuts nothing"),
    Knob("VLM_SEED", "0", "generation seed; decides at temperature > 0"),
    Knob(
        "PASSES", "1", "how many reads; summing up is the runner's job, not the model's", debt=True
    ),
    Knob("LOGPROBS", "1", "record token probabilities beside the page", debt=True),
    Knob("PORT", "8118", "port of the vLLM service on the machine"),
    Knob("RESUME", "1", "whether to continue an interrupted run"),
    Knob("VLLM_USE_FLASHINFER_SAMPLER", "0", "flashinfer sampler in vLLM"),
)
KNOB = {k.name: k for k in KNOBS}


def knob(name: str) -> str:
    try:
        k = KNOB[name]
    except KeyError:
        raise KeyError(
            f"knob {name} is not declared in KNOBS: declare it there instead of reading the environment past the registry"
        ) from None
    v = job.current().settings.get(k.name)
    return k.default if v is None else v


def number(name: str, *, kind: type = float, negative: bool = False) -> float:
    raw = knob(name)
    try:
        v = kind(raw)
    except (TypeError, ValueError):
        raise Refusal(
            f"{name}={raw!r} is not a number: {kind.__name__} expected. A knob that decides a run may not be a typo"
        ) from None
    f = float(v)
    if f != f or f in (float("inf"), float("-inf")):
        raise Refusal(
            f"{name}={raw!r}: not a finite number. `nan` compares False with everything, so every guard around this knob would quietly stop holding -- and the run would finish and say nothing"
        )
    if f < 0 and (not negative):
        raise Refusal(f"{name}={raw!r}: negative, and this knob is not")
    return v


def snapshot() -> dict:
    given = job.current().settings
    return {
        k.name: {
            "value": knob(k.name),
            "default": k.default,
            "set_externally": k.name in given,
            "what": k.what,
            "debt": k.debt,
        }
        for k in KNOBS
    }


def snapshot_with_readers(roles: dict) -> dict:
    snap = snapshot()
    for name, rec in snap.items():
        who = roles.get(name)
        rec["read_by"] = who or "NOBODY IN THIS RUN"
        rec["for_this_run"] = who is not None
    return snap


def debts() -> tuple[str, ...]:
    return tuple((k.name for k in KNOBS if k.debt))


def names() -> tuple[str, ...]:
    return tuple((k.name for k in KNOBS))


def passthrough() -> dict:
    given = job.current().settings
    return {n: given[n] for n in names() if n in given}
