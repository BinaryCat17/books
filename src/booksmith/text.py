"""Reading metric: what the model read, against text that is known.

The old reading figures were measured against Mistral OCR output -- another
model, not known text -- and are void to the last one (`docs/ocr-notes.md`).
This file compares an answer against TRUTH and can fail. It measures
CHARACTERS and CELL ADDRESSES; boxes are `metrics.py`, delivery to the second
level is `fitness.py`, and one combined number would only trade one defect for
another.

FOUR ZEROS THAT MUST NOT BE CONFUSED -- half the code below is for them.

  * AN ARTIFACT: silence is the right answer.
  * THE MODEL WAS SILENT: its cheapest defect, since silence earns CER 0 over
    the answered subset. Counted wholly wrong in the book CER; CER over
    answered is a separate line.
  * TRUTH NOT ANNOTATED: out of the denominator, own line.
  * NOT PAIRED: unknowable, counted at the full length of truth.

PAIRING, three stages in falling trust: anchor verified by box -> ids agreeing
wholesale, box-verified too -> geometry (`_match`, `_anchor_num`). The report
names each: 100% by anchor and 100% by geometry are worth different things.
There is NO fallback -- a rejected anchor consumes the answer block, since
pairing a block whose anchor points elsewhere passes off a foreign answer as
this one's (flawless boxes, anchors swapped: share 0.0, by anchor 0, by number
0, by geometry 0, anchor off box 2). Anchors lie, and so does geometry: two
columns side by side walk a pair to the neighbour. So THE SHARE PAIRED AND THE
STAGE THAT PAIRED IT ARE ALWAYS PRINTED -- CER 0.02 over two blocks of forty
otherwise reads as "the model reads well". The gate is `metrics.matches`
unchanged (two-way coverage 0.75, 6 px), so "box found" and "block paired"
cannot drift apart.

THE NORMALISATION BOUNDARY IS DECLARED AND TRAVELS INTO THE RESULT, refusals
and all (`NORM_REFUSED`, printed above every report). Six books, 32 634 cells
(`docs/lessons-from-deleted-code.md`): NFKC and spaces remove 127 mismatches at
harm 0, case 90 at 0, dash/hyphen/minus 376 at 0, decimal comma 42 at 0,
trailing punctuation 147 at 0. Past that it harms: leading punctuation 139 at
harm 4, all punctuation 504 at harm 108, Cyrillic/Latin lookalikes 14 finds of
29 with the step against 16 of 29 without it (lifts 2.70 and 3.06), and here a
lookalike IS the recognition error. Hyphenation is not joined either: it is a rule of the MODEL's output, and joining while comparing
would clear a model that glued where it must not.

A ROW SHIFT IN A TABLE is the leading invisible damage, so cells are compared
BY ADDRESS: the bag of cells is identical before and after a shift (equal as a
Counter) while the share matched by address falls 0.89 -> 0.33, 8 of 9 against
3 of 9.

`books text bench/slovar/truth bench/slovar/truth` compares truth with itself
and prints three of the four zeros at once: 523 of 523 blocks paired by number,
text 520 blocks and 56578 characters at CER 0.0000, tables 2 blocks and 227
cells with NO ANSWER AT ALL (not "0% matched"), one bait silent, truth unmarked
0. Identity is only a floor; that the numbers can move is said by the mutation
battery, which can fail too -- let normalisation glue hyphens (the forbidden
patch) and it reports 2 uncaught. Distance is checked against direct DP on 700
random pairs, 0 discrepancies.
"""
import copy
import html as _html
import json
import os
import re
import unicodedata
from html.parser import HTMLParser

from . import metrics, otsl, policy


class TextError(RuntimeError):
    pass


# --------------------------------------------------------- normalisation
#
# The level is a VALUE: it travels into the returned dict, or two measurements
# from different days are incomparable in silence.
NORM = "boundary"

_DASHES = "‐‑‒–—―−­-"
_TAIL = ".,;:!?…"
_WS = re.compile(r"\s+")
_DEC = re.compile(r"(?<=\d),(?=\d)")

NORM_STEPS = {
    "none": [],
    "boundary": ["NFKC and spaces", "case", "dash/hyphen/minus",
                 "decimal comma", "trailing punctuation"],
    # SIXTH STEP, MEASURED SEPARATELY. Everything above was measured on CELLS
    # (32 634 over six books) and says nothing about matching a formula against
    # prose: display maths arrives as `\[...\]`, the same fragment inside a
    # paragraph as `$...$` or plain characters (`1728°C`), and at "boundary"
    # they match 0 times by construction.
    #
    # "Технология огнеупоров", 1935 blocks nested by box inside a text block:
    # the text is found among blocks that REMAIN in the book for 841 (43.5 %)
    # at a worst background of 98 (5.1 %), ratio 8.6. Stripping typeface with a
    # SPACE gave 414 (21.4 %) at background 42 (2.2 %), ratio 9.9 -- better
    # ratio, near-equal share of false among the hidden (10.1 % against
    # 11.7 %), half the finds. Chosen by the second number: we hide blocks, so
    # the cost of error counts from what is hidden. (A block searched in prose
    # that contains it self-matches at 99.0 %; excluding it, 35.1 %.)
    #
    # REJECTED -- stripping spaces entirely on top of this: signal 1268
    # (65.5 %) against 841, background 162 (8.4 %) against 98, order holding on
    # all four shifts (6.5/5.7/2.9 against 5.1/4.6/2.4). Profitable too, net
    # 1106 against 743, +363 correct hides for +64 false, 5.7 to 1, and refused
    # because a false hide takes text out of the book while a missed repeat
    # only leaves a line.
    #
    # STRIPPED: wrapper, typeface commands, indices inlined, `^{\circ}` to a
    # degree sign; KEPT: command NAMES, `\alpha` -> `alpha`. Dropping all
    # commands gives 90 more matches and lifts the background 3.4 % -> 4.6 %,
    # signal to background 20.1 -> 15.9: noise. Rejected.
    "latex": ["math wrapper", "typeface commands", "indices inlined",
              "^{\\circ} -> °", "then the boundary steps"],
    # What was rejected is printed beside the number; see `NORM_REFUSED`.
}
# Printed beside the number. Otherwise "CER 0.03" will mean anything at all a
# month from now, and the first proposal will be to strip punctuation too.
NORM_REFUSED = ("leading punctuation (removes 139, harms 4: '.850' == "
                "'850'), all punctuation (504 at harm 108: '6—2' == '6,2'), "
                "Cyrillic/Latin lookalikes (lift 2.70 against 3.06 "
                "without it)")


# LaTeX typeface commands change the SHAPE, not the meaning, so they go; the
# lists are named one by one, since `\alpha` IS meaning. Typeface goes WITHOUT
# A TRACE, a spacing command becomes a space: a space for every typeface
# command made `\mathrm{C}` into " C" where prose has `1470—1728°C` tight,
# halving the matches, 414 against 841 over 1935 candidates.
_TYPEFACE = ("mathrm", "mathbf", "mathit", "mathsf", "mathtt", "text",
               "textrm", "textbf", "textit", "boldsymbol", "operatorname",
               "left", "right", "displaystyle", "limits",
               "bf", "rm", "it", "mbox", "hbox")
# Commands that ARE a space in typesetting. Stripping them without a trace
# would glue together words the author had separated.
_SPACE = ("quad", "qquad")
_WRAPPER = re.compile(r"^\s*(?:\\\[|\\\(|\$\$|\$)|(?:\\\]|\\\)|\$\$|\$)\s*$")
_HEAD = re.compile(r"\\(" + "|".join(_TYPEFACE) + r")(?![a-zA-Z])")
_SP = re.compile(r"\\(" + "|".join(_SPACE) + r")(?![a-zA-Z])")
_INDEX = re.compile(r"[_^]\{([^{}]*)\}")


def bare_math(s: str) -> str:
    """Strip wrapper and typeface off a LaTeX fragment, keeping command NAMES.

    A function, not a line inside `normalize`: with no seam the battery has
    nothing to break. Measured at `NORM_STEPS["latex"]`.
    """
    if not s:
        return ""
    s = s.strip()
    # Twice: `\[` on the left and `\]` on the right are two different ends.
    for _ in range(2):
        s = _WRAPPER.sub("", s).strip()
    s = (s.replace("^{\\circ}", "°").replace("^\\circ", "°")
         .replace("\\circ", "°"))
    s = _SP.sub(" ", s)
    s = _HEAD.sub("", s)
    s = _INDEX.sub(r"\1", s)
    s = re.sub(r"[_^]", "", s)
    s = (s.replace("\\%", "%").replace("\\cdot", "·")
         .replace("\\times", "x"))
    # The NAME of a meaningful command survives: `\alpha` -> `alpha`.
    s = re.sub(r"\\([a-zA-Z]+)", r"\1", s)
    return re.sub(r"[{}\\]", "", s)


