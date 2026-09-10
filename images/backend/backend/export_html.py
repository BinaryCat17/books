"""Level one's product: readable HTML from the contours"""

import glob
import html as _html
import json
import os
import shlex
import shutil
import time
from backend import classes as policy
from backend import identity as stamp
from backend import textnorm
from backend.errors import Refusal
from backend import knobs
from backend import raster as crop
from backend.store import ASSETS
from backend import job
from backend.log import log

from backend.document import (
    _twice_area,
    BookData,
    _ours,
    gather,
)



OPEN = "<!--bs:{}-->"
CLOSE = "<!--/bs:{}-->"


def _wrap(anchor: str, body: str) -> str:
    return OPEN.format(anchor) + body + CLOSE.format(anchor)


def _anchors(html: str) -> list[str]:
    out, i = [], 0
    head = OPEN.split("{}")[0]
    while True:
        i = html.find(head, i)
        if i < 0:
            return out
        j = html.find("-->", i)
        if j < 0:
            raise Refusal(f"mark not closed: {html[i:i + 40]!r}")
        out.append(html[i + len(head):j])
        i = j + 3

CSS = '\nbody{max-width:52em;margin:2em auto;padding:0 1em;\n     font:16px/1.55 Georgia,\'DejaVu Serif\',serif}\nfigure{margin:1.2em 0;padding:0}\nfigure img{max-width:100%;height:auto;display:block;\n           border:1px solid #ddd}\nfigcaption{font:12px/1.4 monospace;color:#777;margin-top:.3em}\np{margin:.7em 0}\n[data-role="furniture"]{opacity:.55}\n[data-text="unread"] figcaption{color:#a60}\n/* A TEXT BLOCK THAT LEFT AS A PICTURE DOES NOT EAT THE SCREEN. Seven per\n   book, and all seven are strips of binding shadow: the model\'s box landed on\n   a scan defect and the model answered that noise with nothing. A 12x408 px\n   crop drawn full size eats a whole column of type -- the reader meets a\n   black thread instead of text. The box is NOT removed (a first-level defect,\n   and it is measured), the number is not hidden (it is in the log and the\n   snapshot); only the display shrinks, and the caption says WHY it is\n   empty. */\n[data-text="unread"] img{max-height:8em;width:auto;object-fit:contain}\nfigure[data-inside]{margin-left:2em;border-left:3px solid #e0c000;padding-left:.8em}\nfigure[data-inside] figcaption{color:#a60}\nhr.sheet[data-no-text]{border-top:2px solid #c00}\nhr.sheet[data-empty]{border-top:2px dotted #c00}\nhr.sheet[data-empty]::after{content:"the model found nothing on this sheet";\n    display:block;font:11px monospace;color:#c00;margin-top:.3em}\nhr.sheet[data-no-text]:not([data-empty])::after{\n    content:"the whole column went into pictures";\n    display:block;font:11px monospace;color:#c00;margin-top:.3em}\nhr.sheet[data-furniture-only]{border-top:2px dashed #c00}\nhr.sheet[data-furniture-only]::after{\n    content:"only furniture on this sheet: no text, no artifacts";\n    display:block;font:11px monospace;color:#c00;margin-top:.3em}\nhr.sheet{border:0;border-top:1px dashed #ccc;margin:2.5em 0}\n\n/* CEILING TRUNCATION -- VISIBLE TO THE EYE, NOT ONLY IN THE LOG. A truncated\n   answer looked no different from a whole one: 118 471 characters (12.95 % of\n   the book\'s text) stood as ordinary <p> and <table>. The mark goes on the\n   block\'s FRAME, not into the text -- `content` stays the model\'s bytes. */\n[data-truncated]{border-left:3px solid #c00;padding-left:.8em;margin-left:-1em}\n[data-truncated]::before{content:"the model\'s answer was cut off by the "\n    "length ceiling -- past this point the text breaks mid-word";\n    display:block;font:11px monospace;color:#c00;margin:.3em 0}\n[data-table-shape]::after{content:"impossible table shape: "\n    attr(data-table-shape);\n    display:block;font:11px monospace;color:#c00;margin-top:.3em}\n\n/* TABLES. There was NOT ONE rule here: 16 selectors in the whole book and\n   zero table ones, so 104 tables were drawn by the browser default --\n   `border-collapse:separate`, no borders, no padding, columns spread. That is\n   what "tables render horribly" meant: the markup was right, there was\n   nothing to show it with. */\ntable{border-collapse:collapse;margin:.2em 0 1.2em;font-size:.92em;\n      line-height:1.35}\nth,td{border:1px solid #bbb;padding:.28em .5em;vertical-align:top;\n      text-align:left}\nth{background:#f2f0ec;font-weight:600}\n/* Digits of one width: a column of numbers aligns itself, with no guess\n   about which column is numeric. Guessing would be dishonest -- in these\n   tables "1 615" stands next to "Other". */\ntd,th{font-variant-numeric:tabular-nums}\ntr:nth-child(even) td{background:#fbfaf9}\n/* A WIDE TABLE SCROLLS INSIDE ITSELF instead of breaking the column of type.\n   The book is 52em wide and the "Output growth" table has seven columns;\n   without this rule the whole page would get horizontal scrolling. */\ndiv[data-level="2"]{overflow-x:auto}\n/* A table caption arrives as a SEPARATE model block (label `figure_title`)\n   and stays a separate <p>: folding it into <caption> would move blocks and\n   break the book\'s order, which a guard of its own checks. So they are made\n   kin by look, not by markup. */\np[data-label="figure_title"]{font-size:.9em;color:#555;margin:1.2em 0 .2em}\n\n/* THE OWNER\'S REPEAT. The detector draws its OWN box around inline maths\n   over the paragraph, the second level reads it apart -- and the same place\n   arrives in the book twice: once inside the paragraph, once as its own <p>.\n   On "Refractory technology" there are 1935 such blocks, and only 414 have\n   their text found among the blocks that REMAIN in the book. Here stood "1916\n   of 1935, found VERBATIM at the owner" -- both words wrong: 1916 came of\n   comparing a block with itself, and at the OWNER the text is found for only\n   476, because the box enclosing a formula and the paragraph carrying its\n   text are different blocks.\n\n   THREE CASES KEPT APART, AND THAT IS THE POINT. Where the repeat is PROVED\n   by comparison the reader is not shown it: the same words are already\n   printed by a block that stays. Where the text DIVERGED we show it, having\n   nothing to prove a repeat with: two readings of one place differ in\n   transcription, but may also carry different things. Where the repeat is\n   proved but the carrier holds the same as RAW latex we show it too: hiding\n   the typeset for the raw makes the page worse.\n\n   WHERE THE HIDDEN STAYS: in `book.html` itself (the markup is in place, only\n   the display is off) and in `assets/source/pages/*.json`. Here stood "and in\n   blocks.json" -- wrong: `content` is not among its fields at all. */\n[data-repeat-text="verbatim"]{display:none}\n/* A proved repeat KEPT for the sake of layout: the carrier holds the same as\n   raw latex, and hiding the typeset would show the reader `FeO-SiO_{2}`\n   instead of a formula. */\n[data-repeat-text="layout"]{opacity:.85}\n/* The reader is told the sheet is shortened, and told it on the sheet. */\nhr.sheet[data-repeats-hidden]::after{\n    content:"repeats hidden on this sheet: " attr(data-repeats-hidden)\n            " (the same text is printed nearby; HTML_REPEATS=show shows all)";\n    display:block;font:11px monospace;color:#999;margin-top:.3em}\n[data-repeat-text="differs"]{opacity:.7;border-left:2px solid #ccc;\n    padding-left:.6em}\n[data-repeat-text="differs"]::after{content:"repeat of block "\n    attr(data-repeat) ", the text diverged";\n    display:block;font:11px monospace;color:#888;margin-top:.2em}\n'


