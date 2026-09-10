"""The model manager: the registry now; placements and leases next"""

import json
import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from fleet import settings
from fleet.errors import BooksmithError, Refusal
from fleet.files import write_json

KINDS = ("layout", "reader", "hybrid")


def registry(raw: object) -> dict:
    if not isinstance(raw, dict):
        raise Refusal("the registry is a mapping of names to entries")
    out = {}
    for name, e in raw.items():
        if not isinstance(e, dict) or e.get("kind") not in KINDS:
            raise Refusal(f"{name}: an entry names a kind, one of {KINDS}")
        has_endpoint, has_image = bool(e.get("endpoint")), bool(e.get("image"))
        if has_endpoint == has_image:
            raise Refusal(f"{name}: an endpoint or an image with a provider, not both and not neither")
        if has_image and not e.get("provider"):
            raise Refusal(f"{name}: an image names its provider")
        knobs = e.get("knobs") or {}
        if not isinstance(knobs, dict):
            raise Refusal(f"{name}: knobs are a mapping")
        out[name] = {**e, "knobs": {k: str(v) for k, v in knobs.items()}}
    return out


def models_path() -> str:
    return os.path.join(settings.home(), "models.json")


def models() -> dict:
    if not os.path.isfile(models_path()):
        return {}
    with open(models_path(), encoding="utf-8") as f:
        return registry(json.load(f))


def create_app() -> FastAPI:
    app = FastAPI(title="fleet")

    @app.exception_handler(BooksmithError)
    def _refusal(_r: Request, e: BooksmithError) -> JSONResponse:
        return JSONResponse({"error": str(e)}, status_code=409)

    @app.get("/models")
    def get_models() -> dict:
        return models()

    @app.put("/models")
    def put_models(body: dict) -> dict:
        checked = registry(body)
        write_json(models_path(), checked, indent=1)
        return checked

    @app.get("/placements")
    def placements() -> list:
        return []

    return app