def normalize(s: str, level: str = NORM) -> str:
    """Bring a string to a form where two spellings of one thing count equal.

    Exactly the steps measured at harm 0, and not one beyond them.
    """
    if level not in NORM_STEPS:
        raise TextError(f"normalisation level {level!r} is not declared; "
                        f"there are {sorted(NORM_STEPS)}")
    if s is None:
        return ""
    if level == "none":
        return s
    if level == "latex":
        s = bare_math(s)
    s = unicodedata.normalize("NFKC", s)
    s = _WS.sub(" ", s).strip()
    s = s.casefold()
    s = "".join("-" if c in _DASHES else c for c in s)
    s = _DEC.sub(".", s)
    return s.rstrip(_TAIL)


# Rejections are PER LEVEL: `NORM_REFUSED` holds those of the CELL
# measurement, which says nothing about matching a formula against prose.
REFUSED = {
    "boundary": NORM_REFUSED,
    "latex": ("strip spaces entirely (signal 1268 against 841, but false "
              "among the hidden 12.8% against 11.7%; refused not on profit "
              "but on the asymmetric cost of error: a false hide takes text "
              "away)"),
}


def norm_note(level: str = NORM) -> dict:
    return {"level": level, "steps": NORM_STEPS[level],
            "not_stripped": REFUSED.get(level, NORM_REFUSED)}


# ----------------------------------------------------------------- distance
#
# Levenshtein, exact, bit-parallel (Myers, 1999): a matrix column in two
# integers, 64 bits at a time. Direct DP is 4 million cells on a pair of
# 2000-character paragraphs, and there are six hundred pages; on 500 pairs of
# 869 characters at 5% corruption, Ukkonen band 30.5 s against bit-parallel
# 1.04 s, same distances on 700 random pairs. A metric too slow to run measures
# nothing.
#
# The budget stands regardless: 100 000 characters against 100 000 is 10^10
# cells, half a minute for one pair. Past it the distance is called an UPPER
# BOUND on its own line -- an estimate passed off as exact would make CER
# unable to fall on exactly the longest blocks.
_BUDGET = 300_000_000     # cells per pair, about a second of counting


def _myers(a, b):
    """Exact distance; mask the width of `a`, one pass over `b`."""
    m = len(a)
    peq = {}
    for i, c in enumerate(a):
        peq[c] = peq.get(c, 0) | (1 << i)
    full = (1 << m) - 1
    vp, vn, score, top = full, 0, m, 1 << (m - 1)
    for c in b:
        eq = peq.get(c, 0)
        xv = eq | vn
        xh = (((eq & vp) + vp) ^ vp) | eq
        hp = vn | (full & ~(xh | vp))
        hn = vp & xh
        if hp & top:
            score += 1
        if hn & top:
            score -= 1
        hp = ((hp << 1) | 1) & full
        hn = (hn << 1) & full
        vp = (hn | (full & ~(xv | hp))) & full
        vn = hp & xv
    return score


def _dist(a, b):
    """(distance, is it exact). The second field is not decoration: see the
    budget above."""
    if a == b:
        return 0, True
    n, m = len(a), len(b)
    if not a or not b:
        return max(n, m), True
    if n * m > _BUDGET:
        return max(n, m), False
    if n > m:
        a, b = b, a          # distance is symmetric; mask the shorter one
    return _myers(a, b), True


# ------------------------------------------------------------------- tables
#
# Structural truth arrives in `meta`, as a list of rows or of addressed cells;
# nothing is GUESSED, and unparsable table keys are a loud error, since
# skipping prints "cells 0", read as "there are no tables".
_CELLS_KEYS = ("cells", "rows")


def _cells_from(obj):
    """{(row, column): text} from a list of rows or a list of addresses."""
    if isinstance(obj, dict):
        for k in _CELLS_KEYS:
            if k in obj:
                return _cells_from(obj[k])
        return None
    if not isinstance(obj, list) or not obj:
        return None
    if all(isinstance(r, list) for r in obj):
        return {(i, j): ("" if c is None else str(c))
                for i, r in enumerate(obj) for j, c in enumerate(r)}
    if all(isinstance(c, dict) for c in obj):
        out = {}
        for c in obj:
            r = c.get("row")
            j = c.get("col", c.get("column"))
            t = c.get("text", "")
            if r is None or j is None:
                return None
            out[(int(r), int(j))] = "" if t is None else str(t)
        return out
    return None


SIDE_KEYS = ("artifact_truth", "artefact truth")


def page_side(page) -> dict:
    """Artifact truth living BESIDE the page, linked by block id.

    `synth` puts the grid in the PAGE's `meta` under the block id as a string
    key; `_truth_grid` looked in the BLOCK's `meta`, which `Block` does not
    have. On a fresh `katalog`, `books synth` printed 13 tables with a grid and
    3982 cells while `text.report` said the book has no structural truth. The
    key is coerced to a string deliberately: json makes keys strings, the id in
    memory is an int, and `side[3]` would miss `side["3"]` silently.
    """
    m = (page.get("meta") or {}) if isinstance(page, dict) else {}
    for k in SIDE_KEYS:
        v = m.get(k)
        if isinstance(v, dict):
            return {str(kk): vv for kk, vv in v.items()}
    return {}


def _truth_grid(b, side=None):
    """Grid of a table's truth, or None -- a table with no structural truth.

    Looked for in the block's `meta` and in the page's artifact truth (`side`):
    markup may carry the grid inside, our bench puts it aside.
    """
    # THE TWO PLACES ARE READ INDEPENDENTLY. Under `if not m and side` the
    # sidecar was read only for a block with empty `meta`: any unrelated key on
    # 523 blocks turned "tables: 2 blocks, 227 cells" into "no structural
    # truth", the tables reclassified as baits, silently.
    m = b.get("meta") or {}
    aside = (side or {}).get(str(b.get("block_id"))) or {}

    def _pick(d):
        if not isinstance(d, dict):
            return None
        for k in ("table", "structure"):
            if isinstance(d.get(k), (dict, list)):
                return d[k]
        return d if any(k in d for k in _CELLS_KEYS) else None

    src, from_side = _pick(m), _pick(aside)
    if src is not None and from_side is not None and src != from_side:
        # Both sides speak and disagree. Taking either silently chooses for
        # the operator which truth to believe.
        raise TextError(
            f"block {b.get('block_id')}: a grid is in the block's meta AND "
            f"beside the page, and they disagree. Which to believe is not "
            f"for the metric to decide.")
    if src is None:
        src = from_side
    if src is None:
        return None
    g = _cells_from(src)
    if g is None:
        raise TextError(
            f"block {b.get('block_id')}: meta holds table keys "
            f"{[k for k in m if k in _CELLS_KEYS or k in ('table', 'structure')]}, "
            f"but no grid reads out of them. Skipping this silently means "
            f"printing 'cells 0' where there are cells.")
    return g


def _truth_text(b, side=None):
    """The artifact's CHARACTERS, lying beside the page, or None.

    The same bridge as `_truth_grid`, for truth the instrument read only as a
    table grid (the cost is in the artifact branch of `measure_pages`). `None`
    means no character truth, so the block is a bait; an empty string is
    declared emptiness, compared as emptiness.
    """
    aside = (side or {}).get(str(b.get("block_id"))) or {}
    if not isinstance(aside, dict):
        return None
    # ONE KEY, `text`. The second name this used to accept, the pre-migration
    # `знаки`, was dead: it is in no tracked file, in no file under
    # `processed/` or `runs/`, and it was never declared in `tools/keymap.json`
    # -- so the rename could not have produced it and nothing writes it. A
    # reader for a key nobody writes is not compatibility, it is a name that
    # outlived its data.
    v = aside.get("text")
    if isinstance(v, str):
        return v
    return None


def _truth_both(b, side=None):
    """Grid AND characters on ONE artifact: refuse aloud. The table branch
    comes first and would drop the characters silently."""
    if _truth_grid(b, side) is not None and _truth_text(b, side) is not None:
        raise TextError(
            f"block {b.get('block_id')}: beside it lie BOTH a table grid "
            f"AND characters. Which truth to count is not for the metric to "
            f"decide: the table branch comes first and would drop the "
            f"characters silently.")


