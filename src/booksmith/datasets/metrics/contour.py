"""Contour metrics: how correctly the model outlined tables, figures, charts.

Three numbers, kept SEPARATE -- one combined score is cured by trading one
fault for another:

1. **localisation**, blind to the label: is a box where the artefact is;
2. **label confusion**, on what was found: was a table called a table;
3. **reading order**, itself three: the MODEL rank against truth, only when
   both sides carry a real rank; the ASSEMBLY order against truth, which is
   what the reader sees, since `assemble/html.py` runs `for b in page.blocks`
   and
   never sorts, so the book gets the list position and not the rank; and
   excess column jumps, the same assembly with NO TRUTH, for the real scans
   nobody annotated.

Beside them, NAMED trouble counters: "found 0 of 3" alone reads as "does not
see them", where the model sees them and merges them into one box.

WHAT WAS BROKEN HERE, AND WHY IT STAYS IN THE HEADER.

* **The IoU gate was dead by construction.** Two-sided cover `c` bounds IoU
  below by `c/(2-c)` -- 0.6 at c=0.75 -- so `IOU_MATCH = 0.5` never fired and a
  sweep 0.01..0.8 gave the same "found 36". One named gate now, two-sided
  cover; IoU only ranks candidates.

* **An empty candidate list passed the gate.** `max(cand, default=(0.0, -1))`
  made `mb[-1]` stitch truth to the LAST box on the page: the mutation
  "thresholds zeroed" printed 100% and reported "grew" off an index bug, and on
  `decayed`, one page of which has no artefact boxes, that line killed the
  battery with IndexError on probe six of nine.

* **A missing flag was read as a present one.** The guard, then named
  `_has_order` and now `_model_has_rank`, defaulted to `True`, so truth
  silent about its reading order counted as annotated, and
  seven benches of nine printed a percentage off it: hard36 "pairs 211, agreed
  73%" (no flag in any of its 36 files), slovar 89%, matematika 100%,
  spravochnik 99%, katalog 99%, atlas 95%, zhurnal 96%. Detectors had been
  ranked by that. Three answers now: marked, not marked, not said.

* **A quantity without its ruler's parameters compares to nothing.** The
  operator was told "excess jumps 7.0 -> 1.3, four times better"; the SAME
  saved boxes (600 golden pages, docling `off` against `full`) give 2718 ->
  471, i.e. 4.53 -> 0.79 over all 600 pages and 5.24 -> 1.06 per counted page,
  and the old revision is not in git. A 216-point cross sweep (overlap
  0.30..0.99, full-width 0.50..1.01, minimum boxes 1..5, two denominators)
  gives "7.0 -> 1.3" at NO point -- nearest 7.04 -> 1.55 and 6.45 -> 1.33 --
  though each half alone comes easily: 7.0 at "overlap 0.9, wide 0.5", 1.3 at
  "overlap 0.95, wide 0.5". Hence named parameters riding into the answer and
  the printout, and a probe over the variant ORDER survives it.

ON THE ABILITY TO FAIL. `probes/contour.py` feeds spoiled input and demands the
number sag. Three-sided -- model output, TRUTH (a metric indifferent to truth
measures one input and is always right), OUR OWN thresholds -- each apart,
since moved together they hide the inert one.
"""
import json
import os

from booksmith.core import page, policy
from booksmith.datasets import bench as bench_mod
from booksmith.core.errors import Unmeasurable
from booksmith.datasets.metrics.base import Metric, Record, Scalar

# The match gate. ONE, and named: the model box must cover truth (no crop) and
# lie inside it (no spill). Measured: a table torn by the gutter gave IoU 0.51
# on its left half and passed as "found", half the table missing.
COVER_MATCH = 0.75
# Below this overlap share boxes count as not intersecting; without it a corner
# touch reads as "the model sees it".
TOUCH = 0.10
# EDGE tolerance, in raster pixels. An area share lies on a small block: for a
# 24x12 folio the model gave [485,83,514,100] against truth [488,86,512,98] --
# three pixels a side, the same place to the eye, cover 0.58 against threshold
# 0.75, and the report said "found 0 of 11".
TOL_PX = 6.0
# UNITS: raster pixels, i.e. PAGE_DPI. Double PAGE_DPI and the tolerance
# doubles in strictness with no edit here. A share of the page would be fairer,
# but a share is what failed on small blocks.


class MetricError(Unmeasurable):
    pass


def _load(d, what="pages"):
    """The one loader, `core.page.load_pages`, under this metric's own error
    class so that a caller catching `MetricError` still does; `what` names
    the side being read, so a bad truth directory is not reported as bad
    model boxes."""
    try:
        return page.load_pages(d, what)
    except Unmeasurable as e:
        raise MetricError(str(e)) from None


def _same_book(truth_dir: str, detect_dir: str) -> str:
    """Are truth and model output about the same PDF.

    Without it `books score` scores one book's truth against another's boxes
    and prints a sensible-looking number. Both snapshots carry the source PDF
    sha256; we compare those, not directory names.
    """
    # THE ONE CHECK is `datasets.bench.same_book`; this keeps the metric's
    # signature (two directories) and its error class.
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
    """What to CALL a model artefact box with no partner in truth.

    PUBLIC FOR A SECOND CONSUMER: `overlay`, which we look at by eye. It sorted
    boxes by one sign, is the label an artefact, and shouted orange at
    everything -- 508 boxes on the golden bench, of which `books score`
    deliberately does not count 350 (69%) as spurious ("on an object outside
    scoring"), leaving 110. A second copy of the rule would be worse: copies
    drifting apart is a trouble already paid for (knob registry against job
    builder, 13 names of 17). The order of the names is a CHAIN -- a box inside
    scored truth is a duplicate before we ask about "outside scoring".
    """
    if any(cover(box, b) >= 0.9 for b in paired):
        return "nested duplicate"
    if any(cover(box, b) >= 0.9 for b in unpaired):
        return "inside a miss"
    if (any(cover(box, b) >= 0.5 or cover(b, box) >= 0.5 for b in outside)
            # ...but NOT when the same box also covers truth artefacts: a
            # full-page box meets any drop cap, and the amnesty would forgive
            # it the tables it swallowed too.
            and sum(1 for b in tb if cover(b["box"], box) >= 0.6) < 2):
        return "on an object outside scoring"
    return "spurious_box"


