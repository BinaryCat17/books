"""YOLOX-layout (unstructured.io): the only non-DETR model on the bench"""

import os
from layout.page import Block, Page
from layout.detector import Detector
from layout import store as book
from layout import order
from layout import knobs
from layout import identity as stamp
from layout.errors import WeightsMissing

MODELS = os.path.expanduser("~/.paddlex/official_models")
LABELS = (
    "Caption",
    "Footnote",
    "Formula",
    "List-item",
    "Page-footer",
    "Page-header",
    "Picture",
    "Section-header",
    "Table",
    "Text",
    "Title",
)
STRIDES = (8, 16, 32)
PAD = 114
INTERP = 1
NMS_IOU = 0.45
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
                f"no {self.onnx}. Download from huggingface.co/unstructuredio/yolo_x_layout"
            )
        self.sess = ort.InferenceSession(self.onnx, providers=["CPUExecutionProvider"])
        self.ort_version = ort.__version__
        self.providers = list(self.sess.get_providers())
        shape = self.sess.get_inputs()[0].shape
        self.in_h, self.in_w = (int(shape[2]), int(shape[3]))
        self.labels = list(LABELS)
        out = self.sess.get_outputs()[0].shape
        want = sum(self.in_h // s * (self.in_w // s) for s in STRIDES)
        if int(out[1]) != want:
            raise WeightsMissing(
                f"output {out}: {out[1]} cells, while the grid {STRIDES} over the input {self.in_h}x{self.in_w} gives {want}. Laying it out blind means inventing boxes."
            )
        if int(out[2]) != 5 + len(self.labels):
            raise WeightsMissing(
                f"output {out}: {out[2]} columns, while we expected {5 + len(self.labels)} = 4 coordinates + objectness + {len(self.labels)} classes."
            )

    def thresholds(self) -> dict[str, float]:
        common = knobs.number("LAYOUT_SCORE_THRESHOLD")
        return {lab: common for lab in self.labels}

    def threshold_drift(self) -> list[str]:
        return [
            f"this build has no native threshold; LAYOUT_SCORE_THRESHOLD={knobs.knob('LAYOUT_SCORE_THRESHOLD')} acts over all {len(self.labels)} classes"
        ]

    def knobs_read(self) -> tuple[str, ...]:
        return ("YOLOX_WEIGHTS", "LAYOUT_SCORE_THRESHOLD", "ASSEMBLY_ORDER")

    def label_map(self) -> dict[str, str]:
        return {}

    def label(self) -> str:
        return book.safe_label(os.path.splitext(self.weights)[0], "the YOLOX weights file")

    def fingerprint(self) -> dict:
        return {
            "name": self.name,
            "model": f"YOLOX-layout ({self.weights}), unstructured.io",
            "weights_dir": self.dir,
            "sha256_weights": stamp.sha256(self.onnx),
            "onnxruntime": self.ort_version,
            "providers": self.providers,
            "input": {"height": self.in_h, "width": self.in_w, "padding": PAD, "keep_aspect": True},
            "native_threshold": None,
            "thresholds_by_class": self.thresholds(),
            "threshold_drift": self.threshold_drift(),
            "label_vocabulary": self.labels,
            "label_map": self.label_map(),
            "prompts": {},
            "reading_order": order.declare("none"),
            "input_downscale": {"cv2_filter": INTERP, "padding": PAD},
            "duplicate_suppression": {
                "method": "NMS",
                "iou": NMS_IOU,
                "by_class": NMS_BY_CLASS,
                "verified_against_unstructured": False,
            },
        }

    def read(self, image_path: str, index: int, dpi: float) -> Page:
        import cv2
        import numpy as np

        img = cv2.imread(image_path)
        if img is None:
            raise RuntimeError(f"the page raster does not read: {image_path}")
        h, w = img.shape[:2]
        r = min(self.in_h / h, self.in_w / w)
        nh, nw = (int(round(h * r)), int(round(w * r)))
        canvas = np.full((self.in_h, self.in_w, 3), PAD, np.uint8)
        canvas[:nh, :nw] = cv2.resize(img, (nw, nh), interpolation=INTERP)
        x = np.ascontiguousarray(canvas[:, :, ::-1].transpose(2, 0, 1)[None].astype(np.float32))
        out = self.sess.run(None, {"images": x})[0][0]
        grids, strides = ([], [])
        for s in STRIDES:
            gh, gw = (self.in_h // s, self.in_w // s)
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
        raw_keep = min(0.01, min(thr.values()))
        keep_idx, rejected = ([], {})
        for i in range(len(best)):
            lab = self.labels[int(cls[i])]
            if float(best[i]) < thr[lab]:
                if float(best[i]) > rejected.get(lab, 0.0):
                    rejected[lab] = float(best[i])
                continue
            keep_idx.append(i)
        before_nms = len(keep_idx)
        keep_idx = _nms(
            boxes[keep_idx], best[keep_idx], cls[keep_idx], keep_idx, NMS_IOU, by_class=NMS_BY_CLASS
        )
        kept = [
            (self.labels[int(cls[i])], float(best[i]), [float(v) for v in boxes[i]])
            for i in keep_idx
        ]
        which = order.rule()
        pol = self.policy() if which == "docling" else None
        order.cover(pol, which)
        perm = order.permutation(
            [t[0] for t in kept], [t[2] for t in kept], w, h, index, pol, which
        )
        kept = [kept[i] for i in perm]
        blocks = [
            Block(block_id=i, box=tuple(b), label=lab, score=s, order=i)
            for i, (lab, s, b) in enumerate(kept)
        ]
        return Page(
            index=index,
            width=w,
            height=h,
            dpi=dpi,
            blocks=blocks,
            raw={
                "output_rows": int(out.shape[0]),
                "output_columns": int(out.shape[1]),
                "feature_grid_cells": int(len(g)),
                "grid_cells_per_level": {
                    str(s): int(self.in_h // s * (self.in_w // s)) for s in STRIDES
                },
                "all_rows": [
                    [float(cls[i]), float(best[i]), *[float(v) for v in boxes[i]]]
                    for i in np.where(best >= raw_keep)[0]
                ],
                "raw_rows_keep_threshold": raw_keep,
                "rows_above_keep_threshold": int((best >= raw_keep).sum()),
            },
            meta={
                "detector": self.name,
                "boxes_accepted": len(kept),
                "rank_ties": 0,
                "reading_order": order.declare("ours", order.WORDS[which]),
                "duplicate_suppression": {
                    "method": "NMS",
                    "iou": NMS_IOU,
                    "by_class": NMS_BY_CLASS,
                    "boxes_in": before_nms,
                    "suppressed": before_nms - len(keep_idx),
                },
                "best_rejected_by_class": rejected,
            },
        )


def _nms(boxes, scores, cls, idx, iou_thr, by_class=True):
    import numpy as np

    keep = []
    groups = np.unique(cls) if by_class else [None]
    for c in groups:
        m = np.where(cls == c)[0] if c is not None else np.arange(len(cls))
        b, s = (boxes[m], scores[m])
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
            a2 = (b[order[1:], 2] - b[order[1:], 0]) * (b[order[1:], 3] - b[order[1:], 1])
            iou = inter / np.maximum(1e-09, a1 + a2 - inter)
            order = order[1:][iou <= iou_thr]
    return sorted(keep)
