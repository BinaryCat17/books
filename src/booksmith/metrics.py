"""Contour metrics: how correctly the model outlined tables, figures, charts.

Three numbers, kept SEPARATE -- one combined score is cured by trading one
fault for another:

1. **localisation**, blind to the label: is a box where the artefact is;
2. **label confusion**, on what was found: was a table called a table;
3. **reading order**, itself three: the MODEL rank against truth, only when
   both sides carry a real rank; the ASSEMBLY order against truth, which is
   what the reader sees, since `doc/html.py` runs `for b in page.blocks` and
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

* **A missing flag was read as a present one.** `_has_order` defaulted to
  `True`, so truth silent about its reading order counted as annotated, and
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
  the printout, and a battery that prints the sweep and checks the variant
  ORDER survives it.

ON THE ABILITY TO FAIL. `mutations()` feeds spoiled input and demands the
number sag. Three-sided -- model output, TRUTH (a metric indifferent to truth
measures one input and is always right), OUR OWN thresholds -- each apart,
since moved together they hide the inert one.
"""
import json
import os

from . import policy

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


class MetricError(RuntimeError):
    pass


def _load(d):
    if not os.path.isdir(d):
        raise MetricError(f"нет каталога {d}")
    out = {}
    for name in sorted(os.listdir(d)):
        if name.endswith(".json") and name != "run.json":
            with open(os.path.join(d, name), encoding="utf-8") as f:
                p = json.load(f)
            if "blocks" not in p or "index" not in p:
                raise MetricError(f"{name}: не похоже на страницу разметки")
            out[int(p["index"])] = p
    if not out:
        raise MetricError(f"в {d} нет страниц разметки")
    return out


def _same_book(truth_dir: str, detect_dir: str) -> str:
    """Are truth and model output about the same PDF.

    Without it `books score` scores one book's truth against another's boxes
    and prints a sensible-looking number. Both snapshots carry the source PDF
    sha256; we compare those, not directory names.
    """
    man = os.path.join(os.path.dirname(truth_dir.rstrip("/")), "manifest.json")
    run = os.path.join(os.path.dirname(detect_dir.rstrip("/")), "run.json")
    if not (os.path.exists(man) and os.path.exists(run)):
        return "sha256 не сверен: нет manifest.json или run.json рядом"
    with open(man, encoding="utf-8") as f:
        a = json.load(f).get("sha256 pdf")
    with open(run, encoding="utf-8") as f:
        b = (json.load(f).get("source") or {}).get("sha256")
    if not (a and b):
        return "sha256 не сверен: поля нет в слепке"
    if a != b:
        raise MetricError(
            f"истина и вывод модели про РАЗНЫЕ книги: sha256 {a[:12]} против "
            f"{b[:12]}. Число тут вышло бы осмысленным на вид и бессмысленным "
            f"по существу.")
    return f"sha256 сверен: {a[:12]}"


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
        return "вложенный дубль"
    if any(cover(box, b) >= 0.9 for b in unpaired):
        return "внутри ненайденного"
    if (any(cover(box, b) >= 0.5 or cover(b, box) >= 0.5 for b in outside)
            # ...but NOT when the same box also covers truth artefacts: a
            # full-page box meets any drop cap, and the amnesty would forgive
            # it the tables it swallowed too.
            and sum(1 for b in tb if cover(b["box"], box) >= 0.6) < 2):
        return "на объекте вне замера"
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
        return "не увидел"
    best = max(touching, key=lambda m: iou(t["box"], m["box"]))
    ct, cm = cover(t["box"], best["box"]), cover(best["box"], t["box"])
    eaten = [o for o in others_truth
             if o is not t and cover(o["box"], best["box"]) >= 0.6]
    if eaten and ct >= 0.6:
        return "слияние"
    # Fragmentation counts ARTEFACT boxes only. Counting text ones gave
    # "missed the table but covered it with text" the name of the cheapest
    # trouble instead of the dearest.
    inside = [m for m in touching if m["label"] in arte
              and cover(m["box"], t["box"]) >= 0.7]
    if len(inside) >= 2:
        return "дробление"
    if policy.role(best["label"]) == "text" and ct >= 0.6:
        return "съеден текстом"
    if ct < 0.85 and cm >= 0.85:
        return "срез"
    if cm < 0.6:
        return "разлив"
    return "рядом, но не совпал"


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
        return "растр НЕ СВЕРЕН: у страниц нет полей width/height"
    dt = sorted({T[i].get("dpi") for i in common}, key=str)
    dm = sorted({M[i].get("dpi") for i in common}, key=str)
    bad = [f"с.{i}: истина {T[i]['width']}x{T[i]['height']}, "
           f"модель {M[i]['width']}x{M[i]['height']}" for i in common
           if (T[i]["width"], T[i]["height"]) != (M[i]["width"], M[i]["height"])]
    if bad:
        raise MetricError(
            f"истина и вывод модели в РАЗНЫХ растрах: координаты в разных "
            f"системах, и число вышло бы правдоподобным и ложным. Разошлись "
            f"{len(bad)} страниц из {len(common)}: " + "; ".join(bad[:3])
            + (" …" if len(bad) > 3 else "")
            + f". dpi: истина {dt}, модель {dm} — смотри PAGE_DPI прогона.")
    note = f"растр сверен: {len(common)} страниц, размеры совпали"
    if dt != dm:
        note += (f"; ярлык dpi РАЗНЫЙ (истина {dt}, модель {dm}) — на "
                 f"координаты не влияет, растр один")
    return note


def compare(truth_dir: str, detect_dir: str) -> dict:
    """Score model output against truth. Numbers and named counters."""
    T, M = _load(truth_dir), _load(detect_dir)
    note = f"{_same_book(truth_dir, detect_dir)}; {_same_raster(T, M)}"
    res = compare_pages(T, M)
    res["book"] = note
    return res


