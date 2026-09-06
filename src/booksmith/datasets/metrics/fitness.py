"""The ink metric as a `Metric`: will the meaning reach the second level.

The measurement is `booksmith.fitness` (measure, report, mutations),
untouched; it counts pixels and its report computes the shares, so the
shares are computed here too, once, from the same counts. Truth is not a
prerequisite: without it the object half is `None` with its reason.
"""
from booksmith import fitness as ink
from booksmith.datasets.metrics.base import Metric, Record, Scalar


def _ratio(n, d, why):
    return Scalar(n / d if d else None, (n, d), why=None if d else why)


class FitnessMetric(Metric):
    name = "fitness"
    needs = frozenset({"pdf", "pages"})

    def run(self, bench, run) -> Record:
        truth = bench.truth_dir if bench is not None and bench.truth_dir else ""
        res = ink.measure(bench.pdf, run.pages_dir, truth)
        tot, obj = res["ink_total"], res["objects"]
        no_ink = "no ink found at all: nothing to measure"
        no_obj = ("no truth given: the object half needs it" if not truth
                  else "no object with ink in the truth")
        scalars = {
            "ink_under_boxes": _ratio(res["ink_under_boxes"], tot, no_ink),
            "ink_under_artefacts": _ratio(res["ink_under_artifact"], tot, no_ink),
            "ink_outside_boxes": Scalar(1 - res["ink_under_boxes"] / tot if tot else None,
                                        (tot - res["ink_under_boxes"], tot),
                                        why=None if tot else no_ink),
            "area_under_boxes": _ratio(res["boxes_area"], res["sheet_area"], "no sheet"),
            "objects_intact": _ratio(res["intact"], obj, no_obj),
            "objects_torn": _ratio(res["torn"], obj, no_obj),
            "objects_left_as_text": _ratio(res["left_as_text"], obj, no_obj),
            "objects_with_company": _ratio(res["arrived_with_company"], obj, no_obj),
            "object_ink_preserved": _ratio(res["object_ink_in_boxes"], res["object_ink"], no_obj),
        }
        params = dict(res["thresholds"])
        params["GUTTER"] = ink.GUTTER
        return Record(self.name, bench.name, run.label, scalars, params, res)

    def report(self, rec: Record, log=print) -> None:
        ink.report(rec.detail, log=log)

    def battery(self, bench, run, log=print) -> int:
        truth = bench.truth_dir if bench is not None and bench.truth_dir else ""
        return ink.mutations(bench.pdf, run.pages_dir, truth, log=log)
