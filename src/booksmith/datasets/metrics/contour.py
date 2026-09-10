"""Contour metrics: how correctly the model outlined tables, figures, charts.

Takes truth pages and a run's pages, returns a Record. Three numbers stay
separate -- localisation blind to the label, label confusion on what was
found, reading order (the model rank, the assembly order the reader gets,
excess column jumps without truth) -- because one combined score is cured by
trading one fault for another. Named trouble counters stand beside them:
"found 0 of 3" does not say whether the model missed the artefacts or merged
them into one box.
"""

from booksmith.core import page, policy
from booksmith.datasets import bench as bench_mod
from booksmith.core.errors import Unmeasurable
from booksmith.datasets.metrics.base import Metric, Record, Scalar, Spec
from booksmith.core.log import log

# The one match gate: two-sided cover, so a box neither crops truth nor spills.
COVER_MATCH = 0.75
# Below this overlap share boxes do not intersect: a corner touch is no sighting.
TOUCH = 0.10
# Edge tolerance in raster pixels (PAGE_DPI); on a small block three pixels a
# side take an area share from 0.75 to 0.58, so the share alone is too strict.
TOL_PX = 6.0


class MetricError(Unmeasurable):
    pass


def _load(d, what="pages"):
    """The one loader, `core.page.load_pages`, under this metric's error class;
    `what` names the side being read, so a bad truth directory is not reported
    as bad model boxes."""
    try:
        return page.load_pages(d, what)
    except Unmeasurable as e:
        raise MetricError(str(e)) from None


def _same_book(truth_dir: str, detect_dir: str) -> str:
    """Are truth and model output about the same PDF, by the source sha256 both
    snapshots carry and not by directory name; otherwise one book's truth
    scores another's boxes and prints a sensible-looking number."""
    # The check itself is `bench.same_book`; this keeps the two-directory
    # signature and the error class.
    from booksmith.datasets import bench as _bench
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
    x0, y0 = max(a[0], b[0]), max(a[1], b[1])
    x1, y1 = min(a[2], b[2]), min(a[3], b[3])
    return max(0.0, x1 - x0) * max(0.0, y1 - y0)


def _area(a):
    return max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])


def iou(a, b):
    i = _inter(a, b)
    u = _area(a) + _area(b) - i
    return 0.0 if u <= 0 else i / u


def cover(a, b):
    """What share of `a` is covered by `b`. The two-sided pair
    cover(t,m)/cover(m,t) tells a crop (first small) from a spill (second)."""
    s = _area(a)
    return 0.0 if s <= 0 else _inter(a, b) / s



def extra_kind(box, paired, unpaired, outside, tb) -> str:
    """What to call a model artefact box with no partner in truth. Public
    because `overlay` names boxes by the same rule. The branches are a chain: a
    box inside scored truth is a duplicate before we ask about outside scoring."""
    if any(cover(box, b) >= 0.9 for b in paired):
        return "nested duplicate"
    if any(cover(box, b) >= 0.9 for b in unpaired):
        return "inside a miss"
    if (any(cover(box, b) >= 0.5 or cover(b, box) >= 0.5 for b in outside)
            # ...unless it swallowed truth artefacts too: a full-page box
            # meets any drop cap.
            and sum(1 for b in tb if cover(b["box"], box) >= 0.6) < 2):
        return "on an object outside scoring"
    return "spurious_box"


def _pad(b, d):
    return (b[0] - d, b[1] - d, b[2] + d, b[3] + d)


def matches(t_box, m_box) -> bool:
    """A match: two-sided cover measured with an edge tolerance. The tolerance
    goes into the cover and not into a separate all-four-edges branch, which
    gives a cliff a few pixels wide."""
    return (cover(t_box, _pad(m_box, TOL_PX)) >= COVER_MATCH
            and cover(m_box, _pad(t_box, TOL_PX)) >= COVER_MATCH)


def _pick(b, boxes, used):
    """The best uncaught candidate for block `b`, or None. An empty candidate
    list must give None: a default index would stitch truth to the last box on
    the page."""
    cand = [(iou(b["box"], x["box"]), j) for j, x in enumerate(boxes)
            if j not in used and matches(b["box"], x["box"])]
    if not cand:
        return None
    return max(cand)[1]


def _diagnose(t, mine, others_truth, arte):
    """Name the trouble. Branches run from the specific to the general."""
    touching = [m for m in mine if cover(t["box"], m["box"]) >= TOUCH
                or cover(m["box"], t["box"]) >= TOUCH]
    if not touching:
        return "not seen"
    best = max(touching, key=lambda m: iou(t["box"], m["box"]))
    ct, cm = cover(t["box"], best["box"]), cover(best["box"], t["box"])
    eaten = [o for o in others_truth
             if o is not t and cover(o["box"], best["box"]) >= 0.6]
    if eaten and ct >= 0.6:
        return "merge"
    # Fragmentation counts artefact boxes only: a table covered by text boxes
    # is a dearer trouble and has its own name below.
    inside = [m for m in touching if m["label"] in arte
              and cover(m["box"], t["box"]) >= 0.7]
    if len(inside) >= 2:
        return "fragmentation"
    if policy.role(best["label"]) == "text" and ct >= 0.6:
        return "eaten by text"
    if ct < 0.85 and cm >= 0.85:
        return "crop"
    if cm < 0.6:
        return "spill"
    return "near, but no match"


