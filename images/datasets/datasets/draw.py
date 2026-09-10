"""The drawers: what puts ink on a synthetic page, and the truth it says"""

from datasets.errors import Refusal

W, H = (1012, 1466)
DPI = 144.0
PT = 72.0 / DPI
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"
FONT_MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
BOX_TITLE_RU = "ВРЕЗКА"
FIG_CAPTION_RU = "Рис. 3.  Схема испытания"
HEADS_RU = ("Марка", "σ, МПа", "δ, %", "НВ", "Примечание")
PROSE_EN = "The lead screw must be lowered to obtain a correct alignment with the half nuts. In addition, the lead screw must be aligned to the bed ways. To test this alignment the lead screw is inserted in the bearings and the carriage is placed at the mid-point on the bed ways, closing the half nuts on the lead screw. A simple indicating jig is then made up. "
PROSE_RU = "Испытание образцов проводилось при температуре восемьсот пятьдесят градусов в течение сорока минут с последующим охлаждением на воздухе. Полученные значения приведены в таблице, откуда видно, что предел прочности возрастает при увеличении содержания хрома. "


class SynthError(Refusal):
    pass


_SAID: dict[int, dict] = {}


def _said_reset() -> None:
    _SAID.clear()


def _said_take() -> dict[int, dict]:
    out = dict(_SAID)
    _SAID.clear()
    return out


def _say(truth, text=None, *, cells=None, spans=None, add=False):
    if not truth:
        raise SynthError("`_say` called before a truth box was added")
    i = len(truth) - 1
    rec = _SAID.get(i)
    if rec is not None and (not add):
        raise SynthError(
            f"character truth of block {i} ({truth[i][4]}) is being written a second time: was {rec!r}, now {text!r}. Either `_say` is one block behind `append`, or add=True is wanted"
        )
    if rec is None:
        rec = {}
        _SAID[i] = rec
    if text is not None:
        t = " ".join(str(text).split())
        rec["text"] = (rec["text"] + " " + t).strip() if add and "text" in rec else t
    if cells is not None:
        rec["rows"] = len(cells)
        rec["cols"] = max((len(r) for r in cells), default=0)
        rec["cells"] = [[" ".join(str(c).split()) for c in row] for row in cells]
    if spans is not None:
        rec["spans"] = spans
    return rec


def _fill(pg, rect, text, size, font="F"):
    import pymupdf

    body = text
    for _ in range(40):
        rc = pg.insert_textbox(
            rect,
            body,
            fontname=font,
            fontsize=size,
            lineheight=1.15,
            align=pymupdf.TEXT_ALIGN_JUSTIFY,
        )
        if rc < 0:
            body = body[: int(len(body) * 0.9)]
            if len(body) < 20:
                raise SynthError(f"not even 20 characters fit the box {rect}")
            continue
        if rc > size * 1.4 and len(body) < len(text) * 12:
            body = body + text
            continue
        return body
    raise SynthError(f"filling the box {rect} did not converge")


def _rect(x0, y0, x1, y1):
    import pymupdf

    return pymupdf.Rect(x0, y0, x1, y1)


def _table(pg, truth, x, y, cols, rows, size=6.4, label="table", ruled=False, colw=62.0, step=9.0):
    grid = [[c for c, _cx in cols]]
    for c, cx in cols:
        pg.insert_text((cx, y), c, fontname="F", fontsize=size)
    for r in range(rows):
        row = []
        for j, (_c, cx) in enumerate(cols):
            cell = f'0 to .00{(r + j) % 7 + 2}"'
            pg.insert_text((cx, y + 10 + r * step), cell, fontname="F", fontsize=size)
            row.append(cell)
        grid.append(row)
    x1 = cols[-1][1] + colw
    y1 = y + 10 + (rows - 1) * step + 4
    if ruled:
        for yy in (y - 8, y + 3, y1):
            pg.draw_line(
                _rect(x - 6, yy, x1, yy).tl, _rect(x - 6, yy, x1, yy).tr, color=(0, 0, 0), width=0.5
            )
        for _c, cx in cols[1:]:
            pg.draw_line(
                _rect(cx - 8, y - 8, cx - 8, y1).tl,
                _rect(cx - 8, y - 8, cx - 8, y1).bl,
                color=(0, 0, 0),
                width=0.4,
            )
    truth.append((x - 6, y - 8, x1, y1, label))
    _say(truth, cells=grid)
    return y1 + 6


