"""Level one's product: readable HTML from the contours.

Text as markup, artifacts as images in place, in the model's reading order.
Level two swaps images for markup one at a time, via `swap.py`.

The observed is never written into the text: score, label, rank, a clipped box
live in `blocks.json`, tied by anchor, and `data-*` sits on our `<figure>`/`<p>`
wrapper. A block with no content goes out as a crop tagged `data-text="unread"`,
so contours and reading order can be checked by eye before a metric fixes them;
once it has content it travels as text, with no change here.
"""
import glob
import html as _html
import json
import os
import re
import shlex
import shutil
import time

from booksmith.core import policy
from booksmith.core import stamp, textnorm
from booksmith.core.errors import Refusal

from dataclasses import dataclass

from booksmith.core.page import Page, anchor
from booksmith.core import knobs
from booksmith.core import book, raster as crop
from booksmith.core.book import ASSETS, SOURCE
from booksmith.processing.assemble import swap
from booksmith.core import job
from booksmith.core.log import log

# Shortest normalised text taken as evidence: below it a match is coincidence.
REPEAT_MIN = 3

CSS = """
body{max-width:52em;margin:2em auto;padding:0 1em;
     font:16px/1.55 Georgia,'DejaVu Serif',serif}
figure{margin:1.2em 0;padding:0}
figure img{max-width:100%;height:auto;display:block;
           border:1px solid #ddd}
figcaption{font:12px/1.4 monospace;color:#777;margin-top:.3em}
p{margin:.7em 0}
[data-role="furniture"]{opacity:.55}
[data-text="unread"] figcaption{color:#a60}
/* A TEXT BLOCK THAT LEFT AS A PICTURE DOES NOT EAT THE SCREEN. Seven per
   book, and all seven are strips of binding shadow: the model's box landed on
   a scan defect and the model answered that noise with nothing. A 12x408 px
   crop drawn full size eats a whole column of type -- the reader meets a
   black thread instead of text. The box is NOT removed (a first-level defect,
   and it is measured), the number is not hidden (it is in the log and the
   snapshot); only the display shrinks, and the caption says WHY it is
   empty. */
[data-text="unread"] img{max-height:8em;width:auto;object-fit:contain}
figure[data-inside]{margin-left:2em;border-left:3px solid #e0c000;padding-left:.8em}
figure[data-inside] figcaption{color:#a60}
hr.sheet[data-no-text]{border-top:2px solid #c00}
hr.sheet[data-empty]{border-top:2px dotted #c00}
hr.sheet[data-empty]::after{content:"the model found nothing on this sheet";
    display:block;font:11px monospace;color:#c00;margin-top:.3em}
hr.sheet[data-no-text]:not([data-empty])::after{
    content:"the whole column went into pictures";
    display:block;font:11px monospace;color:#c00;margin-top:.3em}
hr.sheet[data-furniture-only]{border-top:2px dashed #c00}
hr.sheet[data-furniture-only]::after{
    content:"only furniture on this sheet: no text, no artifacts";
    display:block;font:11px monospace;color:#c00;margin-top:.3em}
hr.sheet{border:0;border-top:1px dashed #ccc;margin:2.5em 0}

/* CEILING TRUNCATION -- VISIBLE TO THE EYE, NOT ONLY IN THE LOG. A truncated
   answer looked no different from a whole one: 118 471 characters (12.95 % of
   the book's text) stood as ordinary <p> and <table>. The mark goes on the
   block's FRAME, not into the text -- `content` stays the model's bytes. */
[data-truncated]{border-left:3px solid #c00;padding-left:.8em;margin-left:-1em}
[data-truncated]::before{content:"the model's answer was cut off by the "
    "length ceiling -- past this point the text breaks mid-word";
    display:block;font:11px monospace;color:#c00;margin:.3em 0}
[data-table-shape]::after{content:"impossible table shape: "
    attr(data-table-shape);
    display:block;font:11px monospace;color:#c00;margin-top:.3em}

/* TABLES. There was NOT ONE rule here: 16 selectors in the whole book and
   zero table ones, so 104 tables were drawn by the browser default --
   `border-collapse:separate`, no borders, no padding, columns spread. That is
   what "tables render horribly" meant: the markup was right, there was
   nothing to show it with. */
table{border-collapse:collapse;margin:.2em 0 1.2em;font-size:.92em;
      line-height:1.35}
th,td{border:1px solid #bbb;padding:.28em .5em;vertical-align:top;
      text-align:left}
th{background:#f2f0ec;font-weight:600}
/* Digits of one width: a column of numbers aligns itself, with no guess
   about which column is numeric. Guessing would be dishonest -- in these
   tables "1 615" stands next to "Other". */
td,th{font-variant-numeric:tabular-nums}
tr:nth-child(even) td{background:#fbfaf9}
/* A WIDE TABLE SCROLLS INSIDE ITSELF instead of breaking the column of type.
   The book is 52em wide and the "Output growth" table has seven columns;
   without this rule the whole page would get horizontal scrolling. The
   wrapper already exists -- `books apply` puts it there. */
/* ALL kinds of swap, not only otsl: `apply.KINDS` is html, otsl, latex and
   text, and a wide `<table>` can arrive as kind `html` -- and then land in an
   unguarded div. This book has 0 such blocks (latex 248, otsl 104, text 60),
   but a rule is cheaper than a caveat. */
div[data-level="2"]{overflow-x:auto}
/* A table caption arrives as a SEPARATE model block (label `figure_title`)
   and stays a separate <p>: folding it into <caption> would move blocks and
   break the book's order, which a guard of its own checks. So they are made
   kin by look, not by markup. */
p[data-label="figure_title"]{font-size:.9em;color:#555;margin:1.2em 0 .2em}

/* THE OWNER'S REPEAT. The detector draws its OWN box around inline maths
   over the paragraph, the second level reads it apart -- and the same place
   arrives in the book twice: once inside the paragraph, once as its own <p>.
   On "Refractory technology" there are 1935 such blocks, and only 414 have
   their text found among the blocks that REMAIN in the book. Here stood "1916
   of 1935, found VERBATIM at the owner" -- both words wrong: 1916 came of
   comparing a block with itself, and at the OWNER the text is found for only
   476, because the box enclosing a formula and the paragraph carrying its
   text are different blocks.

   THREE CASES KEPT APART, AND THAT IS THE POINT. Where the repeat is PROVED
   by comparison the reader is not shown it: the same words are already
   printed by a block that stays. Where the text DIVERGED we show it, having
   nothing to prove a repeat with: two readings of one place differ in
   transcription, but may also carry different things. Where the repeat is
   proved but the carrier holds the same as RAW latex we show it too: hiding
   the typeset for the raw makes the page worse.

   WHERE THE HIDDEN STAYS: in `book.html` itself (the markup is in place, only
   the display is off) and in `assets/source/pages/*.json`. Here stood "and in
   blocks.json" -- wrong: `content` is not among its fields at all. */
[data-repeat-text="verbatim"]{display:none}
/* A proved repeat KEPT for the sake of layout: the carrier holds the same as
   raw latex, and hiding the typeset would show the reader `FeO-SiO_{2}`
   instead of a formula. */
[data-repeat-text="layout"]{opacity:.85}
/* The reader is told the sheet is shortened, and told it on the sheet. */
hr.sheet[data-repeats-hidden]::after{
    content:"repeats hidden on this sheet: " attr(data-repeats-hidden)
            " (the same text is printed nearby; HTML_REPEATS=show shows all)";
    display:block;font:11px monospace;color:#999;margin-top:.3em}
[data-repeat-text="differs"]{opacity:.7;border-left:2px solid #ccc;
    padding-left:.6em}
[data-repeat-text="differs"]::after{content:"repeat of block "
    attr(data-repeat) ", the text diverged";
    display:block;font:11px monospace;color:#888;margin-top:.2em}
"""


