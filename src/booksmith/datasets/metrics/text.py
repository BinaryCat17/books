"""Reading metric: an answer compared against text that is KNOWN.

Takes truth pages and a read run, returns a Record. It measures CHARACTERS and
CELL ADDRESSES -- boxes are `contour.py`, delivery to level two is
`assess/ink.py` -- since one combined number trades one defect for another.
Four zeros stay apart: an artifact (silence is right), the model silent, truth
not annotated, not paired. Cells are compared BY ADDRESS, a row shift leaving
the bag of cells identical. The share paired and the stage that paired it
always print, a CER over two blocks of forty being a figure about pairing.
"""
import html as _html
import re
from html.parser import HTMLParser

from booksmith.datasets.metrics import contour as metrics
from booksmith.core import otsl, page, policy
from booksmith.core.textnorm import NORM, norm_note, normalize
from booksmith.core.errors import TextError, Unmeasurable
from booksmith.datasets.metrics.base import Metric, Record, Scalar, Spec




# ----------------------------------------------------------------- distance
# Levenshtein, exact, bit-parallel (Myers, 1999): a matrix column in two
# integers, 64 bits at a time. Past the budget the distance is called an UPPER
# BOUND on its own line, an estimate passed off as exact keeping CER from
# falling on exactly the longest blocks.
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
    """Artifact truth living beside the page, linked by block id. The key is
    coerced to a string: json makes keys strings and the id in memory is an
    int, so `side[3]` would miss `side["3"]` silently."""
    m = (page.get("meta") or {}) if isinstance(page, dict) else {}
    for k in SIDE_KEYS:
        v = m.get(k)
        if isinstance(v, dict):
            return {str(kk): vv for kk, vv in v.items()}
    return {}


def _truth_grid(b, side=None):
    """Grid of a table's truth, or None -- a table with no structural truth.
    Looked for in the block's `meta` and in the page's artifact truth (`side`):
    markup may carry the grid inside, our bench puts it aside."""
    # The two places are read independently: an unrelated key in the block's
    # `meta` must not hide the sidecar.
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
        # Both sides speak and disagree; taking either chooses for the operator.
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
    """The artifact's CHARACTERS, lying beside the page, or None. The same
    bridge as `_truth_grid`: None means no character truth and the block is a
    bait, an empty string is declared emptiness and compared as emptiness."""
    aside = (side or {}).get(str(b.get("block_id"))) or {}
    if not isinstance(aside, dict):
        return None
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
    """Grid out of an HTML table: tr/td/th, colspan and rowspan. A spanning
    cell occupies all of its addresses, or a row shift under a spanning header
    would be compared against emptiness and fall for the wrong reason."""

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
    """Grid out of the model's answer, whatever shape it arrived in. Both
    parsers are tried: a reader answering OTSL where only HTML was parsed earns
    a zero and the charge "given as prose" for our own parser's defect."""
    if not s:
        return None
    if kind == "otsl":
        return otsl.grid(s) or _html_grid(s)
    return _html_grid(s) or otsl.grid(s)


def _grid_html(g):
    """Grid back into HTML, for the probes: the metric must get exactly what a
    model would send. The cell is escaped, or a cell holding `<` comes back
    truncated and the probes measure a string it never reported."""
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
    Returns (page, block) with the page NOT discarded, or an anchor naming
    another page would pair with a block of this one under "100% by anchor"."""
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
    """Pairs (truth index, answer index, how paired) and the leftovers. Stages
    in falling trust: anchor -> ids agreeing wholesale -> geometry, the anchor
    verified on page number and box exactly as the `number` stage is."""
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
            # The anchor names another page: pairing here would pass off a
            # foreign answer as this one's, "by anchor".
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
def _load(d, what="pages"):
    """The one loader, `core.page.load_pages`, under this metric's own error
    class: a caller catching `TextError` still does, and the message names
    which side was being read."""
    try:
        return page.load_pages(d, what)
    except Unmeasurable as e:
        raise TextError(str(e)) from None


def measure(truth_dir: str, pages_dir: str, norm: str = NORM) -> dict:
    """Compare what was read against truth. The numbers are in the result."""
    T, P = _load(truth_dir, "truth"), _load(pages_dir, "what was read")
    # Book and raster checks come from the contour metric, through getattr: a
    # rename of those private names must give a loud NOT CHECKED, not a crash.
    def _check(name, *a):
        fn = getattr(metrics, name, None)
        if fn is None:
            return f"{name} NOT CHECKED: no such check in the contour metric"
        return fn(*a)

    note = f"{_check('_same_book', truth_dir, pages_dir)}; " \
           f"{_check('_same_raster', T, P)}"
    res = measure_pages(T, P, norm=norm)
    res["book"] = note
    return res


def measure_pages(T: dict, P: dict, norm: str = NORM) -> dict:
    """The same over pages already loaded: this is what the probes feed."""
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
           # Truth is an empty string and the model wrote something:
           # invisible to CER, there being nothing to divide by.
           "invented_on_empty_truth": 0}
    bait = {"artifacts": 0, "read": 0, "stayed_silent": 0,
            "unmatched": 0}
    mt = {"truth_blocks": 0, "by_anchor": 0, "by_number": 0, "by_geometry": 0,
          "unmatched_truth": 0, "extra_in_answer": 0,
          # Three anchor failures, apart: no such block number, another page,
          # boxes disagree.
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
            # The page is absent from the answer: its blocks were never
            # paired, which is not "read to zero".
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
                            # A table given as prose: the addresses are gone,
                            # dearer than silence and not recoverable.
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
        """Table shares, or None when there is nothing to judge by: zero
        answered blocks means "nothing to compare", not "zero per cent
        matched", and a CER already floored at 1 cannot fall for the probes."""
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
        # The denominator is cells in answered blocks, not all cells.
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
            # As for tables: silence on all of them is not "CER 1.0".
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
        log("  these are NOT baits: they DO have character truth, and "
            "reading them is right work, not invention")
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
    # Only blocks with an error, and text and artifacts counted apart: no one
    # denominator fits both, and an artifact record has no `WER` to print.
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


