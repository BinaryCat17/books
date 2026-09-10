from backend import job
from backend.errors import Refusal


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
    Knob(
        "LAYOUT_ENDPOINT",
        "",
        "address of a served layout or hybrid model, the root its /backend routes hang from; read by the served adapter, and by the doctor to know whether there is one to ask; no default",
    ),
    Knob(
        "CROP_DPI",
        "",
        "crop sharpness for an export: empty is the scan's own resolution, or detection's when that cannot be told; a read and a crop do not read it, the model's window deciding there",
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
    Knob("BOOKSMITH_COMMIT", "", "the commit for a machine without git; empty = ask git in place"),
    Knob("MODEL_NAME", "PaddleOCR-VL-1.6-0.9B", "model name for vLLM and for the client"),
    Knob(
        "VLM_READER",
        "paddleocr-vl",
        "which READING adapter to call; the list is the read driver:READERS. It decides which prompt asks about which label, and in what shape the answer arrives",
    ),
    Knob(
        "VLM_TRANSPORT",
        "http",
        "how the question is delivered; the list is the read driver:build. Rental is NOT a third transport: on a rented card the same http looks at 127.0.0.1, where run.sh raised vLLM",
    ),
    Knob("VLM_ENDPOINT", "", "address of an OpenAI-compatible service, /v1 included; no default"),
    Knob("VLM_MAX_TOKENS", "4096", "ceiling of an answer, in tokens"),
    Knob("VLM_TIMEOUT_S", "120", "how long to wait for one answer, s"),
    Knob("VLM_RETRIES", "2", "how many times to repeat a DELIVERY REFUSAL (not an answer)"),
    Knob("VLM_CONCURRENCY", "4", "how many requests to keep in flight at once"),
    Knob("VLM_TEMPERATURE", "0", "VLM temperature; >0 makes the parse unrepeatable on purpose"),
    Knob("VLM_TOP_P", "1.0", "probability cutoff; one cuts nothing"),
    Knob("VLM_SEED", "0", "generation seed; decides at temperature > 0"),
    Knob("PASSES", "1", "how many reads; summing up is the runner's job, not the model's", debt=True),
    Knob("LOGPROBS", "1", "record token probabilities beside the page", debt=True),
    Knob("RESUME", "1", "whether to continue an interrupted run"),
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


def names() -> tuple[str, ...]:
    return tuple(k.name for k in KNOBS)


def passthrough() -> dict:
    given = job.current().settings
    return {n: given[n] for n in names() if n in given}
