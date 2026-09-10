"""Docling layout detectors: heron (RT-DETRv2 R50) and egret-medium (D-FINE).

In: a page raster. Out: a `Page` of boxes with docling labels and no model
reading order at all -- `Block.order` is the position in our list, declared as
such in the fingerprint, so the order metric may not be run on it. There is no
`chart` class (charts leave as `picture`) and no page number of its own.
`DOCLING_PIPELINE` (`off` by default, `post`, `full`) turns on two vendor
docling classes over the boxes, called unedited: the per-class postprocessor and
the rule-based reading order. What each buys and costs is in `core/knobs.py`.
"""
import json
import os
import sys

from booksmith.core.page import Block, Page
from booksmith.processing.layout.base import Detector
# Label roles are our policy and live in one place; a list here would be a second one.
from booksmith.core import book
from booksmith.core import order
from booksmith.core.order import declare as declare_order
from booksmith.core import policy
from booksmith.core import knobs
from booksmith.core import stamp
from booksmith.core.errors import Refusal, WeightsMissing

MODELS = os.path.expanduser("~/.paddlex/official_models")



# --- docling vendor pipeline: label translation ----------------------------

# One set of 17 docling classes spelled two ways in the weights. Declared by name,
# not derived: a rule would slip a new class to the vendor under an invented label.
EGRET_TO_DOCLING = {
    "Caption": "caption",
    "Checkbox-Selected": "checkbox_selected",
    "Checkbox-Unselected": "checkbox_unselected",
    "Code": "code",
    "Document Index": "document_index",
    "Footnote": "footnote",
    "Form": "form",
    "Formula": "formula",
    "Key-Value Region": "key_value_region",
    "List-item": "list_item",
    "Page-footer": "page_footer",
    "Page-header": "page_header",
    "Picture": "picture",
    "Section-header": "section_header",
    "Table": "table",
    "Text": "text",
    "Title": "title",
}

# `off` the model boxes as they are, `post` the postprocessor alone (it also resorts),
# `full` that plus the reading-order rules. Two enabling values, since the effects differ.
PIPELINE_MODES = ("off", "post", "full")

_PIP_INSTALL = ('pip install -e ".[docling]"  (docling-slim==2.123.1 and '
                'rtree; no torch, +54 MB)')


