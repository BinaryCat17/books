"""Contour metrics: how correctly the model outlined tables, figures, charts"""

from metrics import page
from metrics import classes as policy
from metrics import bench as bench_mod
from metrics.errors import Unmeasurable
from metrics.base import Metric, Record, Scalar, Spec
from metrics.log import log

COVER_MATCH = 0.75
TOUCH = 0.1
TOL_PX = 6.0


class MetricError(Unmeasurable):
    pass


def _load(d, what="pages"):
    try:
        return page.load_pages(d, what)
    except Unmeasurable as e:
        raise MetricError(str(e)) from None


def _same_book(truth_dir: str, detect_dir: str) -> str:
    from metrics import bench as _bench

    try:
        b = _bench.Bench.open(truth_dir)
    except Unmeasurable:
        b = None
    try:
        r = _bench.Run.open(detect_dir)
    except Unmeasurable:
        r = _bench.Run.bare(detect_dir)
    try:
        return _bench.same_book(b, r)
    except Unmeasurable as e:
        raise MetricError(str(e)) from None


def _inter(a, b):
    x0, y0 = (max(a[0], b[0]), max(a[1], b[1]))
    x1, y1 = (min(a[2], b[2]), min(a[3], b[3]))
    return max(0.0, x1 - x0) * max(0.0, y1 - y0)


def _area(a):
    return max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])


def iou(a, b):
    i = _inter(a, b)
    u = _area(a) + _area(b) - i
    return 0.0 if u <= 0 else i / u


def cover(a, b):
    s = _area(a)
    return 0.0 if s <= 0 else _inter(a, b) / s


def extra_kind(box, paired, unpaired, outside, tb) -> str:
    if any((cover(box, b) >= 0.9 for b in paired)):
        return "nested duplicate"
    if any((cover(box, b) >= 0.9 for b in unpaired)):
        return "inside a miss"
    if (
        any((cover(box, b) >= 0.5 or cover(b, box) >= 0.5 for b in outside))
        and sum((1 for b in tb if cover(b["box"], box) >= 0.6)) < 2
    ):
        return "on an object outside scoring"
    return "spurious_box"


def _pad(b, d):
    return (b[0] - d, b[1] - d, b[2] + d, b[3] + d)


def matches(t_box, m_box) -> bool:
    return (
        cover(t_box, _pad(m_box, TOL_PX)) >= COVER_MATCH
        and cover(m_box, _pad(t_box, TOL_PX)) >= COVER_MATCH
    )


def _pick(b, boxes, used):
    cand = [
        (iou(b["box"], x["box"]), j)
        for j, x in enumerate(boxes)
        if j not in used and matches(b["box"], x["box"])
    ]
    if not cand:
        return None
    return max(cand)[1]


def _diagnose(t, mine, others_truth, arte, mp):
    touching = [
        m for m in mine if cover(t["box"], m["box"]) >= TOUCH or cover(m["box"], t["box"]) >= TOUCH
    ]
    if not touching:
        return "not seen"
    best = max(touching, key=lambda m: iou(t["box"], m["box"]))
    ct, cm = (cover(t["box"], best["box"]), cover(best["box"], t["box"]))
    eaten = [o for o in others_truth if o is not t and cover(o["box"], best["box"]) >= 0.6]
    if eaten and ct >= 0.6:
        return "merge"
    inside = [m for m in touching if m["label"] in arte and cover(m["box"], t["box"]) >= 0.7]
    if len(inside) >= 2:
        return "fragmentation"
    if mp.role(best["label"]) == "text" and ct >= 0.6:
        return "eaten by text"
    if ct < 0.85 and cm >= 0.85:
        return "crop"
    if cm < 0.6:
        return "spill"
    return "near, but no match"


def _same_raster(T: dict, M: dict) -> str:
    common = sorted(set(T) & set(M))
    if any((k not in p for i in common for p in (T[i], M[i]) for k in ("width", "height"))):
        return "raster NOT CHECKED: pages have no width/height fields"
    dt = sorted({T[i].get("dpi") for i in common}, key=str)
    dm = sorted({M[i].get("dpi") for i in common}, key=str)
    bad = [
        f"p.{i}: truth {T[i]['width']}x{T[i]['height']}, model {M[i]['width']}x{M[i]['height']}"
        for i in common
        if (T[i]["width"], T[i]["height"]) != (M[i]["width"], M[i]["height"])
    ]
    if bad:
        raise MetricError(
            f"truth and model output are in DIFFERENT rasters: coordinates in different systems, and the number would come out plausible and false. {len(bad)} pages of {len(common)} differ: "
            + "; ".join(bad[:3])
            + (" …" if len(bad) > 3 else "")
            + f". dpi: truth {dt}, model {dm} — see the run's PAGE_DPI."
        )
    note = f"raster checked: {len(common)} pages, sizes agree"
    if dt != dm:
        note += f"; the dpi label DIFFERS (truth {dt}, model {dm}) — no effect on coordinates, one raster"
    return note


