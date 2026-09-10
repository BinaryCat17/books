"""A layout or hybrid model behind an endpoint, reached by the model protocol.

In: the address the knob `LAYOUT_ENDPOINT` names. The adapter asks describe
once, keeps the answer, and posts one page per call to the layout route. It
edits nothing the model returns: a page that is not a `Page`, a block whose
label the model did not declare, a layout model that returns text, all refuse
the run. A delivery failure refuses too: a layout answer is never re-asked.

The fingerprint is the model's own, as the describe carried it; the knobs the
model read are in the describe as well, and `detect.py` puts both into the
identity, so a served run of a model equals an in-process run of it.
"""
from __future__ import annotations

from booksmith.core import book, job, knobs, served
from booksmith.core.errors import Refusal
from booksmith.core.page import KINDS, Page
from booksmith.processing.layout.base import Detector

# How long one page may take. A constant and not a knob: it decides whether the
# run finishes, never what the model returns, so it has no place in the identity.
TIMEOUT_S = 600.0


class Served(Detector):
    """The model at `LAYOUT_ENDPOINT`. `describe` is asked at construction."""

    name = "served"

    def __init__(self) -> None:
        self.endpoint = served.root_of(knobs.knob("LAYOUT_ENDPOINT"))
        if not self.endpoint:
            raise Refusal(
                "LAYOUT_ENDPOINT is empty: no model address was given. There "
                "is no default on purpose -- a silent localhost would make "
                "the run knock at nothing and call that the model's silence.")
        # The key is the job's secret, never a knob: a snapshot must not hold it.
        self.headers = served.bearer(
            str(job.current().secrets.get("LAYOUT_API_KEY") or ""))
        try:
            answer = served.fetch(self.endpoint + served.DESCRIBE,
                                  timeout=TIMEOUT_S, headers=self.headers)
        except served.Unreachable as e:
            raise Refusal(
                f"{self.endpoint} does not describe itself: {e.why}. A "
                f"model that cannot say what it is cannot be filed under a "
                f"label, so nothing is asked of it.") from None
        self.describe = served.Describe.from_json(answer)
        if self.describe.kind == "reader":
            raise Refusal(
                f"{self.endpoint} is a reader ({self.describe.label}); a "
                f"layout run needs a layout or hybrid model. Point "
                f"VLM_ENDPOINT at it and run `books read` instead.")
        missing = [k for k in self.FINGERPRINT_REQUIRED
                   if k not in self.describe.fingerprint]
        if missing:
            raise Refusal(
                f"{self.describe.label}: the fingerprint lacks {missing}, "
                f"which the snapshot indexes and the identity stands on.")
        self.labels: tuple[str, ...] = tuple(self.describe.labels)
        self._known = set(self.labels)
        # The policy is the model's declaration, as an in-process adapter's
        # class attribute is; `detect.py` checks it covers the labels whole.
        self.policy_name = self.describe.vocabulary

    # -------------------------------------------------------- the contract --
    def where(self) -> str:
        return self.endpoint

    def served(self) -> dict | None:
        return self.describe.to_json()

    def label(self) -> str:
        return book.safe_label(self.describe.label, "the served model")

    def fingerprint(self) -> dict:
        return dict(self.describe.fingerprint)

    def knobs_read(self) -> tuple[str, ...]:
        return ("LAYOUT_ENDPOINT",)

    def label_map(self) -> dict[str, str]:
        m = self.describe.fingerprint.get("label_map")
        return dict(m) if isinstance(m, dict) else {}

    def threshold_drift(self) -> tuple[str, ...]:
        """What the server said of its thresholds; the drift is computed where
        the knobs are read, and here they were read on the other side."""
        lines = self.describe.fingerprint.get("threshold_drift") or ()
        return tuple(str(x) for x in lines)

    # ------------------------------------------------------------ the count --
    def read(self, image_path: str, index: int, dpi: float) -> Page:
        uri, _ = served.data_uri(image_path)
        sent = served.png_size(image_path)
        req = served.LayoutRequest(index=index, dpi=dpi, image=uri)
        try:
            answer = served.fetch(self.endpoint + served.LAYOUT, req.to_json(),
                                  timeout=TIMEOUT_S, headers=self.headers)
        except served.Unreachable as e:
            raise Refusal(
                f"page {index}: {self.describe.label} at {self.endpoint} did "
                f"not answer the layout route: {e.why}. Not repeated: a "
                f"second ask would be a second experiment.") from None
        try:
            page = Page.from_json(answer if isinstance(answer, dict) else {})
        except (KeyError, TypeError, ValueError) as e:
            raise Refusal(
                f"page {index}: {self.describe.label} answered something that "
                f"is not a page ({type(e).__name__}: {e})") from None
        if page.index != index:
            raise Refusal(
                f"page {index}: {self.describe.label} answered for page "
                f"{page.index}; the answer would be filed under the wrong "
                f"sheet")
        lacking = [k for k in self.PAGE_META_REQUIRED if k not in page.meta]
        if lacking:
            raise Refusal(
                f"page {index}: the answer's meta lacks {lacking}, which the "
                f"detect loop indexes on every page")
        # The sheet the boxes are on must be the sheet that was sent: a page
        # filed at another dpi or size under this run's snapshot would put
        # every box a factor off, plausibly.
        if float(page.dpi) != float(dpi):
            raise Refusal(
                f"page {index}: {self.describe.label} answered at dpi "
                f"{page.dpi}, and the raster was sent at {dpi}")
        if sent is not None and (page.width, page.height) != sent:
            raise Refusal(
                f"page {index}: {self.describe.label} answered a sheet of "
                f"{page.width}x{page.height}, and the raster sent was "
                f"{sent[0]}x{sent[1]}")
        foreign_labels = sorted({b.label for b in page.blocks
                                 if b.label not in self._known})
        if foreign_labels:
            raise Refusal(
                f"page {index}: {self.describe.label} returned labels "
                f"{foreign_labels[:5]} it did not declare in its describe; "
                f"a label outside the declared vocabulary has no role")
        if self.describe.kind == "layout":
            spoken = [b.block_id for b in page.blocks
                      if b.content is not None or b.kind != "none"]
            if spoken:
                raise Refusal(
                    f"page {index}: {self.describe.label} said it is a "
                    f"layout model and returned content on blocks "
                    f"{spoken[:5]}. Text from a model that declared none is "
                    f"filed nowhere; declare the model a hybrid.")
        else:
            bad = sorted({b.kind for b in page.blocks
                          if b.kind not in KINDS + ("none",)})
            if bad:
                raise Refusal(
                    f"page {index}: blocks carry kinds {bad}, and a block's "
                    f"kind is one of {KINDS} or none")
            foreign = sorted({b.kind for b in page.blocks
                              if b.kind != "none"
                              and b.kind not in self.describe.kinds})
            if foreign:
                raise Refusal(
                    f"page {index}: {self.describe.label} declared kinds "
                    f"{list(self.describe.kinds)} and returned {foreign}")
            mute = [b.block_id for b in page.blocks
                    if b.content is not None and b.kind == "none"]
            if mute:
                raise Refusal(
                    f"page {index}: blocks {mute[:5]} carry content and no "
                    f"kind; text nobody says how to treat is filed nowhere")
        return page
