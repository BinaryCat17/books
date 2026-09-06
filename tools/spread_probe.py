"""Check the spread-cut veto: how often it fired, and whether it was right.

WHY THIS FILE EXISTS. The first edition of the veto in `djvu.py` announced "a
0.5 % threshold catches 84 % of the controls" -- and the script that computed
it never entered the tree. A day later the claim was unverifiable, and a live
book said otherwise: 11 refusals of 189, all eleven false. A measurement with
no way to repeat it is an opinion set in monospace.

WHAT IT MEASURES. Per spread: did the veto fire, and on account of what. Black
crossing the gutter falls into THREE classes:

    short         -- a dozen-odd pixels. The BINDING SHADOW, blackest of all on
                     a spread scan. A veto here is a false alarm and a galling
                     one: the shadow is evidence OF a gutter, the opposite of
                     what the veto hunts.
    continuous,
    at the edge   -- a quarter of the width and beyond, flush to the edge of
                     the sheet. The BLACK EDGE OF THE SCAN, by length
                     indistinguishable from a rule: 27..100 % of the spread. It
                     gave 44 false vetoes of 379 on the "Справочник".
    continuous,
    in the body   -- the same length, inside the sheet. A table rule crossing
                     the gutter. On this one the veto should fire -- on this
                     one only.

All three print apart, because merging them loses exactly the class of error
the gauge exists for: both times the veto was wrong, it was wrong by class.

RUN::

    python tools/spread_probe.py --selfcheck            # no books, seconds
    python tools/spread_probe.py raw/*.djvu
    python tools/spread_probe.py --pages 17,20,23 raw/book.djvu

The third form names what was found on suspect sheets: feed it a table across
the whole spread and a bare binding shadow, and the classes must differ.

BOTH SIDES ARE MEASURED ON LIVE SCANS NOW, and raising `PROBE_DPI` to 72 got
there. Negative: the 11 false vetoes of "Огнеупоры" and the 44 of the
"Справочник" are gone. Positive: the one veto left IS a real table across the
gutter ("Справочник" sheet 194, rule over 0.376 of the width) -- the positive
side is no longer synthetic-only. Partial, still: of the three known such
tables only that one is catchable at any threshold, and why is in `djvu.py`.
The cost stays asymmetric: a spurious refusal hands over a two-column spread
with its pages whole; a cut through a table destroys the numbers for good.
"""
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "src"))
from booksmith import djvu  # noqa: E402


def unpack(src, tmp):
    """djvu -> pdf into a temp dir, bypassing the freshness check in to_pdf."""
    out = os.path.join(tmp, "probe.pdf")
    subprocess.run([djvu._tool("ddjvu"), "-format=pdf", "-quality=85",
                    src, out], check=True, capture_output=True)
    return out


def cut_column(pix):
    """The same column `_gutter` picks -- so we measure that very one."""
    data = pix.samples
    lo = int(pix.width * (0.5 - djvu.GUTTER_BAND / 2))
    hi = int(pix.width * (0.5 + djvu.GUTTER_BAND / 2))
    best, best_ink = None, None
    for x in range(lo, max(hi, lo + 1)):
        ink = sum(255 - data[y * pix.stride + x] for y in range(pix.height))
        if best_ink is None or ink < best_ink:
            best, best_ink = x, ink
    return best


