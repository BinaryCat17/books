"""Every applicable metric on one bench and one run: rows, one table, JSON.

The numbers used to land on stdout only, three commands with three argument
shapes, and every comparison between detectors was typed into prose by
hand. This is the one place they are laid side by side and written down.
A null value prints its reason as a footnote, never a blank: "the truth
carries no order" and "zero agreement" must not read alike.
"""
import json
import os
import time

from booksmith.core import config, stamp
from booksmith.core.errors import Refusal
from booksmith.datasets import metrics as registry
from booksmith.datasets.bench import Bench, Run, same_book

RESULTS = os.path.join(config.ROOT, "results")


def rows(bench: Bench, run: Run, which=None, log=print) -> list:
    """Records of every applicable metric, or of the named ones.

    The truth is parsed ONCE here and the run's pages once; the metrics take
    the dicts. `which` names metrics by name and may not name one that is
    not applicable: a table with a line the bench cannot support is a
    number about nothing, and the first edition wrote one.
    """
    # THE TRUTH IS PARSED ONLY IF THERE IS ANY. A book with no `truth/` is a
    # legal thing to measure -- ink and column jumps need none -- and this
    # line raised `truth of <book>: no directory` before applicability was
    # ever consulted, so the truth-free metrics could not be reached on the
    # only runs that have a level two. An empty dict is the honest value:
    # `applicable` withholds "truth" and "content" from it by itself.
    pages = bench.pages() if bench.truth_dir else {}
    # BOTH SIDES BEFORE THE QUESTION. The run's pages decide whether a reading
    # metric applies at all, and they are needed a few lines below anyway.
    model = run.pages()
    # `applicable` DECIDES, and `prerequisites` only explains. Filtering
    # inline here on `have` was the same arithmetic and read as harmless --
    # and it took `applicable` off this path, so the battery's mutation of
    # it ("applicability ignores whether the truth has content") stopped
    # reaching the table and went UNCAUGHT. An instrument that can no longer
    # fail is the one thing this project does not allow.
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
    # WHAT WAS WITHHELD, AND WHAT IT WANTED. A metric that does not apply
    # produced no line at all: on a book with no truth, `contour` and `text`
    # simply were not there, and the reader had a short table and no way to
    # tell "this book cannot answer that" from "the instrument was never
    # run" -- the project's two zeros, in the one place that had no word for
    # either. The needs come from the metric's own declaration and `have`
    # from `prerequisites`, which is the set `applicable` itself filters on,
    # so the explanation cannot drift from the decision.
    for m in registry.METRICS:
        if m in can:
            continue
        log(f"{m.name}: NOT MEASURED, this book and run give no "
            f"{', '.join(sorted(m.needs - have))}")
    note = same_book(bench, run)
    out = []
    for m in todo:
        log(f"{m.name}: {note}")
        out.append(m.run_loaded(bench, run, pages, model, note))
    return out


def results_path(bench: Bench, run: Run, which=None) -> str:
    """Where the table lands. A selection gets its own name: a partial
    table must not replace the full one under the same file.

    AND SO DOES A LEVEL. The label is the MODEL's own name, so a detector
    and a reader can carry the same one, and the first edition keyed the
    file on (book, label) alone -- two levels of one model, one file, the
    second silently overwriting the first. `detect` keeps the bare name so
    the runs already on disk are not renamed for nothing.
    """
    tail = "-only-" + "+".join(which) if which else ""
    kind = run.kind
    level = f"{kind}-" if kind and kind != "detect" else ""
    return os.path.join(RESULTS, f"{bench.name}-{level}{run.label}{tail}.json")


def write_json(records, path: str, log=print, kind: str = "detect") -> str:
    """The records, under a header saying WHEN, BY WHICH CODE and OF WHICH
    LEVEL.

    The file was a bare list, and a directory of them could silently mix
    numbers computed by different code -- which happened inside one hour: a
    prerequisite was corrected, five models were measured after it and one
    before, and the stale file's twelve extra rows read as a difference
    between MODELS. A cross-model table is only a comparison if every cell
    came from the same tree, so the commit rides in the file and the reader
    can refuse.

    `kind` rides along for the same reason one level down. A LEVEL-TWO run
    carries the boxes of whatever DETECTOR made its pages, so its ink
    numbers describe that detector and not the reader whose name is on the
    directory. Put in the model column of a cross-detector table, the reader
    appears beside six detectors with a number it did not earn -- the
    "looks sensible and means nothing" case. The report reads this field and
    leaves such a run out, saying how many it left; a file written before
    the field existed is `detect`, which is what all of them were.
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"when": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                   "kind": kind or "detect",
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
    """The whole file: `when`, `commit` and the raw records.

    A file without the header is REFUSED rather than read as records: it was
    written by other code, which is the one thing the header exists to say.
    """
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
    except ValueError as e:
        # A HALF-WRITTEN FILE IS WHAT A RUNNING SWEEP LEAVES, and this
        # function's own docstring promises a Refusal for a file it cannot
        # use. It raised a bare JSONDecodeError instead.
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