def _same_raster(T: dict, M: dict) -> str:
    """Are both sides' coordinates written in the same raster. Page SIZE is
    compared, not the `dpi` label: one size comes from several dpi, and boxes in
    two rasters give a plausible false number instead of a refusal."""
    common = sorted(set(T) & set(M))
    if any(k not in p for i in common for p in (T[i], M[i])
           for k in ("width", "height")):
        return "raster NOT CHECKED: pages have no width/height fields"
    dt = sorted({T[i].get("dpi") for i in common}, key=str)
    dm = sorted({M[i].get("dpi") for i in common}, key=str)
    bad = [f"p.{i}: truth {T[i]['width']}x{T[i]['height']}, "
           f"model {M[i]['width']}x{M[i]['height']}" for i in common
           if (T[i]["width"], T[i]["height"]) != (M[i]["width"], M[i]["height"])]
    if bad:
        raise MetricError(
            f"truth and model output are in DIFFERENT rasters: coordinates "
            f"in different systems, and the number would come out plausible "
            f"and false. {len(bad)} pages of {len(common)} differ: "
            + "; ".join(bad[:3])
            + (" …" if len(bad) > 3 else "")
            + f". dpi: truth {dt}, model {dm} — see the run's PAGE_DPI.")
    note = f"raster checked: {len(common)} pages, sizes agree"
    if dt != dm:
        note += (f"; the dpi label DIFFERS (truth {dt}, model {dm}) — no "
                 f"effect on coordinates, one raster")
    return note


def compare(truth_dir: str, detect_dir: str) -> dict:
    """Score model output against truth. Numbers and named counters."""
    T, M = _load(truth_dir, "truth"), _load(detect_dir, "model boxes")
    note = f"{_same_book(truth_dir, detect_dir)}; {_same_raster(T, M)}"
    res = compare_pages(T, M)
    res["book"] = note
    return res


def compare_pages(T: dict, M: dict) -> dict:
    missing = sorted(set(T) - set(M))
    if missing:
        raise MetricError(
            f"the model marked up no pages {missing[:5]}: nothing to "
            f"compare. An empty report here would read as 'matched zero', "
            f"which is another thing.")

    arte = set(policy.artefacts())
    # Order is scored only where truth declares it annotated; a missing flag
    # is not permission.
    states = {}
    for p in T.values():
        st = _truth_order_state(p)
        states[st] = states.get(st, 0) + 1
    # Our order rule always prints: undeclared, a list position tells nobody
    # whose order made it.
    rules = sorted({str((M[i].get("meta") or {}).get(
        "reading_order", "not declared (taken as 'model rank')"))
        for i in T if i in M})
    model_rank = all(_model_has_rank(M[i]) for i in T if i in M)
    per_case, conf, ranks = {}, {}, []
    per = {"artefacts_found": {}, "text_furniture_found": {},
           "label_errors": {}, "role_errors": {}}
    ceiling = order_pages = 0
    tot = {"artifacts": 0, "found": 0}
    # Text completeness counts only pages where text is annotated.
    txt = {"block_count": 0, "found": 0, "pages_with_text_markup": 0,
           "pages_total": 0}
    # Completeness per truth label: one number over thirteen labels hides a
    # label at zero finds.
    per_label = {}
    beds = {}
    for i, t in sorted(T.items()):
        m = M[i]
        case = t.get("meta", {}).get("case", str(i))
        tb = [b for b in t["blocks"] if b["label"] in arte]
        mb = [b for b in m["blocks"] if b["label"] in arte]
        mall = m["blocks"]
        used, pairs = set(), []
        for b in tb:
            j = _pick(b, mb, used)
            if j is None:
                pairs.append((b, None))
            else:
                used.add(j)
                pairs.append((b, mb[j]))
        found = sum(1 for _, x in pairs if x is not None)
        c = per_case.setdefault(case, {"artifacts": 0, "found": 0,
                                       "troubles": {}})
        c["artifacts"] += len(tb)
        c["found"] += found
        tot["artifacts"] += len(tb)
        tot["found"] += found

        def bed(name, n=1, c=c):
            c["troubles"][name] = c["troubles"].get(name, 0) + n
            beds[name] = beds.get(name, 0) + n

        for b, x in pairs:
            if x is not None:
                per_label.setdefault(b["label"], [0, 0])[0] += 1
                per["artefacts_found"][page.anchor(i, b["block_id"])] = 1
                continue
            bed(f"{_diagnose(b, mall, tb, arte)} ({b['label']})")
        # Model artefact boxes with no partner in truth. Nesting is measured
        # against PAIRED truth boxes: a fragment of an artefact never found is
        # a miss, not a duplicate of a missing original.
        paired = [b["box"] for b, x in pairs if x is not None]
        unpaired = [b["box"] for b, x in pairs if x is None]
        # Boxes on objects outside scoring are not spurious: that boundary is
        # ours, not a fault of the model.
        outside = [o["box"] for o in
                   (t.get("meta", {}).get("out_of_scope") or [])]
        for j, x in enumerate(mb):
            if j in used:
                continue
            # The naming rule lives in `extra_kind`; here only the counting.
            bed(extra_kind(x["box"], paired, unpaired, outside, tb))

        # Pass B: all blocks matched, blind to the label -- artefacts alone
        # give too few pairs for a bench.
        page_ranks, taken = [], set()
        for b in sorted(t["blocks"], key=lambda z: -_area(z["box"])):
            j = _pick(b, mall, taken)
            if j is None:
                continue
            taken.add(j)
            x = mall[j]
            conf[(b["label"], x["label"])] = conf.get((b["label"], x["label"]), 0) + 1
            if b["label"] != x["label"]:
                per["label_errors"][page.anchor(i, x["block_id"])] = 1
            if policy.role(b["label"]) != policy.role(x["label"]):
                per["role_errors"][page.anchor(i, x["block_id"])] = 1
            # Third member: the position in `mall`, the list
            # `assemble/html.py` walks and the book is assembled by.
            page_ranks.append((b.get("order"), x.get("order"), j))
            if (b["label"] not in arte
                    and _truth_text_state(t) == "yes"):
                txt["found"] += 1
                per["text_furniture_found"][page.anchor(i, b["block_id"])] = 1
                # Artefact labels count in pass A only: pass B is blind to
                # the label and a table caught by a text box would read found.
                per_label.setdefault(b["label"], [0, 0])[0] += 1
        for b in t["blocks"]:
            per_label.setdefault(b["label"], [0, 0])[1] += 1
        txt["pages_total"] += 1
        if _truth_text_state(t) == "yes":
            txt["pages_with_text_markup"] += 1
            txt["block_count"] += len([b for b in t["blocks"]
                                  if b["label"] not in arte])
        # Reading order is scored within a page: a rank is a row number in
        # that page's output, and the next page starts its own numbering.
        if _truth_order_state(t) == ORDER_MARKED:
            ranks.append((i, page_ranks))
            ceiling += _pairs_ceiling(t)
            order_pages += 1

    tot["share"] = (tot["found"] / tot["artifacts"]) if tot["artifacts"] else 0.0
    # Zero blocks is not zero completeness: truth may annotate no text at all.
    txt["share"] = (txt["found"] / txt["block_count"]) if txt["block_count"] else None
    # The reason for silence is named: "not marked" is the bench itself,
    # "not said" a hole in its builder.
    why_order = ""
    if not order_pages:
        why_order = ("truth carries no order: " + ", ".join(
            f"{k} on {states[k]}" for k in
            (ORDER_MARKED, ORDER_UNMARKED, ORDER_SILENT) if states.get(k))
            + f" of {len(T)} pages")
    return {"totals": tot, "sense": sense(T, M), "text_and_furniture": txt,
            "by_case": per_case,
            "by_label": {k: {"truth": v[1], "found": v[0],
                               "bucket": policy.role(k)}
                           for k, v in sorted(per_label.items())},
            "troubles": dict(sorted(beds.items())),
            "label_confusion": {f"{a}->{b}": n for (a, b), n in sorted(conf.items())},
            "order_truth": {"states": states, "page_count": len(T)},
            "order_rule": ", ".join(rules) or "nothing to declare",
            # Two questions: the model rank needs a real rank on both sides,
            # the book's assembly order exists rank or not.
            "model_order": _order_agree(
                ranks, 1, ceiling, order_pages, len(T),
                why_order or ("" if model_rank else
                              f"the model gives no rank "
                              f"({', '.join(rules)})")),
            "assembly_order": _order_agree(
                ranks, 2, ceiling, order_pages, len(T), why_order),
            "jumps": column_jumps(M),
            "per": per}