class _TableHTML(HTMLParser):
    """Grid out of an HTML table: tr/td/th, colspan and rowspan.

    A spanning cell occupies all of its addresses, or a row shift under a
    spanning header would be compared against emptiness and fall for the wrong
    reason.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.cells, self.buf = {}, None
        self.r, self.c, self.busy = -1, 0, {}
        self.span = (1, 1)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "tr":
            self._close()
            self.r += 1
            self.c = 0
        elif tag in ("td", "th"):
            self._close()
            if self.r < 0:
                self.r = 0
            try:
                cs = max(1, int(a.get("colspan", 1)))
                rs = max(1, int(a.get("rowspan", 1)))
            except ValueError:
                cs = rs = 1
            self.span = (rs, cs)
            self.buf = []
        elif tag == "br" and self.buf is not None:
            self.buf.append(" ")

    def handle_endtag(self, tag):
        if tag in ("td", "th", "tr", "table"):
            self._close()

    def handle_data(self, d):
        if self.buf is not None:
            self.buf.append(d)

    def _close(self):
        if self.buf is None:
            return
        text = "".join(self.buf)
        self.buf = None
        while self.busy.get((self.r, self.c)):
            self.c += 1
        rs, cs = self.span
        for i in range(rs):
            for j in range(cs):
                self.busy[(self.r + i, self.c + j)] = True
                self.cells[(self.r + i, self.c + j)] = text
        self.c += cs

    def close(self):
        self._close()
        super().close()


def _html_grid(s):
    """Grid out of the model's answer, or None -- no table markup in it."""
    if not s or "<t" not in s.lower():
        return None
    p = _TableHTML()
    try:
        p.feed(s)
        p.close()
    except Exception:
        return None
    return p.cells or None


def _answer_grid(s, kind=None):
    """Grid out of the model's answer, whatever shape it arrived in.

    `kind="otsl"` was once a valid answer for a table while the grid was parsed
    from HTML ONLY. On `bench/slovar` (2 tables, 227 cells), one flawlessly
    read table fed both ways:

        HTML: matched 227 (100%), cell CER 0.0000, given as text 0
        OTSL: matched   0 (0%),   cell CER 1.0000, given as text 2

    PaddleOCR-VL returns OTSL: flawless reading earned a zero and the charge
    "given as prose", our parser's defect billed to the model. Parsing lives in
    `booksmith/otsl.py`, hashed separately, because "why is the number bad"
    needs three answers -- silence, a failed parse, wrong characters.
    """
    if not s:
        return None
    if kind == "otsl":
        return otsl.grid(s) or _html_grid(s)
    return _html_grid(s) or otsl.grid(s)


def _grid_html(g):
    """Grid back into HTML, for the battery: corruption is convenient over a
    grid, and the metric must get exactly what a model would send.

    THE CELL IS ESCAPED. Unescaped, `a<b&c` came back as `a` (`<b&c` read as a
    tag): the corrupted cell was truncated BEFORE the corruption went in, and
    the battery measured a string it never reported. On the chemistry book, 249 blocks of 6812 carry `<` or `&` (text 65,
    latex 77, otsl 107), and 24 of the 5726 cells parsed by `otsl.grid` (`< 3`,
    `<1,0`, `<28 (Al2O3)`, `>60 MgO; 5—18 (Cr2O3)`); an
    earlier zero was counted with a regex carrying the same defect, stopping at
    `<`. None of the 24 was in fact corrupted -- browsers take `<` as a literal
    unless a letter follows -- and bench truth has a genuine zero, 1211 blocks
    with no `<` and no `&`.
    """
    if not g:
        return "<table></table>"
    rows = max(r for r, _ in g) + 1
    cols = max(c for _, c in g) + 1
    out = ["<table>"]
    for r in range(rows):
        out.append("<tr>")
        for c in range(cols):
            out.append("<td>" + _html.escape(g.get((r, c), "")) + "</td>")
        out.append("</tr>")
    out.append("</table>")
    return "".join(out)


def _shape(g):
    if not g:
        return (0, 0)
    return (max(r for r, _ in g) + 1, max(c for _, c in g) + 1)


# ------------------------------------------------------------------- pairing
_ANCHOR_RE = re.compile(r"^p(\d+)-b(\d+)$")


def _anchor_num(v):
    """Block number out of an anchor: a bare int or the label `p0042-b17`.

    The label is mandatory -- `doc/html.anchor_of` writes it and the second
    level replaces by it; numbers only raised `TextError` on real output, so
    anchor pairing worked zero times out of zero. RETURNS (page, block), the
    page NOT discarded: `p0007-b3` on block 0 of page 0 was once paired with
    block 3 of that page at "anchor to nowhere 0". Of 568 anchors from
    detection output only 101 (18%) hit the same truth object -- 42 blocks
    found where truth has 40 -- so 82% would pair the wrong block under "100%
    by anchor".
    """
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return (None, v)
    if isinstance(v, str):
        t = v.strip()
        m = _ANCHOR_RE.match(t)
        if m:
            return (int(m.group(1)), int(m.group(2)))
        try:
            return (None, int(t))
        except ValueError:
            return None
    return None


def _anchor(b):
    """The truth block number the answer declares for itself, or None."""
    for src in (b, b.get("meta") or {}):
        if not isinstance(src, dict):
            continue
        for k in ("anchor", "truth_block_id"):
            v = src.get(k)
            if v is not None:
                n = _anchor_num(v)
                if n is None:
                    raise TextError(
                        f"anchor {v!r} not parsed: neither a number nor a "
                        f"per-page label of the form p0042-b17. It cannot "
                        f"pair, and quietly falling back to geometry would "
                        f"lie about the method")
                return n
    return None


def _box(b):
    v = b.get("box")
    if not v or len(v) != 4:
        return None
    return tuple(float(x) for x in v)


def _match(tb, pb, page_index=None):
    """Pairs (truth index, answer index, how paired) and the leftovers.

    Stages: anchor -> ids agreeing wholesale -> geometry, the anchor verified
    on page number and box exactly as the `number` stage is.
    """
    pairs, dead, off_page, off_box = [], 0, 0, 0
    t_by_id = {}
    for i, b in enumerate(tb):
        t_by_id.setdefault(b.get("block_id"), i)
    used_t, used_p = set(), set()

    anchored = [(j, _anchor(b)) for j, b in enumerate(pb)]
    for j, a in anchored:
        if a is None:
            continue
        pg_, num = a
        if pg_ is not None and page_index is not None and pg_ != page_index:
            # The anchor names ANOTHER page. Pairing it with a block of this
            # one passes off a foreign answer as this one's, "by anchor".
            off_page += 1
            used_p.add(j)
            continue
        i = t_by_id.get(num)
        if i is None or i in used_t:
            dead += 1          # anchor to nowhere: loud, not a quiet miss
            used_p.add(j)
            continue
        x, y = _box(tb[i]), _box(pb[j])
        if x is not None and y is not None and not metrics.matches(x, y):
            # Number agrees, boxes do not: a checked anchor, not faith.
            off_box += 1
            used_p.add(j)
            continue
        used_t.add(i)
        used_p.add(j)
        pairs.append((i, j, "anchor"))

    # Wholesale ids only when there are NO anchors at all: mixing a declared
    # anchor with a guessed id loses what actually paired the block.
    if not any(a is not None for _, a in anchored) and len(tb) == len(pb):
        ids_t = [b.get("block_id") for b in tb]
        ids_p = [b.get("block_id") for b in pb]
        if None not in ids_t and sorted(ids_t) == sorted(ids_p) \
                and len(set(ids_t)) == len(ids_t):
            p_by_id = {b.get("block_id"): j for j, b in enumerate(pb)}
            cand = []
            for i, b in enumerate(tb):
                j = p_by_id[b["block_id"]]
                x, y = _box(b), _box(pb[j])
                # Only a verified id is believed: ids can agree by accident,
                # boxes from another book cannot.
                if x is None or y is None or not metrics.matches(x, y):
                    cand = None
                    break
                cand.append((i, j, "number"))
            if cand:
                return cand, [], [], (dead, off_page, off_box)

    # Greedy by IoU, ties broken by index so two runs give the same pairs.
    cand = []
    for i, b in enumerate(tb):
        if i in used_t:
            continue
        x = _box(b)
        if x is None:
            continue
        for j, p in enumerate(pb):
            if j in used_p:
                continue
            y = _box(p)
            if y is None or not metrics.matches(x, y):
                continue
            cand.append((-metrics.iou(x, y), i, j))
    for _, i, j in sorted(cand):
        if i in used_t or j in used_p:
            continue
        used_t.add(i)
        used_p.add(j)
        pairs.append((i, j, "geometry"))
    lost_t = [i for i in range(len(tb)) if i not in used_t]
    lost_p = [j for j in range(len(pb)) if j not in used_p]
    return pairs, lost_t, lost_p, (dead, off_page, off_box)


# ----------------------------------------------------------------- measuring
def _load(d):
    """Pages of a directory, keyed by page index.

    Ours rather than `metrics._load`, whose error speaks of boxes: a directory
    of foreign jsons yields a plausible number about nothing.
    """
    if not os.path.isdir(d):
        raise TextError(f"no directory {d}")
    out = {}
    for name in sorted(os.listdir(d)):
        if name.endswith(".json") and name not in ("run.json", "manifest.json"):
            with open(os.path.join(d, name), encoding="utf-8") as f:
                p = json.load(f)
            if "blocks" not in p or "index" not in p:
                raise TextError(f"{name}: does not look like a markup page")
            out[int(p["index"])] = p
    if not out:
        raise TextError(f"no pages in {d}")
    return out


