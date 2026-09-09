"""The reader caught without truth: fabricated charts and looping.

`text.py` is the honest measurement of reading and needs characters nobody
has annotated for a real scan, so it has never produced a number. This file
covers the half that needs no truth, on pages built here -- so a fresh clone
checks it, and so the battery has an input where every probe can fire.

THE FABRICATED CHART IS THE DEFECT THIS EXISTS FOR. A chart is a picture of
a curve; the reader returns a table of numbers read off it by eye, and those
numbers go into the book as text. On the one real level-two run, 56 of 60
answered charts. The counter aimed at it cannot fire -- `chart` is routed
with the promise `text` and a pipe table sniffs as `text`, so promise and
guess agree on all sixty.
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
    """The rule is the LABEL and the SHAPE together.

    The shape alone would call every real table a fabrication; the label
    alone would call a chart described in words one. Both, and neither on
    its own, is what makes this measure the defect and not the format.
    """
    r = reading.measure(_pages([("chart", CHART)]))
    assert r["charts_as_data"] == 1 and r["charts_answered"] == 1, r
    r = reading.measure(_pages([("chart", "a curve rising to the right")]))
    assert r["charts_as_data"] == 0 and r["charts_answered"] == 1, r
    # A REAL TABLE RETURNED AS A GRID IS RIGHT, and must not be counted.
    # Measured over all 6080 answered blocks of the real run, `chart` is the
    # only label that produces two or more delimited rows -- but the rule
    # must say so itself rather than rely on that.
    r = reading.measure(_pages([("table", CHART)]))
    assert r["charts_as_data"] == 0 and r["charts_answered"] == 0, r


def test_one_delimited_line_is_a_caption_and_not_a_table():
    """Two rules, and each asked where only it can answer.

    A caption with a bar in it is rejected by the NUMERIC share; a single
    row of numbers is rejected by the row count, and nothing else would
    reject it. Written with a wordy caption alone, the row rule was never
    consulted and could be deleted with this check still green.
    """
    r = reading.measure(_pages([("chart", "Fig. 4 | viscosity against heat")]))
    assert r["charts_as_data"] == 0, r
    r = reading.measure(_pages([("chart", "0 | 1.00")]))
    assert r["charts_as_data"] == 0, r


def test_declared_markup_that_repeats_is_not_the_model_repeating_itself():
    """A `<lcel>` run is a DECLARED merge, not degeneration.

    Asked of the raw text at 0.20, the real run flagged 33 blocks of which
    13 were markup repeating for a reason: merge cells, dot leaders, and
    chemistry. Stripping the tags and asking 0.30 gives 20 flagged, 19 of
    them genuine.
    """
    assert reading.loop_share("<lcel>" * 60) == 0.0
    assert reading.loop_share("the same words over and over " * 20) > 0.9


def test_a_formula_whose_CONTENT_repeats_is_the_residual_false_positive():
    """AND THE ONE IN TWENTY THIS DOES NOT CATCH, said out loud.

    Stripping removes the LaTeX and OTSL TAGS. It cannot remove the fact
    that `Al 2 O 3 Al 2 O 3 ...` repeats, because that is the compound
    repeating, and no rule over characters can tell a chemist writing the
    same oxide nine times from a model stuck saying it. Measured at 95 %
    precision on the real run, and this is the other five: a defect of the
    instrument, recorded rather than asserted away, because a check that
    demanded 0.0 here would be demanding something untrue.
    """
    assert reading.loop_share(r"\mathrm{Al}_{2}\mathrm{O}_{3} " * 20) > 0.9


def test_the_battery_can_fail_on_pages_that_carry_answers():
    """EVERY PROBE MEASURES SOMETHING, on an input built here.

    A battery whose probes all say "no data" is not a battery, and this
    project has just paid for that lesson one metric over: the junk mask's
    probes were written against a bench with no binding, so six of them were
    silent and the whole feature could be deleted with the suite green.
    """
    lines = []
    pages = _pages([("chart", CHART), ("text", "recognised words here"),
                    ("table", "a | b\n1 | 2")])
    seen, mute, bad = base.run_probes(probes(None, _Run(pages)), log=lines.append)
    assert bad == 0, lines
    assert (seen, mute) == (6, 0), (seen, mute, lines)
    assert not any("no data" in l for l in lines), lines
