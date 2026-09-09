"""The ink metric as a `Metric`, with its battery: will the meaning reach
the second level.

The MEASUREMENT is `processing.assess.ink` (measure, report, the
thresholds), where the production pipeline can ask it of any book without
truth; this file holds what needs the bench: the probes that spoil model
output and truth and demand the number fall, and the `Metric` that turns
the measurement's counts into a `Record`. The shares are computed here
once, from the same counts the report divides.
"""
import os
import shutil

from booksmith.core import page, policy
from booksmith.datasets.metrics.base import (Metric, Probe, Record, Scalar,
                                             battery_summary, run_battery)
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
    """The box wholly off the top-left corner of the sheet, right against it.

    RIGHT against it: the trouble is the negative end of the slice, which breaks
    the harder the nearer to zero. Under the old code a box ending at -20
    covered the sheet bar twenty pixels, one ending at -10000 covered nothing --
    so a probe pushing it further off would catch nothing.
    """
    x0, y0, x1, y1 = b["box"]
    return {**b, "box": [x0 - x1 - 20.0, y0 - y1 - 20.0, -20.0, -20.0]}


def _merge(M):
    """Every artefact box of a page into ONE enclosing box.

    The worst thing that happens to structure: three tables arrive as one
    picture. The probe exists not to make a number fall -- it will rise -- but
    to put the instrument's blindness into its own output AS A QUANTITY.
    Unnamed, the report reads as a verdict on the model whole, and once was.
    """
    out = {}
    for i, p in M.items():
        art = [b for b in p["blocks"] if policy.role(b["label"]) == "artifact"]
        bl = [b for b in p["blocks"] if policy.role(b["label"]) != "artifact"]
        if art:
            bl.append({**art[0], "box": [
                min(b["box"][0] for b in art), min(b["box"][1] for b in art),
                max(b["box"][2] for b in art), max(b["box"][3] for b in art)]})
        out[i] = {**p, "blocks": bl}
    return out


def _traced(M, step=8):
    """Every box cut into a grid of `step`-pixel squares.

    THE CHEAT THAT BEATS THE OLDER GUARD. `area_under_boxes` was put beside
    the ink numbers because one box over the whole sheet takes all the ink;
    a model that traces the ink instead takes all of it at LESS area than an
    honest run -- on slovar, ink under boxes 1.000 at area 0.462 against the
    honest 0.991 at 0.665 -- so the guard reads the rubble as the better
    model. The grid is built from the model's own boxes rather than from the
    ink, so the mutator needs no raster and stays a pure edit of the output.
    """
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
               if policy.role(b["label"]) == "artifact"]
        out[i] = {**p, "blocks": p["blocks"] + add}
    return out


def _at(name, value, fn):
    """Move OUR OWN threshold for the probe and put it back.

    The thresholds live on the measurement module (`ink`), not here: the
    probe moves them there, where `measure` reads them."""
    old = getattr(ink, name)
    setattr(ink, name, value)
    try:
        return fn()
    finally:
        setattr(ink, name, old)