def measure(truth_dir: str, pages_dir: str, norm: str = NORM) -> dict:
    """Compare what was read against truth. The numbers are in the result."""
    T, P = _load(truth_dir), _load(pages_dir)
    # Book and raster checks come ready-made from the contour metric. Through
    # getattr deliberately: these are private names of another file, and a
    # rename must produce a loud NOT CHECKED, not an AttributeError.
    def _check(name, *a):
        fn = getattr(metrics, name, None)
        if fn is None:
            return f"{name} NOT CHECKED: no such check in metrics.py"
        return fn(*a)

    note = f"{_check('_same_book', truth_dir, pages_dir)}; " \
           f"{_check('_same_raster', T, P)}"
    res = measure_pages(T, P, norm=norm)
    res["book"] = note
    return res


def measure_pages(T: dict, P: dict, norm: str = NORM) -> dict:
    """The same over pages already loaded: this is what the battery feeds."""
    txt = {"block_count": 0, "truth_chars": 0, "truth_words": 0,
           "char_distance": 0, "word_distance": 0,
           "char_distance_answered": 0,
           "truth_chars_answered": 0,
           "no_answer": 0, "unmatched": 0, "truth_empty": 0,
           "upper_bounded": 0}
    tab = {"block_count": 0, "cell_count": 0, "cells_matched": 0, "cell_chars": 0,
           "cell_distance": 0, "no_answer": 0, "given_as_text": 0,
           "structure_not_parsed": 0, "grid_shape_differs": 0,
           "unmatched": 0}
    # An artifact WITH CHARACTER TRUTH has its own scale, apart from baits: a
    # formula or a caption MUST be read, and what was read is compared.
    art = {"block_count": 0, "truth_chars": 0, "char_distance": 0,
           "truth_chars_answered": 0,
           "char_distance_answered": 0,
           "no_answer": 0, "unmatched": 0,
           # Truth is an EMPTY STRING and the model wrote something:
           # invisible to CER (nothing to divide by), and once a bait
           # counted as READ.
           "invented_on_empty_truth": 0}
    bait = {"artifacts": 0, "read": 0, "stayed_silent": 0,
            "unmatched": 0}
    mt = {"truth_blocks": 0, "by_anchor": 0, "by_number": 0, "by_geometry": 0,
          "unmatched_truth": 0, "extra_in_answer": 0,
          # THREE DIFFERENT ANCHOR FAILURES, silent about all three once
          # merged: no such block number / another page / boxes disagree. The
          # last two went uncounted while anchors were trusted.
          "anchor_to_nowhere": 0, "anchor_wrong_page": 0,
          "anchor_box_mismatch": 0, "answer_without_box": 0}
    pg = {"truth": len(T), "answer": len(P), "no_answer": 0, "spurious": 0}
    unmarked = 0          # truth not annotated -- NOT a zero of reading
    unmarked_answered = 0
    kind_bad = 0
    per_block = []

    pg["spurious"] = len(set(P) - set(T))
    for i in sorted(T):
        t = T[i]
        p = P.get(i)
        tb = t["blocks"]
        side = page_side(t)
        mt["truth_blocks"] += len(tb)
        if p is None:
            # The page is absent from the answer. Its blocks were not "read
            # to zero", they were never paired -- its own report line.
            pg["no_answer"] += 1
            pairs, lost_t, lost_p, dead = [], list(range(len(tb))), [], (0, 0, 0)
            pb = []
        else:
            pb = p["blocks"]
            pairs, lost_t, lost_p, dead = _match(tb, pb, page_index=i)
        mt["anchor_to_nowhere"] += dead[0]
        mt["anchor_wrong_page"] += dead[1]
        mt["anchor_box_mismatch"] += dead[2]
        mt["extra_in_answer"] += len(lost_p)
        mt["answer_without_box"] += sum(1 for b in pb if _box(b) is None)
        for _, _, how in pairs:
            mt["by_" + how] += 1

        got = {i_: (j_, how) for i_, j_, how in pairs}
        for i_, b in enumerate(tb):
            j_, how = got.get(i_, (None, None))
            ans = pb[j_] if j_ is not None else None
            rec = {"page": i, "block_id": b.get("block_id"),
                   "label": b.get("label"), "matched_by": how or "no pair"}
            _truth_both(b, side)          # both truths at once: refuse aloud
            grid = _truth_grid(b, side)
            content = b.get("content")
            role = policy.role(b["label"])

            if grid is not None:                       # ------------ table
                tab["block_count"] += 1
                rec["bucket"] = "table"
                cells = {k: normalize(v, norm) for k, v in grid.items()}
                chars = sum(len(v) for v in cells.values())
                tab["cell_count"] += len(cells)
                tab["cell_chars"] += chars
                mg = None
                if ans is None:
                    tab["unmatched"] += 1
                    mt["unmatched_truth"] += 1
                else:
                    mg = _answer_grid(ans.get("content"),
                                      ans.get("kind"))
                    if mg is None:
                        c = ans.get("content")
                        if c is None or not c.strip():
                            tab["no_answer"] += 1
                        else:
                            # A table given as prose: the cell addresses are
                            # gone, the characters remain. NOT the same as
                            # silence, and dearer -- structure is not
                            # recoverable.
                            tab["given_as_text"] += 1
                if mg is None:
                    tab["cell_distance"] += chars
                    rec["cells_matched"] = 0
                else:
                    mgn = {k: normalize(v, norm) for k, v in mg.items()}
                    if _shape(mgn) != _shape(cells):
                        tab["grid_shape_differs"] += 1
                    hit = d_sum = 0
                    for k, v in cells.items():
                        got_v = mgn.get(k, "")
                        d, exact = _dist(v, got_v)
                        if not exact:
                            txt["upper_bounded"] += 1
                        d_sum += d
                        hit += (v == got_v)
                    tab["cells_matched"] += hit
                    tab["cell_distance"] += d_sum
                    rec["cells_matched"] = hit
                    rec["cell_count"] = len(cells)
                    if ans.get("kind") not in ("html", "otsl"):
                        kind_bad += 1
                per_block.append(rec)
                continue

            if isinstance(content, str) and content.strip():   # ------- text
                txt["block_count"] += 1
                rec["bucket"] = "text"
                ref = normalize(content, norm)
                rw = ref.split()
                txt["truth_chars"] += len(ref)
                txt["truth_words"] += len(rw)
                if ans is None:
                    txt["unmatched"] += 1
                    mt["unmatched_truth"] += 1
                    txt["char_distance"] += len(ref)
                    txt["word_distance"] += len(rw)
                    rec["CER"] = rec["WER"] = None
                    per_block.append(rec)
                    continue
                out = ans.get("content")
                if out is None or not out.strip():
                    txt["no_answer"] += 1
                    txt["char_distance"] += len(ref)
                    txt["word_distance"] += len(rw)
                    rec["CER"] = rec["WER"] = None
                    per_block.append(rec)
                    continue
                hyp = normalize(out, norm)
                hw = hyp.split()
                dc, exact = _dist(ref, hyp)
                if not exact:
                    txt["upper_bounded"] += 1
                dw, _ = _dist(rw, hw)
                txt["char_distance"] += dc
                txt["word_distance"] += dw
                txt["char_distance_answered"] += dc
                txt["truth_chars_answered"] += len(ref)
                rec["CER"] = dc / len(ref) if ref else None
                rec["WER"] = dw / len(rw) if rw else None
                rec["chars"] = len(ref)
                if ans.get("kind") != "text":
                    kind_bad += 1
                per_block.append(rec)
                continue

            if isinstance(content, str):        # ---- truth is empty string
                txt["truth_empty"] += 1
                rec["bucket"] = "truth_empty"
                per_block.append(rec)
                continue

            if role == "artifact":
                aside_text = _truth_text(b, side)
                if aside_text is None:                    # ----------- bait
                    # No character truth: nothing to read, so any text in the
                    # answer is invention. That is what a bait is.
                    bait["artifacts"] += 1
                    rec["bucket"] = "bait"
                    if ans is None:
                        bait["unmatched"] += 1
                        mt["unmatched_truth"] += 1
                    else:
                        c = ans.get("content")
                        if c is not None and c.strip():
                            bait["read"] += 1
                            rec["chars_read"] = len(c)
                        else:
                            bait["stayed_silent"] += 1
                    per_block.append(rec)
                    continue
                # ---- an artifact WITH TRUTH: formula, caption, diagram label.
                # THE PRICE IS MEASURED: this branch used to be a bait, and on
                # `bench/matematika` 26 formulas answered BYTE-FOR-BYTE from
                # truth gave "26 artifacts, READ 26 (100%), silent 0".
                art["block_count"] += 1
                rec["bucket"] = "artifact_with_truth"
                ref = normalize(aside_text, norm)
                art["truth_chars"] += len(ref)
                if ans is None:
                    art["unmatched"] += 1
                    mt["unmatched_truth"] += 1
                    art["char_distance"] += len(ref)
                    rec["CER"] = None
                    per_block.append(rec)
                    continue
                out = ans.get("content")
                if out is None or not out.strip():
                    art["no_answer"] += 1
                    art["char_distance"] += len(ref)
                    rec["CER"] = None
                    per_block.append(rec)
                    continue
                if not ref and out.strip():
                    art["invented_on_empty_truth"] += 1
                dc, exact = _dist(ref, normalize(out, norm))
                if not exact:
                    txt["upper_bounded"] += 1
                art["char_distance"] += dc
                art["truth_chars_answered"] += len(ref)
                art["char_distance_answered"] += dc
                rec["CER"] = dc / len(ref) if ref else None
                rec["chars"] = len(ref)
                per_block.append(rec)
                continue

            unmarked += 1
            rec["bucket"] = "truth_unmarked"
            if ans is None:
                mt["unmatched_truth"] += 1
            elif (ans.get("content") or "").strip():
                # The model read something and there is nothing to check it
                # against. Neither CER nor baits: both would be invention.
                unmarked_answered += 1
            per_block.append(rec)

    def frac(a, b):
        return (a / b) if b else None

    def table_ratios(tab):
        """Table shares -- or None when there is nothing to judge by.

        Zero answered blocks means "nothing to compare", not "zero per cent
        matched": dividing by all cells printed "matched 0 (0%), cell CER
        1.0000" where the model never answered, and floored the battery, whose
        probe "a cell corrupted in truth" cannot lower a CER already 1.
        """
        answered = tab["block_count"] - tab["no_answer"] - tab["unmatched"]
        if answered <= 0:
            return {"share_cells_matched": None, "cer_cells": None,
                    "answered_blocks": 0}
        return {"share_cells_matched": frac(tab["cells_matched"], tab["cell_count"]),
                "cer_cells": frac(tab["cell_distance"], tab["cell_chars"]),
                "answered_blocks": answered}

    matched = mt["by_anchor"] + mt["by_number"] + mt["by_geometry"]
    res = {
        "normalization": norm_note(norm),
        "geometry_gate": {"two_way_coverage": metrics.COVER_MATCH,
                             "tolerance_px": metrics.TOL_PX},
        "pages": pg,
        "matching": dict(mt, matched_total=matched,
                              share=frac(matched, mt["truth_blocks"])),
        "text": dict(txt,
                      CER=frac(txt["char_distance"], txt["truth_chars"]),
                      WER=frac(txt["word_distance"], txt["truth_words"]),
                      **{"cer_answered": frac(
                          txt["char_distance_answered"],
                          txt["truth_chars_answered"]),
                         "share_no_answer": frac(txt["no_answer"],
                                                 txt["block_count"])}),
        # The denominator is cells IN ANSWERED blocks, not all cells; see
        # `table_ratios` for what dividing by all of them cost.
        "tables": dict(tab, **table_ratios(tab)),
        "artifacts_with_truth": dict(
            art,
            CER=frac(art["char_distance"], art["truth_chars"]),
            **{"cer_answered": frac(art["char_distance_answered"],
                                         art["truth_chars_answered"])}),
        "baits": dict(bait, share=frac(bait["read"], bait["artifacts"])),
        "truth_unmarked": unmarked,
        "answers_on_unmarked": unmarked_answered,
        "answer_kind_wrong": kind_bad,
        "per_block": per_block,
    }
    return res


