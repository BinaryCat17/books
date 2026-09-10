"""PP-DocLayoutV2/V3 (ONNX) straight off the graph: boxes, labels, reading order"""

import os
from layout import store as book
from layout import knobs
from layout.page import Block, Page
from layout.detector import Detector
from layout import order
from layout import identity as stamp
from layout.errors import WeightsMissing

PADDLEX_MODELS = os.path.expanduser("~/.paddlex/official_models")


def weights_dir() -> str:
    d = knobs.knob("LAYOUT_MODEL_DIR")
    if d:
        return d
    return os.path.join(PADDLEX_MODELS, knobs.knob("LAYOUT_MODEL_NAME") + "_onnx")


def has_rank(out) -> bool:
    return out.shape[1] >= 7


class DocLayout(Detector):
    name = "doclayout-onnx"

    def __init__(self, model_dir: str | None = None):
        import onnxruntime as ort
        import yaml

        self.dir = model_dir or weights_dir()
        self.onnx = os.path.join(self.dir, "inference.onnx")
        cfg_path = os.path.join(self.dir, "inference.yml")
        missing = [p for p in (self.onnx, cfg_path) if not os.path.exists(p)]
        if missing:
            raise WeightsMissing(
                f"no layout detection weights in {self.dir}: missing {', '.join((os.path.basename(m) for m in missing))}.\nName the directory with the knob LAYOUT_MODEL_DIR, or put the weights where paddlex looks ({PADDLEX_MODELS})."
            )
        with open(cfg_path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        self.labels: list[str] = list(cfg["label_list"])
        rz = next((p for p in cfg["Preprocess"] if p.get("type") == "Resize"))
        self.target_h, self.target_w = (int(v) for v in rz["target_size"])
        self.keep_ratio = bool(rz.get("keep_ratio", False))
        if self.keep_ratio:
            raise WeightsMissing(
                "the weights say keep_ratio: true, while the adapter squeezes the raster with no padding. The boxes would come out shifted and plausible at once."
            )
        self.interp = int(rz.get("interp", 2))
        self.native_threshold = float(cfg.get("draw_threshold", 0.5))
        nm = next((p for p in cfg["Preprocess"] if p.get("type") == "NormalizeImage"), None)
        self.norm_type = (nm or {}).get("norm_type", "none")
        self.norm_mean = [float(v) for v in (nm or {}).get("mean", [0.0] * 3)]
        self.norm_std = [float(v) for v in (nm or {}).get("std", [1.0] * 3)]
        self.norm_scale = bool((nm or {}).get("is_scale", True))
        if self.norm_type not in ("none", "mean_std"):
            raise WeightsMissing(
                f"unknown normalization {self.norm_type!r} in inference.yml: substituting ours would feed the model the wrong thing."
            )
        self.channel_order = "rgb"
        self.sess = ort.InferenceSession(self.onnx, providers=["CPUExecutionProvider"])
        self.ort_version = ort.__version__
        self.providers = list(self.sess.get_providers())
        cols = self.sess.get_outputs()[0].shape
        if len(cols) != 2 or not isinstance(cols[1], int):
            raise WeightsMissing(
                f"the graph's first output has shape {cols}, and a box table of a fixed number of columns was expected; whether these weights carry a rank cannot be told"
            )
        self.has_order = cols[1] >= 7

    def thresholds(self) -> dict[str, float]:
        common = knobs.number("LAYOUT_SCORE_THRESHOLD")
        table = knobs.number("LAYOUT_TABLE_THRESHOLD")
        return {lab: table if lab == "table" else common for lab in self.labels}

    def threshold_drift(self) -> list[str]:
        out = []
        for name in ("LAYOUT_SCORE_THRESHOLD", "LAYOUT_TABLE_THRESHOLD"):
            v = knobs.number(name)
            if abs(v - self.native_threshold) >= 1e-09:
                out.append(f"{name}={v} against the native draw_threshold={self.native_threshold}")
        return out

    def model_name(self) -> str:
        import yaml

        cfg_path = os.path.join(self.dir, "inference.yml")
        with open(cfg_path, encoding="utf-8") as f:
            g = yaml.safe_load(f).get("Global") or {}
        return g.get("model_name") or "not declared in the weights"

    def knobs_read(self) -> tuple[str, ...]:
        return (
            "LAYOUT_MODEL_NAME",
            "LAYOUT_MODEL_DIR",
            "LAYOUT_SCORE_THRESHOLD",
            "LAYOUT_TABLE_THRESHOLD",
            "ASSEMBLY_ORDER",
        )

    def label_map(self) -> dict[str, str]:
        return {}

    def label(self) -> str:
        return book.safe_label(self.model_name(), "the layout weights")

    def fingerprint(self) -> dict:
        return {
            "name": self.name,
            "model": self.model_name(),
            "name_from_knob": knobs.knob("LAYOUT_MODEL_NAME"),
            "weights_dir": self.dir,
            "sha256_weights": stamp.sha256(self.onnx),
            "onnxruntime": self.ort_version,
            "providers": self.providers,
            "input": {
                "height": self.target_h,
                "width": self.target_w,
                "keep_ratio": self.keep_ratio,
                "interp": self.interp,
                "channel_order": self.channel_order,
                "normalization": {
                    "type": self.norm_type,
                    "divide_by_255": self.norm_scale,
                    "mean": self.norm_mean,
                    "std": self.norm_std,
                },
            },
            "native_threshold": self.native_threshold,
            "reading_order": order.declare("model")
            if self.has_order
            else order.declare("ours", "ours_top_down_left_right: the model gives no rank"),
            "thresholds_by_class": self.thresholds(),
            "threshold_drift": self.threshold_drift(),
            "label_vocabulary": self.labels,
            "label_map": self.label_map(),
            "prompts": {},
        }

    def read(self, image_path: str, index: int, dpi: float) -> Page:
        import cv2
        import numpy as np

        img = cv2.imread(image_path)
        if img is None:
            raise RuntimeError(f"the page raster does not read: {image_path}")
        h, w = img.shape[:2]
        rz = cv2.resize(img, (self.target_w, self.target_h), interpolation=self.interp)
        x = rz[:, :, ::-1].astype(np.float32)
        if self.norm_scale:
            x /= 255.0
        if self.norm_type == "mean_std":
            x = (x - np.array(self.norm_mean, np.float32)) / np.array(self.norm_std, np.float32)
        x = x.transpose(2, 0, 1)[None]
        outs = self.sess.run(
            None,
            {
                "image": x,
                "im_shape": np.array([[float(self.target_h), float(self.target_w)]], np.float32),
                "scale_factor": np.array([[self.target_h / h, self.target_w / w]], np.float32),
            },
        )
        out = outs[0]
        if out.ndim != 2 or out.shape[1] < 6:
            raise RuntimeError(
                f"first graph output {out.shape}: expected a box table of the shape [N, >=6] (class, score, four coordinates). Parsing it blind means inventing boxes."
            )
        if has_rank(out) != self.has_order:
            raise RuntimeError(
                f"page {index}: the graph answered {out.shape[1]} columns and its declared shape said {('a rank' if self.has_order else 'none')}; a rank read from one and not the other is invented order"
            )
        thr = self.thresholds()
        kept, rejected = ([], {})
        for row in out:
            cid, score = (int(row[0]), float(row[1]))
            if not 0 <= cid < len(self.labels):
                continue
            label = self.labels[cid]
            if score < thr[label]:
                if score > rejected.get(label, 0.0):
                    rejected[label] = score
                continue
            kept.append((row, label, score))
        which = None if self.has_order else order.rule()
        if self.has_order:
            kept.sort(key=lambda t: float(t[0][6]))
        else:
            names = [_l for _r, _l, _s in kept]
            pol = self.policy() if which == "docling" else None
            order.cover(pol, which)
            perm = order.permutation(
                names,
                [(float(r[2]), float(r[3]), float(r[4]), float(r[5])) for r, _l, _s in kept],
                w,
                h,
                index,
                pol,
                which,
            )
            kept = [kept[i] for i in perm]
        ranks = (
            [int(round(float(r[6]))) for r, _l, _s in kept]
            if self.has_order
            else list(range(len(kept)))
        )
        ties = len(ranks) - len(set(ranks))
        blocks = [
            Block(
                block_id=i,
                box=(float(r[2]), float(r[3]), float(r[4]), float(r[5])),
                label=label,
                score=score,
                order=rank,
            )
            for i, ((r, label, score), rank) in enumerate(zip(kept, ranks, strict=True))
        ]
        return Page(
            index=index,
            width=w,
            height=h,
            dpi=dpi,
            blocks=blocks,
            raw={
                "output_rows": int(out.shape[0]),
                "columns": int(out.shape[1]),
                "graph_outputs": len(outs),
                "all_rows": [[float(v) for v in r] for r in out],
            },
            meta={
                "detector": self.name,
                "boxes_accepted": len(kept),
                "rank_ties": ties,
                "reading_order": order.declare("model")
                if self.has_order
                else order.declare("ours", order.WORDS[which] + ": the model gives no rank"),
                "best_rejected_by_class": rejected,
            },
        )