def page_pairs(t: dict, m: dict, tp=None, mp=None, said: bool = False) -> dict | None:
    state = bench_mod.trait_state(t.get("meta") or {}, "labelled")
    if state == "no" or (said and state != "yes"):
        return None
    i = int(t["index"])
    _same_raster({i: t}, {i: m})
    return compare_pages({i: t}, {i: m}, tp, mp)["pairs"][i]


def _entry(
    truth: str, by: str, run: str | None, label_ok: bool | None, why: str | None = None
) -> dict:
    return {
        "truth": truth,
        "verdict": "matched" if run else "missed",
        "by": by,
        "run": run,
        "label_ok": label_ok,
        "why": why,
        "b_run": run if by == "B" else None,
        "b_label_ok": label_ok if by == "B" else None,
    }


def compare(truth_dir: str, detect_dir: str, tp=None, mp=None) -> dict:
    T, M = (_load(truth_dir, "truth"), _load(detect_dir, "model boxes"))
    note = f"{_same_book(truth_dir, detect_dir)}; {_same_raster(T, M)}"
    res = compare_pages(T, M, tp, mp)
    res["book"] = note
    return res


def compare_pages(T: dict, M: dict, tp=None, mp=None) -> dict:
    tp = tp or policy.UNION
    mp = mp or policy.UNION
    labelled = bench_mod.labelled_of(T)
    if bench_mod.labelled_said(labelled):
        T = {
            i: p
            for i, p in T.items()
            if bench_mod.trait_state(p.get("meta") or {}, "labelled") == "yes"
        }
        if not T:
            raise MetricError(
                "no page of the truth says it is labelled: nothing to compare, which is not a zero of losses"
            )
    missing = sorted(set(T) - set(M))
    if missing:
        raise MetricError(
            f"the model marked up no pages {missing[:5]}: nothing to compare. An empty report here would read as 'matched zero', which is another thing."
        )
    arte_t, arte_m = (set(tp.artefacts()), set(mp.artefacts()))
    states = {}
    for p in T.values():
        st = _truth_order_state(p)
        states[st] = states.get(st, 0) + 1
    rules = sorted(
        {
            str(
                (M[i].get("meta") or {}).get(
                    "reading_order", "not declared (taken as 'model rank')"
                )
            )
            for i in T
            if i in M
        }
    )
    model_rank = all((_model_has_rank(M[i]) for i in T if i in M))
    per_case, conf, ranks = ({}, {}, [])
    per = {"artefacts_found": {}, "text_furniture_found": {}, "label_errors": {}, "role_errors": {}}
    pairs_out = {}
    ceiling = order_pages = 0
    tot = {"artifacts": 0, "found": 0}
    txt = {"block_count": 0, "found": 0, "pages_with_text_markup": 0, "pages_total": 0}
    per_label = {}
    beds = {}
    for i, t in sorted(T.items()):
        m = M[i]
        case = t.get("meta", {}).get("case", str(i))
        tb = [b for b in t["blocks"] if b["label"] in arte_t]
        mb = [b for b in m["blocks"] if b["label"] in arte_m]
        mall = m["blocks"]
        used, pairs = (set(), [])
        for b in tb:
            j = _pick(b, mb, used)
            if j is None:
                pairs.append((b, None))
            else:
                used.add(j)
                pairs.append((b, mb[j]))
        found = sum((1 for _, x in pairs if x is not None))
        c = per_case.setdefault(case, {"artifacts": 0, "found": 0, "troubles": {}})
        c["artifacts"] += len(tb)
        c["found"] += found
        tot["artifacts"] += len(tb)
        tot["found"] += found

        def bed(name, n=1, c=c):
            c["troubles"][name] = c["troubles"].get(name, 0) + n
            beds[name] = beds.get(name, 0) + n

        entries = {}
        for b, x in pairs:
            ta = page.anchor(i, b["block_id"])
            if x is not None:
                per_label.setdefault(b["label"], [0, 0])[0] += 1
                per["artefacts_found"][ta] = 1
                entries[ta] = _entry(
                    ta, "A", page.anchor(i, x["block_id"]), b["label"] == x["label"]
                )
                continue
            why = _diagnose(b, mall, tb, arte_m, mp)
            bed(f"{why} ({b['label']})")
            entries[ta] = _entry(ta, "A", None, None, why)
        paired = [b["box"] for b, x in pairs if x is not None]
        unpaired = [b["box"] for b, x in pairs if x is None]
        outside = [o["box"] for o in t.get("meta", {}).get("out_of_scope") or []]
        extras = []
        for j, x in enumerate(mb):
            if j in used:
                continue
            kind = extra_kind(x["box"], paired, unpaired, outside, tb)
            bed(kind)
            extras.append(
                {"run": page.anchor(i, x["block_id"]), "verdict": kind, "taken_for": None}
            )
        page_ranks, taken = ([], set())
        b_took = {}
        for b in sorted(t["blocks"], key=lambda z: -_area(z["box"])):
            j = _pick(b, mall, taken)
            ta = page.anchor(i, b["block_id"])
            if j is None:
                entries.setdefault(ta, _entry(ta, "B", None, None))
                continue
            taken.add(j)
            x = mall[j]
            ra = page.anchor(i, x["block_id"])
            ok = b["label"] == x["label"]
            b_took[ra] = ta
            if ta in entries:
                entries[ta]["b_run"], entries[ta]["b_label_ok"] = (ra, ok)
            else:
                entries[ta] = _entry(ta, "B", ra, ok)
            conf[b["label"], x["label"]] = conf.get((b["label"], x["label"]), 0) + 1
            if b["label"] != x["label"]:
                per["label_errors"][page.anchor(i, x["block_id"])] = 1
            if tp.role(b["label"]) != mp.role(x["label"]):
                per["role_errors"][page.anchor(i, x["block_id"])] = 1
            page_ranks.append((b.get("order"), x.get("order"), j))
            if b["label"] not in arte_t and _truth_text_state(t) == "yes":
                txt["found"] += 1
                per["text_furniture_found"][page.anchor(i, b["block_id"])] = 1
                per_label.setdefault(b["label"], [0, 0])[0] += 1
        for b in t["blocks"]:
            per_label.setdefault(b["label"], [0, 0])[1] += 1
        for ex in extras:
            ex["taken_for"] = b_took.get(ex["run"])
        extras += [
            {"run": page.anchor(i, x["block_id"]), "verdict": "not counted", "taken_for": None}
            for j, x in enumerate(mall)
            if j not in taken and x["label"] not in arte_m
        ]
        pairs_out[i] = {
            "pairs": [entries[page.anchor(i, b["block_id"])] for b in t["blocks"]],
            "extras": extras,
        }
        txt["pages_total"] += 1
        if _truth_text_state(t) == "yes":
            txt["pages_with_text_markup"] += 1
            txt["block_count"] += len([b for b in t["blocks"] if b["label"] not in arte_t])
        if _truth_order_state(t) == ORDER_MARKED:
            ranks.append((i, page_ranks))
            ceiling += _pairs_ceiling(t)
            order_pages += 1
    tot["share"] = tot["found"] / tot["artifacts"] if tot["artifacts"] else 0.0
    txt["share"] = txt["found"] / txt["block_count"] if txt["block_count"] else None
    why_order = ""
    if not order_pages:
        why_order = (
            "truth carries no order: "
            + ", ".join(
                (
                    f"{k} on {states[k]}"
                    for k in (ORDER_MARKED, ORDER_UNMARKED, ORDER_SILENT)
                    if states.get(k)
                )
            )
            + f" of {len(T)} pages"
        )
    fates = sense(T, M, tp, mp)
    by_fate = {a: fate for fate, d in fates["per"].items() for a in d}
    for i in pairs_out:
        for e in pairs_out[i]["pairs"]:
            e["fate"] = by_fate.get(e["truth"])
    return {
        "totals": tot,
        "sense": fates,
        "text_and_furniture": txt,
        "labelled": labelled,
        "pairs": pairs_out,
        "by_case": per_case,
        "by_label": {
            k: {"truth": v[1], "found": v[0], "bucket": tp.role(k)}
            for k, v in sorted(per_label.items())
        },
        "troubles": dict(sorted(beds.items())),
        "label_confusion": {f"{a}->{b}": n for (a, b), n in sorted(conf.items())},
        "role_confusion": {
            f"{a}->{b}": n for (a, b), n in sorted(conf.items()) if tp.role(a) != mp.role(b)
        },
        "order_truth": {"states": states, "page_count": len(T)},
        "order_rule": ", ".join(rules) or "nothing to declare",
        "model_order": _order_agree(
            ranks,
            1,
            ceiling,
            order_pages,
            len(T),
            why_order or ("" if model_rank else f"the model gives no rank ({', '.join(rules)})"),
        ),
        "assembly_order": _order_agree(ranks, 2, ceiling, order_pages, len(T), why_order),
        "jumps": column_jumps({i: M[i] for i in T}, pol=mp),
        "per": per,
    }