def probe(src, only=None):
    """One book. Returns (spreads, vetoes, continuous, short, continuous at
    the edge, detail)."""
    import pymupdf
    with tempfile.TemporaryDirectory() as tmp:
        doc = pymupdf.open(unpack(src, tmp))
        spreads = vetoed = through_total = short_total = edge_total = 0
        detail = []
        for page in doc:
            r = page.rect
            if r.width <= r.height * djvu.MIN_SPREAD_RATIO:
                continue
            sheet = page.number + 1
            if only and sheet not in only:
                continue
            spreads += 1
            pix = page.get_pixmap(dpi=djvu.PROBE_DPI,
                                  colorspace=pymupdf.csGRAY, clip=r)
            if pix.width < 8:
                continue
            x = cut_column(pix)
            through, short = djvu.dark_rows(pix, x)
            lo, hi = djvu.body_band(pix)
            # Continuous AT THE EDGE apart from continuous in the body: the
            # 391 rows of the "Справочник" that fired the veto 44 times of 379.
            # One number for both loses the class of error again.
            edge = [y for y in through if not (lo <= y < hi)]
            body = [y for y in through if lo <= y < hi]
            through_total += len(through)
            short_total += len(short)
            edge_total += len(edge)
            rule = djvu.gutter_rule(pix, x)
            is_veto = rule >= djvu.RULE_RUN
            vetoed += is_veto
            if is_veto or only:
                detail.append((sheet, pix.height, body, edge, short, rule,
                               is_veto))
        doc.close()
    return spreads, vetoed, through_total, short_total, edge_total, detail


# (case name, what to draw over two columns of "text", is a veto expected)
CASES = (
    ("a clean gutter", None, False),
    ("binding shadow at the top", "shadow-top", False),
    ("binding shadow the full height", "shadow-full", False),
    ("a rule across the whole spread", "rule-full", True),
    ("a rule across a third", "rule-third", True),
    ("a table across the whole spread", "table", True),
    # Scans are grey, not black: without this case RULE_INK could go to 250
    # and no case drawn in pure black would notice. The mutation has to be
    # caught, or the threshold is unchecked.
    ("a faded rule across the spread", "rule-grey", True),
    # Scan paper is yellowish. Without this case the same threshold could drop
    # to five and the whole sheet would become "ink".
    ("yellowed paper, a clean gutter", "paper-grey", False),
    # THE BLACK EDGE OF THE SHEET -- the defect itself: 44 false vetoes of 379
    # on the "Справочник". Run 27..100% of the width, straight through the
    # length threshold; only position tells it apart. Top and bottom apart: in
    # the live books all 391 continuous rows fell on the TOP edge, so nothing
    # but this case checks the bottom.
    ("a black sheet edge at the top", "edge-top", False),
    ("a black sheet edge at the bottom", "edge-bottom", False),
    # The other side of that threshold: a rule at the very edge of the BODY
    # must cause a veto. At 5.5% of the height -- where the "Справочник" has
    # its nearest-to-edge real rule (row 33 of 599). Reddens if RULE_EDGE goes
    # to 6%.
    ("a rule at the edge of the sheet body", "rule-near-edge", True),
    # A rule ONE probe row tall: 703 blocks of 882 in the "Справочник" are
    # exactly that. The old quantity -- the share of continuous rows -- wanted
    # three of 599 and would never have fired on such a rule.
    ("a rule one probe row tall", "rule-hairline", True),
    # The binding shadow is not always at the edge: in the "Справочник" 4 short
    # rows across the gutter lie at 6.8..13.9% of the height, run up to 0.109
    # of the width. Without this case nothing checks the LOWER side of
    # RULE_RUN: on the edge cases RULE_EDGE now cuts it off.
    ("binding shadow inside the sheet body", "shadow-body", False),
    # A table on ONE page of the spread whose rule runs past the geometric
    # middle: the gutter almost never falls at the half, which is why a column
    # is searched for at all. Such a sheet can and must be cut -- to the right
    # of the rule. Reddens if GUTTER_BAND is narrowed: the cut then hits the
    # middle, that is, the rule.
    ("one page's rule past the middle", "rule-one-page", False),
)