def compare_pages(T: dict, M: dict) -> dict:
    missing = sorted(set(T) - set(M))
    if missing:
        raise MetricError(
            f"модель не разметила страницы {missing[:5]}: сверять нечего. "
            f"Пустой отчёт тут выглядел бы как «совпало ноль», а это другое.")

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
        "reading_order", "не объявлено (принято «ранг модели»)"))
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
            # `doc/html.py` walks and the book is assembled by.
            page_ranks.append((b.get("order"), x.get("order"), j))
            if (b["label"] not in arte
                    and (t.get("meta") or {}).get("text_marked", True)):
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
        if (t.get("meta") or {}).get("text_marked", True):
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
        why_order = ("истина порядка не несёт: " + ", ".join(
            f"{k} у {states[k]}" for k in
            (ORDER_MARKED, ORDER_UNMARKED, ORDER_SILENT) if states.get(k))
            + f" из {len(T)} страниц")
    return {"totals": tot, "sense": sense(T, M), "text_and_furniture": txt,
            "by_case": per_case,
            "by_label": {k: {"truth": v[1], "found": v[0],
                               "bucket": policy.role(k)}
                           for k, v in sorted(per_label.items())},
            "troubles": dict(sorted(beds.items())),
            "label_confusion": {f"{a}->{b}": n for (a, b), n in sorted(conf.items())},
            "order_truth": {"states": states, "page_count": len(T)},
            "order_rule": ", ".join(rules) or "нечего объявлять",
            # TWO QUESTIONS, TWO QUANTITIES. The first is about the model and
            # demands a real rank on both sides. The second is about the BOOK,
            # where an assembly order always exists, rank or not.
            "model_order": _order_agree(
                ranks, 1, ceiling, order_pages, len(T),
                why_order or ("" if model_rank else
                              f"модель ранга не даёт ({', '.join(rules)})")),
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
ORDER_MARKED = "размечен"
ORDER_UNMARKED = "не размечен"
ORDER_SILENT = "not_said"


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
    # "Is this our order" lives in ONE place, `models/base.ours_order`, with
    # the contract and the price of drift. Only the default is local: a missing
    # field means "model rank" here, "unknown" in `doc/html`.
    from .models.base import ours_order
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
    the page list, which `doc/html.py` never sorts and the book therefore gets.
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
    page list, which `doc/html.py` walks without sorting. Zero jumps is a
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
        f"величина НЕ ОПРЕДЕЛЕНА: ни на одной из {pages} страниц не набралось "
        f"{mn} рамок в счёте (всего в счёте {in_count}, мимо счёта "
        f"{wide_n} сквозных и {other} иных разрядов) — прыгать не между чем. "
        f"Это НЕ ноль прыжков.")
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
_SWEEP_RU = {"overlap": "перекрытие x", "wide": "сквозная рамка",
             "min_boxes": "минимум рамок"}


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
    return ", ".join(f"{_SWEEP_RU.get(k, k)} {v}"
                     for k, v in sorted(shift.items()))


