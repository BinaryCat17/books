"""PaddleOCR-VL 1.6 as a reader: which prompt on which label, and what kind of
answer comes back. No request and no address here -- delivery is the transport's
side of the seam in `read/__init__.py`.

The prompts are the vendor's, byte for byte: five of the model card's six tasks
are declared below, `Spotting:` is never asked. No system message, temperature 0
-- the prompt is all there is to steer the answer with, so the kind of content
follows from the choice of task, and the routes are named one by one rather than
derived from the role, each detector's label vocabulary being its own.
"""

# A table box on a page fragment can be suppressed inside the vendor pipeline --
# cross-class suppression (`object_detection/processors.py`, iou_diff), nesting
# (`layout_analysis/processors.py`, layout_merge_bboxes_mode "large"), overlap
# filtering (`paddleocr_vl/uilts.py`, filter_overlap_boxes) -- and none of the
# three may be patched at our end.
import hashlib
import os

from booksmith.processing.read import Reader, Route
from booksmith.core import book
from booksmith.core import knobs
from booksmith.core import policy as policy_mod

# Byte for byte from the model card. The colon and the space are significant.
OCR = "OCR:"
TABLE = "Table Recognition:"
FORMULA = "Formula Recognition:"
CHART = "Chart Recognition:"
SEAL = "Seal Recognition:"

# One reason, shared by every silent label of every vocabulary.
NO_PICTURE = ("reading inside figures was tried and rejected: callouts "
              "unread, an invented pangram on two pages, a runaway loop on a "
              "third, +2100 words of garbage over twenty pages")

# Routes by CLASS, the tree's declaration in `core/policy.py`: a model maps
# its labels onto the classes, and the reader knows what to ask of each
# class. `chart` and `seal` are asked with the vendor's prompts and declared
# `text`, the cautious kind: `books text` compares by characters, so a wrong
# declaration underrates the model rather than putting an invented table in
# the book. `code` and `algorithm` are program listings, and the model has no
# "Code Recognition:" prompt; a listing is characters, so `text` is exact.
ROUTES = {
    "text": Route(OCR, "text"),
    "caption": Route(OCR, "text"),
    "algorithm": Route(OCR, "text"),
    "code": Route(OCR, "text"),
    "page_header": Route(OCR, "text"),
    "page_footer": Route(OCR, "text"),
    "footnote": Route(OCR, "text"),
    "inline_formula": Route(FORMULA, "latex"),
    "display_formula": Route(FORMULA, "latex"),
    "table": Route(TABLE, "otsl"),
    "chart": Route(CHART, "text"),
    "seal": Route(SEAL, "text"),
    "picture": Route("", why=NO_PICTURE),
    "header_image": Route("", why=NO_PICTURE),
    "footer_image": Route("", why=NO_PICTURE),
}


def _weights() -> dict:
    """What weights lie under the model. Declared emptiness, not silence.

    A server's name proves nothing about the weights under it, and this field is
    the only thing that does. Where there are no weights on this machine a
    reason stands here, never a `null`.
    """
    d = knobs.knob("VL_MODEL_DIR")
    if not d or not os.path.isdir(d):
        return {"dir": d or None,
                "why_empty": "no weights here: the counting is done not by "
                                "this machine but by the one VLM_ENDPOINT "
                                "points at"}
    out = {"dir": d, "file_count": len(os.listdir(d))}
    # Where the weights came from is the main field, and `provision.sh` writes
    # it beside them: `config.json` matches byte for byte between the 1.6
    # repository and the old one, so it cannot tell them apart.
    src = os.path.join(d, "SOURCE.json")
    if os.path.exists(src):
        try:
            import json as _j
            out["repo"] = _j.load(open(src, encoding="utf-8")).get(
                "repo")
        except (ValueError, OSError) as e:
            out["repo"] = None
            out["why_empty"] = f"SOURCE.json does not read: {e}"
    else:
        out["repo"] = None
        out["why_empty"] = ("no SOURCE.json beside the weights -- "
                               "provision.sh writes it, so the weights were "
                               "not put here by it, and there is nothing to "
                               "say about which they are")
    # Hash the file that differs between the two repositories; `config.json`
    # stands beside it as a second number, about the architecture.
    for name in ("tokenizer_config.json", "config.json"):
        f = os.path.join(d, name)
        out["sha256 " + name] = (
            hashlib.sha256(open(f, "rb").read()).hexdigest()
            if os.path.exists(f) else None)
    return out


class PaddleOcrVl(Reader):
    """The PaddleOCR-VL reader. Knows the prompts and the kinds, no more."""

    name = "paddleocr-vl"

    def __init__(self, policy: policy_mod.Policy):
        """`policy` is the detector's: its labels onto the classes, and the
        routes follow the classes. A label with no class has no route, and
        `cover` says so before the first cent."""
        self.policy = policy
        self.policy_name = policy.name

    def label(self) -> str:
        """`MODEL_NAME`: the model asked for. See `Reader.label`."""
        return book.safe_label(knobs.knob("MODEL_NAME"), "MODEL_NAME")

    def fingerprint(self) -> dict:
        r = self.routes()
        return {"reader": self.name,
                "model": knobs.knob("MODEL_NAME"),
                "label_vocabulary": self.policy_name,
                # The mapping the routes follow, whole: two runs over one
                # vocabulary name with different mappings are two experiments.
                "classes": {lab: self.policy.classes[lab]
                            for lab in self.policy.labels},
                "weights": _weights(),
                # The prompts ride into the snapshot whole: the prompt is the
                # only thing steering the answer, and not to record it is not
                # to record the run.
                "prompts": {lab: rt.prompt for lab, rt in sorted(r.items())
                           if rt.asked()},
                "never_asked": {lab: rt.why for lab, rt in sorted(r.items())
                                  if not rt.asked()},
                "kinds": {lab: rt.kind for lab, rt in sorted(r.items())
                         if rt.asked()}}

    def knobs_read(self) -> tuple[str, ...]:
        return ("MODEL_NAME", "VL_MODEL_DIR")

    def routes(self) -> dict[str, Route]:
        return {lab: ROUTES[self.policy.cls(lab)] for lab in self.policy.labels}

    def pixels(self) -> tuple[int, int]:
        """The crop window declared by the model itself. Not our numbers.

        `min_pixels` 112 896 and `max_pixels` 1280 * 28 * 28, from the
        PaddleOCR-VL card: below the lower bound its processor stretches the
        crop by interpolation, above the upper one it shrinks it.
        """
        return (112896, 1280 * 28 * 28)
