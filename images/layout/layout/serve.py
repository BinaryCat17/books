"""A detector behind the model protocol"""

from __future__ import annotations

import base64
import contextvars
import hmac
import os
import sys
import tempfile
import threading
import time

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from layout import identity as stamp
from layout import knobs, order
from layout import protocol as served
from layout.detector import Detector
from layout.errors import BooksmithError, Refusal

ADAPTERS = ("doclayout", "docling", "docling-egret", "yolox")


def adapter(which: str) -> Detector:
    if which == "doclayout":
        from layout.doclayout import DocLayout

        return DocLayout()
    if which == "docling":
        from layout.docling import DoclingHeron

        return DoclingHeron()
    if which == "docling-egret":
        from layout.docling import DoclingEgret

        return DoclingEgret()
    if which == "yolox":
        from layout.yolox import YoloXLayout

        return YoloXLayout()
    raise Refusal(f"LAYOUT_ADAPTER={which!r}: one of {ADAPTERS}")


def _adapter_sha(det: Detector) -> str | None:
    mod = sys.modules.get(type(det).__module__)
    path = getattr(mod, "__file__", None)
    return stamp.sha256(path) if path and os.path.isfile(path) else None


class Service:
    def __init__(self, det: Detector, kind: str = "layout", kinds: tuple[str, ...] = (), key: str | None = None):
        if kind not in ("layout", "hybrid"):
            raise Refusal(f"a served detector is layout or hybrid, not {kind!r}")
        if kind == "hybrid" and not kinds:
            raise Refusal("a hybrid declares the kinds of content it returns")
        self.det, self.kind, self.key = det, kind, key
        self.pol = det.policy()
        self.context = contextvars.copy_context()
        self.lock = threading.Lock()
        self.requests = 0
        self.last_request: float | None = None
        fp = det.fingerprint()
        self.describe = served.Describe(
            kind=kind,
            label=det.label(),
            fingerprint=fp,
            classes=dict(self.pol.classes),
            vocabulary=self.pol.name,
            reading_order="own" if fp.get("reading_order") == order.MODEL_RANK else "none",
            knobs={n: knobs.knob(n) for n in det.knobs_read()},
            kinds=tuple(kinds),
            commit=stamp.commit(),
            adapter_sha256=_adapter_sha(det),
        )

    def health(self) -> served.Health:
        return served.Health(ready=True, label=self.describe.label, last_request=self.last_request,
                             requests=self.requests)

    def layout(self, req: served.LayoutRequest) -> dict:
        head, _, payload = req.image.partition(",")
        if not head.startswith("data:image/png;base64") or not payload:
            raise Refusal("layout: the image is not a base64 PNG data URI")
        try:
            raw = base64.b64decode(payload, validate=True)
        except (ValueError, TypeError) as e:
            raise Refusal(f"layout: the image does not decode: {e}") from None
        fd, tmp = tempfile.mkstemp(prefix="page.", suffix=".png")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(raw)
            with self.lock:
                page = self.context.copy().run(self.det.read, tmp, req.index, req.dpi)
                self.requests += 1
                self.last_request = time.time()
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
        return page.to_json()


def create_app(svc: Service) -> FastAPI:
    app = FastAPI(title=f"model {svc.describe.label}")

    def allowed(authorization: str | None = Header(default=None)) -> None:
        if svc.key and not (authorization and hmac.compare_digest(authorization, "Bearer " + svc.key)):
            raise HTTPException(401, "a key is required, and this is not it")

    @app.exception_handler(BooksmithError)
    def _refusal(_r: Request, e: BooksmithError) -> JSONResponse:
        return JSONResponse({"error": f"{type(e).__name__}: {e}"}, status_code=400)

    @app.get(served.DESCRIBE, dependencies=[Depends(allowed)])
    def describe() -> dict:
        return svc.describe.to_json()

    @app.get(served.HEALTH, dependencies=[Depends(allowed)])
    def health() -> dict:
        return svc.health().to_json()

    @app.post(served.LAYOUT, dependencies=[Depends(allowed)])
    def layout(body: dict) -> dict:
        try:
            req = served.LayoutRequest.from_json(body)
        except (ValueError, TypeError) as e:
            raise Refusal(f"layout: {e}") from None
        return svc.layout(req)

    return app
