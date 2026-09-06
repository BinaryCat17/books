"""YOLOX-layout (unstructured.io): the ONLY non-DETR model on the bench.

Why this one. The other five bench detectors are DETRs -- RT-DETR-L with and
without a pointer net, RT-DETR with masks, RT-DETRv2, D-FINE -- one family:
fixed queries, one-to-one Hungarian matching, duplicate suppression as a
LEARNED skill. If merging neighbouring blocks comes of that construction, a
model of another paradigm has to behave differently. YOLOX is anchor-free and
convolutional, predicts densely over a grid, and suppresses duplicates by
algorithm (NMS) rather than by training.

WHAT WE DO WITH THE OUTPUT, AND WHY IT IS NOT A PATCH. The graph returns a RAW
grid: offsets in cells and the logarithm of the size. Decoding it and NMS are
part of YOLOX's own inference as its authors describe it, not our box editing:
without them the model has no answer at all. We merge nothing, cut nothing,
move nothing; the NMS threshold is the native 0.45, declared in the
fingerprint.

LETTERBOXED INPUT. 1024x768, proportions kept, grey padding 114 -- how
unstructured feeds this model. Of the SIX bench detectors (§13 of
`docs/contour-notes.md`) it alone does not tear the sheet's proportions, and
that is no advantage by itself: on `kat_two_side` it still gave one box over
both tables, score 0.71. The "input distortion showed itself on one case of
four" of §10 was taken on V2, not here.

THE DETECTION THRESHOLD HERE IS OURS, to be read together with "the native
0.45", which is about NMS. This build has no SELECTION threshold at all; ours
acts, `LAYOUT_SCORE_THRESHOLD=0.5`, and `threshold_drift()` says so aloud. The
price: on `bench/slovar` 0.5 finds 1 artifact of 3 (33 %), 0.3 finds 2 of 3
(67 %). Every comparative yolox number in `contour-notes` was taken under a
foreign (paddle) threshold applied to a model that has none.
"""
import hashlib
import os

from .base import Block, Page, Recognizer
from .. import order
from ..run import knobs

MODELS = os.path.expanduser("~/.paddlex/official_models")
# Class order -- DocLayNet alphabetical, the way unstructured numbers them.
# Checked on a catalogue strip: class 5 landed on a running head, class 8 on a
# table, so `Page-header` and `Table` are in their places.
LABELS = ("Caption", "Footnote", "Formula", "List-item", "Page-footer",
          "Page-header", "Picture", "Section-header", "Table", "Text", "Title")
STRIDES = (8, 16, 32)
PAD = 114               # grey padding, as in unstructured
# THE DOWNSCALE FILTER. A bare `interpolation=1` inside `_letterbox` once, it
# never reached the fingerprint, unlike `PAD` next to it -- yet it decides
# more than any other number here: on `bench/slovar` (13 pages, all else fixed)
# 520 boxes with LINEAR, 492 with NEAREST, 497 with CUBIC, 519 with AREA, and
# boxes matching the baseline 0, 1 and 28 respectively. The filter moves ALL
# coordinates. In `doclayout` it is read from the weights and lies in the
# fingerprint; here `books replay --check` could not see it by construction,
# and the run was silently unrepeatable. 1 = cv2.INTER_LINEAR -- how the
# reference YOLOX implementation feeds this model.
INTERP = 1
NMS_IOU = 0.45          # the NMS threshold of the reference YOLOX code.
                        # "Native" means "from the reference code", NOT "from
                        # the weights": the weights carry no metadata at all
                        # (producer='pytorch', empty description, empty
                        # custom_metadata_map), only a LICENSE.txt beside them,
                        # without 0.45 in it. The fingerprint admits that in
                        # `verified_against_unstructured: false`. It decides
                        # little: over all 600 golden pages, 5053 boxes at iou
                        # 0.10 against 5097 at 0.45, 0.9 %. NMS_BY_CLASS below
                        # decides far more: 68 boxes.
