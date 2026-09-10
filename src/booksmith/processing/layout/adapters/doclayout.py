"""PP-DocLayoutV2/V3 (ONNX) straight off the graph: boxes, labels, reading order.

In: a page raster. Out: a `Page` with no text. Local and free, on the CPU.

Past the paddlex pipeline: its postprocessing erases the reading rank of exactly
what we cut out (`block_order` null for every image, table and figure_title over
539 pages) and deletes boxes. Nothing here merges boxes, cuts across a gutter,
re-asks or resolves a `{table, text}` conflict; threshold selection is all that
happens, and the graph's raw answer is kept whole before it.
"""
import os

from booksmith.core import book, knobs
from booksmith.core.page import Block, Page
from booksmith.processing.layout.base import Detector
from booksmith.core import order
from booksmith.core import stamp
from booksmith.core.errors import WeightsMissing

# Where paddlex keeps its official weights: a foreign convention, not a setting of ours.
PADDLEX_MODELS = os.path.expanduser("~/.paddlex/official_models")



def weights_dir() -> str:
    """Where the detection weights lie. An empty knob is paddlex's convention."""
    d = knobs.knob("LAYOUT_MODEL_DIR")
    if d:
        return d
    return os.path.join(PADDLEX_MODELS, knobs.knob("LAYOUT_MODEL_NAME") + "_onnx")




# ---------------------------------------------------------- reading order
# A module-level name a probe may patch in memory; of the module, not the class,
# since `setattr` puts a `staticmethod` back as a plain function.


def has_rank(out) -> bool:
    """Do the weights carry a reading rank. Six columns mean they do not:
    `PP-DocLayout_plus-L` has no pointer net, V2 does. A value, not an
    omission, and it goes into the fingerprint explicitly.
    """
    return out.shape[1] >= 7


