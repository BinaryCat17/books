"""Excess column jumps as a metric of its own: truth-free, so `bench/real`
finally gets a number.

The quantity is `contour.column_jumps`, which the contour metric also
carries beside its truth-based numbers. Here it stands alone with `needs`
= pages only, and the parameters that decide the count ride in `params`
because two counts at different parameters are not comparable (the sweep
in `contour` exists for exactly that).
"""
from booksmith.core import order
from booksmith.datasets.metrics import contour
from booksmith.datasets.metrics.base import Metric, Record, Scalar


def _under_one_rule(pages: dict) -> dict:
    """The same boxes, ordered for every model by OUR rule.

    WHY A SECOND COUNT AND NOT A REPLACEMENT. `excess_jumps_per_page` counts
    the order that REACHES THE BOOK, which is the model's own rank where it
    has one (V2, V3) and our `(y0, x0)` where it has none (plus-L, heron,
    egret, yolox). That is the honest end-to-end number and it is two
    different quantities in one column: a table of six models cannot be read
    down it, and the footnote saying so does not make it readable.

    This is the other question -- WHICH BOXES ARE EASIEST TO ORDER -- and it
    is the one a detector can be chosen by, because ordering is a knob we
    hold and not a property of the model. Held constant, the column compares
    boxes; left as it is, it partly compares "answers the question" against
    "does not".

    The spread this closes is not small. The same V2 boxes on the golden
    bench, permuted three ways, are on record in `core/order.py`: our rule
    against the model's own rank against the docling rules, and the first is
    worse than both at every one of 16 sweep points. So a model that returns
    a rank is flattered here by an amount larger than the whole span the
    six-model table shows.

    `order.permutation` and not a sort written here: the rule lived in four
    places across three adapters once and two of them declared it wrongly.
    """
    out = {}
    for i, p in pages.items():
        blocks = p.get("blocks") or []
        if len(blocks) < 2:
            out[i] = p
            continue
        boxes = [b["box"] for b in blocks]
        # `vocab` is unused by the `ours` branch -- it reaches only the
        # docling rules -- and passing None keeps this free of a vocabulary
        # the metric has no business choosing.
        idx = order.permutation([b.get("label") for b in blocks], boxes,
                                p.get("width"), p.get("height"), i, None,
                                which="ours")
        out[i] = {**p, "blocks": [blocks[k] for k in idx]}
    return out


class AssemblyMetric(Metric):
    name = "assembly"
    needs = frozenset({"pages"})

    def _record(self, bench_name, run, pages) -> Record:
        j = contour.column_jumps(pages)
        one = contour.column_jumps(_under_one_rule(pages))
        scalars = {
            "excess_jumps_per_page": Scalar(
                j.get("per_page"), over=(j.get("pages_counted", 0), j.get("page_count", 0)),
                unit="pages",
                why=None if j.get("per_page") is not None else j.get("why") or "not counted"),
            # `.get(key, 0)` DEFAULTS ON A MISSING KEY AND NOT ON A NULL ONE,
            # and `column_jumps` returns the key with None in it whenever not
            # one page gathered enough boxes to jump between -- "the quantity
            # is UNDEFINED", which is the whole reason it says so. So this
            # raised `a scalar without a value must say why` on the first
            # (bench, model) pair that hit it: katalog under yolox, found by
            # the sweep and by nothing before it, because no combination in
            # the tree had ever produced an empty count.
            "excess_jumps": Scalar(
                j.get("excess_jumps"),
                why=None if j.get("excess_jumps") is not None
                else j.get("why") or "not counted"),
            # PER TRANSITION, NOT PER PAGE, and the first edition of this
            # pair was per page and had to be thrown away. Measured on the
            # golden bench, `excess_jumps_per_page` under one rule reprinted
            # the RECALL ordering almost exactly -- yolox best at 3.360 with
            # 368 artefacts found, V2 worst at 5.325 with 698 -- because a
            # model that finds more boxes gives a naive rule more chances to
            # interleave columns. It answered "who found fewest", not "whose
            # boxes are easiest to order", and reading it as a quality column
            # inverted the true ranking.
            #
            # A transition is one move between counted boxes, so it grows
            # with the boxes and divides the confound out. On the same bench
            # it puts V3 and V2 first (0.533, 0.539) and yolox third (0.792)
            # -- no longer rewarding a model for missing things.
            "excess_jumps_per_transition": Scalar(
                (j["excess_jumps"] / j["transitions"])
                if j.get("transitions") else None,
                count=(j.get("excess_jumps"), j.get("transitions")),
                unit="transitions",
                why=None if j.get("transitions") else
                "no page gathered two counted boxes: nothing to jump between"),
            # The same quantity with OUR rule forced on every model, so the
            # column compares BOXES with the ordering held constant. The four
            # models with no rank of their own are unchanged by construction,
            # which is the check that the forcing does what it says.
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
        # WHOSE ORDER WAS COUNTED, beside the count. Excess jumps are counted
        # over the page's block list, and that list is the MODEL's rank for a
        # model that has one and OUR `(y0, x0)` rule for a model that has
        # none -- two different quantities in one column. The spread between
        # them is not small: on the same V2 boxes the golden bench gives 2471
        # extra jumps by our rule against 501 by the model's rank, five times
        # the whole span a six-model table shows. Without this field a table
        # cannot say which of the two it is printing.
        params["order_rule"] = contour.order_rule(pages)
        params["order_rule_one_rule"] = "ours_top_down_left_right (forced)"
        return Record(self.name, bench_name, run.label, scalars, params, j)

    def run(self, bench, run) -> Record:
        return self._record(bench.name if bench is not None else "", run, run.pages())

    def run_loaded(self, bench, run, truth, pages, note) -> Record:
        return self._record(bench.name if bench is not None else "", run, pages)

    def report(self, rec: Record, log=print) -> None:
        contour._report_jumps(rec.detail, log)
