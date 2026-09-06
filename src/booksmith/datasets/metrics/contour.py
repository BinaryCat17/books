"""The contour metric as a `Metric`: boxes, labels, order against truth.

The measurement is `booksmith.metrics` (compare, report, mutations),
untouched; this file turns its result dict into a `Record` and names the
thresholds that rode into it. Every scalar that the report prints as
NOT COMPARED / NOT MARKED is a `None` with the report's own reason.
"""
from booksmith import metrics
from booksmith.datasets.metrics.base import Metric, Record, Scalar


def _order(part: dict) -> Scalar:
    return Scalar(part.get("agreement"), (part.get("pairs", 0), part.get("pairs_possible", 0)),
                  why=None if part.get("agreement") is not None else part.get("why") or "not compared")


class ContourMetric(Metric):
    name = "contour"
    needs = frozenset({"truth", "pages"})

    def run(self, bench, run) -> Record:
        res = metrics.compare(bench.truth_dir, run.pages_dir)
        t, x, s, j = res["totals"], res["text_and_furniture"], res["sense"], res["jumps"]
        lab = metrics.label_errors(res)
        scalars = {
            "artefacts_found": Scalar(t["share"], (t["found"], t["artifacts"])),
            "sense_whole": Scalar(
                s["share"], (s["intact"], s["objects"]),
                why=None if s["share"] is not None else "no artefact in the truth"),
            "text_furniture_found": Scalar(
                x["share"], (x.get("pages_with_text_markup", 0), x.get("pages_total", 0)),
                why=None if x["share"] is not None else "text and furniture NOT MARKED in this truth"),
            "label_errors": Scalar(
                lab, why=None if lab is not None else
                "the two sides speak different label vocabularies; not compared"),
            "role_errors": Scalar(metrics.role_errors(res)),
            "model_order": _order(res["model_order"]),
            "assembly_order": _order(res["assembly_order"]),
            "excess_jumps_per_page": Scalar(
                j.get("per_page"), (j.get("pages_counted", 0), j.get("page_count", 0)),
                why=None if j.get("per_page") is not None else j.get("why") or "not counted"),
        }
        params = {"COVER_MATCH": metrics.COVER_MATCH, "TOUCH": metrics.TOUCH,
                  "TOL_PX": metrics.TOL_PX, "SENSE_WHOLE": metrics.SENSE_WHOLE,
                  "SENSE_NEIGHBOUR": metrics.SENSE_NEIGHBOUR}
        params.update({f"COLUMN_{k}": v for k, v in (j.get("params") or {}).items()})
        return Record(self.name, bench.name, run.label, scalars, params, res)

    def report(self, rec: Record, log=print) -> None:
        metrics.report(rec.detail, log=log)

    def battery(self, bench, run, log=print) -> int:
        return metrics.mutations(bench.truth_dir, run.pages_dir, log=log)