def _union_area(holes):
    """Area of the union of rectangles: a sweep along the vertical."""
    if not holes:
        return 0
    xs = sorted({v for h in holes for v in (h[0], h[2])})
    total = 0
    for a, b in zip(xs, xs[1:], strict=False):
        spans = sorted((h[1], h[3]) for h in holes if h[0] <= a and h[2] >= b)
        cov, end = 0, None
        for y0, y1 in spans:
            if end is None or y0 > end:
                cov += y1 - y0
                end = y1
            elif y1 > end:
                cov += y1 - end
                end = y1
        total += cov * (b - a)
    return total


def why_empty(o: dict | None) -> str:
    """Why a block has no text -- in words, not one flat "unread".

    `books read` counts five zeros apart in `answers/`, and they must not
    collapse here: "the model answered empty" is not "we never read it". `None`
    on input is a sixth case, nothing observed alongside.
    """
    if o is None:
        return "whether it was read: nothing to say -- no answers/ alongside"
    if o.get("error"):
        return f"there was no answer: {o['error']}"
    by_what = o.get("outcome")
    if by_what is None:
        return "never asked: the route is empty with a declared reason"
    if by_what == "length":
        return "the answer was cut off by the length ceiling"
    return "the model kept quiet: the answer came back empty"


def _figure(anchor, b, role, src, info, inside=None, mark="", why=None):
    """Artifact as an image. `src` is a ready source, not a path.

    It may be a half-megabyte `data:image/png;base64,…`, which is pointless and
    costly to escape; `_img_src` builds it, where the inline-or-link choice is
    made.
    """
    cap = (f"{b.label} {b.score:.2f}" if b.score is not None else b.label)
    if inside:
        cap = f"detail of {inside} · " + cap
    if info.get("clipped_by_sheet"):
        cap += " · the box left the sheet"
    # A separate attribute: a backslash inside an f-string wants Python 3.12
    # and the package declares 3.10. Why it is empty goes into the caption.
    unread = "" if role == "artifact" else ' data-text="unread"'
    if role != "artifact" and why:
        cap += " · " + why
    within = f' data-inside="{inside}"' if inside else ""
    return (f'<figure id="{anchor}" data-role="{role}" '
            f'data-label="{b.label}"{unread}{within}{mark}>'
            f'<img src="{src}" alt="{_html.escape(b.label)}" '
            f'width="{info["width"]}" height="{info["height"]}">'
            f'<figcaption>{_html.escape(cap)}</figcaption></figure>')


def is_our_dir(out_dir: str) -> bool:
    """Was this directory built by `books html`? The tell is its own snapshot."""
    return os.path.exists(os.path.join(out_dir, ASSETS, "run.json"))


def _keep_source(detect_dir: str, out_dir: str) -> dict:
    """Put beside the book what it was built from.

    `blocks.json` carries no `content`, so without this the read text lives only
    as markup in `book.html` and in a read directory paid for on a rented card.
    And `books apply` with no keys takes the source from here rather than from
    the snapshot's absolute path, so the book survives being moved. Copy, not
    move: one read serves several builds, and `answers/` comes too — seconds,
    tokens and stop reason are the only answer to "why is this block bad".
    """
    dst = os.path.join(out_dir, SOURCE)
    if os.path.abspath(detect_dir) == os.path.abspath(dst):
        return {"taken": "already_there"}
    was = {}
    if os.path.isdir(dst):
        shutil.rmtree(dst)
    os.makedirs(dst, exist_ok=True)
    for name in ("pages", "answers"):
        src = os.path.join(detect_dir, name)
        if os.path.isdir(src):
            shutil.copytree(src, os.path.join(dst, name))
            was[name] = len(os.listdir(src))
    # What is named here must be found: `books read --resume` sees "read by
    # something else" through `read_with.json`, so losing it hides a model
    # change on a resumed paid run.
    for name, required in (("run.json", True), ("read_with.json", False)):
        src = os.path.join(detect_dir, name)
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(dst, name))
            was[name] = 1
        elif required:
            raise Refusal(
                f"{detect_dir} has no {name} -- there would be nothing to "
                f"rebuild the book from its own source with")
        else:
            was[name] = "MISSING"
    weight = sum(os.path.getsize(os.path.join(dp, f))
              for dp, _, fs in os.walk(dst) for f in fs)
    log(f"source kept in {SOURCE}: "
        + ", ".join(f"{k} {v}" for k, v in was.items())
        + f"; {weight / 1e6:.1f} MB. The book rebuilds without it -- "
          f"`books html {os.path.join(out_dir, SOURCE)}`")
    return was


def observed(detect_dir: str) -> dict:
    """Reading observations by anchor: what `books read` already wrote aside.

    A truncated answer is indistinguishable from a whole one in the markup, so
    the flag has to come from here. `content` is untouched byte for byte: the
    observed travels as its own field, tied by anchor. A missing `answers/` is
    not an error — a detect directory has none — and the empty dict means
    "cannot say whether these were read", never "truncated 0".
    """
    out = {}
    for fp in sorted(glob.glob(os.path.join(detect_dir, "answers", "*.json"))):
        # A file parsing into a list must not kill the build: the right answer
        # is "nothing observed for this page", and the neighbours still arrive.
        try:
            with open(fp, encoding="utf-8") as f:
                recs = json.load(f).get("answers") or []
        except (ValueError, OSError, AttributeError):
            continue
        if not isinstance(recs, list):
            continue
        for r in recs:
            a = r.get("anchor")
            if not a:
                continue
            side = r.get("observed") or {}
            out[a] = {"outcome": r.get("outcome"),
                      "error": r.get("error"),
                      "prompt": side.get("prompt"),
                      "kind_promised": side.get("kind_promised"),
                      "kind_sniffed": side.get("kind_sniffed"),
                      "otsl_grid": side.get("otsl_grid")}
    return out


