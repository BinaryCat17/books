"""A stand-in layout model: an endpoint of the model protocol that answers
from a truth directory.

The served adapter, the identity of a served run, the hybrid writer and the
registry are checked against it locally, with no weights. It is a model in no
sense: it never looks at the image, it answers the truth page for the index
asked, stripped of its text unless it plays a hybrid. It checks our half.
"""
import hashlib
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

from booksmith.core import policy, served


def truth_pages(truth_dir):
    out = {}
    for name in sorted(os.listdir(truth_dir)):
        if name.endswith(".json"):
            with open(os.path.join(truth_dir, name), encoding="utf-8") as f:
                p = json.load(f)
            out[int(p["index"])] = p
    return out


def _weights_hash(pages):
    """A deterministic stand-in for sha256_weights: over the truth itself."""
    h = hashlib.sha256()
    for i in sorted(pages):
        h.update(json.dumps(pages[i]["blocks"], sort_keys=True).encode())
    return h.hexdigest()


class FakeLayout:
    """A service on a random port over `truth_dir`. `kind` is layout or
    hybrid; `fingerprint`, `knobs` and `label` override what the describe
    says; `keep_content=True` makes a layout model return text, which the
    adapter must refuse."""

    def __init__(self, truth_dir, kind="layout", label="truth",
                 vocabulary="PP-DocLayoutV2", fingerprint=None, knobs=None,
                 keep_content=False, kinds=("text",), openai=None,
                 answer=None):
        self.pages = truth_pages(truth_dir)
        self.kind, self.label, self.keep_content = kind, label, keep_content
        labels = list(policy.POLICIES[vocabulary])
        fp = fingerprint if fingerprint is not None else {
            "name": "fake-layout", "model": label,
            "sha256_weights": _weights_hash(self.pages),
            "label_vocabulary": labels, "label_map": {}, "prompts": {},
            "reading_order": "model_rank", "threshold_drift": []}
        self.describe = served.Describe(
            kind=kind, label=label, fingerprint=fp, labels=tuple(labels),
            vocabulary=vocabulary, reading_order="own",
            knobs=dict(knobs or {}),
            kinds=tuple(kinds) if kind == "hybrid" else (),
            openai=openai, commit="fake", adapter_sha256="0" * 64)
        # `answer(page dict) -> page dict` edits what a page answers with.
        self.answer = answer
        self.seen = []
        self.requests = 0
        self.last_request = None
        srv = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _json(self, code, body):
                b = json.dumps(body).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)

            def do_GET(self):
                if self.path == served.DESCRIBE:
                    return self._json(200, srv.describe.to_json())
                if self.path == served.HEALTH:
                    return self._json(200, served.Health(
                        True, srv.label, srv.last_request, srv.requests).to_json())
                return self._json(404, {"error": "no such path"})

            def do_POST(self):
                if self.path != served.LAYOUT:
                    return self._json(404, {"error": "no such path"})
                n = int(self.headers.get("Content-Length") or 0)
                req = served.LayoutRequest.from_json(
                    json.loads(self.rfile.read(n) or b"{}"))
                srv.seen.append({"index": req.index, "dpi": req.dpi,
                                 "bytes": len(req.image),
                                 "authorization": self.headers.get("Authorization")})
                srv.requests += 1
                srv.last_request = time.time()
                page = srv.pages.get(req.index)
                if page is None:
                    return self._json(404, {"error": f"no page {req.index}"})
                out = srv._answer(page)
                return self._json(200, srv.answer(out) if srv.answer else out)

        self.httpd = HTTPServer(("127.0.0.1", 0), H)
        self.port = self.httpd.server_address[1]
        self.url = f"http://127.0.0.1:{self.port}"

    def _answer(self, page):
        d = json.loads(json.dumps(page))
        keep = self.kind == "hybrid" or self.keep_content
        for b in d["blocks"]:
            b.pop("source_category", None)
            if not keep:
                b["content"], b["kind"] = None, "none"
        d["meta"] = {**d.get("meta", {}), "detector": "fake-layout",
                     "boxes_accepted": len(d["blocks"]), "rank_ties": 0,
                     "best_rejected_by_class": {},
                     "reading_order": d.get("meta", {}).get(
                         "reading_order", "model_rank")}
        d["raw"] = None
        return d

    def __enter__(self):
        self.t = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.t.start()
        return self

    def __exit__(self, *a):
        self.httpd.shutdown()
        self.httpd.server_close()
