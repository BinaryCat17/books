"""The application: the settings, the database, the pool, the routes, and
the map from the tree's exceptions to statuses -- a refusal is a 409, an
unmeasurable thing a 422, a stopped job a 499, as the command line's exit
codes tell them apart.
"""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from booksmith.core.errors import BooksmithError, Cancelled, Refusal, Unmeasurable
from booksmith.web.db import Db
from booksmith.web.jobs import Pool
from booksmith.web.routes import router
from booksmith.web.settings import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    app = FastAPI(title="booksmith", docs_url="/api/docs", openapi_url="/api/openapi.json")
    app.state.settings = settings
    app.state.db = Db(settings.db_path)
    app.state.pool = Pool(app.state.db, settings.workers)
    app.include_router(router)

    @app.exception_handler(Refusal)
    def _refusal(_r: Request, e: Refusal) -> JSONResponse:
        return JSONResponse({"error": str(e)}, status_code=409)

    @app.exception_handler(Unmeasurable)
    def _unmeasurable(_r: Request, e: Unmeasurable) -> JSONResponse:
        return JSONResponse({"error": str(e)}, status_code=422)

    @app.exception_handler(Cancelled)
    def _cancelled(_r: Request, e: Cancelled) -> JSONResponse:
        return JSONResponse({"error": str(e)}, status_code=499)

    @app.exception_handler(BooksmithError)
    def _other(_r: Request, e: BooksmithError) -> JSONResponse:
        return JSONResponse({"error": str(e)}, status_code=409)

    return app


def serve(host: str, port: int) -> int:
    import uvicorn
    uvicorn.run(create_app(), host=host, port=port, log_level="info")
    return 0
