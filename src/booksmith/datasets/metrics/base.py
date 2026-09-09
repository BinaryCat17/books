"""What a metric is, what it returns, and the one battery loop.

Three metrics grew three entry points with three argument orders, three
result shapes, three hand-written reports and three copies of the loop that
feeds them spoiled input. Every cross-detector comparison was then assembled
by hand in prose, and the prose records four times that the hand-assembled
numbers drifted. So:

* `Record`: one shape for what a metric returns. Each scalar carries its
  VALUE, what it was counted OVER (n of N), and WHY when it could not be
  counted -- "the truth carries no order" is a reason, not a zero, and a
  table that prints a blank there has lost the distinction the project keeps
  a rule about. `params` carries every threshold that rode into the number
  (they are module constants, not knobs: a threshold is a parameter of the
  measurement, not of the run, and it belongs in the measurement's record).
  `detail` is the raw result dict, unchanged, so the acceptance records lock
  the same dict they always did.
* `Metric`: `needs` names the prerequisites (truth, pages, pdf, content, read);
  `run` measures, `report` prints the prose the metric always printed,
  `probes` hands back the probes that spoil its input. Traits like "is order
  marked" are NOT prerequisites: they are per page and three-state, and the
  metric counts them and reports "over n pages of N".
* `run_probes`: the loop, once. It keeps the rules the three loops had
  learnt separately: the denominator is what was PRINTED; a probe that
  throws is a failed probe with the exception in its line; and a probe may
  say "no data", which is neither caught nor missed. The counts come back as
  numbers, so the caller prints a quantity and never the word "done".
"""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Scalar:
    """One number of a record.

    `count` is the fraction behind a share: (found, artefacts) for "2 of 3
    found". `over` is COVERAGE, what the value was counted over and out of
    what there was, in `unit`: "over 6 pages of 130". They are two things,
    and the first table printed both under one column and named neither;
    a reader could not tell "2/3 found" from "13/13 pages counted".
    `value` None only with a non-empty `why`.
    """
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
        """The record as read back from disk. `detail` comes back as JSON
        left it: integer keys (page indices) are strings there, so a record
        read back equals the original only after the original has been
        through JSON itself; the table test says so."""
        return cls(d["metric"], d["bench"], d["run"],
                   {k: Scalar.from_json(v) for k, v in d["scalars"].items()},
                   d.get("params", {}), d.get("detail", {}))


# THE FOUR PREREQUISITES, and the fourth is about the RUN, not the bench.
# `content` says the TRUTH carries characters; `read` says THIS RUN does. They
# were one for a while and the reading metric was therefore "applicable" to a
# detection run, which never writes a character: on every synthetic bench it
# reported CER 1 and WER 1 -- "this model read everything wrong" where the
# truth is "this run did no reading". Harmless while a book held one run and
# read it; noise wearing a number the moment six detectors are laid side by
# side, and the exact shape of "a zero from a check and a zero from not
# understanding".
NEEDS = ("truth", "pages", "pdf", "content", "read")


class Metric:
    """The contract. Subclasses set `name` and `needs` and implement three
    methods; `tests/test_metrics_contract.py` holds every registered one to
    it."""
    name: str = ""
    needs: frozenset = frozenset()

    def run(self, bench, run) -> Record:
        """Measure from the directories: parses them itself."""
        raise NotImplementedError

    def run_loaded(self, bench, run, truth: dict, pages: dict, note: str) -> Record:
        """Measure from pages already parsed, with the same-book note made
        once for the whole table."""
        raise NotImplementedError

    def report(self, rec: Record, log=print) -> None:
        raise NotImplementedError

    def probes(self, bench, run) -> list:
        """The probes that spoil this bench and run: one module per metric.

        `probes/<name>.py` beside the metric, so the metric module holds the
        measurement and the probe module the damage. Overriding this is for a
        metric whose probes are not a module of their own.
        """
        import importlib
        mod = importlib.import_module(
            f"booksmith.datasets.metrics.probes.{self.name}")
        return mod.probes(bench, run)


def prerequisites(bench, run, pages=None, run_pages=None) -> set:
    """WHICH OF `NEEDS` THIS BENCH AND RUN SUPPLY.

    Returned rather than only consumed, because the answer to "why is this
    metric not in the table" is `m.needs - have` and nothing else. Computed
    twice -- once to choose the metrics, once to explain the ones left out --
    it would be a second copy of the rules below, free to drift from them.
    """
    have = {"pages"}
    if bench is not None and bench.truth_dir:
        have.add("truth")
    if bench is not None and bench.pdf:
        have.add("pdf")
    # `truth_dir` FIRST, and not for speed: `has_content()` with no pages
    # given goes and parses the truth, and a book that has none raises there
    # rather than answering. `table.rows` happens to pass `pages`, so the
    # documented `pages=None` default was a landmine for the next caller --
    # asking "is this metric applicable" blew up instead of saying no.
    if (run is not None and bench is not None and bench.truth_dir
            and bench.has_content(pages)):
        have.add("content")
    # The run's pages are ASKED FOR, not fetched: a caller that has them
    # passes them (`table.rows` does), and a caller with only a stand-in run
    # says nothing and gets nothing. Fetching them here would make every
    # applicability question a directory walk.
    if run_pages is not None and run_has_content(run, run_pages):
        have.add("read")
    return have


def applicable(metrics, bench, run, pages=None, run_pages=None) -> list:
    """The metrics whose prerequisites this bench and run satisfy.

    Prerequisites only. Whether a trait is marked is the metric's own
    business, counted per page and reported as coverage, because a
    bench-level yes/no would either refuse `bench/hard` whole or score it
    whole, and the number the project prints there is "over 6 pages of 130".
    """
    have = prerequisites(bench, run, pages, run_pages)
    return [m for m in metrics if m.needs <= have]


def run_has_content(run, pages=None) -> bool:
    """Did THIS RUN put a character anywhere. Asked of the pages it wrote.

    Parsed here when the caller has not already: `table.rows` has them and
    passes them, and a metric asked on its own does not, and a walk of a few
    hundred small files is cheaper than a metric measuring nothing.
    """
    pages = pages if pages is not None else run.pages()
    return any(b.get("content") for p in pages.values() for b in p["blocks"])


# ------------------------------------------------------------- the battery

@dataclass(frozen=True)
class Probe:
    name: str          # what was spoiled
    want: str          # what must happen to the number
    fn: object         # () -> True | False | None | (bool|None, note)


def run_probes(probes, log=print) -> tuple:
    """Run every probe, print every line, return (seen, mute, bad).

    `seen` is counted from what was printed, never from `len(probes)`: a
    group that never arrived must not count as measured. A probe that
    throws is a failed probe and its line says what it threw. `None` is
    "nothing to measure with" -- printed as `no data`, counted apart.
    """
    seen = mute = bad = 0
    for p in probes:
        want = p.want
        try:
            ok = p.fn()
        except Exception as e:                                  # noqa: BLE001
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