ORDER_MARKED = "marked"
ORDER_UNMARKED = "not marked"
ORDER_SILENT = "not_said"


def order_rule(pages: dict) -> str:
    rules = sorted(
        {
            str((p.get("meta") or {}).get("reading_order", "not declared (taken as 'model rank')"))
            for p in pages.values()
        }
    )
    return ", ".join(rules) or "nothing to declare"


def _truth_text_state(page) -> str:
    return bench_mod.trait_state(page.get("meta") or {}, "text_marked")


def _truth_order_state(page) -> str:
    m = page.get("meta") or {}
    if "order_marked" not in m:
        return ORDER_SILENT
    return ORDER_MARKED if m["order_marked"] else ORDER_UNMARKED


def _model_has_rank(page) -> bool:
    from metrics.page import ours_order

    v = (page.get("meta") or {}).get("reading_order", "model_rank")
    return not ours_order(v)


def _pairs_ceiling(t) -> int:
    o = [b.get("order") for b in t["blocks"] if isinstance(b.get("order"), (int, float))]
    return sum((1 for i in range(len(o)) for j in range(i + 1, len(o)) if o[i] != o[j]))


def _order_agree(by_page, idx: int, ceiling: int, pages: int, of_pages: int, why: str = "") -> dict:
    if why:
        return {
            "pairs": 0,
            "agreement": None,
            "pairs_possible": ceiling,
            "page_count": pages,
            "pages_total": of_pages,
            "why": why,
        }
    ok = bad = norank = 0
    per = {}
    for index, pairs in by_page:
        pp = [(z[0], z[idx]) for z in pairs if z[0] is not None and z[idx] is not None]
        norank += len(pairs) - len(pp)
        ok_p = bad_p = 0
        for i in range(len(pp)):
            for j in range(i + 1, len(pp)):
                a = pp[i][0] - pp[j][0]
                b = pp[i][1] - pp[j][1]
                if a == 0 or b == 0:
                    continue
                ok_p += (a > 0) == (b > 0)
                bad_p += (a > 0) != (b > 0)
        ok += ok_p
        bad += bad_p
        if ok_p + bad_p:
            per[page.anchor(index)] = ok_p / (ok_p + bad_p)
    n = ok + bad
    return {
        "pairs": n,
        "agreement": ok / n if n else None,
        "pairs_possible": ceiling,
        "page_count": pages,
        "pages_total": of_pages,
        "blocks_without_rank": norank,
        "per": per,
    }


