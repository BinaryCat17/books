"""A layout or hybrid model behind an endpoint, reached by the model protocol"""

from __future__ import annotations
from backend import store as book
from backend import job
from backend import knobs
from backend import protocol as served
from backend import classes as policy_mod
from backend.errors import Refusal
from backend.page import KINDS, Page
from backend.detector import Detector

TIMEOUT_S = 600.0


class Served(Detector):
    name = "served"

    def __init__(self) -> None:
        self.endpoint = served.root_of(knobs.knob("LAYOUT_ENDPOINT"))
        if not self.endpoint:
            raise Refusal(
                "LAYOUT_ENDPOINT is empty: no model address was given. There is no default on purpose -- a silent localhost would make the run knock at nothing and call that the model's silence."
            )
        self.headers = served.bearer(str(job.current().secrets.get("LAYOUT_API_KEY") or ""))
        try:
            answer = served.fetch(
                self.endpoint + served.DESCRIBE, timeout=TIMEOUT_S, headers=self.headers
            )
        except served.Unreachable as e:
            raise Refusal(
                f"{self.endpoint} does not describe itself: {e.why}. A model that cannot say what it is cannot be filed under a label, so nothing is asked of it."
            ) from None
        self.describe = served.Describe.from_json(answer)
        if self.describe.kind == "reader":
            raise Refusal(
                f"{self.endpoint} is a reader ({self.describe.label}); a layout run needs a layout or hybrid model. Point VLM_ENDPOINT at it and run `books read` instead."
            )
        missing = [k for k in self.FINGERPRINT_REQUIRED if k not in self.describe.fingerprint]
        if missing:
            raise Refusal(
                f"{self.describe.label}: the fingerprint lacks {missing}, which the snapshot indexes and the identity stands on."
            )
        self.labels: tuple[str, ...] = tuple(self.describe.labels)
        self._known = set(self.labels)
        self._policy = self.describe.policy()
        self.policy_name = self.describe.vocabulary

    def where(self) -> str:
        return self.endpoint

    def policy(self) -> policy_mod.Policy:
        return self._policy

    def served(self) -> dict | None:
        return self.describe.to_json()

    def label(self) -> str:
        return book.safe_label(self.describe.label, "the served model")

    def fingerprint(self) -> dict:
        return served.fingerprint_of(self.describe)

    def knobs_read(self) -> tuple[str, ...]:
        return ("LAYOUT_ENDPOINT",)

    def label_map(self) -> dict[str, str]:
        m = self.describe.fingerprint.get("label_map")
        return dict(m) if isinstance(m, dict) else {}

    def threshold_drift(self) -> tuple[str, ...]:
        lines = self.describe.fingerprint.get("threshold_drift") or ()
        return tuple(str(x) for x in lines)

    def read(self, image_path: str, index: int, dpi: float) -> Page:
        uri, _ = served.data_uri(image_path)
        sent = served.png_size(image_path)
        req = served.LayoutRequest(index=index, dpi=dpi, image=uri)
        try:
            answer = served.fetch(
                self.endpoint + served.LAYOUT,
                req.to_json(),
                timeout=TIMEOUT_S,
                headers=self.headers,
            )
        except served.Unreachable as e:
            raise Refusal(
                f"page {index}: {self.describe.label} at {self.endpoint} did not answer the layout route: {e.why}. Not repeated: a second ask would be a second experiment."
            ) from None
        try:
            page = Page.from_json(answer if isinstance(answer, dict) else {})
        except (KeyError, TypeError, ValueError) as e:
            raise Refusal(
                f"page {index}: {self.describe.label} answered something that is not a page ({type(e).__name__}: {e})"
            ) from None
        if page.index != index:
            raise Refusal(
                f"page {index}: {self.describe.label} answered for page {page.index}; the answer would be filed under the wrong sheet"
            )
        lacking = [k for k in self.PAGE_META_REQUIRED if k not in page.meta]
        if lacking:
            raise Refusal(
                f"page {index}: the answer's meta lacks {lacking}, which the detect loop indexes on every page"
            )
        if float(page.dpi) != float(dpi):
            raise Refusal(
                f"page {index}: {self.describe.label} answered at dpi {page.dpi}, and the raster was sent at {dpi}"
            )
        if sent is not None and (page.width, page.height) != sent:
            raise Refusal(
                f"page {index}: {self.describe.label} answered a sheet of {page.width}x{page.height}, and the raster sent was {sent[0]}x{sent[1]}"
            )
        foreign_labels = sorted({b.label for b in page.blocks if b.label not in self._known})
        if foreign_labels:
            raise Refusal(
                f"page {index}: {self.describe.label} returned labels {foreign_labels[:5]} it did not declare in its describe; a label outside the declared vocabulary has no role"
            )
        if self.describe.kind == "layout":
            spoken = [b.block_id for b in page.blocks if b.content is not None or b.kind != "none"]
            if spoken:
                raise Refusal(
                    f"page {index}: {self.describe.label} said it is a layout model and returned content on blocks {spoken[:5]}. Text from a model that declared none is filed nowhere; declare the model a hybrid."
                )
        else:
            bad = sorted({b.kind for b in page.blocks if b.kind not in KINDS + ("none",)})
            if bad:
                raise Refusal(
                    f"page {index}: blocks carry kinds {bad}, and a block's kind is one of {KINDS} or none"
                )
            foreign = sorted(
                {
                    b.kind
                    for b in page.blocks
                    if b.kind != "none" and b.kind not in self.describe.kinds
                }
            )
            if foreign:
                raise Refusal(
                    f"page {index}: {self.describe.label} declared kinds {list(self.describe.kinds)} and returned {foreign}"
                )
            mute = [b.block_id for b in page.blocks if b.content is not None and b.kind == "none"]
            if mute:
                raise Refusal(
                    f"page {index}: blocks {mute[:5]} carry content and no kind; text nobody says how to treat is filed nowhere"
                )
        return page