def selfcheck():
    """Can the veto fail -- on drawn sheets, without books.

    Half the cases must raise a veto and half must not. A signal that cannot be
    made to fail is not an instrument: the `≠` mark of the old parse stood on
    416 tables of 448 and meant nothing precisely because nobody checked it
    against a known corruption. Returns 1 on any mismatch: a check has to be
    able to stop somebody.

    WHAT IT CATCHES. A run with a knob shifted on purpose (mutation)::

        RULE_RUN 0.25 -> 0.9         6 mismatches of 14
        RULE_RUN 0.25 -> 0.05        1
        RULE_EDGE 0.03 -> 0.0        2
        RULE_EDGE 0.03 -> 0.06       1
        RULE_EDGE 0.03 -> 0.2        1
        RULE_INK 96 -> 250           1
        RULE_INK 96 -> 5             1
        RULE_BAND 0.012 -> 0.4       1
        RULE_BAND 0.012 -> 0.0001    0 -- NOT caught
        GUTTER_BAND 0.20 -> 0.9      6
        GUTTER_BAND 0.20 -> 0.001    1
        PROBE_DPI 72 -> 12           2
        PROBE_DPI 72 -> 150          0 -- NOT caught
        PROBE_DPI 72 -> 36           0 -- NOT caught, and this is the dear one
        MIN_SPREAD_RATIO 1.15 -> 9   0 -- NOT caught

    `RULE_EDGE` is caught BOTH ways, and that is not decoration: a threshold
    brought in against false vetoes must redden when it is removed (the 44 come
    back) and when it is raised (a rule close to the edge stops being seen). A
    threshold checked on one side can be moved as far as you like towards the
    other.

    Four are not caught, and keeping quiet about that is the background all
    this was written to leave. `MIN_SPREAD_RATIO` honestly cannot be: the
    self-check calls `_gutter` directly and never touches the spread test.
    `RULE_BAND` down and `PROBE_DPI` up make the gauge MORE precise -- narrower
    band, stricter filter; higher resolution, clearer rule -- so on drawn
    sheets they do no harm, and whether they do on live scans this cannot say.
    `PROBE_DPI` DOWN to the old 36 is the expensive one: drawn rules stay pure
    black at any resolution, while on the live "Справочник" that step sank
    three real tables to 0.000..0.043, below a scan blot. The drawn sheets
    cannot see it; the books did.
    """
    import pymupdf

    def sheet(kind):
        doc = pymupdf.open()
        pg = doc.new_page(width=800, height=500)
        if kind == "paper-grey":
            pg.draw_rect(pg.rect, color=None, fill=(0.88, 0.85, 0.78))
        for x0 in (60, 430):                      # two columns of "text"
            for i in range(20):
                pg.draw_line(pymupdf.Point(x0, 60 + i * 20),
                             pymupdf.Point(x0 + 310, 60 + i * 20),
                             color=(0, 0, 0), width=3)
        black, grey = (0, 0, 0), (0.55, 0.55, 0.55)
        if kind == "shadow-top":
            # WIDER than the search band (400 +- 40 pt), or `argmin` walks off
            # the shadow into the clean column next door, the case passes for
            # the wrong reason and catches no threshold mutation. In the book
            # the shadow is just so: it covers the gutter, nowhere to walk.
            pg.draw_rect(pymupdf.Rect(340, 0, 460, 12), color=None, fill=black)
        elif kind == "shadow-full":
            pg.draw_rect(pymupdf.Rect(396, 0, 404, 500), color=None, fill=black)
        elif kind == "rule-full":
            pg.draw_line(pymupdf.Point(60, 250), pymupdf.Point(740, 250),
                         color=black, width=4)
        elif kind == "rule-third":
            pg.draw_line(pymupdf.Point(270, 250), pymupdf.Point(530, 250),
                         color=black, width=4)
        elif kind == "rule-grey":
            pg.draw_line(pymupdf.Point(60, 250), pymupdf.Point(740, 250),
                         color=grey, width=5)
        elif kind == "table":
            for i in range(8):
                pg.draw_line(pymupdf.Point(60, 100 + i * 40),
                             pymupdf.Point(740, 100 + i * 40),
                             color=black, width=4)
        elif kind == "edge-top":
            # Full width and flush to the edge, like the edge of a real scan.
            # 8 pt at a height of 500 pt = 1.6% of the probe: as deep as the
            # deepest edge of the "Справочник" (9 rows of 604, 1.5%).
            pg.draw_rect(pymupdf.Rect(0, 0, 800, 8), color=None, fill=black)
        elif kind == "edge-bottom":
            pg.draw_rect(pymupdf.Rect(0, 492, 800, 500), color=None,
                         fill=black)
        elif kind == "rule-near-edge":
            # 28 pt of 500 = 5.5% of the height -- the nearest-to-edge real
            # rule we could measure on a live book.
            pg.draw_rect(pymupdf.Rect(60, 28, 740, 30), color=None, fill=black)
        elif kind == "rule-hairline":
            # 2 pt -- one probe row at the old PROBE_DPI 36, two at today's
            # 72. Bounds on whole pixels, or antialiasing smears the rule over
            # an extra row and the case passes for the wrong reason.
            pg.draw_rect(pymupdf.Rect(60, 250, 740, 252), color=None,
                         fill=black)
        elif kind == "shadow-body":
            # Same width as the shadow on top (or argmin walks off into a
            # clean column), but at 20% of the height -- in the body, where
            # RULE_EDGE no longer cuts it off. Run 120 pt of 800 = 15% of the
            # width against RULE_RUN = 25%. BETWEEN rows of "text" (20 pt
            # apart): stuck to a row, the blot would run 85% of the width and
            # the case would pass for the wrong reason -- so the first edition
            # came out.
            pg.draw_rect(pymupdf.Rect(340, 108, 460, 114), color=None,
                         fill=black)
        elif kind == "rule-one-page":
            # Ends past the middle of the sheet (410 of 800) but short of the
            # column the cut will take: a clean band 410..430 lies to its
            # right.
            pg.draw_rect(pymupdf.Rect(60, 250, 410, 254), color=None,
                         fill=black)
        return doc

    bad = 0
    print("self-check of the veto:")
    for name, kind, want in CASES:
        doc = sheet(kind)
        pg = doc[0]
        got = djvu._gutter(pg, pg.rect) is None
        doc.close()
        ok = got == want
        bad += not ok
        print(f"  {name:38s} veto {'YES' if got else 'no '}  "
              f"expected {'YES' if want else 'no '}"
              f"{'' if ok else '   <-- MISMATCH'}")
    print(f"  mismatches {bad} of {len(CASES)}")
    return 1 if bad else 0


