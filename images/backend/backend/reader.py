"""PaddleOCR-VL 1.6 as a reader: which prompt on which label, and what kind of"""

from backend.read import Reader, Route
from backend import store as book
from backend import knobs
from backend import classes as policy_mod

OCR = "OCR:"
TABLE = "Table Recognition:"
FORMULA = "Formula Recognition:"
CHART = "Chart Recognition:"
SEAL = "Seal Recognition:"
NO_PICTURE = "reading inside figures was tried and rejected: callouts unread, an invented pangram on two pages, a runaway loop on a third, +2100 words of garbage over twenty pages"
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
    return {"sha256_weights": None, "why_empty": "served: the model's describe carries the weights hash"}


class PaddleOcrVl(Reader):
    name = "paddleocr-vl"

    def __init__(self, policy: policy_mod.Policy):
        self.policy = policy
        self.policy_name = policy.name

    def label(self) -> str:
        return book.safe_label(knobs.knob("MODEL_NAME"), "MODEL_NAME")

    def fingerprint(self) -> dict:
        r = self.routes()
        return {
            "reader": self.name,
            "model": knobs.knob("MODEL_NAME"),
            "label_vocabulary": self.policy_name,
            "weights": _weights(),
            "prompts": {lab: rt.prompt for lab, rt in sorted(r.items()) if rt.asked()},
            "never_asked": {lab: rt.why for lab, rt in sorted(r.items()) if not rt.asked()},
            "kinds": {lab: rt.kind for lab, rt in sorted(r.items()) if rt.asked()},
        }

    def knobs_read(self) -> tuple[str, ...]:
        return ("MODEL_NAME",)

    def routes(self) -> dict[str, Route]:
        return {lab: ROUTES[self.policy.cls(lab)] for lab in self.policy.labels}

    def pixels(self) -> tuple[int, int]:
        return (112896, 1280 * 28 * 28)