# ------------------------------------------------------------------ report
def report(res: dict, log=print) -> None:
    if res.get("book"):
        log(res["book"])
    n = res["normalization"]
    log(f"normalisation: {n['level']} — "
        + ", ".join(n["steps"] or ["none"]))
    log(f"  NOT stripped: {n['not_stripped']}")
    p, s = res["pages"], res["matching"]
    log(f"pages: truth {p['truth']}, answer {p['answer']}, "
        f"no answer {p['no_answer']}, spurious {p['spurious']}")
    d = s["share"]
    # The share paired is printed FIRST and always: a CER over two blocks of
    # forty is a figure about pairing, not about reading.
    log(f"paired {s['matched_total']}/{s['truth_blocks']}"
        f" ({'—' if d is None else f'{d*100:.0f}%'}): "
        f"by anchor {s['by_anchor']}, by number {s['by_number']}, "
        f"by geometry {s['by_geometry']}")
    log(f"  NOT paired: truth {s['unmatched_truth']}, "
        f"extra in the answer {s['extra_in_answer']}, "
        f"anchor to nowhere {s['anchor_to_nowhere']}, to another page "
        f"{s['anchor_wrong_page']}, off the box "
        f"{s['anchor_box_mismatch']}, "
        f"no box in the answer {s['answer_without_box']}")
    t = res["text"]
    if not t["block_count"]:
        log("text: NOT MARKED in this truth — nothing to compare "
            "(this is not zero reading)")
    else:
        cer, wer = t["CER"], t["WER"]
        ans = t["cer_answered"]
        log(f"text: blocks {t['block_count']}, "
            f"characters {t['truth_chars']}, "
            f"words {t['truth_words']}; "
            f"CER {'—' if cer is None else f'{cer:.4f}'}, "
            f"WER {'—' if wer is None else f'{wer:.4f}'}")
        log(f"  CER over answered "
            f"{'—' if ans is None else f'{ans:.4f}'} over "
            f"{t['truth_chars_answered']} characters; "
            f"no answer {t['no_answer']} "
            f"({(t['share_no_answer'] or 0)*100:.0f}%), "
            f"not paired {t['unmatched']}, "
            f"truth empty {t['truth_empty']}")
        if t["upper_bounded"]:
            log(f"  distance UPPER BOUNDED on {t['upper_bounded']} blocks: "
                f"strings longer than the budget of {_BUDGET} cells")
    b = res["tables"]
    if not b["block_count"]:
        log("tables: this book has no structural truth — nothing to "
            "compare (this is not zero by cells)")
    elif not b.get("answered_blocks"):
        # A third outcome, not the same as the first: truth EXISTS and the
        # answer does not.
        log(f"tables: blocks {b['block_count']}, cells {b['cell_count']}, "
            f"but THERE IS NO ANSWER TO A SINGLE ONE — nothing to compare, "
            f"and this is NOT 'matched 0%'")
        log(f"  no answer {b['no_answer']}, given as text "
            f"{b['given_as_text']}, not paired {b['unmatched']}")
    else:
        dc, cc = b["share_cells_matched"], b["cer_cells"]
        log(f"tables: blocks {b['block_count']} (answered "
            f"{b['answered_blocks']}), cells {b['cell_count']}, "
            f"matched by address {b['cells_matched']} "
            f"({'—' if dc is None else f'{dc*100:.0f}%'}), "
            f"cell CER {'—' if cc is None else f'{cc:.4f}'}")
        log(f"  no answer {b['no_answer']}, given as text "
            f"{b['given_as_text']}, grid shape differs "
            f"{b['grid_shape_differs']}, not paired {b['unmatched']}")
    ar = res["artifacts_with_truth"]
    if ar["block_count"]:
        c, ca = ar["CER"], ar["cer_answered"]
        answered = ar["block_count"] - ar["no_answer"] - ar["unmatched"]
        if not answered:
            # As for tables: silence on ALL of them once printed "CER
            # 1.0000", computed from nothing and read as measured.
            log(f"artifacts WITH TRUTH (formulas, captions): blocks "
                f"{ar['block_count']}, characters {ar['truth_chars']}, but "
                f"THERE IS NO ANSWER TO A SINGLE ONE — nothing to compare, "
                f"and this is NOT 'CER 1.0'")
        else:
            log(f"artifacts WITH TRUTH (formulas, captions): blocks "
                f"{ar['block_count']} (answered {answered}), characters "
                f"{ar['truth_chars']}, CER "
                f"{'—' if c is None else f'{c:.4f}'}; over answered "
                f"{'—' if ca is None else f'{ca:.4f}'}")
        log(f"  no answer {ar['no_answer']}, not paired "
            f"{ar['unmatched']}, invented on empty truth "
            f"{ar['invented_on_empty_truth']}")
        log(f"  these are NOT baits: they DO have character truth, and "
            f"reading them is right work, not invention")
    a = res["baits"]
    if not a["artifacts"]:
        log("baits: no artifacts without text in truth — nothing to "
            "check invention on")
    else:
        log(f"baits: artifacts {a['artifacts']}, READ "
            f"{a['read']} ({(a['share'] or 0)*100:.0f}%), "
            f"stayed silent {a['stayed_silent']}, "
            f"not paired {a['unmatched']}")
    log(f"truth NOT MARKED: blocks {res['truth_unmarked']}, of them with "
        f"a model answer {res['answers_on_unmarked']} — there is nothing to "
        f"check them against, this is NOT zero reading; wrong answer kind: "
        f"{res['answer_kind_wrong']}")
    # Only blocks WITH AN ERROR: "worst block: CER 0.000" admits there is
    # nothing to print. TEXT AND ARTIFACTS COUNT APART, paid for twice in one
    # day: `scored` took both and divided by text blocks alone, printing "CER 0
    # on all 130 scored out of 104" on `matematika`, where the guard "NOTHING
    # to compare" then never fired. And an artifact record has no `WER`, which
    # this line printed: one wrong letter in one formula brought `books text`
    # down with `KeyError: 'WER'` -- money spent, answers written, no report.
    txt_rec = [r for r in res["per_block"] if r.get("bucket") == "text"]
    art_rec = [r for r in res["per_block"]
               if r.get("bucket") == "artifact_with_truth"]
    for name, rec, total in (("text", txt_rec, res["text"]["block_count"]),
                             ("artifact", art_rec, ar["block_count"])):
        if not total:
            continue
        scored = [r for r in rec if r.get("CER") is not None]
        err = [r for r in scored if r["CER"]]
        if not scored:
            log(f"  there was NOTHING to compare: not one {name} block "
                f"with a computed CER out of {total} — this is NOT "
                f"'CER 0 on all'")
        elif not err:
            log(f"  no {name} blocks with an error: CER 0 on all "
                f"{len(scored)} computed of {total}")
        for r in sorted(err, key=lambda r: -r["CER"])[:3]:
            # `WER` exists for text only. Print what was computed, not what
            # was expected to be there.
            wer = (f", WER {r['WER']:.3f}" if r.get("WER") is not None else "")
            log(f"  worst {name} block p.{r['page']} b.{r['block_id']} "
                f"({r['label']}, {r['matched_by']}): CER {r['CER']:.3f}{wer}, "
                f"characters {r.get('chars', 0)}")