def _grid(x, n, colw=62.0, gap=8.0):
    return [(f"Col {i + 1}", x + i * (colw + gap)) for i in range(n)]


def _chart(pg, truth, x, y, w, h, caption="Fig. 9  Hardness vs carbon"):
    import math

    pg.draw_line(_rect(x, y + h, x, y).bl, _rect(x, y + h, x, y).tl, color=(0, 0, 0), width=0.7)
    pg.draw_line(
        _rect(x, y + h, x + w, y + h).bl,
        _rect(x, y + h, x + w, y + h).br,
        color=(0, 0, 0),
        width=0.7,
    )
    import pymupdf

    pts = [
        pymupdf.Point(x + w * i / 24.0, y + h - h * (0.2 + 0.7 * math.sin(i / 7.0) ** 2))
        for i in range(25)
    ]
    for a, b in zip(pts, pts[1:], strict=False):
        pg.draw_line(a, b, color=(0, 0, 0), width=0.6)
    for i in range(6):
        pg.insert_text((x - 12, y + h - i * h / 5.0), str(i * 20), fontname="F", fontsize=5.2)
    truth.append((x - 14, y - 4, x + w + 4, y + h + 6, "chart"))
    _caption(pg, truth, x + 10, y + h + 18, caption)
    return y + h + 24


def _figure(pg, truth, x, y, w, h, caption="Fig. 26.67  General arrangement"):
    import pymupdf

    R = pymupdf.Rect(x, y, x + w, y + h)
    pg.draw_rect(R, color=(0, 0, 0), width=0.7)
    cx, cy = (x + w * 0.38, y + h * 0.5)
    r = min(w, h) * 0.22
    for k in (1.0, 0.62, 0.28):
        pg.draw_circle(pymupdf.Point(cx, cy), r * k, color=(0, 0, 0), width=0.6)
    pg.draw_line(
        pymupdf.Point(cx - r * 1.35, cy),
        pymupdf.Point(cx + r * 1.35, cy),
        color=(0, 0, 0),
        width=0.35,
        dashes="[2 2] 0",
    )
    pg.draw_line(
        pymupdf.Point(cx, cy - r * 1.35),
        pymupdf.Point(cx, cy + r * 1.35),
        color=(0, 0, 0),
        width=0.35,
        dashes="[2 2] 0",
    )
    bx = x + w * 0.62
    pts = [
        (bx, cy + r),
        (bx, cy - r * 0.8),
        (bx + w * 0.12, cy - r * 0.8),
        (bx + w * 0.12, cy - r * 1.25),
        (bx + w * 0.3, cy - r * 1.25),
        (bx + w * 0.3, cy + r),
    ]
    for a, b in zip(pts, pts[1:], strict=False):
        pg.draw_line(pymupdf.Point(*a), pymupdf.Point(*b), color=(0, 0, 0), width=0.6)
    for i in range(9):
        t0 = bx + i * (w * 0.3 / 9)
        pg.draw_line(
            pymupdf.Point(t0, cy + r), pymupdf.Point(t0 + r * 0.5, cy), color=(0, 0, 0), width=0.3
        )
    yd = y + h - 8
    pg.draw_line(pymupdf.Point(cx - r, yd), pymupdf.Point(cx + r, yd), color=(0, 0, 0), width=0.4)
    for sx, d in ((cx - r, 1), (cx + r, -1)):
        pg.draw_line(
            pymupdf.Point(sx, yd), pymupdf.Point(sx + 4 * d, yd - 2), color=(0, 0, 0), width=0.4
        )
        pg.draw_line(
            pymupdf.Point(sx, yd), pymupdf.Point(sx + 4 * d, yd + 2), color=(0, 0, 0), width=0.4
        )
    pg.insert_text((cx - 8, yd - 3), "A-A", fontname="F", fontsize=5.0)
    truth.append((x, y, x + w, y + h, "image"))
    _caption(pg, truth, x + 10, y + h + 12, caption)
    return y + h + 16


def _text_w(text: str, size: float, font: str = "F") -> float:
    import pymupdf

    f = pymupdf.Font(fontfile=FONT_MONO if font == "M" else FONT)
    return f.text_length(text, fontsize=size)


