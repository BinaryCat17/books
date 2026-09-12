from __future__ import annotations
import contextvars
import hmac
import hashlib
import importlib.metadata
import json
import os
import signal
import subprocess
import time
import urllib.error
import urllib.request

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from vlm import job
from vlm import deadman, knobs
from vlm import protocol as served
from vlm.errors import Refusal
from vlm.log import log

KINDS = ("text", "otsl", "latex")
WEIGHT_FILES = (".safetensors", "config.json", "tokenizer_config.json")
CACHE = ".sha256_weights"
READY_S = 600


def weights_sha256(weights_dir: str) -> str:
    cache = os.path.join(weights_dir, CACHE)
    names = sorted(n for n in os.listdir(weights_dir) if n.endswith(WEIGHT_FILES))
    if not names:
        raise Refusal(f"{weights_dir}: no weight files ({WEIGHT_FILES}) to hash")
    key = json.dumps(
        [
            (
                n,
                os.path.getsize(os.path.join(weights_dir, n)),
                os.stat(os.path.join(weights_dir, n)).st_mtime_ns,
            )
            for n in names
        ]
    )
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
    try:
        with open(cache, "w", encoding="utf-8") as f:
            json.dump({"over": key, "sha256": h.hexdigest()}, f)
    except OSError as e:
        log(
            f"the weights hash could not be cached beside the weights ({e}); it will be taken again at the next start"
        )
    return h.hexdigest()


def command(weights_dir: str, model_name: str, port: int) -> list[str]:
    return [
        "vllm",
        "serve",
        weights_dir,
        "--trust-remote-code",
        "--served-model-name",
        model_name,
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--max-num-batched-tokens",
        "16384",
        "--gpu-memory-utilization",
        "0.60",
        "--no-enable-prefix-caching",
        "--mm-processor-cache-gb",
        "0",
    ]


# Every knob this image reads reaches the describe, and so the run's identity.
# PORT is the exception: where vLLM listens on this machine decides nothing it answers.
DESCRIBED = ("MODEL_NAME", "VL_MODEL_DIR", "VLLM_USE_FLASHINFER_SAMPLER", "VLM_TIMEOUT_S")
NOT_DESCRIBED = ("PORT",)


class Upstream:
    def __init__(self, weights_dir: str, model_name: str, port: int, log_path: str):
        self.weights_dir, self.model_name, self.port = (weights_dir, model_name, port)
        self.log_path = log_path
        self.proc: subprocess.Popen | None = None
        self.url = f"http://127.0.0.1:{port}"

    def start(self) -> None:
        with open(self.log_path, "ab") as out:
            self.proc = subprocess.Popen(
                command(self.weights_dir, self.model_name, self.port),
                stdout=out,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )

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
                self.proc.wait(timeout=10)
        except ProcessLookupError:
            pass


def models_of(upstream_url: str, timeout: float = 5.0) -> list[str]:
    try:
        d = served.fetch(upstream_url + "/v1/models", timeout=timeout)
    except served.Unreachable:
        return []
    return [str(m.get("id")) for m in (d.get("data") if isinstance(d, dict) else None) or []]