def cover_many(a, boxes) -> float:
    """What share of `a` the UNION of the boxes covers.

    Exact, not sampled: clipped rectangles compressed into a coordinate grid,
    area over occupied cells. An approximation is worse than nothing -- this
    number tells "part of the object is gone" from "split across two boxes".

    UNCALLED, AND A DEBT WITH A KNOWN ADDRESS: struck out as dead once, and a
    sceptic reversed the strike. `sense()` covers one box at a time, so a
    half-and-half split lands in "cropped" though the union covers the object
    whole; this is the missing half. Wiring it in moves the golden-bench column
    "cropped 85" -- a change of metric to measure and explain, not a tidy-up.
    """
    ax0, ay0, ax1, ay1 = a
    aw, ah = ax1 - ax0, ay1 - ay0
    if aw <= 0 or ah <= 0:
        return 0.0
    cl = []
    for b in boxes:
        x0, y0 = max(ax0, b[0]), max(ay0, b[1])
        x1, y1 = min(ax1, b[2]), min(ay1, b[3])
        if x1 > x0 and y1 > y0:
            cl.append((x0, y0, x1, y1))
    if not cl:
        return 0.0
    xs = sorted({ax0, ax1, *(v for r in cl for v in (r[0], r[2]))})
    ys = sorted({ay0, ay1, *(v for r in cl for v in (r[1], r[3]))})
    area = 0.0
    for i in range(len(xs) - 1):
        for j in range(len(ys) - 1):
            cx, cy = (xs[i] + xs[i + 1]) / 2, (ys[j] + ys[j + 1]) / 2
            if any(r[0] <= cx <= r[2] and r[1] <= cy <= r[3] for r in cl):
                area += (xs[i + 1] - xs[i]) * (ys[j + 1] - ys[j])
    return area / (aw * ah)

def _pad(b, d):
    return (b[0] - d, b[1] - d, b[2] + d, b[3] + d)


def matches(t_box, m_box) -> bool:
    """A match: two-sided cover measured WITH AN EDGE TOLERANCE.

    The tolerance goes into the cover, not into a separate "all four edges
    within TOL_PX" branch, which gave a CLIFF: a pair differing by 4-5 pixels
    passed on tolerance and, three pixels further, dropped out through cover --
    on the formula book a three-pixel shift took the share from 70% to 59%.
    """
    return (cover(t_box, _pad(m_box, TOL_PX)) >= COVER_MATCH
            and cover(m_box, _pad(t_box, TOL_PX)) >= COVER_MATCH)


