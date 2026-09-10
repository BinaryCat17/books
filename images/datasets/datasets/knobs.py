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
    Knob(
        "CROP_DPI",
        "",
        "crop sharpness for an export: empty is the scan's own resolution, or detection's when that cannot be told; a read and a crop do not read it, the model's window deciding there",
    ),
    Knob("CROP_MARGIN", "0", "margin around the box when cropping, in box fractions"),
    Knob("SYNTH_SEED", "1", "seed of the synthetic bench"),
    Knob("SYNTH_AGING", "old", "bench ageing profile: clean|scan|old|decayed"),
    Knob("BOOKSMITH_COMMIT", "", "the commit for a machine without git; empty = ask git in place"),
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


def names() -> tuple[str, ...]:
    return tuple(k.name for k in KNOBS)
