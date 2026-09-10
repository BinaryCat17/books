"""Excess column jumps as a metric of its own: truth-free, so an unannotated
book gets a number too.

The quantity is `contour.column_jumps`. Here it stands alone with `needs` =
pages only, and the parameters that decide the count ride in `params`: two
counts at different parameters are not comparable.
"""
from booksmith.core import order
from booksmith.datasets.metrics import contour
from booksmith.datasets.metrics.base import Metric, Record, Scalar, Spec


def _under_one_rule(pages: dict) -> dict:
    """The same boxes, ordered for every model by our rule: which boxes are the
    easiest to order, where the raw count part-compares "answers with a rank"
    against "does not". Always `order.permutation`, never a sort written here."""
    out = {}
    for i, p in pages.items():
        blocks = p.get("blocks") or []
        if len(blocks) < 2:
            out[i] = p
            continue
        boxes = [b["box"] for b in blocks]
        # `vocab` reaches only the docling rules; None keeps the metric out of
        # choosing a vocabulary.
        idx = order.permutation([b.get("label") for b in blocks], boxes,
                                p.get("width"), p.get("height"), i, None,
                                which="ours")
        out[i] = {**p, "blocks": [blocks[k] for k in idx]}
    return out


class AssemblyMetric(Metric):
    name = "assembly"
    needs = frozenset({"pages"})
    scalars = (
        Spec("excess_jumps_per_transition", "lower",
             "excess column jumps per move between boxes", 'Is the order right'),
        Spec("excess_jumps_per_transition_one_rule", "lower",
             "the same with one ordering rule forced on every model, so the column compares boxes alone", 'Is the order right'),
        Spec("excess_jumps", "lower",
             "column jumps beyond the unavoidable"),
        Spec("excess_jumps_per_page", "lower",
             "excess column jumps per page"),
        Spec("transitions", "neither",
             "moves between boxes"),
        Spec("pages_with_columns", "neither",
             "pages with more than one column"),
    )

    def _record(self, bench_name, run, pages) -> Record:
        j = contour.column_jumps(pages)
        one = contour.column_jumps(_under_one_rule(pages))
        scalars = {
            "excess_jumps_per_page": Scalar(
                j.get("per_page"), over=(j.get("pages_counted", 0), j.get("page_count", 0)),
                unit="pages",
                why=None if j.get("per_page") is not None else j.get("why") or "not counted"),
            # No `.get(key, 0)` here: `column_jumps` returns the key holding
            # None when the quantity is undefined, and a default would hide it.
            "excess_jumps": Scalar(
                j.get("excess_jumps"),
                why=None if j.get("excess_jumps") is not None
                else j.get("why") or "not counted"),
            # Per transition, not per page: per page rewards a model for
            # finding fewer boxes, while a transition grows with the boxes and
            # divides that confound out.
            "excess_jumps_per_transition": Scalar(
                (j["excess_jumps"] / j["transitions"])
                if j.get("transitions") else None,
                count=(j.get("excess_jumps"), j.get("transitions")),
                unit="transitions",
                why=None if j.get("transitions") else
                "no page gathered two counted boxes: nothing to jump between"),
            # The same quantity with our rule forced on every model: a model
            # with no rank of its own is unchanged by construction.
            "excess_jumps_per_transition_one_rule": Scalar(
                (one["excess_jumps"] / one["transitions"])
                if one.get("transitions") else None,
                count=(one.get("excess_jumps"), one.get("transitions")),
                unit="transitions",
                why=None if one.get("transitions") else
                "no page gathered two counted boxes: nothing to jump between"),
            "transitions": Scalar(j.get("transitions", 0)),
            "pages_with_columns": Scalar(j.get("pages_with_2plus_columns", 0),
                                         count=(j.get("pages_with_2plus_columns", 0), j.get("page_count", 0))),
        }
        params = {f"COLUMN_{k}": v for k, v in (j.get("params") or {}).items()}
        # Whose order was counted, beside the count: the block list is the
        # model's rank for a model that has one and our rule for one that has
        # none, and without this field a table cannot say which it printed.
        params["order_rule"] = contour.order_rule(pages)
        params["order_rule_one_rule"] = "ours_top_down_left_right (forced)"
        return Record(self.name, bench_name, run.label, scalars, params, j)

    def run(self, bench, run) -> Record:
        return self._record(bench.name if bench is not None else "", run, run.pages())

    def run_loaded(self, bench, run, truth, pages, note) -> Record:
        return self._record(bench.name if bench is not None else "", run, pages)

    def report(self, rec: Record, log=print) -> None:
        contour._report_jumps(rec.detail, log)
