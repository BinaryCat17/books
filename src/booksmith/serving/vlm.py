"""A vLLM behind the model protocol: `books serve vlm`.

vLLM serves the chat route and knows nothing of describe; this puts describe
and health beside it and passes `/v1/*` through byte for byte -- no retry, no
edit, no second ask, which is the first rule of the tree. The subprocess is
raised the way the rented run script raised it: in a process group of its
own, killed as a group, watched for its readiness on `/v1/models` before the
shim calls itself ready. The weights are hashed once at start and cached
beside them, so the describe's `sha256_weights` says which weights answer,
which the served model name never did.
"""
from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from booksmith.core import knobs, served
from booksmith.core.errors import Refusal
from booksmith.core.log import log

KINDS = ("text", "otsl", "latex")
# What the identity of the weights is taken over: the tensors and the two
# files that differ between releases of one model.
WEIGHT_FILES = (".safetensors", "config.json", "tokenizer_config.json")
CACHE = ".sha256_weights"
READY_S = 600


def weights_sha256(weights_dir: str) -> str:
    """One hash over the weight files, cached beside them: two gigabytes are
    read once per download, not once per start."""
    cache = os.path.join(weights_dir, CACHE)
    names = sorted(n for n in os.listdir(weights_dir) if n.endswith(WEIGHT_FILES))
    if not names:
        raise Refusal(f"{weights_dir}: no weight files ({WEIGHT_FILES}) to hash")
    # Size and modification time both: a file rewritten at the same size is
    # other weights, and the cache must not outlive them.
    key = json.dumps([(n, os.path.getsize(os.path.join(weights_dir, n)),
                       os.stat(os.path.join(weights_dir, n)).st_mtime_ns)
                      for n in names])
    if os.path.isfile(cache):
        with open(cache, encoding="utf-8") as f:
            had = json.load(f)
        if had.get("over") == key:
            return str(had["sha256"])
    h = hashlib.sha256()
    for n in names:
        with open(os.path.join(weights_dir, n), "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
    with open(cache, "w", encoding="utf-8") as f:
        json.dump({"over": key, "sha256": h.hexdigest()}, f)
    return h.hexdigest()


def command(weights_dir: str, model_name: str, port: int) -> list[str]:
    """The vLLM command line the rented run script raised, and no other:
    the served name is mandatory or the model registers under its path, and
    the memory share leaves room for a detector on the same card."""
    return ["vllm", "serve", weights_dir, "--trust-remote-code",
            "--served-model-name", model_name,
            "--host", "127.0.0.1", "--port", str(port),
            "--max-num-batched-tokens", "16384",
            "--gpu-memory-utilization", "0.60",
            "--no-enable-prefix-caching", "--mm-processor-cache-gb", "0"]


class Upstream:
    """The vLLM subprocess: raised in its own group, waited for, killed as a
    group. `url` is where it answers the chat route."""

    def __init__(self, weights_dir: str, model_name: str, port: int, log_path: str):
        self.weights_dir, self.model_name, self.port = weights_dir, model_name, port
        self.log_path = log_path
        self.proc: subprocess.Popen | None = None
        self.url = f"http://127.0.0.1:{port}"

    def start(self) -> None:
        with open(self.log_path, "ab") as out:
            self.proc = subprocess.Popen(
                command(self.weights_dir, self.model_name, self.port),
                stdout=out, stderr=subprocess.STDOUT, start_new_session=True)

    def alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def stop(self) -> None:
        if self.proc is None:
            return
        try:
            os.killpg(self.proc.pid, signal.SIGTERM)
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(self.proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def models_of(upstream_url: str, timeout: float = 5.0) -> list[str]:
    """The names the upstream chat route serves; empty while it is not up."""
    try:
        d = served.fetch(upstream_url + "/v1/models", timeout=timeout)
    except served.Unreachable:
        return []
    return [str(m.get("id")) for m in ((d.get("data") if isinstance(d, dict) else None) or [])]


class Service:
    """Describe and health for a vLLM at `upstream_url`, and the chat route
    passed through. `weights_dir` is where its weights lie, for the hash;
    None where they are not on this machine, and the fingerprint says so."""

    def __init__(self, upstream_url: str, model_name: str,
                 weights_dir: str | None = None, key: str | None = None,
                 upstream: Upstream | None = None):
        self.upstream_url = upstream_url.rstrip("/")
        self.model_name, self.key, self.upstream = model_name, key, upstream
        self.requests = 0
        self.last_request: float | None = None
        self.started = time.time()
        weights: dict = {"dir": weights_dir}
        if weights_dir and os.path.isdir(weights_dir):
            weights["sha256_weights"] = weights_sha256(weights_dir)
            for name in ("config.json", "tokenizer_config.json"):
                p = os.path.join(weights_dir, name)
                weights["sha256 " + name] = (
                    hashlib.sha256(open(p, "rb").read()).hexdigest()
                    if os.path.exists(p) else None)
            src = os.path.join(weights_dir, "SOURCE.json")
            if os.path.exists(src):
                with open(src, encoding="utf-8") as f:
                    weights["repo"] = json.load(f).get("repo")
        else:
            weights["sha256_weights"] = None
            weights["why_empty"] = ("no weights on this machine: the shim "
                                    "stands before a vLLM it did not raise")
        try:
            import vllm
            version = getattr(vllm, "__version__", None)
        except ImportError:
            version = None
        self.describe = served.Describe(
            kind="reader", label=model_name,
            fingerprint={"reader": "vllm", "model": model_name,
                         "vllm": version, **weights,
                         "sha256_weights": weights["sha256_weights"]},
            knobs={n: knobs.knob(n) for n in
                   ("MODEL_NAME", "VL_MODEL_DIR", "VLLM_USE_FLASHINFER_SAMPLER")},
            kinds=KINDS, openai={"base": "/v1", "model": model_name},
            commit=knobs.knob("BOOKSMITH_COMMIT") or None)

    def ready(self) -> bool:
        return self.model_name in models_of(self.upstream_url)

    def health(self) -> served.Health:
        return served.Health(ready=self.ready(), label=self.model_name,
                             last_request=self.last_request, requests=self.requests)

    def wait_ready(self, timeout: float = READY_S) -> float:
        """Seconds until the upstream answered with the model's name, or a
        Refusal with the tail of its log; a dead subprocess is one too."""
        t0 = time.time()
        while time.time() - t0 < timeout:
            if self.upstream is not None and not self.upstream.alive():
                raise Refusal(f"vLLM died at start; its log is {self.upstream.log_path}")
            if self.ready():
                return time.time() - t0
            time.sleep(1.0)
        raise Refusal(f"vLLM did not answer as {self.model_name!r} within {timeout:.0f} s")

    def proxy(self, method: str, path: str, body: bytes | None,
              headers: dict) -> tuple[int, str, bytes]:
        """One request through, once. (status, content type, body)."""
        h = {k: v for k, v in headers.items()
             if k.lower() in ("content-type", "accept")}
        req = urllib.request.Request(self.upstream_url + path, data=body,
                                     headers=h, method=method)
        try:
            with urllib.request.urlopen(req, timeout=knobs.number("VLM_TIMEOUT_S")) as r:
                return r.status, r.headers.get("Content-Type", "application/json"), r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.headers.get("Content-Type", "application/json"), e.read()
        except (urllib.error.URLError, OSError, TimeoutError) as e:
            return 502, "application/json", json.dumps(
                {"error": f"the model did not answer: {type(e).__name__}: {e}"}).encode()


def handler_for(svc: Service) -> type:
    class H(BaseHTTPRequestHandler):
        def log_message(self, fmt, *a):
            log(f"{self.address_string()} {fmt % a}")

        def _json(self, code: int, body: object) -> None:
            self._raw(code, "application/json", json.dumps(body, ensure_ascii=False).encode())

        def _raw(self, code: int, ctype: str, b: bytes) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        def _allowed(self) -> bool:
            if not svc.key or self.headers.get("Authorization") == "Bearer " + svc.key:
                return True
            self._json(401, {"error": "a key is required, and this is not it"})
            return False

        def _through(self, method: str) -> None:
            n = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(n) if n else None
            code, ctype, out = svc.proxy(method, self.path, body, dict(self.headers))
            if method == "POST" and self.path.endswith("/chat/completions"):
                svc.requests += 1
                svc.last_request = time.time()
            self._raw(code, ctype, out)

        def do_GET(self):
            if not self._allowed():
                return
            if self.path == served.DESCRIBE:
                return self._json(200, svc.describe.to_json())
            if self.path == served.HEALTH:
                return self._json(200, svc.health().to_json())
            if self.path.startswith("/v1/"):
                return self._through("GET")
            return self._json(404, {"error": f"no route {self.path}"})

        def do_POST(self):
            if not self._allowed():
                return
            if self.path.startswith("/v1/"):
                return self._through("POST")
            return self._json(404, {"error": f"no route {self.path}"})

    return H


def serve(svc: Service, host: str = "127.0.0.1", port: int = 0) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), handler_for(svc))