def _pick(b, boxes, used):
    """The best uncaught candidate for block `b`, or None. An empty candidate
    list MUST give None; the old revision returned `(0.0, -1)` and took
    `boxes[-1]`."""
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
    # Fragmentation counts ARTEFACT boxes only. Counting text ones gave
    # "missed the table but covered it with text" the name of the cheapest
    # trouble instead of the dearest.
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
    """Are both sides' coordinates written in the same raster.

    A box is page-raster pixels, and the raster betrays itself by its size;
    until now only the book sha256 was checked. Measured on `spravochnik`: the
    same output rescaled from 144 dpi to 150 gives share 0.69 against 0.76 over
    an ordinary-looking trouble list, and at 180 dpi 0.00 -- zero from
    misunderstanding the input, read as the model's zero. SIZE is compared, not
    `dpi`: the same 1021x1402 page comes from a PDF of half the points at twice
    the dpi, so a differing label at a matching size is only said aloud, on the
    sha256 line. The battery does NOT come here -- its probe "markup shifted by
    one page" substitutes a whole page, size included, and rasters diverge
    lawfully on 4 pages of 36.
    """
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
    # Order is scored ONLY on pages whose truth declared it annotated. A
    # missing flag is not permission.
    states = {}
    for p in T.values():
        st = _truth_order_state(p)
        states[st] = states.get(st, 0) + 1
    # OUR order rule always prints: the second report line scores the list
    # position, and undeclared there is no telling whether the model rank or
    # our top-down numbering produced it.
    rules = sorted({str((M[i].get("meta") or {}).get(
        "reading_order", "not declared (taken as 'model rank')"))
        for i in T if i in M})
    model_rank = all(_model_has_rank(M[i]) for i in T if i in M)
    per_case, conf, ranks = {}, {}, []
    ceiling = order_pages = 0
    tot = {"artifacts": 0, "found": 0}
    # Text completeness counts ONLY pages where text is annotated.
    # `bench/hard` mixes 6 synthetic pages (annotated) with 124 AnnoPage ones
    # (not), and the share printed as if taken over all 130.
    txt = {"block_count": 0, "found": 0, "pages_with_text_markup": 0,
           "pages_total": 0}
    # Completeness per truth LABEL. Without it the report was silent about
    # three quarters of the blocks: "text 94%" is one number over thirteen
    # labels, and `header` at zero finds looks like `text` at full.
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

        def bed(name, n=1):
            c["troubles"][name] = c["troubles"].get(name, 0) + n
            beds[name] = beds.get(name, 0) + n

        for b, x in pairs:
            if x is not None:
                per_label.setdefault(b["label"], [0, 0])[0] += 1
                continue
            bed(f"{_diagnose(b, mall, tb, arte)} ({b['label']})")
        # Model artefact boxes with no partner in truth. A nested duplicate is
        # its own trouble: raw output is unsuppressed, so a box inside a scored
        # one is no invention. Nesting is measured against truth boxes THAT
        # HAVE A PARTNER; against every truth box, a fragment of an artefact
        # never found was called a duplicate of a missing original -- 162 cases
        # of 664 on nine benches, 111 pieces of a fragmented box, 48 a single
        # cropped one, a name promising suppression where the trouble was a
        # miss. "Inside a miss" is its own name and not "spurious box": such a
        # box stands on a real artefact. The two names sum to the old counter.
        paired = [b["box"] for b, x in pairs if x is not None]
        unpaired = [b["box"] for b, x in pairs if x is None]
        # Boxes on objects OUTSIDE SCORING are not spurious: golden-bench
        # categories inexpressible for our model (drop cap, vignette) or
        # arguable (advert, sheet music) are a boundary we drew, not a fault of
        # the model.
        outside = [o["box"] for o in
                   (t.get("meta", {}).get("out_of_scope") or [])]
        for j, x in enumerate(mb):
            if j in used:
                continue
            # The rule lives in `extra_kind`, here only the counting: with
            # `overlay` as its second consumer, drift would make picture and
            # number say different things about one box.
            bed(extra_kind(x["box"], paired, unpaired, outside, tb))

        # Pass B: ALL blocks matched, blind to the label. Artefacts alone will
        # not do -- a page often holds one, and the number came out of five
        # pairs for a whole bench.
        page_ranks, taken = [], set()
        for b in sorted(t["blocks"], key=lambda z: -_area(z["box"])):
            j = _pick(b, mall, taken)
            if j is None:
                continue
            taken.add(j)
            x = mall[j]
            conf[(b["label"], x["label"])] = conf.get((b["label"], x["label"]), 0) + 1
            # Third member: the box POSITION in `mall`, the page block list
            # `assemble/html.py` walks and the book is assembled by.
            page_ranks.append((b.get("order"), x.get("order"), j))
            if (b["label"] not in arte
                    and _truth_text_state(t) == "yes"):
                txt["found"] += 1
                # Completeness for ARTEFACT labels comes from pass A: pass B
                # is blind to the label, so a table caught by a `text` box
                # would count as found. That gave 731 against 698 in the same
                # golden-bench report, and "misses by label" was built on the
                # inflated one.
                per_label.setdefault(b["label"], [0, 0])[0] += 1
        for b in t["blocks"]:
            per_label.setdefault(b["label"], [0, 0])[1] += 1
        txt["pages_total"] += 1
        if _truth_text_state(t) == "yes":
            txt["pages_with_text_markup"] += 1
            txt["block_count"] += len([b for b in t["blocks"]
                                  if b["label"] not in arte])
        # Reading order is scored WITHIN a page: the model rank is a row number
        # in its output for that page, and the next page starts elsewhere.
        # Piled into one list they gave 33% agreement, worse than a coin.
        if _truth_order_state(t) == ORDER_MARKED:
            ranks.append(page_ranks)
            ceiling += _pairs_ceiling(t)
            order_pages += 1

    tot["share"] = (tot["found"] / tot["artifacts"]) if tot["artifacts"] else 0.0
    # Zero blocks is NOT zero completeness: AnnoPage annotates only non-text
    # objects, so golden-bench truth holds no text, and "text 0%" would read as
    # "the model lost all the text".
    txt["share"] = (txt["found"] / txt["block_count"]) if txt["block_count"] else None
    # The reason for silence is NAMED: "not marked" (the bench answers "no
    # order here") is the bench, "not said" (no answer) a hole in its builder.
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
            # TWO QUESTIONS, TWO QUANTITIES. The first is about the model and
            # demands a real rank on both sides. The second is about the BOOK,
            # where an assembly order always exists, rank or not.
            "model_order": _order_agree(
                ranks, 1, ceiling, order_pages, len(T),
                why_order or ("" if model_rank else
                              f"the model gives no rank "
                              f"({', '.join(rules)})")),
            "assembly_order": _order_agree(
                ranks, 2, ceiling, order_pages, len(T), why_order),
            "jumps": column_jumps(M)}


# ------------------------------------------------------------- READING ORDER
# Three answers instead of two. A MISSING flag read as `True` made truth that
# never mentioned its reading order count as annotated, and printed a
# percentage off it -- "pairs 211, agreed 73%" on `bench/hard36`, where the
# flag is in none of the 36 files, and detectors had been ranked by that.
# "Not said" and "not marked" are DIFFERENT zeros: the first a hole in the
# bench, one line from its builder away (today 36 of 36 pages of hard36 and 13
# of 13 of slovar are silent); the second the bench itself, since AnnoPage
# annotates no order at all. Hence separate report lines.
ORDER_MARKED = "marked"
ORDER_UNMARKED = "not marked"
ORDER_SILENT = "not_said"


def order_rule(pages: dict) -> str:
    """WHICH ORDER a page list is in, as the pages themselves declare it.

    The contour metric derives this from the model side and reports it; the
    assembly metric measures excess jumps over the same list and had no way
    to say whose order it counted. One reader for both, and it takes the run's
    pages alone -- assembly has no truth.
    """
    rules = sorted({str((p.get("meta") or {}).get(
        "reading_order", "not declared (taken as 'model rank')"))
        for p in pages.values()})
    return ", ".join(rules) or "nothing to declare"


def _truth_text_state(page) -> str:
    """What TRUTH says about its own TEXT markup: one of the same three
    states, and for the same reason.

    A MISSING FLAG READ AS `True` IS THE DEFECT THIS FILE ALREADY RECORDS for
    `order_marked` -- truth that never mentioned its text markup counted as
    annotated, and detectors were ranked by it. `text_marked` was still asked
    with `.get(..., True)` in two places. Measured on `bench/hard36`: 1 page
    of 36 carries the flag at all (the other 35 say `false`), so
    `text_furniture_found` was 0.727 = 8 of 11 blocks taken from ONE page and
    printed as the bench's text number; `bench/hard` did the same over 6 pages
    of 130. `Bench.trait_state` exists to give the three states and was not
    used here.
    """
    return bench_mod.trait_state(page.get("meta") or {}, "text_marked")


def _truth_order_state(page) -> str:
    """What TRUTH says about its own reading order: one of three states.

    No default here, and none possible: a missing flag answers "the file did
    not say", not "annotated". The model side differs; why is in
    `_model_has_rank`.
    """
    m = page.get("meta") or {}
    if "order_marked" not in m:
        return ORDER_SILENT
    return ORDER_MARKED if m["order_marked"] else ORDER_UNMARKED


