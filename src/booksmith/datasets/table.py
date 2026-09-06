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
from booksmith.datasets import metrics as registry
from booksmith.datasets.bench import Bench, Run, same_book

RESULTS = os.path.join(config.ROOT, "bench", "results")


def rows(bench: Bench, run: Run, which=None, log=print) -> list:
    """Records of every applicable metric (or of the named ones)."""
    pages = bench.pages()
    todo = [registry.BY_NAME[n] for n in which] if which else \
        registry.applicable(registry.METRICS, bench, run, pages)
    out = []
    for m in todo:
        log(f"{m.name}: {same_book(bench, run)}")
        out.append(m.run(bench, run))
    return out


def results_path(bench: Bench, run: Run) -> str:
    return os.path.join(RESULTS, f"{bench.name}-{run.label}.json")


def write_json(records, path: str, log=print) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump([r.to_json() for r in records], f, indent=1,
                  ensure_ascii=False, sort_keys=True)
        f.write("\n")
    log(f"{len(records)} records written to {path}")
    return path


def read_json(path: str) -> list:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _fmt(s) -> str:
    if s.value is None:
        return "—"
    if isinstance(s.value, float):
        return f"{s.value:.3f}"
    return str(s.value)


def render(records, log=print) -> None:
    """One line per scalar: metric, name, value, over, and the reason when
    the value is absent. Wide enough for a terminal, narrow enough to diff."""
    if not records:
        log("no applicable metric")
        return
    log(f"bench {records[0].bench}, run {records[0].run}")
    notes = []
    for r in records:
        for name, s in r.scalars.items():
            over = f"{s.over[0]}/{s.over[1]}" if s.over else ""
            line = f"  {r.metric:8} {name:24} {_fmt(s):>8}  {over:>12}"
            if s.value is None:
                notes.append((r.metric, name, s.why))
                line += f"  [{len(notes)}]"
            log(line)
        if r.params:
            log(f"  {r.metric:8} params: " + ", ".join(
                f"{k}={v}" for k, v in r.params.items()))
    for i, (m, name, why) in enumerate(notes, 1):
        log(f"  [{i}] {m}/{name}: {why}")
