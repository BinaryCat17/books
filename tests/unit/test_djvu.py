"""The veto on cutting a spread: what it must see, and what it must not.

The agreement here is with the scanned sheet, not with a second file: the veto
must fire on a table rule crossing the gutter and stay silent on the black edge
of a scan and on the binding shadow, whatever the height of the probe.

Every check below is held by a measurement on live scans and can fail: putting
the old quantity back reddens it.
"""

from booksmith.processing.extract import djvu

# Points in one probe row, derived from the knob: with 36 wired in, a `PROBE_DPI`
# of 72 would draw these sheets at the wrong scale while the checks passed.
PT = 72 / djvu.PROBE_DPI


WIDE = 750                   # sheet width IN PROBE PIXELS


def _spread(rows=599, draw=()):
    """A synthetic spread: two columns of "text" and a gutter between them.
    Everything here is in probe pixels, `draw` included -- a bench with two
    coordinate systems rests on coincidence."""
    import pymupdf
    h = rows * PT
    w = WIDE * PT                    # wider than 1.15 * h, or it is no spread
    doc = pymupdf.open()
    pg = doc.new_page(width=w, height=h)
    # Two columns of "text": without them `argmin` has nothing to catch and the
    # cut goes anywhere. The step of 20 probe pixels keeps every row off the
    # middle of the sheet, where a spot stuck to a row gives a full-width run.
    y = 25
    while y < rows - 25:
        pg.draw_line(pymupdf.Point(50 * PT, y * PT),
                     pymupdf.Point(350 * PT, y * PT),
                     color=(0, 0, 0), width=1.5 * PT)
        pg.draw_line(pymupdf.Point(400 * PT, y * PT),
                     pymupdf.Point(700 * PT, y * PT),
                     color=(0, 0, 0), width=1.5 * PT)
        y += 20
    for x0, y0, x1, y1 in draw:
        pg.draw_rect(pymupdf.Rect(x0 * PT, y0 * PT, x1 * PT, y1 * PT),
                     color=None, fill=(0, 0, 0))
    return doc, pg


def _cut(doc, pg):
    """Where to cut; `None` is a veto."""
    from booksmith.processing.extract import djvu
    x = djvu._gutter(pg, pg.rect)
    doc.close()
    return x


def test_scan_edge_at_the_top_does_not_veto():
    """A black sheet edge is not a table rule: cutting is allowed. The run at the
    edge is 27..100 % of the width and clears the length threshold outright, so
    only its position tells it from a rule."""
    doc, pg = _spread(draw=[(0, 0, WIDE, 3)])
    assert _cut(doc, pg) is not None, (
        "the black edge of the sheet was taken for a table rule -- that "
        "is the 44 false vetoes of the handbook's 379 spreads")


def test_scan_edge_at_the_bottom_does_not_veto():
    """The same from below, deliberately: every full-width row of the live books
    fell on the upper edge, so the lower half of the threshold has nothing else
    to check against."""
    doc, pg = _spread(draw=[(0, 599 - 3, WIDE, 599)])
    assert _cut(doc, pg) is not None, (
        "an edge at the bottom of the sheet forbade the cut -- the "
        "threshold on position works only from above")


def test_rule_across_the_gutter_vetoes():
    """A rule across the whole spread: cutting is forbidden. The positive side
    fires once in 568 live spreads, and one live positive is no bench, so the
    side is held here."""
    doc, pg = _spread(draw=[(50, 300, 700, 302)])
    assert _cut(doc, pg) is None, (
        "a rule across the whole spread did not stop the cut -- a table "
        "cut in two is restored by nothing")


def test_hairline_rule_of_a_single_probe_row_vetoes():
    """A rule one probe row thick is visible to the veto: a real rule takes one
    row -- 703 blocks of 882 in the handbook -- so a threshold on the share of
    full-width rows in the probe height would never fire on one."""
    doc, pg = _spread(draw=[(50, 300, 700, 301)])
    assert _cut(doc, pg) is None, (
        "a rule one probe row thick went past the veto -- the threshold "
        "measures the thickness of a rule instead of its length")


def test_veto_does_not_depend_on_the_height_of_the_scan():
    """The same sheet, a probe two rows taller -- the same answer. A quantity
    quantised in steps of 1/probe height lets the scan height decide instead of
    the sheet: 3/599 vetoes where 3/601 does not."""
    answers = []
    for rows in (599, 601):
        doc, pg = _spread(rows=rows, draw=[(0, 0, WIDE, 3)])
        answers.append(_cut(doc, pg) is None)
    assert answers[0] == answers[1], (
        f"a 599-row probe -> veto {answers[0]}, a 601-row probe -> veto "
        f"{answers[1]}: the decision follows the scan height, not the sheet")
    assert not answers[0], "a sheet edge must not forbid the cut at all"


def test_rule_near_the_edge_of_the_body_still_vetoes():
    """A rule at the very edge of the sheet body does raise the veto: the other
    side of the threshold on position, the closest real rule to an edge measured
    sitting at 5.5 % of the height. Reddens if `RULE_EDGE` is raised to 6 %."""
    doc, pg = _spread(draw=[(50, 33, 700, 34)])
    assert _cut(doc, pg) is None, (
        "a rule at 5.5 % of the height is invisible to the veto -- the "
        "edge strip has eaten the body of the sheet")


def test_binding_shadow_in_the_body_does_not_veto():
    """A binding shadow in the body of the sheet is not a rule: cut away. A shadow
    is not always at an edge -- in the handbook four short rows sit at 6.8..13.9 %
    of the height -- and only length separates them from a rule."""
    doc, pg = _spread(draw=[(345, 50, 405, 53)])
    assert _cut(doc, pg) is not None, (
        "a binding shadow was taken for a rule -- a shadow is evidence of "
        "the spine, that is, the exact opposite of what the veto looks for")


def test_a_thin_rule_across_the_gutter_needs_the_probe_we_declared():
    """A thin rule across the gutter must be visible: this check stands for
    `PROBE_DPI` and is the only one here that does, the rest being drawn in probe
    pixels. The rule is given in points, which are tied to the paper."""
    import pymupdf
    doc, pg = _spread()
    # 50..700 are the same probe pixels as the thick rule in the check above;
    # the thickness is IN POINTS, which is why it is not multiplied by PT.
    pg.draw_rect(pymupdf.Rect(50 * PT, 300 * PT, 700 * PT, 300 * PT + 0.6),
                 color=None, fill=(0, 0, 0))
    assert _cut(doc, pg) is None, (
        "a thin rule across the spine is invisible to the veto: the probe "
        "is too coarse. "
        f"PROBE_DPI = {djvu.PROBE_DPI}, while the measurement on the "
        "handbook demands 72 -- at 36 three real tables across the spine "
        "are cut in silence")
