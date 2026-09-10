"""What the reader got wrong that can be seen WITHOUT truth.

Truth for a real scan does not exist, so this file measures the defects a reader
can be caught in by looking only at what it returned. The FABRICATED CHART is the
one that matters: asked to read a picture of a curve, the model returns a table of
numbers read off it by eye, and they go into the book as text. The rule asks for
delimited numeric rows under a `chart` LABEL, both together. It does not claim
the numbers are wrong -- nothing here can, without the page -- only that they
were invented from a picture.
"""
import re

from booksmith.datasets.metrics.base import Metric, Record, Scalar, Spec
from booksmith.core import page
from booksmith.core.log import log

# A cell that is a bare number: what a fabricated chart table is made of.
NUMBER = re.compile(r"^[-+]?\d+(?:[.,]\d+)?$")
# Half the filled cells or more, and the answer is data rather than prose.
NUMERIC_SHARE = 0.5
# Two rows is a table; one delimited line is a caption with a bar in it.
MIN_ROWS = 2
# The shingle for degenerate repetition, and the share of it that must be
# repeats: at 0.30 over stripped text, 19 of 20 flagged blocks are genuine.
SHINGLE = 20
LOOP_SHARE = 0.30
_MARKUP = re.compile(r"<(?:fcel|ecel|lcel|ucel|xcel|ched|rhed|srow|nl)>"
                     r"|\\[a-zA-Z]+|[{}&$^_]")


def _rows(text):
    """The answer as delimited rows, or [] if it is not one."""
    out = []
    for line in text.splitlines():
        if "|" in line:
            out.append([c.strip() for c in line.split("|")])
    return out


def is_data_table(text):
    """Is this answer a table of numbers rather than words."""
    rows = _rows(text)
    if len(rows) < MIN_ROWS:
        return False
    filled = [c for r in rows for c in r if c]
    if not filled:
        return False
    return (sum(1 for c in filled if NUMBER.match(c)) / len(filled)
            >= NUMERIC_SHARE)


def loop_share(text):
    """How much of the answer is a repeat of itself, markup discarded first:
    chemistry repeats because the chemistry does, `<lcel>` is a declared merge,
    a dot leader is a property list. What is left repeating is the model."""
    s = " ".join(_MARKUP.sub(" ", text).split())
    if len(s) <= SHINGLE:
        return 0.0
    grams = [s[i:i + SHINGLE] for i in range(len(s) - SHINGLE + 1)]
    return (len(grams) - len(set(grams))) / len(grams)


def measure(pages) -> dict:
    """Counts over the blocks the run actually answered."""
    res = {"blocks": 0, "answered": 0, "charts": 0, "charts_answered": 0,
           "charts_as_data": 0, "looping": 0, "loop_worst": 0.0,
           "loop_worst_anchor": None, "chart_anchors": [], "loop_anchors": []}
    for i, p in sorted(pages.items()):
        for b in p.get("blocks") or []:
            res["blocks"] += 1
            lab = b.get("label") or ""
            chart = lab == "chart"
            res["charts"] += chart
            text = (b.get("content") or "").strip()
            if not text:
                continue
            res["answered"] += 1
            res["charts_answered"] += chart
            anchor = page.anchor(i, b.get("block_id"))
            if chart and is_data_table(text):
                res["charts_as_data"] += 1
                res["chart_anchors"].append(anchor)
            r = loop_share(text)
            if r > res["loop_worst"]:
                res["loop_worst"], res["loop_worst_anchor"] = r, anchor
            if r >= LOOP_SHARE:
                res["looping"] += 1
                res["loop_anchors"].append(anchor)
    return res


def report(res: dict) -> None:
    log(f"answered {res['answered']} of {res['blocks']} blocks "
        f"(shingle {SHINGLE}, repeat share {LOOP_SHARE}, "
        f"numeric share {NUMERIC_SHARE})")
    if not res["charts"]:
        log("no chart block in this run: nothing could be invented from one")
    else:
        log(f"charts {res['charts']}, answered {res['charts_answered']}, "
            f"returned as a TABLE OF NUMBERS {res['charts_as_data']} -- "
            f"numbers read off a curve and placed in the book as text")
        if res["chart_anchors"]:
            log("  " + ", ".join(res["chart_anchors"][:8])
                + (" ..." if len(res["chart_anchors"]) > 8 else ""))
    log(f"answers repeating themselves {res['looping']} "
        f"(worst {res['loop_worst']:.3f} at {res['loop_worst_anchor']})")


class ReadingMetric(Metric):
    """The truth-free half of level two: labels and answers are both in the
    run's own pages, so it measures any book that has been read, with no truth
    and no scan; `read` says THIS RUN produced the characters."""
    name = "reading"
    needs = frozenset({"pages", "read"})
    scalars = (
        Spec("charts_as_data", "lower",
             "charts returned as a table of numbers: values read off a curve and placed in the book as text", 'What failed, and how'),
        Spec("looping", "lower",
             "answers that repeat themselves", 'What failed, and how'),
        Spec("answered", "higher",
             "blocks answered"),
    )

    def run(self, bench, run) -> Record:
        return self.record(measure(run.pages()), bench.name, run.label)

    def run_loaded(self, bench, run, truth, pages, note) -> Record:
        return self.record(measure(pages), bench.name, run.label)

    def record(self, res, bench_name, run_label) -> Record:
        no_chart = "no chart block in this run"
        no_answer = "this run answered nothing"
        scalars = {
            "charts_as_data": Scalar(
                (res["charts_as_data"] / res["charts_answered"])
                if res["charts_answered"] else None,
                count=(res["charts_as_data"], res["charts_answered"]),
                why=None if res["charts_answered"] else no_chart),
            "looping": Scalar(
                (res["looping"] / res["answered"]) if res["answered"] else None,
                count=(res["looping"], res["answered"]),
                why=None if res["answered"] else no_answer),
            "answered": Scalar(
                (res["answered"] / res["blocks"]) if res["blocks"] else None,
                count=(res["answered"], res["blocks"]),
                why=None if res["blocks"] else "no block in this run"),
        }
        params = {"SHINGLE": SHINGLE, "LOOP_SHARE": LOOP_SHARE,
                  "NUMERIC_SHARE": NUMERIC_SHARE, "MIN_ROWS": MIN_ROWS}
        return Record(self.name, bench_name, run_label, scalars, params, res)

    def report(self, rec: Record) -> None:
        report(rec.detail)
