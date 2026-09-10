"""Probes of the contour metric: spoil the boxes, the labels, truth, thresholds"""

from metrics import classes as policy
from metrics import contour as m
from metrics.base import Probe
from metrics.mutate import (
    duplicate as _duplicate,
    grow as _grow,
    only as _only,
    relabel as _relabel,
    shift as _shift,
    shift_rel as _shift_rel,
    shuffle_pages as _shuffle_pages,
)


def _reverse_order(M):
    out = {}
    for i, p in M.items():
        n = len(p["blocks"])
        out[i] = {**p, "blocks": [{**b, "order": n - 1 - j} for j, b in enumerate(p["blocks"])]}
    return out


def _reverse_blocks(M):
    return {i: {**p, "blocks": list(reversed(p["blocks"]))} for i, p in M.items()}


def _forget_order_mark(T):
    out = {}
    for i, p in T.items():
        meta = dict(p.get("meta") or {})
        meta.pop("order_marked", None)
        out[i] = {**p, "meta": meta}
    return out


def _merge_all(M, arte):
    out = {}
    for i, p in M.items():
        a = [b for b in p["blocks"] if b["label"] in arte]
        rest = [b for b in p["blocks"] if b["label"] not in arte]
        if len(a) >= 2:
            box = [
                min((b["box"][0] for b in a)),
                min((b["box"][1] for b in a)),
                max((b["box"][2] for b in a)),
                max((b["box"][3] for b in a)),
            ]
            a = [{**a[0], "box": box}]
        out[i] = {**p, "blocks": rest + a}
    return out


def _split_all(M, arte):
    out = {}
    for i, p in M.items():
        bs = []
        for b in p["blocks"]:
            if b["label"] not in arte:
                bs.append(b)
                continue
            x0, y0, x1, y1 = b["box"]
            mid = (x0 + x1) / 2
            bs.append({**b, "box": [x0, y0, mid, y1]})
            bs.append({**b, "box": [mid, y0, x1, y1]})
        out[i] = {**p, "blocks": bs}
    return out


def _grew(now, was):
    return None if now is None or was is None else now > was


def _beds(res, prefix):
    return sum((n for k, n in res["troubles"].items() if k.startswith(prefix)))


def _multi(T, arte):
    return any((sum((1 for b in p["blocks"] if b["label"] in arte)) > 1 for p in T.values()))