def _model_has_rank(page) -> bool:
    """Does the model output carry a REAL rank rather than our numbering.

    Adapters write `reading_order` into the page meta: the model rank, or an
    honest "ours, top down and left to right". Three bench detectors give no
    rank, and scoring our own numbering against truth gave YOLOX 86% -- best of
    six, at twice the worst find rate.

    THE DEFAULT STAYS, and it is not the trouble truth had: the field came
    after the snapshots, and NOT ONE of the nine `bench/*/detect` runs writes
    it (0 pages of 859). Strict, it would kill the "model order" line on every
    run we have, real ranks included -- `bench/slovar` ranks a 42-box page
    259..300, plainly no list position. Accepted, but NOT SILENTLY: our order
    rule prints as its own field.
    """
    # "Is this our order" lives in ONE place, `core/page.ours_order`, with
    # the contract and the price of drift. Only the default is local: a missing
    # field means "model rank" here, "unknown" in `doc/html`.
    from booksmith.core.page import ours_order
    v = (page.get("meta") or {}).get("reading_order", "model_rank")
    return not ours_order(v)


def _pairs_ceiling(t) -> int:
    """How many block pairs this page's truth could yield at all.

    A denominator stands beside its share: 99% over half a book looks like 99%
    over all of it. Pairs of DIFFERENT rank are counted -- an equal-rank pair
    is not scored by construction, and in the ceiling it would promise a
    measurement that never happens.
    """
    o = [b.get("order") for b in t["blocks"]
         if isinstance(b.get("order"), (int, float))]
    return sum(1 for i in range(len(o)) for j in range(i + 1, len(o))
               if o[i] != o[j])


def _order_agree(by_page, idx: int, ceiling: int, pages: int,
                 of_pages: int, why: str = "") -> dict:
    """The share of agreeing pairs, page by page.

    `idx` says WHOSE order is scored: 1 the model rank, 2 the block position in
    the page list, which `assemble/html.py` never sorts and the book therefore
    gets.
    One quantity for two questions was silent about BOTH the moment a model
    gave no rank.
    """
    if why:
        return {"pairs": 0, "agreement": None, "pairs_possible": ceiling,
                "page_count": pages, "pages_total": of_pages, "why": why}
    ok = bad = norank = 0
    for pairs in by_page:
        pp = [(z[0], z[idx]) for z in pairs
              if z[0] is not None and z[idx] is not None]
        norank += len(pairs) - len(pp)
        for i in range(len(pp)):
            for j in range(i + 1, len(pp)):
                a = pp[i][0] - pp[j][0]
                b = pp[i][1] - pp[j][1]
                if a == 0 or b == 0:
                    continue
                ok += (a > 0) == (b > 0)
                bad += (a > 0) != (b > 0)
    n = ok + bad
    return {"pairs": n, "agreement": (ok / n) if n else None,
            "pairs_possible": ceiling, "page_count": pages,
            "pages_total": of_pages, "blocks_without_rank": norank}


# ------------------------------------- EXCESS JUMPS BETWEEN COLUMNS
# The assembly order WITHOUT TRUTH, needed exactly where truth does not exist
# and will not: `bench/real` is unannotated, and the assembly order reaches the
# book from there too.
#
# How many times assembly jumps between columns BEYOND the unavoidable. Walking
# k columns costs no less than k-1 transitions, so k-1 is subtracted and zero
# means every column was read straight through. A two-column dictionary read
# line-left-line-right yields as many jumps as lines -- the fault that makes a
# book unreadable.
#
# THE GROUPING PARAMETERS ARE DECLARED HERE AND RIDE INTO THE ANSWER AND THE
# PRINTOUT, ALL THREE. That already cost one unreproducible measurement (see
# the header): "7.0 -> 1.3" where the same saved boxes give 4.53 -> 0.79 today,
# reference input 4.49 -> 0.79. How much of a difference is the ruler and not
# the data is answered by `column_jumps_sweep`, printed by `--selfcheck`.
COLUMN_OVERLAP = 0.5   # share of the NARROWER box width their x-intersection
                       # must cover for the two to count as one column. At 0.5
                       # a box lies at least half in the column; at 0.1 columns
                       # fuse over a protruding drop cap, at 0.9 a column falls
                       # apart over a paragraph indent.
COLUMN_WIDE = 0.60     # from what share of page width a box counts as
                       # FULL-WIDTH. Such a box (header, full-measure table)
                       # crosses both columns and glues them into one group,
                       # and the metric then silently prints 0 on exactly the
                       # pages it was made for. Left out of the count: they
                       # belong to no column.
COLUMN_MIN_BOXES = 2   # MINIMUM BOXES COUNTED ON A PAGE. A jump happens only
                       # BETWEEN boxes: with one counted box, or none, the
                       # quantity is UNDEFINED and a zero would be a zero from
                       # misunderstanding. Such a page enters neither numerator
                       # nor denominator; with none at all the answer is a dash
                       # (None).
COLUMN_ROLES = ("artifact", "text")  # buckets taking part in the count.
                       # Furniture (folio, running head) stands in the margin
                       # and at mid-page: centred at the foot it overlaps both
                       # columns and glues them, in the margin it forms a third
                       # column. Jumps from page furniture, not reading order.
#
# WHAT THIS QUANTITY CANNOT DO, AND IT IS MEASURED. A column here is geometry,
# not meaning, so the lawful "formula -- its number at the right margin -- next
# formula" counts as jumps: on `bench/matematika` all 10 excess jumps are that,
# the formula numbers standing as their own 35-pixel "column". The cure is not
# tuned thresholds, which would hide the real fault too, but printing the
# number with its parameters and denominator: 10 jumps on 1 multi-column page
# is not 130 on 12, where a three-column `bench/slovar` page really does arrive
# row by row across the columns (47 on one page).