def main(argv):
    only, files, i = None, [], 0
    while i < len(argv):
        if argv[i] == "--selfcheck":
            i += 1
        elif argv[i] == "--pages":
            only = {int(x) for x in argv[i + 1].split(",")}
            i += 2
        else:
            files.append(argv[i])
            i += 1

    if "--selfcheck" in argv:
        return selfcheck()
    if not files:
        print(__doc__)
        return 2

    for src in files:
        spreads, vetoed, through, short, edge, detail = probe(src, only)
        print(f"\n{os.path.basename(src)}")
        print(f"  spreads {spreads}, vetoes {vetoed} "
              f"({vetoed / max(1, spreads):.1%})")
        print(f"  rows of black across the gutter: continuous {through} "
              f"(of them on the sheet edge {edge}, in the body "
              f"{through - edge}), short {short}")
        if short and not through:
            print("  -- all the black turned out short: without the "
                  "distinction the veto would have fired for nothing on "
                  "every such spread")
        if edge and through == edge:
            print("  -- every continuous row lies on the sheet edge: "
                  "without telling position apart the veto would have fired "
                  "for nothing")
        for sheet_no, h, body, edg, sh, rule, v in detail[:20]:
            print(f"    sheet {sheet_no}: probe {h} rows, continuous in the "
                  f"body {body}, on the edge {edg}, short {sh}, "
                  f"rule {rule:.3f} of the width{'  VETO' if v else ''}")
        if len(detail) > 20:
            print(f"    ... and {len(detail) - 20} more")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