class _DoclingPipeline:
    """Two vendor docling classes over our boxes, no edit of ours inside. Ours is
    the origin flip (the rules expect a bottom origin), the label translation, and
    `skip_cell_assignment=True` since we have no cells. Labels come back ours.
    """

    def __init__(self, mode: str, labels, adapter: str):
        if mode not in PIPELINE_MODES:
            raise Refusal(f"DOCLING_PIPELINE={mode!r}: I know only "
                             f"{PIPELINE_MODES}")
        self.mode = mode
        self.adapter = adapter
        # Lazy import: at `off` the adapter must count with the package absent.
        try:
            import docling
            from docling.datamodel.base_models import Cluster, Page as DlPage
            from docling.datamodel.pipeline_options import (
                BaseLayoutPostprocessorOptions)
            from docling.utils.layout_postprocessor import LayoutPostprocessor
            from docling.models.postprocessing.reading_order_rb import (
                PageElement as RoElement, ReadingOrderPredictor)
            from docling_core.types.doc import BoundingBox, DocItemLabel, Size
        except ImportError as e:
            raise Refusal(
                f"DOCLING_PIPELINE={mode}, and there is no docling "
                f"package: {e}. Install: {_PIP_INSTALL}. Or "
                f"DOCLING_PIPELINE=off -- then the adapter counts the model "
                f"boxes as they are and the package is not needed at all."
                ) from None
        self._Cluster, self._DlPage = Cluster, DlPage
        self._BoundingBox, self._DocItemLabel, self._Size = (
            BoundingBox, DocItemLabel, Size)
        self._LayoutPostprocessor = LayoutPostprocessor
        self._RoElement = RoElement
        # One predictor per run: its constructor sets numbers of its own that must hold.
        self._ro = ReadingOrderPredictor() if mode == "full" else None
        self.options = BaseLayoutPostprocessorOptions(skip_cell_assignment=True)

        # Checked whole at construction against the vocabulary actually asked --
        # `CONFIDENCE_THRESHOLDS`, seventeen names, not `DocItemLabel`'s thirty.
        known = {lab.value for lab in
                 LayoutPostprocessor.CONFIDENCE_THRESHOLDS}
        self.to_docling = {lab: EGRET_TO_DOCLING.get(lab, lab) for lab in labels}
        bad = []
        for lab, name in self.to_docling.items():
            try:
                DocItemLabel(name)
            except ValueError:
                bad.append(f"{lab!r} (-> {name!r}: no such name in the "
                           f"docling vocabulary at all)")
                continue
            if name not in known:
                bad.append(f"{lab!r} (-> {name!r}: the name is in the "
                           f"docling vocabulary, but the postprocessor has "
                           f"no threshold for it)")
        if bad:
            raise Refusal(
                f"adapter {adapter}: labels {', '.join(bad)} are "
                f"indigestible to the docling postprocessor. It knows "
                f"{len(known)} classes -- those listed in "
                f"LayoutPostprocessor.CONFIDENCE_THRESHOLDS -- and takes the "
                f"threshold by label with NO default, so on any other it "
                f"dies with KeyError on the very first page. The translation "
                f"is declared BY NAME in EGRET_TO_DOCLING "
                f"(layout/adapters/docling.py): a rule 'lower-case it' would "
                f"silently accept a new class of new weights and slip it to "
                f"the vendor under an invented name.")
        self.back = {v: k for k, v in self.to_docling.items() if v != k}

        # sha256 of both files: they are the rules, and the package version need not move.
        self.files = {}
        for cls in (LayoutPostprocessor, ReadingOrderPredictor):
            path = sys.modules[cls.__module__].__file__
            self.files[os.path.basename(path)] = stamp.sha256(path)
        self.version = getattr(docling, "__version__", None)

        # Run counters. "Reordered" is two numbers, because two things reorder: the
        # postprocessor sort (both modes) and the order rules (`full` only).
        self.pages = self.before = self.after = self.kids = 0
        self.displaced = 0           # total: out of place against ours
        self.resorted = 0            # postprocessor sort: both modes
        self.reordered = 0           # reading-order rules: `full` only
        self.arte_in_text = 0        # artefact into a TEXT wrapper's children
        self.arte_lost = 0           # ...and not left on the top level

    # The line must begin with "ours": by it `metrics._model_has_rank` knows there is no rank.
    ORDER_RULE = {
        # `post` changes the order: `_sort_clusters(mode="id")` falls back to exact
        # `(top, left)`, our `cluster.cells` being always empty.
        "post": "ours_only_in_the_sense_that_the_model_gave_no_rank: the rule "
                "is FOREIGN -- the docling postprocessor resorted the boxes "
                "by (top, left), exact coordinates, not by our round(y/20) "
                "bands",
        "full": "ours_by_choice_rules_are_doclings_reading_order_rb: RULE-BASED, "
                "740 lines of rules without a single weight, not a model",
    }

    def _label(self, raw):
        """Adapter label -> docling label. An unknown one aloud, not KeyError:
        the fix is one line in `EGRET_TO_DOCLING`, and a bare KeyError would not
        say so.
        """
        try:
            return self._DocItemLabel(self.to_docling[raw])
        except KeyError:
            raise RuntimeError(
                f"label {raw!r} is not from the {self.adapter} weights "
                f"vocabulary: it has no translation into docling's. Declare "
                f"it in EGRET_TO_DOCLING by name.") from None

    def apply(self, blocks, width, height, index):
        """Adapter boxes -> boxes after the vendor. Returns (blocks, meta)."""
        clusters = [
            self._Cluster(
                id=b.block_id, label=self._label(b.label),
                bbox=self._BoundingBox(l=b.box[0], t=b.box[1],
                                       r=b.box[2], b=b.box[3]),
                confidence=b.score, cells=[], children=[])
            for b in blocks]

        resorted = None
        if self.mode in ("post", "full"):
            page = self._DlPage(page_no=index)
            page.size = self._Size(width=float(width), height=float(height))
            # The postprocessor's per-class thresholds are dead here: all seventeen are
            # at most 0.5 and our selection has already cut at `LAYOUT_SCORE_THRESHOLD`.
            clusters = self._LayoutPostprocessor(
                page, clusters, self.options).postprocess()
            # How many the postprocessor itself resorted, in both modes: compared with
            # our numbers (`Cluster.id`), so thinning is not counted as permutation.
            ids = [c.id for c in clusters]
            resorted = sum(1 for a, b in zip(ids, sorted(ids), strict=True) if a != b)

        # At `post` the order rules are never called, so their number is a dash.
        moved = 0 if self.mode == "full" else None
        if self.mode == "full" and clusters:
            size = self._Size(width=float(width), height=float(height))
            els = []
            for i, c in enumerate(clusters):
                bb = c.bbox.to_bottom_left_origin(float(height))
                els.append(self._RoElement(
                    cid=i, text="", page_no=index, page_size=size,
                    label=c.label, l=bb.l, r=bb.r, b=bb.b, t=bb.t,
                    coord_origin=bb.coord_origin))
            # The order depends on the python version: a non-transitive `__lt__` in
            # `reading_order_rb.py` permutes three golden pages of 600 between 3.12 and 3.13.
            order = [e.cid for e in self._ro.predict_reading_order(els)]
            # A permutation must be a permutation: the rules sew three lists back together.
            if sorted(order) != list(range(len(clusters))):
                raise RuntimeError(
                    f"the docling order rules returned no permutation on "
                    f"page {index}: there were {len(clusters)} boxes, "
                    f"{len(order)} numbers came back")
            moved = sum(1 for i, j in enumerate(order) if i != j)
            clusters = [clusters[i] for i in order]

        # Total displacement against our numbering; the two fields below split it by cause.
        final_ids = [c.id for c in clusters]
        displaced = sum(1 for a, b in zip(final_ids, sorted(final_ids), strict=True)
                        if a != b)
        # Who stayed on top: going into children and vanishing from the book differ.
        top = set(final_ids)

        out, kids, arte_in_text, arte_lost = [], {}, 0, 0
        for i, c in enumerate(clusters):
            lab = self.back.get(c.label.value, c.label.value)
            # Children describe themselves: the key is the wrapper's position in this
            # list, and each child carries its own label, box and pre-pipeline number.
            ch = [{"id_before_pipeline": int(k.id),
                   "label": self.back.get(k.label.value, k.label.value),
                   "box": [k.bbox.l, k.bbox.t, k.bbox.r, k.bbox.b]}
                  for k in c.children]
            if ch:
                kids[i] = ch
                # Two numbers for lost structure: an artefact in a text wrapper's
                # children, and one gone from the top list, where nobody can cut it out.
                if policy.role(lab) == "text":
                    art = [k for k in ch
                           if policy.role(k["label"]) == "artifact"]
                    arte_in_text += len(art)
                    arte_lost += sum(1 for k in art
                                     if k["id_before_pipeline"] not in top)
            out.append(Block(
                block_id=i,
                box=(c.bbox.l, c.bbox.t, c.bbox.r, c.bbox.b),
                label=lab, score=c.confidence, order=i))

        self.pages += 1
        self.before += len(blocks)
        self.after += len(out)
        self.kids += sum(len(v) for v in kids.values())
        self.displaced += displaced
        self.resorted += resorted or 0
        self.reordered += moved or 0
        self.arte_in_text += arte_in_text
        self.arte_lost += arte_lost
        meta = {
            "mode": self.mode,
            "boxes_before": len(blocks),
            "boxes_after": len(out),
            "moved_to_children": sum(len(v) for v in kids.values()),
            # Three numbers, and the last two do not add up to the first: they are
            # measured at different steps, each on its own output.
            "boxes_reordered": displaced,
            "reordered_by_postprocessor_sort": resorted,
            "reordered_by_order_rules": moved,
            # The key is the wrapper's position in this list, not a pre-pipeline number.
            "children_by_box_index": kids,
            # Not how much collapsed, but how much was lost by it.
            "artifact_boxes_in_text_wrappers": arte_in_text,
            "of_those_lost_from_top_level": arte_lost,
        }
        return out, meta

    def fingerprint(self):
        return {
            "mode": self.mode,
            "what_is_it": ("VENDOR code, called as it is, without one edit "
                        "of ours inside; reading_order_rb is rule-based, 740 "
                        "lines of rules over boxes, not a single weight"),
            "classes": ["docling.utils.layout_postprocessor.LayoutPostprocessor"]
                      + (["docling.models.postprocessing.reading_order_rb."
                          "ReadingOrderPredictor"] if self.mode == "full"
                         else []),
            "docling_version": self.version,
            "sha256_vendor_files": self.files,
            "postprocess_options": self.options.model_dump(mode="json"),
            "label_map_to_docling": self.to_docling,
            "label_outward": "in the adapter's spelling",
            "summary": {"page_count": self.pages, "boxes_before": self.before,
                     "boxes_after": self.after, "moved_to_children": self.kids,
                     "boxes_reordered": self.displaced,
                     "reordered_by_postprocessor_sort": self.resorted,
                     # A dash, not a zero: at `post` the rules were never called.
                     "reordered_by_order_rules":
                         self.reordered if self.mode == "full" else None,
                     "artifact_boxes_in_text_wrappers":
                         self.arte_in_text,
                     "of_those_lost_from_top_level": self.arte_lost},
        }