COLUMN_OVERLAP = 0.5
COLUMN_WIDE = 0.6
COLUMN_MIN_BOXES = 2
COLUMN_ROLES = ("artifact", "text")


def column_params(overlap=None, wide=None, min_boxes=None, roles=None) -> dict:
    return {
        "x_overlap_of_narrow_box": COLUMN_OVERLAP if overlap is None else overlap,
        "full_width_box_share": COLUMN_WIDE if wide is None else wide,
        "min_boxes_per_page": COLUMN_MIN_BOXES if min_boxes is None else min_boxes,
        "buckets_counted": list(COLUMN_ROLES if roles is None else roles),
    }


def _columns(boxes, overlap=None) -> list:
    ov = COLUMN_OVERLAP if overlap is None else overlap
    n = len(boxes)
    par = list(range(n))

    def find(x):
        while par[x] != x:
            par[x] = par[par[x]]
            x = par[x]
        return x

    for i in range(n):
        for j in range(i + 1, n):
            a, b = (boxes[i], boxes[j])
            ovl = min(a[2], b[2]) - max(a[0], b[0])
            w = min(a[2] - a[0], b[2] - b[0])
            if w > 0 and ovl >= ov * w:
                par[find(i)] = find(j)
    groups = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    left = sorted(groups, key=lambda r: min((boxes[i][0] for i in groups[r])))
    num = {r: k for k, r in enumerate(left)}
    return [num[find(i)] for i in range(n)]


def column_jumps(M: dict, overlap=None, wide=None, min_boxes=None, roles=None, pol=None) -> dict:
    pol = pol or policy.UNION
    par = column_params(overlap, wide, min_boxes, roles)
    ov = par["x_overlap_of_narrow_box"]
    wd = par["full_width_box_share"]
    mn = par["min_boxes_per_page"]
    keep = set(par["buckets_counted"])
    tot_excess = tot_trans = tot_cols = in_count = wide_n = other = 0
    pages = multi = counted = thin = 0
    per_page, columns_by_page = ({}, {})
    for i, p in sorted(M.items()):
        w = float(p.get("width") or 0.0)
        part = []
        for b in p["blocks"]:
            if pol.role(b["label"]) not in keep:
                other += 1
                continue
            if w > 0 and b["box"][2] - b["box"][0] >= wd * w:
                wide_n += 1
                continue
            part.append(b["box"])
        pages += 1
        in_count += len(part)
        if len(part) < mn:
            thin += 1
            continue
        counted += 1
        seq = _columns(part, ov)
        ncols = len(set(seq))
        trans = sum((1 for k in range(1, len(seq)) if seq[k] != seq[k - 1]))
        excess = trans - (ncols - 1)
        tot_trans += trans
        tot_cols += ncols
        tot_excess += excess
        multi += ncols >= 2
        columns_by_page[i] = ncols
        if excess:
            per_page[i] = excess
    ok = counted > 0
    why = (
        ""
        if ok
        else f"the quantity is UNDEFINED: not one of the {pages} pages gathered {mn} counted boxes (counted in all {in_count}, out of the count {wide_n} full-width and {other} of other buckets) — nothing to jump between. This is NOT zero jumps."
    )
    return {
        "excess_jumps": tot_excess if ok else None,
        "per_page": tot_excess / counted if ok else None,
        "transitions": tot_trans,
        "columns": tot_cols,
        "page_count": pages,
        "pages_counted": counted,
        "pages_not_counted_too_few_boxes": thin,
        "pages_with_2plus_columns": multi,
        "boxes_counted": in_count,
        "full_width_boxes": wide_n,
        "boxes_other_buckets": other,
        "by_page": per_page,
        "columns_by_page": columns_by_page,
        "why": why,
        "params": par,
    }