def _figure(anchor, b, role, src, info, inside=None, mark="", why=None):
    cap = f"{b.label} {b.score:.2f}" if b.score is not None else b.label
    if inside:
        cap = f"detail of {inside} · " + cap
    if info.get("clipped_by_sheet"):
        cap += " · the box left the sheet"
    unread = "" if role == "artifact" else ' data-text="unread"'
    if role != "artifact" and why:
        cap += " · " + why
    within = f' data-inside="{inside}"' if inside else ""
    return f'''<figure id="{anchor}" data-role="{role}" data-label="{b.label}"{unread}{within}{mark}><img src="{src}" alt="{_html.escape(b.label)}" width="{info["width"]}" height="{info["height"]}"><figcaption>{_html.escape(cap)}</figcaption></figure>'''


def is_our_dir(out_dir: str) -> bool:
    return os.path.exists(os.path.join(out_dir, ASSETS, "run.json"))



def _img_how() -> str:
    from backend import knobs

    how = (knobs.knob("HTML_IMAGES") or "inline").strip()
    if how not in ("inline", "linked"):
        raise Refusal(
            f"HTML_IMAGES={how!r}: I know only inline | linked. There is no silent default here: a book without pictures looks assembled, and half its meaning is figures and tables."
        )
    return how


def _img_src(path: str, rel: str, how: str) -> str:
    if how == "linked":
        return _html.escape(rel)
    import base64

    with open(path, "rb") as f:
        return "data:image/png;base64," + base64.b64encode(f.read()).decode()


