from __future__ import annotations

import os
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from backend.errors import BooksmithError, Cancelled, Refusal, Unmeasurable
from backend import auth
from backend.db import Db
from backend.pool import Pool
from backend.routes import router
from backend.settings import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    app = FastAPI(title="backend", docs_url="/api/docs", openapi_url="/api/openapi.json")
    app.state.settings = settings
    app.state.db = Db(settings.db_path)
    app.state.pool = Pool(app.state.db, settings)
    app.include_router(router)
    first = os.environ.get("BOOKSMITH_ADMIN") or ""
    if first and not app.state.db.users():
        name, _, password = first.partition(":")
        auth.add_user(app.state.db, name, password, "admin")
        app.state.settings.store_of(1, "admin")

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
