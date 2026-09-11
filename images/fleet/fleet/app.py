import hmac
import os
import threading
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from fleet import registry
from fleet.docker import Docker
from fleet.errors import BooksmithError, Refusal
from fleet.log import log
from fleet.placements import Fleet


def providers() -> dict:
    out = {}
    d = Docker(os.environ.get("FLEET_DOCKER_NETWORK") or "")
    if d.available():
        out["docker"] = d
    try:
        from fleet.vast import Vast, key_present

        if key_present():
            v = Vast()
            out["vast"] = v
            if not v.available():
                log("vast: the key is present but the account did not answer; placements are kept")
    except Exception as e:
        log(f"vast is not available: {e}")
    return out


class Lease(BaseModel):
    model: str
    job: str
    wait_s: float = 60.0


class JobRef(BaseModel):
    job: str


def create_app(fleet: Fleet | None = None, sweep_s: float | None = None, key: str | None = None) -> FastAPI:
    stop = threading.Event()
    key = os.environ.get("FLEET_KEY") if key is None else key

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.fleet = fleet or Fleet(providers())
        log(f"providers: {sorted(app.state.fleet.providers)}; reconcile: {app.state.fleet.reconcile()}")
        every = sweep_s if sweep_s is not None else float(os.environ.get("FLEET_SWEEP_S") or 30)

        def sweeper():
            while not stop.wait(every):
                try:
                    app.state.fleet.sweep()
                except Exception as e:
                    log(f"sweep: {e}")

        threading.Thread(target=sweeper, daemon=True).start()
        yield
        stop.set()

    app = FastAPI(title="fleet", lifespan=lifespan)

    def allowed(authorization: str | None = Header(default=None)) -> None:
        if key and not (authorization and hmac.compare_digest(authorization, "Bearer " + key)):
            raise HTTPException(401, "a key is required, and this is not it")

    guard = [Depends(allowed)]

    @app.exception_handler(BooksmithError)
    def _refusal(_r: Request, e: BooksmithError) -> JSONResponse:
        return JSONResponse({"error": str(e)}, status_code=409)

    @app.get("/models", dependencies=guard)
    def get_models() -> dict:
        return registry.load()

    @app.put("/models", dependencies=guard)
    def put_models(body: dict) -> dict:
        return registry.save(body)

    @app.post("/leases", dependencies=guard)
    def lease(body: Lease, request: Request) -> JSONResponse:
        got = request.app.state.fleet.ensure(body.model, body.job, min(max(body.wait_s, 0.0), 1200.0))
        return JSONResponse(got, status_code=202 if got["state"] == "starting" else 200)

    @app.post("/leases/renew", dependencies=guard)
    def renew(body: JobRef, request: Request) -> dict:
        return {"renewed": request.app.state.fleet.renew(body.job)}

    @app.post("/leases/release", dependencies=guard)
    def release(body: JobRef, request: Request) -> dict:
        return {"released": request.app.state.fleet.release(body.job)}

    @app.get("/leases", dependencies=guard)
    def leases(request: Request) -> list[dict]:
        return request.app.state.fleet.leases()

    @app.get("/placements", dependencies=guard)
    def placements(request: Request) -> list[dict]:
        return [{k: v for k, v in p.items() if k != "key"} for p in request.app.state.fleet.placements()]

    @app.delete("/placements/{pid}", dependencies=guard)
    def stop_placement(pid: str, request: Request) -> dict:
        request.app.state.fleet.stop(pid)
        return {"stopped": pid}

    @app.post("/reconcile", dependencies=guard)
    def reconcile(request: Request) -> dict:
        return request.app.state.fleet.reconcile()

    @app.post("/sweep", dependencies=guard)
    def sweep(request: Request) -> dict:
        return {"stopped": request.app.state.fleet.sweep()}

    @app.get("/ledger", dependencies=guard)
    def ledger(request: Request) -> list[dict]:
        return request.app.state.fleet.ledger()

    @app.get("/health")
    def health(request: Request) -> dict:
        f = getattr(request.app.state, "fleet", None)
        if f is None:
            raise Refusal("starting")
        return {"ready": True, "providers": sorted(f.providers), "placements": len(f.placements())}

    return app
