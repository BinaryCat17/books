"""The veto on cutting a spread: what it must see, and what it must not.

The agreement here is with THE SCANNED SHEET, not with a second file, and it
used to live only as a number in a docstring. The number lasted exactly one
edition: the first gave 11 false refusals of 189
on "Технология огнеупоров", the second 44 of 379 on "Справочник по чугунному
литью" (the rebuild returned 716 pages instead of 760), and both times the
defect was the same by make -- the veto measured ink, not WHAT KIND of ink.

Every check below is held by a measurement on live scans and can fail, proved
by putting the defect back:

    black sheet edge at the top            old code: veto (44 of 379)
    the same edge at the bottom            old code: veto
    a rule one probe row thick             old code: NO veto (threshold
                                           "three rows", while 703 rules of
                                           882 are exactly one row high)
    scan height does not decide            old code: 599 rows -- veto,
                                           601 -- none, on the same sheet

Measured on 568 spreads of two books: the handbook 379, the refractories 189.

The probe was 36 dpi and is now 72, for a third defect of the same make: at
36 dpi the THREE real tables crossing the gutter of the handbook gave 0.000,
0.043 and 0.038, weaker than a scan blot (0.109), and all three were cut. At
72 the gap is complete: 0.376 at one of them, exactly 0.000 at the other 378.
The other two are caught at no threshold -- their rules stop against the
closed frame of each page; named in `djvu.py`, not repaired here.
"""
import os
import sys

import support

from booksmith import djvu

# Points in one probe row. Derived FROM THE KNOB, not from the literal 36 that
# stood here before. Not cosmetic: with 36 wired in, `PROBE_DPI` = 72 would
# have this file drawing sheets at the wrong scale while the checks passed,
# checking nothing. The knob can move now, and the checks follow it.
PT = 72 / djvu.PROBE_DPI


WIDE = 750                   # sheet width IN PROBE PIXELS


def _spread(rows=599, draw=()):
    """A synthetic spread: two columns of "text" and a gutter between them.

    EVERYTHING HERE IS IN PROBE PIXELS, `draw` included. The sheet used to be
    half in probe rows (height) and half in points (width, row step, spots),
    agreeing by accident at `PROBE_DPI` = 36. At 72 it broke aloud: the
    binding shadow of `test_binding_shadow_in_the_body` landed on a row of
    "text" and stuck to it into a full-width run -- the very trap the comment
    below warns of. A bench with two coordinate systems rests on coincidence.

    The numbers are chosen so that at 36 dpi the sheet comes out as before to
    the pixel (750 x 599 probe pixels), so every measurement holding these
    checks is still about the same sheet.
    """
    import pymupdf
    h = rows * PT
    w = WIDE * PT                    # wider than 1.15 * h, or it is no spread
    doc = pymupdf.open()
    pg = doc.new_page(width=w, height=h)
    # Two columns of "text": without them `argmin` has nothing to catch and
    # the cut goes anywhere. The step of 20 probe pixels is chosen so that no
    # row lands on the middle of the sheet: stuck to a text row, any spot by
    # the gutter gives a full-width run and the check passes for a wrong
    # reason.
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
    from booksmith import djvu
    x = djvu._gutter(pg, pg.rect)
    doc.close()
    return x


def test_scan_edge_at_the_top_does_not_veto():
    """A black sheet edge is not a table rule: cutting is allowed.

    The defect itself: on the handbook 391 full-width rows LIE AT THE EDGE
    (204 of them on row 0), none in the body of the sheet, and the run at the
    edge is 27..100 % of the width -- it clears the length threshold
    outright. Hence 44 refusals of 379 spreads, all false.
    """
    doc, pg = _spread(draw=[(0, 0, WIDE, 3)])
    assert _cut(doc, pg) is not None, (
        "the black edge of the sheet was taken for a table rule -- that "
        "is the 44 false vetoes of the handbook's 379 spreads")


def test_scan_edge_at_the_bottom_does_not_veto():
    """The same from below.

    Deliberate: all 391 full-width rows of the live books fell on the UPPER
    edge, so the lower half of the threshold has nothing to check against.
    Half a condition checked by zero observations is an unchecked half.
    """
    doc, pg = _spread(draw=[(0, 599 - 3, WIDE, 599)])
    assert _cut(doc, pg) is not None, (
        "an edge at the bottom of the sheet forbade the cut -- the "
        "threshold on position works only from above")


def test_rule_across_the_gutter_vetoes():
    """A rule across the whole spread: cutting is forbidden.

    The positive side of the veto. On live scans it fires exactly ONCE in 568
    spreads -- handbook 193, above. Here it said no table in our books
    crosses the gutter at all, on a 36 dpi count of one black row through the
    central 10 % of the width in the body of a sheet per 568 spreads, and
    that one the tail of an edge. `djvu.py` retracts the claim, and it is why
    the probe stayed at 36. One live positive is no bench, so the side is
    held here.
    """
    doc, pg = _spread(draw=[(50, 300, 700, 302)])
    assert _cut(doc, pg) is None, (
        "a rule across the whole spread did not stop the cut -- a table "
        "cut in two is restored by nothing")