def probes(bench, run) -> list:
    T = m._load(bench.truth_dir, "truth")
    M = m._load(run.pages_dir, "model boxes")
    tp, mp = (bench.policy, run.policy)
    arte = set(mp.artefacts())
    m_arte = [b["label"] for p in M.values() for b in p["blocks"] if b["label"] in arte]
    pick = max(sorted(set(m_arte)), key=m_arte.count) if m_arte else None
    same = next((p for p in policy.POLICIES.values() if pick in p.labels), None)
    other = next(
        (l for l in (same.labels if same else ()) if l != pick and same.role(l) == "artifact"), None
    )
    m_txt = [b["label"] for p in M.values() for b in p["blocks"] if b["label"] not in arte]
    plain = max(sorted(set(m_txt)), key=m_txt.count) if m_txt else None
    base = m.compare_pages(T, M, tp, mp)
    b_found = base["totals"]["share"]
    b_ord = base["model_order"]["agreement"]
    b_asm = base["assembly_order"]["agreement"]
    b_jump = base["jumps"]["excess_jumps"]
    b_multi = base["jumps"]["pages_with_2plus_columns"]
    b_lab = m.label_errors(base)
    b_role = m.role_errors(base)
    b_merge, b_split = (_beds(base, "merge"), _beds(base, "fragmentation"))
    b_dup, b_in = (_beds(base, "nested duplicate"), _beds(base, "inside a miss"))
    b_blind = _beds(base, "not seen")
    keep_c, keep_t, keep_p = (m.COVER_MATCH, m.TOUCH, m.TOL_PX)

    def R(mm=None, tt=None):
        return m.compare_pages(tt or T, mm or M, tp, mp)

    def found(mm=None, tt=None):
        return R(mm, tt)["totals"]["share"]

    def at(cover=None, touch=None, tol=None):
        try:
            m.COVER_MATCH = keep_c if cover is None else cover
            m.TOUCH = keep_t if touch is None else touch
            m.TOL_PX = keep_p if tol is None else tol
            return m.compare_pages(T, M, tp, mp)
        finally:
            m.COVER_MATCH, m.TOUCH, m.TOL_PX = (keep_c, keep_t, keep_p)

    def mergeable():
        for i, t in T.items():
            mb = [b["box"] for b in M[i]["blocks"] if b["label"] in arte]
            if len(mb) < 2:
                continue
            box = [
                min((b[0] for b in mb)),
                min((b[1] for b in mb)),
                max((b[2] for b in mb)),
                max((b[3] for b in mb)),
            ]
            if (
                sum(
                    (1 for b in t["blocks"] if b["label"] in arte and m.cover(b["box"], box) >= 0.6)
                )
                > 1
            ):
                return True
        return False

    def nested_pair():
        for i, t in T.items():
            mb = [b for b in M[i]["blocks"] if b["label"] in arte]
            used = set()
            for b in [z for z in t["blocks"] if z["label"] in arte]:
                j = m._pick(b, mb, used)
                if j is None:
                    continue
                used.add(j)
                if m.cover(mb[j]["box"], b["box"]) >= 0.9:
                    return True
        return False

    def _nested(mm):
        for i, t in T.items():
            tb = [b["box"] for b in t["blocks"] if b["label"] in arte]
            for x in mm[i]["blocks"]:
                if x["label"] in arte and any((m.cover(x["box"], b) >= 0.9 for b in tb)):
                    return True
        return False

    def _mixable():
        mixed = m._mix_columns(M, pol=mp)
        return any(
            (
                [b["box"] for b in m._columns_of(mixed[i], pol=mp)[0]]
                != [b["box"] for b in m._columns_of(p, pol=mp)[0]]
                for i, p in M.items()
            )
        )

    def halves_inside():
        return _nested(_split_all(M, arte))

    def one_box_dash():
        j = R(m._one_box(M, pol=mp))["jumps"]
        return j["excess_jumps"] is None and j["per_page"] is None and (j["pages_counted"] == 0)

    def monotone():
        hi, lo = (min(0.95, keep_c + 0.15), max(0.05, keep_c - 0.35))
        c_hi = at(cover=hi)["totals"]["share"]
        c_lo = at(cover=lo)["totals"]["share"]
        return (
            c_hi <= b_found <= c_lo,
            f"stricter {c_hi * 100:.0f}%, base {b_found * 100:.0f}%, softer {c_lo * 100:.0f}%",
        )

    def not_dead():
        hi, lo = (min(0.95, keep_c + 0.15), max(0.05, keep_c - 0.35))
        moved = (
            at(cover=hi)["totals"]["share"] < b_found or at(cover=lo)["totals"]["share"] > b_found
        )
        worst = 1.0
        for i, t in sorted(T.items()):
            mb = [b for b in M[i]["blocks"] if b["label"] in arte]
            used = set()
            for b in [x for x in t["blocks"] if x["label"] in arte]:
                j = m._pick(b, mb, used)
                if j is None:
                    continue
                used.add(j)
                worst = min(
                    worst,
                    m.cover(b["box"], m._pad(mb[j]["box"], keep_p)),
                    m.cover(mb[j]["box"], m._pad(b["box"], keep_p)),
                )
        return (
            True if moved else None,
            f"worst cover of a matched pair {worst:.2f} at threshold {keep_c:.2f}",
        )

    def tiny_shift():
        d = 3.0
        tiny = found(_shift(M, d, d))
        n = base["totals"]["artifacts"]
        moved = abs(tiny - b_found) * n
        fragile = 0
        for i, t in sorted(T.items()):
            mb = [b for b in M[i]["blocks"] if b["label"] in arte]
            used = set()
            for b in [x for x in t["blocks"] if x["label"] in arte]:
                j = m._pick(b, mb, used)
                if j is None:
                    continue
                used.add(j)
                x = mb[j]["box"]
                c = min(m.cover(b["box"], m._pad(x, keep_p)), m.cover(x, m._pad(b["box"], keep_p)))
                w = max(1.0, min(b["box"][2] - b["box"][0], x[2] - x[0]))
                h = max(1.0, min(b["box"][3] - b["box"][1], x[3] - x[1]))
                fragile += c - keep_c < d / w + d / h
        tol = max(1.0, float(fragile))
        return (
            moved <= tol,
            f"{moved:.0f} boxes of {n} moved, tolerance {tol:.0f} -- that many pairs sit right on the cover border",
        )

    def ranking_stable():
        rk = m.column_jumps_ranking(m._order_variants(M, pol=mp), pol=mp)
        return (
            rk["stable"],
            f"{rk['variants']} variants, {rk['pairs']} pairs over {rk['points']} points, distinguishes {rk['pairs_distinguished']}"
            + (f", flipped {'; '.join(rk['flipped_pairs'])}" if not rk["stable"] else "")
            + (f", tied everywhere {'; '.join(rk['tied_pairs'])}" if rk["tied_pairs"] else ""),
        )

    return [
        Probe(n, w, f)
        for n, w, f in (
            (
                "boxes shifted by a third of their size",
                "fell",
                lambda: found(_shift_rel(M, 0.34)) < b_found,
            ),
            ("boxes inflated 1.5x (spill)", "fell", lambda: found(_grow(M, 1.5)) < b_found),
            ("boxes shrunk 0.6x (crop)", "fell", lambda: found(_grow(M, 0.6)) < b_found),
            (
                "artefacts dropped altogether",
                "zero",
                lambda: found(_only(M, lambda b: b["label"] not in arte)) == 0.0,
            ),
            (
                f"artefacts called {plain}",
                "zero",
                lambda: (
                    None
                    if not plain
                    else found(_relabel(M, lambda l: plain if l in arte else l)) == 0.0
                ),
            ),
            ("boxes duplicated", "did not grow", lambda: found(_duplicate(M)) <= b_found),
            ("markup shifted by one page", "fell", lambda: found(_shuffle_pages(M)) < b_found),
            (
                "model ranks reversed",
                "model order fell",
                lambda: (
                    None
                    if b_ord is None
                    else R(_reverse_order(M))["model_order"]["agreement"] < b_ord
                ),
            ),
            (
                "model ranks reversed",
                "assembly order UNCHANGED",
                lambda: (
                    None
                    if b_asm is None
                    else R(_reverse_order(M))["assembly_order"]["agreement"] == b_asm
                ),
            ),
            (
                "assembly order reversed (block list)",
                "fell",
                lambda: (
                    None
                    if b_asm is None
                    else R(_reverse_blocks(M))["assembly_order"]["agreement"] < b_asm
                ),
            ),
            (
                "two columns interleaved",
                "more excess jumps",
                lambda: (
                    None
                    if not (b_multi and _mixable())
                    else R(m._mix_columns(M, pol=mp))["jumps"]["excess_jumps"] > b_jump
                ),
            ),
            (
                "all boxes into one column",
                "excess jumps zero",
                lambda: None if not b_jump else R(m._one_column(M))["jumps"]["excess_jumps"] == 0,
            ),
            ("a page with one counted box", "the quantity is a DASH, not a zero", one_box_dash),
            (
                "the page's artefacts merged into one",
                "more merges",
                lambda: (
                    None if not mergeable() else _beds(R(_merge_all(M, arte)), "merge") > b_merge
                ),
            ),
            (
                "every artefact cut in half",
                "more fragmentations",
                lambda: _beds(R(_split_all(M, arte)), "fragmentation") > b_split,
            ),
            (
                "boxes duplicated",
                "more nested duplicates",
                lambda: (
                    None
                    if not nested_pair()
                    else _beds(R(_duplicate(M)), "nested duplicate") > b_dup
                ),
            ),
            (
                "every artefact cut in half",
                "more inside a miss",
                lambda: (
                    None
                    if not halves_inside()
                    else _beds(R(_split_all(M, arte)), "inside a miss") > b_in
                ),
            ),
            (
                f"label {pick} replaced by {other}",
                "more label errors",
                lambda: (
                    _grew(
                        m.label_errors(R(_relabel(M, lambda l: other if l == pick else l))), b_lab
                    )
                    if pick and other
                    else None
                ),
            ),
            (
                f"artefacts called {plain}",
                "more bucket errors",
                lambda: (
                    None
                    if not (
                        plain
                        and any(
                            (
                                bench.policy.role(k.split("->", 1)[0]) == "artifact"
                                for k in base["label_confusion"]
                            )
                        )
                    )
                    else m.role_errors(R(_relabel(M, lambda l: plain if l in arte else l))) > b_role
                ),
            ),
            (
                f"label {pick} replaced by {other}",
                "localisation UNCHANGED",
                lambda: (
                    None
                    if not (pick and other)
                    else found(_relabel(M, lambda l: other if l == pick else l)) == b_found
                ),
            ),
            (
                "the page's artefacts merged into one",
                "sense whole falls",
                lambda: (
                    None
                    if not _multi(T, arte)
                    else R(_merge_all(M, arte))["sense"]["merged"] > base["sense"]["merged"]
                ),
            ),
            (
                "boxes shrunk 0.85x",
                "more cropped",
                lambda: R(_grow(M, 0.85))["sense"]["cropped"] > base["sense"]["cropped"],
            ),
            (
                "boxes shrunk by half",
                "fewer intact",
                lambda: R(_grow(M, 0.5))["sense"]["intact"] < base["sense"]["intact"],
            ),
            (
                "artefacts dropped altogether",
                "no intact left",
                lambda: R(_only(M, lambda b: b["label"] not in arte))["sense"]["intact"] == 0,
            ),
            (
                "truth shifted by a third of the box size",
                "fell",
                lambda: found(tt=_shift_rel(T, 0.34)) < b_found,
            ),
            ("truth inflated 1.5x", "fell", lambda: found(tt=_grow(T, 1.5)) < b_found),
            (
                "the order-marked flag erased from truth",
                "NOT COMPARED, not a number",
                lambda: (
                    None
                    if b_asm is None
                    else all(
                        (
                            R(tt=_forget_order_mark(T))[k]["agreement"] is None
                            for k in ("model_order", "assembly_order")
                        )
                    )
                ),
            ),
            (
                "text and furniture dropped from truth",
                "text zero",
                lambda: (
                    None
                    if not any(
                        (
                            bench.policy.role(b["label"]) != "artifact"
                            for p in T.values()
                            for b in p["blocks"]
                        )
                    )
                    else R(tt=_only(T, lambda b: b["label"] in arte))["text_and_furniture"]["share"]
                    in (0.0, None)
                ),
            ),
            ("COVER_MATCH stricter and softer", "stricter no more, softer no less", monotone),
            (
                "COVER_MATCH moved at all",
                "the share moves at least one way; 'no data' means that on THIS book every pair is far from the border",
                not_dead,
            ),
            (
                "TOL_PX eight times wider",
                "no less",
                lambda: at(tol=keep_p * 8)["totals"]["share"] >= b_found,
            ),
            (
                "TOUCH raised past every overlap",
                "more 'not seen' troubles",
                lambda: (
                    None if not base["troubles"] else _beds(at(touch=1.01), "not seen") > b_blind
                ),
            ),
            (
                "the column grouping parameters swept",
                "the order of the assembly variants does not flip",
                ranking_stable,
            ),
            ("boxes shifted by 3 pixels", "not caught: the metric is not hysterical", tiny_shift),
        )
    ]
