"""The reading metric as a `Metric`: characters and cells against truth.

The measurement is `booksmith.text` (measure, report, mutations),
untouched. Needs `content`: a truth without characters (the golden bench
annotates boxes only) has nothing for it to compare.
"""
from booksmith import text as reading
from booksmith.datasets.metrics.base import Metric, Record, Scalar


def _share(value, n, of, why):
    return Scalar(value, (n, of), why=None if value is not None else why)


class TextMetric(Metric):
    name = "text"
    needs = frozenset({"truth", "pages", "content"})

    def run(self, bench, run) -> Record:
        res = reading.measure(bench.truth_dir, run.pages_dir)
        t, tb, m, bt, a = (res["text"], res["tables"], res["matching"],
                           res["baits"], res["artifacts_with_truth"])
        answered = t["block_count"] - t["no_answer"] - t["unmatched"]
        no_cells = ("no table with a cell grid in the truth" if not tb["cell_count"]
                    else "no table answered" if not tb["answered_blocks"]
                    else "no cell matched")
        scalars = {
            "paired": _share(m["share"], m["matched_total"], m["truth_blocks"],
                             "no truth block to pair"),
            # CER and WER are over EVERY truth block, an unanswered one at
            # full distance; the answered-only figure is its own line.
            "CER": _share(t["CER"], t["block_count"], t["block_count"],
                          "no text block in the truth"),
            "WER": _share(t["WER"], t["block_count"], t["block_count"],
                          "no text block in the truth"),
            "CER_answered": _share(t["cer_answered"], answered, t["block_count"],
                                   "no answered text block"),
            "no_answer": _share(t["share_no_answer"], t["no_answer"], t["block_count"],
                                "no text block in the truth"),
            "cells_matched": _share(tb["share_cells_matched"], tb["cells_matched"],
                                    tb["cell_count"], no_cells),
            "CER_cells": _share(tb["cer_cells"], tb["cells_matched"], tb["cell_count"],
                                no_cells),
            "tables_given_as_text": Scalar(tb["given_as_text"], (tb["given_as_text"], tb["block_count"])),
            "baits_read": _share(bt["share"], bt["read"], bt["artifacts"],
                                 "no bait artefact in the truth"),
            "CER_artefacts": _share(a["CER"], a["block_count"] - a["no_answer"], a["block_count"],
                                    "no artefact with character truth"),
        }
        params = {"normalization": res["normalization"]["level"],
                  **{f"geometry_{k}": v for k, v in (res.get("geometry_gate") or {}).items()}}
        return Record(self.name, bench.name, run.label, scalars, params, res)

    def report(self, rec: Record, log=print) -> None:
        reading.report(rec.detail, log=log)

    def battery(self, bench, run, log=print) -> int:
        return reading.mutations(bench.truth_dir, run.pages_dir, log=log)