def column_params(overlap=None, wide=None, min_boxes=None, roles=None) -> dict:
    """The grouping parameters IN FORCE, not the declared defaults.

    Its own function because they ride into three places at once -- count,
    returned dict, printout -- and a second copy would drift in silence.
    """
    return {"x_overlap_of_narrow_box":
            COLUMN_OVERLAP if overlap is None else overlap,
            "full_width_box_share":
            COLUMN_WIDE if wide is None else wide,
            "min_boxes_per_page":
            COLUMN_MIN_BOXES if min_boxes is None else min_boxes,
            "buckets_counted": list(COLUMN_ROLES if roles is None else roles)}


def _columns(boxes, overlap=None) -> list:
    """A column number for each box: connected groups by x-overlap.

    Connectivity, not clustering by centres: a column is what stands one under
    another, and the chain "A overlaps B, B overlaps C" keeps it whole when the
    setting edge floats. Numbers run left to right so it reads by eye.
    """
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
    """Excess column jumps of the ASSEMBLY ORDER. No truth needed.

    The order taken is the one that reaches the book: the block position in the
    page list, which `assemble/html.py` walks without sorting. Zero jumps is a
    computed value; a page with one counted box yields NO value, there being
    nothing to jump between, and a whole bench of them answers with a dash
    (`None`) and a "why" field.
    """
    par = column_params(overlap, wide, min_boxes, roles)
    ov = par["x_overlap_of_narrow_box"]
    wd = par["full_width_box_share"]
    mn = par["min_boxes_per_page"]
    keep = set(par["buckets_counted"])
    tot_excess = tot_trans = tot_cols = in_count = wide_n = other = 0
    pages = multi = counted = thin = 0
    per_page = {}
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
        # Below the box minimum a page yields no value: a zero would claim
        # "no jumps" where there is nowhere to take them from.
        if len(part) < mn:
            thin += 1
            continue
        counted += 1
        seq = _columns(part, ov)
        ncols = len(set(seq))
        trans = sum(1 for k in range(1, len(seq)) if seq[k] != seq[k - 1])
        # k-1 transitions into a new column are unavoidable; the rest is
        # excess, and it cannot go negative.
        excess = trans - (ncols - 1)
        tot_trans += trans
        tot_cols += ncols
        tot_excess += excess
        multi += ncols >= 2
        if excess:
            per_page[i] = excess
    ok = counted > 0
    why = "" if ok else (
        f"the quantity is UNDEFINED: not one of the {pages} pages gathered "
        f"{mn} counted boxes (counted in all {in_count}, out of the count "
        f"{wide_n} full-width and {other} of other buckets) — nothing to "
        f"jump between. This is NOT zero jumps.")
    return {"excess_jumps": tot_excess if ok else None,
            # A share stands beside its denominator, and that denominator is
            # NOT "all pages": uncounted pages stay out of it.
            "per_page": (tot_excess / counted) if ok else None,
            "transitions": tot_trans, "columns": tot_cols, "page_count": pages,
            "pages_counted": counted,
            # Pages below the box minimum are named apart, or the "pages
            # counted" denominator looks like a typo.
            "pages_not_counted_too_few_boxes": thin,
            # A one-column page gives zero BY CONSTRUCTION: one group, no
            # transitions, indistinguishable without this count from "nothing
            # to measure on".
            "pages_with_2plus_columns": multi,
            "boxes_counted": in_count, "full_width_boxes": wide_n,
            "boxes_other_buckets": other,
            "by_page": per_page,
            "why": why,
            "params": par}


# --------------------------- SWEEP OVER THE GROUPING PARAMETERS
# Until it is said BY HOW MUCH the quantity depends on the parameters, a
# difference between two runs means nothing. The sweep answers with a number:
# the range the quantity roams over as they move one at a time off the declared
# default. ONE at a time, because a cross grid hides an inert parameter among
# the others and of each we need to know whether it is a lever; `cross=True`
# gives the grid anyway.
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


def column_jumps_sweep(M: dict, grid: dict = None, cross: bool = False,
                       key: str = "per_page") -> dict:
    """The range the quantity roams over as the grouping parameters move.

    Baseline at declared defaults, minimum, maximum, every point by name. A
    dash (`None`) is a lawful answer for a point: at a box minimum of 5 a bench
    may yield no counted page at all, which is no zero.
    """
    pts = []
    for p in _sweep_points(grid or COLUMN_SWEEP, cross):
        v = column_jumps(M, **p)
        pts.append({"params": column_params(**p), "shifted": p,
                    "value": v[key], "pages_counted": v["pages_counted"]})
    vals = [p["value"] for p in pts if p["value"] is not None]
    base = pts[0]["value"] if not cross else column_jumps(M)[key]
    return {"quantity": key, "points": len(pts), "baseline": base,
            "min": min(vals) if vals else None,
            "max": max(vals) if vals else None,
            "dashes": sum(1 for p in pts if p["value"] is None),
            "by_point": pts}


def _fmt_point(shift: dict) -> str:
    """Name a sweep point in words: WHAT is shifted off the default."""
    if not shift:
        return "default"
    return ", ".join(f"{_SWEEP_NAMES.get(k, k)} {v}"
                     for k, v in sorted(shift.items()))


def _ranking_rule(rk: dict) -> str:
    """The rule for pairs the sweep never saw: this quantity does not settle a
    close pair. Closeness is the quantity's OWN range over the sweep -- the
    play of the ruler any smaller gap would be paid in."""
    play, near = rk.get("ruler_play"), rk.get("closest_pair_at_default")
    if play is None:
        return ""
    out = (f"Ruler play over the sweep {play:.2f}: a pair parted at the "
           f"default by less than this is NOT SETTLED by the quantity.")
    if near:
        d, who = near
        out += (f" The closest pair here is {who}, difference {d:.2f}"
                + (" (below the play: this cannot count as a win)."
                   if d < play else "."))
    return out