# ---------------------------------------------------------------- mutations
#
# A number that cannot fall measures nothing, and corruption is THREE-SIDED:
# the answer, the TRUTH (a metric blind to it is always "right"), and OUR
# pairing. Each probe corrupts EXACTLY ONE thing: two at once cannot tell a
# live figure from one stuck to its neighbour -- nine runs in a row reported
# "fell" in the contour metric with the threshold dead.
def _pages(P):
    return sorted(P)


def _blocks(P):
    for i in _pages(P):
        for j, b in enumerate(P[i]["blocks"]):
            yield i, j, b


def _pick_text(P, T, want=None):
    """The first answer block whose truth holds non-empty text.

    `want` narrows it: "one digit replaced" on a block with no digits printed
    "no data" -- an honest guard, but no probe.
    """
    for i in _pages(T):
        if i not in P:
            continue
        ids = {b.get("block_id"): b for b in T[i]["blocks"]}
        side = page_side(T[i])
        for j, b in enumerate(P[i]["blocks"]):
            t = ids.get(b.get("block_id"))
            c = b.get("content")
            if t is None or _truth_grid(t, side) is not None:
                continue
            if isinstance(t.get("content"), str) and t["content"].strip() \
                    and isinstance(c, str) and c.strip() \
                    and (want is None or want(c)):
                return i, j
    return None, None


def _pick_table(P, T):
    for i in _pages(T):
        if i not in P:
            continue
        ids = {b.get("block_id"): b for b in T[i]["blocks"]}
        side = page_side(T[i])
        for j, b in enumerate(P[i]["blocks"]):
            t = ids.get(b.get("block_id"))
            # `_answer_grid`, not `_html_grid`: a real model answers in OTSL,
            # where this probe and four neighbours would say "no data" while
            # the battery still reported zero uncaught.
            if t is not None and _truth_grid(t, side) is not None \
                    and _answer_grid(b.get("content"), b.get("kind")):
                return i, j
    return None, None


def _pick_bait(P, T):
    for i in _pages(T):
        if i not in P:
            continue
        ids = {b.get("block_id"): b for b in T[i]["blocks"]}
        side = page_side(T[i])
        for j, b in enumerate(P[i]["blocks"]):
            t = ids.get(b.get("block_id"))
            if t is None or t.get("content") is not None:
                continue
            # NO GRID AND NO CHARACTERS. Without the character check the
            # probe corrupted a FORMULA with known truth, the bait share held,
            # and the battery reddened against a healthy metric.
            if (_truth_grid(t, side) is None and _truth_text(t, side) is None
                    and policy.role(t["label"]) == "artifact"):
                return i, j
    return None, None


def _edit(P, i, j, fn):
    Q = copy.deepcopy(P)
    b = Q[i]["blocks"][j]
    b["content"] = fn(b.get("content"))
    return Q


def _drop10(s):
    """Every tenth character dropped."""
    return "".join(c for k, c in enumerate(s) if (k + 1) % 10)


def _swap_lines(s):
    ls = s.split("\n")
    if len(ls) < 2:
        return None
    ls[0], ls[1] = ls[1], ls[0]
    return "\n".join(ls)


def _swap_words(s):
    w = s.split()
    if len(w) < 2:
        return None
    w[0], w[1] = w[1], w[0]
    return " ".join(w)


_HYPH = re.compile(r"(\w)-\s*\n\s*(\w)")


def _glue(s):
    """Glue hyphenation where there was none. Exactly what a model trained to
    glue does, and the metric must see it."""
    out = _HYPH.sub(r"\1\2", s)
    return None if out == s else out


def _grid_otsl(g):
    """Grid back into OTSL. The pair to `_grid_html`, needed for the same."""
    if not g:
        return "<nl>"
    rows, cols = _shape(g)
    return "".join("".join("<fcel>" + g.get((r, c), "") for c in range(cols))
                   + "<nl>" for r in range(rows))


def _regrid(src, g):
    """The corrupted grid back IN THE SHAPE the answer arrived in.

    Otherwise a probe changes content and format at once. On an answer wholly
    in OTSL, five table probes printed "no data" and the battery still reported
    0 uncaught.
    """
    return _grid_otsl(g) if otsl.looks_like(src) else _grid_html(g)


def _shift_rows(html):
    """A ROW SHIFT IN A TABLE: labels stay, data rolls one row down. The same
    cells, every value attributed to the wrong row."""
    g = _answer_grid(html)
    if not g:
        return None
    rows, cols = _shape(g)
    if rows < 2 or cols < 2:
        return None
    out = {}
    for (r, c), v in g.items():
        out[(r, c) if c == 0 else ((r + 1) % rows, c)] = v
    return _regrid(html, out)


def _detable(html):
    """Table given as plain text: markup gone, characters intact."""
    g = _answer_grid(html)
    if not g:
        return None
    rows, cols = _shape(g)
    return " ".join(g.get((r, c), "") for r in range(rows) for c in range(cols))


def _blank_cell(html):
    g = _answer_grid(html)
    if not g:
        return None
    for k in sorted(g):
        if g[k].strip():
            g[k] = ""
            return _regrid(html, g)
    return None


def _digit(s):
    """Replace one digit. Small and meaningful: if it does not show, then
    normalisation ate more than it declares."""
    for k, c in enumerate(s):
        if c.isdigit():
            return s[:k] + ("8" if c != "8" else "3") + s[k + 1:]
    return None


def _spelling(s):
    """Spelling variance the boundary MUST remove: case, dash kind, character
    width (NFKC), trailing full stop. The figure must not move."""
    out = s.upper().replace("-", "—") + "."
    out = out.replace("A", "Ａ")
    return out if out != s else None


def _shift_boxes(P, frac=0.9):
    Q = copy.deepcopy(P)
    for _, _, b in _blocks(Q):
        x = _box(b)
        if x is None:
            continue
        d = frac * max(4.0, min(x[2] - x[0], x[3] - x[1]))
        b["box"] = [x[0] + d, x[1] + d, x[2] + d, x[3] + d]
    return Q


def _anchor_all(P):
    Q = copy.deepcopy(P)
    for _, _, b in _blocks(Q):
        b.setdefault("meta", {})["anchor"] = b.get("block_id")
    return Q


def _anchor_all_paged(P, shift=0):
    """Anchors as the PER-PAGE label `p0042-b17` that `doc/html` writes: a bare
    number carries no page, so the "another page" gate cannot fire on it.
    `shift` names the neighbouring page with the block number right."""
    Q = copy.deepcopy(P)
    for i, _, b in _blocks(Q):
        b.setdefault("meta", {})["anchor"] = f"p{i + shift:04d}-b{b.get('block_id')}"
    return Q


def _shuffle_pages(P):
    """The answer rolled one page along: comparison goes by page index."""
    ks = _pages(P)
    if len(ks) < 2:
        return None
    return {k: {**copy.deepcopy(P[ks[(n + 1) % len(ks)]]), "index": k}
            for n, k in enumerate(ks)}


def _corrupt_truth(T, fn):
    """Corrupting THE TRUTH ITSELF. A metric blind to truth measures one of
    its inputs -- and will always be right."""
    Q = copy.deepcopy(T)
    for i, _, b in _blocks(Q):
        c = b.get("content")
        if isinstance(c, str) and c.strip():
            out = fn(c)
            if out is not None and out != c:
                b["content"] = out
                return Q, True
    return Q, False