# ------------------------------------------------------------- READING ORDER
# Three states, not two, and separate report lines: "not said" (no field) is a
# hole in the bench builder, "not marked" the bench itself, and neither is
# permission to score order.
ORDER_MARKED = "marked"
ORDER_UNMARKED = "not marked"
ORDER_SILENT = "not_said"


def order_rule(pages: dict) -> str:
    """Which order a page list is in, as the pages themselves declare it. One
    reader for the contour and the assembly metric both, and it takes the run's
    pages alone: assembly has no truth."""
    rules = sorted({str((p.get("meta") or {}).get(
        "reading_order", "not declared (taken as 'model rank')"))
        for p in pages.values()})
    return ", ".join(rules) or "nothing to declare"


def _truth_text_state(page) -> str:
    """What truth says about its own TEXT markup: the same three states, and
    for the same reason. A missing flag is not "annotated": scored as one, a
    share taken from a single marked page prints as the whole bench's."""
    return bench_mod.trait_state(page.get("meta") or {}, "text_marked")


def _truth_order_state(page) -> str:
    """What truth says about its own reading order: one of three states. No
    default is possible -- a missing flag answers "the file did not say", not
    "annotated". The model side differs; why is in `_model_has_rank`."""
    m = page.get("meta") or {}
    if "order_marked" not in m:
        return ORDER_SILENT
    return ORDER_MARKED if m["order_marked"] else ORDER_UNMARKED


def _model_has_rank(page) -> bool:
    """Does the model output carry a real rank rather than our own numbering.
    Adapters write `reading_order` into the page meta; a missing field is taken
    as a model rank, and our order rule prints as its own field beside it."""
    # "Is this our order" lives in `core/page.ours_order`; only the default is
    # local, a missing field meaning "model rank" here and "unknown" in html.
    from booksmith.core.page import ours_order
    v = (page.get("meta") or {}).get("reading_order", "model_rank")
    return not ours_order(v)


def _pairs_ceiling(t) -> int:
    """How many block pairs this page's truth could yield at all: the
    denominator that stands beside the share. Only pairs of DIFFERENT rank
    count -- an equal-rank pair is never scored."""
    o = [b.get("order") for b in t["blocks"]
         if isinstance(b.get("order"), (int, float))]
    return sum(1 for i in range(len(o)) for j in range(i + 1, len(o))
               if o[i] != o[j])


def _order_agree(by_page, idx: int, ceiling: int, pages: int,
                 of_pages: int, why: str = "") -> dict:
    """The share of agreeing pairs, page by page. `idx` says whose order is
    scored: 1 the model rank, 2 the block position in the page list, which
    `assemble/html.py` never sorts and the book therefore gets."""
    if why:
        return {"pairs": 0, "agreement": None, "pairs_possible": ceiling,
                "page_count": pages, "pages_total": of_pages, "why": why}
    ok = bad = norank = 0
    per = {}
    for index, pairs in by_page:
        pp = [(z[0], z[idx]) for z in pairs
              if z[0] is not None and z[idx] is not None]
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
    return {"pairs": n, "agreement": (ok / n) if n else None,
            "pairs_possible": ceiling, "page_count": pages,
            "pages_total": of_pages, "blocks_without_rank": norank,
            "per": per}