def column_jumps_ranking(variants: dict, grid: dict = None,
                         cross: bool = False, key: str = "per_page") -> dict:
    """Does the ORDER of the variants hold across the whole parameter sweep.

    The question the quantity exists for: it picks the better assembly order.
    If A beats B at one point and B beats A at another, choosing by it is
    FORBIDDEN, and that must be known before the choice. A pair counts as
    flipped only on a STRICT change of sign.

    A VARIANT IS REBUILT AT EVERY POINT, because one folded OUT OF COLUMNS (the
    floor "column by column", the ceiling "round robin") depends on the very
    parameters it is measured by: folded at the default and measured at "x
    overlap 0.9", the floor gave 1.93 jumps per page against 1.73 for the model
    -- the flip was the ruler, not the data (600 pages, `bench/annopage`, 16
    points, 1 flipped pair of 6, the only one with the floor; refolded, none).
    So a dict value is a BUILDER handed the whole point; ready pages are
    accepted too, having nothing to rebuild.
    """
    names = list(variants)
    pts = _sweep_points(grid or COLUMN_SWEEP, cross)
    vals = {n: [] for n in names}
    # Rebuilding costs time, measured on the golden bench (600 pages): 18s with
    # ready pages, 103s rebuilding everywhere, 34s with the memo below. The
    # memo is free -- points differing only in `min_boxes` give the SAME build,
    # and "overlap 0.5" and "wide 0.6" coincide with the default. Its key is
    # the parameters IN FORCE, not the shift, or `{}` and `{"overlap": 0.5}`
    # would differ. 11 builds instead of 16, verdict unchanged: run before and
    # after, the ranges matched to the hundredth.
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
            for va, vb in zip(vals[na], vals[nb]):
                if va is None or vb is None or va == vb:
                    continue
                signs.add(va < vb)
            if len(signs) > 1:
                flips.append(f"{na} against {nb}")
            elif not signs:
                # A TIE AT EVERY POINT is muteness, not stability: a pair the
                # quantity never told apart takes no part in the choice, and
                # calling it "not flipped" enters silence as proof.
                ties.append(f"{na} against {nb}")
    # THE CLOSEST PAIR AGAINST THE PLAY OF THE RULER. Stability is checked on
    # the pairs that exist and the next may be closer, so a rule for pairs that
    # were not here prints beside it: a gap smaller than the quantity's own
    # play over the parameters is not settled.
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
    """Do truth and model speak ONE VOCABULARY on the matched pairs.

    Label confusion compares STRINGS; without this check it measured the
    spelling of a foreign vocabulary instead of the model. Bench truth is
    PP-DocLayoutV2 (`table`, `image`), Docling-egret and DocLayNet answer
    `Table`, `Picture` -- EXACTLY ZERO labels in common, the diagonal empty by
    construction: egret 698/698 and yolox 379/379 pairs on the golden bench,
    100% on all six synthetic books, whatever the model did. Worse than
    useless, such confusion CANNOT FAIL -- "label Table replaced by Code"
    demands MORE errors, above 100% there are none, and the battery printed
    "NO" and "uncaught damage: 1" on egret and yolox.

    A vocabulary counts as shared only when some declared policy holds every
    label of both sides at once; policy import checks that. There is no
    TRANSLATION between vocabularies: `picture` = `image` would decide for the
    model, and `chart` is inexpressible in Docling's.
    """
    seen = set()
    for k in res["label_confusion"]:
        a, b = k.split("->", 1)
        seen.add(a)
        seen.add(b)
    return _fits(seen)


def label_errors(res: dict):
    """Label errors, or None -- "nothing to compare with".

    Zero means the model never confused a label, None that the sides answer in
    different vocabularies. A number would pass misunderstanding off as
    measurement, as "0 chapters" stood for "I did not recognise them".
    """
    if not label_alphabet(res):
        return None
    return sum(n for k, n in res["label_confusion"].items()
               if k.split("->", 1)[0] != k.split("->", 1)[1])


def role_errors(res: dict) -> int:
    """BUCKET confusion: did the model call an artefact an artefact.

    What survives of label confusion across a vocabulary border, and always
    scored: the bucket is declared in policy for EVERY vocabulary as a whole
    and rides into the snapshot, so `Table` -> `artifact` is policy, not a
    guess. Coarser than the label deliberately -- `table` -> `chart` inside one
    bucket never lands here -- and that is its honesty.
    """
    return sum(n for k, n in res["label_confusion"].items()
               if policy.role(k.split("->", 1)[0])
               != policy.role(k.split("->", 1)[1]))


def _report_order(res: dict, log) -> None:
    """Reading order: several lines instead of one, each answering its own.

    What truth knows about order (and, separately, "not said"); the MODEL rank,
    its verdict; the ASSEMBLY order, what the reader will see; excess column
    jumps, the same assembly without truth. Fused, the first two were silent
    about both questions the moment a model gave no rank.
    """
    st = res["order_truth"]
    n, c = st["page_count"], st["states"]
    if c.get(ORDER_MARKED, 0) < n:
        log(f"truth about order: marked {c.get(ORDER_MARKED, 0)}, "
            f"not marked {c.get(ORDER_UNMARKED, 0)}, "
            f"NOT SAID {c.get(ORDER_SILENT, 0)} of {n} pages")
    # ITS OWN line: "not said" takes one line from whoever built the bench,
    # "not marked" is not curable at all.
    if c.get(ORDER_SILENT):
        log(f"  'not said' IS NOT 'not marked': {c[ORDER_SILENT]} truth "
            f"pages have NO `order_marked` field AT ALL, and a number over "
            f"them would be taken out of nothing (that is how 'agreed 73%' "
            f"printed on hard36). Cured by whoever built this bench.")
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
    _report_jumps(res["jumps"], log)


def _report_jumps(j: dict, log) -> None:
    """Excess jumps -- THREE answers, never to be confused.

    * a dash -- no quantity: no page reached `COLUMN_MIN_BOXES` counted boxes;
    * zero at one column -- computed, and zero by construction: one group
      yields no transitions;
    * a number at two or more columns -- what the quantity exists for.

    The parameters print in ALL THREE: "12 jumps" without them does not compare
    with another run's "9 jumps".
    """
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


