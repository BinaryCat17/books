"""What the reader got wrong that can be seen WITHOUT truth.

`text.py` compares an answer against known characters and is the honest
measurement of reading quality -- and it has never produced a number, because
truth for a real scan does not exist and drawn pages are 144 dpi typeset
imitations (`docs/limits.md` says so in three reasons). So every defect of
level two has been unmeasured, on a book that cost money to read.

This file measures the ones that need no truth at all, because they are
defects a reader can be caught in by looking only at what it returned.

THE FABRICATED CHART IS THE ONE THAT MATTERS. A `chart` is a picture of a
curve. Asked to read it, the model returns a TABLE OF NUMBERS -- values read
off the curve by eye, to two decimals -- and those numbers are placed into
the book as text. Measured on the one real level-two run: of 60 answered
chart blocks, 58 came back as two or more delimited rows and 56 of those are
majority numeric. One of them, `p0019-b9`, even repeats the axis label as a
data row. This is the project's own rule -- "numbers may only be flagged,
never restored" -- broken by the model, in the shipped HTML, and the counter
aimed at it cannot fire: `readers/paddleocr_vl.py` routes `chart` with the
promise `text`, `driver._sniff` answers `text` for a pipe table, promise and
guess agree, and `kind_not_as_promised` stays silent on all sixty.

WHY IT CANNOT FALSE-POSITIVE ON A REAL TABLE. The rule asks for delimited
numeric rows under a `chart` LABEL. A table returned as a grid is right, and
`table` blocks are routed to OTSL, not to this shape. Measured over all 6080
answered blocks of that run: `chart` is the ONLY label that produces two or
more delimited rows -- 58 blocks against zero for every other label.

WHAT IT DOES NOT CLAIM. It does not say the numbers are wrong; nothing here
can, without the page. It says they were INVENTED FROM A PICTURE, which is a
statement about where they came from, and that is what makes the reading
untrustworthy whatever the digits are.
"""
import re

from booksmith.core import policy
from booksmith.datasets.metrics.base import (Metric, Probe, Record, Scalar,
                                             battery_summary, run_battery)

# A cell that is a bare number: what a fabricated chart table is made of.
NUMBER = re.compile(r"^[-+]?\d+(?:[.,]\d+)?$")
# Half the filled cells or more, and the answer is data rather than prose.
NUMERIC_SHARE = 0.5
# Two rows is a table; one delimited line is a caption with a bar in it.
MIN_ROWS = 2
# The shingle for degenerate repetition, and the share of it that must be
# repeats. Measured over the real run: stripping OTSL and LaTeX markup first
# and asking for 0.30 flags 20 blocks of which 19 are genuine -- 95 per cent.
# Asked of the raw text at 0.20 it flags 33 of which 13 are chemistry that
# repeats because the chemistry does, dot leaders, and `<lcel>` merge runs.
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
    """How much of the answer is a repeat of itself, markup discarded.

    Markup first, and that is the whole difference between a detector and a
    nuisance: `\\mathrm{Al}_2\\mathrm{O}_3` repeats because the chemistry
    does, `<lcel><lcel><lcel>` is a DECLARED merge, and a dot leader is a
    property list. Stripped, what is left repeating is the model repeating
    itself.
    """
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
            anchor = f"p{i:04d}-b{b.get('block_id')}"
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


def report(res: dict, log=print) -> None:
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
    """The truth-free half of level two.

    `needs` is `pages` and `read` and nothing more: the labels and the
    answers are both in the run's own pages, so this measures on any book
    that has been read, with no truth and no scan. `read` is the prerequisite
    that says THIS RUN produced characters -- without it every share here
    would be 0 of 0 and print as a fact about the model.
    """
    name = "reading"
    needs = frozenset({"pages", "read"})

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

    def report(self, rec: Record, log=print) -> None:
        report(rec.detail, log=log)

    def battery(self, bench, run, log=print) -> int:
        return mutations(run.pages(), log=log)


def _edit(pages, fn):
    return {i: {**p, "blocks": [fn(dict(b)) for b in p.get("blocks") or []]}
            for i, p in pages.items()}


def mutations(pages, log=print) -> int:
    """Spoil the answers and demand the numbers move."""
    base = measure(pages)
    charts = base["charts_answered"]
    answered = base["answered"]

    def M(fn):
        return measure(_edit(pages, fn))

    def prose(b):
        if (b.get("label") or "") == "chart" and (b.get("content") or ""):
            b["content"] = "a curve rising from left to right"
        return b

    def data(b):
        if (b.get("content") or "").strip():
            b["content"] = "a | b\n1 | 2\n3 | 4"
        return b

    probes = [
        ("every chart answered in prose", "none is a table of numbers",
         lambda: None if not charts else M(prose)["charts_as_data"] == 0),
        ("every answer made a numeric table",
         "every ANSWERED chart is one, and nothing else is counted",
         lambda: None if not charts else
                 (lambda r: r["charts_as_data"] == charts)(M(data))),
        # THE RULE IS THE LABEL AND THE SHAPE TOGETHER. Counting the shape
        # alone would call every real table a fabrication; counting the label
        # alone would call a chart described in words one.
        ("every block relabelled a chart",
         "the count follows the LABEL, so it rises",
         lambda: None if not answered else
                 M(lambda b: {**b, "label": "chart"})["charts_as_data"]
                 >= base["charts_as_data"]),
        ("every answer replaced by one token repeated",
         "the loop share reaches its ceiling",
         lambda: None if not answered else
                 (lambda r: r["looping"] == r["answered"]
                  and r["loop_worst"] > 0.9)(
                     M(lambda b: {**b, "content": "abc " * 200
                                  if (b.get("content") or "").strip() else b.get("content")}))),
        # A DECLARED MERGE IS NOT A LOOP, and this is why the markup goes
        # first: `<lcel>` runs and repeated chemistry are the false positives
        # that made the raw ratio 39 % wrong.
        ("every answer made of OTSL merge cells",
         "markup that repeats is not the model repeating itself",
         lambda: None if not answered else
                 M(lambda b: {**b, "content": "<lcel>" * 60
                              if (b.get("content") or "").strip()
                              else b.get("content")})["looping"] == 0),
        ("every answer emptied", "nothing is answered and nothing is counted",
         lambda: (lambda r: r["answered"] == 0 and r["charts_as_data"] == 0
                  and r["looping"] == 0)(M(lambda b: {**b, "content": None}))),
    ]
    seen, mute, bad = run_battery([Probe(n, e, f) for n, e, f in probes], log)
    return battery_summary("reading", seen, mute, bad, log)
