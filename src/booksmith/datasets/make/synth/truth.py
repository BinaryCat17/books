"""Measured truth: the boxes snapped to the ink they contain, and the check
that what the drawers said they wrote is what the PDF's text layer holds.

INK and KEEP are knowingly the same numbers as the ink metric's, held
together by a test and never merged by import: the metric must not be
able to change the truth.
"""
from booksmith.datasets.make.synth.draw import SynthError

# --------------------------------------------------------- measured truth
# Truth boxes are measured AGAINST THE INK, not declared as numbers. The reason
# is money: in one evening this generator lied about boxes four times, and all
# four times the numbers looked healthy -- empty text boxes, the right half of
# a spread past the sheet edge (pixels in a field that counts points), a ruled
# form instead of a drawing, and a formula box 83 points wider than the
# formula, a constant set by eye. The last cost the model a false accusation:
# `formula_next_to_table` was filed as its refusal.
#
# Measured, a box cannot come out wider than the drawing, and an empty box
# FAILS instead of keeping quiet.
INK = 160          # darker than this is ink (clean page, before aging)
KEEP = 2           # this many pixels of margin left around the measurement
# Labels whose boxes the cases set by eye around text: they may not only shrink
# to the ink but grow to it. Geometric boxes (table, figure, chart, text
# column) are computed by code and only shrink.
GUESSED = {"figure_title", "display_formula", "doc_title", "paragraph_title",
           "number", "content", "footnote"}
GROW = 6           # how far such a box may grow, in pixels


def _measure(img, boxes, case: str):
    """Pull truth boxes to the ink. An empty box is an error, not a zero."""
    import cv2
    import numpy as np

    ink = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) < INK
    h, w = ink.shape
    out = []
    for x0, y0, x1, y1, lab in boxes:
        a, b = max(0, int(x0)), max(0, int(y0))
        c, d = min(w, int(round(x1))), min(h, int(round(y1)))
        sub = ink[b:d, a:c]
        if sub.size == 0 or not sub.any():
            raise SynthError(
                f"{case}: the truth box {lab} "
                f"{[round(v) for v in (x0, y0, x1, y1)]} is EMPTY -- not one "
                f"pixel is drawn under it. This is not \"a block with no "
                f"content\", this is NOT DRAWN, and in a measurement such a "
                f"box gives the model a permanent undeserved miss.")
        ys, xs = np.where(sub)
        L, T = a + int(xs.min()), b + int(ys.min())
        R, B = a + int(xs.max()) + 1, b + int(ys.max()) + 1
        if lab in GUESSED:
            # Growth ONLY ALONG CONTINUOUS INK. The old edition took the ink
            # box of a window widened by GROW on every side, so a foreign line
            # four pixels away set the edge -- flatly against the docstring: a
            # box is measured against ITS OWN ink. We spread while the next row
            # is non-empty and not a pixel further.
            for _ in range(GROW):
                if L > 0 and ink[T:B, L - 1].any():
                    L -= 1
                if R < w and ink[T:B, R].any():
                    R += 1
                if T > 0 and ink[T - 1, L:R].any():
                    T -= 1
                if B < h and ink[B, L:R].any():
                    B += 1
        out.append((max(0.0, L - KEEP), max(0.0, T - KEEP),
                    min(float(w), R + KEEP), min(float(h), B + KEEP), lab))
    return out


def _text_check(words, boxes, said, case: str):
    """Check the character truth against the PDF TEXT LAYER of the same page.

    Synthetic pages are DRAWN, not scanned, so a clean page has a text layer --
    a second witness independent of our bookkeeping: `_say` records what we
    MEANT to draw, `page.get_text("words")` what actually landed. Nothing had
    such a witness before.

    FOUR NUMBERS, DIFFERENT IN MEANING (a zero from a check and a zero from
    incomprehension are different zeros):

    `missing_from_layer` -- the truth claims a word not on the paper. The one
    real alarm: a box claimed richer than the drawing looks like this.

    `outside_truth` -- a word drawn, covered by NO truth box. Some are
    deliberate (catalogue line numbers stand left of the table box), so the
    number is printed, not forbidden: a silent counter would lie the way
    "0 chapters" lied about four books at once.

    `ghosts` -- a word in a box repeating one already claimed. Source known and
    measured: `insert_textbox` runs several times per box (30 passes for the 20
    boxes of `no_artefacts`) and the layer holds EVERY draft. Layer words
    matched all draft words exactly, 2198 against 2198, 0 unexplained.

    `unexplained` -- a word in a box the truth does not hold at all and
    repetition does not explain. Zero is the norm; anything else must be NAMED,
    so examples print beside the number. One is found: `marginalia` carries the
    fragment `sc`, left when `_fill` cut the body at `len*0.9` inside `screw`
    and the next pass appended flush against it. Nobody had seen it before.

    THE BLIND SPOT: a word lost by the truth that OCCURS AGAIN in the block
    goes to `ghosts`, not `unexplained` -- a mutation put 8 of 16 dropped last
    words there. On prose it widens with the block.

    Only roles text and service are checked: an artifact has no `content`.
    """
    from collections import Counter
    from booksmith.core import policy

    inside = [[] for _ in boxes]
    outside = []
    for x0, y0, x1, y1, w in words:
        cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        # Of the covering boxes take the SMALLEST: boxes nest (a title block
        # inside a drawing field), and "first in the list" would hand the word
        # to the outer box, counting the wrong thing.
        best, area = None, None
        for j, b in enumerate(boxes):
            if b[0] <= cx <= b[2] and b[1] <= cy <= b[3]:
                a = (b[2] - b[0]) * (b[3] - b[1])
                if area is None or a < area:
                    best, area = j, a
        if best is None:
            outside.append(w)
        else:
            inside[best].append(w)

    miss = ghost = unknown = leaders = 0
    samples = []
    for j, b in enumerate(boxes):
        if policy.role(b[4]) == "artifact":
            continue
        have = Counter(inside[j])
        want = Counter((said.get(j, {}).get("text") or "").split())
        m = want - have
        e = have - want
        miss += sum(m.values())
        for w, n in e.items():
            if w in want:
                ghost += n
            elif len(w) >= 4 and set(w) == {"."}:
                # A DOT LEADER is not a word but a typographic rule (see the
                # decision in `_leader_table`). Counted separately rather than
                # as `unexplained`, or sixty contents leaders would hold the
                # alarming counter non-zero forever and hide a real find.
                leaders += n
            else:
                unknown += n
                if len(samples) < 4:
                    samples.append(f"{b[4]}#{j}: {w!r}")
        if m and len(samples) < 4:
            samples.append(f"{b[4]}#{j}: not in the layer {list(m)[:3]}")
    return {"words_in_layer": len(words), "missing_from_layer": miss,
            "outside_truth": len(outside), "ghosts": ghost,
            "dot_leaders": leaders, "unexplained": unknown,
            "outside_truth_samples": sorted(set(outside))[:8],
            "mismatch_examples": samples}