# Duplicates suppressed BY CLASS -- how YOLOX's own `multiclass_nms` is built
# (its class-agnostic mode is off by default). The unstructured wrapper may
# have chosen otherwise and their code could not tell us, so the choice is
# declared here and travels into the fingerprint instead of being implied. It
# shows on boxes of different classes lying in one place: per class, both
# survive.
NMS_BY_CLASS = True


class WeightsMissing(RuntimeError):
    pass


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class YoloXLayout(Recognizer):
    name = "yolox-layout"
    policy_name = "DocLayNet"

    def __init__(self, model_dir: str | None = None, weights: str | None = None):
        import onnxruntime as ort

        self.dir = model_dir or os.path.join(MODELS, "yolox_layout")
        self.weights = weights or knobs.knob("YOLOX_WEIGHTS") or "yolox_l0.05.onnx"
        self.onnx = os.path.join(self.dir, self.weights)
        if not os.path.exists(self.onnx):
            raise WeightsMissing(
                f"no {self.onnx}. Download from "
                f"huggingface.co/unstructuredio/yolo_x_layout")
        self.sess = ort.InferenceSession(
            self.onnx, providers=["CPUExecutionProvider"])
        self.ort_version = ort.__version__
        self.providers = list(self.sess.get_providers())
        shape = self.sess.get_inputs()[0].shape
        # The input of this build is RIGID: (1,3,1024,768). No dynamic axes,
        # no other size can be fed -- fail aloud, do not fit it silently.
        self.in_h, self.in_w = int(shape[2]), int(shape[3])
        self.labels = list(LABELS)
        out = self.sess.get_outputs()[0].shape
        want = sum((self.in_h // s) * (self.in_w // s) for s in STRIDES)
        if int(out[1]) != want:
            raise WeightsMissing(
                f"output {out}: {out[1]} cells, while the grid {STRIDES} over "
                f"the input {self.in_h}x{self.in_w} gives {want}. Laying it "
                f"out blind means inventing boxes.")
        if int(out[2]) != 5 + len(self.labels):
            raise WeightsMissing(
                f"output {out}: {out[2]} columns, while we expected "
                f"{5 + len(self.labels)} = 4 coordinates + objectness + "
                f"{len(self.labels)} classes.")

    def thresholds(self) -> dict[str, float]:
        common = float(knobs.knob("LAYOUT_SCORE_THRESHOLD"))
        return {lab: common for lab in self.labels}

    def threshold_drift(self) -> list[str]:
        return [f"this build has no native threshold; "
                f"LAYOUT_SCORE_THRESHOLD={knobs.knob('LAYOUT_SCORE_THRESHOLD')} "
                f"acts over all {len(self.labels)} classes"]

    def knobs_read(self) -> tuple[str, ...]:
        """Two knobs, checked by grep: `knob()` is called here three times.

        `YOLOX_WEIGHTS` in `__init__` (which weights to take),
        `LAYOUT_SCORE_THRESHOLD` in `thresholds()` and `threshold_drift()`.
        `LAYOUT_TABLE_THRESHOLD` is not read: DocLayNet's `Table` takes the
        common threshold and has none of its own. The paddle weights name and
        directory do not concern this model -- the path is built from `MODELS`
        and `self.weights`.

        `YOLOX_WEIGHTS` is declared even though `YoloXLayout(weights=…)` will
        not read it: `books detect` builds the adapter without arguments, so
        the knob decides the weights on every run that reaches a snapshot.
        """
        return ("YOLOX_WEIGHTS", "LAYOUT_SCORE_THRESHOLD")

    def label_map(self) -> dict[str, str]:
        return {}

    def fingerprint(self) -> dict:
        return {
            "name": self.name,
            "model": f"YOLOX-layout ({self.weights}), unstructured.io",
            "weights_dir": self.dir,
            "sha256_weights": _sha256(self.onnx),
            "onnxruntime": self.ort_version,
            "providers": self.providers,
            "input": {"height": self.in_h, "width": self.in_w,
                     "padding": PAD, "keep_aspect": True},
            "native_threshold": None,
            "thresholds_by_class": self.thresholds(),
            # NOT an empty list. `threshold_drift()` here ALWAYS says
            # something -- "no native threshold, ours acts" -- and that is what
            # makes visible that the selection threshold is OURS, not the
            # weights'. Here stood a wired-in `[]`: the snapshot answered "no
            # drift" and contradicted its own guard, the adapter shouting into
            # the log and keeping quiet in `run.json`. heron and doclayout
            # already do it right; the third of three was forgotten.
            "threshold_drift": self.threshold_drift(),
            "label_vocabulary": self.labels,
            "label_map": self.label_map(),
            "prompts": {},
            "reading_order": None,
            "input_downscale": {"cv2_filter": INTERP, "padding": PAD},
            "duplicate_suppression": {"method": "NMS", "iou": NMS_IOU,
                                  "by_class": NMS_BY_CLASS,
                                  "verified_against_unstructured": False},
        }

    def read(self, image_path: str, index: int, dpi: float) -> Page:
        import cv2
        import numpy as np

        img = cv2.imread(image_path)
        if img is None:
            raise RuntimeError(f"the page raster does not read: {image_path}")
        h, w = img.shape[:2]
        r = min(self.in_h / h, self.in_w / w)
        nh, nw = int(round(h * r)), int(round(w * r))
        canvas = np.full((self.in_h, self.in_w, 3), PAD, np.uint8)
        canvas[:nh, :nw] = cv2.resize(img, (nw, nh), interpolation=INTERP)
        x = np.ascontiguousarray(
            canvas[:, :, ::-1].transpose(2, 0, 1)[None].astype(np.float32))
        out = self.sess.run(None, {"images": x})[0][0]

        grids, strides = [], []
        for s in STRIDES:
            gh, gw = self.in_h // s, self.in_w // s
            yv, xv = np.meshgrid(np.arange(gh), np.arange(gw), indexing="ij")
            grids.append(np.stack((xv, yv), 2).reshape(-1, 2))
            strides.append(np.full((gh * gw, 1), s, np.float32))
        g = np.concatenate(grids).astype(np.float32)
        st = np.concatenate(strides)
        cxy = (out[:, :2] + g) * st
        wh = np.exp(out[:, 2:4]) * st
        boxes = np.concatenate([cxy - wh / 2, cxy + wh / 2], 1) / r

        sc = out[:, 4:5] * out[:, 5:]
        cls = sc.argmax(1)
        best = sc.max(1)

        thr = self.thresholds()
        # Threshold for keeping raw rows. The whole grid (16128 cells) stays
        # out of the json, but the evidence MUST cover everything accepted: the
        # selection threshold comes from a knob and can be below 0.01, and then
        # a threshold sweep over the snapshot lies downward -- on atlas at
        # LAYOUT_SCORE_THRESHOLD=0.005, 20 of 75 accepted boxes had not one row
        # in the raw output.
        raw_keep = min(0.01, min(thr.values()))
        keep_idx, rejected = [], {}
        for i in range(len(best)):
            lab = self.labels[int(cls[i])]
            if float(best[i]) < thr[lab]:
                if float(best[i]) > rejected.get(lab, 0.0):
                    rejected[lab] = float(best[i])
                continue
            keep_idx.append(i)
        # HOW MANY ENTERED SUPPRESSION. A quantity the log did not hold at
        # all, while our own line kills 196..333 boxes a page (measured, 5
        # slovar pages: 318->39, 340->57, 402->69, 253->57, 311->45).
        before_nms = len(keep_idx)
        keep_idx = _nms(boxes[keep_idx], best[keep_idx], cls[keep_idx],
                        keep_idx, NMS_IOU, by_class=NMS_BY_CLASS)

        kept = [(self.labels[int(cls[i])], float(best[i]),
                 [float(v) for v in boxes[i]]) for i in keep_idx]
        # THE ASSEMBLY RULE LIVES IN `order.py`, ONE PER PROJECT. Here stood a
        # sort of its own, `(t[2][1], t[2][0])` -- the third copy of the rule
        # out of four, and two of those four sorted by a DIFFERENT key than
        # they declared. This model has no rank, so the order is ours, and
        # choosing it is the `ASSEMBLY_ORDER` knob's business, not this file's.
        which = order.rule()
        order.cover(self.labels, which)
        perm = order.permutation([t[0] for t in kept], [t[2] for t in kept],
                                 w, h, index, self.labels, which)
        kept = [kept[i] for i in perm]
        blocks = [Block(block_id=i, box=tuple(b), label=lab, score=s, order=i)
                  for i, (lab, s, b) in enumerate(kept)]
        return Page(
            index=index, width=w, height=h, dpi=dpi, blocks=blocks,
            # "output rows" is what the graph RETURNED, "feature grid cells"
            # what decoding by STRIDES gives. Both used to come from
            # out.shape[0], and the log compared a number with itself.
            #
            # THERE IS STILL NOTHING TO CHECK THEM AGAINST, and that has to be
            # said plainly: they are equal BY CONSTRUCTION -- the constructor
            # refuses to build when `out[1] != want`, and the input shape is
            # static. Measured over 53 pages, 6 books, 4 dpi and both weight
            # files: 0 divergences, both quantities 16128 everywhere. The fix
            # was about where the numbers came from, not their independence.
            #
            # THE INDEPENDENT QUANTITIES ARE THE OTHER TWO, below: how many raw
            # rows passed `raw_keep` (588..1520 on the same pages), and how
            # many boxes entered suppression against how many were accepted. A
            # slump of "four times fewer candidates" used to pass in silence.
            raw={"output_rows": int(out.shape[0]),
                 "output_columns": int(out.shape[1]),
                 "feature_grid_cells": int(len(g)),
                 "grid_cells_per_level": {
                     str(s): int((self.in_h // s) * (self.in_w // s))
                     for s in STRIDES},
                 "all_rows": [[float(cls[i]), float(best[i]),
                                 *[float(v) for v in boxes[i]]]
                                for i in np.where(best >= raw_keep)[0]],
                 "raw_rows_keep_threshold": raw_keep,
                 "rows_above_keep_threshold":
                     int((best >= raw_keep).sum())},
            meta={"detector": self.name, "raster": image_path,
                  "boxes_accepted": len(kept), "rank_ties": 0,
                  "reading_order": order.WORDS[which],
                  # A QUANTITY, NOT A WORD. Here stood
                  # `f"NMS iou={NMS_IOU}"`, a string repeating a constant,
                  # while the log said nothing about HOW MUCH it suppressed.
                  # It broke the project rule outright: into the log goes a
                  # quantity, not the word "done".
                  "duplicate_suppression": {"method": "NMS", "iou": NMS_IOU,
                                        "by_class": NMS_BY_CLASS,
                                        "boxes_in": before_nms,
                                        "suppressed": before_nms - len(keep_idx)},
                  "best_rejected_by_class": rejected})


def _nms(boxes, scores, cls, idx, iou_thr, by_class=True):
    """Duplicate suppression, `by_class` as in YOLOX's `multiclass_nms`."""
    import numpy as np

    keep = []
    groups = np.unique(cls) if by_class else [None]
    for c in groups:
        m = np.where(cls == c)[0] if c is not None else np.arange(len(cls))
        b, s = boxes[m], scores[m]
        order = s.argsort()[::-1]
        while len(order):
            i = order[0]
            keep.append(idx[m[i]])
            if len(order) == 1:
                break
            xx0 = np.maximum(b[i, 0], b[order[1:], 0])
            yy0 = np.maximum(b[i, 1], b[order[1:], 1])
            xx1 = np.minimum(b[i, 2], b[order[1:], 2])
            yy1 = np.minimum(b[i, 3], b[order[1:], 3])
            inter = np.maximum(0, xx1 - xx0) * np.maximum(0, yy1 - yy0)
            a1 = (b[i, 2] - b[i, 0]) * (b[i, 3] - b[i, 1])
            a2 = ((b[order[1:], 2] - b[order[1:], 0])
                  * (b[order[1:], 3] - b[order[1:], 1]))
            iou = inter / np.maximum(1e-9, a1 + a2 - inter)
            order = order[1:][iou <= iou_thr]
    return sorted(keep)