def repeats_on(page, covered, pol=None) -> dict:
    """Which blocks of the page repeat what is already printed. By `block_id`.

    One claim: hide this block and no character of the page is lost. So a block
    is compared not with its owner and not with the whole page but with the
    blocks that remain, and the answer names the carrier of the proof; geometry
    is no substitute, a nested block's text standing in its own owner for barely
    a quarter of the cases. Where the carrier holds the same text as raw latex
    the block stays visible: hiding the typeset for the raw makes the page worse.
    """
    pol = pol or policy.UNION
    from_text = [b for b in page.blocks
                 if pol.role(b.label) != "artifact" and (b.content or "").strip()]
    nested = {b.block_id for b in from_text
              if any(o.block_id != b.block_id and covered(b.box, o.box)
                     for o in from_text)}
    # The remaining, and only them: a candidate matched against another
    # candidate would let both be hidden, and neither would stay in the book.
    kept = [b for b in from_text if b.block_id not in nested]
    norm = {b.block_id: textnorm.normalize(b.content, "latex") for b in kept}
    out = {}
    for b in from_text:
        if b.block_id not in nested:
            continue
        own = textnorm.normalize(b.content, "latex")
        carrier = next((o for o in kept
                         if len(own) >= REPEAT_MIN and own in norm[o.block_id]),
                        None)
        why = "differs"
        if carrier is not None:
            why = ("layout" if _raw_latex_at(carrier.content, b.content)
                      else "verbatim")
        out[b.block_id] = (carrier.block_id if carrier else None, why)
    return out


def _raw_latex_at(carrier: str, own: str) -> bool:
    r"""The carrier holds the same text as raw latex, and we hide the typeset.

    The carrier shows
    `FeO-SiO_{2}` where the hidden block holds
    `\[\mathrm{FeO}-\mathrm{SiO}_{2}\]`, and hiding the second wins nothing.
    """
    math = ("\\[", "\\(", "$")
    if not any(m in own for m in math):
        return False
    if any(m in carrier for m in math):
        return False
    return bool(re.search(r"[_^]\{|\\[a-zA-Z]+", carrier))


def torn_of(o: dict | None) -> bool | None:
    """Was the answer truncated: three states, not two.

    `True` — hit the ceiling (`finish_reason == "length"`). `False` — finished by
    itself. `None` — nobody to ask: no `answers/` alongside, or the block was
    never asked.
    """
    by_what = (o or {}).get("outcome")
    return None if by_what is None else (by_what == "length")


def torn_grid(grid: dict | None) -> str | None:
    """An OTSL grid that cannot be a real table, in one phrase.

    Tornness is not enough: on an answer holding not one `<nl>` every count
    `otsl.parse` makes is clean while the grid holds thousands of cells in a row.
    So the rule looks at shape — one row wider than three cells, one column
    deeper than three — and returns the reason in words, or `None`, which is
    "the shape is not forbidden", not "the table is good": cell contents are
    outside this rule.
    """
    if not grid:
        return None
    rows, cells = grid.get("rows") or 0, grid.get("grid_cells") or 0
    if rows == 1 and cells > 3:
        return f"the whole table in one row: {cells} cells"
    # Exactly what is measured, not an average: `cells // rows` calls a 10-row
    # 19-cell grid single-column, where "as many cells as rows" is observable.
    if rows > 3 and cells == rows:
        return f"{rows} rows and only {cells} cells -- one per row"
    return None


def _repeats_how() -> str:
    """`HTML_REPEATS`: hide a proven repeat, or show everything."""
    from booksmith.core import knobs
    how = (knobs.knob("HTML_REPEATS") or "hide").strip()
    if how not in ("hide", "show"):
        raise Refusal(
            f"HTML_REPEATS={how!r}: I know only hide | show. There is no "
            f"silent default here: this is the one build operation that "
            f"removes text from the reader's sight.")
    return how


def _img_how() -> str:
    """`HTML_IMAGES`: inline the crops into the book, or link to the files."""
    from booksmith.core import knobs
    how = (knobs.knob("HTML_IMAGES") or "inline").strip()
    if how not in ("inline", "linked"):
        raise Refusal(
            f"HTML_IMAGES={how!r}: I know only inline | linked. There is no "
            f"silent default here: a book without pictures looks assembled, "
            f"and half its meaning is figures and tables.")
    return how


def _img_src(path: str, rel: str, how: str) -> str:
    """How the book points at a crop: by path or by its own bytes.

    `inline` — `data:image/png;base64,…`: a third larger, but the book opens
    from any path. `linked` is four times smaller, yet over a network path
    (`\\\\wsl.localhost\\...`) the browser silently refuses neighbouring files
    and the reader sees a book without a single picture.
    """
    if how == "linked":
        return _html.escape(rel)
    import base64
    with open(path, "rb") as f:
        return "data:image/png;base64," + base64.b64encode(f.read()).decode()


def _union_share(boxes, sheet):
    """Share of the sheet under artifacts, by union rather than a sum of areas:
    nested boxes would otherwise count twice."""
    if not boxes or sheet <= 0:
        return 0.0
    return min(1.0, _union_area([[float(v) for v in b] for b in boxes]) / sheet)


def _nesting(arts) -> dict:
    """Who is inside whom. Returns {inner block_id: outer block_id}.

    Throws nothing away — it only names the relation. The larger area is outer;
    on equal areas (`image` and `table` do arrive on one rectangle) the outer is
    the one earlier by the model's own rank, not by ours.
    """
    def area(b):
        return max(0.0, b.box[2] - b.box[0]) * max(0.0, b.box[3] - b.box[1])

    def rank(b):
        """The block's place in the model's order as a key, not a bare `order`.

        `Block.order` may be `None`: three adapters of four give no rank, and
        comparing `(o.order, o.block_id)` directly raises on a mixed pair.
        Unranked compares by `block_id`, after the ranked: parse order, not our
        invention.
        """
        return (b.order is None, b.order or 0, b.block_id)

    inner = {}
    for b in arts:
        for o in arts:
            if o.block_id == b.block_id or not _covered(b.box, o.box):
                continue
            ab, ao = area(b), area(o)
            if ab > ao * 1.02:
                continue
            if abs(ab - ao) <= ao * 0.02 and rank(o) >= rank(b):
                continue
            inner[b.block_id] = o.block_id
            break
    # The chain is cut: an outer box itself inside a third stays outer for its
    # own inner one, or the "detail of" caption would point at nothing.
    return inner


def _covered(inner, outer, part=0.9):
    """Share of `inner` covered by `outer` — exactly what decides whether a
    block disappears inside someone else's picture."""
    x0, y0 = max(inner[0], outer[0]), max(inner[1], outer[1])
    x1, y1 = min(inner[2], outer[2]), min(inner[3], outer[3])
    i = max(0.0, x1 - x0) * max(0.0, y1 - y0)
    a = max(0.0, inner[2] - inner[0]) * max(0.0, inner[3] - inner[1])
    return a > 0 and i / a >= part