def _corrupt_truth_cell(T):
    """Corrupt one cell OF THE TRUTH. The metric must fall here too.

    The grid lives BESIDE the page, keyed by block id as a string: `Block` has
    no `meta`. The earlier edition edited the block's `meta`, corrupted
    nothing, and credited itself for an experiment never run.
    """
    Q = copy.deepcopy(T)
    for i, _, b in _blocks(Q):
        side = page_side(Q[i])
        if _truth_grid(b, side) is None:
            continue
        holders = []
        m = b.get("meta") or {}
        if m:
            holders.append(m)
        raw = ((Q[i].get("meta") or {}).get("artifact_truth") or {})
        for key in (str(b.get("block_id")), b.get("block_id")):
            if isinstance(raw.get(key), dict):
                holders.append(raw[key])
                break
        for h in holders:
            src = h
            for key in ("table", "structure"):
                if isinstance(h.get(key), dict):
                    src = h[key]
                    break
            cells = next((src[k] for k in _CELLS_KEYS if k in src), None)
            if isinstance(cells, list) and cells and isinstance(cells[0], list):
                for row in cells:
                    for k, v in enumerate(row):
                        if isinstance(v, str) and v.strip():
                            row[k] = v + "X"
                            return Q, True
    return Q, False

def _map_all(P, fn):
    Q = copy.deepcopy(P)
    for _, _, b in _blocks(Q):
        b["content"] = fn(b.get("content"))
    return Q


def _drop_block(P):
    for i in _pages(P):
        if len(P[i]["blocks"]) > 1:
            Q = copy.deepcopy(P)
            Q[i]["blocks"].pop(0)
            return Q
    return None


def _add_block(P):
    """A spurious answer block, boxed over an existing one so that it clears
    the gate and still stays spurious.

    THE COPY'S ANCHOR IS STRIPPED: with it, the extra block landed in "anchor
    to nowhere" instead of "spurious in answer" and printed NOT CAUGHT.
    """
    i = _pages(P)[0]
    Q = copy.deepcopy(P)
    b = copy.deepcopy(Q[i]["blocks"][0])
    b["block_id"] = 10_000
    b.pop("meta", None)
    Q[i]["blocks"].append(b)
    return Q


def _dead_anchor(P):
    i = _pages(P)[0]
    Q = copy.deepcopy(P)
    Q[i]["blocks"][0].setdefault("meta", {})["anchor"] = 99_999
    return Q


