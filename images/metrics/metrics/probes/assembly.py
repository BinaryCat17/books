from metrics import contour
from metrics.base import Probe


def probes(bench, run) -> list:
    M = run.pages()
    pol = run.policy
    base = contour.column_jumps(M, pol=pol)
    many = any(
        v >= 2
        for v in (
            len(set(contour._columns([b["box"] for b in contour._columns_of(p, pol=pol)[0]])))
            for p in M.values()
        )
    )

    def jumps(mm):
        return contour.column_jumps(mm, pol=pol)["excess_jumps"]

    return [
        Probe(
            "two columns interleaved",
            "more excess jumps",
            lambda: None if not many else jumps(contour._mix_columns(M, pol=pol)) > base["excess_jumps"],
        ),
        Probe(
            "all boxes into one column",
            "zero excess jumps",
            lambda: jumps(contour._one_column(M)) == 0,
        ),
        Probe(
            "one counted box per page",
            "a dash, not a zero",
            lambda: contour.column_jumps(contour._one_box(M, pol=pol), pol=pol)["per_page"] is None,
        ),
    ]