def _ranking_rule(rk: dict) -> str:
    """The rule for pairs the sweep never saw: this quantity does not settle a
    close pair. Closeness is the quantity's OWN range over the sweep -- the
    play of the ruler any smaller gap would be paid in."""
    play, near = rk.get("ruler_play"), rk.get("closest_pair_at_default")
    if play is None:
        return ""
    out = (f"Размах линейки по развёртке {play:.2f}: пара, разошедшаяся при "
           f"умолчании меньше этого, по величине НЕ РЕШАЕТСЯ.")
    if near:
        d, who = near
        out += (f" Ближайшая пара здесь — {who}, разница {d:.2f}"
                + (" (меньше размаха: считать это выигрышем нельзя)."
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
                flips.append(f"{na} против {nb}")
            elif not signs:
                # A TIE AT EVERY POINT is muteness, not stability: a pair the
                # quantity never told apart takes no part in the choice, and
                # calling it "not flipped" enters silence as proof.
                ties.append(f"{na} против {nb}")
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
                 f"{names[a]} против {names[b]}")
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
        log(f"истина о порядке: размечен {c.get(ORDER_MARKED, 0)}, "
            f"не размечен {c.get(ORDER_UNMARKED, 0)}, "
            f"НЕ СКАЗАНО {c.get(ORDER_SILENT, 0)} из {n} страниц")
    # ITS OWN line: "not said" takes one line from whoever built the bench,
    # "not marked" is not curable at all.
    if c.get(ORDER_SILENT):
        log(f"  «не сказано» — ЭТО НЕ «не размечен»: у {c[ORDER_SILENT]} "
            f"страниц истины поля «порядок размечен» НЕТ ВОВСЕ, и число по "
            f"ним было бы взято из ничего (так печаталось «согласовано 73%» "
            f"на hard36). Чинится у того, кто собрал этот стенд.")
    for name, key in (("чтения МОДЕЛИ против истины", "model_order"),
                      ("СБОРКИ книги против истины", "assembly_order")):
        o = res[key]
        tail = ("" if key == "model_order"
                else f"; наш порядок построен так: {res['order_rule']}")
        if o["agreement"] is None:
            log(f"порядок {name}: НЕ СВЕРЯЕТСЯ — {o.get('why', 'нет пар')} "
                f"(это не ноль согласия){tail}")
        else:
            log(f"порядок {name}: согласовано {o['agreement']*100:.0f}%, "
                f"пар измерено {o['pairs']} из {o['pairs_possible']} возможных по "
                f"истине, по {o['page_count']} страницам из {o['pages_total']}"
                + (f", блоков без ранга {o['blocks_without_rank']}"
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
        log(f"лишние прыжки между колонками: ПРОЧЕРК — {j['why']} "
            f"Группировка: {par}")
    else:
        thin = j["pages_not_counted_too_few_boxes"]
        tail = (f"рамок в счёте {j['boxes_counted']}, мимо счёта "
                f"{j['full_width_boxes']} сквозных и {j['boxes_other_buckets']} "
                f"иных разрядов; страниц без счёта {thin} из {j['page_count']} "
                f"(рамок меньше минимума); группировка: {par}")
        if not j["pages_with_2plus_columns"]:
            log(f"лишние прыжки между колонками: 0 — величина ПОСЧИТАНА по "
                f"{j['pages_counted']} страницам, но ноль этот ПО "
                f"ПОСТРОЕНИЮ: ни одной многоколоночной страницы из "
                f"{j['page_count']}, перескакивать было некуда. {tail}")
        else:
            log(f"лишние прыжки между колонками: {j['excess_jumps']} "
                f"({j['per_page']:.2f} на страницу по "
                f"{j['pages_counted']} страницам в счёте из {j['page_count']}; "
                f"переходов {j['transitions']}, колонок {j['columns']} на "
                f"{j['pages_with_2plus_columns']} многоколоночных страницах). "
                f"{tail}")


def report(res: dict, log=print) -> None:
    if res.get("book"):
        log(res["book"])
    t, x = res["totals"], res["text_and_furniture"]
    log(f"артефактов {t['artifacts']}, найдено {t['found']} "
        f"({t['share']*100:.0f}%)")
    for why, n in res["troubles"].items():
        log(f"  {why}: {n}")
    # Text and furniture are three quarters of truth's blocks. Without this
    # line they entered NO printed number: the bench was silent about 337
    # blocks of 382 and looked complete doing it.
    if x["block_count"]:
        note = ""
        if x.get("pages_with_text_markup", 0) < x.get("pages_total", 0):
            note = (f" — считано по {x['pages_with_text_markup']} страницам "
                    f"из {x['pages_total']}, на остальных текст не размечен")
        log(f"текст и служебное: блоков {x['block_count']}, найдено {x['found']} "
            f"({x['share']*100:.0f}%){note}")
    else:
        log("текст и служебное: НЕ РАЗМЕЧЕНЫ в этой истине — сверять нечего "
            "(это не ноль полноты)")
    if res.get("sense"):
        c = res["sense"]
        log(f"СМЫСЛ ЦЕЛ: {c['intact']}/{c['objects']} ({c['share']*100:.0f}%) — "
            f"обрезан {c['cropped']}, слит {c['merged']}, "
            f"назван текстом {c['called_text']}, "
            f"не увиден {c['not_seen']} (объект внутри рамки от "
            f"{c['threshold_fits']:.2f}, сосед от {c['threshold_neighbour']:.2f})")
    miss = {k: v for k, v in res["by_label"].items()
            if v["found"] < v["truth"]}
    if miss:
        log("  недобор по ярлыкам: " + ", ".join(
            f"{k} {v['found']}/{v['truth']}" for k, v in miss.items()))
    _report_order(res, log)
    n_pairs = sum(res["label_confusion"].values())
    # Buckets ALWAYS print: the only part of the confusion that survives a
    # vocabulary border.
    log(f"путаница разрядов: {role_errors(res)} из {n_pairs} пар")
    voc = label_alphabet(res)
    if not voc:
        t_lab = sorted({k.split("->", 1)[0] for k in res["label_confusion"]})
        m_lab = sorted({k.split("->", 1)[1] for k in res["label_confusion"]})
        log(f"путаница ярлыков: НЕ СВЕРЯЕТСЯ — истина и модель отвечают в "
            f"разных словарях (истина ложится в {_fits(t_lab) or '—'}, "
            f"модель в {_fits(m_lab) or '—'}; общих ярлыков "
            f"{len(set(t_lab) & set(m_lab))} из {len(set(t_lab) | set(m_lab))}). "
            f"Это НЕ 100% ошибок: `table` и `Table` про одно и то же, а "
            f"перевода между словарями у нас нет и не должно быть.")
    else:
        bad = {k: v for k, v in res["label_confusion"].items()
               if k.split("->", 1)[0] != k.split("->", 1)[1]}
        log(f"путаница ярлыков: {label_errors(res)} из {n_pairs} пар "
            f"(словарь один: {', '.join(voc)})" + (f" — {bad}" if bad else ""))
    for case, c in sorted(res["by_case"].items(),
                          key=lambda kv: (kv[1]["found"] - kv[1]["artifacts"])):
        if c["found"] < c["artifacts"] or c["troubles"]:
            log(f"  {case:24s} {c['found']}/{c['artifacts']}  "
                + ", ".join(f"{k} {v}" for k, v in sorted(c["troubles"].items())))


# --------------------------------------------------------------- mutations
# A number that cannot fall measures nothing. The battery feeds the metric
# deliberately spoiled input and demands the number sag. THE DAMAGE IS
# THREE-SIDED:
#  * the model output -- the obvious side;
#  * TRUTH -- a metric indifferent to truth measures one input and is always
#    "right";
#  * OUR OWN thresholds, each APART. Moved together, an inert threshold looks
#    like a working one: `IOU_MATCH` never fired while the battery reported
#    "fell" nine runs in a row.

def _map_boxes(M, fn):
    return {i: {**p, "blocks": [{**b, "box": list(fn(b["box"]))}
                                for b in p["blocks"]]} for i, p in M.items()}


def _shift(M, dx, dy):
    return _map_boxes(M, lambda b: (b[0] + dx, b[1] + dy, b[2] + dx, b[3] + dy))


def _shift_rel(M, frac):
    """A shift BY A FRACTION of the box size, not by a constant forty pixels.

    A constant shift checks nothing on large artefacts: a 900x400 box moved by
    40 still covers truth by 96% and passes, and on a book of large artefacts
    the probe "shift by 40" reported "DID NOT FALL" -- rightly, there was
    nothing to fall from.
    """
    def g(b):
        d = frac * max(4.0, min(b[2] - b[0], b[3] - b[1]))
        return (b[0] + d, b[1] + d, b[2] + d, b[3] + d)
    return _map_boxes(M, g)


def _grow(M, f):
    def g(b):
        cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
        w, h = (b[2] - b[0]) * f / 2, (b[3] - b[1]) * f / 2
        return (cx - w, cy - h, cx + w, cy + h)
    return _map_boxes(M, g)


def _only(M, keep):
    return {i: {**p, "blocks": [b for b in p["blocks"] if keep(b)]}
            for i, p in M.items()}


def _relabel(M, fn):
    return {i: {**p, "blocks": [{**b, "label": fn(b["label"])} for b in p["blocks"]]}
            for i, p in M.items()}


def _reverse_order(M):
    out = {}
    for i, p in M.items():
        n = len(p["blocks"])
        out[i] = {**p, "blocks": [{**b, "order": n - 1 - j}
                                  for j, b in enumerate(p["blocks"])]}
    return out


def _reverse_blocks(M):
    """Reverse the block LIST, leaving the ranks alone.

    The damage aims at the ASSEMBLY order and nothing else: the book is built
    from the list (`doc/html.py`) while `order` stays. Without it, `order`
    could be read in place of the list position and nobody would notice.
    """
    return {i: {**p, "blocks": list(reversed(p["blocks"]))}
            for i, p in M.items()}


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
    20 of `docs/contour-notes.md`). Editing `order.permutation` would have left
    the instrument measuring the OLD rule under the current name, the illness
    `order.py` cures. `which="ours"` is explicit and not read from
    `ASSEMBLY_ORDER`: the knob would make sweep columns incomparable between
    runs.
    """
    from . import order
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
    data, contradicting section 18 of `docs/contour-notes.md`. Exactly 1 pair
    of 6 flipped over 16 points, the one with the floor. Refolded at every
    point, nothing flips.
    """
    return {"as_model_gave": lambda **par: M,
            "top_down_left_right": lambda **par: _by_reading(M, **par),
            "column_by_column": lambda **par: _by_columns(M, **par),
            "round_robin_columns": lambda **par: _mix_columns(M, **par)}


def _forget_order_mark(T):
    """Erase truth's order-annotation flag -- the hole hard36 printed
    "agreed 73%" out of."""
    out = {}
    for i, p in T.items():
        m = dict(p.get("meta") or {})
        m.pop("order_marked", None)
        out[i] = {**p, "meta": m}
    return out


def _duplicate(M):
    """Duplicate every box. The found share must NOT grow."""
    return {i: {**p, "blocks": [c for b in p["blocks"] for c in (b, dict(b))]}
            for i, p in M.items()}


def _shuffle_pages(M):
    """Shift the markup one page forward, cyclically: scoring goes by page
    index, and substituting a neighbour must bring everything down."""
    keys = sorted(M)
    return {k: {**M[keys[(n + 1) % len(keys)]], "index": k}
            for n, k in enumerate(keys)}


def _merge_all(M, arte):
    """Merge all artefact boxes of a page into one bounding box."""
    out = {}
    for i, p in M.items():
        a = [b for b in p["blocks"] if b["label"] in arte]
        rest = [b for b in p["blocks"] if b["label"] not in arte]
        if len(a) >= 2:
            box = [min(b["box"][0] for b in a), min(b["box"][1] for b in a),
                   max(b["box"][2] for b in a), max(b["box"][3] for b in a)]
            a = [{**a[0], "box": box}]
        out[i] = {**p, "blocks": rest + a}
    return out


def _split_all(M, arte):
    """Cut every artefact box in half vertically."""
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
    """Did a number that may not exist grow. None on either input means "no
    data": the incomparable counts as neither growth nor its absence."""
    return None if (now is None or was is None) else now > was


def _beds(res, prefix):
    return sum(n for k, n in res["troubles"].items() if k.startswith(prefix))


def _multi(T, arte):
    """Is there a page with more than one truth artefact: without one there is
    nothing to stage the merge probe on."""
    return any(sum(1 for b in p["blocks"] if b["label"] in arte) > 1
               for p in T.values())


def mutations(truth_dir: str, detect_dir: str, log=print) -> int:
    """Run the battery. Returns uncaught damage count (0 -- metric alive)."""
    global COVER_MATCH, TOUCH, TOL_PX
    T, M = _load(truth_dir), _load(detect_dir)
    arte = set(policy.artefacts())
    # The label for the "rename one class" probe comes FROM THE DATA, not
    # hard-coded: `table` in PP-DocLayout*, `Table` in Docling and DocLayNet. A
    # hard-coded name gave a false "NO" on three detectors of six -- dead was
    # its own list of names, not the metric.
    m_arte = [b["label"] for p in M.values() for b in p["blocks"]
              if b["label"] in arte]
    pick = max(set(m_arte), key=m_arte.count) if m_arte else None
    # The second label comes FROM THE SAME VOCABULARY as the first, or `table`
    # is replaced by docling's `Code`: a label this model does not have checks
    # the wrong thing.
    same = next((t for t in policy.POLICIES.values() if pick in t), {})
    other = next((l for l in sorted(same)
                  if l != pick and same[l] == "artifact"), None)
    # A text label of the same vocabulary, for "artefacts called text".
    m_txt = [b["label"] for p in M.values() for b in p["blocks"]
             if b["label"] not in arte]
    plain = max(set(m_txt), key=m_txt.count) if m_txt else None
    base = compare_pages(T, M)
    b_found = base["totals"]["share"]
    b_text = base["text_and_furniture"]["share"]
    b_text_s = "—" if b_text is None else f"{b_text*100:.0f}%"
    # `agreement` is lawfully None when order is not annotated, and must not be
    # multiplied by a hundred: that line killed the whole battery with a
    # TypeError on the golden bench, where it is needed most.
    b_ord = base["model_order"]["agreement"]
    b_ord_s = "—" if b_ord is None else f"{b_ord*100:.0f}%"
    # The ASSEMBLY order is the second quantity here and needs probes of its
    # own: it is the one that reaches the book.
    b_asm = base["assembly_order"]["agreement"]
    b_asm_s = "—" if b_asm is None else f"{b_asm*100:.0f}%"
    b_jump = base["jumps"]["excess_jumps"]
    b_multi = base["jumps"]["pages_with_2plus_columns"]
    # `label errors` is lawfully None: Docling-egret and DocLayNet share zero
    # labels with PP-DocLayoutV2, so there is no diagonal. A number would pass
    # misunderstanding off as measurement; comparing it would be a TypeError.
    b_lab = label_errors(base)
    b_lab_s = "не сверяется (словари разные)" if b_lab is None else str(b_lab)
    b_role = role_errors(base)
    b_merge, b_split = _beds(base, "слияние"), _beds(base, "дробление")
    b_dup, b_in = (_beds(base, "вложенный дубль"),
                   _beds(base, "внутри ненайденного"))
    log(f"исходно: артефактов {b_found*100:.0f}%, текста {b_text_s}, "
        f"порядок модели {b_ord_s}, порядок сборки {b_asm_s}, "
        f"лишних прыжков {b_jump} на {b_multi} многоколоночных страницах, "
        f"ошибок ярлыка {b_lab_s}, "
        f"ошибок разряда {b_role}, "
        f"слияний {b_merge}, дроблений {b_split}, "
        f"вложенных дублей {b_dup}, внутри ненайденного {b_in}")

    def R(mm=None, tt=None):
        return compare_pages(tt or T, mm or M)

    def found(mm=None, tt=None):
        return R(mm, tt)["totals"]["share"]

    def mergeable():
        """Will a merged model box really cover more than one TRUTH artefact.

        The guard must look at BOTH inputs: the damage edits model output while
        the trouble is counted against truth. Asking truth alone declared the
        probe applicable where nothing could be measured -- YOLOX on
        `matematika` has more than one artefact box on NO page, and Heron on
        `katalog` merges into a box covering truth tables by 0.27, honestly a
        spill. Both printed "NO", i.e. "the metric is dead": 3 false verdicts
        over 33 truth/detector pairs. The 0.6 threshold is `eaten`'s.
        """
        for i, t in T.items():
            mb = [b["box"] for b in M[i]["blocks"] if b["label"] in arte]
            if len(mb) < 2:
                continue
            box = [min(b[0] for b in mb), min(b[1] for b in mb),
                   max(b[2] for b in mb), max(b[3] for b in mb)]
            if sum(1 for b in t["blocks"] if b["label"] in arte
                   and cover(b["box"], box) >= 0.6) > 1:
                return True
        return False

    def nested_pair():
        """Is there a SCORED pair whose model box lies inside the truth box (the
        counter's own 0.9 threshold). It makes "boxes duplicated" applicable: a
        copy of such a box is left unpaired and falls inside a FOUND artefact.
        Without one there is nothing to duplicate -- YOLOX on `matematika` has
        NO artefact boxes at all, and "did not grow" would speak of the book,
        not the metric."""
        for i, t in T.items():
            mb = [b for b in M[i]["blocks"] if b["label"] in arte]
            used = set()
            for b in [z for z in t["blocks"] if z["label"] in arte]:
                j = _pick(b, mb, used)
                if j is None:
                    continue
                used.add(j)
                if cover(mb[j]["box"], b["box"]) >= 0.9:
                    return True
        return False

    def _mixable():
        """Does shuffling the columns change anything at all.

        Round-robin damage on a page where the model ALREADY deals blocks round
        robin is empty, and "did not grow" would speak of the book, not the
        metric. `bench/matematika` is that case: its one multi-column page
        holds six display formulas and their six numbers at the right margin,
        already maximal alternation -- 10 excess jumps, all ten lawful. The
        guard looks at the BLOCK ORDER, not the quantity, so it cannot cover a
        dead metric, which would say "NO" on any book that really changed.
        """
        mixed = _mix_columns(M)
        return any([b["box"] for b in _columns_of(mixed[i])[0]]
                   != [b["box"] for b in _columns_of(p)[0]]
                   for i, p in M.items())

    def halves_inside():
        """Will any half land inside a truth artefact: without one the "inside a
        miss" probe is empty. The cut artefact's own pair is not asked -- a
        half covers truth by about a half and cannot reach COVER_MATCH under
        any tolerance."""
        return _nested(_split_all(M, arte))

    def one_box_dash():
        """A dash is `None` in ALL THREE places at once: the quantity, the
        per-page share, the denominator. One of three is not enough -- a
        quantity that forgot its denominator would print "0 on 600 pages"."""
        j = R(_one_box(M))["jumps"]
        return (j["excess_jumps"] is None and j["per_page"] is None
                and j["pages_counted"] == 0)

    def _nested(mm):
        for i, t in T.items():
            tb = [b["box"] for b in t["blocks"] if b["label"] in arte]
            for x in mm[i]["blocks"]:
                if x["label"] in arte and any(cover(x["box"], b) >= 0.9
                                              for b in tb):
                    return True
        return False

    # A probe with nothing to grip on this book is NOT a failure but "no data":
    # "no more merges" on a book with one artefact per page says nothing about
    # the metric. Such probes return None and print under a mark of their own.
    probes = [
        # --- damage to the model output
        ("сдвиг рамок на треть их размера", "упало",
         lambda: found(_shift_rel(M, 0.34)) < b_found),
        ("рамки раздуты в 1.5 раза (разлив)", "упало",
         lambda: found(_grow(M, 1.5)) < b_found),
        ("рамки сжаты в 0.6 раза (срез)", "упало",
         lambda: found(_grow(M, 0.6)) < b_found),
        ("артефакты выкинуты вовсе", "ноль",
         lambda: found(_only(M, lambda b: b["label"] not in arte)) == 0.0),
        # A TEXT label of the same vocabulary, not an invented one: an
        # invented one breaks `policy.role` in the diagnosis, so the probe
        # would fail with someone else's error instead of its answer.
        (f"артефакты названы {plain}", "ноль",
         lambda: None if not plain
                 else found(_relabel(M, lambda l: plain if l in arte else l)) == 0.0),
        ("рамки продублированы", "не выросло",
         lambda: found(_duplicate(M)) <= b_found),
        ("разметка сдвинута на страницу", "упало",
         lambda: found(_shuffle_pages(M)) < b_found),
        ("ранги модели перевёрнуты", "порядок модели упал",
         lambda: None if b_ord is None
                 else R(_reverse_order(M))["model_order"]["agreement"]
                      < b_ord),
        # The same damage, and the second quantity must NOT budge: ranks and
        # the list are different things, and scoring assembly by rank would
        # show here at once.
        ("ранги модели перевёрнуты", "порядок сборки НЕ изменился",
         lambda: None if b_asm is None
                 else R(_reverse_order(M))["assembly_order"]["agreement"]
                      == b_asm),
        ("порядок сборки перевёрнут (список блоков)", "упало",
         lambda: None if b_asm is None
                 else R(_reverse_blocks(M))["assembly_order"]["agreement"]
                      < b_asm),
        # --- damage aimed at order WITHOUT TRUTH
        ("две колонки перемешаны", "лишних прыжков больше",
         lambda: None if not (b_multi and _mixable())
                 else R(_mix_columns(M))["jumps"]["excess_jumps"] > b_jump),
        ("все рамки в одну колонку", "лишних прыжков ноль",
         lambda: None if not b_jump
                 else R(_one_column(M))["jumps"]["excess_jumps"] == 0),
        # TWO ZEROS, A PROBE FOR EACH. The previous one demands the quantity
        # FALL TO ZERO where it is computed -- many boxes, one column, no
        # transitions. This one demands NO QUANTITY AT ALL on a one-box page,
        # where a zero would lie "assembly runs straight through".
        ("страница из одной рамки в счёте", "величина ПРОЧЕРК, а не ноль",
         one_box_dash),
        # --- damage aimed at the NAMED counters
        ("артефакты страницы слиты в один", "слияний больше",
         lambda: None if not mergeable()
                 else _beds(R(_merge_all(M, arte)), "слияние") > b_merge),
        ("каждый артефакт разрезан пополам", "дроблений больше",
         lambda: _beds(R(_split_all(M, arte)), "дробление") > b_split),
        # A nested box has TWO names, each needing its probe: one damage
        # lifting both could not tell a live counter from one stuck to its
        # neighbour. A copy of a scored box is a duplicate; a half whose
        # artefact is no longer found is "inside a miss", with no original.
        ("рамки продублированы", "вложенных дублей больше",
         lambda: None if not nested_pair()
                 else _beds(R(_duplicate(M)), "вложенный дубль") > b_dup),
        ("каждый артефакт разрезан пополам", "внутри ненайденного больше",
         lambda: None if not halves_inside()
                 else _beds(R(_split_all(M, arte)),
                            "внутри ненайденного") > b_in),
        # --- damage aimed at LABEL CONFUSION (the second of the three)
        #
        # "No data", not "NO", when the sides speak different vocabularies:
        # above 100% errors there are none, and on egret/yolox this probe
        # printed "NO" for a fault of comparison, 698/698 pairs being errors
        # before any damage. Now the quantity is honestly not computed there.
        (f"ярлык {pick} подменён на {other}", "ошибок ярлыка больше",
         lambda: _grew(label_errors(R(_relabel(
                     M, lambda l: other if l == pick else l))), b_lab)
                 if (pick and other) else None),
        # BUCKET confusion lives across the vocabulary border and must be able
        # to fail like the rest. The damage is across a bucket, not within one:
        # `table`->`chart` cannot move this number by construction.
        (f"артефакты названы {plain}", "ошибок разряда больше",
         lambda: None if not (plain and any(
                     policy.role(k.split("->", 1)[0]) == "artifact"
                     for k in base["label_confusion"]))
                 else role_errors(R(_relabel(
                     M, lambda l: plain if l in arte else l))) > b_role),
        (f"ярлык {pick} подменён на {other}", "локализация НЕ изменилась",
         lambda: None if not (pick and other)
                 else found(_relabel(M, lambda l: other if l == pick else l)) == b_found),
        # --- the "sense whole" quantity needs a probe too
        ("артефакты страницы слиты в один", "смысл цел падает",
         lambda: None if not _multi(T, arte)
                 else R(_merge_all(M, arte))["sense"]["merged"]
                      > base["sense"]["merged"]),
        # 0.85 per side is 0.72 of the area: the object no longer fits
        # (threshold 0.90) but is still visible (neighbour 0.5), i.e. CROPPED.
        # A stronger squeeze drives it into "not seen", another loss than the
        # probe name promises.
        ("рамки сжаты в 0.85 раза", "обрезанных больше",
         lambda: R(_grow(M, 0.85))["sense"]["cropped"] > base["sense"]["cropped"]),
        ("рамки сжаты вдвое", "целых меньше",
         lambda: R(_grow(M, 0.5))["sense"]["intact"] < base["sense"]["intact"]),
        # Dropping the artefacts leaves the text boxes, so objects go into
        # "called text" and "not seen"; the probe looks at the sum.
        ("артефакты выкинуты вовсе", "целых не осталось",
         lambda: R(_only(M, lambda b: b["label"] not in arte))["sense"]["intact"] == 0),
        # --- damage to TRUTH: the metric must look at both its inputs
        ("истина сдвинута на треть размера рамки", "упало",
         lambda: found(tt=_shift_rel(T, 0.34)) < b_found),
        ("истина раздута в 1.5 раза", "упало",
         lambda: found(tt=_grow(T, 1.5)) < b_found),
        # The order-annotation flag is an input like the boxes, and damaging it
        # must yield SILENCE, not a number: the `True` default made an erased
        # flag indistinguishable from a declared one.
        ("у истины стёрт признак разметки порядка", "НЕ СВЕРЯЕТСЯ, а не число",
         lambda: None if b_asm is None
                 else all(R(tt=_forget_order_mark(T))[k]["agreement"] is None
                          for k in ("model_order", "assembly_order"))),
        ("текст и служебное выкинуты из истины", "текста ноль",
         lambda: None if not any(policy.role(b["label"]) != "artifact"
                                 for p in T.values() for b in p["blocks"])
                 else R(tt=_only(T, lambda b: b["label"] in arte))
                      ["text_and_furniture"]["share"] in (0.0, None)),
    ]
    bad = mute = seen = 0
    for name, want, probe in probes:
        # AN EXCEPTION IN A PROBE IS NOT A FALLEN BATTERY. The header remembers
        # a report line killing a whole run with a TypeError on the golden
        # bench, nothing after it printed and no total at all. `fitness` had
        # the trap; here there was none.
        try:
            ok = probe()
        except Exception as e:                                  # noqa: BLE001
            ok = False
            # NOT the word "fell": seven probes have "fell" for their `want`
            # (there it means "the quantity must fall"), and it would come out
            # "fell -- fell: ValueError". Different things, different words.
            want = f"{want} — ПРОБА БРОСИЛА {type(e).__name__}: {e}"
        mark = "нет данных" if ok is None else ("ok " if ok else "НЕТ")
        log(f"  {mark:>10}  {name}: {want}")
        bad += ok is False
        mute += ok is None
        seen += 1

    # --- damage to OUR OWN thresholds, each one APART
    keep_c, keep_t, keep_p = COVER_MATCH, TOUCH, TOL_PX

    def at(cover=None, touch=None, tol=None):
        """The share at ONE changed threshold, the others left in place."""
        global COVER_MATCH, TOUCH, TOL_PX
        try:
            COVER_MATCH = keep_c if cover is None else cover
            TOUCH = keep_t if touch is None else touch
            TOL_PX = keep_p if tol is None else tol
            return compare_pages(T, M)
        finally:
            COVER_MATCH, TOUCH, TOL_PX = keep_c, keep_t, keep_p

    # PROBES ON OUR OWN THRESHOLDS. The previous two compared THE CEILING WITH
    # ITSELF: at COVER_MATCH=0 the share equals the ceiling by construction and
    # the skip fired at "the share is already at the ceiling", so the probe
    # always passed; TOL_PX was not restored either, so threshold 0.99 was
    # measured at zero tolerance -- two thresholds moved at once, the fault
    # this battery reproaches others for. A threshold must now be a MONOTONE
    # lever: stricter never more, softer never less, one inequality strict.
    #
    # THE OTHER TWO GROUPS SIT UNDER THE SAME TRAP AS THE LOOP ABOVE. The first
    # version of this fix left the thresholds and the lone 3 px shift bare,
    # though their quantities are computed BEFORE any loop: a broken threshold
    # probe then gave 28 printed lines of 33 and NOT ONE total. A refusal here
    # is a named "NO" and a truncated denominator, not silence -- "probes 20"
    # against 33 declared shouts that the battery did not arrive.
    try:
        hi, lo = min(0.95, keep_c + 0.15), max(0.05, keep_c - 0.35)
        c_hi = at(cover=hi)["totals"]["share"]
        c_lo = at(cover=lo)["totals"]["share"]
        t_hi = at(tol=keep_p * 8)["totals"]["share"]
        blind = _beds(at(touch=1.01), "не увидел")
        base_blind = _beds(base, "не увидел")

        # TWO QUESTIONS, AND ONE PROBE MUST NOT ASK BOTH. "Is the threshold
        # monotone" is a property of the METRIC -- stricter cannot give more,
        # softer cannot give less -- and holds on any book. "Is the threshold
        # dead" is a property of the BOOK: where every matched pair lies far
        # from the border there is nothing to move, and "did not budge" speaks
        # of the book. Predicting that is no more accurate than the metric
        # itself, since greedy matching reshuffles pairs at another threshold,
        # so we do NOT guess: nothing moved either way prints "no data" and
        # says where the lever is truly checked. An inert threshold cannot hide
        # there -- it would give "no data" on ALL nine books at once.
        moved = (c_hi < b_found) or (c_lo > b_found)
        # The smallest two-sided cover among matched pairs is a quantity, not a
        # probe: it shows how close to the border the sample comes at all.
        worst = 1.0
        for i, t in sorted(T.items()):
            mb = [b for b in M[i]["blocks"] if b["label"] in arte]
            used = set()
            for b in [x for x in t["blocks"] if x["label"] in arte]:
                j = _pick(b, mb, used)
                if j is None:
                    continue
                used.add(j)
                worst = min(worst, cover(b["box"], _pad(mb[j]["box"], keep_p)),
                            cover(mb[j]["box"], _pad(b["box"], keep_p)))
        for name, ok, why in (
                (f"COVER_MATCH монотонен: строже {c_hi*100:.0f}%, база "
                 f"{b_found*100:.0f}%, мягче {c_lo*100:.0f}%",
                 c_hi <= b_found <= c_lo, "строже не больше, мягче не меньше"),
                (f"COVER_MATCH не мёртв (худшее покрытие совпавшей пары "
                 f"{worst:.2f} при пороге {keep_c:.2f})",
                 True if moved else None,
                 "сдвинулся хоть в одну сторону; «нет данных» значит, что на "
                 "ЭТОЙ книге все пары далеко от границы"),
                (f"TOL_PX x8 ({t_hi*100:.0f}% против {b_found*100:.0f}%)",
                 t_hi >= b_found, "не меньше"),
                (f"TOUCH=1.01 (не увидел {blind} против {base_blind})",
                 blind > base_blind, "бед «не увидел» больше")):
            mark = "нет данных" if ok is None else ("ok " if ok else "НЕТ")
            log(f"  {mark:>10}  {name}: {why}")
            bad += ok is False
            mute += ok is None
            seen += 1

        # --- SWEEP OVER THE COLUMN GROUPING PARAMETERS
        #
        # Until it is said AS A NUMBER how much the quantity depends on a
        # parameter, "4.53 against 0.79" reads as a verdict on the model when
        # it may be a difference of rulers -- as already happened here, see the
        # file header. The sweep is not a probe and does not count towards
        # uncaught damage: it is about what a difference MEANS.
        sw = column_jumps_sweep(M)
        lo, hi, b0 = sw["min"], sw["max"], sw["baseline"]
        if lo is None:
            log(f"  развёртка группировки колонок: величина ПРОЧЕРК во всех "
                f"{sw['points']} точках — на этом стенде мерить не на чем")
        else:
            pt = {p["value"]: _fmt_point(p["shifted"])
                  for p in sw["by_point"]
                  if p["value"] is not None}
            # The default can be ZERO and can be a DASH, so dividing by it is
            # forbidden: on `katalog` it is zero, and a range "in percent of
            # the default" would kill the battery by zero division on the bench
            # with least to measure anyway.
            b0s = "прочерк" if b0 is None else f"{b0:.2f}"
            pct = ("" if not b0 else
                   f", то есть {(hi - lo) / b0 * 100:.0f}% от умолчания")
            log(f"  развёртка группировки колонок ({sw['quantity']}): умолчание "
                f"{b0s}, по {sw['points']} точкам гуляет {lo:.2f}..{hi:.2f} "
                f"(размах {hi - lo:.2f}{pct}); ниже всего при «{pt[lo]}», выше "
                f"всего при «{pt[hi]}»; прочерков {sw['dashes']}")
        # THE MAIN QUESTION ABOUT SENSITIVITY. Spread alone does not forbid the
        # quantity: moving ALL variants together, the choice between them
        # holds. What forbids it is variants swapping places.
        rk = column_jumps_ranking(_order_variants(M))
        span = "; ".join(
            f"{n} {a:.2f}..{b:.2f}" if a is not None else f"{n} прочерк"
            for n, (a, b) in rk["ranges"].items())
        if rk["stable"]:
            # A tie at every point is NOT proof: a pair the quantity never
            # told apart says nothing about the choice.
            log(f"  порядок вариантов сборки на всей развёртке УСТОЙЧИВ: "
                f"{rk['variants']} варианта, {rk['pairs']} пар, ни одна не "
                f"перевернулась на {rk['points']} точках; различает "
                f"{rk['pairs_distinguished']} пар из {rk['pairs']}"
                + (f", ничья на всех точках у {len(rk['tied_pairs'])} "
                   f"({'; '.join(rk['tied_pairs'])}) — про них величина молчит"
                   if rk["tied_pairs"] else "")
                + f". {_ranking_rule(rk)} Пределы: {span}")
        else:
            log(f"  ВНИМАНИЕ: порядок вариантов сборки МЕНЯЕТСЯ от параметров "
                f"группировки — перевернулось {len(rk['flipped_pairs'])} пар "
                f"из {rk['pairs']} на {rk['points']} точках "
                f"({'; '.join(rk['flipped_pairs'])}). ВЫБИРАТЬ модель или "
                f"правило сборки по этой величине НЕЛЬЗЯ: знак разницы держится "
                f"не на данных, а на наших параметрах. {_ranking_rule(rk)} "
                f"Пределы: {span}")

        # --- small damage must NOT be caught
        #
        # EXACT equality was fine while a bench held a hundred artefacts, where
        # one moved box is a percent. The golden bench has 1232, and a
        # three-pixel shift moved two -- the probe screamed "HYSTERICAL" at
        # 0.16%, which is lawful granularity, not jitter. The tolerance is
        # named as a number and printed: it IS our decision.
        tiny = found(_shift(M, 3, 3))
        n = base["totals"]["artifacts"]
        moved = abs(tiny - b_found) * n
        # THE TOLERANCE IS COMPUTED, NOT DECREED. It used to be max(1, 0.5% of
        # the artefact count), a figure out of nowhere. The right measure is
        # how many pairs SIT ON THE BORDER: a pair at cover 0.75 with threshold
        # 0.75 tips on a three-pixel shift because the data is on the edge, not
        # because the metric shakes -- dots.ocr has six such pairs, and the
        # probe blamed the metric for a property of the model. The window
        # FOLLOWS FROM THE SHIFT: d pixels change two-sided cover by at most
        # d/width plus d/height, and a pair with less headroom tips BY
        # CONSTRUCTION.
        d = 3.0
        fragile = 0
        for i, t in sorted(T.items()):
            mb = [b for b in M[i]["blocks"] if b["label"] in arte]
            used = set()
            for b in [x for x in t["blocks"] if x["label"] in arte]:
                j = _pick(b, mb, used)
                if j is None:
                    continue
                used.add(j)
                x = mb[j]["box"]
                c = min(cover(b["box"], _pad(x, keep_p)),
                        cover(x, _pad(b["box"], keep_p)))
                w = max(1.0, min(b["box"][2] - b["box"][0], x[2] - x[0]))
                h = max(1.0, min(b["box"][3] - b["box"][1], x[3] - x[1]))
                fragile += (c - keep_c) < (d / w + d / h)
        tol = max(1.0, float(fragile))
        ok = moved <= tol
        log(f"  {'ok ' if ok else 'НЕТ'}  сдвиг на 3 пикселя: переехало "
            f"{moved:.0f} рамок из {n}; допуск {tol:.0f} — столько пар сидит "
            f"на самой границе покрытия")
        bad += not ok
        seen += 1

    except Exception as e:                                      # noqa: BLE001
        log(f"  {'НЕТ':>10}  ОСТАТОК БАТАРЕИ НЕ ДОЕХАЛ: "
            f"{type(e).__name__}: {e}")
        bad += 1
        seen += 1
    log("чего эта батарея НЕ ловит: неверную ИСТИНУ (против неё только глаза "
        "и `books overlay`); неверный перевод координат моделью (истина и "
        "вывод сверяются друг с другом, а не с растром); подмену книги при "
        "отсутствии слепка рядом; ошибку ярлыка ВНУТРИ разряда, если она "
        "одинакова у истины и модели.")
    # A QUANTITY, NOT THE WORD "DONE", as in `fitness` and `text`: one
    # "uncaught damage: N" line left out the seven probes of thirty-three that
    # measured NOTHING, so the battery printed a zero having measured less than
    # four fifths. THE DENOMINATOR IS COUNTED FROM WHAT WAS PRINTED (`seen`),
    # not derived from `len(probes)` -- there are THREE groups (main loop,
    # thresholds, lone 3 px shift), and adding them by hand gave "probes 32"
    # against 33 printed outcomes.
    log(f"батарея контуров: проб {seen}, померено {seen - mute}, "
        f"нечем мерить {mute} (см. строки «нет данных»), непойманных {bad}")
    return bad

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