def main(host: str, port: int, upstream_url: str = "", key: str | None = None,
         log_dir: str = ".") -> int:
    """`books serve vlm`: a vLLM over `VL_MODEL_DIR`, raised here unless
    `upstream_url` names one already up, behind describe and health."""
    model = knobs.knob("MODEL_NAME")
    weights = knobs.knob("VL_MODEL_DIR") or None
    up = None
    if not upstream_url:
        if not weights:
            raise Refusal("VL_MODEL_DIR is empty and no upstream was named: "
                          "there is nothing to raise vLLM over")
        up = Upstream(weights, model, knobs.number("PORT", kind=int),
                      os.path.join(log_dir, "vllm.log"))
        up.start()
        upstream_url = up.url
    svc = Service(upstream_url, model, weights, key, up)
    try:
        took = svc.wait_ready()
        log(f"vLLM answers as {model} after {took:.0f} s; weights "
            f"{str(svc.describe.fingerprint.get('sha256_weights'))[:12]}")
        srv = serve(svc, host, port)
        log(f"listening on http://{srv.server_address[0]}:{srv.server_address[1]}"
            f"{served.DESCRIBE}, chat route passed through")
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            srv.server_close()
            log(f"served {svc.requests} requests")
    finally:
        if up is not None:
            up.stop()
    return 0
