"""The reader caught without truth: fabricated charts and looping.

`text.py` is the honest measurement of reading and needs characters nobody has
annotated for a real scan. This file covers the half that needs no truth, on
pages built here, so a fresh clone checks it and every probe has an input.

A fabricated chart is the defect it exists for: a chart is a picture of a curve,
and the reader returns a table of numbers read off it by eye, which then go into
the book as text.
"""
from booksmith.datasets.metrics import base, reading
from booksmith.datasets.metrics.probes.reading import probes


def _pages(blocks):
    """One page, `blocks` as (label, content)."""
    return {0: {"index": 0, "width": 100, "height": 100, "dpi": 72.0,
                "blocks": [{"block_id": j, "box": [0, 0, 9, 9], "label": lab,
                            "score": None, "order": j, "content": c,
                            "kind": "text" if c else "none"}
                           for j, (lab, c) in enumerate(blocks)],
                "raw": None, "meta": {}}}


class _Run:
    """A run of pages held in memory: the probes ask a run for its pages."""

    def __init__(self, pages):
        self._pages = pages

    def pages(self):
        return self._pages


CHART = "t, °C | n\n0 | 1.00\n200 | 0.70\n600 | 0.45"


def test_a_chart_returned_as_numbers_is_counted_and_a_described_one_is_not():
    """The rule is the label and the shape together: the shape alone would call
    every real table a fabrication, the label alone would call a chart described
    in words one."""
    r = reading.measure(_pages([("chart", CHART)]))
    assert r["charts_as_data"] == 1 and r["charts_answered"] == 1, r
    r = reading.measure(_pages([("chart", "a curve rising to the right")]))
    assert r["charts_as_data"] == 0 and r["charts_answered"] == 1, r
    # A real table returned as a grid is right and must not be counted; the rule
    # must say so itself rather than rely on `chart` being the only such label.
    r = reading.measure(_pages([("table", CHART)]))
    assert r["charts_as_data"] == 0 and r["charts_answered"] == 0, r


def test_one_delimited_line_is_a_caption_and_not_a_table():
    """Two rules, each asked where only it can answer: a caption with a bar in it
    is rejected by the numeric share, a single row of numbers by the row count,
    and nothing else would reject either."""
    r = reading.measure(_pages([("chart", "Fig. 4 | viscosity against heat")]))
    assert r["charts_as_data"] == 0, r
    r = reading.measure(_pages([("chart", "0 | 1.00")]))
    assert r["charts_as_data"] == 0, r


def test_declared_markup_that_repeats_is_not_the_model_repeating_itself():
    """A `<lcel>` run is a declared merge, not degeneration: the tags are
    stripped before the share is asked, or merge cells, dot leaders and chemistry
    read as a model repeating itself."""
    assert reading.loop_share("<lcel>" * 60) == 0.0
    assert reading.loop_share("the same words over and over " * 20) > 0.9


def test_a_formula_whose_CONTENT_repeats_is_the_residual_false_positive():
    """And the one in twenty this does not catch, said out loud: stripping removes
    the tags, not the fact that a compound repeats, and no rule over characters
    tells a chemist from a model stuck saying the same oxide."""
    assert reading.loop_share(r"\mathrm{Al}_{2}\mathrm{O}_{3} " * 20) > 0.9


def test_the_battery_can_fail_on_pages_that_carry_answers():
    """Every probe measures something, on an input built here: a set of probes that all say "no data" measures nothing."""
    lines = []
    pages = _pages([("chart", CHART), ("text", "recognised words here"),
                    ("table", "a | b\n1 | 2")])
    seen, mute, bad = base.run_probes(probes(None, _Run(pages)), log=lines.append)
    assert bad == 0, lines
    assert (seen, mute) == (6, 0), (seen, mute, lines)
    assert not any("no data" in l for l in lines), lines
