"""Excess column jumps as a metric of its own: truth-free, so an unannotated"""

from metrics import order
from metrics import page
from metrics import contour
from metrics.base import Metric, Record, Scalar, Spec


def _under_one_rule(pages: dict) -> dict:
    out = {}
    for i, p in pages.items():
        blocks = p.get("blocks") or []
        if len(blocks) < 2:
            out[i] = p
            continue
        boxes = [b["box"] for b in blocks]
        idx = order.permutation(
            [b.get("label") for b in blocks],
            boxes,
            p.get("width"),
            p.get("height"),
            i,
            None,
            which="ours",
        )
        out[i] = {**p, "blocks": [blocks[k] for k in idx]}
    return out


class AssemblyMetric(Metric):
    name = "assembly"
    needs = frozenset({"pages"})
    scalars = (
        Spec(
            "excess_jumps_per_transition",
            "lower",
            "excess column jumps per move between boxes",
            "Is the order right",
        ),
        Spec(
            "excess_jumps_per_transition_one_rule",
            "lower",
            "the same with one ordering rule forced on every model, so the column compares boxes alone",
            "Is the order right",
        ),
        Spec("excess_jumps", "lower", "column jumps beyond the unavoidable", per="page"),
        Spec("excess_jumps_per_page", "lower", "excess column jumps per page", unit="pages"),
        Spec("transitions", "neither", "moves between boxes"),
        Spec("pages_with_columns", "neither", "pages with more than one column", per="page"),
    )

    def _record(self, bench_name, run, pages) -> Record:
        j = contour.column_jumps(pages, pol=run.policy)
        one = contour.column_jumps(_under_one_rule(pages), pol=run.policy)
        scalars = {
            "excess_jumps_per_page": Scalar(
                j.get("per_page"),
                over=(j.get("pages_counted", 0), j.get("page_count", 0)),
                unit="pages",
                why=None if j.get("per_page") is not None else j.get("why") or "not counted",
            ),
            "excess_jumps": Scalar(
                j.get("excess_jumps"),
                why=None if j.get("excess_jumps") is not None else j.get("why") or "not counted",
                per={page.anchor(i): n for i, n in j["by_page"].items()},
            ),
            "excess_jumps_per_transition": Scalar(
                j["excess_jumps"] / j["transitions"] if j.get("transitions") else None,
                count=(j.get("excess_jumps"), j.get("transitions")),
                why=None
                if j.get("transitions")
                else "no page gathered two counted boxes: nothing to jump between",
            ),
            "excess_jumps_per_transition_one_rule": Scalar(
                one["excess_jumps"] / one["transitions"] if one.get("transitions") else None,
                count=(one.get("excess_jumps"), one.get("transitions")),
                why=None
                if one.get("transitions")
                else "no page gathered two counted boxes: nothing to jump between",
            ),
            "transitions": Scalar(j.get("transitions", 0)),
            "pages_with_columns": Scalar(
                j["pages_with_2plus_columns"] / j["page_count"] if j.get("page_count") else None,
                count=(j.get("pages_with_2plus_columns", 0), j.get("page_count", 0)),
                why=None if j.get("page_count") else "no page was counted",
                per={page.anchor(i): 1 for i, n in j["columns_by_page"].items() if n >= 2},
            ),
        }
        params = {f"COLUMN_{k}": v for k, v in (j.get("params") or {}).items()}
        params["order_rule"] = contour.order_rule(pages)
        params["order_rule_one_rule"] = "ours_top_down_left_right (forced)"
        return Record(self.name, bench_name, run.label, scalars, params, j)

    def run(self, bench, run) -> Record:
        return self._record(bench.name if bench is not None else "", run, run.pages())

    def run_loaded(self, bench, run, truth, pages, note, want=None) -> Record:
        return self._record(bench.name if bench is not None else "", run, pages)

    def report(self, rec: Record) -> None:
        contour._report_jumps(rec.detail)