def report(res: dict, log=print) -> None:
    if res.get("book"):
        log(res["book"])
    t, x = res["totals"], res["text_and_furniture"]
    log(f"artefacts {t['artifacts']}, found {t['found']} "
        f"({t['share']*100:.0f}%)")
    for why, n in res["troubles"].items():
        log(f"  {why}: {n}")
    # Text and furniture are three quarters of truth's blocks. Without this
    # line they entered NO printed number: the bench was silent about 337
    # blocks of 382 and looked complete doing it.
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
    _report_order(res, log)
    n_pairs = sum(res["label_confusion"].values())
    # Buckets ALWAYS print: the only part of the confusion that survives a
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
# The damage itself is `probes/contour.py`. These are the metric's own helpers:
# the column split the jump count is built on, and the four assembly orders
# `column_jumps_ranking` compares. The probes reach for the same ones.

def _columns_of(p, wide=None, roles=None):
    """Split a page's blocks into those counted for columns and the rest.

    The parameters are taken, not silently defaulted: variants FOLDED from this
    split are measured across the whole sweep, and one folded under some
    parameters and measured under others stops being what it is called.
    """
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
    """Shuffle the columns: blocks dealt round robin -- left, middle, right, left
    again. The worst assembly order at these very boxes, and what the real
    fault looks like: on `bench/slovar` a three-column page arrives from the
    model row by row across the columns, 47 excess jumps. The parameters are
    taken because the top of the scale must be the top AT THE PARAMETERS it is
    measured at; `min_boxes` takes no part in the folding and is accepted only
    so a sweep point can be handed here whole."""
    out = {}
    for i, p in M.items():
        part, rest = _columns_of(p, wide, roles)
        buckets = {}
        for c, b in zip(_columns([b["box"] for b in part], overlap), part):
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
    is 0.4 of the page ON PURPOSE -- at 0.6 and above a box counts as
    full-width, drops out of the count, and the zero would come from an empty
    count rather than the single column."""
    out = {}
    for i, p in M.items():
        w = float(p.get("width") or 0.0) or 1000.0
        x0, x1 = 0.10 * w, 0.50 * w
        out[i] = {**p, "blocks": [{**b, "box": [x0, b["box"][1], x1,
                                                b["box"][3]]}
                                  for b in p["blocks"]]}
    return out


def _one_box(M):
    """Leave ONE counted box on the page; the other participants go.

    The quantity must become a DASH, not a zero: a jump happens only BETWEEN
    boxes, and a zero would read as "assembly runs straight through" where
    there is no assembly at all. Boxes OUTSIDE the count (furniture,
    full-width) stay on purpose -- remove them and the dash would come from an
    empty count rather than the single box.
    """
    out = {}
    for i, p in M.items():
        part, rest = _columns_of(p)
        out[i] = {**p, "blocks": part[:1] + rest}
    return out


def _by_reading(M, overlap=None, wide=None, min_boxes=None, roles=None):
    """Our assembly rule -- ASKED OF `order.py`, not repeated here.

    The parameters take no part (the rule is purely geometric); they are
    accepted only so a sweep point reaches every builder alike.

    A SECOND COPY STOOD HERE: `sorted(key=(box[1], box[0]))` under a docstring
    calling it "the order the adapters declare as ours". The keys matched, this
    file never imported `order`, and NO check tied them -- while this builder
    produced the headline finding "our rule was measured and lost", 2471 excess
    jumps against 501 for the model rank and 439 for docling's rules (section
    20 of `METRICS.md`). Editing `order.permutation` would have left
    the instrument measuring the OLD rule under the current name, the illness
    `order.py` cures. `which="ours"` is explicit and not read from
    `ASSEMBLY_ORDER`: the knob would make sweep columns incomparable between
    runs.
    """
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
    """Column by column, top down inside a column: the best assembly order
    possible at THESE boxes, zero excess jumps by construction, and so the
    bottom of the scale when checking whether the quantity tells variants apart
    at all.

    "BY CONSTRUCTION" HOLDS ONLY AT THE PARAMETERS IT WAS FOLDED AT. A floor
    folded at overlap 0.5 is no floor at 0.9, where columns are cut
    differently: on the golden bench such a floor gave 1.81 and 1.93 jumps per
    page at "x overlap 0.8" and "0.9" -- MORE than the model itself (1.69 and
    1.73), and that is the pair that flipped."""
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
    """Four assembly orders over THE SAME boxes, as BUILDERS, not ready pages.

    These are the variants the quantity chooses between: same boxes, different
    assembly rule. If the sweep changes their ORDER AMONG THEMSELVES, choosing
    by this quantity is forbidden, and that must be known beforehand.

    WHY BUILDERS: the floor and the ceiling are FOLDED from the same columns
    the jumps are counted over, so as ready pages folded at the DEFAULTS the
    floor stopped being a floor wherever a point left them (numbers in
    `_by_columns`). On that the battery printed "you MUST NOT choose a model or
    an assembly rule by this quantity" -- a verdict from the ruler, not the
    data, contradicting `METRICS.md`. Exactly 1 pair
    of 6 flipped over 16 points, the one with the floor. Refolded at every
    point, nothing flips.
    """
    return {"as_model_gave": lambda **par: M,
            "top_down_left_right": lambda **par: _by_reading(M, **par),
            "column_by_column": lambda **par: _by_columns(M, **par),
            "round_robin_columns": lambda **par: _mix_columns(M, **par)}


# ------------------------------------------------- SENSE WHOLE
# The third number, and for our pipeline the main one. "Outlined correctly"
# (two-sided cover 0.75) answers about the precision of the box; the second
# level needs another: IS THE OBJECT'S SENSE WHOLE. A box roomier than needed
# does no harm, the second level deals with the extra air, but a cut-off corner
# cannot be restored and glued objects cannot be separated -- they ride into
# the crop as one picture.
#
# So an object is whole when a box was found that it FITS INTO (not cropped)
# and that no neighbouring truth object got into (not merged). Losses are named
# and differ in price:
#   cropped    -- content outside the box, nothing to restore it with;
#   merged     -- two objects in one box, the second level reads them as one;
#   not seen   -- no box at all, the dearest loss.
#
# The "fits" threshold is a named number and a knob: where the margin ends and
# content begins is our decision, and it has to be visible.
SENSE_WHOLE = 0.90     # what share of the object must lie inside the box
SENSE_NEIGHBOUR = 0.5  # from what share of a neighbour a box counts as merged


def sense(T: dict, M_: dict) -> dict:
    """Is the object's sense whole: not cropped, not merged, not called text."""
    arte = set(policy.artefacts())
    out = {"objects": 0, "intact": 0, "cropped": 0, "merged": 0,
           "called_text": 0, "not_seen": 0,
           "threshold_fits": SENSE_WHOLE, "threshold_neighbour": SENSE_NEIGHBOUR}
    for i, t in sorted(T.items()):
        if i not in M_:
            continue
        mb = [b["box"] for b in M_[i]["blocks"] if b["label"] in arte]
        # Non-artefact boxes are kept apart: outlined correctly but called
        # text is lost differently from never seen -- the first cured by a
        # label, the second by the model. Fusing them would declare 67 AnnoPage
        # tables "invisible" when fifty-four have a box.
        ob = [b["box"] for b in M_[i]["blocks"] if b["label"] not in arte]
        tb = [b for b in t["blocks"] if b["label"] in arte]
        for b in tb:
            out["objects"] += 1
            fits = [x for x in mb
                    if cover(b["box"], x) >= SENSE_WHOLE]
            if not fits:
                if any(cover(b["box"], x) >= 0.5 for x in mb):
                    out["cropped"] += 1
                elif any(cover(b["box"], x) >= SENSE_WHOLE for x in ob):
                    out["called_text"] += 1
                else:
                    out["not_seen"] += 1
                continue
            alone = [x for x in fits
                     if not any(o is not b
                                and cover(o["box"], x) >= SENSE_NEIGHBOUR
                                for o in tb)]
            if alone:
                out["intact"] += 1
            else:
                out["merged"] += 1
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
                  why=None if part.get("agreement") is not None else part.get("why") or "not compared")


