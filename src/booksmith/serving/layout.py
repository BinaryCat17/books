"""A detector behind the model protocol: `books serve layout`.

The detector is built once, under the process's job, and the values of the
knobs it read are the describe's `knobs`: the client folds them into the
identity, so a run through this shim is the run of this model under these
settings, wherever the client was. One page at a time, under a lock: an
ONNX session is one, and two rasters in flight would double the memory for
nothing. A request carries a PNG as a data URI; the adapter reads a file, so
the raster is written to a temporary one and removed after the answer.
"""
from __future__ import annotations

import base64
import json
import os
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from booksmith.core import knobs, order, served, stamp
from booksmith.core.errors import BooksmithError, Refusal
from booksmith.core.log import log
from booksmith.processing.layout.base import Detector


def _adapter_sha(det: Detector) -> str | None:
    mod = sys.modules.get(type(det).__module__)
    path = getattr(mod, "__file__", None)
    return stamp.sha256(path) if path and os.path.isfile(path) else None


class Service:
    """One detector behind the three routes; `kind` is layout or hybrid, and
    a hybrid names the kinds of content its blocks carry."""

    def __init__(self, det: Detector, kind: str = "layout",
                 kinds: tuple[str, ...] = (), key: str | None = None):
        if kind not in ("layout", "hybrid"):
            raise Refusal(f"a served detector is layout or hybrid, not {kind!r}")
        if kind == "hybrid" and not kinds:
            raise Refusal("a hybrid declares the kinds of content it returns")
        self.det, self.kind, self.key = det, kind, key
        self.pol = det.policy()
        self.lock = threading.Lock()
        self.requests = 0
        self.last_request: float | None = None
        fp = det.fingerprint()
        self.describe = served.Describe(
            kind=kind, label=det.label(), fingerprint=fp,
            classes=dict(self.pol.classes), vocabulary=self.pol.name,
            reading_order=("own" if fp.get("reading_order") == order.MODEL_RANK
                           else "none"),
            # Read here, under this process's job: what decided the answers.
            knobs={n: knobs.knob(n) for n in det.knobs_read()},
            kinds=tuple(kinds), commit=stamp.commit(),
            adapter_sha256=_adapter_sha(det))

    def health(self) -> served.Health:
        return served.Health(ready=True, label=self.describe.label,
                             last_request=self.last_request,
                             requests=self.requests)

    def layout(self, req: served.LayoutRequest) -> dict:
        """One page: the raster to a file, the adapter, the page as JSON."""
        head, _, payload = req.image.partition(",")
        if not head.startswith("data:image/png;base64") or not payload:
            raise Refusal("layout: the image is not a base64 PNG data URI; "
                          "the rasters the tree renders are PNG")
        try:
            raw = base64.b64decode(payload, validate=True)
        except (ValueError, TypeError) as e:
            raise Refusal(f"layout: the image does not decode: {e}") from None
        fd, tmp = tempfile.mkstemp(prefix="page.", suffix=".png")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(raw)
            with self.lock:
                page = self.det.read(tmp, req.index, req.dpi)
                self.requests += 1
                self.last_request = time.time()
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
        return page.to_json()


def handler_for(svc: Service) -> type:
    """The request handler over one service. A refusal is a 400 with its
    text, anything else a 500 with its type and text: the client files
    neither as a page, and nothing here is repeated."""

    class H(BaseHTTPRequestHandler):
        def log_message(self, fmt, *a):
            log(f"{self.address_string()} {fmt % a}")

        def _json(self, code: int, body: object) -> None:
            b = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        def _allowed(self) -> bool:
            if not svc.key:
                return True
            if self.headers.get("Authorization") == "Bearer " + svc.key:
                return True
            self._json(401, {"error": "a key is required, and this is not it"})
            return False

        def do_GET(self):
            if not self._allowed():
                return
            if self.path == served.DESCRIBE:
                return self._json(200, svc.describe.to_json())
            if self.path == served.HEALTH:
                return self._json(200, svc.health().to_json())
            return self._json(404, {"error": f"no route {self.path}"})

        def do_POST(self):
            if not self._allowed():
                return
            if self.path != served.LAYOUT:
                return self._json(404, {"error": f"no route {self.path}"})
            n = int(self.headers.get("Content-Length") or 0)
            try:
                req = served.LayoutRequest.from_json(
                    json.loads(self.rfile.read(n) or b"{}"))
                return self._json(200, svc.layout(req))
            except (ValueError, BooksmithError) as e:
                return self._json(400, {"error": f"{type(e).__name__}: {e}"})
            except Exception as e:  # said, never swallowed
                return self._json(500, {"error": f"{type(e).__name__}: {e}"})

    return H


def serve(svc: Service, host: str = "127.0.0.1", port: int = 0) -> ThreadingHTTPServer:
    """The server, bound and not yet running: the caller says when."""
    return ThreadingHTTPServer((host, port), handler_for(svc))


def main(host: str, port: int, kind: str = "layout",
         kinds: tuple[str, ...] = (), key: str | None = None) -> int:
    """`books serve layout`: the adapter the knobs name, behind the routes,
    until stopped."""
    from booksmith.processing.layout import detect as level_one
    det = level_one._adapter()
    svc = Service(det, kind, kinds, key)
    d = svc.describe
    log(f"serving {d.kind} {d.label}: {len(d.classes)} labels of "
        f"{d.vocabulary or 'the model'}, knobs {sorted(d.knobs)}, "
        f"key {'required' if key else 'none'}")
    srv = serve(svc, host, port)
    log(f"listening on http://{srv.server_address[0]}:{srv.server_address[1]}"
        f"{served.DESCRIBE}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
        log(f"served {svc.requests} pages")
    return 0
