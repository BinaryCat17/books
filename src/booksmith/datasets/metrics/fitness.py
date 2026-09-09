"""The ink metric as a `Metric`: will the meaning reach the second level.

The MEASUREMENT is `processing.assess.ink` (measure, report, the thresholds),
where the production pipeline can ask it of any book without truth; this file
holds what needs the bench, and `probes/fitness.py` the damage. The shares are
computed here once, from the same counts the report divides.
"""
from booksmith.datasets.metrics.base import Metric, Record, Scalar
from booksmith.processing.assess import ink


def _ratio(n, d, why):
    return Scalar(n / d if d else None, count=(n, d), why=None if d else why)


class FitnessMetric(Metric):
    """Shares from the measurement's counts: the six the report divides
    (ink under boxes, under artefacts, outside; area under boxes; objects
    intact; object ink preserved) and four it prints as counts, expressed
    here over the object count so that two runs compare (torn, left as
    text, arrived with company, cut as one picture)."""
    name = "fitness"
    needs = frozenset({"pdf", "pages"})

    def run(self, bench, run) -> Record:
        truth = bench.truth_dir if bench is not None and bench.truth_dir else ""
        res = ink.measure(bench.pdf, run.pages_dir, truth)
        return self.record(res, bench.name, run.label, bool(truth))

    def run_loaded(self, bench, run, truth, pages, note) -> Record:
        # The ink measurement renders the PDF page by page and reads the
        # pages itself; the parsed dicts are not what costs here.
        return self.run(bench, run)

    def record(self, res: dict, bench_name: str, run_label: str, with_truth=True) -> Record:
        tot, obj = res["ink_total"], res["objects"]
        no_ink = "no ink found at all: nothing to measure"
        no_obj = ("no truth given: the object half needs it" if not with_truth
                  else "no object with ink in the truth")
        scalars = {
            "ink_under_boxes": _ratio(res["ink_under_boxes"], tot, no_ink),
            "ink_under_artefacts": _ratio(res["ink_under_artifact"], tot, no_ink),
            # `ink_outside_boxes` IS GONE, and it was two defects in one row.
            # It was exactly `1 - ink_under_boxes`, to the last bit, in all 54
            # result files -- two rows, one fact. And it was the row a reader
            # took for "how much of the book was lost", while the binding
            # shadow it counted as lost is 9.8 points of the 14.3 it reported
            # on the one real book. What replaces it is not a complement but
            # a measurement: `ink_under_boxes_clean`, over ink that is ink.
            # THE SAME QUESTION WITH THE BINDING DISCARDED, and both are
            # printed because replacing the raw one silently is the version
            # that would be a repair rather than a ruler. Measured on the one
            # real level-two run: 85.661 % raw, 94.681 % clean, the
            # difference being 9.79 % of the sheet's ink standing in solid
            # dark columns at the binding.
            #
            # CLEANED ON BOTH SIDES OR NOT AT ALL. Under the attack `ink.py`
            # documents -- a box laid on every junk run, pure damage finding
            # nothing -- the raw number pays 85.661 -> 95.202, the clean one
            # moves 94.681 -> 94.681, a gradient of exactly zero, and a
            # denominator-only clean pays 94.959 -> 105.535: not merely
            # gamed but past 100 %, which is what an instrument looks like
            # when it has stopped dividing a thing by the thing it is part of.
            "ink_under_boxes_clean": _ratio(res["clean_under_boxes"],
                                            res["ink_clean"],
                                            "no ink left after the binding"),
            # A PROPERTY OF THE SCAN, NOT OF THE MODEL: how much of this
            # book is binding shadow and black scan edge. Ranking models by
            # it is meaningless -- they all read the same paper -- and it is
            # the number to look at when the clean and raw columns disagree.
            "ink_junk": _ratio(res["ink_junk"], tot, no_ink),
            "area_under_boxes": _ratio(res["boxes_area"], res["sheet_area"], "no sheet"),
            # THE OTHER HALF OF THE GUARD, and it exists because the first
            # half is beaten from the opposite side. `area_under_boxes`
            # catches the model that boxes the whole sheet; a model that
            # TRACES the ink with tiny boxes takes 100 % of it at LESS area
            # than an honest run -- measured on slovar: ink under boxes
            # 1.000 at area 0.462, against the honest 0.991 at 0.665, so the
            # declared guard reads the cheat as better than the real thing.
            #
            # The median box, as a share of its own page, separates them:
            # honest 0.0155, the tracer 0.000081, the whole-sheet box 1.000.
            # NEITHER END IS GOOD, which is why both are `=` and neither is
            # a rank: one is a model that found nothing, the other a model
            # that found everything and split it into rubble.
            "median_box_area": Scalar(
                res["median_box_area"],
                why=None if res["median_box_area"] is not None
                else "no box lands on any sheet"),
            # The same question in the unit a person bills in: one box, one
            # crop, one paid request at level two. Honest 44 a page on
            # slovar against the tracer's 5673.
            "boxes_per_page": _ratio(res["box_count"], res["page_count"],
                                     "no page was measured"),
            # WHERE THE INK ENDS UP, and this is the question the project is
            # for: how much of the book survives, and as WHAT. The two shares
            # plus `ink_outside_boxes` are exhaustive against the sheet's ink
            # -- measured on the one real level-two run, 76.944 % as text,
            # 8.717 % as a picture, 14.339 % under no box, summing to
            # 100.000 %. The rule is the BUILDER's, asked of `html.py` rather
            # than restated: a crop where `role == "artifact" or not content`,
            # a paragraph otherwise.
            #
            # NONE, NOT ZERO, ON A RUN THAT READ NOTHING. A detection run has
            # no content anywhere, so every block is a picture by that rule
            # and "0 % leaves as text" would be printed as a fact about the
            # model. It is a fact about the run, and the two zeros are the
            # rule this project keeps hardest.
            "ink_as_text": _ratio(res["ink_as_text"], tot, no_ink)
            if res["blocks_with_content"] else Scalar(
                None, why="this run read nothing: every block would leave as "
                          "a picture, which is not a measurement of one"),
            "ink_as_picture": _ratio(res["ink_as_picture"], tot, no_ink)
            if res["blocks_with_content"] else Scalar(
                None, why="this run read nothing: every block would leave as "
                          "a picture, which is not a measurement of one"),
            "objects_intact": _ratio(res["intact"], obj, no_obj),
            "objects_in_one_box": _ratio(res["in_one_box"], obj, no_obj),
            "objects_torn": _ratio(res["torn"], obj, no_obj),
            "objects_left_as_text": _ratio(res["left_as_text"], obj, no_obj),
            "objects_with_company": _ratio(res["arrived_with_company"], obj, no_obj),
            "object_ink_preserved": _ratio(res["object_ink_in_boxes"], res["object_ink"], no_obj),
        }
        params = dict(res["thresholds"])
        # THE JUNK MASK IS OURS AND IT IS DECLARED WHOLE. `MID`
        # was already a bare literal inside a printed sentence,
        # reaching no params at all; the other three are the
        # spread-cutter's, imported so there is one copy.
        params.update({"MID": ink.MID, "JUNK_WIDTH": ink.JUNK_WIDTH,
                       "RULE_RUN": ink.RULE_RUN,
                       "GUTTER_BAND": ink.GUTTER_BAND,
                       "MIN_SPREAD_RATIO": ink.MIN_SPREAD_RATIO})
        params["GUTTER"] = ink.GUTTER
        # THE DPI EVERYTHING HERE IS DENOMINATED IN. `assess/ink.py` says it
        # in its own header -- "without it two numbers from two runs are
        # incomparable" -- and then it lived in `detail`, which a table built
        # from `params` cannot reach.
        params["dpi"] = res.get("dpi")
        return Record(self.name, bench_name, run_label, scalars, params, res)

    def report(self, rec: Record, log=print) -> None:
        ink.report(rec.detail, log=log)