def _twice_area(boxes):
    """Area covered by two boxes or more. Vertical sweep, as in `_union_area`;
    triple cover is not counted three times.

    Exactly this ink reaches the book twice: in its own crop and inside someone
    else's. Touching (one box's `x1` equal to another's `x0`) gives 0.
    """
    if len(boxes) < 2:
        return 0.0
    xs = sorted({v for b in boxes for v in (b[0], b[2])})
    total = 0.0
    for a, c in zip(xs, xs[1:], strict=False):
        if c <= a:
            continue
        ev = []
        for b in boxes:
            if b[0] <= a and b[2] >= c and b[3] > b[1]:
                ev.append((b[1], 1))
                ev.append((b[3], -1))
        ev.sort()
        cov, depth, prev = 0.0, 0, None
        for y, d in ev:
            if depth >= 2:
                cov += y - prev
            depth += d
            prev = y
        total += cov * (c - a)
    return total


def _sheet_trouble(blocks, arts, pol=None) -> str | None:
    """What is wrong with the sheet: `empty` | `no-text` | `furniture-only` | None.

    Three failures, never merged: "no text" is "blocks exist, none of them text",
    and a sheet holding one folio is the third case, not that one. A separate
    function; the returned word is also the
    attribute name, with no second copy of these names in this file.
    """
    if not blocks:
        return "empty"
    if any((pol or policy.UNION).role(b.label) == "text" for b in blocks):
        return None
    return "no-text" if arts else "furniture-only"


def _order_src(page) -> str:
    """Where this page's `order` came from, in the adapter's own words.

    Three states, never confused: no field — the snapshot is silent; `null` — the
    adapter said "don't know"; a string — it named the source. The default for a
    missing field lives in `metrics._model_has_rank`, not here.
    """
    m = page.meta or {}
    if "reading_order" not in m:
        return "not_said"
    v = m["reading_order"]
    if v is None:
        return "the field is there, the value is null"
    return v if isinstance(v, str) else f"not a string: {v!r}"


def _ours(v) -> bool:
    """Is this order ours? One rule for the whole project — `core.page`.

    A local copy would drift from the one in `metrics` at the first wording
    change; the contract is recorded where the field is written.
    """
    from booksmith.core.page import ours_order
    return ours_order(v)


# Formula renderer. SVG alone lives in one file and pulls no separate fonts, and
# the book must open offline; KaTeX weighs less (268 KB against 2.11 MB) but
# wants thirty font files, as does MathJax in chtml.
MATHJAX = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "mathjax", "tex-svg.js")

# `pre` is struck from the skip list on purpose: MathJax skips it by default,
# while level two puts a formula artifact into exactly `<pre>`
# (`assemble/apply.render`, kind `latex`).
_SKIP = ("script", "noscript", "style", "textarea", "code", "annotation",
         "annotation-xml")

# `$...$` is on; MathJax has it off by default (only `\\(...\\)`), and the model
# writes inline maths in dollars. The menu is off because `ui/menu` and
# `a11y/assistive-mml` are not in the bundle but load as separate files, which an
# inlined script resolves against the book -- a `file:` origin the browser
# refuses, on every open. The price: right-click no longer shows a formula's
# source TeX, which stays in `assets/source/pages` and the `model_answer` field
# of `assets/swaps.json`.
_MATH_CFG = ('window.MathJax={tex:{inlineMath:[["$","$"],["\\\\(","\\\\)"]],'
             'displayMath:[["\\\\[","\\\\]"],["$$","$$"]]},'
             'options:{enableMenu:false,skipHtmlTags:'
             + json.dumps(list(_SKIP)) + '}};')


def _math(out_dir: str) -> tuple[str, str]:
    """What renders the formulas. Knob `HTML_MATH`: inline | local | cdn | off.

    `inline` puts MathJax inside the book (+2.3 MB) and is the registry's
    default. `local` writes it as a neighbouring file, `cdn` pulls it from the
    network on every open and says so in the log, `off` is raw LaTeX.

    There is no second default here: the registry is asked and its answer used. A
    fallback of this module's own would be a second place naming a default, and
    with `local` over a network path the book looks built with no formulas in it.
    """
    import shutil

    from booksmith.core import knobs
    how = (knobs.knob("HTML_MATH") or "").strip()
    if how not in ("inline", "local", "cdn", "off"):
        raise Refusal(
            f"HTML_MATH={how!r}: I know only inline | local | cdn | off. "
            f"There is no silent default here: a book with unrendered "
            f"formulas looks sound and cannot be read.")
    if how == "off":
        return "", "formulas NOT rendered (HTML_MATH=off) -- raw LaTeX"
    cfg = f"<script>{_MATH_CFG}</script>"
    if how == "cdn":
        return (cfg + '<script id="MathJax-script" async '
                'src="https://cdn.jsdelivr.net/npm/mathjax@3.2.2/es5/'
                'tex-svg.js"></script>',
                "formulas drawn by MathJax FROM THE NETWORK -- without it "
                "the book will not open")
    if not os.path.exists(MATHJAX):
        raise Refusal(
            f"no {MATHJAX}: HTML_MATH={how}, and there is no renderer "
            f"beside the code. Either put it there, or HTML_MATH=cdn (needs "
            f"the network on opening), or HTML_MATH=off (raw LaTeX).")
    if how == "local":
        os.makedirs(os.path.join(out_dir, ASSETS), exist_ok=True)
        shutil.copy2(MATHJAX, os.path.join(out_dir, ASSETS, "tex-svg.js"))
        return (cfg + f'<script id="MathJax-script" async '
                f'src="{ASSETS}/tex-svg.js"></script>',
                f"formulas drawn by MathJax from {ASSETS}/tex-svg.js "
                f"({os.path.getsize(MATHJAX)/1e6:.1f} MB). WARNING: over a "
                f"network path (\\\\wsl.localhost\\...) the browser will "
                f"silently not load this file, and there will be no formulas")
    # Inline: a `</script>` inside the bundle would tear our tag, so the
    # sequence is split -- the same string to JS, no tag end to the parser.
    with open(MATHJAX, encoding="utf-8") as f:
        code = f.read().replace("</script>", "<\\/script>")
    return (cfg + f'<script id="MathJax-script">{code}</script>',
            f"formulas drawn by MathJax INSIDE the book "
            f"(+{os.path.getsize(MATHJAX)/1e6:.1f} MB) -- neither network nor "
            f"neighbouring files needed")


# ------------------------------------------------------------ the data pass
# What the book is made of, before a byte of it is emitted: every block with
# its role by the run's own policy, what reading said of it, how it nests and
# repeats, and whether the book shows it as a crop or a paragraph. A viewer
# takes a page of this; `emit` takes the whole and writes the book. Nothing
# here opens the scan: the crop facts, which need it, are the emission's.

@dataclass
class BlockData:
    anchor: str
    page: int
    block_id: int
    label: str
    cls: str
    role: str
    score: float | None
    order: int | None
    order_source: str
    content: str | None
    kind: str
    box: list
    reading: dict | None
    hit_ceiling: bool | None
    repeat_of: str | None
    repeat_verdict: str | None
    table_shape: str | None
    inside_artifacts: list | None
    inside: str | None
    contains: list | None
    # Nested in a box that is not an artifact: the same words twice as two
    # paragraphs, and strictly so when both sides are text.
    nested_in_text: bool
    nested_in_text_strict: bool
    # What the book shows: a crop, or a paragraph of the model's bytes.
    as_picture: bool
    why_empty: str | None


