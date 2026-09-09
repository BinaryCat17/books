"""Probes of the reading metric: spoil the answer, the truth and our pairing.

Corruption is THREE-SIDED -- the answer, the TRUTH (a metric blind to it is
always "right") and OUR pairing -- and each probe corrupts EXACTLY ONE thing:
two at once cannot tell a live figure from one stuck to its neighbour.
"""
import copy
import re

from booksmith.core import otsl, policy
from booksmith.datasets.metrics import contour as metrics
from booksmith.datasets.metrics import text as m
from booksmith.datasets.metrics.base import Probe


def _pick_text(P, T, want=None):
    """The first answer block whose truth holds non-empty text. `want` narrows
    it: "one digit replaced" on a block with no digits is an honest guard and
    no probe."""
    for i in m._pages(T):
        if i not in P:
            continue
        ids = {b.get("block_id"): b for b in T[i]["blocks"]}
        side = m.page_side(T[i])
        for j, b in enumerate(P[i]["blocks"]):
            t = ids.get(b.get("block_id"))
            c = b.get("content")
            if t is None or m._truth_grid(t, side) is not None:
                continue
            if isinstance(t.get("content"), str) and t["content"].strip() \
                    and isinstance(c, str) and c.strip() \
                    and (want is None or want(c)):
                return i, j
    return None, None


def _pick_table(P, T):
    for i in m._pages(T):
        if i not in P:
            continue
        ids = {b.get("block_id"): b for b in T[i]["blocks"]}
        side = m.page_side(T[i])
        for j, b in enumerate(P[i]["blocks"]):
            t = ids.get(b.get("block_id"))
            # `_answer_grid`, not `_html_grid`: a real model answers in OTSL,
            # where this probe and four neighbours would say "no data" while the
            # battery still reported zero uncaught.
            if t is not None and m._truth_grid(t, side) is not None \
                    and m._answer_grid(b.get("content"), b.get("kind")):
                return i, j
    return None, None


