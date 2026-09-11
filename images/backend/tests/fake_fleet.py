import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class FakeFleet:
    def __init__(self, images: dict | None = None):
        fake = self
        self.models: dict = {}
        self.images = images or {}
        self.leases: list = []
        self.calls: list = []
        self.starting = 0

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
                if self.path == "/models":
                    return self._json(200, fake.models)
                if self.path == "/placements":
                    return self._json(200, [{"id": "p1", "model": m["model"], "state": "ready"} for m in fake.leases])
                if self.path == "/ledger":
                    return self._json(200, [{"model": "old", "cost_usd": 0.5, "why": "idle"}])
                self._json(404, {"error": "no route"})

            def do_DELETE(self):
                fake.calls.append((self.path, {}))
                if self.path.startswith("/placements/"):
                    return self._json(200, {"stopped": self.path.rsplit("/", 1)[-1]})
                self._json(404, {"error": "no route"})

            def do_PUT(self):
                n = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(n) or b"{}")
                for name, e in body.items():
                    if bool(e.get("endpoint")) == bool(e.get("image")):
                        return self._json(409, {"error": f"{name}: an endpoint or an image"})
                fake.models = {n: {"knobs": {}, **e} for n, e in body.items()}
                for e in fake.models.values():
                    e["knobs"] = {k: str(v) for k, v in e["knobs"].items()}
                self._json(200, fake.models)

            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(n) or b"{}")
                fake.calls.append((self.path, body))
                if self.path == "/leases":
                    e = fake.models.get(body["model"])
                    if e is None:
                        return self._json(409, {"error": f"no model {body['model']!r}"})
                    if e.get("endpoint"):
                        return self._json(200, {"state": "ready", "endpoint": e["endpoint"], "key": e.get("api_key") or "", "lease": None, "placement": None})
                    if e["image"] not in fake.images:
                        return self._json(409, {"error": f"no offer for {e['image']}"})
                    if fake.starting > 0:
                        fake.starting -= 1
                        return self._json(202, {"state": "starting", "endpoint": "", "key": "", "lease": None, "placement": "p1"})
                    lid = f"lease-{len(fake.leases) + 1}"
                    fake.leases.append({"id": lid, "job": body["job"], "model": body["model"]})
                    return self._json(200, {"state": "ready", "endpoint": fake.images[e["image"]], "key": "k-" + lid, "lease": lid, "placement": "p1"})
                if self.path == "/leases/renew":
                    return self._json(200, {"renewed": sum(1 for x in fake.leases if x["job"] == body["job"])})
                if self.path == "/leases/release":
                    n = len([x for x in fake.leases if x["job"] == body["job"]])
                    fake.leases = [x for x in fake.leases if x["job"] != body["job"]]
                    return self._json(200, {"released": n})
                self._json(404, {"error": "no route"})

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.srv.server_address[1]}"

    def __enter__(self):
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *a):
        self.srv.shutdown()
        self.srv.server_close()
