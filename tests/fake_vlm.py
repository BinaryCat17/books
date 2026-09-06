"""A stand-in VLM: an OpenAI-compatible endpoint that answers to order.

WHY. The whole of level two -- crops, prompts, answer parsing, page assembly,
five different zeros, the snapshot -- is checked HERE, for nothing, and only
then goes to a rented card. The previous level two paid rental after rental to
debug its parser: thirteen runs and $0.52, two of them useful, and every trap
turned out to be ours, not one the model's.

The server answers exactly what it was told to: a string, emptiness, a cut at
the ceiling, a 500. So each of level two's five troubles reproduces on the spot
in milliseconds instead of waiting for the model to deign to fall silent.

It is a model in no sense: it does not read the image and does not pretend to.
It checks OUR half.
"""
import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer


class FakeVlm:
    """A service on a random port. `plan` decides what it answers.

    `plan` is one answer for every request, or a dict {prompt -> answer}, or a
    function (prompt, image) -> answer. An answer is a dict:

        {"text": "...", "finish": "stop"}   an ordinary answer
        {"text": "", "finish": "stop"}      the model stayed silent
        {"text": "...", "finish": "length"} cut off at the ceiling
        {"http": 500}                       delivery refused
    """

    def __init__(self, plan, model="PaddleOCR-VL-1.6-0.9B"):
        self.plan, self.model = plan, model
        self.seen = []                      # what was asked, in order
        srv = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):      # silence in the checks' output
                pass

            def _json(self, code, body):
                b = json.dumps(body).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)

            def do_GET(self):
                if self.path.endswith("/models"):
                    return self._json(200, {"data": [{"id": srv.model}]})
                return self._json(404, {"error": "no such path"})

            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0)
                req = json.loads(self.rfile.read(n) or b"{}")
                content = (req.get("messages") or [{}])[0].get("content") or []
                prompt = next((c.get("text") for c in content
                               if c.get("type") == "text"), "")
                uri = next((c.get("image_url", {}).get("url") for c in content
                            if c.get("type") == "image_url"), "")
                # The image bytes are taken WHOLE: the checks verify that the
                # crop which reached the model is that one and not its
                # neighbour.
                img = b""
                if "," in uri:
                    img = base64.b64decode(uri.split(",", 1)[1])
                srv.seen.append({"prompt": prompt, "bytes": len(img),
                                 "model": req.get("model"),
                                 "generation": {k: v for k, v in req.items()
                                                if k in ("temperature",
                                                         "max_tokens")}})
                a = srv._answer(prompt, img)
                if "http" in a:
                    return self._json(a["http"], {"error": "a staged refusal"})
                return self._json(200, {
                    "model": srv.model,
                    "choices": [{"message": {"content": a.get("text")},
                                 "finish_reason": a.get("finish", "stop")}],
                    "usage": {"completion_tokens": len(a.get("text") or "")}})

        self.httpd = HTTPServer(("127.0.0.1", 0), H)
        self.port = self.httpd.server_address[1]
        self.url = f"http://127.0.0.1:{self.port}/v1"

    def _answer(self, prompt, img):
        p = self.plan
        if callable(p):
            return p(prompt, img)
        if isinstance(p, dict) and not {"text", "http"} & set(p):
            return p.get(prompt, {"text": ""})
        return p

    def __enter__(self):
        self.t = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.t.start()
        return self

    def __exit__(self, *a):
        self.httpd.shutdown()
        self.httpd.server_close()