@dataclass
class PageData:
    index: int
    width: int
    height: int
    dpi: float
    order_source: str
    trouble: str | None
    image_share: float
    largest_artifact_share: float
    repeats_verbatim: int
    nested_artifacts: int
    blocks: list


@dataclass
class BookData:
    run_dir: str
    pdf: str
    page_dpi: float
    sha256: str | None
    sha256_said: str | None
    policy: policy.Policy
    observed: bool
    repeats_how: str
    snapshot: dict
    pages: list


def observed_page(detect_dir: str, index: int) -> dict:
    """What reading said of one page's blocks, keyed by anchor: the one
    answers file, not the directory."""
    path = os.path.join(detect_dir, "answers", f"{anchor(index)}.json")
    out = {}
    try:
        with open(path, encoding="utf-8") as f:
            recs = json.load(f).get("answers")
    except (ValueError, OSError, AttributeError):
        return out
    if not isinstance(recs, list):
        return out
    for r in recs:
        a = r.get("anchor")
        if not a:
            continue
        side = r.get("observed") or {}
        out[a] = {"outcome": r.get("outcome"),
                  "error": r.get("error"),
                  "prompt": side.get("prompt"),
                  "kind_promised": side.get("kind_promised"),
                  "kind_sniffed": side.get("kind_sniffed"),
                  "otsl_grid": side.get("otsl_grid")}
    return out


def answers_present(detect_dir: str) -> bool:
    """Whether the run carries answers at all: `None` reading facts mean
    "no answers/ alongside" only when this is false."""
    d = os.path.join(detect_dir, "answers")
    return os.path.isdir(d) and any(n.endswith(".json") for n in os.listdir(d))


def _snapshot(detect_dir: str) -> dict:
    with open(os.path.join(detect_dir, "run.json"), encoding="utf-8") as f:
        return json.load(f)


def _gather_page(page: Page, pol: policy.Policy, obs: dict, obs_present: bool) -> PageData:
    """One page's data, the loop the builder walked, without the scan."""
    order_src = _order_src(page)
    arts = [b for b in page.blocks if pol.role(b.label) == "artifact"]
    repeats_page = repeats_on(page, _covered, pol)
    sheet = float(page.width) * float(page.height)
    share = _union_share([b.box for b in arts], sheet)
    trouble = _sheet_trouble(page.blocks, arts, pol)
    biggest = 0.0
    for b in arts:
        one = ((b.box[2] - b.box[0]) * (b.box[3] - b.box[1])) / sheet if sheet else 0.0
        biggest = max(biggest, one)
    nested_in = _nesting(arts)
    verbatim = sum(1 for v in repeats_page.values() if v[1] == "verbatim")
    blocks = []
    for b in page.blocks:
        a = anchor(page.index, b.block_id)
        role = pol.role(b.label)
        inside = [o for o in arts
                  if o.block_id != b.block_id and _covered(b.box, o.box)]
        outside = [o for o in page.blocks
                   if o.block_id != b.block_id
                   and pol.role(o.label) != "artifact"
                   and _covered(b.box, o.box)]
        in_text = role != "artifact" and bool(outside)
        strict = (in_text and role == "text"
                  and any(pol.role(o.label) == "text" for o in outside))
        repeat = repeat_text = None
        if b.block_id in repeats_page:
            owner_id, repeat_text = repeats_page[b.block_id]
            repeat = (anchor(page.index, owner_id)
                      if owner_id is not None else "page")
        o = obs.get(a) or {}
        outer = nested_in.get(b.block_id)
        outer_a = anchor(page.index, outer) if outer is not None else None
        # `.strip()`: `"   "` is truthy, so a whitespace answer would take
        # the paragraph branch -- an empty `<p></p>`, no crop cut, the ink
        # gone while every counter called it text. `from_text` asks the same.
        as_picture = role == "artifact" or not (b.content or "").strip()
        blocks.append(BlockData(
            anchor=a, page=page.index, block_id=b.block_id, label=b.label,
            cls=pol.cls(b.label), role=role, score=b.score, order=b.order,
            order_source=order_src, content=b.content, kind=b.kind,
            box=list(b.box),
            # `None` across the board means "no `answers/` alongside", not
            # "read without trouble".
            reading=(o or None),
            # Three values, not two: `torn or None` would make `null` mean
            # both "read whole" and "never asked".
            hit_ceiling=torn_of(o),
            repeat_of=repeat, repeat_verdict=repeat_text,
            table_shape=torn_grid(o.get("otsl_grid")),
            inside_artifacts=[anchor(page.index, x.block_id) for x in inside] or None,
            inside=outer_a,
            contains=[anchor(page.index, k) for k, v in nested_in.items()
                      if v == b.block_id] or None,
            nested_in_text=in_text, nested_in_text_strict=strict,
            as_picture=as_picture,
            why_empty=(why_empty(o if obs_present else None)
                       if not b.content else None)))
    return PageData(index=page.index, width=page.width, height=page.height,
                    dpi=float(page.dpi), order_source=order_src, trouble=trouble,
                    image_share=share, largest_artifact_share=biggest,
                    repeats_verbatim=verbatim, nested_artifacts=len(nested_in),
                    blocks=blocks)


def gather_page(detect_dir: str, index: int) -> PageData:
    """One page of a run as the book would show it: the page file and its
    answers file, and nothing else opened."""
    snap = _snapshot(detect_dir)
    pol = policy.Policy.from_snapshot(snap.get("policy"))
    path = os.path.join(detect_dir, "pages", f"{index:04d}.json")
    if not os.path.isfile(path):
        raise Refusal(f"no page {index} in {detect_dir}")
    with open(path, encoding="utf-8") as f:
        page = Page.from_json(json.load(f))
    return _gather_page(page, pol, observed_page(detect_dir, index),
                        answers_present(detect_dir))