def _caption(pg, truth, x, y, text, size=6.2, label="figure_title"):
    pg.insert_text((x, y), text, fontname="F", fontsize=size)
    truth.append((x - 2, y - size - 1, x + _text_w(text, size) + 2, y + 2, label))
    _say(truth, text)
    return y + size + 2


def _halftone(pg, truth, x, y, w, h, caption="Fig. 31  Milling head, photograph"):
    import numpy as np
    import pymupdf

    n = 4
    gh, gw = (int(h * n), int(w * n))
    yy, xx = np.mgrid[0:gh, 0:gw] / float(max(gh, gw))
    g = 0.45 + 0.35 * np.sin(6.0 * xx) * np.cos(4.0 * yy)
    g += 0.25 * ((xx - 0.55) ** 2 + (yy - 0.45) ** 2 < 0.03)
    g += 0.06 * np.random.default_rng(3).normal(0, 1, g.shape)
    g = np.clip(g, 0.05, 0.95)
    m = (np.arange(16).reshape(4, 4) + 0.5) / 16.0
    thr = np.tile(m, (gh // 4 + 1, gw // 4 + 1))[:gh, :gw]
    dot = ((g > thr) * 255).astype(np.uint8)
    pix = pymupdf.Pixmap(pymupdf.csGRAY, gw, gh, dot.tobytes(), 0)
    pg.insert_image(_rect(x, y, x + w, y + h), pixmap=pix)
    pg.draw_rect(_rect(x, y, x + w, y + h), color=(0, 0, 0), width=0.5)
    truth.append((x, y, x + w, y + h, "image"))
    _caption(pg, truth, x + 8, y + h + 12, caption)
    return y + h + 16


def _stamp(pg, truth, x, y, r=34.0):
    R = _rect(x - r, y - r * 0.6, x + r, y + r * 0.6)
    pg.draw_oval(R, color=(0.25, 0.25, 0.25), width=1.1)
    pg.draw_oval(
        _rect(x - r * 0.8, y - r * 0.45, x + r * 0.8, y + r * 0.45),
        color=(0.25, 0.25, 0.25),
        width=0.6,
    )
    pg.insert_text(
        (x - r * 0.6, y + 2), "BIBLIOTEKA", fontname="F", fontsize=6.0, color=(0.25, 0.25, 0.25)
    )
    pg.insert_text(
        (x - r * 0.42, y + 11), "No. 4187", fontname="F", fontsize=5.0, color=(0.25, 0.25, 0.25)
    )
    truth.append((R.x0, R.y0, R.x1, R.y1, "seal"))
    _say(truth, "BIBLIOTEKA No. 4187")
    return R.y1


def _leader_table(pg, truth, x, y, rows, w=230.0, size=6.4, label="table"):
    grid = []
    for i in range(rows):
        yy = y + i * 9.4
        name = f"Bearing bronze {i + 3}"
        pg.insert_text((x, yy), name + " " + "." * 28, fontname="F", fontsize=size)
        pg.insert_text((x + w - 26, yy), f"{12 + i * 3}.{i % 9}", fontname="F", fontsize=size)
        grid.append([name, f"{12 + i * 3}.{i % 9}"])
    truth.append((x - 4, y - 8, x + w, y + (rows - 1) * 9.4 + 4, label))
    _say(truth, cells=grid)
    return y + (rows - 1) * 9.4 + 10


def _span_header_table(pg, truth, x, y, groups, rows, colw=54.0, size=6.2):
    cols = []
    cx = x
    top, second, spans = ([], [], [])
    for name, n in groups:
        span = n * colw
        pg.insert_text((cx + span / 2 - len(name) * 1.6, y), name, fontname="F", fontsize=size)
        pg.draw_line(
            _rect(cx, y + 3, cx + span - 8, y + 3).tl,
            _rect(cx, y + 3, cx + span - 8, y + 3).tr,
            color=(0, 0, 0),
            width=0.4,
        )
        spans.append({"row": 0, "col": len(cols), "cols": n})
        for j in range(n):
            cols.append(cx + j * colw)
            top.append(name if j == 0 else "")
            second.append(f"d{j + 1}")
            pg.insert_text((cx + j * colw, y + 13), f"d{j + 1}", fontname="F", fontsize=size)
        cx += span
    grid = [top, second]
    for r in range(rows):
        row = []
        for j, ccx in enumerate(cols):
            cell = f"{(r * 3 + j) % 90 + 10}.{j}"
            pg.insert_text((ccx, y + 25 + r * 9.0), cell, fontname="F", fontsize=size)
            row.append(cell)
        grid.append(row)
    y1 = y + 25 + (rows - 1) * 9.0 + 4
    truth.append((x - 5, y - 9, cols[-1] + colw - 8, y1, "table"))
    _say(truth, cells=grid, spans=spans)
    return y1 + 6


def _has_glyphs(text: str, font: str = "F") -> list[str]:
    import pymupdf

    f = pymupdf.Font(fontfile=FONT_MONO if font == "M" else FONT)
    return sorted({c for c in text if c.strip() and (not f.has_glyph(ord(c)))})


def _line(pg, x0, y0, x1, y1, width=0.9):
    import pymupdf

    if width < 0.5:
        raise SynthError(
            f"a rule {width} pt is under the floor of 0.5: neither `_measure` nor the model will see it"
        )
    pg.draw_line(pymupdf.Point(x0, y0), pymupdf.Point(x1, y1), color=(0, 0, 0), width=width)


def _put(pg, x, y, text, size=6.4, font="F", right=None, sheet_w=None):
    w = _text_w(text, size, font)
    if right is not None:
        x = right - w
    if sheet_w is not None and x + w > sheet_w + 0.5:
        raise SynthError(
            f"the line {text[:24]!r}, {w:.0f} pt wide, does not fit a {sheet_w:.0f} pt sheet from x={x:.0f}: `insert_text` will clip it silently"
        )
    pg.insert_text((x, y), text, fontname=font, fontsize=size)
    return w


ENTRY_EN = "{h}, n. The part of the mechanism that carries the load. Used in lathes and presses. See also {s}."
ENTRY_RU = "{h}, -а, м. Часть механизма, передающая усилие. Применяется в станках и прессах. См. также ст. {s}."


def _entries(
    pg,
    truth,
    x,
    y,
    y_end,
    w,
    sheet_w,
    words,
    size=5.8,
    hang=8.0,
    bold_head=False,
    label="text",
    lead=1.25,
    tpl=ENTRY_EN,
    start=0,
):
    step = size * lead
    n = start
    while y < y_end - step * 2:
        head = words[n % len(words)]
        body = tpl.format(h=head, s=words[(n + 3) % len(words)])
        lines, cur = ([], "")
        for word in body.split():
            trial = (cur + " " + word).strip()
            if _text_w(trial, size) > w - (hang if lines else 0):
                lines.append(cur)
                cur = word
            else:
                cur = trial
        lines.append(cur)
        if y + step * len(lines) > y_end:
            break
        y0 = y
        drawn = []
        for k, ln in enumerate(lines):
            xx = x + (hang if k else 0)
            if k == 0 and bold_head:
                sp = " ".join(head)
                wl = _put(pg, xx, y, sp, size, sheet_w=sheet_w)
                rest = ln[len(head) :].lstrip()
                _put(pg, xx + wl + 2, y, rest, size, sheet_w=sheet_w)
                drawn.append(sp + " " + rest)
            else:
                _put(pg, xx, y, ln, size, sheet_w=sheet_w)
                drawn.append(ln)
            y += step
        truth.append((x - 1, y0 - size, x + w, y - step + 2, label))
        _say(truth, " ".join(drawn))
        y += step * 0.55
        n += 1
    return y


def _running_head(pg, truth, x0, x1, y, left, right, page_no, size=5.6, rule=True):
    wl = _put(pg, x0, y, left, size, sheet_w=x1 + 40)
    truth.append((x0 - 2, y - size - 1, x0 + wl + 2, y + 2, "header"))
    _say(truth, left)
    wr = _put(pg, 0, y, right, size, right=x1, sheet_w=x1 + 40)
    truth.append((x1 - wr - 2, y - size - 1, x1 + 2, y + 2, "header"))
    _say(truth, right)
    if rule:
        _line(pg, x0, y + 4, x1, y + 4, 0.6)
    w = _put(pg, (x0 + x1) / 2 - 6, y + 16, str(page_no), size, sheet_w=x1 + 40)
    truth.append(
        ((x0 + x1) / 2 - 8, y + 16 - size - 1, (x0 + x1) / 2 - 6 + w + 2, y + 18, "number")
    )
    _say(truth, str(page_no))


def _formula(pg, truth, x, y, text, size=8.5, number=None, right=None, sheet_w=None):
    bad = _has_glyphs(text, "M")
    if bad:
        raise SynthError(
            f"the font lacks {bad}: they draw as empty boxes, and the bench would measure squares instead of a formula"
        )
    w = _put(pg, x, y, text, size, font="M", sheet_w=sheet_w)
    truth.append((x - 3, y - size - 1, x + w + 3, y + 3, "display_formula"))
    _say(truth, text)
    if number is not None and right is not None:
        nw = _put(pg, 0, y, number, size - 2, right=right, sheet_w=sheet_w)
        truth.append((right - nw - 2, y - size + 1, right + 2, y + 2, "formula_number"))
        _say(truth, number)
    return y + size * 1.9


def _matrix(pg, truth, x, y, rows, cols, size=6.6, kind="matrix", sheet_w=None):
    step, colw = (size * 1.55, size * 3.4)
    drawn = []
    for r in range(rows):
        row = []
        for c in range(cols):
            _put(
                pg,
                x + 10 + c * colw,
                y + r * step,
                f"a{r + 1}{c + 1}",
                size,
                font="M",
                sheet_w=sheet_w,
            )
            row.append(f"a{r + 1}{c + 1}")
        drawn.append(" ".join(row))
    x1 = x + 10 + (cols - 1) * colw + _text_w("a11", size, "M") + 8
    y1 = y + (rows - 1) * step + 3
    if kind == "matrix":
        for xx, d in ((x + 4, 1), (x1, -1)):
            _line(pg, xx, y - size, xx, y1, 0.7)
            _line(pg, xx, y - size, xx + 4 * d, y - size - 3, 0.6)
            _line(pg, xx, y1, xx + 4 * d, y1 + 3, 0.6)
    else:
        _line(pg, x + 4, y - size, x + 4, y1, 0.7)
        _line(pg, x1, y - size, x1, y1, 0.7)
    truth.append((x, y - size - 4, x1 + 5, y1 + 4, "display_formula"))
    _say(truth, " ; ".join(drawn))
    return y1 + size * 1.4


def _box_insert(pg, truth, x, y, w, h, prose, size=5.8, title=BOX_TITLE_RU):
    import pymupdf

    pg.draw_rect(pymupdf.Rect(x, y, x + w, y + h), color=(0, 0, 0), width=0.8)
    _put(pg, x + 8, y + 12, title, size + 1, sheet_w=x + w)
    body = _fill(pg, _rect(x + 8, y + 18, x + w - 8, y + h - 6), prose, size)
    truth.append((x, y, x + w, y + h, "text"))
    _say(truth, title + " " + body)
    return y + h + 8


def _refs(pg, truth, x, y, y_end, w, sheet_w, size=5.6, start=1):
    step = size * 1.3
    n = start
    y0 = y
    drawn = []
    while y < y_end - step:
        ln = f"[{n}] Ivanov A. B. Machine tool design, vol. {n}. Moscow, {1950 + n}, p. {40 + n * 7}."
        while _text_w(ln, size) > w:
            ln = ln[:-2]
        _put(pg, x, y, ln, size, sheet_w=sheet_w)
        drawn.append(ln)
        y += step
        n += 1
    truth.append((x - 2, y0 - size, x + w, y - step + 2, "reference_content"))
    _say(truth, " ".join(drawn))
    return y


def _frame_stamp(pg, truth, x0, y0, x1, y1, title="GENERAL ARRANGEMENT", no="26.67"):
    import pymupdf

    pg.draw_rect(pymupdf.Rect(x0, y0, x1, y1), color=(0, 0, 0), width=1.4)
    sw, sh = (168.0, 46.0)
    sx, sy = (x1 - 6 - sw, y1 - 6 - sh)
    pg.draw_rect(pymupdf.Rect(sx, sy, sx + sw, sy + sh), color=(0, 0, 0), width=0.9)
    for k in (1, 2):
        _line(pg, sx, sy + k * sh / 3, sx + sw, sy + k * sh / 3, 0.6)
    _line(pg, sx + sw * 0.62, sy, sx + sw * 0.62, sy + sh, 0.6)
    _put(pg, sx + 4, sy + 11, title[:22], 5.6, sheet_w=x1)
    _put(pg, sx + 4, sy + 11 + sh / 3, "Scale 1:2", 5.2, sheet_w=x1)
    _put(pg, sx + 4, sy + 11 + 2 * sh / 3, "Sheet 1 of 3", 5.2, sheet_w=x1)
    _put(pg, sx + sw * 0.62 + 4, sy + 11, f"No. {no}", 5.6, sheet_w=x1)
    _put(pg, sx + sw * 0.62 + 4, sy + 11 + sh / 3, "Drawn A.B.", 5.2, sheet_w=x1)
    _put(pg, sx + sw * 0.62 + 4, sy + 11 + 2 * sh / 3, "1953", 5.2, sheet_w=x1)
    truth.append((sx, sy, sx + sw, sy + sh, "table"))
    _say(
        truth,
        cells=[[title[:22], f"No. {no}"], ["Scale 1:2", "Drawn A.B."], ["Sheet 1 of 3", "1953"]],
    )
    return (sx, sy)


def _callouts(pg, truth, cx, cy, r, items, sheet_w):
    import math
    import pymupdf

    for _k, (ang, n) in enumerate(items):
        a = math.radians(ang)
        x0, y0 = (cx + r * math.cos(a), cy + r * math.sin(a))
        x1, y1 = (cx + (r + 46) * math.cos(a), cy + (r + 46) * math.sin(a))
        pg.draw_line(pymupdf.Point(x0, y0), pymupdf.Point(x1, y1), color=(0, 0, 0), width=0.5)
        pg.draw_circle(pymupdf.Point(x1, y1), 6.0, color=(0, 0, 0), width=0.6)
        _put(pg, x1 - 2.5, y1 + 2.5, str(n), 5.4, sheet_w=sheet_w)


def _plate(pg, truth, x, y, w, h, views=1):
    import math
    import pymupdf

    for v in range(views):
        vx = x + v * (w / views)
        vw = w / views - (10 if views > 1 else 0)
        cx, cy = (vx + vw * 0.5, y + h * 0.5)
        r = min(vw, h) * 0.3
        pg.draw_rect(pymupdf.Rect(vx, y, vx + vw, y + h), color=(0, 0, 0), width=0.8)
        for k in (1.0, 0.7, 0.42, 0.18):
            pg.draw_circle(pymupdf.Point(cx, cy), r * k, color=(0, 0, 0), width=0.6)
        pg.draw_line(
            pymupdf.Point(cx - r * 1.3, cy),
            pymupdf.Point(cx + r * 1.3, cy),
            color=(0, 0, 0),
            width=0.35,
            dashes="[3 3] 0",
        )
        pg.draw_line(
            pymupdf.Point(cx, cy - r * 1.3),
            pymupdf.Point(cx, cy + r * 1.3),
            color=(0, 0, 0),
            width=0.35,
            dashes="[3 3] 0",
        )
        for i in range(8):
            a = math.radians(i * 45)
            pg.draw_line(
                pymupdf.Point(cx + r * 0.42 * math.cos(a), cy + r * 0.42 * math.sin(a)),
                pymupdf.Point(cx + r * 0.7 * math.cos(a), cy + r * 0.7 * math.sin(a)),
                color=(0, 0, 0),
                width=0.5,
            )
        truth.append((vx, y, vx + vw, y + h, "image"))
    return y + h


PW, PH = (W * PT, H * PT)
MARGIN, COLW, GUT = (34.0, 210.0, 18.0)
TOP, BOT = (40.0, 700.0)
COL_X = (MARGIN, MARGIN + COLW + GUT)


def _page(doc, wide=False, pw=None, ph=None):
    pw = PW if pw is None else pw
    ph = PH if ph is None else ph
    pg = doc.new_page(width=2 * pw if wide else pw, height=ph)
    pg.insert_font(fontname="F", fontfile=FONT)
    pg.insert_font(fontname="M", fontfile=FONT_MONO)
    return pg


def _flow(pg, t, x, y, y_end, prose, w=COLW, size=6.6, gap=8.0):
    n = 0
    while y < y_end - 24:
        h = min(y_end - y, 34 + n * 17 % 62)
        body = _fill(pg, _rect(x, y, x + w, y + h), prose, size)
        t.append((x, y, x + w, y + h, "text"))
        _say(t, body)
        y += h + gap
        n += 1
    return y
