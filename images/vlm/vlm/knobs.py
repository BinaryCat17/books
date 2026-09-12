from vlm import job
from vlm.errors import Refusal


class Knob:
    __slots__ = ("name", "default", "what", "debt")

    def __init__(self, name: str, default: str, what: str, debt: bool = False) -> None:
        self.name, self.default, self.what = (name, default, what)
        self.debt = bool(debt)


KNOBS = (
    Knob("MODEL_NAME", "PaddleOCR-VL-1.6-0.9B", "model name for vLLM and for the client"),
    Knob("VL_MODEL_DIR", "", "VLM weights dir; run.sh sets it, vLLM reads"),
    Knob("PORT", "8118", "port of the vLLM service on the machine"),
    Knob("VLLM_USE_FLASHINFER_SAMPLER", "0", "flashinfer sampler in vLLM"),
    Knob("VLM_TIMEOUT_S", "120", "how long to wait for one answer, s"),
    Knob("BOOKSMITH_COMMIT", "", "the commit the image was built at; empty when nothing stamped it"),
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


def names() -> tuple[str, ...]:
    return tuple(k.name for k in KNOBS)
