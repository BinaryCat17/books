"""The layout detector as a contour recogniser in its own right.

The FIRST HALF of the first level: boxes, labels and reading order, no VLM call.
Local, on the CPU, free -- 214 MB of weights, a couple of seconds a page. Its
worth: contour metrics get checked on a real model's real output without
renting a card.

WHY PAST THE PADDLEX PIPELINE. By measurement, not from love of the low level.
Its postprocessing ERASES THE READING ORDER OF EXACTLY WHAT WE CUT OUT: over
539 pages of one book `block_order` is `null` for 683 of 683 `image`, 695 of
695 `figure_title`, 584 of 584 `table`, 534 of 534 `number` -- and 0 of 6431
`text`. The raw output ranks EVERY box: 1254 of 1254 over 65 pages of `bench/`.
The order is there; it is thrown away selectively. It deletes boxes too: over
six books (3268 pages) `image` 2660 -> 1872, `inline_formula` 15541 -> 14.
Geometry it barely touches -- boxes match the detector's byte for byte -- so
the stages select, they do not reshape.

WHAT THESE NUMBERS CANNOT JUDGE. Those runs carried our own patch layer: the
same directories' `job.log` lists "layout detection in twelve looks" and "text
blocks resembling a table go for a re-ask". So the pipeline's TABLE COUNT is
not comparable with ours -- theirs came of relabelling by our own hand, not of
the library. Only what the patches never touched compares: reading order and
box deletion, above.

WHAT THIS MODULE MUST NOT DO. Merge boxes, cut across a gutter, re-ask, resolve
a `{table, text}` conflict. Threshold selection is all that happens here, and
the threshold comes from the weights. The graph's raw answer is kept WHOLE,
before selection: otherwise the threshold, our one intervention, cannot be
replayed without paying for a recount.
"""
import hashlib
import os

from ..run import knobs
from .base import Block, Page, Recognizer
from .. import order

# Where paddlex keeps its official weights: a foreign library's convention, not
# a setting of ours. `LAYOUT_MODEL_DIR` is empty exactly to say "take them
# where they lie by default", and the resolved path goes into the fingerprint.
PADDLEX_MODELS = os.path.expanduser("~/.paddlex/official_models")


class WeightsMissing(RuntimeError):
    """Weights are missing or incomplete. An ordinary error, not an exit.

    Not `SystemExit`: the adapter is a library, and the bench must catch this
    like any other trouble instead of dying with the process.
    """


def weights_dir() -> str:
    """Where the detection weights lie. An empty knob is paddlex's convention."""
    d = knobs.knob("LAYOUT_MODEL_DIR")
    if d:
        return d
    return os.path.join(PADDLEX_MODELS, knobs.knob("LAYOUT_MODEL_NAME") + "_onnx")


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------- reading order
# ONE SEAM, HERE FOR THE BATTERY, which breaks the checked place IN MEMORY. The
# probe "our rule displaced the model rank" needs a MODULE-level name to patch:
# assembly order is checked by BEHAVIOUR, and tree parsing would see `.sort(`
# and agree with any key. Its pair, "an order the model never gave is not set
# at all", patches `order.permutation`, where the rule now lives. Of the module
# and not the class: `setattr` puts a `staticmethod` back as a PLAIN function,
# the call would arrive shifted by an argument, and the damage would outlive
# the mutation (TypeError).


def has_rank(out) -> bool:
    """Do the weights carry a READING RANK. Six columns mean they do not.

    `PP-DocLayout_plus-L` had no pointer net yet -- class, score, four
    coordinates, and that is all; V2 added it. A VALUE, not an omission, and it
    goes into the fingerprint explicitly.
    """
    return out.shape[1] >= 7


