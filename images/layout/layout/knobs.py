from layout import job
from layout.errors import Refusal


class Knob:
    __slots__ = ("name", "default", "what", "debt")

    def __init__(self, name: str, default: str, what: str, debt: bool = False) -> None:
        self.name, self.default, self.what = (name, default, what)
        self.debt = bool(debt)


KNOBS = (
    Knob(
        "LAYOUT_ADAPTER",
        "doclayout",
        "which adapter this container serves: doclayout, docling, docling-egret or yolox",
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
        "YOLOX_WEIGHTS", "", "which YOLOX weights to take: yolox_l0.05.onnx (the default) or yolox_tiny.onnx"
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