class Service:
    def __init__(
        self,
        upstream_url: str,
        model_name: str,
        weights_dir: str | None = None,
        key: str | None = None,
        upstream: Upstream | None = None,
    ):
        self.upstream_url = upstream_url.rstrip("/")
        self.model_name, self.key, self.upstream = (model_name, key, upstream)
        self.context = contextvars.copy_context()
        self.requests = 0
        self.last_request: float | None = None
        self.started = time.time()
        weights: dict = {"dir": weights_dir}
        if weights_dir and os.path.isdir(weights_dir):
            weights["sha256_weights"] = weights_sha256(weights_dir)
            for name in ("config.json", "tokenizer_config.json"):
                p = os.path.join(weights_dir, name)
                weights["sha256 " + name] = (
                    hashlib.sha256(open(p, "rb").read()).hexdigest() if os.path.exists(p) else None
                )
            src = os.path.join(weights_dir, "SOURCE.json")
            if os.path.exists(src):
                with open(src, encoding="utf-8") as f:
                    weights["repo"] = json.load(f).get("repo")
        else:
            weights["sha256_weights"] = None
            weights["why_empty"] = (
                "no weights on this machine: the shim stands before a vLLM it did not raise"
            )
        try:
            version: str | None = importlib.metadata.version("vllm")
        except importlib.metadata.PackageNotFoundError:
            version = None
        self.describe = served.Describe(
            kind="reader",
            label=model_name,
            fingerprint={
                "reader": "vllm",
                "model": model_name,
                "vllm": version,
                **weights,
                "sha256_weights": weights["sha256_weights"],
            },
            knobs={n: knobs.knob(n) for n in DESCRIBED},
            kinds=KINDS,
            openai={"base": "/v1", "model": model_name},
            commit=os.environ.get("BOOKSMITH_COMMIT") or None,
        )

    def ready(self) -> bool:
        return self.model_name in models_of(self.upstream_url)

    def health(self) -> served.Health:
        return served.Health(
            ready=self.ready(),
            label=self.model_name,
            last_request=self.last_request,
            requests=self.requests,
        )

    def wait_ready(self, timeout: float = READY_S) -> float:
        t0 = time.time()
        while time.time() - t0 < timeout:
            job.current().check()
            if self.upstream is not None and (not self.upstream.alive()):
                raise Refusal(f"vLLM died at start; its log is {self.upstream.log_path}")
            if self.ready():
                return time.time() - t0
            time.sleep(1.0)
        raise Refusal(f"vLLM did not answer as {self.model_name!r} within {timeout:.0f} s")

    def proxy(self, method: str, path: str, body: bytes | None, headers: dict) -> tuple[int, str, bytes]:
        h = {k: v for k, v in headers.items() if k.lower() in ("content-type", "accept")}
        req = urllib.request.Request(self.upstream_url + path, data=body, headers=h, method=method)
        try:
            with urllib.request.urlopen(req, timeout=knobs.number("VLM_TIMEOUT_S")) as r:
                return (r.status, r.headers.get("Content-Type", "application/json"), r.read())
        except urllib.error.HTTPError as e:
            return (e.code, e.headers.get("Content-Type", "application/json"), e.read())
        except (urllib.error.URLError, OSError, TimeoutError) as e:
            return (
                502,
                "application/json",
                json.dumps({"error": f"the model did not answer: {type(e).__name__}: {e}"}).encode(),
            )


def create_app(svc: Service) -> FastAPI:
    app = FastAPI(title=f"model {svc.model_name}")

    def allowed(authorization: str | None = Header(default=None)) -> None:
        if svc.key and not (authorization and hmac.compare_digest(authorization, "Bearer " + svc.key)):
            raise HTTPException(401, "a key is required, and this is not it")

    @app.get(served.DESCRIBE, dependencies=[Depends(allowed)])
    def describe() -> dict:
        return svc.describe.to_json()

    @app.get(served.HEALTH, dependencies=[Depends(allowed)])
    def health() -> dict:
        return svc.health().to_json()

    @app.api_route("/v1/{path:path}", methods=["GET", "POST"], dependencies=[Depends(allowed)])
    async def through(path: str, request: Request) -> Response:
        body = await request.body()
        code, ctype, out = await run_in_threadpool(
            svc.proxy, request.method, "/v1/" + path, body or None, dict(request.headers)
        )
        if request.method == "POST" and path.endswith("chat/completions"):
            svc.requests += 1
            svc.last_request = time.time()
        return Response(out, status_code=code, media_type=ctype)

    return app


def main(port: int, upstream_url: str = "", key: str | None = None, log_dir: str = ".") -> None:
    import uvicorn

    model = knobs.knob("MODEL_NAME")
    weights = knobs.knob("VL_MODEL_DIR") or None
    up = None
    if not upstream_url:
        if not weights:
            raise Refusal("VL_MODEL_DIR is empty and no upstream was named")
        up = Upstream(weights, model, knobs.number("PORT", kind=int), os.path.join(log_dir, "vllm.log"))
        up.start()
        upstream_url = up.url
    svc = Service(upstream_url, model, weights if up is not None else None, key, up)
    try:
        took = svc.wait_ready()
        log(f"vLLM answers as {model} after {took:.0f} s")
        deadman.watch(lambda: svc.last_request, float(os.environ.get("BOOKSMITH_IDLE_S") or 0))
        uvicorn.run(create_app(svc), host="0.0.0.0", port=port)
    finally:
        if up is not None:
            up.stop()