COLUMN_SWEEP = {
    "overlap": (0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9),
    "wide": (0.5, 0.6, 0.7, 0.8, 1.01),
    "min_boxes": (2, 3, 5),
}
_SWEEP_NAMES = {"overlap": "x overlap", "wide": "full-width box", "min_boxes": "minimum boxes"}


def _sweep_points(grid: dict, cross: bool) -> list:
    if cross:
        pts = [{}]
        for k in sorted(grid):
            pts = [dict(p, **{k: v}) for p in pts for v in grid[k]]
        return pts
    return [{}] + [{k: v} for k in sorted(grid) for v in grid[k]]


def _fmt_point(shift: dict) -> str:
    if not shift:
        return "default"
    return ", ".join((f"{_SWEEP_NAMES.get(k, k)} {v}" for k, v in sorted(shift.items())))


def column_jumps_ranking(
    variants: dict, grid: dict = None, cross: bool = False, key: str = "per_page", pol=None
) -> dict:
    names = list(variants)
    pts = _sweep_points(grid or COLUMN_SWEEP, cross)
    vals = {n: [] for n in names}
    made = {}
    for p in pts:
        par = column_params(**p)
        ckey = (
            par["x_overlap_of_narrow_box"],
            par["full_width_box_share"],
            tuple(par["buckets_counted"]),
        )
        for n in names:
            v = variants[n]
            if not callable(v):
                pages = v
            else:
                if (n, ckey) not in made:
                    made[n, ckey] = v(**p)
                pages = made[n, ckey]
            vals[n].append(column_jumps(pages, pol=pol, **p)[key])
    flips, ties = ([], [])
    for a in range(len(names)):
        for b in range(a + 1, len(names)):
            na, nb = (names[a], names[b])
            signs = set()
            for va, vb in zip(vals[na], vals[nb], strict=True):
                if va is None or vb is None or va == vb:
                    continue
                signs.add(va < vb)
            if len(signs) > 1:
                flips.append(f"{na} against {nb}")
            elif not signs:
                ties.append(f"{na} against {nb}")
    play = max(
        (
            mx - mn
            for mn, mx in (
                (
                    min([v for v in vals[n] if v is not None], default=None),
                    max([v for v in vals[n] if v is not None], default=None),
                )
                for n in names
            )
            if mn is not None
        ),
        default=None,
    )
    near = None
    if pts and pts[0] == {}:
        gaps = [
            (abs(vals[names[a]][0] - vals[names[b]][0]), f"{names[a]} against {names[b]}")
            for a in range(len(names))
            for b in range(a + 1, len(names))
            if vals[names[a]][0] is not None
            and vals[names[b]][0] is not None
            and (vals[names[a]][0] != vals[names[b]][0])
        ]
        near = min(gaps) if gaps else None
    return {
        "quantity": key,
        "points": len(pts),
        "variants": len(names),
        "pairs": len(names) * (len(names) - 1) // 2,
        "flipped_pairs": flips,
        "tied_pairs": ties,
        "pairs_distinguished": len(names) * (len(names) - 1) // 2 - len(ties),
        "ruler_play": play,
        "closest_pair_at_default": near,
        "stable": not flips,
        "ranges": {
            n: (
                min([v for v in vals[n] if v is not None], default=None),
                max([v for v in vals[n] if v is not None], default=None),
            )
            for n in names
        },
        "by_point": [
            {"point": _fmt_point(p), "values": {n: vals[n][k] for n in names}}
            for k, p in enumerate(pts)
        ],
    }


def _fits(labels) -> list:
    return policy.fits(labels)


def label_alphabet(res: dict) -> list:
    seen = set()
    for k in res["label_confusion"]:
        a, b = k.split("->", 1)
        seen.add(a)
        seen.add(b)
    return _fits(seen)


def label_errors(res: dict):
    if not label_alphabet(res):
        return None
    return sum(
        (n for k, n in res["label_confusion"].items() if k.split("->", 1)[0] != k.split("->", 1)[1])
    )


def role_errors(res: dict) -> int:
    return sum(res["role_confusion"].values())


def _report_order(res: dict) -> None:
    st = res["order_truth"]
    n, c = (st["page_count"], st["states"])
    if c.get(ORDER_MARKED, 0) < n:
        log(
            f"truth about order: marked {c.get(ORDER_MARKED, 0)}, not marked {c.get(ORDER_UNMARKED, 0)}, NOT SAID {c.get(ORDER_SILENT, 0)} of {n} pages"
        )
    if c.get(ORDER_SILENT):
        log(
            f"  'not said' IS NOT 'not marked': {c[ORDER_SILENT]} truth pages have NO `order_marked` field AT ALL, and a number over them would be taken out of nothing (that is how 'agreed 73%' printed as a number). Cured by whoever built this bench."
        )
    for name, key in (
        ("of MODEL reading against truth", "model_order"),
        ("of book ASSEMBLY against truth", "assembly_order"),
    ):
        o = res[key]
        tail = "" if key == "model_order" else f"; our order is built so: {res['order_rule']}"
        if o["agreement"] is None:
            log(
                f"order {name}: NOT COMPARED — {o.get('why', 'no pairs')} (this is not zero agreement){tail}"
            )
        else:
            log(
                f"order {name}: agreed {o['agreement'] * 100:.0f}%, pairs measured {o['pairs']} of {o['pairs_possible']} possible by truth, over {o['page_count']} pages of {o['pages_total']}"
                + (
                    f", blocks without rank {o['blocks_without_rank']}"
                    if o.get("blocks_without_rank")
                    else ""
                )
                + tail
            )
    _report_jumps(res["jumps"])


