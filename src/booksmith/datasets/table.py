"""Every applicable metric on one bench and one run: rows, one table, JSON.

The one place the numbers are laid side by side and written down. A null value
prints its reason as a footnote, never a blank: "the truth carries no order"
and "zero agreement" must not read alike.
"""
import dataclasses
import json
import os
import time

from booksmith.core import job, stamp
from booksmith.core.errors import Refusal
from booksmith.datasets import metrics as registry
from booksmith.datasets.bench import (Bench, Run, book_of, labelled_of, labelled_said,
                                      same_book, trait_state)
from booksmith.core.log import log



def rows(bench: Bench, run: Run, which=None, pages_want=None) -> list:
    """Records of every applicable metric, or of the named ones. Truth and the
    run's pages are parsed once here and the metrics take the dicts; `which` may
    not name a metric this bench and run cannot support. `pages_want` cuts
    both sides to a set of page indices before any metric asks, so a number
    can be had for one page; None is the whole book. Each record carries
    the run's identity and the scan's hash out of the run's snapshot."""
    # The truth is parsed only if there is any: a book with no `truth/` is a
    # legal thing to measure, and `applicable` withholds "truth" and "content"
    # from an empty dict by itself.
    pages = bench.pages() if bench.truth_dir else {}
    # BOTH SIDES BEFORE THE QUESTION. The run's pages decide whether a reading
    # metric applies at all, and they are needed a few lines below anyway.
    model = run.pages()
    if pages_want is not None:
        want = set(pages_want)
        if not want:
            raise Refusal("an empty page set: nothing to measure, which is not a zero")
        for side, have in (("the run", model), ("the truth", pages)):
            gone = sorted(want - set(have)) if have or side == "the run" else []
            if gone:
                raise Refusal(f"{side} has no pages {gone[:5]}: nothing to measure there")
        # A truth that names its labelled pages is a fact of the whole truth,
        # decided here where the whole is in hand: a page cut out alone would
        # tell the metric nothing of it, and be compared where the book's
        # own measure leaves it out.
        if pages and labelled_said(labelled_of(pages)):
            out = sorted(i for i in want
                         if trait_state(pages[i].get("meta") or {}, "labelled") != "yes")
            if out:
                raise Refusal(f"pages {out[:5]} are not labelled in this truth, "
                              f"which names its labelled pages: nothing to "
                              f"compare there")
        pages = {i: p for i, p in pages.items() if i in want}
        model = {i: p for i, p in model.items() if i in want}
    # `applicable` decides and `prerequisites` only explains: filtering inline
    # on `have` would take `applicable` off this path, where the probes'
    # mutation of it must still reach the table.
    can = registry.base.applicable(registry.METRICS, bench, run, pages, model)
    have = registry.base.prerequisites(bench, run, pages, model)
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
    # What was withheld, and what it wanted: a metric that does not apply must
    # not simply be absent, or "this book cannot answer that" reads as "the
    # instrument was never run". The needs and `have` come from one place, so
    # the explanation cannot drift from the decision.
    for m in registry.METRICS:
        if m in can:
            continue
        log(f"{m.name}: NOT MEASURED, this book and run give no "
            f"{', '.join(sorted(m.needs - have))}")
    note = same_book(bench, run)
    out = []
    for i, m in enumerate(todo, 1):
        # Asked before every metric: a measure is a job, and a job can be stopped.
        job.current().check()
        log(f"{m.name}: {note}", n=i, of=len(todo), metric=m.name)
        rec = m.run_loaded(bench, run, pages, model, note, pages_want)
        out.append(dataclasses.replace(rec, book=book_of(bench),
                                       identity=run.snapshot.get("identity"),
                                       source_sha256=run.sha256))
    return out


def pages_tail(pages) -> str:
    """A page set as a file-name part: runs of consecutive indices as ranges."""
    out, seq = [], sorted(set(pages))
    i = 0
    while i < len(seq):
        j = i
        while j + 1 < len(seq) and seq[j + 1] == seq[j] + 1:
            j += 1
        out.append(str(seq[i]) if i == j else f"{seq[i]}-{seq[j]}")
        i = j + 1
    return "+".join(out)


def results_path(bench: Bench, run: Run, which=None, store: str | None = None,
                 pages=None) -> str:
    """Where the table lands, under the store's `results/`, the store being
    the one the bench lies in unless named. A selection gets its own name,
    and so does a page set, and so does a level: a detector and a reader
    can share a label, and one file for both would overwrite. A bench keeps
    its bare name and a book under `processed/` is prefixed, since the two
    roots can hold one name; `detect` keeps the bare level, renaming
    nothing on disk."""
    from booksmith.core import book as book_mod
    store = store or book_mod.store_of(bench.root)
    prefix = "processed-" if book_of(bench).startswith("processed/") else ""
    tail = "-only-" + "+".join(which) if which else ""
    if pages is not None:
        tail += "-pages-" + pages_tail(pages)
    kind = run.kind
    level = f"{kind}-" if kind and kind != "detect" else ""
    return os.path.join(store, "results", f"{prefix}{bench.name}-{level}{run.label}{tail}.json")


def write_json(records, path: str, kind: str = "detect", pages=None,
               only=None) -> str:
    """The records under a header saying when, by which code, of which
    level, over which pages and of which metrics. The commit rides in the
    file so a cross-model table comes from one tree; `kind` keeps a
    level-two run, whose boxes are a detector's, out of the model column;
    `pages` is the set measured, null for the whole book, and `only` the
    metrics asked for, null for every applicable one: the report renders
    only a whole measure, and reads that off the header."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"when": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                   "kind": kind or "detect",
                   "pages": sorted(set(pages)) if pages is not None else None,
                   "only": list(only) if only else None,
                   # Ignoring the results themselves: a pass that writes 54
                   # of these would otherwise dirty the tree with its own
                   # first file and stamp the other 53 unusable.
                   "commit": stamp.commit(ignore=stamp.OUTPUT_PATHS),
                   "records": [r.to_json() for r in records]},
                  f, indent=1, ensure_ascii=False, sort_keys=True)
        f.write("\n")
    log(f"{len(records)} records written to {path}")
    return path


def read_json(path: str) -> list:
    """The records back from disk, as `Record`s."""
    from booksmith.datasets.metrics.base import Record
    return [Record.from_json(d) for d in read_file(path)["records"]]


def read_file(path: str) -> dict:
    """The whole file: `when`, `commit` and the raw records. A file with no
    header is REFUSED rather than read as records: it was written by other code,
    which is the one thing the header exists to say."""
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
    except ValueError as e:
        # A half-written file is what an interrupted sweep leaves, and this
        # promises a Refusal for a file it cannot use.
        raise Refusal(
            f"{path} is not readable JSON ({e}). A results file is written "
            f"whole at the end of `books bench all`; a broken one is a run "
            f"that was interrupted. Measure it again.") from None
    if not isinstance(d, dict) or "records" not in d:
        raise Refusal(
            f"{path} has no header: it was written before results carried "
            f"the commit that computed them, and a table built from it would "
            f"mix numbers from two trees. Re-run `books bench all` for it.")
    return d


def _fmt(s) -> str:
    if s.value is None:
        return "—"
    if isinstance(s.value, float):
        return f"{s.value:.3f}"
    return str(s.value)


def render(records) -> None:
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
