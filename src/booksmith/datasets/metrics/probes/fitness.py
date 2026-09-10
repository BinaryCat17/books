"""Probes of the ink metric: spoil the output, the truth and our thresholds."""
import json
import os
import tempfile

from booksmith.core import page, policy
from booksmith.datasets.metrics.base import Probe
from booksmith.processing.assess import ink


def _edit(M, fn):
    return {i: {**p, "blocks": [b for b in map(fn, p["blocks"]) if b]}
            for i, p in M.items()}


def _scale(b, f):
    x0, y0, x1, y1 = b["box"]
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    w, h = (x1 - x0) * f / 2, (y1 - y0) * f / 2
    return {**b, "box": [cx - w, cy - h, cx + w, cy + h]}


def _shift(b, f=0.5):
    """The box down by a share of its own height."""
    x0, y0, x1, y1 = b["box"]
    d = (y1 - y0) * f
    return {**b, "box": [x0, y0 + d, x1, y1 + d]}


def _offpage(b):
    """The box wholly off the top-left corner, RIGHT against it: the trouble is
    the negative end of the slice, which breaks the harder the nearer zero."""
    x0, y0, x1, y1 = b["box"]
    return {**b, "box": [x0 - x1 - 20.0, y0 - y1 - 20.0, -20.0, -20.0]}


def _merge(M):
    """Every artefact box of a page into ONE enclosing box: three tables
    arriving as one picture, the worst thing that happens to structure."""
    out = {}
    for i, p in M.items():
        art = [b for b in p["blocks"] if policy.UNION.role(b["label"]) == "artifact"]
        bl = [b for b in p["blocks"] if policy.UNION.role(b["label"]) != "artifact"]
        if art:
            bl.append({**art[0], "box": [
                min(b["box"][0] for b in art), min(b["box"][1] for b in art),
                max(b["box"][2] for b in art), max(b["box"][3] for b in art)]})
        out[i] = {**p, "blocks": bl}
    return out


def _traced(M, step=8):
    """Every box cut into a grid of `step`-pixel squares: a model that traces
    the ink takes all of it at less area than an honest run. The grid is built
    from the model's own boxes, so this needs no raster."""
    out = {}
    for i, p in M.items():
        bl, n = [], 0
        for b in p["blocks"]:
            x0, y0, x1, y1 = (int(v) for v in b["box"])
            for y in range(y0, y1 + 1, step):
                for x in range(x0, x1 + 1, step):
                    bl.append({**b, "block_id": n,
                               "box": [x, y, min(x + step - 1, x1),
                                       min(y + step - 1, y1)]})
                    n += 1
        out[i] = {**p, "blocks": bl}
    return out


def _double(M):
    """Hand every artefact box out a SECOND time, now as a text one."""
    out = {}
    for i, p in M.items():
        add = [{**b, "label": "text", "block_id": 10 ** 6 + j}
               for j, b in enumerate(p["blocks"])
               if policy.UNION.role(b["label"]) == "artifact"]
        out[i] = {**p, "blocks": p["blocks"] + add}
    return out


def _at(name, value, fn):
    """Move OUR OWN threshold for one probe and put it back. The thresholds
    live on the measurement module, where `measure` reads them."""
    old = getattr(ink, name)
    setattr(ink, name, value)
    try:
        return fn()
    finally:
        setattr(ink, name, old)


def _halve(M):
    """Every artefact box into two halves, flush against each other: no ink is
    lost and the object no longer cuts as ONE picture."""
    out = {}
    for i, p in M.items():
        bl = []
        for b in p["blocks"]:
            if policy.UNION.role(b["label"]) != "artifact":
                bl.append(b)
                continue
            x0, y0, x1, y1 = b["box"]
            cx = (x0 + x1) / 2
            bl.append({**b, "box": [x0, y0, cx, y1]})
            bl.append({**b, "box": [cx, y0, x1, y1]})
        out[i] = {**p, "blocks": bl}
    return out


