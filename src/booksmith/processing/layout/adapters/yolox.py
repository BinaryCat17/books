"""YOLOX-layout (unstructured.io): the only non-DETR model on the bench.

In: a page raster, letterboxed to 1024x768 with grey padding. Out: DocLayNet-
labelled boxes with no reading rank at all.
Anchor-free and convolutional, it suppresses duplicates by algorithm (NMS at the
reference 0.45) rather than by training -- the one paradigm here that can say
whether block merging comes of the DETR construction. Decoding the raw grid and
NMS are the model's own inference, not our editing. The selection threshold is
ours: this build has none, so `LAYOUT_SCORE_THRESHOLD` acts and is declared.
"""
import os

from booksmith.core.page import Block, Page
from booksmith.processing.layout.base import Detector
from booksmith.core import book
from booksmith.core import order
from booksmith.core import knobs
from booksmith.core import stamp
from booksmith.core.errors import WeightsMissing

MODELS = os.path.expanduser("~/.paddlex/official_models")
# DocLayNet alphabetical, the way unstructured numbers the classes.
LABELS = ("Caption", "Footnote", "Formula", "List-item", "Page-footer",
          "Page-header", "Picture", "Section-header", "Table", "Text", "Title")
STRIDES = (8, 16, 32)
PAD = 114               # grey padding, as in unstructured
# 1 = cv2.INTER_LINEAR, as the reference YOLOX code feeds it; it moves every coordinate.
INTERP = 1
NMS_IOU = 0.45          # from the reference YOLOX code, not the weights: they hold no metadata
# By class, as YOLOX's own `multiclass_nms` is: declared, since the wrapper may differ.
NMS_BY_CLASS = True



class YoloXLayout(Detector):
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
        # The input of this build is rigid: (1,3,1024,768), no dynamic axes.
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
        common = knobs.number("LAYOUT_SCORE_THRESHOLD")
        return {lab: common for lab in self.labels}

    def threshold_drift(self) -> list[str]:
        return [f"this build has no native threshold; "
                f"LAYOUT_SCORE_THRESHOLD={knobs.knob('LAYOUT_SCORE_THRESHOLD')} "
                f"acts over all {len(self.labels)} classes"]

    def knobs_read(self) -> tuple[str, ...]:
        """The knobs this adapter reads, checked by grep. `ASSEMBLY_ORDER` is
        among them because this model has no rank of its own; all three are
        declared unconditionally, a knob that acts on even one path acting.
        """
        return ("YOLOX_WEIGHTS", "LAYOUT_SCORE_THRESHOLD",
                "ASSEMBLY_ORDER")

    def label_map(self) -> dict[str, str]:
        return {}

    def label(self) -> str:
        """The weights file's stem: one adapter, one architecture, and the
        weights are chosen by `YOLOX_WEIGHTS`, so the file is the only thing
        that tells two runs of this adapter apart."""
        return book.safe_label(os.path.splitext(self.weights)[0],
                               "the YOLOX weights file")

    def fingerprint(self) -> dict:
        return {
            "name": self.name,
            "model": f"YOLOX-layout ({self.weights}), unstructured.io",
            "weights_dir": self.dir,
            "sha256_weights": stamp.sha256(self.onnx),
            "onnxruntime": self.ort_version,
            "providers": self.providers,
            "input": {"height": self.in_h, "width": self.in_w,
                     "padding": PAD, "keep_aspect": True},
            "native_threshold": None,
            "thresholds_by_class": self.thresholds(),
            # Always non-empty here: the selection threshold is ours, and `run.json` says it.
            "threshold_drift": self.threshold_drift(),
            "label_vocabulary": self.labels,
            "label_map": self.label_map(),
            "prompts": {},
            "reading_order": order.declare("none"),
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
        # The evidence must cover everything accepted, even at a knob set below 0.01.
        raw_keep = min(0.01, min(thr.values()))
        keep_idx, rejected = [], {}
        for i in range(len(best)):
            lab = self.labels[int(cls[i])]
            if float(best[i]) < thr[lab]:
                if float(best[i]) > rejected.get(lab, 0.0):
                    rejected[lab] = float(best[i])
                continue
            keep_idx.append(i)
        # How many entered suppression: NMS drops 196..333 boxes a page.
        before_nms = len(keep_idx)
        keep_idx = _nms(boxes[keep_idx], best[keep_idx], cls[keep_idx],
                        keep_idx, NMS_IOU, by_class=NMS_BY_CLASS)

        kept = [(self.labels[int(cls[i])], float(best[i]),
                 [float(v) for v in boxes[i]]) for i in keep_idx]
        # This model has no rank, so the order is ours: the rule lives in `order.py`.
        which = order.rule()
        order.cover(self.labels, which)
        perm = order.permutation([t[0] for t in kept], [t[2] for t in kept],
                                 w, h, index, self.labels, which)
        kept = [kept[i] for i in perm]
        blocks = [Block(block_id=i, box=tuple(b), label=lab, score=s, order=i)
                  for i, (lab, s, b) in enumerate(kept)]
        return Page(
            index=index, width=w, height=h, dpi=dpi, blocks=blocks,
            # `output_rows` and `feature_grid_cells` are equal by construction, so they
            # check nothing; the independent quantities are the rows above `raw_keep`.
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
            # No `raster` path: a machine-local scratch name makes identical runs differ.
            meta={"detector": self.name,
                  "boxes_accepted": len(kept), "rank_ties": 0,
                  "reading_order": order.declare("ours", order.WORDS[which]),
                  # A quantity, not the word "done": how much was suppressed.
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
