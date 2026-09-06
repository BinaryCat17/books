"""Excess column jumps as a metric of its own: truth-free, so `bench/real`
finally gets a number.

The quantity is `contour.column_jumps`, which the contour metric also
carries beside its truth-based numbers. Here it stands alone with `needs`
= pages only, and the parameters that decide the count ride in `params`
because two counts at different parameters are not comparable (the sweep
in `contour` exists for exactly that).
"""
from booksmith.datasets.metrics import contour
from booksmith.datasets.metrics.base import Metric, Record, Scalar


class AssemblyMetric(Metric):
    name = "assembly"
    needs = frozenset({"pages"})

    def _record(self, bench_name, run, pages) -> Record:
        j = contour.column_jumps(pages)
        scalars = {
            "excess_jumps_per_page": Scalar(
                j.get("per_page"), over=(j.get("pages_counted", 0), j.get("page_count", 0)),
                unit="pages",
                why=None if j.get("per_page") is not None else j.get("why") or "not counted"),
            "excess_jumps": Scalar(j.get("excess_jumps", 0)),
            "transitions": Scalar(j.get("transitions", 0)),
            "pages_with_columns": Scalar(j.get("pages_with_2plus_columns", 0),
                                         count=(j.get("pages_with_2plus_columns", 0), j.get("page_count", 0))),
        }
        params = {f"COLUMN_{k}": v for k, v in (j.get("params") or {}).items()}
        return Record(self.name, bench_name, run.label, scalars, params, j)

    def run(self, bench, run) -> Record:
        return self._record(bench.name if bench is not None else "", run, run.pages())

    def run_loaded(self, bench, run, truth, pages, note) -> Record:
        return self._record(bench.name if bench is not None else "", run, pages)

    def report(self, rec: Record, log=print) -> None:
        contour._report_jumps(rec.detail, log)

    def battery(self, bench, run, log=print) -> int:
        """Three spoilings of the assembly order, through the shared loop.

        The same three probes stand inside the contour battery, where they
        are measured beside the truth-based ones; here they stand alone so
        that this metric can fail on a book with no truth at all. The
        summary line is the shared one, so the acceptance lock on it has
        the shape every battery will have after the fold.
        """
        from booksmith.datasets.metrics.base import Probe, battery_summary, run_battery
        M = run.pages()
        base = contour.column_jumps(M)
        many = any(v >= 2 for v in (
            len(set(contour._columns([b["box"] for b in contour._columns_of(p)[0]])))
            for p in M.values()))

        def jumps(mm):
            return contour.column_jumps(mm)["excess_jumps"]
        probes = [
            Probe("two columns interleaved", "more excess jumps",
                  lambda: None if not many else jumps(contour._mix_columns(M)) > base["excess_jumps"]),
            Probe("all boxes into one column", "zero excess jumps",
                  lambda: jumps(contour._one_column(M)) == 0),
            Probe("one counted box per page", "a dash, not a zero",
                  lambda: contour.column_jumps(contour._one_box(M))["per_page"] is None),
        ]
        seen, mute, bad = run_battery(probes, log)
        log("what this battery does NOT catch: a wrong column split (the "
            "columns are found by the same rule the count uses); a page "
            "whose assembly is wrong INSIDE one column.")
        return battery_summary("assembly", seen, mute, bad, log)
