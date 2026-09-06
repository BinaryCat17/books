"""PaddleOCR-VL 1.6 as a READER: which prompt on which label, and what kind
of answer comes back.

Not one request and not one address here -- that belongs to the MODEL, not to
delivery (the seam is in `read/__init__.py`). The file is declarations
throughout, each taken from the model card or paid for by a measurement;
guesses have no place in it.

THE PROMPTS ARE THE VENDOR'S, BYTE FOR BYTE. The model card and the vLLM
recipe name six tasks by the same strings:

    "OCR:"  "Table Recognition:"  "Formula Recognition:"
    "Chart Recognition:"  "Spotting:"  "Seal Recognition:"

Five of the six are declared below; `Spotting:` we never ask.

No system message, temperature 0. The prompt is ALL there is to steer the
answer with -- nothing asks for "such-and-such a format" -- so the kind of
content is decided by the choice of task, not by a request.

WHY THE ROUTES ARE NAMED ONE BY ONE AND NOT DERIVED FROM THE ROLE. The role
(`policy.role`) answers "cut out or print", not "what to ask":
`display_formula` and `table` are both `artifact`, while their prompts and
answer kinds differ. The vocabulary is besides OWN to every detector -- 25
names for PP-DocLayoutV2, 20 for plus-L, 17 each for both docling models, 11
for DocLayNet -- and "what I do not know I ask as text" would silently lead
the twenty-sixth class of new weights by the wrong prompt. `Reader.cover()`
fells the run on an unknown label BEFORE the first cent.

WHAT WE DO NOT ASK, AND THAT IS A MEASUREMENT, NOT CAUTION. `image`,
`header_image`, `footer_image` -- reading text inside figures was TRIED AND
REJECTED (`docs/ocr-notes.md`): the callouts `A` and `B` unread, a digit `1`
in their place; on two pages the schoolbook pangram `The quick brown fox…`,
invented whole from a line drawing; on a third a loop `1.` `2.` … `100.`;
+2100 words of rubbish over twenty
pages in all. A line drawing is noise to this model, and it cannot keep
silent.

WHAT IS DECLARED CAUTIOUSLY AND AWAITS A MEASUREMENT. `chart` and `seal` carry
the vendor's prompts, but the KIND of their answer we have never measured.
`text` is declared, the most cautious of the four: `books text` compares it BY
CHARACTERS and the book shows it escaped, so an error of declaration
underrates the model without spoiling the book with an invented
table. Beside the answer always lies a GUESS at the kind (`read/run.py`
sniffs it into `observed.kind_sniffed`), and its divergence from the declared
is a named counter: the first run says by number whether `text` should become
`otsl`. Changing it by guess, without asking the bench, is repairing the
model, and there is none of that here.
"""
import hashlib
import os

from ...read import Reader, Route
from ...run import knobs

# Byte for byte from the model card. The colon and the space are significant.
OCR = "OCR:"
TABLE = "Table Recognition:"
FORMULA = "Formula Recognition:"
CHART = "Chart Recognition:"
SEAL = "Seal Recognition:"

# ONE reason, shared by every silent label of every vocabulary -- three of
# them under PP-DocLayoutV2, one under each of the other four.
NO_PICTURE = ("reading inside figures was tried and rejected: callouts "
              "unread, an invented pangram on two pages, a runaway loop on a "
              "third, +2100 words of garbage over twenty pages")

# Routes by the DETECTOR'S VOCABULARY. The top-level key is the policy name,
# exactly as in `policy.POLICIES`: two dictionaries would drift apart, and
# that has happened here already (the knob registry against the job builder,
# 13 names of 17).
_TEXT_V2 = ("abstract", "algorithm", "aside_text", "content", "doc_title",
            "figure_title", "footer", "footnote", "formula_number", "header",
            "number", "paragraph_title", "reference", "reference_content",
            "text", "vertical_text", "vision_footnote")
_TEXT_PLUS = ("abstract", "algorithm", "aside_text", "content", "doc_title",
              "figure_title", "footer", "footnote", "formula_number",
              "header", "number", "paragraph_title", "reference",
              "reference_content", "text")
_TEXT_DOCLING = ("caption", "checkbox_selected", "checkbox_unselected",
                 "document_index", "footnote", "form", "key_value_region",
                 "list_item", "page_footer", "page_header", "section_header",
                 "text", "title")
_TEXT_EGRET = ("Caption", "Checkbox-Selected", "Checkbox-Unselected",
               "Document Index", "Footnote", "Form", "Key-Value Region",
               "List-item", "Page-footer", "Page-header", "Section-header",
               "Text", "Title")
_TEXT_DOCLAYNET = ("Caption", "Footnote", "List-item", "Page-footer",
                   "Page-header", "Section-header", "Text", "Title")


def _routes(text_labels, table, formula, picture, extra=()):
    r = {lab: Route(OCR, "text") for lab in text_labels}
    for lab in table:
        r[lab] = Route(TABLE, "otsl")
    for lab in formula:
        r[lab] = Route(FORMULA, "latex")
    for lab in picture:
        r[lab] = Route("", why=NO_PICTURE)
    r.update(extra)
    return r