def mutations(pdf: str, detect_dir: str, truth_dir: str = "", log=print) -> int:
    """Feed the metric knowingly spoiled input and see that the number fell."""
    import json
    import shutil
    import tempfile

    base = ink.measure(pdf, detect_dir, truth_dir)
    M0 = page.load_pages(detect_dir)
    T0 = page.load_pages(truth_dir) if truth_dir else {}
    trash = []

    def _dump(M):
        d = tempfile.mkdtemp()
        trash.append(d)
        for i, p in M.items():
            with open(os.path.join(d, f"{i:04d}.json"), "w",
                      encoding="utf-8") as f:
                json.dump(p, f, ensure_ascii=False)
        return d

    def R(M):
        """Measure against SPOILED model output."""
        return ink.measure(pdf, _dump(M), truth_dir)

    def RT(T):
        """Measure against spoiled TRUTH. The model output stays whole."""
        return ink.measure(pdf, detect_dir, _dump(T))

    def R2():
        """The book again, unspoiled -- for probes that move OUR threshold
        rather than the model's output. The ink masks are cached, so this is
        the junk mask recomputed and not the pages re-rendered."""
        return ink.measure(pdf, detect_dir, truth_dir)

    def _on_junk(M):
        """A full-height box over every junk run: pure damage, finds nothing.

        The attack `ink.py` documents, as a mutator. It needs the raster --
        junk is a property of the sheet, not of the output -- and the ink
        masks are cached, so it costs the reading and not the rendering.
        """
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
                                    np.flatnonzero(d == -1)):
                        add.append({"block_id": 900000 + len(add),
                                    "box": [int(a), 0, int(b - 1),
                                            im.shape[0] - 1],
                                    "label": "text", "score": 1.0, "order": 0,
                                    "content": None, "kind": "none"})
                out[i] = {**p, "blocks": p["blocks"] + add}
            return out
        finally:
            doc.close()

    art = lambda b: policy.role(b["label"]) == "artifact"
    # A full-sheet box, and DELIBERATELY an artefact. It used to take the label
    # of the page's first block: a text one, and the degenerate answer is tested
    # at half strength, winning nothing on objects -- where it wins most.
    full = {i: {**p, "blocks": [{"box": [0, 0, p["width"], p["height"]],
                                 "label": "image", "block_id": 0, "order": 0,
                                 "score": None, "content": None,
                                 "kind": "none"}]}
            for i, p in M0.items()}
    def _halve(M):
        """Every artefact box into two halves, flush against each other.

        No ink is lost -- the union covers the same -- but the object no longer
        cuts as ONE picture: it arrives in two pieces. Without this there would
        be nothing to check the difference between "no loss" and "cuts whole".
        """
        out = {}
        for i, p in M.items():
            bl = []
            for b in p["blocks"]:
                if policy.role(b["label"]) != "artifact":
                    bl.append(b)
                    continue
                x0, y0, x1, y1 = b["box"]
                cx = (x0 + x1) / 2
                bl.append({**b, "box": [x0, y0, cx, y1]})
                bl.append({**b, "box": [cx, y0, x1, y1]})
            out[i] = {**p, "blocks": bl}
        return out

    # Damage that two probes both reach for is computed ONCE: on the golden
    # bench every extra `measure` is 600 rendered pages.
    halved = R(_halve(M0)) if base["objects"] else None
    as_text = R(_edit(M0, lambda b: {**b, "label": "text"}))
    moved = RT(_edit(T0, _shift)) if base["objects"] else None

    probes = [
        ("artefact boxes cut in half", "fewer cut as one picture",
         lambda: None if not base["objects"] else
                 halved["in_one_box"] < base["in_one_box"]),
        ("artefact boxes cut in half", "and no ink is lost by it",
         lambda: None if not base["objects"] else
                 halved["object_ink_in_boxes"]
                 >= base["object_ink_in_boxes"]),
        # The guard `None if not base["objects"]` is the neighbours' and was
        # missing here. Without `--truth` both sides are zero, `0 <= 0` is True,
        # and the battery printed "ok" about a nesting it had not checked: a
        # zero from not understanding, dressed as a satisfied condition. Mirror
        # of the trouble ten lines below, where a zero gave a false "NO" line.
        ("nesting", "no more cut as one picture than intact",
         lambda: None if not base["objects"] else
                 base["in_one_box"] <= base["intact"]),
        ("no boxes at all", "zero ink under boxes",
         lambda: R(_edit(M0, lambda b: None))["ink_under_boxes"] == 0),
        # Without this probe the metric could be won with rubbish, finding
        # nothing (`_clip`), and not one of the eight probes saw it.
        ("boxes moved off the top-left corner", "zero ink under boxes",
         lambda: R(_edit(M0, _offpage))["ink_under_boxes"] == 0),
        # The same guard, missing here too. The price: without `--truth` there
        # are no objects, "object ink in boxes" is zero before the damage and
        # after, `0 < 0` is False, and the battery printed the "NO" mark --
        # accusing the instrument where there is nothing to measure. Six books
        # of six, `books fitness … --selfcheck` without `--truth` returned 1.
        ("boxes shrunk by half", "less object ink preserved",
         lambda: None if not base["objects"] else
                 R(_edit(M0, lambda b: _scale(b, 0.5)))["object_ink_in_boxes"]
                 < base["object_ink_in_boxes"]),
        ("artefacts called text", "zero ink under artefacts",
         lambda: as_text["ink_under_artifact"] == 0),
        ("artefacts called text", "objects left as text",
         lambda: None if not base["objects"] else
                 as_text["left_as_text"] > base["left_as_text"]),
        ("boxes dropped except the text ones", "fewer intact",
         lambda: None if not base["objects"] else
                 R(_edit(M0, lambda b: None if art(b) else b))["intact"] < base["intact"]),
        # Without this probe the metric could be taken with one box, having
        # found nothing.
        ("one box over the whole sheet", "ink 100%, but area 100% too",
         lambda: (lambda r: r["ink_under_boxes"] == r["ink_total"]
                  and r["boxes_area"] == r["sheet_area"])(R(full))),
        # ----------------------------------------- the junk mask, ours ---
        # A THRESHOLD OF OURS DECIDES WHAT IS NOT INFORMATION, so it is
        # probed from both ends like every other. `no data` where the book
        # has no solid dark column at all: a drawn bench carries none, which
        # is exactly why a drawn bench is the false-positive test.
        # MONOTONE IN THE GATE, which is the invariant worth asserting: a
        # wider band can only admit more, never less. It does not RISE on
        # every book -- on "Технология огнеупоров" all 261 dark columns are
        # already at the edges, so opening the gate finds nothing new -- and
        # a probe demanding a rise there would be demanding a property of
        # the paper.
        ("the binding band blown to the whole sheet",
         "the gate can only admit more, never less",
         lambda: None if not base["dark_columns"] else
                 _at("MID", 0.5, lambda: R2()["ink_junk"])
                 >= base["ink_junk"]),
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
        # THE MASK MUST NOT SEE THE MODEL. That is the whole argument that
        # discarding junk is a property of the ruler and not a repair of the
        # model: no output can move it, so no model can win by it.
        ("the model output emptied, and a box over the whole sheet",
         "the junk mask does not move: it reads the raster, never the boxes",
         lambda: (R(_edit(M0, lambda b: None))["ink_junk"] == base["ink_junk"]
                  and R(full)["ink_junk"] == base["ink_junk"])),
        # AND THE DOCUMENTED ATTACK PAYS NOTHING. A box laid on every junk
        # run is pure damage finding nothing; on the raw number it paid
        # 85.661 -> 95.202 on a real book, and here it must move the clean
        # number by not one pixel.
        ("a box on every junk run",
         "raw rises and CLEAN does not move -- the attack's gradient is zero",
         lambda: None if not base["ink_junk"] else
                 (lambda r: r["ink_under_boxes"] > base["ink_under_boxes"]
                  and r["clean_under_boxes"] == base["clean_under_boxes"])(
                     R(_on_junk(M0)))),
        ("clean ink under boxes never exceeds the clean ink",
         "both sides are cleaned -- a denominator-only mask gives 105 %",
         lambda: base["clean_under_boxes"] <= base["ink_clean"]),
        # THE SPLIT IS EXHAUSTIVE OR IT IS NOT A SPLIT. Text plus picture is
        # exactly the boxed ink, so with `ink_outside_boxes` the three
        # account for every dark pixel on the sheet and none of them twice.
        # Overlapping boxes are what makes this worth asserting: a pixel
        # under both a crop and a paragraph is counted once, in the crop.
        ("the split against the whole",
         "text + picture is exactly the ink under boxes, never more",
         lambda: (base["ink_as_text"] + base["ink_as_picture"]
                  == base["ink_under_boxes"])),
        # A DETECTION RUN READS NOTHING, so the split sits at its floor --
        # everything a picture -- and the only way to see it move is to put
        # content in. Handing every block a character moves ink out of the
        # picture share and into the text one, and the artefact-role blocks
        # must NOT move: a plate stays a plate whatever the reader returns.
        ("every block handed a character",
         "ink leaves as text where it left as a picture, and the artefacts "
         "do not move",
         lambda: None if not any(policy.role(b["label"]) != "artifact"
                                 for p in M0.values() for b in p["blocks"])
         else (lambda r: r["ink_as_text"] > base["ink_as_text"]
               and r["ink_as_picture"] < base["ink_as_picture"]
               and r["ink_under_artifact"] == base["ink_under_artifact"])(
             R(_edit(M0, lambda b: {**b, "content": "x"})))),
        # AND THE GUARD IS BEATEN FROM THE OTHER SIDE, which is why there are
        # three of them. Cut every box into a grid and `area_under_boxes` and
        # `ink_under_boxes` are IDENTICAL to the digit -- the same pixels
        # covered by rubble instead of by blocks -- while the crops level two
        # pays for multiply. Worse in the wild: a model that traces the INK
        # takes every pixel at LESS area than an honest run (measured on
        # slovar, 1.000 of the ink at area 0.462 against the honest 0.991 at
        # 0.665), so the older guard reads the rubble as the better model.
        # The two degeneracies are geometric opposites and no one number
        # separates both. These probes demand that each catches its own.
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
        # ...and it wins on OBJECTS too, where the older probe looked at page
        # ink only: the headline line of the report is taken whole by one box,
        # and that belongs in the battery, not in the header alone.
        ("one box over the whole sheet",
         "and ALL objects intact — this is how the metric is won",
         lambda: None if not base["objects"] else
                 (lambda r: r["intact"] == r["objects"]
                  and r["in_one_box"] == r["objects"])(R(full))),
        # ADMITTED BLINDNESS, AND ONE SEEING NUMBER: the older numbers must NOT
        # fall under merging (blindness named as a quantity, not as an aside)
        # and "arrived with company" must GROW, else the instrument would go
        # blind whole and silently again. The "nothing to measure" guard is
        # special here -- there is nothing to merge if no page holds two objects
        # at once, and a book of one table is an honest "no data".
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
                             f"{r['arrived_with_company']}"))(
                     R(_merge(M0)))),
        # DOUBLING, as raw docling-heron does it with its 4435 doubled pairs.
        # The union of boxes does NOT change, so no object number has the right
        # to move. Made for a caught defect: "left as text" was `t_kept + kept`,
        # a pixel under two boxes going for two. On bench/hard36: 21 -> 31, ten
        # objects with half their ink under open sky declared "not lost".
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
        # THERE ARE FIVE THRESHOLDS, NOT TWO. Only INK and WHOLE were probed;
        # kill ALMOST, BITTEN or EDGE alone and the battery stays green while
        # the printed numbers slide (almost whole 3 -> 0 and bitten 5 -> 8;
        # bitten 5 -> 0; ink at the edge 26076 -> 529). Thresholds are brought
        # TO THEIR NEIGHBOURS rather than nudged at random: the class between
        # two must move ENTIRELY, checkable on any bench where the class holds
        # anyone. Guard on an empty class as the neighbours': nothing to measure
        # is "no data", not "ok".
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
        # EDGE is a ruler too, and printed: "of what was lost, N% lies in the
        # band at the edge". Blown up to half the shorter side it covers the
        # sheet, so ALL the lost ink must land at the edge. Truth is passed
        # although the band does not depend on it: without it `measure` walks
        # EVERY annotated page while `base` walks the truth pages only, and
        # "lost" would run on different denominators -- the probe failed on
        # that. Blown to 1.0 and not 0.5 because `int(min(h, w) * 0.5)` rounds
        # DOWN, leaving an uncovered one-pixel strip across an odd-sided sheet
        # -- 83 pixels of ink on hard36, and the probe failed on them, accusing
        # a live threshold.
        # THE SIXTH THRESHOLD IS PROBED LIKE THE FIFTH: a threshold without a
        # probe is a number that cannot be refuted. Blown to 0.0 (every column
        # holding a single dark pixel is a dark column) and squeezed to 1.0
        # (dark over the full height of the sheet, margins included -- no such
        # thing exists).
        ("the dark column blown up and squeezed",
         "now all the ink is in columns, now none",
         lambda: (_at("GUTTER", 0.0, lambda: ink.measure(pdf, detect_dir, truth_dir)
                      ["ink_in_dark_columns"]) >= base["ink_in_dark_columns"]
                  and _at("GUTTER", 1.0, lambda: ink.measure(pdf, detect_dir, truth_dir)
                          ["dark_columns"]) < base["dark_columns"])),
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
        # Spoil the truth, leave the output alone. What is asked is the NUMBER
        # of object ink, not the share preserved: on a perfectly outlined book
        # the share does not move when truth shifts, and the probe would accuse
        # the instrument where there is nothing to measure (caught on a toy page
        # whose model box coincides with the object: 100% -> 100%). The number
        # under a shifted box differs always, save on a uniformly filled sheet.
        ("truth shifted down by half an object",
         "object ink came out different",
         lambda: None if not base["objects"] else
                 (moved["object_ink"] != base["object_ink"],
                  f"object ink {base['object_ink']} -> "
                  f"{moved['object_ink']}, preserved "
                  f"{base['object_ink_in_boxes'] / max(1, base['object_ink']) * 100:.1f}%"
                  f" -> {moved['object_ink_in_boxes'] / max(1, moved['object_ink']) * 100:.1f}%")),
        ("truth moved off the sheet", "zero objects, and all of them "
         "'empty'",
         lambda: None if not base["objects"] else
                 (lambda r: r["objects"] == 0 and r["empty_objects"]
                  == base["objects"] + base["empty_objects"])(
                     RT(_edit(T0, _offpage)))),
    ]
    # THE LOOP IS THE SHARED ONE (`base.run_battery`); the spoiled copies on
    # disk are removed whatever happens inside it. The mark column was one
    # character wider here than in the other two batteries; it is not now.
    try:
        seen, mute, bad = run_battery([Probe(n, e, f) for n, e, f in probes], log)
    finally:
        for d in trash:
            shutil.rmtree(d, ignore_errors=True)
    # A QUANTITY, NOT THE WORD "DONE". This said "probes 9, uncaught 0" while
    # without `--truth` five of the nine measured nothing: green, having
    # measured less than half. The reason for silence VARIES -- no truth, an
    # empty "almost whole" class, no page with two objects at once -- so lumping
    # them into "needs truth" would swap one zero for another. Which it is, the
    # probe's own line says.
    return battery_summary("fitness", seen, mute, bad, log)

