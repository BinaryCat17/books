"""First-level product: readable HTML from the contours.

Text as markup, artifacts as images in place, in the model's reading order. The
second level swaps images for markup one at a time, via `swap.py`.

WHAT NEVER TOUCHES WHAT — a rule, not taste. The observed is NOT written into
the text: score, label, rank, a clipped box live in `blocks.json`, tied by
anchor. Such marks (`⚠`, `≠`, `<mark>`, a scan link) once went into the markup,
editing the model's output in place, and it cost: the marker landed in cells
before the table caption was read and the box stopped recognising its own
table — 9 misses out of 33. `data-*` sits on OUR `<figure>`/`<p>` wrapper.

WHY TEXT TOO BECOMES AN IMAGE FOR NOW: `books detect` gives contours only and
`Block.content` is empty everywhere, so a textless block goes out as a crop
tagged `data-text="unread"` -- the eye can check contours and reading order
BEFORE a metric fixes them. Once reading exists those blocks travel as text,
with no change here.
"""
import glob
import html as _html
import json
import os
import re
import shlex
import shutil
import time

from .. import policy
from .. import text as booktext

# Shortest normalised text accepted as evidence. Sweep at `repeats_on`: the
# false-positive curve is flat (9.3..12.0 % over 2..8), so this is argued, not
# tuned.
REPEAT_MIN = 3
from ..models.base import Page
from ..run import knobs


from . import crop, swap

# THE BOOK'S KITCHEN. The build root holds EXACTLY ONE file, `book.html`, and it
# is self-contained; crops, the observed, the snapshot and the swap journal move
# here. Not tidiness: the book is opened by double-click, and a root with four
# json files and a two-megabyte js makes the reader choose what to open. Crops
# stay files EVEN WHEN inlined (`HTML_IMAGES=inline`): edits, measurements and
# the second level need them, not just reading.
ASSETS = "assets"
SOURCE = os.path.join(ASSETS, "source")

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


def anchor_of(page_index: int, block_id: int) -> str:
    """Block anchor. PER PAGE: `block_id` restarts on every page."""
    return f"p{page_index:04d}-b{block_id}"