class DoclingHeron(Detector):
    name = "docling-heron"
    policy_name = "Docling"

    def __init__(self, model_dir: str | None = None):
        import onnxruntime as ort

        self.dir = model_dir or os.path.join(MODELS, "docling-heron_onnx")
        self.onnx = os.path.join(self.dir, "model.onnx")
        cfg_path = os.path.join(self.dir, "config.json")
        pre_path = os.path.join(self.dir, "preprocessor_config.json")
        missing = [p for p in (self.onnx, cfg_path, pre_path)
                   if not os.path.exists(p)]
        if missing:
            raise WeightsMissing(
                f"no docling heron weights: {missing}. Download three "
                f"files from "
                f"huggingface.co/docling-project/docling-layout-heron-onnx "
                f"into {self.dir}")
        with open(cfg_path, encoding="utf-8") as f:
            cfg = json.load(f)
        i2l = cfg.get("id2label") or {}
        # The vocabulary comes from the weights; this build carries none, so the list acts.
        self.labels = ([i2l[str(i)] for i in range(len(i2l))] if i2l
                       else list(DEFAULT_LABELS))
        # The knob is read once per run, not per page, and before the ONNX session:
        # refusing for a missing package must cost milliseconds, not seconds.
        self.pipeline = knobs.knob("DOCLING_PIPELINE")
        self._pipe = (None if self.pipeline == "off"
                      else _DoclingPipeline(self.pipeline, self.labels,
                                            self.name))
        with open(pre_path, encoding="utf-8") as f:
            pre = json.load(f)
        size = pre.get("size") or {}
        self.target_h = int(size.get("height", 640))
        self.target_w = int(size.get("width", 640))
        # The filter is translated, not passed on: PIL 2 is BILINEAR, cv2 2 is CUBIC.
        pil = int(pre.get("resample", 2))
        # PIL: 0 NEAREST, 1 LANCZOS, 2 BILINEAR, 3 BICUBIC, 4 BOX, 5 HAMMING
        # cv2: 0 NEAREST, 1 LINEAR, 2 CUBIC, 3 AREA, 4 LANCZOS4
        PIL_TO_CV2 = {0: 0, 1: 4, 2: 1, 3: 2, 4: 3, 5: 3}
        if pil not in PIL_TO_CV2:
            raise WeightsMissing(
                f"unknown filter code resample={pil} in the preprocessor: "
                f"substituting our own would shrink the page with the wrong "
                f"filter.")
        self.interp_pil = pil
        self.interp = PIL_TO_CV2[pil]
        self.do_pad = bool(pre.get("do_pad", False))
        if self.do_pad:
            raise WeightsMissing(
                "the preprocessor says do_pad: true, and we shrink the "
                "raster with no padding -- the boxes would come out shifted "
                "and plausible at once.")
        self.do_rescale = bool(pre.get("do_rescale", False))
        self.do_normalize = bool(pre.get("do_normalize", False))
        self.sess = ort.InferenceSession(
            self.onnx, providers=["CPUExecutionProvider"])
        self.ort_version = ort.__version__
        self.providers = list(self.sess.get_providers())
        kinds = {i.name: i.type for i in self.sess.get_inputs()}
        self.uint8_input = "uint8" in kinds.get("images", "")

    def _our_order(self, kept, w, h, index):
        """Our assembly order at `off`, where this list is the book, and a mere
        numbering at `post`/`full`, where the vendor sorts: there the number is
        `Cluster.id`, by which children are stitched to their wrapper.
        """
        if self._pipe is not None:
            kept.sort(key=lambda t: (round(t[2][1] / 20), t[2][0]))
            return kept
        # The rule is asked once and passed on, or the guard and the sort could part.
        which = order.rule()
        order.cover(self.labels, which)
        perm = order.permutation([t[0] for t in kept], [t[2] for t in kept],
                                 w, h, index, self.labels, which)
        return [kept[i] for i in perm]

    def _run_pipeline(self, blocks, w, h, index):
        """Model boxes -> boxes after the vendor. Returns (blocks, meta). The
        order line is handed out from here always, never a constant in `read()`:
        a constant would survive the pipeline being switched on and lie.
        """
        if self._pipe is None:
            # The words come from `order.py`, so they cannot part from the sort.
            return blocks, {"reading_order": declare_order("ours", order.WORDS[order.rule()])}
        blocks, m = self._pipe.apply(blocks, w, h, index)
        pp = self._pipe
        if pp.pages == 1 or pp.pages % 10 == 0:
            print(f"  [docling pipeline {pp.mode}] {pp.pages} pp.: boxes "
                  f"{pp.before} -> {pp.after}, into children {pp.kids} (of "
                  f"those, artefacts in text wrappers {pp.arte_in_text}, "
                  f"lost {pp.arte_lost}), "
                  f"out of place {pp.displaced} (the sort moved "
                  f"{pp.resorted}, the rules permuted "
                  + (str(pp.reordered) if pp.mode == "full"
                     else "-- (never called)") + ")")
        return blocks, {"reading_order": declare_order("ours", _DoclingPipeline.ORDER_RULE[pp.mode]),
                        "docling_pipeline": m}

    def thresholds(self) -> dict[str, float]:
        """The threshold per class. This build has no native `draw_threshold`,
        so the common knob is taken -- and said outright, so that the number
        does not look like a foreign default."""
        common = knobs.number("LAYOUT_SCORE_THRESHOLD")
        return {lab: common for lab in self.labels}

    def threshold_drift(self) -> list[str]:
        """How the acting threshold differs from the native one: this build has
        none -- docling keeps its seventeen thresholds in the pipeline code -- so
        the guard says there is nothing to compare with, not "no drift".
        """
        return [f"the weights have no native threshold; acting is "
                f"LAYOUT_SCORE_THRESHOLD="
                f"{knobs.knob('LAYOUT_SCORE_THRESHOLD')} "
                f"on all {len(self.labels)} classes"]

    def knobs_read(self) -> tuple[str, ...]:
        """The knobs this adapter reads, checked by grep. All three are declared
        unconditionally: a knob that acts on even one path acts. `DoclingEgret`
        inherits the list, having no `knob()` of its own.
        """
        return ("LAYOUT_SCORE_THRESHOLD", "DOCLING_PIPELINE",
                "ASSEMBLY_ORDER")

    def label_map(self) -> dict[str, str]:
        """Labels are not translated into the PP-DocLayoutV2 vocabulary: docling
        has no `chart` at all, and reducing `picture` to `image` would make "a
        chart called a picture" indistinguishable from "a chart found".
        """
        return {}

    def label(self) -> str:
        """The variant: `docling-heron`, `docling-egret`, where the adapter name
        is the model name. `DOCLING_PIPELINE` deliberately stays out of it: it
        changes the identity, and a clash under one label is refused by name."""
        return book.safe_label(self.name, "the docling variant")

    def fingerprint(self) -> dict:
        # The pipeline total, once per run: the adapter has no "run finished" hook, and
        # `detect.py` calls `fingerprint()` before the page loop as well as after it.
        if self._pipe is not None and self._pipe.pages:
            it = self._pipe.fingerprint()["summary"]
            share = (100.0 * it["boxes_after"] / it["boxes_before"]
                    if it["boxes_before"] else 0.0)
            rules = (str(it["reordered_by_order_rules"])
                       if self._pipe.mode == "full" else "-- (never called)")
            # `post` does change the order: the postprocessor sorts by exact (top, left).
            order = ("VENDOR RULES (reading_order_rb, not a model)"
                       if self._pipe.mode == "full" else
                       "resorted by the docling postprocessor by "
                       "(top, left), there is no model rank")
            print(f"docling pipeline {self._pipe.mode}: pages "
                  f"{it['page_count']}, boxes {it['boxes_before']} -> "
                  f"{it['boxes_after']} ({share:.1f}%), into children "
                  f"{it['moved_to_children']}, of those artefacts in text "
                  f"wrappers {it['artifact_boxes_in_text_wrappers']} "
                  f"(lost from the top list "
                  f"{it['of_those_lost_from_top_level']}); "
                  f"out of place against our order "
                  f"{it['boxes_reordered']} (the postprocessor sort moved "
                  f"{it['reordered_by_postprocessor_sort']}, the rules "
                  f"permuted {rules}); reading order {order}")
        return {
            "name": self.name,
            "model": getattr(self, "full_name",
                              "docling-layout-heron (RT-DETRv2 R50)"),
            "architecture": getattr(self, "architecture", "RT-DETRv2 R50"),
            "weights_dir": self.dir,
            "sha256_weights": stamp.sha256(self.onnx),
            "onnxruntime": self.ort_version,
            "providers": self.providers,
            "input": {"height": self.target_h, "width": self.target_w,
                     "pil_filter": self.interp_pil,
                     "cv2_filter": self.interp, "padding": self.do_pad,
                     "input_uint8": self.uint8_input,
                     "divide_by_255": self.do_rescale,
                     "normalization": self.do_normalize},
            # The weights have no native threshold -- a value, not an omission.
            "native_threshold": None,
            "thresholds_by_class": self.thresholds(),
            # Not an empty list: an empty field would read as "no drift" beside the guard.
            "threshold_drift": self.threshold_drift(),
            "label_vocabulary": self.labels,
            "label_map": self.label_map(),
            "prompts": {},
            # The model gives no reading order at all: a value, not an empty place.
            "reading_order": declare_order("none"),
            # Named at `off` too, as a value: an empty place would read as "not looked at".
            "docling_pipeline": (self._pipe.fingerprint() if self._pipe else {
                "mode": "off",
                "what_is_it": ("the vendor postprocessing and docling's "
                            "reading-order rules; switched off -- the model "
                            "boxes go as they are, the order is ours"),
                "docling_version": None,
                "sha256_vendor_files": {},
                "postprocess_options": None,
                "label_map_to_docling": {},
                "summary": None}),
        }

    def read(self, image_path: str, index: int, dpi: float) -> Page:
        import cv2
        import numpy as np

        img = cv2.imread(image_path)
        if img is None:
            raise RuntimeError(f"the page raster does not read: {image_path}")
        h, w = img.shape[:2]
        rz = cv2.resize(img, (self.target_w, self.target_h),
                        interpolation=self.interp)
        x = rz[:, :, ::-1]                     # BGR -> RGB
        if self.uint8_input:
            x = np.ascontiguousarray(x.transpose(2, 0, 1)[None].astype(np.uint8))
        else:
            x = x.astype(np.float32)
            if self.do_rescale:
                x /= 255.0
            x = np.ascontiguousarray(x.transpose(2, 0, 1)[None])
        labels, boxes, scores = self.sess.run(
            None, {"images": x,
                   # (width, height), not the other way round: reversed, boxes leave the sheet.
                   "orig_target_sizes": np.array([[w, h]], np.int64)})
        labels, boxes, scores = labels[0], boxes[0], scores[0]

        thr = self.thresholds()
        kept, rejected = [], {}
        for cid, box, sc in zip(labels, boxes, scores, strict=True):
            cid, sc = int(cid), float(sc)
            if not 0 <= cid < len(self.labels):
                raise RuntimeError(
                    f"the model returned class {cid}, the vocabulary knows "
                    f"{len(self.labels)}: an invented label is worse than a "
                    f"refusal.")
            lab = self.labels[cid]
            if sc < thr[lab]:
                if sc > rejected.get(lab, 0.0):
                    rejected[lab] = sc
                continue
            kept.append((lab, sc, [float(v) for v in box]))
        # The model gives no order, so it is ours, and it lives in `order.py`.
        kept = self._our_order(kept, w, h, index)
        blocks = [Block(block_id=i, box=tuple(b), label=lab, score=sc, order=i)
                  for i, (lab, sc, b) in enumerate(kept)]
        # After our sort and numbering: the box number is the `Cluster.id` children hang on.
        blocks, pipe_meta = self._run_pipeline(blocks, w, h, index)
        return Page(
            index=index, width=w, height=h, dpi=dpi, blocks=blocks,
            raw={"output_rows": int(len(scores)),
                 "all_rows": [[float(c), float(s), *[float(v) for v in b]]
                                for c, b, s in zip(labels, boxes, scores, strict=True)]},
            # No `raster` path: a machine-local scratch name makes identical runs differ.
            meta={"detector": self.name,
                  # The model's number; how many survive the vendor is in "docling pipeline".
                  "boxes_accepted": len(kept),
                  "rank_ties": 0,
                  # The place in the dict is not cosmetic: at `off` the page must not change.
                  **pipe_meta,
                  "best_rejected_by_class": rejected})


