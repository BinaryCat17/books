"""OTSL: parsing the table markup the reading models answer in"""

import html as _html
import re

CONTENT = ("fcel", "ched", "rhed", "srow")
EMPTY = ("ecel",)
SPAN = ("lcel", "ucel", "xcel")
BREAK = ("nl",)
HEADER = ("ched", "rhed")
TAGS = CONTENT + EMPTY + SPAN + BREAK
_TOK = re.compile("<(" + "|".join(TAGS) + ")>")


def looks_like(s: object) -> bool:
    if not isinstance(s, str):
        return False
    toks = _TOK.findall(s)
    return "nl" in toks or len(toks) >= 2


def grid(s: str) -> dict | None:
    return parse(s)[0] if looks_like(s) else None


def parse(s: str) -> tuple[dict | None, dict]:
    cells, _, tally = _walk(s)
    return (cells, tally)


def _walk(s: str) -> tuple[dict | None, dict, dict]:
    tally = {
        "grid_cells": 0,
        "rows": 0,
        "with_content": 0,
        "empty": 0,
        "continuations": 0,
        "continuations_to_nowhere": 0,
        "rows_of_unequal_length": 0,
        "text_before_first_tag": 0,
        "text_after_last_tag": 0,
        "chars": 0,
    }
    if not looks_like(s):
        return (None, {}, tally)
    toks = list(_TOK.finditer(s))
    head = s[: toks[0].start()].strip()
    if head:
        tally["text_before_first_tag"] = len(head)
    tail = s[toks[-1].end() :] if toks[-1].group(1) in BREAK else ""
    if tail.strip():
        tally["text_after_last_tag"] = len(tail.strip())
    cells: dict[tuple[int, int], str] = {}
    r, c = (0, 0)
    owner: dict[tuple[int, int], tuple[int, int]] = {}
    tag_of: dict[tuple[int, int], str] = {}
    widths: list[int] = []
    for i, m in enumerate(toks):
        name = m.group(1)
        if name in BREAK:
            widths.append(c)
            r, c = (r + 1, 0)
            continue
        end = toks[i + 1].start() if i + 1 < len(toks) else len(s)
        txt = s[m.end() : end]
        if name in CONTENT:
            cells[r, c] = txt
            owner[r, c] = (r, c)
            tag_of[r, c] = name
            tally["with_content"] += 1
            tally["chars"] += len(txt)
        elif name in EMPTY:
            cells[r, c] = ""
            owner[r, c] = (r, c)
            tag_of[r, c] = name
            tally["empty"] += 1
        else:
            tally["continuations"] += 1
            left, up = ((r, c - 1), (r - 1, c))
            if name == "lcel":
                src = left
            elif name == "ucel":
                src = up
            else:
                src = left if left in cells else up
            if src in cells:
                cells[r, c] = cells[src]
                owner[r, c] = owner.get(src, src)
            else:
                cells[r, c] = ""
                owner[r, c] = (r, c)
                tag_of[r, c] = name
                tally["continuations_to_nowhere"] += 1
        c += 1
    if c:
        widths.append(c)
    tally["grid_cells"] = len(cells)
    tally["rows"] = len(widths)
    if widths:
        tally["rows_of_unequal_length"] = sum((1 for w in widths if w != max(widths)))
    return (cells or None, {"owner": owner, "tag": tag_of}, tally)


def layout(s: str) -> tuple[list, dict]:
    cells, own, tally = _walk(s)
    tally = dict(tally, **{"merges": 0, "non_rectangular_merges": 0})
    if not cells:
        return ([], tally)
    owner, tag_of = (own["owner"], own["tag"])
    ours: dict[tuple[int, int], list] = {}
    for addr, root in owner.items():
        ours.setdefault(root, []).append(addr)
    out = []
    for root in sorted(ours):
        addresses = ours[root]
        r0, c0 = root
        rs = {r for r, _ in addresses}
        cs = {c for _, c in addresses}
        h, w = (max(rs) - min(rs) + 1, max(cs) - min(cs) + 1)
        rect = len(addresses) == h * w
        if h * w > 1:
            tally["merges"] += 1
            if not rect:
                tally["non_rectangular_merges"] += 1
        if h * w > 1 and rect:
            out.append(
                {
                    "row": r0,
                    "col": c0,
                    "rows": h,
                    "cols": w,
                    "text": cells.get(root, ""),
                    "tag": tag_of.get(root, "fcel"),
                }
            )
        else:
            root_one = tag_of[root]
            for a in sorted(addresses):
                out.append(
                    {
                        "row": a[0],
                        "col": a[1],
                        "rows": 1,
                        "cols": 1,
                        "text": cells.get(a, ""),
                        "tag": tag_of.get(a, root_one),
                    }
                )
    out.sort(key=lambda d: (d["row"], d["col"]))
    return (out, tally)


def to_html(s: str) -> str:
    cs, t = layout(s)
    if not cs:
        return ""
    by_rows: dict[int, list] = {}
    for c in cs:
        by_rows.setdefault(c["row"], []).append(c)
    rows = t["rows"]
    out = ["<table>"]
    for r in range(rows):
        out.append("<tr>")
        for cell in by_rows.get(r, ()):
            tag = "th" if cell["tag"] in HEADER else "td"
            span = ""
            if cell["cols"] > 1:
                span += f''' colspan="{cell["cols"]}"'''
            if cell["rows"] > 1:
                span += f''' rowspan="{cell["rows"]}"'''
            out.append(f"<{tag}{span}>" + _html.escape(cell["text"]) + f"</{tag}>")
        out.append("</tr>")
    out.append("</table>")
    return "".join(out)