def _pick_bait(P, T):
    for i in m._pages(T):
        if i not in P:
            continue
        ids = {b.get("block_id"): b for b in T[i]["blocks"]}
        side = m.page_side(T[i])
        for j, b in enumerate(P[i]["blocks"]):
            t = ids.get(b.get("block_id"))
            if t is None or t.get("content") is not None:
                continue
            # NO GRID AND NO CHARACTERS. Without the character check the probe
            # corrupted a FORMULA with known truth and reddened a healthy metric.
            if (m._truth_grid(t, side) is None and m._truth_text(t, side) is None
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
    """Glue hyphenation where there was none: exactly what a model trained to
    glue does, and the metric must see it."""
    out = _HYPH.sub(r"\1\2", s)
    return None if out == s else out


def _regrid(src, g):
    """The corrupted grid back IN THE SHAPE the answer arrived in, or a probe
    changes content and format at once."""
    return m._grid_otsl(g) if otsl.looks_like(src) else m._grid_html(g)


def _shift_rows(html):
    """A ROW SHIFT IN A TABLE: labels stay, data rolls one row down. The same
    cells, every value attributed to the wrong row."""
    g = m._answer_grid(html)
    if not g:
        return None
    rows, cols = m._shape(g)
    if rows < 2 or cols < 2:
        return None
    out = {}
    for (r, c), v in g.items():
        out[(r, c) if c == 0 else ((r + 1) % rows, c)] = v
    return _regrid(html, out)


def _detable(html):
    """Table given as plain text: markup gone, characters intact."""
    g = m._answer_grid(html)
    if not g:
        return None
    rows, cols = m._shape(g)
    return " ".join(g.get((r, c), "") for r in range(rows) for c in range(cols))


def _blank_cell(html):
    g = m._answer_grid(html)
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
    width, trailing full stop. The figure must not move."""
    out = s.upper().replace("-", "—") + "."
    out = out.replace("A", "Ａ")
    return out if out != s else None


def _shift_boxes(P, frac=0.9):
    Q = copy.deepcopy(P)
    for _, _, b in m._blocks(Q):
        x = m._box(b)
        if x is None:
            continue
        d = frac * max(4.0, min(x[2] - x[0], x[3] - x[1]))
        b["box"] = [x[0] + d, x[1] + d, x[2] + d, x[3] + d]
    return Q


def _anchor_all(P):
    Q = copy.deepcopy(P)
    for _, _, b in m._blocks(Q):
        b.setdefault("meta", {})["anchor"] = b.get("block_id")
    return Q


def _anchor_all_paged(P, shift=0):
    """Anchors as the per-page label the builder writes: a bare number carries
    no page, so the "another page" gate cannot fire on it. `shift` names the
    neighbouring page with the block number right."""
    Q = copy.deepcopy(P)
    for i, _, b in m._blocks(Q):
        b.setdefault("meta", {})["anchor"] = f"p{i + shift:04d}-b{b.get('block_id')}"
    return Q


def _shuffle_pages(P):
    """The answer rolled one page along: comparison goes by page index."""
    ks = m._pages(P)
    if len(ks) < 2:
        return None
    return {k: {**copy.deepcopy(P[ks[(n + 1) % len(ks)]]), "index": k}
            for n, k in enumerate(ks)}


def _corrupt_truth(T, fn):
    """Corrupting THE TRUTH ITSELF: a metric blind to truth measures one of its
    inputs and will always be right."""
    Q = copy.deepcopy(T)
    for _i, _, b in m._blocks(Q):
        c = b.get("content")
        if isinstance(c, str) and c.strip():
            out = fn(c)
            if out is not None and out != c:
                b["content"] = out
                return Q, True
    return Q, False


def _corrupt_truth_cell(T):
    """Corrupt one cell OF THE TRUTH. The grid lives BESIDE the page, keyed by
    block id as a string: an earlier edition edited the block's own `meta`,
    corrupted nothing, and credited itself for an experiment never run."""
    Q = copy.deepcopy(T)
    for i, _, b in m._blocks(Q):
        side = m.page_side(Q[i])
        if m._truth_grid(b, side) is None:
            continue
        holders = []
        meta = b.get("meta") or {}
        if meta:
            holders.append(meta)
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
            cells = next((src[k] for k in m._CELLS_KEYS if k in src), None)
            if isinstance(cells, list) and cells and isinstance(cells[0], list):
                for row in cells:
                    for k, v in enumerate(row):
                        if isinstance(v, str) and v.strip():
                            row[k] = v + "X"
                            return Q, True
    return Q, False


def _map_all(P, fn):
    Q = copy.deepcopy(P)
    for _, _, b in m._blocks(Q):
        b["content"] = fn(b.get("content"))
    return Q


def _drop_block(P):
    for i in m._pages(P):
        if len(P[i]["blocks"]) > 1:
            Q = copy.deepcopy(P)
            Q[i]["blocks"].pop(0)
            return Q
    return None


def _add_block(P):
    """A spurious answer block, boxed over an existing one so that it clears the
    gate and still stays spurious. THE COPY'S ANCHOR IS STRIPPED: with it, the
    extra block landed in "anchor to nowhere" instead of "spurious in answer"."""
    i = m._pages(P)[0]
    Q = copy.deepcopy(P)
    b = copy.deepcopy(Q[i]["blocks"][0])
    b["block_id"] = 10_000
    b.pop("meta", None)
    Q[i]["blocks"].append(b)
    return Q


def _dead_anchor(P):
    i = m._pages(P)[0]
    Q = copy.deepcopy(P)
    Q[i]["blocks"][0].setdefault("meta", {})["anchor"] = 99_999
    return Q


def probes(bench, run) -> list:
    T = m._load(bench.truth_dir, "truth")
    P = m._load(run.pages_dir, "what was read")
    base = m.measure_pages(T, P)
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
    b_flat = base["tables"]["given_as_text"]

    ti, tj = _pick_text(P, T)
    di, dj = _pick_text(P, T, want=lambda c: any(x.isdigit() for x in c))
    bi, bj = _pick_table(P, T)
    ai, aj = _pick_bait(P, T)

    def M(pp=None, tt=None):
        return m.measure_pages(tt or T, pp or P)

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

    def digit():
        if di is None:
            return None
        new = _digit(P[di]["blocks"][dj]["content"])
        if new is None:
            return None
        return cer_up(_edit(P, di, dj, lambda _: new))

    def neighbour():
        """A NEIGHBOUR's answer substituted whole: caught only by comparing
        against THIS block's truth, and a metric that scores "looks like text"
        misses it."""
        if ti is None:
            return None
        src = None
        for i, j, b in m._blocks(P):
            c = b.get("content")
            if isinstance(c, str) and c.strip() and (i, j) != (ti, tj):
                src = c
                break
        if src is None:
            return None
        return cer_up(_edit(P, ti, tj, lambda _: src))

    def bait():
        if ai is None:
            return None
        mm = _edit(P, ai, aj,
                   lambda _: "Fig. 4. Diagram of the setup, 12 captions")
        return grew(M(mm)["baits"]["share"], b_bait)

    def dropped():
        mm = _drop_block(P)
        return None if mm is None else grew(
            M(mm)["matching"]["unmatched_truth"], b_lost)

    def anchor_gate():
        """GUARD OVER THE "anchor off box" GATE: an anchor is verified, not
        trusted, so a box shift must break pairing EVEN WHERE ALL WAS PAIRED BY
        ANCHOR. Not always applicable, and both guards are asked of the INPUT:
        with no block paired by anchor there is nothing to break, and where the
        shift sinks into the pixel tolerance "did not land" and "gate gone"
        would answer alike."""
        A = _anchor_all(P)
        was = M(A)["matching"]
        if not was["by_anchor"]:
            return None
        S = _shift_boxes(A)
        if not any(x is not None and y is not None
                   and not metrics.matches(x, y)
                   for (_, _, a), (_, _, s) in zip(m._blocks(A), m._blocks(S), strict=True)
                   for x, y in ((m._box(a), m._box(s)),)):
            return None
        return grew(M(S)["matching"]["anchor_box_mismatch"],
                    was["anchor_box_mismatch"])

    def anchor_page_gate():
        """THE SECOND GATE OF THE SAME STAGE, COVERED BY NOTHING: with the
        off-page gate removed the battery still reported zero uncaught. The
        corruption must use the per-page label; a bare number carries no page."""
        A = _anchor_all_paged(P)
        was = M(A)["matching"]
        if not was["by_anchor"]:
            return None
        mm = M(_anchor_all_paged(P, shift=1))["matching"]
        return (fell(mm["share"], was["share"])
                and grew(mm["anchor_wrong_page"], was["anchor_wrong_page"]))

    def truth_chars():
        tt, ok = _corrupt_truth(T, _drop10)
        return None if (not ok or b_cer is None) else cer(tt=tt) > b_cer

    def _same_numbers_in_otsl():
        """A table in OTSL scores THE SAME as one in HTML. Measured before the
        fix at `_answer_grid`: 100% as HTML, 0% as OTSL."""
        if bi is None:
            return None
        src = P[bi]["blocks"][bj].get("content") or ""
        if otsl.looks_like(src):
            return None          # ALREADY OTSL -- nothing to compare with
        g = m._answer_grid(src)
        if not g:
            return None
        mm = _edit(P, bi, bj, lambda _: m._grid_otsl(g))
        mm[bi]["blocks"][bj]["kind"] = "otsl"
        a, b = M(mm)["tables"], base["tables"]
        return (a["cells_matched"] == b["cells_matched"]
                and a["given_as_text"] == b["given_as_text"])

    def _artefact_truth(fn, field):
        """Corrupt an artifact that HAS character truth. Keep looking until a
        block there is something to corrupt in, and the corruption must CHANGE
        something: silence on the first of twenty-six formulas put out both
        probes at once and the battery printed zero uncaught."""
        for i in sorted(T):
            if i not in P:
                continue
            side = m.page_side(T[i])
            for b in T[i]["blocks"]:
                if m._truth_text(b, side) is None:
                    continue
                for k, pb in enumerate(P[i]["blocks"]):
                    if pb.get("block_id") != b.get("block_id"):
                        continue
                    old = pb.get("content")
                    if not old or fn(old) == old:
                        continue                    # nothing to corrupt here
                    return M(_edit(P, i, k, lambda _, old=old: fn(old)))[
                        "artifacts_with_truth"][field]
        return None

    return [Probe(n, w, f) for n, w, f in (
        # --- corrupting the model ANSWER: characters
        ("every tenth character dropped", "CER grew",
         lambda: cer_up(one(_drop10))),
        ("two lines swapped inside the block", "CER grew",
         lambda: cer_up(one(_swap_lines))),
        ("two words swapped", "WER grew",
         lambda: (lambda mm: None if mm is None
                  else grew(M(mm)["text"]["WER"], b_wer))(one(_swap_words))),
        ("hyphenation glued where there was none", "CER grew",
         lambda: cer_up(one(_glue))),
        ("one digit replaced", "CER grew", digit),
        ("an empty answer on a non-empty block", "more no-answer",
         lambda: (lambda mm: None if mm is None else
                  grew(M(mm)["text"]["share_no_answer"], b_none))(
             one(lambda s_: ""))),
        ("an empty answer on a non-empty block", "CER grew",
         lambda: cer_up(one(lambda s_: ""))),
        ("every answer dropped", "CER exactly 1.0 and no answer 1.0",
         lambda: (lambda r: r["text"]["CER"] == 1.0
                  and r["text"]["share_no_answer"] == 1.0)(
             M(_map_all(P, lambda c: None)))),
        ("the NEIGHBOUR's answer whole", "CER grew", neighbour),
        # --- corrupting the ANSWER: table
        ("A ROW SHIFT IN A TABLE (the same bag of cells)",
         "fewer matched cells",
         lambda: (lambda mm: None if mm is None else
                  fell(M(mm)["tables"]["share_cells_matched"], b_cell))(
             one_tab(_shift_rows))),
        ("one cell emptied", "fewer matched cells",
         lambda: (lambda mm: None if mm is None else
                  fell(M(mm)["tables"]["share_cells_matched"], b_cell))(
             one_tab(_blank_cell))),
        ("the table given as plain text", "more given as text",
         lambda: (lambda mm: None if mm is None else
                  grew(M(mm)["tables"]["given_as_text"], b_flat))(
             one_tab(_detable))),
        ("the table given as plain text", "cell CER grew",
         lambda: (lambda mm: None if mm is None else
                  grew(M(mm)["tables"]["cer_cells"], b_cellcer))(
             one_tab(_detable))),
        # --- corrupting the ANSWER: bait
        ("text added to an artifact (bait)", "more baits", bait),
        # --- corrupting OUR OWN PAIRING: it is an input too
        ("answer boxes shifted by 0.9 of their size",
         "fewer paired (where pairing was not by anchor)",
         lambda: fell(M(_shift_boxes(P))["matching"]["share"], b_match)),
        ("a block dropped from the answer", "more not paired", dropped),
        ("an extra block in the answer", "more extra",
         lambda: grew(M(_add_block(P))["matching"]["extra_in_answer"], b_extra)),
        ("the anchor points nowhere", "more anchors to nowhere",
         lambda: grew(M(_dead_anchor(P))["matching"]["anchor_to_nowhere"], b_dead)),
        ("the answer shifted by one page", "CER grew",
         lambda: (lambda mm: None if mm is None else cer_up(mm))(
             _shuffle_pages(P))),
        ("with anchors, boxes shifted by 0.9", "'anchor off box' grows",
         anchor_gate),
        ("the anchor names the neighbouring page with the right block number",
         "pairing falls, 'anchor to another page' grows", anchor_page_gate),
        # --- corrupting TRUTH: the metric must look at BOTH inputs
        ("every tenth character dropped in truth", "CER grew", truth_chars),
        ("a table cell corrupted in truth", "fewer matched cells",
         lambda: (lambda tt: None if not tt[1] else
                  fell(M(tt=tt[0])["tables"]["share_cells_matched"], b_cell))(
             _corrupt_truth_cell(T))),
        # --- REVERSE probes: the figure must STAY PUT
        ("the input not corrupted at all", "every number stays put",
         lambda: M() == base),
        ("variance inside the boundary (case, dash, NFKC, dot)",
         "CER unchanged",
         lambda: (lambda mm: None if mm is None else cer(mm) == b_cer)(
             one(_spelling))),
        # The same variance at level "none" MUST move the figure, or
        # normalisation is dead and the probe above praises inaction.
        ("the same variance at normalisation 'none'", "CER changed",
         lambda: (lambda mm: None if mm is None else
                  m.measure_pages(T, mm, norm="none")["text"]["CER"]
                  != m.measure_pages(T, P, norm="none")["text"]["CER"])(
             one(_spelling))),
        # --- what model reading will be judged by: three defects that were
        # costly on the first paid run
        ("the table given as OTSL instead of HTML",
         "the same numbers (the parsing is ours, not the model's trouble)",
         _same_numbers_in_otsl),
        ("an artifact with character truth corrupted", "artifact CER grew",
         lambda: (lambda v: None if v is None else
                  grew(v, base["artifacts_with_truth"]["CER"]))(
             _artefact_truth(lambda c: "#" + c[1:], "CER"))),
        ("an artifact with truth not read", "more no-answer",
         lambda: (lambda v: None if v is None else
                  v > base["artifacts_with_truth"]["no_answer"])(
             _artefact_truth(lambda c: "", "no_answer"))),
    )]
