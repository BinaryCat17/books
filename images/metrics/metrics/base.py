from dataclasses import dataclass, field
from metrics.log import log


@dataclass(frozen=True)
class Scalar:
    value: float | int | None
    count: tuple[int, int] | None = None
    over: tuple[int, int] | None = None
    unit: str = ""
    why: str | None = None
    per: dict[str, float] | None = None
    side: str = ""

    def __post_init__(self):
        if self.value is None and (not self.why):
            raise ValueError("a scalar without a value must say why")
        if self.value is not None and isinstance(self.value, bool):
            raise ValueError("a scalar is a number, not a flag")
        if self.over is not None and (not self.unit):
            raise ValueError("coverage without a unit says nothing")
        if self.side not in ("", "truth", "run"):
            raise ValueError(f"side is truth or run, not {self.side!r}")
        blocks = bool(self.per) and any("-b" in k for k in self.per)
        if blocks and (not self.side):
            raise ValueError("block anchors without a side name nobody's blocks")
        if not self.per:
            object.__setattr__(self, "per", None)
        if not blocks:
            object.__setattr__(self, "side", "")

    def to_json(self) -> dict:
        d = {"value": self.value}
        if self.count is not None:
            d["count"] = {"n": self.count[0], "of": self.count[1]}
        if self.over is not None:
            d["over"] = {"n": self.over[0], "of": self.over[1], "unit": self.unit}
        if self.why:
            d["why"] = self.why
        if self.per:
            d["per"] = self.per
            if self.side:
                d["side"] = self.side
        return d

    @classmethod
    def from_json(cls, d: dict) -> "Scalar":
        c, o = (d.get("count"), d.get("over"))
        return cls(
            d.get("value"),
            (c["n"], c["of"]) if c else None,
            (o["n"], o["of"]) if o else None,
            o["unit"] if o else "",
            d.get("why"),
            d.get("per"),
            d.get("side", ""),
        )


@dataclass
class Record:
    metric: str
    bench: str
    run: str
    scalars: dict = field(default_factory=dict)
    params: dict = field(default_factory=dict)
    detail: dict = field(default_factory=dict)
    identity: str | None = None
    source_sha256: str | None = None
    book: str | None = None
    truth_sha256: str | None = None

    def row(self) -> dict:
        out = {"metric": self.metric, "bench": self.bench, "run": self.run}
        out.update({k: s.value for k, s in self.scalars.items()})
        return out

    def to_json(self) -> dict:
        return {
            "metric": self.metric,
            "bench": self.bench,
            "run": self.run,
            "book": self.book,
            "identity": self.identity,
            "source_sha256": self.source_sha256,
            "truth_sha256": self.truth_sha256,
            "scalars": {k: s.to_json() for k, s in self.scalars.items()},
            "params": self.params,
            "detail": self.detail,
        }

    @classmethod
    def from_json(cls, d: dict) -> "Record":
        return cls(
            d["metric"],
            d["bench"],
            d["run"],
            {k: Scalar.from_json(v) for k, v in d["scalars"].items()},
            d.get("params", {}),
            d.get("detail", {}),
            d.get("identity"),
            d.get("source_sha256"),
            d.get("book"),
            d.get("truth_sha256"),
        )


CURRENT, STALE, NOT_RECORDED, NOT_CHECKED = ("current", "stale", "not recorded", "not checked")


PER = ("page", "block", "none")


@dataclass(frozen=True)
class Spec:
    name: str
    better: str
    gloss: str
    question: str = ""
    per: str = "none"
    side: str = ""
    unit: str = ""

    def __post_init__(self):
        if self.better not in ("higher", "lower", "neither"):
            raise ValueError(f"{self.name}: better must be higher, lower or neither, not {self.better!r}")
        if self.per not in PER:
            raise ValueError(f"{self.name}: per is one of {PER}, not {self.per!r}")
        if (self.per == "block") != (self.side in ("truth", "run")):
            raise ValueError(
                f"{self.name}: a scalar per block names whose blocks, truth or run, and no other does"
            )


class Metric:
    name: str = ""
    description: str = ""
    needs: frozenset = frozenset()
    scalars: tuple = ()

    def run(self, bench, run) -> Record:
        raise NotImplementedError

    def run_loaded(self, bench, run, truth: dict, pages: dict, note: str, want=None) -> Record:
        raise NotImplementedError

    def report(self, rec: Record) -> None:
        raise NotImplementedError

    def probes(self, bench, run) -> list:
        import importlib

        mod = importlib.import_module(f"metrics.probes.{self.name}")
        return mod.probes(bench, run)


def prerequisites(bench, run, pages=None, run_pages=None) -> set:
    have = {"pages"}
    if bench is not None and bench.truth_dir:
        have.add("truth")
    if bench is not None and bench.pdf:
        have.add("pdf")
    if run is not None and bench is not None and bench.truth_dir and bench.has_content(pages):
        have.add("content")
    if run_pages is not None and run_has_content(run, run_pages):
        have.add("read")
    return have


def applicable(metrics, bench, run, pages=None, run_pages=None) -> list:
    have = prerequisites(bench, run, pages, run_pages)
    return [m for m in metrics if m.needs <= have]


def run_has_content(run, pages=None) -> bool:
    pages = pages if pages is not None else run.pages()
    return any(b.get("content") for p in pages.values() for b in p["blocks"])


@dataclass(frozen=True)
class Probe:
    name: str
    want: str
    fn: object


def run_probes(probes) -> tuple:
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
        mark = "no data" if ok is None else "ok " if ok else "NO"
        log(f"  {mark:>10}  {p.name}: {want}")
        seen += 1
        mute += ok is None
        bad += ok is False
    return (seen, mute, bad)
