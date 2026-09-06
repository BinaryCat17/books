"""Every applicable metric on one bench and one run: rows, one table, JSON.

The numbers used to land on stdout only, three commands with three argument
shapes, and every comparison between detectors was typed into prose by
hand. This is the one place they are laid side by side and written down.
A null value prints its reason as a footnote, never a blank: "the truth
carries no order" and "zero agreement" must not read alike.
"""
import json
import os

from booksmith.core import config
from booksmith.core.errors import Refusal
from booksmith.datasets import metrics as registry
from booksmith.datasets.bench import Bench, Run, same_book

RESULTS = os.path.join(config.ROOT, "bench", "results")


def rows(bench: Bench, run: Run, which=None, log=print) -> list:
    """Records of every applicable metric, or of the named ones.

    The truth is parsed ONCE here and the run's pages once; the metrics take
    the dicts. `which` names metrics by name and may not name one that is
    not applicable: a table with a line the bench cannot support is a
    number about nothing, and the first edition wrote one.
    """
    pages = bench.pages()
    can = registry.base.applicable(registry.METRICS, bench, run, pages)
    if which:
        unknown = [n for n in which if n not in registry.BY_NAME]
        if unknown:
            raise Refusal(f"no metric named {', '.join(unknown)}; there are "
                          f"{', '.join(registry.BY_NAME)}")
        off = [n for n in which if registry.BY_NAME[n] not in can]
        if off:
            raise Refusal(f"{', '.join(off)} cannot be measured on {bench.name} "
                          f"with run {run.label}: needs "
                          + "; ".join(f"{n}: {', '.join(sorted(registry.BY_NAME[n].needs))}"
                                      for n in off))
        todo = [registry.BY_NAME[n] for n in which]
    else:
        todo = can
    model = run.pages()
    note = same_book(bench, run)
    out = []
    for m in todo:
        log(f"{m.name}: {note}")
        out.append(m.run_loaded(bench, run, pages, model, note))
    return out


def results_path(bench: Bench, run: Run, which=None) -> str:
    """Where the table lands. A selection gets its own name: a partial
    table must not replace the full one under the same file."""
    tail = "-only-" + "+".join(which) if which else ""
    return os.path.join(RESULTS, f"{bench.name}-{run.label}{tail}.json")


def write_json(records, path: str, log=print) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump([r.to_json() for r in records], f, indent=1,
                  ensure_ascii=False, sort_keys=True)
        f.write("\n")
    log(f"{len(records)} records written to {path}")
    return path


def read_json(path: str) -> list:
    """The records back from disk, as `Record`s."""
    from booksmith.datasets.metrics.base import Record
    with open(path, encoding="utf-8") as f:
        return [Record.from_json(d) for d in json.load(f)]


def _fmt(s) -> str:
    if s.value is None:
        return "—"
    if isinstance(s.value, float):
        return f"{s.value:.3f}"
    return str(s.value)


def render(records, log=print) -> None:
    """One line per scalar: metric, name, value, the counts behind a share,
    the coverage in its unit, and a footnote where the value is absent."""
    if not records:
        log("no applicable metric")
        return
    log(f"bench {records[0].bench}, run {records[0].run}")
    log(f"  {'metric':8} {'scalar':24} {'value':>8}  {'count':>16}  {'over':>20}")
    notes = []
    for r in records:
        for name, s in r.scalars.items():
            count = f"{s.count[0]}/{s.count[1]}" if s.count else ""
            over = f"{s.over[0]}/{s.over[1]} {s.unit}" if s.over else ""
            line = f"  {r.metric:8} {name:24} {_fmt(s):>8}  {count:>16}  {over:>20}"
            if s.value is None:
                notes.append((r.metric, name, s.why))
                line += f"  [{len(notes)}]"
            log(line)
        if r.params:
            log(f"  {r.metric:8} params: " + ", ".join(
                f"{k}={v}" for k, v in r.params.items()))
    for i, (m, name, why) in enumerate(notes, 1):
        log(f"  [{i}] {m}/{name}: {why}")