DEFAULT_LABELS = (
    "caption", "footnote", "formula", "list_item", "page_footer",
    "page_header", "picture", "section_header", "table", "text", "title",
    "document_index", "code", "checkbox_selected", "checkbox_unselected",
    "form", "key_value_region")


class DoclingEgret(DoclingHeron):
    """docling egret-medium: D-FINE, the third architecture on the bench. Its
    graph gives raw logits and boxes in normalised cxcywh, not finished triples,
    and decoding them is D-FINE's own inference, not our postprocessing.
    """
    name = "docling-egret"
    policy_name = "Docling-egret"
    architecture = "D-FINE"

    def __init__(self, model_dir: str | None = None):
        self.full_name = "docling-layout-egret-medium (D-FINE)"
        super().__init__(model_dir or os.path.join(MODELS, "docling-egret_onnx"))
        names = [i.name for i in self.sess.get_inputs()]
        if names != ["pixel_values"]:
            raise WeightsMissing(
                f"graph input {names}, ['pixel_values'] was expected: "
                f"parsing at random means feeding the model the wrong "
                f"thing.")

    def read(self, image_path: str, index: int, dpi: float) -> Page:
        import cv2
        import numpy as np

        img = cv2.imread(image_path)
        if img is None:
            raise RuntimeError(f"the page raster does not read: {image_path}")
        h, w = img.shape[:2]
        rz = cv2.resize(img, (self.target_w, self.target_h),
                        interpolation=self.interp)
        x = rz[:, :, ::-1].astype(np.float32)
        if self.do_rescale:
            x /= 255.0
        x = np.ascontiguousarray(x.transpose(2, 0, 1)[None])
        logits, boxes = self.sess.run(None, {"pixel_values": x})
        logits, boxes = logits[0], boxes[0]          # [Q, C], [Q, 4] cxcywh
        prob = 1.0 / (1.0 + np.exp(-logits))          # focal loss -> sigmoid
        nq, nc = prob.shape
        if nc != len(self.labels):
            raise RuntimeError(
                f"the graph gave {nc} classes, the vocabulary knows "
                f"{len(self.labels)}: an invented label is worse than a "
                f"refusal.")
        # D-FINE's own rule, not argmax over classes: sigmoid, topk over the flattened
        # Q*C, label = i % C. The length is Q, the graph's `num_queries`, not our knob.
        flat = prob.reshape(-1)
        top = np.argsort(-flat, kind="stable")[:nq]

        thr = self.thresholds()
        # How many rows above their own threshold the topk itself cut: part of the
        # model's rule, but counted on every page, so the loss is never silent.
        thr_row = np.array([thr[lab] for lab in self.labels], np.float32)
        inside = np.zeros(nq * nc, bool)
        inside[top] = True
        cut = int(((prob >= thr_row[None, :]).reshape(-1) & ~inside).sum())

        kept, rejected = [], {}
        for idx in top:
            q, cid = int(idx) // nc, int(idx) % nc
            s = float(flat[idx])
            lab = self.labels[cid]
            if s < thr[lab]:
                if s > rejected.get(lab, 0.0):
                    rejected[lab] = s
                continue
            cx, cy, bw, bh = (float(v) for v in boxes[q])
            kept.append((lab, s, [(cx - bw / 2) * w, (cy - bh / 2) * h,
                                  (cx + bw / 2) * w, (cy + bh / 2) * h]))
        kept = self._our_order(kept, w, h, index)
        blocks = [Block(block_id=i, box=tuple(b), label=lab, score=s, order=i)
                  for i, (lab, s, b) in enumerate(kept)]
        # Counted before the pipeline: the vendor is what suppresses coincident pairs.
        geom = [tuple(b) for _, _, b in kept]
        blocks, pipe_meta = self._run_pipeline(blocks, w, h, index)
        return Page(
            index=index, width=w, height=h, dpi=dpi, blocks=blocks,
            # The graph's answer whole, before our selection: a threshold cannot be
            # lowered for one class without the sigmoid on queries a neighbour won.
            raw={"output_rows": int(nq),
                 "class_count": int(nc),
                 "logits": [[float(v) for v in r] for r in logits],
                 "boxes": [[float(v) for v in r] for r in boxes],
                 "how_to_read_logits": "sigmoid per channel (focal loss)",
                 "raw_row_coords": "cxcywh, normalised"},
            meta={"detector": self.name,
                  "boxes_accepted": len(kept), "rank_ties": 0,
                  # See heron: the place of the key keeps the match when the knob is off.
                  **pipe_meta,
                  # The rule as a value, and beside it a number: a zero means they agreed.
                  "selection_rule": f"topk {nq} over the flattened Q*C, "
                                    f"label = i % {nc} (as in D-FINE/RT-DETR)",
                  "extra_labels_on_shared_boxes":
                      len(geom) - len(set(geom)),
                  "rows_above_threshold_outside_topk": cut,
                  # The best rejected among the topk rows: a class missing did not make it.
                  "best_rejected_by_class": rejected})

