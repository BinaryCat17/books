"""Probes of the assembly metric: spoil the block order, count the jumps.

The same three stand inside the contour probes, where they are measured beside
the truth-based ones; here they stand alone, so this metric can fail on a book
with no truth at all.
"""
from booksmith.datasets.metrics import contour
from booksmith.datasets.metrics.base import Probe


def probes(bench, run) -> list:
    M = run.pages()
    base = contour.column_jumps(M)
    many = any(v >= 2 for v in (
        len(set(contour._columns([b["box"] for b in contour._columns_of(p)[0]])))
        for p in M.values()))

    def jumps(mm):
        return contour.column_jumps(mm)["excess_jumps"]

    return [
        Probe("two columns interleaved", "more excess jumps",
              lambda: None if not many
                      else jumps(contour._mix_columns(M)) > base["excess_jumps"]),
        Probe("all boxes into one column", "zero excess jumps",
              lambda: jumps(contour._one_column(M)) == 0),
        Probe("one counted box per page", "a dash, not a zero",
              lambda: contour.column_jumps(contour._one_box(M))["per_page"] is None),
    ]