def test_hairline_rule_of_a_single_probe_row_vetoes():
    """A rule ONE probe row thick is visible to the veto.

    Measured: at 36 dpi a real rule takes one row -- 703 blocks of 882 in the
    handbook, median 1. The old quantity, the share of full-width rows in the
    probe height against `RULE_MAX` = 0.005, demanded THREE on a 599-row
    probe, that is, it would never have fired on a real rule.
    """
    doc, pg = _spread(draw=[(50, 300, 700, 301)])
    assert _cut(doc, pg) is None, (
        "a rule one probe row thick went past the veto -- the threshold "
        "measures the thickness of a rule instead of its length")


def test_veto_does_not_depend_on_the_height_of_the_scan():
    """The same sheet, a probe two rows taller -- the same answer.

    The old quantity was quantised in steps of 1/probe height: with three
    full-width rows 3/599 = 0.005008 vetoed and 3/601 = 0.004992 did not. On
    the handbook, of the 39 spreads with exactly three rows, 31 got a veto
    (those whose scan came out 599 rows tall) and 8 did not (601 and 604).
    The scan height decided, not the sheet.
    """
    answers = []
    for rows in (599, 601):
        doc, pg = _spread(rows=rows, draw=[(0, 0, WIDE, 3)])
        answers.append(_cut(doc, pg) is None)
    assert answers[0] == answers[1], (
        f"a 599-row probe -> veto {answers[0]}, a 601-row probe -> veto "
        f"{answers[1]}: the decision follows the scan height, not the sheet")
    assert not answers[0], "a sheet edge must not forbid the cut at all"


def test_rule_near_the_edge_of_the_body_still_vetoes():
    """A rule at the very edge of the sheet body DOES raise the veto.

    The other side of the threshold on position: only so much of the probe
    may be cut away. The closest real rule to an edge we could measure is at
    5.5 % of the height (handbook, row 33 of 599); on the two other books,
    8.1 % ("Кристаллизация") and 7.7 % ("Биохимия"). The check reddens if
    `RULE_EDGE` is raised to 6 %.
    """
    doc, pg = _spread(draw=[(50, 33, 700, 34)])
    assert _cut(doc, pg) is None, (
        "a rule at 5.5 % of the height is invisible to the veto -- the "
        "edge strip has eaten the body of the sheet")


def test_binding_shadow_in_the_body_does_not_veto():
    """A binding shadow in the body of the sheet is not a rule: cut away.

    A shadow is not always at an edge: in the handbook 4 short rows of black
    across the gutter sit at 6.8..13.9 % of the height, run up to 0.109 of
    the width, and only length separates them from a rule. The margin here
    was called "2.3 times to the threshold of 0.25"; `djvu.py` retracts it --
    2.3x was measured at 36 dpi over a missed positive.
    """
    doc, pg = _spread(draw=[(345, 50, 405, 53)])
    assert _cut(doc, pg) is not None, (
        "a binding shadow was taken for a rule -- a shadow is evidence of "
        "the spine, that is, the exact opposite of what the veto looks for")


def test_a_thin_rule_across_the_gutter_needs_the_probe_we_declared():
    """A THIN rule across the gutter must be visible -- the knob sees it.

    This check stands for `PROBE_DPI`, not for the veto, and it is the only
    one here that does. The rest are deliberately indifferent to the knob (the
    sheet is in probe pixels), so none would notice it going back to 36 --
    which kills real tables in silence, by the three numbers above.

    The rule here is given IN POINTS, not in probe pixels, and that is the
    whole idea: a point is tied to the paper, a probe pixel to the knob.
    0.6 pt is a thin but ordinary rule (5 pixels on a 600 dpi scan). At 72 dpi
    it fills almost a whole probe row and stays black; at 36 it averages with
    white, lightens past `RULE_INK` and disappears.

    Sweep by thickness (both sides -- veto or cut):

        0.4 pt   36 dpi CUTS   72 dpi veto
        0.6 pt   36 dpi CUTS   72 dpi veto      <- taken here
        0.8 pt   36 dpi veto   72 dpi veto
        1.0 pt and thicker -- both see it
    """
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


def test_the_probe_selfcheck_agrees_with_the_veto():
    """`tools/spread_probe.py --selfcheck` must agree with this code.

    An agreement between files: the gauge measures the veto with its own
    fourteen sheets and its own copy of the column choice. Drifting from
    `djvu.py`, it keeps printing numbers -- about something other than what
    the pipeline does. That is how the old "a 0.5 % threshold catches 84 % of
    the controls" became unverifiable.
    """
    import importlib.util
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(root, "tools", "spread_probe.py")
    if not os.path.exists(path):
        support.skip(f"no {path} -- the gauge is not in the tree")
    spec = importlib.util.spec_from_file_location("spread_probe", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["spread_probe"] = mod
    spec.loader.exec_module(mod)
    assert len(mod.CASES) >= 14, (
        f"selfcheck sheets {len(mod.CASES)}, there were 14: cases have "
        f"been struck out, not added")
    import io
    from contextlib import redirect_stdout
    buf = io.StringIO()
    with redirect_stdout(buf):
        bad = mod.selfcheck()
    # `selfcheck` returns 1 on ANY divergence, not their number: they are
    # named in what it printed, so take them from there -- otherwise a failure
    # says "1" and keeps quiet about which sheet diverged.
    assert bad == 0, (f"the gauge diverged from the veto, sheets "
                      f"{len(mod.CASES)}:\n" + buf.getvalue())
