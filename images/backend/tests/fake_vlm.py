"""A stand-in VLM: an OpenAI-compatible endpoint that answers to order"""

import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer


class FakeVlm:
    def __init__(self, plan, model="PaddleOCR-VL-1.6-0.9B"):
        self.plan, self.model = (plan, model)
        self.seen = []
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
                srv.seen.append(
                    {"path": self.path, "authorization": self.headers.get("Authorization")}
                )
                if self.path.endswith("/models"):
                    return self._json(200, {"data": [{"id": srv.model}]})
                return self._json(404, {"error": "no such path"})

            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0)
                req = json.loads(self.rfile.read(n) or b"{}")
                content = (req.get("messages") or [{}])[0].get("content") or []
                prompt = next((c.get("text") for c in content if c.get("type") == "text"), "")
                uri = next(
                    (
                        c.get("image_url", {}).get("url")
                        for c in content
                        if c.get("type") == "image_url"
                    ),
                    "",
                )
                img = b""
                if "," in uri:
                    img = base64.b64decode(uri.split(",", 1)[1])
                srv.seen.append(
                    {
                        "path": self.path,
                        "prompt": prompt,
                        "bytes": len(img),
                        "model": req.get("model"),
                        "authorization": self.headers.get("Authorization"),
                        "generation": {
                            k: v for k, v in req.items() if k in ("temperature", "max_tokens")
                        },
                    }
                )
                a = srv._answer(prompt, img)
                if "http" in a:
                    return self._json(a["http"], {"error": "a staged refusal"})
                return self._json(
                    200,
                    {
                        "model": srv.model,
                        "choices": [
                            {
                                "message": {"content": a.get("text")},
                                "finish_reason": a.get("finish", "stop"),
                            }
                        ],
                        "usage": {"completion_tokens": len(a.get("text") or "")},
                    },
                )

        self.httpd = HTTPServer(("127.0.0.1", 0), H)
        self.port = self.httpd.server_address[1]
        self.url = f"http://127.0.0.1:{self.port}/v1"

    def _answer(self, prompt, img):
        p = self.plan
        if callable(p):
            return p(prompt, img)
        if isinstance(p, dict) and (not {"text", "http"} & set(p)):
            return p.get(prompt, {"text": ""})
        return p

    def __enter__(self):
        self.t = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.t.start()
        return self

    def __exit__(self, *a):
        self.httpd.shutdown()
        self.httpd.server_close()
