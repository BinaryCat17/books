import re
from metrics.base import Metric, Record, Scalar, Spec
from metrics import page
from metrics.log import log

NUMBER = re.compile("^[-+]?\\d+(?:[.,]\\d+)?$")
NUMERIC_SHARE = 0.5
MIN_ROWS = 2
SHINGLE = 20
LOOP_SHARE = 0.3
_MARKUP = re.compile("<(?:fcel|ecel|lcel|ucel|xcel|ched|rhed|srow|nl)>|\\\\[a-zA-Z]+|[{}&$^_]")


def _rows(text):
    out = []
    for line in text.splitlines():
        if "|" in line:
            out.append([c.strip() for c in line.split("|")])
    return out


def is_data_table(text):
    rows = _rows(text)
    if len(rows) < MIN_ROWS:
        return False
    filled = [c for r in rows for c in r if c]
    if not filled:
        return False
    return sum(1 for c in filled if NUMBER.match(c)) / len(filled) >= NUMERIC_SHARE


def loop_share(text):
    s = " ".join(_MARKUP.sub(" ", text).split())
    if len(s) <= SHINGLE:
        return 0.0
    grams = [s[i : i + SHINGLE] for i in range(len(s) - SHINGLE + 1)]
    return (len(grams) - len(set(grams))) / len(grams)


def measure(pages) -> dict:
    res = {
        "blocks": 0,
        "answered": 0,
        "charts": 0,
        "charts_answered": 0,
        "charts_as_data": 0,
        "looping": 0,
        "loop_worst": 0.0,
        "loop_worst_anchor": None,
        "chart_anchors": [],
        "loop_anchors": [],
        "per": {"looping": {}, "answered": {}},
    }
    for i, p in sorted(pages.items()):
        on_page = answered_on_page = 0
        for b in p.get("blocks") or []:
            res["blocks"] += 1
            on_page += 1
            lab = b.get("label") or ""
            chart = lab == "chart"
            res["charts"] += chart
            text = (b.get("content") or "").strip()
            if not text:
                continue
            res["answered"] += 1
            answered_on_page += 1
            res["charts_answered"] += chart
            anchor = page.anchor(i, b.get("block_id"))
            if chart and is_data_table(text):
                res["charts_as_data"] += 1
                res["chart_anchors"].append(anchor)
            r = loop_share(text)
            if r > res["loop_worst"]:
                res["loop_worst"], res["loop_worst_anchor"] = (r, anchor)
            if r >= LOOP_SHARE:
                res["looping"] += 1
                res["loop_anchors"].append(anchor)
                res["per"]["looping"][anchor] = r
        if on_page:
            res["per"]["answered"][page.anchor(i)] = answered_on_page / on_page
    return res


def report(res: dict) -> None:
    log(
        f"answered {res['answered']} of {res['blocks']} blocks (shingle {SHINGLE}, repeat share {LOOP_SHARE}, numeric share {NUMERIC_SHARE})"
    )
    if not res["charts"]:
        log("no chart block in this run: nothing could be invented from one")
    else:
        log(
            f"charts {res['charts']}, answered {res['charts_answered']}, returned as a TABLE OF NUMBERS {res['charts_as_data']} -- numbers read off a curve and placed in the book as text"
        )
        if res["chart_anchors"]:
            log(
                "  " + ", ".join(res["chart_anchors"][:8]) + (" ..." if len(res["chart_anchors"]) > 8 else "")
            )
    log(
        f"answers repeating themselves {res['looping']} (worst {res['loop_worst']:.3f} at {res['loop_worst_anchor']})"
    )


class ReadingMetric(Metric):
    description = "what the reading returned: answered, looping, charts as data"
    name = "reading"
    needs = frozenset({"pages", "read"})
    scalars = (
        Spec(
            "charts_as_data",
            "lower",
            "charts returned as a table of numbers: values read off a curve and placed in the book as text",
            "What failed, and how",
            per="block",
            side="run",
        ),
        Spec(
            "looping",
            "lower",
            "answers that repeat themselves",
            "What failed, and how",
            per="block",
            side="run",
        ),
        Spec("answered", "higher", "blocks answered", per="page"),
    )

    def run(self, bench, run) -> Record:
        return self.record(measure(run.pages()), bench.name, run.label)

    def run_loaded(self, bench, run, truth, pages, note, want=None) -> Record:
        return self.record(measure(pages), bench.name, run.label)

    def record(self, res, bench_name, run_label) -> Record:
        no_chart = "no chart block in this run"
        no_answer = "this run answered nothing"
        scalars = {
            "charts_as_data": Scalar(
                res["charts_as_data"] / res["charts_answered"] if res["charts_answered"] else None,
                count=(res["charts_as_data"], res["charts_answered"]),
                why=None if res["charts_answered"] else no_chart,
                per=dict.fromkeys(res["chart_anchors"], 1),
                side="run",
            ),
            "looping": Scalar(
                res["looping"] / res["answered"] if res["answered"] else None,
                count=(res["looping"], res["answered"]),
                why=None if res["answered"] else no_answer,
                per=res["per"]["looping"],
                side="run",
            ),
            "answered": Scalar(
                res["answered"] / res["blocks"] if res["blocks"] else None,
                count=(res["answered"], res["blocks"]),
                why=None if res["blocks"] else "no block in this run",
                per=res["per"]["answered"],
            ),
        }
        params = {
            "SHINGLE": SHINGLE,
            "LOOP_SHARE": LOOP_SHARE,
            "NUMERIC_SHARE": NUMERIC_SHARE,
            "MIN_ROWS": MIN_ROWS,
        }
        return Record(self.name, bench_name, run_label, scalars, params, res)

    def report(self, rec: Record) -> None:
        report(rec.detail)
