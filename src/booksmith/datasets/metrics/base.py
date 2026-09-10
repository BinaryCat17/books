"""What a metric is, what it returns, and the one probe loop.

`Record` is one shape for what a metric returns: each scalar carries its value,
what it was counted OVER (n of N), and WHY when it could not be counted -- a
reason is not a zero -- beside the thresholds that rode in and the raw detail
dict. `Metric` declares `needs` and implements `run`, `report` and `probes`;
traits like "is order marked" are not prerequisites but per-page counts. In
`run_probes` the denominator is what was PRINTED, a probe that throws is a
failed probe, and "no data" is neither caught nor missed.
"""
from dataclasses import dataclass, field
from booksmith.core.log import log


@dataclass(frozen=True)
class Scalar:
    """One number of a record. `count` is the fraction behind a share (2 of 3
    found), `over` is COVERAGE in `unit` (over 6 pages of 130) -- two different
    things -- and `value` is None only with a non-empty `why`."""
    value: float | int | None
    count: tuple[int, int] | None = None    # (numerator, denominator) of a share
    over: tuple[int, int] | None = None     # (counted, of), coverage
    unit: str = ""                          # of `over`: pages, blocks, pairs
    why: str | None = None

    def __post_init__(self):
        if self.value is None and not self.why:
            raise ValueError("a scalar without a value must say why")
        if self.value is not None and isinstance(self.value, bool):
            raise ValueError("a scalar is a number, not a flag")
        if self.over is not None and not self.unit:
            raise ValueError("coverage without a unit says nothing")

    def to_json(self) -> dict:
        d = {"value": self.value}
        if self.count is not None:
            d["count"] = {"n": self.count[0], "of": self.count[1]}
        if self.over is not None:
            d["over"] = {"n": self.over[0], "of": self.over[1], "unit": self.unit}
        if self.why:
            d["why"] = self.why
        return d

    @classmethod
    def from_json(cls, d: dict) -> "Scalar":
        c, o = d.get("count"), d.get("over")
        return cls(d.get("value"), (c["n"], c["of"]) if c else None,
                   (o["n"], o["of"]) if o else None, o["unit"] if o else "",
                   d.get("why"))


@dataclass
class Record:
    metric: str
    bench: str
    run: str
    scalars: dict = field(default_factory=dict)      # name -> Scalar
    params: dict = field(default_factory=dict)
    detail: dict = field(default_factory=dict)

    def row(self) -> dict:
        """One flat line of the table: identities, then the values."""
        out = {"metric": self.metric, "bench": self.bench, "run": self.run}
        out.update({k: s.value for k, s in self.scalars.items()})
        return out

    def to_json(self) -> dict:
        return {"metric": self.metric, "bench": self.bench, "run": self.run,
                "scalars": {k: s.to_json() for k, s in self.scalars.items()},
                "params": self.params, "detail": self.detail}

    @classmethod
    def from_json(cls, d: dict) -> "Record":
        """The record as read back from disk. `detail` comes back as JSON left
        it: integer page indices are strings there, so a record read back equals
        the original only after the original has been through JSON itself."""
        return cls(d["metric"], d["bench"], d["run"],
                   {k: Scalar.from_json(v) for k, v in d["scalars"].items()},
                   d.get("params", {}), d.get("detail", {}))


# `content` says the TRUTH carries characters, `read` that THIS RUN does: one
# prerequisite for both makes the reading metric "applicable" to a run that
# never wrote a character, and it answers CER 1 instead of "no reading here".
NEEDS = ("truth", "pages", "pdf", "content", "read")


@dataclass(frozen=True)
class Spec:
    """One scalar a metric publishes: which way is better, and what it means.
    `better` has no default -- a guessed direction tells a reader to maximise a
    failure mode; `question` names the report section this scalar headlines."""
    name: str
    better: str
    gloss: str
    question: str = ""

    def __post_init__(self):
        if self.better not in ("higher", "lower", "neither"):
            raise ValueError(f"{self.name}: better must be higher, lower or "
                             f"neither, not {self.better!r}")


class Metric:
    """The contract. Subclasses set `name` and `needs` and implement three
    methods; `tests/contract/test_metrics_contract.py` holds every registered one to
    it."""
    name: str = ""
    needs: frozenset = frozenset()
    scalars: tuple = ()

    def run(self, bench, run) -> Record:
        """Measure from the directories: parses them itself."""
        raise NotImplementedError

    def run_loaded(self, bench, run, truth: dict, pages: dict, note: str) -> Record:
        """Measure from pages already parsed, with the same-book note made
        once for the whole table."""
        raise NotImplementedError

    def report(self, rec: Record) -> None:
        raise NotImplementedError

    def probes(self, bench, run) -> list:
        """The probes that spoil this bench and run: `probes/<name>.py` beside
        the metric, so the metric module holds the measurement and the probe
        module the damage. Override only for a metric with no probe module."""
        import importlib
        mod = importlib.import_module(
            f"booksmith.datasets.metrics.probes.{self.name}")
        return mod.probes(bench, run)


def prerequisites(bench, run, pages=None, run_pages=None) -> set:
    """Which of `NEEDS` this bench and run supply. Returned rather than only
    consumed: the answer to "why is this metric not in the table" is
    `m.needs - have`, and a second computation would be free to drift."""
    have = {"pages"}
    if bench is not None and bench.truth_dir:
        have.add("truth")
    if bench is not None and bench.pdf:
        have.add("pdf")
    # `truth_dir` first, and not for speed: `has_content()` with no pages given
    # parses the truth, and a book with none raises instead of answering.
    if (run is not None and bench is not None and bench.truth_dir
            and bench.has_content(pages)):
        have.add("content")
    # The run's pages are asked for, not fetched: fetching them here would make
    # every applicability question a directory walk.
    if run_pages is not None and run_has_content(run, run_pages):
        have.add("read")
    return have


def applicable(metrics, bench, run, pages=None, run_pages=None) -> list:
    """The metrics whose prerequisites this bench and run satisfy. Prerequisites
    only: whether a trait is marked is the metric's own business, counted per
    page, a bench-level yes/no refusing or scoring a mixed bench whole."""
    have = prerequisites(bench, run, pages, run_pages)
    return [m for m in metrics if m.needs <= have]


def run_has_content(run, pages=None) -> bool:
    """Did this run put a character anywhere, asked of the pages it wrote.
    Parsed here when the caller has not already: a walk of a few hundred small
    files is cheaper than a metric measuring nothing."""
    pages = pages if pages is not None else run.pages()
    return any(b.get("content") for p in pages.values() for b in p["blocks"])


# ------------------------------------------------------------- the probes

@dataclass(frozen=True)
class Probe:
    name: str          # what was spoiled
    want: str          # what must happen to the number
    fn: object         # () -> True | False | None | (bool|None, note)


def run_probes(probes) -> tuple:
    """Run every probe, print every line, return (seen, mute, bad). `seen` is
    counted from what was printed, never from `len(probes)`; a probe that throws
    is a failed probe; `None` is "nothing to measure with", counted apart."""
    seen = mute = bad = 0
    for p in probes:
        want = p.want
        try:
            ok = p.fn()
        except Exception as e:
            ok = False
            want = f"{want} — THE PROBE THREW {type(e).__name__}: {e}"
        if isinstance(ok, tuple):
            ok, note = ok
            want = f"{want} [{note}]"
        mark = "no data" if ok is None else ("ok " if ok else "NO")
        log(f"  {mark:>10}  {p.name}: {want}")
        seen += 1
        mute += ok is None
        bad += ok is False
    return seen, mute, bad