class DocLayout(Detector):
    """PP-DocLayoutV2 (ONNX) directly: boxes, labels, reading order.
    `read()` returns a `Page` without one character of text -- `content` `None`,
    `kind` `"none"`. Text is level two, a separate recogniser.
    """

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
                f"no layout detection weights in {self.dir}: missing "
                f"{', '.join(os.path.basename(m) for m in missing)}.\n"
                f"Name the directory with the knob LAYOUT_MODEL_DIR, or put "
                f"the weights where paddlex looks ({PADDLEX_MODELS}).")
        with open(cfg_path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f)

        # The vocabulary comes from the weights, not the pipeline yaml, whose comments lie.
        self.labels: list[str] = list(cfg["label_list"])

        # Preprocessing comes from the weights; `target_size` is (height, width), as
        # `Resize.generate_scale` reads it -- at 800x800 a swap would be invisible.
        rz = next(p for p in cfg["Preprocess"] if p.get("type") == "Resize")
        self.target_h, self.target_w = (int(v) for v in rz["target_size"])
        self.keep_ratio = bool(rz.get("keep_ratio", False))
        if self.keep_ratio:
            # `read()` squeezes with no padding, so keep_ratio weights come out shifted.
            raise WeightsMissing(
                "the weights say keep_ratio: true, while the adapter squeezes "
                "the raster with no padding. The boxes would come out shifted "
                "and plausible at once.")
        self.interp = int(rz.get("interp", 2))
        self.native_threshold = float(cfg.get("draw_threshold", 0.5))

        # Normalization comes from the weights, not assumed: these divide by 255 and no more.
        nm = next((p for p in cfg["Preprocess"]
                   if p.get("type") == "NormalizeImage"), None)
        self.norm_type = (nm or {}).get("norm_type", "none")
        self.norm_mean = [float(v) for v in (nm or {}).get("mean", [0.0] * 3)]
        self.norm_std = [float(v) for v in (nm or {}).get("std", [1.0] * 3)]
        self.norm_scale = bool((nm or {}).get("is_scale", True))
        if self.norm_type not in ("none", "mean_std"):
            raise WeightsMissing(
                f"unknown normalization {self.norm_type!r} in inference.yml: "
                f"substituting ours would feed the model the wrong thing.")
        self.channel_order = "rgb"

        self.sess = ort.InferenceSession(
            self.onnx, providers=["CPUExecutionProvider"])
        self.ort_version = ort.__version__
        self.providers = list(self.sess.get_providers())
        # Whether the weights carry a reading rank is graph metadata, static:
        # the first output's column count, eight or seven with a rank, six
        # without. Decided here, before any page, so the fingerprint and the
        # describe say the same thing at construction as after the book.
        cols = self.sess.get_outputs()[0].shape
        if len(cols) != 2 or not isinstance(cols[1], int):
            raise WeightsMissing(
                f"the graph's first output has shape {cols}, and a box table "
                f"of a fixed number of columns was expected; whether these "
                f"weights carry a rank cannot be told")
        self.has_order = cols[1] >= 7

    # --------------------------------------------------------- thresholds
    def thresholds(self) -> dict[str, float]:
        """A threshold for each class, no default picked up en route: a one-key
        dict silently gives the rest 0.5, so every class is listed. `table` has
        a knob of its own, being the one class already tinkered with.
        """
        common = knobs.number("LAYOUT_SCORE_THRESHOLD")
        table = knobs.number("LAYOUT_TABLE_THRESHOLD")
        return {lab: (table if lab == "table" else common) for lab in self.labels}

    def threshold_drift(self) -> list[str]:
        """How the acting thresholds differ from the weights' native one: the
        value is compared, not the registry default, or a knob set to 0.99
        would pass in silence.
        """
        out = []
        for name in ("LAYOUT_SCORE_THRESHOLD", "LAYOUT_TABLE_THRESHOLD"):
            v = knobs.number(name)
            if abs(v - self.native_threshold) >= 1e-9:
                out.append(f"{name}={v} against the native "
                           f"draw_threshold={self.native_threshold}")
        return out

    # -------------------------------------------------------- fingerprint
    def model_name(self) -> str:
        """The name comes from the weights (`Global.model_name`), not the knob,
        which only picks the default directory. V2 and V3 share a vocabulary and
        a native threshold, so nothing else here would catch one put in for the other.
        """
        import yaml

        cfg_path = os.path.join(self.dir, "inference.yml")
        with open(cfg_path, encoding="utf-8") as f:
            g = yaml.safe_load(f).get("Global") or {}
        # No name in the weights means "not declared", not a licence to use the knob.
        return g.get("model_name") or "not declared in the weights"

    def knobs_read(self) -> tuple[str, ...]:
        """The knobs this adapter reads, verified by grep over the file. All
        declared unconditionally, `ASSEMBLY_ORDER` included: a knob that acts on
        even one path acts, at the price of entering identities it did not steer.
        """
        return ("LAYOUT_MODEL_NAME", "LAYOUT_MODEL_DIR",
                "LAYOUT_SCORE_THRESHOLD", "LAYOUT_TABLE_THRESHOLD",
                "ASSEMBLY_ORDER")

    def label_map(self) -> dict[str, str]:
        """The model's vocabulary IS the common one: labels are not translated."""
        return {}

    def label(self) -> str:
        """From the weights, not from `LAYOUT_MODEL_NAME`: the knob is what was
        asked for and the weights are what answered. Undeclared weights give a
        name `safe_label` refuses, and `--run` is the answer.
        """
        return book.safe_label(self.model_name(), "the layout weights")

    def fingerprint(self) -> dict:
        """What tells this run from another. Travels into the snapshot whole."""
        return {
            "name": self.name,
            "model": self.model_name(),
            # Beside the name from the weights: their divergence is a weights swap.
            "name_from_knob": knobs.knob("LAYOUT_MODEL_NAME"),
            "weights_dir": self.dir,
            "sha256_weights": stamp.sha256(self.onnx),
            "onnxruntime": self.ort_version,
            "providers": self.providers,
            "input": {"height": self.target_h, "width": self.target_w,
                     "keep_ratio": self.keep_ratio, "interp": self.interp,
                     "channel_order": self.channel_order,
                     "normalization": {"type": self.norm_type,
                                      "divide_by_255": self.norm_scale,
                                      "mean": self.norm_mean,
                                      "std": self.norm_std}},
            "native_threshold": self.native_threshold,
            "reading_order": (order.declare("model") if self.has_order
                               else order.declare("ours", "ours_top_down_left_right: the "
                                                  "model gives no rank")),
            "thresholds_by_class": self.thresholds(),
            "threshold_drift": self.threshold_drift(),
            "label_vocabulary": self.labels,
            # Declared even when empty: an empty dict is a value, not a gap.
            "label_map": self.label_map(),
            # The detector has no prompts at all -- also a value, not a gap.
            "prompts": {},
        }

    # ------------------------------------------------------------ the count
    def read(self, image_path: str, index: int, dpi: float) -> Page:
        """Read a page raster: boxes, labels, order. No text."""
        import cv2
        import numpy as np

        img = cv2.imread(image_path)
        if img is None:
            raise RuntimeError(f"the page raster does not read: {image_path}")
        h, w = img.shape[:2]
        rz = cv2.resize(img, (self.target_w, self.target_h),
                        interpolation=self.interp)
        # BGR -> RGB, as PaddleDetection's Decode does. Nothing checks it: the
        # bench is achromatic, and on grey a channel swap is invisible.
        x = rz[:, :, ::-1].astype(np.float32)
        if self.norm_scale:
            x /= 255.0
        if self.norm_type == "mean_std":
            x = (x - np.array(self.norm_mean, np.float32)) / np.array(
                self.norm_std, np.float32)
        x = x.transpose(2, 0, 1)[None]
        # The number of graph outputs is not fixed: V2 gives two, V3 three.
        outs = self.sess.run(None, {
            "image": x,
            "im_shape": np.array([[float(self.target_h),
                                   float(self.target_w)]], np.float32),
            "scale_factor": np.array([[self.target_h / h,
                                       self.target_w / w]], np.float32)})
        out = outs[0]
        if out.ndim != 2 or out.shape[1] < 6:
            raise RuntimeError(
                f"first graph output {out.shape}: expected a box table of the "
                f"shape [N, >=6] (class, score, four coordinates). Parsing it "
                f"blind means inventing boxes.")
        if has_rank(out) != self.has_order:
            raise RuntimeError(
                f"page {index}: the graph answered {out.shape[1]} columns and "
                f"its declared shape said {'a rank' if self.has_order else 'none'}; "
                f"a rank read from one and not the other is invented order")

        thr = self.thresholds()
        kept, rejected = [], {}
        for row in out:
            cid, score = int(row[0]), float(row[1])
            if not 0 <= cid < len(self.labels):
                continue
            label = self.labels[cid]
            if score < thr[label]:
                # The best rejected per class: "table 0" may mean "0.03 below the threshold".
                if score > rejected.get(label, 0.0):
                    rejected[label] = score
                continue
            kept.append((row, label, score))

        # `Block.order` is the model's own rank, not our sort position: the ranks
        # come with holes where the threshold removed a box, and come tied -- a tie
        # is left as the graph handed it over rather than resolved by us.
        which = None if self.has_order else order.rule()
        if self.has_order:
            kept.sort(key=lambda t: float(t[0][6]))
        else:
            # No model rank, so the order is ours and declared: the rule lives in
            # `order.py`, one for the project, chosen by `ASSEMBLY_ORDER`.
            names = [_l for _r, _l, _s in kept]
            pol = self.policy() if which == "docling" else None
            order.cover(pol, which)
            perm = order.permutation(
                names, [(float(r[2]), float(r[3]), float(r[4]), float(r[5]))
                        for r, _l, _s in kept],
                w, h, index, pol, which)
            kept = [kept[i] for i in perm]
        # With no model rank `order` is our sort position, and the fingerprint says so.
        ranks = ([int(round(float(r[6]))) for r, _l, _s in kept]
                 if self.has_order else list(range(len(kept))))
        ties = len(ranks) - len(set(ranks))
        blocks = [
            Block(block_id=i, box=(float(r[2]), float(r[3]),
                                   float(r[4]), float(r[5])),
                  label=label, score=score, order=rank)
            for i, ((r, label, score), rank) in enumerate(zip(kept, ranks, strict=True))]

        return Page(
            index=index, width=w, height=h, dpi=dpi, blocks=blocks,
            # The graph's answer whole, before selection: the threshold must replay.
            raw={"output_rows": int(out.shape[0]),
                 "columns": int(out.shape[1]),
                 "graph_outputs": len(outs),
                 "all_rows": [[float(v) for v in r] for r in out]},
            # No `raster` path: a machine-local scratch name makes identical runs differ.
            meta={"detector": self.name,
                  "boxes_accepted": len(kept),
                  "rank_ties": ties,
                  # Whose order this is: `metrics._model_has_rank` reads the page `meta`,
                  # not the fingerprint, and defaults to "model rank" without it.
                  # `ours` must come first -- `core/page.ours_order` keys on that prefix.
                  "reading_order": (order.declare("model") if self.has_order else
                                     order.declare("ours", order.WORDS[which]
                                                   + ": the model gives no rank")),
                  "best_rejected_by_class": rejected})