def gather(detect_dir: str, verify: bool = True) -> BookData:
    """The whole run as data. `verify` hashes the scan against the snapshot,
    which a build must and a viewer need not."""
    snap = _snapshot(detect_dir)
    pdf = snap["source"]["path"]
    page_dpi = float(snap["raster"]["dpi"])
    # The run's own policy, out of its snapshot: a block's role is the
    # model's declaration, not whatever this process happens to know.
    pol = policy.Policy.from_snapshot(snap.get("policy"))
    if not os.path.exists(pdf):
        raise Refusal(
            f"the parse source is not in place: {pdf}\n"
            f"HTML is built from the PDF, not from the detection raster -- a "
            f"crop of a dense table at {page_dpi:.0f} dpi is unreadable.")
    said = (snap.get("source") or {}).get("sha256")
    now = None
    if verify:
        # The source check stands here, not at the end: after the work it
        # would give a book made from a foreign file and no snapshot.
        now = stamp.sha256(pdf)
        if said and said != now:
            raise Refusal(
                f"{pdf} changed after detection: the snapshot swore sha256 "
                f"{said[:12]}, now it is {now[:12]}. The crops would come from "
                f"one file and the boxes from another. Recompute books detect, "
                f"or put back the PDF the boxes were counted on.")
        # A number, not "matched": a snapshot without the field is "nothing
        # to check against", not "checked and equal", and it says so.
        log(f"source {os.path.basename(pdf)} sha256 {now[:12]}"
            + (" -- matched the detection snapshot" if said
               else " -- the detection snapshot named no sha256, nothing to "
                    "check against"))
    files = sorted(glob.glob(os.path.join(detect_dir, "pages", "*.json")))
    if not files:
        raise Refusal(f"no pages in {detect_dir} -- run books detect first")
    obs_present = answers_present(detect_dir)
    repeats_how = _repeats_how()
    pages = []
    for page_n, fp in enumerate(files, 1):
        # A build is a job: it says where it is and can be stopped between pages.
        job.current().check()
        with open(fp, encoding="utf-8") as f:
            page = Page.from_json(json.load(f))
        pages.append(_gather_page(page, pol, observed_page(detect_dir, page.index),
                                  obs_present))
        if page_n % 10 == 0 or page_n == len(files):
            log(f"  {page_n}/{len(files)} pages gathered", n=page_n, of=len(files))
    return BookData(run_dir=detect_dir, pdf=pdf, page_dpi=page_dpi, sha256=now,
                    sha256_said=said, policy=pol, observed=obs_present,
                    repeats_how=repeats_how, snapshot=snap, pages=pages)


# ------------------------------------------------------------ the emission
def _refuse_live_journal(out_dir: str) -> None:
    """Level two's swap journal, and this stands first: rebuilding into the
    same directory wipes the book while `swaps.json` survives and starts
    lying, and `books apply --undo` would then blame an edit past the
    journal. A refusal about destroying the output belongs above every
    complaint about the input."""
    _j = book.journal_path(out_dir)
    if os.path.exists(_j):
        try:
            with open(_j, encoding="utf-8") as f:
                _n = sum(len(v) for v in (json.load(f).get("swaps") or {}).values())
        except (ValueError, OSError):
            _n = -1
        raise Refusal(
            f"{out_dir} holds the second level's swap journal"
            + (f" ({_n} swaps)" if _n >= 0 else " (unreadable)")
            + ".\nA rebuild wipes the book along with them while the journal "
              "survives and starts lying. Build into another directory, or "
              "remove swaps.json if the swaps are no longer needed.")