def why_empty(o: dict | None) -> str:
    """WHY a block has no text -- in words, not one flat "unread".

    `books read` counts FIVE zeros apart in `answers/`; the book collapsed them
    into one. Measured: `p0024-b23` (gutter-shadow strip, 12x408 px) has outcome
    `stop`, error `null`, empty text -- the model ANSWERED EMPTY, while the
    caption said "unread", i.e. "we never read it". `None` on input is a sixth
    case: nothing observed alongside.
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
    """Artifact as an image. `src` is a READY source, not a path.

    It may be a half-megabyte `data:image/png;base64,…`, which is pointless and
    costly to escape; `_img_src` builds it, where the inline-or-link choice is
    made.
    """
    cap = (f"{b.label} {b.score:.2f}" if b.score is not None else b.label)
    if inside:
        cap = f"detail of {inside} · " + cap
    if info.get("clipped_by_sheet"):
        cap += " · the box left the sheet"
    # A separate attribute: a backslash inside an f-string is Python 3.12 syntax
    # and the package declares 3.10. WHY it is empty goes into the caption: a
    # mute attribute made the book call the model's silence unread.
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
    """Was this directory built by `books html`? The tell is its own snapshot.

    The old layout (`run.json` in the root) counts TOO: books built before the
    snapshot moved into `assets/` are ours — neither to overwrite unasked nor to
    call foreign. Lives here, not in `cli.py`: the builder writes the snapshot
    and must own where it lies. A path retyped elsewhere drifts silently, as it
    did when the snapshot moved.
    """
    return (os.path.exists(os.path.join(out_dir, ASSETS, "run.json"))
            or os.path.exists(os.path.join(out_dir, "run.json")))


def _keep_source(detect_dir: str, out_dir: str, log) -> dict:
    """Put beside the book WHAT IT WAS BUILT FROM.

    NOT TIDINESS: `blocks.json` carries fifteen fields per block but not
    `content`, so the read text lived only as markup inside `book.html` and in a
    foreign read directory paid for on a rented card. Delete that and the only
    way back is a new rental -- on "Refractory technology", 915 078 characters
    and $0.545. THE SECOND WIN MATTERS MORE: `books apply` with no keys takes
    the source from the book's snapshot, where an ABSOLUTE path is recorded, so
    moving the book or the read directory left it not knowing what to place.

    Copy, not move: one read serves several builds (`HTML_IMAGES`, crop
    sharpness). `answers/` comes too — seconds, tokens, stop reason are the only
    answer to "why is this block bad".
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
    # WHAT IS NAMED HERE MUST BE FOUND. After the rename to `read_with.json`
    # the old name stayed on disk and this line skipped it quietly: 2945 bytes
    # of reading fingerprint -- model name, repo, weights sha256, 25 prompts --
    # never moved into `source/`, while acceptance still showed the same 412
    # swaps. Costlier: `books read --resume` detects "read by something else"
    # through this file, so without it a model change on a resumed PAID run
    # stops being visible.
    for name, required in (("run.json", True), ("read_with.json", False)):
        src = os.path.join(detect_dir, name)
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(dst, name))
            was[name] = 1
        elif required:
            raise SystemExit(
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
    """READING observations by anchor: what `books read` already wrote aside.

    `books read` counts five zeros apart and names them ("cut off by the
    ceiling: 14" with all fourteen anchors), and that knowledge then vanished: a
    `pages/*.json` block has seven fields and no truncation flag, `blocks.json`
    carried twelve and none either (fifteen now), `finish_reason` appeared
    nowhere outside `read/`.

    THE COST OF SILENCE, on "Refractory technology": 14 truncated of 6156
    blocks — 0.23 %, 118 471 characters, 12.95 % of the book's read text
    (915 078). All fourteen entered the book, four via `books apply` (two
    tables, a formula, a chart) and ten as ordinary `<p>`, none distinguishable
    from a whole one. The worst, `p0055-b11`, is 4x4 on the scan and a `<table>`
    with 2047 `<td>` in ONE row in the book — 36 % of the book's cells.

    `content` is untouched byte for byte: the observed travels as its own field,
    tied by anchor. A missing `answers/` is NOT an error — a detect directory
    has none by construction — and the empty dict means "cannot say whether
    these were read", said aloud rather than printed as "truncated 0".
    """
    out = {}
    for fp in sorted(glob.glob(os.path.join(detect_dir, "answers", "*.json"))):
        # CATCH "WRONG JSON" TOO: a file parsing into a LIST raises
        # `AttributeError` on `.get` and would kill the whole build where the
        # right answer is "nothing observed for this page". The neighbouring
        # pages must still arrive.
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


def repeats_on(page, covered) -> dict:
    """Which blocks of the page repeat what is already printed. By `block_id`.

    ONE CLAIM, ONCE PROVED WRONG: "hide this block and no character of the page
    is lost". So a block is compared NOT with its owner and NOT with the whole
    page, but with the blocks that REMAIN.

    1935 candidates on "Refractory technology": HIDDEN 728 (37.6 %), kept for
    layout 65, differs 1142; background on a foreign page 85 (+1), 38 (+5), 36
    (+37), 17 (+200). The measure is the false share AMONG THE HIDDEN at the
    worst background, 11.7 %. Rejected: a block compared with ITSELF gave 99.0 %
    against a 1.9-6.7 % background where self-match is impossible.

    GEOMETRY IS NO SUBSTITUTE: a nested block has its text in THAT SAME owner
    for only 476 of 1935, another 140 elsewhere on the page. So the answer names
    the CARRIER of the proof; naming the enclosing box, 23 of 841 named one
    without that text.

    THE LENGTH THRESHOLD IS A WEAK LEVER: 2/3/4/5/6/8 give false shares 11.7 /
    10.7 / 11.0 / 12.0 / 9.8 / 9.3 % at 841 / 793 / 672 / 591 / 461 / 227 hidden
    — flat, so choosing by it chases noise. A two-character match ("°c", "50")
    is coincidence.

    LAYOUT IS NOT TRADED FOR RAW SOURCE: where the carrier holds the same text
    as raw latex, hiding the typeset block shows `FeO-SiO_{2}` instead of a
    formula. 66 such stay visible.
    """
    from_text = [b for b in page.blocks
                 if policy.role(b.label) != "artifact" and (b.content or "").strip()]
    nested = {b.block_id for b in from_text
              if any(o.block_id != b.block_id and covered(b.box, o.box)
                     for o in from_text)}
    # THE REMAINING — and only them. A candidate matched against another
    # candidate would let both be hidden: each "exists at the neighbour", and
    # neither stays in the book.
    kept = [b for b in from_text if b.block_id not in nested]
    norm = {b.block_id: booktext.normalize(b.content, "latex") for b in kept}
    out = {}
    for b in from_text:
        if b.block_id not in nested:
            continue
        own = booktext.normalize(b.content, "latex")
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
    r"""The carrier holds the same text as RAW latex, and we hide the typeset.

    A separate function for the mutation battery. Measured on the real book:
    65 blocks where the carrier shows `FeO-SiO_{2}` and the hidden block holds
    `\[\mathrm{FeO}-\mathrm{SiO}_{2}\]`. Hiding the second worsens the page and
    wins nothing. This said 66 and was stale by one; the figure the build
    prints is the outcome -- `books html <book>/assets/source` reports it as
    "proven but KEPT".
    """
    math = ("\\[", "\\(", "$")
    if not any(m in own for m in math):
        return False
    if any(m in carrier for m in math):
        return False
    return bool(re.search(r"[_^]\{|\\[a-zA-Z]+", carrier))


def torn_of(o: dict | None) -> bool | None:
    """Was the answer truncated: THREE states, not two.

    `True` — hit the ceiling (`finish_reason == "length"`). `False` — finished
    by itself. `None` — nobody to ask: no `answers/` alongside, or the block was
    NEVER ASKED (figures, an empty route with a declared reason).

    A separate function for the mutation battery: a check that cannot be broken
    is not proved (as `apply._same`). Of 6156 blocks 14 are truncated, 6073
    finished, 69 never asked; without `None` the last two both printed `False` —
    a field made AGAINST merging two zeros was merging them itself.
    """
    by_what = (o or {}).get("outcome")
    return None if by_what is None else (by_what == "length")


def torn_grid(grid: dict | None) -> str | None:
    """An OTSL grid that CANNOT be a real table, in one phrase.

    TORNNESS WAS NOT ENOUGH: `otsl.parse` counts continuations to nowhere, rows
    of unequal length and text outside tags, and on the truncated `p0055-b11`
    all of them are CLEAN — the answer holds not one `<nl>`. A zero from not
    knowing, while the grid screams 2047 cells in a row.

    So the rule looks at SHAPE, both halves checked by mutation
    (`tests/selfcheck.py`): one row wider than three cells, one column deeper
    than three. On "Refractory technology" EXACTLY ONE table of 104 falls under
    each — `p0055-b11` (2047 cells in a row), `p0166-b2` (7 rows of one cell).
    Median width 5 cells, second-widest row 11.

    THE THRESHOLD BARELY MATTERS HERE: a sweep 1..11 gives two finds at 1..6 and
    one at 7..11, `p0166-b2` falling off at its own number. No false positives
    at any threshold, but measured on ONE book and 104 tables.

    Returns the REASON in words, or None — "the shape is not forbidden", not
    "the table is good": cell contents are outside this rule.
    """
    if not grid:
        return None
    rows, cells = grid.get("rows") or 0, grid.get("grid_cells") or 0
    if rows == 1 and cells > 3:
        return f"the whole table in one row: {cells} cells"
    # SAY EXACTLY WHAT IS MEASURED. Judging by the AVERAGE (`cells // rows`)
    # called a 10-row / 19-cell grid — a two-column table missing one cell —
    # single-column. An average claims nothing about columns; the observation
    # can: exactly as many cells as rows.
    if rows > 3 and cells == rows:
        return f"{rows} rows and only {cells} cells -- one per row"
    return None


def _repeats_how() -> str:
    """`HTML_REPEATS`: hide a proven repeat, or show everything."""
    from ..run import knobs
    how = (knobs.knob("HTML_REPEATS") or "hide").strip()
    if how not in ("hide", "show"):
        raise SystemExit(
            f"HTML_REPEATS={how!r}: I know only hide | show. There is no "
            f"silent default here: this is the one build operation that "
            f"removes text from the reader's sight.")
    return how


def _img_how() -> str:
    """`HTML_IMAGES`: inline the crops into the book, or link to the files."""
    from ..run import knobs
    how = (knobs.knob("HTML_IMAGES") or "inline").strip()
    if how not in ("inline", "linked"):
        raise SystemExit(
            f"HTML_IMAGES={how!r}: I know only inline | linked. There is no "
            f"silent default here: a book without pictures looks assembled, "
            f"and half its meaning is figures and tables.")
    return how


def _img_src(path: str, rel: str, how: str) -> str:
    """How the book points at a crop: by path or by its own bytes.

    `inline` — `data:image/png;base64,…`: a third larger, but the book opens
    FROM ANY path. `linked` is four times smaller, yet over a network path
    (`\\\\wsl.localhost\\...`) the browser silently refuses neighbouring files
    and the reader sees a book without a single picture.
    """
    if how == "linked":
        return _html.escape(rel)
    import base64
    with open(path, "rb") as f:
        return "data:image/png;base64," + base64.b64encode(f.read()).decode()


def _union_share(boxes, sheet):
    """Share of the sheet under artifacts, by UNION rather than a sum of areas:
    nested boxes would otherwise count twice."""
    from .feed import _union_area
    if not boxes or sheet <= 0:
        return 0.0
    return min(1.0, _union_area([[float(v) for v in b] for b in boxes]) / sheet)


def _nesting(arts) -> dict:
    """Who is inside whom. Returns {inner block_id: outer block_id}.

    THROWS NOTHING AWAY — it only names the relation. The larger area is outer;
    on equal areas (it happens: `image` and `table` arrive on ONE rectangle) the
    outer is the one earlier by the model's own rank — its rank, not ours.
    """
    def area(b):
        return max(0.0, b.box[2] - b.box[0]) * max(0.0, b.box[3] - b.box[1])

    def rank(b):
        """The block's place in the model's order as a KEY, not a bare `order`.

        `models/base.py` allows `Block.order = None`: three adapters of four
        give no rank (yolox, both docling), and on the fourth it is empty for
        exactly what the first level cuts as images — 100 % of `image`,
        `figure_title`, `table`. Comparing `(o.order, o.block_id)` directly
        killed the WHOLE build on a ranked / unranked pair (`TypeError: '>=' not
        supported between instances of 'NoneType' and 'int'`). Unranked compares
        by `block_id`, AFTER the ranked: parse order, not our invention.
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
    # The chain is cut: an outer box that itself lies inside a third stays outer
    # for its own inner one, or the "detail of" caption would point at
    # nothing.
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
    """Area covered by TWO boxes or more. Vertical sweep, as in `_union_area`;
    triple cover is not counted three times.

    Exactly this ink reaches the book twice: in its own crop and inside someone
    else's. Touching (one box's `x1` equal to another's `x0`) gives 0.
    """
    if len(boxes) < 2:
        return 0.0
    xs = sorted({v for b in boxes for v in (b[0], b[2])})
    total = 0.0
    for a, c in zip(xs, xs[1:]):
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


def _sheet_trouble(blocks, arts) -> str | None:
    """What is wrong with the sheet: `empty` | `no-text` | `furniture-only` | None.

    THREE FAILURES, TWO MARKS, and the third printed someone else's: "no text"
    meant only "blocks exist, none of them text", so a sheet with one folio
    (`footer`, bucket "furniture") got the red "the whole column went into
    pictures" at
    `data-image-share="0.00"` — `bench/atlas` p. 0, and over the book "pages
    with no text block" read 9 against eight real.

    A separate function, not three lines in `build`, for the mutation battery: a
    guard that cannot be broken is not proved. THE RETURNED WORD IS ALSO THE
    ATTRIBUTE NAME (`data-empty`, `data-no-text`, `data-furniture-only`): there
    is no second copy of these names in this file.
    """
    if not blocks:
        return "empty"
    if any(policy.role(b.label) == "text" for b in blocks):
        return None
    return "no-text" if arts else "furniture-only"


def _order_src(page) -> str:
    """Where this page's `order` came from, in the adapter's own words.

    Three states, never confused: NO field — the snapshot is silent (all nine
    bench directories predate it); `null` — the adapter said "don't know"; a
    string — it named the source. The "model rank" default for a missing field
    lives in `metrics._model_has_rank` and is NOT repeated here: passing the
    unknown off as the model's is the substitution being fixed.
    """
    m = page.meta or {}
    if "reading_order" not in m:
        return "not_said"
    v = m["reading_order"]
    if v is None:
        return "the field is there, the value is null"
    return v if isinstance(v, str) else f"not a string: {v!r}"


def _ours(v) -> bool:
    """Is this order ours? One rule for the whole project — `models.base`.

    A local copy of this check would drift from the one in `metrics` at the
    first wording change; the contract and the cost of drift are recorded where
    the field is written, in the adapter contract.
    """
    from ..models.base import ours_order
    return ours_order(v)


# Formula renderer. SVG is not taste: of the three it alone lives in ONE file
# and pulls no separate fonts, and the book must open offline — it goes on a
# disk and is read half a year later. KaTeX weighs less (268 KB against 2.11 MB)
# but wants thirty font files; MathJax in chtml, the same.
MATHJAX = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "mathjax", "tex-svg.js")

# `pre` IS STRUCK FROM THE SKIP LIST ON PURPOSE: MathJax skips it by default,
# while the second level puts a formula artifact into exactly `<pre>`
# (`doc/apply.render`, kind `latex`). The default would leave the very blocks
# this is built for as source — 2260 formulas of 6080 read blocks on
# "Refractory technology".
_SKIP = ("script", "noscript", "style", "textarea", "code", "annotation",
         "annotation-xml")

# `$...$` is on; MathJax has it OFF by default (only `\\(...\\)`), and the model
# writes inline maths in dollars -- "where $\\alpha$ is the coefficient".
#
# THE MENU IS OFF, AND NOT FUSSINESS. The MathJax menu (`ui/menu`) and
# `a11y/assistive-mml` are not in the bundle: they LOAD as separate files. In an
# inlined script the path base is empty, the address resolves against the book,
# and the browser answers:
#
#   Unsafe attempt to load URL …/book.html from frame with URL …/book.html.
#   'file:' URLs are treated as unique security origins.
#
# Formulas render anyway, but a book read off a disk must go to the network for
# nothing, and a red console line on every open teaches one to ignore the
# console. THE PRICE: right-click no longer shows a formula's source TeX; the
# model's bytes remain in `assets/source/pages` and the `model_answer` field
# of `assets/swaps.json`.
_MATH_CFG = ('window.MathJax={tex:{inlineMath:[["$","$"],["\\\\(","\\\\)"]],'
             'displayMath:[["\\\\[","\\\\]"],["$$","$$"]]},'
             'options:{enableMenu:false,skipHtmlTags:'
             + json.dumps(list(_SKIP)) + '}};')


def _math(out_dir: str) -> tuple[str, str]:
    """What renders the formulas. Knob `HTML_MATH`: local | cdn | off.

    Default `local` keeps the book self-contained: 2.11 MB beside it, opening
    without a network whenever. `cdn` is for when the extra weight matters more
    than independence, and it is DECLARED in the log, not implied. `off` is raw
    LaTeX, as before this knob.
    """
    import shutil

    from ..run import knobs
    how = (knobs.knob("HTML_MATH") or "local").strip()
    if how not in ("inline", "local", "cdn", "off"):
        raise SystemExit(
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
        raise SystemExit(
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
    # inline: WE EMBED. A `</script>` inside the bundle would tear our tag, so
    # the sequence is split — an old, safe trick: the same string to JS, no
    # longer a tag end to the HTML parser.
    with open(MATHJAX, encoding="utf-8") as f:
        code = f.read().replace("</script>", "<\\/script>")
    return (cfg + f'<script id="MathJax-script">{code}</script>',
            f"formulas drawn by MathJax INSIDE the book "
            f"(+{os.path.getsize(MATHJAX)/1e6:.1f} MB) -- neither network nor "
            f"neighbouring files needed")


def build(detect_dir: str, out_dir: str, log=print) -> dict:
    """Build HTML from a `books detect` directory. Returns the build's numbers."""
    import pymupdf

    detect_dir = os.path.abspath(detect_dir)
    out_dir = os.path.abspath(out_dir)
    with open(os.path.join(detect_dir, "run.json"), encoding="utf-8") as f:
        snap = json.load(f)
    pdf = snap["source"]["path"]
    page_dpi = float(snap["raster"]["dpi"])
    if not os.path.exists(pdf):
        raise SystemExit(
            f"the parse source is not in place: {pdf}\n"
            f"HTML is built from the PDF, not from the detection raster -- a "
            f"crop of a dense table at {page_dpi:.0f} dpi is unreadable.")

    # THE SOURCE CHECK STANDS HERE, not at the end, and that cost experience.
    # sha256 used to run after all the work: `slovar`'s 568 crops cut, book.html
    # and blocks.json on disk, and only then a ValueError. A PDF swapped under
    # the same path (a djvu rebuilt with another spread cut, another book of the
    # same name) gave the worst outcome — a book made from a FOREIGN file and
    # WITHOUT a snapshot, run.json being written below and never reached — plus
    # a traceback instead of an explanation.
    from .. import detect as _detect        # _sha256, _commit, _packages
    said = (snap.get("source") or {}).get("sha256")
    now = _detect._sha256(pdf)
    if said and said != now:
        raise SystemExit(
            f"{pdf} changed after detection: the snapshot swore sha256 "
            f"{said[:12]}, now it is {now[:12]}. The crops would come from one "
            f"file and the boxes from another. Recompute books detect, or put "
            f"back the PDF the boxes were counted on.")
    # A number, not "matched". A snapshot WITHOUT the sha256 field is not
    # "checked and equal" but "nothing to check against", and it says so. The
    # branch serves snapshots predating the field; all nine
    # `bench/*/detect/run.json` carry it non-empty, so nothing reaches it now.
    log(f"source {os.path.basename(pdf)} sha256 {now[:12]}"
        + (" -- matched the detection snapshot" if said
           else " -- the detection snapshot named no sha256, nothing to "
                "check against"))

    # THE SECOND LEVEL'S SWAP JOURNAL. Rebuilding into the same directory wipes
    # the book with every swap while `swaps.json` survives and starts lying: it
    # claims "N swapped" about a book showing pictures again, and `books apply
    # --undo` then misdiagnoses "the book was edited past the journal". It was
    # edited by this very command, so this command must say so.
    _j = os.path.join(out_dir, ASSETS, "swaps.json")
    if os.path.exists(_j):
        try:
            with open(_j, encoding="utf-8") as f:
                _n = sum(len(v) for v in (json.load(f).get("swaps") or {}).values())
        except (ValueError, OSError):
            _n = -1
        raise SystemExit(
            f"{out_dir} holds the second level's swap journal"
            + (f" ({_n} swaps)" if _n >= 0 else " (unreadable)")
            + ".\nA rebuild wipes the book along with them while the journal "
              "survives and starts lying. Build into another directory, or "
              "remove swaps.json if the swaps are no longer needed.")

    expected = []          # anchors in the order the book must carry them
    files = sorted(glob.glob(os.path.join(detect_dir, "pages", "*.json")))
    if not files:
        raise SystemExit(f"no pages in {detect_dir} -- run books detect "
                         f"first")

    doc = pymupdf.open(pdf)
    # Read BEFORE the loop, not inside: otherwise once per crop (488 on the
    # book) and — worse — an environment edit mid-run would give a book with
    # some pictures inlined and some not.
    img_how = _img_how()
    repeats_how = _repeats_how()
    blockdir = os.path.join(out_dir, ASSETS, "blocks")
    os.makedirs(blockdir, exist_ok=True)
    for old in glob.glob(os.path.join(blockdir, "*.png")):
        os.unlink(old)

    body, side = [], {}
    counts = {r: 0 for r in policy.ROLES}
    cut_n = clipped = 0
    # Three troubles that SILENTLY spoil the book; all must be numbers, not
    # discoveries made while reading the finished HTML.
    #
    #  * INK TWICE — sheet share under two crops or more. Boxes may overlap and
    #    we cut by every one, so the same lines reach the book as two pictures.
    #    Opposite of a loss, so measure area, not blocks: hard36 gave 792 blocks,
    #    792 anchors, 792 crops, none lost. On `slovar`, `reference` and
    #    `reference_content` overlap 166 times (one covers up to 20 neighbours),
    #    a column reaches the book twice — 23.45% of all paper — where two
    #    earlier counters printed 0 and 0, both seeing only artifact boxes.
    #  * `nested artifacts` — two artifact boxes, one inside the other; raw
    #    output is unsuppressed and both reach the build. Which one gets the
    #    block is undeclared, so it needs its own number.
    #  * A PAGE WITHOUT TEXT — the bench's costliest: the whole column in one
    #    `table` box, the page a single <figure> with not one line. Double ink
    #    and nesting are blind to it, so two numbers stand apart: pages with no
    #    text, and the largest share of a sheet in one box.
    dup_text = nested = no_text = no_blocks = only_service = 0
    obs = observed(detect_dir)
    torn_n = shape_n = 0
    torn_a, shape_a = [], []
    # THE OTHER HALF OF THE SAME QUESTION, counted by nobody until now.
    # `dup_text` is text inside an ARTIFACT box; this is text inside a TEXT box —
    # the same words as two <p>, no crops cut, so the first number is blind to it
    # by construction. Measured on "Refractory technology": 175 against 1935,
    # eleven times more, almost all `inline_formula` (1847 of 1935) — inline
    # maths boxed over the paragraph, read twice, printed as its own <p>.
    #
    # THE DENOMINATOR IS NAMED IN THE NAME: nesting into ANY non-artifact box,
    # text and furniture together. The strict reading (bucket "text" both sides)
    # is printed beside it: 1935 against 1879, difference 56.
    dup_in_text = 0
    # COUNTED HERE RATHER THAN REMEMBERED: the strict number was once printed
    # INTO THE LOG AS A CONSTANT, so on `bench/slovar` the line honestly printed
    # 233 and promised 1879 in the same breath — a number from another book.
    dup_in_text_strict = 0
    # A REPEAT IS NOT MERE NESTING: nesting is a fact about the model's BOXES, a
    # repeat a claim about TEXT needing comparison. Both counted, both printed:
    # 1935 nested against 1916 repeats — nineteen blocks nest by box while their
    # text did not match, and dropping them would be a loss.
    repeat_count = differs = by_layout = 0
    # WHOSE ORDER WAS ASSEMBLED — the book's chief property, named nowhere until
    # now. On three adapters of four `Block.order` is our top-down left-to-right
    # sort, not the model's rank, and the adapter says so in the page meta field
    # `reading_order`. Counted per page: a hand-made directory can be mixed.
    order_src_n = {}
    ink2 = sheet_pt_all = 0.0
    worst2 = (0.0, None)
    biggest = (0.0, None)
    for fp in files:
        with open(fp, encoding="utf-8") as f:
            page = Page.from_json(json.load(f))
        order_src = _order_src(page)
        order_src_n[order_src] = order_src_n.get(order_src, 0) + 1
        arts = [b for b in page.blocks if policy.role(b.label) == "artifact"]
        repeats_page = repeats_on(page, _covered)
        sheet = float(page.width) * float(page.height)
        share = _union_share([b.box for b in arts], sheet)
        # One word, one rule (`_sheet_trouble`). Three failures, never confused:
        # "saw nothing", "saw one thing covering everything", "saw only
        # furniture". Reasoning and cost live at the rule; no second copy here.
        trouble = _sheet_trouble(page.blocks, arts)
        empty = trouble == "empty"
        blank = trouble == "no-text"
        no_text += blank
        no_blocks += empty
        only_service += trouble == "furniture-only"
        for b in arts:
            one = ((b.box[2] - b.box[0]) * (b.box[3] - b.box[1])) / sheet
            if one > biggest[0]:
                biggest = (one, page.index)
        nested_in = _nesting(arts)
        nested += len(nested_in)
        # RULE 2: a column wholly gone into pictures is marked on the sheet, and
        # so is HOW MUCH IS HIDDEN HERE. Every other shortening is visible
        # (empty crop, truncation, empty sheet); the only one that REMOVES TEXT
        # was mute — 728 blocks vanished without a trace.
        hidden_here = sum(1 for v in repeats_page.values() if v[1] == "verbatim")
        body.append(
            f'<hr class="sheet" data-sheet="{page.index}" '
            f'data-image-share="{share:.2f}"'
            + (f' data-repeats-hidden="{hidden_here}"'
               if hidden_here and repeats_how == "hide" else "")
            + (f' data-{trouble}="yes"' if trouble else '') + '>')
        cuts = []
        # NOT INSIDE THE LOOP: building the expectation during the walk made the
        # guard tautological — reverse the walk and the expectation reverses
        # too. Three mutations (reversed, shift by one, drop the last) — NOT ONE
        # was caught. It must follow from `page.blocks` on its own.
        expected.extend(anchor_of(page.index, b.block_id) for b in page.blocks)
        for b in page.blocks:
            a = anchor_of(page.index, b.block_id)
            role = policy.role(b.label)
            inside = [o for o in arts
                      if o.block_id != b.block_id and _covered(b.box, o.box)]
            if role != "artifact" and inside:
                dup_text += 1
            # The same nesting measure over TEXT boxes: words that reached the
            # book twice, as two <p>. A block does not cover itself; artifacts
            # were counted above.
            outside = [o for o in page.blocks
                       if o.block_id != b.block_id
                       and policy.role(o.label) != "artifact"
                       and _covered(b.box, o.box)]
            if role != "artifact" and outside:
                dup_in_text += 1
                if role == "text" and any(policy.role(o.label) == "text"
                                           for o in outside):
                    dup_in_text_strict += 1
            # Decided BEFORE the loop, for the whole page at once: it needs to
            # know which blocks remain, unknown inside the walk.
            repeat = repeat_text = None
            if b.block_id in repeats_page:
                owner_id, repeat_text = repeats_page[b.block_id]
                repeat = (anchor_of(page.index, owner_id)
                          if owner_id is not None else "page")
                repeat_count += repeat_text == "verbatim"
                differs += repeat_text == "differs"
                by_layout += repeat_text == "layout"
            counts[role] += 1
            # WHAT READING SAID: an attribute, not an edit — `content` travels
            # as the model's bytes, the observed alongside.
            o = obs.get(a) or {}
            torn = torn_of(o)
            shape = torn_grid(o.get("otsl_grid"))
            mark = ' data-truncated="yes"' if torn else ""
            if repeat:
                # UNDER `show` THE MARK STAYS AND THE HIDING DOES NOT: the
                # observed remains, only its consequence is switched off.
                kind = (repeat_text if repeats_how == "hide"
                       else ("shown by HTML_REPEATS=show"
                             if repeat_text == "verbatim" else repeat_text))
                mark += (f' data-repeat="{repeat}"'
                         f' data-repeat-text="{kind}"')
            if shape:
                mark += f' data-table-shape="{_html.escape(shape, quote=True)}"'
            if torn:
                torn_n += 1
                torn_a.append(a)
            if shape:
                shape_n += 1
                shape_a.append(a)
            outer = nested_in.get(b.block_id)
            outer_a = anchor_of(page.index, outer) if outer is not None else None
            if role == "artifact" or not b.content:
                rel = f"{ASSETS}/blocks/{a}.png"
                info = crop.cut(doc, page.index, b.box, page_dpi,
                                os.path.join(out_dir, rel))
                # A CROP IS ALWAYS A FILE, reaching the book as a link or as its
                # own bytes; the second copy does not cancel the first. Files
                # serve edits, measurements and the second level; the book
                # serves reading from any path.
                src = _img_src(os.path.join(out_dir, rel), rel, img_how)
                cut_n += 1
                clipped += bool(info["clipped_by_sheet"])
                cuts.append([float(v) for v in info["box_in_points"]])
                body.append(swap.wrap(
                    a, _figure(a, b, role, src, info, inside=outer_a,
                               mark=mark,
                               why=(why_empty(o if obs else None)
                                    if not b.content else None))))
            else:
                info = {}
                body.append(swap.wrap(
                    a, f'<p id="{a}" data-role="{role}" '
                       f'data-label="{b.label}"{mark}>'
                       f'{_html.escape(b.content)}</p>'))
            side[a] = {"page": page.index, "block_id": b.block_id,
                       # `None` across the board means "no `answers/`
                       # alongside", not "read without trouble".
                       "reading": (o or None),
                       # THREE VALUES, NOT TWO. `torn or None` made `null` mean
                       # both "read whole" (6073 blocks) and "never asked" (69
                       # figures) — a field made AGAINST merging two zeros
                       # merged them itself.
                       "hit_ceiling": torn,
                       "repeat_of": repeat,
                       "repeat_verdict": repeat_text,
                       "table_shape": shape,
                       "label": b.label, "score": b.score,
                       # The field was called "model rank" and lied on three
                       # adapters of four, where it is OUR position in the list.
                       # Ours named theirs printed the order metric percentages
                       # out of nothing — 86% for YOLOX, which has no rank.
                       "order": b.order, "order_source": order_src,
                       "role": role,
                       "box": list(b.box), "crop": info or None,
                       "inside_artifacts": [anchor_of(page.index, o.block_id)
                                             for o in inside] or None,
                       "inside": outer_a,
                       "contains": [anchor_of(page.index, k)
                                    for k, v in nested_in.items()
                                    if v == b.block_id] or None}
        # Counted over boxes ACTUALLY cut, in sheet points rather than `b.box`:
        # a crop has its own margin (`CROP_MARGIN`) and its own clip by the sheet
        # edge, and it is the crop that reaches the book.
        # WHAT THIS NUMBER CANNOT SEE: crops, not ink in general. On `slovar`
        # all 166 overlaps are text over text (`reference` over
        # `reference_content`, both "text" by policy). Once reading exists such
        # blocks travel as lines, no crops are cut and this falls to zero — while
        # the words stay doubled, as two <p>. That zero will be a zero from not
        # knowing, needing its own number over all blocks, not over crops.
        r = doc[page.index].rect
        sheet_pt = float(r.width) * float(r.height)
        twice = min(_twice_area(cuts), sheet_pt)
        ink2 += twice
        sheet_pt_all += sheet_pt
        if sheet_pt > 0 and twice / sheet_pt > worst2[0]:
            worst2 = (twice / sheet_pt, page.index)
    doc.close()

    # THE SECOND CHECK, AFTER THE WORK. The first asks "is this the file the
    # boxes were computed on"; this one, "was it swapped WHILE we cut". Measured
    # on a copy of `slovar/detect`, PDF swapped 1.5 s in: the build ran to the
    # end without a complaint, 568 crops came from two files, the snapshot swore
    # by the first one's hash, `replay --check` printed "41 of 41" and returned
    # 0 — a lying run declared repeatable, which the first check cannot catch by
    # construction. Cost: one pass, `slovar.pdf` is 10.7 MB and hashes in
    # 0.010 s against 6.1 s for the build.
    #
    # WHAT THE PAIR STILL MISSES: a there-and-back swap. The PDF replaced by an
    # all-black one from second 1.2 to 3.2 of a 6.3 s build and restored before
    # the end: exit code 0, 476 crops of 568 differ from the reference, 367 pure
    # black, all three snapshot hashes matched, `books replay --check` printed
    # "42 of 42". Both checks look at the EDGES; the middle is invisible to
    # them. Only a page hash beside every crop closes it; not done.
    try:
        after = _detect._sha256(pdf)
    except OSError as e:
        # A SECOND read, and the file may have vanished meanwhile. The first
        # check answers the same trouble with SystemExit and text; a traceback
        # here would make one trouble speak in two voices.
        raise SystemExit(
            f"{pdf} vanished during the build: {type(e).__name__}: {e}. "
            f"The book is not written.") from None
    if after != now:
        raise SystemExit(
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
    # THE BOOK'S ORDER IS CHECKED, NOT ASSUMED. The builder walks `page.blocks`
    # as they are and the book inherits their order — the model's rank or our
    # `order.py`. NOTHING checked that: a sceptic reversed the walk with one word
    # (`reversed`) and the full battery stayed green, 201 checks, 0 failures,
    # because all three instruments measure detect PAGES, not the assembled
    # document. One pass over the string catches any permutation, and the failure
    # names the PLACE of divergence: without it there is nothing to fix.
    got = swap.anchors(page_html)
    if got != expected:
        where = next((i for i, (a, b) in enumerate(zip(got, expected)) if a != b),
                   min(len(got), len(expected)))
        raise SystemExit(
            f"the book is assembled NOT in the order it was walked: "
            f"{len(expected)} anchors expected, {len(got)} came out; first "
            f"divergence at place {where} -- expected "
            f"{expected[where] if where < len(expected) else '(end)'}, got "
            f"{got[where] if where < len(got) else '(end)'}. The book's order "
            f"IS the reading order; muddled, the document stays sound to the "
            f"eye and unreadable in substance.")

    # LEFTOVERS OF THE OLD LAYOUT — ALOUD, NOT SILENTLY. Rebuilding into a
    # directory made before the kitchen moved puts `assets/` BESIDE the old
    # `blocks/`, `blocks.json`, `run.json`: "one file in the root" quietly stops
    # being true, the book gains two `blocks.json`, and readers take different
    # ones. We do not remove them — someone else's work, only a human may erase.
    leftovers = [n for n in ("blocks", "blocks.json", "run.json", "tex-svg.js")
               if os.path.exists(os.path.join(out_dir, n))]
    if leftovers:
        log(f"WARNING: files of the old layout remain at the book's root: "
            f"{', '.join(leftovers)}. The kitchen is now in `{ASSETS}/`, and "
            f"these are a second copy nobody reads. Remove them by hand; the "
            f"swap journal `swaps.json` at the root, however, IS READ and must "
            f"not be touched.")

    # The source goes AFTER the book assembled without a refusal: no point
    # copying 22 MB for a build that is about to fail.
    _keep_source(detect_dir, out_dir, log)
    out_html = os.path.join(out_dir, "book.html")
    with open(out_html, "w", encoding="utf-8") as f:
        f.write(page_html)
    with open(os.path.join(out_dir, ASSETS, "blocks.json"), "w",
              encoding="utf-8") as f:
        json.dump(side, f, ensure_ascii=False, indent=1)

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
        "commit": _detect._commit(),
        # sha256 RECOMPUTED, not copied from the detect snapshot: a PDF at the
        # same path can be rebuilt (another spread cut, another pymupdf, another
        # book of the same name), crops would come from the new file, the
        # snapshot would swear by the old, and `replay --check` would print
        # "full" and return 0 — a lying run declared repeatable. Same number as
        # checked BEFORE the first crop; the file is read once, not thrice.
        "source": {**snap["source"], "sha256": now,
                     "sha256_per_detect_snapshot": said,
                     # Both, not one: "equal before and after" claims about the
                     # WHOLE run; one number before the work, only its start.
                     "sha256_after_build": after},
        "adapter": {
            "name": "doc.html",
            # THE MODULE NAME is how `books replay --check` finds this
            # snapshot's writer and matches its fingerprint against today's
            # code. Without it the check printed "fingerprint never verified"
            # and `--selfcheck` returned 1: the step that makes the book was
            # the only one never verified. Same key `detect.py` writes.
            "module": "booksmith.doc.html",
            "sha256": _detect._sha256(os.path.join(here, "html.py")),
            "sha256_crop_code": _detect._sha256(os.path.join(here, "crop.py")),
            "sha256_swap_code": _detect._sha256(os.path.join(here, "swap.py")),
            "sha256_detect_snapshot": _detect._sha256(
                os.path.join(detect_dir, "run.json"))},
        "policy": policy.snapshot(),
        "crop": crop.params(page_dpi),
        # The build has no prompts, no generation, no weights — these are VALUES.
        "prompts": {},
        "generation": {"temperature": None, "max_tokens": None,
                       "top_p": None, "seed": None},
        "packages": _detect._packages(),
        "weights": {"vl": None, "layout": snap["weights"]["layout"]},
        "summary": {"page_count": len(files), "by_bucket": counts,
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
                 "comparison_normalization": booktext.norm_note("latex"),
                 "text_inside_text_box_strict":
                     dup_in_text_strict,
                 # A number, not only an attribute. `null` (not 0) means "no
                 # `answers/` alongside, nothing to say": the two zeros must
                 # differ in the snapshot too, not only in the log.
                 "reading_observed": bool(obs) or None,
                 "hit_ceiling": torn_n if obs else None,
                 # Truncation is DECLARED, not silent: a list of twenty for
                 # twenty-one troubles would read as complete.
                 "truncated_anchors": (
                     (torn_a[:20] + (["…and %d more" % (torn_n - 20)]
                                     if torn_n > 20 else []))
                     if obs else None),
                 "impossible_table_shape": shape_n if obs else None,
                 "impossible_table_anchors": (
                     (shape_a[:20] + (["…and %d more" % (shape_n - 20)]
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

    log(f"pages {len(files)}, blocks {sum(counts.values())} "
        f"(text {counts['text']}, artifacts {counts['artifact']}, "
        f"furniture {counts['furniture']})")
    # THE SHARPNESS APPLIED, not the default. `crop.params()` with no argument
    # let an empty `CROP_DPI` expand to the process's `PAGE_DPI`: `bench/atlas`
    # detected at `PAGE_DPI=150` and built at the default claimed "26 crops at
    # 144 dpi" while coordinates were rescaled from 150.
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
    # HIDING THE PROVEN IS ALLOWED, THE UNPROVEN IS NOT, so each count is
    # printed apart: "1935 hidden" would sound the same where the comparison
    # matched and where it did not.
    if repeat_count + differs + by_layout == 0:
        # A ZERO FROM NOT KNOWING, SAID ALOUD. On a detect directory without
        # reading (`bench/slovar`) there are 233 nested boxes and content in
        # none — nothing to compare — where "proven 0, differs 0" read as "no
        # repeats found".
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
            f"text.NORM_STEPS")
    if obs:
        log(f"reading observations: {len(obs)} answers alongside; cut off by "
            f"the ceiling {torn_n}, impossible table shape {shape_n}"
            + (f"; truncated: {', '.join(torn_a[:5])}"
               f"{'…' if torn_n > 5 else ''}" if torn_n else "")
            + (f"; impossible: {', '.join(shape_a[:5])}"
               f"{'…' if shape_n > 5 else ''}" if shape_n else ""))
        if torn_n or shape_n:
            log(f"  THESE BLOCKS ARE IN THE BOOK and marked "
                f"data-truncated / data-table-shape. The model's text is not "
                f"edited by a byte: the truncation is its defect, ours is to "
                f"name it aloud")
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
    # WHOSE ORDER — as a number. Without it the header's "in the model's reading
    # order" was a claim nobody checked: with yolox and both docling the order
    # is OURS, and the eye cannot tell.
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
            + f"; ours, not the model's, on {ours} of {len(files)} pp.")
    log(f"anchors in the document {len(swap.anchors(page_html))}, "
        f"observations alongside {len(side)}")
    log(f"formulas: {math_note}")
    log(f"{out_html} ({os.path.getsize(out_html)/1024:.0f} KB), "
        f"crops in {blockdir}")
    return {"page_count": len(files), "by_bucket": counts, "crop_count": cut_n,
            "clipped_by_sheet": clipped, "html": out_html,
            "block_order": {
                "by_page_meta": dict(sorted(order_src_n.items())),
                "pages_with_our_order": ours},
            "crop": crop.params(page_dpi), "policy": policy.snapshot()}
