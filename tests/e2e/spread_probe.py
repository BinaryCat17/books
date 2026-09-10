"""The spread-cut veto gauge: how often it fired, and whether it was right.

Per spread it prints the black crossing the gutter in three classes: short
(the binding shadow), continuous at the sheet edge (the black scan border),
and continuous in the body (a table rule) -- only the third should veto.

    python tests/e2e/spread_probe.py --selfcheck        # no books, seconds
    python tests/e2e/spread_probe.py raw/*.djvu
    python tests/e2e/spread_probe.py --pages 17,20,23 raw/book.djvu
"""
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))), "src"))
from booksmith.processing.extract import djvu


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
            # Edge apart from body: one number for both loses the class of
            # error.
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
    # Scans are grey, not black: without this case RULE_INK could go to 250.
    ("a faded rule across the spread", "rule-grey", True),
    # Scan paper is yellowish: without this case RULE_INK could drop to 5.
    ("yellowed paper, a clean gutter", "paper-grey", False),
    # The black edge of a scan: only its position tells it from a rule.
    # Bottom as well as top: on live scans every continuous row fell on top.
    ("a black sheet edge at the top", "edge-top", False),
    ("a black sheet edge at the bottom", "edge-bottom", False),
    # The other side of that threshold: a rule at 5.5% of the height vetoes.
    ("a rule at the edge of the sheet body", "rule-near-edge", True),
    # A rule one probe row tall, which most real rules are.
    ("a rule one probe row tall", "rule-hairline", True),
    # A binding shadow inside the sheet body: the lower side of RULE_RUN.
    ("binding shadow inside the sheet body", "shadow-body", False),
    # A one-page rule past the geometric middle: cuttable, to the right of it.
    ("one page's rule past the middle", "rule-one-page", False),
)


def selfcheck():
    """Can the veto fail -- on drawn sheets, without books. Half the cases
    must raise a veto and half must not; returns 1 on any mismatch. RULE_EDGE
    is checked on both sides, or it could be moved freely towards one."""
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
            # Wider than the search band (400 +- 40 pt), or argmin walks off
            # the shadow into the clean column next door.
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
            # Full width and flush to the edge, like a real scan edge; 8 pt
            # of 500 = 1.6% of the probe, as deep as the deepest measured.
            pg.draw_rect(pymupdf.Rect(0, 0, 800, 8), color=None, fill=black)
        elif kind == "edge-bottom":
            pg.draw_rect(pymupdf.Rect(0, 492, 800, 500), color=None,
                         fill=black)
        elif kind == "rule-near-edge":
            # 28 pt of 500 = 5.5% of the height: the nearest-to-edge real
            # rule measured on a live book.
            pg.draw_rect(pymupdf.Rect(60, 28, 740, 30), color=None, fill=black)
        elif kind == "rule-hairline":
            # 2 pt = one probe row. Whole-pixel bounds, or antialiasing
            # smears the rule over an extra row.
            pg.draw_rect(pymupdf.Rect(60, 250, 740, 252), color=None,
                         fill=black)
        elif kind == "shadow-body":
            # In the body, past RULE_EDGE: 15% of the width against RULE_RUN
            # 25%, and between rows of "text", not stuck to one.
            pg.draw_rect(pymupdf.Rect(340, 108, 460, 114), color=None,
                         fill=black)
        elif kind == "rule-one-page":
            # Ends past the middle (410 of 800) but left of the cut column:
            # 410..430 stays clean.
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
