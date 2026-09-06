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
* `Metric`: `needs` names the prerequisites (truth, pages, pdf, content);
  `run` measures, `report` prints the prose the metric always printed,
  `battery` runs its probes. Traits like "is order marked" are NOT
  prerequisites: they are per page and three-state, and the metric counts
  them and reports "over n pages of N".
* `run_battery`: the loop, once. It keeps the rules the three loops had
  learnt separately: the denominator is what was PRINTED; a probe that
  throws is a failed probe with the exception in its line; a probe may say
  "no data", which is neither caught nor missed; and the summary is a
  quantity, never the word "done".
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


NEEDS = ("truth", "pages", "pdf", "content")


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

    def battery(self, bench, run, log=print) -> int:
        """Uncaught probes, 0 when the metric can fail on every probe."""
        raise NotImplementedError


def applicable(metrics, bench, run, pages=None) -> list:
    """The metrics whose prerequisites this bench and run satisfy.

    Prerequisites only. Whether a trait is marked is the metric's own
    business, counted per page and reported as coverage, because a
    bench-level yes/no would either refuse `bench/hard` whole or score it
    whole, and the number the project prints there is "over 6 pages of 130".
    """
    have = {"pages"}
    if bench is not None and bench.truth_dir:
        have.add("truth")
    if bench is not None and bench.pdf:
        have.add("pdf")
    if run is not None and bench is not None and bench.has_content(pages):
        have.add("content")
    return [m for m in metrics if m.needs <= have]


# ------------------------------------------------------------- the battery

@dataclass(frozen=True)
class Probe:
    name: str          # what was spoiled
    want: str          # what must happen to the number
    fn: object         # () -> True | False | None | (bool|None, note)


def run_battery(probes, log=print, width=10) -> tuple:
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
        log(f"  {mark:>{width}}  {p.name}: {want}")
        seen += 1
        mute += ok is None
        bad += ok is False
    return seen, mute, bad


def battery_summary(title, seen, mute, bad, log=print) -> int:
    """The last line: a quantity, and the same shape for every battery."""
    log(f"{title} battery: probes {seen}, measured {seen - mute}, "
        f"nothing to measure with {mute} (see the 'no data' lines), "
        f"uncaught {bad}")
    return bad