def mutations(truth_dir: str, pages_dir: str, log=print) -> int:
    """Run the battery. Returns uncaught corruptions (0 -- the metric lives)."""
    T, P = _load(truth_dir), _load(pages_dir)
    base = measure_pages(T, P)
    b_cer = base["text"]["CER"]
    b_wer = base["text"]["WER"]
    b_none = base["text"]["share_no_answer"]
    b_cell = base["tables"]["share_cells_matched"]
    b_cellcer = base["tables"]["cer_cells"]
    b_bait = base["baits"]["share"]
    b_match = base["matching"]["share"]
    b_lost = base["matching"]["unmatched_truth"]
    b_extra = base["matching"]["extra_in_answer"]
    b_dead = base["matching"]["anchor_to_nowhere"]
    b_offbox = base["matching"]["anchor_box_mismatch"]
    b_offpage = base["matching"]["anchor_wrong_page"]
    b_flat = base["tables"]["given_as_text"]

    def s(x, f="{:.4f}"):
        return "—" if x is None else f.format(x)

    log(f"baseline: paired {s(b_match, '{:.2f}')}, CER {s(b_cer)}, "
        f"WER {s(b_wer)}, no answer {s(b_none, '{:.2f}')}, "
        f"cells matched {s(b_cell, '{:.2f}')}, cell CER {s(b_cellcer)}, "
        f"baits {s(b_bait, '{:.2f}')}, "
        f"not paired {b_lost}, extra {b_extra}")

    ti, tj = _pick_text(P, T)
    di, dj = _pick_text(P, T, want=lambda c: any(x.isdigit() for x in c))
    bi, bj = _pick_table(P, T)
    ai, aj = _pick_bait(P, T)

    def M(pp=None, tt=None):
        return measure_pages(tt or T, pp or P)

    def cer(pp=None, tt=None):
        return M(pp, tt)["text"]["CER"]

    def one(fn):
        """Corrupt ONE text block of the answer; None -- nothing to corrupt."""
        if ti is None:
            return None
        old = P[ti]["blocks"][tj].get("content")
        new = fn(old)
        if new is None or new == old:
            return None
        return _edit(P, ti, tj, lambda _: new)

    def one_tab(fn):
        if bi is None:
            return None
        old = P[bi]["blocks"][bj].get("content")
        new = fn(old)
        if new is None or new == old:
            return None
        return _edit(P, bi, bj, lambda _: new)

    def grew(now, was):
        return None if (now is None or was is None) else now > was

    def fell(now, was):
        return None if (now is None or was is None) else now < was

    def cer_up(mm):
        return None if mm is None else grew(cer(mm), b_cer)

    probes = []

    # --- corrupting the model ANSWER: characters
    probes.append(("every tenth character dropped", "CER grew",
                   lambda: cer_up(one(_drop10))))
    probes.append(("two lines swapped inside the block", "CER grew",
                   lambda: cer_up(one(_swap_lines))))
    probes.append(("two words swapped", "WER grew",
                   lambda: (lambda mm: None if mm is None
                            else grew(M(mm)["text"]["WER"], b_wer))(
                       one(_swap_words))))
    probes.append(("hyphenation glued where there was none", "CER grew",
                   lambda: cer_up(one(_glue))))

    def digit():
        """Small and meaningful: if it does not show, normalisation ate more
        than the boundary declares."""
        if di is None:
            return None
        new = _digit(P[di]["blocks"][dj]["content"])
        if new is None:
            return None
        return cer_up(_edit(P, di, dj, lambda _: new))

    probes.append(("one digit replaced", "CER grew", digit))
    probes.append(("an empty answer on a non-empty block", "more no-answer",
                   lambda: (lambda mm: None if mm is None else
                            grew(M(mm)["text"]["share_no_answer"], b_none))(
                       one(lambda s_: ""))))
    probes.append(("an empty answer on a non-empty block", "CER grew",
                   lambda: cer_up(one(lambda s_: ""))))
    probes.append(("every answer dropped",
                   "CER exactly 1.0 and no answer 1.0",
                   lambda: (lambda r: r["text"]["CER"] == 1.0
                            and r["text"]["share_no_answer"] == 1.0)(
                       M(_map_all(P, lambda c: None)))))

    # A NEIGHBOUR's answer substituted whole. Caught only by comparing against
    # THIS block's truth: a metric that scores "looks like text" misses it.
    def neighbour():
        if ti is None:
            return None
        src = None
        for i, j, b in _blocks(P):
            c = b.get("content")
            if isinstance(c, str) and c.strip() and (i, j) != (ti, tj):
                src = c
                break
        if src is None:
            return None
        return cer_up(_edit(P, ti, tj, lambda _: src))

    probes.append(("the NEIGHBOUR's answer whole", "CER grew", neighbour))

    # --- corrupting the ANSWER: table
    probes.append(("A ROW SHIFT IN A TABLE (the same bag of cells)",
                   "fewer matched cells",
                   lambda: (lambda mm: None if mm is None else
                            fell(M(mm)["tables"]["share_cells_matched"],
                                 b_cell))(one_tab(_shift_rows))))
    probes.append(("one cell emptied", "fewer matched cells",
                   lambda: (lambda mm: None if mm is None else
                            fell(M(mm)["tables"]["share_cells_matched"],
                                 b_cell))(one_tab(_blank_cell))))
    probes.append(("the table given as plain text", "more given as text",
                   lambda: (lambda mm: None if mm is None else
                            grew(M(mm)["tables"]["given_as_text"], b_flat))(
                       one_tab(_detable))))
    probes.append(("the table given as plain text", "cell CER grew",
                   lambda: (lambda mm: None if mm is None else
                            grew(M(mm)["tables"]["cer_cells"], b_cellcer))(
                       one_tab(_detable))))

    # --- corrupting the ANSWER: bait
    def bait():
        if ai is None:
            return None
        mm = _edit(P, ai, aj,
                   lambda _: "Fig. 4. Diagram of the setup, 12 captions")
        return grew(M(mm)["baits"]["share"], b_bait)

    probes.append(("text added to an artifact (bait)", "more baits",
                   bait))

    # --- corrupting OUR OWN PAIRING: it is an input too
    # ALWAYS APPLICABLE now that the anchor is verified against the box:
    # geometry decides on all three stages. An applicability guard stood here,
    # true only BEFORE that gate; on `bench/slovar` (523 blocks, all anchored)
    # it fires while the share falls 1.0000 -> 0.0038 and "anchor off box"
    # rises 0 -> 521. Today's benches pair by number, so dropping it moves no
    # number; it was dangerous for the output of `books read`.
    def shifted():
        return fell(M(_shift_boxes(P))["matching"]["share"], b_match)

    probes.append(("answer boxes shifted by 0.9 of their size",
                   "fewer paired (where pairing was not by anchor)",
                   shifted))
    def dropped():
        mm = _drop_block(P)
        return None if mm is None else grew(
            M(mm)["matching"]["unmatched_truth"], b_lost)

    probes.append(("a block dropped from the answer", "more not paired",
                   dropped))
    probes.append(("an extra block in the answer", "more extra",
                   lambda: grew(M(_add_block(P))["matching"]
                                ["extra_in_answer"], b_extra)))
    probes.append(("the anchor points nowhere", "more anchors to nowhere",
                   lambda: grew(M(_dead_anchor(P))["matching"]
                                ["anchor_to_nowhere"], b_dead)))
    probes.append(("the answer shifted by one page", "CER grew",
                   lambda: (lambda mm: None if mm is None else cer_up(mm))(
                       _shuffle_pages(P))))
    # GUARD OVER THE "anchor off box" GATE: an anchor is verified, not trusted,
    # so a box shift must break pairing EVEN WHERE ALL WAS PAIRED BY ANCHOR.
    # The opposite contract (`== b_match`) predates the gate; after it the
    # battery printed 1 uncaught on all six benches. Nothing else covers that
    # counter. NOT ALWAYS APPLICABLE: the anchored input before the shift is
    # compared against itself after, so the shift is the only difference.
    def anchor_gate():
        A = _anchor_all(P)
        was = M(A)["matching"]
        # Nothing to break: NOT ONE block paired by anchor, as when boxes miss
        # truth even unshifted. The first edition demanded A FALL IN SHARE,
        # already zero there: 0.0 -> 0.0 with the counter 0 -> 523, red against
        # a healthy instrument.
        if not was["by_anchor"]:
            return None
        # The corruption did not land: 0.9 of the shorter side sinks into the
        # `metrics.TOL_PX` = 6 px tolerance. Asked OF THE INPUT, or "did not
        # land" and "gate gone" answer alike and the probe cannot fail.
        S = _shift_boxes(A)
        if not any(x is not None and y is not None
                   and not metrics.matches(x, y)
                   for (_, _, a), (_, _, s) in zip(_blocks(A), _blocks(S))
                   for x, y in ((_box(a), _box(s)),)):
            return None
        return grew(M(S)["matching"]["anchor_box_mismatch"],
                    was["anchor_box_mismatch"])

    probes.append(("with anchors, boxes shifted by 0.9",
                   "'anchor off box' grows",
                   anchor_gate))

    # THE SECOND GATE OF THE SAME STAGE, COVERED BY NOTHING: with the
    # `off_page` gate removed the battery still reported 0 uncaught. The
    # corruption must use the label `p0042-b17`; a bare number carries no page.
    def anchor_page_gate():
        A = _anchor_all_paged(P)
        was = M(A)["matching"]
        if not was["by_anchor"]:
            return None
        m = M(_anchor_all_paged(P, shift=1))["matching"]
        return (fell(m["share"], was["share"])
                and grew(m["anchor_wrong_page"],
                         was["anchor_wrong_page"]))

    probes.append(("the anchor names the neighbouring page with the right "
                   "block number",
                   "pairing falls, 'anchor to another page' grows",
                   anchor_page_gate))

    # --- corrupting TRUTH: the metric must look at BOTH inputs
    def truth_chars():
        tt, ok = _corrupt_truth(T, _drop10)
        return None if (not ok or b_cer is None) else cer(tt=tt) > b_cer

    probes.append(("every tenth character dropped in truth", "CER grew",
                   truth_chars))
    probes.append(("a table cell corrupted in truth",
                   "fewer matched cells",
                   lambda: (lambda tt: None if not tt[1] else
                            fell(M(tt=tt[0])["tables"]["share_cells_matched"],
                                 b_cell))(_corrupt_truth_cell(T))))

    # --- REVERSE probes: the figure must STAY PUT
    probes.append(("the input not corrupted at all",
                   "every number stays put",
                   lambda: M() == base))
    probes.append(("variance inside the boundary (case, dash, NFKC, dot)",
                   "CER unchanged",
                   lambda: (lambda mm: None if mm is None
                            else cer(mm) == b_cer)(one(_spelling))))
    # The same variance at level "none" MUST move the figure: otherwise
    # normalisation is dead and the probe above praises inaction, not work.
    probes.append(("the same variance at normalisation 'none'",
                   "CER changed",
                   lambda: (lambda mm: None if mm is None else
                            measure_pages(T, mm, norm="none")["text"]["CER"]
                            != measure_pages(T, P, norm="none")["text"]["CER"])(
                       one(_spelling))))

    # ---- SECOND LEVEL: what model reading will be judged by --------------
    # Three probes, each closing a defect costly on the first paid run.

    def _same_numbers_in_otsl():
        """A table in OTSL scores THE SAME as one in HTML. Measured before the
        fix at `_answer_grid`: 100% as HTML, 0% as OTSL."""
        if bi is None:
            return None
        src = P[bi]["blocks"][bj].get("content") or ""
        if otsl.looks_like(src):
            return None          # ALREADY OTSL -- nothing to compare with
        g = _answer_grid(src)
        if not g:
            return None
        mm = _edit(P, bi, bj, lambda _: _grid_otsl(g))
        mm[bi]["blocks"][bj]["kind"] = "otsl"
        a, b = M(mm)["tables"], base["tables"]
        return (a["cells_matched"] == b["cells_matched"]
                and a["given_as_text"] == b["given_as_text"])

    def _artefact_truth(fn, field):
        """Corrupt an artifact that HAS character truth.

        TWO RULES ALREADY AT THE NEIGHBOURS (`one`, `one_tab`), both broken
        here once. Keep looking until a block there is something to corrupt in:
        silence on the first of twenty-six formulas put out BOTH new probes at
        once and the battery printed zero uncaught. And the corruption must
        CHANGE something: an answer may already begin with `#`, and the probe
        then reddens against a healthy instrument.
        """
        for i in sorted(T):
            if i not in P:
                continue
            side = page_side(T[i])
            for b in T[i]["blocks"]:
                if _truth_text(b, side) is None:
                    continue
                for k, pb in enumerate(P[i]["blocks"]):
                    if pb.get("block_id") != b.get("block_id"):
                        continue
                    old = pb.get("content")
                    if not old or fn(old) == old:
                        continue                    # nothing to corrupt here
                    return M(_edit(P, i, k, lambda _: fn(old)))[
                        "artifacts_with_truth"][field]
        return None

    probes.append(("the table given as OTSL instead of HTML",
                   "the same numbers (the parsing is ours, not the model's "
                   "trouble)",
                   _same_numbers_in_otsl))
    probes.append(("an artifact with character truth corrupted",
                   "artifact CER grew",
                   lambda: (lambda v: None if v is None else
                            grew(v, base["artifacts_with_truth"]["CER"]))(
                       _artefact_truth(lambda c: "#" + c[1:], "CER"))))
    probes.append(("an artifact with truth not read", "more no-answer",
                   lambda: (lambda v: None if v is None else
                            v > base["artifacts_with_truth"]["no_answer"])(
                       _artefact_truth(lambda c: "", "no_answer"))))

    bad = mute = seen = 0
    for name, want, probe in probes:
        # AN EXCEPTION IN A PROBE IS NOT A FALL OF THE BATTERY: `measure_pages`
        # throwing on the 12th probe of 28 gave 16 printed lines and NOT ONE
        # total, leaving exit code the only witness.
        try:
            ok = probe()
        except Exception as e:                                  # noqa: BLE001
            ok = False
            # NOT the word "fell": seven probes in `metrics.py` have "fell" as
            # their `want`, which would read "fell -- fell: ValueError".
            want = f"{want} — THE PROBE THREW {type(e).__name__}: {e}"
        mark = "no data" if ok is None else ("ok " if ok else "NO")
        log(f"  {mark:>10}  {name}: {want}")
        bad += ok is False
        mute += ok is None
        seen += 1

    log("what this battery does NOT catch: a wrong TRUTH (nothing to check "
        "it against but the scan and the eyes); a model invention that got "
        "into truth twice; an error inside the normalisation boundary — it "
        "is stripped on purpose and by measurement; reading lost BEFORE the "
        "metric, when the block is in neither truth nor answer.")
    # A FIGURE, NOT THE WORD "DONE", as in `fitness`: a lone "uncaught: N" hid
    # ten or eleven probes of twenty-eight that measured NOTHING, and a broken
    # helper (`_anchor_all`) sends a probe to "no data", where breakage looks
    # like health. THE DENOMINATOR IS WHAT WAS PRINTED (`seen`): adding groups
    # by hand gave `metrics.mutations` "probes 32" against 33 outcomes.
    log(f"reading battery: probes {seen}, measured {seen - mute}, "
        f"nothing to measure with {mute} (see the 'no data' lines), "
        f"uncaught {bad}")
    return bad