def probes(bench, run) -> list:
    pdf = bench.pdf
    detect_dir = run.pages_dir
    truth_dir = bench.truth_dir if bench is not None and bench.truth_dir else ""
    base = ink.measure(pdf, detect_dir, truth_dir)
    M0 = page.load_pages(detect_dir)
    T0 = page.load_pages(truth_dir) if truth_dir else {}
    once = {}

    def _dump(M, d):
        for i, p in M.items():
            with open(os.path.join(d, f"{i:04d}.json"), "w",
                      encoding="utf-8") as f:
                json.dump(p, f, ensure_ascii=False)
        return d

    def R(M):
        """Measure against SPOILED model output. The copy on disk goes with the
        measurement, whatever happens inside it."""
        with tempfile.TemporaryDirectory() as d:
            return ink.measure(pdf, _dump(M, d), truth_dir)

    def RT(T):
        """Measure against spoiled TRUTH; the model output stays whole."""
        with tempfile.TemporaryDirectory() as d:
            return ink.measure(pdf, detect_dir, _dump(T, d))

    def R2():
        """The book again, unspoiled -- for probes that move OUR threshold
        rather than the output. The ink masks are cached, so this is the junk
        mask recomputed and not the pages re-rendered."""
        return ink.measure(pdf, detect_dir, truth_dir)

    def _on_junk(M):
        """A full-height box over every junk run: pure damage, finds nothing.
        Junk is a property of the sheet, so this one needs the raster."""
        import numpy as np
        import pymupdf
        doc = pymupdf.open(pdf)
        try:
            out = {}
            for i, p in M.items():
                im = ink._ink_of(pdf, doc, i, p["dpi"])
                j = ink._junk_columns(im)
                add = []
                if j.any():
                    d = np.diff(np.r_[0, j.astype(np.int8), 0])
                    for a, b in zip(np.flatnonzero(d == 1),
                                    np.flatnonzero(d == -1), strict=True):
                        add.append({"block_id": 900000 + len(add),
                                    "box": [int(a), 0, int(b - 1),
                                            im.shape[0] - 1],
                                    "label": "text", "score": 1.0, "order": 0,
                                    "content": None, "kind": "none"})
                out[i] = {**p, "blocks": p["blocks"] + add}
            return out
        finally:
            doc.close()

    def art(b):
        return policy.UNION.role(b["label"]) == "artifact"

    # A full-sheet box, and DELIBERATELY an artefact: with a text label the
    # degenerate answer is tested at half strength, winning nothing on objects.
    full = {i: {**p, "blocks": [{"box": [0, 0, p["width"], p["height"]],
                                 "label": "image", "block_id": 0, "order": 0,
                                 "score": None, "content": None,
                                 "kind": "none"}]}
            for i, p in M0.items()}

    def only(key, fn):
        """Damage two probes both reach for, measured once: on the golden bench
        every extra `measure` is 600 rendered pages."""
        if key not in once:
            once[key] = fn()
        return once[key]

    def halved():
        return only("halved", lambda: R(_halve(M0)))

    def as_text():
        return only("as_text", lambda: R(_edit(M0, lambda b: {**b, "label": "text"})))

    def moved():
        return only("moved", lambda: RT(_edit(T0, _shift)))

    return [Probe(n, e, f) for n, e, f in (
        ("artefact boxes cut in half", "fewer cut as one picture",
         lambda: None if not base["objects"] else
                 halved()["in_one_box"] < base["in_one_box"]),
        ("artefact boxes cut in half", "and no ink is lost by it",
         lambda: None if not base["objects"] else
                 halved()["object_ink_in_boxes"] >= base["object_ink_in_boxes"]),
        ("nesting", "no more cut as one picture than intact",
         lambda: None if not base["objects"] else
                 base["in_one_box"] <= base["intact"]),
        ("no boxes at all", "zero ink under boxes",
         lambda: R(_edit(M0, lambda b: None))["ink_under_boxes"] == 0),
        # Without this the metric could be won with rubbish, finding nothing.
        ("boxes moved off the top-left corner", "zero ink under boxes",
         lambda: R(_edit(M0, _offpage))["ink_under_boxes"] == 0),
        ("boxes shrunk by half", "less object ink preserved",
         lambda: None if not base["objects"] else
                 R(_edit(M0, lambda b: _scale(b, 0.5)))["object_ink_in_boxes"]
                 < base["object_ink_in_boxes"]),
        ("artefacts called text", "zero ink under artefacts",
         lambda: as_text()["ink_under_artifact"] == 0),
        ("artefacts called text", "objects left as text",
         lambda: None if not base["objects"] else
                 as_text()["left_as_text"] > base["left_as_text"]),
        ("boxes dropped except the text ones", "fewer intact",
         lambda: None if not base["objects"] else
                 R(_edit(M0, lambda b: None if art(b) else b))["intact"]
                 < base["intact"]),
        # Without this the metric could be taken with one box, having found
        # nothing.
        ("one box over the whole sheet", "ink 100%, but area 100% too",
         lambda: (lambda r: r["ink_under_boxes"] == r["ink_total"]
                  and r["boxes_area"] == r["sheet_area"])(R(full))),
        # ----------------------------------------- the junk mask, ours ---
        # A threshold of ours decides what is not information, so it is probed
        # from both ends. What is asserted is MONOTONY in the gate -- a wider
        # band can only admit more -- since a rise is a property of the paper;
        # `no data` on a book with no solid dark column at all.
        ("the binding band blown to the whole sheet",
         "the gate can only admit more, never less",
         lambda: None if not base["dark_columns"] else
                 _at("MID", 0.5, lambda: R2()["ink_junk"]) >= base["ink_junk"]),
        ("the crossing veto opened",
         "no run can be a rule any more, so there is more junk, not less",
         lambda: None if not base["dark_columns"] else
                 _at("RULE_RUN", 1.01, lambda: R2()["ink_junk"])
                 >= base["ink_junk"]),
        ("the binding band squeezed to nothing",
         "nothing is positional any more: no junk at all",
         lambda: None if not base["dark_columns"] else
                 _at("MID", 0.0, lambda: _at("MIN_SPREAD_RATIO", 10 ** 6,
                                             lambda: R2()["ink_junk"])) == 0),
        ("the crossing veto shut",
         "a rule crosses everything now, so nothing is junk",
         lambda: None if not base["ink_junk"] else
                 _at("RULE_RUN", 0.0, lambda: R2()["ink_junk"]) == 0),
        ("the width cap squeezed to nothing",
         "every band is too wide to be a shadow: no junk",
         lambda: None if not base["ink_junk"] else
                 _at("JUNK_WIDTH", 0.0, lambda: R2()["ink_junk"]) == 0),
        ("every pixel black",
         "a sheet that is all ink has no binding to find",
         lambda: _at("INK", 256, lambda: R2()["ink_junk"]) == 0),
        # The mask must not see the model: no output can move it, so discarding
        # junk is a property of the ruler and not a repair.
        ("the model output emptied, and a box over the whole sheet",
         "the junk mask does not move: it reads the raster, never the boxes",
         lambda: (R(_edit(M0, lambda b: None))["ink_junk"] == base["ink_junk"]
                  and R(full)["ink_junk"] == base["ink_junk"])),
        # The attack that pays on the raw number pays nothing on the clean one.
        ("a box on every junk run",
         "raw rises and CLEAN does not move -- the attack's gradient is zero",
         lambda: None if not base["ink_junk"] else
                 (lambda r: r["ink_under_boxes"] > base["ink_under_boxes"]
                  and r["clean_under_boxes"] == base["clean_under_boxes"])(
                     R(_on_junk(M0)))),
        # A detection run reads nothing, so the split sits at its floor and only
        # content moves it. Guarded on the ABSENCE of content: with content
        # everywhere already the probe would demand a rise that cannot happen.
        ("every block handed a character",
         "ink leaves as text where it left as a picture, and the artefacts "
         "do not move",
         lambda: None if not any(policy.UNION.role(b["label"]) != "artifact"
                                 and not (b.get("content") or "").strip()
                                 for p in M0.values() for b in p["blocks"])
         else (lambda r: r["ink_as_text"] > base["ink_as_text"]
               and r["ink_as_picture"] < base["ink_as_picture"]
               # The artefact ink must STAY in the picture share; asked of the
               # split, because the mutator cannot move `ink_under_artifact`.
               and r["ink_as_picture"] >= base["ink_under_artifact"])(
             R(_edit(M0, lambda b: {**b, "content": "x"})))),
        # The guard is beaten from both sides, hence three of them: rubble
        # covers the same pixels at the same area while the crops level two pays
        # for multiply, and the two degeneracies are geometric opposites.
        ("the boxes cut into a grid of tiny ones",
         "the area guard does not move ONE PIXEL, and the ink does not "
         "either -- the median box and the bill are what see it",
         lambda: (lambda r: r["boxes_area"] == base["boxes_area"]
                  and r["ink_under_boxes"] == base["ink_under_boxes"]
                  and r["median_box_area"] < base["median_box_area"] / 10
                  and r["box_count"] > base["box_count"] * 10)(R(_traced(M0)))),
        ("one box over the whole sheet",
         "the median box is the whole page -- the other end of the same guard",
         lambda: R(full)["median_box_area"] == 1.0),
        ("one box over the whole sheet",
         "and ALL objects intact — this is how the metric is won",
         lambda: None if not base["objects"] else
                 (lambda r: r["intact"] == r["objects"]
                  and r["in_one_box"] == r["objects"])(R(full))),
        # Admitted blindness with one seeing number: the older numbers must not
        # fall under merging and "arrived with company" must grow. Nothing to
        # merge where no page holds two objects, and that is an honest no data.
        ("all artefact boxes merged into one",
         "the older numbers do not fall, and 'arrived with company' grows",
         lambda: None if not base["objects"] else
                 (lambda r: (None if not r["boxes_with_many_objects"] else
                             (r["intact"] >= base["intact"]
                              and r["object_ink_in_boxes"]
                              >= base["object_ink_in_boxes"]
                              and r["arrived_with_company"]
                              > base["arrived_with_company"]),
                             f"intact {base['intact']} -> {r['intact']}, "
                             f"torn {base['torn']} -> {r['torn']}, "
                             f"with company "
                             f"{base['arrived_with_company']} -> "
                             f"{r['arrived_with_company']}"))(R(_merge(M0)))),
        # DOUBLING, as raw docling-heron does it. The union of boxes does not
        # change, so no object number has the right to move.
        ("every artefact box handed out as a text one too",
         "NOTHING changes by objects: a pixel under two boxes is one pixel",
         lambda: None if not base["objects"] else
                 (lambda r: all(r[k] == base[k] for k in
                                ("intact", "almost_intact", "bitten", "torn",
                                 "in_one_box", "left_as_text",
                                 "object_ink_in_boxes")))(R(_double(M0)))),
        # --- the second side of the spoiling: OUR OWN thresholds -----------
        # Extremes, not "nudge it and see": a nudge could change nothing on a
        # bench where every object is whole anyway, and a dead threshold would
        # pass.
        ("the ink threshold zeroed and maxed",
         "ink is now zero, now the whole sheet",
         lambda: _at("INK", 0, lambda: ink.measure(pdf, detect_dir)["ink_total"]) == 0
                 and _at("INK", 256, lambda: (lambda r: r["ink_total"]
                                              == r["sheet_area"])(
                     ink.measure(pdf, detect_dir)))),
        ("the 'intact' threshold zeroed and maxed",
         "intact is now all, now none",
         lambda: None if not base["objects"] else
                 _at("WHOLE", 0.0, lambda: (lambda r: r["intact"] == r["objects"])(
                     ink.measure(pdf, detect_dir, truth_dir)))
                 and _at("WHOLE", 1.01,
                         lambda: ink.measure(pdf, detect_dir, truth_dir)["intact"] == 0)),
        # Every threshold gets its own probe, or one killed alone slides the
        # numbers while the probes stay green. Each is brought TO ITS
        # NEIGHBOUR: the class between two must move entirely.
        ("the 'almost intact' threshold brought to its neighbours",
         "the class between 'intact' and 'bitten' moves entirely",
         lambda: None if not base["almost_intact"] + base["bitten"] else
                 _at("ALMOST", ink.WHOLE,
                     lambda: ink.measure(pdf, detect_dir, truth_dir)["almost_intact"] == 0)
                 and _at("ALMOST", ink.BITTEN,
                         lambda: ink.measure(pdf, detect_dir, truth_dir)["bitten"] == 0)),
        ("the 'bitten' threshold brought to its neighbours",
         "the class between 'almost intact' and 'torn' moves entirely",
         lambda: None if not base["bitten"] + base["torn"] else
                 _at("BITTEN", 0.0,
                     lambda: ink.measure(pdf, detect_dir, truth_dir)["torn"] == 0)
                 and _at("BITTEN", ink.ALMOST,
                         lambda: ink.measure(pdf, detect_dir, truth_dir)["bitten"] == 0)),
        # The dark column is a ruler too: blown to 0.0 every column holding a
        # single dark pixel is one, squeezed to 1.0 no such thing exists.
        # `no data` on a book with no dark column, as its four siblings above.
        ("the dark column blown up and squeezed",
         "now all the ink is in columns, now none",
         lambda: None if not base["dark_columns"] else
                 (_at("GUTTER", 0.0, lambda: ink.measure(pdf, detect_dir, truth_dir)
                      ["ink_in_dark_columns"]) >= base["ink_in_dark_columns"]
                  and _at("GUTTER", 1.0, lambda: ink.measure(pdf, detect_dir, truth_dir)
                          ["dark_columns"]) < base["dark_columns"])),
        # EDGE is printed as "of what was lost, N% lies in the band at the
        # edge". Blown to 1.0 and not 0.5 because the band rounds DOWN, leaving
        # an uncovered one-pixel strip across an odd-sided sheet.
        ("the edge band blown up and squeezed",
         "at the edge now everything lost, now less",
         lambda: None if base["ink_total"] <= base["ink_under_boxes"] else
                 (lambda lost:
                  _at("EDGE", 1.0, lambda: ink.measure(pdf, detect_dir, truth_dir)
                      ["ink_outside_boxes_at_edge"]) == lost
                  and _at("EDGE", 0.0, lambda: ink.measure(pdf, detect_dir, truth_dir)
                          ["ink_outside_boxes_at_edge"]) < lost)(
                     base["ink_total"] - base["ink_under_boxes"])),
        # --- the third side of the spoiling: THE TRUTH ---------------------
        # What is asked is the NUMBER of object ink, not the share preserved: on
        # a perfectly outlined book the share does not move when truth shifts.
        ("truth shifted down by half an object",
         "object ink came out different",
         lambda: None if not base["objects"] else
                 (moved()["object_ink"] != base["object_ink"],
                  f"object ink {base['object_ink']} -> "
                  f"{moved()['object_ink']}, preserved "
                  f"{base['object_ink_in_boxes'] / max(1, base['object_ink']) * 100:.1f}%"
                  f" -> {moved()['object_ink_in_boxes'] / max(1, moved()['object_ink']) * 100:.1f}%")),
        ("truth moved off the sheet",
         "zero objects, and all of them 'empty'",
         lambda: None if not base["objects"] else
                 (lambda r: r["objects"] == 0 and r["empty_objects"]
                  == base["objects"] + base["empty_objects"])(
                     RT(_edit(T0, _offpage)))),
    )]