class DocLayout(Recognizer):
    """PP-DocLayoutV2 (ONNX) directly: boxes, labels, reading order.

    `read()` returns a `Page` without one character of text: `content` `None`
    on every block, `kind` `"none"`. Text is the first level's second half, a
    separate recogniser.
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

        # The label vocabulary comes from the WEIGHTS, not the pipeline yaml,
        # whose index comments lie: `9: footer`, `13: header`, `23: text`,
        # where in fact 9 is `footer_image`, 13 `header_image`, 23
        # `vertical_text`. Index 21 = `table` agrees in both, which is why it
        # went unnoticed.
        self.labels: list[str] = list(cfg["label_list"])

        # Preprocessing comes from the weights too; not one number here is
        # ours. `target_size` is stored as (HEIGHT, WIDTH), the way
        # `Resize.generate_scale` reads it in PaddleDetection (`resize_h,
        # resize_w = self.target_size`). At 800x800 the swap is invisible, so
        # the order stays explicit and the fields are named -- otherwise the
        # first non-square weights skew the scale while boxes stay plausible.
        rz = next(p for p in cfg["Preprocess"] if p.get("type") == "Resize")
        self.target_h, self.target_w = (int(v) for v in rz["target_size"])
        self.keep_ratio = bool(rz.get("keep_ratio", False))
        if self.keep_ratio:
            # `read()` squeezes the raster to exactly target_h x target_w.
            # keep_ratio would need padding, subtracted back out of the
            # coordinates. Such weights we refuse LOUDLY -- in silence they
            # would give plausible, shifted boxes.
            raise WeightsMissing(
                "the weights say keep_ratio: true, while the adapter squeezes "
                "the raster with no padding. The boxes would come out shifted "
                "and plausible at once.")
        self.interp = int(rz.get("interp", 2))
        self.native_threshold = float(cfg.get("draw_threshold", 0.5))

        # Normalization is read from the weights, not assumed. These have
        # `norm_type: none`, mean 0, std 1 -- division by 255 and nothing else,
        # so while that holds the difference is invisible; on the first weights
        # with mean/std a silent assumption would give plausible wrong boxes.
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

    # --------------------------------------------------------- thresholds
    def thresholds(self) -> dict[str, float]:
        """A threshold for EACH of the 25 classes, no default picked up en route.

        Not a one-key dict, and that is paid for: in paddlex postprocessing a
        threshold dict with one class silently gives the rest 0.5, so "lower
        the table threshold" moved every class at once. We write the selection
        here; same rule -- list them all.

        `table` comes from `LAYOUT_TABLE_THRESHOLD`, the other twenty-four from
        `LAYOUT_SCORE_THRESHOLD`. Two knobs because the table is the only class
        whose threshold this project has already tinkered with, and that trace
        must stay separately visible.
        """
        common = float(knobs.knob("LAYOUT_SCORE_THRESHOLD"))
        table = float(knobs.knob("LAYOUT_TABLE_THRESHOLD"))
        return {lab: (table if lab == "table" else common) for lab in self.labels}

    def threshold_drift(self) -> list[str]:
        """How the ACTING thresholds differ from the weights' native one.

        The value is compared, not the registry default: the earlier version
        checked `KNOB[...].default`, so `LAYOUT_SCORE_THRESHOLD=0.99` passed in
        silence and the guard slept in the one case it was written for.
        """
        out = []
        for name in ("LAYOUT_SCORE_THRESHOLD", "LAYOUT_TABLE_THRESHOLD"):
            v = float(knobs.knob(name))
            if abs(v - self.native_threshold) >= 1e-9:
                out.append(f"{name}={v} against the native "
                           f"draw_threshold={self.native_threshold}")
        return out

    # -------------------------------------------------------- fingerprint
    def model_name(self) -> str:
        """The model name comes from the WEIGHTS (`Global.model_name`), not the knob.

        `LAYOUT_MODEL_NAME` only picks the default directory (see
        `weights_dir`); with `LAYOUT_MODEL_DIR` set it has nothing to do with
        the weights lying there. Measured: with
        `LAYOUT_MODEL_DIR=~/.paddlex/official_models/PP-DocLayoutV3_onnx` and
        the knob at its default, the snapshot wrote "model: PP-DocLayoutV2"
        beside the sha256 of V3 weights, the log "PP-DocLayoutV2 from
        ...V3_onnx".

        Nothing else catches it: V2 and V3 label vocabularies match BYTE FOR
        BYTE (25 classes each) and native `draw_threshold` is 0.5 for both, so
        by construction neither the policy guard (`policy.for_labels` chooses
        by vocabulary) nor `threshold_drift` sees V3 put in for V2.
        `PP-DocLayout_plus-L` has another vocabulary (20 classes) and a
        differently named policy that reaches the log, so THAT substitution
        shows without the name. The invisible pair is V2/V3.
        """
        import yaml

        cfg_path = os.path.join(self.dir, "inference.yml")
        with open(cfg_path, encoding="utf-8") as f:
            g = yaml.safe_load(f).get("Global") or {}
        # Weights with no name mean "not declared", not a licence to fall
        # back on the knob: that silent substitution is what is fixed here.
        return g.get("model_name") or "not declared in the weights"

    def knobs_read(self) -> tuple[str, ...]:
        """The knobs THIS adapter reads. Verified by grep over the file.

        `knobs.knob()` is called five times over four names:
        `LAYOUT_MODEL_DIR` and `LAYOUT_MODEL_NAME` in `weights_dir()`,
        `LAYOUT_SCORE_THRESHOLD` and `LAYOUT_TABLE_THRESHOLD` in `thresholds()`
        and `threshold_drift()`, `LAYOUT_MODEL_NAME` again in `fingerprint()`
        (the "name by knob" field).

        Both weights knobs are declared UNCONDITIONALLY, though `weights_dir()`
        runs only for `DocLayout()` without a directory: a knob that acts on
        even one path acts. The opposite caution costs more -- "this knob does
        not concern you" on a run where it chose the weights.
        """
        return ("LAYOUT_MODEL_NAME", "LAYOUT_MODEL_DIR",
                "LAYOUT_SCORE_THRESHOLD", "LAYOUT_TABLE_THRESHOLD")

    def label_map(self) -> dict[str, str]:
        """The model's vocabulary IS the common one: labels are not translated."""
        return {}

    def fingerprint(self) -> dict:
        """What tells this run from another. Travels into the snapshot whole."""
        return {
            "name": self.name,
            "model": self.model_name(),
            # The knob stands beside the name from the weights NOT for
            # decoration: their divergence IS a weights substitution, visible
            # no other way.
            "name_from_knob": knobs.knob("LAYOUT_MODEL_NAME"),
            "weights_dir": self.dir,
            "sha256_weights": _sha256(self.onnx),
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
            "reading_order": ("model_rank" if getattr(self, "has_order", True)
                               else "ours_top_down_left_right: the model "
                                    "gives no rank"),
            "thresholds_by_class": self.thresholds(),
            "threshold_drift": self.threshold_drift(),
            "label_vocabulary": self.labels,
            # Declared even when empty: an empty dict means "the model's
            # vocabulary is the common one", and that is a VALUE.
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
        # BGR -> RGB: cv2 reads BGR, PaddleDetection's Decode converts to
        # RGB. NOTHING CHECKS THIS: the synthetic bench is achromatic (`_age`
        # greys the page), and on grey a channel swap is invisible. The order
        # comes from foreign code, NOT from measurement -- it needs a colour
        # page, and until then it is a convention, not a fact.
        x = rz[:, :, ::-1].astype(np.float32)
        if self.norm_scale:
            x /= 255.0
        if self.norm_type == "mean_std":
            x = (x - np.array(self.norm_mean, np.float32)) / np.array(
                self.norm_std, np.float32)
        x = x.transpose(2, 0, 1)[None]
        # The number of graph outputs is NOT fixed: PP-DocLayoutV2 has two --
        # boxes [N,8] and a counter; PP-DocLayoutV3 three -- boxes [N,7], a
        # counter and a reading-order relation matrix [N,200,200]. Unpacking
        # two rigidly dropped the run on the first page of the new weights: a
        # model update ran into one line.
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
        self.has_order = has_rank(out)

        thr = self.thresholds()
        kept, rejected = [], {}
        for row in out:
            cid, score = int(row[0]), float(row[1])
            if not 0 <= cid < len(self.labels):
                continue
            label = self.labels[cid]
            if score < thr[label]:
                # The best REJECTED per class: without it "table 0" reads as
                # "no table on the page" when it may mean "a table 0.03 below
                # the threshold", and that one is settled by a knob.
                if score > rejected.get(label, 0.0):
                    rejected[label] = score
                continue
            kept.append((row, label, score))

        # Reading order. The graph gives eight numbers per box: class, score,
        # four coordinates and the rank -- twice, column 6 being exactly the
        # rounding of column 7 (checked over 6000 rows, 6000 of 6000). Either
        # sort gives one order.
        #
        # `Block.order` gets the MODEL'S OWN RANK, not our sort position. That
        # matters twice:
        #
        #  * ranks come with HOLES where the threshold removed a box.
        #    Continuous numbering erased that trace, and two runs at different
        #    thresholds gave incomparable `order` for the same box;
        #  * ranks come TIED: 48 boxes of exactly equal rank on 18 pages of 65,
        #    among them `{table, text}` pairs on one rectangle. We do NOT
        #    resolve the tie -- a stable sort on the single rank leaves them as
        #    the graph handed them over, for a declared policy one level up.
        #    The earlier version added the LABEL as a second key, so the
        #    alphabet resolved {table, text} on one rectangle, `table` always
        #    before `text`, and the HTML builder took that for reading order:
        #    exactly the decision for the model we promised not to make.
        which = None if self.has_order else order.rule()
        if self.has_order:
            kept.sort(key=lambda t: float(t[0][6]))
        else:
            # THE MODEL GIVES NO RANK -- THEN THE ORDER IS OURS, AND
            # DECLARED. Nothing stood here, and boxes went into the book as the
            # graph handed them over after duplicate suppression: BY DESCENDING
            # CONFIDENCE. Measured (plus-L, 200 pages of `bench/annopage`, 3354
            # adjacent box pairs): descending confidence 100.0% of pairs, "top
            # down and left to right" about half -- a coin. The exact figure is
            # NOT REPEATED HERE on purpose: it lived in four copies and drifted
            # (50.4 against 50.1); it is stated once, in section 18 of
            # `docs/contour-notes.md`. `meta` said "ours, position in the list"
            # -- honest, but a list position is an accident, not a rule, and
            # the book was assembled by it.
            #
            # We fix not the model's boxes but the order the model never gave:
            # ours by definition, so a DECLARED rule. IT LIVES IN `order.py`,
            # ONE FOR THE PROJECT, chosen by `ASSEMBLY_ORDER`. `our_order_key`
            # stood here -- first of FOUR copies across three adapters, two of
            # which sorted by a key other than the one they declared -- and the
            # choice between it and the graph order was UNSETTLED. Measurement
            # settled it, and both lost to a third: on the same V2 boxes our
            # rule gives 2471 extra jumps, the model rank 501, docling's rules
            # 439, ours worse than both at all 16 sweep points (`order.py`).
            names = [_l for _r, _l, _s in kept]
            order.cover(self.labels, which)
            perm = order.permutation(
                names, [(float(r[2]), float(r[3]), float(r[4]), float(r[5]))
                        for r, _l, _s in kept],
                w, h, index, self.labels, which)
            kept = [kept[i] for i in perm]
        # No model rank -- then `order` is our sort position, and the
        # fingerprint says so: calling it a rank would credit the model with an
        # order it never gave.
        ranks = ([int(round(float(r[6]))) for r, _l, _s in kept]
                 if self.has_order else list(range(len(kept))))
        ties = len(ranks) - len(set(ranks))
        blocks = [
            Block(block_id=i, box=(float(r[2]), float(r[3]),
                                   float(r[4]), float(r[5])),
                  label=label, score=score, order=rank)
            for i, ((r, label, score), rank) in enumerate(zip(kept, ranks))]

        return Page(
            index=index, width=w, height=h, dpi=dpi, blocks=blocks,
            # The graph's answer WHOLE, before selection -- the module
            # header says why the evidence cannot be thrown away.
            raw={"output_rows": int(out.shape[0]),
                 "columns": int(out.shape[1]),
                 "graph_outputs": len(outs),
                 "all_rows": [[float(v) for v in r] for r in out]},
            meta={"detector": self.name, "raster": image_path,
                  "boxes_accepted": len(kept),
                  "rank_ties": ties,
                  # WHOSE ORDER THIS IS -- told to the METRIC, not only to
                  # the snapshot: `metrics._model_has_rank` reads the PAGE's
                  # `meta`, not the fingerprint, and without the field defaults
                  # to "model rank". The six-column build (PP-DocLayout_plus-L;
                  # weights beside V2, switched on by LAYOUT_MODEL_DIR) has no
                  # rank at all, `order` is our numbering of graph rows, and on
                  # the stored plus-L runs the metric printed "agreed"
                  # 29/36/41/44/46/44 % over six benches instead of "NOT
                  # COMPARED" -- a zero from misunderstanding dressed as a
                  # percentage, and a low one: it reads as "the model reads the
                  # page in the wrong order".
                  #
                  # The battery showed it was noise: the probe "reading order
                  # reversed: it fell" answered NO on those same six runs,
                  # because reversing OUR numbering raised agreement to
                  # 71/64/59/56/54/56 % -- wobbling around half. With this line
                  # the probe prints "no data", and uncaught mutations on
                  # plus-L fell by one in each of the six runs; on the nine V2
                  # benches (real ranks) it was 0 and stayed 0.
                  #
                  # THE WORD `ours` MUST COME FIRST: that prefix is the whole
                  # signal by which the guard knows our order
                  # (`models/base.ours_order`, one place for the project). Case
                  # it strips deliberately, so lower case is convention, not
                  # condition. Changing these words, keep `ours` first.
                  "reading_order": ("model_rank" if self.has_order else
                                     order.WORDS[which]
                                     + ": the model gives no rank"),
                  "best_rejected_by_class": rejected})