def _ratio(n, d, why):
    return Scalar(n / d if d else None, count=(n, d), why=None if d else why)


class FitnessMetric(Metric):
    """Shares from the measurement's counts: the six the report divides
    (ink under boxes, under artefacts, outside; area under boxes; objects
    intact; object ink preserved) and four it prints as counts, expressed
    here over the object count so that two runs compare (torn, left as
    text, arrived with company, cut as one picture)."""
    name = "fitness"
    needs = frozenset({"pdf", "pages"})

    def run(self, bench, run) -> Record:
        truth = bench.truth_dir if bench is not None and bench.truth_dir else ""
        res = ink.measure(bench.pdf, run.pages_dir, truth)
        return self.record(res, bench.name, run.label, bool(truth))

    def run_loaded(self, bench, run, truth, pages, note) -> Record:
        # The ink measurement renders the PDF page by page and reads the
        # pages itself; the parsed dicts are not what costs here.
        return self.run(bench, run)

    def record(self, res: dict, bench_name: str, run_label: str, with_truth=True) -> Record:
        tot, obj = res["ink_total"], res["objects"]
        no_ink = "no ink found at all: nothing to measure"
        no_obj = ("no truth given: the object half needs it" if not with_truth
                  else "no object with ink in the truth")
        scalars = {
            "ink_under_boxes": _ratio(res["ink_under_boxes"], tot, no_ink),
            "ink_under_artefacts": _ratio(res["ink_under_artifact"], tot, no_ink),
            "ink_outside_boxes": Scalar(1 - res["ink_under_boxes"] / tot if tot else None,
                                        count=(tot - res["ink_under_boxes"], tot),
                                        why=None if tot else no_ink),
            # THE SAME QUESTION WITH THE BINDING DISCARDED, and both are
            # printed because replacing the raw one silently is the version
            # that would be a repair rather than a ruler. Measured on the one
            # real level-two run: 85.661 % raw, 94.681 % clean, the
            # difference being 9.79 % of the sheet's ink standing in solid
            # dark columns at the binding.
            #
            # CLEANED ON BOTH SIDES OR NOT AT ALL. Under the attack `ink.py`
            # documents -- a box laid on every junk run, pure damage finding
            # nothing -- the raw number pays 85.661 -> 95.202, the clean one
            # moves 94.681 -> 94.681, a gradient of exactly zero, and a
            # denominator-only clean pays 94.959 -> 105.535: not merely
            # gamed but past 100 %, which is what an instrument looks like
            # when it has stopped dividing a thing by the thing it is part of.
            "ink_under_boxes_clean": _ratio(res["clean_under_boxes"],
                                            res["ink_clean"],
                                            "no ink left after the binding"),
            # A PROPERTY OF THE SCAN, NOT OF THE MODEL: how much of this
            # book is binding shadow and black scan edge. Ranking models by
            # it is meaningless -- they all read the same paper -- and it is
            # the number to look at when the clean and raw columns disagree.
            "ink_junk": _ratio(res["ink_junk"], tot, no_ink),
            "area_under_boxes": _ratio(res["boxes_area"], res["sheet_area"], "no sheet"),
            # THE OTHER HALF OF THE GUARD, and it exists because the first
            # half is beaten from the opposite side. `area_under_boxes`
            # catches the model that boxes the whole sheet; a model that
            # TRACES the ink with tiny boxes takes 100 % of it at LESS area
            # than an honest run -- measured on slovar: ink under boxes
            # 1.000 at area 0.462, against the honest 0.991 at 0.665, so the
            # declared guard reads the cheat as better than the real thing.
            #
            # The median box, as a share of its own page, separates them:
            # honest 0.0155, the tracer 0.000081, the whole-sheet box 1.000.
            # NEITHER END IS GOOD, which is why both are `=` and neither is
            # a rank: one is a model that found nothing, the other a model
            # that found everything and split it into rubble.
            "median_box_area": Scalar(
                res["median_box_area"],
                why=None if res["median_box_area"] is not None
                else "no box lands on any sheet"),
            # The same question in the unit a person bills in: one box, one
            # crop, one paid request at level two. Honest 44 a page on
            # slovar against the tracer's 5673.
            "boxes_per_page": _ratio(res["box_count"], res["page_count"],
                                     "no page was measured"),
            # WHERE THE INK ENDS UP, and this is the question the project is
            # for: how much of the book survives, and as WHAT. The two shares
            # plus `ink_outside_boxes` are exhaustive against the sheet's ink
            # -- measured on the one real level-two run, 76.944 % as text,
            # 8.717 % as a picture, 14.339 % under no box, summing to
            # 100.000 %. The rule is the BUILDER's, asked of `html.py` rather
            # than restated: a crop where `role == "artifact" or not content`,
            # a paragraph otherwise.
            #
            # NONE, NOT ZERO, ON A RUN THAT READ NOTHING. A detection run has
            # no content anywhere, so every block is a picture by that rule
            # and "0 % leaves as text" would be printed as a fact about the
            # model. It is a fact about the run, and the two zeros are the
            # rule this project keeps hardest.
            "ink_as_text": _ratio(res["ink_as_text"], tot, no_ink)
            if res["blocks_with_content"] else Scalar(
                None, why="this run read nothing: every block would leave as "
                          "a picture, which is not a measurement of one"),
            "ink_as_picture": _ratio(res["ink_as_picture"], tot, no_ink)
            if res["blocks_with_content"] else Scalar(
                None, why="this run read nothing: every block would leave as "
                          "a picture, which is not a measurement of one"),
            "objects_intact": _ratio(res["intact"], obj, no_obj),
            "objects_in_one_box": _ratio(res["in_one_box"], obj, no_obj),
            "objects_torn": _ratio(res["torn"], obj, no_obj),
            "objects_left_as_text": _ratio(res["left_as_text"], obj, no_obj),
            "objects_with_company": _ratio(res["arrived_with_company"], obj, no_obj),
            "object_ink_preserved": _ratio(res["object_ink_in_boxes"], res["object_ink"], no_obj),
        }
        params = dict(res["thresholds"])
        # THE JUNK MASK IS OURS AND IT IS DECLARED WHOLE. `MID`
        # was already a bare literal inside a printed sentence,
        # reaching no params at all; the other three are the
        # spread-cutter's, imported so there is one copy.
        params.update({"MID": ink.MID, "JUNK_WIDTH": ink.JUNK_WIDTH,
                       "RULE_RUN": ink.RULE_RUN,
                       "GUTTER_BAND": ink.GUTTER_BAND,
                       "MIN_SPREAD_RATIO": ink.MIN_SPREAD_RATIO})
        params["GUTTER"] = ink.GUTTER
        # THE DPI EVERYTHING HERE IS DENOMINATED IN. `assess/ink.py` says it
        # in its own header -- "without it two numbers from two runs are
        # incomparable" -- and then it lived in `detail`, which a table built
        # from `params` cannot reach.
        params["dpi"] = res.get("dpi")
        return Record(self.name, bench_name, run_label, scalars, params, res)

    def report(self, rec: Record, log=print) -> None:
        ink.report(rec.detail, log=log)

    def battery(self, bench, run, log=print) -> int:
        truth = bench.truth_dir if bench is not None and bench.truth_dir else ""
        return mutations(bench.pdf, run.pages_dir, truth, log=log)