def _report_jumps(j: dict) -> None:
    par = ", ".join((f"{k} {v}" for k, v in j["params"].items()))
    if j["excess_jumps"] is None:
        log(f"excess column jumps: DASH — {j['why']} Grouping: {par}")
    else:
        thin = j["pages_not_counted_too_few_boxes"]
        tail = f"boxes counted {j['boxes_counted']}, out of the count {j['full_width_boxes']} full-width and {j['boxes_other_buckets']} of other buckets; pages not counted {thin} of {j['page_count']} (fewer boxes than the minimum); grouping: {par}"
        if not j["pages_with_2plus_columns"]:
            log(
                f"excess column jumps: 0 — the quantity IS COMPUTED over {j['pages_counted']} pages, but this zero is BY CONSTRUCTION: not one multi-column page of {j['page_count']}, there was nowhere to jump. {tail}"
            )
        else:
            log(
                f"excess column jumps: {j['excess_jumps']} ({j['per_page']:.2f} per page over {j['pages_counted']} counted pages of {j['page_count']}; transitions {j['transitions']}, columns {j['columns']} on {j['pages_with_2plus_columns']} multi-column pages). {tail}"
            )


def report(res: dict) -> None:
    if res.get("book"):
        log(res["book"])
    t, x = (res["totals"], res["text_and_furniture"])
    lb = res.get("labelled") or {}
    if lb.get("yes") or lb.get("no"):
        log(
            f"truth says which pages are labelled: yes {lb['yes']}, no {lb['no']}, not said {lb['not_said']} -- only the pages that say yes were compared"
        )
    log(f"artefacts {t['artifacts']}, found {t['found']} ({t['share'] * 100:.0f}%)")
    for why, n in res["troubles"].items():
        log(f"  {why}: {n}")
    if x["block_count"]:
        note = ""
        if x.get("pages_with_text_markup", 0) < x.get("pages_total", 0):
            note = f" — counted over {x['pages_with_text_markup']} pages of {x['pages_total']}, text not marked on the rest"
        log(
            f"text and furniture: blocks {x['block_count']}, found {x['found']} ({x['share'] * 100:.0f}%){note}"
        )
    else:
        log(
            "text and furniture: NOT MARKED in this truth — nothing to compare (this is not zero completeness)"
        )
    if res.get("sense") and res["sense"]["share"] is None:
        log(
            "SENSE WHOLE: no artefact in the truth on the compared pages — nothing to lose whole (this is not zero)"
        )
    elif res.get("sense"):
        c = res["sense"]
        log(
            f"SENSE WHOLE: {c['intact']}/{c['objects']} ({c['share'] * 100:.0f}%) — cropped {c['cropped']}, merged {c['merged']}, called text {c['called_text']}, not seen {c['not_seen']} (object inside the box from {c['threshold_fits']:.2f}, neighbour from {c['threshold_neighbour']:.2f})"
        )
    miss = {k: v for k, v in res["by_label"].items() if v["found"] < v["truth"]}
    if miss:
        log(
            "  misses by label: "
            + ", ".join((f"{k} {v['found']}/{v['truth']}" for k, v in miss.items()))
        )
    _report_order(res)
    n_pairs = sum(res["label_confusion"].values())
    log(f"bucket confusion: {role_errors(res)} of {n_pairs} pairs")
    voc = label_alphabet(res)
    if not voc:
        t_lab = sorted({k.split("->", 1)[0] for k in res["label_confusion"]})
        m_lab = sorted({k.split("->", 1)[1] for k in res["label_confusion"]})
        log(
            f"label confusion: NOT COMPARED — truth and model answer in different vocabularies (truth fits {_fits(t_lab) or '—'}, model {_fits(m_lab) or '—'}; labels in common {len(set(t_lab) & set(m_lab))} of {len(set(t_lab) | set(m_lab))}). This is NOT 100% errors: `table` and `Table` are the same thing, and we have no translation between vocabularies, nor should we."
        )
    else:
        bad = {
            k: v
            for k, v in res["label_confusion"].items()
            if k.split("->", 1)[0] != k.split("->", 1)[1]
        }
        log(
            f"label confusion: {label_errors(res)} of {n_pairs} pairs (one vocabulary: {', '.join(voc)})"
            + (f" — {bad}" if bad else "")
        )
    for case, c in sorted(
        res["by_case"].items(), key=lambda kv: kv[1]["found"] - kv[1]["artifacts"]
    ):
        if c["found"] < c["artifacts"] or c["troubles"]:
            log(
                f"  {case:24s} {c['found']}/{c['artifacts']}  "
                + ", ".join((f"{k} {v}" for k, v in sorted(c["troubles"].items())))
            )


