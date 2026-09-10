from fleet import job
from fleet.errors import Refusal


class Knob:
    __slots__ = ("name", "default", "what", "debt")

    def __init__(self, name: str, default: str, what: str, debt: bool = False) -> None:
        self.name, self.default, self.what = (name, default, what)
        self.debt = bool(debt)


KNOBS = (
    Knob(
        "MIN_LINK_MBPS",
        "2.0",
        "the link threshold in Mbps, measured to us, below which a machine is rejected, and blacklisted only when a faster witness makes the link the machine's own; it tells a broken machine from a working one, not a slow from a fast, and is not derived from the job's size",
    ),
    Knob(
        "BOOKSMITH_LEDGER",
        "",
        "where to write the run journal; empty = runs/ledger.jsonl. The machine blacklist lives beside the journal",
    ),
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


def names() -> tuple[str, ...]:
    return tuple(k.name for k in KNOBS)
