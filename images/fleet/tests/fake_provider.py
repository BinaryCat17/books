import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Shim:
    def __init__(self, key: str):
        shim = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                ok = self.headers.get("Authorization") == f"Bearer {shim.key}"
                body = json.dumps({"ready": shim.ready, "label": "fake", "requests": 0} if ok else {"error": "key"}).encode()
                self.send_response(200 if ok else 401)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.key, self.ready = key, True
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.srv.server_address[1]}"

    def close(self):
        self.srv.shutdown()
        self.srv.server_close()


class FakeProvider:
    name = "fake"

    def __init__(self, rate: float = 0.0, ready_after: int = 0):
        self.rate_usd_h, self.ready_after = rate, ready_after
        self.running: dict[str, Shim] = {}
        self.stopped: list[str] = []
        self.n = 0
        self.foreign: list[str] = []

    def start(self, model, entry, key):
        self.n += 1
        shim = Shim(key)
        shim.ready = self.ready_after == 0
        self.ready_after = max(0, self.ready_after - 1)
        hid = f"c{self.n}"
        self.running[hid] = shim
        return {"id": hid, "endpoint": shim.url, "rate_usd_h": self.rate_usd_h}

    def alive(self, handle):
        return handle in self.running

    def stop(self, handle):
        shim = self.running.pop(handle, None)
        if shim:
            shim.close()
        self.stopped.append(handle)
        if handle in self.foreign:
            self.foreign.remove(handle)

    def list(self):
        return [{"id": h, "model": "?", "state": "running"} for h in list(self.running) + list(self.foreign)]

    def rate(self, entry):
        return self.rate_usd_h