def emit(data: BookData, out_dir: str) -> dict:
    """The book written out of the data: crops cut from the scan, the page as
    markup, `blocks.json` with the crop facts beside each block, the build's
    own snapshot, the source kept beside it. Returns the build's numbers."""
    out_dir = os.path.abspath(out_dir)
    detect_dir = data.run_dir
    _refuse_live_journal(out_dir)
    pdf, page_dpi, pol = data.pdf, data.page_dpi, data.policy
    now = data.sha256 if data.sha256 is not None else stamp.sha256(pdf)
    said = data.sha256_said
    # Data gathered without verifying is verified here: a book is never
    # built from a scan other than the one the boxes were counted on.
    if said and now != said:
        raise Refusal(
            f"{pdf} changed after detection: the snapshot swore sha256 "
            f"{said[:12]}, now it is {now[:12]}. The crops would come from "
            f"one file and the boxes from another.")
    obs = data.observed
    repeats_how = data.repeats_how

    doc = crop.open_pdf(pdf)
    # Read before the loop, not inside: an environment edit mid-run would give a
    # book with some pictures inlined and some not.
    img_how = _img_how()
    blockdir = os.path.join(out_dir, ASSETS, "blocks")
    os.makedirs(blockdir, exist_ok=True)
    for old in glob.glob(os.path.join(blockdir, "*.png")):
        os.unlink(old)

    expected = []          # anchors in the order the book must carry them
    body, side = [], {}
    counts = {r: 0 for r in policy.ROLES}
    cut_n = clipped = 0
    dup_text = nested = no_text = no_blocks = only_service = 0
    torn_n = shape_n = 0
    torn_a, shape_a = [], []
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
                f'<hr class="sheet" data-sheet="{pg.index}" '
                f'data-image-share="{pg.image_share:.2f}"'
                + (f' data-repeats-hidden="{pg.repeats_verbatim}"'
                   if pg.repeats_verbatim and repeats_how == "hide" else "")
                + (f' data-{pg.trouble}="yes"' if pg.trouble else '') + '>')
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
                    # Under `show` the mark stays and the hiding does not: only
                    # the consequence of the observation is switched off.
                    kind = (b.repeat_verdict if repeats_how == "hide"
                            else ("shown by HTML_REPEATS=show"
                                  if b.repeat_verdict == "verbatim" else b.repeat_verdict))
                    mark += (f' data-repeat="{b.repeat_of}"'
                             f' data-repeat-text="{kind}"')
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
                    info = crop.cut(doc, pg.index, b.box, page_dpi,
                                    os.path.join(out_dir, rel))
                    # A crop is always a file, reaching the book as a link or as
                    # its own bytes: files serve edits, measurements and level
                    # two, the book serves reading from any path.
                    src = _img_src(os.path.join(out_dir, rel), rel, img_how)
                    cut_n += 1
                    clipped += bool(info["clipped_by_sheet"])
                    cuts.append([float(v) for v in info["box_in_points"]])
                    body.append(swap.wrap(
                        a, _figure(a, b, b.role, src, info, inside=b.inside,
                                   mark=mark, why=b.why_empty)))
                else:
                    info = {}
                    body.append(swap.wrap(
                        a, f'<p id="{a}" data-role="{b.role}" '
                           f'data-label="{b.label}"{mark}>'
                           f'{_html.escape(b.content)}</p>'))
                side[a] = {"page": b.page, "block_id": b.block_id,
                           "reading": b.reading,
                           "hit_ceiling": b.hit_ceiling,
                           "repeat_of": b.repeat_of,
                           "repeat_verdict": b.repeat_verdict,
                           "table_shape": b.table_shape,
                           "label": b.label, "score": b.score,
                           # A position in the list, not a model rank on three
                           # adapters of four: `order_source` says which it is.
                           "order": b.order, "order_source": b.order_source,
                           "role": b.role,
                           "box": list(b.box), "crop": info or None,
                           "inside_artifacts": b.inside_artifacts,
                           "inside": b.inside,
                           "contains": b.contains}
            # Counted over the boxes actually cut, in sheet points rather than
            # `b.box`: a crop has its own margin (`CROP_MARGIN`) and its own
            # clip by the sheet edge, and it is the crop that reaches the book.
            r = doc[pg.index].rect
            sheet_pt = float(r.width) * float(r.height)
            twice = min(_twice_area(cuts), sheet_pt)
            ink2 += twice
            sheet_pt_all += sheet_pt
            if sheet_pt > 0 and twice / sheet_pt > worst2[0]:
                worst2 = (twice / sheet_pt, pg.index)
    finally:
        doc.close()

    # The second check, after the work: the first asks "is this the file the
    # boxes were computed on", this one "was it swapped while we cut". Both look
    # at the edges -- a there-and-back swap inside the build is invisible to
    # them, and only a page hash beside every crop would close that.
    try:
        after = stamp.sha256(pdf)
    except OSError as e:
        raise Refusal(
            f"{pdf} vanished during the build: {type(e).__name__}: {e}. "
            f"The book is not written.") from None
    if after != now:
        raise Refusal(
            f"{pdf} was swapped DURING the build: at the start sha256 "
            f"{now[:12]}, now {after[:12]}. Some crops are cut from one file "
            f"and some from another, and which is unknown. The book is not "
            f"written; repeat books html whole.")

    os.makedirs(out_dir, exist_ok=True)
    math_head, math_note = _math(out_dir)
    page_html = ("<!doctype html>\n<html lang=\"ru\"><head>"
                 "<meta charset=\"utf-8\">"
                 f"<title>{_html.escape(os.path.basename(pdf))}</title>"
                 f"<style>{CSS}</style>{math_head}</head>\n<body>\n"
                 + "\n".join(body) + "\n</body></html>\n")
    # The book's order is checked, not assumed: every metric measures detect
    # pages and not the assembled document, so a reversed walk would pass them
    # all. One pass over the string catches any permutation, and the failure
    # names the place of divergence.
    got = swap.anchors(page_html)
    if got != expected:
        where = next((i for i, (a, b) in enumerate(zip(got, expected, strict=False)) if a != b),
                     min(len(got), len(expected)))
        raise Refusal(
            f"the book is assembled NOT in the order it was walked: "
            f"{len(expected)} anchors expected, {len(got)} came out; first "
            f"divergence at place {where} -- expected "
            f"{expected[where] if where < len(expected) else '(end)'}, got "
            f"{got[where] if where < len(got) else '(end)'}. The book's order "
            f"IS the reading order; muddled, the document stays sound to the "
            f"eye and unreadable in substance.")

    # The source goes after the book assembles without a refusal: no point
    # copying 22 MB for a build that is about to fail.
    _keep_source(detect_dir, out_dir)
    out_html = os.path.join(out_dir, "book.html")
    with open(out_html, "w", encoding="utf-8") as f:
        f.write(page_html)
    with open(os.path.join(out_dir, ASSETS, "blocks.json"), "w",
              encoding="utf-8") as f:
        json.dump(side, f, ensure_ascii=False, indent=1)

    files = len(data.pages)
    snap = data.snapshot
    # Its own snapshot, not "inherit detection": the build has its own knobs
    # (`CROP_DPI`, `CROP_MARGIN`) and policy, without which nothing says at what
    # sharpness these pictures were cut. `books replay --check` must return 0
    # here too.
    here = os.path.dirname(os.path.abspath(__file__))
    snap_out = {
        "when": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "knobs": knobs.snapshot(),
        "raster": dict(snap["raster"]),
        "args": {"detect": detect_dir, "out": out_dir},
        "commit": stamp.commit(),
        # sha256 recomputed, not copied from the detect snapshot: a PDF rebuilt
        # at the same path gives crops from the new file under a snapshot
        # swearing by the old, which `replay --check` would call repeatable.
        "source": {**snap["source"], "sha256": now,
                   "sha256_per_detect_snapshot": said,
                   # Both, not one: two numbers claim about the whole run,
                   # one only about its start.
                   "sha256_after_build": after},
        "adapter": {
            "name": "doc.html",
            # The module name is how `books replay --check` finds this
            # snapshot's writer and matches its fingerprint against the code.
            # The same key `detect.py` writes.
            "module": __name__,
            "sha256": stamp.sha256(os.path.join(here, "html.py")),
            "sha256_crop_code": stamp.sha256(crop.__file__),
            "sha256_swap_code": stamp.sha256(os.path.join(here, "swap.py")),
            "sha256_detect_snapshot": stamp.sha256(
                os.path.join(detect_dir, "run.json"))},
        "policy": pol.snapshot(),
        "crop": crop.params(page_dpi),
        # The build has no prompts, no generation, no weights — these are values.
        "prompts": {},
        "generation": {"temperature": None, "max_tokens": None,
                       "top_p": None, "seed": None},
        "packages": stamp.packages(),
        "weights": {"vl": None, "layout": snap["weights"]["layout"]},
        "summary": {"page_count": files, "by_bucket": counts,
                    "crop_count": cut_n, "clipped_by_sheet": clipped,
                    "double_ink_sheet_share": (
                        round(ink2 / sheet_pt_all, 4)
                        if sheet_pt_all > 0 else None),
                    "worst_sheet_double_ink": (
                        {"page_no": worst2[1], "share": round(worst2[0], 4)}
                        if worst2[1] is not None else None),
                    "text_inside_artifact_boxes": dup_text,
                    "text_inside_non_artifact_box": dup_in_text,
                    "repeats_proven": repeat_count,
                    "repeats_mode": repeats_how,
                    "nested_but_text_differs": differs,
                    "repeats_kept_for_layout": by_layout,
                    "comparison_normalization": textnorm.norm_note("latex"),
                    "text_inside_text_box_strict":
                        dup_in_text_strict,
                    # `null`, not 0: "no `answers/` alongside, nothing to say"
                    # must differ from zero troubles in the snapshot too.
                    "reading_observed": bool(obs) or None,
                    "hit_ceiling": torn_n if obs else None,
                    # The list says when it is cut short: twenty of twenty-one
                    # would read as complete.
                    "truncated_anchors": (
                        (torn_a[:20] + ([f"…and {torn_n - 20} more"]
                                        if torn_n > 20 else []))
                        if obs else None),
                    "impossible_table_shape": shape_n if obs else None,
                    "impossible_table_anchors": (
                        (shape_a[:20] + ([f"…and {shape_n - 20} more"]
                                         if shape_n > 20 else []))
                        if obs else None),
                    "nested_artifacts": nested,
                    "block_order": {
                        "by_page_meta": dict(sorted(order_src_n.items())),
                        "pages_with_our_order": sum(
                            n for v, n in order_src_n.items() if _ours(v))},
                    "anchor_count": len(swap.anchors(page_html))},
        "repeat_command": " ".join(shlex.quote(a) for a in
                                   ["books", "html", detect_dir, "--out", out_dir]),
    }
    with open(os.path.join(out_dir, ASSETS, "run.json"), "w",
              encoding="utf-8") as f:
        json.dump(snap_out, f, ensure_ascii=False, indent=1)

    # `manifest.json` is what makes the directory a book: it carries
    # `source: {name, sha256}`, and by it `core.book.Book.list` tells a book from
    # a stray, `datasets.bench.Bench` opens one, and the format floors count. The
    # values are not invented here -- both come from the snapshot's own `source`
    # block, whose sha256 is recomputed from the file this build read.
    man = os.path.join(out_dir, "manifest.json")
    if not os.path.isfile(man):
        with open(man, "w", encoding="utf-8") as f:
            json.dump({"book": os.path.basename(out_dir.rstrip("/")),
                       "source": {"name": os.path.basename(pdf),
                                  "sha256": now}},
                      f, ensure_ascii=False, indent=1)

    log(f"pages {files}, blocks {sum(counts.values())} "
        f"(text {counts['text']}, artifacts {counts['artifact']}, "
        f"furniture {counts['furniture']})")
    # The sharpness applied, not the default: `crop.params()` with no argument
    # lets an empty `CROP_DPI` expand to the process's own `PAGE_DPI`, which the
    # detection need not have used.
    _cp = crop.params(page_dpi)
    log(f"crops {cut_n} at {_cp['dpi']:.0f} dpi ({_cp['dpi_source']}), "
        f"margin {_cp['margin']}, clipped by the sheet {clipped}")
    # "0.00%" means "all crops compared, no intersections"; a zero denominator
    # means "nothing to compare with", and it says so.
    if sheet_pt_all > 0:
        log(f"ink twice {ink2 / sheet_pt_all * 100:.2f}% of sheet area"
            + (f", worst sheet p. {worst2[1]}: {worst2[0] * 100:.0f}%"
               if worst2[1] is not None
               else " -- on no sheet did the crops intersect"))
    else:
        log("ink twice: no data -- the sheet area is zero")
    log(f"text blocks inside an artifact box {dup_text} "
        f"(they ARE in the HTML, but their ink also went into the artifact's "
        f"picture), nested artifacts {nested} (subordinated to the outer one "
        f"and marked data-inside; not one thrown away)")
    log(f"text blocks inside a NON-ARTIFACT box {dup_in_text} -- the same "
        f"words went into the book twice, as two <p>; no crops are cut for "
        f"them, and the double-ink counter is blind to them by construction. "
        f"The denominator is in the name: any box but an artifact one; of "
        f"those blocks with bucket \"text\" on BOTH sides, "
        f"{dup_in_text_strict}"
        + (" -- the numbers agree, no furniture boxes among the enclosing"
           if dup_in_text == dup_in_text_strict else
           f", the difference of {dup_in_text - dup_in_text_strict} falls on "
           f"furniture boxes"))
    # Hiding the proven is allowed, the unproven is not, so the counts print
    # apart: one number would sound the same where the comparison matched and
    # where it did not.
    if repeat_count + differs + by_layout == 0:
        # A zero from not knowing, said aloud: nested boxes with content in none
        # of them is not "no repeats found".
        log(f"repeats: NOTHING TO COMPARE WITH -- {dup_in_text} nested "
            f"boxes and content in none of them. This is not \"no repeats "
            f"found\"")
    else:
        log(f"of them a REPEAT: proved by comparison {repeat_count} "
            + ("(HIDDEN in the book, markup and source in place)"
               if repeats_how == "hide"
               else "(ALL SHOWN: HTML_REPEATS=show)")
            + f", the text diverged at {differs} (SHOWN and marked -- there "
            f"is nothing to prove a repeat with), at {by_layout} proved but "
            f"KEPT: the carrier holds the same as raw latex, and hiding the "
            f"typeset would make the page worse. Compared NOT with the owner "
            f"but with the blocks that REMAIN; the \"latex\" step -- see "
            f"core/textnorm.NORM_STEPS")
    if obs:
        n_obs = sum(1 for pg in data.pages for b in pg.blocks if b.reading)
        log(f"reading observations: {n_obs} answers alongside; cut off by "
            f"the ceiling {torn_n}, impossible table shape {shape_n}"
            + (f"; truncated: {', '.join(torn_a[:5])}"
               f"{'…' if torn_n > 5 else ''}" if torn_n else "")
            + (f"; impossible: {', '.join(shape_a[:5])}"
               f"{'…' if shape_n > 5 else ''}" if shape_n else ""))
        if torn_n or shape_n:
            log("  THESE BLOCKS ARE IN THE BOOK and marked "
                "data-truncated / data-table-shape. The model's text is not "
                "edited by a byte: the truncation is its defect, ours is to "
                "name it aloud")
    else:
        log("reading observations: NO answers/ alongside -- whether these "
            "blocks were read and how it ended, there is nothing to say. This "
            "is not \"no troubles found\"")
    log(f"pages where the model found NOTHING: {no_blocks}")
    log(f"pages with nothing but furniture: {only_service} "
        f"(no text, no artifacts -- there was nothing to cut into pictures, "
        f"and this is NOT \"the whole column went into pictures\")")
    log(f"pages without a single text block {no_text} "
        f"(the whole column went into pictures), largest share of a sheet in "
        f"one box {biggest[0]*100:.0f}%"
        + (f" on p. {biggest[1]}" if biggest[1] is not None else ""))
    # Whose order, as a number: with yolox and both docling the order is ours,
    # and the eye cannot tell.
    ours = sum(n for v, n in order_src_n.items() if _ours(v))
    if len(order_src_n) == 1:
        v, n = next(iter(order_src_n.items()))
        log(f"block order: \"{v}\" on all {n} pp.; "
            f"ours, not the model's, on {ours} pp."
            + (" (the page meta says nothing about order -- whose it is, the "
               "detection snapshot does not say; \"ours\" here is NOT "
               "counted, not disproved)"
               if v == "not_said" else ""))
    else:
        log("block order DIFFERS across pages: "
            + ", ".join(f"\"{v}\" -- {n} pp."
                        for v, n in sorted(order_src_n.items(),
                                           key=lambda kv: (-kv[1], kv[0])))
            + f"; ours, not the model's, on {ours} of {files} pp.")
    log(f"anchors in the document {len(swap.anchors(page_html))}, "
        f"observations alongside {len(side)}")
    log(f"formulas: {math_note}")
    log(f"{out_html} ({os.path.getsize(out_html)/1024:.0f} KB), "
        f"crops in {blockdir}")
    return {"page_count": files, "by_bucket": counts, "crop_count": cut_n,
            "clipped_by_sheet": clipped, "html": out_html,
            "block_order": {
                "by_page_meta": dict(sorted(order_src_n.items())),
                "pages_with_our_order": ours},
            "crop": crop.params(page_dpi), "policy": pol.snapshot()}


def build(detect_dir: str, out_dir: str) -> dict:
    """Build HTML from a `books detect` directory: the data pass, then the
    emission. Returns the build's numbers."""
    detect_dir = os.path.abspath(detect_dir)
    out_dir = os.path.abspath(out_dir)
    # `emit` refuses this too; here it stands before `gather` opens the
    # input, since a refusal about destroying the output belongs above every
    # complaint about the input.
    _refuse_live_journal(out_dir)
    return emit(gather(detect_dir), out_dir)