# ------------------------------------- EXCESS JUMPS BETWEEN COLUMNS
# The assembly order WITHOUT TRUTH, for the real scans nobody annotated: how
# many times assembly jumps between columns beyond the unavoidable. Walking k
# columns costs no less than k-1 transitions, so zero means every column was
# read straight through, and a two-column dictionary read line-left-line-right
# yields as many jumps as lines.
#
# A column here is geometry, not meaning: the lawful "formula -- its number at
# the right margin -- next formula" counts as jumps. The cure is not tuned
# thresholds, which would hide the real fault too, but the parameters below
# riding into the answer and the printout, so that two runs compare.
COLUMN_OVERLAP = 0.5   # x-overlap share of the narrower box for two to be one column
COLUMN_WIDE = 0.60     # from this share of page width a box is full-width: it has no column
COLUMN_MIN_BOXES = 2   # fewer counted boxes on a page and the quantity is undefined
COLUMN_ROLES = ("artifact", "text")  # buckets counted; furniture would glue the columns


def column_params(overlap=None, wide=None, min_boxes=None, roles=None) -> dict:
    """The grouping parameters in force, not the declared defaults. Its own
    function because they ride into the count, the returned dict and the
    printout alike, and a second copy would drift in silence."""
    return {"x_overlap_of_narrow_box":
            COLUMN_OVERLAP if overlap is None else overlap,
            "full_width_box_share":
            COLUMN_WIDE if wide is None else wide,
            "min_boxes_per_page":
            COLUMN_MIN_BOXES if min_boxes is None else min_boxes,
            "buckets_counted": list(COLUMN_ROLES if roles is None else roles)}


def _columns(boxes, overlap=None) -> list:
    """A column number for each box: connected groups by x-overlap, not
    clusters by centre, so the chain "A overlaps B, B overlaps C" survives a
    floating setting edge. Numbers run left to right, so it reads by eye."""
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
            a, b = boxes[i], boxes[j]
            ovl = min(a[2], b[2]) - max(a[0], b[0])
            w = min(a[2] - a[0], b[2] - b[0])
            if w > 0 and ovl >= ov * w:
                par[find(i)] = find(j)
    groups = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    left = sorted(groups, key=lambda r: min(boxes[i][0] for i in groups[r]))
    num = {r: k for k, r in enumerate(left)}
    return [num[find(i)] for i in range(n)]


def column_jumps(M: dict, overlap=None, wide=None, min_boxes=None,
                 roles=None) -> dict:
    """Excess column jumps of the assembly order; no truth needed. The order is
    the block position in the page list, which `assemble/html.py` walks without
    sorting. Too few counted boxes yield no value, and never a zero."""
    par = column_params(overlap, wide, min_boxes, roles)
    ov = par["x_overlap_of_narrow_box"]
    wd = par["full_width_box_share"]
    mn = par["min_boxes_per_page"]
    keep = set(par["buckets_counted"])
    tot_excess = tot_trans = tot_cols = in_count = wide_n = other = 0
    pages = multi = counted = thin = 0
    per_page, columns_by_page = {}, {}
    for i, p in sorted(M.items()):
        w = float(p.get("width") or 0.0)
        part = []
        for b in p["blocks"]:
            if policy.role(b["label"]) not in keep:
                other += 1
                continue
            if w > 0 and (b["box"][2] - b["box"][0]) >= wd * w:
                wide_n += 1
                continue
            part.append(b["box"])
        pages += 1
        in_count += len(part)
        # Below the box minimum a page yields no value: nowhere to jump.
        if len(part) < mn:
            thin += 1
            continue
        counted += 1
        seq = _columns(part, ov)
        ncols = len(set(seq))
        trans = sum(1 for k in range(1, len(seq)) if seq[k] != seq[k - 1])
        # k-1 transitions into a new column are unavoidable; the rest is excess.
        excess = trans - (ncols - 1)
        tot_trans += trans
        tot_cols += ncols
        tot_excess += excess
        multi += ncols >= 2
        columns_by_page[i] = ncols
        if excess:
            per_page[i] = excess
    ok = counted > 0
    why = "" if ok else (
        f"the quantity is UNDEFINED: not one of the {pages} pages gathered "
        f"{mn} counted boxes (counted in all {in_count}, out of the count "
        f"{wide_n} full-width and {other} of other buckets) — nothing to "
        f"jump between. This is NOT zero jumps.")
    return {"excess_jumps": tot_excess if ok else None,
            # The denominator is counted pages, not all pages.
            "per_page": (tot_excess / counted) if ok else None,
            "transitions": tot_trans, "columns": tot_cols, "page_count": pages,
            "pages_counted": counted,
            # Named apart, or the "pages counted" denominator looks like a typo.
            "pages_not_counted_too_few_boxes": thin,
            # A one-column page gives zero by construction; this count says so.
            "pages_with_2plus_columns": multi,
            "boxes_counted": in_count, "full_width_boxes": wide_n,
            "boxes_other_buckets": other,
            "by_page": per_page,
            "columns_by_page": columns_by_page,
            "why": why,
            "params": par}


# --------------------------- SWEEP OVER THE GROUPING PARAMETERS
# The range the quantity roams over as the parameters move off the default, so
# a difference between two runs can be told from the ruler's play. ONE at a
# time, or a cross grid hides an inert parameter among the others;
# `cross=True` gives the grid anyway.
COLUMN_SWEEP = {"overlap": (0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90),
                "wide": (0.50, 0.60, 0.70, 0.80, 1.01),
                "min_boxes": (2, 3, 5)}
_SWEEP_NAMES = {"overlap": "x overlap", "wide": "full-width box",
                "min_boxes": "minimum boxes"}