MATHJAX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mathjax", "tex-svg.js")


_SKIP = ("script", "noscript", "style", "textarea", "code", "annotation", "annotation-xml")


_MATH_CFG = (
    'window.MathJax={tex:{inlineMath:[["$","$"],["\\\\(","\\\\)"]],displayMath:[["\\\\[","\\\\]"],["$$","$$"]]},options:{enableMenu:false,skipHtmlTags:'
    + json.dumps(list(_SKIP))
    + "}};"
)


def _math(out_dir: str) -> tuple[str, str]:
    from backend import knobs

    how = (knobs.knob("HTML_MATH") or "").strip()
    if how not in ("inline", "local", "cdn", "off"):
        raise Refusal(
            f"HTML_MATH={how!r}: I know only inline | local | cdn | off. There is no silent default here: a book with unrendered formulas looks sound and cannot be read."
        )
    if how == "off":
        return ("", "formulas NOT rendered (HTML_MATH=off) -- raw LaTeX")
    cfg = f"<script>{_MATH_CFG}</script>"
    if how == "cdn":
        return (
            cfg
            + '<script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3.2.2/es5/tex-svg.js"></script>',
            "formulas drawn by MathJax FROM THE NETWORK -- without it the book will not open",
        )
    if not os.path.exists(MATHJAX):
        raise Refusal(
            f"no {MATHJAX}: HTML_MATH={how}, and there is no renderer beside the code. Either put it there, or HTML_MATH=cdn (needs the network on opening), or HTML_MATH=off (raw LaTeX)."
        )
    if how == "local":
        os.makedirs(os.path.join(out_dir, ASSETS), exist_ok=True)
        shutil.copy2(MATHJAX, os.path.join(out_dir, ASSETS, "tex-svg.js"))
        return (
            cfg + f'<script id="MathJax-script" async src="{ASSETS}/tex-svg.js"></script>',
            f"formulas drawn by MathJax from {ASSETS}/tex-svg.js ({os.path.getsize(MATHJAX) / 1000000.0:.1f} MB). WARNING: over a network path (\\\\wsl.localhost\\...) the browser will silently not load this file, and there will be no formulas",
        )
    with open(MATHJAX, encoding="utf-8") as f:
        code = f.read().replace("</script>", "<\\/script>")
    return (
        cfg + f'<script id="MathJax-script">{code}</script>',
        f"formulas drawn by MathJax INSIDE the book (+{os.path.getsize(MATHJAX) / 1000000.0:.1f} MB) -- neither network nor neighbouring files needed",
    )


