import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from fleet import settings
from fleet.errors import BooksmithError


def create_app() -> FastAPI:
    app = FastAPI(title="fleet")

    @app.exception_handler(BooksmithError)
    def _refusal(_r: Request, e: BooksmithError) -> JSONResponse:
        return JSONResponse({"error": str(e)}, status_code=409)

    @app.get("/placements")
    def placements() -> list:
        return []

    @app.get("/health")
    def health() -> dict:
        return {"ready": True, "home": os.path.isdir(settings.home())}

    return app