def _sweep_points(grid: dict, cross: bool) -> list:
    """Sweep points. The first is the declared default: the spread is measured
    from it, and without it there is no telling from what."""
    if cross:
        pts = [{}]
        for k in sorted(grid):
            pts = [dict(p, **{k: v}) for p in pts for v in grid[k]]
        return pts
    return [{}] + [{k: v} for k in sorted(grid) for v in grid[k]]


def _fmt_point(shift: dict) -> str:
    """Name a sweep point in words: WHAT is shifted off the default."""
    if not shift:
        return "default"
    return ", ".join(f"{_SWEEP_NAMES.get(k, k)} {v}"
                     for k, v in sorted(shift.items()))


def column_jumps_ranking(variants: dict, grid: dict = None,
                         cross: bool = False, key: str = "per_page") -> dict:
    """Does the order of the variants hold across the whole sweep; if it flips,
    choosing by this quantity is forbidden. A dict value may be a builder handed
    the point: a variant folded out of columns is rebuilt at every one."""
    names = list(variants)
    pts = _sweep_points(grid or COLUMN_SWEEP, cross)
    vals = {n: [] for n in names}
    # The memo key is the parameters IN FORCE, not the shift: points differing
    # only in `min_boxes` give the same build, and so do `{}` and overlap 0.5.
    made = {}
    for p in pts:
        par = column_params(**p)
        ckey = (par["x_overlap_of_narrow_box"],
                par["full_width_box_share"],
                tuple(par["buckets_counted"]))
        for n in names:
            v = variants[n]
            if not callable(v):
                pages = v
            else:
                if (n, ckey) not in made:
                    made[(n, ckey)] = v(**p)
                pages = made[(n, ckey)]
            vals[n].append(column_jumps(pages, **p)[key])
    flips, ties = [], []
    for a in range(len(names)):
        for b in range(a + 1, len(names)):
            na, nb = names[a], names[b]
            signs = set()
            for va, vb in zip(vals[na], vals[nb], strict=True):
                if va is None or vb is None or va == vb:
                    continue
                signs.add(va < vb)
            if len(signs) > 1:
                flips.append(f"{na} against {nb}")
            elif not signs:
                # A tie at every point is muteness, not stability: such a
                # pair takes no part in the choice.
                ties.append(f"{na} against {nb}")
    # A gap smaller than the quantity's own play over the parameters is not
    # settled, and the next pair may be closer than the ones measured here.
    play = max((mx - mn for mn, mx in
                ((min([v for v in vals[n] if v is not None], default=None),
                  max([v for v in vals[n] if v is not None], default=None))
                 for n in names) if mn is not None), default=None)
    near = None
    if pts and pts[0] == {}:
        gaps = [(abs(vals[names[a]][0] - vals[names[b]][0]),
                 f"{names[a]} against {names[b]}")
                for a in range(len(names)) for b in range(a + 1, len(names))
                if vals[names[a]][0] is not None
                and vals[names[b]][0] is not None
                and vals[names[a]][0] != vals[names[b]][0]]
        near = min(gaps) if gaps else None
    return {"quantity": key, "points": len(pts), "variants": len(names),
            "pairs": len(names) * (len(names) - 1) // 2,
            "flipped_pairs": flips,
            "tied_pairs": ties,
            "pairs_distinguished": len(names) * (len(names) - 1) // 2 - len(ties),
            "ruler_play": play,
            "closest_pair_at_default": near,
            "stable": not flips,
            "ranges": {n: (min([v for v in vals[n] if v is not None],
                                default=None),
                            max([v for v in vals[n] if v is not None],
                                default=None)) for n in names},
            "by_point": [{"point": _fmt_point(p),
                           "values": {n: vals[n][k] for n in names}}
                          for k, p in enumerate(pts)]}


def _fits(labels) -> list:
    """Which declared vocabularies hold ALL of these labels at once."""
    have = set(labels)
    return sorted(n for n, t in policy.POLICIES.items() if have <= set(t))


def label_alphabet(res: dict) -> list:
    """Do truth and model speak one vocabulary on the matched pairs: some
    declared policy must hold every label of both sides at once. There is no
    translation between vocabularies; `picture` = `image` would decide for the model."""
    seen = set()
    for k in res["label_confusion"]:
        a, b = k.split("->", 1)
        seen.add(a)
        seen.add(b)
    return _fits(seen)


def label_errors(res: dict):
    """Label errors, or None for "nothing to compare with": zero means the
    model never confused a label, None that the sides answer in different
    vocabularies and a number would pass misunderstanding off as measurement."""
    if not label_alphabet(res):
        return None
    return sum(n for k, n in res["label_confusion"].items()
               if k.split("->", 1)[0] != k.split("->", 1)[1])


def role_errors(res: dict) -> int:
    """Bucket confusion: did the model call an artefact an artefact. Always
    scored, since policy declares a bucket for every vocabulary; coarser than
    the label on purpose, so `table` -> `chart` inside one bucket never lands here."""
    return sum(n for k, n in res["label_confusion"].items()
               if policy.role(k.split("->", 1)[0])
               != policy.role(k.split("->", 1)[1]))