class ContourMetric(Metric):
    name = "contour"
    needs = frozenset({"truth", "pages"})

    def run(self, bench, run) -> Record:
        res = compare(bench.truth_dir, run.pages_dir)
        return self.record(res, bench.name, run.label)

    def run_loaded(self, bench, run, truth, pages, note) -> Record:
        res = compare_pages(truth, pages)
        res["book"] = f"{note}; {_same_raster(truth, pages)}"
        return self.record(res, bench.name, run.label)

    def record(self, res: dict, bench_name: str, run_label: str) -> Record:
        t, x, s, j = res["totals"], res["text_and_furniture"], res["sense"], res["jumps"]
        lab = label_errors(res)
        # The pairs the confusion was counted over: one entry per matched
        # (truth, model) block, which is the denominator both error counts
        # are shares of.
        pairs = sum(res["label_confusion"].values())
        scalars = {
            "artefacts_found": Scalar(t["share"], count=(t["found"], t["artifacts"])),
            "sense_whole": Scalar(
                s["share"], count=(s["intact"], s["objects"]),
                why=None if s["share"] is not None else "no artefact in the truth"),
            # THE FOUR WAYS AN OBJECT IS LOST, each over the same objects, so
            # the five together account for every one of them. `sense_whole`
            # was the only one that reached a scalar, and the rest lived in
            # `detail` -- where a TABLE cannot read them. Three sections of
            # `METRICS.md` are about MERGING and its headline is
            # "merging is 71% of ALL misses": the document that replaces that
            # prose could not have stated the project's central level-one
            # finding, and deleting the prose would have deleted the finding.
            **{f"artefacts_{k}": Scalar(
                (s[k] / s["objects"]) if s["objects"] else None,
                count=(s[k], s["objects"]),
                why=None if s["objects"] else "no artefact in the truth")
               for k in ("merged", "cropped", "called_text", "not_seen")},
            "text_furniture_found": Scalar(
                x["share"], count=(x["found"], x["block_count"]),
                over=(x.get("pages_with_text_markup", 0), x.get("pages_total", 0)), unit="pages",
                why=None if x["share"] is not None else "text and furniture NOT MARKED in this truth"),
            # BOTH CARRY THEIR DENOMINATOR, and it is not decoration: the
            # matched-pair count moves by more than half between models, so a
            # bare count RANKS THEM WRONG. Measured on slovar: plus-L 233 of
            # 239 pairs against V3's 442 of 495 -- by the printed number
            # plus-L looks twice as good and by the rate it is the worst
            # (0.975 against 0.893). Every other scalar in this record already
            # carried its count.
            "label_errors": Scalar(
                lab, count=None if lab is None else (lab, pairs),
                why=None if lab is not None else
                "the two sides speak different label vocabularies; not compared"),
            "role_errors": Scalar(role_errors(res), count=(role_errors(res),
                                                           pairs)),
            "model_order": _order(res["model_order"]),
            "assembly_order": _order(res["assembly_order"]),
            # `excess_jumps_per_page` STOOD HERE AND IN `assembly`, from one
            # call of `column_jumps` -- byte-identical in all 54 result files,
            # printed twice in every per-bench table. The assembly one is the
            # copy that keeps it: that metric IS the column-jump measurement,
            # it carries `order_rule` in its params saying whose order was
            # counted, and this one did not. A second copy drifts, and this
            # one could only ever have drifted into being wrong.
        }
        params = {"COVER_MATCH": COVER_MATCH, "TOUCH": TOUCH, "TOL_PX": TOL_PX,
                  "SENSE_WHOLE": SENSE_WHOLE, "SENSE_NEIGHBOUR": SENSE_NEIGHBOUR}
        params.update({f"COLUMN_{k}": v for k, v in (j.get("params") or {}).items()})
        return Record(self.name, bench_name, run_label, scalars, params, res)

    def report(self, rec: Record, log=print) -> None:
        report(rec.detail, log=log)