# ------------------------------------------------ what the probes also use
# The metric's own helpers, walked over by the measurement and by
# `probes/text.py` alike.
def _pages(P):
    return sorted(P)


def _blocks(P):
    for i in _pages(P):
        for j, b in enumerate(P[i]["blocks"]):
            yield i, j, b


def _grid_otsl(g):
    """Grid back into OTSL. The pair to `_grid_html`, needed for the same."""
    if not g:
        return "<nl>"
    rows, cols = _shape(g)
    return "".join("".join("<fcel>" + g.get((r, c), "") for c in range(cols))
                   + "<nl>" for r in range(rows))


# ------------------------------------------------- the metric, as a Metric ---
# The measurement above returns its dict; this turns it into a `Record` and
# names the thresholds that rode in. Every scalar the report prints as NOT
# COMPARED or NOT MARKED is a None carrying the report's own reason.
def _share_count(value, n, of, why):
    """A share with the counts behind it, or the reason there is none."""
    return Scalar(value, count=(n, of), why=None if value is not None else why)


def _over_blocks(value, n, of, why):
    """A rate counted over n blocks of N, or the reason there is none."""
    return Scalar(value, over=(n, of), unit="blocks", why=None if value is not None else why)


class TextMetric(Metric):
    """Characters and table cells against truth: did the reader return the text and the cell addresses known to be there."""
    name = "text"
    # `read` as well as `content`: truth must carry characters and this run
    # must have produced some, or a detection run reads as CER 1.
    needs = frozenset({"truth", "pages", "content", "read"})
    scalars = (
        Spec("paired", "higher",
             "blocks paired with a truth block"),
        Spec("CER", "lower",
             "character error rate over paired blocks"),
        Spec("WER", "lower",
             "word error rate over paired blocks"),
        Spec("CER_answered", "lower",
             "character error rate over the blocks the reader answered"),
        Spec("no_answer", "lower",
             "blocks with no answer"),
        Spec("cells_matched", "higher",
             "table cells matched by address"),
        Spec("CER_cells", "lower",
             "character error rate over matched cells"),
        Spec("tables_given_as_text", "lower",
             "tables answered as text"),
        Spec("baits_read", "lower",
             "baits read as content"),
        Spec("CER_artefacts", "lower",
             "character error rate over artifact blocks"),
        Spec("CER_artefacts_answered", "lower",
             "character error rate over answered artifact blocks"),
    )

    def run(self, bench, run) -> Record:
        res = measure(bench.truth_dir, run.pages_dir)
        return self.record(res, bench.name, run.label)

    def run_loaded(self, bench, run, truth, pages, note) -> Record:
        from booksmith.datasets.metrics.contour import _same_raster
        res = measure_pages(truth, pages)
        res["book"] = f"{note}; {_same_raster(truth, pages)}"
        return self.record(res, bench.name, run.label)

    def record(self, res: dict, bench_name: str, run_label: str) -> Record:
        t, tb, m, bt, a = (res["text"], res["tables"], res["matching"],
                           res["baits"], res["artifacts_with_truth"])
        answered = t["block_count"] - t["no_answer"] - t["unmatched"]
        art_answered = a["block_count"] - a["no_answer"] - a["unmatched"]
        no_cells = ("no table with a cell grid in the truth" if not tb["cell_count"]
                    else "no table answered" if not tb["answered_blocks"]
                    else "no cell matched")
        scalars = {
            "paired": _share_count(m["share"], m["matched_total"], m["truth_blocks"],
                             "no truth block to pair"),
            # CER and WER are over EVERY truth block, an unanswered one at
            # full distance; the answered-only figure is its own line.
            "CER": Scalar(t["CER"], why=None if t["CER"] is not None else "no text block in the truth"),
            "WER": Scalar(t["WER"], why=None if t["WER"] is not None else "no text block in the truth"),
            "CER_answered": _over_blocks(t["cer_answered"], answered, t["block_count"],
                                    "no answered text block"),
            "no_answer": _share_count(t["share_no_answer"], t["no_answer"], t["block_count"],
                                "no text block in the truth"),
            "cells_matched": _share_count(tb["share_cells_matched"], tb["cells_matched"],
                                    tb["cell_count"], no_cells),
            "CER_cells": Scalar(tb["cer_cells"], over=(tb["cells_matched"], tb["cell_count"]),
                                unit="cells", why=None if tb["cer_cells"] is not None else no_cells),
            "tables_given_as_text": _share_count(
                tb["given_as_text"] / tb["block_count"] if tb["block_count"] else None,
                tb["given_as_text"], tb["block_count"], "no table in the truth"),
            "baits_read": _share_count(bt["share"], bt["read"], bt["artifacts"],
                                 "no bait artefact in the truth"),
            # Over every artefact with character truth, like CER; the
            # answered-only figure is the dict's `cer_answered`.
            "CER_artefacts": Scalar(a["CER"], why=None if a["CER"] is not None
                                    else "no artefact with character truth"),
            "CER_artefacts_answered": _over_blocks(a["cer_answered"], art_answered, a["block_count"],
                                              "no answered artefact with character truth"),
        }
        params = {"normalization": res["normalization"]["level"],
                  **{f"geometry_{k}": v for k, v in (res.get("geometry_gate") or {}).items()}}
        return Record(self.name, bench_name, run_label, scalars, params, res)

    def report(self, rec: Record, log=print) -> None:
        report(rec.detail, log=log)