def _report_order(res: dict) -> None:
    """Reading order, a line per question: what truth knows, the model rank,
    the assembly order the reader will see, and excess column jumps. Fused,
    they fall silent about all of them the moment a model gives no rank."""
    st = res["order_truth"]
    n, c = st["page_count"], st["states"]
    if c.get(ORDER_MARKED, 0) < n:
        log(f"truth about order: marked {c.get(ORDER_MARKED, 0)}, "
            f"not marked {c.get(ORDER_UNMARKED, 0)}, "
            f"NOT SAID {c.get(ORDER_SILENT, 0)} of {n} pages")
    # Its own line: "not said" is curable by the bench builder, "not marked"
    # is not curable at all.
    if c.get(ORDER_SILENT):
        log(f"  'not said' IS NOT 'not marked': {c[ORDER_SILENT]} truth "
            f"pages have NO `order_marked` field AT ALL, and a number over "
            f"them would be taken out of nothing (that is how 'agreed 73%' "
            f"printed as a number). Cured by whoever built this bench.")
    for name, key in (("of MODEL reading against truth", "model_order"),
                      ("of book ASSEMBLY against truth", "assembly_order")):
        o = res[key]
        tail = ("" if key == "model_order"
                else f"; our order is built so: {res['order_rule']}")
        if o["agreement"] is None:
            log(f"order {name}: NOT COMPARED — "
                f"{o.get('why', 'no pairs')} "
                f"(this is not zero agreement){tail}")
        else:
            log(f"order {name}: agreed {o['agreement']*100:.0f}%, "
                f"pairs measured {o['pairs']} of {o['pairs_possible']} "
                f"possible by truth, over {o['page_count']} pages of "
                f"{o['pages_total']}"
                + (f", blocks without rank {o['blocks_without_rank']}"
                   if o.get("blocks_without_rank") else "") + tail)
    _report_jumps(res["jumps"])


def _report_jumps(j: dict) -> None:
    """Excess jumps, three answers never to be confused: a dash (no page
    reached `COLUMN_MIN_BOXES`), a computed zero (one column, no transitions),
    a number. The parameters print in all three, or two runs do not compare."""
    par = ", ".join(f"{k} {v}" for k, v in j["params"].items())
    if j["excess_jumps"] is None:
        log(f"excess column jumps: DASH — {j['why']} "
            f"Grouping: {par}")
    else:
        thin = j["pages_not_counted_too_few_boxes"]
        tail = (f"boxes counted {j['boxes_counted']}, out of the count "
                f"{j['full_width_boxes']} full-width and "
                f"{j['boxes_other_buckets']} of other buckets; pages not "
                f"counted {thin} of {j['page_count']} (fewer boxes than the "
                f"minimum); grouping: {par}")
        if not j["pages_with_2plus_columns"]:
            log(f"excess column jumps: 0 — the quantity IS COMPUTED over "
                f"{j['pages_counted']} pages, but this zero is BY "
                f"CONSTRUCTION: not one multi-column page of "
                f"{j['page_count']}, there was nowhere to jump. {tail}")
        else:
            log(f"excess column jumps: {j['excess_jumps']} "
                f"({j['per_page']:.2f} per page over "
                f"{j['pages_counted']} counted pages of {j['page_count']}; "
                f"transitions {j['transitions']}, columns {j['columns']} on "
                f"{j['pages_with_2plus_columns']} multi-column pages). "
                f"{tail}")


def report(res: dict) -> None:
    if res.get("book"):
        log(res["book"])
    t, x = res["totals"], res["text_and_furniture"]
    log(f"artefacts {t['artifacts']}, found {t['found']} "
        f"({t['share']*100:.0f}%)")
    for why, n in res["troubles"].items():
        log(f"  {why}: {n}")
    # Text and furniture are three quarters of truth's blocks.
    if x["block_count"]:
        note = ""
        if x.get("pages_with_text_markup", 0) < x.get("pages_total", 0):
            note = (f" — counted over {x['pages_with_text_markup']} pages "
                    f"of {x['pages_total']}, text not marked on the rest")
        log(f"text and furniture: blocks {x['block_count']}, found "
            f"{x['found']} ({x['share']*100:.0f}%){note}")
    else:
        log("text and furniture: NOT MARKED in this truth — nothing to "
            "compare (this is not zero completeness)")
    if res.get("sense"):
        c = res["sense"]
        log(f"SENSE WHOLE: {c['intact']}/{c['objects']} "
            f"({c['share']*100:.0f}%) — cropped {c['cropped']}, "
            f"merged {c['merged']}, called text {c['called_text']}, "
            f"not seen {c['not_seen']} (object inside the box from "
            f"{c['threshold_fits']:.2f}, neighbour from "
            f"{c['threshold_neighbour']:.2f})")
    miss = {k: v for k, v in res["by_label"].items()
            if v["found"] < v["truth"]}
    if miss:
        log("  misses by label: " + ", ".join(
            f"{k} {v['found']}/{v['truth']}" for k, v in miss.items()))
    _report_order(res)
    n_pairs = sum(res["label_confusion"].values())
    # Buckets always print: the only part of the confusion that crosses a
    # vocabulary border.
    log(f"bucket confusion: {role_errors(res)} of {n_pairs} pairs")
    voc = label_alphabet(res)
    if not voc:
        t_lab = sorted({k.split("->", 1)[0] for k in res["label_confusion"]})
        m_lab = sorted({k.split("->", 1)[1] for k in res["label_confusion"]})
        log(f"label confusion: NOT COMPARED — truth and model answer in "
            f"different vocabularies (truth fits {_fits(t_lab) or '—'}, "
            f"model {_fits(m_lab) or '—'}; labels in common "
            f"{len(set(t_lab) & set(m_lab))} of "
            f"{len(set(t_lab) | set(m_lab))}). This is NOT 100% errors: "
            f"`table` and `Table` are the same thing, and we have no "
            f"translation between vocabularies, nor should we.")
    else:
        bad = {k: v for k, v in res["label_confusion"].items()
               if k.split("->", 1)[0] != k.split("->", 1)[1]}
        log(f"label confusion: {label_errors(res)} of {n_pairs} pairs "
            f"(one vocabulary: {', '.join(voc)})"
            + (f" — {bad}" if bad else ""))
    for case, c in sorted(res["by_case"].items(),
                          key=lambda kv: (kv[1]["found"] - kv[1]["artifacts"])):
        if c["found"] < c["artifacts"] or c["troubles"]:
            log(f"  {case:24s} {c['found']}/{c['artifacts']}  "
                + ", ".join(f"{k} {v}" for k, v in sorted(c["troubles"].items())))