def emit(data: BookData, out_dir: str) -> dict:
    out_dir = os.path.abspath(out_dir)
    detect_dir = data.run_dir
    pdf, page_dpi, pol = (data.pdf, data.page_dpi, data.policy)
    now = data.sha256 if data.sha256 is not None else stamp.sha256(pdf)
    said = data.sha256_said
    if said and now != said:
        raise Refusal(
            f"{pdf} changed after detection: the snapshot swore sha256 {said[:12]}, now it is {now[:12]}. The crops would come from one file and the boxes from another."
        )
    obs = data.observed
    repeats_how = data.repeats_how
    doc = crop.open_pdf(pdf)
    img_how = _img_how()
    blockdir = os.path.join(out_dir, ASSETS, "blocks")
    os.makedirs(blockdir, exist_ok=True)
    for old in glob.glob(os.path.join(blockdir, "*.png")):
        os.unlink(old)
    expected = []
    body, side = ([], {})
    counts = {r: 0 for r in policy.ROLES}
    cut_n = clipped = 0
    dup_text = nested = no_text = no_blocks = only_service = 0
    torn_n = shape_n = 0
    torn_a, shape_a = ([], [])
    dup_in_text = dup_in_text_strict = 0
    repeat_count = differs = by_layout = 0
    order_src_n = {}
    ink2 = sheet_pt_all = 0.0
    worst2 = (0.0, None)
    biggest = (0.0, None)
    try:
        for page_n, pg in enumerate(data.pages, 1):
            job.current().check()
            if page_n % 10 == 0 or page_n == len(data.pages):
                log(f"  {page_n}/{len(data.pages)} pages built", n=page_n, of=len(data.pages))
            order_src_n[pg.order_source] = order_src_n.get(pg.order_source, 0) + 1
            no_text += pg.trouble == "no-text"
            no_blocks += pg.trouble == "empty"
            only_service += pg.trouble == "furniture-only"
            if pg.largest_artifact_share > biggest[0]:
                biggest = (pg.largest_artifact_share, pg.index)
            nested += pg.nested_artifacts
            body.append(
                f'<hr class="sheet" data-sheet="{pg.index}" data-image-share="{pg.image_share:.2f}"'
                + (
                    f' data-repeats-hidden="{pg.repeats_verbatim}"'
                    if pg.repeats_verbatim and repeats_how == "hide"
                    else ""
                )
                + (f' data-{pg.trouble}="yes"' if pg.trouble else "")
                + ">"
            )
            cuts = []
            expected.extend(b.anchor for b in pg.blocks)
            for b in pg.blocks:
                a = b.anchor
                if b.role != "artifact" and b.inside_artifacts:
                    dup_text += 1
                dup_in_text += b.nested_in_text
                dup_in_text_strict += b.nested_in_text_strict
                repeat_count += b.repeat_verdict == "verbatim"
                differs += b.repeat_verdict == "differs"
                by_layout += b.repeat_verdict == "layout"
                counts[b.role] += 1
                mark = ' data-truncated="yes"' if b.hit_ceiling else ""
                if b.repeat_of:
                    kind = (
                        b.repeat_verdict
                        if repeats_how == "hide"
                        else "shown by HTML_REPEATS=show"
                        if b.repeat_verdict == "verbatim"
                        else b.repeat_verdict
                    )
                    mark += f' data-repeat="{b.repeat_of}" data-repeat-text="{kind}"'
                if b.table_shape:
                    mark += f' data-table-shape="{_html.escape(b.table_shape, quote=True)}"'
                if b.hit_ceiling:
                    torn_n += 1
                    torn_a.append(a)
                if b.table_shape:
                    shape_n += 1
                    shape_a.append(a)
                if b.as_picture:
                    rel = f"{ASSETS}/blocks/{a}.png"
                    info = crop.cut(doc, pg.index, b.box, page_dpi, os.path.join(out_dir, rel))
                    src = _img_src(os.path.join(out_dir, rel), rel, img_how)
                    cut_n += 1
                    clipped += bool(info["clipped_by_sheet"])
                    cuts.append([float(v) for v in info["box_in_points"]])
                    body.append(
                        _wrap(
                            a,
                            _figure(
                                a, b, b.role, src, info, inside=b.inside, mark=mark, why=b.why_empty
                            ),
                        )
                    )
                else:
                    info = {}
                    body.append(
                        _wrap(
                            a,
                            f'<p id="{a}" data-role="{b.role}" data-label="{b.label}"{mark}>{_html.escape(b.content)}</p>',
                        )
                    )
                side[a] = {
                    "page": b.page,
                    "block_id": b.block_id,
                    "reading": b.reading,
                    "hit_ceiling": b.hit_ceiling,
                    "repeat_of": b.repeat_of,
                    "repeat_verdict": b.repeat_verdict,
                    "table_shape": b.table_shape,
                    "label": b.label,
                    "score": b.score,
                    "order": b.order,
                    "order_source": b.order_source,
                    "role": b.role,
                    "box": list(b.box),
                    "crop": info or None,
                    "inside_artifacts": b.inside_artifacts,
                    "inside": b.inside,
                    "contains": b.contains,
                }
            r = doc[pg.index].rect
            sheet_pt = float(r.width) * float(r.height)
            twice = min(_twice_area(cuts), sheet_pt)
            ink2 += twice
            sheet_pt_all += sheet_pt
            if sheet_pt > 0 and twice / sheet_pt > worst2[0]:
                worst2 = (twice / sheet_pt, pg.index)
    finally:
        doc.close()
    try:
        after = stamp.sha256(pdf)
    except OSError as e:
        raise Refusal(
            f"{pdf} vanished during the build: {type(e).__name__}: {e}. The book is not written."
        ) from None
    if after != now:
        raise Refusal(
            f"{pdf} was swapped DURING the build: at the start sha256 {now[:12]}, now {after[:12]}. Some crops are cut from one file and some from another, and which is unknown. The book is not written; repeat books html whole."
        )
    os.makedirs(out_dir, exist_ok=True)
    math_head, math_note = _math(out_dir)
    page_html = (
        f'<!doctype html>\n<html lang="ru"><head><meta charset="utf-8"><title>{_html.escape(os.path.basename(pdf))}</title><style>{CSS}</style>{math_head}</head>\n<body>\n'
        + "\n".join(body)
        + "\n</body></html>\n"
    )
    got = _anchors(page_html)
    if got != expected:
        where = next(
            (i for i, (a, b) in enumerate(zip(got, expected, strict=False)) if a != b),
            min(len(got), len(expected)),
        )
        raise Refusal(
            f"the book is assembled NOT in the order it was walked: {len(expected)} anchors expected, {len(got)} came out; first divergence at place {where} -- expected {(expected[where] if where < len(expected) else '(end)')}, got {(got[where] if where < len(got) else '(end)')}. The book's order IS the reading order; muddled, the document stays sound to the eye and unreadable in substance."
        )
    out_html = os.path.join(out_dir, "book.html")
    with open(out_html, "w", encoding="utf-8") as f:
        f.write(page_html)
    with open(os.path.join(out_dir, ASSETS, "blocks.json"), "w", encoding="utf-8") as f:
        json.dump(side, f, ensure_ascii=False, indent=1)
    files = len(data.pages)
    snap = data.snapshot
    snap_out = {
        "when": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "knobs": knobs.snapshot(),
        "raster": dict(snap["raster"]),
        "args": {"detect": detect_dir, "out": out_dir},
        "commit": stamp.commit(),
        "source": {
            **snap["source"],
            "sha256": now,
            "sha256_per_detect_snapshot": said,
            "sha256_after_build": after,
        },
        "adapter": {
            "name": "doc.html",
            "module": __name__,
            "sha256": stamp.sha256(os.path.abspath(__file__)),
            "sha256_crop_code": stamp.sha256(crop.__file__),
            "sha256_detect_snapshot": stamp.sha256(os.path.join(detect_dir, "run.json")),
        },
        "policy": pol.snapshot(),
        "crop": crop.params(page_dpi),
        "prompts": {},
        "generation": {"temperature": None, "max_tokens": None, "top_p": None, "seed": None},
        "packages": stamp.packages(),
        "weights": {"vl": None, "layout": snap["weights"]["layout"]},
        "summary": {
            "page_count": files,
            "by_bucket": counts,
            "crop_count": cut_n,
            "clipped_by_sheet": clipped,
            "double_ink_sheet_share": round(ink2 / sheet_pt_all, 4) if sheet_pt_all > 0 else None,
            "worst_sheet_double_ink": {"page_no": worst2[1], "share": round(worst2[0], 4)}
            if worst2[1] is not None
            else None,
            "text_inside_artifact_boxes": dup_text,
            "text_inside_non_artifact_box": dup_in_text,
            "repeats_proven": repeat_count,
            "repeats_mode": repeats_how,
            "nested_but_text_differs": differs,
            "repeats_kept_for_layout": by_layout,
            "comparison_normalization": textnorm.norm_note("latex"),
            "text_inside_text_box_strict": dup_in_text_strict,
            "reading_observed": bool(obs) or None,
            "hit_ceiling": torn_n if obs else None,
            "truncated_anchors": torn_a[:20] + ([f"…and {torn_n - 20} more"] if torn_n > 20 else [])
            if obs
            else None,
            "impossible_table_shape": shape_n if obs else None,
            "impossible_table_anchors": shape_a[:20]
            + ([f"…and {shape_n - 20} more"] if shape_n > 20 else [])
            if obs
            else None,
            "nested_artifacts": nested,
            "block_order": {
                "by_page_meta": dict(sorted(order_src_n.items())),
                "pages_with_our_order": sum((n for v, n in order_src_n.items() if _ours(v))),
            },
            "anchor_count": len(_anchors(page_html)),
        },
        "repeat_command": " ".join(
            shlex.quote(a) for a in ["books", "html", detect_dir, "--out", out_dir]
        ),
    }
    with open(os.path.join(out_dir, ASSETS, "run.json"), "w", encoding="utf-8") as f:
        json.dump(snap_out, f, ensure_ascii=False, indent=1)
    man = os.path.join(out_dir, "manifest.json")
    if not os.path.isfile(man):
        with open(man, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "book": os.path.basename(out_dir.rstrip("/")),
                    "source": {"name": os.path.basename(pdf), "sha256": now},
                },
                f,
                ensure_ascii=False,
                indent=1,
            )
    log(
        f"pages {files}, blocks {sum(counts.values())} (text {counts['text']}, artifacts {counts['artifact']}, furniture {counts['furniture']})"
    )
    _cp = crop.params(page_dpi)
    log(
        f"crops {cut_n} at {_cp['dpi']:.0f} dpi ({_cp['dpi_source']}), margin {_cp['margin']}, clipped by the sheet {clipped}"
    )
    if sheet_pt_all > 0:
        log(
            f"ink twice {ink2 / sheet_pt_all * 100:.2f}% of sheet area"
            + (
                f", worst sheet p. {worst2[1]}: {worst2[0] * 100:.0f}%"
                if worst2[1] is not None
                else " -- on no sheet did the crops intersect"
            )
        )
    else:
        log("ink twice: no data -- the sheet area is zero")
    log(
        f"text blocks inside an artifact box {dup_text} (they ARE in the HTML, but their ink also went into the artifact's picture), nested artifacts {nested} (subordinated to the outer one and marked data-inside; not one thrown away)"
    )
    log(
        f'text blocks inside a NON-ARTIFACT box {dup_in_text} -- the same words went into the book twice, as two <p>; no crops are cut for them, and the double-ink counter is blind to them by construction. The denominator is in the name: any box but an artifact one; of those blocks with bucket "text" on BOTH sides, {dup_in_text_strict}'
        + (
            " -- the numbers agree, no furniture boxes among the enclosing"
            if dup_in_text == dup_in_text_strict
            else f", the difference of {dup_in_text - dup_in_text_strict} falls on furniture boxes"
        )
    )
    if repeat_count + differs + by_layout == 0:
        log(
            f'repeats: NOTHING TO COMPARE WITH -- {dup_in_text} nested boxes and content in none of them. This is not "no repeats found"'
        )
    else:
        log(
            f"of them a REPEAT: proved by comparison {repeat_count} "
            + (
                "(HIDDEN in the book, markup and source in place)"
                if repeats_how == "hide"
                else "(ALL SHOWN: HTML_REPEATS=show)"
            )
            + f', the text diverged at {differs} (SHOWN and marked -- there is nothing to prove a repeat with), at {by_layout} proved but KEPT: the carrier holds the same as raw latex, and hiding the typeset would make the page worse. Compared NOT with the owner but with the blocks that REMAIN; the "latex" step -- see core/textnorm.NORM_STEPS'
        )
    if obs:
        n_obs = sum(1 for pg in data.pages for b in pg.blocks if b.reading)
        log(
            f"reading observations: {n_obs} answers alongside; cut off by the ceiling {torn_n}, impossible table shape {shape_n}"
            + (
                f"; truncated: {', '.join(torn_a[:5])}{('…' if torn_n > 5 else '')}"
                if torn_n
                else ""
            )
            + (
                f"; impossible: {', '.join(shape_a[:5])}{('…' if shape_n > 5 else '')}"
                if shape_n
                else ""
            )
        )
        if torn_n or shape_n:
            log(
                "  THESE BLOCKS ARE IN THE BOOK and marked data-truncated / data-table-shape. The model's text is not edited by a byte: the truncation is its defect, ours is to name it aloud"
            )
    else:
        log(
            'reading observations: NO answers/ alongside -- whether these blocks were read and how it ended, there is nothing to say. This is not "no troubles found"'
        )
    log(f"pages where the model found NOTHING: {no_blocks}")
    log(
        f'pages with nothing but furniture: {only_service} (no text, no artifacts -- there was nothing to cut into pictures, and this is NOT "the whole column went into pictures")'
    )
    log(
        f"pages without a single text block {no_text} (the whole column went into pictures), largest share of a sheet in one box {biggest[0] * 100:.0f}%"
        + (f" on p. {biggest[1]}" if biggest[1] is not None else "")
    )
    ours = sum((n for v, n in order_src_n.items() if _ours(v)))
    if len(order_src_n) == 1:
        v, n = next(iter(order_src_n.items()))
        log(
            f'''block order: "{v}" on all {n} pp.; ours, not the model's, on {ours} pp.'''
            + (
                ' (the page meta says nothing about order -- whose it is, the detection snapshot does not say; "ours" here is NOT counted, not disproved)'
                if v == "not_said"
                else ""
            )
        )
    else:
        log(
            "block order DIFFERS across pages: "
            + ", ".join(
                (
                    f'"{v}" -- {n} pp.'
                    for v, n in sorted(order_src_n.items(), key=lambda kv: (-kv[1], kv[0]))
                )
            )
            + f"; ours, not the model's, on {ours} of {files} pp."
        )
    log(
        f"anchors in the document {len(_anchors(page_html))}, observations alongside {len(side)}"
    )
    log(f"formulas: {math_note}")
    log(f"{out_html} ({os.path.getsize(out_html) / 1024:.0f} KB), crops in {blockdir}")
    return {
        "page_count": files,
        "by_bucket": counts,
        "crop_count": cut_n,
        "clipped_by_sheet": clipped,
        "html": out_html,
        "block_order": {
            "by_page_meta": dict(sorted(order_src_n.items())),
            "pages_with_our_order": ours,
        },
        "crop": crop.params(page_dpi),
        "policy": pol.snapshot(),
    }


def build(detect_dir: str, out_dir: str) -> dict:
    detect_dir = os.path.abspath(detect_dir)
    out_dir = os.path.abspath(out_dir)
    return emit(gather(detect_dir), out_dir)