ROUTES = {
    "PP-DocLayoutV2": _routes(
        _TEXT_V2, ("table",), ("display_formula", "inline_formula"),
        ("image", "header_image", "footer_image"),
        extra={"chart": Route(CHART, "text"), "seal": Route(SEAL, "text")}),
    "PP-DocLayout_plus-L": _routes(
        _TEXT_PLUS, ("table",), ("formula",),
        ("image",),
        extra={"chart": Route(CHART, "text"), "seal": Route(SEAL, "text")}),
    "Docling": _routes(
        _TEXT_DOCLING, ("table",), ("formula",), ("picture",),
        # `code` in docling is a program listing. The model has no "Code
        # Recognition:" prompt; we ask as text, because a listing IS
        # characters, and `text` here is not caution but the substance.
        extra={"code": Route(OCR, "text")}),
    "Docling-egret": _routes(
        _TEXT_EGRET, ("Table",), ("Formula",), ("Picture",),
        extra={"Code": Route(OCR, "text")}),
    "DocLayNet": _routes(
        _TEXT_DOCLAYNET, ("Table",), ("Formula",), ("Picture",)),
}


def _weights() -> dict:
    """What weights lie under the model. Declared emptiness, not silence.

    What the field is for: a server's NAME proves nothing about the weights
    under it, and this fingerprint is the only thing that does (`read/http.py`
    says so at `check`). The measurement it is written from: `provision.sh`
    pulled `PaddlePaddle/PaddleOCR-VL` while `MODEL_NAME` declared
    `PaddleOCR-VL-1.6-0.9B` -- DIFFERENT weights, the 1.6 repository being
    separate -- and the run would have come out successful and wrong, the
    snapshot naming a version it never counted with.

    At home there are no weights at all, and then a reason stands here, not a
    `null`.
    """
    d = knobs.knob("VL_MODEL_DIR")
    if not d or not os.path.isdir(d):
        return {"dir": d or None,
                "why_empty": "no weights here: the counting is done not by "
                                "this machine but by the one VLM_ENDPOINT "
                                "points at"}
    out = {"dir": d, "file_count": len(os.listdir(d))}
    # WHERE THE WEIGHTS CAME FROM is the main field, and `provision.sh` writes
    # it beside them. Here stood only `sha256 config.json`, called the sole
    # proof of the version. A measurement refuted that: for `PaddleOCR-VL-1.6`
    # and for the old `PaddleOCR-VL` that file MATCHES BYTE FOR BYTE -- 2059
    # bytes, sha256 ce7f4565f8b1db78… -- so the guard missed exactly the run
    # it was written for ("we pull one, we declare another"), catching only
    # "no weights at all".
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
    # We hash the file that DIFFERS between the two repositories, not the one
    # that matches. `config.json` is kept beside it as a second number: it is
    # about the architecture, and its matching is itself a quantity.
    for name in ("tokenizer_config.json", "config.json"):
        f = os.path.join(d, name)
        out["sha256 " + name] = (
            hashlib.sha256(open(f, "rb").read()).hexdigest()
            if os.path.exists(f) else None)
    return out


class PaddleOcrVl(Reader):
    """The PaddleOCR-VL reader. Knows the prompts and the kinds, no more."""

    name = "paddleocr-vl"

    def __init__(self, policy_name: str = "PP-DocLayoutV2"):
        if policy_name not in ROUTES:
            raise SystemExit(
                f"no routes for the label vocabulary {policy_name!r}: I know "
                f"{sorted(ROUTES)}. Asking by a foreign vocabulary means "
                f"driving a table with the text prompt and recording prose as "
                f"the reading.")
        self.policy_name = policy_name

    def fingerprint(self) -> dict:
        r = self.routes()
        return {"reader": self.name,
                "model": knobs.knob("MODEL_NAME"),
                "label_vocabulary": self.policy_name,
                "weights": _weights(),
                # The prompts ride into the snapshot WHOLE, not as a number:
                # this is what fills the `prompts` field of the snapshot
                # registry (`run/replay.py`), empty on every run before this
                # reader. The prompt is the only thing that steers the answer
                # here, and not to record it is not to record the run.
                "prompts": {lab: rt.prompt for lab, rt in sorted(r.items())
                           if rt.asked()},
                "never_asked": {lab: rt.why for lab, rt in sorted(r.items())
                                  if not rt.asked()},
                "kinds": {lab: rt.kind for lab, rt in sorted(r.items())
                         if rt.asked()}}

    def knobs_read(self) -> tuple[str, ...]:
        return ("MODEL_NAME", "VL_MODEL_DIR")

    def routes(self) -> dict[str, Route]:
        return dict(ROUTES[self.policy_name])

    def pixels(self) -> tuple[int, int]:
        """The crop window declared by the model itself. Not our numbers.

        `min_pixels` = 112 896 and `max_pixels` = 1280 * 28 * 28 = 1 003 520,
        from the PaddleOCR-VL card. Below the lower its processor stretches
        the crop by interpolation (measured earlier: a table crop at 144 dpi
        came out 375 x 66 = 24 750 px, four times under, and was stretched);
        above the upper it shrinks.
        """
        return (112896, 1280 * 28 * 28)