# ------------------------------------------------ what the probes also use
# The column split the jump count is built on, and the four assembly orders
# `column_jumps_ranking` compares; `probes/contour.py` reaches for the same.

def _columns_of(p, wide=None, roles=None):
    """Split a page's blocks into those counted for columns and the rest. The
    parameters are taken, not silently defaulted: a variant folded under one set
    and measured under another stops being what it is called."""
    w = float(p.get("width") or 0.0)
    wd = COLUMN_WIDE if wide is None else wide
    keep = set(COLUMN_ROLES if roles is None else roles)
    part, rest = [], []
    for b in p["blocks"]:
        if (policy.role(b["label"]) in keep
                and (w <= 0 or (b["box"][2] - b["box"][0]) < wd * w)):
            part.append(b)
        else:
            rest.append(b)
    return part, rest


def _mix_columns(M, overlap=None, wide=None, min_boxes=None, roles=None):
    """Blocks dealt round robin over the columns: the worst assembly order at
    these boxes, the ceiling of the scale. The parameters are taken because the
    top must be the top at the parameters it is measured at."""
    out = {}
    for i, p in M.items():
        part, rest = _columns_of(p, wide, roles)
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
    """All boxes into one column: every box gets the same x-interval. The width
    stays under `COLUMN_WIDE` on purpose -- wider, the boxes drop out of the
    count and the zero would come from an empty count, not one column."""
    out = {}
    for i, p in M.items():
        w = float(p.get("width") or 0.0) or 1000.0
        x0, x1 = 0.10 * w, 0.50 * w
        out[i] = {**p, "blocks": [{**b, "box": [x0, b["box"][1], x1,
                                                b["box"][3]]}
                                  for b in p["blocks"]]}
    return out


def _one_box(M):
    """Leave one counted box on the page: the quantity must become a dash, not
    a zero, a jump happening only between boxes. Boxes outside the count stay,
    or the dash would come from an empty count rather than the single box."""
    out = {}
    for i, p in M.items():
        part, rest = _columns_of(p)
        out[i] = {**p, "blocks": part[:1] + rest}
    return out


def _by_reading(M, overlap=None, wide=None, min_boxes=None, roles=None):
    """Our assembly rule, asked of `order.py` and never copied here, or the
    instrument would measure an old rule under the current name. `which="ours"`
    is explicit: the knob would make sweep columns incomparable between runs."""
    from booksmith.core import order
    out = {}
    for i, p in M.items():
        bs = p["blocks"]
        idx = order.permutation([b.get("label") for b in bs],
                                [b["box"] for b in bs],
                                p.get("width"), p.get("height"), i,
                                None, which="ours")
        out[i] = {**p, "blocks": [bs[k] for k in idx]}
    return out


def _by_columns(M, overlap=None, wide=None, min_boxes=None, roles=None):
    """Column by column, top down inside a column: the floor of the scale, zero
    excess jumps by construction, which holds only at the parameters it was
    folded at, so it is refolded at every sweep point."""
    out = {}
    for i, p in M.items():
        part, rest = _columns_of(p, wide, roles)
        col = _columns([b["box"] for b in part], overlap)
        order = sorted(range(len(part)),
                       key=lambda k: (col[k], part[k]["box"][1],
                                      part[k]["box"][0]))
        out[i] = {**p, "blocks": [part[k] for k in order] + rest}
    return out


def _order_variants(M):
    """Four assembly orders over the same boxes, as builders and not ready
    pages: the floor and the ceiling are folded from the very columns the jumps
    are counted over, so they must be refolded at every sweep point."""
    return {"as_model_gave": lambda **par: M,
            "top_down_left_right": lambda **par: _by_reading(M, **par),
            "column_by_column": lambda **par: _by_columns(M, **par),
            "round_robin_columns": lambda **par: _mix_columns(M, **par)}


# ------------------------------------------------- SENSE WHOLE
# What the second level needs beyond a precise box: is the object's SENSE
# whole. A roomier box does no harm -- level two deals with the extra air --
# but a cut-off corner cannot be restored and glued objects cannot be
# separated: they ride into the crop as one picture. So an object is whole when
# a box was found that it FITS INTO (not cropped) and that no neighbouring
# truth object got into (not merged). The losses are named and differ in price:
# cropped, merged, called text, and not seen, the dearest.
SENSE_WHOLE = 0.90     # what share of the object must lie inside the box
SENSE_NEIGHBOUR = 0.5  # from what share of a neighbour a box counts as merged


def sense(T: dict, M_: dict) -> dict:
    """Is the object's sense whole: not cropped, not merged, not called text."""
    arte = set(policy.artefacts())
    out = {"objects": 0, "intact": 0, "cropped": 0, "merged": 0,
           "called_text": 0, "not_seen": 0,
           "threshold_fits": SENSE_WHOLE, "threshold_neighbour": SENSE_NEIGHBOUR,
           "per": {k: {} for k in ("intact", "cropped", "merged",
                                   "called_text", "not_seen")}}
    for i, t in sorted(T.items()):
        if i not in M_:
            continue
        mb = [b["box"] for b in M_[i]["blocks"] if b["label"] in arte]
        # Outlined but called text is a different loss from never seen: a
        # label cures the first, only the model the second.
        ob = [b["box"] for b in M_[i]["blocks"] if b["label"] not in arte]
        tb = [b for b in t["blocks"] if b["label"] in arte]
        for b in tb:
            out["objects"] += 1
            fits = [x for x in mb
                    if cover(b["box"], x) >= SENSE_WHOLE]
            if not fits:
                if any(cover(b["box"], x) >= 0.5 for x in mb):
                    fate = "cropped"
                elif any(cover(b["box"], x) >= SENSE_WHOLE for x in ob):
                    fate = "called_text"
                else:
                    fate = "not_seen"
            else:
                alone = [x for x in fits
                         if not any(o is not b
                                    and cover(o["box"], x) >= SENSE_NEIGHBOUR
                                    for o in tb)]
                fate = "intact" if alone else "merged"
            out[fate] += 1
            out["per"][fate][page.anchor(i, b["block_id"])] = 1
    n = out["objects"]
    out["share"] = (out["intact"] / n) if n else None
    return out


