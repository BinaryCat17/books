"""Every applicable metric on one bench and one run: rows, one table, JSON"""

import dataclasses
import json
import os
import time
from metrics import job
from metrics import identity as stamp
from metrics.errors import Refusal
from metrics import metrics as registry
from metrics.bench import Bench, Run, book_of, labelled_of, labelled_said, same_book, trait_state
from metrics.log import log


def rows(bench: Bench, run: Run, which=None, pages_want=None) -> list:
    pages = bench.pages() if bench.truth_dir else {}
    model = run.pages()
    if pages_want is not None:
        want = set(pages_want)
        if not want:
            raise Refusal("an empty page set: nothing to measure, which is not a zero")
        for side, have in (("the run", model), ("the truth", pages)):
            gone = sorted(want - set(have)) if have or side == "the run" else []
            if gone:
                raise Refusal(f"{side} has no pages {gone[:5]}: nothing to measure there")
        if pages and labelled_said(labelled_of(pages)):
            out = sorted(
                (i for i in want if trait_state(pages[i].get("meta") or {}, "labelled") != "yes")
            )
            if out:
                raise Refusal(
                    f"pages {out[:5]} are not labelled in this truth, which names its labelled pages: nothing to compare there"
                )
        pages = {i: p for i, p in pages.items() if i in want}
        model = {i: p for i, p in model.items() if i in want}
    can = registry.base.applicable(registry.METRICS, bench, run, pages, model)
    have = registry.base.prerequisites(bench, run, pages, model)
    if which:
        unknown = [n for n in which if n not in registry.BY_NAME]
        if unknown:
            raise Refusal(
                f"no metric named {', '.join(unknown)}; there are {', '.join(registry.BY_NAME)}"
            )
        off = [n for n in which if registry.BY_NAME[n] not in can]
        if off:
            raise Refusal(
                f"{', '.join(off)} cannot be measured on {bench.name} with run {run.label}: needs "
                + "; ".join((f"{n}: {', '.join(sorted(registry.BY_NAME[n].needs))}" for n in off))
            )
        todo = [registry.BY_NAME[n] for n in which]
    else:
        todo = can
    for m in registry.METRICS:
        if m in can:
            continue
        log(
            f"{m.name}: NOT MEASURED, this book and run give no {', '.join(sorted(m.needs - have))}"
        )
    note = same_book(bench, run)
    out = []
    for i, m in enumerate(todo, 1):
        job.current().check()
        log(f"{m.name}: {note}", n=i, of=len(todo), metric=m.name)
        rec = m.run_loaded(bench, run, pages, model, note, pages_want)
        out.append(
            dataclasses.replace(
                rec,
                book=book_of(bench),
                identity=run.snapshot.get("identity"),
                source_sha256=run.sha256,
            )
        )
    return out


def pages_tail(pages) -> str:
    out, seq = ([], sorted(set(pages)))
    i = 0
    while i < len(seq):
        j = i
        while j + 1 < len(seq) and seq[j + 1] == seq[j] + 1:
            j += 1
        out.append(str(seq[i]) if i == j else f"{seq[i]}-{seq[j]}")
        i = j + 1
    return "+".join(out)


def results_path(bench: Bench, run: Run, which=None, store: str | None = None, pages=None) -> str:
    from metrics import store as book_mod

    store = store or book_mod.store_of(bench.root)
    prefix = "processed-" if book_of(bench).startswith("processed/") else ""
    tail = "-only-" + "+".join(which) if which else ""
    if pages is not None:
        tail += "-pages-" + pages_tail(pages)
    kind = run.kind
    level = f"{kind}-" if kind and kind != "detect" else ""
    return os.path.join(store, "results", f"{prefix}{bench.name}-{level}{run.label}{tail}.json")


def write_json(records, path: str, kind: str = "detect", pages=None, only=None) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "when": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "kind": kind or "detect",
                "pages": sorted(set(pages)) if pages is not None else None,
                "only": list(only) if only else None,
                "commit": stamp.commit(ignore=stamp.OUTPUT_PATHS),
                "records": [r.to_json() for r in records],
            },
            f,
            indent=1,
            ensure_ascii=False,
            sort_keys=True,
        )
        f.write("\n")
    log(f"{len(records)} records written to {path}")
    return path


def read_json(path: str) -> list:
    from metrics.base import Record

    return [Record.from_json(d) for d in read_file(path)["records"]]


def read_file(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
    except ValueError as e:
        raise Refusal(
            f"{path} is not readable JSON ({e}). A results file is written whole at the end of `books bench all`; a broken one is a run that was interrupted. Measure it again."
        ) from None
    if not isinstance(d, dict) or "records" not in d:
        raise Refusal(
            f"{path} has no header: it was written before results carried the commit that computed them, and a table built from it would mix numbers from two trees. Re-run `books bench all` for it."
        )
    return d


def _fmt(s) -> str:
    if s.value is None:
        return "—"
    if isinstance(s.value, float):
        return f"{s.value:.3f}"
    return str(s.value)


def render(records) -> None:
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
            log(f"  {r.metric:8} params: " + ", ".join((f"{k}={v}" for k, v in r.params.items())))
    for i, (m, name, why) in enumerate(notes, 1):
        log(f"  [{i}] {m}/{name}: {why}")
