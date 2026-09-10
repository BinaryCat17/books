"""An atlas of drawings: landscape sheet, large graphics, little text"""

from datasets.draw import (
    PROSE_EN,
    _callouts,
    _caption,
    _flow,
    _frame_stamp,
    _grid,
    _halftone,
    _page,
    _plate,
    _put,
    _say,
    _table,
    _text_w,
)

SHEET = (1440, 1012)
PT = 0.5
PW, PH = (SHEET[0] * PT, SHEET[1] * PT)
MARGIN, TOP, BOT_Y = (26.0, 34.0, 480.0)
ABOUT = "album of drawings: landscape sheet, drawing field, title block, specification inside the field, callout numbers; tests `image` against a nested `table`"


def _sheet(doc, wide=False):
    return _page(doc, wide=wide, pw=PW, ph=PH)


def c_atl_plate_only(doc, rng):
    pg = _sheet(doc)
    t = []
    _plate(pg, t, MARGIN + 40, TOP + 10, PW - 2 * MARGIN - 80, 380)
    _caption(pg, t, MARGIN + 46, TOP + 408, "Fig. 12  Machine tool bed")
    return (pg, t)


def c_atl_frame_stamp(doc, rng):
    pg = _sheet(doc)
    t = []
    _plate(pg, t, MARGIN + 30, TOP + 6, PW - 2 * MARGIN - 60, 360)
    _frame_stamp(pg, t, 10, 10, PW - 10, PH - 10)
    return (pg, t)


def c_atl_spec_inside(doc, rng):
    pg = _sheet(doc)
    t = []
    _plate(pg, t, MARGIN, TOP, 400, 380)
    _table(
        pg,
        t,
        MARGIN + 430,
        TOP + 30,
        _grid(MARGIN + 430, 3, colw=68.0, gap=6.0),
        22,
        size=5.6,
        colw=68.0,
        step=9.4,
    )
    _frame_stamp(pg, t, 10, 10, PW - 10, PH - 10, no="26.68")
    return (pg, t)


def c_atl_two_views(doc, rng):
    pg = _sheet(doc)
    t = []
    _plate(pg, t, MARGIN + 20, TOP + 10, PW - 2 * MARGIN - 40, 360, views=2)
    _caption(pg, t, MARGIN + 26, TOP + 386, "Fig. 14  Front view")
    _caption(pg, t, PW / 2 + 20, TOP + 386, "Fig. 15  Section A-A")
    return (pg, t)


def c_atl_callouts(doc, rng):
    pg = _sheet(doc)
    t = []
    _plate(pg, t, MARGIN + 90, TOP, PW - 2 * MARGIN - 180, 380)
    _callouts(
        pg,
        t,
        PW / 2,
        TOP + 190,
        110,
        [(20, 1), (75, 2), (135, 3), (200, 4), (250, 5), (315, 6)],
        PW,
    )
    _caption(pg, t, MARGIN + 96, TOP + 400, "Fig. 16  Assembly, items 1-6")
    return (pg, t)


def c_atl_caption_above(doc, rng):
    pg = _sheet(doc)
    t = []
    _caption(pg, t, MARGIN + 46, TOP + 10, "Fig. 17  Tailstock, plan")
    _plate(pg, t, MARGIN + 40, TOP + 20, PW - 2 * MARGIN - 80, 380)
    return (pg, t)


def c_atl_photo_plate(doc, rng):
    pg = _sheet(doc)
    t = []
    _halftone(
        pg, t, MARGIN + 60, TOP, PW - 2 * MARGIN - 120, 370, "Fig. 18  Milling head, photograph"
    )
    return (pg, t)


def c_atl_text_and_plate(doc, rng):
    pg = _sheet(doc)
    t = []
    _plate(pg, t, MARGIN + 60, TOP, PW - 2 * MARGIN - 120, 300)
    _caption(pg, t, MARGIN + 66, TOP + 318, "Fig. 19  Gearbox, section")
    _flow(pg, t, MARGIN, TOP + 336, BOT_Y, PROSE_EN, w=PW - 2 * MARGIN)
    return (pg, t)


def c_atl_spread_plate(doc, rng):
    pg = _sheet(doc, wide=True)
    t = []
    _plate(pg, t, MARGIN + 40, TOP, 2 * PW - 2 * MARGIN - 80, 400)
    _caption(pg, t, MARGIN + 46, TOP + 420, "Fig. 20  Machine tool bed, general arrangement")
    return (pg, t)


def c_atl_rotated_plate(doc, rng):
    pg = _sheet(doc)
    t = []
    _plate(pg, t, MARGIN + 40, TOP, PW - 2 * MARGIN - 200, 370)
    _frame_stamp(pg, t, 10, 10, PW - 10, PH - 10, no="26.69")
    return (pg, t)


def c_atl_sparse(doc, rng):
    pg = _sheet(doc)
    t = []
    _plate(pg, t, MARGIN + 40, TOP + 40, 240, 180)
    _caption(pg, t, MARGIN + 46, TOP + 236, "Fig. 21  Detail of key")
    _put(pg, PW / 2 - 8, PH - 24, "48", 6.4, sheet_w=PW)
    t.append((PW / 2 - 10, PH - 24 - 6.4, PW / 2 - 8 + _text_w("48", 6.4) + 2, PH - 22, "number"))
    _say(t, "48")
    return (pg, t)


CASES = {
    "atl_plate_only": c_atl_plate_only,
    "atl_frame_stamp": c_atl_frame_stamp,
    "atl_spec_inside": c_atl_spec_inside,
    "atl_two_views": c_atl_two_views,
    "atl_callouts": c_atl_callouts,
    "atl_caption_above": c_atl_caption_above,
    "atl_photo_plate": c_atl_photo_plate,
    "atl_text_and_plate": c_atl_text_and_plate,
    "atl_spread_plate": c_atl_spread_plate,
    "atl_rotated_plate": c_atl_rotated_plate,
    "atl_sparse": c_atl_sparse,
}
SPREADS = {"atl_spread_plate"}
ROTATE = {"atl_rotated_plate": 90}