# ------------------------------------------------- the metric, as a Metric ---
# The measurement above returns its dict; this turns it into a `Record` and
# names the thresholds that rode in. Every scalar the report prints as NOT
# COMPARED / NOT MARKED is a None with the report's own reason.
def _order(part: dict) -> Scalar:
    """Agreement over the pages whose truth marks order; none marked, no
    value, and the report's own reason."""
    return Scalar(part.get("agreement"),
                  over=(part.get("page_count", 0), part.get("pages_total", 0)), unit="pages",
                  why=None if part.get("agreement") is not None else part.get("why") or "not compared",
                  per=part.get("per"))


class ContourMetric(Metric):
    """Boxes, labels and order against truth: did a box land where the artefact is, was it called the right thing, is the order right."""
    name = "contour"
    needs = frozenset({"truth", "pages"})
    scalars = (
        Spec("artefacts_found", "higher",
             "tables and pictures found", 'How much of the book survived'),
        Spec("text_furniture_found", "higher",
             "text and furniture found", 'How much of the book survived'),
        Spec("sense_whole", "higher",
             "objects whose meaning arrived whole"),
        Spec("assembly_order", "higher",
             "reading order of the assembled book agrees with truth", 'Is the order right'),
        Spec("model_order", "higher",
             "the model's own rank agrees with truth"),
        Spec("artefacts_not_seen", "lower",
             "artefacts the model never boxed", 'What failed, and how'),
        Spec("artefacts_cropped", "lower",
             "artefacts boxed, but cut short", 'What failed, and how'),
        Spec("artefacts_called_text", "lower",
             "artefacts boxed as text: they leave as a line and the structure leaves with them", 'What failed, and how'),
        Spec("artefacts_merged", "neither",
             "artefacts sharing a box with a neighbour; no direction, since a wider picture is split at level two", 'What failed, and how'),
        Spec("label_errors", "lower",
             "blocks whose label is not the truth's"),
        Spec("role_errors", "lower",
             "blocks whose role is not the truth's"),
    )

    def run(self, bench, run) -> Record:
        res = compare(bench.truth_dir, run.pages_dir)
        return self.record(res, bench.name, run.label)

    def run_loaded(self, bench, run, truth, pages, note) -> Record:
        res = compare_pages(truth, pages)
        res["book"] = f"{note}; {_same_raster(truth, pages)}"
        return self.record(res, bench.name, run.label)

    def record(self, res: dict, bench_name: str, run_label: str) -> Record:
        t, x, s, j = res["totals"], res["text_and_furniture"], res["sense"], res["jumps"]
        lab, rol, per = label_errors(res), role_errors(res), res["per"]
        # One entry per matched (truth, model) block: the denominator both
        # error shares are over.
        pairs = sum(res["label_confusion"].values())
        no_pair = "no truth block was matched to a model block"
        scalars = {
            "artefacts_found": Scalar(t["share"], count=(t["found"], t["artifacts"]),
                                      per=per["artefacts_found"], side="truth"),
            "sense_whole": Scalar(
                s["share"], count=(s["intact"], s["objects"]),
                why=None if s["share"] is not None else "no artefact in the truth",
                per=s["per"]["intact"], side="truth"),
            # The four ways an object is lost, each over the same objects, so
            # with `sense_whole` the five account for every one of them.
            **{f"artefacts_{k}": Scalar(
                (s[k] / s["objects"]) if s["objects"] else None,
                count=(s[k], s["objects"]),
                why=None if s["objects"] else "no artefact in the truth",
                per=s["per"][k], side="truth")
               for k in ("merged", "cropped", "called_text", "not_seen")},
            "text_furniture_found": Scalar(
                x["share"], count=(x["found"], x["block_count"]),
                over=(x.get("pages_with_text_markup", 0), x.get("pages_total", 0)), unit="pages",
                why=None if x["share"] is not None else "text and furniture NOT MARKED in this truth",
                per=per["text_furniture_found"], side="truth"),
            # Shares of the matched pairs: the pair count moves by more than
            # half between models, so a bare count ranks them wrong.
            "label_errors": Scalar(
                lab / pairs if lab is not None and pairs else None,
                count=None if lab is None else (lab, pairs),
                why=None if lab is not None and pairs else (
                    "the two sides speak different label vocabularies; not compared"
                    if lab is None else no_pair),
                per=per["label_errors"] if lab is not None else None, side="run"),
            "role_errors": Scalar(
                rol / pairs if pairs else None, count=(rol, pairs),
                why=None if pairs else no_pair,
                per=per["role_errors"], side="run"),
            "model_order": _order(res["model_order"]),
            "assembly_order": _order(res["assembly_order"]),
            # Excess jumps per page belong to the `assembly` metric alone: that
            # metric IS the column-jump measurement and names whose order it
            # counted, and a second copy would drift.
        }
        params = {"COVER_MATCH": COVER_MATCH, "TOUCH": TOUCH, "TOL_PX": TOL_PX,
                  "SENSE_WHOLE": SENSE_WHOLE, "SENSE_NEIGHBOUR": SENSE_NEIGHBOUR}
        params.update({f"COLUMN_{k}": v for k, v in (j.get("params") or {}).items()})
        return Record(self.name, bench_name, run_label, scalars, params, res)

    def report(self, rec: Record) -> None:
        report(rec.detail)
