from datasets.draw import SynthError

INK = 160
KEEP = 2
GUESSED = {
    "figure_title",
    "display_formula",
    "doc_title",
    "paragraph_title",
    "number",
    "content",
    "footnote",
}
GROW = 6


def _measure(img, boxes, case: str):
    import cv2
    import numpy as np

    ink = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) < INK
    h, w = ink.shape
    out = []
    for x0, y0, x1, y1, lab in boxes:
        a, b = (max(0, int(x0)), max(0, int(y0)))
        c, d = (min(w, int(round(x1))), min(h, int(round(y1))))
        sub = ink[b:d, a:c]
        if sub.size == 0 or not sub.any():
            raise SynthError(
                f'{case}: the truth box {lab} {[round(v) for v in (x0, y0, x1, y1)]} is EMPTY -- not one pixel is drawn under it. This is not "a block with no content", this is NOT DRAWN, and in a measurement such a box gives the model a permanent undeserved miss.'
            )
        ys, xs = np.where(sub)
        L, T = (a + int(xs.min()), b + int(ys.min()))
        R, B = (a + int(xs.max()) + 1, b + int(ys.max()) + 1)
        if lab in GUESSED:
            for _ in range(GROW):
                if L > 0 and ink[T:B, L - 1].any():
                    L -= 1
                if R < w and ink[T:B, R].any():
                    R += 1
                if T > 0 and ink[T - 1, L:R].any():
                    T -= 1
                if B < h and ink[B, L:R].any():
                    B += 1
        out.append(
            (
                max(0.0, L - KEEP),
                max(0.0, T - KEEP),
                min(float(w), R + KEEP),
                min(float(h), B + KEEP),
                lab,
            )
        )
    return out


def _text_check(words, boxes, said, case: str):
    from collections import Counter
    from datasets import classes as policy

    inside = [[] for _ in boxes]
    outside = []
    for x0, y0, x1, y1, w in words:
        cx, cy = ((x0 + x1) / 2.0, (y0 + y1) / 2.0)
        best, area = (None, None)
        for j, b in enumerate(boxes):
            if b[0] <= cx <= b[2] and b[1] <= cy <= b[3]:
                a = (b[2] - b[0]) * (b[3] - b[1])
                if area is None or a < area:
                    best, area = (j, a)
        if best is None:
            outside.append(w)
        else:
            inside[best].append(w)
    miss = ghost = unknown = leaders = 0
    samples = []
    for j, b in enumerate(boxes):
        if policy.POLICIES["PP-DocLayoutV2"].role(b[4]) == "artifact":
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
                leaders += n
            else:
                unknown += n
                if len(samples) < 4:
                    samples.append(f"{b[4]}#{j}: {w!r}")
        if m and len(samples) < 4:
            samples.append(f"{b[4]}#{j}: not in the layer {list(m)[:3]}")
    return {
        "words_in_layer": len(words),
        "missing_from_layer": miss,
        "outside_truth": len(outside),
        "ghosts": ghost,
        "dot_leaders": leaders,
        "unexplained": unknown,
        "outside_truth_samples": sorted(set(outside))[:8],
        "mismatch_examples": samples,
    }