def _columns_of(p, wide=None, roles=None, pol=None):
    pol = pol or policy.UNION
    w = float(p.get("width") or 0.0)
    wd = COLUMN_WIDE if wide is None else wide
    keep = set(COLUMN_ROLES if roles is None else roles)
    part, rest = ([], [])
    for b in p["blocks"]:
        if pol.role(b["label"]) in keep and (w <= 0 or b["box"][2] - b["box"][0] < wd * w):
            part.append(b)
        else:
            rest.append(b)
    return (part, rest)


def _mix_columns(M, overlap=None, wide=None, min_boxes=None, roles=None, pol=None):
    out = {}
    for i, p in M.items():
        part, rest = _columns_of(p, wide, roles, pol)
        buckets = {}
        for c, b in zip(_columns([b["box"] for b in part], overlap), part, strict=True):
            buckets.setdefault(c, []).append(b)
        mixed = []
        while any(buckets.values()):
            for c in sorted(buckets):
                if buckets[c]:
                    mixed.append(buckets[c].pop(0))
        out[i] = {**p, "blocks": mixed + rest}
    return out


def _one_column(M):
    out = {}
    for i, p in M.items():
        w = float(p.get("width") or 0.0) or 1000.0
        x0, x1 = (0.1 * w, 0.5 * w)
        out[i] = {
            **p,
            "blocks": [{**b, "box": [x0, b["box"][1], x1, b["box"][3]]} for b in p["blocks"]],
        }
    return out


def _one_box(M, pol=None):
    out = {}
    for i, p in M.items():
        part, rest = _columns_of(p, pol=pol)
        out[i] = {**p, "blocks": part[:1] + rest}
    return out


def _by_reading(M, overlap=None, wide=None, min_boxes=None, roles=None):
    from metrics import order

    out = {}
    for i, p in M.items():
        bs = p["blocks"]
        idx = order.permutation(
            [b.get("label") for b in bs],
            [b["box"] for b in bs],
            p.get("width"),
            p.get("height"),
            i,
            None,
            which="ours",
        )
        out[i] = {**p, "blocks": [bs[k] for k in idx]}
    return out


def _by_columns(M, overlap=None, wide=None, min_boxes=None, roles=None, pol=None):
    out = {}
    for i, p in M.items():
        part, rest = _columns_of(p, wide, roles, pol)
        col = _columns([b["box"] for b in part], overlap)
        order = sorted(
            range(len(part)), key=lambda k: (col[k], part[k]["box"][1], part[k]["box"][0])
        )
        out[i] = {**p, "blocks": [part[k] for k in order] + rest}
    return out


def _order_variants(M, pol=None):
    return {
        "as_model_gave": lambda **par: M,
        "top_down_left_right": lambda **par: _by_reading(M, **par),
        "column_by_column": lambda **par: _by_columns(M, pol=pol, **par),
        "round_robin_columns": lambda **par: _mix_columns(M, pol=pol, **par),
    }


SENSE_WHOLE = 0.9
SENSE_NEIGHBOUR = 0.5


def sense(T: dict, M_: dict, tp=None, mp=None) -> dict:
    arte_t = set((tp or policy.UNION).artefacts())
    arte_m = set((mp or policy.UNION).artefacts())
    out = {
        "objects": 0,
        "intact": 0,
        "cropped": 0,
        "merged": 0,
        "called_text": 0,
        "not_seen": 0,
        "threshold_fits": SENSE_WHOLE,
        "threshold_neighbour": SENSE_NEIGHBOUR,
        "per": {k: {} for k in ("intact", "cropped", "merged", "called_text", "not_seen")},
    }
    for i, t in sorted(T.items()):
        if i not in M_:
            continue
        mb = [b["box"] for b in M_[i]["blocks"] if b["label"] in arte_m]
        ob = [b["box"] for b in M_[i]["blocks"] if b["label"] not in arte_m]
        tb = [b for b in t["blocks"] if b["label"] in arte_t]
        for b in tb:
            out["objects"] += 1
            fits = [x for x in mb if cover(b["box"], x) >= SENSE_WHOLE]
            if not fits:
                if any((cover(b["box"], x) >= 0.5 for x in mb)):
                    fate = "cropped"
                elif any((cover(b["box"], x) >= SENSE_WHOLE for x in ob)):
                    fate = "called_text"
                else:
                    fate = "not_seen"
            else:
                alone = [
                    x
                    for x in fits
                    if not any((o is not b and cover(o["box"], x) >= SENSE_NEIGHBOUR for o in tb))
                ]
                fate = "intact" if alone else "merged"
            out[fate] += 1
            out["per"][fate][page.anchor(i, b["block_id"])] = 1
    n = out["objects"]
    out["share"] = out["intact"] / n if n else None
    return out


def _order(part: dict) -> Scalar:
    return Scalar(
        part.get("agreement"),
        over=(part.get("page_count", 0), part.get("pages_total", 0)),
        unit="pages",
        why=None if part.get("agreement") is not None else part.get("why") or "not compared",
        per=part.get("per"),
    )


