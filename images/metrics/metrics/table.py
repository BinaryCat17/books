import dataclasses
from metrics import job
from metrics.errors import Refusal
import metrics as registry
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
            out = sorted(i for i in want if trait_state(pages[i].get("meta") or {}, "labelled") != "yes")
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
            raise Refusal(f"no metric named {', '.join(unknown)}; there are {', '.join(registry.BY_NAME)}")
        off = [n for n in which if registry.BY_NAME[n] not in can]
        if off:
            raise Refusal(
                f"{', '.join(off)} cannot be measured on {bench.name} with run {run.label}: needs "
                + "; ".join(f"{n}: {', '.join(sorted(registry.BY_NAME[n].needs))}" for n in off)
            )
        todo = [registry.BY_NAME[n] for n in which]
    else:
        todo = can
    for m in registry.METRICS:
        if m in can:
            continue
        log(f"{m.name}: NOT MEASURED, this book and run give no {', '.join(sorted(m.needs - have))}")
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
