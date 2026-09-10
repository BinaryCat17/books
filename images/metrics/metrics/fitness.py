from metrics import page
from metrics.base import Metric, Record, Scalar, Spec
from metrics import ink


def _ratio(n, d, why, per=None, side=""):
    return Scalar(n / d if d else None, count=(n, d), why=None if d else why, per=per, side=side)


class FitnessMetric(Metric):
    description = "will the meaning reach the second level: ink under boxes, objects intact"
    name = "fitness"
    needs = frozenset({"pdf", "pages"})
    scalars = (
        Spec(
            "ink_under_boxes",
            "higher",
            "ink that lands inside some box",
            "How much of the book survived",
            per="page",
        ),
        Spec(
            "ink_under_boxes_clean",
            "higher",
            "the same over the ink that is ink: binding shadow and scan edge discarded from both sides",
            "How much of the book survived",
            per="page",
        ),
        Spec(
            "ink_as_text",
            "higher",
            "ink that leaves the book as text rather than as a picture of itself",
            "How much of the book survived",
            per="page",
        ),
        Spec(
            "object_ink_preserved",
            "higher",
            "ink of the truth objects that survives inside boxes",
            "How much of the book survived",
            per="block",
            side="truth",
        ),
        Spec(
            "ink_under_artefacts",
            "neither",
            "ink under boxes of artifact role: a composition, not a quality",
            per="page",
        ),
        Spec("ink_as_picture", "neither", "ink that leaves as a picture", per="page"),
        Spec(
            "ink_junk",
            "neither",
            "ink discarded as binding shadow or scan edge: a property of the scan",
            per="page",
        ),
        Spec(
            "area_under_boxes",
            "neither",
            "share of the sheet under boxes: a full-sheet box scores the maximum",
        ),
        Spec("median_box_area", "neither", "median box area as a share of the sheet"),
        Spec("boxes_per_page", "neither", "boxes per page", per="page"),
        Spec(
            "objects_intact",
            "higher",
            "truth objects whose ink is intact under one box",
            per="block",
            side="truth",
        ),
        Spec(
            "objects_in_one_box",
            "higher",
            "truth objects covered by exactly one box",
            per="block",
            side="truth",
        ),
        Spec("objects_torn", "lower", "truth objects torn between boxes", per="block", side="truth"),
        Spec(
            "objects_left_as_text",
            "lower",
            "truth objects boxed as text",
            per="block",
            side="truth",
        ),
        Spec(
            "objects_with_company",
            "lower",
            "truth objects sharing a box",
            per="block",
            side="truth",
        ),
    )

    def run(self, bench, run, want=None) -> Record:
        truth = bench.truth_dir if bench is not None and bench.truth_dir else ""
        res = ink.measure(
            bench.pdf, run.pages_dir, truth, run.policy, bench.policy if truth else None, want=want
        )
        return self.record(res, bench.name, run.label, bool(truth))

    def run_loaded(self, bench, run, truth, pages, note, want=None) -> Record:
        return self.run(bench, run, want)

    def record(self, res: dict, bench_name: str, run_label: str, with_truth=True) -> Record:
        tot, obj = (res["ink_total"], res["objects"])
        no_ink = "no ink found at all: nothing to measure"
        no_obj = (
            "no truth given: the object half needs it"
            if not with_truth
            else "no object with ink in the truth"
        )
        pages, objects = (res["pages"], res["per_object"])

        def by_page(num, den):
            return {page.anchor(i): p[num] / p[den] for i, p in pages.items() if p[den]}

        def which(field, want=True):
            return {a: 1 for a, o in objects.items() if o[field] == want}

        scalars = {
            "ink_under_boxes": _ratio(
                res["ink_under_boxes"], tot, no_ink, by_page("ink_under_boxes", "ink_total")
            ),
            "ink_under_artefacts": _ratio(
                res["ink_under_artifact"], tot, no_ink, by_page("ink_under_artifact", "ink_total")
            ),
            "ink_under_boxes_clean": _ratio(
                res["clean_under_boxes"],
                res["ink_clean"],
                "no ink left after the binding",
                by_page("clean_under_boxes", "ink_clean"),
            ),
            "ink_junk": _ratio(res["ink_junk"], tot, no_ink, by_page("ink_junk", "ink_total")),
            "area_under_boxes": _ratio(res["boxes_area"], res["sheet_area"], "no sheet"),
            "median_box_area": Scalar(
                res["median_box_area"],
                why=None if res["median_box_area"] is not None else "no box lands on any sheet",
            ),
            "boxes_per_page": _ratio(
                res["box_count"],
                res["page_count"],
                "no page was measured",
                {page.anchor(i): p["box_count"] for i, p in pages.items()},
            ),
            "ink_as_text": _ratio(res["ink_as_text"], tot, no_ink, by_page("ink_as_text", "ink_total"))
            if res["blocks_with_content"]
            else Scalar(
                None,
                why="this run read nothing: every block would leave as a picture, which is not a measurement of one",
            ),
            "ink_as_picture": _ratio(
                res["ink_as_picture"], tot, no_ink, by_page("ink_as_picture", "ink_total")
            )
            if res["blocks_with_content"]
            else Scalar(
                None,
                why="this run read nothing: every block would leave as a picture, which is not a measurement of one",
            ),
            "objects_intact": _ratio(res["intact"], obj, no_obj, which("fate", "intact"), "truth"),
            "objects_in_one_box": _ratio(res["in_one_box"], obj, no_obj, which("in_one_box"), "truth"),
            "objects_torn": _ratio(res["torn"], obj, no_obj, which("fate", "torn"), "truth"),
            "objects_left_as_text": _ratio(res["left_as_text"], obj, no_obj, which("left_as_text"), "truth"),
            "objects_with_company": _ratio(
                res["arrived_with_company"], obj, no_obj, which("with_company"), "truth"
            ),
            "object_ink_preserved": _ratio(
                res["object_ink_in_boxes"],
                res["object_ink"],
                no_obj,
                {a: o["kept"] / o["ink"] for a, o in objects.items()},
                "truth",
            ),
        }
        params = dict(res["thresholds"])
        params.update(
            {
                "MID": ink.MID,
                "JUNK_WIDTH": ink.JUNK_WIDTH,
                "RULE_RUN": ink.RULE_RUN,
                "GUTTER_BAND": ink.GUTTER_BAND,
                "MIN_SPREAD_RATIO": ink.MIN_SPREAD_RATIO,
            }
        )
        params["GUTTER"] = ink.GUTTER
        params["dpi"] = res.get("dpi")
        return Record(self.name, bench_name, run_label, scalars, params, res)

    def report(self, rec: Record) -> None:
        ink.report(rec.detail)
