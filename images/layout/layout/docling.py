import json
import os
import sys
from layout.page import Block, Page
from layout.detector import Detector
from layout import store as book
from layout import order
from layout import classes as policy_mod
from layout.order import declare as declare_order
from layout import knobs
from layout.log import log
from layout import identity as stamp
from layout.errors import Refusal, WeightsMissing

MODELS = os.path.expanduser("~/.paddlex/official_models")
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
PIPELINE_MODES = ("off", "post", "full")
_PIP_INSTALL = "the docling extra  (docling-slim==2.123.1 and rtree; no torch, +54 MB)"


class _DoclingPipeline:
    def __init__(self, mode: str, labels, adapter: str, pol=None):
        self._pol, self._labels = (pol, tuple(labels))
        if mode not in PIPELINE_MODES:
            raise Refusal(f"DOCLING_PIPELINE={mode!r}: I know only {PIPELINE_MODES}")
        self.mode = mode
        self.adapter = adapter
        try:
            import docling
            from docling.datamodel.base_models import Cluster, Page as DlPage
            from docling.datamodel.pipeline_options import BaseLayoutPostprocessorOptions
            from docling.utils.layout_postprocessor import LayoutPostprocessor
            from docling.models.postprocessing.reading_order_rb import (
                PageElement as RoElement,
                ReadingOrderPredictor,
            )
            from docling_core.types.doc import BoundingBox, DocItemLabel, Size
        except ImportError as e:
            raise Refusal(
                f"DOCLING_PIPELINE={mode}, and there is no docling package: {e}. Install: {_PIP_INSTALL}. Or DOCLING_PIPELINE=off -- then the adapter counts the model boxes as they are and the package is not needed at all."
            ) from None
        self._Cluster, self._DlPage = (Cluster, DlPage)
        self._BoundingBox, self._DocItemLabel, self._Size = (BoundingBox, DocItemLabel, Size)
        self._LayoutPostprocessor = LayoutPostprocessor
        self._RoElement = RoElement
        self._ro = ReadingOrderPredictor() if mode == "full" else None
        self.options = BaseLayoutPostprocessorOptions(skip_cell_assignment=True)
        known = {lab.value for lab in LayoutPostprocessor.CONFIDENCE_THRESHOLDS}
        self.to_docling = {lab: EGRET_TO_DOCLING.get(lab, lab) for lab in labels}
        bad = []
        for lab, name in self.to_docling.items():
            try:
                DocItemLabel(name)
            except ValueError:
                bad.append(f"{lab!r} (-> {name!r}: no such name in the docling vocabulary at all)")
                continue
            if name not in known:
                bad.append(
                    f"{lab!r} (-> {name!r}: the name is in the docling vocabulary, but the postprocessor has no threshold for it)"
                )
        if bad:
            raise Refusal(
                f"adapter {adapter}: labels {', '.join(bad)} are indigestible to the docling postprocessor. It knows {len(known)} classes -- those listed in LayoutPostprocessor.CONFIDENCE_THRESHOLDS -- and takes the threshold by label with NO default, so on any other it dies with KeyError on the very first page. The translation is declared BY NAME in EGRET_TO_DOCLING (layout/adapters/docling.py): a rule 'lower-case it' would silently accept a new class of new weights and slip it to the vendor under an invented name."
            )
        self.back = {v: k for k, v in self.to_docling.items() if v != k}
        self.files = {}
        for cls in (LayoutPostprocessor, ReadingOrderPredictor):
            path = sys.modules[cls.__module__].__file__
            self.files[os.path.basename(path)] = stamp.sha256(path)
        self.version = getattr(docling, "__version__", None)
        self.pages = self.before = self.after = self.kids = 0
        self.displaced = 0
        self.resorted = 0
        self.reordered = 0
        self.arte_in_text = 0
        self.arte_lost = 0

    ORDER_RULE = {
        "post": "ours_only_in_the_sense_that_the_model_gave_no_rank: the rule is FOREIGN -- the docling postprocessor resorted the boxes by (top, left), exact coordinates, not by our round(y/20) bands",
        "full": "ours_by_choice_rules_are_doclings_reading_order_rb: RULE-BASED, 740 lines of rules without a single weight, not a model",
    }

    @property
    def pol(self):
        if self._pol is None:
            self._pol = policy_mod.for_labels(self._labels)
        return self._pol

    def _label(self, raw):
        try:
            return self._DocItemLabel(self.to_docling[raw])
        except KeyError:
            raise RuntimeError(
                f"label {raw!r} is not from the {self.adapter} weights vocabulary: it has no translation into docling's. Declare it in EGRET_TO_DOCLING by name."
            ) from None

    def apply(self, blocks, width, height, index):
        clusters = [
            self._Cluster(
                id=b.block_id,
                label=self._label(b.label),
                bbox=self._BoundingBox(l=b.box[0], t=b.box[1], r=b.box[2], b=b.box[3]),
                confidence=b.score,
                cells=[],
                children=[],
            )
            for b in blocks
        ]
        resorted = None
        if self.mode in ("post", "full"):
            page = self._DlPage(page_no=index)
            page.size = self._Size(width=float(width), height=float(height))
            clusters = self._LayoutPostprocessor(page, clusters, self.options).postprocess()
            ids = [c.id for c in clusters]
            resorted = sum((1 for a, b in zip(ids, sorted(ids), strict=True) if a != b))
        moved = 0 if self.mode == "full" else None
        if self.mode == "full" and clusters:
            size = self._Size(width=float(width), height=float(height))
            els = []
            for i, c in enumerate(clusters):
                bb = c.bbox.to_bottom_left_origin(float(height))
                els.append(
                    self._RoElement(
                        cid=i,
                        text="",
                        page_no=index,
                        page_size=size,
                        label=c.label,
                        l=bb.l,
                        r=bb.r,
                        b=bb.b,
                        t=bb.t,
                        coord_origin=bb.coord_origin,
                    )
                )
            order = [e.cid for e in self._ro.predict_reading_order(els)]
            if sorted(order) != list(range(len(clusters))):
                raise RuntimeError(
                    f"the docling order rules returned no permutation on page {index}: there were {len(clusters)} boxes, {len(order)} numbers came back"
                )
            moved = sum((1 for i, j in enumerate(order) if i != j))
            clusters = [clusters[i] for i in order]
        final_ids = [c.id for c in clusters]
        displaced = sum((1 for a, b in zip(final_ids, sorted(final_ids), strict=True) if a != b))
        top = set(final_ids)
        out, kids, arte_in_text, arte_lost = ([], {}, 0, 0)
        for i, c in enumerate(clusters):
            lab = self.back.get(c.label.value, c.label.value)
            ch = [
                {
                    "id_before_pipeline": int(k.id),
                    "label": self.back.get(k.label.value, k.label.value),
                    "box": [k.bbox.l, k.bbox.t, k.bbox.r, k.bbox.b],
                }
                for k in c.children
            ]
            if ch:
                kids[i] = ch
                if self.pol.role(lab) == "text":
                    art = [k for k in ch if self.pol.role(k["label"]) == "artifact"]
                    arte_in_text += len(art)
                    arte_lost += sum(1 for k in art if k["id_before_pipeline"] not in top)
            out.append(
                Block(
                    block_id=i,
                    box=(c.bbox.l, c.bbox.t, c.bbox.r, c.bbox.b),
                    label=lab,
                    score=c.confidence,
                    order=i,
                )
            )
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
            "boxes_reordered": displaced,
            "reordered_by_postprocessor_sort": resorted,
            "reordered_by_order_rules": moved,
            "children_by_box_index": kids,
            "artifact_boxes_in_text_wrappers": arte_in_text,
            "of_those_lost_from_top_level": arte_lost,
        }
        return (out, meta)

    def fingerprint(self):
        return {
            "mode": self.mode,
            "what_is_it": "VENDOR code, called as it is, without one edit of ours inside; reading_order_rb is rule-based, 740 lines of rules over boxes, not a single weight",
            "classes": ["docling.utils.layout_postprocessor.LayoutPostprocessor"]
            + (
                ["docling.models.postprocessing.reading_order_rb.ReadingOrderPredictor"]
                if self.mode == "full"
                else []
            ),
            "docling_version": self.version,
            "sha256_vendor_files": self.files,
            "postprocess_options": self.options.model_dump(mode="json"),
            "label_map_to_docling": self.to_docling,
            "label_outward": "in the adapter's spelling",
            "summary": {
                "page_count": self.pages,
                "boxes_before": self.before,
                "boxes_after": self.after,
                "moved_to_children": self.kids,
                "boxes_reordered": self.displaced,
                "reordered_by_postprocessor_sort": self.resorted,
                "reordered_by_order_rules": self.reordered if self.mode == "full" else None,
                "artifact_boxes_in_text_wrappers": self.arte_in_text,
                "of_those_lost_from_top_level": self.arte_lost,
            },
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
        missing = [p for p in (self.onnx, cfg_path, pre_path) if not os.path.exists(p)]
        if missing:
            raise WeightsMissing(
                f"no docling heron weights: {missing}. Download three files from huggingface.co/docling-project/docling-layout-heron-onnx into {self.dir}"
            )
        with open(cfg_path, encoding="utf-8") as f:
            cfg = json.load(f)
        i2l = cfg.get("id2label") or {}
        self.labels = [i2l[str(i)] for i in range(len(i2l))] if i2l else list(DEFAULT_LABELS)
        self.pipeline = knobs.knob("DOCLING_PIPELINE")
        self._pipe = (
            None
            if self.pipeline == "off"
            else _DoclingPipeline(self.pipeline, self.labels, self.name, self.policy())
        )
        with open(pre_path, encoding="utf-8") as f:
            pre = json.load(f)
        size = pre.get("size") or {}
        self.target_h = int(size.get("height", 640))
        self.target_w = int(size.get("width", 640))
        pil = int(pre.get("resample", 2))
        PIL_TO_CV2 = {0: 0, 1: 4, 2: 1, 3: 2, 4: 3, 5: 3}
        if pil not in PIL_TO_CV2:
            raise WeightsMissing(
                f"unknown filter code resample={pil} in the preprocessor: substituting our own would shrink the page with the wrong filter."
            )
        self.interp_pil = pil
        self.interp = PIL_TO_CV2[pil]
        self.do_pad = bool(pre.get("do_pad", False))
        if self.do_pad:
            raise WeightsMissing(
                "the preprocessor says do_pad: true, and we shrink the raster with no padding -- the boxes would come out shifted and plausible at once."
            )
        self.do_rescale = bool(pre.get("do_rescale", False))
        self.do_normalize = bool(pre.get("do_normalize", False))
        self.sess = ort.InferenceSession(self.onnx, providers=["CPUExecutionProvider"])
        self.ort_version = ort.__version__
        self.providers = list(self.sess.get_providers())
        kinds = {i.name: i.type for i in self.sess.get_inputs()}
        self.uint8_input = "uint8" in kinds.get("images", "")

    def _our_order(self, kept, w, h, index):
        if self._pipe is not None:
            kept.sort(key=lambda t: (round(t[2][1] / 20), t[2][0]))
            return kept
        which = order.rule()
        pol = self.policy() if which == "docling" else None
        order.cover(pol, which)
        perm = order.permutation([t[0] for t in kept], [t[2] for t in kept], w, h, index, pol, which)
        return [kept[i] for i in perm]

    def _run_pipeline(self, blocks, w, h, index):
        if self._pipe is None:
            return (blocks, {"reading_order": declare_order("ours", order.WORDS[order.rule()])})
        blocks, m = self._pipe.apply(blocks, w, h, index)
        pp = self._pipe
        if pp.pages == 1 or pp.pages % 10 == 0:
            log(
                f"  [docling pipeline {pp.mode}] {pp.pages} pp.: boxes {pp.before} -> {pp.after}, into children {pp.kids} (of those, artefacts in text wrappers {pp.arte_in_text}, lost {pp.arte_lost}), out of place {pp.displaced} (the sort moved {pp.resorted}, the rules permuted "
                + (str(pp.reordered) if pp.mode == "full" else "-- (never called)")
                + ")"
            )
        return (
            blocks,
            {
                "reading_order": declare_order("ours", _DoclingPipeline.ORDER_RULE[pp.mode]),
                "docling_pipeline": m,
            },
        )

    def thresholds(self) -> dict[str, float]:
        common = knobs.number("LAYOUT_SCORE_THRESHOLD")
        return {lab: common for lab in self.labels}

    def threshold_drift(self) -> list[str]:
        return [
            f"the weights have no native threshold; acting is LAYOUT_SCORE_THRESHOLD={knobs.knob('LAYOUT_SCORE_THRESHOLD')} on all {len(self.labels)} classes"
        ]

    def knobs_read(self) -> tuple[str, ...]:
        return ("LAYOUT_SCORE_THRESHOLD", "DOCLING_PIPELINE", "ASSEMBLY_ORDER")

    def label_map(self) -> dict[str, str]:
        return {}

    def label(self) -> str:
        return book.safe_label(self.name, "the docling variant")

    def fingerprint(self) -> dict:
        if self._pipe is not None and self._pipe.pages:
            it = self._pipe.fingerprint()["summary"]
            share = 100.0 * it["boxes_after"] / it["boxes_before"] if it["boxes_before"] else 0.0
            rules = str(it["reordered_by_order_rules"]) if self._pipe.mode == "full" else "-- (never called)"
            order = (
                "VENDOR RULES (reading_order_rb, not a model)"
                if self._pipe.mode == "full"
                else "resorted by the docling postprocessor by (top, left), there is no model rank"
            )
            log(
                f"docling pipeline {self._pipe.mode}: pages {it['page_count']}, boxes {it['boxes_before']} -> {it['boxes_after']} ({share:.1f}%), into children {it['moved_to_children']}, of those artefacts in text wrappers {it['artifact_boxes_in_text_wrappers']} (lost from the top list {it['of_those_lost_from_top_level']}); out of place against our order {it['boxes_reordered']} (the postprocessor sort moved {it['reordered_by_postprocessor_sort']}, the rules permuted {rules}); reading order {order}"
            )
        return {
            "name": self.name,
            "model": getattr(self, "full_name", "docling-layout-heron (RT-DETRv2 R50)"),
            "architecture": getattr(self, "architecture", "RT-DETRv2 R50"),
            "weights_dir": self.dir,
            "sha256_weights": stamp.sha256(self.onnx),
            "onnxruntime": self.ort_version,
            "providers": self.providers,
            "input": {
                "height": self.target_h,
                "width": self.target_w,
                "pil_filter": self.interp_pil,
                "cv2_filter": self.interp,
                "padding": self.do_pad,
                "input_uint8": self.uint8_input,
                "divide_by_255": self.do_rescale,
                "normalization": self.do_normalize,
            },
            "native_threshold": None,
            "thresholds_by_class": self.thresholds(),
            "threshold_drift": self.threshold_drift(),
            "label_vocabulary": self.labels,
            "label_map": self.label_map(),
            "prompts": {},
            "reading_order": declare_order("none"),
            "docling_pipeline": self._pipe.fingerprint()
            if self._pipe
            else {
                "mode": "off",
                "what_is_it": "the vendor postprocessing and docling's reading-order rules; switched off -- the model boxes go as they are, the order is ours",
                "docling_version": None,
                "sha256_vendor_files": {},
                "postprocess_options": None,
                "label_map_to_docling": {},
                "summary": None,
            },
        }

    def read(self, image_path: str, index: int, dpi: float) -> Page:
        import cv2
        import numpy as np

        img = cv2.imread(image_path)
        if img is None:
            raise RuntimeError(f"the page raster does not read: {image_path}")
        h, w = img.shape[:2]
        rz = cv2.resize(img, (self.target_w, self.target_h), interpolation=self.interp)
        x = rz[:, :, ::-1]
        if self.uint8_input:
            x = np.ascontiguousarray(x.transpose(2, 0, 1)[None].astype(np.uint8))
        else:
            x = x.astype(np.float32)
            if self.do_rescale:
                x /= 255.0
            x = np.ascontiguousarray(x.transpose(2, 0, 1)[None])
        labels, boxes, scores = self.sess.run(
            None, {"images": x, "orig_target_sizes": np.array([[w, h]], np.int64)}
        )
        labels, boxes, scores = (labels[0], boxes[0], scores[0])
        thr = self.thresholds()
        kept, rejected = ([], {})
        for cid, box, sc in zip(labels, boxes, scores, strict=True):
            cid, sc = (int(cid), float(sc))
            if not 0 <= cid < len(self.labels):
                raise RuntimeError(
                    f"the model returned class {cid}, the vocabulary knows {len(self.labels)}: an invented label is worse than a refusal."
                )
            lab = self.labels[cid]
            if sc < thr[lab]:
                if sc > rejected.get(lab, 0.0):
                    rejected[lab] = sc
                continue
            kept.append((lab, sc, [float(v) for v in box]))
        kept = self._our_order(kept, w, h, index)
        blocks = [
            Block(block_id=i, box=tuple(b), label=lab, score=sc, order=i)
            for i, (lab, sc, b) in enumerate(kept)
        ]
        blocks, pipe_meta = self._run_pipeline(blocks, w, h, index)
        return Page(
            index=index,
            width=w,
            height=h,
            dpi=dpi,
            blocks=blocks,
            raw={
                "output_rows": int(len(scores)),
                "all_rows": [
                    [float(c), float(s), *[float(v) for v in b]]
                    for c, b, s in zip(labels, boxes, scores, strict=True)
                ],
            },
            meta={
                "detector": self.name,
                "boxes_accepted": len(kept),
                "rank_ties": 0,
                **pipe_meta,
                "best_rejected_by_class": rejected,
            },
        )


DEFAULT_LABELS = (
    "caption",
    "footnote",
    "formula",
    "list_item",
    "page_footer",
    "page_header",
    "picture",
    "section_header",
    "table",
    "text",
    "title",
    "document_index",
    "code",
    "checkbox_selected",
    "checkbox_unselected",
    "form",
    "key_value_region",
)


class DoclingEgret(DoclingHeron):
    name = "docling-egret"
    policy_name = "Docling-egret"
    architecture = "D-FINE"

    def __init__(self, model_dir: str | None = None):
        self.full_name = "docling-layout-egret-medium (D-FINE)"
        super().__init__(model_dir or os.path.join(MODELS, "docling-egret_onnx"))
        names = [i.name for i in self.sess.get_inputs()]
        if names != ["pixel_values"]:
            raise WeightsMissing(
                f"graph input {names}, ['pixel_values'] was expected: parsing at random means feeding the model the wrong thing."
            )

    def read(self, image_path: str, index: int, dpi: float) -> Page:
        import cv2
        import numpy as np

        img = cv2.imread(image_path)
        if img is None:
            raise RuntimeError(f"the page raster does not read: {image_path}")
        h, w = img.shape[:2]
        rz = cv2.resize(img, (self.target_w, self.target_h), interpolation=self.interp)
        x = rz[:, :, ::-1].astype(np.float32)
        if self.do_rescale:
            x /= 255.0
        x = np.ascontiguousarray(x.transpose(2, 0, 1)[None])
        logits, boxes = self.sess.run(None, {"pixel_values": x})
        logits, boxes = (logits[0], boxes[0])
        prob = 1.0 / (1.0 + np.exp(-logits))
        nq, nc = prob.shape
        if nc != len(self.labels):
            raise RuntimeError(
                f"the graph gave {nc} classes, the vocabulary knows {len(self.labels)}: an invented label is worse than a refusal."
            )
        flat = prob.reshape(-1)
        top = np.argsort(-flat, kind="stable")[:nq]
        thr = self.thresholds()
        thr_row = np.array([thr[lab] for lab in self.labels], np.float32)
        inside = np.zeros(nq * nc, bool)
        inside[top] = True
        cut = int(((prob >= thr_row[None, :]).reshape(-1) & ~inside).sum())
        kept, rejected = ([], {})
        for idx in top:
            q, cid = (int(idx) // nc, int(idx) % nc)
            s = float(flat[idx])
            lab = self.labels[cid]
            if s < thr[lab]:
                if s > rejected.get(lab, 0.0):
                    rejected[lab] = s
                continue
            cx, cy, bw, bh = (float(v) for v in boxes[q])
            kept.append(
                (
                    lab,
                    s,
                    [(cx - bw / 2) * w, (cy - bh / 2) * h, (cx + bw / 2) * w, (cy + bh / 2) * h],
                )
            )
        kept = self._our_order(kept, w, h, index)
        blocks = [
            Block(block_id=i, box=tuple(b), label=lab, score=s, order=i) for i, (lab, s, b) in enumerate(kept)
        ]
        geom = [tuple(b) for _, _, b in kept]
        blocks, pipe_meta = self._run_pipeline(blocks, w, h, index)
        return Page(
            index=index,
            width=w,
            height=h,
            dpi=dpi,
            blocks=blocks,
            raw={
                "output_rows": int(nq),
                "class_count": int(nc),
                "logits": [[float(v) for v in r] for r in logits],
                "boxes": [[float(v) for v in r] for r in boxes],
                "how_to_read_logits": "sigmoid per channel (focal loss)",
                "raw_row_coords": "cxcywh, normalised",
            },
            meta={
                "detector": self.name,
                "boxes_accepted": len(kept),
                "rank_ties": 0,
                **pipe_meta,
                "selection_rule": f"topk {nq} over the flattened Q*C, label = i % {nc} (as in D-FINE/RT-DETR)",
                "extra_labels_on_shared_boxes": len(geom) - len(set(geom)),
                "rows_above_threshold_outside_topk": cut,
                "best_rejected_by_class": rejected,
            },
        )
