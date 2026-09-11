import os
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
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
        from fleet.vast import Vast

        v = Vast()
        if v.available():
            out["vast"] = v
    except Exception as e:
        log(f"vast is not available: {e}")
    return out


class Lease(BaseModel):
    model: str
    job: str


class JobRef(BaseModel):
    job: str


def create_app(fleet: Fleet | None = None, sweep_s: float | None = None) -> FastAPI:
    stop = threading.Event()

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

    @app.exception_handler(BooksmithError)
    def _refusal(_r: Request, e: BooksmithError) -> JSONResponse:
        return JSONResponse({"error": str(e)}, status_code=409)

    @app.get("/models")
    def get_models() -> dict:
        return registry.load()

    @app.put("/models")
    def put_models(body: dict) -> dict:
        return registry.save(body)

    @app.post("/leases")
    def lease(body: Lease, request: Request) -> dict:
        return request.app.state.fleet.ensure(body.model, body.job)

    @app.post("/leases/renew")
    def renew(body: JobRef, request: Request) -> dict:
        return {"renewed": request.app.state.fleet.renew(body.job)}

    @app.post("/leases/release")
    def release(body: JobRef, request: Request) -> dict:
        return {"released": request.app.state.fleet.release(body.job)}

    @app.get("/leases")
    def leases(request: Request) -> list[dict]:
        return request.app.state.fleet.leases()

    @app.get("/placements")
    def placements(request: Request) -> list[dict]:
        return [{k: v for k, v in p.items() if k != "key"} for p in request.app.state.fleet.placements()]

    @app.delete("/placements/{pid}")
    def stop_placement(pid: str, request: Request) -> dict:
        request.app.state.fleet.stop(pid)
        return {"stopped": pid}

    @app.post("/reconcile")
    def reconcile(request: Request) -> dict:
        return request.app.state.fleet.reconcile()

    @app.post("/sweep")
    def sweep(request: Request) -> dict:
        return {"stopped": request.app.state.fleet.sweep()}

    @app.get("/ledger")
    def ledger(request: Request) -> list[dict]:
        return request.app.state.fleet.ledger()

    @app.get("/health")
    def health(request: Request) -> dict:
        f = getattr(request.app.state, "fleet", None)
        if f is None:
            raise Refusal("starting")
        return {"ready": True, "providers": sorted(f.providers), "placements": len(f.placements())}

    return app