class ContourMetric(Metric):
    name = "contour"
    needs = frozenset({"truth", "pages"})
    scalars = (
        Spec(
            "artefacts_found",
            "higher",
            "tables and pictures found",
            "How much of the book survived",
            per="block",
            side="truth",
        ),
        Spec(
            "text_furniture_found",
            "higher",
            "text and furniture found",
            "How much of the book survived",
            per="block",
            side="truth",
            unit="pages",
        ),
        Spec(
            "sense_whole",
            "higher",
            "objects whose meaning arrived whole",
            per="block",
            side="truth",
        ),
        Spec(
            "assembly_order",
            "higher",
            "reading order of the assembled book agrees with truth",
            "Is the order right",
            per="page",
            unit="pages",
        ),
        Spec(
            "model_order",
            "higher",
            "the model's own rank agrees with truth",
            per="page",
            unit="pages",
        ),
        Spec(
            "artefacts_not_seen",
            "lower",
            "artefacts the model never boxed",
            "What failed, and how",
            per="block",
            side="truth",
        ),
        Spec(
            "artefacts_cropped",
            "lower",
            "artefacts boxed, but cut short",
            "What failed, and how",
            per="block",
            side="truth",
        ),
        Spec(
            "artefacts_called_text",
            "lower",
            "artefacts boxed as text: they leave as a line and the structure leaves with them",
            "What failed, and how",
            per="block",
            side="truth",
        ),
        Spec(
            "artefacts_merged",
            "neither",
            "artefacts sharing a box with a neighbour; no direction, since a wider picture is split at level two",
            "What failed, and how",
            per="block",
            side="truth",
        ),
        Spec(
            "label_errors",
            "lower",
            "blocks whose label is not the truth's",
            per="block",
            side="run",
        ),
        Spec(
            "role_errors", "lower", "blocks whose role is not the truth's", per="block", side="run"
        ),
    )

    def run(self, bench, run) -> Record:
        res = compare(bench.truth_dir, run.pages_dir, bench.policy, run.policy)
        return self.record(res, bench.name, run.label)

    def run_loaded(self, bench, run, truth, pages, note, want=None) -> Record:
        res = compare_pages(truth, pages, bench.policy, run.policy)
        res["book"] = f"{note}; {_same_raster(truth, pages)}"
        return self.record(res, bench.name, run.label)

    def record(self, res: dict, bench_name: str, run_label: str) -> Record:
        t, x, s, j = (res["totals"], res["text_and_furniture"], res["sense"], res["jumps"])
        lab, rol, per = (label_errors(res), role_errors(res), res["per"])
        pairs = sum(res["label_confusion"].values())
        no_pair = "no truth block was matched to a model block"
        scalars = {
            "artefacts_found": Scalar(
                t["share"] if t["artifacts"] else None,
                count=(t["found"], t["artifacts"]),
                why=None if t["artifacts"] else "no artefact in the truth",
                per=per["artefacts_found"],
                side="truth",
            ),
            "sense_whole": Scalar(
                s["share"],
                count=(s["intact"], s["objects"]),
                why=None if s["share"] is not None else "no artefact in the truth",
                per=s["per"]["intact"],
                side="truth",
            ),
            **{
                f"artefacts_{k}": Scalar(
                    s[k] / s["objects"] if s["objects"] else None,
                    count=(s[k], s["objects"]),
                    why=None if s["objects"] else "no artefact in the truth",
                    per=s["per"][k],
                    side="truth",
                )
                for k in ("merged", "cropped", "called_text", "not_seen")
            },
            "text_furniture_found": Scalar(
                x["share"],
                count=(x["found"], x["block_count"]),
                over=(x.get("pages_with_text_markup", 0), x.get("pages_total", 0)),
                unit="pages",
                why=None
                if x["share"] is not None
                else "text and furniture NOT MARKED in this truth",
                per=per["text_furniture_found"],
                side="truth",
            ),
            "label_errors": Scalar(
                lab / pairs if lab is not None and pairs else None,
                count=None if lab is None else (lab, pairs),
                why=None
                if lab is not None and pairs
                else "the two sides speak different label vocabularies; not compared"
                if lab is None
                else no_pair,
                per=per["label_errors"] if lab is not None else None,
                side="run",
            ),
            "role_errors": Scalar(
                rol / pairs if pairs else None,
                count=(rol, pairs),
                why=None if pairs else no_pair,
                per=per["role_errors"],
                side="run",
            ),
            "model_order": _order(res["model_order"]),
            "assembly_order": _order(res["assembly_order"]),
        }
        params = {
            "COVER_MATCH": COVER_MATCH,
            "TOUCH": TOUCH,
            "TOL_PX": TOL_PX,
            "SENSE_WHOLE": SENSE_WHOLE,
            "SENSE_NEIGHBOUR": SENSE_NEIGHBOUR,
        }
        params.update({f"COLUMN_{k}": v for k, v in (j.get("params") or {}).items()})
        detail = {k: v for k, v in res.items() if k != "pairs"}
        return Record(self.name, bench_name, run_label, scalars, params, detail)

    def report(self, rec: Record) -> None:
        report(rec.detail)
